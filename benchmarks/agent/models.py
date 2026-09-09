from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TokenUsage:
    input: int | None = None
    output: int | None = None

    @property
    def total(self) -> int | None:
        if self.input is None or self.output is None:
            return None

        return self.input + self.output

    def to_dict(self) -> dict[str, int | None]:
        return {
            "input": self.input,
            "output": self.output,
            "total": self.total,
        }


@dataclass
class BenchmarkResult:
    runner: str
    task_id: str
    success: bool
    duration_ms: float
    files: list[str] = field(default_factory=list)
    symbols: list[str] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tokens: TokenUsage = field(default_factory=TokenUsage)
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "runner": self.runner,
            "task_id": self.task_id,
            "success": self.success,
            "duration_ms": self.duration_ms,
            "files": list(self.files),
            "symbols": list(self.symbols),
            "tool_calls": list(self.tool_calls),
            "tokens": self.tokens.to_dict(),
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "metadata": dict(self.metadata),
        }
