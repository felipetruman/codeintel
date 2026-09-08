use std::{
    collections::BTreeMap,
    fs::{self, File},
    io::BufReader,
    path::{Path, PathBuf},
    time::UNIX_EPOCH,
};

use anyhow::{Context, Result};

use ignore::WalkBuilder;

use serde::{Deserialize, Serialize};

pub const MANIFEST_FILE: &str = "manifest.json";

pub const MANIFEST_SCHEMA_VERSION: u32 = 1;

const MAX_FILE_BYTES: u64 = 4 * 1024 * 1024;

const BINARY_SNIFF_BYTES: usize = 8192;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct FileFingerprint {
    pub size: u64,
    pub modified_ns: u64,
    pub content_hash: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct IndexManifest {
    pub schema_version: u32,
    pub root: String,

    pub files: BTreeMap<String, FileFingerprint>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq, Eq)]
pub struct ChangeSet {
    pub unchanged: Vec<String>,
    pub added: Vec<String>,
    pub modified: Vec<String>,
    pub deleted: Vec<String>,
}

impl ChangeSet {
    pub fn has_changes(&self) -> bool {
        !self.added.is_empty() || !self.modified.is_empty() || !self.deleted.is_empty()
    }
}

impl IndexManifest {
    pub fn save(&self, root: &Path) -> Result<()> {
        let path = manifest_path(root);

        crate::persistence::atomic_write_json(&path, self)
    }

    pub fn load(root: &Path) -> Result<Self> {
        let path = manifest_path(root);

        let file = File::open(&path).with_context(|| format!("cannot open {}", path.display()))?;

        serde_json::from_reader(BufReader::new(file))
            .with_context(|| format!("cannot decode {}", path.display()))
    }

    pub fn is_compatible(&self, root: &Path) -> bool {
        if self.schema_version != MANIFEST_SCHEMA_VERSION {
            return false;
        }

        let Ok(root) = root.canonicalize() else {
            return false;
        };

        self.root == root.to_string_lossy()
    }
}

pub fn scan_manifest(root: &Path) -> Result<IndexManifest> {
    scan_manifest_internal(root, None)
}

pub fn scan_manifest_incremental(root: &Path, previous: &IndexManifest) -> Result<IndexManifest> {
    if !previous.is_compatible(root) {
        return scan_manifest(root);
    }

    scan_manifest_internal(root, Some(previous))
}

fn scan_manifest_internal(root: &Path, previous: Option<&IndexManifest>) -> Result<IndexManifest> {
    let root = root
        .canonicalize()
        .with_context(|| format!("cannot canonicalize {}", root.display()))?;

    let walker = WalkBuilder::new(&root)
        .hidden(true)
        .parents(true)
        .git_ignore(true)
        .git_global(true)
        .git_exclude(true)
        .build();

    let mut files = BTreeMap::new();

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

        let relative = path
            .strip_prefix(&root)
            .unwrap_or(path)
            .to_string_lossy()
            .to_string();

        let modified_ns = modified_ns(&metadata);

        if let Some(previous) = previous
            && let Some(old) = previous.files.get(&relative)
            && old.size == metadata.len()
            && old.modified_ns == modified_ns
        {
            files.insert(relative, old.clone());

            continue;
        }

        let Ok(bytes) = fs::read(path) else {
            continue;
        };

        if is_binary(&bytes) {
            continue;
        }

        files.insert(
            relative,
            FileFingerprint {
                size: metadata.len(),

                modified_ns,

                content_hash: fnv1a64(&bytes),
            },
        );
    }

    Ok(IndexManifest {
        schema_version: MANIFEST_SCHEMA_VERSION,

        root: root.to_string_lossy().to_string(),

        files,
    })
}

pub fn compare_manifests(old: &IndexManifest, new: &IndexManifest) -> ChangeSet {
    let mut changes = ChangeSet::default();

    for (path, fingerprint) in &new.files {
        match old.files.get(path) {
            None => {
                changes.added.push(path.clone());
            }

            Some(previous) if previous == fingerprint => {
                changes.unchanged.push(path.clone());
            }

            Some(_) => {
                changes.modified.push(path.clone());
            }
        }
    }

    for path in old.files.keys() {
        if !new.files.contains_key(path) {
            changes.deleted.push(path.clone());
        }
    }

    changes
}

pub fn manifest_path(root: &Path) -> PathBuf {
    root.join(".codeintel").join(MANIFEST_FILE)
}

fn modified_ns(metadata: &fs::Metadata) -> u64 {
    metadata
        .modified()
        .ok()
        .and_then(|time| time.duration_since(UNIX_EPOCH).ok())
        .map(|duration| duration.as_nanos())
        .and_then(|value| u64::try_from(value).ok())
        .unwrap_or_default()
}

fn fnv1a64(bytes: &[u8]) -> u64 {
    let mut hash = 0xcbf29ce484222325_u64;

    for byte in bytes {
        hash ^= u64::from(*byte);

        hash = hash.wrapping_mul(0x100000001b3);
    }

    hash
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
