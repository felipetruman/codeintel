use std::{
    collections::BTreeSet,
    env,
    path::{Path, PathBuf},
};

use anyhow::Result;
use serde::Serialize;

use crate::{
    graph::{GraphIndex, graph_path},
    index::{CodeIndex, index_path},
    manifest::{IndexManifest, compare_manifests, manifest_path, scan_manifest_incremental},
    structural::{SourceLanguage, StructuralIndex, structural_path},
};

#[derive(Debug, Serialize)]
pub struct DoctorCheck {
    pub name: String,
    pub status: String,
    pub detail: String,
}

pub fn run(root: &Path) -> Result<Vec<DoctorCheck>> {
    let canonical = root.canonicalize()?;

    let expected_root = canonical.to_string_lossy().to_string();

    let mut checks = vec![
        command_check("git"),
        command_check("rg"),
        command_check("claude"),
        command_check("codex"),
    ];

    let (manifest_check, manifest) = inspect_manifest(&canonical);

    checks.push(manifest_check);

    let (lexical_check, lexical) = inspect_lexical(&canonical, &expected_root);

    checks.push(lexical_check);

    let (structural_check, structural) = inspect_structural(&canonical, &expected_root);

    checks.push(structural_check);

    let (graph_check, graph) = inspect_graph(&canonical, &expected_root);

    checks.push(graph_check);

    checks.push(freshness_check(
        &canonical,
        manifest.as_ref(),
        lexical.as_ref(),
        structural.as_ref(),
        graph.as_ref(),
    ));

    checks.push(DoctorCheck {
        name: "workspace".into(),

        status: "ok".into(),

        detail: canonical.display().to_string(),
    });

    Ok(checks)
}

fn inspect_manifest(root: &Path) -> (DoctorCheck, Option<IndexManifest>) {
    let path = manifest_path(root);

    if !path.exists() {
        return (
            DoctorCheck {
                name: "manifest".into(),

                status: "missing".into(),

                detail: path.display().to_string(),
            },
            None,
        );
    }

    match IndexManifest::load(root) {
        Ok(manifest) => {
            if !manifest.is_compatible(root) {
                return (
                    DoctorCheck {
                        name: "manifest".into(),

                        status: "incompatible".into(),

                        detail: format!(
                            "{} schema={} root={}",
                            path.display(),
                            manifest.schema_version,
                            manifest.root,
                        ),
                    },
                    None,
                );
            }

            let detail = format!(
                "{} schema={} files={}",
                path.display(),
                manifest.schema_version,
                manifest.files.len(),
            );

            (
                DoctorCheck {
                    name: "manifest".into(),

                    status: "ok".into(),

                    detail,
                },
                Some(manifest),
            )
        }

        Err(error) => (
            DoctorCheck {
                name: "manifest".into(),

                status: "corrupt".into(),

                detail: format!("{}: {error:#}", path.display(),),
            },
            None,
        ),
    }
}

fn inspect_lexical(root: &Path, expected_root: &str) -> (DoctorCheck, Option<CodeIndex>) {
    let path = index_path(root);

    if !path.exists() {
        return (missing_check("lexical_index", &path), None);
    }

    match CodeIndex::load(root) {
        Ok(index) if index.root == expected_root => {
            let detail = format!(
                "{} files={} cached_files={}",
                path.display(),
                index.files.len(),
                index.file_trigrams.len(),
            );

            (
                DoctorCheck {
                    name: "lexical_index".into(),

                    status: "ok".into(),

                    detail,
                },
                Some(index),
            )
        }

        Ok(index) => (
            DoctorCheck {
                name: "lexical_index".into(),

                status: "incompatible".into(),

                detail: format!("{} root={}", path.display(), index.root,),
            },
            None,
        ),

        Err(error) => (corrupt_check("lexical_index", &path, &error), None),
    }
}

fn inspect_structural(root: &Path, expected_root: &str) -> (DoctorCheck, Option<StructuralIndex>) {
    let path = structural_path(root);

    if !path.exists() {
        return (missing_check("structural_index", &path), None);
    }

    match StructuralIndex::load(root) {
        Ok(index) if index.root == expected_root => {
            let detail = format!(
                "{} files={} definitions={} references={}",
                path.display(),
                index.file_data.len(),
                index.definitions.len(),
                index.references.len(),
            );

            (
                DoctorCheck {
                    name: "structural_index".into(),

                    status: "ok".into(),

                    detail,
                },
                Some(index),
            )
        }

        Ok(index) => (
            DoctorCheck {
                name: "structural_index".into(),

                status: "incompatible".into(),

                detail: format!("{} root={}", path.display(), index.root,),
            },
            None,
        ),

        Err(error) => (corrupt_check("structural_index", &path, &error), None),
    }
}

