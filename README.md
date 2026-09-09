# CodeIntel

**Find the code that matters before your agent starts editing.**

[![Version: 0.6.0](https://img.shields.io/badge/version-0.6.0-blue)](Cargo.toml)
[![Rust edition: 2024](https://img.shields.io/badge/Rust-edition_2024-orange?logo=rust)](Cargo.toml)
[![Local Rust tests: 59 passed](https://img.shields.io/badge/local_Rust_tests-59_passed-brightgreen)](docs/verification/2026-09-09-v0.5.0.md)
[![Core API keys: none](https://img.shields.io/badge/core_API_keys-none-teal)](#what-you-gain)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache_2.0-blue)](LICENSE)

CodeIntel is a local code intelligence engine for developers and coding agents.
It combines literal and regex search, Tree-sitter analysis, a repository graph,
and ranked context behind a Rust CLI and four MCP tools.

The test badge is a **local verification snapshot from September 9, 2026**,
not a live CI status or a code coverage percentage.
[Read the evidence and reproduction steps](docs/verification/2026-09-09-v0.5.0.md).
Badges are rendered by [Shields.io](https://shields.io/).

## New in v0.6.0

The [agent benchmark matrix](benchmarks/agent/README.md) adds reproducible
rg/CodeIntel comparisons and opt-in Claude/Codex A/B runners. It includes
isolated repository snapshots, retrieval and graph scoring, nullable telemetry,
and machine-readable reports. Real-agent runs require explicit permission and
Linux Bubblewrap containment; the default verification uses no model calls.

This version adds benchmark tooling without changing the Rust retrieval runtime
or its dependencies. See the [changelog](CHANGELOG.md) for the release scope.
The v0.5.0 test evidence below remains a dated historical record.

The [v0.6.0 interface verification](docs/verification/2026-09-09-v0.6.0.md)
exercises all **10 CLI commands and 4 MCP tools** through the release binary.
Its **17 integration tests** run in CI without model calls.

## What you gain

| Your task | What CodeIntel provides | Practical benefit |
| --- | --- | --- |
| Find an implementation | Verified literal or regex matches with file locations | Start from matching code instead of opening files one by one. |
| Understand an unfamiliar repository | Files ranked by task relevance, structure, and graph signals | Give your agent a focused starting set of files to inspect. |
| Plan a change | Definitions, callers, callees, and transitive impact | Inspect known dependencies before editing shared code. |
| Keep working after edits | Automatic freshness checks and per-file lexical/parse reuse | Query again without manually rebuilding the index each time. |
| Use intelligence locally | CLI and MCP, without embeddings, API keys, or an inference service | Keep indexing and retrieval on your machine without a model-service dependency. |

CodeIntel returns evidence for an agent to inspect; it does not replace tests,
code review, or compiler checks. Smaller, better-targeted context can help reduce
unnecessary reading, but **no token savings or agent speedup percentage is claimed
here**. Those require a controlled agent benchmark.

## How it works

1. **Scan:** select eligible files and compare their metadata with the persisted
   manifest to detect additions, edits, and deletions.
2. **Retrieve:** use a trigram index to narrow lexical candidates, then verify
   matches against source text.
3. **Analyze:** parse supported languages with Tree-sitter and conservatively
   resolve definitions and references into a graph.
4. **Rank:** combine lexical and structural relevance, PageRank, graph proximity,
   and path penalties using weighted reciprocal rank fusion.
5. **Serve:** return results through the CLI or MCP, refreshing indexes as needed.

~~~mermaid
flowchart LR
    Source[Repository files] --> Fresh[Freshness scan]
    Fresh --> Lexical[Trigram index]
    Fresh --> Structural[Tree-sitter index]
    Structural --> Graph[Reference graph and PageRank]
    Lexical --> Context[Hybrid context ranking]
    Structural --> Context
    Graph --> Context
    Context --> Interfaces[CLI and MCP]
~~~

Lexical and structural indexes remain independent. The current version reuses
unchanged per-file work, while reference resolution, graph construction, and
PageRank are global when a refresh requires rebuilding them.

## Verified behavior

A fresh **v0.5.0** build was tested against a three-file Python fixture with the
call chain `submit_order → checkout → process_payment`.

| Check | Observed result |
| --- | --- |
| Search for `process_payment` | Returned `checkout.py` and `payment.py`, exactly the expected files. |
| Inspect `process_payment` | Returned its definition. |
| Analyze impact | Direct caller: `checkout`; transitive blast radius: **2**. |
| Edit only `payment.py` | **3 scanned, 2 reused, 1 modified, 1 reparsed**. |
| Query unchanged state again | **3 reused, 0 modified, 0 reparsed**. |

These are functional checks on a small synthetic fixture, not production-scale
performance measurements. [Run the same proof](docs/verification/2026-09-09-v0.5.0.md#reproduce-the-functional-proof).

### Test evidence

The fresh local Rust suite completed with **59 passed, 0 failed, 0 ignored**.
Formatting, Clippy with warnings denied, and the locked release build also passed.

| Test suite | Passed | What it checks |
| --- | ---: | --- |
| [Core retrieval](tests/core.rs) | 2 | Lexical search and context behavior. |
| [Structural analysis](tests/structural.rs) | 9 | Language parsing and conservative resolution. |
| [Graph](tests/graph.rs) | 5 | Graph relationships, ranking, and impact. |
| [Hybrid context](tests/hybrid_context.rs) | 8 | Combined ranking behavior. |
| [Incremental indexing](tests/incremental.rs) | 9 | Per-file change detection and reuse. |
| [Freshness](tests/freshness.rs) | 12 | Index freshness, rebuilds, and recovery. |
| [CLI/MCP freshness](tests/interface_freshness.rs) | 4 | Queries refresh indexes after source edits. |
| [Persistence](tests/persistence.rs) | 3 | Atomic writes and stored index behavior. |
| [Daemon](tests/daemon.rs) | 2 | Watch-triggered index refresh. |
| [Doctor](tests/doctor.rs) | 5 | Read-only diagnostics. |

See the [verification record](docs/verification/2026-09-09-v0.5.0.md) for the
revision, commands, environment, and limits of this evidence.

## Install

Build from source with a Rust toolchain that supports edition 2024, Cargo,
and a C compiler for the Tree-sitter parsers. Git is used to clone the project
and detect repository roots.

~~~bash
git clone https://github.com/felipetruman/codeintel.git
cd codeintel
cargo install --path . --locked
codeintel --version
~~~

Ensure Cargo's binary directory (normally `$HOME/.cargo/bin`) is on `PATH`.
To build without installing, run `cargo build --release --locked` and use
`./target/release/codeintel` instead of `codeintel`.

## Quick start

From the repository you want to inspect:

~~~bash
codeintel context "understand repository architecture" . --limit 5
codeintel search 'resolve_root' . --limit 10
codeintel symbol resolve_root .
codeintel impact resolve_root . --depth 2
codeintel doctor .
~~~

The symbol examples use this repository's `resolve_root` function. Replace
it with a symbol from your project when inspecting another repository.

Queries create or refresh `.codeintel/` automatically; a separate indexing
step or running daemon is optional. The repository must be writable for
index persistence. Add `.codeintel/` to your project's `.gitignore` to keep
generated indexes out of commits.

Search, context, symbols, symbol, graph, and impact commands print JSON.
Use `codeintel --help` or `codeintel <command> --help` to inspect arguments.
Keep native tools such as `rg` available as a fallback.

## Navigation

- [Architecture](#architecture) and [persistent state](#persistent-state)
- [Lexical search](#lexical-search) and [hybrid context](#hybrid-context)
- [Structural intelligence](#structural-intelligence) and
  [graph intelligence](#graph-intelligence)
- [MCP integration](#mcp) and [diagnostics](#doctor)
- [Repository path handling](#repository-path-handling) and
  [development](#development)

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

## Fresh incremental indexing

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

The server communicates over stdin/stdout using newline-delimited JSON-RPC.
Configure your MCP client to launch the installed binary with these values:

~~~json
{
  "command": "/absolute/path/to/codeintel",
  "args": ["mcp", "/absolute/path/to/your/repository"]
}
~~~

Replace both paths and place this server entry in your client's MCP
configuration format. An explicit repository path avoids depending on the
client's working directory. Tool calls can override the server's default
repository with their `path` argument.

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

Edits that preserve both file size and modification time can evade this
metadata check. Freshness is not a byte-for-byte integrity audit on every
query.

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

Most CLI commands default their path argument to `.`. Pass an explicit path
to inspect another repository; these commands do not use environment
variables in place of their default `.`.

For MCP, CodeIntel selects the path in this order:

1. Tool call `path`, then the path passed to `codeintel mcp`.
2. `CODEINTEL_ROOT`.
3. `CLAUDE_PROJECT_DIR`.
4. Current directory.

When possible, Git resolves the selected path to the repository top-level.
A path inside a Git repository therefore selects the whole repository, not
only that subdirectory. Outside Git, CodeIntel uses the canonical directory.

## Indexed files and limitations

The scanner respects Git ignore rules and skips hidden entries, internal
index files, files larger than 4 MiB, and files detected as binary. Symbol
and graph analysis is limited to the supported Tree-sitter languages;
lexical search can cover other text files admitted by the scanner.

Graph impact represents conservatively resolved references. Unresolved
calls, dynamic dispatch, and type-dependent relationships can be absent,
so blast radius is not a complete semantic dependency analysis.

## Development

Run the repository's Rust checks from the project root:

~~~bash
cargo fmt --check
cargo test --locked
cargo clippy --locked --all-targets --all-features -- -D warnings
cargo build --release --locked
git diff --check
~~~

See [AGENTS.md](AGENTS.md) for architecture and engineering conventions.

## License

CodeIntel is licensed under [Apache-2.0](LICENSE).

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
