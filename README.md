# CodeIntel

Local code intelligence and retrieval engine for agentic coding tools.

CodeIntel combines fast lexical search, Tree-sitter structural analysis,
a repository graph, PageRank, blast-radius analysis and hybrid context
ranking behind CLI and MCP interfaces.

As of **v0.5**, persistent indexes stay fresh automatically through an
incremental freshness pipeline.

## Architecture

~~~text
                         CodeIntel
                            |
            +---------------+---------------+
            |               |               |
         Lexical        Structural         Graph
            |               |               |
         Trigram         Tree-sitter      Call graph
            |               |               |
      text / regex      symbols / refs    PageRank
            |               |               |
            +---------------+---------------+
                            |
                    Hybrid Context
                            |
                  weighted RRF ranking
                            |
                     CLI / MCP / Agent
~~~

## v0.5 — Fresh Incremental Indexing

CodeIntel v0.5 adds an authoritative freshness pipeline for all
persistent indexes.

~~~text
repository source
       |
       v
manifest scan
       |
       +---- unchanged ------> reuse cached work
       |
       +---- added ----------> lexical index + Tree-sitter parse
       |
       +---- modified -------> lexical refresh + Tree-sitter reparse
       |
       +---- deleted --------> remove cached file data
       |
       v
global reference resolution
       |
       v
GraphIndex rebuild
       |
       v
PageRank rebuild
       |
       v
atomic persistence
       |
       v
manifest written last
~~~

The graph is rebuilt globally in v0.5 because structural symbol IDs can
still depend on source positions. Lexical and Tree-sitter work is reused
per file whenever possible.

## Persistent state

CodeIntel stores repository-local state under:

~~~text
.codeintel/
├── manifest.json
├── index.json
├── structural.json
└── graph.json
~~~

### `manifest.json`

Tracks source fingerprints used for freshness detection:

- repository-relative path
- file size
- high-resolution modification time
- content hash

For unchanged `size + mtime`, the previous content hash can be reused
without rereading the entire source file.

### `index.json`

Persistent trigram lexical index with reusable per-file trigram data.

### `structural.json`

Tree-sitter structural index containing:

- symbol definitions
- references
- conservative reference resolution
- reusable structural data per file

### `graph.json`

Repository graph containing:

- symbol nodes
- incoming edges
- outgoing edges
- PageRank
- data used for blast-radius analysis

## Incremental refresh metrics

Refresh operations expose:

~~~text
scanned
reused
added
modified
deleted
reparsed
~~~

Example:

~~~text
fresh: scanned=120 reused=119 added=0 modified=1 deleted=0 reparsed=1
~~~

A no-change pass should normally report:

~~~text
added=0
modified=0
deleted=0
reparsed=0
~~~

## Automatic freshness

Manual `codeintel index` is no longer required before normal queries.

The freshness pipeline is used automatically by:

- CLI search
- CLI context
- CLI symbols
- CLI symbol inspection
- CLI graph
- CLI impact analysis
- MCP `code_search`
- MCP `code_context`
- MCP `code_symbol`
- MCP `code_impact`
- daemon refreshes

Each command or MCP tool call operates on one coherent fresh index
snapshot.

## Index

Ensure persistent indexes are current:

~~~bash
codeintel index .
~~~

The command reports index sizes and freshness metrics.

Example:

~~~text
indexed 42 files, 180 definitions, 1400 references and 180 graph nodes
fresh: scanned=42 reused=42 added=0 modified=0 deleted=0 reparsed=0
~~~

## Lexical search

Literal search:

~~~bash
codeintel search 'PaymentService' .
~~~

Regex:

~~~bash
codeintel search 'fn\s+\w+' . --regex
~~~

The trigram index narrows candidate files and real source content is
used to verify results.

## Hybrid context

~~~bash
codeintel context \
  "change graph impact ranking" \
  . \
  --limit 10
~~~

`code_context` combines:

~~~text
lexical relevance
+ structural relevance
+ PageRank
+ graph proximity
+ repository path penalties
        |
        v
weighted Reciprocal Rank Fusion
~~~

Each returned file includes the ranking contribution from the available
channels.

## Structural intelligence

Supported Tree-sitter languages:

- Rust
- Python
- JavaScript / JSX
- TypeScript / TSX

Search symbols:

~~~bash
codeintel symbols . --query payment
~~~

