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

use crate::manifest::ChangeSet;

pub const INDEX_DIR: &str = ".codeintel";

pub const INDEX_FILE: &str = "index.json";

const MAX_FILE_BYTES: u64 = 4 * 1024 * 1024;

const BINARY_SNIFF_BYTES: usize = 8192;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CodeIndex {
    pub root: String,

    pub files: Vec<String>,

    pub postings: BTreeMap<String, Vec<u32>>,

    #[serde(default)]
    pub file_trigrams: BTreeMap<String, BTreeSet<String>>,

    pub indexed_at_unix: u64,
}

#[derive(Debug, Clone, Copy, Default, Serialize, Deserialize, PartialEq, Eq)]
pub struct LexicalRefreshStats {
    pub reused: usize,
    pub reindexed: usize,
    pub removed: usize,
}

impl CodeIndex {
    pub fn build(root: &Path) -> Result<Self> {
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

        let mut file_trigrams = BTreeMap::new();

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

            let Some((relative, trigrams)) = index_file(&root, path)? else {
                continue;
            };

            file_trigrams.insert(relative, trigrams);
        }

        Ok(Self::from_file_trigrams(&root, file_trigrams))
    }

    pub fn refresh_incremental(
        root: &Path,
        previous: &Self,
        changes: &ChangeSet,
    ) -> Result<(Self, LexicalRefreshStats)> {
        let root = root
            .canonicalize()
            .with_context(|| format!("cannot canonicalize {}", root.display()))?;

        let previous_root = PathBuf::from(&previous.root);

        if previous_root.canonicalize().ok().as_ref() != Some(&root) {
            let rebuilt = Self::build(&root)?;

            let stats = LexicalRefreshStats {
                reused: 0,
                reindexed: rebuilt.files.len(),
                removed: 0,
            };

            return Ok((rebuilt, stats));
        }

        // Legacy v0.4 indexes do not contain the
        // per-file lexical cache required for safe reuse.
        if previous.file_trigrams.len() != previous.files.len() {
            let rebuilt = Self::build(&root)?;

            let stats = LexicalRefreshStats {
                reused: 0,
                reindexed: rebuilt.files.len(),
                removed: changes.deleted.len(),
            };

            return Ok((rebuilt, stats));
        }

        let mut file_trigrams = previous.file_trigrams.clone();

        let mut stats = LexicalRefreshStats::default();

        for path in &changes.deleted {
            if file_trigrams.remove(path).is_some() {
                stats.removed += 1;
            }
        }

        for path in &changes.modified {
            file_trigrams.remove(path);

            let absolute = root.join(path);

            if let Some((relative, trigrams)) = index_file(&root, &absolute)? {
                file_trigrams.insert(relative, trigrams);

                stats.reindexed += 1;
            }
        }

        for path in &changes.added {
            let absolute = root.join(path);

            if let Some((relative, trigrams)) = index_file(&root, &absolute)? {
                file_trigrams.insert(relative, trigrams);

                stats.reindexed += 1;
            }
        }

        stats.reused = changes
            .unchanged
            .iter()
            .filter(|path| file_trigrams.contains_key(path.as_str()))
            .count();

        Ok((Self::from_file_trigrams(&root, file_trigrams), stats))
    }

    fn from_file_trigrams(root: &Path, file_trigrams: BTreeMap<String, BTreeSet<String>>) -> Self {
        let files: Vec<String> = file_trigrams.keys().cloned().collect();

        let mut postings: BTreeMap<String, Vec<u32>> = BTreeMap::new();

        for (file_id, path) in files.iter().enumerate() {
            let Some(trigrams) = file_trigrams.get(path) else {
                continue;
            };

            let file_id = file_id as u32;

            for trigram in trigrams {
                postings.entry(trigram.clone()).or_default().push(file_id);
            }
        }

        Self {
            root: root.to_string_lossy().to_string(),

            files,
            postings,
            file_trigrams,

            indexed_at_unix: current_unix_time(),
        }
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

fn index_file(root: &Path, path: &Path) -> Result<Option<(String, BTreeSet<String>)>> {
    if is_internal_path(path) {
        return Ok(None);
    }

    let metadata = match fs::metadata(path) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            return Ok(None);
        }
        Err(error) => {
            return Err(error).with_context(|| format!("cannot stat {}", path.display()));
        }
    };

    if !metadata.is_file() {
        return Ok(None);
    }

    if metadata.len() > MAX_FILE_BYTES {
        return Ok(None);
    }

    let bytes = match fs::read(path) {
        Ok(bytes) => bytes,

        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            return Ok(None);
        }

        Err(error) => {
            return Err(error).with_context(|| format!("cannot read {}", path.display()));
        }
    };

    if is_binary(&bytes) {
        return Ok(None);
    }

    let relative = path
        .strip_prefix(root)
        .unwrap_or(path)
        .to_string_lossy()
        .to_string();

    let text = String::from_utf8_lossy(&bytes);

    Ok(Some((relative, unique_trigrams(&text))))
}

fn current_unix_time() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
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
