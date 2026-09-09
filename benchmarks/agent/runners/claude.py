from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from benchmarks.agent.manifests import BenchmarkTask
from benchmarks.agent.models import (
    BenchmarkResult,
    TokenUsage,
)
from benchmarks.agent.process import run_process


BENCHMARK_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "files": {
            "type": "array",
            "items": {
                "type": "string",
            },
        },
        "symbols": {
            "type": "array",
            "items": {
                "type": "string",
            },
        },
        "answer": {
            "type": "string",
        },
    },
    "required": [
        "files",
        "symbols",
        "answer",
    ],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class ClaudeConfig:
    executable: str = "claude"
    model: str | None = None
    timeout_seconds: float = 300.0
    codeintel_binary: str = "codeintel"


@dataclass(frozen=True)
class ClaudeTelemetry:
    files: list[str]
    symbols: list[str]
    files_read: list[str]
    tool_calls: list[dict[str, Any]]
    tokens: TokenUsage
    is_error: bool
    structured_output: bool
    raw_usage: dict[str, Any] | None


def benchmark_prompt(
    task: BenchmarkTask,
) -> str:
    return (
        f"{task.prompt}\n\n"
        "This is a read-only benchmark. "
        "Do not modify repository files. "
        "Investigate the repository and return "
        "the requested structured result. "
        "Use repository-relative paths in `files`. "
        "`files` must contain files relevant to the answer. "
        "`symbols` must contain relevant code symbols."
    )


def _mcp_config(
    config: ClaudeConfig,
    repo: Path,
    codeintel_enabled: bool,
) -> dict[str, Any]:
    servers: dict[str, Any] = {}

    if codeintel_enabled:
        servers["codeintel"] = {
            "type": "stdio",
            "command": config.codeintel_binary,
            "args": [
                "mcp",
                str(repo.resolve()),
            ],
        }

    return {
        "mcpServers": servers,
    }


def build_claude_command(
    config: ClaudeConfig,
    repo: Path,
    prompt: str,
    codeintel_enabled: bool,
) -> list[str]:
    mcp_json = json.dumps(
        _mcp_config(
            config,
            repo,
            codeintel_enabled,
        ),
        separators=(",", ":"),
    )

    schema_json = json.dumps(
        BENCHMARK_OUTPUT_SCHEMA,
        separators=(",", ":"),
    )

    argv = [
        config.executable,
        "-p",
        "--restricted",
        "--permission-mode",
        "plan",
        "--permission-prompts",
        "none",
        "--no-session-persistence",
        "--no-chrome",
        "--strict-mcp-config",
        "--mcp-config",
        mcp_json,
        "--output-format",
        "stream-json",
        "--verbose",
        "--json-schema",
        schema_json,
    ]

    if config.model:
        argv.extend(
            [
                "--model",
                config.model,
            ]
        )

    argv.append(prompt)

    return argv


