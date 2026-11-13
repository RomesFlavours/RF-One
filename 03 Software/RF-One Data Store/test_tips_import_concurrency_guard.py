#!/usr/bin/env python
"""Run the Tips Import Concurrency Guard synthetic-fixture test suite
(TIPS_IMPORT_CONCURRENCY_GUARD_001 task §8).

Mirrors `test_tips_clover_import.py` exactly: builds a synthetic fixture
against a disposable database, asserts the required behaviors, and always
rolls back. Never contacts Clover production — every Clover call in this
suite goes through `FakeCloverClient`/`RaisingCloverClient`
(`rfone_data_store/tips_import_concurrency_guard_validation.py`), never the
real API.

Usage:
    python test_tips_import_concurrency_guard.py
    RFONE_DATABASE_URL=sqlite:///path/to/disposable.db python test_tips_import_concurrency_guard.py
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
from rfone_data_store.tips_import_concurrency_guard_validation import run_validation


def main() -> int:
    url = resolve_test_database_url("tips_import_concurrency_guard")
    print(f"Database URL: {redact_database_url(url)}")

    engine = create_configured_engine(url)
    try:
        session_factory = create_session_factory(engine)
        result = run_validation(session_factory)
    finally:
        engine.dispose()
        cleanup_disposable_test_database_url(url)

    if result.success:
        print(f"Tips Import Concurrency Guard tests: SUCCESS ({len(result.checks_passed)}/{len(result.checks_passed)} checks passed)")
        return 0

    print(
        "Tips Import Concurrency Guard tests: FAILURE "
        f"({len(result.checks_passed)} passed, {len(result.checks_failed)} failed)"
    )
    for description in result.checks_failed:
        print(f"  FAILED: {description}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
