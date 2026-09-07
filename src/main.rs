use std::path::PathBuf;

use anyhow::Result;
use clap::{Parser, Subcommand};

use codeintel::{
    context::build_context, daemon, doctor, index::CodeIndex, mcp, search::search_index,
    workspace::resolve_root,
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

            let index = CodeIndex::rebuild(&root)?;

            println!(
                "indexed {} files into {}",
                index.files.len(),
                root.join(".codeintel/index.json").display()
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
