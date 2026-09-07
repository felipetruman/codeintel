# CodeIntel v0.4 — Hybrid Context Ranking

## Goal

Replace lexical-only `code_context` ranking with hybrid ranking combining:

- lexical relevance
- structural relevance
- graph importance
- graph proximity
- repository-area penalties

No embeddings or external model calls.

## Architecture

~~~text
task
 |
 +--> lexical ranking
 |
 +--> structural ranking
 |
 +--> graph importance
 |
 +--> graph proximity
 |
 +--> Weighted Reciprocal Rank Fusion
 |
 +--> path penalties
 |
 `--> ContextBundle
~~~

## Ranking

Use Weighted Reciprocal Rank Fusion.

~~~text
RRF(file) =
    lexical_weight    / (K + lexical_rank)
  + structural_weight / (K + structural_rank)
  + graph_weight      / (K + graph_rank)
  + proximity_weight  / (K + proximity_rank)
~~~

Constants:

~~~text
K = 60

lexical_weight    = 1.00
structural_weight = 1.20
graph_weight      = 0.80
proximity_weight  = 1.00
~~~

Missing rank contributes zero.

## Lexical ranking

Reuse existing trigram-backed `search_index`.

For every task term:

- search up to 50 hits
- aggregate by file
- reward multiple unique terms
- reward exact symbol-like matches

Produces an ordered file ranking.

## Structural ranking

Use `StructuralIndex`.

For each task term inspect:

- definition names
- reference names

Priority:

1. exact definition match
2. partial definition match
3. reference match

Produces an ordered file ranking.

## Graph importance

Use `GraphIndex`.

Aggregate PageRank by file:

~~~text
file_graph_score =
    max(symbol_pagerank)
    + 0.25 * sum(other_symbol_pagerank)
~~~

This prevents large files with many trivial symbols from dominating.

## Graph proximity

Start from structurally matched symbols.

Traverse resolved graph edges through callers and callees.

Maximum depth:

~~~text
2
~~~

Weights:

~~~text
depth 0 = 1.00
depth 1 = 0.60
depth 2 = 0.30
~~~

Only resolved graph edges participate.

Never use:

- external_or_method
- ambiguous
- unresolved

as graph edges.

## Path penalties

Apply after RRF.

~~~text
normal source                  1.00
tests/, test/, __tests__/      0.75
docs/, examples/               0.60
fixtures/, snapshots/          0.50
generated/, dist/, build/      0.35
vendor/                        0.35
~~~

Files are penalized, not excluded.

## Explicit test intent

Disable test penalty when task contains terms such as:

~~~text
test
tests
testing
spec
fixture
snapshot
pytest
vitest
jest
~~~

## Explicit docs intent

Disable docs penalty when task contains:

~~~text
docs
documentation
readme
guide
~~~

## ContextFile

Target structure:

~~~rust
pub struct ContextFile {
    pub path: String,
    pub score: f64,
    pub lexical_rank: Option<usize>,
    pub structural_rank: Option<usize>,
    pub graph_rank: Option<usize>,
    pub proximity_rank: Option<usize>,
    pub penalty: f64,
    pub matches: Vec<SearchHit>,
}
~~~

## ContextBundle

Keep:

~~~rust
pub struct ContextBundle {
    pub task: String,
    pub files: Vec<ContextFile>,
}
~~~

## Public interface

Existing commands remain unchanged:

~~~text
codeintel context TASK PATH

MCP:
code_context
~~~

Internal API:

~~~rust
pub fn build_hybrid_context(
    lexical: &CodeIndex,
    structural: &StructuralIndex,
    graph: &GraphIndex,
    task: &str,
    limit: usize,
) -> Result<ContextBundle>
~~~

## Index loading

Hybrid context ensures:

~~~text
CodeIndex
StructuralIndex
GraphIndex
~~~

CLI and MCP must use the same ranking engine.

## Graceful degradation

If structural or graph data is missing:

~~~text
hybrid context
  -> degrade gracefully
  -> lexical ranking still works
~~~

A query must not fail only because graph signals are unavailable.

## Determinism

Given identical:

~~~text
repository
indexes
task
limit
~~~

output order must be deterministic.

Final tie-breaker:

~~~text
path ascending
~~~

## Tests

Create:

~~~text
tests/hybrid_context.rs
~~~

Required cases:

1. lexical relevance still works
2. structural source beats unrelated lexical noise
3. graph-important source gains ranking
4. graph neighbor gains proximity
5. tests penalized by default
6. explicit test intent disables penalty
7. docs penalized by default
8. explicit docs intent disables penalty
9. graph absence degrades gracefully
10. deterministic ordering
11. limit respected
12. all previous regression suites stay green

## MCP

Keep tool:

~~~text
code_context
~~~

Update description to mention:

~~~text
lexical
structural
graph
proximity
~~~

No new MCP tool.

## Version

~~~text
CodeIntel 0.4.0
~~~

## Non-goals

Not included:

- embeddings
- vector database
- LLM reranking
- compiler/LSP semantic resolution
- learned ranking
- persistent query cache
- incremental graph update
- cross-repository ranking
