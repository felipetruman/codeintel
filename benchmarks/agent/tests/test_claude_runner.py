from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from benchmarks.agent.manifests import (
    BenchmarkTask,
    GroundTruth,
)
from benchmarks.agent.runners.claude import (
    ClaudeConfig,
    ClaudeRunner,
    build_claude_command,
    parse_claude_stream,
)


def task() -> BenchmarkTask:
    return BenchmarkTask(
        id="claude-test",
        type="relevant-files",
        query="payment",
        prompt="Find the payment implementation.",
        corpus="synthetic/test",
        expected=GroundTruth(),
    )


def mcp_payload(argv: list[str]) -> dict:
    index = argv.index("--mcp-config")
    return json.loads(argv[index + 1])


def test_baseline_uses_strict_empty_mcp_config(
    tmp_path: Path,
):
    argv = build_claude_command(
        ClaudeConfig(
            executable="claude",
            model="test-model",
            codeintel_binary="codeintel",
        ),
        repo=tmp_path,
        prompt="test prompt",
        codeintel_enabled=False,
    )

    assert "-p" in argv
    assert "--restricted" in argv
    assert "--strict-mcp-config" in argv
    assert "--output-format" in argv
    assert "stream-json" in argv
    assert "--json-schema" in argv
    assert "--no-session-persistence" in argv
    assert "--permission-mode" in argv
    assert "plan" in argv

    assert mcp_payload(argv) == {
        "mcpServers": {}
    }


def test_codeintel_arm_has_only_benchmark_mcp(
    tmp_path: Path,
):
    argv = build_claude_command(
        ClaudeConfig(
            executable="claude",
            codeintel_binary="/opt/codeintel",
        ),
        repo=tmp_path,
        prompt="test prompt",
        codeintel_enabled=True,
    )

    payload = mcp_payload(argv)

    assert set(
        payload["mcpServers"]
    ) == {"codeintel"}

    server = payload[
        "mcpServers"
    ]["codeintel"]

    assert server["type"] == "stdio"
    assert server["command"] == "/opt/codeintel"

    assert server["args"] == [
        "mcp",
        str(tmp_path.resolve()),
    ]


def test_ab_commands_differ_only_in_mcp_payload(
    tmp_path: Path,
):
    config = ClaudeConfig(
        executable="claude",
        model="same-model",
        codeintel_binary="/opt/codeintel",
    )

    baseline = build_claude_command(
        config,
        repo=tmp_path,
        prompt="same prompt",
        codeintel_enabled=False,
    )

    enhanced = build_claude_command(
        config,
        repo=tmp_path,
        prompt="same prompt",
        codeintel_enabled=True,
    )

    index = baseline.index(
        "--mcp-config"
    )

    baseline[index + 1] = "<MCP>"
    enhanced[index + 1] = "<MCP>"

    assert baseline == enhanced


def test_parser_extracts_structured_output_tools_and_usage(
    tmp_path: Path,
):
    source = (
        tmp_path
        / "src"
        / "payment.py"
    )

    stdout = "\n".join(
        [
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "tool-1",
                                "name": "Read",
                                "input": {
                                    "file_path": str(
                                        source
                                    )
                                },
                            },
                            {
                                "type": "tool_use",
                                "id": "tool-2",
                                "name": (
                                    "mcp__codeintel__search"
                                ),
                                "input": {
                                    "query": "payment"
                                },
                            },
                        ]
                    },
                }
            ),
            json.dumps(
                {
                    "type": "result",
                    "subtype": "success",
                    "is_error": False,
                    "usage": {
                        "input_tokens": 10,
                        "cache_read_input_tokens": 7,
                        "cache_creation_input_tokens": 3,
                        "output_tokens": 4,
                    },
                    "structured_output": {
                        "files": [
                            "src/payment.py"
                        ],
                        "symbols": [
                            "process_payment"
                        ],
                        "answer": "Found it.",
                    },
                }
            ),
        ]
    )

    telemetry = parse_claude_stream(
        stdout,
        tmp_path,
    )

    assert telemetry.files == [
        "src/payment.py"
    ]

    assert telemetry.symbols == [
        "process_payment"
    ]

    assert telemetry.files_read == [
        "src/payment.py"
    ]

    assert [
        call["name"]
        for call in telemetry.tool_calls
    ] == [
        "Read",
        "mcp__codeintel__search",
    ]

    assert telemetry.tokens.input == 20
    assert telemetry.tokens.output == 4
    assert telemetry.tokens.total == 24
    assert telemetry.is_error is False


def test_runner_does_not_persist_raw_agent_stream(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    import benchmarks.agent.runners.claude as module

    stream = json.dumps(
        {
            "type": "result",
            "is_error": False,
            "usage": {
                "input_tokens": 1,
                "output_tokens": 1,
            },
            "structured_output": {
                "files": [],
                "symbols": [],
                "answer": "secret-looking-output",
            },
        }
    )

    monkeypatch.setattr(
        module,
        "run_process",
        lambda *args, **kwargs: SimpleNamespace(
            stdout=stream,
            stderr="sensitive stderr",
            exit_code=0,
            timed_out=False,
            duration_ms=42.0,
        ),
    )

    result = ClaudeRunner(
        codeintel_enabled=False,
        config=ClaudeConfig(
            executable="claude",
        ),
    ).run(
        task(),
        tmp_path,
    )

    assert result.success is True
    assert result.stdout == ""
    assert result.stderr == ""
    assert result.metadata[
        "stderr_present"
    ] is True


@pytest.mark.skipif(
    os.getenv(
        "CODEINTEL_BENCH_REAL_AGENTS"
    )
    != "1",
    reason=(
        "real agent tests are opt-in"
    ),
)
def test_real_claude_agent_opt_in(
    tmp_path: Path,
):
    (
        tmp_path
        / "payment.py"
    ).write_text(
        "def process_payment():\n"
        "    return True\n",
        encoding="utf-8",
    )

    result = ClaudeRunner(
        codeintel_enabled=False,
        config=ClaudeConfig(
            timeout_seconds=120,
        ),
    ).run(
        task(),
        tmp_path,
    )

    assert result.success is True
