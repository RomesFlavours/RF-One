#!/usr/bin/env python
"""HTTP check of the contextual "How … works" help of the Compensation,
Clover Acquisition, Tips validation, Training trainer, Employee Directory
(Anagrafica dipendenti) and Interviews pages of RF-One Web.

Same convention as `test_compensation_v1_http.py`: a throwaway SQLite
database created BEFORE `app.py` is imported, migrated explicitly, Werkzeug's
test client, `main()` returning an exit code. Never touches AWS, Clover, a
Payroll Provider, a real database or an e-mail server, and calls no AI
provider (interviews are created directly through the service).

For every reachable page it asserts: status 200, the page's own
`data-how-works="<section>"` link and `id="help-<section>"` content, the
expected label ("How <Module> works" on a module home, "How this page works"
elsewhere), exactly one `id="rf-help-dialog"`, and that the old per-page
"How Works" link element is gone.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from datetime import UTC, date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_how_works_people_comp_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "how-works-people-comp-secret"
os.environ.pop("RFONE_CLOVER_LIVE_SYNC_ENABLED", None)

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
import auth  # noqa: E402
import training_integration as ti  # noqa: E402
from db import SessionFactory, _engine  # noqa: E402
from rfone_data_store import employee_directory as directory  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.interviews import service as interview_svc  # noqa: E402
from rfone_data_store.interviews.models import InterviewSession  # noqa: E402,F401
from rfone_data_store.payroll_calculation import workweek as ww  # noqa: E402
from rfone_data_store.tips import calculation_run_service as run_svc  # noqa: E402
from rfone_data_store.tips_scheduler_validation import _build_fixture  # noqa: E402

m.Base.metadata.create_all(_engine)  # Interviews tables, as test_interviews.py does.

HOST = "https://localhost"
CSRF = "test-csrf"
PASSWORD = "a-long-enough-test-password"
DIALOG_RE = re.compile(r'id="rf-help-dialog"')


def client_for(account: m.RFOneAccount):
    client = web_app.app.test_client()
    with client.session_transaction() as session:
        session.clear()
        session[auth.SESSION_ACCOUNT_KEY] = account.id
        session[auth.SESSION_VERSION_KEY] = account.session_version
        session[auth.SESSION_CSRF_KEY] = CSRF
    return client


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}"
              + ("" if condition or not detail else f" ({detail})"))

    def check_page(client, url: str, section: str, module: str | None = None) -> str:
        resp = client.get(url, base_url=HOST)
        html = resp.get_data(as_text=True)
        label = f"How {module} works" if module else "How this page works"
        check(f"{url}: status 200", resp.status_code == 200, f"got {resp.status_code}")
        check(f"{url}: link data-how-works=\"{section}\"", f'data-how-works="{section}"' in html)
        check(f"{url}: content id=\"help-{section}\"", f'id="help-{section}"' in html)
        check(f"{url}: label '{label}'", label in html)
        check(f"{url}: exactly one help dialog", len(DIALOG_RE.findall(html)) == 1,
              f"found {len(DIALOG_RE.findall(html))}")
        check(f"{url}: no obsolete per-page How Works link", 'class="how-works-link"' not in html)
        return html

    try:
        with SessionFactory() as s:
            # ---- Compensation fixture ------------------------------------
            legal_entity = m.LegalEntity(legal_name="Help LLC", status="ACTIVE")
            s.add(legal_entity)
            s.flush()
            restaurant = m.Restaurant(name="Help Restaurant", legal_entity_id=legal_entity.id)
            source_system = m.SourceSystem(code="HELP_ADP", name="Help ADP")
            merchant = m.Merchant(name="Help Merchant")
            s.add_all([restaurant, source_system, merchant])
            s.flush()
            location = m.Location(merchant_id=merchant.id, name="Help Location",
                                  timezone="America/New_York", operating_day_cutoff_time=time(4, 0))
            s.add(location)
            s.flush()
            s.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=location.id, is_primary=True))
            ww.set_workweek_start(s, restaurant_id=restaurant.id, start_weekday=0,
                                  effective_from=datetime(2000, 1, 1, tzinfo=timezone.utc))
            worker = m.Employee(location_id=location.id, display_name="Alex Helper")
            s.add(worker)
            s.flush()
            for day in (7, 8):
                start = datetime(2026, 9, day, 10, tzinfo=ZoneInfo("America/New_York")).astimezone(timezone.utc)
                s.add(m.Shift(employee_id=worker.id, clock_in=start, clock_out=start + timedelta(hours=8)))
            term = m.EmployeeCompensationTerm(
                employee_id=worker.id, legal_entity_id=legal_entity.id, function_label="Server",
                compensation_basis="HOURLY", hourly_rate_minor=2000,
                valid_from=datetime(2026, 1, 1, tzinfo=timezone.utc))
            s.add(term)
            s.commit()
            legal_entity_id, worker_id, term_id = legal_entity.id, worker.id, term.id
            restaurant_id, source_system_id, location_id = restaurant.id, source_system.id, location.id

            # ---- Tips fixture: one saved CALCULATED run --------------------
            tips_restaurant, tips_location, tips_source, tips_employee = _build_fixture(s, suffix="HELP")
            day = date(2026, 5, 3)
            order = m.Order(
                location_id=tips_location.id, source_system_id=tips_source.id, source_order_id="HELP-ORDER-1",
                employee_id=tips_employee.id, source_employee_id=tips_employee.source_employee_id,
                created_at=datetime(2026, 5, 3, 15, 0, tzinfo=UTC), business_date=day, state="locked",
                payment_state="PAID", currency="USD", total=10000)
            s.add(order)
            s.flush()
            payment = m.Payment(
                order_id=order.id, source_system_id=tips_source.id, source_payment_id="HELP-PAY-1",
                employee_id=tips_employee.id, source_employee_id=tips_employee.source_employee_id,
                created_at=datetime(2026, 5, 3, 15, 0, tzinfo=UTC), amount=10000, result="SUCCESS",
                currency="USD")
            s.add(payment)
            s.flush()
            s.add(m.PaymentTip(payment_id=payment.id, amount=1500, source_present=True))
            s.commit()
            tips_run, reason = run_svc.save_calculation_run(
                s, restaurant_id=tips_restaurant.id, first_business_date=day, last_business_date=day)
            assert tips_run is not None, reason
            s.commit()
            tips_run_id = tips_run.id

            # ---- Accounts --------------------------------------------------
            boss = account_service.create_account(
                s, username="help-boss", display_name="Boss Helper", password=PASSWORD,
                status="ACTIVE", is_admin=True)
            reader = account_service.create_account(
                s, username="help-reader", display_name="Reader Helper", password=PASSWORD, status="ACTIVE")
            recipient = account_service.create_account(
                s, username="help-recipient", display_name="Recipient Helper", password=PASSWORD,
                status="ACTIVE")
            s.flush()
            for code, role in (("COMPENSATION", None), ("CLOVER_ACQUISITION", None), ("TIPS", None),
                               ("EMPLOYEES", "admin"), ("ORGANIZATION", "admin"), ("TRAINING", "trainer")):
                account_service.set_domain_access(s, account_id=boss.id, domain_code=code, enabled=True,
                                                  role_code=role)
            account_service.set_domain_access(s, account_id=reader.id, domain_code="EMPLOYEES",
                                              enabled=True, role_code=None)
            ti.create_and_link_training_identity(s, rfone_account_id=boss.id, role_code="trainer")
            s.commit()

            # ---- Directory people and one interview ------------------------
            people_ids = {}
            for account in (boss, recipient):
                person = directory.create_person(s, display_name=account.display_name, account_id=boss.id)
                directory.link_context(s, employee_id=person.id, kind="RFONE_ACCOUNT",
                                       target_id=account.id, account_id=boss.id)
                people_ids[account.id] = person.id
            s.commit()
            interview = interview_svc.request_interview(s, boss, recipient.id, "Learn how a difficult complaint is handled")
            s.commit()
            interview_id = interview.id
            recipient_person_id = people_ids[recipient.id]
            s.refresh(boss); s.refresh(reader); s.refresh(recipient)
            boss_client, reader_client, recipient_client = (
                client_for(boss), client_for(reader), client_for(recipient))

        # ---- Compensation: build a run, approve it, reconcile it ----------
        check_page(boss_client, "/compensation", "compensation-home", "Compensation")
        check_page(boss_client, "/compensation/runs/new", "compensation-run-new")
        resp = boss_client.post("/compensation/runs/new", base_url=HOST, data={
            "legal_entity_id": str(legal_entity_id), "period_start": "2026-09-01",
            "period_end": "2026-09-14", "csrf_token": CSRF})
        check("fixture: compensation run created", resp.status_code in (302, 303), str(resp.status_code))
        run_id = int(resp.headers["Location"].rstrip("/").rsplit("/", 1)[-1])
        check_page(boss_client, f"/compensation/runs/{run_id}", "compensation-run-detail")
        boss_client.post(f"/compensation/runs/{run_id}/employees/{worker_id}/calculate", base_url=HOST, data={
            "term_0": str(term_id), "hours_0": "16", "tips_amount": "10", "bonus_amount": "0",
            "csrf_token": CSRF})
        boss_client.post(f"/compensation/runs/{run_id}/mark-calculated", base_url=HOST, data={"csrf_token": CSRF})
        resp = boss_client.post(f"/compensation/runs/{run_id}/approve", base_url=HOST, data={"csrf_token": CSRF})
        check("fixture: compensation run approved", resp.status_code in (302, 303)
              and "/compensation/snapshots/" in resp.headers.get("Location", ""), str(resp.status_code))
        snapshot_id = int(resp.headers["Location"].rstrip("/").rsplit("/", 1)[-1])
        check_page(boss_client, f"/compensation/snapshots/{snapshot_id}", "compensation-snapshot-detail")
        resp = boss_client.post(f"/compensation/snapshots/{snapshot_id}/reconciliation/new", base_url=HOST, data={
            "restaurant_id": str(restaurant_id), "source_system_id": str(source_system_id),
            "run_type": "REGULAR", "period_start": "2026-09-01", "period_end": "2026-09-14",
            "pay_date": "2026-09-18", f"regular_pay_{worker_id}": "320.00", f"tips_{worker_id}": "10.00",
            "csrf_token": CSRF})
        check("fixture: provider result recorded", resp.status_code in (302, 303)
              and "/compensation/reconciliations/" in resp.headers.get("Location", ""), str(resp.status_code))
        recon_id = int(resp.headers["Location"].rstrip("/").rsplit("/", 1)[-1])
        check_page(boss_client, f"/compensation/reconciliations/{recon_id}", "compensation-reconciliation-detail")
        check_page(boss_client, f"/compensation/period-summary?location_id={location_id}"
                   "&first_business_date=2026-09-07&last_business_date=2026-09-08",
                   "compensation-period-summary")

        # ---- Clover Acquisition ------------------------------------------
        check_page(boss_client, "/clover-acquisition", "clover-acquisition", "Clover Acquisition")
        check_page(boss_client, "/clover-acquisition?from=tips", "clover-acquisition", "Clover Acquisition")

        # ---- Tips validation ---------------------------------------------
        check_page(boss_client, "/tips/runs", "tips-validation-runs")
        check_page(boss_client, f"/tips/runs/{tips_run_id}", "tips-validation-run")

        # ---- Training trainer --------------------------------------------
        check_page(boss_client, "/training-trainer/students", "training-trainer-students")
        check_page(boss_client, "/training-trainer/students/new", "training-trainer-new-student")

        # ---- Anagrafica dipendenti ---------------------------------------
        html = check_page(boss_client, "/administration/employees", "employee-directory", "Anagrafica dipendenti")
        check("directory help keeps the full-guide link (#list)",
              "/administration/employees/how-it-works#list" in html)
        check("directory help explains administrator actions to an administrator",
              "Conferma che è una persona nuova</dt>" in html)
        html = check_page(reader_client, "/administration/employees", "employee-directory", "Anagrafica dipendenti")
        check("directory help hides administrator buttons from a non-administrator",
              "Crea persona in RF1</dt>" not in html and "Collega alla persona</dt>" not in html)
        html = check_page(boss_client, f"/administration/employees/{recipient_person_id}",
                          "employee-directory-detail")
        check("detail help keeps the full-guide links (#detail, #applicability)",
              "/administration/employees/how-it-works#detail" in html
              and "/administration/employees/how-it-works#applicability" in html)
        html = check_page(reader_client, f"/administration/employees/{recipient_person_id}",
                          "employee-directory-detail")
        check("detail help hides the edit buttons from a non-administrator",
              "Salva dati interni</dt>" not in html and "Riconcilia le due identità</dt>" not in html)
        guide = boss_client.get("/administration/employees/how-it-works", base_url=HOST)
        check("the Anagrafica full guide still opens (200)", guide.status_code == 200)

        # ---- Interviews --------------------------------------------------
        html = check_page(boss_client, "/admin/interviews", "interviews-request", "Interviews")
        check("interviews help keeps the full-guide link (#request)", "/interviews/how-it-works#request" in html)
        html = check_page(boss_client, f"/admin/interviews/{interview_id}", "interviews-results")
        check("results help keeps the full-guide link (#results)", "/interviews/how-it-works#results" in html)
        check("results help explains Delete to a Domain administrator", "Delete interview</dt>" in html)
        html = check_page(recipient_client, f"/interviews/{interview_id}", "interviews-session")
        check("session help keeps the full-guide link (#session)", "/interviews/how-it-works#session" in html)
        guide = boss_client.get("/interviews/how-it-works", base_url=HOST)
        check("the Interviews full guide still opens (200)", guide.status_code == 200)
    finally:
        try:
            _engine.dispose()
            os.remove(_TEST_DB_PATH)
        except OSError:
            pass

    print(f"\n{len(passed)} passed, {len(failed)} failed")
    if failed:
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
