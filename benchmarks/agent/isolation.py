from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
import os
import shutil
import tempfile


DEFAULT_EXCLUDES = (
    ".git",
    ".codeintel",
)


def _ignored_names(
    _directory: str,
    names: list[str],
) -> set[str]:
    return {
        name
        for name in names
        if name in DEFAULT_EXCLUDES
    }


@contextmanager
def isolated_repository(
    source: Path,
) -> Iterator[Path]:
    source = Path(source).resolve()

    if not source.is_dir():
        raise ValueError(
            f"repository source is not a directory: {source}"
        )

    with tempfile.TemporaryDirectory(
        prefix="codeintel-benchmark-"
    ) as temporary:
        destination = (
            Path(temporary) / "repo"
        )

        shutil.copytree(
            source,
            destination,
            symlinks=True,
            ignore=_ignored_names,
        )

        yield destination


def repository_digest(
    root: Path,
    exclude: tuple[str, ...] = DEFAULT_EXCLUDES,
) -> str:
    root = Path(root).resolve()

    if not root.is_dir():
        raise ValueError(
            f"repository root is not a directory: {root}"
        )

    excluded = set(exclude)
    digest = sha256()

    for current, dirs, files in os.walk(
        root,
        topdown=True,
        followlinks=False,
    ):
        current_path = Path(current)

        dirs[:] = sorted(
            directory
            for directory in dirs
            if directory not in excluded
        )

        for filename in sorted(files):
            path = current_path / filename

            relative = path.relative_to(
                root
            ).as_posix()

            if any(
                part in excluded
                for part in Path(relative).parts
            ):
                continue

            digest.update(
                b"P\0"
                + relative.encode("utf-8")
                + b"\0"
            )

            if path.is_symlink():
                digest.update(b"L\0")
                digest.update(
                    os.readlink(path).encode(
                        "utf-8"
                    )
                )
                digest.update(b"\0")
                continue

            digest.update(b"F\0")

            with path.open("rb") as handle:
                while True:
                    chunk = handle.read(
                        1024 * 1024
                    )

                    if not chunk:
                        break

                    digest.update(chunk)

            digest.update(b"\0")

    return digest.hexdigest()
