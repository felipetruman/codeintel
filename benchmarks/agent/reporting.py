from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any
import csv
import json

from benchmarks.agent.models import (
    BenchmarkResult,
)


@dataclass(frozen=True)
class RunMetadata:
    run_id: str
    timestamp: str
    codeintel_version: str | None
    git_sha: str | None
    python_version: str
    platform: str
    architecture: str
    claude_version: str | None
    codex_version: str | None
    seed: int
    runners: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "codeintel_version": self.codeintel_version,
            "git_sha": self.git_sha,
            "python_version": self.python_version,
            "platform": self.platform,
            "architecture": self.architecture,
            "claude_version": self.claude_version,
            "codex_version": self.codex_version,
            "seed": self.seed,
            "runners": list(self.runners),
        }


def _round(
    value: float,
) -> float:
    return round(
        value,
        6,
    )


def _score_values(entries: list[BenchmarkResult]) -> dict[str, list[float]]:
    values = {}
    for result in entries:
        scores = result.metadata.get("scores", {})
        if isinstance(scores, dict):
            _collect_scores(values, scores)
    return values


def _collect_scores(values: dict, scores: dict) -> None:
    for key, value in scores.items():
        values.setdefault(key, [])
        if type(value) in (int, float):
            values[key].append(float(value))


def _runner_summary(entries: list[BenchmarkResult]) -> dict:
    values = _score_values(entries)
    successes = sum(result.success for result in entries)
    return {
        "runs": len(entries),
        "successes": successes,
        "success_rate": _round(successes / len(entries)),
        "avg_duration_ms": _round(mean(result.duration_ms for result in entries)),
        "metrics": {
            key: _round(mean(items)) if items else None
            for key, items in sorted(values.items())
        },
    }


def summarize(results: list[BenchmarkResult]) -> dict[str, Any]:
    grouped = {}
    for result in results:
        grouped.setdefault(result.runner, []).append(result)
    return {
        "total_results": len(results),
        "runners": {
            name: _runner_summary(entries) for name, entries in sorted(grouped.items())
        },
    }


def _write_json(
    path: Path,
    payload: Any,
) -> None:
    path.write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _csv_rows(
    summary: dict[str, Any],
) -> tuple[list[str], list[dict[str, Any]]]:
    runners = summary.get(
        "runners",
        {},
    )

    metric_names = sorted(
        {metric for data in runners.values() for metric in data.get("metrics", {})}
    )

    fields = [
        "runner",
        "runs",
        "successes",
        "success_rate",
        "avg_duration_ms",
        *metric_names,
    ]

    rows = []

    for runner in sorted(runners):
        data = runners[runner]

        row: dict[str, Any] = {
            "runner": runner,
            "runs": data["runs"],
            "successes": data["successes"],
            "success_rate": data["success_rate"],
            "avg_duration_ms": data["avg_duration_ms"],
        }

        metrics = data.get(
            "metrics",
            {},
        )

        for metric in metric_names:
            row[metric] = metrics.get(
                metric,
                "",
            )

        rows.append(row)

    return fields, rows


def write_run(
    output_dir: Path,
    metadata: RunMetadata,
    results: list[BenchmarkResult],
) -> dict[str, Path]:
    output_dir = Path(output_dir)

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    run_path = output_dir / "run.json"
    results_path = output_dir / "results.jsonl"
    summary_path = output_dir / "summary.json"
    csv_path = output_dir / "summary.csv"

    _write_json(
        run_path,
        metadata.to_dict(),
    )

    with results_path.open(
        "w",
        encoding="utf-8",
    ) as handle:
        for result in results:
            handle.write(
                json.dumps(
                    result.to_dict(),
                    sort_keys=True,
                    ensure_ascii=False,
                )
            )
            handle.write("\n")

    summary = summarize(results)

    _write_json(
        summary_path,
        summary,
    )

    fields, rows = _csv_rows(summary)

    with csv_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
        )

        writer.writeheader()
        writer.writerows(rows)

    return {
        "run": run_path,
        "results": results_path,
        "summary": summary_path,
        "csv": csv_path,
    }
