from __future__ import annotations

import sys
from pathlib import Path

import pytest

from benchmarks.agent.manifests import (
    BenchmarkTask,
    GroundTruth,
)
from benchmarks.agent.runners.agent_base import (
    AgentCommand,
    GenericAgentRunner,
    render_command,
    validate_command,
)


def benchmark_task() -> BenchmarkTask:
    return BenchmarkTask(
        id="agent-test",
        type="relevant-files",
        query="payment",
        prompt="Find payment code.",
        corpus="synthetic/test",
        expected=GroundTruth(),
    )


def test_render_command_substitutes_prompt_and_repo(
    tmp_path: Path,
):
    command = AgentCommand(
        name="fake",
        argv=(
            "agent",
            "--repo",
            "{repo}",
            "--prompt",
            "{prompt}",
        ),
        timeout_seconds=10,
        codeintel_enabled=False,
    )

    assert render_command(
        command,
        prompt="Find payment code.",
        repo=tmp_path,
    ) == [
        "agent",
        "--repo",
        str(tmp_path.resolve()),
        "--prompt",
        "Find payment code.",
    ]


def test_python_dict_braces_are_not_placeholders():
    command = AgentCommand(
        name="fake",
        argv=(
            "python",
            "-c",
            "print({'files': ['x.py']})",
            "{prompt}",
        ),
        timeout_seconds=10,
        codeintel_enabled=False,
    )

    validate_command(command)


def test_command_requires_prompt_placeholder():
    command = AgentCommand(
        name="fake",
        argv=(
            "agent",
            "--repo",
            "{repo}",
        ),
        timeout_seconds=10,
        codeintel_enabled=False,
    )

    with pytest.raises(
        ValueError,
        match="prompt",
    ):
        validate_command(command)


@pytest.mark.parametrize(
    "argv",
    [
        ("sh", "-c", "{prompt}"),
        ("bash", "-c", "{prompt}"),
        ("zsh", "-c", "{prompt}"),
    ],
)
def test_shell_wrappers_are_rejected(argv):
    command = AgentCommand(
        name="unsafe",
        argv=argv,
        timeout_seconds=10,
        codeintel_enabled=False,
    )

    with pytest.raises(
        ValueError,
        match="shell",
    ):
        validate_command(command)


def test_unknown_placeholder_is_rejected():
    command = AgentCommand(
        name="fake",
        argv=(
            "agent",
            "{prompt}",
            "{secret}",
        ),
        timeout_seconds=10,
        codeintel_enabled=False,
    )

    with pytest.raises(
        ValueError,
        match="placeholder",
    ):
        validate_command(command)


def test_invalid_timeout_is_rejected():
    command = AgentCommand(
        name="fake",
        argv=(
            "agent",
            "{prompt}",
        ),
        timeout_seconds=0,
        codeintel_enabled=False,
    )

    with pytest.raises(
        ValueError,
        match="timeout",
    ):
        validate_command(command)


def test_generic_agent_normalizes_json_telemetry(
    tmp_path: Path,
):
    script = (
        "import json,sys;"
        "print(json.dumps({"
        "'files':['src/payment.py'],"
        "'symbols':['process_payment'],"
        "'tool_calls':[{'name':'read'}],"
        "'usage':{"
        "'input_tokens':12,"
        "'output_tokens':3"
        "},"
        "'response':sys.argv[1]"
        "}))"
    )

    command = AgentCommand(
        name="fake-agent",
        argv=(
            sys.executable,
            "-c",
            script,
            "{prompt}",
        ),
        timeout_seconds=5,
        codeintel_enabled=True,
    )

    result = GenericAgentRunner(
        command
    ).run(
        benchmark_task(),
        tmp_path,
    )

    assert result.success is True
    assert result.exit_code == 0

    assert result.files == [
        "src/payment.py"
    ]

    assert result.symbols == [
        "process_payment"
    ]

    assert result.tool_calls == [
        {"name": "read"}
    ]

    assert result.tokens.input == 12
    assert result.tokens.output == 3
    assert result.tokens.total == 15

    assert result.metadata[
        "codeintel_enabled"
    ] is True

    assert result.metadata[
        "telemetry_format"
    ] == "json"


def test_missing_telemetry_remains_null(
    tmp_path: Path,
):
    command = AgentCommand(
        name="plain-agent",
        argv=(
            sys.executable,
            "-c",
            "import sys; print(sys.argv[1])",
            "{prompt}",
        ),
        timeout_seconds=5,
        codeintel_enabled=False,
    )

    result = GenericAgentRunner(
        command
    ).run(
        benchmark_task(),
        tmp_path,
    )

    assert result.success is True
    assert result.files == []
    assert result.symbols == []
    assert result.tool_calls == []

    assert result.tokens.input is None
    assert result.tokens.output is None
    assert result.tokens.total is None

    assert result.metadata[
        "telemetry_format"
    ] is None


def test_nonzero_agent_exit_is_failure(
    tmp_path: Path,
):
    command = AgentCommand(
        name="failing-agent",
        argv=(
            sys.executable,
            "-c",
            "raise SystemExit(9)",
            "{prompt}",
        ),
        timeout_seconds=5,
        codeintel_enabled=False,
    )

    result = GenericAgentRunner(
        command
    ).run(
        benchmark_task(),
        tmp_path,
    )

    assert result.success is False
    assert result.exit_code == 9
