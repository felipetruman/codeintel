from __future__ import annotations

import importlib

from benchmarks.agent.manifests import (
    BenchmarkTask,
    GroundTruth,
)
from benchmarks.agent.models import (
    BenchmarkResult,
    TokenUsage,
)


def scheduler_module():
    try:
        return importlib.import_module("benchmarks.agent.scheduler")
    except ModuleNotFoundError as error:
        raise AssertionError("benchmark scheduler is not implemented") from error


def test_balanced_order_alternates_two_runner_order():
    module = scheduler_module()

    assert module.balanced_order(
        ["baseline", "codeintel"],
        repeat=4,
    ) == [
        "baseline",
        "codeintel",
        "codeintel",
        "baseline",
        "baseline",
        "codeintel",
        "codeintel",
        "baseline",
    ]


def test_balanced_order_rotates_more_than_two_runners():
    module = scheduler_module()

    assert module.balanced_order(
        ["a", "b", "c"],
        repeat=3,
    ) == [
        "a",
        "b",
        "c",
        "b",
        "c",
        "a",
        "c",
        "a",
        "b",
    ]


def test_balanced_order_rejects_invalid_repeat():
    module = scheduler_module()

    try:
        module.balanced_order(
            ["a"],
            repeat=0,
        )
    except ValueError as error:
        assert "repeat" in str(error)
    else:
        raise AssertionError("repeat=0 must fail")


def test_score_result_adds_retrieval_metrics():
    module = scheduler_module()

    task = BenchmarkTask(
        id="x",
        type="relevant-files",
        query="payment",
        prompt="payment",
        corpus="synthetic/x",
        expected=GroundTruth(
            files=(
                "a.py",
                "b.py",
            ),
        ),
    )

    result = BenchmarkResult(
        runner="rg",
        task_id="x",
        success=True,
        duration_ms=1,
        files=[
            "a.py",
            "noise.py",
        ],
        tokens=TokenUsage(),
    )

    scored = module.score_result(
        task,
        result,
    )

    scores = scored.metadata["scores"]

    assert scores["file_precision"] == 0.5

    assert scores["file_recall"] == 0.5

    assert scores["file_f1"] == 0.5


def test_score_result_adds_graph_metrics():
    module = scheduler_module()

    task = BenchmarkTask(
        id="impact",
        type="impact-analysis",
        query="target",
        prompt="target",
        corpus="synthetic/x",
        expected=GroundTruth(
            direct_callers=("caller",),
            blast_radius=2,
        ),
    )

    result = BenchmarkResult(
        runner="codeintel",
        task_id="impact",
        success=True,
        duration_ms=1,
        tokens=TokenUsage(),
        metadata={
            "direct_callers": ["caller"],
            "blast_radius": 3,
        },
    )

    scored = module.score_result(
        task,
        result,
    )

    scores = scored.metadata["scores"]

    assert scores["direct_caller_precision"] == 1.0

    assert scores["direct_caller_recall"] == 1.0

    assert scores["blast_radius_error"] == 1
