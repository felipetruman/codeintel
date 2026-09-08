# CodeIntel Agent Benchmark v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible benchmark inside `benchmarks/agent/` comparing `rg`, CodeIntel, Claude Code, Claude Code + CodeIntel MCP, Codex, and Codex + CodeIntel MCP on synthetic and real repositories.

**Architecture:** A Python harness orchestrates isolated benchmark runs and normalizes every runner into one result schema. Runners only execute tools; scoring is independent and ground-truth driven. Real repositories are copied into temporary workspaces before any benchmark execution.

**Tech Stack:** Python 3.11+, PyYAML 6.x, pytest 8.x, stdlib subprocess/json/csv/tempfile/shutil, installed `rg`, `codeintel`, `claude`, and `codex` CLIs.

**Spec:** `docs/superpowers/specs/2026-09-08-codeintel-agent-benchmark-design.md`

## Global Constraints

- Benchmark lives under `benchmarks/agent/`.
- CodeIntel Rust runtime behavior must not change.
- Synthetic fixtures: Rust, TypeScript, Python.
- Real repository benchmark must never mutate the original repository.
- Agent benchmark variants must use identical repository snapshots and prompts.
- Missing telemetry is `null`; metrics must never be fabricated.
- Claude/Codex real runs are opt-in and excluded from normal tests.
- Generated benchmark result directories are not committed.
- Task manifests are data and must never execute arbitrary shell.
- Subprocesses require timeout and process-group termination.
- Scoring must be deterministic for a fixed result and ground truth.
- Provider pricing is user supplied; no authoritative mutable pricing is embedded.

---

## File Map

~~~text
benchmarks/
├── __init__.py
└── agent/
    ├── __init__.py
    ├── README.md
    ├── pyproject.toml
    ├── benchmark.py
    ├── models.py
    ├── manifests.py
    ├── process.py
    ├── isolation.py
    ├── reporting.py
    ├── scheduler.py
    │
    ├── config/
    │   ├── default.yaml
    │   └── agents.yaml
    │
    ├── corpus/
    │   └── synthetic/
    │       ├── rust-cross-file/
    │       ├── typescript-service/
    │       └── python-dependency/
    │
    ├── tasks/
    │   ├── locate-symbol.yaml
    │   ├── relevant-files.yaml
    │   ├── impact-analysis.yaml
    │   └── change-planning.yaml
    │
    ├── runners/
    │   ├── __init__.py
    │   ├── base.py
    │   ├── rg.py
    │   ├── codeintel.py
    │   ├── agent_base.py
    │   ├── claude.py
    │   └── codex.py
    │
    ├── scoring/
    │   ├── __init__.py
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
    │   ├── test_models.py
    │   ├── test_manifests.py
    │   ├── test_process.py
    │   ├── test_retrieval_scoring.py
    │   ├── test_graph_scoring.py
    │   ├── test_rg_runner.py
    │   ├── test_codeintel_runner.py
    │   ├── test_isolation.py
    │   ├── test_reporting.py
    │   ├── test_scheduler.py
    │   └── test_agent_runners.py
    │
    └── results/
        └── .gitkeep
~~~

---

# Task 1: Core Models + Safe Process Runner

**Files:**
- Create: `benchmarks/__init__.py`
- Create: `benchmarks/agent/__init__.py`
- Create: `benchmarks/agent/pyproject.toml`
- Create: `benchmarks/agent/models.py`
- Create: `benchmarks/agent/process.py`
- Create: `benchmarks/agent/tests/test_models.py`
- Create: `benchmarks/agent/tests/test_process.py`

**Interfaces:**

Produces:

~~~python
@dataclass(frozen=True)
class TokenUsage:
    input: int | None = None
    output: int | None = None

@dataclass
class BenchmarkResult:
    runner: str
    task_id: str
    success: bool
    duration_ms: float
    files: list[str]
    symbols: list[str]
    tool_calls: list[str]
    tokens: TokenUsage
    stdout: str
    stderr: str
    exit_code: int | None
    metadata: dict[str, object]

