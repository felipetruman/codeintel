# CodeIntel v0.2 Structural Intelligence Design

## Goal

Add a structural code intelligence layer without replacing the existing
v0.1 lexical/trigram engine.

## Architecture

```text
                         CodeIntel
                            |
              +-------------+-------------+
              |                           |
              v                           v
       Lexical Engine              Structural Engine
         v0.1                         v0.2
              |                           |
          trigrams                    Tree-sitter
              |                           |
          regex/text            definitions/references
              |                           |
              +-------------+-------------+
                            |
                         Agents
```

## Supported languages

v0.2 supports:

- Rust
- Python
- JavaScript
- JSX
- TypeScript
- TSX

Additional grammars are intentionally deferred.

## Persistent storage

Lexical:

```text
.codeintel/index.json
```

Structural:

```text
.codeintel/structural.json
```

The two indexes remain separate so either engine can evolve independently.

## Structural model

### Definition

A definition records:

- stable symbol ID
- symbol name
- symbol kind
- source language
- repository-relative path
- line
- column
- byte range

### Reference

A reference records:

- referenced symbol name
- reference kind
- source language
- repository-relative path
- line
- column
- containing definition, when known
- resolved target definition, when deterministically resolvable
- resolution strategy

## Resolution

Resolution is deliberately conservative.

Priority:

1. exactly one same-file definition with the referenced name;
2. otherwise exactly one same-language repository-wide definition;
3. multiple candidates => ambiguous;
4. no candidate => unresolved.

CodeIntel does not pretend this is compiler-grade semantic analysis.

## Symbol graph

Resolved references produce implicit directed relationships:

```text
caller definition
      |
      v
reference
      |
      v
callee definition
```

This supports caller/callee discovery without yet introducing PageRank.

## Interfaces

CLI:

```text
codeintel symbols PATH --query QUERY
codeintel symbol NAME PATH
```

MCP:

```text
code_symbol
```

Existing interfaces remain:

```text
code_search
code_context
```

## Index lifecycle

`codeintel index` rebuilds both:

```text
lexical index
structural index
```

`codeintel serve` rebuilds both when source changes.

## Explicit limitations

v0.2 does not implement:

- type inference
- dynamic dispatch resolution
- dependency injection resolution
- imports/modules semantic resolution
- SCIP/LSP semantic indexes
- graph PageRank
- git churn
- blast radius scoring
- test mapping

Those belong to later layers.
