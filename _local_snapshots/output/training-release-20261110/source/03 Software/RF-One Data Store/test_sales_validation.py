#!/usr/bin/env python
"""Run the Sales module synthetic validation suite (TASK_REPOSITORY_STABILIZATION_001).

Mirrors `test_organization_validation.py`'s use of
`sales_validation.run_validation()`: builds a synthetic fixture against a
disposable database inside one transaction, asserts the required behaviors,
and always rolls back — never leaves synthetic rows behind.

If `RFONE_DATABASE_URL` is unset, a fresh disposable SQLite database is
self-provisioned automatically (GLOBAL_INTEGRITY_FIX_001 / C-4); if it is
set but points at the shared operational default (`data/rfone.db`), this
refuses to run (`UnsafeTestDatabaseError`) instead of risking real data.

Usage:
    python test_sales_validation.py
    RFONE_DATABASE_URL=sqlite:///path/to/disposable.db python test_sales_validation.py
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
from rfone_data_store.sales_validation import run_validation


def main() -> int:
    url = resolve_test_database_url("sales")
    print(f"Database URL: {redact_database_url(url)}")

    engine = create_configured_engine(url)
    try:
        session_factory = create_session_factory(engine)
        result = run_validation(session_factory)
    finally:
        engine.dispose()
        cleanup_disposable_test_database_url(url)

    if result.success:
        print(f"Sales (TASK_REPOSITORY_STABILIZATION_001) tests: SUCCESS ({len(result.checks_passed)}/{len(result.checks_passed)} checks passed)")
        return 0

    print(
        "Sales (TASK_REPOSITORY_STABILIZATION_001) tests: FAILURE "
        f"({len(result.checks_passed)} passed, {len(result.checks_failed)} failed)"
    )
    for description in result.checks_failed:
        print(f"  FAILED: {description}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
