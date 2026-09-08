use std::path::PathBuf;

use anyhow::Result;
use clap::{Parser, Subcommand};

use codeintel::{
    context::build_hybrid_context, daemon, doctor, freshness::ensure_fresh_indexes, mcp,
    search::search_index, workspace::resolve_root,
};

#[derive(Debug, Parser)]
#[command(
    name = "codeintel",
    version,
    about = "Local code intelligence engine for agentic coding tools"
)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Debug, Subcommand)]
enum Command {
    Index {
        #[arg(default_value = ".")]
        path: PathBuf,
    },

    Search {
        query: String,

        #[arg(default_value = ".")]
        path: PathBuf,

        #[arg(long)]
        regex: bool,

        #[arg(long, default_value_t = 50)]
        limit: usize,
    },

    Context {
        task: String,

        #[arg(default_value = ".")]
        path: PathBuf,

        #[arg(long, default_value_t = 10)]
        limit: usize,
    },

    Symbols {
        #[arg(default_value = ".")]
        path: PathBuf,

        #[arg(long, default_value = "")]
        query: String,

        #[arg(long, default_value_t = 50)]
        limit: usize,
    },

    Symbol {
        name: String,

        #[arg(default_value = ".")]
        path: PathBuf,
    },

    Graph {
        #[arg(default_value = ".")]
        path: PathBuf,

        #[arg(long, default_value_t = 20)]
        limit: usize,
    },

    Impact {
        name: String,

        #[arg(default_value = ".")]
        path: PathBuf,

        #[arg(long, default_value_t = 4)]
        depth: usize,
    },

    Serve {
        #[arg(default_value = ".")]
        path: PathBuf,
    },

    Mcp {
        path: Option<PathBuf>,
    },

    Doctor {
        #[arg(default_value = ".")]
        path: PathBuf,
    },
}

fn main() -> Result<()> {
    let cli = Cli::parse();

    match cli.command {
        Command::Index { path } => {
            let root = resolve_root(Some(path))?;

            let fresh = ensure_fresh_indexes(&root)?;

            println!(
                "indexed {} files, {} definitions, {} references and {} graph nodes",
                fresh.lexical.files.len(),
                fresh.structural.definitions.len(),
                fresh.structural.references.len(),
                fresh.graph.nodes.len(),
            );

            println!(
                "fresh: scanned={} reused={} added={} modified={} deleted={} reparsed={}",
                fresh.stats.scanned,
                fresh.stats.reused,
                fresh.stats.added,
                fresh.stats.modified,
                fresh.stats.deleted,
                fresh.stats.reparsed,
            );

            println!(
                "manifest: {}",
                root.join(".codeintel/manifest.json").display()
            );

            println!("lexical: {}", root.join(".codeintel/index.json").display());

            println!(
                "structural: {}",
                root.join(".codeintel/structural.json").display()
            );

            println!("graph: {}", root.join(".codeintel/graph.json").display());
        }

        Command::Search {
            query,
            path,
            regex,
            limit,
        } => {
            let root = resolve_root(Some(path))?;

            let fresh = ensure_fresh_indexes(&root)?;

            let hits = search_index(&fresh.lexical, &query, regex, limit)?;

            println!("{}", serde_json::to_string_pretty(&hits)?);
        }

        Command::Context { task, path, limit } => {
            let root = resolve_root(Some(path))?;

            let fresh = ensure_fresh_indexes(&root)?;

            let bundle = build_hybrid_context(
                &fresh.lexical,
                &fresh.structural,
                &fresh.graph,
                &task,
                limit,
            )?;

            println!("{}", serde_json::to_string_pretty(&bundle)?);
        }

        Command::Symbols { path, query, limit } => {
            let root = resolve_root(Some(path))?;

            let fresh = ensure_fresh_indexes(&root)?;

            println!(
                "{}",
                serde_json::to_string_pretty(&fresh.structural.find_symbols(&query, limit,))?
            );
        }

        Command::Symbol { name, path } => {
            let root = resolve_root(Some(path))?;

            let fresh = ensure_fresh_indexes(&root)?;

            println!(
                "{}",
                serde_json::to_string_pretty(&fresh.structural.lookup_symbol(&name,))?
            );
        }

        Command::Graph { path, limit } => {
            let root = resolve_root(Some(path))?;

            let fresh = ensure_fresh_indexes(&root)?;

            println!(
                "{}",
                serde_json::to_string_pretty(&fresh.graph.ranked_symbols(limit,))?
            );
        }

        Command::Impact { name, path, depth } => {
            let root = resolve_root(Some(path))?;

            let fresh = ensure_fresh_indexes(&root)?;

            println!(
                "{}",
                serde_json::to_string_pretty(&fresh.graph.impact_symbol(&name, depth,))?
            );
        }

        Command::Serve { path } => {
            let root = resolve_root(Some(path))?;

            daemon::serve(&root)?;
        }

        Command::Mcp { path } => {
            mcp::serve(path)?;
        }

        Command::Doctor { path } => {
            let root = resolve_root(Some(path))?;

            println!("{}", serde_json::to_string_pretty(&doctor::run(&root,)?)?);
        }
    }

    Ok(())
}
