#!/usr/bin/env python
"""Run the Backup Position / Organizational Fallback Policy / Organizational
Coverage Check synthetic-fixture test suite (TASK_ORG_CHART_ADMIN_PAGE §21).

Mirrors `test_attention_org_runtime.py` exactly. No Domain package is
imported by this test or by the module it runs. No AI provider is called.

Usage:
    python test_organizational_coverage.py
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
from rfone_data_store.organizational_coverage_validation import run_validation


def main() -> int:
    url = resolve_test_database_url("organizational_coverage")
    print(f"Database URL: {redact_database_url(url)}")

    engine = create_configured_engine(url)
    try:
        session_factory = create_session_factory(engine)
        result = run_validation(session_factory)
    finally:
        engine.dispose()
        cleanup_disposable_test_database_url(url)

    if result.success:
        print(f"Organizational Coverage tests: SUCCESS ({len(result.checks_passed)}/{len(result.checks_passed)} checks passed)")
        return 0

    print(f"Organizational Coverage tests: FAILURE ({len(result.checks_passed)} passed, {len(result.checks_failed)} failed)")
    for description in result.checks_failed:
        print(f"  FAILED: {description}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
