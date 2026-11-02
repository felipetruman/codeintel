"""Create an evidence-only, read-only review context from two git commits.

This is *not* an AI reviewer: it cannot approve a change, execute project code,
or publish GitHub comments. Run it inside an isolated E2B workspace when the
repository is untrusted. It is safe to unit-test on synthetic local git repos.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import Any, Sequence


class ReviewError(RuntimeError):
    """A review context cannot be trusted or cannot be prepared."""


def _run(argv: Sequence[str], *, cwd: Path, timeout: int) -> bytes:
    try:
        run = subprocess.run(list(argv), cwd=cwd, check=False, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ReviewError(f"command unavailable or timed out: {argv[0]}") from exc
    if run.returncode != 0:
        # Avoid echoing possibly sensitive stderr or repository contents.
        raise ReviewError(f"{argv[0]} exited with status {run.returncode}")
    if len(run.stdout) > 2 * 1024 * 1024:
        raise ReviewError(f"{argv[0]} response exceeds 2 MiB")
    return run.stdout


def _revision(repo: Path, ref: str) -> str:
    if not ref or "\x00" in ref or len(ref) > 256:
        raise ReviewError("invalid git revision")
    raw = _run(["git", "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}"],
               cwd=repo, timeout=15)
    sha = raw.decode("ascii", "strict").strip()
    if len(sha) not in {40, 64} or any(ch not in "0123456789abcdef" for ch in sha):
        raise ReviewError("git returned an invalid commit SHA")
    return sha


def _context_paths(repo: Path, payload: Any, max_context: int) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("files"), list):
        raise ReviewError("codeintel context returned an invalid JSON schema")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in payload["files"]:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            continue
        name = item["path"]
        if not name or name in seen or Path(name).is_absolute() or "\x00" in name:
            continue
        candidate = (repo / name).resolve()
        if not candidate.is_relative_to(repo) or not candidate.is_file():
            continue
        seen.add(name)
        score = item.get("score")
        result.append({"path": name, "score": score if type(score) in (int, float) else None})
        if len(result) >= max_context:
            break
    return result


def build_review_report(repo: Path, base: str, head: str, *,
                        codeintel_command: Sequence[str] = ("codeintel",),
                        max_files: int = 200, max_context: int = 10) -> dict[str, Any]:
    """Collect deterministic file-change and CodeIntel context evidence.

    No model/AI verdict is generated. ``base`` and ``head`` must resolve to
    commits already available in the local repository. No shell is invoked.
    """
    root = Path(repo).resolve()
    if not root.is_dir() or max_files < 0 or max_context < 1 or not codeintel_command:
        raise ReviewError("invalid review configuration")
    try:
        base_sha = _revision(root, base)
        head_sha = _revision(root, head)
        changed_raw = _run(["git", "diff", "--no-ext-diff", "--name-only", "-z",
                            "--diff-filter=ACMRT", base_sha, head_sha, "--"], cwd=root, timeout=30)
        paths = [part.decode("utf-8", "surrogateescape") for part in changed_raw.split(b"\x00") if part]
    except (UnicodeError, ValueError) as exc:
        raise ReviewError("git returned invalid change metadata") from exc
    if len(paths) > max_files:
        raise ReviewError("too many changed files for one review")
    report: dict[str, Any] = {
        "schema_version": 1, "status": "no_changes" if not paths else "context_ready",
        "base_sha": base_sha, "head_sha": head_sha, "changed_files": paths,
        "context_files": [], "findings": [], "validated": False,
    }
    if not paths:
        return report
    # This task is a search prompt, never a command; shell=False is mandatory.
    task = "Review changes and dependencies for files: " + ", ".join(paths[:30])
    raw = _run([*codeintel_command, "context", task, str(root), "--limit", str(max_context)],
               cwd=root, timeout=90)
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise ReviewError("codeintel context returned invalid JSON") from exc
    report["context_files"] = _context_paths(root, payload, max_context)
    return report
