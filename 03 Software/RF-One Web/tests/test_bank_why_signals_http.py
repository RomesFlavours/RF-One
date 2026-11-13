#!/usr/bin/env python
"""HTTP test for WHY Rules (BANK_WHO_WHY_MODE_001), on an ISOLATED, MIGRATED COPY of the local database.

The page lists the recognised WHO whose WHY is not determinable, grouped by WHO, Source and reason; a WHO set
MULTIPLE no longer takes the WHY registered on its pair; a WHO WHY rule is simulated, refused unsimulated,
saved inactive, then activated; the WHO goes back to UNIQUE. No movement decision and no WHO + Source
classification changes at any point.
"""
from __future__ import annotations

import atexit
import json
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
_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)
_SOURCE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "RF-One" / "Bank" / "rfone.db"
if not _SOURCE.exists():
    print("SKIPPED: no local Bank database to copy.")
    sys.exit(0)
_FOLDER = tempfile.mkdtemp(prefix="rfone_why_signals_")
atexit.register(shutil.rmtree, _FOLDER, ignore_errors=True)
_COPY = Path(_FOLDER) / "rfone.db"
_src = sqlite3.connect(f"file:{_SOURCE.as_posix()}?mode=ro", uri=True)
_dst = sqlite3.connect(_COPY)
_src.backup(_dst)
_dst.close()
_src.close()
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_COPY.as_posix()}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "why-signals-test-secret"
os.environ["RFONE_BANK_SINGLE_ENGINE"] = "1"   # Phase 3A, as the server: no background import pipeline
os.environ["RFONE_BANK_GUIDED"] = "1"
os.environ["CBANK_BANK_DB"] = str(_COPY)
os.environ["CBANK_STORE_DIR"] = str(Path(_FOLDER) / "store")
os.environ["CBANK_AUTO_RUN"] = "0"
os.environ["CBANK_BANK_CODE_ROOT"] = str(Path(APP_DIR).parents[1])

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
import bank_why_signals  # noqa: E402
from db import SessionFactory  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
BANK_CSRF_RE = re.compile(r'<meta name="bank-csrf" content="([^"]+)"')


def preserved(db):
    return (sorted(tuple(r) for r in db.execute(select(m.FinancialTransaction.id, m.FinancialTransaction.explanation_id)).all()),
            db.scalar(select(func.count(m.BankTransactionExplanation.id))),
            sorted(tuple(r) for r in db.execute(select(m.BankWhoSourceClassification.occurrence_id,
                   m.BankWhoSourceClassification.payment_instrument_id, m.BankWhoSourceClassification.transaction_reason_id)).all()))


