# Hybrid Context Ranking v0.4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace lexical-only context ranking with deterministic hybrid retrieval.

**Architecture:** Generate lexical and structural candidates, derive graph importance and graph proximity, fuse rankings with weighted RRF, then apply repository-area penalties.

**Tech Stack:** Rust, existing trigram index, Tree-sitter structural index, GraphIndex/PageRank.

**Spec:** `docs/superpowers/specs/2026-09-07-codeintel-v04-hybrid-context-design.md`

## Global Constraints

- No embeddings.
- No external model calls.
- Weighted RRF with K=60.
- Preserve lexical fallback.
- CLI and MCP use the same hybrid implementation.
- Deterministic path tie-breaker.
- Target version 0.4.0.

---

### Task 1: Hybrid ranking engine

**Files:**
- Modify: `src/context.rs`
- Test: `tests/hybrid_context.rs`

- [ ] Write failing ranking tests.
- [ ] Verify RED.
- [ ] Implement lexical, structural, graph and proximity channels.
- [ ] Implement RRF.
- [ ] Implement path penalties.
- [ ] Verify GREEN.

### Task 2: CLI and MCP integration

**Files:**
- Modify: `src/main.rs`
- Modify: `src/mcp.rs`

- [ ] Route CLI context through repository hybrid context.
- [ ] Route MCP code_context through the same function.
- [ ] Preserve lexical fallback.
- [ ] Verify MCP response.

### Task 3: Documentation and version

**Files:**
- Modify: `Cargo.toml`
- Modify: `README.md`
- Modify: `skills/codeintel/SKILL.md`

- [ ] Bump version to 0.4.0.
- [ ] Document ranking signals.
- [ ] Update agent instructions.

### Task 4: Verification

- [ ] cargo fmt --check
- [ ] cargo test
- [ ] cargo clippy -D warnings
- [ ] cargo build --release
- [ ] Real context query.
- [ ] MCP query.
- [ ] Commit.
- [ ] Merge main.
- [ ] Push origin/main.
