from __future__ import annotations

from benchmarks.agent.runners.agent_sandbox import AgentProcessOptions

from dataclasses import dataclass, replace
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
from benchmarks.agent.runners.agent_sandbox import run_agent_process as run_process
from benchmarks.agent.runners.agent_protocol import (
    sanitized_usage,
    json_lines,
    structured_payload,
    BENCHMARK_OUTPUT_SCHEMA,
    mcp_executable,
    benchmark_prompt,
)


@dataclass(frozen=True)
class CodexInvocation:
    repo: Path
    prompt: str
    codeintel_enabled: bool
    schema_path: Path


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
            + _toml_string(mcp_executable(config.codeintel_binary))
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


def build_codex_command(config: CodexConfig, invocation: CodexInvocation) -> list[str]:
    repo, prompt = invocation.repo, invocation.prompt
    codeintel_enabled, schema_path = (
        invocation.codeintel_enabled,
        invocation.schema_path,
    )
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

    argv.extend(["--", prompt])

    return argv


def _parse_final_json(
    value: Any,
) -> dict[str, Any] | None:
    if not isinstance(
        value,
        str,
    ):
        return None

    text = value.strip()

    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()

        if len(lines) >= 3:
            text = "\n".join(lines[1:-1]).strip()

    try:
        payload = json.loads(text)
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


def _usage(value: Any) -> TokenUsage:
    usage = sanitized_usage(value) or {}
    return TokenUsage(
        input=usage.get("input_tokens"), output=usage.get("output_tokens")
    )


def _codex_item(item: Any, telemetry: CodexTelemetry, repo: Path) -> CodexTelemetry:
    if not isinstance(item, dict):
        raise ValueError("completed item must be an object")
    kind = item.get("type")
    if kind == "agent_message":
        files, symbols = structured_payload(_parse_final_json(item.get("text")), repo)
        return replace(telemetry, files=files, symbols=symbols, structured_output=True)
    if kind in {"command_execution", "mcp_tool_call", "web_search", "file_change"}:
        call = {
            key: item[key]
            for key in ("type", "server", "tool", "name")
            if isinstance(item.get(key), str)
        }
        telemetry.tool_calls.append(call)
    return telemetry


def parse_codex_stream(stdout: str, repo: Path) -> CodexTelemetry:
    telemetry = CodexTelemetry([], [], [], TokenUsage(), True, False, None)
    try:
        events = json_lines(stdout)
        completed = [event for event in events if event.get("type") == "turn.completed"]
        if len(completed) != 1:
            return telemetry
        if any(event.get("type") in {"turn.failed", "error"} for event in events):
            return telemetry
        for event in events:
            if event.get("type") == "item.completed":
                telemetry = _codex_item(event.get("item"), telemetry, repo)
        usage = completed[0].get("usage")
        return replace(
            telemetry,
            failed=not telemetry.structured_output,
            tokens=_usage(usage),
            raw_usage=sanitized_usage(usage),
        )
    except (ValueError, TypeError):
        return replace(telemetry, failed=True, structured_output=False)


def _execute_codex(config: CodexConfig, repo: Path, prompt: str, enabled: bool):
    fd, raw_schema = tempfile.mkstemp(
        prefix=("codeintel-agent-schema-"),
        suffix=".json",
    )

    schema_path = Path(raw_schema)

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
            config,
            CodexInvocation(
                codeintel_enabled=enabled,
                schema_path=schema_path,
                repo=repo,
                prompt=prompt,
            ),
        )

        process = run_process(
            argv,
            cwd=repo,
            timeout_seconds=config.timeout_seconds,
            options=AgentProcessOptions(
                agent="codex",
                codeintel_binary=config.codeintel_binary if enabled else None,
            ),
        )

    finally:
        schema_path.unlink(missing_ok=True)

    return process


class CodexRunner:
    def __init__(
        self,
        codeintel_enabled: bool,
        config: CodexConfig | None = None,
    ) -> None:
        self.codeintel_enabled = codeintel_enabled

        self.config = config if config is not None else CodexConfig()

        self.name = "codex-codeintel" if codeintel_enabled else "codex"

    def run(
        self,
        task: BenchmarkTask,
        repo: Path,
    ) -> BenchmarkResult:
        prompt = benchmark_prompt(task)

        process = _execute_codex(self.config, repo, prompt, self.codeintel_enabled)

        telemetry = parse_codex_stream(
            process.stdout,
            repo,
        )

        success = (
            not process.timed_out
            and process.exit_code == 0
            and not telemetry.failed
            and telemetry.structured_output
        )

        return BenchmarkResult(
            runner=self.name,
            task_id=task.id,
            success=success,
            duration_ms=(process.duration_ms),
            files=telemetry.files,
            symbols=telemetry.symbols,
            tool_calls=(telemetry.tool_calls),
            tokens=telemetry.tokens,
            stdout="",
            stderr="",
            exit_code=(process.exit_code),
            metadata={
                "agent": "codex",
                "model": (self.config.model),
                "codeintel_enabled": (self.codeintel_enabled),
                "telemetry_format": ("codex-jsonl"),
                "structured_output": (telemetry.structured_output),
                # JSONL does not expose a
                # trustworthy canonical list
                # of every file read.
                "tool_calls_observed": bool(telemetry.tool_calls),
                "files_read": None,
                "usage": (telemetry.raw_usage),
                "timed_out": (process.timed_out),
                "stderr_present": bool(process.stderr),
            },
        )
