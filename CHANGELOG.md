# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [1.0.0] — 2026-11-01

### Added
- Data files for a fictional payments company, "Fabrikam Payments LLC", Q3 2026: NIST CSF 2.0 current, target and
  last-quarter maturity for 22 categories; 10 top risks with inherent, residual and last-quarter scores; 12 KRIs with
  green/red thresholds; a 12-month regulatory and assurance calendar; 3 board decisions with options and costs.
- `scripts/build_pack.py`: generates `pack/board-pack.md` (six sections plus appendix), `pack/board-pack.xlsx`
  (eight sheets, no macros, reproducible bytes) and two matplotlib charts with the numbers behind them in JSON.
- `scripts/validate_data.py`: reports every data problem at once (ranges, owners, thresholds, recommendations,
  broken links, calendar window and required assurance events).
- `scripts/roll_quarter.py`: copies this quarter's values into the last-quarter columns to start the next pack.
- `docs/method.md` (every rule with worked numbers) and `docs/how-to-adapt.md`.
- pytest suite (scoring, validation, determinism, workbook, charts, quarter roll-over) and CI that validates,
  tests, rebuilds and fails if the committed pack is stale.
- `SECURITY.md`, `CODE_OF_CONDUCT.md`, Dependabot for GitHub Actions, this changelog.
