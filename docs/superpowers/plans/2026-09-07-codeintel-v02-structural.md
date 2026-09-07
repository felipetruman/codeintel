# CodeIntel v0.2 Structural Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add persistent Tree-sitter-based structural indexing, symbol lookup and deterministic reference resolution.

**Architecture:** Keep the v0.1 trigram index independent. Add `StructuralIndex` as a second persistent index containing definitions and references. CLI, daemon and MCP compose both indexes but neither depends on the internal storage format of the other.

**Tech Stack:** Rust 2024, tree-sitter, tree-sitter-rust, tree-sitter-python, tree-sitter-javascript, tree-sitter-typescript, serde.

**Spec:** `docs/superpowers/specs/2026-09-07-codeintel-v02-structural-design.md`

## Global Constraints

- Preserve all v0.1 functionality.
- Structural analysis remains local and API-key-free.
- Resolution must prefer uncertainty over invented edges.
- Rust, Python, JavaScript/JSX and TypeScript/TSX only in v0.2.
- `cargo test`, `cargo fmt`, `cargo clippy -D warnings` and release build must pass.

---

### Task 1: Structural data model

**Files:**
- Create: `src/structural.rs`
- Modify: `src/lib.rs`
- Test: `tests/structural.rs`

**Produces:**
- `StructuralIndex`
- `SymbolDefinition`
- `SymbolReference`
- `SymbolView`

Test first, verify RED, implement, verify GREEN.

### Task 2: Tree-sitter extraction

Extract function/class/type/module definitions and call-like references for all supported languages.

Test with real Rust, Python and TypeScript source snippets.

### Task 3: Conservative reference resolution

Resolve references using same-file uniqueness first and repository-wide same-language uniqueness second.

Ambiguous and unresolved references must remain explicitly marked.

### Task 4: CLI integration

Add:

```text
codeintel symbols
codeintel symbol
```

`codeintel index` must rebuild lexical and structural indexes.

### Task 5: MCP integration

Add read-only MCP tool:

```text
code_symbol
```

The tool returns definitions, callers, callees and relevant references.

### Task 6: Daemon and doctor

`serve` rebuilds both indexes.

`doctor` reports both persistent indexes.

### Task 7: Agent instructions and verification

Update skills/docs and verify Claude Code and Codex continue to expose CodeIntel successfully.
