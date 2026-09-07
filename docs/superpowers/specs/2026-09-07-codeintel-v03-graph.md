# CodeIntel v0.3 Graph Intelligence

## Goal

Transform resolved structural references into a persistent directed symbol graph.

## Features

- adjacency graph
- incoming/outgoing edges
- PageRank
- direct callers
- transitive callers
- blast radius
- depth-limited impact traversal
- CLI graph ranking
- CLI impact analysis
- MCP `code_impact`

## Storage

```text
.codeintel/index.json
.codeintel/structural.json
.codeintel/graph.json
```

## Graph semantics

Only structural references with both:

```text
owner != null
target != null
```

become graph edges.

`external_or_method`, ambiguous and unresolved references do not create edges.

## PageRank

Directed PageRank:

```text
damping = 0.85
max iterations = 100
tolerance = 1e-10
```

## Blast radius

For symbol S:

```text
S
↑
direct callers
↑
callers of callers
↑
...
```

Blast radius is the number of unique upstream symbols reachable within the configured depth.
