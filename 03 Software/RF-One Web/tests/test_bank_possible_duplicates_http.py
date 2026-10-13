#!/usr/bin/env python
"""HTTP test for possible duplicates at import (BANK_POSSIBLE_DUPLICATES_001).

Product Owner decision, 2026-10-13: a possible duplicate (same date,
description and amount) is an exception for the normal review, never a reason
to block the import. Without a decision it is imported, marked "Da verificare"
and linked to the movement it may repeat — never deleted, merged or confirmed
automatically. A running balance or bank reference that differs proves two
movements: they are kept as distinct. An unreadable row still has to be decided.

Runs against a DISPOSABLE SQLite database and staging folder created here.
"""

from __future__ import annotations

import io
import os
import re
import shutil
import sys
import tempfile
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_possible_dup_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "possible-dup-test-secret"
_STAGING_DIR = tempfile.mkdtemp(prefix="rfoneweb_possible_dup_staging_")

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
from rfone_data_store.bank_reconciliation import import_session  # noqa: E402

web_app.app.config["BANK_IMPORT_STAGING_DIR"] = _STAGING_DIR
CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
TOKEN_RE = re.compile(r"/bank/import/([0-9a-f]{32})")

CARD_NO = "Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n"
BANK = "Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #\n"

FILES = [
    # 0: a card with the same coffee twice in one file (no balance: nothing proves two).
    ("Chase3144_Activity_20261007.csv", (CARD_NO
        + "10/01/2026,10/02/2026,STARBUCKS 123,Food,Sale,-5.00,\n"
        + "10/01/2026,10/02/2026,STARBUCKS 123,Food,Sale,-5.00,\n"
        + "10/03/2026,10/03/2026,HOME DEPOT 44,Home,Sale,-80.00,\n").encode()),
    # 1: a bank account: two identical withdrawals, the balance proves two; one
    #    row repeating a transaction stored on ANOTHER Source; one unreadable row.
    ("Chase0214_Activity_20261007.csv", (BANK
        + "DEBIT,10/06/2026,WITHDRAWAL 10/06,-9600.00,MISC_DEBIT,10400.00,\n"
        + "DEBIT,10/06/2026,WITHDRAWAL 10/06,-9600.00,MISC_DEBIT,800.00,\n"
        + "DEBIT,10/07/2026,ADP PAYROLL,-100.00,ACH_DEBIT,700.00,\n"
        + "DEBIT,not-a-date,BROKEN ROW,,ACH_DEBIT,,\n").encode()),
]


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}"
              + ("" if condition or not detail else f"   [{str(detail)[:300]}]"))

    try:
        with SessionFactory() as db:
            account_service.create_account(db, username="pd_operator", display_name="pd_operator",
                                           password="OperatorPass123!", status="ACTIVE", is_admin=False)
            db.commit()
            operator = db.query(m.RFOneAccount).filter_by(username="pd_operator").one()
            account_service.set_domain_access(db, account_id=operator.id, domain_code="BANK", enabled=True,
                                              role_code=None)
            llc = config_service.create_entity(db, name="Test Owner, LLC", legal_name="Test Owner, LLC")
            other = m.PaymentInstrument(display_name="Old Card", instrument_type="CREDIT_CARD",
                                        institution="Chase", last_four="9999", status="ACTIVE")
            db.add(other)
            db.flush()
            stored = m.FinancialTransaction(
                payment_instrument_id=other.id, bank_source="CHASE_CREDIT_CARD_NO_CARD",
                posting_date=date(2026, 10, 7), description_original="ADP PAYROLL",
                description_normalized="ADP PAYROLL", amount_minor=-10000, status="COMPLETED",
                duplicate_status="NONE", review_status="REQUIRES_REVIEW")
            db.add(stored)
            db.commit()
            stored_id, llc_id = stored.id, llc.id

        client = web_app.app.test_client()
        client.post("/login", data={"username": "pd_operator", "password": "OperatorPass123!",
                                    "csrf_token": CSRF_RE.search(client.get("/login").data.decode()).group(1)})

        def csrf():
            return CSRF_RE.search(client.get("/bank").data.decode()).group(1)

        resp = client.post("/bank/upload", content_type="multipart/form-data", data={
            "csrf_token": csrf(), "files": [(io.BytesIO(c), n) for n, c in FILES]})
        token = TOKEN_RE.search(resp.headers.get("Location", "")).group(1)
        client.get(f"/bank/import/{token}")

        def save_source(index, prefill, **extra):
            data = dict(prefill, csrf_token=csrf(), import_token=token, import_file_index=str(index), **extra)
            return client.post("/bank/instruments/new", data=data, headers={"X-Requested-With": "fetch"})

        save_source(0, import_session.source_prefill("BANK", "Chase", "CREDIT_CARD", "3144"))
        save_source(1, import_session.source_prefill("BANK", "Chase", "BANK_ACCOUNT", "0214"))
        with SessionFactory() as s:
            card_id = s.scalars(select(m.PaymentInstrument.id).where(m.PaymentInstrument.last_four == "3144")).one()
            bank_id = s.scalars(select(m.PaymentInstrument.id).where(m.PaymentInstrument.last_four == "0214")).one()

        def complete(instrument_id, index, **fields):
            """The Source modal's Save on a row that has its Source (as in the two-pass test)."""
            with SessionFactory() as s:
                i = s.get(m.PaymentInstrument, instrument_id)
                data = {"display_name": i.display_name, "instrument_type": i.instrument_type,
                        "institution": i.institution or "", "last_four": i.last_four or "",
                        "keep_external_account_identifier": "1", "currency": i.currency or "", "status": i.status}
            data.update(fields, csrf_token=csrf(), import_token=token, import_file_index=str(index))
            return client.post(f"/bank/instruments/{instrument_id}/edit", data=data,
                               headers={"X-Requested-With": "fetch"})

        complete(bank_id, 1, owner_entity=f"re:{llc_id}")
        complete(card_id, 0, settlement_bank_account_id=str(bank_id), settlement_valid_from="2026-01-01")

        client.post(f"/bank/import/{token}/check", data={"csrf_token": csrf()})
        page = client.get(f"/bank/import/{token}").data.decode("utf-8")
        check("the balance proves the two 9,600.00 withdrawals distinct: listed, no question",
              "proven distinct by the bank" in page and "the running balance differs" in page, page[-3000:])
        check("only the unreadable row must be decided before Confirm",
              re.search(r'data-figure="unresolved">1<', page) is not None
              and re.search(r'data-figure="to_verify">2<', page) is not None)
        key = re.search(r'data-issue-key="([^"]+)" data-decision=""[^>]*>\s*<td data-label="Row" class="col-narrow">5<',
                        page)
        client.post(f"/bank/import/{token}/decide", data={"csrf_token": csrf(), "key": key.group(1) if key else "",
                                                           "decision": "EXCLUDE"})
        resp = client.post(f"/bank/upload/{token}/confirm", data={"csrf_token": csrf()})

        with SessionFactory() as s:
            new = s.scalars(select(m.FinancialTransaction).where(m.FinancialTransaction.import_batch_id.is_not(None))
                            .order_by(m.FinancialTransaction.id)).all()
            coffees = [t for t in new if t.description_original == "STARBUCKS 123"]
            withdrawals = [t for t in new if t.description_original == "WITHDRAWAL 10/06"]
            payroll = [t for t in new if t.description_original == "ADP PAYROLL"]
            check("Confirm is not blocked by possible duplicates: every readable row imported (3 + 3)",
                  len(new) == 6, f"{len(new)} {resp.status_code} {resp.headers.get('Location')}")
            check("the repeated coffee is kept, marked Da verificare and linked to the first one",
                  len(coffees) == 2 and coffees[0].duplicate_status == "NONE"
                  and coffees[1].duplicate_status == "CANDIDATE_DUPLICATE"
                  and coffees[1].duplicate_of_transaction_id == coffees[0].id,
                  str([(t.id, t.duplicate_status, t.duplicate_of_transaction_id) for t in coffees]))
            check("the withdrawals the balance proves distinct are both kept, neither flagged",
                  len(withdrawals) == 2 and {t.duplicate_status for t in withdrawals} == {"NONE"},
                  str([t.duplicate_status for t in withdrawals]))
            check("a repeat of a movement stored on ANOTHER Source is kept, Da verificare, linked to it",
                  len(payroll) == 1 and payroll[0].duplicate_status == "CANDIDATE_DUPLICATE"
                  and payroll[0].duplicate_of_transaction_id == stored_id,
                  str([(t.duplicate_status, t.duplicate_of_transaction_id) for t in payroll]))
            check("nothing is confirmed automatically",
                  not any(t.duplicate_status in ("CONFIRMED_DUPLICATE", "CONFIRMED_DISTINCT") for t in new))
        review = client.get("/bank/review?year=2026&month=10").data.decode("utf-8")
        check("the Review shows the possible duplicates as Da verificare, with the link to the other movement",
              review.count(">Da verificare</span>") >= 2 and f"#{stored_id}</a>" in review, review[:500])
    finally:
        try:
            os.remove(_TEST_DB_PATH)
        except OSError:
            pass
        shutil.rmtree(_STAGING_DIR, ignore_errors=True)

    print(f"\n{len(passed)} passed, {len(failed)} failed.")
    if failed:
        print("FAILED CHECKS:")
        for description in failed:
            print(f"  - {description}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
