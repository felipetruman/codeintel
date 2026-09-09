from __future__ import annotations

from dataclasses import dataclass, fields, replace
import math
from benchmarks.agent.scoring.retrieval import precision, recall

from benchmarks.agent.manifests import (
    BenchmarkTask,
)
from benchmarks.agent.models import (
    BenchmarkResult,
    TokenUsage,
)


@dataclass(frozen=True)
class Pricing:
    input_per_million: float
    output_per_million: float


@dataclass(frozen=True)
class AgentMetrics:
    success: bool
    duration_ms: float

    files_read: int | None
    relevant_files_read: int | None
    irrelevant_files_read: int | None

    file_precision: float
    file_recall: float

    tool_calls: int | None

    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None


@dataclass(frozen=True)
class PairComparison:
    task_id: str

    baseline_runner: str
    enhanced_runner: str

    baseline: AgentMetrics
    enhanced: AgentMetrics

    success_delta: int

    duration_reduction_pct: float | None
    files_read_reduction_pct: float | None

    input_token_reduction_pct: float | None
    output_token_reduction_pct: float | None
    total_token_reduction_pct: float | None

    file_precision_delta: float | None
    file_recall_delta: float | None

    tool_call_reduction_pct: float | None

    baseline_cost_usd: float | None
    enhanced_cost_usd: float | None
    cost_reduction_pct: float | None


def percent_reduction(
    baseline: float | int | None, enhanced: float | int | None
) -> float | None:
    if baseline is None or enhanced is None:
        return None
    if not math.isfinite(baseline) or not math.isfinite(enhanced):
        return None
    if baseline <= 0 or enhanced < 0:
        return None
    return (baseline - enhanced) / baseline * 100.0


def _file_quality(
    returned: list[str], expected: tuple[str, ...]
) -> tuple[float, float]:
    return precision(returned, expected), recall(returned, expected)


def _files_read(
    result: BenchmarkResult,
) -> list[str] | None:
    value = result.metadata.get("files_read")

    if value is None:
        return None

    if not isinstance(
        value,
        list,
    ):
        return None

    return [
        item
        for item in value
        if isinstance(
            item,
            str,
        )
    ]


def agent_metrics(
    result: BenchmarkResult,
    task: BenchmarkTask,
) -> AgentMetrics:
    expected_files = task.expected.files

    precision, recall = _file_quality(
        result.files,
        expected_files,
    )

    read_files = _files_read(result)

    files_read_count = None
    relevant_read = None
    irrelevant_read = None

    if read_files is not None:
        unique_read = set(read_files)

        expected_set = set(expected_files)

        files_read_count = len(unique_read)

        relevant_read = len(unique_read & expected_set)

        irrelevant_read = files_read_count - relevant_read

    return AgentMetrics(
        success=result.success,
        duration_ms=result.duration_ms,
        files_read=files_read_count,
        relevant_files_read=(relevant_read),
        irrelevant_files_read=(irrelevant_read),
        file_precision=precision,
        file_recall=recall,
        tool_calls=(
            len(result.tool_calls)
            if result.metadata.get("tool_calls_observed", True)
            else None
        ),
        input_tokens=(result.tokens.input),
        output_tokens=(result.tokens.output),
        total_tokens=(result.tokens.total),
    )


def estimated_cost(
    usage: TokenUsage,
    pricing: Pricing | None,
) -> float | None:
    if pricing is None:
        return None

    if usage.input is None or usage.output is None:
        return None

    return (usage.input / 1_000_000) * pricing.input_per_million + (
        usage.output / 1_000_000
    ) * pricing.output_per_million


def compare_pair(
    baseline: BenchmarkResult,
    enhanced: BenchmarkResult,
    task: BenchmarkTask,
    pricing: Pricing | None = None,
) -> PairComparison:
    if baseline.task_id != enhanced.task_id or baseline.task_id != task.id:
        raise ValueError("A/B results must reference the same task")
    bm, em = agent_metrics(baseline, task), agent_metrics(enhanced, task)
    bc, ec = estimated_cost(baseline.tokens, pricing), estimated_cost(
        enhanced.tokens, pricing
    )
    comparison = PairComparison(
        task_id=task.id,
        baseline_runner=baseline.runner,
        enhanced_runner=enhanced.runner,
        baseline=bm,
        enhanced=em,
        success_delta=int(enhanced.success) - int(baseline.success),
        duration_reduction_pct=percent_reduction(bm.duration_ms, em.duration_ms),
        files_read_reduction_pct=percent_reduction(bm.files_read, em.files_read),
        input_token_reduction_pct=percent_reduction(bm.input_tokens, em.input_tokens),
        output_token_reduction_pct=percent_reduction(
            bm.output_tokens, em.output_tokens
        ),
        total_token_reduction_pct=percent_reduction(bm.total_tokens, em.total_tokens),
        file_precision_delta=em.file_precision - bm.file_precision,
        file_recall_delta=em.file_recall - bm.file_recall,
        tool_call_reduction_pct=percent_reduction(bm.tool_calls, em.tool_calls),
        baseline_cost_usd=bc,
        enhanced_cost_usd=ec,
        cost_reduction_pct=percent_reduction(bc, ec),
    )

    if baseline.success and enhanced.success:
        return comparison
    unavailable = {
        field.name: None
        for field in fields(PairComparison)
        if field.name.endswith("_reduction_pct")
    }
    return replace(
        comparison, file_precision_delta=None, file_recall_delta=None, **unavailable
    )
