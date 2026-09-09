from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
from typing import Any

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
from benchmarks.agent.runners.claude import (
    BENCHMARK_OUTPUT_SCHEMA,
    benchmark_prompt,
)


@dataclass(frozen=True)
class CodexConfig:
    executable: str = "codex"
    model: str | None = None
    timeout_seconds: float = 300.0
    codeintel_binary: str = "codeintel"


@dataclass(frozen=True)
class CodexTelemetry:
    files: list[str]
    symbols: list[str]
    tool_calls: list[dict[str, Any]]
    tokens: TokenUsage
    failed: bool
    structured_output: bool
    raw_usage: dict[str, Any] | None


def _toml_string(
    value: str,
) -> str:
    return json.dumps(value)


def _codeintel_overrides(
    config: CodexConfig,
    repo: Path,
) -> list[str]:
    return [
        "-c",
        (
            "mcp_servers.codeintel.command="
            + _toml_string(
                config.codeintel_binary
            )
        ),
        "-c",
        (
            "mcp_servers.codeintel.args="
            + json.dumps(
                [
                    "mcp",
                    str(repo.resolve()),
                ],
                separators=(",", ":"),
            )
        ),
    ]


def build_codex_command(
    config: CodexConfig,
    repo: Path,
    prompt: str,
    codeintel_enabled: bool,
    schema_path: Path,
) -> list[str]:
    argv = [
        config.executable,
        "exec",
        "--json",
        "--color",
        "never",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "-C",
        str(repo.resolve()),
        "--output-schema",
        str(schema_path),
    ]

    if config.model:
        argv.extend(
            [
                "--model",
                config.model,
            ]
        )

    if codeintel_enabled:
        argv.extend(
            _codeintel_overrides(
                config,
                repo,
            )
        )

    argv.append(prompt)

    return argv


def _json_lines(
    stdout: str,
) -> list[dict[str, Any]]:
    result: list[
        dict[str, Any]
    ] = []

    for line in stdout.splitlines():
        value = line.strip()

        if not value:
            continue

        try:
            payload = json.loads(
                value
            )
        except json.JSONDecodeError:
            continue

        if isinstance(
            payload,
            dict,
        ):
            result.append(
                payload
            )

    return result


