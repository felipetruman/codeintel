# CodeIntel Autonomous Review: design inicial (v0.7)

Data: 2026-11-02. Status: especificação para revisão; não é liberação de produção.

## Objetivo e abordagens

Evoluir o repositório **CodeIntel**, preservando seu núcleo Rust local-first e independente de API keys, para suportar code review e debug por agentes com evidências verificáveis.

Alternativas avaliadas:
1. Fork completo do DeepSeek DSH SuperAgent: rápida obtenção de Tickets, mas alto acoplamento a protótipo mono-repositório e execução local ampla. Rejeitada.
2. Incorporar agentes ao motor Rust: quebra separação de responsabilidades e a utilidade do CLI/MCP offline. Rejeitada.
3. **Camada opcional de orquestração (escolhida)** que consome CodeIntel CLI/MCP e utiliza E2B exclusivamente para execução de agentes e código não confiável.

O modelo operacional futuro combina autorização/eventos/Tickets (DSH), investigação e verificação em etapas (Uber Debug Assist) e disciplina RED-GREEN-REFACTOR, revisão e provas (obra/superpowers).

## Auditoria da base atual

- `src/context.rs`: fusão de busca lexical, símbolos, grafo e proximidade; saída estruturada.
- `src/graph.rs` e `src/structural.rs`: análise de chamadas e impacto conservadora; chamadas dinâmicas podem não ser resolvidas.
- `src/mcp.rs`: quatro ferramentas read-only (`code_search`, `code_context`, `code_symbol`, `code_impact`).
- `benchmarks/agent/runners/{claude,codex}.py`: comparadores read-only e não executores de produção.
- `benchmarks/agent/runners/agent_sandbox.py`: Bubblewrap exclusivo dos benchmarks. **Não usar como fallback para executar tarefas; o runtime futuro será somente E2B.**
- `.github/workflows/verify.yml`: gates Rust, MCP/CLI e benchmarks existentes a preservar.
- `AGENTS.md`: mantém motor sem API keys e resolução conservadora. Nenhuma alteração ao motor nesta fase.

## Escopo implementado (primeiro PR)

1. CLI `python3 -m integrations.review --repo <checkout> --base <sha> --head <sha>`.
2. Resolver refs existentes localmente, coletar arquivos via `git diff -z`, sem shell; limite de 200 arquivos.
3. Consumir `codeintel context` uma vez e validar caminho relativo e existência sob a raiz; máximo 10 arquivos.
4. Relatório JSON schema 1 com SHAs, `changed_files`, `context_files`, `findings: []`, `validated: false`.
5. Falha explícita, sem JSON de sucesso, para refs inválidos, erro de ferramenta e resposta malformada.
6. Testes Python offline e workflow CI independente sem segredos.

Este incremento **não realiza code review com IA**, não abre PRs automaticamente, não executa modelos nem configura E2B. É o contrato de evidências que os módulos seguintes reutilizarão.

## Arquitetura-alvo

```text
GitHub App (HMAC+deduplicação) -> Ticket/Policy duráveis (fora E2B)
   -> E2B efêmera por tarefa (checkout por commit SHA)
   -> CodeIntel CLI/MCP + adaptador oficial Claude/Codex
   -> Validation Gate (achados, linha/diff, testes, evidências)
   -> Publicador GitHub externo à sandbox -> revisão humana
```

- Sem merge automático. Credenciais de escrita do GitHub não chegam ao código não confiável.
- Não montar tokens pessoais da máquina nem credenciais de assinatura em workers compartilhados.
- Work idempotente `(installation_id, repo_id, pr_number, head_sha, pipeline_version)`; fechar/invalidar revisão de head obsoleto.
- Revisores têm permissão de leitura por padrão; correções somente em branches dedicadas, exigindo gates antes de draft PR.
- Limites por tarefa: tempo, custo, tamanho de contexto, concorrência e tentativas; `sandbox.kill()` em `finally`.
- Conteúdos de Issues, traces, comentários, código e logs são entradas não confiáveis; não podem alterar políticas.
- Resultados: falso positivo, achado sem evidência e regressão sem teste são erros de qualidade.
- Monitoramento de produção futuramente via Freedom Observe, em modo de leitura e com sanitização.

## Critérios de aceitação

- JSON contém SHAs verificáveis e separa evidência de opinião de IA.
- Nomes contendo espaços são tratados sem shell expansion; arquivos deletados não entram como arquivos editáveis.
- Refs inválidos, timeout/falha do CodeIntel e JSON malformado falham fechados.
- Contexto com path traversal/absoluto é descartado.
- Nenhuma mudança de contratos Rust/MCP nem autorização de terceiros.
- O piloto E2B/Claude/Codex/GitHub requer testes próprios e **não** é considerado entregue por este PR.

## Riscos a validar nas próximas etapas

Isolamento real entre tenants, limites e cobrança E2B, compatibilidade das CLIs com autenticação de assinatura, PRs provenientes de forks, GitHub rate limits, limpeza de sandboxes, qualidade dos grafos e acesso controlado a evidências de produção.
