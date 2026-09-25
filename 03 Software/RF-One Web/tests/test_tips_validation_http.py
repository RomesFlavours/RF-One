#!/usr/bin/env python
"""TIPS_AWS_FINALIZATION_WORKFLOW_001 — the Tips period validation workflow,
end to end, through RF-One Web's real login, on the AWS topology model.

AWS runs `rfone-web` and `rfone-tips` on two different hostnames. A browser
sends the RF-One session cookie only back to the host that issued it, so a
Tips period cannot be validated on the Tips host by an identified person.
The fix offers the one human validation step on RF-One Web itself
(`tips_validation_routes.py`), behind `require_domain_access("TIPS")` and
CSRF, calling the same `calculation_run_service.validate_run`.

Proves, with a real login and a real CALCULATED run produced by the one
calculation service (`save_calculation_run`):

   1. an unauthenticated user cannot validate;
   2. an authenticated user without TIPS access (BANK only) cannot validate;
   3. an authorized user can open the run and validate it...
   4. ...which makes it FINAL, attributed to that user;
   5. a CALCULATED run is not payable;
   6. there is no payable intermediate "validated" state: payment requires
      FINAL, and a run carrying a validation timestamp without being FINAL
      is still not payable;
   7. a FINAL run is payable;
   8. a run overlapping a FINAL run cannot also become FINAL;
   9. the session works on the host that issued it and is NOT sent to a
      different host (the AWS two-hostname model), so the validation step
      must live on RF-One Web's host;
  10. CSRF protection stays active on the validation POST.

Throwaway SQLite database, created before `app.py` is imported. Never
touches AWS, Clover, Mercury or any production database. No payment is
executed: payability is checked through the query the Payment Cycle uses.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from datetime import UTC, date, datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_tips_validation_http_test_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "http-test-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.tips import calculation_run_service as run_svc  # noqa: E402
from rfone_data_store.tips import payment_cycle_service as cycle_svc  # noqa: E402
from rfone_data_store.tips_scheduler_validation import _build_fixture  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
WEB_HOST = "https://rfone-web.example"
TIPS_HOST = "https://rfone-tips.example"
DAY = date(2026, 5, 3)
PASSWORD = "a-long-enough-test-password"


def extract_csrf(html: bytes) -> str | None:
    match = CSRF_RE.search(html.decode("utf-8"))
    return match.group(1) if match else None


def logged_in_client(username: str):
    client = web_app.app.test_client()
    resp = client.get("/login", base_url=WEB_HOST)
    client.post(
        "/login", base_url=WEB_HOST,
        data={"username": username, "password": PASSWORD, "csrf_token": extract_csrf(resp.data)},
    )
    return client


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}"
              + ("" if condition or not detail else f" ({detail})"))

    try:
        # ---- fixture: one Business Day of tips, calculated and saved -----
        with SessionFactory() as s:
            restaurant, location, source_system, employee = _build_fixture(s, suffix="AWSV")
            for n, (opened, tip) in enumerate(
                [(datetime(2026, 5, 3, 15, 0, tzinfo=UTC), 1000),
                 (datetime(2026, 5, 4, 2, 0, tzinfo=UTC), 2000)], start=1,
            ):
                order = m.Order(
                    location_id=location.id, source_system_id=source_system.id,
                    source_order_id=f"AWSV-ORDER-{n}", employee_id=employee.id,
                    source_employee_id=employee.source_employee_id, created_at=opened,
                    business_date=DAY, state="locked", payment_state="PAID", currency="USD", total=10000,
                )
                s.add(order)
                s.flush()
                payment = m.Payment(
                    order_id=order.id, source_system_id=source_system.id,
                    source_payment_id=f"AWSV-PAY-{n}", employee_id=employee.id,
                    source_employee_id=employee.source_employee_id, created_at=opened,
                    amount=10000, result="SUCCESS", currency="USD",
                )
                s.add(payment)
                s.flush()
                s.add(m.PaymentTip(payment_id=payment.id, amount=tip, source_present=True))
            s.commit()

            run, reason = run_svc.save_calculation_run(
                s, restaurant_id=restaurant.id, first_business_date=DAY, last_business_date=DAY,
            )
            assert run is not None, reason
            s.commit()
            run_id, restaurant_id = run.id, restaurant.id

            validator = account_service.create_account(
                s, username="tips-validator", display_name="Tips Validator", password=PASSWORD,
            )
            bank_only = account_service.create_account(
                s, username="bank-only", display_name="Bank Only", password=PASSWORD,
            )
            s.flush()
            account_service.set_domain_access(
                s, account_id=validator.id, domain_code="TIPS", enabled=True, role_code=None,
            )
            account_service.set_domain_access(
                s, account_id=bank_only.id, domain_code="BANK", enabled=True, role_code=None,
            )
            s.commit()
            validator_id = validator.id

        def run_state(rid: int) -> str:
            with SessionFactory() as s:
                return s.get(m.TipDistributionCalculationRun, rid).state

        def payable_run_ids() -> set[int]:
            with SessionFactory() as s:
                return {e.calculation_run_id for e in cycle_svc.get_unpaid_entitlements(s, restaurant_id)}

        check("fixture: the one calculation service saved a balanced CALCULATED run",
              run_state(run_id) == m.TIPS_RUN_STATE_CALCULATED)

        # ---- 5. CALCULATED is not payable --------------------------------
        check("5. a CALCULATED run is not payable", payable_run_ids() == set())

        # ---- 6. no payable 'validated but not final' state ----------------
        with SessionFactory() as s:
            forced = s.get(m.TipDistributionCalculationRun, run_id)
            forced.validated_at = datetime.now(UTC)
            forced.validated_by_account_id = validator_id
            s.flush()
            not_payable = cycle_svc.get_unpaid_entitlements(s, restaurant_id) == []
            s.rollback()
        check("6. payment requires FINAL: the run states are exactly CALCULATED and FINAL, and a run "
              "carrying a validation stamp without being FINAL is still not payable",
              m.TIPS_RUN_STATES == (m.TIPS_RUN_STATE_CALCULATED, m.TIPS_RUN_STATE_FINAL) and not_payable)

        # ---- 1. unauthenticated ------------------------------------------
        anon = web_app.app.test_client()
        resp_get = anon.get(f"/tips/runs/{run_id}", base_url=WEB_HOST)
        resp_post = anon.post(f"/tips/runs/{run_id}/validate", base_url=WEB_HOST, data={"csrf_token": "x"})
        check("1. an unauthenticated user is sent to login and cannot validate",
              resp_get.status_code == 302 and "/login" in resp_get.headers["Location"]
              and resp_post.status_code == 302 and "/login" in resp_post.headers["Location"]
              and run_state(run_id) == m.TIPS_RUN_STATE_CALCULATED)

        # ---- 2. authenticated, not authorized (BANK is not TIPS) ----------
        bank_client = logged_in_client("bank-only")
        home = bank_client.get("/", base_url=WEB_HOST)
        csrf = extract_csrf(home.data)
        resp_get = bank_client.get(f"/tips/runs/{run_id}", base_url=WEB_HOST)
        resp_post = bank_client.post(
            f"/tips/runs/{run_id}/validate", base_url=WEB_HOST, data={"csrf_token": csrf},
        )
        check("2. an authenticated user with BANK but no TIPS access is refused (403) and cannot validate",
              home.status_code == 200 and resp_get.status_code == 403 and resp_post.status_code == 403
              and b"validate saved periods" not in home.data
              and run_state(run_id) == m.TIPS_RUN_STATE_CALCULATED)

        # ---- 9. the session is host-scoped (the AWS two-hostname model) ----
        tips_client = logged_in_client("tips-validator")
        same_host = tips_client.get("/tips/runs", base_url=WEB_HOST)
        other_host = tips_client.get("/tips/runs", base_url=TIPS_HOST)
        check("9. the RF-One session works on the host that issued it and is not sent to another "
              "hostname — so validation must be served by RF-One Web's host, as it now is",
              same_host.status_code == 200 and f"/tips/runs/{run_id}".encode() in same_host.data
              and other_host.status_code == 302 and "/login" in other_host.headers["Location"])

        home = tips_client.get("/", base_url=WEB_HOST)
        check("   Home links an authorized user to the Tips validation page",
              b'href="/tips/runs"' in home.data)

        # ---- 3. authorized user opens the report --------------------------
        report = tips_client.get(f"/tips/runs/{run_id}", base_url=WEB_HOST)
        csrf = extract_csrf(report.data)
        check("3. an authorized user sees the saved report and the validation form",
              report.status_code == 200 and b"Validate this period as Tips Validator" in report.data
              and csrf is not None)

        # ---- 10. CSRF stays active ----------------------------------------
        no_token = tips_client.post(f"/tips/runs/{run_id}/validate", base_url=WEB_HOST, data={})
        bad_token = tips_client.post(
            f"/tips/runs/{run_id}/validate", base_url=WEB_HOST, data={"csrf_token": "forged"},
        )
        check("10. CSRF: a validation POST without, or with a forged, token is rejected (400) "
              "and changes nothing",
              no_token.status_code == 400 and bad_token.status_code == 400
              and run_state(run_id) == m.TIPS_RUN_STATE_CALCULATED)

        # ---- 3/4. authorized validation -> FINAL --------------------------
        resp = tips_client.post(
            f"/tips/runs/{run_id}/validate", base_url=WEB_HOST, data={"csrf_token": csrf},
        )
        with SessionFactory() as s:
            final = s.get(m.TipDistributionCalculationRun, run_id)
            final_ok = (
                final.state == m.TIPS_RUN_STATE_FINAL
                and final.validated_by_account_id == validator_id
                and final.finalized_by_account_id == validator_id
                and final.finalized_automatically is False
            )
        check("4. the authorized user's validation makes the run FINAL, attributed to them",
              resp.status_code == 302 and final_ok)

        # ---- 7. FINAL is payable ------------------------------------------
        check("7. the FINAL run's entitlements are payable", payable_run_ids() == {run_id})

        # ---- 8. overlapping run cannot also become FINAL ------------------
        with SessionFactory() as s:
            overlap, reason = run_svc.save_calculation_run(
                s, restaurant_id=restaurant_id, first_business_date=DAY, last_business_date=date(2026, 5, 4),
            )
            assert overlap is not None, reason
            s.commit()
            overlap_id = overlap.id
        page = tips_client.get(f"/tips/runs/{overlap_id}", base_url=WEB_HOST)
        csrf = extract_csrf(page.data) or extract_csrf(tips_client.get("/", base_url=WEB_HOST).data)
        resp = tips_client.post(
            f"/tips/runs/{overlap_id}/validate", base_url=WEB_HOST, data={"csrf_token": csrf},
        )
        after = tips_client.get(f"/tips/runs/{overlap_id}", base_url=WEB_HOST)
        check("8. a run overlapping the FINAL run cannot also become FINAL: no form is offered, a "
              "forced POST is refused, and only the first run stays payable",
              b"Validate this period" not in page.data
              and f"Run {run_id} is already the FINAL run".encode() in page.data
              and resp.status_code == 302
              and run_state(overlap_id) == m.TIPS_RUN_STATE_CALCULATED
              and f"Run {run_id} is already the FINAL run".encode() in after.data
              and payable_run_ids() == {run_id})

        # ---- immutability: a FINAL run cannot be validated twice ----------
        resp = tips_client.post(
            f"/tips/runs/{run_id}/validate", base_url=WEB_HOST, data={"csrf_token": csrf},
        )
        with SessionFactory() as s:
            still = s.get(m.TipDistributionCalculationRun, run_id)
            unchanged = still.validated_by_account_id == validator_id and still.is_final
        check("   a FINAL run is not re-validated (already final) and stays as approved",
              resp.status_code == 302 and unchanged)

    finally:
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
