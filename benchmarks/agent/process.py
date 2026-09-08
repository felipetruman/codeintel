from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
import os
import signal
import subprocess
import time


@dataclass(frozen=True)
class ProcessResult:
    argv: list[str]
    stdout: str
    stderr: str
    exit_code: int | None
    duration_ms: float
    timed_out: bool


def _terminate_process_group(
    process: subprocess.Popen[str],
) -> tuple[str, str]:
    try:
        os.killpg(
            process.pid,
            signal.SIGTERM,
        )
    except ProcessLookupError:
        pass

    try:
        return process.communicate(
            timeout=0.5,
        )
    except subprocess.TimeoutExpired:
        try:
            os.killpg(
                process.pid,
                signal.SIGKILL,
            )
        except ProcessLookupError:
            pass

        return process.communicate()


def run_process(
    argv: list[str],
    cwd: Path,
    timeout_seconds: float,
    env: Mapping[str, str] | None = None,
) -> ProcessResult:
    if not argv:
        raise ValueError(
            "argv must not be empty"
        )

    if timeout_seconds <= 0:
        raise ValueError(
            "timeout_seconds must be > 0"
        )

    root = Path(cwd)

    if not root.is_dir():
        raise ValueError(
            f"cwd is not a directory: {root}"
        )

    effective_env = None

    if env is not None:
        effective_env = {
            **os.environ,
            **dict(env),
        }

    started = time.monotonic()

    process = subprocess.Popen(
        argv,
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False,
        start_new_session=True,
        env=effective_env,
    )

    timed_out = False

    try:
        stdout, stderr = process.communicate(
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        timed_out = True
        stdout, stderr = _terminate_process_group(
            process
        )

    duration_ms = (
        time.monotonic() - started
    ) * 1000.0

    return ProcessResult(
        argv=list(argv),
        stdout=stdout,
        stderr=stderr,
        exit_code=(
            None
            if timed_out
            else process.returncode
        ),
        duration_ms=duration_ms,
        timed_out=timed_out,
    )