fn inspect_graph(root: &Path, expected_root: &str) -> (DoctorCheck, Option<GraphIndex>) {
    let path = graph_path(root);

    if !path.exists() {
        return (missing_check("graph_index", &path), None);
    }

    match GraphIndex::load(root) {
        Ok(index) if index.root == expected_root => {
            let detail = format!(
                "{} nodes={} pagerank={}",
                path.display(),
                index.nodes.len(),
                index.pagerank.len(),
            );

            (
                DoctorCheck {
                    name: "graph_index".into(),

                    status: "ok".into(),

                    detail,
                },
                Some(index),
            )
        }

        Ok(index) => (
            DoctorCheck {
                name: "graph_index".into(),

                status: "incompatible".into(),

                detail: format!("{} root={}", path.display(), index.root,),
            },
            None,
        ),

        Err(error) => (corrupt_check("graph_index", &path, &error), None),
    }
}

fn freshness_check(
    root: &Path,
    manifest: Option<&IndexManifest>,
    lexical: Option<&CodeIndex>,
    structural: Option<&StructuralIndex>,
    graph: Option<&GraphIndex>,
) -> DoctorCheck {
    let Some(manifest) = manifest else {
        let manifest_path = manifest_path(root);

        let status = if manifest_path.exists() {
            "invalid"
        } else {
            "missing"
        };

        return DoctorCheck {
            name: "index_freshness".into(),

            status: status.into(),

            detail: if status == "missing" {
                "manifest is missing".into()
            } else {
                "manifest is corrupt or incompatible".into()
            },
        };
    };

    let (Some(lexical), Some(structural), Some(graph)) = (lexical, structural, graph) else {
        return DoctorCheck {
            name: "index_freshness".into(),

            status: "incomplete".into(),

            detail: "one or more persistent indexes are missing, corrupt, or incompatible".into(),
        };
    };

    if let Some(detail) = coherence_problem(lexical, structural, graph) {
        return DoctorCheck {
            name: "index_freshness".into(),

            status: "incomplete".into(),

            detail,
        };
    }

    let current = match scan_manifest_incremental(root, manifest) {
        Ok(current) => current,

        Err(error) => {
            return DoctorCheck {
                name: "index_freshness".into(),

                status: "error".into(),

                detail: format!("freshness scan failed: {error:#}"),
            };
        }
    };

    let changes = compare_manifests(manifest, &current);

    if changes.has_changes() {
        return DoctorCheck {
            name: "index_freshness".into(),

            status: "stale".into(),

            detail: format!(
                "scanned={} reused={} added={} modified={} deleted={}",
                current.files.len(),
                changes.unchanged.len(),
                changes.added.len(),
                changes.modified.len(),
                changes.deleted.len(),
            ),
        };
    }

    DoctorCheck {
        name: "index_freshness".into(),

        status: "fresh".into(),

        detail: format!(
            "scanned={} reused={} added=0 modified=0 deleted=0",
            current.files.len(),
            changes.unchanged.len(),
        ),
    }
}

fn coherence_problem(
    lexical: &CodeIndex,
    structural: &StructuralIndex,
    graph: &GraphIndex,
) -> Option<String> {
    if lexical.file_trigrams.len() != lexical.files.len()
        || lexical
            .files
            .iter()
            .any(|path| !lexical.file_trigrams.contains_key(path))
    {
        return Some("lexical per-file cache is incomplete".into());
    }

    let supported: BTreeSet<&str> = lexical
        .files
        .iter()
        .filter(|path| SourceLanguage::from_path(path).is_some())
        .map(String::as_str)
        .collect();

    if supported
        .iter()
        .any(|path| !structural.file_data.contains_key(*path))
    {
        return Some("structural per-file cache is incomplete".into());
    }

    let structural_ids: BTreeSet<u64> = structural
        .definitions
        .iter()
        .map(|symbol| symbol.id)
        .collect();

    let graph_ids: BTreeSet<u64> = graph.nodes.keys().copied().collect();

    if structural_ids != graph_ids {
        return Some("graph nodes do not match structural definitions".into());
    }

    None
}

fn missing_check(name: &str, path: &Path) -> DoctorCheck {
    DoctorCheck {
        name: name.into(),

        status: "missing".into(),

        detail: path.display().to_string(),
    }
}

fn corrupt_check(name: &str, path: &Path, error: &anyhow::Error) -> DoctorCheck {
    DoctorCheck {
        name: name.into(),

        status: "corrupt".into(),

        detail: format!("{}: {error:#}", path.display(),),
    }
}

fn command_check(command: &str) -> DoctorCheck {
    let found = executable_on_path(command);

    DoctorCheck {
        name: command.to_string(),

        status: if found { "ok".into() } else { "missing".into() },

        detail: if found {
            "available on PATH".into()
        } else {
            "not found on PATH".into()
        },
    }
}

fn executable_on_path(name: &str) -> bool {
    let Some(path) = env::var_os("PATH") else {
        return false;
    };

    env::split_paths(&path)
        .map(|directory| directory.join(name))
        .any(|candidate: PathBuf| candidate.is_file())
}
