"""Thin client for the public USASpending.gov search API.

Only two endpoints are used:

* ``POST /api/v2/search/spending_by_award/``       award rows, paginated
* ``POST /api/v2/search/spending_by_award_count/`` award counts for a filter set

No API key is needed. Requests use modest page sizes, a timeout, and retry
with exponential backoff on 429 and 5xx responses and on transport errors.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Iterable

import httpx

BASE_URL = "https://api.usaspending.gov"
AWARDS_PATH = "/api/v2/search/spending_by_award/"
COUNT_PATH = "/api/v2/search/spending_by_award_count/"

# Assistance award type codes for grants:
# 02 block grant, 03 formula grant, 04 project grant, 05 cooperative agreement.
GRANT_TYPE_CODES = ["02", "03", "04", "05"]

# The search endpoints reject start dates earlier than this.
EARLIEST_SEARCH_DATE = date(2007, 10, 1)

PAGE_LIMIT = 100  # the API maximum for spending_by_award

AWARD_FIELDS = [
    "Award ID",
    "Recipient Name",
    "recipient_id",
    "Award Amount",
    "Start Date",
    "Awarding Agency",
    "Assistance Listings",
]

RETRY_STATUSES = {429, 500, 502, 503, 504}


class USASpendingError(RuntimeError):
    """Raised when the API returns an error that retrying will not fix."""


@dataclass(frozen=True)
class Award:
    award_id: str
    recipient_name: str
    recipient_key: str
    amount: float
    start_date: str | None
    agency: str | None
    # Every assistance listing that has obligations on this award. When there
    # is more than one, "Award Amount" includes money from the other programs.
    listings: tuple[str, ...] = ()

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Award":
        name = (row.get("Recipient Name") or "UNKNOWN RECIPIENT").strip()
        # recipient_id is a stable hash per recipient; fall back to the name
        # when it is missing so repeat winners are still grouped.
        key = row.get("recipient_id") or f"name:{name.upper()}"
        amount = row.get("Award Amount")
        return cls(
            award_id=str(row.get("Award ID") or ""),
            recipient_name=name,
            recipient_key=key,
            amount=float(amount) if amount is not None else 0.0,
            start_date=row.get("Start Date"),
            agency=row.get("Awarding Agency"),
            listings=tuple(
                sorted(
                    {
                        item["cfda_number"]
                        for item in (row.get("Assistance Listings") or [])
                        if isinstance(item, dict) and item.get("cfda_number")
                    }
                )
            ),
        )


@dataclass
class FetchResult:
    awards: list[Award]
    pages: int
    truncated: bool


def build_filters(
    listing: str,
    start: date,
    end: date,
    recipient_types: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Filter block shared by the award and count endpoints.

    ``new_awards_only`` restricts the window to awards whose start falls in
    it, which matches the question "who won this program recently" better
    than any award with activity in the window.
    """
    filters: dict[str, Any] = {
        "award_type_codes": GRANT_TYPE_CODES,
        "program_numbers": [listing],
        "time_period": [
            {
                "start_date": max(start, EARLIEST_SEARCH_DATE).isoformat(),
                "end_date": end.isoformat(),
                "date_type": "new_awards_only",
            }
        ],
    }
    if recipient_types:
        filters["recipient_type_names"] = list(recipient_types)
    return filters


class USASpendingClient:
    def __init__(
        self,
        transport: httpx.BaseTransport | None = None,
        base_url: str = BASE_URL,
        timeout: float = 30.0,
        max_attempts: int = 5,
        backoff: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
        min_interval: float = 0.25,
    ) -> None:
        self._http = httpx.Client(
            base_url=base_url,
            timeout=timeout,
            transport=transport,
            headers={"User-Agent": "award-odds (+https://github.com/finessehumxn/award-odds)"},
        )
        self.max_attempts = max_attempts
        self.backoff = backoff
        self._sleep = sleep
        # Minimum gap between requests. The API has no published rate limit,
        # but it starts dropping connections under bursts of requests.
        self.min_interval = min_interval
        self._last_request = 0.0

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "USASpendingClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- transport ---------------------------------------------------------

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        last_error: str = ""
        for attempt in range(1, self.max_attempts + 1):
            wait = self._last_request + self.min_interval - time.monotonic()
            if wait > 0:
                self._sleep(wait)
            self._last_request = time.monotonic()
            try:
                resp = self._http.post(path, json=body)
            except httpx.TransportError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            else:
                if resp.status_code < 400:
                    return resp.json()
                if resp.status_code not in RETRY_STATUSES:
                    raise USASpendingError(
                        f"{path} returned {resp.status_code}: {resp.text[:300]}"
                    )
                last_error = f"HTTP {resp.status_code}"
                retry_after = resp.headers.get("Retry-After")
                if retry_after and retry_after.isdigit() and attempt < self.max_attempts:
                    self._sleep(float(retry_after))
                    continue
            if attempt < self.max_attempts:
                self._sleep(self.backoff * 2 ** (attempt - 1))
        raise USASpendingError(
            f"{path} failed after {self.max_attempts} attempts ({last_error})"
        )

    # -- endpoints ---------------------------------------------------------

    def count_awards(self, filters: dict[str, Any]) -> int:
        data = self._post(COUNT_PATH, {"filters": filters})
        return int(data.get("results", {}).get("grants", 0))

    def fetch_awards(
        self,
        filters: dict[str, Any],
        max_pages: int = 50,
        on_page: Callable[[int], None] | None = None,
    ) -> FetchResult:
        """Page through award rows until ``hasNext`` is false or ``max_pages``.

        Sorted by award amount, largest first, so a truncated fetch still
        contains the biggest awards (and is flagged as truncated).
        """
        awards: list[Award] = []
        page = 0
        has_next = True
        while has_next and page < max_pages:
            page += 1
            data = self._post(
                AWARDS_PATH,
                {
                    "filters": filters,
                    "fields": AWARD_FIELDS,
                    "page": page,
                    "limit": PAGE_LIMIT,
                    "sort": "Award Amount",
                    "order": "desc",
                },
            )
            awards.extend(Award.from_row(r) for r in data.get("results", []))
            has_next = bool(data.get("page_metadata", {}).get("hasNext"))
            if on_page:
                on_page(page)
        return FetchResult(awards=awards, pages=page, truncated=has_next)
