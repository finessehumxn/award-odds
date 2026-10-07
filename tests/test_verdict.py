import pytest

from award_odds.stats import SizeStats
from award_odds.verdict import (
    GOOD_FIT, LONG_SHOT, MODERATE, POSSIBLE, STRONG, WEAK,
    budget_factor, concentration_factor, decide, type_factor,
)

SIZES = SizeStats(count=100, total=1e7, minimum=10_000, p10=50_000, p25=100_000,
                  median=150_000, p75=200_000, p90=400_000, maximum=1_000_000)


@pytest.mark.parametrize("count,total,rating", [
    (20, 100, STRONG), (19, 100, MODERATE), (5, 100, MODERATE), (4, 100, WEAK), (0, 100, WEAK),
])
def test_type_factor_thresholds(count, total, rating):
    f = type_factor("nonprofit", count, total)
    assert f.rating == rating
    assert f"{count:,} of {total:,} awards" in f.evidence


@pytest.mark.parametrize("budget,rating", [
    (100_000, STRONG), (200_000, STRONG), (60_000, MODERATE), (400_000, MODERATE),
    (400_001, WEAK), (49_999, WEAK),
])
def test_budget_factor_bands(budget, rating):
    assert budget_factor(budget, SIZES).rating == rating


@pytest.mark.parametrize("share,rating", [(0.50, WEAK), (0.49, MODERATE), (0.25, MODERATE), (0.249, STRONG)])
def test_concentration_thresholds(share, rating):
    assert concentration_factor(share, 40).rating == rating


def t(rating):  # type factor with a given rating
    return {STRONG: type_factor("x", 50, 100), MODERATE: type_factor("x", 10, 100),
            WEAK: type_factor("x", 1, 100)}[rating]


def test_r1_type_weak_is_long_shot_even_if_everything_else_is_strong():
    v = decide([t(WEAK), budget_factor(150_000, SIZES), concentration_factor(0.1, 40)])
    assert v.band == LONG_SHOT and v.rule_fired.startswith("R1")


def test_r2_two_weak_factors():
    v = decide([t(MODERATE), budget_factor(5_000_000, SIZES), concentration_factor(0.9, 40)])
    assert v.band == LONG_SHOT and v.rule_fired.startswith("R2")


def test_r3_good_fit():
    v = decide([t(STRONG), budget_factor(150_000, SIZES), concentration_factor(0.3, 40)])
    assert v.band == GOOD_FIT and v.rule_fired.startswith("R3")


def test_r3_blocked_by_one_weak_factor():
    v = decide([t(STRONG), budget_factor(5_000_000, SIZES), concentration_factor(0.1, 40)])
    assert v.band == POSSIBLE and v.rule_fired.startswith("R4")


def test_r4_moderate_type():
    v = decide([t(MODERATE), concentration_factor(0.1, 40)])
    assert v.band == POSSIBLE
