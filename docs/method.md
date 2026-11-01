# Method: how every number in the pack is computed

The board pack contains no hand-typed figures. Every score, status, trend, count and colour comes from the files in
[`data/`](../data) through [`scripts/packdata.py`](../scripts/packdata.py). This page explains each rule, with the
numbers from the Fabrikam Payments sample so you can check them by hand.

## 1. Security posture (NIST CSF 2.0)

**Unit of scoring: the category.** [`data/csf-profile.csv`](../data/csf-profile.csv) scores each of the 22 CSF 2.0
categories (GV.OC to RC.CO) three times: `current`, `target` and `last_quarter`, on a 0–5 maturity scale.

| Level | Label | What you would see |
|------:|-------|--------------------|
| 0 | Absent | Nothing in place |
| 1 | Ad hoc | Done by individuals when they remember; not repeatable |
| 2 | Developing | Partly documented, applied unevenly |
| 3 | Defined | Documented, owned, applied across the company |
| 4 | Managed | Measured; reviewed and improved on evidence |
| 5 | Optimised | Tuned continuously; benchmarked against peers |

Half points are allowed (`2.5` = most of level 2 in place, some of level 3). Every row carries one sentence of
`evidence`: if you cannot write that sentence, you cannot defend the score in front of an auditor or a board member.

**Why 0–5 maturity and not CSF Implementation Tiers.** The four CSF tiers (Partial, Risk Informed, Repeatable,
Adaptive) describe how rigorous the organisation's risk governance is overall. They are too coarse to show quarterly
progress. A 0–5 score per category moves when real work is done, which is what a board wants to see. You can still
quote a tier in the narrative.

**Function score** = arithmetic mean of its categories, rounded once to one decimal, halves rounded up
(3.25 → 3.3). Rounding once, at the source, means the tables, the chart and the gaps always agree.

> Recover: RC.RP 2.0 and RC.CO 2.5 → mean 2.25 → **2.3**. Target: 4.0 and 3.5 → 3.75 → **3.8**.

**Gap** = target − current, on the rounded function scores. Gap bands come from `gap_bands` in
[`organisation.yaml`](../data/organisation.yaml):

| Gap | Label |
|-----|-------|
| ≤ 0.0 | At target |
| ≤ 0.5 | Close |
| ≤ 1.0 | Gap |
| > 1.0 | Priority gap |

> Recover: 3.8 − 2.3 = 1.5 → **Priority gap**.

**Function trend**: a change of 0.05 or more since last quarter is *Improving* or *Worsening*; less is *Stable*.

**Overall posture** = mean of the six function scores, rounded to one decimal; **% of target** = posture ÷ target
posture. Each function counts equally. If your board cares more about one function, change the mean in
`Pack.posture_current` rather than inflating scores.

## 2. Risk scores

Every risk in [`data/risks.csv`](../data/risks.csv) has three likelihood × impact pairs on 1–5 scales:

* **Inherent**: before any controls. It shows how bad the scenario is.
* **Residual**: with the controls working today. It drives every status in the pack.
* **Last quarter**: the residual pair reported in the previous pack. Empty for a new risk.

The likelihood and impact scales are written in business terms (frequency; AED loss, hours of disruption,
regulatory consequence) in `likelihood_scale` and `impact_scale`. Score = likelihood × impact, 1–25.

| Score | Band |
|------:|------|
| 1–4 | Low |
| 5–9 | Medium |
| 10–16 | High |
| 17–25 | Critical |

