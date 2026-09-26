#!/usr/bin/env python
"""Run the Clover acquisition jobs synthetic test suite (CLOVER_ACQUISITION_JOBS_001):
Sync Now, Historical Backfill and the job lifecycle, against a disposable
database. Never contacts Clover production.

Usage:
    python test_clover_acquisition_jobs.py
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
from rfone_data_store.clover_acquisition_jobs_validation import run_validation


def main() -> int:
    url = resolve_test_database_url("clover_acquisition_jobs")
    print(f"Database URL: {redact_database_url(url)}")

    engine = create_configured_engine(url)
    try:
        session_factory = create_session_factory(engine)
        result = run_validation(session_factory, database_url=url)
    finally:
        engine.dispose()
        cleanup_disposable_test_database_url(url)

    if result.success:
        print(f"Clover acquisition jobs tests: SUCCESS ({len(result.checks_passed)}/{len(result.checks_passed)} checks passed)")
        return 0

    print(
        "Clover acquisition jobs tests: FAILURE "
        f"({len(result.checks_passed)} passed, {len(result.checks_failed)} failed)"
    )
    for description in result.checks_failed:
        print(f"  FAILED: {description}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
