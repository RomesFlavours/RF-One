#!/usr/bin/env python
"""Run the Tips scheduling/schedule-service synthetic-fixture test suite
(TASK_TIPS_COMPLETE_001 §3/§16).

Mirrors `test_tips_payment_execution.py` exactly. Uses a FAKE Mercury
client — no network call, no `MERCURY_SANDBOX_API_TOKEN` required.

Usage:
    python test_tips_scheduler.py
    RFONE_DATABASE_URL=sqlite:///path/to/disposable.db python test_tips_scheduler.py
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
from rfone_data_store.tips_scheduler_validation import run_validation


def main() -> int:
    url = resolve_test_database_url("tips_scheduler")
    print(f"Database URL: {redact_database_url(url)}")

    engine = create_configured_engine(url)
    try:
        session_factory = create_session_factory(engine)
        result = run_validation(session_factory)
    finally:
        engine.dispose()
        cleanup_disposable_test_database_url(url)

    if result.success:
        print(f"Tips Scheduler tests: SUCCESS ({len(result.checks_passed)}/{len(result.checks_passed)} checks passed)")
        return 0

    print(
        "Tips Scheduler tests: FAILURE "
        f"({len(result.checks_passed)} passed, {len(result.checks_failed)} failed)"
    )
    for description in result.checks_failed:
        print(f"  FAILED: {description}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
