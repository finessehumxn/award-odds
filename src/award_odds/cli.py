"""Command line entry point: ``award-odds 93.243 --org-type nonprofit --budget 250000``."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import date
from typing import Sequence

from . import __version__
from .client import USASpendingClient, USASpendingError
from .recipient_types import ORG_TYPES
from .report import Report, build_report
from .verdict import RULES, money


def to_json(report: Report) -> str:
    data = asdict(report)
    data["start"] = report.start.isoformat()
    data["end"] = report.end.isoformat()
    data["rules"] = RULES if report.verdict else []
    data["source"] = "https://api.usaspending.gov (spending_by_award, spending_by_award_count)"
    return json.dumps(data, indent=2)


def render_text(report: Report) -> str:
    out: list[str] = []
    w = out.append
    w(f"Assistance listing {report.listing}  |  new grant awards {report.start} to {report.end}")
    w("Source: USASpending.gov (public API, no key)")
    w("")
    if report.total_awards == 0:
        w("No grant awards found for this listing in this window.")
        w("Check the listing number, or widen --years.")
        return "\n".join(out)

    s = report.stats
    w("AWARDS")
    w(f"  awards                 {report.total_awards:,}")
    suffix = " (in fetched rows)" if report.truncated else ""
    w(f"  unique recipients      {s.unique_recipients:,}{suffix}")
    if s.sizes:
        z = s.sizes
        w(f"  total award dollars    {money(s.total_dollars)}{suffix}")
        w("")
        scope = "all awards" if s.sizes_include_multi or not s.multi_program else "single-listing awards"
        w(f"AWARD SIZE ({scope}, n={z.count:,})")
        w(f"  p25                    {money(z.p25)}")
        w(f"  median                 {money(z.median)}")
        w(f"  p75                    {money(z.p75)}")
        w(f"  max                    {money(z.maximum)}")
        w("")
        w("CONCENTRATION")
        w(f"  top 10 recipients took {s.top10_share:.1%} of award dollars")
    w("")
    w("TOP RECIPIENTS (by award dollars)")
    for i, r in enumerate(s.top_recipients, 1):
        w(f"  {i:>2}. {r.name[:52]:<52} {r.awards:>4} awards  {money(r.dollars):>16}  {r.share:6.1%}")

    if report.mix:
        m = report.mix
        w("")
        w("RECIPIENT TYPE MIX (award counts, USASpending classification)")
        rows = list(m.counts.items()) + [("no type recorded", m.unclassified)]
        for label, n in rows:
            if n:
                w(f"  {label:<22} {n:>7,}  {n / m.total:6.1%}")

    if report.factors:
        w("")
        who = ORG_TYPES[report.org_type][0] if report.org_type else "you"
        w(f"FIT FOR: {who}" + (f", budget {money(report.budget)}" if report.budget is not None else ""))
        for f in report.factors:
            w(f"  [{f.rating:<8}] {f.name}")
            w(f"             evidence: {f.evidence}")
            w(f"             rule:     {f.rule}")
        w("")
        if report.verdict:
            w(f"VERDICT: {report.verdict.band}")
            w(f"  fired: {report.verdict.rule_fired}")
            w("  rules, applied in order:")
            for r in RULES:
                w(f"    {r}")
        else:
            w("VERDICT: none (pass --org-type to get a band; the type factor drives rules R1 and R3)")

    if report.notes:
        w("")
        w("NOTES")
        for n in report.notes:
            w(f"  - {n}")
    w("")
    w("Past awards describe who won, not your odds. Grounded, not calibrated.")
    return "\n".join(out)


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="award-odds",
        description="Before you apply for a federal grant, see who actually won it.",
    )
    p.add_argument("listing", help="assistance listing (CFDA) number, e.g. 93.243")
    p.add_argument("--years", type=int, default=5, help="look-back window in years (default 5)")
    p.add_argument("--org-type", choices=sorted(ORG_TYPES), help="your organization type")
    p.add_argument("--budget", type=float, help="total amount you plan to request, in dollars")
    p.add_argument("--max-pages", type=int, default=50,
                   help="cap on 100-row pages fetched (default 50 = 5,000 awards)")
    p.add_argument("--json", action="store_true", help="print JSON instead of text")
    p.add_argument("--version", action="version", version=f"award-odds {__version__}")
    args = p.parse_args(argv)
    if args.years < 1:
        p.error("--years must be at least 1")
    if args.max_pages < 1:
        p.error("--max-pages must be at least 1")
    if args.budget is not None and args.budget <= 0:
        p.error("--budget must be positive")
    return args


def main(
    argv: Sequence[str] | None = None,
    client: USASpendingClient | None = None,
    today: date | None = None,
) -> int:
    args = parse_args(argv)
    own_client = client is None
    client = client or USASpendingClient()
    progress = None
    if not args.json and sys.stderr.isatty():
        def progress(page: int) -> None:
            print(f"\rfetching awards, page {page}...", end="", file=sys.stderr, flush=True)
    try:
        report = build_report(
            client,
            args.listing,
            years=args.years,
            org_type=args.org_type,
            budget=args.budget,
            today=today,
            max_pages=args.max_pages,
            on_page=progress,
        )
    except ValueError as exc:
        print(f"award-odds: {exc}", file=sys.stderr)
        return 2
    except USASpendingError as exc:
        print(f"award-odds: USASpending API error: {exc}", file=sys.stderr)
        return 1
    finally:
        if progress:
            print("\r" + " " * 40 + "\r", end="", file=sys.stderr)
        if own_client:
            client.close()
    print(to_json(report) if args.json else render_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
