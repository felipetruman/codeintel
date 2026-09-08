# CodeIntel v0.5 — Fresh Incremental Indexing

## Goal

Make CodeIntel indexes automatically fresh while avoiding unnecessary
full repository reparsing.

The system must detect repository changes and reuse work from files
that have not changed.

Target version:

~~~text
CodeIntel 0.5.0
~~~

## Current problem

Current persistent indexes can become stale.

If `.codeintel/index.json`, `.codeintel/structural.json`, or
`.codeintel/graph.json` already exist, normal `ensure()` paths may load
them even after repository source files have changed.

The watcher avoids stale data by rebuilding the complete lexical,
structural, and graph indexes after filesystem changes.

This is correct but unnecessarily expensive for large repositories.

## Architecture

~~~text
repository
    |
    v
filesystem scan
    |
    v
manifest comparison
    |
    +--> unchanged
    |       |
    |       `--> reuse existing lexical + structural data
    |
    +--> added
    |       |
    |       +--> lexical index
    |       `--> Tree-sitter parse
    |
    +--> modified
    |       |
    |       +--> lexical reindex
    |       `--> Tree-sitter reparse
    |
    `--> deleted
            |
            `--> remove indexed data

             |
             v
    global reference resolution
             |
             v
       GraphIndex rebuild
             |
             v
       atomic persistence
~~~

## Design principles

1. Freshness is mandatory.
2. Reuse unchanged file work.
3. Correctness is more important than maximal incrementality.
4. Fall back to full rebuild whenever persistent state is incompatible.
5. CLI, MCP and daemon use the same freshness pipeline.
6. Persistent files must never be partially written.
7. Output must remain deterministic.

## Manifest

Introduce:

~~~text
.codeintel/manifest.json
~~~

Suggested representation:

~~~rust
pub struct IndexManifest {
    pub schema_version: u32,
    pub root: String,
    pub files: BTreeMap<String, FileFingerprint>,
}

pub struct FileFingerprint {
    pub size: u64,
    pub modified_ns: u128,
    pub content_hash: u64,
}
~~~

Exact integer/hash implementation may differ, but behavior must match
this design.

## Fingerprinting

Fingerprint each indexable file using:

~~~text
path
size
mtime
content hash
~~~

Fast path:

1. Compare path.
2. Compare size.
3. Compare high-resolution mtime.
4. Only calculate content hash when needed.

However, persisted manifest state must ultimately be able to detect
content changes reliably.

Do not rely exclusively on second-resolution mtime.

## Change classification

Every freshness pass classifies files into:

~~~text
unchanged
added
modified
deleted
~~~

Result structure:

~~~rust
pub struct ChangeSet {
    pub unchanged: Vec<String>,
    pub added: Vec<String>,
    pub modified: Vec<String>,
    pub deleted: Vec<String>,
}
~~~

Ordering must be deterministic.

## Incremental lexical index

Current lexical index stores:

~~~text
files[]
trigram -> file IDs
~~~

File IDs make in-place deletion/reordering difficult.

For v0.5 it is acceptable to reconstruct the final global posting map
from cached per-file lexical state while only re-reading/re-tokenizing
changed files.

Recommended internal representation:

~~~rust
pub struct FileLexicalData {
    pub path: String,
    pub trigrams: BTreeSet<String>,
}
~~~

Persistent representation may remain optimized differently.

Required behavior:

- unchanged file: do not read/re-tokenize source unnecessarily
- added file: generate trigrams
- modified file: regenerate trigrams
- deleted file: remove lexical data
- final global index remains compatible with search behavior

## Incremental structural index

Tree-sitter parsing is one of the primary expensive operations to avoid.

For unchanged files:

~~~text
reuse definitions
reuse references
~~~

For added/modified files:

~~~text
Tree-sitter parse again
extract definitions
extract references
~~~

For deleted files:

~~~text
remove definitions
remove references
~~~

After merging per-file structural data:

~~~text
global reference resolution runs again
~~~

This preserves correctness across cross-file changes.

## Symbol IDs

Current symbol IDs include source position information such as
`start_byte`.

Therefore editing one file may change IDs for multiple definitions in
that file.

v0.5 must not assume symbol IDs survive arbitrary edits.

For this reason:

- structural parsing is incremental per file
- reference resolution is global
- graph construction is global

Stable semantic symbol IDs are explicitly deferred.

## Graph behavior

For v0.5:

~~~text
GraphIndex rebuild = global
PageRank rebuild = global
~~~

The graph is rebuilt from the refreshed StructuralIndex.

Do not attempt incremental PageRank in this version.

Reason:

- global graph computation is relatively cheap compared to full file IO
  and Tree-sitter parsing
- correctness is simpler
- current symbol IDs are not edit-stable

## Freshness pipeline

Introduce one authoritative entry point.

Suggested API:

~~~rust
pub fn ensure_fresh_indexes(
    root: &Path,
) -> Result<FreshIndexSet>
~~~

Suggested output:

~~~rust
pub struct FreshIndexSet {
    pub lexical: CodeIndex,
    pub structural: StructuralIndex,
    pub graph: GraphIndex,
    pub stats: RefreshStats,
}
~~~

CLI, MCP and daemon should converge on this pipeline where appropriate.

## Refresh statistics

Expose internal refresh metrics:

~~~rust
pub struct RefreshStats {
    pub scanned: usize,
    pub reused: usize,
    pub added: usize,
    pub modified: usize,
    pub deleted: usize,
    pub reparsed: usize,
}
~~~

Expected invariant:

~~~text
reparsed = added + modified
~~~

for Tree-sitter-supported files, subject to language filtering.

## No-change fast path

If repository manifest matches current filesystem state:

~~~text
scan
  |
  `--> no changes
         |
         +--> load lexical
         +--> load structural
         `--> load graph
~~~

No source files should be reparsed.

This must be benchmarkable/testable.

## Index compatibility

Persistent state must carry a schema version.

Example:

~~~text
MANIFEST_SCHEMA_VERSION = 1
~~~

If:

- manifest is missing
- manifest is corrupted
- schema version differs
- lexical index cannot be loaded
- structural index cannot be loaded
- graph index cannot be loaded
- root does not match

then:

~~~text
safe full rebuild
~~~

No stale or partial state may be returned.

## Atomic writes

Persistent index files must be saved atomically.

Pattern:

~~~text
write .tmp
fsync/flush as appropriate
rename into final path
~~~

Applicable files:

~~~text
.codeintel/index.json
.codeintel/structural.json
.codeintel/graph.json
.codeintel/manifest.json
~~~

Failure while writing a new state must not destroy the last valid index.

## Daemon

The existing filesystem watcher remains.

Instead of:

~~~text
filesystem event
    ->
full lexical rebuild
    ->
full structural rebuild
    ->
full graph rebuild
~~~

use:

~~~text
filesystem event
    ->
debounce
    ->
freshness pipeline
    ->
incremental lexical/AST refresh
    ->
global graph rebuild
~~~

Keep `.codeintel` event suppression.

## CLI behavior

Existing public commands remain compatible:

~~~text
codeintel search
codeintel context
codeintel symbols
codeintel symbol
codeintel graph
codeintel impact
~~~

Commands that need repository intelligence must not silently use stale
indexes.

## MCP behavior

Existing MCP tools remain:

~~~text
code_search
code_context
code_symbol
code_impact
~~~

Queries must receive fresh repository state.

No new MCP tool is required for the core v0.5 functionality.

Optional refresh statistics may later be exposed separately.

## Doctor

Extend `codeintel doctor` with:

~~~text
manifest
index_freshness
~~~

Possible statuses:

~~~text
ok
stale
missing
invalid
~~~

Doctor should not mutate the repository indexes merely to report status.

## Performance target

For a repository where one source file changes:

~~~text
full filesystem metadata scan: acceptable
full source-file reread: not acceptable
full Tree-sitter reparse: not acceptable
single changed-file parse: expected
global reference resolution: acceptable
global graph/PageRank rebuild: acceptable
~~~

## Correctness invariants

After refresh:

1. deleted files never appear in search.
2. newly added files are searchable.
3. modified content replaces old lexical content.
4. deleted symbols disappear.
5. new symbols appear.
6. cross-file references are re-resolved.
7. graph contains only current resolved references.
8. PageRank corresponds to current graph.
9. unchanged files are not reparsed.
10. repeated no-change refresh is deterministic.

## Tests

Create:

~~~text
tests/freshness.rs
tests/incremental.rs
~~~

Required cases:

### Manifest

1. manifest round-trip
2. unchanged files classify unchanged
3. new file classifies added
4. edited file classifies modified
5. removed file classifies deleted
6. corrupted manifest triggers rebuild
7. schema mismatch triggers rebuild

### Lexical freshness

8. newly added text becomes searchable
9. removed text disappears
10. modified text replaces stale trigram results
11. unchanged file lexical work is reused

### Structural freshness

12. modified source is reparsed
13. unchanged source is reused
14. deleted symbol disappears
15. new symbol appears
16. cross-file references re-resolve after edit

### Graph freshness

17. deleted edge disappears
18. new edge appears
19. PageRank remains normalized

### Fast path

20. second refresh with zero changes reparses zero files

### Atomic persistence

21. failed temporary write does not corrupt previous state where practical
22. all generated JSON files remain decodable

### Regression

23. all v0.1-v0.4 tests stay green

## Observability

Refresh output should support messages such as:

~~~text
fresh: scanned=327 reused=326 added=0 modified=1 deleted=0 reparsed=1
~~~

Daemon should report the same statistics after refresh.

## Files likely involved

~~~text
src/index.rs
src/structural.rs
src/graph.rs
src/daemon.rs
src/doctor.rs
src/main.rs
src/mcp.rs
src/lib.rs
~~~

Likely new modules:

~~~text
src/manifest.rs
src/freshness.rs
~~~

Exact decomposition may change during implementation if tests reveal a
cleaner boundary.

## Non-goals

Not part of v0.5:

- incremental PageRank
- incremental graph edge mutation
- compiler/LSP semantic resolution
- stable semantic symbol IDs
- embeddings
- vector database
- cross-repository cache
- remote index sharing
- background distributed indexing
- database-backed storage

## Future direction

A later version may introduce:

~~~text
stable semantic IDs
        |
        v
incremental reference graph
        |
        v
incremental PageRank / affected subgraph
~~~

That work should happen only after v0.5 establishes a correct freshness
foundation.
