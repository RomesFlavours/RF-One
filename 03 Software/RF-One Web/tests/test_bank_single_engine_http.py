#!/usr/bin/env python
"""HTTP test for the single Bank engine (Bank unification Phase 3A).

With RFONE_BANK_SINGLE_ENGINE=1: a CSV import writes no automatic decision (the old import classification,
matcher and workers are off); right after it the single engine runs and records its results in the Bank
database; a second identical import starts no new run; a person's decision from Guided Reconciliation goes
through Bank's manual service and stays protected; any automatic decision row from an old path is refused;
the export per LLC follows the Source owner.

Runs against a DISPOSABLE SQLite database created here and deleted at the end.
"""

from __future__ import annotations

import io
import os
import re
import shutil
import sys
import tempfile
import threading
import zipfile
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
for p in (APP_DIR, BASE_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_single_engine_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
_STORE_DIR = tempfile.mkdtemp(prefix="rfoneweb_single_engine_exports_")
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "single-engine-test-secret"
os.environ.update(RFONE_BANK_GUIDED="1", RFONE_BANK_SINGLE_ENGINE="1", CBANK_BANK_DB=_TEST_DB_PATH,
                  CBANK_STORE_DIR=_STORE_DIR, CBANK_WHO_WHY="1", CBANK_AUTO_RUN="0",
                  CBANK_BANK_CODE_ROOT=str(Path(APP_DIR).parents[1]))

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
import bank_guided_reconciliation as guided  # noqa: E402
from _bank_upload_helper import upload_and_confirm  # noqa: E402
from db import SessionFactory  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.bank_reconciliation import matching, single_engine  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
TOKEN_RE = re.compile(r'<meta name="cbank-token" content="([^"]+)"')
CSV = ("Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #\n"
       "DEBIT,09/02/2026,SYNTHETIC SUPPLIER ONE 1234,-120.00,DEBIT_CARD,880.00,\n"
       "DEBIT,09/03/2026,SYNTHETIC SUPPLIER TWO 5678,-45.50,DEBIT_CARD,834.50,\n"
       "CREDIT,09/04/2026,SYNTHETIC DEPOSIT,300.00,ACH_CREDIT,1134.50,\n").encode()


def wait_engine():
    for t in [t for t in threading.enumerate() if t.name == "bank-engine-after-import"]:
        t.join(timeout=300)


def count(model, *where):
    with SessionFactory() as s:
        return s.scalar(select(func.count()).select_from(model).where(*where)) or 0


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}"
              + ("" if condition or not detail else f"   [{str(detail)[:300]}]"))

    with SessionFactory() as s:
        account_service.create_account(s, username="se_operator", display_name="se_operator",
                                       password="OperatorPass123!", status="ACTIVE", is_admin=False)
        s.commit()
        op = s.query(m.RFOneAccount).filter_by(username="se_operator").one()
        account_service.set_domain_access(s, account_id=op.id, domain_code="BANK", enabled=True, role_code=None,
                                          scope=m.DOMAIN_ACCESS_SCOPE_ALL)
        s.commit()

    check("0. single engine on and Guided Reconciliation mounted", single_engine.enabled() and guided.available())
    client = web_app.app.test_client()
    client.post("/login", data={"username": "se_operator", "password": "OperatorPass123!",
                                "csrf_token": CSRF_RE.search(client.get("/login").data.decode()).group(1)})
    csrf = CSRF_RE.search(client.get("/bank").data.decode()).group(1)

    resp = upload_and_confirm(client, {"csrf_token": csrf, "files": (io.BytesIO(CSV), "Chase0101_Activity_20260920.csv")})
    with SessionFactory() as s:
        txns = list(s.scalars(select(m.FinancialTransaction)))
    check("1. the CSV import still works (3 movements)", len(txns) == 3, (resp.status_code, len(txns)))
    check("2. the import wrote no automatic decision (old classification off)",
          count(m.BankTransactionExplanation) == 0, count(m.BankTransactionExplanation))
    check("3. the old automatic matcher wrote nothing", count(m.FinancialTransactionMatch) == 0)
    wait_engine()
    runs = count(m.BankEngineRun)
    results = count(m.BankEngineResult)
    check("4. right after the import the single engine ran and recorded every movement",
          runs == 1 and results == 3, (runs, results))

    upload_and_confirm(client, {"csrf_token": csrf, "files": (io.BytesIO(CSV), "Chase0101_Activity_20260920.csv")})
    wait_engine()
    check("5. the same file again: no new movement, no new run (no double processing)",
          count(m.FinancialTransaction) == 3 and count(m.BankEngineRun) == 1,
          (count(m.FinancialTransaction), count(m.BankEngineRun)))

    with SessionFactory() as s:
        txn = s.scalars(select(m.FinancialTransaction).order_by(m.FinancialTransaction.id)).first()
        try:
            s.add(m.BankTransactionExplanation(financial_transaction_id=txn.id, decision_source="RULE",
                                               decision_status="AUTO_APPLIED"))
            s.flush()
            refused = False
        except single_engine.LegacyEngineDisabled:
            refused = True
        s.rollback()
        why = next(r for r in s.scalars(select(m.BankTransactionReason).where(m.BankTransactionReason.status == "ACTIVE"))
                   if r.accounting_classification_id)
        txn_id, why_id = txn.id, why.id
    check("6. any automatic decision row from an old path is refused", refused)
    check("7. the old background workers do not start",
          (web_app.app.extensions["bank_import_worker"].wake() or web_app.app.extensions["bank_import_worker"].thread is None)
          and (web_app.app.extensions["bank_who_worker"].wake() or web_app.app.extensions["bank_who_worker"].thread is None))
    with SessionFactory() as s:
        check("8. the old matcher hook is off", matching.on_financial_transaction_acquired(s, s.get(m.FinancialTransaction, txn_id)) is None)

    page = client.get("/bank/reconcile/").data.decode("utf-8")
    token = TOKEN_RE.search(page).group(1)
    run_id = int(re.search(r"runId=(\d+)", page).group(1))
    check("9. the Dashboard shows the engine run from the Bank database", "Guided Reconciliation" in page and run_id >= 1)
    resp = client.post(f"/bank/reconcile/api/runs/{run_id}/txn/{txn_id}/decision", headers={"X-CBank-Token": token},
                       data={"who": "SYNTHETIC SUPPLIER ONE", "why_id": why_id})
    body = resp.get_json() or {}
    with SessionFactory() as s:
        exp = s.get(m.BankTransactionExplanation, s.get(m.FinancialTransaction, txn_id).explanation_id)
    check("10. a person's decision from the Wizard goes through Bank's manual service (HUMAN)",
          resp.status_code == 200 and exp is not None and exp.decision_source == "HUMAN"
          and exp.transaction_reason_id == why_id, (resp.status_code, body.get("error")))
    check("11. ... and the engine protects it", (body.get("result") or {}).get("protected") == "HUMAN (Bank)",
          (body.get("result") or {}).get("protected"))

    zip_resp = client.get(f"/bank/reconcile/export/{run_id}.zip")
    names = zipfile.ZipFile(io.BytesIO(zip_resp.data)).namelist() if zip_resp.status_code == 200 else []
    check("12. the export per LLC downloads, one workbook per LLC plus the inter-entity one",
          zip_resp.status_code == 200 and any("InterEntity" in n for n in names), names)

    print()
    print(f"{len(passed)} passed, {len(failed)} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        try:
            from db import _engine
            _engine.dispose()
            if "app" in guided._cbank:
                guided._cbank["app"].config["CON"].close()
            os.remove(_TEST_DB_PATH)
            shutil.rmtree(_STORE_DIR, ignore_errors=True)
        except Exception:  # noqa: BLE001 — best-effort cleanup of the throwaway files
            pass
