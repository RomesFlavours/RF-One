#!/usr/bin/env python
"""Tests for the PayPal Technical Connector
(`rfone_data_store/technical/connectors/paypal/`) — FINANCIAL_MODEL_
CONVERGENCE_001 Phase 5: parsing a raw PayPal Transaction Search
`transaction_details` entry (`parser.py`), mapping its status
(`mapping.py`), and idempotent ingestion into the canonical
`FinancialTransaction` ledger (`ingest.py`).

Ported/adapted from `feature/purchased-invoice-intake-alignment`'s
`test_paypal_connector.py`, retargeted from that branch's
`PaymentInstrumentTransaction` (not present on this branch) to canonical
`FinancialTransaction`. Adds coexistence checks (Phase 5 task §18) proving
a CSV-sourced and a PayPal-sourced `FinancialTransaction` share the same
canonical table without either requiring the other's provenance model.

No real PayPal credentials/network access are used or required — every
fixture here is a raw dict shaped like PayPal's own Transaction Search API
response (per PayPal's public API reference), fed directly into
`ingest_transaction_details()`. `client.py` (the actual HTTP/OAuth2 layer)
is not exercised by this suite.

Always targets its own disposable, self-provisioned SQLite database (never
`RFONE_DATABASE_URL`/the shared local `data/rfone.db`) — same convention as
the other Bank Reconciliation test scripts in this directory.

Usage:
    python test_paypal_connector.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from sqlalchemy import select

from rfone_data_store.database import (
    cleanup_disposable_test_database_url,
    create_configured_engine,
    create_disposable_test_database_url,
    create_session_factory,
)
from rfone_data_store import models as m
from rfone_data_store.technical.connectors.paypal import ingest, mapping, parser

UTC = timezone.utc


class Result:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[str] = []

    def check(self, description: str, condition: bool) -> None:
        (self.passed if condition else self.failed).append(description)


def _customer_payment_raw(transaction_id: str = "9XY123456A789012B") -> dict:
    """A PayPal "customer paid us" transaction: gross 100.00, fee -3.00,
    net 97.00."""
    return {
        "transaction_info": {
            "transaction_id": transaction_id,
            "transaction_event_code": "T0006",
            "transaction_initiation_date": "2026-08-01T10:15:00.000Z",
            "transaction_updated_date": "2026-08-01T10:15:05.000Z",
            "transaction_amount": {"currency_code": "USD", "value": "100.00"},
            "fee_amount": {"currency_code": "USD", "value": "-3.00"},
            "transaction_status": "S",
            "transaction_subject": "Invoice #123",
            "transaction_note": "Payment for services",
        },
        "payer_info": {
            "email_address": "customer@example.com",
            "payer_name": {"given_name": "Jane", "surname": "Doe"},
        },
    }


def _transfer_to_bank_raw(transaction_id: str = "TRANSFER0000000001") -> dict:
    """A PayPal "transfer to linked bank account" transaction (no fee)."""
    return {
        "transaction_info": {
            "transaction_id": transaction_id,
            "transaction_event_code": "T0400",
            "transaction_initiation_date": "2026-08-02T09:00:00.000Z",
            "transaction_amount": {"currency_code": "USD", "value": "-97.00"},
            "transaction_status": "S",
            "transaction_subject": "Withdraw to bank",
        },
        "payer_info": {},
    }


def main() -> int:
    url = create_disposable_test_database_url("paypal_connector")
    result = Result()
    try:
        engine = create_configured_engine(url)
        session_factory = create_session_factory(engine)
        with session_factory() as session:
            legal_entity = m.LegalEntity(legal_name="PayPal Connector Test LE", status="ACTIVE")
            session.add(legal_entity)
            session.flush()
            paypal_instrument = m.PaymentInstrument(
                legal_entity_id=legal_entity.id, instrument_type="PAYPAL",
                display_name="PayPal Business", currency="USD",
            )
            session.add(paypal_instrument)
            session.commit()

            # --- 1. Parsing (parser.py) ---
            parsed = parser.parse_transaction_detail(_customer_payment_raw())
            result.check("parsed transaction_id matches raw payload", parsed.transaction_id == "9XY123456A789012B")
            result.check("parsed gross_amount_minor == 10000 (100.00)", parsed.gross_amount_minor == 10000)
            result.check("parsed fee_amount_minor == -300 (-3.00)", parsed.fee_amount_minor == -300)
            result.check("parsed net_amount_minor == 9700 (gross + fee)", parsed.net_amount_minor == 9700)
            result.check("parsed currency == USD", parsed.currency == "USD")
            result.check(
                "parsed transaction_datetime preserves full precision (no truncation)",
                parsed.transaction_datetime == datetime(2026, 8, 1, 10, 15, 0, tzinfo=UTC),
            )
            result.check("parsed event_code preserved verbatim (T0006)", parsed.event_code == "T0006")
            result.check("parsed counterparty_name == 'Jane Doe'", parsed.counterparty_name == "Jane Doe")
            result.check(
                "parsed counterparty_identifier == payer email",
                parsed.counterparty_identifier == "customer@example.com",
            )
            result.check("mapping 'S' -> COMPLETED", mapping.to_canonical_status("S") == "COMPLETED")
            result.check("mapping unrecognized code -> UNKNOWN", mapping.to_canonical_status("Z9") == "UNKNOWN")

            # --- 2. PayPal transaction import -> canonical FinancialTransaction ---
            raw_details = [_customer_payment_raw(), _transfer_to_bank_raw()]
            run = ingest.ingest_transaction_details(
                session, payment_instrument_id=paypal_instrument.id, raw_transaction_details=raw_details,
            )
            session.commit()

            transactions = session.scalars(
                select(m.FinancialTransaction).where(
                    m.FinancialTransaction.payment_instrument_id == paypal_instrument.id
                )
            ).all()
            result.check("import created exactly 2 FinancialTransaction rows", len(transactions) == 2)

            customer_payment = session.scalars(
                select(m.FinancialTransaction).filter_by(external_transaction_id="9XY123456A789012B")
            ).first()
            result.check("customer payment row was created", customer_payment is not None)
            result.check(
                "customer payment amount_minor == net (9700)",
                customer_payment is not None and customer_payment.amount_minor == 9700,
            )
            result.check(
                "customer payment gross_amount_minor preserved (10000)",
                customer_payment is not None and customer_payment.gross_amount_minor == 10000,
            )
            result.check(
                "customer payment fee_amount_minor preserved (-300)",
                customer_payment is not None and customer_payment.fee_amount_minor == -300,
            )
            result.check(
                "customer payment net_amount_minor preserved (9700)",
                customer_payment is not None and customer_payment.net_amount_minor == 9700,
            )
            result.check(
                "customer payment status mapped to COMPLETED",
                customer_payment is not None and customer_payment.status == "COMPLETED",
            )
            result.check(
                "customer payment native_transaction_type preserves PayPal's own T-code",
                customer_payment is not None and customer_payment.native_transaction_type == "T0006",
            )
            result.check(
                "customer payment counterparty_name preserved",
                customer_payment is not None and customer_payment.counterparty_name == "Jane Doe",
            )
            result.check(
                "customer payment counterparty_identifier preserved",
                customer_payment is not None and customer_payment.counterparty_identifier == "customer@example.com",
            )
            result.check(
                "customer payment description_original carries PayPal's subject",
                customer_payment is not None and customer_payment.description_original == "Invoice #123",
            )
            result.check(
                "customer payment classification defaults to UNKNOWN (never guessed by the connector)",
                customer_payment is not None and customer_payment.classification == "UNKNOWN",
            )
            result.check(
                "customer payment linked to canonical PayPal PaymentInstrument",
                customer_payment is not None and customer_payment.payment_instrument_id == paypal_instrument.id,
            )
            result.check(
                "customer payment source_system_id preserved (PayPal SourceSystem)",
                customer_payment is not None and customer_payment.source_system is not None
                and customer_payment.source_system.code == "PAYPAL",
            )
            result.check(
                "customer payment import_batch_id is NULL (no BankImportBatch for PayPal)",
                customer_payment is not None and customer_payment.import_batch_id is None,
            )

            transfer = session.scalars(
                select(m.FinancialTransaction).filter_by(external_transaction_id="TRANSFER0000000001")
            ).first()
            result.check(
                "transfer-to-bank amount_minor == -9700 (outflow on PayPal's own ledger)",
                transfer is not None and transfer.amount_minor == -9700,
            )
            result.check(
                "transfer-to-bank related_external_transaction_id/currency-free: no currency field invented",
                not hasattr(m.FinancialTransaction, "currency"),
            )

            source_records = session.scalars(
                select(m.SourceRecord).where(m.SourceRecord.ingestion_run_id == run.id)
            ).all()
            result.check("one SourceRecord written per ingested transaction", len(source_records) == 2)
            result.check(
                "every SourceRecord carries a payload_hash (dedup/change-detection signal)",
                all(sr.payload_hash for sr in source_records),
            )
            result.check(
                "IngestionRun finished COMPLETE with lock_key released", run.status == "COMPLETE" and run.lock_key is None
            )
            result.check(
                "no RawBankTransaction created for PayPal ingestion",
                session.scalars(select(m.RawBankTransaction)).first() is None,
            )
            result.check(
                "no BankImportBatch created for PayPal ingestion",
                session.scalars(select(m.BankImportBatch)).first() is None,
            )
            result.check(
                "no PaymentInstrumentTransaction model exists on this branch (not reintroduced)",
                not hasattr(m, "PaymentInstrumentTransaction"),
            )

            # --- 3. Re-import of the same PayPal transaction does not duplicate it ---
            ingest.ingest_transaction_details(
                session, payment_instrument_id=paypal_instrument.id, raw_transaction_details=raw_details,
            )
            session.commit()
            transactions_after_reimport = session.scalars(
                select(m.FinancialTransaction).where(
                    m.FinancialTransaction.payment_instrument_id == paypal_instrument.id
                )
            ).all()
            result.check(
                "re-running the same import still yields exactly 2 rows (idempotent, no duplicates)",
                len(transactions_after_reimport) == 2,
            )

            # A changed re-import should UPDATE the existing row, not add a third one.
            updated_raw = _customer_payment_raw()
            updated_raw["transaction_info"]["transaction_status"] = "V"  # e.g. later reversed
            ingest.ingest_transaction_details(
                session, payment_instrument_id=paypal_instrument.id, raw_transaction_details=[updated_raw],
            )
            session.commit()
            still_two = session.scalars(
                select(m.FinancialTransaction).where(
                    m.FinancialTransaction.payment_instrument_id == paypal_instrument.id
                )
            ).all()
            result.check(
                "re-importing an UPDATED same-id transaction still yields 2 rows (upsert, not insert)",
                len(still_two) == 2,
            )
            refreshed = session.scalars(
                select(m.FinancialTransaction).filter_by(external_transaction_id="9XY123456A789012B")
            ).first()
            result.check(
                "the existing row's status was updated in place (REVERSED)",
                refreshed is not None and refreshed.status == "REVERSED",
            )

            # --- 4. Canonical CSV/PayPal coexistence (task §18) ---
            bank_instrument = m.PaymentInstrument(
                legal_entity_id=legal_entity.id, instrument_type="BANK_ACCOUNT",
                display_name="Chase Checking", currency="USD",
            )
            session.add(bank_instrument)
            session.flush()
            batch = m.BankImportBatch(
                detected_format="CHASE_BANK_ACCOUNT",
                payment_instrument_id=bank_instrument.id,
                original_file_name="statement.csv",
                raw_file_bytes=b"date,description,amount\n",
                sha256="0" * 64,
                row_count=1,
            )
            session.add(batch)
            session.flush()
            csv_txn = m.FinancialTransaction(
                payment_instrument_id=bank_instrument.id,
                bank_source="CHASE_BANK_ACCOUNT",
                posting_date=datetime(2026, 8, 1).date(),
                description_original="CSV sourced row",
                description_normalized="csv sourced row",
                amount_minor=-5000,
                import_batch_id=batch.id,
                source_row_number=1,
                status="COMPLETED",
            )
            session.add(csv_txn)
            raw_row = m.RawBankTransaction(
                import_batch_id=batch.id, row_number=1,
                raw_fields={"date": "2026-08-01", "description": "CSV sourced row", "amount": "-50.00"},
                row_fingerprint="fp-1", parse_status="PARSED",
            )
            session.add(raw_row)
            session.flush()
            raw_row.normalized_transaction_id = csv_txn.id
            session.commit()

            both_sources = session.scalars(
                select(m.FinancialTransaction).where(
                    m.FinancialTransaction.id.in_([csv_txn.id, customer_payment.id])
                )
            ).all()
            result.check(
                "CSV-sourced and PayPal-sourced FinancialTransaction rows coexist in the same table",
                len(both_sources) == 2,
            )
            result.check(
                "CSV transaction carries BankImportBatch/RawBankTransaction provenance",
                csv_txn.import_batch_id is not None
                and session.scalars(
                    select(m.RawBankTransaction).filter_by(normalized_transaction_id=csv_txn.id)
                ).first() is not None,
            )
            result.check(
                "PayPal transaction carries IngestionRun/SourceRecord provenance, no import_batch_id",
                customer_payment.import_batch_id is None
                and session.scalars(
                    select(m.SourceRecord).filter_by(source_id=customer_payment.external_transaction_id)
                ).first() is not None,
            )
            result.check(
                "CSV transaction has no SourceRecord (does not require PayPal's provenance model)",
                session.scalars(
                    select(m.SourceRecord).filter_by(source_id=str(csv_txn.source_row_number))
                ).first() is None,
            )
            result.check(
                "PayPal transaction has no RawBankTransaction (does not require CSV's provenance model)",
                session.scalars(
                    select(m.RawBankTransaction).filter_by(normalized_transaction_id=customer_payment.id)
                ).first() is None,
            )
    finally:
        cleanup_disposable_test_database_url(url)

    total = len(result.passed) + len(result.failed)
    if result.failed:
        print(f"FAILURE ({len(result.passed)}/{total} checks passed)")
        for description in result.failed:
            print(f"  FAILED: {description}")
        return 1
    print(f"SUCCESS ({len(result.passed)}/{total} checks passed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
