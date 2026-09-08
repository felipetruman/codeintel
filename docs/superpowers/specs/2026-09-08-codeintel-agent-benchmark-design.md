# CodeIntel Agent Benchmark v1

Date: 2026-09-08

## Goal

Build a reproducible benchmark under:

~~~text
benchmarks/agent/
~~~

The benchmark measures whether CodeIntel improves:

- deterministic code retrieval
- repository understanding
- impact analysis
- Claude Code
- Codex

## Benchmark matrix

Deterministic:

~~~text
rg
CodeIntel
~~~

Agentic:

~~~text
Claude Code
Claude Code + CodeIntel MCP
Codex
Codex + CodeIntel MCP
~~~

## Architecture

~~~text
benchmarks/agent/
├── README.md
├── pyproject.toml
├── benchmark.py
│
├── config/
│   ├── default.yaml
│   └── agents.yaml
│
├── corpus/
│   ├── synthetic/
│   │   ├── rust-cross-file/
│   │   ├── typescript-service/
│   │   └── python-dependency/
│   └── manifests/
│
├── tasks/
│   ├── locate-symbol.yaml
│   ├── relevant-files.yaml
│   ├── impact-analysis.yaml
│   └── change-planning.yaml
│
├── runners/
│   ├── base.py
│   ├── rg.py
│   ├── codeintel.py
│   ├── claude.py
│   └── codex.py
│
├── scoring/
│   ├── retrieval.py
│   ├── graph.py
│   ├── agent.py
│   └── cost.py
│
├── schemas/
│   ├── task.schema.json
│   └── result.schema.json
│
├── tests/
└── results/
    └── .gitkeep
~~~

## Harness

The benchmark harness uses Python.

CodeIntel itself remains Rust.

Python is used for:

- subprocess orchestration
- Claude/Codex CLI execution
- JSON/JSONL/CSV
- statistics
- scoring
- timeout handling
- result aggregation

## Corpus

Two corpus types are required.

### Synthetic

Versioned fixtures with exact ground truth.

Initial languages:

- Rust
- TypeScript
- Python

Ground truth can contain:

- expected symbols
- relevant files
- direct callers
- transitive callers
- blast radius

### Real repositories

Any repository can be passed by path:

~~~bash
python benchmarks/agent/benchmark.py \
  --repo /path/to/repository
~~~

The original repository must never be modified.

Agent runs use isolated temporary copies or worktrees.

## Tasks

Required task types:

~~~text
locate-symbol
relevant-files
impact-analysis
change-planning
~~~

Example:

~~~yaml
id: rust-payment-impact
type: impact-analysis

prompt: >
  Find process_payment and identify all files and
  symbols affected if its behavior changes.

expected:
  symbols:
    - process_payment

  relevant_files:
    - src/payment.rs
    - src/api.rs

  direct_callers:
    - checkout
~~~

v1 tasks are read-only.

Patch generation and edit scoring are deferred.

## Runner contract

Every runner returns normalized data.

~~~json
{
  "runner": "codeintel",
  "task_id": "rust-payment-impact",
  "success": true,
  "duration_ms": 42,
  "files": [],
  "symbols": [],
  "tool_calls": [],
  "tokens": {
    "input": null,
    "output": null
  },
  "stdout": "",
  "stderr": "",
  "exit_code": 0
}
~~~

Runners execute.

Scorers evaluate.

A runner must never score its own output.

## rg runner

Acts as lexical baseline.

Capture:

- duration
- matched files
- matched lines
- candidate count

## CodeIntel runner

Supports:

~~~text
search
context
symbol
impact
~~~

Modes:

~~~text
cold
warm
~~~

Cold removes benchmark-local `.codeintel`.

Warm indexes once and measures subsequent queries.

## Claude Code runner

Execute real Claude Code CLI using configurable command templates.

Modes:

~~~text
claude
claude-codeintel
~~~

Capture when observable:

- duration
- exit code
- stdout
- stderr
- files read
- tool calls
- input tokens
- output tokens

Unavailable telemetry must remain null.

Never fabricate metrics.

## Codex runner

Same runner contract as Claude.

Modes:

~~~text
codex
codex-codeintel
~~~

## CodeIntel isolation

Agent baseline:

~~~text
Claude/Codex
without CodeIntel MCP
~~~

Experiment:

~~~text
same agent
same task
same repository snapshot
same model/config
same timeout
+
CodeIntel MCP
~~~

Only CodeIntel availability should change.

## Fair A/B runs

A valid comparison requires:

~~~text
same repository snapshot
same prompt
same agent
same model
same timeout
same configuration
~~~

