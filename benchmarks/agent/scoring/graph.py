from __future__ import annotations

from collections.abc import Sequence

from benchmarks.agent.scoring.retrieval import (
    precision,
    recall,
)


def graph_metrics(
    direct_callers: Sequence[str],
    expected_callers: Sequence[str],
    blast_radius: int | None,
    expected_blast_radius: int | None,
) -> dict[str, float | int | None]:
    error: int | None = None

    if blast_radius is not None and expected_blast_radius is not None:
        error = abs(blast_radius - expected_blast_radius)

    return {
        "direct_caller_precision": precision(
            direct_callers,
            expected_callers,
        ),
        "direct_caller_recall": recall(
            direct_callers,
            expected_callers,
        ),
        "blast_radius_error": error,
    }
