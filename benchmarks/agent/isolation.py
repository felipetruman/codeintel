from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
import os
import shutil
import stat
import tempfile

DEFAULT_EXCLUDES = (".git", ".codeintel")


def _ignored_names(_directory: str, names: list[str]) -> set[str]:
    return set(names).intersection(DEFAULT_EXCLUDES)


def _entries(root: Path, excluded: tuple[str, ...]) -> Iterator[Path]:
    for current, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(set(dirs).difference(excluded))
        names = set(dirs).union(files).difference(excluded)
        yield from (Path(current) / name for name in sorted(names))


def _link_target(path: Path, source: Path) -> Path:
    try:
        relative = path.resolve(strict=True).relative_to(source)
    except (OSError, RuntimeError, ValueError) as error:
        raise ValueError(
            f"unsafe or dangling symlink: {path.relative_to(source)}"
        ) from error
    if set(relative.parts).intersection(DEFAULT_EXCLUDES):
        raise ValueError(
            f"symlink points into excluded state: {path.relative_to(source)}"
        )
    return relative


def _validated_links(source: Path) -> dict[Path, Path]:
    links = {}
    for path in _entries(source, DEFAULT_EXCLUDES):
        if path.is_symlink():
            links[path.relative_to(source)] = _link_target(path, source)
        elif not (path.is_file() or path.is_dir()):
            raise ValueError(f"unsupported special file: {path.relative_to(source)}")
    return links


@contextmanager
def isolated_repository(source: Path) -> Iterator[Path]:
    source = Path(source).resolve()
    if not source.is_dir():
        raise ValueError(f"repository source is not a directory: {source}")
    links = _validated_links(source)
    with tempfile.TemporaryDirectory(prefix="codeintel-benchmark-") as temporary:
        destination = Path(temporary) / "repo"
        shutil.copytree(source, destination, symlinks=True, ignore=_ignored_names)
        for relative, target in links.items():
            copied = destination / relative
            copied.unlink()
            copied.symlink_to(os.path.relpath(destination / target, copied.parent))
        yield destination


def _hash_entry(digest, path: Path, root: Path) -> None:
    digest.update(b"P\0" + path.relative_to(root).as_posix().encode() + b"\0")
    digest.update(str(stat.S_IMODE(path.lstat().st_mode)).encode() + b"\0")
    if path.is_symlink():
        digest.update(b"L\0" + os.readlink(path).encode() + b"\0")
        return
    if path.is_dir():
        digest.update(b"D\0")
        return
    digest.update(b"F\0")
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    digest.update(b"\0")


def repository_digest(root: Path, exclude: tuple[str, ...] = DEFAULT_EXCLUDES) -> str:
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError(f"repository root is not a directory: {root}")
    digest = sha256()
    for path in _entries(root, exclude):
        _hash_entry(digest, path, root)
    return digest.hexdigest()
