from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
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


ALLOWED_PLACEHOLDERS = frozenset(
    {
        "prompt",
        "repo",
    }
)

SHELL_EXECUTABLES = frozenset(
    {
        "sh",
        "bash",
        "zsh",
    }
)

PLACEHOLDER_PATTERN = re.compile(
    r"\{([A-Za-z_][A-Za-z0-9_]*)\}"
)


@dataclass(frozen=True)
class AgentCommand:
    name: str
    argv: tuple[str, ...]
    timeout_seconds: float
    codeintel_enabled: bool


def _placeholders(
    value: str,
) -> set[str]:
    return set(
        PLACEHOLDER_PATTERN.findall(
            value
        )
    )


def validate_command(
    command: AgentCommand,
) -> None:
    if not command.name.strip():
        raise ValueError(
            "agent command name must not be empty"
        )

    if not command.argv:
        raise ValueError(
            "agent argv must not be empty"
        )

    if command.timeout_seconds <= 0:
        raise ValueError(
            "agent timeout must be greater than zero"
        )

    executable = Path(
        command.argv[0]
    ).name

    if (
        executable in SHELL_EXECUTABLES
        and len(command.argv) >= 2
        and command.argv[1] == "-c"
    ):
        raise ValueError(
            "shell wrapper commands are not allowed"
        )

    placeholders: set[str] = set()

    for argument in command.argv:
        placeholders.update(
            _placeholders(argument)
        )

    unknown = (
        placeholders
        - ALLOWED_PLACEHOLDERS
    )

    if unknown:
        raise ValueError(
            "unknown command placeholder(s): "
            + ", ".join(
                sorted(unknown)
            )
        )

    if "prompt" not in placeholders:
        raise ValueError(
            "agent command must contain "
            "the {prompt} placeholder"
        )


def render_command(
    command: AgentCommand,
    prompt: str,
    repo: Path,
) -> list[str]:
    validate_command(command)

    repository = str(
        Path(repo).resolve()
    )

    return [
        argument
        .replace(
            "{prompt}",
            prompt,
        )
        .replace(
            "{repo}",
            repository,
        )
        for argument in command.argv
    ]


def _string_list(
    value: Any,
) -> list[str]:
    if not isinstance(
        value,
        list,
    ):
        return []

    result = []

    for item in value:
        if (
            isinstance(item, str)
            and item not in result
        ):
            result.append(item)

    return result


def _tool_calls(
    value: Any,
) -> list[Any]:
    if not isinstance(
        value,
        list,
    ):
        return []

    return value


def _token_usage(
    value: Any,
) -> TokenUsage:
    if not isinstance(
        value,
        dict,
    ):
        return TokenUsage()

    raw_input = value.get(
        "input_tokens",
        value.get("input"),
    )

    raw_output = value.get(
        "output_tokens",
        value.get("output"),
    )

    input_tokens = (
        raw_input
        if isinstance(raw_input, int)
        and not isinstance(raw_input, bool)
        else None
    )

    output_tokens = (
        raw_output
        if isinstance(raw_output, int)
        and not isinstance(raw_output, bool)
        else None
    )

    return TokenUsage(
        input=input_tokens,
        output=output_tokens,
    )


def _json_payload(
    stdout: str,
) -> dict[str, Any] | None:
    value = stdout.strip()

    if not value:
        return None

    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return None

    if not isinstance(
        payload,
        dict,
    ):
        return None

    return payload


class GenericAgentRunner:
    def __init__(
        self,
        command: AgentCommand,
    ) -> None:
        validate_command(command)

        self.command = command
        self.name = command.name

    def run(
        self,
        task: BenchmarkTask,
        repo: Path,
    ) -> BenchmarkResult:
        argv = render_command(
            self.command,
            prompt=task.prompt,
            repo=repo,
        )

        process = run_process(
            argv,
            cwd=repo,
            timeout_seconds=(
                self.command.timeout_seconds
            ),
        )

        payload = _json_payload(
            process.stdout
        )

        files: list[str] = []
        symbols: list[str] = []
        tool_calls: list[Any] = []
        tokens = TokenUsage()

        telemetry_format = None

        if payload is not None:
            telemetry_format = "json"

            files = _string_list(
                payload.get("files")
            )

            symbols = _string_list(
                payload.get("symbols")
            )

            tool_calls = _tool_calls(
                payload.get(
                    "tool_calls"
                )
            )

            tokens = _token_usage(
                payload.get("usage")
            )

        success = (
            not process.timed_out
            and process.exit_code == 0
        )

        return BenchmarkResult(
            runner=self.name,
            task_id=task.id,
            success=success,
            duration_ms=process.duration_ms,
            files=files,
            symbols=symbols,
            tool_calls=tool_calls,
            tokens=tokens,
            stdout=process.stdout,
            stderr=process.stderr,
            exit_code=process.exit_code,
            metadata={
                "agent": self.command.name,
                "codeintel_enabled": (
                    self.command.codeintel_enabled
                ),
                "telemetry_format": (
                    telemetry_format
                ),
            },
        )
