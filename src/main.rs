use std::path::PathBuf;

use anyhow::Result;
use clap::{Parser, Subcommand};

use codeintel::{
    context::build_context, daemon, doctor, index::CodeIndex, mcp, search::search_index,
    structural::StructuralIndex, workspace::resolve_root,
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
    /// Rebuild lexical and structural indexes.
    Index {
        #[arg(default_value = ".")]
        path: PathBuf,
    },

    /// Search source code.
    Search {
        query: String,

        #[arg(default_value = ".")]
        path: PathBuf,

        #[arg(long)]
        regex: bool,

        #[arg(long, default_value_t = 50)]
        limit: usize,
    },

    /// Build ranked lexical context for a task.
    Context {
        task: String,

        #[arg(default_value = ".")]
        path: PathBuf,

        #[arg(long, default_value_t = 10)]
        limit: usize,
    },

    /// Search structural symbol definitions.
    Symbols {
        #[arg(default_value = ".")]
        path: PathBuf,

        #[arg(long, default_value = "")]
        query: String,

        #[arg(long, default_value_t = 50)]
        limit: usize,
    },

    /// Inspect a symbol, callers, callees and references.
    Symbol {
        name: String,

        #[arg(default_value = ".")]
        path: PathBuf,
    },

    /// Watch repository and refresh both indexes.
    Serve {
        #[arg(default_value = ".")]
        path: PathBuf,
    },

    /// Start MCP stdio server.
    Mcp { path: Option<PathBuf> },

    /// Validate CodeIntel environment and indexes.
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

            println!(
                "indexed {} files, {} definitions and {} references",
                lexical.files.len(),
                structural.definitions.len(),
                structural.references.len(),
            );

            println!("lexical: {}", root.join(".codeintel/index.json").display());

            println!(
                "structural: {}",
                root.join(".codeintel/structural.json").display()
            );
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

            let bundle = build_context(&index, &task, limit)?;

            println!("{}", serde_json::to_string_pretty(&bundle)?);
        }

        Command::Symbols { path, query, limit } => {
            let root = resolve_root(Some(path))?;

            let lexical = CodeIndex::ensure(&root)?;

            let structural = StructuralIndex::ensure(&root, &lexical.files)?;

            let symbols = structural.find_symbols(&query, limit);

            println!("{}", serde_json::to_string_pretty(&symbols)?);
        }

        Command::Symbol { name, path } => {
            let root = resolve_root(Some(path))?;

            let lexical = CodeIndex::ensure(&root)?;

            let structural = StructuralIndex::ensure(&root, &lexical.files)?;

            let view = structural.lookup_symbol(&name);

            println!("{}", serde_json::to_string_pretty(&view)?);
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
