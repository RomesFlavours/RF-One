#!/usr/bin/env python
"""Canonical FinancialTransaction tests — Phase 2 only
(FINANCIAL_MODEL_CONVERGENCE_001).

Proves only the Phase 2 SCHEMA: that `FinancialTransaction` references
`PaymentInstrument`, that its signed `amount_minor` and gross/fee/net
breakdown store integer minor units, that all three date/time concepts
(`posting_date`/`transaction_date`/`transaction_datetime`) can coexist and
be independently nullable, that `classification`/`status` accept and
default to their approved values, that `(payment_instrument_id,
external_transaction_id)` uniqueness holds exactly as PayPal ingestion
requires, and that `duplicate_of_transaction_id` self-references this
canonical table.

Deliberately does NOT test CSV import, Recognition, PayPal ingestion, or
matching, and requires no legacy transaction table
(`NormalizedFinancialTransaction`/`PaymentInstrumentTransaction`) — neither
exists on this branch.

Always targets a disposable, self-cleaning SQLite database — never the
shared `RFONE_DATABASE_URL` / local `data/rfone.db`.

Usage:
    python test_financial_transaction.py
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timezone

from sqlalchemy.exc import IntegrityError

from rfone_data_store.database import (
    cleanup_disposable_test_database_url,
    create_configured_engine,
    create_session_factory,
    redact_database_url,
    resolve_test_database_url,
    run_migrations_to_head,
)
from rfone_data_store import models as m

UTC = timezone.utc


def main() -> int:
    url = resolve_test_database_url("financial_transaction")
    print(f"Database URL: {redact_database_url(url)}")

    run_migrations_to_head(url)

    engine = create_configured_engine(url)
    checks_passed: list[str] = []
    checks_failed: list[str] = []

    def check(description: str, condition: bool) -> None:
        (checks_passed if condition else checks_failed).append(description)

    try:
        session_factory = create_session_factory(engine)

        with session_factory() as session:
            legal_entity = m.LegalEntity(legal_name="FT Test Legal Entity", status="ACTIVE")
            session.add(legal_entity)
            session.flush()

            bank_account = m.PaymentInstrument(
                legal_entity_id=legal_entity.id,
                instrument_type="BANK_ACCOUNT",
                display_name="FT Test Bank Account",
                institution="CHASE",
            )
            paypal_instrument = m.PaymentInstrument(
                legal_entity_id=legal_entity.id,
                instrument_type="PAYPAL",
                display_name="FT Test PayPal Account",
            )
            session.add_all([bank_account, paypal_instrument])
            session.flush()

            # --- 1. References PaymentInstrument; 2. signed amount_minor ------
            csv_txn = m.FinancialTransaction(
                payment_instrument_id=bank_account.id,
                bank_source="CHASE",
                amount_minor=-12345,
                status="COMPLETED",
            )
            session.add(csv_txn)
            session.commit()

            reloaded_csv_txn = session.get(m.FinancialTransaction, csv_txn.id)
            check(
                "FinancialTransaction can reference PaymentInstrument",
                reloaded_csv_txn.payment_instrument_id == bank_account.id
                and reloaded_csv_txn.payment_instrument.display_name == "FT Test Bank Account",
            )
            check("amount_minor stores signed integer monetary values", reloaded_csv_txn.amount_minor == -12345)

            # --- 3-7. Three independent date/time concepts --------------------
            posting_only = m.FinancialTransaction(
                payment_instrument_id=bank_account.id,
                amount_minor=-500,
                posting_date=date(2026, 7, 1),
                transaction_date=date(2026, 6, 30),
            )
            session.add(posting_only)
            session.commit()
            reloaded_posting_only = session.get(m.FinancialTransaction, posting_only.id)
            check("posting_date can be stored independently", reloaded_posting_only.posting_date == date(2026, 7, 1))
            check(
                "transaction_date can be stored independently",
                reloaded_posting_only.transaction_date == date(2026, 6, 30),
            )

            api_precise_ts = datetime(2026, 7, 1, 14, 30, 5, tzinfo=UTC)
            api_style = m.FinancialTransaction(
                payment_instrument_id=paypal_instrument.id,
                amount_minor=-999,
                transaction_datetime=api_precise_ts,
                external_transaction_id="PAYPAL-TXN-001",
            )
            session.add(api_style)
            session.commit()
            reloaded_api_style = session.get(m.FinancialTransaction, api_style.id)
            check(
                "transaction_datetime preserves timestamp precision",
                reloaded_api_style.transaction_datetime == api_precise_ts,
            )
            check(
                "posting_date may be NULL for API-style transactions",
                reloaded_api_style.posting_date is None,
            )

            all_three = m.FinancialTransaction(
                payment_instrument_id=bank_account.id,
                amount_minor=-42,
                posting_date=date(2026, 7, 2),
                transaction_date=date(2026, 7, 1),
                transaction_datetime=datetime(2026, 7, 1, 9, 0, 0, tzinfo=UTC),
            )
            session.add(all_three)
            session.commit()
            reloaded_all_three = session.get(m.FinancialTransaction, all_three.id)
            check(
                "all three date/time fields can coexist on one transaction",
                reloaded_all_three.posting_date == date(2026, 7, 2)
                and reloaded_all_three.transaction_date == date(2026, 7, 1)
                and reloaded_all_three.transaction_datetime == datetime(2026, 7, 1, 9, 0, 0, tzinfo=UTC),
            )

            # --- 8-9. classification -------------------------------------------
            check("classification defaults to UNKNOWN", reloaded_csv_txn.classification == "UNKNOWN")
            classified = m.FinancialTransaction(
                payment_instrument_id=bank_account.id, amount_minor=-1, classification="INTERNAL_TRANSFER",
            )
            session.add(classified)
            session.commit()
            check(
                "classification accepts the approved values",
                session.get(m.FinancialTransaction, classified.id).classification == "INTERNAL_TRANSFER",
            )

            # --- 10. status -----------------------------------------------------
            check("status accepts the approved values", reloaded_csv_txn.status == "COMPLETED")

            # --- 11. external_transaction_id -------------------------------------
            check(
                "external_transaction_id can be stored",
                reloaded_api_style.external_transaction_id == "PAYPAL-TXN-001",
            )

            # --- 14. gross/fee/net integer minor units -----------------------
            breakdown = m.FinancialTransaction(
                payment_instrument_id=paypal_instrument.id,
                amount_minor=950,
                gross_amount_minor=1000,
                fee_amount_minor=50,
                net_amount_minor=950,
                external_transaction_id="PAYPAL-TXN-002",
            )
            session.add(breakdown)
            session.commit()
            reloaded_breakdown = session.get(m.FinancialTransaction, breakdown.id)
            check(
                "gross/fee/net fields store integer minor units",
                reloaded_breakdown.gross_amount_minor == 1000
                and reloaded_breakdown.fee_amount_minor == 50
                and reloaded_breakdown.net_amount_minor == 950,
            )

            # --- 15. duplicate_of_transaction_id self-reference -----------------
            duplicate = m.FinancialTransaction(
                payment_instrument_id=bank_account.id,
                amount_minor=-12345,
                duplicate_status="CANDIDATE_DUPLICATE",
                duplicate_of_transaction_id=csv_txn.id,
            )
            session.add(duplicate)
            session.commit()
            reloaded_duplicate = session.get(m.FinancialTransaction, duplicate.id)
            check(
                "duplicate_of_transaction_id can self-reference another canonical FinancialTransaction",
                reloaded_duplicate.duplicate_of_transaction_id == csv_txn.id
                and reloaded_duplicate.duplicate_of.id == csv_txn.id,
            )

        # --- 12. duplicate external_transaction_id for same instrument rejected --
        with session_factory() as session:
            legal_entity = m.LegalEntity(legal_name="FT Uniqueness Test Entity", status="ACTIVE")
            session.add(legal_entity)
            session.flush()

            instrument_a = m.PaymentInstrument(
                legal_entity_id=legal_entity.id, instrument_type="PAYPAL", display_name="Uniqueness Instrument A",
            )
            instrument_b = m.PaymentInstrument(
                legal_entity_id=legal_entity.id, instrument_type="PAYPAL", display_name="Uniqueness Instrument B",
            )
            session.add_all([instrument_a, instrument_b])
            session.flush()

            first = m.FinancialTransaction(
                payment_instrument_id=instrument_a.id, amount_minor=-1, external_transaction_id="DUP-001",
            )
            session.add(first)
            session.commit()

            duplicate_same_instrument = m.FinancialTransaction(
                payment_instrument_id=instrument_a.id, amount_minor=-2, external_transaction_id="DUP-001",
            )
            session.add(duplicate_same_instrument)
            rejected = False
            try:
                session.commit()
            except IntegrityError:
                rejected = True
                session.rollback()
            check(
                "duplicate external_transaction_id for the same PaymentInstrument is rejected when non-null",
                rejected,
            )

            # --- 13. same external_transaction_id, different instrument allowed --
            same_id_other_instrument = m.FinancialTransaction(
                payment_instrument_id=instrument_b.id, amount_minor=-3, external_transaction_id="DUP-001",
            )
            session.add(same_id_other_instrument)
            allowed = True
            try:
                session.commit()
            except IntegrityError:
                allowed = False
                session.rollback()
            check(
                "the same external_transaction_id may belong to a different PaymentInstrument",
                allowed,
            )

            # Multiple NULL external_transaction_id rows on the same instrument
            # must never conflict with each other (standard SQL/SQLite unique
            # semantics) — confirms the uniqueness rule only applies when
            # external_transaction_id is actually present.
            null_a = m.FinancialTransaction(payment_instrument_id=instrument_a.id, amount_minor=-4)
            null_b = m.FinancialTransaction(payment_instrument_id=instrument_a.id, amount_minor=-5)
            session.add_all([null_a, null_b])
            both_null_allowed = True
            try:
                session.commit()
            except IntegrityError:
                both_null_allowed = False
                session.rollback()
            check(
                "multiple NULL external_transaction_id rows on the same instrument do not conflict",
                both_null_allowed,
            )

        # --- 16. no legacy transaction table required for these tests -----------
        check(
            "no legacy transaction table is required for these tests",
            not hasattr(m, "NormalizedFinancialTransaction") and not hasattr(m, "PaymentInstrumentTransaction"),
        )

    finally:
        engine.dispose()
        cleanup_disposable_test_database_url(url)

    if not checks_failed:
        print(
            f"FinancialTransaction Phase 2 tests: SUCCESS ({len(checks_passed)}/{len(checks_passed)} checks passed)"
        )
        return 0

    print(
        f"FinancialTransaction Phase 2 tests: FAILURE "
        f"({len(checks_passed)} passed, {len(checks_failed)} failed)"
    )
    for description in checks_failed:
        print(f"  FAILED: {description}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
