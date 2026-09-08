# CodeIntel v0.5 Fresh Incremental Indexing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Guarantee fresh CodeIntel indexes while reusing lexical and Tree-sitter work for unchanged files.

**Architecture:** Add a persistent repository manifest and one authoritative freshness pipeline. Refresh lexical and structural data per changed file, re-resolve structural references globally, then rebuild the graph and PageRank globally before atomically persisting the refreshed state.

**Tech Stack:** Rust, serde/serde_json, ignore, Tree-sitter, existing trigram index, notify, GraphIndex/PageRank.

**Spec:** `docs/superpowers/specs/2026-09-08-codeintel-v05-fresh-incremental-design.md`

## Global Constraints

- Target version: `0.5.0`.
- Freshness is mandatory.
- Unchanged Tree-sitter-supported files must not be reparsed.
- Structural reference resolution remains global.
- Graph and PageRank rebuild remain global.
- Persistent index writes must be atomic.
- Schema incompatibility triggers safe full rebuild.
- Existing CLI and MCP tool names remain compatible.
- All v0.1-v0.4 regression tests must stay green.

---

## File map

### New

~~~text
src/manifest.rs
src/freshness.rs
tests/freshness.rs
tests/incremental.rs
~~~

### Modify

~~~text
src/index.rs
src/structural.rs
src/graph.rs
src/daemon.rs
src/doctor.rs
src/main.rs
src/mcp.rs
src/lib.rs
Cargo.toml
README.md
skills/codeintel/SKILL.md
~~~

---

### Task 1: Manifest and change detection

**Files:**
- Create: `src/manifest.rs`
- Modify: `src/lib.rs`
- Create: `tests/freshness.rs`

**Produces:**

~~~rust
pub struct IndexManifest
pub struct FileFingerprint
pub struct ChangeSet
pub fn scan_manifest(root: &Path) -> Result<IndexManifest>
pub fn compare_manifests(old: &IndexManifest, new: &IndexManifest) -> ChangeSet
~~~

- [ ] Write tests for unchanged/added/modified/deleted classification.
- [ ] Run tests and confirm RED.
- [ ] Implement manifest scanning.
- [ ] Implement deterministic comparison.
- [ ] Add schema version.
- [ ] Add manifest load/save.
- [ ] Run tests and confirm GREEN.
- [ ] Commit.

---

### Task 2: Atomic persistence

**Files:**
- Modify: `src/index.rs`
- Modify: `src/structural.rs`
- Modify: `src/graph.rs`
- Modify: `src/manifest.rs`
- Test: `tests/freshness.rs`

**Produces:**

~~~rust
atomic JSON persistence
~~~

- [ ] Write JSON persistence/decodability test.
- [ ] Confirm RED where behavior differs.
- [ ] Introduce shared atomic-write helper if appropriate.
- [ ] Save via temporary file and rename.
- [ ] Preserve previous valid file until replacement succeeds.
- [ ] Confirm GREEN.
- [ ] Commit.

---

### Task 3: Incremental lexical refresh

**Files:**
- Modify: `src/index.rs`
- Create/modify: `tests/incremental.rs`

**Produces:**

~~~rust
CodeIndex incremental refresh from ChangeSet
~~~

- [ ] Test new file becomes searchable.
- [ ] Test deleted file disappears.
- [ ] Test modified text replaces old postings.
- [ ] Test unchanged lexical data is reusable.
- [ ] Confirm RED.
- [ ] Implement per-file lexical representation or equivalent cache.
- [ ] Reconstruct deterministic final postings.
- [ ] Confirm GREEN.
- [ ] Commit.

---

### Task 4: Incremental Tree-sitter structural refresh

**Files:**
- Modify: `src/structural.rs`
- Test: `tests/incremental.rs`

**Produces:**

~~~rust
incremental per-file structural extraction
global reference resolution
reparse statistics
~~~

- [ ] Test changed file reparses.
- [ ] Test unchanged file does not reparse.
- [ ] Test deleted symbol disappears.
- [ ] Test new symbol appears.
- [ ] Test cross-file references re-resolve.
- [ ] Confirm RED.
- [ ] Extract reusable per-file parse path.
- [ ] Merge unchanged + reparsed structural data.
- [ ] Run global reference resolution.
- [ ] Confirm GREEN.
- [ ] Commit.

