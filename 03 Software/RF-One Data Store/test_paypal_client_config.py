#!/usr/bin/env python
"""Tests for the PayPal connector's credential/endpoint resolution
(`rfone_data_store/technical/connectors/paypal/client.py`) —
baseline-closure fix: NO implicit production endpoint.

Pure environment-variable resolution logic, no database, no network call,
no real PayPal credentials. Complements `test_paypal_connector.py`, which
deliberately never exercises `client.py` at all (it only tests `parser.py`/
`mapping.py`/`ingest.py` against synthetic payloads).

Usage:
    python test_paypal_client_config.py
"""

from __future__ import annotations

import os
import sys

from rfone_data_store.technical.connectors.paypal.client import (
    DEFAULT_LIVE_BASE_URL,
    DEFAULT_SANDBOX_BASE_URL,
    PayPalCredentialsError,
    load_credentials_from_env,
)

_ENV_KEYS = ("PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET", "PAYPAL_API_BASE_URL")


class Result:
    def __init__(self) -> None:
        self.success = True
        self.checks_passed: list[str] = []
        self.checks_failed: list[str] = []

    def check(self, description: str, condition: bool) -> None:
        if condition:
            self.checks_passed.append(description)
        else:
            self.checks_failed.append(description)
            self.success = False


class _EnvScope:
    """Minimal context manager: clears the 3 PayPal env vars on entry,
    restores whatever was there before on exit — no external dependency,
    never touches any other environment variable."""

    def __enter__(self):
        self._saved = {key: os.environ.pop(key, None) for key in _ENV_KEYS}
        return self

    def __exit__(self, *exc_info):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def run_validation() -> Result:
    result = Result()

    with _EnvScope():
        os.environ["PAYPAL_CLIENT_ID"] = "fake-client-id"
        os.environ["PAYPAL_CLIENT_SECRET"] = "fake-client-secret"

        # (1) Unset PAYPAL_API_BASE_URL cannot silently contact production.
        credentials = load_credentials_from_env()
        result.check(
            "unset PAYPAL_API_BASE_URL resolves to the SANDBOX endpoint, never production",
            credentials.api_base_url == DEFAULT_SANDBOX_BASE_URL,
        )
        result.check(
            "the resolved sandbox endpoint is never PayPal's live API host",
            credentials.api_base_url != DEFAULT_LIVE_BASE_URL,
        )

    with _EnvScope():
        os.environ["PAYPAL_CLIENT_ID"] = "fake-client-id"
        os.environ["PAYPAL_CLIENT_SECRET"] = "fake-client-secret"
        os.environ["PAYPAL_API_BASE_URL"] = DEFAULT_SANDBOX_BASE_URL

        # (2) Explicit sandbox URL works (round-trips unchanged).
        credentials = load_credentials_from_env()
        result.check(
            "an explicitly configured sandbox PAYPAL_API_BASE_URL is honored unchanged",
            credentials.api_base_url == DEFAULT_SANDBOX_BASE_URL,
        )

    with _EnvScope():
        os.environ["PAYPAL_CLIENT_ID"] = "fake-client-id"
        os.environ["PAYPAL_CLIENT_SECRET"] = "fake-client-secret"
        os.environ["PAYPAL_API_BASE_URL"] = DEFAULT_LIVE_BASE_URL

        # (3) Explicit production URL remains possible when DELIBERATELY configured.
        credentials = load_credentials_from_env()
        result.check(
            "explicitly configuring the live PAYPAL_API_BASE_URL is still possible when deliberately set",
            credentials.api_base_url == DEFAULT_LIVE_BASE_URL,
        )

    with _EnvScope():
        # (4) Missing credentials still fail closed regardless of the URL fix.
        missing_credentials_raised = False
        try:
            load_credentials_from_env()
        except PayPalCredentialsError:
            missing_credentials_raised = True
        result.check(
            "missing PAYPAL_CLIENT_ID/PAYPAL_CLIENT_SECRET still fails closed with PayPalCredentialsError",
            missing_credentials_raised,
        )

    return result


def main() -> int:
    result = run_validation()
    if result.success:
        print(f"PayPal client config tests: SUCCESS ({len(result.checks_passed)}/{len(result.checks_passed)} checks passed)")
        return 0

    print(
        "PayPal client config tests: FAILURE "
        f"({len(result.checks_passed)} passed, {len(result.checks_failed)} failed)"
    )
    for description in result.checks_failed:
        print(f"  FAILED: {description}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
