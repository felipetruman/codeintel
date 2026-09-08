from pathlib import Path
import shutil

from benchmarks.agent.manifests import load_task
from benchmarks.agent.runners.rg import RgRunner


AGENT_ROOT = Path(__file__).resolve().parents[1]


def test_rg_runner_finds_process_payment_files(tmp_path):
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

    task = load_task(
        AGENT_ROOT
        / "tasks"
        / "locate-symbol.yaml"
    )

    result = RgRunner().run(
        task,
        repo,
    )

    assert result.success is True
    assert result.exit_code == 0

    assert "src/payment.rs" in result.files
    assert "src/checkout.rs" in result.files

    assert result.metadata[
        "operation"
    ] == "search"

    assert result.metadata[
        "candidate_count"
    ] >= 2
