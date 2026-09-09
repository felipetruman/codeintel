from __future__ import annotations

import pytest

from benchmarks.agent.agent_metrics import (
    Pricing,
    agent_metrics,
    compare_pair,
    estimated_cost,
    percent_reduction,
)
from benchmarks.agent.manifests import (
    BenchmarkTask,
    GroundTruth,
)
from benchmarks.agent.models import (
    BenchmarkResult,
    TokenUsage,
)


def task() -> BenchmarkTask:
    return BenchmarkTask(
        id="agent-metrics",
        type="relevant-files",
        query="payment",
        prompt="Find payment files.",
        corpus="synthetic/test",
        expected=GroundTruth(
            files=(
                "src/payment.py",
                "src/api.py",
            ),
        ),
    )


def result(
    *,
    runner: str,
    success: bool = True,
    duration_ms: float = 1000.0,
    files: list[str] | None = None,
    files_read: list[str] | None = None,
    tool_calls: int = 2,
    input_tokens: int | None = 1000,
    output_tokens: int | None = 100,
) -> BenchmarkResult:
    return BenchmarkResult(
        runner=runner,
        task_id="agent-metrics",
        success=success,
        duration_ms=duration_ms,
        files=(
            files
            if files is not None
            else [
                "src/payment.py",
                "src/noise.py",
            ]
        ),
        symbols=[],
        tool_calls=[
            {
                "name": f"tool-{index}"
            }
            for index in range(
                tool_calls
            )
        ],
        tokens=TokenUsage(
            input=input_tokens,
            output=output_tokens,
        ),
        stdout="",
        stderr="",
        exit_code=0,
        metadata={
            "files_read": files_read,
        },
    )


def test_percent_reduction():
    assert percent_reduction(
        1000,
        750,
    ) == pytest.approx(25.0)

    assert percent_reduction(
        10,
        8,
    ) == pytest.approx(20.0)


def test_percent_reduction_missing_or_zero_baseline_is_null():
    assert percent_reduction(
        None,
        10,
    ) is None

    assert percent_reduction(
        10,
        None,
    ) is None

    assert percent_reduction(
        0,
        0,
    ) is None


def test_agent_metrics_scores_final_retrieved_files():
    metrics = agent_metrics(
        result(
            runner="claude",
            files=[
                "src/payment.py",
                "src/noise.py",
            ],
            files_read=[
                "src/payment.py",
                "src/noise.py",
                "src/api.py",
            ],
        ),
        task(),
    )

    assert metrics.success is True
    assert metrics.duration_ms == 1000.0

    assert metrics.files_read == 3
    assert metrics.relevant_files_read == 2
    assert metrics.irrelevant_files_read == 1

    assert metrics.file_precision == pytest.approx(
        0.5
    )

    assert metrics.file_recall == pytest.approx(
        0.5
    )

    assert metrics.tool_calls == 2
    assert metrics.input_tokens == 1000
    assert metrics.output_tokens == 100
    assert metrics.total_tokens == 1100


def test_missing_file_read_telemetry_stays_null():
    metrics = agent_metrics(
        result(
            runner="codex",
            files_read=None,
        ),
        task(),
    )

    assert metrics.files_read is None
    assert metrics.relevant_files_read is None
    assert metrics.irrelevant_files_read is None


def test_compare_pair_computes_ab_reductions():
    baseline = result(
        runner="claude",
        duration_ms=10_000,
        files_read=[
            "src/payment.py",
            "src/api.py",
            "src/noise.py",
            "src/other.py",
        ],
        input_tokens=1000,
        output_tokens=200,
    )

    enhanced = result(
        runner="claude-codeintel",
        duration_ms=8_000,
        files=[
            "src/payment.py",
            "src/api.py",
        ],
        files_read=[
            "src/payment.py",
            "src/api.py",
        ],
        input_tokens=750,
        output_tokens=150,
    )

    comparison = compare_pair(
        baseline,
        enhanced,
        task(),
    )

    assert comparison.duration_reduction_pct == pytest.approx(
        20.0
    )

    assert comparison.input_token_reduction_pct == pytest.approx(
        25.0
    )

    assert comparison.total_token_reduction_pct == pytest.approx(
        25.0
    )

    assert comparison.files_read_reduction_pct == pytest.approx(
        50.0
    )

    assert comparison.file_precision_delta == pytest.approx(
        0.5
    )

    assert comparison.file_recall_delta == pytest.approx(
        0.5
    )


def test_compare_pair_requires_same_task():
    baseline = result(
        runner="claude",
    )

    enhanced = result(
        runner="claude-codeintel",
    )

    enhanced = BenchmarkResult(
        runner=enhanced.runner,
        task_id="different-task",
        success=enhanced.success,
        duration_ms=enhanced.duration_ms,
        files=enhanced.files,
        symbols=enhanced.symbols,
        tool_calls=enhanced.tool_calls,
        tokens=enhanced.tokens,
        stdout=enhanced.stdout,
        stderr=enhanced.stderr,
        exit_code=enhanced.exit_code,
        metadata=enhanced.metadata,
    )

    with pytest.raises(
        ValueError,
        match="same task",
    ):
        compare_pair(
            baseline,
            enhanced,
            task(),
        )


def test_estimated_cost_uses_user_supplied_pricing():
    pricing = Pricing(
        input_per_million=3.0,
        output_per_million=15.0,
    )

    assert estimated_cost(
        TokenUsage(
            input=1_000_000,
            output=1_000_000,
        ),
        pricing,
    ) == pytest.approx(18.0)


def test_estimated_cost_missing_usage_is_null():
    pricing = Pricing(
        input_per_million=3.0,
        output_per_million=15.0,
    )

    assert estimated_cost(
        TokenUsage(
            input=None,
            output=10,
        ),
        pricing,
    ) is None


def test_compare_pair_cost_is_optional():
    comparison = compare_pair(
        result(
            runner="claude",
        ),
        result(
            runner="claude-codeintel",
        ),
        task(),
    )

    assert comparison.baseline_cost_usd is None
    assert comparison.enhanced_cost_usd is None
    assert comparison.cost_reduction_pct is None
