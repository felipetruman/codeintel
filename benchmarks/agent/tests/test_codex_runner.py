from __future__ import annotations

from benchmarks.agent.runners.codex import CodexInvocation

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from benchmarks.agent.manifests import (
    BenchmarkTask,
    GroundTruth,
)
from benchmarks.agent.runners.codex import (
    CodexConfig,
    CodexRunner,
    build_codex_command,
    parse_codex_stream,
)


def task() -> BenchmarkTask:
    return BenchmarkTask(
        id="codex-test",
        type="impact-analysis",
        query="process_payment",
        prompt=("Find callers of process_payment."),
        corpus="synthetic/test",
        expected=GroundTruth(),
    )


def strip_codeintel_overrides(
    argv: list[str],
) -> list[str]:
    result: list[str] = []
    index = 0

    while index < len(argv):
        if argv[index : index + 1] == ["-c"] and _is_mcp_override(
            argv[index + 1 : index + 2]
        ):
            index += 2
            continue

        result.append(argv[index])
        index += 1

    return result


def test_baseline_is_ephemeral_and_read_only(
    tmp_path: Path,
):
    argv = build_codex_command(
        CodexConfig(
            executable="codex", model="test-model", codeintel_binary="codeintel"
        ),
        CodexInvocation(
            repo=tmp_path,
            prompt="test prompt",
            codeintel_enabled=False,
            schema_path=Path("/tmp/schema.json"),
        ),
    )

    assert argv[:2] == [
        "codex",
        "exec",
    ]

    assert "--json" in argv
    assert "--ephemeral" in argv

    assert "--ignore-user-config" in argv

    assert "--ignore-rules" in argv

    assert "--skip-git-repo-check" in argv

    sandbox_index = argv.index("--sandbox")

    assert argv[sandbox_index + 1] == "read-only"

    assert "--output-schema" in argv

    assert not any("mcp_servers.codeintel." in value for value in argv)


def test_codeintel_arm_adds_inline_mcp(
    tmp_path: Path,
):
    argv = build_codex_command(
        CodexConfig(executable="codex", codeintel_binary="/opt/codeintel"),
        CodexInvocation(
            repo=tmp_path,
            prompt="test prompt",
            codeintel_enabled=True,
            schema_path=Path("/tmp/schema.json"),
        ),
    )

    overrides = [
        argv[index + 1] for index, value in enumerate(argv[:-1]) if value == "-c"
    ]

    assert 'mcp_servers.codeintel.command="/opt/codeintel"' in overrides

    expected_args = "mcp_servers.codeintel.args=" + json.dumps(
        [
            "mcp",
            str(tmp_path.resolve()),
        ],
        separators=(",", ":"),
    )

    assert expected_args in overrides


def test_ab_commands_only_differ_by_codeintel_mcp(
    tmp_path: Path,
):
    config = CodexConfig(
        executable="codex",
        model="same-model",
        codeintel_binary=("/opt/codeintel"),
    )

    schema = Path("/tmp/schema.json")

    baseline = build_codex_command(
        config,
        CodexInvocation(
            repo=tmp_path,
            prompt="same prompt",
            codeintel_enabled=False,
            schema_path=schema,
        ),
    )

    enhanced = build_codex_command(
        config,
        CodexInvocation(
            repo=tmp_path,
            prompt="same prompt",
            codeintel_enabled=True,
            schema_path=schema,
        ),
    )

    assert strip_codeintel_overrides(enhanced) == baseline


def test_parser_extracts_output_tools_and_tokens(
    tmp_path: Path,
):
    stdout = _stream_parser_extracts_output_tools_and_tokens(tmp_path)

    telemetry = parse_codex_stream(
        stdout,
        tmp_path,
    )

    assert telemetry.files == [
        "src/payment.py",
        "src/api.py",
    ]

    assert telemetry.symbols == [
        "process_payment",
        "submit_order",
    ]

    assert [call["type"] for call in telemetry.tool_calls] == [
        "command_execution",
        "mcp_tool_call",
    ]

    # cached_input_tokens is a subset of
    # input_tokens and must not be added.
    assert telemetry.tokens.input == 20
    assert telemetry.tokens.output == 4
    assert telemetry.tokens.total == 24

    assert telemetry.failed is False


