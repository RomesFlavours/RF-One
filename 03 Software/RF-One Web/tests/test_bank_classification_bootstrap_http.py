#!/usr/bin/env python
"""HTTP-level test for the classification bootstrap
(BANK_CLASSIFICATION_BOOTSTRAP_001).

Exercises over HTTP the Classification page as the WHO occurrence list
with its rules, the invoice boundary and the standing UI rules. The former
What catalog import and receiver-group approval routes are retired with the
legacy Classification template (BANK_FINAL_CLEANUP_001) and are checked to
be gone.

Never touches a real bank file, AWS, or any production database.
"""

from __future__ import annotations

import io
import os
import re
import sys
import tempfile
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_classification_bootstrap_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "classification-bootstrap-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.bank_reconciliation import accounting_dedup  # noqa: E402
from rfone_data_store.bank_reconciliation import card_configuration as cards  # noqa: E402
from rfone_data_store.bank_reconciliation import classification as classification_service  # noqa: E402
from rfone_data_store.bank_reconciliation import recognition  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
FULL_ACCOUNT_NUMBER = "1122334455667788"

# Deliberately TEST- prefixed: the canonical RF-One chart already owns
# 5000/5100/2100, and reusing those codes would exercise the conflict
# path instead of the import path this test is about.
CSV_PLAN = (
    b"Statement Type,Code,Name,Parent,Level\n"
    b"P&L,TEST-5000,Cost of goods sold,,0\n"
    b"P&L,TEST-5100,Food cost,TEST-5000,1\n"
    b"P&L,,Total cost of goods sold,,0\n"
    b"Balance Sheet,TEST-2100,Accounts payable,,0\n"
)


