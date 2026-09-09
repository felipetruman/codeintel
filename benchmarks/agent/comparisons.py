from dataclasses import asdict
from itertools import product
from pathlib import Path
from typing import Any
import csv
import json

from benchmarks.agent.agent_metrics import compare_pair
from benchmarks.agent.manifests import BenchmarkTask
from benchmarks.agent.models import BenchmarkResult
from benchmarks.agent.runner_matrix import ab_pairs

FIELDS = [
    "task_id",
    "repeat",
    "baseline_runner",
    "enhanced_runner",
    "success_delta",
    "duration_reduction_pct",
    "files_read_reduction_pct",
    "input_token_reduction_pct",
    "output_token_reduction_pct",
    "total_token_reduction_pct",
    "file_precision_delta",
    "file_recall_delta",
    "tool_call_reduction_pct",
]


def _group_results(results: list[BenchmarkResult]) -> dict:
    grouped = {}
    for result in results:
        repetition = result.metadata.get("repeat")
        if type(repetition) is not int:
            continue
        key = (result.task_id, repetition, result.runner)
        if key in grouped:
            raise ValueError(f"duplicate comparison result: {key}")
        grouped[key] = result
    return grouped


def _comparison_row(task, repetition, pair, grouped) -> dict | None:
    baseline = grouped.get((task.id, repetition, pair[0]))
    enhanced = grouped.get((task.id, repetition, pair[1]))
    if baseline is None or enhanced is None:
        return None
    row = asdict(compare_pair(baseline, enhanced, task))
    row["repeat"] = repetition
    return row


def write_comparisons(
    output: Path,
    tasks: list[BenchmarkTask],
    results: list[BenchmarkResult],
    runner_names: list[str],
) -> list[dict[str, Any]]:
    grouped = _group_results(results)
    repeats = sorted({key[1] for key in grouped})
    combinations = product(tasks, repeats, ab_pairs(runner_names))
    rows = [
        row
        for task, repetition, pair in combinations
        if (row := _comparison_row(task, repetition, pair, grouped)) is not None
    ]
    output.mkdir(parents=True, exist_ok=True)
    (output / "comparisons.json").write_text(
        json.dumps(rows, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    with (output / "comparisons.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return rows
