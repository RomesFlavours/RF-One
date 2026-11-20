#!/usr/bin/env python
"""Run the Payroll synthetic-fixture test suite (TASK_PAYROLL_001 §34).

Mirrors `test_tips_engine.py`/`test_restaurant_profile_bootstrap.py`: builds
a synthetic fixture against a disposable database inside one transaction,
asserts the required behaviors, and always rolls back.

This inserts a synthetic `SourceSystem(code="CLOVER")`/`SourceSystem(code="ADP")`
row, which would collide with real catalog rows on an already-populated
database. To make that impossible rather than merely documented: if
`RFONE_DATABASE_URL` is unset, a fresh disposable SQLite database is
self-provisioned automatically (GLOBAL_INTEGRITY_FIX_001 / C-4); if it is
set but points at the shared operational default (`data/rfone.db`), this
refuses to run (`UnsafeTestDatabaseError`) instead of risking real data.

Usage:
    python test_payroll_engine.py
    RFONE_DATABASE_URL=sqlite:///path/to/disposable.db python test_payroll_engine.py
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
from rfone_data_store.payroll_validation import run_validation


def main() -> int:
    url = resolve_test_database_url("payroll")
    print(f"Database URL: {redact_database_url(url)}")

    engine = create_configured_engine(url)
    try:
        session_factory = create_session_factory(engine)
        result = run_validation(session_factory)
    finally:
        engine.dispose()
        cleanup_disposable_test_database_url(url)

    if result.success:
        print(f"Payroll engine tests: SUCCESS ({len(result.checks_passed)}/{len(result.checks_passed)} checks passed)")
        return 0

    print(
        "Payroll engine tests: FAILURE "
        f"({len(result.checks_passed)} passed, {len(result.checks_failed)} failed)"
    )
    for description in result.checks_failed:
        print(f"  FAILED: {description}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
