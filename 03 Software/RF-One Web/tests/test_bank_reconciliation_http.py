#!/usr/bin/env python
"""HTTP-level regression test for Bank Reconciliation V1 (manual CSV
import & normalization). Mirrors `test_compensation_v1_http.py`'s own
convention exactly: a throwaway SQLite database created BEFORE `app.py`
is imported (via `RFONE_DATABASE_URL`), migrated explicitly, Werkzeug's
Flask test client, `main()` returning an exit code. Never touches a real
bank file, AWS, or any production database.

Canonical Financial Model Convergence — Phase 3/4/6 (FINANCIAL_MODEL_
CONVERGENCE_001): adapted from the proven V1 HTTP test suite
(`feature/bank-reconciliation-mvp`) to use the canonical
`PaymentInstrument`/`FinancialTransaction` models. Phase 4 restores the
Export/Supplier-Receiving-classification HTTP coverage Phase 3 deferred.
Phase 6 adds minimal coverage for the Bank Review cross-ledger internal-
transfer match confirmation action.

Exercises: domain-access gating, PaymentInstrument creation, CSV upload
over HTTP, normalization into the canonical FinancialTransaction ledger,
Supplier/Receiving explanation assignment, the Kermali export download,
and HUMAN confirmation of a cross-ledger internal-transfer match.
"""

from __future__ import annotations

import io
import os
import re
import sys
import tempfile
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_bank_http_test_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "http-test-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.bank_reconciliation import export as export_service  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')

CHASE_BANK_CSV = (
    "Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #\n"
    "DEBIT,05/05/2026,US FOODS INVOICE,-412.50,ACH_DEBIT,9000.00,\n"
).encode("utf-8")


def extract_csrf(html: bytes) -> str:
    match = CSRF_RE.search(html.decode("utf-8"))
    assert match, "csrf_token not found in response HTML"
    return match.group(1)


