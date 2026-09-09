from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from benchmarks.agent.isolation import (
    isolated_repository,
)
from benchmarks.agent.manifests import (
    BenchmarkTask,
)
from benchmarks.agent.models import (
    BenchmarkResult,
)
from benchmarks.agent.scoring.graph import (
    graph_metrics,
)
from benchmarks.agent.scoring.retrieval import (
    f1,
    precision,
    precision_at_k,
    recall,
    recall_at_k,
    reciprocal_rank,
)


def balanced_order(
    runners: list[str],
    repeat: int,
) -> list[str]:
    if repeat <= 0:
        raise ValueError("repeat must be greater than zero")

    if not runners:
        raise ValueError("at least one runner is required")

    result: list[str] = []

    for repetition in range(repeat):
        offset = repetition % len(runners)

        rotated = runners[offset:] + runners[:offset]

        result.extend(rotated)

    return result


def _file_scores(task: BenchmarkTask, result: BenchmarkResult) -> dict:
    p = precision(result.files, task.expected.files)
    r = recall(result.files, task.expected.files)
    return {
        "file_precision": p,
        "file_recall": r,
        "file_f1": f1(p, r),
        "file_precision_at_5": precision_at_k(result.files, task.expected.files, 5),
        "file_recall_at_5": recall_at_k(result.files, task.expected.files, 5),
        "file_mrr": reciprocal_rank(result.files, task.expected.files),
    }


def _needs_graph(task: BenchmarkTask) -> bool:
    if task.type == "impact-analysis":
        return True
    return bool(task.expected.direct_callers) or task.expected.blast_radius is not None


def _graph_scores(task: BenchmarkTask, result: BenchmarkResult) -> dict:
    callers = result.metadata.get("direct_callers")
    radius = result.metadata.get("blast_radius")
    if type(radius) is not int:
        radius = None
    if not isinstance(callers, list):
        return {
            "direct_caller_precision": None,
            "direct_caller_recall": None,
            "blast_radius_error": None,
        }
    return graph_metrics(
        callers, task.expected.direct_callers, radius, task.expected.blast_radius
    )


def score_result(task: BenchmarkTask, result: BenchmarkResult) -> BenchmarkResult:
    scores = _file_scores(task, result)
    if _needs_graph(task):
        scores.update(_graph_scores(task, result))
    if not result.success:
        scores = dict.fromkeys(scores)
    result.metadata["scores"] = scores
    return result


def run_matrix(
    tasks: list[BenchmarkTask],
    runners: Mapping[str, object],
    source_resolver,
    repeat: int,
) -> list[BenchmarkResult]:
    runner_names = list(runners.keys())

    ordering = balanced_order(
        runner_names,
        repeat,
    )

    results: list[BenchmarkResult] = []

    for task in tasks:
        source = Path(source_resolver(task)).resolve()

        for sequence_index, runner_name in enumerate(ordering):
            runner = runners[runner_name]

            with isolated_repository(source) as repository:
                result = runner.run(
                    task,
                    repository,
                )

            result.metadata["sequence_index"] = sequence_index

            result.metadata["repeat_index"] = sequence_index // len(runner_names)

            results.append(
                score_result(
                    task,
                    result,
                )
            )

    return results
