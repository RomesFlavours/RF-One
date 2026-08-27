#!/usr/bin/env python
"""Run the Payroll synthetic-fixture test suite (TASK_PAYROLL_001 §34).

Mirrors `test_tips_engine.py`/`test_restaurant_profile_bootstrap.py`: builds
a synthetic fixture against the currently configured database inside one
transaction, asserts the required behaviors, and always rolls back.

Like those existing test entry points, this inserts a synthetic
`SourceSystem(code="CLOVER")`/`SourceSystem(code="ADP")` row, which would
collide with real catalog rows already present on an already-populated
database (e.g. the local `data/rfone.db`) before the transaction is even
rolled back. Run this against a fresh/staging database, exactly as
`create_database.py` already expects for `schema_validation.py`.

Usage:
    RFONE_DATABASE_URL=sqlite:///path/to/fresh.db python test_payroll_engine.py
"""

from __future__ import annotations

import sys

from rfone_data_store.database import create_configured_engine, create_session_factory, get_database_url, redact_database_url
from rfone_data_store.payroll_validation import run_validation


def main() -> int:
    url = get_database_url()
    print(f"Database URL: {redact_database_url(url)}")

    engine = create_configured_engine(url)
    session_factory = create_session_factory(engine)
    result = run_validation(session_factory)

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
