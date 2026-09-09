from __future__ import annotations

from collections.abc import Sequence


def _dedupe(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _top(returned: Sequence[str], k: int) -> list[str]:
    if k <= 0:
        raise ValueError("k must be greater than zero")
    return _dedupe(returned)[:k]


def _intersection_size(returned: Sequence[str], expected: Sequence[str]) -> int:
    return len(set(returned).intersection(expected))


def precision(returned: Sequence[str], expected: Sequence[str]) -> float:
    count = len(set(returned))
    if not count:
        return float(not expected)
    return _intersection_size(returned, expected) / count


def recall(returned: Sequence[str], expected: Sequence[str]) -> float:
    truth = set(expected)
    return _intersection_size(returned, expected) / len(truth) if truth else 1.0


def f1(
    precision_value: float,
    recall_value: float,
) -> float:
    denominator = precision_value + recall_value

    if denominator == 0:
        return 0.0

    return 2 * precision_value * recall_value / denominator


def precision_at_k(returned: Sequence[str], expected: Sequence[str], k: int) -> float:
    return _intersection_size(_top(returned, k), expected) / k


def recall_at_k(returned: Sequence[str], expected: Sequence[str], k: int) -> float:
    return recall(_top(returned, k), expected)


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
