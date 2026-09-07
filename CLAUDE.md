# CodeIntel Development Instructions

## Purpose

CodeIntel is a local-first code intelligence layer for agentic coding tools.

## Current architecture

- `workspace.rs`: repository root resolution
- `index.rs`: persistent lexical/trigram index
- `search.rs`: literal and regex retrieval
- `context.rs`: task-oriented context ranking
- `daemon.rs`: filesystem watcher
- `mcp.rs`: MCP stdio integration
- `doctor.rs`: environment diagnostics

## Engineering rules

1. Keep public interfaces small.
2. Keep CodeIntel local-first and API-key-free.
3. Preserve native grep/search tools as fallback.
4. Do not claim semantic correctness for lexical retrieval.
5. Add tests before new behavior.
6. Run cargo fmt, cargo test and cargo clippy before completion.

## Product direction

Future structural retrieval should add Tree-sitter, symbols, references, graph ranking, git intelligence and test mapping as separate components.
