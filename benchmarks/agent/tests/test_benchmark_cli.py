from __future__ import annotations

import importlib
import json
from pathlib import Path


AGENT_ROOT = (
    Path(__file__).resolve().parents[1]
)


def benchmark_module():
    try:
        return importlib.import_module(
            "benchmarks.agent.benchmark"
        )
    except ModuleNotFoundError as error:
        raise AssertionError(
            "benchmark CLI is not implemented"
        ) from error


def test_cli_requires_exactly_one_source_mode():
    module = benchmark_module()

    parser = module.build_parser()

    for argv in [
        [],
        [
            "--corpus",
            "synthetic",
            "--repo",
            ".",
        ],
    ]:
        try:
            parser.parse_args(argv)
        except SystemExit:
            pass
        else:
            raise AssertionError(
                "source mode must be mutually exclusive"
            )


def test_rg_synthetic_cli_smoke(
    tmp_path: Path,
):
    module = benchmark_module()

    output = tmp_path / "results"

    exit_code = module.main(
        [
            "--corpus",
            "synthetic",
            "--tasks",
            str(
                AGENT_ROOT
                / "tasks"
                / "locate-symbol.yaml"
            ),
            "--runner",
            "rg",
            "--repeat",
            "1",
            "--seed",
            "1337",
            "--timeout",
            "10",
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0

    for filename in [
        "run.json",
        "results.jsonl",
        "summary.json",
        "summary.csv",
    ]:
        assert (
            output / filename
        ).is_file()

    lines = (
        output / "results.jsonl"
    ).read_text(
        encoding="utf-8"
    ).splitlines()

    assert len(lines) == 1

    result = json.loads(
        lines[0]
    )

    assert result["runner"] == "rg"
    assert result["success"] is True

    scores = result[
        "metadata"
    ][
        "scores"
    ]

    assert scores[
        "file_recall"
    ] == 1.0


def test_all_selects_deterministic_runners():
    module = benchmark_module()

    assert module.resolve_runners(
        explicit=[],
        all_runners=True,
    ) == [
        "rg",
        "codeintel",
    ]


def test_repeated_runner_names_are_deduplicated():
    module = benchmark_module()

    assert module.resolve_runners(
        explicit=[
            "rg",
            "rg",
            "codeintel",
        ],
        all_runners=False,
    ) == [
        "rg",
        "codeintel",
    ]
