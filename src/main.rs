use std::path::PathBuf;

use anyhow::Result;
use clap::{Parser, Subcommand};

use codeintel::{
    context::build_repository_context, daemon, doctor, graph::GraphIndex, index::CodeIndex, mcp,
    search::search_index, structural::StructuralIndex, workspace::resolve_root,
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

            let lexical = CodeIndex::rebuild(&root)?;

            let structural = StructuralIndex::rebuild(&root, &lexical.files)?;

            let graph = GraphIndex::rebuild(&root, &structural)?;

            println!(
                "indexed {} files, {} definitions, {} references and {} graph nodes",
                lexical.files.len(),
                structural.definitions.len(),
                structural.references.len(),
                graph.nodes.len(),
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

            let index = CodeIndex::ensure(&root)?;

            let hits = search_index(&index, &query, regex, limit)?;

            println!("{}", serde_json::to_string_pretty(&hits)?);
        }

        Command::Context { task, path, limit } => {
            let root = resolve_root(Some(path))?;

            let index = CodeIndex::ensure(&root)?;

            let bundle = build_repository_context(&root, &index, &task, limit)?;

            println!("{}", serde_json::to_string_pretty(&bundle)?);
        }

        Command::Symbols { path, query, limit } => {
            let root = resolve_root(Some(path))?;

            let lexical = CodeIndex::ensure(&root)?;

            let structural = StructuralIndex::ensure(&root, &lexical.files)?;

            println!(
                "{}",
                serde_json::to_string_pretty(&structural.find_symbols(&query, limit,))?
            );
        }

        Command::Symbol { name, path } => {
            let root = resolve_root(Some(path))?;

            let lexical = CodeIndex::ensure(&root)?;

            let structural = StructuralIndex::ensure(&root, &lexical.files)?;

            println!(
                "{}",
                serde_json::to_string_pretty(&structural.lookup_symbol(&name,))?
            );
        }

        Command::Graph { path, limit } => {
            let root = resolve_root(Some(path))?;

            let lexical = CodeIndex::ensure(&root)?;

            let structural = StructuralIndex::ensure(&root, &lexical.files)?;

            let graph = GraphIndex::ensure(&root, &structural)?;

            println!(
                "{}",
                serde_json::to_string_pretty(&graph.ranked_symbols(limit))?
            );
        }

        Command::Impact { name, path, depth } => {
            let root = resolve_root(Some(path))?;

            let lexical = CodeIndex::ensure(&root)?;

            let structural = StructuralIndex::ensure(&root, &lexical.files)?;

            let graph = GraphIndex::ensure(&root, &structural)?;

            println!(
                "{}",
                serde_json::to_string_pretty(&graph.impact_symbol(&name, depth,))?
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

            println!("{}", serde_json::to_string_pretty(&doctor::run(&root)?)?);
        }
    }

    Ok(())
}
