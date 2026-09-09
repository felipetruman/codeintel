from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import platform as platform_module
import sys

from benchmarks.agent.manifests import (
    BenchmarkTask,
    load_tasks,
)
from benchmarks.agent.process import (
    run_process,
)
from benchmarks.agent.reporting import (
    RunMetadata,
    write_run,
)
from benchmarks.agent.runners.codeintel import (
    CodeIntelRunner,
)
from benchmarks.agent.runners.rg import (
    RgRunner,
)
from benchmarks.agent.scheduler import (
    run_matrix,
)

AGENT_ROOT = Path(__file__).resolve().parent

REPOSITORY_ROOT = AGENT_ROOT.parents[1]

DETERMINISTIC_RUNNERS = (
    "rg",
    "codeintel",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codeintel-agent-benchmark",
        description="Deterministic and agentic benchmark harness for CodeIntel.",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--corpus", choices=["synthetic"], help="Use built-in synthetic corpora."
    )
    source.add_argument("--repo", type=Path, help="Benchmark an arbitrary repository.")
    parser.add_argument(
        "--tasks",
        type=Path,
        default=AGENT_ROOT / "tasks",
        help="Task manifest file or directory.",
    )
    parser.add_argument(
        "--runner",
        action="append",
        choices=DETERMINISTIC_RUNNERS,
        default=[],
        help="Runner to execute. Repeatable.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="all_runners",
        help="Run all currently available runners.",
    )
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--codeintel-mode", choices=["cold", "warm"], default="warm")
    parser.add_argument("--codeintel-binary", default="codeintel")
    parser.add_argument("--timeout", type=float, default=30.0)
    return parser


def resolve_runners(
    explicit: list[str],
    all_runners: bool,
) -> list[str]:
    if all_runners:
        return list(DETERMINISTIC_RUNNERS)

    selected = explicit if explicit else list(DETERMINISTIC_RUNNERS)

    return list(dict.fromkeys(selected))


def _safe_version(
    argv: list[str],
) -> str | None:
    try:
        result = run_process(
            argv,
            cwd=REPOSITORY_ROOT,
            timeout_seconds=5,
        )
    except (
        FileNotFoundError,
        OSError,
        ValueError,
    ):
        return None

    if result.timed_out or result.exit_code != 0:
        return None

    value = result.stdout.strip()

    return value or None


def _git_sha() -> str | None:
    return _safe_version(
        [
            "git",
            "rev-parse",
            "HEAD",
        ]
    )


def _make_run_id(
    seed: int,
) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    return f"{stamp}-seed{seed}"


def _metadata(
    run_id: str,
    seed: int,
    runner_names: list[str],
    codeintel_binary: str,
) -> RunMetadata:
    return RunMetadata(
        run_id=run_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        codeintel_version=_safe_version(
            [
                codeintel_binary,
                "--version",
            ]
        ),
        git_sha=_git_sha(),
        python_version=platform_module.python_version(),
        platform=platform_module.system(),
        architecture=platform_module.machine(),
        claude_version=None,
        codex_version=None,
        seed=seed,
        runners=tuple(runner_names),
    )


def _source_resolver(
    corpus: str | None,
    repo: Path | None,
):
    if corpus == "synthetic":

        def resolve(
            task: BenchmarkTask,
        ) -> Path:
            source = AGENT_ROOT / "corpus" / task.corpus

            if not source.is_dir():
                raise ValueError("synthetic corpus does not exist: " f"{source}")

            return source

        return resolve

    if repo is None:
        raise ValueError("repository path is required")

    repository = repo.resolve()

    if not repository.is_dir():
        raise ValueError(f"repository does not exist: {repository}")

    def resolve_real(
        _task: BenchmarkTask,
    ) -> Path:
        return repository

    return resolve_real


def _runner_instances(
    names: list[str],
    codeintel_binary: str,
    codeintel_mode: str,
    timeout: float,
):
    runners = {}

    for name in names:
        if name == "rg":
            runners[name] = RgRunner(
                timeout_seconds=timeout,
            )

        elif name == "codeintel":
            runners[name] = CodeIntelRunner(
                binary=codeintel_binary,
                mode=codeintel_mode,
                timeout_seconds=timeout,
            )

        else:
            raise ValueError(f"unsupported runner: {name}")

    return runners


def main(
    argv: list[str] | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.repeat <= 0:
        parser.error("--repeat must be greater than zero")

    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")

    runner_names = resolve_runners(
        explicit=args.runner,
        all_runners=args.all_runners,
    )

    tasks = load_tasks(args.tasks)

    if not tasks:
        parser.error("no benchmark tasks found")

    return _execute(args, runner_names, tasks)


def _execute(args, runner_names, tasks) -> int:
    run_id = _make_run_id(args.seed)

    output = (
        args.output if args.output is not None else (AGENT_ROOT / "results" / run_id)
    )

    runners = _runner_instances(
        names=runner_names,
        codeintel_binary=args.codeintel_binary,
        codeintel_mode=args.codeintel_mode,
        timeout=args.timeout,
    )

    resolver = _source_resolver(
        corpus=args.corpus,
        repo=args.repo,
    )

    results = run_matrix(
        tasks=tasks,
        runners=runners,
        source_resolver=resolver,
        repeat=args.repeat,
    )

    metadata = _metadata(
        run_id=run_id,
        seed=args.seed,
        runner_names=runner_names,
        codeintel_binary=args.codeintel_binary,
    )

    paths = write_run(
        output,
        metadata,
        results,
    )

    summary = paths["summary"]

    print(f"run_id: {run_id}")

    print(f"results: {paths['results']}")

    print(f"summary: {summary}")

    successful = sum(result.success for result in results)

    print("success: " f"{successful}/{len(results)}")

    return 0 if successful == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
