"""PayPal REST API client — OAuth2 client-credentials token exchange plus
the Transaction Search API (`GET /v1/reporting/transactions`). No parsing,
mapping, or persistence logic lives here (see `parser.py`/`mapping.py`/
`ingest.py`) — this module only knows how to talk to PayPal's HTTP API,
using PayPal's official API architecture.

Consistent with CLAUDE.md's "External Technology": PayPal itself is the
commodity capability RF-One integrates with, not something to reimplement —
RF-One's own proprietary value is in the connector's normalization/
reconciliation layer around it (`parser.py`, `mapping.py`, `ingest.py`,
`bank_reconciliation/`), which is why every network call is isolated to
this one class, kept small and replaceable.

Credentials are read from environment variables only — never hard-coded or
committed (`PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, optionally
`PAYPAL_API_BASE_URL` to target the sandbox
`https://api-m.sandbox.paypal.com` instead of the live API). No real
PayPal credentials are available in this environment — this module is
exercised only up to the point of an HTTP call; `PayPalCredentialsError`/
network calls themselves are not covered by the test suite for that
reason (ported unchanged from `feature/purchased-invoice-intake-alignment`).
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import requests

DEFAULT_API_BASE_URL = "https://api-m.paypal.com"


class PayPalCredentialsError(RuntimeError):
    """Raised when PayPal API credentials are not configured in the
    environment — never silently falls back to a fake/sandbox default."""


@dataclass(frozen=True)
class PayPalCredentials:
    client_id: str
    client_secret: str
    api_base_url: str = DEFAULT_API_BASE_URL


def load_credentials_from_env() -> PayPalCredentials:
    """Reads `PAYPAL_CLIENT_ID`/`PAYPAL_CLIENT_SECRET`/`PAYPAL_API_BASE_URL`
    from the environment. Raises `PayPalCredentialsError` rather than
    returning a partially-configured/placeholder client — a real
    PayPal connection is either fully configured or explicitly not
    attempted."""
    client_id = os.environ.get("PAYPAL_CLIENT_ID")
    client_secret = os.environ.get("PAYPAL_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise PayPalCredentialsError(
            "PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET are not set in the environment - "
            "a real PayPal connection cannot be established without them."
        )
    api_base_url = os.environ.get("PAYPAL_API_BASE_URL", DEFAULT_API_BASE_URL)
    return PayPalCredentials(client_id=client_id, client_secret=client_secret, api_base_url=api_base_url)


class PayPalClient:
    """Thin wrapper around PayPal's OAuth2 token endpoint and Transaction
    Search API. Every network call is isolated to this class so
    `ingest.py` can be exercised end-to-end by supplying already-fetched
    raw `transaction_details` payloads directly, without ever calling
    PayPal — see `technical/connectors/paypal`'s own tests
    (`03 Software/RF-One Data Store/test_paypal_connector.py`), which cover
    `parser.py`/`mapping.py`/`ingest.py` this way and never instantiate
    this class."""

    def __init__(self, credentials: PayPalCredentials) -> None:
        self._credentials = credentials
        self._access_token: str | None = None

    def _fetch_access_token(self) -> str:
        basic = base64.b64encode(
            f"{self._credentials.client_id}:{self._credentials.client_secret}".encode("ascii")
        ).decode("ascii")
        response = requests.post(
            f"{self._credentials.api_base_url}/v1/oauth2/token",
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "client_credentials"},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()["access_token"]

    def _authorized_headers(self) -> dict[str, str]:
        if self._access_token is None:
            self._access_token = self._fetch_access_token()
        return {"Authorization": f"Bearer {self._access_token}", "Content-Type": "application/json"}

    def fetch_transactions(self, start_date: datetime, end_date: datetime, *, page: int = 1) -> dict[str, Any]:
        """One page of PayPal's Transaction Search API for the given UTC
        datetime window (PayPal itself limits a single request to a 31-day
        range — callers requesting a longer window are responsible for
        splitting it, this method does not)."""
        params = {
            "start_date": start_date.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "end_date": end_date.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "fields": "all",
            "page_size": 500,
            "page": page,
        }
        response = requests.get(
            f"{self._credentials.api_base_url}/v1/reporting/transactions",
            headers=self._authorized_headers(),
            params=params,
            timeout=60,
        )
        response.raise_for_status()
        return response.json()

    def fetch_all_transactions(self, start_date: datetime, end_date: datetime) -> list[dict[str, Any]]:
        """Pages through the full result set for the window, returning the
        raw `transaction_details` entries (PayPal's own vocabulary, entirely
        unmodified — `parser.py` is what interprets them)."""
        page = 1
        all_details: list[dict[str, Any]] = []
        while True:
            payload = self.fetch_transactions(start_date, end_date, page=page)
            details = payload.get("transaction_details", [])
            all_details.extend(details)
            total_pages = payload.get("total_pages", 1)
            if page >= total_pages:
                break
            page += 1
        return all_details