def main() -> int:
    passed, failed = [], []

    def check(description, condition, detail=""):
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f"   [{str(detail)[:400]}]"))

    with SessionFactory() as db:
        before = preserved(db)
        account_service.create_account(db, username="ws_operator", display_name="ws_operator", password="OperatorPass123!",
                                       status="ACTIVE", is_admin=False)
        db.commit()
        op = db.query(m.RFOneAccount).filter_by(username="ws_operator").one()
        account_service.set_domain_access(db, account_id=op.id, domain_code="BANK", enabled=True, role_code=None,
                                          scope=m.DOMAIN_ACCESS_SCOPE_ALL)
        db.commit()
    client = web_app.app.test_client()
    client.post("/login", data={"username": "ws_operator", "password": "OperatorPass123!",
                                "csrf_token": CSRF_RE.search(client.get("/login").data.decode()).group(1)})
    page = client.get("/bank/why-signals").data.decode()
    csrf = BANK_CSRF_RE.search(page).group(1)
    check("1. page with breadcrumb and both modals closable by X",
          'aria-current="page">WHY Rules' in page and 'data-cancel="ws-movements" aria-label="Close"' in page
          and 'data-cancel="ws-rule" aria-label="Close"' in page)
    check("2. WHY Rules is in the Bank menu", "/bank/why-signals" in client.get("/bank").data.decode())

    data = client.get("/bank/why-signals/data").get_json()
    labels = set(data["labels"].values())
    check("3. groups by WHO, Source and reason, with the four reasons named as approved (+ incomplete split)",
          data["ok"] and labels == {"Serve una classificazione WHO + Source", "Serve una regola per il WHY",
                                    "Serve un documento o un chiarimento", "Regole in conflitto",
                                    "Ripartizione incompleta"}
          and all({"who", "source", "label", "count", "movements", "action"} <= set(g) for g in data["groups"]))
    check("4. the group counts add up, every movement once",
          sum(g["count"] for g in data["groups"]) == data["movements"] == sum(data["counts"].values())
          and len({mv["id"] for g in data["groups"] for mv in g["movements"]}) == data["movements"], data["counts"])
    check("5. no WHO is MULTIPLE after the migration; pair groups offer Classify WHO + Source",
          data["multiple"] == [] and all(g["action"] == "CLASSIFY_PAIR" for g in data["groups"]
                                         if g["reason"] == "WHO_SOURCE_CLASSIFICATION_MISSING"))

    # A WHO whose WHY comes from its WHO + Source pair today.
    eng = bank_why_signals._engine()
    try:
        paired = next(r for r in (eng.evaluate(t) for t in eng.txns) if r["why_method"] == "WHO + SOURCE" and r["who_id"])
    finally:
        eng.db.close()
    who_id = paired["who_id"]
    direction = "money out" if paired["amount_minor"] < 0 else "money in"
    r = client.post("/bank/why-signals/mode", data={"csrf_token": csrf, "who_id": who_id, "mode": "MULTIPLE"}).get_json()
    data = client.get("/bank/why-signals/data?refresh=1").get_json()
    mine = [g for g in data["groups"] if g["who_id"] == who_id]
    check("6. MULTIPLE: the registered pair WHY is no longer used -> Serve una regola per il WHY",
          r.get("ok") and mine and all(g["reason"] == "WHY_RULE_MISSING" and g["action"] == "DEFINE_RULE" for g in mine)
          and any(mv["id"] == paired["txn_id"] for g in mine for mv in g["movements"]), mine[:1])

    why = next(y for y in data["whys"] if y["id"] != paired["why_id"])
    spec = dict(who_ids=[who_id], conditions=[dict(field="direction", op="is", value=direction)], why_id=why["id"])
    sim = client.post("/bank/why-signals/simulate", data={"csrf_token": csrf, "spec": json.dumps(spec)}).get_json()
    check("7. simulation before saving: the movements of the WHO and the WHY they would get",
          sim.get("ok") and sim["summary"]["new_why"] >= 1 and any(x["id"] == paired["txn_id"] and x["after"] == why["name"]
                                                                  for x in sim["rows"]), sim.get("summary") or sim)
    refused = client.post("/bank/why-signals/rules", data={"csrf_token": csrf, "spec": json.dumps(spec)})
    check("8. a rule not simulated is refused", refused.status_code in (400, 409) and "Simulate" in refused.get_json()["error"])
    bad = client.post("/bank/why-signals/simulate", data={"csrf_token": csrf, "spec": json.dumps(dict(spec, conditions=[]))})
    check("9. a rule without conditions is refused", bad.status_code in (400, 409))
    saved = client.post("/bank/why-signals/rules", data={"csrf_token": csrf, "spec": json.dumps(spec), "simulated": "yes"}).get_json()
    data = client.get("/bank/why-signals/data?refresh=1").get_json()
    check("10. saved INACTIVE by default: the movements stay open",
          saved.get("status") == "INACTIVE" and any(g["who_id"] == who_id for g in data["groups"])
          and any(x["id"] == saved["id"] and x["status"] == "INACTIVE" for x in data["rules"]), saved)
    client.post(f"/bank/why-signals/rules/{saved['id']}/activate", data={"csrf_token": csrf})
    data = client.get("/bank/why-signals/data?refresh=1").get_json()
    check("11. activated: the WHY of those movements is determined by the rule (no longer listed for that direction)",
          not any(g["who_id"] == who_id and any(mv["id"] == paired["txn_id"] for mv in g["movements"]) for g in data["groups"]))
    no_token = client.post("/bank/why-signals/mode", data={"who_id": who_id, "mode": "UNIQUE"})
    check("12. writes need the CSRF token", no_token.status_code in (400, 403, 409))
    client.post(f"/bank/why-signals/rules/{saved['id']}/deactivate", data={"csrf_token": csrf})
    client.post("/bank/why-signals/mode", data={"csrf_token": csrf, "who_id": who_id, "mode": "UNIQUE"})
    data = client.get("/bank/why-signals/data?refresh=1").get_json()
    check("13. back to UNIQUE: the pair decides again", data["multiple"] == []
          and not any(g["who_id"] == who_id and any(mv["id"] == paired["txn_id"] for mv in g["movements"]) for g in data["groups"]))
    with SessionFactory() as db:
        check("14. no movement decision and no WHO + Source classification changed", preserved(db) == before)

    print(f"\n{len(passed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
