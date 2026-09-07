# CodeIntel

Local code intelligence and retrieval engine for agentic coding tools.

## v0.2

CodeIntel combines two independent retrieval layers.

```text
              CodeIntel
                 |
        +--------+--------+
        |                 |
     Lexical          Structural
        |                 |
     trigram          Tree-sitter
        |                 |
 regex / text      symbols / refs
        |                 |
        +--------+--------+
                 |
               Agent
```

## Supported structural languages

- Rust
- Python
- JavaScript / JSX
- TypeScript / TSX

## Index

```bash
codeintel index .
```

Creates:

```text
.codeintel/index.json
.codeintel/structural.json
```

## Lexical search

```bash
codeintel search 'PaymentService' .
```

Regex:

```bash
codeintel search 'fn\s+\w+' . --regex
```

## Context

```bash
codeintel context 'implement payment retry' .
```

## Symbols

```bash
codeintel symbols . --query payment
```

## Symbol graph

```bash
codeintel symbol processPayment .
```

Returns:

```text
definitions
callers
callees
references
```

## Watch

```bash
codeintel serve .
```

## MCP tools

```text
code_search
code_context
code_symbol
```

## Doctor

```bash
codeintel doctor .
```

## Current resolution policy

```text
same-file unique definition
          |
          v
repository-wide same-language unique definition
          |
          v
otherwise ambiguous/unresolved
```

This is intentionally conservative and is not compiler-grade semantic analysis.

## Graph hygiene

CodeIntel distinguishes plain calls from member/method calls.

```text
foo()
  -> eligible for conservative local resolution

object.foo()
  -> external_or_method
  -> no speculative graph edge
```

Structural resolution also checks whether a symbol kind is compatible
with the reference before creating an edge.
# codeintel
# codeintel