These are the same bands as the
[application-risk-assessment-template](https://github.com/bizidwassim-design/application-risk-assessment-template),
so a risk can move from a project assessment to the board pack without being rescored.

**Validation**: residual may never be higher than inherent. If it is, either the inherent score is too low or a
control is making things worse, and both need a conversation before the board meeting.

**Ranking**: residual score, highest first; ties broken by inherent score, then by ID.

## 3. Risk appetite

`risk_appetite` in `organisation.yaml` gives, per risk category, the **highest residual score the board accepts**.
A risk is *above appetite* when its residual score is strictly greater.

> R08 (Resilience, appetite 8) has residual 3 × 4 = 12 → **above appetite**.
> R06 (Data protection, appetite 6) has residual 2 × 3 = 6 → **within appetite**.

An appetite per category, rather than one number, is deliberate: a payments company can live with more uncertainty in
internal technology choices than in its card-scheme and data-protection obligations.

## 4. Risk trend

Residual score now compared with last quarter's residual score:

| Change | Trend |
|--------|-------|
| Lower | Improving |
| Higher | Worsening |
| Same | Stable |
| No last-quarter score | New |

The summary also compares the number of risks above appetite now with the number that were above appetite last
quarter (risks that are new this quarter are not counted in last quarter's figure).

## 5. Key risk indicators (KRIs)

Each KRI in [`data/kris.csv`](../data/kris.csv) has a `direction` and two thresholds:

* `green_threshold`: the target. At or better than this value, the KRI is **Green**.
* `red_threshold`: the tolerance. Worse than this value, the KRI is **Red**.
* Anything in between, including the red threshold itself, is **Amber**.

| Direction | Green | Amber | Red |
|-----------|-------|-------|-----|
| `higher_is_worse` (e.g. overdue reviews) | value ≤ green | green < value ≤ red | value > red |
| `lower_is_worse` (e.g. restore success %) | value ≥ green | red ≤ value < green | value < red |

> KRI-08, restore success, `lower_is_worse`, green 95, red 85. Current 80 < 85 → **Red**. Last quarter 92 → Amber.

**KRI trend.** A raw change is not always a trend: going from 3.4% to 3.5% is noise. The pack treats a change as
real only if it is at least `kri_stable_share` (10%) of the width of the amber band, `|red − green|`.

> KRI-04, containment time, green 4 h, red 24 h → band 20 h → noise threshold 2 h.
> 7.0 h → 9.5 h is +2.5 h → **Worsening**.

**Validation**: both thresholds must exist, must differ, and must be in the right order for the direction
(for `higher_is_worse` green must be below red). Every KRI needs an owner.

**Coverage check.** A risk with no KRI linked to it in either direction is listed under *Not yet measured*. It is a
prompt to design one, not an error.

## 6. Calendar

[`data/calendar.csv`](../data/calendar.csv) lists the next twelve months. Validation checks that every date falls
inside `calendar_window_start`–`calendar_window_end` and that the entries together mention every term in
`calendar_must_include` (PCI DSS, UAE Information Assurance, PDPL, ISO/IEC 27001, penetration test, tabletop). That
stops a quarter's pack going out with the PCI DSS assessment quietly missing.

The summary lists entries that start within `look_ahead_days` (90) of the board meeting.

## 7. Decisions

Each decision in [`data/decisions.yaml`](../data/decisions.yaml) must have:

* a `type`: Risk acceptance, Budget or Policy exception;
* at least two options, each with a cost range (`cost_min` ≤ `cost_max`) and its effect on the risk;
* a `recommendation` that names one of its options;
* `if_declined`: what happens to the risk if the board says no;
* a `proposed_resolution`: the sentence the company secretary can minute.

The summary page adds up the cost ranges of the recommended options so the board sees the total commitment it is
asked for.

## 8. Reproducibility

* No wall-clock dates: everything comes from the data. The same data gives the same bytes.
* CSV and JSON are written with `\n` line endings.
* The workbook's zip entries and document properties carry a fixed timestamp and are stored uncompressed, so the
  bytes depend only on the content and the pinned `openpyxl` version, not on the operating system or zlib build.
* PNG charts are written without the software-version metadata. They are byte-stable on one machine, but font
  rasterisation can differ slightly between operating systems, so CI checks the numbers behind them
  ([`pack/charts/chart-data.json`](../pack/charts/chart-data.json)) instead of the pixels.
