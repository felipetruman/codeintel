import pytest

from benchmarks.agent.scoring.graph import graph_metrics


def test_graph_metrics():
    metrics = graph_metrics(
        direct_callers=[
            "checkout",
            "noise",
        ],
        expected_callers=[
            "checkout",
            "submit",
        ],
        blast_radius=3,
        expected_blast_radius=2,
    )

    assert metrics["direct_caller_precision"] == pytest.approx(0.5)

    assert metrics["direct_caller_recall"] == pytest.approx(0.5)

    assert metrics["blast_radius_error"] == 1


def test_graph_metrics_preserve_missing_blast_radius():
    metrics = graph_metrics(
        direct_callers=[],
        expected_callers=[],
        blast_radius=None,
        expected_blast_radius=2,
    )

    assert metrics["blast_radius_error"] is None