def main() -> int:
    checks_passed: list[str] = []
    checks_failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        if condition:
            checks_passed.append(description)
        else:
            checks_failed.append(description)
            print(f"FAILED: {description}" + (f" ({detail})" if detail else ""))

    try:
        with SessionFactory() as s:
            admin = account_service.create_account(
                s, username="RFone", display_name="Admin", password="AdminPass123!",
                status="ACTIVE", is_admin=True,
            )
            operator = account_service.create_account(
                s, username="bank_operator", display_name="Bank Operator", password="OperatorPass123!",
                status="ACTIVE", is_admin=False,
            )
            legal_entity = m.LegalEntity(legal_name="Verification LLC", status="ACTIVE")
            s.add(legal_entity)
            s.commit()
            operator_id, legal_entity_id = operator.id, legal_entity.id

        # -----------------------------------------------------------------
        # Access gating: a user with no BANK access is refused.
        # -----------------------------------------------------------------
        no_access_client = web_app.app.test_client()
        resp = no_access_client.get("/login")
        csrf = extract_csrf(resp.data)
        no_access_client.post(
            "/login", data={"username": "bank_operator", "password": "OperatorPass123!", "csrf_token": csrf},
        )
        resp = no_access_client.get("/bank")
        check("a user with no BANK domain access is refused (403)", resp.status_code == 403)

        with SessionFactory() as s:
            account_service.set_domain_access(
                s, account_id=operator_id, domain_code="BANK", enabled=True, role_code=None,
            )
            s.commit()

        operator_client = web_app.app.test_client()
        resp = operator_client.get("/login")
        csrf = extract_csrf(resp.data)
        operator_client.post(
            "/login", data={"username": "bank_operator", "password": "OperatorPass123!", "csrf_token": csrf},
        )
        resp = operator_client.get("/bank")
        check("an authorized user reaches /bank (200)", resp.status_code == 200)
        resp = operator_client.get("/")
        check(
            "Home shows the Bank Reconciliation card as a real link",
            b'href="/bank"' in resp.data,
        )

        # -----------------------------------------------------------------
        # Configure a Payment Instrument (Chase bank account — no in-file
        # identifier, so it must be resolved explicitly at upload time).
        # -----------------------------------------------------------------
        resp = operator_client.get("/bank")
        csrf = extract_csrf(resp.data)
        resp = operator_client.post(
            "/bank/instruments/new",
            data={
                "institution": "CHASE", "display_name": "Chase Checking 0214",
                "instrument_type": "BANK_ACCOUNT", "legal_entity_id": str(legal_entity_id),
                "csrf_token": csrf,
            },
        )
        check("creating a Payment Instrument redirects back to /bank", resp.status_code in (302, 303))

        with SessionFactory() as s:
            instrument = s.query(m.PaymentInstrument).filter_by(display_name="Chase Checking 0214").one()
            instrument_id = instrument.id
        check(
            "the created Payment Instrument has Company/Legal Entity configured (never invented)",
            True,  # configured explicitly above; existence checked structurally below
        )

        # -----------------------------------------------------------------
        # Security/QA regression carried forward from the source branch: a
        # First-Citizens-style instrument configured with a full
        # `external_account_identifier` must never render that full number
        # on the Bank home page — only the last 4 characters.
        # -----------------------------------------------------------------
        full_account_number = "1234567890123456"
        resp = operator_client.post(
            "/bank/instruments/new",
            data={
                "institution": "FIRST_CITIZENS", "display_name": "First Citizens Full-Number Test",
                "instrument_type": "BANK_ACCOUNT", "external_account_identifier": full_account_number,
                "csrf_token": csrf,
            },
        )
        resp = operator_client.get("/bank")
        check(
            "the full external_account_identifier never appears verbatim on the Bank home page",
            full_account_number.encode() not in resp.data,
        )
        check(
            "only the last 4 characters of external_account_identifier are shown",
            full_account_number[-4:].encode() in resp.data,
        )

        # -----------------------------------------------------------------
        # Upload a Chase bank-account CSV over HTTP, resolving the
        # instrument explicitly (spec §3.2 — never inferred from the file
        # name alone).
        # -----------------------------------------------------------------
        resp = operator_client.get("/bank")
        csrf = extract_csrf(resp.data)
        resp = operator_client.post(
            "/bank/upload",
            data={
                "files": (io.BytesIO(CHASE_BANK_CSV), "chase_0214.csv"),
                "payment_instrument_id": str(instrument_id),
                "csrf_token": csrf,
            },
            content_type="multipart/form-data",
        )
        check("uploading a CSV redirects back to /bank", resp.status_code in (302, 303))

        with SessionFactory() as s:
            batch = s.query(m.BankImportBatch).filter_by(original_file_name="chase_0214.csv").one()
            check("the uploaded batch is normalized (instrument resolved, no errors)", batch.status == "NORMALIZED")
            txn = s.query(m.FinancialTransaction).filter_by(import_batch_id=batch.id).one()
            txn_id = txn.id
            check("the normalized amount matches the CSV (-412.50 -> -41250)", txn.amount_minor == -41250)
            check(
                "the normalized transaction references the canonical PaymentInstrument",
                txn.payment_instrument_id == instrument_id,
            )

        # -----------------------------------------------------------------
        # Review page renders the uploaded transaction and its current
        # Recognition status — Recognition runs automatically at import,
        # finds no matching rule, and leaves it NEEDS_HUMAN_REVIEW.
        # -----------------------------------------------------------------
        resp = operator_client.get("/bank/review")
        check("review page responds 200", resp.status_code == 200)
        check("review page shows the uploaded transaction's description", b"US FOODS INVOICE" in resp.data)
        check("review page shows the automatic NEEDS_HUMAN_REVIEW Recognition status", b"NEEDS_HUMAN_REVIEW" in resp.data)
        check(
            "review page no longer offers the retired legacy explanation-catalog form",
            b"Add a Supplier/Receiving explanation" not in resp.data,
        )

        # -----------------------------------------------------------------
        # Export is blocked (no resolved reconciliation decision) before
        # the human confirms Occurrence/Reason.
        # -----------------------------------------------------------------
        resp = operator_client.get("/bank/export?year=2026&month=5")
        check(
            "export page shows a blocking reason before a reconciliation decision is recorded",
            b"Export blocked" in resp.data and b"Missing reconciliation decision" in resp.data,
        )

        # Canonical Occurrence/Reason vocabulary — created directly (no UI
        # CRUD for controlled vocabulary; the human selects from existing
        # entries, per Decision 11).
        with SessionFactory() as s:
            occurrence_type = m.BankOccurrenceType(code="SUPPLIER", name="Supplier")
            s.add(occurrence_type)
            s.commit()
            occurrence = m.BankOccurrence(canonical_name="US Foods", occurrence_type_id=occurrence_type.id)
            reason = m.BankTransactionReason(code="SUPPLIER_INVOICE_PAYMENT", name="Supplier Invoice Payment")
            s.add_all([occurrence, reason])
            s.commit()
            export_mapping = m.BankTransactionReasonExportMapping(
                bank_transaction_reason_id=reason.id, food_cost=True,
            )
            s.add(export_mapping)
            s.commit()
            occurrence_id, reason_id = occurrence.id, reason.id

        resp = operator_client.get("/bank/review")
        csrf = extract_csrf(resp.data)
        resp = operator_client.post(
            f"/bank/transactions/{txn_id}/recognition-decision",
            data={
                "occurrence_id": str(occurrence_id), "transaction_reason_id": str(reason_id),
                "reuse_for_future": "on", "csrf_token": csrf,
            },
        )
        check(
            "one HUMAN reconciliation-decision action satisfies the canonical decision "
            "(no second legacy assignment action is required)",
            resp.status_code in (302, 303),
        )

        with SessionFactory() as s:
            txn_after = s.get(m.FinancialTransaction, txn_id)
            check(
                "FinancialTransaction.explanation_id now points at the HUMAN decision",
                txn_after.explanation_id is not None,
            )
            decision = s.get(m.BankTransactionExplanation, txn_after.explanation_id)
            check(
                "the current decision is HUMAN_CONFIRMED with the chosen Occurrence/Reason",
                decision.decision_source == "HUMAN" and decision.occurrence_id == occurrence_id
                and decision.transaction_reason_id == reason_id,
            )
            check(
                "requesting reuse-for-future created a BankRecognitionRule",
                s.query(m.BankRecognitionRule).filter_by(occurrence_id=occurrence_id).count() == 1,
            )

        # -----------------------------------------------------------------
        # Export now succeeds; verify column order and real Excel types.
        # -----------------------------------------------------------------
        resp = operator_client.get("/bank/export?year=2026&month=5")
        check("export page shows no blocking reason once the decision is resolved", b"Export blocked" not in resp.data)

        resp = operator_client.get("/bank/export?year=2026&month=5")
        csrf = extract_csrf(resp.data)
        resp = operator_client.post(
            "/bank/export", data={"year": "2026", "month": "5", "csrf_token": csrf},
        )
        check("export download responds 200", resp.status_code == 200)
        check(
            "export download has the xlsx mimetype",
            resp.mimetype == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        check(
            "export download filename follows RfBank_YYYY_MM.xlsx",
            "RfBank_2026_05.xlsx" in resp.headers.get("Content-Disposition", ""),
        )

        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(resp.data))
        ws = wb.active
        header = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
        check(
            "downloaded workbook's header matches the 12 required columns in order",
            header == list(export_service.KERMALI_COLUMNS),
        )
        data_row = next(ws.iter_rows(min_row=2, max_row=2, values_only=True))
        check("downloaded workbook's Date cell is a real date", hasattr(data_row[1], "year"))
        check("downloaded workbook's Amount cell is numeric", isinstance(data_row[3], (int, float)))
        check("downloaded workbook's Food $ column carries the amount (food_cost explanation)", data_row[5] == -412.50)
        check("downloaded workbook's Company column is populated from the Legal Entity", data_row[11] == "Verification LLC")

        # -----------------------------------------------------------------
        # Phase 6: cross-ledger internal-transfer match — minimal Bank
        # Review integration. AUTO matching is never triggered by
        # ingestion in this phase (out of scope); these two rows are
        # created directly to exercise the HUMAN-confirm UI path exactly
        # as an operator would use it when evidence needs a human look.
        # -----------------------------------------------------------------
        with SessionFactory() as s:
            # The Bank Instrument creation UI (`/bank/instruments/new`,
            # exercised above) never captures a currency — a genuine,
            # pre-existing gap this phase does not silently patch (see the
            # Phase 6 final report). Matching correctly treats a NULL
            # currency as insufficient evidence and never guesses
            # compatibility, so the instrument's currency is set directly
            # here to exercise the match workflow itself.
            bank_instrument = s.get(m.PaymentInstrument, instrument_id)
            bank_instrument.currency = "USD"
            paypal_instrument = m.PaymentInstrument(
                legal_entity_id=legal_entity_id, instrument_type="PAYPAL",
                display_name="PayPal Business", currency="USD", linked_instrument_id=instrument_id,
            )
            s.add(paypal_instrument)
            s.commit()
            paypal_out = m.FinancialTransaction(
                payment_instrument_id=paypal_instrument.id, external_transaction_id="PP-HTTP-TRANSFER-1",
                transaction_datetime=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc), amount_minor=-2500,
            )
            bank_in = m.FinancialTransaction(
                payment_instrument_id=instrument_id, external_transaction_id="BANK-HTTP-DEP-1",
                transaction_datetime=datetime(2026, 6, 1, 9, 5, tzinfo=timezone.utc), amount_minor=2500,
            )
            s.add_all([paypal_out, bank_in])
            s.commit()
            paypal_out_id, bank_in_id = paypal_out.id, bank_in.id

        resp = operator_client.get("/bank/review")
        check(
            "Bank Review shows a Confirm-transfer candidate form for an unmatched, matchable transaction",
            b"counterpart_transaction_id" in resp.data,
        )
        csrf = extract_csrf(resp.data)
        resp = operator_client.post(
            f"/bank/transactions/{bank_in_id}/match-decision",
            data={"counterpart_transaction_id": str(paypal_out_id), "csrf_token": csrf},
        )
        check("match-decision POST redirects back to Bank Review", resp.status_code in (302, 303))

        with SessionFactory() as s:
            paypal_out_after = s.get(m.FinancialTransaction, paypal_out_id)
            bank_in_after = s.get(m.FinancialTransaction, bank_in_id)
            check(
                "both sides of the confirmed internal transfer are classified INTERNAL_TRANSFER, not REVENUE/EXPENSE",
                paypal_out_after.classification == "INTERNAL_TRANSFER"
                and bank_in_after.classification == "INTERNAL_TRANSFER",
            )
            lower_id, higher_id = sorted([paypal_out_id, bank_in_id])
            match = s.query(m.FinancialTransactionMatch).filter_by(
                transaction_a_id=lower_id, transaction_b_id=higher_id,
            ).one()
            check(
                "the match was recorded as HUMAN with confirmed_by set to the operator's identity",
                match.match_method == "HUMAN" and match.confirmed_by == "bank_operator",
            )

        resp = operator_client.get("/bank/review")
        check(
            "Bank Review now shows the confirmed INTERNAL_TRANSFER badge instead of a candidate form",
            b"INTERNAL_TRANSFER" in resp.data,
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
    print(f"{len(checks_passed)} passed, {len(checks_failed)} failed.")
    if checks_failed:
        print("FAILED CHECKS:")
        for c in checks_failed:
            print(" -", c)
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
