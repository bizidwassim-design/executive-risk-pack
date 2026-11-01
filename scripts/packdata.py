#!/usr/bin/env python3
"""Load, validate and score the data behind the executive risk pack.

The files in ``data/`` are the single source of truth. This module reads them,
reports every problem it finds in one pass, and computes everything the board
pack shows: risk scores and bands, appetite status, trends, KRI RAG status,
NIST CSF 2.0 function averages and gaps.

Nothing here writes files. ``build_pack.py`` renders; ``validate_data.py`` checks.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

CSF_FUNCTIONS: list[tuple[str, str]] = [
    ("Govern", "GV"),
    ("Identify", "ID"),
    ("Protect", "PR"),
    ("Detect", "DE"),
    ("Respond", "RS"),
    ("Recover", "RC"),
]
TREATMENTS = {"Mitigate", "Transfer", "Accept", "Avoid"}
TREATMENT_STATUSES = {"Not started", "On track", "At risk", "Delayed", "Complete"}
KRI_DIRECTIONS = {"higher_is_worse", "lower_is_worse"}
CALENDAR_TYPES = {"Assessment", "Audit", "Regulatory", "Test", "Exercise"}
CALENDAR_STATUSES = {"Planned", "Booked", "In preparation", "Conditional", "Done"}
DECISION_TYPES = {"Risk acceptance", "Budget", "Policy exception"}
MAX_TOP_RISKS = 10


class DataError(Exception):
    """Raised with every validation problem found, not just the first."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("\n".join(problems))
        self.problems = problems


# --------------------------------------------------------------------------- model


@dataclass
class CsfCategory:
    function: str
    category_id: str
    name: str
    current: float
    target: float
    last_quarter: float
    evidence: str

    @property
    def gap(self) -> float:
        return round(self.target - self.current, 2)


@dataclass
class FunctionScore:
    function: str
    current: float
    target: float
    last_quarter: float
    gap: float
    gap_label: str
    trend: str


@dataclass
class Risk:
    id: str
    title: str
    business_impact: str
    category: str
    owner: str
    inherent_likelihood: int
    inherent_impact: int
    residual_likelihood: int
    residual_impact: int
    last_q_likelihood: int | None
    last_q_impact: int | None
    treatment: str
    treatment_status: str
    next_milestone: str
    milestone_due: date
    csf_function: str
    linked_kris: list[str]
    appetite: int = 0
    bands: list[tuple[int, str]] = field(default_factory=list, repr=False)

    @property
    def inherent_score(self) -> int:
        return self.inherent_likelihood * self.inherent_impact

    @property
    def residual_score(self) -> int:
        return self.residual_likelihood * self.residual_impact

    @property
    def last_q_score(self) -> int | None:
        if self.last_q_likelihood is None or self.last_q_impact is None:
            return None
        return self.last_q_likelihood * self.last_q_impact

    @property
    def inherent_band(self) -> str:
        return band_for(self.inherent_score, self.bands)

    @property
    def residual_band(self) -> str:
        return band_for(self.residual_score, self.bands)

    @property
    def trend(self) -> str:
        return risk_trend(self.residual_score, self.last_q_score)

    @property
    def above_appetite(self) -> bool:
        return self.residual_score > self.appetite


@dataclass
class Kri:
    id: str
    name: str
    meaning: str
    unit: str
    direction: str
    green_threshold: float
    red_threshold: float
    current: float
    last_quarter: float
    decimals: int
    owner: str
    csf_function: str
    linked_risks: list[str]
    stable_share: float = 0.10

    @property
    def rag(self) -> str:
        return kri_rag(self.current, self.green_threshold, self.red_threshold, self.direction)

    @property
    def last_rag(self) -> str:
        return kri_rag(self.last_quarter, self.green_threshold, self.red_threshold, self.direction)

    @property
    def trend(self) -> str:
        return kri_trend(
            self.current, self.last_quarter, self.green_threshold, self.red_threshold,
            self.direction, self.stable_share,
        )

    def fmt(self, value: float) -> str:
        text = f"{value:.{self.decimals}f}"
        return f"{text}%" if self.unit == "%" else text


@dataclass
class CalendarItem:
    start: date
    end: date
    activity: str
    type: str
    driver: str
    owner: str
    status: str
    board_note: str


