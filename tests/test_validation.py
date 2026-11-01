from __future__ import annotations

from pathlib import Path

import pytest

from conftest import replace_in
from packdata import DataError, load


def problems(data_dir: Path) -> list[str]:
    with pytest.raises(DataError) as exc:
        load(data_dir)
    return exc.value.problems


def test_shipped_data_is_valid() -> None:
    pack = load()
    assert len(pack.risks) == 10
    assert 10 <= len(pack.kris) <= 12
    assert [f.function for f in pack.functions] == ["Govern", "Identify", "Protect", "Detect", "Respond", "Recover"]
    assert {d.type for d in pack.decisions} == {"Risk acceptance", "Budget", "Policy exception"}


def test_shipped_data_headline_figures() -> None:
    pack = load()
    assert pack.kri_counts() == {"Red": 3, "Amber": 5, "Green": 4}
    assert sum(r.above_appetite for r in pack.risks) == 5
    assert pack.risk_trend_counts() == {"Worsening": 2, "Stable": 2, "Improving": 5, "New": 1}
    top = pack.risks_by_residual()[0]
    assert (top.id, top.residual_score, top.residual_band) == ("R03", 16, "High")


def test_score_out_of_range(data_copy: Path) -> None:
    replace_in(data_copy / "risks.csv", "Chief Operating Officer,4,4,4,4,3,4", "Chief Operating Officer,4,6,4,4,3,4")
    assert any("inherent_impact=6 is outside 1-5" in p for p in problems(data_copy))


def test_maturity_out_of_range(data_copy: Path) -> None:
    replace_in(data_copy / "csf-profile.csv", "Policy,3.5,4.0,3.5", "Policy,3.5,5.5,3.5")
    assert any("target=5.5 is outside 0-5" in p for p in problems(data_copy))


def test_risk_without_owner(data_copy: Path) -> None:
    replace_in(data_copy / "risks.csv", "Chief People Officer,3,4", ",3,4")
    assert any("(R07)" in p and "owner is empty" in p for p in problems(data_copy))


def test_residual_above_inherent(data_copy: Path) -> None:
    replace_in(data_copy / "risks.csv", "Chief Financial Officer,4,4,2,3", "Chief Financial Officer,2,2,4,4")
    assert any("residual score is higher than inherent" in p for p in problems(data_copy))


def test_kri_missing_threshold(data_copy: Path) -> None:
    replace_in(data_copy / "kris.csv", "%,higher_is_worse,4,10,", "%,higher_is_worse,,10,")
    assert any("(KRI-02)" in p and "green_threshold is empty" in p for p in problems(data_copy))


def test_kri_thresholds_in_wrong_order(data_copy: Path) -> None:
    replace_in(data_copy / "kris.csv", "%,lower_is_worse,95,85,", "%,lower_is_worse,85,95,")
    assert any("lower_is_worse needs green_threshold above red_threshold" in p for p in problems(data_copy))


def test_decision_recommendation_must_be_an_option(data_copy: Path) -> None:
    replace_in(data_copy / "decisions.yaml", "    recommendation: A\n", "    recommendation: Z\n")
    assert any("recommendation 'Z' is not one of the option ids" in p for p in problems(data_copy))


def test_decision_without_recommendation(data_copy: Path) -> None:
    replace_in(data_copy / "decisions.yaml", "    recommendation: A\n", "    recommendation:\n")
    assert any("recommendation is empty" in p for p in problems(data_copy))


def test_unknown_link(data_copy: Path) -> None:
    replace_in(data_copy / "kris.csv", "Chief Operating Officer,Govern,R03", "Chief Operating Officer,Govern,R99")
    assert any("linked risk R99 is not in risks.csv" in p for p in problems(data_copy))


def test_calendar_must_cover_required_events(data_copy: Path) -> None:
    path = data_copy / "calendar.csv"
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    path.write_text("".join(line for line in lines if "tabletop" not in line.lower()), encoding="utf-8",
                    newline="\n")
    assert any("no entry mentions 'tabletop'" in p for p in problems(data_copy))


def test_all_problems_reported_at_once(data_copy: Path) -> None:
    replace_in(data_copy / "risks.csv", "Chief People Officer,3,4", ",3,4")
    replace_in(data_copy / "kris.csv", "%,higher_is_worse,4,10,", "%,higher_is_worse,,10,")
    assert len(problems(data_copy)) >= 2
