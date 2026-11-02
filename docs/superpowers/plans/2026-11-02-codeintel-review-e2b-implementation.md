# CodeIntel Review + E2B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar coleta verificável de evidências de PR ao CodeIntel e evoluir para revisão e debugging autônomos executados exclusivamente em E2B.

**Architecture:** Núcleo Rust permanece intocado. Uma camada opcional Python agrega evidências; workers E2B futuros recebem tickets e executam agentes. Políticas, persistência e publicação no GitHub ficam fora da sandbox.

**Tech Stack:** Rust existente, Python 3.11+, git, unittest; futuro E2B Python SDK, GitHub App, Claude Code/Codex CLI.

**Spec:** `docs/superpowers/specs/2026-11-02-codeintel-autonomous-review-design.md`

## Global Constraints

- Preservar CLI/MCP 0.6, resolver contextos conservadoramente e não adicionar dependências de IA ao motor Rust.
- Nenhuma execução de PR não confiável ou de agentes fora do E2B.
- PRs somente para revisão humana, nunca merge automático.
- TDD RED-GREEN-REFACTOR, testes e verificação antes de divulgar sucesso.

## Review Focus

- Nomes com espaços: parsing NUL e teste.
- Ref começando por hífen: negar/falhar fechado e teste.
- Contexto com path traversal: descartar e testar.
- CLI de contexto indisponível ou JSON inválido: erro sem saída de sucesso e teste.
- Webhook duplicado ou head obsoleto: impedir segundo post (Task 3, pendente).

---

### Task 1: Evidências determinísticas de PR

**Files:** `integrations/review/report.py`; `integrations/review/tests/test_report.py`.

**Interfaces:** `build_review_report(repo: Path, base: str, head: str, *, codeintel_command: Sequence[str] = ('codeintel',), max_files: int = 200, max_context: int = 10) -> dict`; falha com `ReviewError`.

- [x] Escrever testes para refs, caminhos, arquivos alterados, falhas de ferramenta e schema.
- [x] Executar testes e observar RED (módulo inexistente).
- [x] Implementar comparação Git sem shell e contexto CodeIntel.
- [x] Executar testes locais; nove casos verdes inicialmente, 12 casos após revisão de head/dirty checkout e score não finito.
- [ ] Confirmar CI remoto e revisão independente antes de merge.

### Task 2: CLI e testes no CI

**Files:** `integrations/review/cli.py`, `integrations/review/__main__.py`, `integrations/review/tests/test_cli.py`, `.github/workflows/review-context-check.yml`.

**Interfaces:** `main(argv: Sequence[str] | None = None) -> int`; 0 imprime relatório, 2 indica ReviewError sem JSON de sucesso.

- [x] Escrever testes CLI RED.
- [x] Implementar `argparse` e mensagens seguras de erro.
- [x] Executar suite local: 14 testes verdes.
- [ ] Validar workflow no GitHub Actions e checar diff do PR.

### Task 3: Tickets idempotentes e E2B isolada (pendente)

**Files propostos:** `integrations/review/tickets.py`, `integrations/review/runtime_e2b.py`, testes correspondentes.

**Interfaces a definir em spec derivada:** `TicketStore.reserve(key)` e `SandboxRuntime.run(ticket)`.

- [ ] Escrever testes de duplicação, interrupção e `kill()` em `finally`.
- [ ] Confirmar RED.
- [ ] Implementar execução por SHA em template E2B fixo, sem fallback local.
- [ ] Verificar GREEN com mocks e smoke real autorizado.
- [ ] Revisar isolamento, tempo/custo e recuperação.

### Task 4: Code Review com Claude/Codex (pendente)

**Files propostos:** `integrations/review/agent.py`, `integrations/review/publish.py`, testes.

- [ ] Escrever testes de achado sem evidência, linha inexistente e PR atualizado.
- [ ] Confirmar RED.
- [ ] Executar CLI oficial na E2B, saída estruturada.
- [ ] Validar findings e publicar via GitHub App externa à E2B.
- [ ] Verificar PR sintético com aprovação humana e sem auto-merge.

### Task 5: Auto Debug inspirado no Uber Debug Assist (pendente)

**Files propostos:** `integrations/debug/pipeline.py`, `integrations/debug/validation.py`, testes.

- [ ] Testes de diagnóstico inconclusivo e regressão não reproduzida.
- [ ] Confirmar RED.
- [ ] Reunir logs sanitizados (Freedom Observe) e contexto de código.
- [ ] Exigir falha antes, correção e sucesso depois, com limite de tentativas.
- [ ] Gerar PR draft com evidências após todos os gates.

## Estado da execução

Tasks 1 e 2 implementadas e testadas localmente, aguardando CI e revisão. Tasks 3 a 5 **não iniciadas**. O plano não significa que a integração E2B esteja operacional.