@dataclass
class Option:
    id: str
    label: str
    description: str
    cost_min: int
    cost_max: int
    effect: str


@dataclass
class Decision:
    id: str
    type: str
    title: str
    linked_risks: list[str]
    decide_by: date
    context: str
    options: list[Option]
    recommendation: str
    rationale: str
    if_declined: str
    proposed_resolution: str

    @property
    def recommended(self) -> Option:
        return next(o for o in self.options if o.id == self.recommendation)


@dataclass
class Pack:
    org: dict[str, Any]
    report: dict[str, Any]
    config: dict[str, Any]
    csf: list[CsfCategory]
    functions: list[FunctionScore]
    risks: list[Risk]
    kris: list[Kri]
    calendar: list[CalendarItem]
    decisions: list[Decision]

    # ---- headline figures used by every renderer ---------------------------

    @property
    def posture_current(self) -> float:
        return round1(sum(f.current for f in self.functions) / len(self.functions))

    @property
    def posture_target(self) -> float:
        return round1(sum(f.target for f in self.functions) / len(self.functions))

    @property
    def posture_last_quarter(self) -> float:
        return round1(sum(f.last_quarter for f in self.functions) / len(self.functions))

    @property
    def posture_pct_of_target(self) -> int:
        return round(100 * self.posture_current / self.posture_target)

    def risks_by_residual(self) -> list[Risk]:
        return sorted(self.risks, key=lambda r: (-r.residual_score, -r.inherent_score, r.id))

    def kri_counts(self) -> dict[str, int]:
        counts = {"Red": 0, "Amber": 0, "Green": 0}
        for k in self.kris:
            counts[k.rag] += 1
        return counts

    def risk_trend_counts(self) -> dict[str, int]:
        counts = {"Worsening": 0, "Stable": 0, "Improving": 0, "New": 0}
        for r in self.risks:
            counts[r.trend] += 1
        return counts

    def look_ahead(self) -> list[CalendarItem]:
        start: date = self.report["board_meeting"]
        days = int(self.report["look_ahead_days"])
        return [c for c in self.calendar if 0 <= (c.start - start).days <= days]


# ------------------------------------------------------------------ pure scoring


def round1(value: float) -> float:
    """Round to one decimal, halves away from zero (3.25 -> 3.3), as people expect on paper.

    Python's round() uses banker's rounding on binary floats, which would print 3.25 as 3.2.
    Function scores are rounded once, here, so every table, chart and gap agrees.
    """
    return float(Decimal(repr(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def band_for(score: int, bands: list[tuple[int, str]]) -> str:
    """Return the label of the first band whose upper bound is >= score."""
    for upper, label in bands:
        if score <= upper:
            return label
    raise ValueError(f"score {score} is above every band")


def risk_trend(current: int, last: int | None) -> str:
    """Residual score now vs last quarter. A lower score is an improvement."""
    if last is None:
        return "New"
    if current < last:
        return "Improving"
    if current > last:
        return "Worsening"
    return "Stable"


def kri_rag(value: float, green: float, red: float, direction: str) -> str:
    """Green at or better than the green threshold; Red worse than the red threshold.

    For ``higher_is_worse`` "better" means lower; for ``lower_is_worse`` it means higher.
    Anything between the two thresholds, including the red threshold itself, is Amber.
    """
    if direction == "higher_is_worse":
        if value <= green:
            return "Green"
        if value > red:
            return "Red"
        return "Amber"
    if direction == "lower_is_worse":
        if value >= green:
            return "Green"
        if value < red:
            return "Red"
        return "Amber"
    raise ValueError(f"unknown direction {direction!r}")


def kri_trend(current: float, last: float, green: float, red: float,
              direction: str, stable_share: float) -> str:
    """Improving / Worsening / Stable, judged against the width of the amber band.

    A move smaller than ``stable_share`` x |red - green| is noise, not a trend.
    """
    delta = round(current - last, 9)  # 5.6 - 5.0 must be 0.6, not 0.5999...
    if abs(delta) < round(stable_share * abs(red - green), 9) or delta == 0:
        return "Stable"
    better = delta < 0 if direction == "higher_is_worse" else delta > 0
    return "Improving" if better else "Worsening"


def function_trend(current: float, last: float) -> str:
    if current - last >= 0.05:
        return "Improving"
    if last - current >= 0.05:
        return "Worsening"
    return "Stable"


def gap_label(gap: float, gap_bands: list[tuple[float, str]]) -> str:
    for upper, label in gap_bands:
        if gap <= upper + 1e-9:
            return label
    return gap_bands[-1][1]


# ------------------------------------------------------------------------ loading


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(fh)]


def _as_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value).strip())


