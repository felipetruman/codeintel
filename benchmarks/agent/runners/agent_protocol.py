from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from benchmarks.agent.manifests import BenchmarkTask

BENCHMARK_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "files": {"type": "array", "items": {"type": "string"}},
        "symbols": {"type": "array", "items": {"type": "string"}},
        "answer": {"type": "string"},
    },
    "required": ["files", "symbols", "answer"],
    "additionalProperties": False,
}


def benchmark_prompt(task: BenchmarkTask) -> str:
    return (
        f"{task.prompt}\n\nThis is a read-only benchmark. "
        "Do not modify repository files. Investigate the repository and return "
        "the requested structured result. Use repository-relative paths in `files`. "
        "`files` must contain files relevant to the answer. "
        "`symbols` must contain relevant code symbols."
    )


def nonnegative_int(value: Any) -> int | None:
    if type(value) is not int:
        return None
    return value if value >= 0 else None


def sanitized_usage(value: Any) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    keys = (
        "input_tokens",
        "output_tokens",
        "cached_input_tokens",
        "cache_read_input_tokens",
        "cache_creation_input_tokens",
    )
    return {
        key: number
        for key in keys
        if (number := nonnegative_int(value.get(key))) is not None
    }


def json_lines(stdout: str) -> list[dict[str, Any]]:
    events = [json.loads(line) for line in stdout.splitlines() if line.strip()]
    if not all(isinstance(event, dict) for event in events):
        raise ValueError("stream events must be objects")
    return events


def relative_path(value: str, repo: Path) -> str:
    path = Path(value)
    if not path.is_absolute():
        path = repo / path
    return path.resolve().relative_to(repo.resolve()).as_posix()


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("expected string array")
    if not all(isinstance(item, str) for item in value):
        raise ValueError("expected string array entries")
    return list(dict.fromkeys(value))


def structured_payload(value: Any, repo: Path) -> tuple[list[str], list[str]]:
    if not isinstance(value, dict):
        raise ValueError("structured output must be an object")
    if set(value) != {"files", "symbols", "answer"}:
        raise ValueError("structured output fields do not match schema")
    if not isinstance(value["answer"], str):
        raise ValueError("answer must be a string")
    files = [relative_path(item, repo) for item in string_list(value["files"])]
    return list(dict.fromkeys(files)), string_list(value["symbols"])


def mcp_executable(value: str) -> str:
    resolved = shutil.which(value)
    return str(Path(resolved).resolve()) if resolved else value
