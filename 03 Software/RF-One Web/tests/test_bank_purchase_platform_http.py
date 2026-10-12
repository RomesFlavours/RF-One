#!/usr/bin/env python
"""HTTP test for the Purchase platform Source type
(BANK_PURCHASE_PLATFORM_SOURCE_001).

A purchase platform (Amazon, Sam's, Instacart, ...) is a DOCUMENTARY source:
it provides orders, receipts, invoices and refunds to link to the movements of
the PAYMENT sources (bank account, credit card, PayPal). It is not another
account: it may have an owner / LLC (optional, never assigned automatically),
is never expected to send bank statements, never enters the bank-movement
import path (no duplicated spend), and never reaches the export.

Runs against a DISPOSABLE SQLite database created here and deleted at the end.
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

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_purchase_platform_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "purchase-platform-test-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from sqlalchemy import select  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.bank_reconciliation import configuration as config_service  # noqa: E402
from rfone_data_store.bank_reconciliation import export as export_service  # noqa: E402
from rfone_data_store.bank_reconciliation import import_preview  # noqa: E402
from rfone_data_store.bank_reconciliation import monthly_source  # noqa: E402
from rfone_data_store.bank_reconciliation import service as bank_service  # noqa: E402
from rfone_data_store.bank_reconciliation import who_recognition  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
FETCH = {"X-Requested-With": "fetch"}
CHASE = ("Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #\n"
         "DEBIT,10/05/2026,AMAZON MKTPL ORDER 1,-41.00,DEBIT_CARD,900.00,\n").encode()


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}"
              + ("" if condition or not detail else f"   [{str(detail)[:300]}]"))

    try:
        with SessionFactory() as db:
            account_service.create_account(db, username="pp_operator", display_name="pp_operator",
                                           password="OperatorPass123!", status="ACTIVE", is_admin=False)
            db.commit()
            operator = db.query(m.RFOneAccount).filter_by(username="pp_operator").one()
            account_service.set_domain_access(db, account_id=operator.id, domain_code="BANK", enabled=True,
                                              role_code=None)
            llc = config_service.create_entity(db, name="WP, LLC", legal_name="WP, LLC")
            checking = bank_service.create_payment_instrument(
                db, institution="Chase", display_name="WP Checking", instrument_type="BANK_ACCOUNT",
                last_four="3376", legal_entity_id=llc.legal_entity_id)
            db.commit()
            ids = {"checking": checking.id, "llc": llc.id, "llc_le": llc.legal_entity_id}

        client = web_app.app.test_client()
        client.post("/login", data={"username": "pp_operator", "password": "OperatorPass123!",
                                    "csrf_token": CSRF_RE.search(client.get("/login").data.decode()).group(1)})

        def token():
            return CSRF_RE.search(client.get("/bank/sources").data.decode()).group(1)

        # 1. Created through the Source modal's one Save, with no identifier and no owner.
        resp = client.post("/bank/instruments/new", headers=FETCH, data={
            "csrf_token": token(), "display_name": "Amazon", "instrument_type": "PURCHASE_PLATFORM",
            "institution": "", "last_four": "", "external_account_identifier": "", "currency": ""})
        with SessionFactory() as s:
            amazon = s.scalars(select(m.PaymentInstrument).where(m.PaymentInstrument.display_name == "Amazon")).one()
            ids["amazon"] = amazon.id
        check("1. a Purchase platform is saved with its type, no identifier, no owner, no LLC",
              resp.get_json()["ok"] and amazon.instrument_type == "PURCHASE_PLATFORM" and not amazon.is_payment_source
              and amazon.last_four is None and amazon.external_account_identifier is None
              and amazon.legal_entity_id is None and amazon.owner_reporting_entity_id is None)

        html = client.get("/bank/sources").data.decode("utf-8")
        row = html[html.index(f'data-source-id="{ids["amazon"]}"'):]
        row = row[:row.index("</tr>")]
        check("2. the list shows it as a Purchase platform, with no owner and no 'Not configured' warning",
              "Purchase platform" in row and "Documentary source" in row and "Not configured" not in row)
        check("2. the modal offers the type and its owner choice (only a card's owner is derived)",
              '<option value="PURCHASE_PLATFORM">Purchase platform</option>' in html
              and 'data-source-hide="CREDIT_CARD"' in html)

        resp = client.post("/bank/instruments/new", headers=FETCH, data={
            "csrf_token": token(), "display_name": "Sam's", "instrument_type": "PURCHASE_PLATFORM",
            "owner_entity": f"re:{ids['llc']}"})
        with SessionFactory() as s:
            sams = s.scalars(select(m.PaymentInstrument).where(m.PaymentInstrument.display_name == "Sam's")).one()
            sams_owner = (sams.legal_entity_id, sams.owner_reporting_entity_id)
            ids["sams"] = sams.id
        html = client.get("/bank/sources").data.decode("utf-8")
        sams_row = html[html.index(f'data-source-id="{ids["sams"]}"'):]
        sams_row = sams_row[:sams_row.index("</tr>")]
        check("3. a purchase platform can be saved with an owner / LLC (existing conventions) and shows it",
              resp.get_json()["ok"] and sams_owner == (ids["llc_le"], None) and "WP, LLC" in sams_row,
              str(resp.get_json()))
        with SessionFactory() as s:
            amazon_owner = s.get(m.PaymentInstrument, ids["amazon"])
        check("3b. a platform saved without one keeps its owner empty: nothing is assigned automatically",
              amazon_owner.legal_entity_id is None and amazon_owner.owner_reporting_entity_id is None)

        # 4. Never a choice where money movements are assigned.
        home = client.get("/bank?year=2026&month=10").data.decode("utf-8")
        upload = home[home.index('id="payment_instrument_id"'):]
        upload = upload[:upload.index("</select>")]
        review = client.get("/bank/review?year=2026&month=10").data.decode("utf-8")
        check("4. not offered as the Source of an uploaded file, nor in the Review Source filter",
              "Amazon" not in upload and "WP Checking" in upload and "Amazon" not in review)

        with SessionFactory() as s:
            relevant = {i.id for i in monthly_source.relevant_instruments(s)}
            preview = import_preview.preview_import(
                s, files=[import_preview.StagedFile("Chase3376_Activity_20261015.csv", CHASE)],
                uploaded_by_account_id=None)
        check("5. never expected to send bank files (monthly completeness, Import expected Sources)",
              ids["amazon"] not in relevant and ids["checking"] in relevant
              and not any("Amazon" in name for name in preview["expected_sources"])
              and not any("Amazon" in w for w in preview["warnings"]), str(preview["expected_sources"]))

        with SessionFactory() as s:
            refusals = []
            for attempt in (
                lambda: bank_service.import_csv(s, file_bytes=CHASE, original_file_name="x.csv",
                                                uploaded_by_account_id=None, payment_instrument_id=ids["amazon"]),
                lambda: bank_service.save_source_profile(s, detected_format="CHASE_BANK_ACCOUNT",
                                                         payment_instrument_id=ids["amazon"],
                                                         original_file_name="amazon.csv"),
            ):
                try:
                    attempt()
                    refusals.append(False)
                except ValueError as exc:
                    refusals.append("purchase platform" in str(exc))
            s.rollback()
            batch = bank_service.import_csv(s, file_bytes=CHASE, original_file_name="Chase3376_Activity_20261015.csv",
                                            uploaded_by_account_id=None)
            s.commit()
            txn = s.scalars(select(m.FinancialTransaction)).one()
            try:
                bank_service.assign_batch_instrument(s, batch_id=batch.batch.id, payment_instrument_id=ids["amazon"],
                                                     reason="test", changed_by_account_id=None)
                refusals.append(False)
            except ValueError as exc:
                refusals.append("purchase platform" in str(exc))
            try:
                bank_service.reassign_transaction_instrument(s, transaction_id=txn.id, payment_instrument_id=ids["amazon"],
                                                             reason="test", changed_by_account_id=None)
                refusals.append(False)
            except ValueError as exc:
                refusals.append("purchase platform" in str(exc))
            s.rollback()
            on_amazon = s.scalars(select(m.FinancialTransaction).where(
                m.FinancialTransaction.payment_instrument_id == ids["amazon"])).all()
        check("6. the bank-movement import path (file, file recognition rule, batch, transaction) refuses it: "
              "no duplicated spend",
              refusals == [True, True, True, True] and not on_amazon, str(refusals))

        with SessionFactory() as s:
            blockers = export_service.compute_export_blockers(s, year=2026, month=10)
            amazon_warning = bank_service.instrument_export_warning(s.get(m.PaymentInstrument, ids["amazon"]))
            platform_with_digits = bank_service.create_payment_instrument(
                s, institution="Instacart", display_name="Instacart", instrument_type="PURCHASE_PLATFORM",
                last_four="3376")
            s.flush()
            registered, _entities, _lookups = who_recognition.build_contexts(s)
            s.rollback()
        check("7. it never reaches the export: no blocker, no export warning",
              not any(b.instrument_id == ids["amazon"] for b in blockers)
              and amazon_warning is None, str([b.reason for b in blockers]))
        check("8. never taken for an own account in WHO recognition, even with digits",
              registered.get("3376") == ids["checking"])
        with SessionFactory() as s:
            payment_sources = {i.id for i in monthly_source.relevant_instruments(s)}
        check("9. the existing payment sources are unchanged", ids["checking"] in payment_sources)
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
