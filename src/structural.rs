use std::{
    collections::{BTreeMap, BTreeSet},
    fs::{self, File},
    io::BufReader,
    path::{Path, PathBuf},
    time::{SystemTime, UNIX_EPOCH},
};

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use tree_sitter::{Language, Node, Parser};

pub const STRUCTURAL_FILE: &str = "structural.json";

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, PartialOrd, Ord)]
#[serde(rename_all = "snake_case")]
pub enum SourceLanguage {
    Rust,
    Python,
    JavaScript,
    TypeScript,
    Tsx,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum SymbolKind {
    Function,
    Class,
    Struct,
    Enum,
    Trait,
    Interface,
    Type,
    Module,
    Constant,
    Static,
    Method,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ReferenceKind {
    Call,
    MethodCall,
    Construct,
    Macro,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ReferenceResolution {
    SameFile,
    GlobalUnique,
    ExternalOrMethod,
    Ambiguous,
    Unresolved,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SymbolDefinition {
    pub id: u64,
    pub name: String,
    pub kind: SymbolKind,
    pub language: SourceLanguage,
    pub path: String,
    pub line: usize,
    pub column: usize,
    pub start_byte: usize,
    pub end_byte: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SymbolReference {
    pub name: String,
    pub kind: ReferenceKind,
    pub language: SourceLanguage,
    pub path: String,
    pub line: usize,
    pub column: usize,
    pub owner: Option<u64>,
    pub target: Option<u64>,
    pub resolution: ReferenceResolution,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StructuralIndex {
    pub root: String,
    pub definitions: Vec<SymbolDefinition>,
    pub references: Vec<SymbolReference>,
    pub indexed_at_unix: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SymbolView {
    pub query: String,
    pub definitions: Vec<SymbolDefinition>,
    pub callers: Vec<SymbolDefinition>,
    pub callees: Vec<SymbolDefinition>,
    pub references: Vec<SymbolReference>,
}

impl SourceLanguage {
    pub fn from_path(path: &str) -> Option<Self> {
        let extension = Path::new(path)
            .extension()?
            .to_string_lossy()
            .to_ascii_lowercase();

        match extension.as_str() {
            "rs" => Some(Self::Rust),
            "py" => Some(Self::Python),
            "js" | "jsx" | "mjs" | "cjs" => Some(Self::JavaScript),
            "ts" => Some(Self::TypeScript),
            "tsx" => Some(Self::Tsx),
            _ => None,
        }
    }

    fn tree_sitter_language(self) -> Language {
        match self {
            Self::Rust => tree_sitter_rust::LANGUAGE.into(),
            Self::Python => tree_sitter_python::LANGUAGE.into(),
            Self::JavaScript => tree_sitter_javascript::LANGUAGE.into(),
            Self::TypeScript => tree_sitter_typescript::LANGUAGE_TYPESCRIPT.into(),
            Self::Tsx => tree_sitter_typescript::LANGUAGE_TSX.into(),
        }
    }
}

impl StructuralIndex {
    pub fn build(root: &Path, files: &[String]) -> Result<Self> {
        let root = root
            .canonicalize()
            .with_context(|| format!("cannot canonicalize structural root {}", root.display()))?;

        let mut definitions = Vec::new();
        let mut references = Vec::new();

        for relative in files {
            let Some(language) = SourceLanguage::from_path(relative) else {
                continue;
            };

            let absolute = root.join(relative);

            let Ok(source) = fs::read(&absolute) else {
                continue;
            };

            let mut parser = Parser::new();
            let grammar = language.tree_sitter_language();

            parser
                .set_language(&grammar)
                .with_context(|| format!("cannot initialize parser for {relative}"))?;

            let Some(tree) = parser.parse(&source, None) else {
                continue;
            };

            walk_node(
                tree.root_node(),
                &source,
                relative,
                language,
                None,
                &mut definitions,
                &mut references,
            );
        }

        resolve_references(&definitions, &mut references);

        let indexed_at_unix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();

        Ok(Self {
            root: root.to_string_lossy().to_string(),
            definitions,
            references,
            indexed_at_unix,
        })
    }

    pub fn rebuild(root: &Path, files: &[String]) -> Result<Self> {
        let index = Self::build(root, files)?;
        index.save()?;
        Ok(index)
    }

    pub fn ensure(root: &Path, files: &[String]) -> Result<Self> {
        let path = structural_path(root);

        if path.exists() {
            return Self::load(root);
        }

        Self::rebuild(root, files)
    }

    pub fn save(&self) -> Result<()> {
        let root = PathBuf::from(&self.root);
        let path = structural_path(&root);

        crate::persistence::atomic_write_json(&path, self)
    }

    pub fn load(root: &Path) -> Result<Self> {
        let path = structural_path(root);

        let file = File::open(&path).with_context(|| format!("cannot open {}", path.display()))?;

        serde_json::from_reader(BufReader::new(file))
            .with_context(|| format!("cannot decode {}", path.display()))
    }

    pub fn find_symbols(&self, query: &str, limit: usize) -> Vec<SymbolDefinition> {
        let query = query.to_ascii_lowercase();

        self.definitions
            .iter()
            .filter(|symbol| query.is_empty() || symbol.name.to_ascii_lowercase().contains(&query))
            .take(limit)
            .cloned()
            .collect()
    }

    pub fn lookup_symbol(&self, name: &str) -> SymbolView {
        let mut definitions: Vec<SymbolDefinition> = self
            .definitions
            .iter()
            .filter(|symbol| symbol.name == name)
            .cloned()
            .collect();

        if definitions.is_empty() {
            definitions = self
                .definitions
                .iter()
                .filter(|symbol| symbol.name.eq_ignore_ascii_case(name))
                .cloned()
                .collect();
        }

        let target_ids: BTreeSet<u64> = definitions.iter().map(|symbol| symbol.id).collect();

        let by_id: BTreeMap<u64, SymbolDefinition> = self
            .definitions
            .iter()
            .map(|symbol| (symbol.id, symbol.clone()))
            .collect();

        let mut callers = BTreeMap::<u64, SymbolDefinition>::new();

        let mut callees = BTreeMap::<u64, SymbolDefinition>::new();

        let mut related_references = Vec::new();

        for reference in &self.references {
            let points_to_symbol = reference.target.is_some_and(|id| target_ids.contains(&id));

            let comes_from_symbol = reference.owner.is_some_and(|id| target_ids.contains(&id));

            if points_to_symbol
                && let Some(owner) = reference.owner
                && let Some(symbol) = by_id.get(&owner)
            {
                callers.insert(owner, symbol.clone());
            }

            if comes_from_symbol
                && let Some(target) = reference.target
                && let Some(symbol) = by_id.get(&target)
            {
                callees.insert(target, symbol.clone());
            }

            if points_to_symbol || comes_from_symbol || reference.name == name {
                related_references.push(reference.clone());
            }
        }

        SymbolView {
            query: name.to_string(),
            definitions,
            callers: callers.into_values().collect(),
            callees: callees.into_values().collect(),
            references: related_references,
        }
    }
}

pub fn structural_path(root: &Path) -> PathBuf {
    root.join(".codeintel").join(STRUCTURAL_FILE)
}

fn walk_node(
    node: Node<'_>,
    source: &[u8],
    path: &str,
    language: SourceLanguage,
    owner: Option<u64>,
    definitions: &mut Vec<SymbolDefinition>,
    references: &mut Vec<SymbolReference>,
) {
    let mut current_owner = owner;

    if let Some((name_node, kind)) = definition_for(node, language)
        && let Some(name) = node_text(name_node, source)
    {
        let point = name_node.start_position();

        let id = stable_symbol_id(path, &name, kind, name_node.start_byte());

        definitions.push(SymbolDefinition {
            id,
            name,
            kind,
            language,
            path: path.to_string(),
            line: point.row + 1,
            column: point.column + 1,
            start_byte: name_node.start_byte(),
            end_byte: name_node.end_byte(),
        });

        current_owner = Some(id);
    }

    if let Some((name_node, kind)) = reference_for(node, language)
        && let Some(name) = node_text(name_node, source)
    {
        let point = name_node.start_position();

        references.push(SymbolReference {
            name,
            kind,
            language,
            path: path.to_string(),
            line: point.row + 1,
            column: point.column + 1,
            owner: current_owner,
            target: None,
            resolution: ReferenceResolution::Unresolved,
        });
    }

    let mut cursor = node.walk();

    for child in node.named_children(&mut cursor) {
        walk_node(
            child,
            source,
            path,
            language,
            current_owner,
            definitions,
            references,
        );
    }
}

fn definition_for<'tree>(
    node: Node<'tree>,
    language: SourceLanguage,
) -> Option<(Node<'tree>, SymbolKind)> {
    match language {
        SourceLanguage::Rust => {
            let kind = match node.kind() {
                "function_item" => SymbolKind::Function,
                "struct_item" => SymbolKind::Struct,
                "enum_item" => SymbolKind::Enum,
                "trait_item" => SymbolKind::Trait,
                "type_item" => SymbolKind::Type,
                "mod_item" => SymbolKind::Module,
                "const_item" => SymbolKind::Constant,
                "static_item" => SymbolKind::Static,
                _ => return None,
            };

            node.child_by_field_name("name").map(|name| (name, kind))
        }

        SourceLanguage::Python => {
            let kind = match node.kind() {
                "function_definition" => SymbolKind::Function,
                "class_definition" => SymbolKind::Class,
                _ => return None,
            };

            node.child_by_field_name("name").map(|name| (name, kind))
        }

        SourceLanguage::JavaScript | SourceLanguage::TypeScript | SourceLanguage::Tsx => {
            match node.kind() {
                "function_declaration" | "generator_function_declaration" => node
                    .child_by_field_name("name")
                    .map(|name| (name, SymbolKind::Function)),

                "class_declaration" => node
                    .child_by_field_name("name")
                    .map(|name| (name, SymbolKind::Class)),

                "method_definition" => node
                    .child_by_field_name("name")
                    .map(|name| (name, SymbolKind::Method)),

                "interface_declaration" => node
                    .child_by_field_name("name")
                    .map(|name| (name, SymbolKind::Interface)),

                "type_alias_declaration" => node
                    .child_by_field_name("name")
                    .map(|name| (name, SymbolKind::Type)),

                "enum_declaration" => node
                    .child_by_field_name("name")
                    .map(|name| (name, SymbolKind::Enum)),

                "variable_declarator" => {
                    let name = node.child_by_field_name("name")?;

                    if name.kind() != "identifier" {
                        return None;
                    }

                    let value = node.child_by_field_name("value")?;

                    match value.kind() {
                        "arrow_function" | "function_expression" | "generator_function" => {
                            Some((name, SymbolKind::Function))
                        }
                        _ => None,
                    }
                }

                _ => None,
            }
        }
    }
}

fn reference_for<'tree>(
    node: Node<'tree>,
    language: SourceLanguage,
) -> Option<(Node<'tree>, ReferenceKind)> {
    match language {
        SourceLanguage::Rust => match node.kind() {
            "call_expression" => {
                let function = node.child_by_field_name("function")?;

                let kind = if function.kind() == "identifier" {
                    ReferenceKind::Call
                } else {
                    ReferenceKind::MethodCall
                };

                rightmost_name_node(function).map(|name| (name, kind))
            }

            "macro_invocation" => {
                let macro_node = node.child_by_field_name("macro")?;

                rightmost_name_node(macro_node).map(|name| (name, ReferenceKind::Macro))
            }

            _ => None,
        },

        SourceLanguage::Python => {
            if node.kind() != "call" {
                return None;
            }

            let function = node.child_by_field_name("function")?;

            let kind = if function.kind() == "identifier" {
                ReferenceKind::Call
            } else {
                ReferenceKind::MethodCall
            };

            rightmost_name_node(function).map(|name| (name, kind))
        }

        SourceLanguage::JavaScript | SourceLanguage::TypeScript | SourceLanguage::Tsx => {
            match node.kind() {
                "call_expression" => {
                    let function = node.child_by_field_name("function")?;

                    let kind = if function.kind() == "identifier" {
                        ReferenceKind::Call
                    } else {
                        ReferenceKind::MethodCall
                    };

                    rightmost_name_node(function).map(|name| (name, kind))
                }

                "new_expression" => {
                    let constructor = node.child_by_field_name("constructor")?;

                    let kind = if constructor.kind() == "identifier" {
                        ReferenceKind::Construct
                    } else {
                        ReferenceKind::MethodCall
                    };

                    rightmost_name_node(constructor).map(|name| (name, kind))
                }

                _ => None,
            }
        }
    }
}

fn rightmost_name_node<'tree>(node: Node<'tree>) -> Option<Node<'tree>> {
    if matches!(
        node.kind(),
        "identifier" | "field_identifier" | "property_identifier" | "type_identifier"
    ) {
        return Some(node);
    }

    let mut cursor = node.walk();
    let mut result = None;

    for child in node.named_children(&mut cursor) {
        if let Some(candidate) = rightmost_name_node(child) {
            result = Some(candidate);
        }
    }

    result
}

fn node_text(node: Node<'_>, source: &[u8]) -> Option<String> {
    let text = node.utf8_text(source).ok()?.trim();

    if text.is_empty() {
        None
    } else {
        Some(text.to_string())
    }
}

type DefinitionKey = (SourceLanguage, String);
type DefinitionCandidate = (u64, String, SymbolKind);

fn resolve_references(definitions: &[SymbolDefinition], references: &mut [SymbolReference]) {
    let mut by_name: BTreeMap<DefinitionKey, Vec<DefinitionCandidate>> = BTreeMap::new();

    for definition in definitions {
        by_name
            .entry((definition.language, definition.name.clone()))
            .or_default()
            .push((definition.id, definition.path.clone(), definition.kind));
    }

    for reference in references {
        reference.target = None;

        if reference.kind == ReferenceKind::MethodCall {
            reference.resolution = ReferenceResolution::ExternalOrMethod;
            continue;
        }

        let Some(raw_candidates) = by_name.get(&(reference.language, reference.name.clone()))
        else {
            reference.resolution = ReferenceResolution::Unresolved;
            continue;
        };

        let candidates: Vec<(u64, &str)> = raw_candidates
            .iter()
            .filter(|(_, _, symbol_kind)| reference_target_compatible(reference.kind, *symbol_kind))
            .map(|(id, path, _)| (*id, path.as_str()))
            .collect();

        if candidates.is_empty() {
            reference.resolution = ReferenceResolution::Unresolved;
            continue;
        }

        let same_file: Vec<u64> = candidates
            .iter()
            .filter(|(_, path)| *path == reference.path.as_str())
            .map(|(id, _)| *id)
            .collect();

        if same_file.len() == 1 {
            reference.target = same_file.first().copied();

            reference.resolution = ReferenceResolution::SameFile;

            continue;
        }

        if same_file.len() > 1 {
            reference.resolution = ReferenceResolution::Ambiguous;

            continue;
        }

        if candidates.len() == 1 {
            reference.target = candidates.first().map(|(id, _)| *id);

            reference.resolution = ReferenceResolution::GlobalUnique;
        } else {
            reference.resolution = ReferenceResolution::Ambiguous;
        }
    }
}

fn reference_target_compatible(reference_kind: ReferenceKind, symbol_kind: SymbolKind) -> bool {
    match reference_kind {
        ReferenceKind::Call => {
            matches!(symbol_kind, SymbolKind::Function)
        }

        ReferenceKind::Construct => {
            matches!(
                symbol_kind,
                SymbolKind::Class | SymbolKind::Struct | SymbolKind::Function
            )
        }

        ReferenceKind::MethodCall | ReferenceKind::Macro => false,
    }
}

fn stable_symbol_id(path: &str, name: &str, kind: SymbolKind, start_byte: usize) -> u64 {
    let material = format!("{path}\0{name}\0{}\0{start_byte}", symbol_kind_name(kind),);

    fnv1a(material.as_bytes())
}

fn symbol_kind_name(kind: SymbolKind) -> &'static str {
    match kind {
        SymbolKind::Function => "function",
        SymbolKind::Class => "class",
        SymbolKind::Struct => "struct",
        SymbolKind::Enum => "enum",
        SymbolKind::Trait => "trait",
        SymbolKind::Interface => "interface",
        SymbolKind::Type => "type",
        SymbolKind::Module => "module",
        SymbolKind::Constant => "constant",
        SymbolKind::Static => "static",
        SymbolKind::Method => "method",
    }
}

fn fnv1a(bytes: &[u8]) -> u64 {
    let mut hash = 0xcbf29ce484222325_u64;

    for byte in bytes {
        hash ^= u64::from(*byte);

        hash = hash.wrapping_mul(0x100000001b3);
    }

    hash
}
