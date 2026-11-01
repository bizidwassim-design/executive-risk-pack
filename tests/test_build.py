from __future__ import annotations

import csv
from pathlib import Path

import pytest

from build_pack import build, fmt_cost, fmt_range
from conftest import ROOT
from datetime import date
from packdata import load
from roll_quarter import COPIES, roll_file

SHEETS = ["Summary", "CSF Profile", "Top Risks", "Heat Map", "KRIs", "Calendar", "Decisions", "Scales"]


def test_build_is_deterministic(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    build(ROOT / "data", a, charts=False)
    build(ROOT / "data", b, charts=False)
    for name in ("board-pack.md", "board-pack.xlsx", "charts/chart-data.json"):
        assert (a / name).read_bytes() == (b / name).read_bytes(), name


def test_committed_pack_matches_data(tmp_path: Path) -> None:
    build(ROOT / "data", tmp_path, charts=False)
    for name in ("board-pack.md", "board-pack.xlsx", "charts/chart-data.json"):
        assert (tmp_path / name).read_bytes() == (ROOT / "pack" / name).read_bytes(), \
            f"pack/{name} is stale: run python scripts/build_pack.py"


def test_markdown_has_every_section(tmp_path: Path) -> None:
    build(ROOT / "data", tmp_path, charts=False)
    md = (tmp_path / "board-pack.md").read_text(encoding="utf-8")
    for heading in ("## 1. Summary for the board", "## 2. Security posture against target", "## 3. Top risks",
                    "## 4. Key risk indicators", "## 5. Regulatory and assurance calendar",
                    "## 6. Decisions required"):
        assert heading in md
    assert md.count("**Recommendation: option") == 3
    assert "| Impact ↓ · Likelihood →" in md


def test_workbook_sheets(tmp_path: Path) -> None:
    openpyxl = pytest.importorskip("openpyxl")
    build(ROOT / "data", tmp_path, charts=False)
    wb = openpyxl.load_workbook(tmp_path / "board-pack.xlsx")
    assert wb.sheetnames == SHEETS
    risk_ids = [r[0].value for r in wb["Top Risks"].iter_rows(min_row=5, max_col=1) if r[0].value]
    assert len(risk_ids) == 10 and risk_ids[0] == "R03"


def test_charts_render(tmp_path: Path) -> None:
    pytest.importorskip("matplotlib")
    build(ROOT / "data", tmp_path, charts=True)
    for name in ("csf-current-vs-target.png", "residual-risk-heatmap.png"):
        assert (tmp_path / "charts" / name).read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_formatting_helpers() -> None:
    assert fmt_cost(2_400_000, 2_900_000, "AED") == "AED 2.4m–2.9m"
    assert fmt_cost(40_000, 60_000, "AED") == "AED 40k–60k"
    assert fmt_cost(0, 0, "AED") == "No new spend"
    assert fmt_range(date(2026, 11, 16), date(2026, 11, 20)) == "16–20 Nov 2026"
    assert fmt_range(date(2027, 1, 18), date(2027, 2, 2)) == "18 Jan – 2 Feb 2027"


def test_roll_quarter(data_copy: Path) -> None:
    for name, copies in COPIES.items():
        roll_file(data_copy / name, copies)
    pack = load(data_copy)
    assert all(r.trend == "Stable" for r in pack.risks)
    assert all(k.trend == "Stable" for k in pack.kris)
    assert all(f.trend == "Stable" for f in pack.functions)
    with (data_copy / "risks.csv").open(encoding="utf-8", newline="") as fh:
        assert "\r\n" not in fh.read()
    with (data_copy / "kris.csv").open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert all(r["current"] == r["last_quarter"] for r in rows)
