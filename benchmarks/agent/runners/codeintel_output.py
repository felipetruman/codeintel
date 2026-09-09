from pathlib import Path
from typing import Any

from benchmarks.agent.runners.agent_protocol import relative_path, nonnegative_int


def _objects(value: Any) -> list[dict]:
    if not isinstance(value, list):
        raise ValueError("expected an array")
    if not all(isinstance(item, dict) for item in value):
        raise ValueError("expected object entries")
    return value


def _paths(items: list[dict], repo: Path) -> list[str]:
    paths = []
    for item in items:
        if not isinstance(item.get("path"), str):
            raise ValueError("path must be a string")
        paths.append(relative_path(item["path"], repo))
    return list(dict.fromkeys(paths))


def _names(items: list[dict]) -> list[str]:
    names = [item.get("name") for item in items]
    if not all(isinstance(name, str) for name in names):
        raise ValueError("symbol name must be a string")
    return list(dict.fromkeys(names))


def _search(payload, repo):
    items = _objects(payload)
    return _paths(items, repo), [], {"candidate_count": len(items)}


def _context(payload, repo):
    return _paths(_objects(payload["files"]), repo), [], {}


def _symbol(payload, repo):
    definitions = _objects(payload["definitions"])
    callers = _objects(payload["callers"])
    callees = _objects(payload["callees"])
    references = _objects(payload["references"])
    items = definitions + callers + callees
    metadata = {
        "callers": _names(callers),
        "callees": _names(callees),
        "references_count": len(references),
    }
    return _paths(items, repo), _names(items), metadata


def _impact(payload, repo):
    definitions = _objects(payload["definitions"])
    direct = _objects(payload["direct_callers"])
    impacted = _objects([item["symbol"] for item in _objects(payload["impacted"])])
    radius = nonnegative_int(payload["blast_radius"])
    if radius is None:
        raise ValueError("blast radius must be a non-negative integer")
    items = definitions + direct + impacted
    metadata = {
        "direct_callers": _names(direct),
        "impacted": _names(impacted),
        "blast_radius": radius,
        "pagerank": payload.get("pagerank"),
    }
    return _paths(items, repo), _names(items), metadata


PARSERS = {"search": _search, "context": _context, "symbol": _symbol, "impact": _impact}


def parse_output(operation: str, payload: Any, repo: Path) -> tuple[list, list, dict]:
    if operation != "search" and not isinstance(payload, dict):
        raise ValueError("operation payload must be an object")
    return PARSERS[operation](payload, repo)
