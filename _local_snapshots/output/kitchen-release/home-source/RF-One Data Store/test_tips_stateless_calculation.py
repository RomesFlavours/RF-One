#!/usr/bin/env python
"""Run the stateless Tips calculation synthetic-fixture test suite
(TIPS_STATELESS_CALCULATION_001).

Mirrors `test_tips_distribution_engine.py` exactly: builds a synthetic
fixture against a disposable database inside one transaction, runs the
REAL Tip Distribution Engine over it, asserts the audit report correctly
explains that output, and always rolls back.

Usage:
    python test_tips_stateless_calculation.py
    RFONE_DATABASE_URL=sqlite:///path/to/disposable.db python test_tips_stateless_calculation.py
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
from rfone_data_store.tips_stateless_calculation_validation import run_validation


def main() -> int:
    url = resolve_test_database_url("tips_stateless_calculation")
    print(f"Database URL: {redact_database_url(url)}")

    engine = create_configured_engine(url)
    try:
        session_factory = create_session_factory(engine)
        result = run_validation(session_factory)
    finally:
        engine.dispose()
        cleanup_disposable_test_database_url(url)

    if result.success:
        print(f"Stateless Tips Calculation tests: SUCCESS ({len(result.checks_passed)}/{len(result.checks_passed)} checks passed)")
        return 0

    print(
        "Stateless Tips Calculation tests: FAILURE "
        f"({len(result.checks_passed)} passed, {len(result.checks_failed)} failed)"
    )
    for description in result.checks_failed:
        print(f"  FAILED: {description}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
