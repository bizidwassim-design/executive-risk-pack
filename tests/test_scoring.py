from __future__ import annotations

import pytest

from packdata import band_for, function_trend, gap_label, kri_rag, kri_trend, risk_trend, round1

BANDS = [(4, "Low"), (9, "Medium"), (16, "High"), (25, "Critical")]


@pytest.mark.parametrize("score,label", [(1, "Low"), (4, "Low"), (5, "Medium"), (9, "Medium"), (10, "High"),
                                         (16, "High"), (17, "Critical"), (25, "Critical")])
def test_band_boundaries(score: int, label: str) -> None:
    assert band_for(score, BANDS) == label


def test_band_above_scale_raises() -> None:
    with pytest.raises(ValueError):
        band_for(26, BANDS)


@pytest.mark.parametrize("value,expected", [(0, "Green"), (2, "Green"), (2.1, "Amber"), (8, "Amber"),
                                            (8.01, "Red"), (20, "Red")])
def test_kri_rag_higher_is_worse(value: float, expected: str) -> None:
    assert kri_rag(value, green=2, red=8, direction="higher_is_worse") == expected


@pytest.mark.parametrize("value,expected", [(100, "Green"), (95, "Green"), (94.9, "Amber"), (85, "Amber"),
                                            (84.9, "Red"), (0, "Red")])
def test_kri_rag_lower_is_worse(value: float, expected: str) -> None:
    assert kri_rag(value, green=95, red=85, direction="lower_is_worse") == expected


def test_kri_rag_unknown_direction() -> None:
    with pytest.raises(ValueError):
        kri_rag(1, 1, 2, "sideways")


def test_kri_trend_uses_width_of_amber_band() -> None:
    # band width 6, stable share 10% -> moves under 0.6 are noise
    assert kri_trend(5.5, 5.0, 2, 8, "higher_is_worse", 0.10) == "Stable"
    assert kri_trend(5.6, 5.0, 2, 8, "higher_is_worse", 0.10) == "Worsening"
    assert kri_trend(4.0, 5.0, 2, 8, "higher_is_worse", 0.10) == "Improving"
    assert kri_trend(80, 92, 95, 85, "lower_is_worse", 0.10) == "Worsening"
    assert kri_trend(96, 92, 95, 85, "lower_is_worse", 0.10) == "Improving"
    assert kri_trend(3, 3, 0, 5, "higher_is_worse", 0.0) == "Stable"


@pytest.mark.parametrize("now,last,expected", [(12, 15, "Improving"), (16, 12, "Worsening"), (10, 10, "Stable"),
                                               (9, None, "New")])
def test_risk_trend(now: int, last: int | None, expected: str) -> None:
    assert risk_trend(now, last) == expected


def test_function_trend_ignores_rounding_noise() -> None:
    assert function_trend(3.02, 3.0) == "Stable"
    assert function_trend(3.1, 3.0) == "Improving"
    assert function_trend(2.25, 2.5) == "Worsening"


def test_round1_rounds_halves_up() -> None:
    assert round1(3.25) == 3.3
    assert round1(2.875) == 2.9
    assert round1(2.85) == 2.9
    assert round1(2.666) == 2.7
    assert round1(2.0) == 2.0


def test_gap_label() -> None:
    bands = [(0.0, "At target"), (0.5, "Close"), (1.0, "Gap"), (5.0, "Priority gap")]
    assert gap_label(-0.5, bands) == "At target"
    assert gap_label(0.0, bands) == "At target"
    assert gap_label(0.5, bands) == "Close"
    assert gap_label(1.0, bands) == "Gap"
    assert gap_label(1.5, bands) == "Priority gap"
