#!/usr/bin/env python
"""Run the Compensation-from-real-hours synthetic-fixture test suite
(`payroll_calculation/compensation_period.py`): inclusion by Shifts, never
by Compensation Terms; Regular / Overtime / Total Hours per Workweek; wage,
bonus and tips shown or MISSING; separate hours and compensation-data
statuses; Restaurants without a Legal Entity reported, never guessed.

Mirrors `test_compensation_period_summary.py`: disposable database, always
rolled back.

Usage:
    python test_compensation_period.py
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
from rfone_data_store.compensation_period_validation import run_validation


def main() -> int:
    url = resolve_test_database_url("compensation_period")
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
            "Compensation from real hours tests: SUCCESS "
            f"({len(result.checks_passed)}/{len(result.checks_passed)} checks passed)"
        )
        return 0

    print(
        "Compensation from real hours tests: FAILURE "
        f"({len(result.checks_passed)} passed, {len(result.checks_failed)} failed)"
    )
    for description in result.checks_failed:
        print(f"  FAILED: {description}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