def extract_csrf(html: bytes) -> str:
    match = CSRF_RE.search(html.decode("utf-8"))
    assert match, "csrf_token not found"
    return match.group(1)


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        if condition:
            passed.append(description)
        else:
            failed.append(description)
            print(f"FAILED: {description}" + (f" ({detail})" if detail else ""))

    try:
        with SessionFactory() as s:
            account_service.create_account(
                s, username="class_operator", display_name="Classification Operator",
                password="OperatorPass123!", status="ACTIVE", is_admin=False,
            )
            account_service.create_account(
                s, username="no_bank_class", display_name="No Bank",
                password="NoBankPass123!", status="ACTIVE", is_admin=False,
            )
            entity = m.LegalEntity(legal_name="Bootstrap HTTP LLC", status="ACTIVE")
            s.add(entity)
            s.commit()
            operator = s.query(m.RFOneAccount).filter_by(username="class_operator").one()
            account_service.set_domain_access(
                s, account_id=operator.id, domain_code="BANK", enabled=True, role_code=None,
            )

            checking = m.PaymentInstrument(
                legal_entity_id=entity.id, instrument_type="BANK_ACCOUNT",
                display_name="HTTP Checking", institution="CHASE", last_four="0001",
                external_account_identifier=FULL_ACCOUNT_NUMBER, currency="USD",
            )
            s.add(checking)
            s.flush()
            card = m.PaymentInstrument(
                legal_entity_id=None, instrument_type="CREDIT_CARD",
                display_name="HTTP Card", institution="CHASE", last_four="1057",
            )
            s.add(card)
            s.flush()
            cards.assign_settlement_account(
                s, credit_card_payment_instrument_id=card.id,
                settlement_bank_account_id=checking.id, valid_from=date(2026, 1, 1),
            )
            s.add(m.BankOccurrenceType(code="SUPPLIER", name="Supplier"))

            def txn(instrument, day, amount, description):
                s.add(m.FinancialTransaction(
                    payment_instrument_id=instrument.id, bank_source="CHASE_BANK_ACCOUNT",
                    posting_date=date(2026, 5, day), description_original=description,
                    description_normalized=description.upper(), amount_minor=amount,
                    status="COMPLETED", duplicate_status="NONE", review_status="REQUIRES_REVIEW",
                ))

            txn(checking, 1, -10000, "US FOODS INC #4821")
            txn(checking, 2, -20000, "US Foods Inc. *4821")
            txn(checking, 3, -5000, "PUBLIX 1488")
            txn(card, 1, -10000, "US FOODS INC #4821")      # accounting duplicate
            s.commit()
            accounting_dedup.recompute_accounting_dedup(s)
            s.commit()

        client = web_app.app.test_client()
        resp = client.get("/login")
        client.post("/login", data={
            "username": "class_operator", "password": "OperatorPass123!",
            "csrf_token": extract_csrf(resp.data),
        })

        # =================================================================
        # Page structure
        # =================================================================
        with SessionFactory() as s:
            baseline_whats = s.query(m.BankAccountingClassification).count()

        page = client.get("/bank/classification").data
        check(
            "the canonical accounting catalog is present after the ordinary migration",
            baseline_whats == 137, detail=str(baseline_whats),
        )
        # BANK_SIMPLE_WHO_RULE_001 — Classification is now the WHO occurrence
        # list with the shared Rule modal. WHAT / WHY / WHO are maintained in
        # Configuration, and the receiver review is no longer rendered here.
        check(
            "the page is the WHO occurrence list, pointing to Configuration for the vocabulary",
            b"Search WHO" in page and b'id="who-rule-modal"' in page and b"/bank/configuration" in page
            and b"A. What" not in page and b"D. Unclassified Receivers" not in page,
        )
        check("the full account number is never rendered",
              FULL_ACCOUNT_NUMBER.encode() not in page)

        # =================================================================
        # Receiver candidates
        # =================================================================
        check("the receiver review is no longer built on the Classification page",
              b"Receiver groups" not in page and b'name="receiver_q"' not in page)

        # =================================================================
        # Retired routes (BANK_FINAL_CLEANUP_001)
        # =================================================================
        # The What catalog import preview and the receiver-group approval
        # were reachable only from the retired legacy Classification
        # template. Their services stay (Data Store test
        # test_bank_classification_bootstrap.py); the routes are gone.
        csrf = extract_csrf(page)
        with SessionFactory() as s:
            whats_before = s.query(m.BankAccountingClassification).count()
            whos_before = s.query(m.BankOccurrence).count()
        retired = [
            client.post("/bank/classification/what/import", data={
                "catalog_file": (io.BytesIO(CSV_PLAN), "plan.csv"), "csrf_token": csrf,
            }, content_type="multipart/form-data"),
            client.post("/bank/classification/what/import/confirm", data={"csrf_token": csrf}),
            client.post("/bank/classification/receivers/approve", data={
                "payee_key": "DEBIT|US FOODS INC 4821", "new_occurrence_name": "US Foods",
                "csrf_token": csrf,
            }),
        ]
        with SessionFactory() as s:
            check("the retired What-import and receiver-approval routes are gone (404) and write nothing",
                  all(r.status_code == 404 for r in retired)
                  and s.query(m.BankAccountingClassification).count() == whats_before
                  and s.query(m.BankOccurrence).count() == whos_before,
                  detail=str([r.status_code for r in retired]))

        # A WHO a person created, with the exact-description rule a person
        # approved: the Classification list shows both.
        with SessionFactory() as s:
            type_id = s.query(m.BankOccurrenceType).filter_by(code="SUPPLIER").one().id
            who = classification_service.create_occurrence(
                s, canonical_name="US Foods", occurrence_type_id=type_id, default_transaction_reason_id=None)
            recognition.create_or_reuse_rule(
                s, match_type="EXACT_NORMALIZED_DESCRIPTION", normalized_pattern="US FOODS INC 4821",
                occurrence_id=who.id, transaction_reason_id=None, payment_instrument_id=None,
                direction=None, auto_apply_enabled=True, created_from_transaction_id=None)
            s.commit()

        page = client.get("/bank/classification").data
        check("the WHO is listed on Classification with a Rule button",
              b"US Foods" in page and b'class="who-rule-open"' in page and b"table-stack" in page)
        check("its rule is shown next to its WHO",
              "is exactly \u201cUS FOODS INC 4821\u201d".encode() in page)

        # The modal controller is available on this page too.
        check("the shared modal controller is loaded",
              b"rf-one-modal.js" in client.get("/bank/classification").data)

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
