#!/usr/bin/env python
"""Run the Selection (Resume Screening) synthetic validation suite
(TASK_SELECTION_001).

Mirrors `test_sales_validation.py`'s use of
`selection_validation.run_validation()`: builds synthetic fixtures against a
disposable database, asserts the required behaviors, and cleans up
afterward.

Note that `selection_validation.run_validation()` itself performs real
`session.commit()` calls internally (each of its ~20 `_assert_*` helpers)
and relies on manual delete-based cleanup rather than a single rolled-back
transaction — see `07 Tasks/Reports/GLOBAL_INTEGRITY_FIX_001_TEST_DATABASE_ISOLATION_REPORT.md`.
Running it against a disposable, self-provisioned database (rather than
rewriting its internals) makes that pattern safe: even if an exception
strikes between a commit and its cleanup, the whole disposable database file
is discarded afterward regardless. If `RFONE_DATABASE_URL` is unset, a fresh
disposable SQLite database is self-provisioned automatically
(GLOBAL_INTEGRITY_FIX_001 / C-4); if it is set but points at the shared
operational default (`data/rfone.db`), this refuses to run
(`UnsafeTestDatabaseError`) instead of risking real data.

Usage:
    python test_selection_engine.py
    RFONE_DATABASE_URL=sqlite:///path/to/disposable.db python test_selection_engine.py
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
from rfone_data_store.selection_validation import run_validation


def main() -> int:
    url = resolve_test_database_url("selection")
    print(f"Database URL: {redact_database_url(url)}")

    engine = create_configured_engine(url)
    try:
        session_factory = create_session_factory(engine)
        result = run_validation(session_factory)
    finally:
        engine.dispose()
        cleanup_disposable_test_database_url(url)

    if result.success:
        print(f"Selection engine (TASK_SELECTION_001) tests: SUCCESS ({len(result.checks_passed)}/{len(result.checks_passed)} checks passed)")
        return 0

    print(
        "Selection engine (TASK_SELECTION_001) tests: FAILURE "
        f"({len(result.checks_passed)} passed, {len(result.checks_failed)} failed)"
    )
    for description in result.checks_failed:
        print(f"  FAILED: {description}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
