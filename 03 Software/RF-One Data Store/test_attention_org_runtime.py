#!/usr/bin/env python
"""Run the Organizational Responsibility + Attention Management shared
runtime's synthetic-fixture test suite (TASK_ATTENTION_ORG_RUNTIME §17-18).

Mirrors `test_tips_distribution_engine.py` exactly. No Domain package
(Tips included) is imported by this test or by the module it runs.

Usage:
    python test_attention_org_runtime.py
    RFONE_DATABASE_URL=sqlite:///path/to/disposable.db python test_attention_org_runtime.py
"""

from __future__ import annotations

import sys

from rfone_data_store.attention_org_runtime_validation import run_validation
from rfone_data_store.database import (
    cleanup_disposable_test_database_url,
    create_configured_engine,
    create_session_factory,
    redact_database_url,
    resolve_test_database_url,
)


def main() -> int:
    url = resolve_test_database_url("attention_org_runtime")
    print(f"Database URL: {redact_database_url(url)}")

    engine = create_configured_engine(url)
    try:
        session_factory = create_session_factory(engine)
        result = run_validation(session_factory)
    finally:
        engine.dispose()
        cleanup_disposable_test_database_url(url)

    if result.success:
        print(f"Organizational Responsibility + Attention runtime tests: SUCCESS ({len(result.checks_passed)}/{len(result.checks_passed)} checks passed)")
        return 0

    print(
        "Organizational Responsibility + Attention runtime tests: FAILURE "
        f"({len(result.checks_passed)} passed, {len(result.checks_failed)} failed)"
    )
    for description in result.checks_failed:
        print(f"  FAILED: {description}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
