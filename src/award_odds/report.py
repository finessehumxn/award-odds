"""Glue: run the queries for one listing and assemble a report."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Callable

from . import recipient_types as rt
from .client import USASpendingClient, build_filters
from .stats import AwardStats, summarize
from .verdict import Factor, Verdict, budget_factor, concentration_factor, decide, type_factor

LISTING_RE = re.compile(r"^\d{2}\.\d{3}$")


@dataclass
class TypeMix:
    total: int
    counts: dict[str, int]  # display label -> award count
    unclassified: int


@dataclass
class Report:
    listing: str
    start: date
    end: date
    total_awards: int
    stats: AwardStats
    truncated: bool
    pages: int
    mix: TypeMix | None
    org_type: str | None = None
    budget: float | None = None
    factors: list[Factor] = field(default_factory=list)
    verdict: Verdict | None = None
    notes: list[str] = field(default_factory=list)


def plural(n: int, word: str) -> str:
    return word if n == 1 else word + "s"


def years_ago(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year - years)
    except ValueError:  # Feb 29
        return d.replace(year=d.year - years, day=28)


def type_mix(client: USASpendingClient, listing: str, start: date, end: date, total: int) -> TypeMix:
    counts: dict[str, int] = {}
    for label, category in rt.MIX_CATEGORIES:
        counts[label] = client.count_awards(build_filters(listing, start, end, [category]))
    gov = client.count_awards(build_filters(listing, start, end, [rt.GOVERNMENT_PARENT]))
    gov_sub = sum(
        counts[label] for label, cat in rt.MIX_CATEGORIES if cat in rt.GOVERNMENT_SUBTYPES
    )
    counts["other government"] = max(gov - gov_sub, 0)
    classified = client.count_awards(build_filters(listing, start, end, rt.CLASSIFIED_UNION))
    return TypeMix(total=total, counts=counts, unclassified=max(total - classified, 0))


def build_report(
    client: USASpendingClient,
    listing: str,
    years: int = 5,
    org_type: str | None = None,
    budget: float | None = None,
    today: date | None = None,
    max_pages: int = 50,
    on_page: Callable[[int], None] | None = None,
) -> Report:
    if not LISTING_RE.match(listing):
        raise ValueError(f"assistance listing should look like 93.243, got {listing!r}")
    if org_type is not None and org_type not in rt.ORG_TYPES:
        raise ValueError(f"unknown org type {org_type!r}")

    end = today or date.today()
    start = years_ago(end, years)
    filters = build_filters(listing, start, end)

    total = client.count_awards(filters)
    fetched = client.fetch_awards(filters, max_pages=max_pages, on_page=on_page) if total else None
    stats = summarize(fetched.awards if fetched else [])
    mix = type_mix(client, listing, start, end, total) if total else None

    report = Report(
        listing=listing,
        start=start,
        end=end,
        total_awards=total,
        stats=stats,
        truncated=bool(fetched and fetched.truncated),
        pages=fetched.pages if fetched else 0,
        mix=mix,
        org_type=org_type,
        budget=budget,
    )
    if report.truncated:
        report.notes.append(
            f"Fetched the largest {stats.awards_fetched:,} of {total:,} awards "
            f"(--max-pages {max_pages}). Size and concentration figures cover "
            "those rows only and skew high."
        )
    if stats.non_positive:
        n = stats.non_positive
        report.notes.append(
            f"{n:,} {plural(n, 'award')} had a zero or negative amount (deobligations "
            f"or corrections) and {'is' if n == 1 else 'are'} left out of size and dollar figures."
        )
    if stats.multi_program:
        n = stats.multi_program
        sizes_scope = (
            "all awards, because none are single-listing"
            if stats.sizes_include_multi
            else "single-listing awards only"
        )
        report.notes.append(
            f"{n:,} {plural(n, 'award')} ({stats.multi_program_dollar_share:.1%} of award "
            f"dollars) also {'carries' if n == 1 else 'carry'} money from other assistance listings. USASpending's "
            "award amount covers the whole award, so total dollars, concentration and "
            f"top recipients overstate this program for those awards. Award sizes use "
            f"{sizes_scope}."
        )
    if mix and total and mix.unclassified / total > 0.10:
        report.notes.append(
            f"{mix.unclassified:,} awards ({mix.unclassified / total:.0%}) have no "
            "recipient type in USASpending, so the type factor is less reliable."
        )

    if total and (org_type or budget is not None):
        factors = []
        if org_type:
            label, category = rt.ORG_TYPES[org_type]
            if label in mix.counts:
                type_count = mix.counts[label]
            else:
                type_count = client.count_awards(build_filters(listing, start, end, [category]))
            factors.append(type_factor(label, type_count, total))
        if budget is not None and stats.sizes:
            factors.append(budget_factor(budget, stats.sizes))
        if stats.sizes:
            factors.append(concentration_factor(stats.top10_share, stats.unique_recipients))
        report.factors = factors
        # A band needs the recipient-type factor; without it R1 and R3 cannot apply.
        if org_type:
            report.verdict = decide(factors)
    return report