Inspect a symbol:

~~~bash
codeintel symbol process_payment .
~~~

A symbol view can contain:

~~~text
definitions
callers
callees
references
~~~

## Reference resolution policy

Resolution is intentionally conservative.

~~~text
same-file unique compatible definition
              |
              v
repository-wide same-language unique compatible definition
              |
              v
otherwise ambiguous / unresolved
~~~

Method and member calls are treated specially:

~~~text
foo()
  -> eligible for conservative resolution

object.foo()
  -> external_or_method
  -> no speculative graph edge
~~~

CodeIntel is not a compiler or LSP and does not currently perform
type-aware semantic resolution.

## Graph intelligence

Rank important symbols:

~~~bash
codeintel graph . --limit 20
~~~

Analyze blast radius:

~~~bash
codeintel impact resolve_root . --depth 4
~~~

The graph contains only references that resolve to both an owner and a
target.

PageRank is recalculated after structural changes.

## Daemon

Watch a repository:

~~~bash
codeintel serve .
~~~

The daemon:

1. ensures indexes are fresh at startup;
2. watches the repository recursively;
3. ignores `.codeintel` self-events;
4. debounces filesystem bursts;
5. invokes the same incremental freshness pipeline used by CLI and MCP.

A single modified source file can therefore reuse all unaffected
lexical and structural data.

## MCP

Start the MCP server:

~~~bash
codeintel mcp .
~~~

Available tools:

~~~text
code_search
code_context
code_symbol
code_impact
~~~

### `code_search`

Persistent lexical/trigram search.

### `code_context`

Hybrid repository context ranking.

### `code_symbol`

Tree-sitter symbol inspection with definitions, callers, callees and
references.

### `code_impact`

Graph impact analysis with PageRank, direct callers, transitive callers
and blast radius.

All MCP tool calls automatically ensure repository freshness.

## Doctor

~~~bash
codeintel doctor .
~~~

`doctor` is intentionally **read-only**.

It can report:

- command availability
- manifest presence and compatibility
- lexical index status
- structural index status
- graph index status
- per-file cache coherence
- graph/structural coherence
- source/index freshness

Typical freshness statuses:

~~~text
fresh
stale
missing
incomplete
invalid
error
~~~

Example stale state:

~~~text
index_freshness:
  status: stale
  scanned=42 reused=41 added=0 modified=1 deleted=0
~~~

Running `doctor` does not create, repair, refresh or rewrite persistent
index state.

## Atomic persistence

Persistent JSON files use same-directory temporary files followed by
atomic rename.

The manifest is written **last** and acts as the commit marker for the
completed index generation.

If persistent state is missing, corrupt or incompatible, the normal
freshness pipeline safely falls back to a full rebuild.

## Freshness strategy

For an existing compatible manifest:

~~~text
same path + same size + same high-resolution mtime
        |
        v
reuse previous content hash
        |
        v
classify unchanged without rereading source contents
~~~

When metadata changes, CodeIntel reads and hashes the file again before
classifying it.

## Current incremental boundaries

Incremental in v0.5:

- manifest scanning
- lexical per-file trigram work
- Tree-sitter per-file parsing
- deletion handling
- changed-file replacement

Global in v0.5:

- structural reference resolution
- graph construction
- PageRank

This keeps correctness conservative while avoiding the most expensive
repeated source processing.

## Safety and recovery

CodeIntel falls back to a safe rebuild when persistent state cannot be
trusted, including:

- missing manifest
- corrupt manifest
- incompatible manifest schema
- missing persistent index
- corrupt persistent index
- incompatible repository root
- incomplete per-file lexical cache
- incomplete structural cache
- graph/structural mismatch

## Repository path handling

CodeIntel resolves the repository root from:

1. explicit CLI/MCP path;
2. `CODEINTEL_ROOT`;
3. `CLAUDE_PROJECT_DIR`;
4. current directory.

When possible, Git is used to resolve the repository top-level.

## Design principles

CodeIntel v0.5 prioritizes:

- local execution
- deterministic ranking
- conservative graph resolution
- persistent indexes
- incremental source processing
- automatic freshness
- atomic persistence
- graceful recovery
- small agent-facing interfaces

No embeddings, vector database or external inference service is required
for the core indexing and retrieval pipeline.

## Version

~~~text
CodeIntel 0.5.0
~~~
