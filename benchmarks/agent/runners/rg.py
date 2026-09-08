from __future__ import annotations

import json
from pathlib import Path

from benchmarks.agent.manifests import (
    BenchmarkTask,
)
from benchmarks.agent.models import (
    BenchmarkResult,
    TokenUsage,
)
from benchmarks.agent.process import (
    run_process,
)


def _normalize_path(path: str) -> str:
    while path.startswith("./"):
        path = path[2:]

    return path


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


class RgRunner:
    name = "rg"

    def __init__(
        self,
        binary: str = "rg",
        timeout_seconds: float = 30,
    ) -> None:
        self.binary = binary
        self.timeout_seconds = (
            timeout_seconds
        )

    def run(
        self,
        task: BenchmarkTask,
        repo: Path,
    ) -> BenchmarkResult:
        result = run_process(
            [
                self.binary,
                "--json",
                "--line-number",
                "--column",
                task.query,
                ".",
            ],
            cwd=repo,
            timeout_seconds=self.timeout_seconds,
        )

        files: list[str] = []
        matches = 0
        parse_errors = 0

        for line in result.stdout.splitlines():
            if not line.strip():
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                parse_errors += 1
                continue

            if event.get("type") != "match":
                continue

            data = event.get("data", {})
            path_data = data.get(
                "path",
                {},
            )

            path = path_data.get("text")

            if isinstance(path, str):
                files.append(
                    _normalize_path(path)
                )

            matches += 1

        # rg exit 1 means a valid search with zero matches.
        valid_exit = result.exit_code in {
            0,
            1,
        }

        return BenchmarkResult(
            runner=self.name,
            task_id=task.id,
            success=(
                not result.timed_out
                and valid_exit
                and parse_errors == 0
            ),
            duration_ms=result.duration_ms,
            files=_dedupe(files),
            symbols=[],
            tool_calls=[],
            tokens=TokenUsage(),
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.exit_code,
            metadata={
                "operation": "search",
                "candidate_count": matches,
                "parse_errors": parse_errors,
                "query": task.query,
            },
        )
