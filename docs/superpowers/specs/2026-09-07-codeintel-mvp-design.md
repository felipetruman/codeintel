# CodeIntel MVP Design

## Objetivo

Criar uma camada local de code intelligence para agentes como Claude Code e Codex.

O usuário continua utilizando seu agente normalmente. CodeIntel fornece ferramentas MCP para navegação, busca e seleção de contexto.

## Arquitetura

```text
Agent
  |
Skill / Instructions
  |
MCP stdio
  |
CodeIntel
  |
  +-- Workspace resolver
  +-- Persistent lexical index
  +-- Trigram candidate retrieval
  +-- Regex/literal verifier
  +-- Context ranking
  +-- File watcher
  |
.codeintel/index.json
```

## Interfaces v0.1

### CLI

- `codeintel index [PATH]`
- `codeintel search QUERY [PATH]`
- `codeintel context TASK [PATH]`
- `codeintel serve [PATH]`
- `codeintel mcp [PATH]`
- `codeintel doctor [PATH]`

### MCP

- `code_search`
- `code_context`

## Busca

Buscas literais com pelo menos três caracteres utilizam um índice invertido de trigrams para reduzir o conjunto de arquivos candidatos.

Regex continua fazendo verificação sobre arquivos conhecidos pelo índice.

O resultado final sempre é validado contra o conteúdo real do arquivo.

## Persistência

O índice fica em:

`.codeintel/index.json`

## Watcher

`codeintel serve` observa alterações no workspace e reconstrói o índice com debounce.

A v0.1 prioriza correção sobre atualização incremental granular.

## Integração com agentes

Claude Code e Codex recebem:

1. MCP server CodeIntel.
2. Skill/instruções para preferência por `code_context` e `code_search`.
3. Fallback para ferramentas nativas quando CodeIntel não encontrar contexto suficiente.

## Fora do escopo da v0.1

- Tree-sitter
- Symbol index
- Reference graph
- Call graph
- Git churn
- Test mapping
- Personalized PageRank
- Rank fusion estrutural
- Atualização incremental granular
