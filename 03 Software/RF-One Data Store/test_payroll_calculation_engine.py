#!/usr/bin/env python
"""Run the Payroll Calculation Engine synthetic-fixture test suite (Product
Owner decision, corrected Option C).

Mirrors `test_identity_authority_signature.py` exactly: builds a synthetic
fixture against a disposable database, asserts the required behaviors, and
always rolls back.

Usage:
    python test_payroll_calculation_engine.py
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
from rfone_data_store.payroll_calculation_validation import run_validation


def main() -> int:
    url = resolve_test_database_url("payroll_calculation_engine")
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
            "Payroll Calculation Engine tests: SUCCESS "
            f"({len(result.checks_passed)}/{len(result.checks_passed)} checks passed)"
        )
        return 0

    print(
        "Payroll Calculation Engine tests: FAILURE "
        f"({len(result.checks_passed)} passed, {len(result.checks_failed)} failed)"
    )
    for description in result.checks_failed:
        print(f"  FAILED: {description}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
