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
        raise ValueError(
            "repeat must be greater than zero"
        )

    if not runners:
        raise ValueError(
            "at least one runner is required"
        )

    result: list[str] = []

    for repetition in range(repeat):
        offset = (
            repetition
            % len(runners)
        )

        rotated = (
            runners[offset:]
            + runners[:offset]
        )

        result.extend(rotated)

    return result


def score_result(
    task: BenchmarkTask,
    result: BenchmarkResult,
) -> BenchmarkResult:
    file_precision = precision(
        result.files,
        task.expected.files,
    )

    file_recall = recall(
        result.files,
        task.expected.files,
    )

    scores: dict[
        str,
        float | int | None,
    ] = {
        "file_precision": file_precision,
        "file_recall": file_recall,
        "file_f1": f1(
            file_precision,
            file_recall,
        ),
        "file_precision_at_5": precision_at_k(
            result.files,
            task.expected.files,
            5,
        ),
        "file_recall_at_5": recall_at_k(
            result.files,
            task.expected.files,
            5,
        ),
        "file_mrr": reciprocal_rank(
            result.files,
            task.expected.files,
        ),
    }

    if (
        task.type == "impact-analysis"
        or task.expected.direct_callers
        or task.expected.blast_radius
        is not None
    ):
        raw_callers = result.metadata.get(
            "direct_callers",
            [],
        )

        direct_callers = (
            [
                value
                for value in raw_callers
                if isinstance(
                    value,
                    str,
                )
            ]
            if isinstance(
                raw_callers,
                list,
            )
            else []
        )

        raw_radius = result.metadata.get(
            "blast_radius"
        )

        blast_radius = (
            raw_radius
            if isinstance(
                raw_radius,
                int,
            )
            and not isinstance(
                raw_radius,
                bool,
            )
            else None
        )

        scores.update(
            graph_metrics(
                direct_callers,
                task.expected.direct_callers,
                blast_radius,
                task.expected.blast_radius,
            )
        )

    result.metadata[
        "scores"
    ] = scores

    return result


def run_matrix(
    tasks: list[BenchmarkTask],
    runners: Mapping[str, object],
    source_resolver,
    repeat: int,
) -> list[BenchmarkResult]:
    runner_names = list(
        runners.keys()
    )

    ordering = balanced_order(
        runner_names,
        repeat,
    )

    results: list[BenchmarkResult] = []

    for task in tasks:
        source = Path(
            source_resolver(task)
        ).resolve()

        for sequence_index, runner_name in enumerate(
            ordering
        ):
            runner = runners[
                runner_name
            ]

            with isolated_repository(
                source
            ) as repository:
                result = runner.run(
                    task,
                    repository,
                )

            result.metadata[
                "sequence_index"
            ] = sequence_index

            result.metadata[
                "repeat_index"
            ] = (
                sequence_index
                // len(runner_names)
            )

            results.append(
                score_result(
                    task,
                    result,
                )
            )

    return results
