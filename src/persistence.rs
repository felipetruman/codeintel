use std::{
    fs::{self, File, OpenOptions},
    io::Write,
    path::{Path, PathBuf},
    process,
    sync::atomic::{AtomicU64, Ordering},
};

use anyhow::{Context, Result};

use serde::Serialize;

static TEMP_COUNTER: AtomicU64 = AtomicU64::new(0);

pub fn atomic_write_json<T>(path: &Path, value: &T) -> Result<()>
where
    T: Serialize + ?Sized,
{
    let parent = path.parent().context("atomic JSON path has no parent")?;

    fs::create_dir_all(parent).with_context(|| format!("cannot create {}", parent.display()))?;

    let temp = temporary_path(path)?;

    let result = write_and_replace(path, &temp, value);

    if result.is_err() {
        let _ = fs::remove_file(&temp);
    }

    result
}

fn write_and_replace<T>(path: &Path, temp: &Path, value: &T) -> Result<()>
where
    T: Serialize + ?Sized,
{
    let bytes = serde_json::to_vec(value)
        .with_context(|| format!("cannot serialize {}", path.display()))?;

    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(temp)
        .with_context(|| format!("cannot create temporary {}", temp.display()))?;

    file.write_all(&bytes)
        .with_context(|| format!("cannot write temporary {}", temp.display()))?;

    file.flush()
        .with_context(|| format!("cannot flush temporary {}", temp.display()))?;

    file.sync_all()
        .with_context(|| format!("cannot sync temporary {}", temp.display()))?;

    drop(file);

    fs::rename(temp, path)
        .with_context(|| format!("cannot atomically replace {}", path.display()))?;

    // Best-effort directory sync so the rename itself is
    // durable on filesystems that support syncing directories.
    if let Ok(directory) = File::open(path.parent().unwrap_or_else(|| Path::new("."))) {
        let _ = directory.sync_all();
    }

    Ok(())
}

fn temporary_path(path: &Path) -> Result<PathBuf> {
    let parent = path.parent().context("atomic JSON path has no parent")?;

    let filename = path
        .file_name()
        .context("atomic JSON path has no filename")?
        .to_string_lossy();

    for _ in 0..100 {
        let counter = TEMP_COUNTER.fetch_add(1, Ordering::Relaxed);

        let candidate = parent.join(format!(".{filename}.tmp-{}-{counter}", process::id(),));

        if !candidate.exists() {
            return Ok(candidate);
        }
    }

    anyhow::bail!(
        "could not allocate atomic temporary path for {}",
        path.display()
    )
}
