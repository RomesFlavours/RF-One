#!/usr/bin/env python
"""Run the Tips payment-modes (MANUAL / AUTO WITH APPROVAL / AUTO WITHOUT
APPROVAL) synthetic-fixture test suite
(TASK_TIPS_RECONCILIATION_AND_PAYMENT_CONTROL_001 §4).

Usage:
    python test_tips_payment_modes.py
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
from rfone_data_store.tips_payment_modes_validation import run_validation


def main() -> int:
    url = resolve_test_database_url("tips_payment_modes")
    print(f"Database URL: {redact_database_url(url)}")

    engine = create_configured_engine(url)
    try:
        session_factory = create_session_factory(engine)
        result = run_validation(session_factory)
    finally:
        engine.dispose()
        cleanup_disposable_test_database_url(url)

    if result.success:
        print(f"Tips Payment Modes tests: SUCCESS ({len(result.checks_passed)}/{len(result.checks_passed)} checks passed)")
        return 0

    print(
        "Tips Payment Modes tests: FAILURE "
        f"({len(result.checks_passed)} passed, {len(result.checks_failed)} failed)"
    )
    for description in result.checks_failed:
        print(f"  FAILED: {description}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