@dataclass(frozen=True)
class ProcessResult:
    argv: list[str]
    stdout: str
    stderr: str
    exit_code: int | None
    duration_ms: float
    timed_out: bool

def run_process(
    argv: list[str],
    cwd: Path,
    timeout_seconds: float,
    env: Mapping[str, str] | None = None,
) -> ProcessResult
~~~

- [ ] **Step 1: Create Python project metadata**

Create `benchmarks/agent/pyproject.toml`:

~~~toml
[project]
name = "codeintel-agent-benchmark"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "PyYAML>=6.0,<7.0",
]

[project.optional-dependencies]
test = [
  "pytest>=8.0,<9.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
~~~

- [ ] **Step 2: Write failing model tests**

Create tests asserting:

~~~python
from benchmarks.agent.models import BenchmarkResult, TokenUsage

def test_result_serializes_missing_tokens_as_null():
    result = BenchmarkResult(
        runner="rg",
        task_id="x",
        success=True,
        duration_ms=1.5,
        files=["src/a.rs"],
        symbols=[],
        tool_calls=[],
        tokens=TokenUsage(),
        stdout="",
        stderr="",
        exit_code=0,
        metadata={},
    )

    data = result.to_dict()

    assert data["tokens"] == {
        "input": None,
        "output": None,
        "total": None,
    }
~~~

- [ ] **Step 3: Verify RED**

Run:

~~~bash
python -m pytest benchmarks/agent/tests/test_models.py -q
~~~

Expected: FAIL because `benchmarks.agent.models` does not exist.

- [ ] **Step 4: Implement models**

Implement `TokenUsage.total` and `BenchmarkResult.to_dict()` using dataclasses only.

- [ ] **Step 5: Write process timeout tests**

Test:

~~~python
def test_process_timeout_terminates_child(tmp_path):
    result = run_process(
        [
            sys.executable,
            "-c",
            "import time; time.sleep(30)",
        ],
        cwd=tmp_path,
        timeout_seconds=0.1,
    )

    assert result.timed_out is True
    assert result.exit_code is None
    assert result.duration_ms < 5000
~~~

- [ ] **Step 6: Verify RED**

~~~bash
python -m pytest benchmarks/agent/tests/test_process.py -q
~~~

- [ ] **Step 7: Implement safe subprocess execution**

Requirements:

~~~text
shell=False
start_new_session=True
capture stdout/stderr
monotonic wall-clock timing
SIGTERM process group on timeout
SIGKILL fallback if necessary
never serialize environment variables
~~~

- [ ] **Step 8: GREEN**

~~~bash
python -m pytest \
  benchmarks/agent/tests/test_models.py \
  benchmarks/agent/tests/test_process.py \
  -q
~~~

- [ ] **Step 9: Commit**

~~~bash
git add benchmarks
git -c commit.gpgsign=false commit \
  -m "feat: add benchmark core runtime"
~~~

---

# Task 2: Task Manifests + Synthetic Corpus

**Files:**
- Create: `benchmarks/agent/manifests.py`
- Create: `benchmarks/agent/schemas/task.schema.json`
- Create: `benchmarks/agent/tasks/*.yaml`
- Create: `benchmarks/agent/corpus/synthetic/*`
- Create: `benchmarks/agent/tests/test_manifests.py`

**Interfaces:**

~~~python
@dataclass(frozen=True)
class GroundTruth:
    files: tuple[str, ...]
    symbols: tuple[str, ...]
    direct_callers: tuple[str, ...]
    impacted: tuple[str, ...]
    blast_radius: int | None

@dataclass(frozen=True)
class BenchmarkTask:
    id: str
    type: str
    query: str
    prompt: str
    corpus: str
    expected: GroundTruth

def load_task(path: Path) -> BenchmarkTask
def load_tasks(path: Path) -> list[BenchmarkTask]
~~~

- [ ] **Step 1: Write parser tests**

Tests must reject:

~~~yaml
id: ""
type: shell-command
prompt: "x"
command: "rm -rf /"
~~~

and accept supported types:

~~~text
locate-symbol
relevant-files
impact-analysis
change-planning
~~~

- [ ] **Step 2: Verify RED**

~~~bash
python -m pytest benchmarks/agent/tests/test_manifests.py -q
~~~

- [ ] **Step 3: Implement strict YAML parser**

Use `yaml.safe_load`.

Reject unknown task types.

Ignore no fields silently: validate known top-level keys.

- [ ] **Step 4: Create Rust fixture**

Structure:

~~~text
rust-cross-file/
└── src/
    ├── lib.rs
    ├── payment.rs
    ├── api.rs
    └── checkout.rs
~~~

Required graph:

~~~text
submit_order
   ↓
checkout
   ↓
process_payment
   ↓
validate_payment
~~~

Also include:

~~~rust
crate::payment::qualified_payment()
~~~

as explicit ground truth for the known v0.5 qualified-call limitation.

- [ ] **Step 5: Create TypeScript fixture**

Required graph:

~~~text
routeCheckout()
   ↓
checkout()
   ↓
processPayment()
~~~

Include one member call:

~~~typescript
gateway.process()
~~~

which must remain distinguishable from a free function call.

- [ ] **Step 6: Create Python fixture**

Required graph:

~~~text
route_checkout()
   ↓
checkout()
   ↓
process_payment()
~~~

- [ ] **Step 7: Create four task manifests**

Each task must include exact expected files/symbols.

- [ ] **Step 8: GREEN**

~~~bash
python -m pytest benchmarks/agent/tests/test_manifests.py -q
~~~

- [ ] **Step 9: Commit**

~~~bash
git add benchmarks/agent
git -c commit.gpgsign=false commit \
  -m "test: add benchmark corpora and ground truth"
~~~

---

# Task 3: Retrieval + Graph Scoring

**Files:**
- Create: `benchmarks/agent/scoring/__init__.py`
- Create: `benchmarks/agent/scoring/retrieval.py`
- Create: `benchmarks/agent/scoring/graph.py`
- Create: `benchmarks/agent/scoring/agent.py`
- Create: `benchmarks/agent/scoring/cost.py`
- Create: `benchmarks/agent/tests/test_retrieval_scoring.py`
- Create: `benchmarks/agent/tests/test_graph_scoring.py`

**Interfaces:**

~~~python
def precision(
    returned: Sequence[str],
    expected: Sequence[str],
) -> float

def recall(
    returned: Sequence[str],
    expected: Sequence[str],
) -> float

def f1(precision_value: float, recall_value: float) -> float

def precision_at_k(
    returned: Sequence[str],
    expected: Sequence[str],
    k: int,
) -> float

def recall_at_k(
    returned: Sequence[str],
    expected: Sequence[str],
    k: int,
) -> float

def reciprocal_rank(
    returned: Sequence[str],
    expected: Sequence[str],
) -> float

def graph_metrics(
    direct_callers: Sequence[str],
    expected_callers: Sequence[str],
    blast_radius: int | None,
    expected_blast_radius: int | None,
) -> dict[str, float | int | None]
~~~

- [ ] **Step 1: Write exact metric tests**

Cases:

~~~text
returned=[a,b,c]
expected=[a,c,d]

precision=2/3
recall=2/3
f1=2/3
precision@2=1/2
recall@2=1/3
MRR=1.0
~~~

Also test empty expected/returned inputs.

- [ ] **Step 2: RED**

~~~bash
python -m pytest \
  benchmarks/agent/tests/test_retrieval_scoring.py \
  benchmarks/agent/tests/test_graph_scoring.py \
  -q
~~~

- [ ] **Step 3: Implement pure deterministic scorers**

Normalize duplicate returned paths before scoring.

Do not reorder ranked results except duplicate removal.

- [ ] **Step 4: GREEN**

~~~bash
python -m pytest \
  benchmarks/agent/tests/test_retrieval_scoring.py \
  benchmarks/agent/tests/test_graph_scoring.py \
  -q
~~~

- [ ] **Step 5: Commit**

~~~bash
git add benchmarks/agent/scoring benchmarks/agent/tests
git -c commit.gpgsign=false commit \
  -m "feat: add benchmark scoring"
~~~

---

# Task 4: rg + CodeIntel Deterministic Runners

**Files:**
- Create: `benchmarks/agent/runners/__init__.py`
- Create: `benchmarks/agent/runners/base.py`
- Create: `benchmarks/agent/runners/rg.py`
- Create: `benchmarks/agent/runners/codeintel.py`
- Create: `benchmarks/agent/tests/test_rg_runner.py`
- Create: `benchmarks/agent/tests/test_codeintel_runner.py`

**Interfaces:**

~~~python
class Runner(Protocol):
    name: str

    def run(
        self,
        task: BenchmarkTask,
        repo: Path,
    ) -> BenchmarkResult:
        ...

class RgRunner:
    name = "rg"

class CodeIntelRunner:
    name = "codeintel"

    def __init__(
        self,
        binary: str = "codeintel",
        mode: Literal["cold", "warm"] = "warm",
    ) -> None:
        ...
~~~

- [ ] **Step 1: RED rg integration test**

Run against Rust fixture and assert `process_payment` returns expected files.

- [ ] **Step 2: Implement rg runner**

Use:

~~~bash
rg --json --line-number --column <query> <repo>
~~~

Parse JSON events.

Never parse colored human output.

- [ ] **Step 3: GREEN rg**

~~~bash
python -m pytest benchmarks/agent/tests/test_rg_runner.py -q
~~~

- [ ] **Step 4: RED CodeIntel integration**

Assert:

~~~text
search → files
context → ranked files
symbol → symbols/callers
impact → impacted/direct_callers/blast radius metadata
~~~

- [ ] **Step 5: Implement CodeIntel runner**

Use JSON stdout from:

~~~bash
codeintel search <query> <repo>
codeintel context <task> <repo> --limit 20
codeintel symbol <symbol> <repo>
codeintel impact <symbol> <repo> --depth 8
~~~

Cold mode deletes only:

~~~text
<isolated benchmark repo>/.codeintel
~~~

Warm mode executes:

~~~bash
codeintel index <repo>
~~~

before measured queries.

- [ ] **Step 6: GREEN deterministic runners**

~~~bash
python -m pytest \
  benchmarks/agent/tests/test_rg_runner.py \
  benchmarks/agent/tests/test_codeintel_runner.py \
  -q
~~~

- [ ] **Step 7: Commit**

~~~bash
git add benchmarks/agent
git -c commit.gpgsign=false commit \
  -m "feat: add deterministic benchmark runners"
~~~

---

# Task 5: Repository Isolation

**Files:**
- Create: `benchmarks/agent/isolation.py`
- Create: `benchmarks/agent/tests/test_isolation.py`

**Interfaces:**

~~~python
@contextmanager
def isolated_repository(source: Path) -> Iterator[Path]:
    ...

def repository_digest(
    root: Path,
    exclude: Iterable[str] = (".git", ".codeintel"),
) -> str:
    ...
~~~

- [ ] **Step 1: Write mutation safety test**

Create source repo with:

~~~text
src/a.rs
README.md
.git/
~~~

Inside isolated copy:

~~~text
modify src/a.rs
create .codeintel/index.json
create arbitrary agent output
~~~

After context exit assert source digest unchanged.

- [ ] **Step 2: RED**

~~~bash
python -m pytest benchmarks/agent/tests/test_isolation.py -q
~~~

- [ ] **Step 3: Implement isolation**

Requirements:

~~~text
source must exist
source must be directory
temporary root via tempfile.TemporaryDirectory
copytree with symlinks=True
exclude .git/.codeintel from copied runtime state
never run agent inside original repository
cleanup temporary directory on success/failure
~~~

- [ ] **Step 4: GREEN**

~~~bash
python -m pytest benchmarks/agent/tests/test_isolation.py -q
~~~

- [ ] **Step 5: Commit**

~~~bash
git add benchmarks/agent
git -c commit.gpgsign=false commit \
  -m "feat: isolate benchmark repositories"
~~~

---

# Task 6: Result Persistence + Console/CSV Reporting

**Files:**
- Create: `benchmarks/agent/reporting.py`
- Create: `benchmarks/agent/schemas/result.schema.json`
- Create: `benchmarks/agent/tests/test_reporting.py`
- Modify: `.gitignore`
- Create: `benchmarks/agent/results/.gitkeep`

**Interfaces:**

~~~python
@dataclass(frozen=True)
class RunMetadata:
    run_id: str
    timestamp: str
    codeintel_version: str | None
    git_sha: str | None
    python_version: str
    platform: str
    architecture: str
    claude_version: str | None
    codex_version: str | None
    seed: int
    runners: tuple[str, ...]

def write_run(
    output_dir: Path,
    metadata: RunMetadata,
    results: Sequence[dict[str, object]],
) -> Path

def summarize(
    results: Sequence[dict[str, object]],
) -> list[dict[str, object]]
~~~

- [ ] **Step 1: RED reporting tests**

Verify generation of:

~~~text
run.json
results.jsonl
summary.json
summary.csv
~~~

- [ ] **Step 2: Implement reporting**

Use UTF-8 and deterministic JSON key ordering.

One JSONL object per execution.

- [ ] **Step 3: Update `.gitignore`**

Add:

~~~gitignore
/benchmarks/agent/results/*
!/benchmarks/agent/results/.gitkeep
~~~

- [ ] **Step 4: GREEN**

~~~bash
python -m pytest benchmarks/agent/tests/test_reporting.py -q
~~~

- [ ] **Step 5: Commit**

~~~bash
git add .gitignore benchmarks/agent
git -c commit.gpgsign=false commit \
  -m "feat: persist benchmark reports"
~~~

---

# Task 7: Benchmark Scheduler + Deterministic CLI

**Files:**
- Create: `benchmarks/agent/scheduler.py`
- Create: `benchmarks/agent/benchmark.py`
- Create: `benchmarks/agent/config/default.yaml`
- Create: `benchmarks/agent/tests/test_scheduler.py`

**Interfaces:**

~~~python
def balanced_order(
    runners: Sequence[str],
    repeat: int,
) -> list[str]:
    ...

def main(argv: Sequence[str] | None = None) -> int:
    ...
~~~

- [ ] **Step 1: RED balanced-order test**

For baseline/experiment repeated four times:

~~~text
baseline
codeintel
codeintel
baseline
baseline
codeintel
codeintel
baseline
~~~

- [ ] **Step 2: Implement scheduler**

Ordering must be deterministic.

Record seed even when no randomization occurs.

- [ ] **Step 3: RED CLI test**

Test:

~~~bash
python benchmarks/agent/benchmark.py \
  --corpus synthetic \
  --runner rg \
  --runner codeintel
~~~

Expected:

~~~text
exit 0
creates run directory
contains rg results
contains codeintel results
contains scoring
~~~

- [ ] **Step 4: Implement CLI**

Arguments:

~~~text
--corpus synthetic
--repo PATH
--tasks PATH
--runner NAME (repeatable)
--all
--repeat N
--seed N
--output PATH
--codeintel-mode cold|warm
--timeout SECONDS
~~~

Require exactly one of:

~~~text
--corpus
--repo
~~~

- [ ] **Step 5: GREEN**

~~~bash
python -m pytest benchmarks/agent/tests/test_scheduler.py -q
~~~

Smoke:

~~~bash
python benchmarks/agent/benchmark.py \
  --corpus synthetic \
  --runner rg \
  --runner codeintel \
  --repeat 1
~~~

- [ ] **Step 6: Commit**

~~~bash
git add benchmarks/agent
git -c commit.gpgsign=false commit \
  -m "feat: add benchmark scheduler and cli"
~~~

---

# Task 8: Generic Agent Runner

**Files:**
- Create: `benchmarks/agent/runners/agent_base.py`
- Create: `benchmarks/agent/config/agents.yaml`
- Create: `benchmarks/agent/tests/test_agent_runners.py`

**Interfaces:**

~~~python
@dataclass(frozen=True)
class AgentCommand:
    name: str
    argv: tuple[str, ...]
    timeout_seconds: float
    codeintel_enabled: bool

def render_command(
    template: Sequence[str],
    prompt: str,
    repo: Path,
) -> list[str]

def validate_command_template(
    template: Sequence[str],
) -> None
~~~

Allowed substitutions:

~~~text
{prompt}
{repo}
~~~

No shell expansion.

- [ ] **Step 1: RED command validation**

Reject:

~~~text
empty argv
shell metacharacter wrapper such as ["sh", "-c", "..."]
unknown placeholders
missing {prompt}
~~~

Accept direct executable argv templates.

- [ ] **Step 2: Implement command rendering**

Never call `shell=True`.

Prompt is one argv element after formatting.

- [ ] **Step 3: Implement generic agent execution**

Capture:

~~~text
stdout
stderr
exit code
duration
tokens when parsable
tool calls when parsable
files when parsable
raw output retained
~~~

Unknown telemetry remains null/empty.

- [ ] **Step 4: GREEN**

~~~bash
python -m pytest benchmarks/agent/tests/test_agent_runners.py -q
~~~

- [ ] **Step 5: Commit**

~~~bash
git add benchmarks/agent
git -c commit.gpgsign=false commit \
  -m "feat: add generic agent benchmark runner"
~~~

---

# Task 9: Claude Code Runner

**Files:**
- Create: `benchmarks/agent/runners/claude.py`
- Modify: `benchmarks/agent/config/agents.yaml`
- Modify: `benchmarks/agent/tests/test_agent_runners.py`

**Interfaces:**

~~~python
class ClaudeRunner:
    name = "claude"

class ClaudeCodeIntelRunner:
    name = "claude-codeintel"
~~~

- [ ] **Step 1: Inspect installed CLI contract**

Run:

~~~bash
claude --version
claude --help
~~~

Record version in benchmark run metadata.

- [ ] **Step 2: Add configurable Claude template**

Default config must invoke Claude non-interactively and pass the benchmark prompt as an argv value.

The template remains overridable from YAML.

- [ ] **Step 3: Add mocked unit tests**

Mock subprocess output containing:

~~~json
{
  "result": "analysis",
  "usage": {
    "input_tokens": 100,
    "output_tokens": 20
  }
}
~~~

Assert normalized tokens:

~~~text
input=100
output=20
total=120
~~~

- [ ] **Step 4: Implement CodeIntel variant**

`claude` baseline must not inject benchmark CodeIntel configuration.

`claude-codeintel` must create benchmark-local MCP configuration pointing to:

~~~bash
codeintel mcp <isolated-repo>
~~~

Any generated MCP config must live inside the isolated benchmark workspace or temporary benchmark directory.

- [ ] **Step 5: Unit GREEN**

~~~bash
python -m pytest benchmarks/agent/tests/test_agent_runners.py -q
~~~

- [ ] **Step 6: Opt-in real smoke**

Only when explicitly invoked:

~~~bash
CODEINTEL_BENCH_REAL_AGENTS=1 \
python benchmarks/agent/benchmark.py \
  --corpus synthetic \
  --runner claude \
  --runner claude-codeintel \
  --repeat 1
~~~

Verify same task prompt and source snapshot.

- [ ] **Step 7: Commit**

~~~bash
git add benchmarks/agent
git -c commit.gpgsign=false commit \
  -m "feat: benchmark Claude with CodeIntel"
~~~

---

# Task 10: Codex Runner

**Files:**
- Create: `benchmarks/agent/runners/codex.py`
- Modify: `benchmarks/agent/config/agents.yaml`
- Modify: `benchmarks/agent/tests/test_agent_runners.py`

**Interfaces:**

~~~python
class CodexRunner:
    name = "codex"

class CodexCodeIntelRunner:
    name = "codex-codeintel"
~~~

- [ ] **Step 1: Inspect installed CLI contract**

Run:

~~~bash
codex --version
codex --help
codex exec --help
~~~

Record version.

- [ ] **Step 2: Add configurable Codex template**

Default must use non-interactive execution.

No `bash -c`.

- [ ] **Step 3: Add mocked telemetry tests**

Feed JSON/JSONL fixture output and assert available token/tool telemetry is normalized.

Unknown fields must not crash parsing.

- [ ] **Step 4: Implement CodeIntel variant**

Inject benchmark-local MCP configuration only into the experiment variant.

Baseline receives no benchmark CodeIntel MCP.

- [ ] **Step 5: Unit GREEN**

~~~bash
python -m pytest benchmarks/agent/tests/test_agent_runners.py -q
~~~

- [ ] **Step 6: Opt-in real smoke**

~~~bash
CODEINTEL_BENCH_REAL_AGENTS=1 \
python benchmarks/agent/benchmark.py \
  --corpus synthetic \
  --runner codex \
  --runner codex-codeintel \
  --repeat 1
~~~

- [ ] **Step 7: Commit**

~~~bash
git add benchmarks/agent
git -c commit.gpgsign=false commit \
  -m "feat: benchmark Codex with CodeIntel"
~~~

---

# Task 11: Agent Scoring + A/B Deltas

**Files:**
- Modify: `benchmarks/agent/scoring/agent.py`
- Modify: `benchmarks/agent/scoring/cost.py`
- Create: `benchmarks/agent/tests/test_agent_scoring.py`

**Interfaces:**

~~~python
def agent_metrics(
    files_read: Sequence[str],
    expected_files: Sequence[str],
) -> dict[str, float | int]

def percent_reduction(
    baseline: float | int | None,
    experiment: float | int | None,
) -> float | None

def compare_pair(
    baseline: BenchmarkResult,
    experiment: BenchmarkResult,
) -> dict[str, object]

def estimated_cost(
    tokens: TokenUsage,
    input_price_per_million: float | None,
    output_price_per_million: float | None,
) -> float | None
~~~

- [ ] **Step 1: RED**

Test:

~~~text
baseline tokens=1000
experiment tokens=750
token reduction=25%
~~~

Also:

~~~text
baseline time=10s
experiment time=8s
time reduction=20%
~~~

- [ ] **Step 2: Implement**

Zero baseline must return `None` rather than divide by zero.

Missing token telemetry returns `None`.

- [ ] **Step 3: GREEN**

~~~bash
python -m pytest benchmarks/agent/tests/test_agent_scoring.py -q
~~~

- [ ] **Step 4: Commit**

~~~bash
git add benchmarks/agent
git -c commit.gpgsign=false commit \
  -m "feat: score agent benchmark comparisons"
~~~

---

# Task 12: Full Matrix + README

**Files:**
- Create: `benchmarks/agent/README.md`
- Modify: `benchmarks/agent/benchmark.py`
- Modify: `README.md`

- [ ] **Step 1: Support all runner names**

~~~text
rg
codeintel
claude
claude-codeintel
codex
codex-codeintel
~~~

`--all` selects all six.

- [ ] **Step 2: Console report**

Required columns when available:

~~~text
Runner
Success
Recall
Precision
F1
Time
Input Tokens
Output Tokens
Total Tokens
~~~

- [ ] **Step 3: Write benchmark README**

Include commands:

~~~bash
python benchmarks/agent/benchmark.py \
  --corpus synthetic \
  --runner rg \
  --runner codeintel
~~~

~~~bash
python benchmarks/agent/benchmark.py \
  --corpus synthetic \
  --all \
  --repeat 5
~~~

~~~bash
python benchmarks/agent/benchmark.py \
  --repo /path/to/repository \
  --runner codeintel
~~~

- [ ] **Step 4: Add root README section**

Document benchmark as optional developer tooling.

Do not present benchmark dependencies as CodeIntel runtime dependencies.

- [ ] **Step 5: Commit**

~~~bash
git add README.md benchmarks/agent
git -c commit.gpgsign=false commit \
  -m "docs: document agent benchmark"
~~~

---

# Task 13: Full Verification

**Files:**
- No production changes expected.

- [ ] **Step 1: Python tests**

~~~bash
python -m pytest benchmarks/agent/tests -q
~~~

- [ ] **Step 2: Existing Rust regression**

~~~bash
cargo fmt --check
cargo test --locked
cargo clippy --locked --all-targets --all-features -- -D warnings
cargo build --release --locked
~~~

- [ ] **Step 3: Deterministic real smoke**

~~~bash
python benchmarks/agent/benchmark.py \
  --corpus synthetic \
  --runner rg \
  --runner codeintel \
  --repeat 2
~~~

Verify:

~~~text
results.jsonl exists
summary.json exists
summary.csv exists
both runners present
precision/recall/f1 present
~~~

- [ ] **Step 4: Real repository isolation smoke**

~~~bash
BEFORE="$(git status --porcelain=v1 -uall)"

python benchmarks/agent/benchmark.py \
  --repo . \
  --runner codeintel \
  --repeat 1

AFTER="$(git status --porcelain=v1 -uall)"

test "$BEFORE" = "$AFTER"
~~~

- [ ] **Step 5: Check generated results ignored**

~~~bash
test -z "$(git status --porcelain -- benchmarks/agent/results)"
~~~

except tracked `.gitkeep`.

- [ ] **Step 6: Verify CodeIntel unchanged**

~~~bash
git diff main...HEAD -- src Cargo.toml Cargo.lock
~~~

Expected: no benchmark-driven runtime modifications unless explicitly justified and reviewed separately.

- [ ] **Step 7: Final tree**

~~~bash
git status --short
git log --oneline main..HEAD
~~~

Expected: clean working tree.

---

# Acceptance Matrix

~~~text
Synthetic Rust corpus                 required
Synthetic TypeScript corpus           required
Synthetic Python corpus               required

rg runner                             required
CodeIntel runner                      required

Claude baseline                       required
Claude + CodeIntel                    required
Codex baseline                        required
Codex + CodeIntel                     required

precision                             required
recall                                required
f1                                    required
precision@k                           required
recall@k                              required
MRR                                   required

direct caller precision               required
direct caller recall                  required
blast radius error                    required

duration                              required
files read                            when observable
tool calls                            when observable
input tokens                          when observable
output tokens                         when observable

JSONL                                 required
JSON summary                          required
CSV summary                           required

real repo isolation                   required
timeout/process cleanup               required
normal tests do not consume quota     required
CodeIntel runtime unchanged           required
~~~

# Recommended Execution Order

~~~text
Task 1   core models/process
Task 2   corpus/manifests
Task 3   scoring
Task 4   rg/codeintel
Task 5   isolation
Task 6   reporting
Task 7   scheduler/CLI
Task 8   generic agent
Task 9   Claude
Task 10  Codex
Task 11  A/B scoring
Task 12  docs/full matrix
Task 13  verification
~~~
