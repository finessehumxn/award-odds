"""Optional smoke test against the real API. Run with AWARD_ODDS_LIVE=1."""

import os

import pytest

from award_odds.client import USASpendingClient
from award_odds.report import build_report

pytestmark = pytest.mark.skipif(os.environ.get("AWARD_ODDS_LIVE") != "1",
                                reason="set AWARD_ODDS_LIVE=1 to hit api.usaspending.gov")


def test_live_small_listing():
    with USASpendingClient() as client:
        report = build_report(client, "66.951", years=5, org_type="nonprofit", budget=100_000)
    assert report.total_awards > 0
    assert report.stats.sizes is not None
    assert report.verdict is not None
    assert report.verdict.band in {"Long shot", "Possible", "Good fit"}
