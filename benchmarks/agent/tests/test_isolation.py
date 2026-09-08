from __future__ import annotations

import importlib
from pathlib import Path


def isolation_module():
    try:
        return importlib.import_module(
            "benchmarks.agent.isolation"
        )
    except ModuleNotFoundError as error:
        raise AssertionError(
            "repository isolation is not implemented"
        ) from error


def test_isolated_repository_never_mutates_source(
    tmp_path: Path,
):
    module = isolation_module()

    source = tmp_path / "source"
    source.mkdir()

    (source / "src").mkdir()
    (source / "src" / "main.py").write_text(
        "VALUE = 1\n",
        encoding="utf-8",
    )

    before = module.repository_digest(source)

    with module.isolated_repository(source) as isolated:
        assert isolated != source
        assert (
            isolated / "src" / "main.py"
        ).read_text(encoding="utf-8") == "VALUE = 1\n"

        (
            isolated / "src" / "main.py"
        ).write_text(
            "VALUE = 999\n",
            encoding="utf-8",
        )

        (
            isolated / "generated.txt"
        ).write_text(
            "temporary\n",
            encoding="utf-8",
        )

    after = module.repository_digest(source)

    assert after == before

    assert (
        source / "src" / "main.py"
    ).read_text(encoding="utf-8") == "VALUE = 1\n"

    assert not (
        source / "generated.txt"
    ).exists()


def test_isolation_excludes_runtime_state(
    tmp_path: Path,
):
    module = isolation_module()

    source = tmp_path / "source"
    source.mkdir()

    (source / "app.py").write_text(
        "print('ok')\n",
        encoding="utf-8",
    )

    (source / ".git").mkdir()
    (source / ".git" / "HEAD").write_text(
        "secret-git-state\n",
        encoding="utf-8",
    )

    (source / ".codeintel").mkdir()
    (
        source
        / ".codeintel"
        / "manifest.json"
    ).write_text(
        "{}\n",
        encoding="utf-8",
    )

    with module.isolated_repository(source) as isolated:
        assert (isolated / "app.py").is_file()
        assert not (isolated / ".git").exists()
        assert not (
            isolated / ".codeintel"
        ).exists()


def test_repository_digest_ignores_git_and_codeintel(
    tmp_path: Path,
):
    module = isolation_module()

    root = tmp_path / "repo"
    root.mkdir()

    (root / "file.txt").write_text(
        "stable\n",
        encoding="utf-8",
    )

    first = module.repository_digest(root)

    (root / ".git").mkdir()
    (root / ".git" / "x").write_text(
        "git\n",
        encoding="utf-8",
    )

    (root / ".codeintel").mkdir()
    (root / ".codeintel" / "x").write_text(
        "index\n",
        encoding="utf-8",
    )

    second = module.repository_digest(root)

    assert second == first


def test_repository_digest_changes_with_source(
    tmp_path: Path,
):
    module = isolation_module()

    root = tmp_path / "repo"
    root.mkdir()

    file = root / "file.txt"

    file.write_text(
        "one\n",
        encoding="utf-8",
    )

    first = module.repository_digest(root)

    file.write_text(
        "two\n",
        encoding="utf-8",
    )

    second = module.repository_digest(root)

    assert first != second
