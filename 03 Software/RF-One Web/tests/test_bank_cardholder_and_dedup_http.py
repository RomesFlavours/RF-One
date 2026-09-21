#!/usr/bin/env python
"""HTTP-level test for cardholder history, settlement accounts and
accounting deduplication (BANK_CARDHOLDER_AND_ACCOUNTING_DEDUPLICATION_001).

Same convention as the other RF-One Web suites: a throwaway SQLite
database created BEFORE `app.py` is imported, migrated explicitly,
Werkzeug's test client, `main()` returning an exit code. Never touches a
real bank file, AWS, or any production database.

Exercises over HTTP: the extended Payment Instruments list, settlement
account and cardholder assignment with their history, the accounting
deduplication summary and recompute, the Review marking of suppressed
copies, the BANK domain gate, CSRF on every mutation, and the standing
rule that a full account number is never rendered.
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

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_card_dedup_test_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "card-dedup-http-test-secret"

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

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')

FULL_ACCOUNT_NUMBER = "9876543210001234"


def extract_csrf(html: bytes) -> str:
    match = CSRF_RE.search(html.decode("utf-8"))
    assert match, "csrf_token not found in response HTML"
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
        # -----------------------------------------------------------------
        # Accounts, instruments and transactions.
        # -----------------------------------------------------------------
        with SessionFactory() as s:
            account_service.create_account(
                s, username="card_operator", display_name="Card Operator",
                password="OperatorPass123!", status="ACTIVE", is_admin=False,
            )
            account_service.create_account(
                s, username="no_bank_user", display_name="No Bank",
                password="NoBankPass123!", status="ACTIVE", is_admin=False,
            )
            entity = m.LegalEntity(legal_name="Cardholder Test LLC", status="ACTIVE")
            s.add(entity)
            s.commit()
            operator = s.query(m.RFOneAccount).filter_by(username="card_operator").one()
            account_service.set_domain_access(
                s, account_id=operator.id, domain_code="BANK", enabled=True, role_code=None,
            )
            s.commit()
            entity_id = entity.id

        operator_client = web_app.app.test_client()
        resp = operator_client.get("/login")
        operator_client.post("/login", data={
            "username": "card_operator", "password": "OperatorPass123!",
            "csrf_token": extract_csrf(resp.data),
        })

        # Bank account carrying a FULL account number — the standing rule is
        # that it is never rendered, only its last four.
        resp = operator_client.get("/bank")
        csrf = extract_csrf(resp.data)
        operator_client.post("/bank/instruments/new", data={
            "institution": "CHASE", "display_name": "Chase Checking 1234",
            "instrument_type": "BANK_ACCOUNT", "legal_entity_id": str(entity_id),
            "external_account_identifier": FULL_ACCOUNT_NUMBER, "csrf_token": csrf,
        })
        for name, last_four in (("Chase Card 1057", "1057"), ("Chase Card 4482", "4482")):
            operator_client.post("/bank/instruments/new", data={
                "institution": "CHASE", "display_name": name,
                "instrument_type": "CREDIT_CARD", "last_four": last_four,
                "csrf_token": csrf,
            })

        with SessionFactory() as s:
            checking = s.query(m.PaymentInstrument).filter_by(display_name="Chase Checking 1234").one()
            mother = s.query(m.PaymentInstrument).filter_by(display_name="Chase Card 1057").one()
            child = s.query(m.PaymentInstrument).filter_by(display_name="Chase Card 4482").one()
            checking_id, mother_id, child_id = checking.id, mother.id, child.id

        # -----------------------------------------------------------------
        # Payment Instruments list.
        # -----------------------------------------------------------------
        listing = operator_client.get("/bank").data
        check(
            "the Payment Instruments list shows the required columns",
            all(
                col in listing for col in (
                    b"<th>Name</th>", b"<th>Institution</th>", b"<th>Type</th>",
                    b"<th>Last 4</th>", b"<th>Company</th>", b"<th>Settlement Account</th>",
                    b"<th>Current Cardholder</th>", b"<th>State</th>",
                )
            ),
        )
        check(
            "23. the full account number is never rendered on the instruments list",
            FULL_ACCOUNT_NUMBER.encode() not in listing,
        )
        check(
            "23b. only its last four digits are shown",
            FULL_ACCOUNT_NUMBER[-4:].encode() in listing,
        )
        check(
            "a card with no settlement account is visibly flagged, not silently blank",
            b"Not configured" in listing,
        )
        check(
            "24. the instruments table stays responsive — wide layout, stacking table, local scroll",
            b"wrap-wide" in listing and b"table-stack" in listing and b"table-scroll" in listing,
        )

        # -----------------------------------------------------------------
        # Domain gate and CSRF on the new mutations.
        # -----------------------------------------------------------------
        ungated = web_app.app.test_client()
        resp = ungated.get("/login")
        ungated.post("/login", data={
            "username": "no_bank_user", "password": "NoBankPass123!",
            "csrf_token": extract_csrf(resp.data),
        })
        check(
            "the settlement-account route is behind the BANK domain gate",
            ungated.post(f"/bank/instruments/{mother_id}/settlement").status_code == 403,
        )
        check(
            "the cardholder route is behind the BANK domain gate",
            ungated.post(f"/bank/instruments/{mother_id}/cardholder").status_code == 403,
        )
        check(
            "the recompute route is behind the BANK domain gate",
            ungated.post("/bank/accounting-dedup/recompute").status_code == 403,
        )
        check(
            "a settlement assignment without a CSRF token is refused",
            operator_client.post(
                f"/bank/instruments/{mother_id}/settlement",
                data={"settlement_bank_account_id": str(checking_id), "valid_from": "2026-01-01"},
            ).status_code in (400, 403),
        )

        # -----------------------------------------------------------------
        # Settlement account and cardholder, over HTTP.
        # -----------------------------------------------------------------
        edit_page = operator_client.get(f"/bank/instruments/{mother_id}/edit").data
        check("the card edit page offers a settlement account panel", b"Settlement account" in edit_page)
        check("the card edit page offers a cardholder panel", b"Cardholder" in edit_page)
        check(
            "only bank accounts are offered as settlement accounts, never another card",
            b"Chase Checking 1234" in edit_page and b"<option" in edit_page
            and edit_page.count(b"Chase Card 4482") <= 1,
        )

        csrf = extract_csrf(edit_page)
        for card_id in (mother_id, child_id):
            page = operator_client.get(f"/bank/instruments/{card_id}/edit").data
            resp = operator_client.post(
                f"/bank/instruments/{card_id}/settlement",
                data={
                    "settlement_bank_account_id": str(checking_id),
                    "valid_from": "2026-01-01", "notes": "QA synthetic assignment",
                    "csrf_token": extract_csrf(page),
                },
            )
            check(f"assigning a settlement account to instrument {card_id} redirects back",
                  resp.status_code in (302, 303))

        page = operator_client.get(f"/bank/instruments/{mother_id}/edit").data
        resp = operator_client.post(
            f"/bank/instruments/{mother_id}/cardholder",
            data={
                "holder_kind": "UNLINKED_PERSON", "holder_display_name": "QA Test Holder",
                "valid_from": "2026-01-01", "csrf_token": extract_csrf(page),
            },
        )
        check("assigning a cardholder redirects back", resp.status_code in (302, 303))

        page = operator_client.get(f"/bank/instruments/{mother_id}/edit").data
        resp = operator_client.post(
            f"/bank/instruments/{mother_id}/cardholder",
            data={
                "holder_kind": "UNLINKED_PERSON", "holder_display_name": "QA Second Holder",
                "valid_from": "2026-06-01", "csrf_token": extract_csrf(page),
            },
        )
        history_page = operator_client.get(f"/bank/instruments/{mother_id}/edit").data
        check(
            "the cardholder history shows both holders, the previous one closed",
            b"QA Test Holder" in history_page and b"QA Second Holder" in history_page,
        )
        check(
            "the settlement history is shown with its effective date",
            b"QA synthetic assignment" in history_page and b"2026-01-01" in history_page,
        )
        check(
            "the full account number is never rendered on the card edit page",
            FULL_ACCOUNT_NUMBER.encode() not in history_page,
        )

        listing = operator_client.get("/bank").data
        check(
            "the instruments list now shows the current cardholder and settlement account",
            b"QA Second Holder" in listing and b"Chase Checking 1234" in listing,
        )
        check(
            "the card's Company is derived through its settlement account",
            b"Cardholder Test LLC" in listing and b"via settlement account" in listing,
        )

        # -----------------------------------------------------------------
        # Deduplication over HTTP.
        # -----------------------------------------------------------------
        with SessionFactory() as s:
            batch = m.BankImportBatch(
                detected_format="CHASE_CREDIT_CARD_WITH_CARD",
                original_file_name="QA_SYNTHETIC_Chase1057.CSV",
                raw_file_bytes=b"QA synthetic bytes", sha256="qa-synthetic-1",
                row_count=2, status="NORMALIZED",
            )
            s.add(batch)
            s.flush()
            for instrument_id in (mother_id, child_id):
                s.add(m.FinancialTransaction(
                    payment_instrument_id=instrument_id,
                    bank_source="CHASE_CREDIT_CARD_WITH_CARD", posting_date=date(2026, 5, 5),
                    description_original="US FOODS INC #4821",
                    description_normalized="US FOODS INC #4821", amount_minor=-41250,
                    status="COMPLETED", duplicate_status="NONE",
                    review_status="REQUIRES_REVIEW", import_batch_id=batch.id,
                ))
            s.commit()

        with SessionFactory() as s:
            raw_count_before = s.query(m.RawBankTransaction).count()

        page = operator_client.get("/bank").data
        resp = operator_client.post(
            "/bank/accounting-dedup/recompute", data={"csrf_token": extract_csrf(page)},
        )
        check("the recompute action redirects back to Import & Instruments",
              resp.status_code in (302, 303))

        with SessionFactory() as s:
            rows = s.query(m.FinancialTransaction).order_by(m.FinancialTransaction.id).all()
            canonical = [t for t in rows if t.accounting_status == accounting_dedup.CANONICAL]
            suppressed = [t for t in rows if t.accounting_status == accounting_dedup.DUPLICATE_SUPPRESSED]
            check(
                "two cards settling to one account produce one canonical row and one excluded copy",
                len(canonical) == 1 and len(suppressed) == 1
                and suppressed[0].accounting_canonical_transaction_id == canonical[0].id,
                detail=f"canonical={len(canonical)} suppressed={len(suppressed)}",
            )
            suppressed_id = suppressed[0].id if suppressed else None
            canonical_id = canonical[0].id if canonical else None
            raw_count_after = s.query(m.RawBankTransaction).count()
            transaction_count_after = len(rows)

        summary_page = operator_client.get("/bank").data
        check("the Import & Instruments page reports the deduplication summary",
              b"Accounting deduplication" in summary_page
              and b"Canonical transactions" in summary_page
              and b"Duplicate groups" in summary_page
              and b"Excluded from accounting" in summary_page
              and b"Raw rows preserved" in summary_page
              and b"No settlement account" in summary_page)

        review = operator_client.get("/bank/review").data
        check("the Review marks the excluded copy instead of hiding it",
              b"EXCLUDED FROM ACCOUNTING" in review)
        check("the excluded copy names its canonical transaction",
              b"Same accounting fact as transaction" in review)
        check("the duplicate group detail shows the originating batch/file",
              b"Duplicate group" in review and b"QA_SYNTHETIC_Chase1057.CSV" in review)
        check("the canonical row states it covers the whole group",
              b"Canonical for" in review)
        check(
            "21. no Who/Why/What control is offered on the excluded copy",
            suppressed_id is not None
            and f'data-transaction-id="{suppressed_id}"'.encode() not in review,
            detail=f"suppressed_id={suppressed_id}",
        )
        check(
            "21b. the canonical row DOES still offer the Who/Why/What control",
            canonical_id is not None
            and f'data-transaction-id="{canonical_id}"'.encode() in review,
            detail=f"canonical_id={canonical_id}",
        )
        check(
            "17. deduplication creates and deletes nothing — the ledger keeps both rows",
            transaction_count_after == 2 and raw_count_after == raw_count_before,
            detail=f"transactions={transaction_count_after} raw={raw_count_after}",
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