---

### Task 5: Freshness orchestration

**Files:**
- Create: `src/freshness.rs`
- Modify: `src/lib.rs`
- Test: `tests/freshness.rs`
- Test: `tests/incremental.rs`

**Produces:**

~~~rust
pub struct FreshIndexSet
pub struct RefreshStats

pub fn ensure_fresh_indexes(
    root: &Path,
) -> Result<FreshIndexSet>
~~~

- [ ] Test zero-change refresh reparses zero files.
- [ ] Test corrupted manifest triggers safe rebuild.
- [ ] Test schema mismatch triggers safe rebuild.
- [ ] Confirm RED.
- [ ] Implement initial/full-build path.
- [ ] Implement incremental path.
- [ ] Rebuild GraphIndex from refreshed structure.
- [ ] Persist indexes + manifest atomically.
- [ ] Return refresh statistics.
- [ ] Confirm GREEN.
- [ ] Commit.

---

### Task 6: CLI and MCP freshness integration

**Files:**
- Modify: `src/main.rs`
- Modify: `src/mcp.rs`
- Test: integration coverage where appropriate

**Behavior:**

~~~text
search/context/symbol/impact
must not silently use stale indexes
~~~

- [ ] Route repository-intelligence commands through freshness pipeline.
- [ ] Preserve existing public command/tool names.
- [ ] Test source edit followed by CLI query without explicit `index`.
- [ ] Test source edit followed by MCP query without explicit `index`.
- [ ] Confirm GREEN.
- [ ] Commit.

---

### Task 7: Daemon incremental refresh

**Files:**
- Modify: `src/daemon.rs`
- Test: unit/integration coverage where practical

- [ ] Keep filesystem watcher.
- [ ] Keep `.codeintel` event suppression.
- [ ] Keep debounce.
- [ ] Replace full rebuild chain with freshness pipeline.
- [ ] Print RefreshStats.
- [ ] Verify changed single file produces `reparsed=1` in fixture.
- [ ] Commit.

---

### Task 8: Doctor freshness checks

**Files:**
- Modify: `src/doctor.rs`
- Test: `tests/freshness.rs`

**Adds checks:**

~~~text
manifest
index_freshness
~~~

- [ ] Test missing manifest.
- [ ] Test fresh repository.
- [ ] Test stale repository.
- [ ] Ensure doctor is read-only.
- [ ] Commit.

---

### Task 9: Version and documentation

**Files:**
- Modify: `Cargo.toml`
- Modify: `Cargo.lock`
- Modify: `README.md`
- Modify: `skills/codeintel/SKILL.md`

- [ ] Bump to `0.5.0`.
- [ ] Document automatic freshness.
- [ ] Document refresh statistics.
- [ ] Explain incremental AST parsing scope.
- [ ] Explain graph remains globally rebuilt.
- [ ] Commit.

---

### Task 10: Full verification

- [ ] `cargo fmt --check`
- [ ] `cargo test`
- [ ] `cargo clippy --all-targets --all-features -- -D warnings`
- [ ] `cargo build --release`
- [ ] Verify `codeintel --version` reports `0.5.0`.
- [ ] Run initial index.
- [ ] Run no-change refresh and confirm `reparsed=0`.
- [ ] Modify one disposable fixture source.
- [ ] Refresh and confirm changed-file-only Tree-sitter parse.
- [ ] Verify lexical search sees changed content.
- [ ] Verify structural symbol sees changed content.
- [ ] Verify graph remains normalized.
- [ ] Verify MCP `code_context`.
- [ ] Verify MCP `code_symbol`.
- [ ] Verify MCP `code_impact`.
- [ ] Verify Claude Code MCP.
- [ ] Verify Codex MCP.
- [ ] Verify clean feature branch.
- [ ] Fast-forward merge into `main`.
- [ ] Re-run verification on `main`.
- [ ] Push `origin/main`.
- [ ] Delete local feature branch.
