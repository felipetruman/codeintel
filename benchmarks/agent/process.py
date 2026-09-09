from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
import math
import os
import selectors
import signal
import subprocess
import time


@dataclass(frozen=True)
class ProcessOptions:
    env: Mapping[str, str] | None = None
    max_output_bytes: int = 8 * 1024 * 1024
    inherit_env: bool = True


@dataclass(frozen=True)
class ProcessResult:
    argv: list[str]
    stdout: str
    stderr: str
    exit_code: int | None
    duration_ms: float
    timed_out: bool
    output_limited: bool = False


def _kill_group(process: subprocess.Popen) -> None:
    # Always kill the group, even if its leader has already exited. Children can
    # close their inherited pipes and otherwise survive a successful command.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=5)


def _read_ready(selector, ready, buffers, remaining: int) -> int:
    for key, _ in ready:
        chunk = os.read(key.fd, min(65536, remaining + 1))
        if not chunk:
            selector.unregister(key.fileobj)
            continue
        buffers[key.data].extend(chunk[:remaining])
        remaining -= len(chunk)
        if remaining < 0:
            return remaining
    return remaining


def _capture(
    process, deadline: float, limit: int
) -> tuple[list[bytearray], bool, bool]:
    buffers = [bytearray(), bytearray()]
    remaining = limit
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ, 0)
        selector.register(process.stderr, selectors.EVENT_READ, 1)
        while selector.get_map():
            wait = deadline - time.monotonic()
            if wait <= 0:
                return buffers, True, False
            ready = selector.select(min(wait, 0.05))
            remaining = _read_ready(selector, ready, buffers, remaining)
            if remaining < 0:
                return buffers, False, True
    try:
        process.wait(timeout=max(0.001, deadline - time.monotonic()))
    except subprocess.TimeoutExpired:
        return buffers, True, False
    return buffers, False, False


def _validate_timeout(timeout: float) -> None:
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout_seconds must be finite and > 0")


def _validate(argv: list[str], cwd: Path, timeout: float, limit: int) -> None:
    _validate_timeout(timeout)
    if not argv:
        raise ValueError("argv must not be empty")
    if not cwd.is_dir():
        raise ValueError(f"cwd is not a directory: {cwd}")
    if limit <= 0:
        raise ValueError("max_output_bytes must be > 0")


def run_process(
    argv: list[str],
    cwd: Path,
    timeout_seconds: float,
    options: ProcessOptions | None = None,
) -> ProcessResult:
    options = options or ProcessOptions()
    env, max_output_bytes = options.env, options.max_output_bytes
    inherit_env = options.inherit_env
    root = Path(cwd)
    _validate(argv, root, timeout_seconds, max_output_bytes)
    effective_env = {**os.environ, **(env or {})} if inherit_env else dict(env or {})
    started = time.monotonic()
    with subprocess.Popen(
        argv,
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        start_new_session=True,
        env=effective_env,
    ) as process:
        try:
            buffers, timed_out, limited = _capture(
                process, started + timeout_seconds, max_output_bytes
            )
        finally:
            _kill_group(process)
    stdout, stderr = (
        bytes(buffer).decode("utf-8", errors="replace") for buffer in buffers
    )
    exit_code = None if timed_out or limited else process.returncode
    return ProcessResult(
        list(argv),
        stdout,
        stderr,
        exit_code,
        (time.monotonic() - started) * 1000,
        timed_out,
        limited,
    )