Run ordering alternates across repetitions:

~~~text
baseline
codeintel
codeintel
baseline
...
~~~

This reduces order/cache bias.

## Deterministic metrics

Required:

~~~text
latency_ms
files_returned
precision
recall
f1
precision_at_k
recall_at_k
mrr
~~~

Graph metrics:

~~~text
direct_caller_precision
direct_caller_recall
blast_radius_error
~~~

## Agent metrics

When observable:

~~~text
success
duration_ms
files_read
files_relevant
irrelevant_files_read
file_precision
file_recall
tool_calls
input_tokens
output_tokens
total_tokens
~~~

Comparisons:

~~~text
token_reduction_pct
time_reduction_pct
irrelevant_file_reduction_pct
recall_delta
success_delta
~~~

## Cost

Optional.

Only calculate cost when:

- token telemetry exists
- user provides pricing configuration

Provider pricing must not be hardcoded as authoritative benchmark data.

## Results

Each execution creates:

~~~text
benchmarks/agent/results/
└── <run-id>/
    ├── run.json
    ├── results.jsonl
    ├── summary.json
    └── summary.csv
~~~

`run.json` records:

- timestamp
- CodeIntel version
- git SHA
- OS
- architecture
- Python version
- Claude version
- Codex version
- repository
- selected runners
- random seed
- configuration

Generated results are gitignored.

## CLI

Deterministic:

~~~bash
python benchmarks/agent/benchmark.py \
  --corpus synthetic \
  --runner rg \
  --runner codeintel
~~~

Agents:

~~~bash
python benchmarks/agent/benchmark.py \
  --corpus synthetic \
  --runner claude \
  --runner claude-codeintel \
  --runner codex \
  --runner codex-codeintel
~~~

Real repository:

~~~bash
python benchmarks/agent/benchmark.py \
  --repo /path/to/repository \
  --runner codeintel \
  --runner claude-codeintel
~~~

Everything:

~~~bash
python benchmarks/agent/benchmark.py \
  --corpus synthetic \
  --all \
  --repeat 5
~~~

## Synthetic fixtures

### Rust

Cover:

- same-file calls
- imported cross-file functions
- transitive impact
- unresolved method calls
- qualified paths

The known v0.5 case:

~~~rust
crate::payment::process_payment()
~~~

must have explicit ground truth.

This lets future CodeIntel versions measure improvement in qualified-call
resolution.

### TypeScript

Cover:

- exports/imports
- cross-file functions
- service dependencies
- member-call ambiguity
- relevant-file selection

### Python

Cover:

- imported functions
- direct callers
- transitive callers
- cross-file impact

## Safety

The harness must:

- never mutate original repositories
- run agents in temporary copies/worktrees
- enforce timeouts
- terminate subprocess trees
- avoid logging secrets
- never persist environment variables
- never print API keys
- reject unsafe command templates
- treat task manifests as data, not shell programs

## Reproducibility

Each run records:

- benchmark configuration
- source repository revision
- CodeIntel revision/version
- agent CLI versions
- random seed
- environment metadata

Default scoring is deterministic.

## Tests

Unit tests:

- task parsing
- result normalization
- precision
- recall
- F1
- precision@k
- recall@k
- MRR
- graph scoring
- serialization
- timeout behavior
- command validation

Integration tests:

- rg synthetic fixture
- CodeIntel synthetic fixture
- cold/warm CodeIntel
- result generation
- repository isolation

Claude/Codex real executions are opt-in.

They may consume quota and must not run in the normal test suite.

## Success criteria

v1 is complete when:

1. Rust/TypeScript/Python synthetic corpus works.
2. rg and CodeIntel are automatically comparable.
3. Claude Code runner works.
4. Codex runner works.
5. Both agents support with/without CodeIntel.
6. Real repository paths are supported safely.
7. Precision/recall/F1/MRR are calculated.
8. Graph metrics are calculated.
9. Token/tool telemetry is captured when exposed.
10. JSONL/JSON/CSV reports are generated.
11. Automated tests cover the harness.
12. Benchmark code does not change CodeIntel runtime behavior.

## Non-goals v1

Not included:

- dashboard
- hosted service
- distributed benchmark
- provider APIs
- automatic pricing lookup
- patch grading
- LLM-as-judge as primary ground truth
- embeddings
- changes to CodeIntel runtime

## Future

~~~text
v1.1
- code-edit tasks
- patch correctness
- test-pass scoring

v1.2
- incremental graph benchmarks
- larger public corpora

v2
- historical repo tasks
- regression datasets
- CI trend tracking
- dashboard
~~~