def _unique_strings(
    value: Any,
) -> list[str]:
    if not isinstance(
        value,
        list,
    ):
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
            path = (
                path.resolve()
                .relative_to(
                    repo.resolve()
                )
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

    for item in _unique_strings(
        value
    ):
        normalized = _relative_path(
            item,
            repo,
        )

        if normalized not in result:
            result.append(
                normalized
            )

    return result


def _parse_final_json(
    value: Any,
) -> dict[str, Any] | None:
    if not isinstance(
        value,
        str,
    ):
        return None

    text = value.strip()

    if (
        text.startswith("```")
        and text.endswith("```")
    ):
        lines = text.splitlines()

        if len(lines) >= 3:
            text = "\n".join(
                lines[1:-1]
            ).strip()

    try:
        payload = json.loads(
            text
        )
    except json.JSONDecodeError:
        return None

    return (
        payload
        if isinstance(
            payload,
            dict,
        )
        else None
    )


def _usage(
    value: Any,
) -> TokenUsage:
    if not isinstance(
        value,
        dict,
    ):
        return TokenUsage()

    raw_input = value.get(
        "input_tokens"
    )

    raw_output = value.get(
        "output_tokens"
    )

    input_tokens = (
        raw_input
        if isinstance(
            raw_input,
            int,
        )
        and not isinstance(
            raw_input,
            bool,
        )
        else None
    )

    output_tokens = (
        raw_output
        if isinstance(
            raw_output,
            int,
        )
        and not isinstance(
            raw_output,
            bool,
        )
        else None
    )

    return TokenUsage(
        input=input_tokens,
        output=output_tokens,
    )


def parse_codex_stream(
    stdout: str,
    repo: Path,
) -> CodexTelemetry:
    files: list[str] = []
    symbols: list[str] = []

    tool_calls: list[
        dict[str, Any]
    ] = []

    tokens = TokenUsage()
    raw_usage = None
    failed = False
    structured_seen = False

    tool_types = {
        "command_execution",
        "mcp_tool_call",
        "web_search",
        "file_change",
    }

    for event in _json_lines(
        stdout
    ):
        event_type = event.get(
            "type"
        )

        if event_type in {
            "turn.failed",
            "error",
        }:
            failed = True

        if event_type == "item.completed":
            item = event.get(
                "item"
            )

            if not isinstance(
                item,
                dict,
            ):
                continue

            item_type = item.get(
                "type"
            )

            if item_type in tool_types:
                call: dict[
                    str,
                    Any,
                ] = {
                    "type": item_type,
                }

                for key in (
                    "server",
                    "tool",
                    "name",
                ):
                    raw = item.get(
                        key
                    )

                    if isinstance(
                        raw,
                        str,
                    ):
                        call[key] = raw

                tool_calls.append(
                    call
                )

            if item_type == "agent_message":
                structured = (
                    _parse_final_json(
                        item.get(
                            "text"
                        )
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

                    symbols = (
                        _unique_strings(
                            structured.get(
                                "symbols"
                            )
                        )
                    )

        if event_type == "turn.completed":
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

    return CodexTelemetry(
        files=files,
        symbols=symbols,
        tool_calls=tool_calls,
        tokens=tokens,
        failed=failed,
        structured_output=(
            structured_seen
        ),
        raw_usage=raw_usage,
    )


class CodexRunner:
    def __init__(
        self,
        codeintel_enabled: bool,
        config: CodexConfig | None = None,
    ) -> None:
        self.codeintel_enabled = (
            codeintel_enabled
        )

        self.config = (
            config
            if config is not None
            else CodexConfig()
        )

        self.name = (
            "codex-codeintel"
            if codeintel_enabled
            else "codex"
        )

    def run(
        self,
        task: BenchmarkTask,
        repo: Path,
    ) -> BenchmarkResult:
        prompt = benchmark_prompt(
            task
        )

        fd, raw_schema = (
            tempfile.mkstemp(
                prefix=(
                    "codeintel-agent-schema-"
                ),
                suffix=".json",
            )
        )

        schema_path = Path(
            raw_schema
        )

        try:
            with os.fdopen(
                fd,
                "w",
                encoding="utf-8",
            ) as handle:
                json.dump(
                    BENCHMARK_OUTPUT_SCHEMA,
                    handle,
                    separators=(",", ":"),
                )

            argv = build_codex_command(
                self.config,
                repo,
                prompt,
                self.codeintel_enabled,
                schema_path,
            )

            process = run_process(
                argv,
                cwd=repo,
                timeout_seconds=(
                    self.config.timeout_seconds
                ),
            )

        finally:
            schema_path.unlink(
                missing_ok=True
            )

        telemetry = (
            parse_codex_stream(
                process.stdout,
                repo,
            )
        )

        success = (
            not process.timed_out
            and process.exit_code == 0
            and not telemetry.failed
        )

        return BenchmarkResult(
            runner=self.name,
            task_id=task.id,
            success=success,
            duration_ms=(
                process.duration_ms
            ),
            files=telemetry.files,
            symbols=telemetry.symbols,
            tool_calls=(
                telemetry.tool_calls
            ),
            tokens=telemetry.tokens,
            stdout="",
            stderr="",
            exit_code=(
                process.exit_code
            ),
            metadata={
                "agent": "codex",
                "model": (
                    self.config.model
                ),
                "codeintel_enabled": (
                    self.codeintel_enabled
                ),
                "telemetry_format": (
                    "codex-jsonl"
                ),
                "structured_output": (
                    telemetry.structured_output
                ),
                # JSONL does not expose a
                # trustworthy canonical list
                # of every file read.
                "files_read": None,
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
