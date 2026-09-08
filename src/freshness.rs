use std::{collections::BTreeSet, path::Path};

use anyhow::{Context, Result};

use serde::{Deserialize, Serialize};

use crate::{
    graph::GraphIndex,
    index::CodeIndex,
    manifest::{IndexManifest, compare_manifests, scan_manifest, scan_manifest_incremental},
    structural::{SourceLanguage, StructuralIndex},
};

#[derive(Debug, Clone, Copy, Default, Serialize, Deserialize, PartialEq, Eq)]
pub struct RefreshStats {
    pub scanned: usize,
    pub reused: usize,
    pub added: usize,
    pub modified: usize,
    pub deleted: usize,
    pub reparsed: usize,
}

#[derive(Debug, Clone)]
pub struct FreshIndexSet {
    pub lexical: CodeIndex,
    pub structural: StructuralIndex,
    pub graph: GraphIndex,
    pub stats: RefreshStats,
}

pub fn ensure_fresh_indexes(root: &Path) -> Result<FreshIndexSet> {
    let root = root
        .canonicalize()
        .with_context(|| format!("cannot canonicalize freshness root {}", root.display()))?;

    let previous_state = load_compatible_state(&root);

    let Some((previous_manifest, previous_lexical, previous_structural, previous_graph)) =
        previous_state
    else {
        return full_rebuild(&root);
    };

    let current_manifest = scan_manifest_incremental(&root, &previous_manifest)?;

    let changes = compare_manifests(&previous_manifest, &current_manifest);

    if !changes.has_changes() {
        return Ok(FreshIndexSet {
            stats: RefreshStats {
                scanned: current_manifest.files.len(),

                reused: changes.unchanged.len(),

                added: 0,
                modified: 0,
                deleted: 0,
                reparsed: 0,
            },

            lexical: previous_lexical,

            structural: previous_structural,

            graph: previous_graph,
        });
    }

    let (lexical, _lexical_stats) =
        CodeIndex::refresh_incremental(&root, &previous_lexical, &changes)?;

    let (structural, structural_stats) = StructuralIndex::refresh_incremental(
        &root,
        &previous_structural,
        &lexical.files,
        &changes,
    )?;

    let graph = GraphIndex::build(&structural);

    persist_state(&root, &lexical, &structural, &graph, &current_manifest)?;

    Ok(FreshIndexSet {
        stats: RefreshStats {
            scanned: current_manifest.files.len(),

            reused: changes.unchanged.len(),

            added: changes.added.len(),

            modified: changes.modified.len(),

            deleted: changes.deleted.len(),

            reparsed: structural_stats.reparsed,
        },

        lexical,
        structural,
        graph,
    })
}

fn load_compatible_state(
    root: &Path,
) -> Option<(IndexManifest, CodeIndex, StructuralIndex, GraphIndex)> {
    let manifest = IndexManifest::load(root).ok()?;

    if !manifest.is_compatible(root) {
        return None;
    }

    let lexical = CodeIndex::load(root).ok()?;

    let structural = StructuralIndex::load(root).ok()?;

    let graph = GraphIndex::load(root).ok()?;

    if !roots_match(root, &lexical, &structural, &graph) {
        return None;
    }

    if !lexical_cache_complete(&lexical) {
        return None;
    }

    if !structural_cache_complete(&lexical, &structural) {
        return None;
    }

    if !graph_matches_structural(&structural, &graph) {
        return None;
    }

    Some((manifest, lexical, structural, graph))
}

fn roots_match(
    root: &Path,
    lexical: &CodeIndex,
    structural: &StructuralIndex,
    graph: &GraphIndex,
) -> bool {
    let expected = root.to_string_lossy();

    lexical.root == expected && structural.root == expected && graph.root == expected
}

fn lexical_cache_complete(lexical: &CodeIndex) -> bool {
    lexical
        .files
        .iter()
        .all(|path| lexical.file_trigrams.contains_key(path))
        && lexical.file_trigrams.len() == lexical.files.len()
}

fn structural_cache_complete(lexical: &CodeIndex, structural: &StructuralIndex) -> bool {
    lexical
        .files
        .iter()
        .filter(|path| SourceLanguage::from_path(path).is_some())
        .all(|path| structural.file_data.contains_key(path))
}

fn graph_matches_structural(structural: &StructuralIndex, graph: &GraphIndex) -> bool {
    let structural_ids: BTreeSet<u64> = structural
        .definitions
        .iter()
        .map(|symbol| symbol.id)
        .collect();

    let graph_ids: BTreeSet<u64> = graph.nodes.keys().copied().collect();

    structural_ids == graph_ids
}

fn full_rebuild(root: &Path) -> Result<FreshIndexSet> {
    let manifest = scan_manifest(root)?;

    let lexical = CodeIndex::build(root)?;

    let structural = StructuralIndex::build(root, &lexical.files)?;

    let graph = GraphIndex::build(&structural);

    persist_state(root, &lexical, &structural, &graph, &manifest)?;

    let reparsed = structural.file_data.len();

    Ok(FreshIndexSet {
        stats: RefreshStats {
            scanned: manifest.files.len(),

            reused: 0,

            added: manifest.files.len(),

            modified: 0,
            deleted: 0,
            reparsed,
        },

        lexical,
        structural,
        graph,
    })
}

fn persist_state(
    root: &Path,
    lexical: &CodeIndex,
    structural: &StructuralIndex,
    graph: &GraphIndex,
    manifest: &IndexManifest,
) -> Result<()> {
    // Manifest is persisted last and acts as the
    // commit marker for the coherent index generation.
    lexical.save()?;

    structural.save()?;

    graph.save(root)?;

    manifest.save(root)?;

    Ok(())
}
