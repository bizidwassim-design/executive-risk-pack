#!/usr/bin/env python3
"""Check the data files before building the pack.

Checks (every problem is reported, not just the first):
  * scores in range: likelihood and impact 1-5, maturity 0-5, residual never above inherent
  * every risk has an owner, a known category with an appetite, a treatment and a status
  * every KRI has a direction, a green and a red threshold in the right order, and an owner
  * every decision has at least two options, valid cost ranges, a recommendation that names
    one of its options, and text for "if declined" and the proposed resolution
  * risks, KRIs and decisions only link to IDs that exist
  * calendar dates fall inside the 12-month window and cover the required assurance events

Usage:
  python scripts/validate_data.py [--data data]
Exit code 0 when the data is valid, 1 otherwise.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from packdata import DATA_DIR, DataError, load  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the executive risk pack data files.")
    parser.add_argument("--data", type=Path, default=DATA_DIR, help="folder with the data files (default: data/)")
    args = parser.parse_args(argv)
    try:
        pack = load(args.data)
    except DataError as exc:
        print(f"FAIL: {len(exc.problems)} problem(s) in {args.data}", file=sys.stderr)
        for p in exc.problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    kc = pack.kri_counts()
    print(
        f"OK: {len(pack.csf)} CSF categories in {len(pack.functions)} functions, "
        f"{len(pack.risks)} risks ({sum(r.above_appetite for r in pack.risks)} above appetite), "
        f"{len(pack.kris)} KRIs ({kc['Green']} green, {kc['Amber']} amber, {kc['Red']} red), "
        f"{len(pack.calendar)} calendar entries, {len(pack.decisions)} decisions"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
