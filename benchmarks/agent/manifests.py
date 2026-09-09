from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

SUPPORTED_TASK_TYPES = frozenset(
    {
        "locate-symbol",
        "relevant-files",
        "impact-analysis",
        "change-planning",
    }
)

TOP_LEVEL_KEYS = frozenset(
    {
        "id",
        "type",
        "query",
        "prompt",
        "corpus",
        "expected",
    }
)

EXPECTED_KEYS = frozenset(
    {
        "files",
        "symbols",
        "direct_callers",
        "impacted",
        "blast_radius",
    }
)


@dataclass(frozen=True)
class GroundTruth:
    files: tuple[str, ...] = ()
    symbols: tuple[str, ...] = ()
    direct_callers: tuple[str, ...] = ()
    impacted: tuple[str, ...] = ()
    blast_radius: int | None = None


@dataclass(frozen=True)
class BenchmarkTask:
    id: str
    type: str
    query: str
    prompt: str
    corpus: str
    expected: GroundTruth


def _require_string(
    data: dict[str, Any],
    key: str,
) -> str:
    value = data.get(key)

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key!r} must be a non-empty string")

    return value.strip()


def _string_tuple(
    data: dict[str, Any],
    key: str,
) -> tuple[str, ...]:
    value = data.get(key, [])

    if value is None:
        return ()

    if not isinstance(value, list):
        raise ValueError(f"expected.{key} must be a list")

    result = []

    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"expected.{key} entries must be non-empty strings")

        result.append(item.strip())

    return tuple(result)


def _mapping(value: Any, allowed: frozenset[str], label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a mapping")
    unknown = set(value).difference(allowed)
    if unknown:
        raise ValueError(
            f"unknown {label} fields: " + ", ".join(sorted(map(str, unknown)))
        )
    return value


def _read_yaml(path: Path) -> dict:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ValueError(f"cannot read task manifest: {path}") from error
    except yaml.YAMLError as error:
        raise ValueError(f"invalid YAML task manifest: {path}") from error


def _blast_radius(value: Any) -> int | None:
    if value is None:
        return None
    if type(value) is not int:
        raise ValueError("expected.blast_radius must be a non-negative integer or null")
    if value < 0:
        raise ValueError("expected.blast_radius must be a non-negative integer or null")
    return value


def _ground_truth(value: Any) -> GroundTruth:
    raw = _mapping({} if value is None else value, EXPECTED_KEYS, "expected")
    return GroundTruth(
        files=_string_tuple(raw, "files"),
        symbols=_string_tuple(raw, "symbols"),
        direct_callers=_string_tuple(raw, "direct_callers"),
        impacted=_string_tuple(raw, "impacted"),
        blast_radius=_blast_radius(raw.get("blast_radius")),
    )


def load_task(path: Path) -> BenchmarkTask:
    raw = _mapping(_read_yaml(Path(path)), TOP_LEVEL_KEYS, "task")
    task_type = _require_string(raw, "type")
    if task_type not in SUPPORTED_TASK_TYPES:
        raise ValueError(f"unsupported task type: {task_type}")
    return BenchmarkTask(
        id=_require_string(raw, "id"),
        type=task_type,
        query=_require_string(raw, "query"),
        prompt=_require_string(raw, "prompt"),
        corpus=_require_string(raw, "corpus"),
        expected=_ground_truth(raw.get("expected")),
    )


def load_tasks(path: Path) -> list[BenchmarkTask]:
    path = Path(path)

    if path.is_file():
        return [load_task(path)]

    if not path.is_dir():
        raise ValueError(f"task path does not exist: {path}")

    manifests = sorted(
        [
            *path.glob("*.yaml"),
            *path.glob("*.yml"),
        ],
        key=lambda item: item.name,
    )

    return [load_task(manifest) for manifest in manifests]
