#!/usr/bin/env python
"""Run the central Clover data acquisition synthetic-fixture test suite
(CLOVER_DATA_ACQUISITION_ARCHITECTURE_001).

Mirrors `test_tips_distribution_engine.py` exactly: builds a synthetic
fixture against a disposable database inside one transaction, asserts the
required behaviors, and always rolls back. Never contacts Clover
production — every Clover call in this suite goes through `FakeCloverClient`
(`rfone_data_store/clover_acquisition_validation.py`), never the real API.

Usage:
    python test_clover_acquisition.py
    RFONE_DATABASE_URL=sqlite:///path/to/disposable.db python test_clover_acquisition.py
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
from rfone_data_store.clover_acquisition_validation import run_validation


def main() -> int:
    url = resolve_test_database_url("clover_acquisition")
    print(f"Database URL: {redact_database_url(url)}")

    engine = create_configured_engine(url)
    try:
        session_factory = create_session_factory(engine)
        result = run_validation(session_factory)
    finally:
        engine.dispose()
        cleanup_disposable_test_database_url(url)

    if result.success:
        print(f"Clover acquisition tests: SUCCESS ({len(result.checks_passed)}/{len(result.checks_passed)} checks passed)")
        return 0

    print(
        "Clover acquisition tests: FAILURE "
        f"({len(result.checks_passed)} passed, {len(result.checks_failed)} failed)"
    )
    for description in result.checks_failed:
        print(f"  FAILED: {description}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
