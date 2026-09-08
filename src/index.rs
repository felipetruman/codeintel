use std::{
    collections::{BTreeMap, BTreeSet},
    fs::{self, File},
    io::BufReader,
    path::{Path, PathBuf},
    time::{SystemTime, UNIX_EPOCH},
};

use anyhow::{Context, Result};
use ignore::WalkBuilder;
use serde::{Deserialize, Serialize};

pub const INDEX_DIR: &str = ".codeintel";
pub const INDEX_FILE: &str = "index.json";

const MAX_FILE_BYTES: u64 = 4 * 1024 * 1024;
const BINARY_SNIFF_BYTES: usize = 8192;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CodeIndex {
    pub root: String,
    pub files: Vec<String>,
    pub postings: BTreeMap<String, Vec<u32>>,
    pub indexed_at_unix: u64,
}

impl CodeIndex {
    pub fn build(root: &Path) -> Result<Self> {
        let root = root
            .canonicalize()
            .with_context(|| format!("cannot canonicalize {}", root.display()))?;

        let mut files = Vec::new();
        let mut postings: BTreeMap<String, Vec<u32>> = BTreeMap::new();

        let walker = WalkBuilder::new(&root)
            .hidden(true)
            .parents(true)
            .git_ignore(true)
            .git_global(true)
            .git_exclude(true)
            .build();

        for entry in walker {
            let Ok(entry) = entry else {
                continue;
            };

            let Some(file_type) = entry.file_type() else {
                continue;
            };

            if !file_type.is_file() {
                continue;
            }

            let path = entry.path();

            if is_internal_path(path) {
                continue;
            }

            let Ok(metadata) = entry.metadata() else {
                continue;
            };

            if metadata.len() > MAX_FILE_BYTES {
                continue;
            }

            let Ok(bytes) = fs::read(path) else {
                continue;
            };

            if is_binary(&bytes) {
                continue;
            }

            let relative = path
                .strip_prefix(&root)
                .unwrap_or(path)
                .to_string_lossy()
                .to_string();

            let file_id = files.len() as u32;
            files.push(relative);

            let text = String::from_utf8_lossy(&bytes);

            for trigram in unique_trigrams(&text) {
                postings.entry(trigram).or_default().push(file_id);
            }
        }

        let indexed_at_unix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();

        Ok(Self {
            root: root.to_string_lossy().to_string(),
            files,
            postings,
            indexed_at_unix,
        })
    }

    pub fn ensure(root: &Path) -> Result<Self> {
        let path = index_path(root);

        if path.exists() {
            return Self::load(root);
        }

        let index = Self::build(root)?;
        index.save()?;
        Ok(index)
    }

    pub fn rebuild(root: &Path) -> Result<Self> {
        let index = Self::build(root)?;
        index.save()?;
        Ok(index)
    }

    pub fn save(&self) -> Result<()> {
        let root = PathBuf::from(&self.root);
        let path = index_path(&root);

        crate::persistence::atomic_write_json(&path, self)
    }

    pub fn load(root: &Path) -> Result<Self> {
        let path = index_path(root);

        let file = File::open(&path).with_context(|| format!("cannot open {}", path.display()))?;

        let index = serde_json::from_reader(BufReader::new(file))
            .with_context(|| format!("cannot decode {}", path.display()))?;

        Ok(index)
    }

    pub fn candidate_file_ids(&self, query: &str) -> Vec<u32> {
        if query.chars().count() < 3 {
            return (0..self.files.len() as u32).collect();
        }

        let trigrams = unique_trigrams(query);

        if trigrams.is_empty() {
            return (0..self.files.len() as u32).collect();
        }

        let mut lists: Vec<&Vec<u32>> = Vec::new();

        for trigram in &trigrams {
            let Some(posting) = self.postings.get(trigram) else {
                return Vec::new();
            };

            lists.push(posting);
        }

        lists.sort_by_key(|posting| posting.len());

        let Some(first) = lists.first() else {
            return Vec::new();
        };

        let mut candidates: BTreeSet<u32> = first.iter().copied().collect();

        for posting in lists.iter().skip(1) {
            let current: BTreeSet<u32> = posting.iter().copied().collect();

            candidates = candidates.intersection(&current).copied().collect();

            if candidates.is_empty() {
                break;
            }
        }

        candidates.into_iter().collect()
    }

    pub fn absolute_file_path(&self, file_id: u32) -> Option<PathBuf> {
        let relative = self.files.get(file_id as usize)?;
        Some(PathBuf::from(&self.root).join(relative))
    }
}

pub fn index_path(root: &Path) -> PathBuf {
    root.join(INDEX_DIR).join(INDEX_FILE)
}

fn unique_trigrams(text: &str) -> BTreeSet<String> {
    let chars: Vec<char> = text.chars().collect();

    if chars.len() < 3 {
        return BTreeSet::new();
    }

    chars
        .windows(3)
        .map(|window| window.iter().collect::<String>())
        .collect()
}

fn is_binary(bytes: &[u8]) -> bool {
    bytes.iter().take(BINARY_SNIFF_BYTES).any(|byte| *byte == 0)
}

fn is_internal_path(path: &Path) -> bool {
    path.components().any(|component| {
        matches!(
            component.as_os_str().to_str(),
            Some(".codeintel" | ".git" | "target" | "node_modules")
        )
    })
}