def _json_lines(
    stdout: str,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []

    for line in stdout.splitlines():
        line = line.strip()

        if not line:
            continue

        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue

        if isinstance(value, dict):
            result.append(value)

    return result


def _unique_strings(
    value: Any,
) -> list[str]:
    if not isinstance(value, list):
        return []

    result: list[str] = []

    for item in value:
        if (
            isinstance(item, str)
            and item not in result
        ):
            result.append(item)

    return result


def _relative_path(
    value: str,
    repo: Path,
) -> str:
    path = Path(value)

    if path.is_absolute():
        try:
            path = path.resolve().relative_to(
                repo.resolve()
            )
        except ValueError:
            return value

    normalized = path.as_posix()

    if normalized.startswith("./"):
        normalized = normalized[2:]

    return normalized


def _normalize_files(
    value: Any,
    repo: Path,
) -> list[str]:
    result: list[str] = []

    for item in _unique_strings(value):
        normalized = _relative_path(
            item,
            repo,
        )

        if normalized not in result:
            result.append(normalized)

    return result


def _usage(
    value: Any,
) -> TokenUsage:
    if not isinstance(value, dict):
        return TokenUsage()

    input_total = 0
    input_seen = False

    for key in (
        "input_tokens",
        "cache_read_input_tokens",
        "cache_creation_input_tokens",
    ):
        raw = value.get(key)

        if (
            isinstance(raw, int)
            and not isinstance(raw, bool)
        ):
            input_total += raw
            input_seen = True

    raw_output = value.get(
        "output_tokens"
    )

    output_tokens = (
        raw_output
        if isinstance(raw_output, int)
        and not isinstance(raw_output, bool)
        else None
    )

    return TokenUsage(
        input=(
            input_total
            if input_seen
            else None
        ),
        output=output_tokens,
    )


def _structured_payload(
    event: dict[str, Any],
) -> dict[str, Any] | None:
    value = event.get(
        "structured_output"
    )

    if isinstance(value, dict):
        return value

    raw_result = event.get(
        "result"
    )

    if not isinstance(
        raw_result,
        str,
    ):
        return None

    try:
        parsed = json.loads(
            raw_result
        )
    except json.JSONDecodeError:
        return None

    return (
        parsed
        if isinstance(parsed, dict)
        else None
    )


def parse_claude_stream(
    stdout: str,
    repo: Path,
) -> ClaudeTelemetry:
    files: list[str] = []
    symbols: list[str] = []
    files_read: list[str] = []
    tool_calls: list[
        dict[str, Any]
    ] = []

    tokens = TokenUsage()
    raw_usage = None
    is_error = False
    structured_seen = False

    for event in _json_lines(stdout):
        if event.get("type") == "assistant":
            message = event.get(
                "message"
            )

            if isinstance(
                message,
                dict,
            ):
                content = message.get(
                    "content"
                )

                if isinstance(
                    content,
                    list,
                ):
                    for block in content:
                        if not isinstance(
                            block,
                            dict,
                        ):
                            continue

                        if (
                            block.get("type")
                            != "tool_use"
                        ):
                            continue

                        name = block.get(
                            "name"
                        )

                        if not isinstance(
                            name,
                            str,
                        ):
                            name = "unknown"

                        tool_calls.append(
                            {
                                "name": name,
                            }
                        )

                        tool_input = block.get(
                            "input"
                        )

                        if (
                            name
                            in {
                                "Read",
                                "NotebookRead",
                            }
                            and isinstance(
                                tool_input,
                                dict,
                            )
                        ):
                            file_path = (
                                tool_input.get(
                                    "file_path"
                                )
                            )

                            if isinstance(
                                file_path,
                                str,
                            ):
                                normalized = (
                                    _relative_path(
                                        file_path,
                                        repo,
                                    )
                                )

                                if (
                                    normalized
                                    not in files_read
                                ):
                                    files_read.append(
                                        normalized
                                    )

        if event.get("type") == "result":
            is_error = bool(
                event.get(
                    "is_error",
                    False,
                )
            )

            usage_value = event.get(
                "usage"
            )

            if isinstance(
                usage_value,
                dict,
            ):
                raw_usage = usage_value
                tokens = _usage(
                    usage_value
                )

            structured = (
                _structured_payload(
                    event
                )
            )

            if structured is not None:
                structured_seen = True

                files = _normalize_files(
                    structured.get(
                        "files"
                    ),
                    repo,
                )

                symbols = _unique_strings(
                    structured.get(
                        "symbols"
                    )
                )

    return ClaudeTelemetry(
        files=files,
        symbols=symbols,
        files_read=files_read,
        tool_calls=tool_calls,
        tokens=tokens,
        is_error=is_error,
        structured_output=structured_seen,
        raw_usage=raw_usage,
    )


class ClaudeRunner:
    def __init__(
        self,
        codeintel_enabled: bool,
        config: ClaudeConfig | None = None,
    ) -> None:
        self.codeintel_enabled = (
            codeintel_enabled
        )

        self.config = (
            config
            if config is not None
            else ClaudeConfig()
        )

        self.name = (
            "claude-codeintel"
            if codeintel_enabled
            else "claude"
        )

    def run(
        self,
        task: BenchmarkTask,
        repo: Path,
    ) -> BenchmarkResult:
        prompt = benchmark_prompt(
            task
        )

        argv = build_claude_command(
            self.config,
            repo,
            prompt,
            self.codeintel_enabled,
        )

        process = run_process(
            argv,
            cwd=repo,
            timeout_seconds=(
                self.config.timeout_seconds
            ),
        )

        telemetry = parse_claude_stream(
            process.stdout,
            repo,
        )

        success = (
            not process.timed_out
            and process.exit_code == 0
            and not telemetry.is_error
        )

        return BenchmarkResult(
            runner=self.name,
            task_id=task.id,
            success=success,
            duration_ms=process.duration_ms,
            files=telemetry.files,
            symbols=telemetry.symbols,
            tool_calls=telemetry.tool_calls,
            tokens=telemetry.tokens,
            stdout="",
            stderr="",
            exit_code=process.exit_code,
            metadata={
                "agent": "claude",
                "model": self.config.model,
                "codeintel_enabled": (
                    self.codeintel_enabled
                ),
                "telemetry_format": (
                    "claude-stream-json"
                ),
                "structured_output": (
                    telemetry.structured_output
                ),
                "files_read": (
                    telemetry.files_read
                ),
                "usage": (
                    telemetry.raw_usage
                ),
                "timed_out": (
                    process.timed_out
                ),
                "stderr_present": bool(
                    process.stderr
                ),
            },
        )
