"""Minimal read-only Clover REST API client.

Only HTTP GET is used. No write methods are implemented on purpose so this
client structurally cannot perform POST/PUT/PATCH/DELETE requests.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import requests

from .config import CloverConfig

DEFAULT_TIMEOUT_SECONDS = 30
MAX_RETRIES = 5
BACKOFF_BASE_SECONDS = 1.5


@dataclass
class CloverGetResult:
    path: str
    status_code: int
    ok: bool
    data: Any = None
    error: str | None = None


class CloverClient:
    """Read-only GET client for the Clover production REST API."""

    def __init__(self, config: CloverConfig, session: requests.Session | None = None):
        self._config = config
        self._session = session or requests.Session()

    @property
    def merchant_id(self) -> str:
        return self._config.merchant_id

    @property
    def base_url(self) -> str:
        return self._config.base_url

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._config.api_token}",
            "Accept": "application/json",
        }

    def get(self, path: str, params: dict[str, Any] | None = None) -> CloverGetResult:
        """Issue a single GET request with conservative retry/backoff.

        Retries only on network errors, 429 (rate limit) and 5xx responses.
        Never retries on 4xx client errors other than 429, since a write
        operation is never attempted and retrying a genuine client error
        would not change the outcome.
        """
        url = f"{self._config.base_url}{path}"
        last_error: str | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = self._session.get(
                    url,
                    headers=self._headers(),
                    params=params,
                    timeout=DEFAULT_TIMEOUT_SECONDS,
                )
            except requests.RequestException as exc:
                last_error = f"network error: {exc.__class__.__name__}: {exc}"
                if attempt < MAX_RETRIES:
                    time.sleep(BACKOFF_BASE_SECONDS * attempt)
                    continue
                return CloverGetResult(path=path, status_code=0, ok=False, error=last_error)

            if response.status_code == 429:
                if attempt < MAX_RETRIES:
                    retry_after = response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else BACKOFF_BASE_SECONDS * attempt
                    time.sleep(delay)
                    continue
                return CloverGetResult(
                    path=path, status_code=429, ok=False, error="rate limited (retries exhausted)"
                )

            if 500 <= response.status_code < 600:
                if attempt < MAX_RETRIES:
                    time.sleep(BACKOFF_BASE_SECONDS * attempt)
                    continue
                return CloverGetResult(
                    path=path,
                    status_code=response.status_code,
                    ok=False,
                    error=f"server error after retries: HTTP {response.status_code}",
                )

            if response.status_code in (401, 403):
                return CloverGetResult(
                    path=path,
                    status_code=response.status_code,
                    ok=False,
                    error=f"authentication/authorization failed: HTTP {response.status_code}",
                )

            if response.status_code == 404:
                return CloverGetResult(
                    path=path, status_code=404, ok=False, error="endpoint not found (HTTP 404)"
                )

            if not response.ok:
                return CloverGetResult(
                    path=path,
                    status_code=response.status_code,
                    ok=False,
                    error=f"unexpected HTTP status {response.status_code}",
                )

            try:
                data = response.json()
            except ValueError as exc:
                return CloverGetResult(
                    path=path,
                    status_code=response.status_code,
                    ok=False,
                    error=f"malformed JSON response: {exc}",
                )

            return CloverGetResult(path=path, status_code=response.status_code, ok=True, data=data)

        return CloverGetResult(path=path, status_code=0, ok=False, error=last_error or "unknown error")
