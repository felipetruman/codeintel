use std::{path::Path, sync::mpsc, thread, time::Duration};

use anyhow::{Context, Result};

use notify::{Event, RecursiveMode, Watcher};

use crate::freshness::{FreshIndexSet, ensure_fresh_indexes};

const DEBOUNCE_MS: u64 = 250;

pub fn refresh_once(root: &Path) -> Result<FreshIndexSet> {
    ensure_fresh_indexes(root)
}

pub fn serve(root: &Path) -> Result<()> {
    println!("codeintel: ensuring fresh indexes");

    let fresh = refresh_once(root)?;

    println!(
        "codeintel: watching {} ({} files, {} definitions, {} graph nodes; reused={}, added={}, modified={}, deleted={}, reparsed={})",
        root.display(),
        fresh.lexical.files.len(),
        fresh.structural.definitions.len(),
        fresh.graph.nodes.len(),
        fresh.stats.reused,
        fresh.stats.added,
        fresh.stats.modified,
        fresh.stats.deleted,
        fresh.stats.reparsed,
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
                if codeintel_only_event(&event) {
                    continue;
                }

                thread::sleep(Duration::from_millis(DEBOUNCE_MS));

                drain_pending_events(&rx);

                match refresh_once(root) {
                    Ok(fresh) => {
                        println!(
                            "codeintel: indexes refreshed ({} files, {} definitions, {} graph nodes; reused={}, added={}, modified={}, deleted={}, reparsed={})",
                            fresh.lexical.files.len(),
                            fresh.structural.definitions.len(),
                            fresh.graph.nodes.len(),
                            fresh.stats.reused,
                            fresh.stats.added,
                            fresh.stats.modified,
                            fresh.stats.deleted,
                            fresh.stats.reparsed,
                        );
                    }

                    Err(error) => {
                        eprintln!("codeintel: refresh failed: {error:#}");
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

fn codeintel_only_event(event: &Event) -> bool {
    !event.paths.is_empty()
        && event.paths.iter().all(|path| {
            path.components()
                .any(|component| component.as_os_str() == ".codeintel")
        })
}

fn drain_pending_events(rx: &mpsc::Receiver<notify::Result<Event>>) {
    while let Ok(event) = rx.try_recv() {
        if let Err(error) = event {
            eprintln!("codeintel: watcher error during debounce: {error}");
        }
    }
}
