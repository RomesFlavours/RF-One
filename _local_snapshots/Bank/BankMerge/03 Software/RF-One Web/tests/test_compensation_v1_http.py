#!/usr/bin/env python
"""HTTP-level regression/verification test for Compensation V1 (manual
Payroll Handoff). Mirrors `test_accounts_and_domains_http.py`'s own
convention exactly: a throwaway SQLite database created BEFORE `app.py` is
imported (via `RFONE_DATABASE_URL`), migrated explicitly, Werkzeug's Flask
test client, `main()` returning an exit code. Never touches AWS, ADP, or
any production database — no real data is communicated to a Payroll
Provider and no real payroll is processed.

Exercises the full V1 cycle end to end: ingresso -> preparazione ->
approvazione -> prospetto/export -> conferma comunicazione manuale ->
registrazione risultato -> riconciliazione, plus Legal Entity access
gating and CSV export.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from decimal import Decimal

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_compensation_http_test_")
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

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')


def extract_csrf(html: bytes) -> str:
    match = CSRF_RE.search(html.decode("utf-8"))
    assert match, "csrf_token not found in response HTML"
    return match.group(1)


def main() -> int:
    checks_passed: list[str] = []
    checks_failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        if condition:
            checks_passed.append(description)
        else:
            checks_failed.append(description)
            print(f"FAILED: {description}" + (f" ({detail})" if detail else ""))

    try:
        # -----------------------------------------------------------------
        # Seed fixture: one Legal Entity, one Restaurant, one Source
        # System, one Employee with an HOURLY Compensation Term.
        # -----------------------------------------------------------------
        with SessionFactory() as s:
            legal_entity = m.LegalEntity(legal_name="Verification LLC", status="ACTIVE")
            s.add(legal_entity)
            s.flush()

            restaurant = m.Restaurant(name="Verification Restaurant", legal_entity_id=legal_entity.id)
            s.add(restaurant)

            source_system = m.SourceSystem(code="VERIFY_ADP", name="Verification ADP")
            s.add(source_system)

            merchant = m.Merchant(name="Verification Merchant")
            s.add(merchant)
            s.flush()
            location = m.Location(merchant_id=merchant.id, name="Verification Location")
            s.add(location)
            s.flush()
            employee = m.Employee(location_id=location.id, display_name="Alex Verification")
            s.add(employee)
            s.flush()

            from datetime import datetime, timezone
            term = m.EmployeeCompensationTerm(
                employee_id=employee.id, legal_entity_id=legal_entity.id, function_label="Server",
                compensation_basis="HOURLY", hourly_rate_minor=2000,
                valid_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
            s.add(term)

            # A SALARIED Employee for the same Legal Entity/period — V1's
            # declared, out-of-scope limit. Never calculable; must show up
            # explicitly in the run detail page, never silently.
            salaried_employee = m.Employee(location_id=location.id, display_name="Sam Salaried")
            s.add(salaried_employee)
            s.flush()
            salaried_term = m.EmployeeCompensationTerm(
                employee_id=salaried_employee.id, legal_entity_id=legal_entity.id,
                function_label="Manager", compensation_basis="SALARIED",
                salaried_period_amount_minor=150000,
                valid_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
            s.add(salaried_term)
            s.commit()

            legal_entity_id = legal_entity.id
            employee_id = employee.id
            term_id = term.id
            salaried_employee_id = salaried_employee.id

            admin = account_service.create_account(
                s, username="RFone", display_name="Pino Miraglia", password="AdminPass123!",
                status="ACTIVE", is_admin=True,
            )
            operator = account_service.create_account(
                s, username="payroll_operator", display_name="Payroll Operator", password="OperatorPass123!",
                status="ACTIVE",
            )
            s.commit()
            admin_id, operator_id = admin.id, operator.id

        # -----------------------------------------------------------------
        # Access gating: a user with no COMPENSATION access is refused.
        # -----------------------------------------------------------------
        no_access_client = web_app.app.test_client()
        resp = no_access_client.get("/login")
        csrf = extract_csrf(resp.data)
        no_access_client.post(
            "/login", data={"username": "payroll_operator", "password": "OperatorPass123!", "csrf_token": csrf},
        )
        resp = no_access_client.get("/compensation")
        check("a user with no COMPENSATION domain access is refused (403)", resp.status_code == 403)

        # Grant operator COMPENSATION access, as an admin would.
        admin_client = web_app.app.test_client()
        resp = admin_client.get("/login")
        csrf = extract_csrf(resp.data)
        admin_client.post(
            "/login", data={"username": "RFone", "password": "AdminPass123!", "csrf_token": csrf},
        )
        resp = admin_client.get(f"/admin/accounts/{operator_id}/access")
        csrf = extract_csrf(resp.data)
        resp = admin_client.post(
            f"/admin/accounts/{operator_id}/access",
            data={"enabled_COMPENSATION": "on", "csrf_token": csrf},
        )
        check("admin grants operator COMPENSATION access (redirects)", resp.status_code in (302, 303))

        operator_client = web_app.app.test_client()
        resp = operator_client.get("/login")
        csrf = extract_csrf(resp.data)
        operator_client.post(
            "/login", data={"username": "payroll_operator", "password": "OperatorPass123!", "csrf_token": csrf},
        )

        resp = operator_client.get("/")
        check(
            "Home shows the Compensation card as a real link, not 'Work in progress'",
            b'href="/compensation"' in resp.data and b"Work in progress" not in resp.data,
        )

        # -----------------------------------------------------------------
        # 1. Ingresso / preparazione — create a run, calculate an Employee.
        # -----------------------------------------------------------------
        resp = operator_client.get("/compensation")
        check("operator can open /compensation (200)", resp.status_code == 200)

        resp = operator_client.get("/compensation/runs/new")
        csrf = extract_csrf(resp.data)
        resp = operator_client.post(
            "/compensation/runs/new",
            data={
                "legal_entity_id": str(legal_entity_id), "period_start": "2026-09-01",
                "period_end": "2026-09-14", "csrf_token": csrf,
            },
        )
        check("creating a run redirects to its detail page", resp.status_code in (302, 303))
        run_id = int(resp.headers["Location"].rstrip("/").rsplit("/", 1)[-1])

        resp = operator_client.get(f"/compensation/runs/{run_id}")
        check("run detail page shows the eligible Employee", b"Alex Verification" in resp.data)
        check(
            "run detail page shows the SALARIED Employee explicitly, flagged as not supported "
            "in V1 (never silently omitted, never given a computed/placeholder value)",
            b"Sam Salaried" in resp.data and b"TO COMPLETE OUTSIDE RF-ONE" in resp.data
            and b"not supported in V1" in resp.data,
        )
        csrf = extract_csrf(resp.data)

        resp = operator_client.post(
            f"/compensation/runs/{run_id}/employees/{employee_id}/incentives",
            data={
                "label": "Wine Sales Contribution", "amount": "200", "source_note": "September promo",
                "csrf_token": csrf,
            },
        )
        check("adding a positive Incentive Contribution redirects", resp.status_code in (302, 303))

        resp = operator_client.get(f"/compensation/runs/{run_id}")
        csrf = extract_csrf(resp.data)
        resp = operator_client.post(
            f"/compensation/runs/{run_id}/employees/{employee_id}/incentives",
            data={"label": "Performance Contribution", "amount": "-75", "csrf_token": csrf},
        )
        check("adding a negative Incentive Contribution redirects", resp.status_code in (302, 303))

        resp = operator_client.get(f"/compensation/runs/{run_id}")
        csrf = extract_csrf(resp.data)
        resp = operator_client.post(
            f"/compensation/runs/{run_id}/employees/{employee_id}/calculate",
            data={
                "term_0": str(term_id), "hours_0": "40", "tips_amount": "100.00", "bonus_amount": "0",
                "csrf_token": csrf,
            },
        )
        check("calculating the Employee redirects", resp.status_code in (302, 303))

        with SessionFactory() as s:
            from rfone_data_store import models as m2
            from sqlalchemy import select
            calc = s.scalars(
                select(m2.EmployeePayrollCalculation).where(
                    m2.EmployeePayrollCalculation.calculation_run_id == run_id
                )
            ).one()
            check(
                "the persisted calculation reflects the entered hours/tips and the Recognized "
                "Incentive (MAX(0, 200-75) = 125)",
                calc.regular_hours == Decimal("40.0000")
                and calc.regular_pay == Decimal("800.00")
                and calc.tips_amount == Decimal("100.00")
                and calc.incentive_recognized_amount == Decimal("125.00")
                and calc.gross_pay == Decimal("1025.00"),
                detail=f"got hours={calc.regular_hours} pay={calc.regular_pay} incentive={calc.incentive_recognized_amount} gross={calc.gross_pay}",
            )

        # -----------------------------------------------------------------
        # 2. Approvazione.
        # -----------------------------------------------------------------
        resp = operator_client.get(f"/compensation/runs/{run_id}")
        csrf = extract_csrf(resp.data)
        resp = operator_client.post(
            f"/compensation/runs/{run_id}/mark-calculated", data={"csrf_token": csrf},
        )
        check("marking the run CALCULATED redirects", resp.status_code in (302, 303))

        resp = operator_client.get(f"/compensation/runs/{run_id}")
        csrf = extract_csrf(resp.data)
        resp = operator_client.post(
            f"/compensation/runs/{run_id}/approve", data={"csrf_token": csrf},
        )
        check("approving the run redirects to the Approved Snapshot", resp.status_code in (302, 303))
        snapshot_id = int(resp.headers["Location"].rstrip("/").rsplit("/", 1)[-1])

        with SessionFactory() as s:
            from sqlalchemy import select as select3
            salaried_in_snapshot = s.scalars(
                select3(m.ApprovedEmployeeCompensationResult).where(
                    m.ApprovedEmployeeCompensationResult.snapshot_id == snapshot_id,
                    m.ApprovedEmployeeCompensationResult.employee_id == salaried_employee_id,
                )
            ).first()
            check(
                "the SALARIED Employee (never calculated) is never included in the Approved "
                "Snapshot — excluded entirely, never with a computed zero",
                salaried_in_snapshot is None,
            )

        # -----------------------------------------------------------------
        # 3. Prospetto/export — manual view + CSV, missing provider mapping
        # correctly flagged (never invented).
        # -----------------------------------------------------------------
        resp = operator_client.get(f"/compensation/snapshots/{snapshot_id}")
        check("snapshot detail page opens (200)", resp.status_code == 200)
        check("snapshot detail shows the approved gross pay", b"1025.00" in resp.data)
        check("snapshot detail flags the missing Payroll Provider employee-ID mapping", b"MISSING" in resp.data)

        resp = operator_client.get(f"/compensation/snapshots/{snapshot_id}/export.csv")
        check("CSV export responds 200 with text/csv", resp.status_code == 200 and "text/csv" in resp.content_type)
        check("CSV export contains the Employee name and the Recognized Incentive", b"Alex Verification" in resp.data and b"125.00" in resp.data.replace(b"\r\n", b"\n"))

        # -----------------------------------------------------------------
        # 4. Conferma comunicazione manuale.
        # -----------------------------------------------------------------
        resp = operator_client.get(f"/compensation/snapshots/{snapshot_id}")
        csrf = extract_csrf(resp.data)
        resp = operator_client.post(
            f"/compensation/snapshots/{snapshot_id}/confirm-communication",
            data={"communicated_at": "2026-09-16", "reference": "ADP batch #7", "csrf_token": csrf},
        )
        check("confirming manual communication redirects", resp.status_code in (302, 303))

        with SessionFactory() as s:
            run_after_export = s.get(m.CompensationPreparationRun, run_id)
            check("the run transitions to EXPORTED after the first communication confirmation", run_after_export.status == "EXPORTED")

        # -----------------------------------------------------------------
        # 5. Registrazione risultato + riconciliazione (a deliberate
        # difference on Regular Pay, a missing Tips line, and a
        # Provider-added Holiday line).
        # -----------------------------------------------------------------
        with SessionFactory() as s:
            restaurant_row = s.scalars(
                select(m.Restaurant).where(m.Restaurant.legal_entity_id == legal_entity_id)
            ).one()
            source_system_row = s.scalars(select(m.SourceSystem)).first()
            restaurant_id_for_form = restaurant_row.id
            source_system_id_for_form = source_system_row.id

        resp = operator_client.get(f"/compensation/snapshots/{snapshot_id}")
        csrf = extract_csrf(resp.data)
        resp = operator_client.post(
            f"/compensation/snapshots/{snapshot_id}/reconciliation/new",
            data={
                "restaurant_id": str(restaurant_id_for_form), "source_system_id": str(source_system_id_for_form),
                "run_type": "REGULAR", "period_start": "2026-09-01", "period_end": "2026-09-14",
                "pay_date": "2026-09-18",
                f"regular_pay_{employee_id}": "790.00",
                f"incentive_{employee_id}": "125.00",
                f"other_label_{employee_id}": "Holiday",
                f"other_amount_{employee_id}": "64.00",
                "csrf_token": csrf,
            },
        )
        check("recording the Provider result redirects to the reconciliation", resp.status_code in (302, 303))
        reconciliation_id = int(resp.headers["Location"].rstrip("/").rsplit("/", 1)[-1])

        resp = operator_client.get(f"/compensation/reconciliations/{reconciliation_id}")
        check("reconciliation detail page opens (200)", resp.status_code == 200)
        check("reconciliation shows a DIFFERENT status for Regular Pay", b"DIFFERENT" in resp.data)
        check("reconciliation shows a MISSING status for Tips (approved, not reported)", b"MISSING_IN_PROVIDER" in resp.data)
        check("reconciliation shows the Provider-added Holiday line as MISSING_IN_RFONE", b"Holiday" in resp.data and b"MISSING_IN_RFONE" in resp.data)
        check("reconciliation never renders a Gross/Net comparison line", b"Gross Pay" not in resp.data and b"Net Pay" not in resp.data)

        with SessionFactory() as s:
            from sqlalchemy import select as select2
            diff_line = s.scalars(
                select2(m.CompensationReconciliationLine).where(
                    m.CompensationReconciliationLine.reconciliation_id == reconciliation_id,
                    m.CompensationReconciliationLine.component_label == "Regular Pay",
                )
            ).one()
            diff_line_id = diff_line.id

        resp = operator_client.get(f"/compensation/reconciliations/{reconciliation_id}")
        csrf = extract_csrf(resp.data)
        resp = operator_client.post(
            f"/compensation/reconciliations/{reconciliation_id}/lines/{diff_line_id}/annotate",
            data={"note": "Provider rounded a partial hour; accepted.", "resolution_status": "ACCEPTED", "csrf_token": csrf},
        )
        check("annotating a reconciliation line redirects", resp.status_code in (302, 303))

        with SessionFactory() as s:
            reloaded_line = s.get(m.CompensationReconciliationLine, diff_line_id)
            check(
                "the annotation (note, resolution, resolver) was persisted",
                reloaded_line.resolution_status == "ACCEPTED"
                and reloaded_line.resolved_by == "Payroll Operator"
                and reloaded_line.note == "Provider rounded a partial hour; accepted.",
            )

        # -----------------------------------------------------------------
        # The originally approved values were never overwritten by the
        # Provider's returned result.
        # -----------------------------------------------------------------
        with SessionFactory() as s:
            approved_result = s.scalars(
                select(m.ApprovedEmployeeCompensationResult).where(
                    m.ApprovedEmployeeCompensationResult.snapshot_id == snapshot_id
                )
            ).one()
            check(
                "the Approved Compensation Snapshot's regular_pay is untouched by the Provider's "
                "different reported value (800.00, never overwritten to 790.00)",
                approved_result.regular_pay == Decimal("800.00"),
            )

    finally:
        for suffix in ("", "-wal", "-shm", "-journal"):
            candidate = _TEST_DB_PATH + suffix
            if os.path.exists(candidate):
                try:
                    os.remove(candidate)
                except OSError:
                    pass

    print()
    print(f"{len(checks_passed)} passed, {len(checks_failed)} failed.")
    if checks_failed:
        print("FAILED CHECKS:")
        for c in checks_failed:
            print(" -", c)
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