def _split(value: str) -> list[str]:
    return [p.strip() for p in value.split(";") if p.strip()]


class _Collector:
    """Accumulates problems so the user sees all of them at once."""

    def __init__(self) -> None:
        self.problems: list[str] = []

    def add(self, where: str, message: str) -> None:
        self.problems.append(f"{where}: {message}")

    def number(self, where: str, field_name: str, raw: str, *, integer: bool = False,
               lo: float | None = None, hi: float | None = None,
               required: bool = True) -> float | None:
        if raw == "":
            if required:
                self.add(where, f"{field_name} is empty")
            return None
        try:
            value = int(raw) if integer else float(raw)
        except ValueError:
            self.add(where, f"{field_name}={raw!r} is not a{'n integer' if integer else ' number'}")
            return None
        if lo is not None and value < lo or hi is not None and value > hi:
            self.add(where, f"{field_name}={raw} is outside {lo:g}-{hi:g}")
            return None
        return value

    def text(self, where: str, field_name: str, raw: Any) -> str:
        value = "" if raw is None else str(raw).strip()
        if not value:
            self.add(where, f"{field_name} is empty")
        return value

    def date(self, where: str, field_name: str, raw: Any) -> date | None:
        try:
            return _as_date(raw)
        except (TypeError, ValueError):
            self.add(where, f"{field_name}={raw!r} is not an ISO date (YYYY-MM-DD)")
            return None


