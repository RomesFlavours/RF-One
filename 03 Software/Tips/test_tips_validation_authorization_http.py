#!/usr/bin/env python
"""TIPS_AWS_FINALIZATION_WORKFLOW_001 — the Tips app's OWN validation route
applies the same gates as RF-One Web's.

Where Tips shares a host with RF-One Web (locally, or behind one ingress),
the RF-One session reaches `/tips-runs/<id>/validate`. Being signed in was
the only check there; it now also requires TIPS Domain access and the
RF-One CSRF token, so no weaker path to FINAL exists beside RF-One Web's.

The shared RF-One session is simulated with `session_transaction`, writing
exactly the keys RF-One Web's `auth.log_in`/`get_csrf_token` write. Tips
never issues them. Throwaway SQLite; never touches AWS, Clover or Mercury.
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import UTC, date, datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="tips_validation_authz_test_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_FLASK_SECRET_KEY"] = "tips-validation-authz-test-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as tips_app  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store import rfone_web_session as shared_session  # noqa: E402
from rfone_data_store.tips import calculation_run_service as run_svc  # noqa: E402
from rfone_data_store.tips_scheduler_validation import _build_fixture, _make_order_with_tip  # noqa: E402

DAY = date(2026, 5, 3)
CSRF = "shared-rfone-csrf-token"


def signed_in(account) -> "object":
    """A Tips test client carrying the RF-One session RF-One Web would have
    issued for `account` on the same host."""
    client = tips_app.app.test_client()
    with client.session_transaction() as sess:
        sess[shared_session.SESSION_ACCOUNT_KEY] = account.id
        sess[shared_session.SESSION_VERSION_KEY] = account.session_version
        sess[shared_session.SESSION_CSRF_KEY] = CSRF
    return client


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}"
              + ("" if condition or not detail else f" ({detail})"))

    try:
        with tips_app.SessionFactory() as s:
            restaurant, location, source_system, employee = _build_fixture(s, suffix="TVA")
            _make_order_with_tip(s, location=location, source_system=source_system, employee=employee,
                                 business_date=DAY, order_suffix="TVA-1")
            run, reason = run_svc.save_calculation_run(
                s, restaurant_id=restaurant.id, first_business_date=DAY, last_business_date=DAY,
            )
            assert run is not None, reason
            validator = account_service.create_account(
                s, username="tva-validator", display_name="TVA Validator", password="a-long-enough-password",
            )
            bank_only = account_service.create_account(
                s, username="tva-bank", display_name="TVA Bank", password="a-long-enough-password",
            )
            s.flush()
            account_service.set_domain_access(s, account_id=validator.id, domain_code="TIPS",
                                              enabled=True, role_code=None)
            account_service.set_domain_access(s, account_id=bank_only.id, domain_code="BANK",
                                              enabled=True, role_code=None)
            s.commit()
            run_id = run.id
            s.expunge_all()

        def state() -> str:
            with tips_app.SessionFactory() as s:
                return s.get(m.TipDistributionCalculationRun, run_id).state

        url = f"/tips-runs/{run_id}/validate"

        anon = tips_app.app.test_client()
        anon.post(url, data={"csrf_token": CSRF})
        check("unauthenticated: refused, run stays CALCULATED", state() == m.TIPS_RUN_STATE_CALCULATED)

        bank_client = signed_in(bank_only)
        page = bank_client.get(f"/tips-runs/{run_id}")
        bank_client.post(url, data={"csrf_token": CSRF})
        check("signed in with BANK but not TIPS: no form, POST refused, run stays CALCULATED",
              b"not authorized to validate Tips periods" in page.data
              and b"Validate this period as" not in page.data
              and state() == m.TIPS_RUN_STATE_CALCULATED)

        tips_client = signed_in(validator)
        page = tips_client.get(f"/tips-runs/{run_id}")
        check("authorized: the form carries the shared RF-One CSRF token",
              f'name="csrf_token" value="{CSRF}"'.encode() in page.data)
        no_token = tips_client.post(url, data={})
        forged = tips_client.post(url, data={"csrf_token": "forged"})
        check("CSRF: missing or forged token -> 400, run stays CALCULATED",
              no_token.status_code == 400 and forged.status_code == 400
              and state() == m.TIPS_RUN_STATE_CALCULATED)

        tips_client.post(url, data={"csrf_token": CSRF})
        with tips_app.SessionFactory() as s:
            final = s.get(m.TipDistributionCalculationRun, run_id)
            ok = final.state == m.TIPS_RUN_STATE_FINAL and final.validated_by_account_id == validator.id
        check("authorized with a valid token: the run becomes FINAL, attributed to the validator", ok)

    finally:
        tips_app._engine.dispose()
        for suffix in ("", "-wal", "-shm", "-journal"):
            candidate = _TEST_DB_PATH + suffix
            if os.path.exists(candidate):
                try:
                    os.remove(candidate)
                except OSError:
                    pass

    print()
    print(f"{len(passed)} passed, {len(failed)} failed.")
    if failed:
        print("FAILED CHECKS:")
        for c in failed:
            print(" -", c)
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
