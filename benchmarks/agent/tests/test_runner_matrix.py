from __future__ import annotations

import pytest

from benchmarks.agent.runner_matrix import (
    AGENT_RUNNERS,
    ALL_RUNNERS,
    DEFAULT_RUNNERS,
    ab_pairs,
    balanced_runner_order,
    contains_real_agents,
    require_real_agent_opt_in,
    resolve_runner_names,
)


def test_default_matrix_is_deterministic_only():
    assert resolve_runner_names(
        requested=[],
        all_runners=False,
    ) == list(DEFAULT_RUNNERS)


def test_all_matrix_contains_six_runners():
    assert resolve_runner_names(
        requested=[],
        all_runners=True,
    ) == list(ALL_RUNNERS)

    assert len(ALL_RUNNERS) == 6

    assert ALL_RUNNERS == (
        "rg",
        "codeintel",
        "claude",
        "claude-codeintel",
        "codex",
        "codex-codeintel",
    )


def test_explicit_runner_order_is_preserved_and_deduplicated():
    assert resolve_runner_names(
        requested=[
            "codex",
            "rg",
            "codex",
            "codeintel",
        ],
        all_runners=False,
    ) == [
        "codex",
        "rg",
        "codeintel",
    ]


def test_unknown_runner_is_rejected():
    with pytest.raises(
        ValueError,
        match="unknown runner",
    ):
        resolve_runner_names(
            requested=["magic"],
            all_runners=False,
        )


def test_real_agent_detection():
    assert contains_real_agents(["rg", "codeintel"]) is False

    assert contains_real_agents(["rg", "claude"]) is True

    assert AGENT_RUNNERS == frozenset(
        {
            "claude",
            "claude-codeintel",
            "codex",
            "codex-codeintel",
        }
    )


def test_real_agents_require_explicit_opt_in():
    with pytest.raises(
        ValueError,
        match="allow-real-agents",
    ):
        require_real_agent_opt_in(
            ["claude"],
            allowed=False,
        )

    require_real_agent_opt_in(
        ["claude"],
        allowed=True,
    )


def test_balanced_order_rotates_across_repetitions():
    runners = [
        "claude",
        "claude-codeintel",
    ]

    assert balanced_runner_order(
        runners,
        repetition=0,
        seed=0,
    ) == [
        "claude",
        "claude-codeintel",
    ]

    assert balanced_runner_order(
        runners,
        repetition=1,
        seed=0,
    ) == [
        "claude-codeintel",
        "claude",
    ]


def test_ab_pairs_detect_available_agent_pairs():
    assert ab_pairs(
        [
            "rg",
            "claude",
            "claude-codeintel",
            "codex",
            "codex-codeintel",
        ]
    ) == [
        (
            "claude",
            "claude-codeintel",
        ),
        (
            "codex",
            "codex-codeintel",
        ),
    ]
