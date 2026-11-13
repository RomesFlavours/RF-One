#!/usr/bin/env python
"""Run the RF-One canonical operational data model synthetic-fixture test
suite (RFONE_OPERATIONAL_DATA_MODEL_001).

Mirrors `test_clover_acquisition.py` exactly: builds a synthetic fixture
against a disposable database, asserts the required behaviors, and always
rolls back. Never contacts Clover production — this suite is specifically
about proving the canonical schema works entirely without any external
system involved.

Usage:
    python test_rfone_operational_data_model.py
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
from rfone_data_store.rfone_operational_data_model_validation import run_validation


def main() -> int:
    url = resolve_test_database_url("rfone_operational_data_model")
    print(f"Database URL: {redact_database_url(url)}")

    engine = create_configured_engine(url)
    try:
        session_factory = create_session_factory(engine)
        result = run_validation(session_factory)
    finally:
        engine.dispose()
        cleanup_disposable_test_database_url(url)

    if result.success:
        print(f"RF-One operational data model tests: SUCCESS ({len(result.checks_passed)}/{len(result.checks_passed)} checks passed)")
        return 0

    print(
        "RF-One operational data model tests: FAILURE "
        f"({len(result.checks_passed)} passed, {len(result.checks_failed)} failed)"
    )
    for description in result.checks_failed:
        print(f"  FAILED: {description}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
