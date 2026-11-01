# How to adapt the pack to your organisation

Start with the sample. Build it once, read [`pack/board-pack.md`](../pack/board-pack.md) end to end, and decide what
your board would ask about. Then replace the Fabrikam data one file at a time, running the validator after each one.

```bash
pip install -r requirements.txt
python scripts/validate_data.py      # tells you every problem at once
python scripts/build_pack.py         # writes pack/
```

## 1. Organisation profile — `data/organisation.yaml`

| Block | What to change |
|-------|----------------|
| `organisation` | Name, sector, size, technology, regulatory scope. Used in the header and the workbook. |
| `report` | Quarter, period dates, board meeting date, who presents to whom, classification, currency. |
| `calendar_window_*` | The twelve months the calendar covers, usually the day after the period ends plus one year. |
| `calendar_must_include` | The assessments your regulators and certifications require. The validator refuses a calendar that misses one. |
| `narrative` | Three sentences: what improved, what got worse, what you need. No numbers; the script adds those. |
| `likelihood_scale`, `impact_scale` | Rewrite the impact levels in your own money, downtime and regulatory terms. Agree them with the CFO and the risk committee before the first pack, then leave them alone. |
| `risk_appetite` | One maximum residual score per risk category, approved by the board. Add or rename categories freely; every risk must use one of them. |
| `kri_stable_share` | Raise it if your KRIs are noisy; lower it if small moves matter. |

## 2. Posture — `data/csf-profile.csv`

Keep the 22 CSF 2.0 category IDs. Score `current` with the control owners in a workshop, not alone. Set `target`
once a year with the board's ambition in mind; a target of 5 everywhere is neither credible nor affordable.
The `evidence` column is what you say when a director asks "why a 2?".

If you use a different framework (ISO/IEC 27001 Annex A themes, CIS Controls v8), you can keep the file format and
replace `function` and `category_id`, but you will need to edit `CSF_FUNCTIONS` in `scripts/packdata.py`.

## 3. Risks — `data/risks.csv`

* **Ten risks, not forty.** The validator stops at ten. A board can discuss ten; anything more becomes a list.
* **Write the title as an event** ("Ransomware stops card processing"), not a topic ("Ransomware").
* **Write `business_impact` for a non-specialist**: what stops, who is hurt, roughly how much it costs.
* **Owner = a business role**, not the CISO for everything. Owners are accountable for the treatment.
* `last_q_likelihood` / `last_q_impact` stay empty for a risk that is new this quarter.
* `treatment_status` is one of Not started, On track, At risk, Delayed, Complete.
* `linked_kris` uses `;` between IDs.

## 4. KRIs — `data/kris.csv`

Pick 10 to 12 indicators that move within a quarter and that someone owns. For each one decide, with its owner:

1. the `direction` (`higher_is_worse` or `lower_is_worse`);
2. the `green_threshold` — where you want to be;
3. the `red_threshold` — the point where the board should worry.

Write `what_it_tells_the_board` in one sentence without jargon. `decimals` controls how the value is printed.

## 5. Calendar — `data/calendar.csv`

One row per event, `start` and `end` as ISO dates (same date for a one-day event). `driver` says *why* it happens,
naming the standard or regulation by name and clause only. `status` is Planned, Booked, In preparation,
Conditional or Done. Use `board_note` for what the board needs to know, and leave it empty otherwise.

## 6. Decisions — `data/decisions.yaml`

Bring a decision to the board only if it is truly theirs: accepting a risk above appetite, spending above
management's authority, or an exception to a board-approved policy. For each one give two or three real options,
including "do nothing" when it is a real option, with a cost range and the effect on the risk score.
Say clearly what happens if the board declines.

## 7. Each new quarter

```bash
python scripts/roll_quarter.py --dry-run   # shows what will change
python scripts/roll_quarter.py             # current -> last quarter in all three CSV files
```

Then update `report` in `organisation.yaml`, enter the new scores, refresh the calendar and decisions, write a
new three-line narrative, validate, build, and commit `data/` and `pack/` together. The Git history becomes your
audit trail of what the board was told and when.

## 8. Presenting it

* Send the pack five working days before the meeting; nobody reads 30 pages on the morning of the meeting.
* Spend most of your slot on section 6. The board's job is to decide; the rest of the pack is context.
* Open with the three sentences of the narrative and the summary table. Go into detail only when asked.
* Print the workbook only if a director asks for it; it is for the risk committee and the auditors.
* Use [`pack/board-pack.md`](../pack/board-pack.md) as-is on GitHub, or convert it to PDF or Word with a Markdown
  converter (for example `pandoc board-pack.md -o board-pack.docx`) and apply your company template.

## 9. Changing the look

* Workbook colours and column widths: `render_workbook` in `scripts/build_pack.py`.
* Chart colours: the constants at the top of `scripts/build_pack.py`. Keep the four band colours distinct from the
  blue used for maturity so the two charts never send mixed signals.
* Wording of the generated sentences: `render_markdown` in the same file.

After any change, rebuild and commit `pack/` with the code; CI fails if the committed pack is stale.
