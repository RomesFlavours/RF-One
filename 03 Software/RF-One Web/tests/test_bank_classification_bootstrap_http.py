#!/usr/bin/env python
"""HTTP-level test for the classification bootstrap
(BANK_CLASSIFICATION_BOOTSTRAP_001).

Exercises over HTTP: the What catalog import (upload, preview, confirm,
and the absence of any preview-free path), the Unclassified Receivers
section with its search, filters, sorting and pagination, group approval
onto a new and an existing Who, the Assigned / Learned Rules section, the
invoice boundary, the BANK gate and CSRF, and the standing UI rules.

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

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
TOKEN_RE = re.compile(r'name="preview_token" value="([^"]+)"')
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
            baseline_whats == 136, detail=str(baseline_whats),
        )
        check(
            "the page presents the five sections in order",
            all(marker in page for marker in (
                b"A. What", b"B. Why", b"C. Who",
                b"D. Unclassified Receivers", b"E. Assigned / Learned Rules",
            ))
            and page.index(b"A. What") < page.index(b"D. Unclassified Receivers")
            < page.index(b"E. Assigned / Learned Rules"),
        )
        check("the invoice boundary is stated on the page",
              b"Suppliers paid by invoice" in page and b"Accounts Payable settlement" in page)
        check("the page uses the wide, no-horizontal-scroll layout",
              b"wrap-wide" in page and b"table-stack" in page)
        check("the full account number is never rendered",
              FULL_ACCOUNT_NUMBER.encode() not in page)

        # =================================================================
        # Receiver candidates
        # =================================================================
        check("receiver groups are derived and shown",
              b"US FOODS INC 4821" in page and b"PUBLIX 1488" in page)
        check("the accounting duplicate is NOT offered as its own candidate",
              page.count(b"US FOODS INC 4821") >= 1
              and b"Transactions represented" in page)
        check("the summary reports the suppressed copies separately",
              b"Receiver groups" in page and b"Still unclassified" in page)
        check("search, status filter, sorting and pagination controls are present",
              all(marker in page for marker in (
                  b'name="receiver_q"', b'name="receiver_status"', b'name="receiver_sort"',
              )) and b"page 1 of" in page)

        filtered = client.get("/bank/classification?receiver_q=publix#receivers").data
        check("the receiver search filters the groups",
              b"PUBLIX 1488" in filtered and b"US FOODS INC 4821" not in filtered)
        by_value = client.get("/bank/classification?receiver_sort=value").data
        check("sorting by value responds", by_value.count(b"US FOODS INC 4821") >= 1)

        # =================================================================
        # What catalog import: preview, then confirm
        # =================================================================
        csrf = extract_csrf(page)
        resp = client.post("/bank/classification/what/import", data={
            "catalog_file": (io.BytesIO(CSV_PLAN), "plan.csv"),
            "csrf_token": csrf,
        }, content_type="multipart/form-data")
        preview = resp.data
        check("uploading a plan renders a preview", resp.status_code == 200
              and b"nothing has been imported yet" in preview)
        check("the preview shows statement type, code, name, parent, level and source",
              all(marker in preview for marker in (
                  b"<th>Statement</th>", b"<th>Code</th>", b"<th>Name</th>",
                  b"<th>Parent</th>", b"<th>Level</th>", b"<th>Source</th>",
                  b"<th>Anomalies</th>",
              )))
        check("the preview reports the Total row as skipped",
              b"TOTAL" in preview and b"Total cost of goods sold" in preview)

        with SessionFactory() as s:
            # BANK_CANONICAL_ACCOUNTING_CATALOG_001: the migration now seeds the
            # canonical chart, so "wrote nothing" means "unchanged", not "empty".
            check("the preview wrote nothing",
                  s.query(m.BankAccountingClassification).count() == baseline_whats)

        token_match = TOKEN_RE.search(preview.decode("utf-8"))
        check("the preview carries a confirmation token", token_match is not None)
        resp = client.post("/bank/classification/what/import/confirm", data={
            "preview_token": token_match.group(1), "csrf_token": extract_csrf(preview),
        })
        check("confirming the preview redirects back", resp.status_code in (302, 303))

        with SessionFactory() as s:
            codes = {w.code for w in s.query(m.BankAccountingClassification).all()}
            check("only the account rows were imported, not the Total",
                  {"TEST-5000", "TEST-5100", "TEST-2100"} <= codes
                  and "TEST-TOTAL" not in codes
                  and len(codes) == baseline_whats + 3,
                  detail=f"{len(codes)} codes, baseline {baseline_whats}")
            check("the hierarchy survived the import",
                  s.query(m.BankAccountingClassification).filter_by(code="TEST-5100").one().parent_id
                  == s.query(m.BankAccountingClassification).filter_by(code="TEST-5000").one().id)
            cogs_id = s.query(m.BankAccountingClassification).filter_by(code="TEST-5100").one().id

        page = client.get("/bank/classification").data
        check("the imported catalog appears in the What section",
              b"TEST-5100" in page and b"Food cost" in page)

        # A Why for the approval below.
        csrf = extract_csrf(page)
        client.post("/bank/classification/why/new", data={
            "code": "FOOD_PURCHASE", "name": "Food purchase",
            "accounting_classification_id": str(cogs_id), "csrf_token": csrf,
        })
        with SessionFactory() as s:
            why_id = s.query(m.BankTransactionReason).filter_by(code="FOOD_PURCHASE").one().id
            type_id = s.query(m.BankOccurrenceType).one().id

        # =================================================================
        # Approval
        # =================================================================
        page = client.get("/bank/classification").data
        csrf = extract_csrf(page)
        resp = client.post("/bank/classification/receivers/approve", data={
            "payee_key": "DEBIT|US FOODS INC 4821",
            "new_occurrence_name": "US Foods", "occurrence_type_id": str(type_id),
            "default_transaction_reason_id": str(why_id),
            "learn_description": "on", "csrf_token": csrf,
        })
        check("approving a group redirects back to Classification",
              resp.status_code in (302, 303))

        with SessionFactory() as s:
            who = s.query(m.BankOccurrence).filter_by(canonical_name="US Foods").one()
            decided = s.query(m.BankTransactionExplanation).filter(
                m.BankTransactionExplanation.occurrence_id == who.id,
                m.BankTransactionExplanation.decision_source == "HUMAN",
            ).all()
            check("both transactions of the group were classified in one action",
                  len(decided) == 2, detail=str(len(decided)))
            check("Why and What were derived from the Who, not supplied per transaction",
                  all(d.transaction_reason_id == why_id
                      and d.accounting_classification_code_snapshot == "TEST-5100" for d in decided))
            rules = s.query(m.BankRecognitionRule).all()
            check("an exact-match rule was recorded for future imports",
                  len(rules) == 1 and rules[0].match_type == "EXACT_NORMALIZED_DESCRIPTION"
                  and rules[0].normalized_pattern == "US FOODS INC 4821")
            copy = s.query(m.FinancialTransaction).filter_by(
                payment_instrument_id=s.query(m.PaymentInstrument).filter_by(
                    display_name="HTTP Card").one().id).one()
            check("the suppressed accounting copy was not classified",
                  copy.accounting_status == accounting_dedup.DUPLICATE_SUPPRESSED
                  and copy.explanation_id is None)

        page = client.get("/bank/classification").data
        check("the approved group is reported as ASSIGNED",
              b"ASSIGNED" in page)
        check("the learned rule is listed in the Assigned / Learned Rules section",
              b"EXACT_NORMALIZED_DESCRIPTION" in page and b"US FOODS INC 4821" in page)

        # Approving another group onto the SAME existing Who.
        with SessionFactory() as s:
            who_id = s.query(m.BankOccurrence).filter_by(canonical_name="US Foods").one().id
        csrf = extract_csrf(page)
        resp = client.post("/bank/classification/receivers/approve", data={
            "payee_key": "DEBIT|PUBLIX 1488", "occurrence_id": str(who_id),
            "learn_description": "on", "csrf_token": csrf,
        })
        with SessionFactory() as s:
            check("a second group can be approved onto the same existing Who",
                  s.query(m.BankRecognitionRule).count() == 2)

        # =================================================================
        # Security
        # =================================================================
        ungated = web_app.app.test_client()
        resp = ungated.get("/login")
        ungated.post("/login", data={
            "username": "no_bank_class", "password": "NoBankPass123!",
            "csrf_token": extract_csrf(resp.data),
        })
        check("the import route is behind the BANK domain gate",
              ungated.post("/bank/classification/what/import").status_code == 403)
        check("the approval route is behind the BANK domain gate",
              ungated.post("/bank/classification/receivers/approve").status_code == 403)
        check("an import without CSRF is refused",
              client.post("/bank/classification/what/import", data={
                  "catalog_file": (io.BytesIO(CSV_PLAN), "plan.csv"),
              }, content_type="multipart/form-data").status_code in (400, 403))
        check("an approval without CSRF is refused",
              client.post("/bank/classification/receivers/approve", data={
                  "payee_key": "DEBIT|PUBLIX 1488",
              }).status_code in (400, 403))

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
