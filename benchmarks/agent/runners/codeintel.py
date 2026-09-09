from __future__ import annotations

import json
from pathlib import Path
import shutil
from typing import Literal

from benchmarks.agent.manifests import BenchmarkTask
from benchmarks.agent.models import BenchmarkResult
from benchmarks.agent.process import run_process
from benchmarks.agent.runners.codeintel_output import parse_output

Operation = Literal["search", "context", "symbol", "impact"]


class CodeIntelRunner:
    name = "codeintel"

    def __init__(
        self,
        binary: str = "codeintel",
        mode: Literal["cold", "warm"] = "warm",
        timeout_seconds: float = 30,
    ) -> None:
        if mode not in {"cold", "warm"}:
            raise ValueError(f"unsupported CodeIntel mode: {mode}")
        self.binary = binary
        self.mode = mode
        self.timeout_seconds = timeout_seconds

    def _prepare(self, repo: Path):
        state = repo / ".codeintel"
        if self.mode == "cold":
            if state.exists():
                shutil.rmtree(state)
            return None
        return run_process(
            [self.binary, "index", str(repo)], repo, self.timeout_seconds
        )

    def _argv(self, operation: Operation, text: str, repo: Path) -> list[str]:
        options = {
            "search": ["--limit", "50"],
            "context": ["--limit", "20"],
            "symbol": [],
            "impact": ["--depth", "8"],
        }
        if operation not in options:
            raise ValueError(f"unsupported operation: {operation}")
        return [self.binary, operation, *options[operation], "--", text, str(repo)]

    def _result(self, task_id, operation, process) -> BenchmarkResult:
        return BenchmarkResult(
            self.name,
            task_id,
            False,
            process.duration_ms,
            exit_code=process.exit_code,
            metadata={
                "operation": operation,
                "mode": self.mode,
                "timed_out": process.timed_out,
            },
        )

    def run_operation(
        self, operation: Operation, text: str, repo: Path, task_id: str
    ) -> BenchmarkResult:
        repo = Path(repo).resolve()
        argv = self._argv(operation, text, repo)
        preparation = self._prepare(repo)
        if preparation is not None and preparation.exit_code != 0:
            result = self._result(task_id, operation, preparation)
            result.metadata["stage"] = "index"
            return result
        process = run_process(argv, repo, self.timeout_seconds)
        result = self._result(task_id, operation, process)
        if preparation is not None:
            result.metadata["index_duration_ms"] = preparation.duration_ms
        if process.exit_code != 0:
            return result
        try:
            files, symbols, metadata = parse_output(
                operation, json.loads(process.stdout), repo
            )
        except (ValueError, TypeError, KeyError):
            result.metadata["parse_error"] = "invalid CodeIntel output"
            return result
        result.files, result.symbols = files, symbols
        result.metadata.update(metadata)
        result.success = True
        return result

    def run(self, task: BenchmarkTask, repo: Path) -> BenchmarkResult:
        operations = {
            "locate-symbol": ("search", task.query),
            "relevant-files": ("context", task.prompt),
            "change-planning": ("context", task.prompt),
            "impact-analysis": ("impact", task.query),
        }
        if task.type not in operations:
            raise ValueError(f"unsupported task type: {task.type}")
        operation, text = operations[task.type]
        return self.run_operation(operation, text, repo, task.id)
