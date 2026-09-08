from __future__ import annotations

from pathlib import Path
from typing import Protocol

from benchmarks.agent.manifests import (
    BenchmarkTask,
)
from benchmarks.agent.models import (
    BenchmarkResult,
)


class Runner(Protocol):
    name: str

    def run(
        self,
        task: BenchmarkTask,
        repo: Path,
    ) -> BenchmarkResult:
        ...
