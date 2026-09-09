from __future__ import annotations

import pytest

from benchmarks.agent.full_matrix import main


def test_plan_all_lists_all_six_without_running_agents(
    capsys: pytest.CaptureFixture[str],
):
    status = main(
        [
            "--corpus",
            "synthetic",
            "--all",
            "--plan",
        ]
    )

    assert status == 0

    output = capsys.readouterr().out

    for runner in (
        "rg",
        "codeintel",
        "claude",
        "claude-codeintel",
        "codex",
        "codex-codeintel",
    ):
        assert runner in output


def test_real_agent_execution_requires_opt_in():
    with pytest.raises(SystemExit):
        main(
            [
                "--corpus",
                "synthetic",
                "--runner",
                "claude",
            ]
        )


def test_deterministic_plan_needs_no_real_agent_opt_in(
    capsys: pytest.CaptureFixture[str],
):
    status = main(
        [
            "--corpus",
            "synthetic",
            "--runner",
            "rg",
            "--runner",
            "codeintel",
            "--plan",
        ]
    )

    assert status == 0

    output = capsys.readouterr().out

    assert "rg" in output
    assert "codeintel" in output
