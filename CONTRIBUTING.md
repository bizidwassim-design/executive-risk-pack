# Contributing

Thanks for helping improve the pack. Better wording for boards, new checks in the validator, extra renderers and
translations are all welcome.

## Ground rules

* **Fictional data only.** Sample organisations are "Fabrikam", "Contoso" or "Northwind Logistics". Never commit real
  risks, real KRI values, people's names, client names, hostnames or anything taken from a real board pack.
* **Data is the single source of truth.** Never type a number into the generated pack. If the pack needs a new
  figure, add it to `data/` and compute it in `scripts/packdata.py`.
* **Plain executive English.** Short sentences, business impact first, every acronym explained once or avoided.
* **Standards by name and ID only.** Reference "NIST CSF 2.0 RC.RP" or "PCI DSS v4.0.1 requirement 11.4"; never
  paste the text of a standard.
* **Deterministic output.** Same data, same bytes: no `datetime.now()`, explicit sort keys with a final tie-break
  on ID, LF line endings.
* **Python 3.10+**, `from __future__ import annotations`, type hints, `#!/usr/bin/env python3` on scripts.
* Be kind — see the [Code of Conduct](CODE_OF_CONDUCT.md).

## Development loop

```bash
pip install -r requirements.txt pytest
python scripts/validate_data.py
pytest -q
python scripts/build_pack.py
git diff --stat pack/        # CI fails if board-pack.md, board-pack.xlsx or chart-data.json drift
```

If you change data, scoring or a renderer, **rebuild and commit `pack/` in the same commit**. The workbook is binary
but reproducible, so it only changes when its content does.

## Where things live

| Change | File |
|--------|------|
| Scales, bands, appetite, narrative, reporting dates | `data/organisation.yaml` |
| Validation rules, scoring, RAG, trends | `scripts/packdata.py` |
| Markdown wording and layout | `render_markdown` in `scripts/build_pack.py` |
| Workbook sheets and styles | `render_workbook` in `scripts/build_pack.py` |
| Charts | `render_charts` in `scripts/build_pack.py` |
| Quarter roll-over | `scripts/roll_quarter.py` |

## Ideas that would be welcome

* An HTML or PDF renderer with print styles.
* A second sample organisation in another sector, selectable with `--data`.
* Risk movement arrows (last quarter to now) on the heat-map chart.
* French or Arabic headings for the generated pack.

## Making a change

1. Open an issue describing the problem or idea (optional for small fixes).
2. Fork and branch (`fix/kri-trend`, `feat/html-output`).
3. Add or update tests in `tests/`; keep the suite green.
4. Rebuild `pack/` if anything in it changes.
5. Open a pull request explaining what changed and why.

## Licensing of contributions

By contributing you agree that your work is released under the repository's [MIT License](LICENSE).
