from pathlib import Path
import shutil

from benchmarks.agent.manifests import load_task
from benchmarks.agent.runners.codeintel import (
    CodeIntelRunner,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
AGENT_ROOT = Path(__file__).resolve().parents[1]
CODEINTEL = (
    REPO_ROOT
    / "target"
    / "debug"
    / "codeintel"
)


def fixture_copy(tmp_path):
    source = (
        AGENT_ROOT
        / "corpus"
        / "synthetic"
        / "rust-cross-file"
    )

    repo = tmp_path / "repo"

    shutil.copytree(
        source,
        repo,
    )

    return repo


def runner():
    assert CODEINTEL.is_file()

    return CodeIntelRunner(
        binary=str(CODEINTEL),
        mode="warm",
        timeout_seconds=30,
    )


def test_codeintel_runner_supports_all_operations(
    tmp_path,
):
    repo = fixture_copy(tmp_path)
    subject = runner()

    search = subject.run_operation(
        operation="search",
        text="process_payment",
        repo=repo,
        task_id="search",
    )

    assert search.success is True
    assert "src/payment.rs" in search.files
    assert "src/checkout.rs" in search.files

    context = subject.run_operation(
        operation="context",
        text="process_payment checkout",
        repo=repo,
        task_id="context",
    )

    assert context.success is True
    assert "src/payment.rs" in context.files
    assert "src/checkout.rs" in context.files

    symbol = subject.run_operation(
        operation="symbol",
        text="process_payment",
        repo=repo,
        task_id="symbol",
    )

    assert symbol.success is True
    assert "process_payment" in symbol.symbols
    assert "checkout" in symbol.symbols

    impact = subject.run_operation(
        operation="impact",
        text="process_payment",
        repo=repo,
        task_id="impact",
    )

    assert impact.success is True

    assert impact.metadata[
        "direct_callers"
    ] == ["checkout"]

    assert impact.metadata[
        "impacted"
    ] == [
        "checkout",
        "submit_order",
    ]

    assert impact.metadata[
        "blast_radius"
    ] == 2


def test_codeintel_runner_maps_impact_task(
    tmp_path,
):
    repo = fixture_copy(tmp_path)

    task = load_task(
        AGENT_ROOT
        / "tasks"
        / "impact-analysis.yaml"
    )

    result = runner().run(
        task,
        repo,
    )

    assert result.success is True
    assert result.metadata[
        "operation"
    ] == "impact"
    assert result.metadata[
        "direct_callers"
    ] == ["checkout"]
