import json
from pathlib import Path

import httpx
import pytest

from award_odds.client import USASpendingClient

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str):
    return json.loads((FIXTURES / name).read_text())


class FakeUSASpending:
    """Serves recorded responses for assistance listing 66.951 (EPA Environmental
    Education Grants), recorded from the live API on 2026-10-07."""

    def __init__(self):
        self.counts = load("epa_66951_counts.json")["counts"]
        self.pages = {
            1: load("epa_66951_awards_page1.json"),
            2: load("epa_66951_awards_page2.json"),
        }
        self.requests: list[tuple[str, dict]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append((request.url.path, body))
        if request.url.path.endswith("/spending_by_award_count/"):
            key = ",".join(sorted(body["filters"].get("recipient_type_names", []))) or "*"
            return httpx.Response(200, json={"results": {"grants": self.counts[key]}})
        if request.url.path.endswith("/spending_by_award/"):
            return httpx.Response(200, json=self.pages[body["page"]])
        return httpx.Response(404, json={"detail": "not found"})


@pytest.fixture
def fake_api():
    return FakeUSASpending()


@pytest.fixture
def epa_client(fake_api):
    client = USASpendingClient(transport=httpx.MockTransport(fake_api), sleep=lambda s: None)
    yield client
    client.close()
