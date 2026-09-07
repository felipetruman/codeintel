---
name: codeintel
description: Repository navigation, indexed lexical search and Tree-sitter structural code intelligence using CodeIntel.
---

# CodeIntel

Use CodeIntel as the preferred first-pass repository intelligence layer.

## Start of a coding task

Before broad repository exploration, call `code_context` with the user's task.

Use the result to identify likely files.

## Repository-wide text search

Use `code_search` for:

- exact text
- symbols
- constants
- configuration values
- error messages
- regex searches

## Structural inspection

When a concrete function, class, method, type or module becomes relevant,
call `code_symbol`.

`code_symbol` can provide:

- definitions
- callers
- callees
- references
- resolution status

Treat ambiguous and unresolved references as uncertainty, not facts.

## Fallback

Native Grep, Glob, Read, rg, git and LSP remain valid when:

- CodeIntel returns insufficient results
- a known small file is being inspected
- compiler-grade semantic resolution is needed
- dynamic dispatch or dependency injection matters
- CodeIntel reports an error

Never represent the current structural graph as compiler-complete.
