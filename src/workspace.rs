use std::{
    env,
    path::{Path, PathBuf},
    process::Command,
};

use anyhow::{Context, Result};

pub fn resolve_root(input: Option<PathBuf>) -> Result<PathBuf> {
    let mut start = if let Some(path) = input {
        path
    } else if let Some(path) = env::var_os("CODEINTEL_ROOT") {
        PathBuf::from(path)
    } else if let Some(path) = env::var_os("CLAUDE_PROJECT_DIR") {
        PathBuf::from(path)
    } else {
        env::current_dir().context("failed to determine current directory")?
    };

    if start.is_file() {
        start = start.parent().unwrap_or(Path::new(".")).to_path_buf();
    }

    let canonical = start
        .canonicalize()
        .with_context(|| format!("workspace path does not exist: {}", start.display()))?;

    let output = Command::new("git")
        .arg("-C")
        .arg(&canonical)
        .args(["rev-parse", "--show-toplevel"])
        .output();

    if let Ok(output) = output
        && output.status.success()
    {
        let root = String::from_utf8_lossy(&output.stdout).trim().to_owned();

        if !root.is_empty() {
            return Ok(PathBuf::from(root));
        }
    }

    Ok(canonical)
}
