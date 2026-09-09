import pytest

from benchmarks.agent.isolation import isolated_repository, repository_digest
from benchmarks.agent.manifests import BenchmarkTask, GroundTruth
from benchmarks.agent.models import TokenUsage
from benchmarks.agent.process import ProcessResult
from benchmarks.agent.runners import claude, codex
from benchmarks.agent.runners.agent_base import AgentCommand, render_command


@pytest.mark.parametrize("usage", [TokenUsage(input=5), TokenUsage(output=5)])
def test_partial_token_total_is_unknown(usage):
    assert usage.total is None


def test_isolation_rejects_external_symlink(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    outside = tmp_path / "outside"
    outside.write_text("protected")
    (source / "escape").symlink_to(outside)
    with pytest.raises(ValueError, match="symlink"):
        with isolated_repository(source):
            pytest.fail("unsafe snapshot accepted")
    assert outside.read_text() == "protected"


def test_isolation_rebases_absolute_internal_link(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    target = source / "target"
    target.write_text("original")
    (source / "link").symlink_to(target)
    with isolated_repository(source) as isolated:
        (isolated / "link").write_text("snapshot")
    assert target.read_text() == "original"


def test_digest_tracks_directory_links(tmp_path):
    (tmp_path / "one").mkdir()
    (tmp_path / "two").mkdir()
    link = tmp_path / "link"
    link.symlink_to("one", target_is_directory=True)
    before = repository_digest(tmp_path)
    link.unlink()
    link.symlink_to("two", target_is_directory=True)
    assert repository_digest(tmp_path) != before


@pytest.mark.parametrize(
    "module,runner", [(claude, claude.ClaudeRunner), (codex, codex.CodexRunner)]
)
@pytest.mark.parametrize("stdout", ["", "garbage", "{}", "[]"])
def test_agent_requires_valid_completed_output(
    tmp_path, monkeypatch, module, runner, stdout
):
    process = ProcessResult([], stdout, "", 0, 1.0, False)
    monkeypatch.setattr(module, "run_process", lambda *a, **k: process)
    task = BenchmarkTask(
        "test", "relevant-files", "query", "prompt", "synthetic", GroundTruth()
    )
    result = runner(False).run(task, tmp_path)
    assert result.success is False
    assert result.stdout == result.stderr == ""


def test_prompt_placeholder_is_not_recursively_substituted(tmp_path):
    command = AgentCommand("fake", ("agent", "{prompt}"), 1, False)
    assert render_command(command, "literal {repo}", tmp_path)[-1] == "literal {repo}"


def test_process_kills_detached_stdio_child_on_normal_exit(tmp_path):
    import sys
    import time
    from benchmarks.agent.process import run_process

    marker = tmp_path / "survivor"
    child = (
        f"import time,pathlib; time.sleep(0.3); pathlib.Path({str(marker)!r}).touch()"
    )
    parent = f"import subprocess,sys; subprocess.Popen([sys.executable,'-c',{child!r}], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)"
    run_process([sys.executable, "-c", parent], tmp_path, 2)
    time.sleep(0.5)
    assert not marker.exists()


def test_process_bounds_output(tmp_path):
    import sys
    from benchmarks.agent.process import run_process

    result = run_process(
        [sys.executable, "-c", "import sys; sys.stdout.write('x'*100000)"],
        tmp_path,
        2,
        max_output_bytes=1024,
    )
    assert result.output_limited
    assert result.exit_code is None
    assert len(result.stdout.encode()) <= 1024


def test_synthetic_source_cannot_escape_corpus(tmp_path):
    from benchmarks.agent.full_matrix import _task_source

    task = BenchmarkTask(
        "test", "relevant-files", "q", "p", str(tmp_path), GroundTruth()
    )
    with pytest.raises(ValueError, match="corpus"):
        _task_source(task, synthetic=True, repo=None)


def test_ab_pairs_reverse_within_two_full_matrix_repetitions():
    from benchmarks.agent.runner_matrix import (
        ALL_RUNNERS,
        ab_pairs,
        balanced_runner_order,
    )

    first = balanced_runner_order(list(ALL_RUNNERS), 0, 0)
    second = balanced_runner_order(list(ALL_RUNNERS), 1, 0)
    for baseline, enhanced in ab_pairs(list(ALL_RUNNERS)):
        assert (first.index(baseline) < first.index(enhanced)) != (
            second.index(baseline) < second.index(enhanced)
        )


def test_generic_failure_does_not_persist_stream(tmp_path):
    import sys
    from benchmarks.agent.runners.agent_base import GenericAgentRunner

    command = AgentCommand(
        "fake",
        (sys.executable, "-c", "print('sensitive raw text')", "{prompt}"),
        1,
        False,
    )
    task = BenchmarkTask("test", "relevant-files", "q", "p", "synthetic", GroundTruth())
    result = GenericAgentRunner(command).run(task, tmp_path)
    assert not result.success
    assert result.stdout == result.stderr == ""


def test_rg_query_is_literal_and_not_an_option(tmp_path):
    from benchmarks.agent.runners.rg import RgRunner

    (tmp_path / "file.txt").write_text("--hidden [literal]")
    task = BenchmarkTask(
        "test", "locate-symbol", "--hidden [literal]", "p", "synthetic", GroundTruth()
    )
    result = RgRunner().run(task, tmp_path)
    assert result.success
    assert result.files == ["file.txt"]
