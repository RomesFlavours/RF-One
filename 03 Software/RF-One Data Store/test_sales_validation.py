#!/usr/bin/env python
"""Run the Sales module synthetic validation suite (TASK_REPOSITORY_STABILIZATION_001).

Mirrors `test_organization_validation.py`'s use of
`sales_validation.run_validation()`: builds a synthetic fixture against the
currently configured database inside one transaction, asserts the required
behaviors, and always rolls back — never leaves synthetic rows behind.

Usage:
    RFONE_DATABASE_URL=sqlite:///path/to/fresh.db python test_sales_validation.py
"""

from __future__ import annotations

import sys

from rfone_data_store.database import create_configured_engine, create_session_factory, get_database_url, redact_database_url
from rfone_data_store.sales_validation import run_validation


def main() -> int:
    url = get_database_url()
    print(f"Database URL: {redact_database_url(url)}")

    engine = create_configured_engine(url)
    session_factory = create_session_factory(engine)
    result = run_validation(session_factory)

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
