from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, replace
from datetime import datetime, timezone
import inspect
import json
from pathlib import Path
import platform
import subprocess
from typing import Any, Callable

from benchmarks.agent.agent_metrics import compare_pair
from benchmarks.agent.isolation import isolated_repository
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
    ab_pairs,
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

    return (
        value.splitlines()[0]
        if value
        else None
    )


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


def _construct_compatible(
    cls: type,
    candidates: dict[str, Any],
):
    signature = inspect.signature(cls)

    kwargs = {
        name: value
        for name, value in candidates.items()
        if name in signature.parameters
    }

    return cls(**kwargs)


def build_runners(
    names: list[str],
    *,
    codeintel_binary: str,
    rg_binary: str,
    codeintel_mode: str,
    deterministic_timeout: float,
    agent_timeout: float,
    claude_model: str | None,
    codex_model: str | None,
) -> dict[str, Any]:
    runners: dict[str, Any] = {}

    for name in names:
        if name == "rg":
            runners[name] = _construct_compatible(
                RgRunner,
                {
                    "executable": rg_binary,
                    "binary": rg_binary,
                    "timeout_seconds": (
                        deterministic_timeout
                    ),
                },
            )

        elif name == "codeintel":
            runners[name] = _construct_compatible(
                CodeIntelRunner,
                {
                    "executable": (
                        codeintel_binary
                    ),
                    "binary": (
                        codeintel_binary
                    ),
                    "codeintel_binary": (
                        codeintel_binary
                    ),
                    "mode": (
                        codeintel_mode
                    ),
                    "timeout_seconds": (
                        deterministic_timeout
                    ),
                },
            )

        elif name in {
            "claude",
            "claude-codeintel",
        }:
            runners[name] = ClaudeRunner(
                codeintel_enabled=(
                    name
                    == "claude-codeintel"
                ),
                config=ClaudeConfig(
                    model=claude_model,
                    timeout_seconds=(
                        agent_timeout
                    ),
                    codeintel_binary=(
                        codeintel_binary
                    ),
                ),
            )

        elif name in {
            "codex",
            "codex-codeintel",
        }:
            runners[name] = CodexRunner(
                codeintel_enabled=(
                    name
                    == "codex-codeintel"
                ),
                config=CodexConfig(
                    model=codex_model,
                    timeout_seconds=(
                        agent_timeout
                    ),
                    codeintel_binary=(
                        codeintel_binary
                    ),
                ),
            )

        else:
            raise ValueError(
                f"unsupported runner: {name}"
            )

    return runners


def _task_source(
    task: BenchmarkTask,
    *,
    synthetic: bool,
    repo: Path | None,
) -> Path:
    if synthetic:
        source = (
            AGENT_ROOT
            / "corpus"
            / task.corpus
        )
    else:
        if repo is None:
            raise ValueError(
                "repository path is required"
            )

        source = repo

    source = source.resolve()

    if not source.exists():
        raise FileNotFoundError(
            f"corpus/repository not found: {source}"
        )

    return source


def _score(
    result: BenchmarkResult,
    task: BenchmarkTask,
) -> BenchmarkResult:
    signature = inspect.signature(
        score_result
    )

    names = list(
        signature.parameters
    )

    if len(names) != 2:
        raise RuntimeError(
            "unexpected score_result signature: "
            + str(signature)
        )

    if names[0].startswith("task"):
        scored = score_result(
            task,
            result,
        )
    else:
        scored = score_result(
            result,
            task,
        )

    if isinstance(
        scored,
        BenchmarkResult,
    ):
        return scored

    if isinstance(
        scored,
        dict,
    ):
        metadata = dict(
            result.metadata
        )

        metadata.update(scored)

        return replace(
            result,
            metadata=metadata,
        )

    raise TypeError(
        "score_result returned "
        f"unsupported type: {type(scored)!r}"
    )


def execute_matrix(
    *,
    tasks: list[BenchmarkTask],
    runner_names: list[str],
    runners: dict[str, Any],
    repeat: int,
    seed: int,
    source_resolver: Callable[
        [BenchmarkTask],
        Path,
    ],
) -> list[BenchmarkResult]:
    results: list[BenchmarkResult] = []

    sequence = 0

    for repetition in range(repeat):
        order = balanced_runner_order(
            runner_names,
            repetition,
            seed,
        )

        for task in tasks:
            source = source_resolver(task)

            for runner_name in order:
                runner = runners[
                    runner_name
                ]

                with isolated_repository(
                    source
                ) as isolated:
                    raw = runner.run(
                        task,
                        isolated,
                    )

                    scored = _score(
                        raw,
                        task,
                    )

                metadata = dict(
                    scored.metadata
                )

                metadata.update(
                    {
                        "repeat": repetition,
                        "sequence": sequence,
                        "source": str(source),
                    }
                )

                results.append(
                    replace(
                        scored,
                        metadata=metadata,
                    )
                )

                sequence += 1

    return results


