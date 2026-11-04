#!/usr/bin/env python
"""Run the EMPLOYEE_ASSIGNMENT_CLOVER_ALIGNMENT_001 synthetic-fixture test
suite.

Mirrors `test_tips_order_service_owner.py` exactly: builds a synthetic
fixture against a disposable database inside one transaction, exercises
real model/engine code, asserts the required behaviors, and always rolls
back.

Usage:
    python test_employee_assignment_one_role.py
    RFONE_DATABASE_URL=sqlite:///path/to/disposable.db python test_employee_assignment_one_role.py
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
from rfone_data_store.employee_assignment_one_role_validation import run_validation


def main() -> int:
    url = resolve_test_database_url("employee_assignment_one_role")
    print(f"Database URL: {redact_database_url(url)}")

    engine = create_configured_engine(url)
    try:
        session_factory = create_session_factory(engine)
        result = run_validation(session_factory)
    finally:
        engine.dispose()
        cleanup_disposable_test_database_url(url)

    if result.success:
        print(f"Employee Assignment One-Role tests: SUCCESS ({len(result.checks_passed)}/{len(result.checks_passed)} checks passed)")
        return 0

    print(
        "Employee Assignment One-Role tests: FAILURE "
        f"({len(result.checks_passed)} passed, {len(result.checks_failed)} failed)"
    )
    for description in result.checks_failed:
        print(f"  FAILED: {description}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
