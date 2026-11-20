"""“+ New WHO” from reconciliation (BANK_RECONCILIATION_NEW_WHO_001).

Proves, on a throwaway database, that:

* Review and Reconciliation offer “+ New WHO” in Select WHO / WHY, with its
  dialog and script, next to “+ Create New WHY”;
* `POST /bank/whos/create` creates the WHO as Configuration does — an
  ACTIVE counterparty with no WHY, no default WHY, no Entity — and creates
  NO recognition rule, NO alias, and classifies NO transaction;
* a name that already IS an active WHO (same name, identity key, alias)
  reuses it — no duplicate; look-alike names are only offered by the lookup;
* empty / too-short names, a merged (inactive) WHO's name and a post
  without CSRF are refused, writing nothing;
* the created WHO is then in the modal's WHO list, and the normal Confirm
  records the classification with it.

BANK_OLD_RULES_REMOVAL_001: the old rule system's tables are gone, so the
counts no longer include recognition rules or WHO recognitions — the check
"…and nothing else" now covers aliases and explanations only (no rule / no
recognition hold by construction), and the final check "still no recognition
rule was created" is removed; every other check is unchanged.

Never touches a real bank file, AWS, or any production database.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_new_who_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "bank-new-who-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

from sqlalchemy import func, select  # noqa: E402

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
AUG = date(2026, 8, 12)


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    try:
        with SessionFactory() as s:
            account_service.create_account(s, username="new_who", display_name="New Who",
                                           password="NewWhoPass123!", status="ACTIVE", is_admin=False)
            s.flush()
            operator = s.query(m.RFOneAccount).filter_by(username="new_who").one()
            account_service.set_domain_access(s, account_id=operator.id, domain_code="BANK", enabled=True,
                                              role_code=None)
            legal = m.LegalEntity(legal_name="New Who LLC", status="ACTIVE")
            s.add(legal)
            s.flush()
            checking = m.PaymentInstrument(legal_entity_id=legal.id, instrument_type="BANK_ACCOUNT",
                                           display_name="New Who Checking", institution="CHASE", last_four="0008",
                                           currency="USD")
            s.add(checking)
            s.flush()
            batch = m.BankImportBatch(detected_format="CHASE_BANK_ACCOUNT", original_file_name="seed.csv",
                                      raw_file_bytes=b"x", sha256="8" * 64, status="NORMALIZED",
                                      payment_instrument_id=checking.id)
            s.add(batch)
            s.flush()
            counterparty = s.scalars(select(m.BankOccurrenceType).where(
                m.BankOccurrenceType.code == "COUNTERPARTY")).one()
            for name, status in (("Sysco Food Services", "ACTIVE"), ("Acme Supplies", "ACTIVE"),
                                 ("Old Vendor", "INACTIVE")):
                s.add(m.BankOccurrence(canonical_name=name, occurrence_type_id=counterparty.id, status=status))
            s.flush()
            why = s.scalars(select(m.BankTransactionReason).where(
                m.BankTransactionReason.status == "ACTIVE").order_by(m.BankTransactionReason.id)).first()
            tx = m.FinancialTransaction(
                payment_instrument_id=checking.id, bank_source="CHASE_BANK_ACCOUNT", import_batch_id=batch.id,
                posting_date=AUG, transaction_date=AUG, description_original="GREEN GROCER 12",
                description_normalized="GREEN GROCER 12", amount_minor=-4200, status="COMPLETED",
                duplicate_status="NONE", review_status="REQUIRES_REVIEW", accounting_status="CANONICAL",
                fingerprint="new-who-1", classification="UNKNOWN")
            s.add(tx)
            s.commit()
            tx_id, why_id = tx.id, why.id

        client = web_app.app.test_client()
        login = client.get("/login").data.decode()
        client.post("/login", data={"username": "new_who", "password": "NewWhoPass123!",
                                    "csrf_token": CSRF_RE.search(login).group(1)})
        review = client.get("/bank/review?year=2026&month=8").data.decode("utf-8")
        csrf = CSRF_RE.search(review).group(1)

        def counts():
            with SessionFactory() as s:
                return {
                    "who": s.scalar(select(func.count(m.BankOccurrence.id))),
                    "aliases": s.scalar(select(func.count(m.BankOccurrenceAlias.id))),
                    "explanations": s.scalar(select(func.count(m.BankTransactionExplanation.id))),
                }

        def create(name, with_csrf=True):
            data = {"name": name}
            if with_csrf:
                data["csrf_token"] = csrf
            return client.post("/bank/whos/create", data=data, headers={"X-Requested-With": "fetch"})

        # ------------------------------------------------------------ pages
        reconciliation = client.get("/bank/review?view=reconciled&year=2026&month=8").data.decode("utf-8")
        for label, page in (("Review > To Reconcile", review), ("Review > Reconciled", reconciliation)):
            check(f"{label}: Select WHO / WHY offers + New WHO next to + Create New WHY, with its dialog",
                  'id="who-picker-create"' in page and ">+ New WHO</button>" in page
                  and 'id="who-create-dialog"' in page and "js/bank-who-create.js" in page
                  and "js/rf-one-busy.js" in page and 'id="why-picker-create"' in page)

        # ---------------------------------------------------------- create
        before = counts()
        resp = create("Green Grocer")
        data = resp.get_json()
        after = counts()
        with SessionFactory() as s:
            who = s.get(m.BankOccurrence, data["who"]["id"]) if data.get("ok") else None
            shape = (who.status, who.occurrence_type.code, who.default_transaction_reason_id,
                     s.scalar(select(func.count(m.BankOccurrenceReasonAssociation.id)).where(
                         m.BankOccurrenceReasonAssociation.occurrence_id == who.id)),
                     s.scalar(select(func.count(m.BankOccurrenceReportingEntity.id)).where(
                         m.BankOccurrenceReportingEntity.occurrence_id == who.id))) if who else None
        check("Save creates the WHO as Configuration does: active counterparty, no WHY, no Entity",
              resp.status_code == 200 and data["ok"] and not data["reused"]
              and shape == ("ACTIVE", "COUNTERPARTY", None, 0, 0), str((data, shape)))
        check("…and nothing else: no alias, no transaction classified",
              after["who"] == before["who"] + 1 and all(after[k] == before[k] for k in after if k != "who"),
              str((before, after)))
        new_id = data["who"]["id"]

        # ------------------------------------------------------ duplicates
        for typed in ("Green Grocer", "  green   grocer ", "GREEN GROCER"):
            resp = create(typed)
            check(f"“{typed}” already is that WHO: reused, no duplicate",
                  resp.get_json()["ok"] and resp.get_json()["reused"] and resp.get_json()["who"]["id"] == new_id
                  and counts()["who"] == after["who"], resp.get_data(as_text=True)[:200])
        options = client.get("/bank/who-rules/who-options?q=Sysco").get_json()
        check("the lookup offers a look-alike WHO to choose (Sysco → Sysco Food Services), never decides it",
              any(o["name"] == "Sysco Food Services" for o in options["similar"] + options["matches"])
              and options["create"] == "Sysco", str(options))

        # -------------------------------------------------------- refusals
        for typed, why in (("", "empty"), ("X", "too short"), ("Old Vendor", "a merged (inactive) WHO")):
            resp = create(typed)
            check(f"refused — {why} — and nothing written",
                  resp.status_code == 400 and not resp.get_json()["ok"] and counts() == after,
                  resp.get_data(as_text=True)[:200])
        resp = create("No Csrf Vendor", with_csrf=False)
        check("refused without CSRF, nothing written", resp.status_code in (400, 403) and counts() == after,
              str(resp.status_code))

        # ---------------------------------------- selection and Confirm
        whos = client.get("/bank/manual-reconciliation/whos").get_json()
        check("the new WHO is in the modal's WHO list (alphabetical)",
              any(w["id"] == new_id for w in whos)
              and [w["name"].upper() for w in whos] == sorted(w["name"].upper() for w in whos))
        resp = client.post(f"/bank/transactions/{tx_id}/who-why", data={
            "csrf_token": csrf, "occurrence_id": str(new_id), "transaction_reason_id": str(why_id),
            "return_to": "/bank/review?year=2026&month=8"})
        with SessionFactory() as s:
            explanation = s.scalars(select(m.BankTransactionExplanation).where(
                m.BankTransactionExplanation.financial_transaction_id == tx_id)
                .order_by(m.BankTransactionExplanation.id.desc())).first()
        check("the normal Confirm then records the classification with the new WHO",
              resp.status_code == 302 and explanation is not None and explanation.occurrence_id == new_id,
              str(resp.status_code))
        # BANK_OLD_RULES_REMOVAL_001: "still no recognition rule was created"
        # is gone with bank_recognition_rules — it holds by construction.
    finally:
        try:
            os.remove(_TEST_DB_PATH)
        except OSError:
            pass

    print(f"\n{len(passed)} passed, {len(failed)} failed.")
    if failed:
        print("FAILED CHECKS:")
        for description in failed:
            print(f"  - {description}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
