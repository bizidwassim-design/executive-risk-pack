#!/usr/bin/env python3
"""Start a new quarter: copy this quarter's values into the "last quarter" columns.

What it changes (in place, LF line endings):
  csf-profile.csv  last_quarter        <- current
  kris.csv         last_quarter        <- current
  risks.csv        last_q_likelihood   <- residual_likelihood
                   last_q_impact       <- residual_impact

It does not touch scores for the new quarter, the calendar, the decisions or
organisation.yaml: update those by hand, then run validate_data.py and build_pack.py.

Usage:
  python scripts/roll_quarter.py [--data data] [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from packdata import DATA_DIR  # noqa: E402

COPIES: dict[str, list[tuple[str, str]]] = {
    "csf-profile.csv": [("current", "last_quarter")],
    "kris.csv": [("current", "last_quarter")],
    "risks.csv": [("residual_likelihood", "last_q_likelihood"), ("residual_impact", "last_q_impact")],
}


def roll_file(path: Path, copies: list[tuple[str, str]], dry_run: bool = False) -> int:
    """Copy columns within one CSV. Returns the number of rows whose values changed."""
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    for src, dst in copies:
        if src not in fields or dst not in fields:
            raise SystemExit(f"{path.name}: expected columns {src!r} and {dst!r}")
    changed = 0
    for row in rows:
        before = tuple(row[dst] for _, dst in copies)
        for src, dst in copies:
            row[dst] = row[src]
        if tuple(row[dst] for _, dst in copies) != before:
            changed += 1
    if not dry_run:
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Copy current values into the last-quarter columns.")
    parser.add_argument("--data", type=Path, default=DATA_DIR, help="folder with the data files (default: data/)")
    parser.add_argument("--dry-run", action="store_true", help="report what would change without writing")
    args = parser.parse_args(argv)
    for name, copies in COPIES.items():
        n = roll_file(args.data / name, copies, args.dry_run)
        verb = "would update" if args.dry_run else "updated"
        print(f"{name}: {verb} {n} row(s)")
    print("Next: update organisation.yaml (quarter, dates), enter the new scores, then validate and build.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
