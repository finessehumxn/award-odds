from datetime import date

import httpx
import pytest

from award_odds.client import (
    GRANT_TYPE_CODES,
    Award,
    USASpendingClient,
    USASpendingError,
    build_filters,
)

from .conftest import load


def make_client(handler, sleeps=None):
    sleeps = sleeps if sleeps is not None else []
    return USASpendingClient(
        transport=httpx.MockTransport(handler), sleep=sleeps.append, backoff=0.5,
        min_interval=0,
    )


def test_parses_real_award_rows():
    rows = load("samhsa_93243_page1_trimmed.json")["results"]
    awards = [Award.from_row(r) for r in rows]
    first = awards[0]
    assert first.award_id == "H79TI087926"
    assert first.recipient_name == "HEALTH CARE SERVICES, CALIFORNIA DEPARTMENT OF"
    assert first.recipient_key == "7fe0d08f-685f-a9cc-f9f6-f9e6c6c20e22-C"
    assert first.amount == 322294432.0
    assert first.start_date == "2024-09-30"
    assert first.agency == "Department of Health and Human Services"


def test_missing_recipient_id_and_amount_fall_back():
    a = Award.from_row({"Award ID": "X1", "Recipient Name": " Some Org ", "Award Amount": None})
    assert a.recipient_key == "name:SOME ORG"
    assert a.recipient_name == "Some Org"
    assert a.amount == 0.0


def test_build_filters_shape_and_date_clamp():
    f = build_filters("93.243", date(2001, 1, 1), date(2026, 10, 7), ["nonprofit"])
    assert f["award_type_codes"] == GRANT_TYPE_CODES
    assert f["program_numbers"] == ["93.243"]
    assert f["time_period"] == [
        {"start_date": "2007-10-01", "end_date": "2026-10-07", "date_type": "new_awards_only"}
    ]
    assert f["recipient_type_names"] == ["nonprofit"]
    assert "recipient_type_names" not in build_filters("93.243", date(2020, 1, 1), date(2021, 1, 1))


def test_pagination_follows_has_next(epa_client, fake_api):
    result = epa_client.fetch_awards(build_filters("66.951", date(2021, 10, 7), date(2026, 10, 7)))
    assert result.pages == 2
    assert not result.truncated
    assert len(result.awards) == 131
    pages = [b["page"] for p, b in fake_api.requests if p.endswith("/spending_by_award/")]
    assert pages == [1, 2]
    body = fake_api.requests[0][1]
    assert body["limit"] == 100
    assert body["sort"] == "Award Amount" and body["order"] == "desc"


def test_max_pages_truncates_and_flags(epa_client):
    result = epa_client.fetch_awards(
        build_filters("66.951", date(2021, 10, 7), date(2026, 10, 7)), max_pages=1
    )
    assert result.pages == 1
    assert result.truncated
    assert len(result.awards) == 100


def test_count_awards(epa_client):
    f = build_filters("66.951", date(2021, 10, 7), date(2026, 10, 7), ["higher_education"])
    assert epa_client.count_awards(f) == 30


def test_retries_5xx_with_exponential_backoff():
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(503, text="busy")
        return httpx.Response(200, json={"results": {"grants": 7}})

    sleeps = []
    client = make_client(handler, sleeps)
    assert client.count_awards({}) == 7
    assert len(calls) == 3
    assert sleeps == [0.5, 1.0]


def test_429_honours_retry_after():
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "3"})
        return httpx.Response(200, json={"results": {"grants": 1}})

    sleeps = []
    assert make_client(handler, sleeps).count_awards({}) == 1
    assert sleeps == [3.0]


def test_transport_errors_are_retried():
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ConnectTimeout("timed out", request=request)
        return httpx.Response(200, json={"results": {"grants": 2}})

    assert make_client(handler).count_awards({}) == 2
    assert len(calls) == 2


def test_gives_up_after_max_attempts():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(502)

    sleeps = []
    with pytest.raises(USASpendingError, match="after 5 attempts"):
        make_client(handler, sleeps).count_awards({})
    assert len(calls) == 5
    assert sleeps == [0.5, 1.0, 2.0, 4.0]  # no sleep after the final attempt


def test_client_errors_are_not_retried():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(422, json={"detail": "Field 'limit' value '101' is above max '100'"})

    with pytest.raises(USASpendingError, match="422"):
        make_client(handler).count_awards({})
    assert len(calls) == 1


def test_multi_program_awards_are_detected():
    # Recorded 93.243 awards that also carry State Opioid Response (93.788) money.
    rows = load("samhsa_93243_page1_trimmed.json")["results"]
    assert all(Award.from_row(r).listings == ("93.243", "93.788") for r in rows)


def test_requests_are_spaced_by_min_interval():
    sleeps = []
    client = USASpendingClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"results": {"grants": 1}})),
        sleep=sleeps.append,
        min_interval=60,
    )
    client.count_awards({})
    client.count_awards({})
    assert len(sleeps) == 1 and 59 < sleeps[0] <= 60


def test_first_request_never_waits_even_right_after_boot(monkeypatch):
    # Regression: the spacing clock started at 0.0, so on a machine whose
    # monotonic clock was under min_interval (a fresh CI runner) the very
    # first request slept.
    import award_odds.client as client_mod

    monkeypatch.setattr(client_mod.time, "monotonic", lambda: 5.0)
    sleeps = []
    client = USASpendingClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"results": {"grants": 1}})),
        sleep=sleeps.append,
        min_interval=60,
    )
    client.count_awards({})
    assert sleeps == []
