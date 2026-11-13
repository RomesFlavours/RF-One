#!/usr/bin/env python
"""Run the mandatory Tips payment-connector acceptance tests (STEP 12B
integration §27).

Mirrors `test_tips_payment_execution.py` exactly. No real external provider
call is ever made — no network, no `MERCURY_SANDBOX_API_TOKEN` required.

Usage:
    python test_tips_payment_connector.py
    RFONE_DATABASE_URL=sqlite:///path/to/disposable.db python test_tips_payment_connector.py
"""

from __future__ import annotations

import sys

from rfone_data_store.database import (
    cleanup_disposable_test_database_url,
    create_configured_engine,
    create_session_factory,
    redact_database_url,
    resolve_test_database_url,
)
from rfone_data_store.tips_payment_connector_validation import run_validation


def main() -> int:
    url = resolve_test_database_url("tips_payment_connector")
    print(f"Database URL: {redact_database_url(url)}")

    engine = create_configured_engine(url)
    try:
        session_factory = create_session_factory(engine)
        result = run_validation(session_factory)
    finally:
        engine.dispose()
        cleanup_disposable_test_database_url(url)

    if result.success:
        print(f"Tips Payment Connector tests: SUCCESS ({len(result.checks_passed)}/{len(result.checks_passed)} checks passed)")
        return 0

    print(
        "Tips Payment Connector tests: FAILURE "
        f"({len(result.checks_passed)} passed, {len(result.checks_failed)} failed)"
    )
    for description in result.checks_failed:
        print(f"  FAILED: {description}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
