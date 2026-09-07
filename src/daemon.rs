use std::{path::Path, sync::mpsc, thread, time::Duration};

use anyhow::{Context, Result};
use notify::{Event, RecursiveMode, Watcher};

use crate::index::CodeIndex;

pub fn serve(root: &Path) -> Result<()> {
    println!("codeintel: building initial index");

    let index = CodeIndex::rebuild(root)?;

    println!(
        "codeintel: watching {} ({} files indexed)",
        root.display(),
        index.files.len()
    );

    let (tx, rx) = mpsc::channel();

    let mut watcher = notify::recommended_watcher(move |event: notify::Result<Event>| {
        let _ = tx.send(event);
    })
    .context("failed to create filesystem watcher")?;

    watcher
        .watch(root, RecursiveMode::Recursive)
        .with_context(|| format!("failed to watch {}", root.display()))?;

    loop {
        match rx.recv() {
            Ok(Ok(event)) => {
                if event.paths.iter().all(|path| {
                    path.components()
                        .any(|component| component.as_os_str() == ".codeintel")
                }) {
                    continue;
                }

                thread::sleep(Duration::from_millis(250));

                while rx.try_recv().is_ok() {}

                match CodeIndex::rebuild(root) {
                    Ok(index) => {
                        println!("codeintel: index refreshed ({} files)", index.files.len());
                    }

                    Err(error) => {
                        eprintln!("codeintel: index refresh failed: {error:#}");
                    }
                }
            }

            Ok(Err(error)) => {
                eprintln!("codeintel: watcher error: {error}");
            }

            Err(error) => {
                return Err(error).context("filesystem watcher channel closed");
            }
        }
    }
}
