from __future__ import annotations

from dataclasses import dataclass, replace
import json
from pathlib import Path
from typing import Any

from benchmarks.agent.manifests import BenchmarkTask
from benchmarks.agent.models import (
    BenchmarkResult,
    TokenUsage,
)
from benchmarks.agent.runners.agent_sandbox import run_agent_process as run_process
from benchmarks.agent.runners.agent_protocol import (
    BENCHMARK_OUTPUT_SCHEMA,
    mcp_executable,
    benchmark_prompt,
    sanitized_usage,
    json_lines,
    relative_path,
    structured_payload,
)


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
    files_read: list[str] | None
    tool_calls: list[dict[str, Any]]
    tokens: TokenUsage
    is_error: bool
    structured_output: bool
    raw_usage: dict[str, Any] | None


def _mcp_config(
    config: ClaudeConfig,
    repo: Path,
    codeintel_enabled: bool,
) -> dict[str, Any]:
    servers: dict[str, Any] = {}

    if codeintel_enabled:
        servers["codeintel"] = {
            "type": "stdio",
            "command": mcp_executable(config.codeintel_binary),
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

    argv.extend(["--", prompt])

    return argv


def _usage(value: Any) -> TokenUsage:
    usage = sanitized_usage(value)
    if usage is None:
        return TokenUsage()
    inputs = [
        usage[key]
        for key in (
            "input_tokens",
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
        )
        if key in usage
    ]
    return TokenUsage(
        input=sum(inputs) if inputs else None, output=usage.get("output_tokens")
    )


def _content(event: dict) -> list[dict]:
    message = event.get("message", {})
    if not isinstance(message, dict):
        raise ValueError("message must be an object")
    content = message.get("content", [])
    if not isinstance(content, list):
        raise ValueError("message content must be an array")
    return [block for block in content if isinstance(block, dict)]


def _record_tool(
    block: dict, telemetry: ClaudeTelemetry, pending: dict, repo: Path
) -> None:
    name = block.get("name")
    if not isinstance(name, str):
        raise ValueError("tool name must be a string")
    telemetry.tool_calls.append({"name": name})
    if name not in {"Read", "NotebookRead"}:
        return
    tool_input = block.get("input", {})
    if not isinstance(tool_input, dict):
        raise ValueError("tool input must be an object")
    path = tool_input.get("file_path", tool_input.get("notebook_path"))
    if isinstance(path, str):
        pending[block.get("id")] = relative_path(path, repo)


def _completed_read(block: dict, pending: dict) -> str | None:
    if block.get("type") != "tool_result":
        return None
    if block.get("is_error", False) is not False:
        return None
    return pending.pop(block.get("tool_use_id"), None)


def _claude_result(
    event: dict, telemetry: ClaudeTelemetry, repo: Path
) -> ClaudeTelemetry:
    payload = event.get("structured_output")
    if payload is None:
        payload = json.loads(event.get("result", ""))
    files, symbols = structured_payload(payload, repo)
    return replace(
        telemetry,
        files=files,
        symbols=symbols,
        structured_output=True,
        is_error=event.get("is_error", False) is not False,
        raw_usage=sanitized_usage(event.get("usage")),
        tokens=_usage(event.get("usage")),
    )


def _read_events(
    events: list[dict], telemetry: ClaudeTelemetry, pending: dict, repo: Path
) -> list[str]:
    reads = []
    for event in events:
        kind = event.get("type")
        if kind == "assistant":
            _assistant_events(event, telemetry, pending, repo)
        if kind == "user":
            reads.extend(
                path
                for block in _content(event)
                if (path := _completed_read(block, pending)) is not None
            )
    return reads


def _assistant_events(
    event: dict, telemetry: ClaudeTelemetry, pending: dict, repo: Path
) -> None:
    for block in _content(event):
        if block.get("type") == "tool_use":
            _record_tool(block, telemetry, pending, repo)


def parse_claude_stream(stdout: str, repo: Path) -> ClaudeTelemetry:
    telemetry = ClaudeTelemetry([], [], None, [], TokenUsage(), True, False, None)
    pending: dict[str, str] = {}
    reads: list[str] = []
    try:
        events = json_lines(stdout)
        results = [event for event in events if event.get("type") == "result"]
        if len(results) != 1:
            return telemetry
        reads = _read_events(events, telemetry, pending, repo)
        telemetry = _claude_result(results[0], telemetry, repo)
    except (ValueError, TypeError):
        return replace(telemetry, is_error=True, structured_output=False)
    # Read events are a lower bound; without successful results telemetry is unknown.
    return replace(telemetry, files_read=list(dict.fromkeys(reads)) if reads else None)


class ClaudeRunner:
    def __init__(
        self,
        codeintel_enabled: bool,
        config: ClaudeConfig | None = None,
    ) -> None:
        self.codeintel_enabled = codeintel_enabled

        self.config = config if config is not None else ClaudeConfig()

        self.name = "claude-codeintel" if codeintel_enabled else "claude"

    def run(
        self,
        task: BenchmarkTask,
        repo: Path,
    ) -> BenchmarkResult:
        prompt = benchmark_prompt(task)

        argv = build_claude_command(
            self.config,
            repo,
            prompt,
            self.codeintel_enabled,
        )

        process = run_process(
            argv,
            cwd=repo,
            agent="claude",
            timeout_seconds=(self.config.timeout_seconds),
            codeintel_binary=(
                self.config.codeintel_binary if self.codeintel_enabled else None
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
            and telemetry.structured_output
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
                "codeintel_enabled": (self.codeintel_enabled),
                "telemetry_format": ("claude-stream-json"),
                "structured_output": (telemetry.structured_output),
                "files_read": (telemetry.files_read),
                "usage": (telemetry.raw_usage),
                "timed_out": (process.timed_out),
                "stderr_present": bool(process.stderr),
            },
        )
