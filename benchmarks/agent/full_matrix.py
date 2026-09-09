from __future__ import annotations

from dataclasses import dataclass

import argparse
from datetime import datetime, timezone
from pathlib import Path
import platform
import subprocess
from typing import Callable

from benchmarks.agent.isolation import isolated_repository, repository_digest
from benchmarks.agent.runners.base import Runner
from benchmarks.agent.comparisons import write_comparisons
from benchmarks.agent.manifests import (
    BenchmarkTask,
    load_tasks,
)
from benchmarks.agent.models import BenchmarkResult
from benchmarks.agent.reporting import (
    RunMetadata,
    write_run,
)
from benchmarks.agent.runner_matrix import (
    ALL_RUNNERS,
    balanced_runner_order,
    require_real_agent_opt_in,
    resolve_runner_names,
)
from benchmarks.agent.runners.claude import (
    ClaudeConfig,
    ClaudeRunner,
)
from benchmarks.agent.runners.codex import (
    CodexConfig,
    CodexRunner,
)
from benchmarks.agent.runners.codeintel import (
    CodeIntelRunner,
)
from benchmarks.agent.runners.rg import RgRunner
from benchmarks.agent.scheduler import score_result


@dataclass(frozen=True)
class RunnerSettings:
    codeintel_binary: str
    rg_binary: str
    codeintel_mode: str
    deterministic_timeout: float
    agent_timeout: float
    claude_model: str | None
    codex_model: str | None


@dataclass(frozen=True)
class MatrixSettings:
    repeat: int
    seed: int
    source_resolver: Callable[[BenchmarkTask], Path]


AGENT_ROOT = Path(__file__).resolve().parent


def _version(
    argv: list[str],
) -> str | None:
    try:
        process = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (
        OSError,
        subprocess.TimeoutExpired,
    ):
        return None

    if process.returncode != 0:
        return None

    value = process.stdout.strip()

    if not value:
        value = process.stderr.strip()

    return value.splitlines()[0] if value else None


