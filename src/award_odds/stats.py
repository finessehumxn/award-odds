"""Pure functions over award rows. No I/O here."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Sequence

from .client import Award


def percentile(sorted_values: Sequence[float], q: float) -> float:
    """Linear-interpolated percentile (same method as numpy's default).

    ``sorted_values`` must be sorted ascending and non-empty; ``q`` is 0..100.
    """
    if not sorted_values:
        raise ValueError("percentile of empty sequence")
    if not 0 <= q <= 100:
        raise ValueError("q must be between 0 and 100")
    pos = (len(sorted_values) - 1) * q / 100
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = pos - lo
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * frac


@dataclass
class SizeStats:
    count: int
    total: float
    minimum: float
    p10: float
    p25: float
    median: float
    p75: float
    p90: float
    maximum: float


@dataclass
class RecipientTotal:
    name: str
    awards: int
    dollars: float
    share: float  # of all positive award dollars


@dataclass
class AwardStats:
    awards_fetched: int
    non_positive: int  # zero or negative award amounts, excluded from sizes
    unique_recipients: int
    sizes: SizeStats | None  # single-listing awards only, see summarize()
    total_dollars: float = 0.0  # all positive award amounts, award level
    top_recipients: list[RecipientTotal] = field(default_factory=list)
    top10_share: float = 0.0
    multi_program: int = 0  # awards that also carry other listings' money
    multi_program_dollar_share: float = 0.0
    sizes_include_multi: bool = False  # True only when no single-listing awards exist


def size_stats(amounts: Sequence[float]) -> SizeStats | None:
    values = sorted(a for a in amounts if a > 0)
    if not values:
        return None
    return SizeStats(
        count=len(values),
        total=sum(values),
        minimum=values[0],
        p10=percentile(values, 10),
        p25=percentile(values, 25),
        median=percentile(values, 50),
        p75=percentile(values, 75),
        p90=percentile(values, 90),
        maximum=values[-1],
    )


def summarize(awards: Sequence[Award], top_n: int = 10) -> AwardStats:
    """Award size distribution, unique recipients and dollar concentration.

    Only positive award amounts count toward dollars. Negative or zero
    amounts (deobligations, corrections) are counted and reported separately.

    The size distribution uses single-listing awards only. USASpending's
    award amount is the whole award, so an award that also carries another
    program's money would overstate what this program pays. If every award
    is multi-listing, all awards are used and ``sizes_include_multi`` is set.
    Concentration and top recipients use all awards at award level.
    """
    positive = [a for a in awards if a.amount > 0]
    single = [a for a in positive if len(a.listings) <= 1]
    sizes = size_stats([a.amount for a in (single or positive)])
    sizes_include_multi = bool(positive) and not single

    by_recipient: dict[str, list[Award]] = defaultdict(list)
    for a in awards:
        by_recipient[a.recipient_key].append(a)

    totals: list[tuple[str, int, float]] = []
    for group in by_recipient.values():
        dollars = sum(a.amount for a in group if a.amount > 0)
        # Most common spelling of the name within the group.
        names = [a.recipient_name for a in group]
        name = max(set(names), key=names.count)
        totals.append((name, len(group), dollars))
    totals.sort(key=lambda t: (-t[2], t[0]))

    all_dollars = sum(a.amount for a in positive)
    top = [
        RecipientTotal(
            name=name,
            awards=n,
            dollars=d,
            share=(d / all_dollars) if all_dollars else 0.0,
        )
        for name, n, d in totals[:top_n]
    ]
    top10_dollars = sum(d for _, _, d in totals[:10])
    multi = [a for a in awards if len(a.listings) > 1]
    multi_dollars = sum(a.amount for a in multi if a.amount > 0)
    return AwardStats(
        awards_fetched=len(awards),
        non_positive=len(awards) - len(positive),
        unique_recipients=len(by_recipient),
        sizes=sizes,
        total_dollars=all_dollars,
        top_recipients=top,
        top10_share=(top10_dollars / all_dollars) if all_dollars else 0.0,
        multi_program=len(multi),
        multi_program_dollar_share=(multi_dollars / all_dollars) if all_dollars else 0.0,
        sizes_include_multi=sizes_include_multi,
    )
