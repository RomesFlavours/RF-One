#!/usr/bin/env python
"""Run the Tips engine's synthetic-fixture test suite (TASK_TIPS_001 §23).

Mirrors `create_database.py`'s use of `schema_validation.run_validation()`:
builds a synthetic fixture against the currently configured database inside
one transaction, asserts the required behaviors, and always rolls back —
never leaves synthetic Tip/Policy/Allocation rows behind.

Like `schema_validation.py`'s own fixture, this inserts a synthetic
`SourceSystem(code="CLOVER")` row, which collides with the real one already
present on an already-ingested database (e.g. the populated local
`data/rfone.db`) before the transaction is even rolled back. Run this
against a fresh/staging database (e.g. one freshly brought to head via
`rfone_data_store.database.run_migrations_to_head` on an empty SQLite file),
exactly as `create_database.py` already expects for `schema_validation.py` —
this is a pre-existing repository convention, not new to this task.

Usage:
    RFONE_DATABASE_URL=sqlite:///path/to/fresh.db python test_tips_engine.py
"""

from __future__ import annotations

import sys

from rfone_data_store.database import create_configured_engine, create_session_factory, get_database_url, redact_database_url
from rfone_data_store.tips_validation import run_validation


def main() -> int:
    url = get_database_url()
    print(f"Database URL: {redact_database_url(url)}")

    engine = create_configured_engine(url)
    session_factory = create_session_factory(engine)
    result = run_validation(session_factory)

    if result.success:
        print(f"Tips engine tests: SUCCESS ({len(result.checks_passed)}/{len(result.checks_passed)} checks passed)")
        return 0

    print(
        "Tips engine tests: FAILURE "
        f"({len(result.checks_passed)} passed, {len(result.checks_failed)} failed)"
    )
    for description in result.checks_failed:
        print(f"  FAILED: {description}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