def test_parser_marks_failed_turn(
    tmp_path: Path,
):
    stdout = json.dumps(
        {
            "type": "turn.failed",
            "error": {"message": "failed"},
        }
    )

    telemetry = parse_codex_stream(
        stdout,
        tmp_path,
    )

    assert telemetry.failed is True


def test_runner_uses_temporary_schema_and_discards_raw_stream(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    import benchmarks.agent.runners.codex as module

    captured: dict[
        str,
        object,
    ] = {}

    stream = _stream_runner_uses_temporary_schema_and_discards_raw_stream(tmp_path)

    def fake_run_process(
        argv,
        **kwargs,
    ):
        captured["argv"] = list(argv)

        schema_index = argv.index("--output-schema")

        schema_path = Path(argv[schema_index + 1])

        assert schema_path.exists()

        captured["schema_path"] = schema_path

        return SimpleNamespace(
            stdout=stream,
            stderr="sensitive stderr",
            exit_code=0,
            timed_out=False,
            duration_ms=21.0,
        )

    monkeypatch.setattr(
        module,
        "run_process",
        fake_run_process,
    )

    result = CodexRunner(
        codeintel_enabled=False,
        config=CodexConfig(
            executable="codex",
        ),
    ).run(
        task(),
        tmp_path,
    )

    assert result.success is True

    assert result.stdout == ""
    assert result.stderr == ""

    assert result.metadata["stderr_present"] is True

    assert result.metadata["files_read"] is None

    schema_path = captured["schema_path"]

    assert isinstance(
        schema_path,
        Path,
    )

    assert not schema_path.exists()


@pytest.mark.skipif(
    os.getenv("CODEINTEL_BENCH_REAL_AGENTS") != "1",
    reason=("real agent tests are opt-in"),
)
def test_real_codex_agent_opt_in(
    tmp_path: Path,
):
    (tmp_path / "payment.py").write_text(
        "def process_payment():\n" "    return True\n",
        encoding="utf-8",
    )

    result = CodexRunner(
        codeintel_enabled=False,
        config=CodexConfig(
            timeout_seconds=120,
        ),
    ).run(
        task(),
        tmp_path,
    )

    assert result.success is True


def _stream_parser_extracts_output_tools_and_tokens(tmp_path):
    return "\n".join(
        [
            json.dumps({"type": "thread.started", "thread_id": "abc"}),
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "1",
                        "type": "command_execution",
                        "command": "rg process_payment",
                    },
                }
            ),
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "2",
                        "type": "mcp_tool_call",
                        "server": "codeintel",
                        "tool": "impact",
                    },
                }
            ),
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "3",
                        "type": "agent_message",
                        "text": json.dumps(
                            {
                                "files": ["src/payment.py", "src/api.py"],
                                "symbols": ["process_payment", "submit_order"],
                                "answer": "done",
                            }
                        ),
                    },
                }
            ),
            json.dumps(
                {
                    "type": "turn.completed",
                    "usage": {
                        "input_tokens": 20,
                        "cached_input_tokens": 7,
                        "output_tokens": 4,
                    },
                }
            ),
        ]
    )


def _stream_runner_uses_temporary_schema_and_discards_raw_stream(tmp_path):
    return "\n".join(
        [
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "type": "agent_message",
                        "text": json.dumps(
                            {"files": [], "symbols": [], "answer": "sensitive"}
                        ),
                    },
                }
            ),
            json.dumps(
                {
                    "type": "turn.completed",
                    "usage": {"input_tokens": 2, "output_tokens": 1},
                }
            ),
        ]
    )


def _is_mcp_override(values):
    return bool(values) and values[0].startswith("mcp_servers.codeintel.")
