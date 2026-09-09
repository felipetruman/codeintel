"""Reproduce the README's functional claims without modifying the source repo."""

import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BINARY = ROOT / "target" / "release" / "codeintel"
SOURCES = {
    "payment.py": "def process_payment():\n    return True\n",
    "checkout.py": (
        "from payment import process_payment\n"
        "def checkout():\n    return process_payment()\n"
    ),
    "routes.py": "from checkout import checkout\ndef submit_order():\n    return checkout()\n",
}


def command(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        [str(BINARY), *args, str(repo)], text=True, timeout=30
    )


def verify_retrieval(repo: Path) -> None:
    search = json.loads(command(repo, "search", "process_payment"))
    files = sorted({item["path"] for item in search})
    assert files == ["checkout.py", "payment.py"], files
    symbol = json.loads(command(repo, "symbol", "process_payment"))
    assert {item["name"] for item in symbol["definitions"]} == {"process_payment"}
    context = json.loads(command(repo, "context", "change process_payment checkout"))
    assert "payment.py" in {item["path"] for item in context["files"]}
    print("search_files: " + ", ".join(files))
    print("definition: process_payment")


def verify_impact(repo: Path) -> None:
    impact = json.loads(command(repo, "impact", "process_payment"))
    callers = [item["name"] for item in impact["direct_callers"]]
    assert callers == ["checkout"], callers
    assert impact["blast_radius"] == 2, impact
    assert {item["symbol"]["name"] for item in impact["impacted"]} == {
        "checkout",
        "submit_order",
    }
    print("direct_callers: " + ", ".join(callers))
    print("blast_radius: 2")


def verify_freshness(repo: Path) -> None:
    (repo / "payment.py").write_text(
        "def process_payment():\n    return False\n", encoding="utf-8"
    )
    expected = {
        "modified": "scanned=3 reused=2 added=0 modified=1 deleted=0 reparsed=1",
        "unchanged": "scanned=3 reused=3 added=0 modified=0 deleted=0 reparsed=0",
    }
    for label, counters in expected.items():
        output = command(repo, "index")
        assert "fresh: " + counters in output, output
        print(f"{label}: {counters}")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="codeintel-proof-") as temporary:
        repo = Path(temporary)
        for name, source in SOURCES.items():
            (repo / name).write_text(source, encoding="utf-8")
        verify_retrieval(repo)
        verify_impact(repo)
        verify_freshness(repo)
    print("PASS: core retrieval, graph impact, and incremental reuse")


if __name__ == "__main__":
    main()