def _git_sha(
    repo: Path,
) -> str | None:
    try:
        process = subprocess.run(
            [
                "git",
                "rev-parse",
                "HEAD",
            ],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (
        OSError,
        subprocess.TimeoutExpired,
    ):
        return None

    if process.returncode != 0:
        return None

    value = process.stdout.strip()

    return value or None


def build_runners(names: list[str], settings: RunnerSettings) -> dict[str, Runner]:
    claude_config = ClaudeConfig(
        model=settings.claude_model,
        timeout_seconds=settings.agent_timeout,
        codeintel_binary=settings.codeintel_binary,
    )
    codex_config = CodexConfig(
        model=settings.codex_model,
        timeout_seconds=settings.agent_timeout,
        codeintel_binary=settings.codeintel_binary,
    )
    factories = {
        "rg": lambda: RgRunner(
            binary=settings.rg_binary, timeout_seconds=settings.deterministic_timeout
        ),
        "codeintel": lambda: CodeIntelRunner(
            binary=settings.codeintel_binary,
            mode=settings.codeintel_mode,
            timeout_seconds=settings.deterministic_timeout,
        ),
        "claude": lambda: ClaudeRunner(False, claude_config),
        "claude-codeintel": lambda: ClaudeRunner(True, claude_config),
        "codex": lambda: CodexRunner(False, codex_config),
        "codex-codeintel": lambda: CodexRunner(True, codex_config),
    }
    return {name: factories[name]() for name in names}


def _synthetic_source(task: BenchmarkTask) -> Path:
    corpus = (AGENT_ROOT / "corpus").resolve()
    source = (corpus / task.corpus).resolve()
    if not source.is_relative_to(corpus):
        raise ValueError("synthetic corpus must stay inside the corpus directory")
    return source


def _repository_source(repo: Path | None) -> Path:
    if repo is None:
        raise ValueError("repository path is required")
    return repo.resolve()


def _task_source(task: BenchmarkTask, *, synthetic: bool, repo: Path | None) -> Path:
    source = _synthetic_source(task) if synthetic else _repository_source(repo)
    if not source.is_dir():
        raise FileNotFoundError(f"corpus/repository not found: {source}")
    return source


def _execute_one(
    task: BenchmarkTask, runner: Runner, snapshot: Path
) -> BenchmarkResult:
    with isolated_repository(snapshot) as isolated:
        before = repository_digest(isolated)
        try:
            result = runner.run(task, isolated)
        except (OSError, ValueError) as error:
            result = BenchmarkResult(
                runner.name,
                task.id,
                False,
                0.0,
                metadata={"runner_error": type(error).__name__},
            )
        if repository_digest(isolated) != before:
            result.success = False
            result.metadata["repository_mutated"] = True
        return score_result(task, result)


def execute_matrix(
    tasks: list[BenchmarkTask], runners: dict[str, Runner], settings: MatrixSettings
) -> list[BenchmarkResult]:
    runner_names = list(runners)
    repeat, seed = settings.repeat, settings.seed
    source_resolver = settings.source_resolver
    results = []
    for task in tasks:
        source = source_resolver(task)
        # Freeze once per task; all repetitions and arms consume identical bytes.
        with isolated_repository(source) as snapshot:
            digest = repository_digest(snapshot)
            for repetition in range(repeat):
                order = balanced_runner_order(runner_names, repetition, seed)
                for name in order:
                    result = _execute_one(task, runners[name], snapshot)
                    result.metadata.update(
                        repeat=repetition, sequence=len(results), source_digest=digest
                    )
                    results.append(result)
    return results


def _make_run_metadata(
    *, seed: int, runners: list[str], codeintel_binary: str
) -> RunMetadata:
    now = datetime.now(timezone.utc)
    return RunMetadata(
        run_id=now.strftime("%Y%m%dT%H%M%SZ"),
        timestamp=now.isoformat(),
        codeintel_version=_version([codeintel_binary, "--version"]),
        git_sha=_git_sha(AGENT_ROOT.parent.parent),
        python_version=platform.python_version(),
        platform=platform.platform(),
        architecture=platform.machine(),
        claude_version=(
            _version(["claude", "--version"]) if "claude" in runners else None
        ),
        codex_version=_version(["codex", "--version"]) if "codex" in runners else None,
        seed=seed,
        runners=tuple(runners),
    )


def print_results(
    results: list[BenchmarkResult],
) -> None:
    if not results:
        return

    print()

    print(
        "RUNNER                 "
        "TASK                     "
        "OK   MS        FILES TOKENS CALLS"
    )

    print("-" * 88)

    for result in results:
        tokens = str(result.tokens.total) if result.tokens.total is not None else "-"

        print(
            f"{result.runner:<22}"
            f"{result.task_id:<25}"
            f"{'yes' if result.success else 'no':<5}"
            f"{result.duration_ms:<10.1f}"
            f"{len(result.files):<6}"
            f"{tokens:<7}"
            f"{len(result.tool_calls)}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the CodeIntel Agent Benchmark full matrix."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--corpus", choices=["synthetic"])
    source.add_argument("--repo", type=Path)
    parser.add_argument("--tasks", type=Path, default=AGENT_ROOT / "tasks")
    parser.add_argument("--runner", action="append", default=[], choices=ALL_RUNNERS)
    parser.add_argument("--all", action="store_true", help="Select all six runners.")
    parser.add_argument(
        "--allow-real-agents",
        action="store_true",
        help="Explicitly allow Claude and Codex model calls.",
    )
    parser.add_argument(
        "--plan", action="store_true", help="Print matrix without executing runners."
    )
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output", type=Path, default=AGENT_ROOT / "results")
    parser.add_argument("--codeintel-binary", default="codeintel")
    parser.add_argument("--rg-binary", default="rg")
    parser.add_argument("--codeintel-mode", choices=["cold", "warm"], default="warm")
    parser.add_argument("--deterministic-timeout", type=float, default=60.0)
    parser.add_argument("--agent-timeout", type=float, default=300.0)
    parser.add_argument("--claude-model", default=None)
    parser.add_argument("--codex-model", default=None)
    return parser


def _print_plan(
    tasks: list[BenchmarkTask],
    runners: list[str],
    repeat: int,
    seed: int,
) -> None:
    print("CodeIntel Agent Benchmark — plan")

    print(f"tasks={len(tasks)}")

    print(f"repeat={repeat}")

    print(f"seed={seed}")

    print("runners=" + ",".join(runners))

    print()

    for repetition in range(repeat):
        order = balanced_runner_order(
            runners,
            repetition,
            seed,
        )

        print(f"repeat {repetition}: " + " -> ".join(order))


def main(
    argv: list[str] | None = None,
) -> int:
    parser = build_parser()

    args = parser.parse_args(argv)

    if args.repeat < 1:
        parser.error("--repeat must be >= 1")

    try:
        runner_names = resolve_runner_names(
            requested=args.runner,
            all_runners=args.all,
        )
    except ValueError as error:
        parser.error(str(error))

    tasks = load_tasks(args.tasks)
    if not tasks:
        parser.error("no benchmark tasks found")
    if len({task.id for task in tasks}) != len(tasks):
        parser.error("benchmark task IDs must be unique")

    if args.plan:
        _print_plan(
            tasks,
            runner_names,
            args.repeat,
            args.seed,
        )

        return 0

    try:
        require_real_agent_opt_in(
            runner_names,
            args.allow_real_agents,
        )
    except ValueError as error:
        parser.error(str(error))

    return _execute(args, runner_names, tasks)


def _execute(args, runner_names, tasks) -> int:
    runners = build_runners(
        runner_names,
        RunnerSettings(
            codeintel_binary=args.codeintel_binary,
            rg_binary=args.rg_binary,
            codeintel_mode=args.codeintel_mode,
            deterministic_timeout=args.deterministic_timeout,
            agent_timeout=args.agent_timeout,
            claude_model=args.claude_model,
            codex_model=args.codex_model,
        ),
    )

    source_resolver = lambda task: _task_source(
        task,
        synthetic=(args.corpus == "synthetic"),
        repo=args.repo,
    )

    results = execute_matrix(
        tasks,
        runners,
        MatrixSettings(
            repeat=args.repeat, seed=args.seed, source_resolver=source_resolver
        ),
    )

    metadata = _make_run_metadata(
        seed=args.seed,
        runners=runner_names,
        codeintel_binary=(args.codeintel_binary),
    )

    write_run(
        args.output,
        metadata,
        results,
    )

    comparisons = write_comparisons(
        args.output,
        tasks,
        results,
        runner_names,
    )

    print_results(results)

    print()
    print(f"results={len(results)}")

    print(f"comparisons=" f"{len(comparisons)}")

    print(f"output=" f"{args.output.resolve()}")

    return 0 if all(result.success for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
