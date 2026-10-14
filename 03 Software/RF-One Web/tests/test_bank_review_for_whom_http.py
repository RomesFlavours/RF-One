#!/usr/bin/env python
"""HTTP test for For Whom in Review Transactions (BANK_REVIEW_FOR_WHOM_001).

The Source / Instrument of a transaction is provenance, set by the import's
file -> Source mapping: Review shows it read-only, with no per-transaction
Reassign. Under it, FOR WHOM — the Reporting Entity / LLC that benefited —
is a reconciliation decision, editable in To Reconcile (before WHO / WHY)
and in Reconciled, changing the beneficiary and nothing else.

BANK_OLD_RULES_REMOVAL_001: the check "11. no Rule and no Standard is
created" is removed — the old rule and Standard tables no longer exist, so
nothing can be created there; every other check (and its number) is unchanged.

Runs against a DISPOSABLE SQLite database created here and deleted at the end.
"""

from __future__ import annotations

import html as html_lib
import os
import re
import sys
import tempfile
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_review_for_whom_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "review-for-whom-test-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
import tempfile as _tempfile  # noqa: E402
web_app.app.config["BANK_IMPORT_STAGING_DIR"] = _tempfile.mkdtemp(prefix="rfoneweb_staging_")  # never the real staging folder
from db import SessionFactory  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.bank_reconciliation import card_configuration, recognition  # noqa: E402
from rfone_data_store.bank_reconciliation import configuration as config_service  # noqa: E402
from rfone_data_store.bank_reconciliation import reconciliation_status  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
TO_REC = "/bank/review?year=2026&month=8"
REC = "/bank/review?view=reconciled&year=2026&month=8"


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f"   [{str(detail)[:300]}]"))

    try:
        # ------------------------------------------------------------ fixture
        ids: dict[str, int] = {}
        with SessionFactory() as db:
            account_service.create_account(db, username="fw_operator", display_name="fw_operator",
                                           password="OperatorPass123!", status="ACTIVE", is_admin=False)
            db.commit()
            operator = db.query(m.RFOneAccount).filter_by(username="fw_operator").one()
            account_service.set_domain_access(db, account_id=operator.id, domain_code="BANK", enabled=True, role_code=None)
            wp = config_service.create_entity(db, name="Rome's Flavours WP", legal_name="Rome's Flavours WP, LLC")
            md = config_service.create_entity(db, name="Rome's Flavours Mount Dora", legal_name="Rome's Flavours Mount Dora, LLC")
            brand = config_service.create_entity(db, name="Brand X", legal_name="")
            old = config_service.create_entity(db, name="Old Closed LLC", legal_name="Old Closed, LLC", active=False)
            checking = m.PaymentInstrument(display_name="RFWP-Checking", instrument_type="BANK_ACCOUNT",
                                           institution="CHASE", last_four="3376",
                                           legal_entity_id=wp.legal_entity_id, status="ACTIVE")
            # The card's OWN entity is Mount Dora; it settles to WP's checking.
            card = m.PaymentInstrument(display_name="WP Card", instrument_type="CREDIT_CARD", institution="CHASE",
                                       last_four="1057", legal_entity_id=md.legal_entity_id, status="ACTIVE")
            db.add_all([checking, card])
            db.flush()
            card_configuration.assign_settlement_account(
                db, credit_card_payment_instrument_id=card.id, settlement_bank_account_id=checking.id,
                valid_from=date(2026, 1, 1))
            why = db.scalars(select(m.BankTransactionReason).where(m.BankTransactionReason.status == "ACTIVE",
                                                                    m.BankTransactionReason.accounting_classification_id.is_not(None))
                             .order_by(m.BankTransactionReason.id)).first()
            gfs = config_service.save_who(db, occurrence_id=None, name="Gordon Food Service", active=True,
                                          reason_ids=[why.id], default_reason_id=why.id,
                                          reporting_entity_ids=[])

            def txn(instrument, day, text, minor):
                t = m.FinancialTransaction(
                    payment_instrument_id=instrument.id, bank_source="CHASE_BANK_ACCOUNT",
                    posting_date=date(2026, 8, day), description_original=text, description_normalized=text,
                    amount_minor=minor, status="COMPLETED", duplicate_status="NONE", review_status="REQUIRES_REVIEW")
                db.add(t)
                db.flush()
                return t
            t1 = txn(checking, 5, "ZELLE PAYMENT TO MARIA LOPEZ", -30000)        # To Reconcile, no WHO
            t2 = txn(card, 6, "AMAZON MKTPL ORDER 77", -8994)                     # To Reconcile, card
            t3 = txn(checking, 7, "GORDON FOOD SERVICE #1234 ORLANDO FL", -128437)  # Reconciled
            db.commit()
            recognition.record_human_decision(db, recognition.HumanDecisionRequest(
                transaction_id=t3.id, occurrence_id=gfs.id, transaction_reason_id=why.id,
                confirmed_by_account_id=operator.id))
            db.commit()
            ids.update(wp=wp.id, md=md.id, brand=brand.id, old=old.id, checking=checking.id, card=card.id,
                       gfs=gfs.id, why=why.id, t1=t1.id, t2=t2.id, t3=t3.id, operator=operator.id)

        client = web_app.app.test_client()
        client.post("/login", data={"username": "fw_operator", "password": "OperatorPass123!",
                                    "csrf_token": CSRF_RE.search(client.get("/login").data.decode()).group(1)})
        page = client.get(TO_REC).data.decode("utf-8")
        token = CSRF_RE.search(page).group(1)

        def source_cell(html, tid):
            start = html.index(f'<tr id="t-{tid}"')
            cell = html[start:]
            at = cell.index('data-label="Instrument"')
            return cell[at:cell.index("</td>", at)]

        def rec_cell(html, tid):
            start = html.index(f'<tr id="t-{tid}"')
            cell = html[start:]
            at = cell.index('class="rp-account"')
            return cell[at:cell.index("</td>", at)]

        def selected(cell):
            match = re.search(r'<option value="(\d+)" selected>', cell)
            return int(match.group(1)) if match else None

        def set_for_whom(tid, entity_id, back=TO_REC):
            return client.post(f"/bank/reconciliation/{tid}/for-whom",
                               data={"csrf_token": token, "for_whom_id": str(entity_id), "return_to": back})

        def snapshot(tid):
            with SessionFactory() as s:
                t = s.get(m.FinancialTransaction, tid)
                e = s.get(m.BankTransactionExplanation, t.explanation_id) if t.explanation_id else None
                a = s.scalars(select(m.BankTransactionAllocation).where(
                    m.BankTransactionAllocation.financial_transaction_id == tid)).all()
                return {"instrument": t.payment_instrument_id, "amount": t.amount_minor, "date": t.posting_date,
                        "explanation": t.explanation_id, "who": e.occurrence_id if e else None,
                        "why": e.transaction_reason_id if e else None,
                        "for_whom": [x.reporting_entity_id for x in a], "alloc_status": [x.status for x in a],
                        "status": reconciliation_status.statuses_for(s, [t])[t.id]}

        # ================================================================ 1-6
        c1, c2 = source_cell(page, ids["t1"]), source_cell(page, ids["t2"])
        check("1. no Reassign control in Review (no Reassign / Move to / Why? (required))",
              "Reassign" not in page and "Move to" not in page and "Why? (required)" not in page)
        check("2. the Source / Instrument stays visible, read-only",
              '<span class="source-name">RFWP-Checking</span>' in c1 and '<span class="source-name">WP Card</span>' in c2)
        check("3. For Whom is shown under the Source, as a compact selector",
              c1.index("source-name") < c1.index("For Whom:") and 'name="for_whom_id"' in c1)
        options = re.findall(r'<option value="(\d+)"[^>]*>([^<]+)</option>', c1)
        check("4. the selector lists the ACTIVE Reporting Entities, alphabetically, by name (no inactive, no ids)",
              [html_lib.unescape(name) for _, name in options] == ["Brand X", "Rome's Flavours Mount Dora", "Rome's Flavours WP"]
              and str(ids["old"]) not in [v for v, _ in options], str(options))
        check("5. the default comes from the Source's ownership: bank account -> its LLC; card -> its "
              "settlement account's LLC (not the card's own)",
              selected(c1) == ids["wp"] and selected(c2) == ids["wp"], f"{selected(c1)} {selected(c2)}")

        # ================================================================ 7-12 (To Reconcile)
        before = snapshot(ids["t1"])
        resp = set_for_whom(ids["t1"], ids["md"])
        after = snapshot(ids["t1"])
        check("7/12. in To Reconcile, before any WHO / WHY, For Whom is saved",
              resp.status_code == 302 and after["for_whom"] == [ids["md"]] and before["who"] is None,
              str(after))
        check("7. it returns to the same Review row", resp.headers["Location"].endswith(f"{TO_REC}#t-{ids['t1']}"),
              resp.headers.get("Location"))
        check("8-11. the Source, WHO, WHY, amount and date are unchanged",
              (after["instrument"], after["who"], after["why"], after["amount"], after["date"], after["explanation"])
              == (before["instrument"], before["who"], before["why"], before["amount"], before["date"], before["explanation"]))
        # BANK_OLD_RULES_REMOVAL_001: "11. no Rule and no Standard is created"
        # is gone with the old rule / Standard tables — it holds by construction.
        check("12. the row stays To Reconcile (still needs its WHO), status Needs review",
              after["status"] == "Needs review" and f'data-transaction-id="{ids["t1"]}"' in client.get(TO_REC).data.decode())
        check("6. the stored For Whom is displayed (not the default)",
              selected(source_cell(client.get(TO_REC).data.decode(), ids["t1"])) == ids["md"])
        resp = set_for_whom(ids["t1"], ids["old"])
        check("4. an inactive entity is refused", snapshot(ids["t1"])["for_whom"] == [ids["md"]])

        # WHO + WHY chosen afterwards keep the For Whom a person already chose.
        client.post(f"/bank/transactions/{ids['t1']}/who-why", data={
            "csrf_token": token, "occurrence_id": str(ids["gfs"]), "transaction_reason_id": str(ids["why"])})
        check("7. choosing WHO / WHY later keeps the For Whom", snapshot(ids["t1"])["for_whom"] == [ids["md"]])

        # ================================================================ 13-14 (Reconciled)
        rec = client.get(REC).data.decode("utf-8")
        r3 = rec_cell(rec, ids["t3"])
        check("13. Reconciled shows For Whom under the Account / Card, editable",
              r3.index("rp-account-name") < r3.index("For Whom:") and 'data-action="for-whom"' in r3
              and "<th>For whom</th>" not in rec)
        before3 = snapshot(ids["t3"])
        resp = set_for_whom(ids["t3"], ids["brand"], back=REC)
        after3 = snapshot(ids["t3"])
        check("13. setting For Whom from Reconciled persists and returns to the row",
              after3["for_whom"] == [ids["brand"]] and resp.headers["Location"].endswith(f"{REC}#t-{ids['t3']}")
              and (after3["who"], after3["why"], after3["instrument"]) == (before3["who"], before3["why"], before3["instrument"]))
        client.post(f"/bank/reconciliation/{ids['t3']}/confirm", data={
            "csrf_token": token, "for_whom_id": str(ids["wp"]), "return_to": REC})
        confirmed = snapshot(ids["t3"])
        check("14. Confirm records the For Whom shown (COMPLETE, Confirmed)",
              confirmed["status"] == "Confirmed" and confirmed["for_whom"] == [ids["wp"]], str(confirmed))
        resp = set_for_whom(ids["t3"], ids["wp"], back=REC)
        check("14. choosing the same For Whom again changes nothing (still Confirmed)",
              snapshot(ids["t3"])["status"] == "Confirmed")
        resp = set_for_whom(ids["t3"], ids["md"], back=REC)
        changed = snapshot(ids["t3"])
        msg = client.get(resp.headers["Location"]).data.decode("utf-8")
        check("14. a changed For Whom on a Confirmed row follows the existing rule: Needs review until "
              "confirmed again, with the new beneficiary kept",
              changed["status"] == "Needs review" and changed["for_whom"] == [ids["md"]]
              and changed["alloc_status"] != ["COMPLETE"] and "needs a new confirmation" in msg, str(changed))
        client.post(f"/bank/reconciliation/{ids['t3']}/confirm", data={
            "csrf_token": token, "for_whom_id": str(ids["md"]), "return_to": REC})
        check("14. a new Confirm makes it Confirmed for the new LLC",
              snapshot(ids["t3"])["status"] == "Confirmed" and snapshot(ids["t3"])["for_whom"] == [ids["md"]])
        with SessionFactory() as s:
            a = s.scalars(select(m.BankTransactionAllocation).where(
                m.BankTransactionAllocation.financial_transaction_id == ids["t3"])).one()
            check("14. paid by WP's account for Mount Dora: the intercompany consequence is derived",
                  a.intercompany_outcome == "CROSS_ENTITY", a.intercompany_outcome)

        # ================================================================ 15-16
        resp = client.post(f"/bank/transactions/{ids['t2']}/reassign-instrument", data={
            "csrf_token": token, "payment_instrument_id": str(ids["checking"]), "reason": "x"})
        check("15. there is no per-transaction Source reassignment path (404) and nothing moved",
              resp.status_code == 404 and snapshot(ids["t2"])["instrument"] == ids["card"])
        rules = {r.rule for r in web_app.app.url_map.iter_rules()}
        check("16. the Source / Import workflow is unchanged (Source page, file Change Source, staged upload)",
              client.get("/bank/sources").status_code == 200 and client.get("/bank").status_code == 200
              and "/bank/batches/<int:batch_id>/resolve-instrument" in rules
              and "/bank/upload/<token>/confirm" in rules)
    finally:
        try:
            os.remove(_TEST_DB_PATH)
        except OSError:
            pass

    print(f"\n{len(passed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