def _make_run_metadata(
    *,
    seed: int,
    runners: list[str],
    codeintel_binary: str,
) -> RunMetadata:
    now = datetime.now(
        timezone.utc
    )

    values: dict[str, Any] = {
        "run_id": now.strftime(
            "%Y%m%dT%H%M%SZ"
        ),
        "timestamp": now.isoformat(),
        "codeintel_version": _version(
            [
                codeintel_binary,
                "--version",
            ]
        ),
        "git_sha": _git_sha(
            AGENT_ROOT.parent.parent
        ),
        "python_version": (
            platform.python_version()
        ),
        "platform": (
            platform.platform()
        ),
        "architecture": (
            platform.machine()
        ),
        "claude_version": _version(
            [
                "claude",
                "--version",
            ]
        ),
        "codex_version": _version(
            [
                "codex",
                "--version",
            ]
        ),
        "seed": seed,
        "runners": runners,
    }

    signature = inspect.signature(
        RunMetadata
    )

    kwargs = {
        name: values.get(name)
        for name in signature.parameters
    }

    return RunMetadata(**kwargs)


def _write_reports(
    output: Path,
    metadata: RunMetadata,
    results: list[BenchmarkResult],
) -> Any:
    output.mkdir(
        parents=True,
        exist_ok=True,
    )

    signature = inspect.signature(
        write_run
    )

    kwargs: dict[str, Any] = {}

    for name in signature.parameters:
        lowered = name.lower()

        if (
            "metadata" in lowered
            or lowered
            in {
                "run",
                "run_metadata",
            }
        ):
            kwargs[name] = metadata

        elif "result" in lowered:
            kwargs[name] = results

        elif (
            "output" in lowered
            or "directory" in lowered
            or lowered
            in {
                "path",
                "root",
            }
        ):
            kwargs[name] = output

        else:
            raise RuntimeError(
                "unexpected write_run parameter: "
                + name
            )

    return write_run(**kwargs)


def write_comparisons(
    output: Path,
    tasks: list[BenchmarkTask],
    results: list[BenchmarkResult],
    runner_names: list[str],
) -> list[dict[str, Any]]:
    task_map = {
        task.id: task
        for task in tasks
    }

    pairs = ab_pairs(
        runner_names
    )

    comparisons: list[
        dict[str, Any]
    ] = []

    grouped: dict[
        tuple[str, int, str],
        BenchmarkResult,
    ] = {}

    for result in results:
        repeat = result.metadata.get(
            "repeat"
        )

        if not isinstance(
            repeat,
            int,
        ):
            continue

        grouped[
            (
                result.task_id,
                repeat,
                result.runner,
            )
        ] = result

    repeats = sorted(
        {
            key[1]
            for key in grouped
        }
    )

    for task_id, task in task_map.items():
        for repetition in repeats:
            for (
                baseline_name,
                enhanced_name,
            ) in pairs:
                baseline = grouped.get(
                    (
                        task_id,
                        repetition,
                        baseline_name,
                    )
                )

                enhanced = grouped.get(
                    (
                        task_id,
                        repetition,
                        enhanced_name,
                    )
                )

                if (
                    baseline is None
                    or enhanced is None
                ):
                    continue

                comparison = compare_pair(
                    baseline,
                    enhanced,
                    task,
                )

                row = asdict(
                    comparison
                )

                row[
                    "repeat"
                ] = repetition

                comparisons.append(row)

    json_path = (
        output
        / "comparisons.json"
    )

    json_path.write_text(
        json.dumps(
            comparisons,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    csv_path = (
        output
        / "comparisons.csv"
    )

    flat_rows: list[
        dict[str, Any]
    ] = []

    for row in comparisons:
        flat_rows.append(
            {
                "task_id": (
                    row["task_id"]
                ),
                "repeat": (
                    row["repeat"]
                ),
                "baseline_runner": (
                    row["baseline_runner"]
                ),
                "enhanced_runner": (
                    row["enhanced_runner"]
                ),
                "success_delta": (
                    row["success_delta"]
                ),
                "duration_reduction_pct": (
                    row[
                        "duration_reduction_pct"
                    ]
                ),
                "files_read_reduction_pct": (
                    row[
                        "files_read_reduction_pct"
                    ]
                ),
                "input_token_reduction_pct": (
                    row[
                        "input_token_reduction_pct"
                    ]
                ),
                "output_token_reduction_pct": (
                    row[
                        "output_token_reduction_pct"
                    ]
                ),
                "total_token_reduction_pct": (
                    row[
                        "total_token_reduction_pct"
                    ]
                ),
                "file_precision_delta": (
                    row[
                        "file_precision_delta"
                    ]
                ),
                "file_recall_delta": (
                    row[
                        "file_recall_delta"
                    ]
                ),
                "tool_call_reduction_pct": (
                    row[
                        "tool_call_reduction_pct"
                    ]
                ),
            }
        )

    fieldnames = [
        "task_id",
        "repeat",
        "baseline_runner",
        "enhanced_runner",
        "success_delta",
        "duration_reduction_pct",
        "files_read_reduction_pct",
        "input_token_reduction_pct",
        "output_token_reduction_pct",
        "total_token_reduction_pct",
        "file_precision_delta",
        "file_recall_delta",
        "tool_call_reduction_pct",
    ]

    with csv_path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(
            flat_rows
        )

    return comparisons


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
        tokens = (
            str(result.tokens.total)
            if result.tokens.total
            is not None
            else "-"
        )

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
        description=(
            "Run the CodeIntel Agent "
            "Benchmark full matrix."
        )
    )

    source = (
        parser.add_mutually_exclusive_group(
            required=True
        )
    )

    source.add_argument(
        "--corpus",
        choices=["synthetic"],
    )

    source.add_argument(
        "--repo",
        type=Path,
    )

    parser.add_argument(
        "--tasks",
        type=Path,
        default=(
            AGENT_ROOT
            / "tasks"
        ),
    )

    parser.add_argument(
        "--runner",
        action="append",
        default=[],
        choices=ALL_RUNNERS,
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help="Select all six runners.",
    )

    parser.add_argument(
        "--allow-real-agents",
        action="store_true",
        help=(
            "Explicitly allow Claude "
            "and Codex model calls."
        ),
    )

    parser.add_argument(
        "--plan",
        action="store_true",
        help=(
            "Print matrix without "
            "executing runners."
        ),
    )

    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=0,
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=(
            AGENT_ROOT
            / "results"
        ),
    )

    parser.add_argument(
        "--codeintel-binary",
        default="codeintel",
    )

    parser.add_argument(
        "--rg-binary",
        default="rg",
    )

    parser.add_argument(
        "--codeintel-mode",
        choices=[
            "cold",
            "warm",
        ],
        default="warm",
    )

    parser.add_argument(
        "--deterministic-timeout",
        type=float,
        default=60.0,
    )

    parser.add_argument(
        "--agent-timeout",
        type=float,
        default=300.0,
    )

    parser.add_argument(
        "--claude-model",
        default=None,
    )

    parser.add_argument(
        "--codex-model",
        default=None,
    )

    return parser


