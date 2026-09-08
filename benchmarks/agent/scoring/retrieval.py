from __future__ import annotations

from collections.abc import Sequence


def _dedupe(
    values: Sequence[str],
) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []

    for value in values:
        if value in seen:
            continue

        seen.add(value)
        result.append(value)

    return result


def precision(
    returned: Sequence[str],
    expected: Sequence[str],
) -> float:
    ranked = _dedupe(returned)
    truth = set(expected)

    if not ranked:
        return 1.0 if not truth else 0.0

    relevant = sum(
        item in truth
        for item in ranked
    )

    return relevant / len(ranked)


def recall(
    returned: Sequence[str],
    expected: Sequence[str],
) -> float:
    ranked = _dedupe(returned)
    truth = set(expected)

    if not truth:
        return 1.0

    relevant = sum(
        item in truth
        for item in ranked
    )

    return relevant / len(truth)


def f1(
    precision_value: float,
    recall_value: float,
) -> float:
    denominator = (
        precision_value + recall_value
    )

    if denominator == 0:
        return 0.0

    return (
        2
        * precision_value
        * recall_value
        / denominator
    )


def precision_at_k(
    returned: Sequence[str],
    expected: Sequence[str],
    k: int,
) -> float:
    if k <= 0:
        raise ValueError(
            "k must be greater than zero"
        )

    top = _dedupe(returned)[:k]
    truth = set(expected)

    relevant = sum(
        item in truth
        for item in top
    )

    return relevant / k


def recall_at_k(
    returned: Sequence[str],
    expected: Sequence[str],
    k: int,
) -> float:
    if k <= 0:
        raise ValueError(
            "k must be greater than zero"
        )

    truth = set(expected)

    if not truth:
        return 1.0

    top = _dedupe(returned)[:k]

    relevant = sum(
        item in truth
        for item in top
    )

    return relevant / len(truth)


def reciprocal_rank(
    returned: Sequence[str],
    expected: Sequence[str],
) -> float:
    truth = set(expected)

    if not truth:
        return 1.0

    for index, item in enumerate(
        _dedupe(returned),
        start=1,
    ):
        if item in truth:
            return 1.0 / index

    return 0.0
