import pytest

from benchmarks.agent.scoring.retrieval import (
    f1,
    precision,
    precision_at_k,
    recall,
    recall_at_k,
    reciprocal_rank,
)


def test_standard_retrieval_metrics():
    returned = ["a", "b", "c"]
    expected = ["a", "c", "d"]

    assert precision(returned, expected) == pytest.approx(2 / 3)
    assert recall(returned, expected) == pytest.approx(2 / 3)

    p = precision(returned, expected)
    r = recall(returned, expected)

    assert f1(p, r) == pytest.approx(2 / 3)
    assert precision_at_k(
        returned,
        expected,
        2,
    ) == pytest.approx(1 / 2)
    assert recall_at_k(
        returned,
        expected,
        2,
    ) == pytest.approx(1 / 3)
    assert reciprocal_rank(
        returned,
        expected,
    ) == 1.0


def test_duplicate_results_are_not_double_counted():
    returned = ["a", "a", "b"]
    expected = ["a", "b"]

    assert precision(returned, expected) == 1.0
    assert recall(returned, expected) == 1.0


def test_empty_expected_is_perfect_recall():
    assert recall([], []) == 1.0
    assert precision([], []) == 1.0


def test_empty_returned_with_expected_has_zero_metrics():
    assert precision([], ["a"]) == 0.0
    assert recall([], ["a"]) == 0.0
    assert reciprocal_rank([], ["a"]) == 0.0


def test_reciprocal_rank_uses_first_relevant_result():
    assert reciprocal_rank(
        ["noise", "target", "later"],
        ["target"],
    ) == pytest.approx(0.5)


@pytest.mark.parametrize("k", [0, -1])
def test_at_k_requires_positive_k(k):
    with pytest.raises(ValueError):
        precision_at_k(["a"], ["a"], k)

    with pytest.raises(ValueError):
        recall_at_k(["a"], ["a"], k)
