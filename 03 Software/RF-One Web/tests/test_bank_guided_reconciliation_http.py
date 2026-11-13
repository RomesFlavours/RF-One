#!/usr/bin/env python
"""HTTP test for Guided Reconciliation inside the Bank application
(Bank unification, Phase 1 — `bank_guided_reconciliation.py`).

The C-Bank Dashboard and Wizard are served by this application under
/bank/reconcile/, behind the Bank gate, with the Bank shell around them.
C-Bank keeps its own store and reads the Bank database read-only.

Runs against a DISPOSABLE SQLite Bank database and a DISPOSABLE C-Bank
store, both created here and deleted at the end. Needs the C-Bank worktree
(`RFONE_BANK_CBANK_ROOT`, default: the sibling `rf-one-c-bank-prototype`).
"""

from __future__ import annotations

import io
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_guided_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
_STORE_DIR = tempfile.mkdtemp(prefix="rfoneweb_guided_store_")
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "guided-reconciliation-test-secret"
os.environ["RFONE_BANK_GUIDED"] = "1"
os.environ["CBANK_BANK_DB"] = _TEST_DB_PATH
os.environ["CBANK_STORE_DIR"] = _STORE_DIR
os.environ["CBANK_BANK_CODE_ROOT"] = str(Path(APP_DIR).parents[1])

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
import bank_guided_reconciliation as guided  # noqa: E402
from db import SessionFactory  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
TOKEN_RE = re.compile(r'<meta name="cbank-token" content="([^"]+)"')
TABS_RE = re.compile(r'<a class="module-tab[^"]*"\s+href="([^"]+)"[^>]*>([^<]+)</a>')
BANK_PAGES = ("/bank", "/bank/review", "/bank/export", "/bank/sources", "/bank/ai-rules",
              "/bank/configuration", "/bank/instructions")


