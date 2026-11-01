#!/usr/bin/env python3
"""Build the quarterly executive cyber-risk pack from the files in data/.

Outputs (default folder: pack/):
  board-pack.md                       the board pack, 5-6 printed pages
  board-pack.xlsx                     the same content as a workbook, one sheet per section
  charts/csf-current-vs-target.png    NIST CSF 2.0 maturity by function (needs matplotlib)
  charts/residual-risk-heatmap.png    5x5 residual-risk heat map (needs matplotlib)
  charts/chart-data.json              the numbers behind both charts (always written; diffed by CI)

Usage:
  python scripts/build_pack.py [--data data] [--out pack] [--no-charts] [--quiet]

The build is deterministic: same data, same bytes. No wall-clock dates are used.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
import zipfile
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from packdata import DATA_DIR, ROOT, DataError, Pack, Risk, band_for, load  # noqa: E402

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
RAG_ICON = {"Green": "🟢", "Amber": "🟠", "Red": "🔴"}
BAND_ICON = {"Low": "🟩", "Medium": "🟨", "High": "🟧", "Critical": "🟥"}
FUNCTION_PLAIN = {
    "Govern": "Direction, roles, policy and oversight of cyber risk",
    "Identify": "Knowing our assets, suppliers and risks",
    "Protect": "Safeguards that prevent or limit an attack",
    "Detect": "Spotting an attack quickly",
    "Respond": "Containing and managing an incident",
    "Recover": "Restoring service and trust after an incident",
}
LIKELIHOOD_SHORT = {1: "Rare", 2: "Unlikely", 3: "Possible", 4: "Likely", 5: "Almost certain"}
IMPACT_SHORT = {1: "Minor", 2: "Moderate", 3: "Significant", 4: "Major", 5: "Severe"}

# Chart colours: categorical blue steps for "this quarter / last quarter", ink for the target,
# and the reserved status palette (good / warning / serious / critical) for risk bands.
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
SURFACE = "#fcfcfb"
BLUE = "#2a78d6"
BLUE_LIGHT = "#9ec5f4"
BAND_COLOUR = {"Low": "#0ca30c", "Medium": "#fab219", "High": "#ec835a", "Critical": "#d03b3b"}

# Workbook fills (light tints so black text stays readable).
XL_HEADER = "1C5CAB"
XL_RAG = {"Green": "C6EFCE", "Amber": "FFEB9C", "Red": "FFC7CE"}
XL_BAND = {"Low": "C6EFCE", "Medium": "FFEB9C", "High": "F8CBAD", "Critical": "FF9B9B"}
XL_TIMESTAMP = (2026, 1, 1, 0, 0, 0)


# ------------------------------------------------------------------ formatting


def fmt_date(d: date) -> str:
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def fmt_range(start: date, end: date) -> str:
    if start == end:
        return fmt_date(start)
    if (start.year, start.month) == (end.year, end.month):
        return f"{start.day}–{end.day} {MONTHS[start.month - 1]} {start.year}"
    if start.year == end.year:
        return f"{start.day} {MONTHS[start.month - 1]} – {end.day} {MONTHS[end.month - 1]} {end.year}"
    return f"{fmt_date(start)} – {fmt_date(end)}"


def fmt_money(value: int) -> str:
    if value == 0:
        return "0"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}m"
    return f"{value / 1_000:.0f}k"


def fmt_cost(lo: int, hi: int, currency: str) -> str:
    if lo == hi == 0:
        return "No new spend"
    if lo == hi:
        return f"{currency} {fmt_money(lo)}"
    return f"{currency} {fmt_money(lo)}–{fmt_money(hi)}"


def fmt_score(value: float) -> str:
    return f"{value:.1f}"


def md_escape(text: str) -> str:
    return text.replace("|", "\\|")


def plural(n: int, word: str, many: str | None = None) -> str:
    return f"{n} {word if n == 1 else (many or word + 's')}"


# ------------------------------------------------------------------ derived facts


def last_quarter_above_appetite(pack: Pack) -> int:
    return sum(1 for r in pack.risks if r.last_q_score is not None and r.last_q_score > r.appetite)


def last_quarter_red_kris(pack: Pack) -> int:
    return sum(1 for k in pack.kris if k.last_rag == "Red")


def heat_cells(risks: list[Risk]) -> dict[tuple[int, int], list[str]]:
    cells: dict[tuple[int, int], list[str]] = {}
    for r in sorted(risks, key=lambda x: x.id):
        cells.setdefault((r.residual_likelihood, r.residual_impact), []).append(r.id)
    return cells


def risks_without_kri(pack: Pack) -> list[Risk]:
    linked = {rid for k in pack.kris for rid in k.linked_risks}
    return [r for r in pack.risks if not r.linked_kris and r.id not in linked]


# ------------------------------------------------------------------ Markdown


def render_markdown(pack: Pack) -> str:
    rep, org = pack.report, pack.org
    cur = rep["currency"]
    ranked = pack.risks_by_residual()
    above = [r for r in ranked if r.above_appetite]
    trends = pack.risk_trend_counts()
    kc = pack.kri_counts()
    red_kris = [k for k in pack.kris if k.rag == "Red"]
    total_lo = sum(d.recommended.cost_min for d in pack.decisions)
    total_hi = sum(d.recommended.cost_max for d in pack.decisions)
    out: list[str] = []
    w = out.append

    w(f"# {rep['title']} — {rep['quarter']}")
    w("")
    w(f"**{org['name']}** · {rep['presented_to']} · {fmt_date(rep['board_meeting'])}  ")
    w(f"Prepared by the {rep['prepared_by']} · Reporting period "
      f"{fmt_date(rep['period_start'])} to {fmt_date(rep['period_end'])} · {rep['classification']}")
    w("")
    w(f"> **Sample pack.** {org['name']} and every figure in this document are fictional. "
      "It is generated from the files in [`data/`](../data) by [`scripts/build_pack.py`](../scripts/build_pack.py).")
    w("")

    # ---- 1. Summary ---------------------------------------------------------
    w("## 1. Summary for the board")
    w("")
    w("**Three things to remember**")
    w("")
    for i, line in enumerate(pack.config["narrative"], start=1):
        w(f"{i}. {line}")
    w("")
    w("**Where we stand**")
    w("")
    w("| Measure | Last quarter | This quarter | Direction |")
    w("|---|---|---|---|")
    pd = pack.posture_current - pack.posture_last_quarter
    w(f"| Security maturity, 0–5 (target {fmt_score(pack.posture_target)} by {rep['target_profile_by']}) "
      f"| {fmt_score(pack.posture_last_quarter)} | **{fmt_score(pack.posture_current)}** "
      f"({pack.posture_pct_of_target}% of target) | {'Improving' if pd >= 0.05 else 'Worsening' if pd <= -0.05 else 'Stable'} |")
    la, ln = last_quarter_above_appetite(pack), len(above)
    w(f"| Top risks above the board's appetite | {la} of {len(pack.risks)} | **{ln} of {len(pack.risks)}** "
      f"| {'Worsening' if ln > la else 'Improving' if ln < la else 'Stable'} |")
    lr, nr = last_quarter_red_kris(pack), kc["Red"]
    w(f"| Key risk indicators at red | {lr} of {len(pack.kris)} | **{nr} of {len(pack.kris)}** "
      f"| {'Worsening' if nr > lr else 'Improving' if nr < lr else 'Stable'} |")
    w(f"| Top risks that moved | — | {trends['Improving']} better, {trends['Worsening']} worse, "
      f"{trends['Stable']} unchanged, {trends['New']} new | — |")
    w("")
    w("**Decisions requested today**")
    w("")
    w("| # | Decision | Type | Recommendation | Cost |")
    w("|---|---|---|---|---|")
    for d in pack.decisions:
        o = d.recommended
        w(f"| {d.id} | {md_escape(d.title)} | {d.type} | Option {o.id}: {md_escape(o.label)} "
          f"| {fmt_cost(o.cost_min, o.cost_max, cur)} |")
    w("")
    w(f"Approving all three recommendations commits {fmt_cost(total_lo, total_hi, cur)}. Details in section 6.")
    w("")
    soon = pack.look_ahead()
    if soon:
        w(f"**Coming up in the next {rep['look_ahead_days']} days**")
        w("")
        for c in soon:
            w(f"- {fmt_range(c.start, c.end)} — {c.activity}")
        w("")

    # ---- 2. Posture ---------------------------------------------------------
    w("## 2. Security posture against target")
    w("")
    best = max(pack.functions, key=lambda f: (f.current - f.last_quarter, f.function))
    worst_gap = max(pack.functions, key=lambda f: (f.gap, f.function))
    w(f"We score each of the 22 NIST CSF 2.0 categories from 0 (absent) to 5 (optimised) and average them by "
      f"function. Overall maturity is **{fmt_score(pack.posture_current)} out of 5**, "
      f"{pack.posture_pct_of_target}% of the target the board set for {rep['target_profile_by']}. "
      f"The biggest improvement this quarter was in **{best.function}**. "
      f"The largest gap to target is in **{worst_gap.function}**.")
    w("")
    w("| Function | What it covers | Last quarter | Now | Target | Gap | Status | Trend |")
    w("|---|---|---|---|---|---|---|---|")
    for f in pack.functions:
        w(f"| **{f.function}** | {FUNCTION_PLAIN[f.function]} | {fmt_score(f.last_quarter)} | **{fmt_score(f.current)}** "
          f"| {fmt_score(f.target)} | {fmt_score(f.gap)} | {f.gap_label} | {f.trend} |")
    w("")
    w("![NIST CSF 2.0 maturity by function: last quarter, this quarter and target](charts/csf-current-vs-target.png)")
    w("")
    w("**Largest category gaps and why**")
    w("")
    for cat in sorted(pack.csf, key=lambda x: (-x.gap, x.category_id))[:4]:
        w(f"- **{cat.category_id} {cat.name}** — {fmt_score(cat.current)} against {fmt_score(cat.target)}. {cat.evidence}")
    w("")

    # ---- 3. Risks -----------------------------------------------------------
    w("## 3. Top risks")
    w("")
    w(f"These are the {len(pack.risks)} risks that could hurt {org['short_name']} most. "
      f"Each is scored from 1 to 25 (likelihood × impact) before controls (inherent) and with today's controls "
      f"(residual). **{plural(len(above), 'risk')} {'is' if len(above) == 1 else 'are'} above the appetite the board approved.**")
    w("")
    w("| # | Risk | Owner | Inherent | Residual | Appetite | Trend | Treatment |")
    w("|---|---|---|---|---|---|---|---|")
    for r in ranked:
        appetite = f"≤ {r.appetite} — {'**above**' if r.above_appetite else 'within'}"
        w(f"| {r.id} | {md_escape(r.title)} | {r.owner} | {r.inherent_score} {r.inherent_band} "
          f"| {BAND_ICON[r.residual_band]} **{r.residual_score} {r.residual_band}** | {appetite} "
          f"| {r.trend} | {r.treatment_status} |")
    w("")
    w("**Residual-risk heat map** (where each risk sits today)")
    w("")
    cells = heat_cells(pack.risks)
    header = " | ".join(f"{n} {LIKELIHOOD_SHORT[n]}" for n in range(1, 6))
    w(f"| Impact ↓ · Likelihood → | {header} |")
    w("|---|---|---|---|---|---|")
    for imp in range(5, 0, -1):
        row = []
        for lik in range(1, 6):
            band = BAND_ICON[_band(pack, lik * imp)]
            ids = ", ".join(cells.get((lik, imp), []))
            row.append(f"{band} **{ids}**" if ids else band)
        w(f"| **{imp} {IMPACT_SHORT[imp]}** | " + " | ".join(row) + " |")
    w("")
    w("🟩 Low (1–4) · 🟨 Medium (5–9) · 🟧 High (10–16) · 🟥 Critical (17–25). "
      "The same map as a chart: [`charts/residual-risk-heatmap.png`](charts/residual-risk-heatmap.png).")
    w("")
    w("**Risks that need the board's attention**")
    w("")
    for r in above:
        w(f"- **{r.id} {r.title}** ({r.residual_score}, above appetite of {r.appetite}). {r.business_impact} "
          f"*Next step:* {r.next_milestone} — {r.treatment_status.lower()}, due {fmt_date(r.milestone_due)}.")
    moved = [r for r in ranked if r.trend in ("Worsening", "New") and not r.above_appetite]
    for r in moved:
        w(f"- **{r.id} {r.title}** ({r.trend.lower()}, {r.residual_score}, within appetite). {r.business_impact}")
    no_kri = risks_without_kri(pack)
    if no_kri:
        w("")
        w("*Not yet measured:* " + ", ".join(f"{r.id}" for r in no_kri)
          + " has no key risk indicator. One will be proposed in next quarter's pack.")
    w("")

    # ---- 4. KRIs ------------------------------------------------------------
    w("## 4. Key risk indicators")
    w("")
    w(f"{len(pack.kris)} indicators tell us early whether a risk is growing. "
      f"This quarter: **{kc['Green']} green, {kc['Amber']} amber, {kc['Red']} red.** "
      f"Green means at or better than target; red means past the limit the board tolerates.")
    w("")
    w("| Status | Indicator | Now | Last quarter | Green / red at | Trend | Owner |")
    w("|---|---|---|---|---|---|---|")
    for k in sorted(pack.kris, key=lambda x: ({"Red": 0, "Amber": 1, "Green": 2}[x.rag], x.id)):
        op_g = "≤" if k.direction == "higher_is_worse" else "≥"
        op_r = ">" if k.direction == "higher_is_worse" else "<"
        w(f"| {RAG_ICON[k.rag]} {k.rag} | {md_escape(k.name)} | **{k.fmt(k.current)}** | {k.fmt(k.last_quarter)} "
          f"| {op_g} {k.fmt(k.green_threshold)} / {op_r} {k.fmt(k.red_threshold)} | {k.trend} | {k.owner} |")
    w("")
    if red_kris:
        w("**Why the red indicators matter**")
        w("")
        for k in red_kris:
            w(f"- **{k.name}: {k.fmt(k.current)}.** {k.meaning} Linked to {', '.join(k.linked_risks)}.")
        w("")

    # ---- 5. Calendar --------------------------------------------------------
    w("## 5. Regulatory and assurance calendar")
    w("")
    w(f"The next twelve months of audits, assessments, tests and exercises "
      f"({fmt_date(rep['calendar_window_start'])} to {fmt_date(rep['calendar_window_end'])}).")
    w("")
    w("| When | Activity | Why | Owner | Status | Note for the board |")
    w("|---|---|---|---|---|---|")
    for c in pack.calendar:
        w(f"| {fmt_range(c.start, c.end)} | {md_escape(c.activity)} | {md_escape(c.driver)} | {c.owner} "
          f"| {c.status} | {md_escape(c.board_note)} |")
    w("")

    # ---- 6. Decisions -------------------------------------------------------
    w("## 6. Decisions required")
    w("")
    for d in pack.decisions:
        w(f"### {d.id}. {d.title}")
        w("")
        w(f"*{d.type} · linked to {', '.join(d.linked_risks)} · decision needed by {fmt_date(d.decide_by)}*")
        w("")
        w(d.context)
        w("")
        w("| Option | What it means | Cost | Effect on risk |")
        w("|---|---|---|---|")
        for o in d.options:
            name = f"**{o.id}. {o.label}** (recommended)" if o.id == d.recommendation else f"{o.id}. {o.label}"
            w(f"| {md_escape(name)} | {md_escape(o.description)} | {fmt_cost(o.cost_min, o.cost_max, cur)} "
              f"| {md_escape(o.effect)} |")
        w("")
        w(f"**Recommendation: option {d.recommendation}.** {d.rationale}")
        w("")
        w(f"**If the board declines:** {d.if_declined}")
        w("")
        w(f"> **Proposed resolution.** {d.proposed_resolution}")
        w("")

    # ---- Appendix -----------------------------------------------------------
    w("## Appendix: how to read this pack")
    w("")
    w("| Score | Likelihood | Impact |")
    w("|---|---|---|")
    for n in range(1, 6):
        w(f"| {n} | {pack.config['likelihood_scale'][n]} | {pack.config['impact_scale'][n]} |")
    w("")
    w("- **Risk score** = likelihood × impact, 1 to 25. Bands: Low 1–4, Medium 5–9, High 10–16, Critical 17–25.")
    w("- **Appetite** is the highest residual score the board accepts for each category: "
      + ", ".join(f"{k} {v}" for k, v in pack.config["appetite"].items()) + ".")
    w("- **Maturity** 0–5: " + "; ".join(f"{n} {t.split(' - ')[0]}" for n, t in pack.config["maturity_scale"].items())
      + ".")
    w(f"- **Trends** compare with last quarter. A KRI change smaller than "
      f"{round(pack.config['kri_stable_share'] * 100)}% of the gap between its green and red thresholds is shown as stable.")
    w("- Full method: [`docs/method.md`](../docs/method.md).")
    w("")
    return "\n".join(out)


def _band(pack: Pack, score: int) -> str:
    return band_for(score, pack.config["bands"])


# ------------------------------------------------------------------ workbook


def render_workbook(pack: Pack, path: Path) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    rep, org = pack.report, pack.org
    cur = rep["currency"]
    wb = Workbook()
    fixed = datetime(*XL_TIMESTAMP)
    wb.properties.creator = "executive-risk-pack"
    wb.properties.lastModifiedBy = "executive-risk-pack"
    wb.properties.title = f"{org['name']} — {rep['title']} — {rep['quarter']}"
    wb.properties.created = fixed
    wb.properties.modified = fixed

    head_font = Font(bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor=XL_HEADER)
    wrap = Alignment(wrap_text=True, vertical="top")
    thin = Side(style="thin", color="D9D9D9")
    box = Border(left=thin, right=thin, top=thin, bottom=thin)

    def fill(hex_colour: str) -> PatternFill:
        return PatternFill("solid", fgColor=hex_colour)

    def sheet(title: str, heading: str, columns: list[tuple[str, int]], first: bool = False):
        ws = wb.active if first else wb.create_sheet()
        ws.title = title
        ws["A1"] = heading
        ws["A1"].font = Font(bold=True, size=14)
        ws["A2"] = f"{org['name']} · {rep['quarter']} · {rep['classification']}"
        ws["A2"].font = Font(italic=True, color="595959")
        for i, (name, width) in enumerate(columns, start=1):
            cell = ws.cell(row=4, column=i, value=name)
            cell.font, cell.fill, cell.alignment, cell.border = head_font, head_fill, wrap, box
            ws.column_dimensions[get_column_letter(i)].width = width
        ws.freeze_panes = "A5"
        return ws

    def row(ws, values: list, fills: dict[int, str] | None = None, bold: set[int] | None = None) -> None:
        r = ws.max_row + 1
        for i, v in enumerate(values, start=1):
            cell = ws.cell(row=r, column=i, value=v)
            cell.alignment, cell.border = wrap, box
            if fills and i in fills:
                cell.fill = fill(fills[i])
            if bold and i in bold:
                cell.font = Font(bold=True)

    # Summary
    ws = sheet("Summary", f"{rep['title']} — {rep['quarter']}", [("Measure", 48), ("Last quarter", 16),
                                                                    ("This quarter", 16), ("Note", 60)], first=True)
    kc = pack.kri_counts()
    trends = pack.risk_trend_counts()
    above = sum(1 for r in pack.risks if r.above_appetite)
    row(ws, ["Security maturity (NIST CSF 2.0, 0-5)", pack.posture_last_quarter, pack.posture_current,
             f"Target {pack.posture_target} by {rep['target_profile_by']}; {pack.posture_pct_of_target}% of target"])
    row(ws, ["Top risks above appetite", last_quarter_above_appetite(pack), above, f"of {len(pack.risks)} top risks"])
    row(ws, ["KRIs at red", last_quarter_red_kris(pack), kc["Red"],
             f"{kc['Green']} green, {kc['Amber']} amber, {kc['Red']} red"])
    row(ws, ["Top risks: better / worse / unchanged / new", None,
             f"{trends['Improving']} / {trends['Worsening']} / {trends['Stable']} / {trends['New']}", ""])
    ws.cell(row=ws.max_row + 2, column=1, value="Three things to remember").font = Font(bold=True)
    for line in pack.config["narrative"]:
        ws.cell(row=ws.max_row + 1, column=1, value=line)
    ws.cell(row=ws.max_row + 2, column=1, value="Decisions requested").font = Font(bold=True)
    for d in pack.decisions:
        o = d.recommended
        ws.cell(row=ws.max_row + 1, column=1, value=f"{d.id}. {d.title}")
        ws.cell(row=ws.max_row, column=3, value=f"Option {o.id}")
        ws.cell(row=ws.max_row, column=4, value=fmt_cost(o.cost_min, o.cost_max, cur))
    ws.cell(row=ws.max_row + 2, column=1,
            value="Sample workbook. The organisation and every figure are fictional.").font = Font(italic=True)

    # CSF profile
    ws = sheet("CSF Profile", "NIST CSF 2.0 maturity (0-5): current vs target",
               [("Function", 12), ("Category", 10), ("Category name", 40), ("Last quarter", 12), ("Current", 10),
                ("Target", 10), ("Gap", 8), ("Evidence", 80)])
    for f in pack.functions:
        row(ws, [f.function, "ALL", f"Function average — {f.gap_label}, {f.trend.lower()}", f.last_quarter,
                 f.current, f.target, f.gap, FUNCTION_PLAIN[f.function]], bold={1, 2, 3, 5})
        for cat in (x for x in pack.csf if x.function == f.function):
            row(ws, [cat.function, cat.category_id, cat.name, cat.last_quarter, cat.current, cat.target,
                     cat.gap, cat.evidence])
    ws.auto_filter.ref = f"A4:H{ws.max_row}"

    # Risks
    ws = sheet("Top Risks", "Top risks: inherent and residual scores",
               [("ID", 6), ("Risk", 36), ("Business impact", 60), ("Category", 14), ("Owner", 26),
                ("Inh. L", 7), ("Inh. I", 7), ("Inherent", 9), ("Inh. band", 10), ("Res. L", 7), ("Res. I", 7),
                ("Residual", 9), ("Res. band", 10), ("Last quarter", 9), ("Trend", 11), ("Appetite", 9),
                ("Within appetite", 10), ("Treatment", 10), ("Status", 11), ("Next milestone", 44), ("Due", 11),
                ("CSF function", 11), ("KRIs", 22)])
    for r in pack.risks_by_residual():
        row(ws, [r.id, r.title, r.business_impact, r.category, r.owner, r.inherent_likelihood, r.inherent_impact,
                 r.inherent_score, r.inherent_band, r.residual_likelihood, r.residual_impact, r.residual_score,
                 r.residual_band, r.last_q_score, r.trend, r.appetite, "No" if r.above_appetite else "Yes",
                 r.treatment, r.treatment_status, r.next_milestone, r.milestone_due.isoformat(), r.csf_function,
                 ", ".join(r.linked_kris)],
            fills={9: XL_BAND[r.inherent_band], 13: XL_BAND[r.residual_band],
                   17: XL_RAG["Red"] if r.above_appetite else XL_RAG["Green"]}, bold={12})
    ws.auto_filter.ref = f"A4:W{ws.max_row}"

    # Heat map
    ws = sheet("Heat Map", "Residual-risk heat map (likelihood x impact)",
               [("Impact \\ Likelihood", 22)] + [(f"{n} {LIKELIHOOD_SHORT[n]}", 16) for n in range(1, 6)])
    cells = heat_cells(pack.risks)
    for imp in range(5, 0, -1):
        values: list = [f"{imp} {IMPACT_SHORT[imp]}"]
        fills: dict[int, str] = {}
        for lik in range(1, 6):
            values.append(", ".join(cells.get((lik, imp), [])) or None)
            fills[lik + 1] = XL_BAND[_band(pack, lik * imp)]
        row(ws, values, fills=fills, bold={1, 2, 3, 4, 5, 6})
        ws.row_dimensions[ws.max_row].height = 34
    ws.cell(row=ws.max_row + 2, column=1, value="Bands: Low 1-4, Medium 5-9, High 10-16, Critical 17-25.")

    # KRIs
    ws = sheet("KRIs", "Key risk indicators with RAG status",
               [("ID", 8), ("Indicator", 44), ("What it tells the board", 56), ("Unit", 7), ("Direction", 15),
                ("Green at", 9), ("Red beyond", 10), ("Last quarter", 11), ("Current", 9), ("RAG", 8),
                ("Last RAG", 9), ("Trend", 11), ("Owner", 30), ("CSF function", 11), ("Risks", 12)])
    for k in pack.kris:
        row(ws, [k.id, k.name, k.meaning, k.unit, k.direction, k.green_threshold, k.red_threshold, k.last_quarter,
                 k.current, k.rag, k.last_rag, k.trend, k.owner, k.csf_function, ", ".join(k.linked_risks)],
            fills={10: XL_RAG[k.rag], 11: XL_RAG[k.last_rag]}, bold={9, 10})
    ws.auto_filter.ref = f"A4:O{ws.max_row}"

    # Calendar
    ws = sheet("Calendar", "Regulatory and assurance calendar (next 12 months)",
               [("Start", 11), ("End", 11), ("Activity", 60), ("Type", 12), ("Driver", 40), ("Owner", 30),
                ("Status", 14), ("Note for the board", 60)])
    for c in pack.calendar:
        row(ws, [c.start.isoformat(), c.end.isoformat(), c.activity, c.type, c.driver, c.owner, c.status,
                 c.board_note or None])
    ws.auto_filter.ref = f"A4:H{ws.max_row}"

    # Decisions
    ws = sheet("Decisions", "Decisions required from the board",
               [("ID", 6), ("Type", 16), ("Decision", 44), ("Option", 7), ("Option label", 36),
                ("What it means", 60), (f"Cost min ({cur})", 13), (f"Cost max ({cur})", 13), ("Effect on risk", 50),
                ("Recommended", 12)])
    for d in pack.decisions:
        for o in d.options:
            rec = o.id == d.recommendation
            row(ws, [d.id, d.type, d.title, o.id, o.label, o.description, o.cost_min, o.cost_max, o.effect,
                     "Yes" if rec else None], fills={10: XL_RAG["Green"]} if rec else None,
                bold={4, 5} if rec else None)
            ws.cell(row=ws.max_row, column=7).number_format = "#,##0"
            ws.cell(row=ws.max_row, column=8).number_format = "#,##0"
        row(ws, [d.id, "Rationale", d.rationale])
        row(ws, [d.id, "If declined", d.if_declined])
        row(ws, [d.id, "Resolution", d.proposed_resolution], bold={3})

    # Scales
    ws = sheet("Scales", "Scales, bands and appetite", [("Item", 22), ("Level", 8), ("Meaning", 100)])
    for n in range(1, 6):
        row(ws, ["Likelihood", n, pack.config["likelihood_scale"][n]])
    for n in range(1, 6):
        row(ws, ["Impact", n, pack.config["impact_scale"][n]])
    for upper, label in pack.config["bands"]:
        row(ws, ["Risk band", upper, f"{label}: score up to {upper}"], fills={3: XL_BAND[label]})
    for n, text in pack.config["maturity_scale"].items():
        row(ws, ["Maturity", n, text])
    for cat, value in pack.config["appetite"].items():
        row(ws, ["Appetite", value, f"{cat}: highest residual score accepted"])
    row(ws, ["KRI RAG", None, "Green at or better than the green threshold; red worse than the red threshold; "
                              "amber in between."])

    buffer = io.BytesIO()
    wb.save(buffer)
    _rezip_deterministic(buffer.getvalue(), path)


def _rezip_deterministic(blob: bytes, path: Path) -> None:
    """Rewrite the .xlsx so the bytes depend only on the content.

    openpyxl stamps each zip entry with the wall clock and the host OS, and writes the
    save time into docProps/core.xml. Entries are stored uncompressed so the result does
    not depend on the zlib build either; the file is small enough for that not to matter.
    """
    iso = "{:04d}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}Z".format(*XL_TIMESTAMP)
    src = zipfile.ZipFile(io.BytesIO(blob))
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as dst:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename == "docProps/core.xml":
                data = re.sub(rb"(<dcterms:modified[^>]*>)[^<]*(</dcterms:modified>)",
                              lambda m: m.group(1) + iso.encode() + m.group(2), data)
            new = zipfile.ZipInfo(info.filename, date_time=XL_TIMESTAMP)
            new.compress_type = zipfile.ZIP_STORED
            new.create_system = 3
            new.external_attr = 0o600 << 16
            dst.writestr(new, data)


# ------------------------------------------------------------------ charts


def chart_data(pack: Pack) -> dict:
    return {
        "quarter": pack.report["quarter"],
        "csf_functions": [
            {"function": f.function, "last_quarter": f.last_quarter, "current": f.current, "target": f.target}
            for f in pack.functions
        ],
        "residual_heatmap": [
            {"id": r.id, "likelihood": r.residual_likelihood, "impact": r.residual_impact,
             "score": r.residual_score, "band": r.residual_band}
            for r in sorted(pack.risks, key=lambda x: x.id)
        ],
    }


def _tint(hex_colour: str, share: float) -> str:
    """Mix a colour with white; share=0 keeps the colour, share=1 is white."""
    rgb = [int(hex_colour[i:i + 2], 16) for i in (1, 3, 5)]
    mixed = [round(c + (255 - c) * share) for c in rgb]
    return "#" + "".join(f"{c:02x}" for c in mixed)


def render_charts(pack: Pack, out_dir: Path) -> list[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch, Rectangle

    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": GRID, "axes.labelcolor": INK_2,
        "xtick.color": INK_2, "ytick.color": INK, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
    })
    meta = {"Software": None}
    written: list[Path] = []

    # 1. CSF maturity by function --------------------------------------------
    fns = list(reversed(pack.functions))  # Govern at the top
    fig, ax = plt.subplots(figsize=(8, 4.4), dpi=150)
    h = 0.34
    for i, f in enumerate(fns):
        ax.barh(i + h / 2 + 0.02, f.last_quarter, height=h, color=BLUE_LIGHT, zorder=2)
        ax.barh(i - h / 2 - 0.02, f.current, height=h, color=BLUE, zorder=2)
        ax.plot([f.target, f.target], [i - 0.44, i + 0.44], color=INK, linewidth=2.2, zorder=3,
                solid_capstyle="butt")
        ax.text(f.current + 0.05, i - h / 2 - 0.02, fmt_score(f.current), va="center", ha="left",
                fontsize=8.5, color=INK, zorder=4)
    ax.set_yticks(range(len(fns)), [f.function for f in fns])
    ax.set_xlim(0, 5)
    ax.set_xticks(range(6), ["0\nAbsent", "1\nAd hoc", "2\nDeveloping", "3\nDefined", "4\nManaged", "5\nOptimised"])
    ax.grid(axis="x", color=GRID, linewidth=0.8, zorder=0)
    ax.tick_params(length=0)
    for side in ("top", "right", "bottom"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color("#c3c2b7")
    ax.set_title(f"NIST CSF 2.0 maturity by function — {pack.report['quarter']}", loc="left", fontsize=11,
                 color=INK, pad=26)
    ax.legend(handles=[Patch(color=BLUE_LIGHT, label="Last quarter"), Patch(color=BLUE, label="This quarter"),
                       plt.Line2D([0], [0], color=INK, linewidth=2.2, label=f"Target ({pack.report['target_profile_by']})")],
              loc="lower left", bbox_to_anchor=(0, 1.0), ncol=3, frameon=False, fontsize=8.5, borderaxespad=0.3)
    fig.tight_layout()
    p = out_dir / "csf-current-vs-target.png"
    fig.savefig(p, metadata=meta)
    plt.close(fig)
    written.append(p)

    # 2. Residual-risk heat map ----------------------------------------------
    cells = heat_cells(pack.risks)
    fig, ax = plt.subplots(figsize=(7, 5.6), dpi=150)
    gap = 0.03
    for lik in range(1, 6):
        for imp in range(1, 6):
            label = _band(pack, lik * imp)
            ids = cells.get((lik, imp), [])
            face = _tint(BAND_COLOUR[label], 0.15 if ids else 0.62)
            ax.add_patch(Rectangle((lik - 0.5 + gap, imp - 0.5 + gap), 1 - 2 * gap, 1 - 2 * gap,
                                   facecolor=face, edgecolor="none"))
            ax.text(lik + 0.42, imp - 0.42, str(lik * imp), ha="right", va="bottom", fontsize=7, color=INK_2)
            if ids:
                ax.text(lik, imp + 0.02, "\n".join(ids), ha="center", va="center", fontsize=10,
                        fontweight="bold", color=INK, linespacing=1.25)
    ax.set_xlim(0.5, 5.5)
    ax.set_ylim(0.5, 5.5)
    ax.set_aspect("equal")
    ax.set_xticks(range(1, 6), [f"{n}\n{LIKELIHOOD_SHORT[n]}" for n in range(1, 6)])
    ax.set_yticks(range(1, 6), [f"{IMPACT_SHORT[n]} {n}" for n in range(1, 6)])
    ax.tick_params(length=0)
    for side in ax.spines.values():
        side.set_visible(False)
    ax.set_xlabel("Likelihood", color=INK_2)
    ax.set_ylabel("Impact", color=INK_2)
    ax.set_title(f"Residual risk — {pack.report['quarter']} (top {len(pack.risks)} risks)", loc="left",
                 fontsize=11, color=INK, pad=26)
    ax.legend(handles=[Patch(color=_tint(BAND_COLOUR[b], 0.15), label=f"{b} ({lo}–{hi})") for b, lo, hi in
                       (("Low", 1, 4), ("Medium", 5, 9), ("High", 10, 16), ("Critical", 17, 25))],
              loc="lower left", bbox_to_anchor=(0, 1.0), ncol=4, frameon=False, fontsize=8.5, borderaxespad=0.3)
    fig.tight_layout()
    p = out_dir / "residual-risk-heatmap.png"
    fig.savefig(p, metadata=meta)
    plt.close(fig)
    written.append(p)
    return written


# ------------------------------------------------------------------ main


def build(data_dir: Path, out_dir: Path, charts: bool = True) -> list[Path]:
    pack = load(data_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    chart_dir = out_dir / "charts"
    chart_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    md = out_dir / "board-pack.md"
    md.write_text(render_markdown(pack), encoding="utf-8", newline="\n")
    written.append(md)

    xlsx = out_dir / "board-pack.xlsx"
    render_workbook(pack, xlsx)
    written.append(xlsx)

    cj = chart_dir / "chart-data.json"
    cj.write_text(json.dumps(chart_data(pack), indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    written.append(cj)

    if charts:
        try:
            written.extend(render_charts(pack, chart_dir))
        except ImportError:
            print("warning: matplotlib is not installed; PNG charts were not regenerated "
                  "(pip install matplotlib)", file=sys.stderr)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the quarterly executive cyber-risk pack.")
    parser.add_argument("--data", type=Path, default=DATA_DIR, help="folder with the data files (default: data/)")
    parser.add_argument("--out", type=Path, default=ROOT / "pack", help="output folder (default: pack/)")
    parser.add_argument("--no-charts", action="store_true", help="skip the PNG charts")
    parser.add_argument("-q", "--quiet", action="store_true", help="print nothing on success")
    args = parser.parse_args(argv)
    try:
        written = build(args.data, args.out, charts=not args.no_charts)
    except DataError as exc:
        print(f"{len(exc.problems)} data problem(s):", file=sys.stderr)
        for p in exc.problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    if not args.quiet:
        for p in written:
            try:
                shown = p.resolve().relative_to(ROOT)
            except ValueError:
                shown = p
            print(f"wrote {shown.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
