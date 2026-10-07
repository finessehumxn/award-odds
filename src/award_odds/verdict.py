"""The fit readout: a few factors, each with its evidence, and fixed rules.

Every threshold lives in this file and is printed with the output. There is
no model and no hidden weighting. If you disagree with a verdict, the factor
that produced it and the rule that fired are both on screen.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .stats import SizeStats

STRONG, MODERATE, WEAK = "strong", "moderate", "weak"

LONG_SHOT, POSSIBLE, GOOD_FIT = "Long shot", "Possible", "Good fit"

# Thresholds. Change them here and the printed rules change with them.
TYPE_SHARE_STRONG = 0.20  # >= 20% of awards went to your type
TYPE_SHARE_WEAK = 0.05  # <  5% of awards went to your type
TOP10_SHARE_WEAK = 0.50  # top 10 recipients took >= 50% of dollars
TOP10_SHARE_STRONG = 0.25  # top 10 recipients took <  25% of dollars

RULES = [
    f"R1  Your type won under {TYPE_SHARE_WEAK:.0%} of awards -> {LONG_SHOT}.",
    f"R2  Two or more factors are weak -> {LONG_SHOT}.",
    f"R3  Your type won at least {TYPE_SHARE_STRONG:.0%} of awards and no factor is weak -> {GOOD_FIT}.",
    f"R4  Anything else -> {POSSIBLE}.",
]

FACTOR_RULES = {
    "Recipient type": (
        f"strong if >= {TYPE_SHARE_STRONG:.0%} of awards, "
        f"weak if < {TYPE_SHARE_WEAK:.0%}, else moderate"
    ),
    "Budget vs past awards": (
        "strong if inside the middle 50% (p25-p75), "
        "moderate if inside p10-p90, else weak"
    ),
    "Concentration": (
        f"weak if top 10 recipients took >= {TOP10_SHARE_WEAK:.0%} of dollars, "
        f"strong if < {TOP10_SHARE_STRONG:.0%}, else moderate"
    ),
}


@dataclass
class Factor:
    name: str
    rating: str
    evidence: str
    rule: str


@dataclass
class Verdict:
    band: str
    rule_fired: str
    factors: list[Factor] = field(default_factory=list)


def money(x: float) -> str:
    return f"${x:,.0f}"


def type_factor(type_label: str, type_count: int, total: int) -> Factor:
    share = type_count / total if total else 0.0
    if share >= TYPE_SHARE_STRONG:
        rating = STRONG
    elif share < TYPE_SHARE_WEAK:
        rating = WEAK
    else:
        rating = MODERATE
    return Factor(
        name="Recipient type",
        rating=rating,
        evidence=(
            f"{type_count:,} of {total:,} awards ({share:.1%}) went to "
            f"recipients classified as {type_label}"
        ),
        rule=FACTOR_RULES["Recipient type"],
    )


def budget_factor(budget: float, sizes: SizeStats) -> Factor:
    if sizes.p25 <= budget <= sizes.p75:
        rating, where = STRONG, "inside the middle 50% of past awards"
    elif sizes.p10 <= budget <= sizes.p90:
        rating, where = MODERATE, "outside the middle 50% but inside p10-p90"
    elif budget > sizes.p90:
        rating, where = WEAK, "larger than 90% of past awards"
    else:
        rating, where = WEAK, "smaller than 90% of past awards"
    return Factor(
        name="Budget vs past awards",
        rating=rating,
        evidence=(
            f"{money(budget)} is {where} "
            f"(p10 {money(sizes.p10)}, p25 {money(sizes.p25)}, "
            f"p75 {money(sizes.p75)}, p90 {money(sizes.p90)}; n={sizes.count:,})"
        ),
        rule=FACTOR_RULES["Budget vs past awards"],
    )


def concentration_factor(top10_share: float, unique_recipients: int) -> Factor:
    if top10_share >= TOP10_SHARE_WEAK:
        rating = WEAK
    elif top10_share < TOP10_SHARE_STRONG:
        rating = STRONG
    else:
        rating = MODERATE
    return Factor(
        name="Concentration",
        rating=rating,
        evidence=(
            f"top 10 of {unique_recipients:,} recipients took "
            f"{top10_share:.1%} of award dollars"
        ),
        rule=FACTOR_RULES["Concentration"],
    )


def decide(factors: list[Factor]) -> Verdict:
    """Apply R1-R4 in order. The first rule that matches wins."""
    by_name = {f.name: f for f in factors}
    type_f = by_name.get("Recipient type")
    weak = [f for f in factors if f.rating == WEAK]

    if type_f is not None and type_f.rating == WEAK:
        return Verdict(LONG_SHOT, RULES[0], factors)
    if len(weak) >= 2:
        return Verdict(LONG_SHOT, RULES[1], factors)
    if type_f is not None and type_f.rating == STRONG and not weak:
        return Verdict(GOOD_FIT, RULES[2], factors)
    return Verdict(POSSIBLE, RULES[3], factors)
