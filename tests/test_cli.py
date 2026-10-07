import json
from datetime import date

import httpx

from award_odds.cli import main
from award_odds.client import USASpendingClient

TODAY = date(2026, 10, 7)


def run(capsys, client, *argv):
    code = main(list(argv), client=client, today=TODAY)
    out = capsys.readouterr()
    return code, out.out, out.err


def test_text_report_good_fit(capsys, epa_client):
    code, out, _ = run(capsys, epa_client, "66.951", "--org-type", "nonprofit", "--budget", "100000")
    assert code == 0
    assert "new grant awards 2021-10-07 to 2026-10-07" in out
    assert "awards                 131" in out
    assert "unique recipients      119" in out
    assert "median                 $100,000" in out
    assert "top 10 recipients took 15.6% of award dollars" in out
    assert "nonprofit                   97   74.0%" in out
    assert "97 of 131 awards (74.0%) went to recipients classified as nonprofit" in out
    assert "VERDICT: Good fit" in out
    assert "fired: R3" in out
    assert "R1  Your type won under 5% of awards -> Long shot." in out


def test_type_with_no_wins_is_long_shot(capsys, epa_client, fake_api):
    code, out, _ = run(capsys, epa_client, "66.951", "--org-type", "small_business")
    assert code == 0
    assert "0 of 131 awards (0.0%) went to recipients classified as small business" in out
    assert "VERDICT: Long shot" in out and "fired: R1" in out
    # small_business is not in the displayed mix, so it costs one extra count query
    types = [b["filters"].get("recipient_type_names") for p, b in fake_api.requests]
    assert ["small_business"] in types


def test_budget_without_org_type_shows_factor_but_no_band(capsys, epa_client):
    code, out, _ = run(capsys, epa_client, "66.951", "--budget", "500000")
    assert code == 0
    assert "larger than 90% of past awards" in out
    assert "VERDICT: none" in out


def test_json_output(capsys, epa_client):
    code, out, _ = run(capsys, epa_client, "66.951", "--org-type", "university", "--json")
    assert code == 0
    data = json.loads(out)
    assert data["total_awards"] == 131
    assert data["mix"]["counts"]["higher education"] == 30
    assert data["verdict"]["band"] == "Good fit"
    assert data["verdict"]["factors"][0]["evidence"].startswith("30 of 131 awards")
    assert len(data["rules"]) == 4


def test_no_awards(capsys):
    def handler(request):
        if request.url.path.endswith("_count/"):
            return httpx.Response(200, json={"results": {"grants": 0}})
        raise AssertionError("should not page when the count is zero")

    client = USASpendingClient(transport=httpx.MockTransport(handler))
    code, out, _ = run(capsys, client, "99.999", "--org-type", "nonprofit")
    assert code == 0
    assert "No grant awards found" in out


def test_bad_listing_exits_2(capsys, epa_client):
    code, _, err = run(capsys, epa_client, "93243")
    assert code == 2
    assert "should look like 93.243" in err


def test_api_failure_exits_1(capsys):
    client = USASpendingClient(transport=httpx.MockTransport(lambda r: httpx.Response(500)),
                               sleep=lambda s: None)
    code, _, err = run(capsys, client, "66.951")
    assert code == 1
    assert "USASpending API error" in err


def test_truncation_note(capsys, epa_client):
    code, out, _ = run(capsys, epa_client, "66.951", "--max-pages", "1")
    assert code == 0
    assert "Fetched the largest 100 of 131 awards" in out
    assert "unique recipients      93 (in fetched rows)" in out
