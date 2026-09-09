# CodeIntel Agent Benchmark v1

Deterministic benchmark for measuring whether CodeIntel improves code
retrieval and coding-agent repository understanding.

## Runners

Six runners are supported:

| Runner | Type | CodeIntel |
| --- | --- | --- |
| `rg` | deterministic baseline | no |
| `codeintel` | deterministic | yes |
| `claude` | agent baseline | no |
| `claude-codeintel` | agent | MCP |
| `codex` | agent baseline | no |
| `codex-codeintel` | agent | MCP |

Claude and Codex A/B arms use the same task, isolated repository snapshot,
model configuration, timeout and benchmark prompt.

The intended difference inside each pair is the CodeIntel MCP server.

## Safety

Agent executions are disabled unless explicitly enabled.

A plan never calls a model:

    python -m benchmarks.agent.full_matrix \
      --corpus synthetic \
      --all \
      --plan

Real agent execution requires:

    --allow-real-agents

The benchmark:

- copies repositories into temporary isolated directories;
- does not modify the source repository;
- runs agent tasks read-only;
- does not persist raw Claude/Codex stdout or stderr;
- leaves missing telemetry as `null`;
- does not invent file-read telemetry;
- does not calculate cost unless pricing is explicitly supplied.

## Deterministic matrix

    python -m benchmarks.agent.full_matrix \
      --corpus synthetic \
      --runner rg \
      --runner codeintel \
      --repeat 2

If no runner is specified, the safe default is:

    rg
    codeintel

## Full six-runner plan

    python -m benchmarks.agent.full_matrix \
      --corpus synthetic \
      --all \
      --repeat 2 \
      --plan

## Full six-runner execution

This performs real Claude and Codex calls:

    python -m benchmarks.agent.full_matrix \
      --corpus synthetic \
      --all \
      --repeat 2 \
      --allow-real-agents

Models can be pinned:

    python -m benchmarks.agent.full_matrix \
      --corpus synthetic \
      --all \
      --allow-real-agents \
      --claude-model YOUR_CLAUDE_MODEL \
      --codex-model YOUR_CODEX_MODEL

## Arbitrary repository

    python -m benchmarks.agent.full_matrix \
      --repo /path/to/repository \
      --runner rg \
      --runner codeintel \
      --repeat 2

For real agents:

    python -m benchmarks.agent.full_matrix \
      --repo /path/to/repository \
      --runner claude \
      --runner claude-codeintel \
      --allow-real-agents

## Tasks

v1 contains read-only repository-understanding tasks:

- locate symbol;
- relevant files;
- impact analysis;
- change planning.

Code-edit grading is intentionally deferred.

Synthetic fixtures currently exercise:

- Rust call graphs and qualified-path limitations;
- TypeScript member-call ambiguity;
- Python cross-file impact.

## Metrics

Deterministic metrics include:

- latency;
- returned files;
- precision;
- recall;
- F1;
- precision@k;
- recall@k;
- MRR;
- direct-caller precision/recall;
- blast-radius error.

Agent metrics include, when observable:

- success;
- duration;
- final relevant files;
- file precision/recall;
- files read;
- relevant files read;
- irrelevant files read;
- tool calls;
- input tokens;
- output tokens;
- total tokens.

Missing telemetry remains `null`.

## A/B comparisons

When both members of an agent pair are executed, the benchmark emits A/B
deltas for:

- duration;
- input tokens;
- output tokens;
- total tokens;
- files read;
- tool calls;
- file precision;
- file recall.

Pairs:

    claude -> claude-codeintel
    codex  -> codex-codeintel

## Outputs

The existing benchmark report writer produces:

    run.json
    results.jsonl
    summary.json
    summary.csv

The full matrix additionally produces:

    comparisons.json
    comparisons.csv

Generated results under `benchmarks/agent/results/` are ignored by Git.

## Real-agent tests

Unit tests never call Claude or Codex by default.

Explicit opt-in:

    CODEINTEL_BENCH_REAL_AGENTS=1 \
    python -m pytest benchmarks/agent/tests -q

This can spend model quota and should only be enabled intentionally.

## CodeIntel modes

Use persistent warm indexes:

    --codeintel-mode warm

Force cold deterministic CodeIntel runs:

    --codeintel-mode cold

## Benchmark invariants

The benchmark must not alter the CodeIntel Rust runtime.

The feature is implemented entirely under:

    benchmarks/agent/