def _print_plan(
    tasks: list[BenchmarkTask],
    runners: list[str],
    repeat: int,
    seed: int,
) -> None:
    print(
        "CodeIntel Agent Benchmark — plan"
    )

    print(
        f"tasks={len(tasks)}"
    )

    print(
        f"repeat={repeat}"
    )

    print(
        f"seed={seed}"
    )

    print(
        "runners="
        + ",".join(runners)
    )

    print()

    for repetition in range(
        repeat
    ):
        order = balanced_runner_order(
            runners,
            repetition,
            seed,
        )

        print(
            f"repeat {repetition}: "
            + " -> ".join(order)
        )


def main(
    argv: list[str] | None = None,
) -> int:
    parser = build_parser()

    args = parser.parse_args(
        argv
    )

    if args.repeat < 1:
        parser.error(
            "--repeat must be >= 1"
        )

    try:
        runner_names = resolve_runner_names(
            requested=args.runner,
            all_runners=args.all,
        )
    except ValueError as error:
        parser.error(
            str(error)
        )

    tasks = load_tasks(
        args.tasks
    )

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
        parser.error(
            str(error)
        )

    runners = build_runners(
        runner_names,
        codeintel_binary=(
            args.codeintel_binary
        ),
        rg_binary=(
            args.rg_binary
        ),
        codeintel_mode=(
            args.codeintel_mode
        ),
        deterministic_timeout=(
            args.deterministic_timeout
        ),
        agent_timeout=(
            args.agent_timeout
        ),
        claude_model=(
            args.claude_model
        ),
        codex_model=(
            args.codex_model
        ),
    )

    source_resolver = lambda task: _task_source(
        task,
        synthetic=(
            args.corpus
            == "synthetic"
        ),
        repo=args.repo,
    )

    results = execute_matrix(
        tasks=tasks,
        runner_names=runner_names,
        runners=runners,
        repeat=args.repeat,
        seed=args.seed,
        source_resolver=(
            source_resolver
        ),
    )

    metadata = _make_run_metadata(
        seed=args.seed,
        runners=runner_names,
        codeintel_binary=(
            args.codeintel_binary
        ),
    )

    _write_reports(
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
    print(
        f"results={len(results)}"
    )

    print(
        f"comparisons="
        f"{len(comparisons)}"
    )

    print(
        f"output="
        f"{args.output.resolve()}"
    )

    return (
        0
        if all(
            result.success
            for result in results
        )
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
