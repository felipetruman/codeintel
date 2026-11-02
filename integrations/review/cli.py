"""Read-only PR review context collector. Requires an already checked-out repository."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from collections.abc import Sequence

from .report import ReviewError, build_review_report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare CodeIntel PR review evidence (not an AI verdict).")
    parser.add_argument("--repo", default=".", help="Existing repository checkout")
    parser.add_argument("--base", required=True, help="Base commit SHA or locally available ref")
    parser.add_argument("--head", required=True, help="Head commit SHA or locally available ref")
    parser.add_argument("--codeintel-bin", default="codeintel", help="Trusted CodeIntel executable")
    args = parser.parse_args(argv)
    try:
        report = build_review_report(Path(args.repo), args.base, args.head,
                                     codeintel_command=(args.codeintel_bin,))
    except ReviewError as exc:
        print(f"review context failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
