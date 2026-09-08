from pathlib import Path

import pytest

from benchmarks.agent.manifests import (
    BenchmarkTask,
    GroundTruth,
    load_task,
    load_tasks,
)


def write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "task.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def test_load_task_accepts_supported_manifest(tmp_path):
    path = write(
        tmp_path,
        """
id: payment-impact
type: impact-analysis
query: process_payment
prompt: Find callers of process_payment.
corpus: synthetic/rust-cross-file
expected:
  files:
    - src/payment.rs
    - src/checkout.rs
  symbols:
    - process_payment
  direct_callers:
    - checkout
  impacted:
    - checkout
    - submit_order
  blast_radius: 2
""",
    )

    task = load_task(path)

    assert task == BenchmarkTask(
        id="payment-impact",
        type="impact-analysis",
        query="process_payment",
        prompt="Find callers of process_payment.",
        corpus="synthetic/rust-cross-file",
        expected=GroundTruth(
            files=("src/payment.rs", "src/checkout.rs"),
            symbols=("process_payment",),
            direct_callers=("checkout",),
            impacted=("checkout", "submit_order"),
            blast_radius=2,
        ),
    )


@pytest.mark.parametrize(
    "task_type",
    [
        "locate-symbol",
        "relevant-files",
        "impact-analysis",
        "change-planning",
    ],
)
def test_supported_task_types(tmp_path, task_type):
    path = write(
        tmp_path,
        f"""
id: task
type: {task_type}
query: payment
prompt: Analyze payment.
corpus: synthetic/rust-cross-file
expected: {{}}
""",
    )

    assert load_task(path).type == task_type


def test_rejects_unsupported_task_type(tmp_path):
    path = write(
        tmp_path,
        """
id: dangerous
type: shell-command
query: x
prompt: x
corpus: synthetic/rust-cross-file
expected: {}
command: rm -rf /
""",
    )

    with pytest.raises(ValueError):
        load_task(path)


def test_rejects_unknown_top_level_fields(tmp_path):
    path = write(
        tmp_path,
        """
id: x
type: locate-symbol
query: x
prompt: x
corpus: synthetic/rust-cross-file
expected: {}
surprise: true
""",
    )

    with pytest.raises(ValueError, match="unknown"):
        load_task(path)


def test_rejects_unknown_expected_fields(tmp_path):
    path = write(
        tmp_path,
        """
id: x
type: locate-symbol
query: x
prompt: x
corpus: synthetic/rust-cross-file
expected:
  files: []
  magic_score: 99
""",
    )

    with pytest.raises(ValueError, match="unknown"):
        load_task(path)


def test_load_tasks_is_sorted(tmp_path):
    for name in ["z.yaml", "a.yaml"]:
        (tmp_path / name).write_text(
            f"""
id: {name}
type: locate-symbol
query: x
prompt: x
corpus: synthetic/rust-cross-file
expected: {{}}
""",
            encoding="utf-8",
        )

    tasks = load_tasks(tmp_path)

    assert [task.id for task in tasks] == [
        "a.yaml",
        "z.yaml",
    ]


def test_repository_manifests_are_valid():
    root = (
        Path(__file__).resolve().parents[1]
    )

    tasks = load_tasks(root / "tasks")

    assert len(tasks) == 4
    assert {
        task.type for task in tasks
    } == {
        "locate-symbol",
        "relevant-files",
        "impact-analysis",
        "change-planning",
    }

    for task in tasks:
        corpus = root / "corpus" / task.corpus
        assert corpus.is_dir()
