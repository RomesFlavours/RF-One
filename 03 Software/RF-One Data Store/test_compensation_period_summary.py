#!/usr/bin/env python
"""Run the Compensation Period Summary synthetic-fixture test suite
(COMPENSATION_PERIOD_SUMMARY_001): weekly hours above 40, partial weeks,
Shifts crossing the Workweek boundary, FINAL Tips runs read without
duplication, zero versus not available, and the shared Workweek setting.

Mirrors `test_compensation_v1.py`: disposable database, always rolled back.

Usage:
    python test_compensation_period_summary.py
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
from rfone_data_store.compensation_period_summary_validation import run_validation


def main() -> int:
    url = resolve_test_database_url("compensation_period_summary")
    print(f"Database URL: {redact_database_url(url)}")

    engine = create_configured_engine(url)
    try:
        session_factory = create_session_factory(engine)
        result = run_validation(session_factory)
    finally:
        engine.dispose()
        cleanup_disposable_test_database_url(url)

    if result.success:
        print(
            "Compensation Period Summary tests: SUCCESS "
            f"({len(result.checks_passed)}/{len(result.checks_passed)} checks passed)"
        )
        return 0

    print(
        "Compensation Period Summary tests: FAILURE "
        f"({len(result.checks_passed)} passed, {len(result.checks_failed)} failed)"
    )
    for description in result.checks_failed:
        print(f"  FAILED: {description}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
