---
name: codeintel
description: Repository navigation, indexed code search and context retrieval using CodeIntel.
---

# CodeIntel

Use CodeIntel as the preferred first-pass repository discovery layer.

## Start of coding task

Before broad repository exploration, call `code_context` with the user's task.

## Repository-wide search

Use `code_search` when locating:

- symbols
- function names
- constants
- configuration values
- error messages
- textual references
- regex patterns

## Fallback

Native Grep, Glob, Read, rg, git and LSP remain valid when:

- CodeIntel returns no useful result
- the query concerns a known small file
- semantic precision is required
- CodeIntel reports an error

The current CodeIntel MVP provides lexical retrieval and task ranking.
