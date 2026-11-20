#!/usr/bin/env python
"""Run the ORDER_SERVICE_OWNER_SOURCE_SEMANTICS_001 synthetic-fixture test
suite.

Mirrors `test_tips_distribution_engine.py` exactly: builds a synthetic
fixture against a disposable database inside one transaction, runs the REAL
Tip Distribution Engine and AI Rule Authoring over it, asserts the required
behaviors, and always rolls back.

Usage:
    python test_tips_order_service_owner.py
    RFONE_DATABASE_URL=sqlite:///path/to/disposable.db python test_tips_order_service_owner.py
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
from rfone_data_store.tips_order_service_owner_validation import run_validation


def main() -> int:
    url = resolve_test_database_url("tips_order_service_owner")
    print(f"Database URL: {redact_database_url(url)}")

    engine = create_configured_engine(url)
    try:
        session_factory = create_session_factory(engine)
        result = run_validation(session_factory)
    finally:
        engine.dispose()
        cleanup_disposable_test_database_url(url)

    if result.success:
        print(f"Order Service Owner tests: SUCCESS ({len(result.checks_passed)}/{len(result.checks_passed)} checks passed)")
        return 0

    print(
        "Order Service Owner tests: FAILURE "
        f"({len(result.checks_passed)} passed, {len(result.checks_failed)} failed)"
    )
    for description in result.checks_failed:
        print(f"  FAILED: {description}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
