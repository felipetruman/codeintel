from __future__ import annotations


DEFAULT_RUNNERS = (
    "rg",
    "codeintel",
)

ALL_RUNNERS = (
    "rg",
    "codeintel",
    "claude",
    "claude-codeintel",
    "codex",
    "codex-codeintel",
)

AGENT_RUNNERS = frozenset(
    {
        "claude",
        "claude-codeintel",
        "codex",
        "codex-codeintel",
    }
)


def resolve_runner_names(
    requested: list[str],
    all_runners: bool,
) -> list[str]:
    if all_runners and requested:
        raise ValueError(
            "--all cannot be combined with --runner"
        )

    if all_runners:
        return list(ALL_RUNNERS)

    if not requested:
        return list(DEFAULT_RUNNERS)

    result: list[str] = []

    for runner in requested:
        if runner not in ALL_RUNNERS:
            raise ValueError(
                f"unknown runner: {runner}"
            )

        if runner not in result:
            result.append(runner)

    return result


def contains_real_agents(
    runners: list[str],
) -> bool:
    return any(
        runner in AGENT_RUNNERS
        for runner in runners
    )


def require_real_agent_opt_in(
    runners: list[str],
    allowed: bool,
) -> None:
    if (
        contains_real_agents(runners)
        and not allowed
    ):
        raise ValueError(
            "real agent runners require "
            "--allow-real-agents"
        )


def balanced_runner_order(
    runners: list[str],
    repetition: int,
    seed: int,
) -> list[str]:
    if not runners:
        return []

    offset = (
        repetition
        + seed
    ) % len(runners)

    return (
        runners[offset:]
        + runners[:offset]
    )


def ab_pairs(
    runners: list[str],
) -> list[tuple[str, str]]:
    available = set(runners)

    candidates = [
        (
            "claude",
            "claude-codeintel",
        ),
        (
            "codex",
            "codex-codeintel",
        ),
    ]

    return [
        pair
        for pair in candidates
        if (
            pair[0] in available
            and pair[1] in available
        )
    ]
