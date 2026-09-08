from __future__ import annotations

import csv
import importlib
import json
from pathlib import Path

from benchmarks.agent.models import (
    BenchmarkResult,
    TokenUsage,
)


def reporting_module():
    try:
        return importlib.import_module(
            "benchmarks.agent.reporting"
        )
    except ModuleNotFoundError as error:
        raise AssertionError(
            "benchmark reporting is not implemented"
        ) from error


def make_results():
    return [
        BenchmarkResult(
            runner="rg",
            task_id="t1",
            success=True,
            duration_ms=10.0,
            files=["a.py"],
            tokens=TokenUsage(),
            metadata={
                "scores": {
                    "file_precision": 1.0,
                    "file_recall": 0.5,
                }
            },
        ),
        BenchmarkResult(
            runner="rg",
            task_id="t2",
            success=False,
            duration_ms=30.0,
            files=[],
            tokens=TokenUsage(),
            metadata={
                "scores": {
                    "file_precision": 0.0,
                    "file_recall": 0.0,
                }
            },
        ),
        BenchmarkResult(
            runner="codeintel",
            task_id="t1",
            success=True,
            duration_ms=20.0,
            files=["a.py", "b.py"],
            tokens=TokenUsage(
                input=None,
                output=None,
            ),
            metadata={
                "scores": {
                    "file_precision": 1.0,
                    "file_recall": 1.0,
                }
            },
        ),
    ]


def test_summarize_groups_by_runner():
    module = reporting_module()

    summary = module.summarize(
        make_results()
    )

    assert summary["total_results"] == 3

    assert summary["runners"]["rg"][
        "runs"
    ] == 2

    assert summary["runners"]["rg"][
        "successes"
    ] == 1

    assert summary["runners"]["rg"][
        "success_rate"
    ] == 0.5

    assert summary["runners"]["rg"][
        "avg_duration_ms"
    ] == 20.0

    assert summary["runners"]["rg"][
        "metrics"
    ][
        "file_precision"
    ] == 0.5


def test_write_run_creates_all_machine_readable_outputs(
    tmp_path: Path,
):
    module = reporting_module()

    metadata = module.RunMetadata(
        run_id="run-test",
        timestamp="2026-09-08T00:00:00+00:00",
        codeintel_version="0.5.0",
        git_sha="abc123",
        python_version="3.14.6",
        platform="Linux",
        architecture="x86_64",
        claude_version=None,
        codex_version=None,
        seed=1337,
        runners=("rg", "codeintel"),
    )

    paths = module.write_run(
        tmp_path,
        metadata,
        make_results(),
    )

    assert set(paths) == {
        "run",
        "results",
        "summary",
        "csv",
    }

    run = json.loads(
        (tmp_path / "run.json").read_text(
            encoding="utf-8"
        )
    )

    assert run["run_id"] == "run-test"
    assert run["runners"] == [
        "rg",
        "codeintel",
    ]

    lines = (
        tmp_path / "results.jsonl"
    ).read_text(
        encoding="utf-8"
    ).splitlines()

    assert len(lines) == 3

    payload = json.loads(lines[2])

    assert payload["tokens"] == {
        "input": None,
        "output": None,
        "total": None,
    }

    summary = json.loads(
        (
            tmp_path / "summary.json"
        ).read_text(
            encoding="utf-8"
        )
    )

    assert summary["total_results"] == 3

    with (
        tmp_path / "summary.csv"
    ).open(
        newline="",
        encoding="utf-8",
    ) as handle:
        rows = list(
            csv.DictReader(handle)
        )

    assert {
        row["runner"]
        for row in rows
    } == {
        "rg",
        "codeintel",
    }


def test_json_output_is_deterministic(
    tmp_path: Path,
):
    module = reporting_module()

    metadata = module.RunMetadata(
        run_id="stable",
        timestamp="stable",
        codeintel_version=None,
        git_sha=None,
        python_version="3",
        platform="Linux",
        architecture="x86_64",
        claude_version=None,
        codex_version=None,
        seed=1,
        runners=("rg",),
    )

    first = tmp_path / "first"
    second = tmp_path / "second"

    module.write_run(
        first,
        metadata,
        make_results(),
    )

    module.write_run(
        second,
        metadata,
        make_results(),
    )

    for filename in [
        "run.json",
        "results.jsonl",
        "summary.json",
        "summary.csv",
    ]:
        assert (
            first / filename
        ).read_bytes() == (
            second / filename
        ).read_bytes()