def load(data_dir: Path = DATA_DIR) -> Pack:
    """Read and validate every data file. Raises DataError listing all problems."""
    c = _Collector()

    with (data_dir / "organisation.yaml").open(encoding="utf-8") as fh:
        org_file = yaml.safe_load(fh) or {}
    with (data_dir / "decisions.yaml").open(encoding="utf-8") as fh:
        dec_file = yaml.safe_load(fh) or {}

    org = org_file.get("organisation") or {}
    report = dict(org_file.get("report") or {})
    for key in ("name", "sector", "headquarters", "staff"):
        if not org.get(key):
            c.add("organisation.yaml", f"organisation.{key} is missing")
    for key in ("title", "quarter", "period_start", "period_end", "board_meeting", "prepared_by",
                "currency", "look_ahead_days", "calendar_window_start", "calendar_window_end"):
        if report.get(key) in (None, ""):
            c.add("organisation.yaml", f"report.{key} is missing")
    for key in ("period_start", "period_end", "board_meeting", "calendar_window_start", "calendar_window_end"):
        if report.get(key) not in (None, ""):
            report[key] = c.date("organisation.yaml", f"report.{key}", report[key])

    bands = sorted((int(b["max_score"]), str(b["label"])) for b in org_file.get("risk_bands") or [])
    if not bands or bands[-1][0] != 25:
        c.add("organisation.yaml", "risk_bands must end with max_score 25")
    gap_bands = sorted((float(b["max_gap"]), str(b["label"])) for b in org_file.get("gap_bands") or [])
    if not gap_bands:
        c.add("organisation.yaml", "gap_bands is missing")
    appetite: dict[str, int] = {str(k): int(v) for k, v in (org_file.get("risk_appetite") or {}).items()}
    for cat, value in appetite.items():
        if not 1 <= value <= 25:
            c.add("organisation.yaml", f"risk_appetite.{cat}={value} is outside 1-25")
    stable_share = float(org_file.get("kri_stable_share", 0.10))
    for scale in ("likelihood_scale", "impact_scale"):
        if sorted((org_file.get(scale) or {}).keys()) != [1, 2, 3, 4, 5]:
            c.add("organisation.yaml", f"{scale} must define levels 1 to 5")
    if sorted((org_file.get("maturity_scale") or {}).keys()) != [0, 1, 2, 3, 4, 5]:
        c.add("organisation.yaml", "maturity_scale must define levels 0 to 5")

    # ---- CSF profile --------------------------------------------------------
    csf: list[CsfCategory] = []
    seen_cat: set[str] = set()
    prefixes = dict(CSF_FUNCTIONS)
    for n, row in enumerate(_read_csv(data_dir / "csf-profile.csv"), start=2):
        where = f"csf-profile.csv line {n}"
        fn = row.get("function", "")
        cid = row.get("category_id", "")
        if fn not in prefixes:
            c.add(where, f"function {fn!r} is not one of {', '.join(prefixes)}")
        elif not cid.startswith(prefixes[fn] + "."):
            c.add(where, f"category {cid!r} does not belong to {fn} ({prefixes[fn]}.*)")
        if cid in seen_cat:
            c.add(where, f"duplicate category {cid}")
        seen_cat.add(cid)
        scores = [c.number(where, f, row.get(f, ""), lo=0, hi=5) for f in ("current", "target", "last_quarter")]
        name = c.text(where, "category_name", row.get("category_name"))
        evidence = c.text(where, "evidence", row.get("evidence"))
        if None not in scores:
            csf.append(CsfCategory(fn, cid, name, scores[0], scores[1], scores[2], evidence))  # type: ignore[arg-type]
    for fn, _ in CSF_FUNCTIONS:
        if not any(cat.function == fn for cat in csf):
            c.add("csf-profile.csv", f"no category scored for function {fn}")

    functions: list[FunctionScore] = []
    for fn, _ in CSF_FUNCTIONS:
        cats = [cat for cat in csf if cat.function == fn]
        if not cats:
            continue
        cur = round1(sum(x.current for x in cats) / len(cats))
        tgt = round1(sum(x.target for x in cats) / len(cats))
        last = round1(sum(x.last_quarter for x in cats) / len(cats))
        gap = round(tgt - cur, 2)
        functions.append(FunctionScore(fn, cur, tgt, last, gap, gap_label(gap, gap_bands) if gap_bands else "",
                                       function_trend(cur, last)))

    # ---- KRIs (read before risks so links can be checked both ways) --------
    kri_rows = _read_csv(data_dir / "kris.csv")
    kri_ids = {r.get("id", "") for r in kri_rows}
    risk_rows = _read_csv(data_dir / "risks.csv")
    risk_ids = {r.get("id", "") for r in risk_rows}

    kris: list[Kri] = []
    seen: set[str] = set()
    for n, row in enumerate(kri_rows, start=2):
        kid = row.get("id", "")
        where = f"kris.csv line {n} ({kid or 'no id'})"
        if not kid:
            c.add(where, "id is empty")
        if kid in seen:
            c.add(where, f"duplicate id {kid}")
        seen.add(kid)
        direction = row.get("direction", "")
        if direction not in KRI_DIRECTIONS:
            c.add(where, f"direction {direction!r} must be one of {sorted(KRI_DIRECTIONS)}")
        green = c.number(where, "green_threshold", row.get("green_threshold", ""))
        red = c.number(where, "red_threshold", row.get("red_threshold", ""))
        if green is not None and red is not None and direction in KRI_DIRECTIONS:
            if green == red:
                c.add(where, "green_threshold and red_threshold are equal: there is no amber band")
            elif direction == "higher_is_worse" and green > red:
                c.add(where, "higher_is_worse needs green_threshold below red_threshold")
            elif direction == "lower_is_worse" and green < red:
                c.add(where, "lower_is_worse needs green_threshold above red_threshold")
        current = c.number(where, "current", row.get("current", ""))
        last = c.number(where, "last_quarter", row.get("last_quarter", ""))
        decimals = c.number(where, "decimals", row.get("decimals", "0") or "0", integer=True, lo=0, hi=3)
        name = c.text(where, "name", row.get("name"))
        meaning = c.text(where, "what_it_tells_the_board", row.get("what_it_tells_the_board"))
        unit = c.text(where, "unit", row.get("unit"))
        owner = c.text(where, "owner", row.get("owner"))
        fn = row.get("csf_function", "")
        if fn not in prefixes:
            c.add(where, f"csf_function {fn!r} is not a CSF 2.0 function")
        links = _split(row.get("linked_risks", ""))
        for rid in links:
            if rid not in risk_ids:
                c.add(where, f"linked risk {rid} is not in risks.csv")
        if None not in (green, red, current, last, decimals) and direction in KRI_DIRECTIONS:
            kris.append(Kri(kid, name, meaning, unit, direction, green, red, current, last,  # type: ignore[arg-type]
                            int(decimals), owner, fn, links, stable_share))  # type: ignore[arg-type]

    # ---- Risks --------------------------------------------------------------
    risks: list[Risk] = []
    seen = set()
    if not 1 <= len(risk_rows) <= MAX_TOP_RISKS:
        c.add("risks.csv", f"the pack shows 1 to {MAX_TOP_RISKS} top risks; found {len(risk_rows)}")
    for n, row in enumerate(risk_rows, start=2):
        rid = row.get("id", "")
        where = f"risks.csv line {n} ({rid or 'no id'})"
        if not rid:
            c.add(where, "id is empty")
        if rid in seen:
            c.add(where, f"duplicate id {rid}")
        seen.add(rid)
        title = c.text(where, "title", row.get("title"))
        impact_text = c.text(where, "business_impact", row.get("business_impact"))
        owner = c.text(where, "owner", row.get("owner"))
        category = row.get("category", "")
        if category not in appetite:
            c.add(where, f"category {category!r} has no risk_appetite entry in organisation.yaml")
        vals = {f: c.number(where, f, row.get(f, ""), integer=True, lo=1, hi=5)
                for f in ("inherent_likelihood", "inherent_impact", "residual_likelihood", "residual_impact")}
        lql = c.number(where, "last_q_likelihood", row.get("last_q_likelihood", ""), integer=True, lo=1, hi=5,
                       required=False)
        lqi = c.number(where, "last_q_impact", row.get("last_q_impact", ""), integer=True, lo=1, hi=5,
                       required=False)
        if (lql is None) != (lqi is None) and (row.get("last_q_likelihood") or row.get("last_q_impact")):
            c.add(where, "last_q_likelihood and last_q_impact must both be set, or both empty for a new risk")
        if None not in vals.values():
            if vals["residual_likelihood"] * vals["residual_impact"] > vals["inherent_likelihood"] * vals["inherent_impact"]:  # type: ignore[operator]
                c.add(where, "residual score is higher than inherent score")
        treatment = row.get("treatment", "")
        if treatment not in TREATMENTS:
            c.add(where, f"treatment {treatment!r} must be one of {sorted(TREATMENTS)}")
        status = row.get("treatment_status", "")
        if status not in TREATMENT_STATUSES:
            c.add(where, f"treatment_status {status!r} must be one of {sorted(TREATMENT_STATUSES)}")
        milestone = c.text(where, "next_milestone", row.get("next_milestone"))
        due = c.date(where, "milestone_due", row.get("milestone_due", ""))
        fn = row.get("csf_function", "")
        if fn not in prefixes:
            c.add(where, f"csf_function {fn!r} is not a CSF 2.0 function")
        links = _split(row.get("linked_kris", ""))
        for kid in links:
            if kid not in kri_ids:
                c.add(where, f"linked KRI {kid} is not in kris.csv")
        if None not in vals.values() and due is not None and category in appetite:
            risks.append(Risk(
                rid, title, impact_text, category, owner,
                int(vals["inherent_likelihood"]), int(vals["inherent_impact"]),  # type: ignore[arg-type]
                int(vals["residual_likelihood"]), int(vals["residual_impact"]),  # type: ignore[arg-type]
                None if lql is None or lqi is None else int(lql),
                None if lql is None or lqi is None else int(lqi),
                treatment, status, milestone, due, fn, links, appetite[category], bands,
            ))

    # ---- Calendar -----------------------------------------------------------
    calendar: list[CalendarItem] = []
    w_start, w_end = report.get("calendar_window_start"), report.get("calendar_window_end")
    for n, row in enumerate(_read_csv(data_dir / "calendar.csv"), start=2):
        where = f"calendar.csv line {n}"
        start = c.date(where, "start", row.get("start", ""))
        end = c.date(where, "end", row.get("end") or row.get("start", ""))
        if start and end and end < start:
            c.add(where, "end is before start")
        if start and isinstance(w_start, date) and isinstance(w_end, date) and not w_start <= start <= w_end:
            c.add(where, f"start {start} is outside the 12-month window {w_start} to {w_end}")
        ctype = row.get("type", "")
        if ctype not in CALENDAR_TYPES:
            c.add(where, f"type {ctype!r} must be one of {sorted(CALENDAR_TYPES)}")
        status = row.get("status", "")
        if status not in CALENDAR_STATUSES:
            c.add(where, f"status {status!r} must be one of {sorted(CALENDAR_STATUSES)}")
        activity = c.text(where, "activity", row.get("activity"))
        driver = c.text(where, "driver", row.get("driver"))
        owner = c.text(where, "owner", row.get("owner"))
        if start and end:
            calendar.append(CalendarItem(start, end, activity, ctype, driver, owner, status,
                                         row.get("board_note", "")))
    calendar.sort(key=lambda x: (x.start, x.activity))
    haystack = " ".join(f"{x.activity} {x.driver}" for x in calendar).lower()
    for must in report.get("calendar_must_include") or []:
        if str(must).lower() not in haystack:
            c.add("calendar.csv", f"no entry mentions {must!r} (required by report.calendar_must_include)")

    # ---- Decisions ----------------------------------------------------------
    decisions: list[Decision] = []
    seen = set()
    raw_decisions = dec_file.get("decisions") or []
    if not raw_decisions:
        c.add("decisions.yaml", "no decisions listed")
    for i, d in enumerate(raw_decisions, start=1):
        did = str(d.get("id") or "")
        where = f"decisions.yaml #{i} ({did or 'no id'})"
        if not did:
            c.add(where, "id is empty")
        if did in seen:
            c.add(where, f"duplicate id {did}")
        seen.add(did)
        dtype = str(d.get("type") or "")
        if dtype not in DECISION_TYPES:
            c.add(where, f"type {dtype!r} must be one of {sorted(DECISION_TYPES)}")
        title = c.text(where, "title", d.get("title"))
        context = c.text(where, "context", d.get("context"))
        rationale = c.text(where, "rationale", d.get("rationale"))
        if_declined = c.text(where, "if_declined", d.get("if_declined"))
        resolution = c.text(where, "proposed_resolution", d.get("proposed_resolution"))
        decide_by = c.date(where, "decide_by", d.get("decide_by"))
        links = [str(x) for x in d.get("linked_risks") or []]
        for rid in links:
            if rid not in risk_ids:
                c.add(where, f"linked risk {rid} is not in risks.csv")
        options: list[Option] = []
        opt_ids: set[str] = set()
        for o in d.get("options") or []:
            oid = str(o.get("id") or "")
            ow = f"{where} option {oid or '?'}"
            if not oid or oid in opt_ids:
                c.add(ow, "option id is empty or duplicated")
            opt_ids.add(oid)
            lo = c.number(ow, "cost_min", str(o.get("cost_min", "")), integer=True, lo=0, hi=10**10)
            hi = c.number(ow, "cost_max", str(o.get("cost_max", "")), integer=True, lo=0, hi=10**10)
            if lo is not None and hi is not None and lo > hi:
                c.add(ow, "cost_min is greater than cost_max")
            label = c.text(ow, "label", o.get("label"))
            desc = c.text(ow, "description", o.get("description"))
            effect = c.text(ow, "effect", o.get("effect"))
            if lo is not None and hi is not None:
                options.append(Option(oid, label, desc, int(lo), int(hi), effect))
        if len(options) < 2:
            c.add(where, "a decision needs at least two options")
        rec = str(d.get("recommendation") or "")
        if not rec:
            c.add(where, "recommendation is empty")
        elif rec not in opt_ids:
            c.add(where, f"recommendation {rec!r} is not one of the option ids {sorted(opt_ids)}")
        if decide_by is not None and rec in {o.id for o in options}:
            decisions.append(Decision(did, dtype, title, links, decide_by, context, options, rec,
                                      rationale, if_declined, resolution))

    if c.problems:
        raise DataError(c.problems)

    config = {
        "bands": bands,
        "gap_bands": gap_bands,
        "appetite": appetite,
        "likelihood_scale": org_file["likelihood_scale"],
        "impact_scale": org_file["impact_scale"],
        "maturity_scale": org_file["maturity_scale"],
        "narrative": list(org_file.get("narrative") or []),
        "kri_stable_share": stable_share,
    }
    return Pack(org, report, config, csf, functions, risks, kris, calendar, decisions)
