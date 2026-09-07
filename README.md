# CodeIntel

Local code intelligence and retrieval engine for agentic coding tools.

## Current MVP

- persistent lexical indexing
- trigram candidate retrieval
- literal and regex verification
- task-oriented context ranking
- repository watcher
- MCP integration
- Claude Code and Codex integration

## Build

```bash
cargo build --release
```

## Index

```bash
codeintel index .
```

## Search

```bash
codeintel search 'PaymentService' .
```

## Regex

```bash
codeintel search 'fn\s+\w+' . --regex
```

## Context

```bash
codeintel context 'implement retry in payment processing' .
```

## Watch

```bash
codeintel serve .
```

## MCP

```bash
codeintel mcp
```

## Doctor

```bash
codeintel doctor .
```

## Next layer

```text
Tree-sitter
   |
symbols
   |
references
   |
call graph
   |
rank fusion
```
