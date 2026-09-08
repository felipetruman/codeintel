import sys

from benchmarks.agent.process import run_process


def test_process_captures_stdout_and_exit_code(tmp_path):
    result = run_process(
        [
            sys.executable,
            "-c",
            "print('hello-benchmark')",
        ],
        cwd=tmp_path,
        timeout_seconds=5,
    )

    assert result.timed_out is False
    assert result.exit_code == 0
    assert result.stdout.strip() == "hello-benchmark"
    assert result.stderr == ""
    assert result.duration_ms >= 0


def test_process_preserves_nonzero_exit_code(tmp_path):
    result = run_process(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "print('boom', file=sys.stderr); "
                "raise SystemExit(7)"
            ),
        ],
        cwd=tmp_path,
        timeout_seconds=5,
    )

    assert result.timed_out is False
    assert result.exit_code == 7
    assert "boom" in result.stderr


def test_process_timeout_terminates_child(tmp_path):
    result = run_process(
        [
            sys.executable,
            "-c",
            "import time; time.sleep(30)",
        ],
        cwd=tmp_path,
        timeout_seconds=0.1,
    )

    assert result.timed_out is True
    assert result.exit_code is None
    assert result.duration_ms < 5000


def test_process_rejects_empty_argv(tmp_path):
    try:
        run_process(
            [],
            cwd=tmp_path,
            timeout_seconds=1,
        )
    except ValueError as exc:
        assert "argv" in str(exc)
    else:
        raise AssertionError(
            "empty argv must raise ValueError"
        )


def test_process_rejects_invalid_timeout(tmp_path):
    try:
        run_process(
            [sys.executable, "-V"],
            cwd=tmp_path,
            timeout_seconds=0,
        )
    except ValueError as exc:
        assert "timeout" in str(exc)
    else:
        raise AssertionError(
            "timeout <= 0 must raise ValueError"
        )
