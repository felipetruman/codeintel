use std::{path::Path, sync::mpsc, thread, time::Duration};

use anyhow::{Context, Result};
use notify::{Event, RecursiveMode, Watcher};

use crate::{graph::GraphIndex, index::CodeIndex, structural::StructuralIndex};

pub fn serve(root: &Path) -> Result<()> {
    println!("codeintel: building indexes");

    let lexical = CodeIndex::rebuild(root)?;

    let structural = StructuralIndex::rebuild(root, &lexical.files)?;

    let graph = GraphIndex::rebuild(root, &structural)?;

    println!(
        "codeintel: watching {} ({} files, {} definitions, {} graph nodes)",
        root.display(),
        lexical.files.len(),
        structural.definitions.len(),
        graph.nodes.len(),
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
                    Ok(lexical) => match StructuralIndex::rebuild(root, &lexical.files) {
                        Ok(structural) => match GraphIndex::rebuild(root, &structural) {
                            Ok(graph) => {
                                println!(
                                    "codeintel: indexes refreshed ({} files, {} definitions, {} graph nodes)",
                                    lexical.files.len(),
                                    structural.definitions.len(),
                                    graph.nodes.len(),
                                );
                            }

                            Err(error) => {
                                eprintln!("codeintel: graph refresh failed: {error:#}");
                            }
                        },

                        Err(error) => {
                            eprintln!("codeintel: structural refresh failed: {error:#}");
                        }
                    },

                    Err(error) => {
                        eprintln!("codeintel: lexical refresh failed: {error:#}");
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
