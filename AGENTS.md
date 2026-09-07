# CodeIntel Development Instructions

## Purpose

CodeIntel is a local-first code intelligence layer for agentic coding tools.

## Architecture

### Lexical engine

- `index.rs`: persistent trigram index
- `search.rs`: literal and regex retrieval
- `context.rs`: task-oriented lexical ranking

### Structural engine

- `structural.rs`: Tree-sitter parsing, definitions, references and conservative resolution

### Runtime

- `workspace.rs`: workspace resolution
- `daemon.rs`: index refresh
- `mcp.rs`: MCP interface
- `doctor.rs`: diagnostics

## Structural language support

- Rust
- Python
- JavaScript / JSX
- TypeScript / TSX

## Engineering rules

1. Keep lexical and structural indexes independent.
2. Keep CodeIntel local-first and API-key-free.
3. Prefer explicit ambiguity over false semantic certainty.
4. Preserve native search tools as fallback.
5. Tests precede behavior changes.
6. Run `cargo fmt --check`.
7. Run `cargo test`.
8. Run `cargo clippy --all-targets --all-features -- -D warnings`.
9. Run `cargo build --release`.

## Product direction

Next structural layers may add:

- import-aware resolution
- semantic indexes such as SCIP/LSP
- graph ranking
- git churn
- blast radius
- test mapping