def bank_rows() -> dict:
    con = sqlite3.connect(f"file:{_TEST_DB_PATH}?mode=ro", uri=True)
    try:
        names = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
        return {n: con.execute(f'select count(*) from "{n}"').fetchone()[0] for n in names}
    finally:
        con.close()


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}"
              + ("" if condition or not detail else f"   [{str(detail)[:300]}]"))

    def login(client, username):
        client.post("/login", data={"username": username, "password": "OperatorPass123!",
                                    "csrf_token": CSRF_RE.search(client.get("/login").data.decode()).group(1)})

    with SessionFactory() as db:
        for username in ("guided_operator", "guided_other"):
            account_service.create_account(db, username=username, display_name=username,
                                           password="OperatorPass123!", status="ACTIVE", is_admin=False)
        db.commit()
        operator = db.query(m.RFOneAccount).filter_by(username="guided_operator").one()
        account_service.set_domain_access(db, account_id=operator.id, domain_code="BANK", enabled=True,
                                          role_code=None, scope=m.DOMAIN_ACCESS_SCOPE_ALL)
        db.commit()

    check("0. the C-Bank code is found and the mount is active", guided.available(), str(guided.cbank_root()))

    anonymous = web_app.app.test_client()
    resp = anonymous.get("/bank/reconcile/")
    check("1. without a login the page is not served (login first)",
          resp.status_code in (302, 401, 403) and b"cbank-token" not in resp.data, resp.status_code)

    other = web_app.app.test_client()
    login(other, "guided_other")
    resp = other.get("/bank/reconcile/")
    check("2. an account without the Bank Domain gets 403, page and API alike",
          resp.status_code == 403 and other.post("/bank/reconcile/api/runs").status_code == 403, resp.status_code)

    client = web_app.app.test_client()
    login(client, "guided_operator")
    home = client.get("/bank").data.decode("utf-8")
    tabs = TABS_RE.findall(home)
    # BANK_WHO_RULES_001 (2026-10-25): WHO Rules is the only rules engine in the menu; this page stays
    # reachable by its address, out of the menu.
    check("3. 'Guided Reconciliation' is not a Bank menu tab (reachable by its address)",
          all(label != "Guided Reconciliation" for _, label in tabs) and ("/bank/who-search-text", "WHO Rules") in tabs, tabs)

    resp = client.get("/bank/reconcile")
    check("4. /bank/reconcile leads to /bank/reconcile/", resp.status_code in (301, 308)
          and resp.headers.get("Location", "").endswith("/bank/reconcile/"), resp.status_code)

    resp = client.get("/bank/reconcile/")
    page = resp.data.decode("utf-8")
    token = (TOKEN_RE.search(page) or [None, None])[1]
    check("5. the page is served by the Bank application, with the Bank shell",
          resp.status_code == 200 and "Guided Reconciliation" in page and 'class="site-header"' in page
          and "css/rf-one.css" in page and token is not None, resp.status_code)
    crumb = page[page.find('class="breadcrumb"'):][:600]
    check("6. breadcrumb RF-One › Bank Reconciliation › Guided Reconciliation",
          "RF-One" in crumb and "Bank Reconciliation" in crumb and "Guided Reconciliation" in crumb, crumb)
    check("7. the page calls its API under the Bank prefix", 'const B="/bank/reconcile"' in page)

    check("8. a C-Bank write without its token is refused (403)",
          client.post("/bank/reconcile/api/runs", data={"kind": "month", "month": "2026-09"}).status_code == 403)

    # BANK_UPLOAD_AND_RECONCILE_001: a run is automatic processing — refused until the data are complete, then
    # accepted once a complete file set is uploaded on Upload and Reconcile.
    resp = client.post("/bank/reconcile/api/runs", data={"kind": "month", "month": "2026-09"},
                       headers={"X-CBank-Token": token})
    check("8b. with no complete data the run is refused by the one completeness gate (409)", resp.status_code == 409
          and "Upload and Reconcile" in resp.get_json()["error"], resp.data[:200])
    with SessionFactory() as db:
        from rfone_data_store.bank_reconciliation import configuration as config_service
        llc = config_service.create_entity(db, name="Guided Test, LLC", legal_name="Guided Test, LLC")
        db.add(m.PaymentInstrument(display_name="Guided checking", instrument_type="BANK_ACCOUNT", institution="Chase",
                                   last_four="0101", status="ACTIVE", owner_reporting_entity_id=llc.id))
        db.commit()
    work = client.get("/bank/work").data.decode("utf-8")
    client.post("/bank/work/upload", content_type="multipart/form-data", data={
        "csrf_token": CSRF_RE.search(work).group(1),
        "files": (io.BytesIO(b"Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #\n"
                             b"DEBIT,09/02/2026,GUIDED TEST SUPPLIER,-12.00,DEBIT_CARD,88.00,\n"),
                  "Chase0101_Activity_20260930.csv")})
    check("8c. after the upload the data are ready", "Data ready for reconciliation" in client.get("/bank/work").data.decode())
    before = bank_rows()
    resp = client.post("/bank/reconcile/api/runs", data={"kind": "month", "month": "2026-09"},
                       headers={"X-CBank-Token": token})
    body = resp.get_json(silent=True) or {}
    run_id = body.get("run_id")
    check("9. a run started from the Bank page reaches the C-Bank engine", resp.status_code == 200
          and body.get("ok") and run_id, resp.data[:300])
    # Phase 3A (supersedes the separate store): the run is recorded in the Bank database itself, and it changes
    # no movement, raw row, decision or allocation.
    after = bank_rows()
    kept = ("financial_transactions", "raw_bank_transactions", "bank_transaction_explanations",
            "bank_transaction_allocations")
    check("10. the run changes no movement, raw row, decision or allocation",
          all(after[t] == before[t] for t in kept), {t: (before[t], after[t]) for t in kept})
    check("11. the run is recorded in the Bank database (bank_engine_runs)",
          after["bank_engine_runs"] == before["bank_engine_runs"] + 1)

    resp = client.get(f"/bank/reconcile/?run={run_id}")
    check("12. the Dashboard of the run opens", resp.status_code == 200
          and f"/bank/reconcile/export/{run_id}.zip" in resp.data.decode("utf-8"), resp.status_code)
    resp = client.get(f"/bank/reconcile/api/runs/{run_id}/results")
    check("13. the Wizard's API answers under the prefix", resp.status_code == 200
          and (resp.get_json() or {}).get("ok") is True, resp.status_code)
    resp = client.get(f"/bank/reconcile/export/{run_id}.zip")
    check("14. the per-LLC export downloads", resp.status_code == 200
          and resp.mimetype == "application/zip", resp.status_code)

    statuses = {p: client.get(p).status_code for p in BANK_PAGES}
    check("15. every other Bank page still opens", all(s == 200 for s in statuses.values()), statuses)

    os.environ["RFONE_BANK_GUIDED"] = "0"
    check("16. RFONE_BANK_GUIDED=0 turns the mount off (rollback switch)", not guided.available())

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
