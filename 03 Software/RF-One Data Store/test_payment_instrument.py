#!/usr/bin/env python
"""Canonical PaymentInstrument tests — Phase 1 only
(FINANCIAL_MODEL_CONVERGENCE_001).

Proves only the Phase 1 model: that `PaymentInstrument` supports all three
approved `instrument_type` values, that the fields absorbed from the
earlier `FinancialAccount` model (`institution`/`last_four`/
`external_account_identifier`) can be stored, and that its existing
`legal_entity_id`/`linked_instrument_id`/`source_system_id`/`status`
relationships and constraints behave as designed.

Deliberately does NOT test transactions, PayPal ingestion, CSV
reconciliation, Recognition, or matching — those belong to later,
not-yet-authorized phases.

Always targets a disposable, self-cleaning SQLite database — never the
shared `RFONE_DATABASE_URL` / local `data/rfone.db`.

Usage:
    python test_payment_instrument.py
"""

from __future__ import annotations

import sys

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


def main() -> int:
    url = resolve_test_database_url("payment_instrument")
    print(f"Database URL: {redact_database_url(url)}")

    run_migrations_to_head(url)

    engine = create_configured_engine(url)
    checks_passed: list[str] = []
    checks_failed: list[str] = []

    def check(description: str, condition: bool) -> None:
        (checks_passed if condition else checks_failed).append(description)

    try:
        session_factory = create_session_factory(engine)

        # --- 1-3. All three approved instrument_type values -----------------
        with session_factory() as session:
            legal_entity = m.LegalEntity(legal_name="Test Legal Entity", status="ACTIVE")
            session.add(legal_entity)
            session.flush()

            source_system = m.SourceSystem(code="PAYPAL", name="PayPal", active=True)
            session.add(source_system)
            session.flush()

            bank_account = m.PaymentInstrument(
                legal_entity_id=legal_entity.id,
                instrument_type="BANK_ACCOUNT",
                display_name="Test Chase Checking",
                institution="CHASE",
                last_four="1234",
                external_account_identifier="000111222333",
            )
            credit_card = m.PaymentInstrument(
                legal_entity_id=legal_entity.id,
                instrument_type="CREDIT_CARD",
                display_name="Test Chase Credit Card",
                institution="CHASE",
                last_four="5678",
            )
            paypal = m.PaymentInstrument(
                legal_entity_id=legal_entity.id,
                instrument_type="PAYPAL",
                display_name="Test PayPal Account",
                provider="PayPal",
                source_system_id=source_system.id,
                linked_instrument_id=None,
            )
            session.add_all([bank_account, credit_card, paypal])
            session.commit()

            check("PaymentInstrument supports BANK_ACCOUNT", bank_account.instrument_type == "BANK_ACCOUNT")
            check("PaymentInstrument supports CREDIT_CARD", credit_card.instrument_type == "CREDIT_CARD")
            check("PaymentInstrument supports PAYPAL", paypal.instrument_type == "PAYPAL")

            # --- 4-6. Absorbed FinancialAccount fields -----------------------
            reloaded_bank_account = session.get(m.PaymentInstrument, bank_account.id)
            check("institution can be stored", reloaded_bank_account.institution == "CHASE")
            check("last_four can be stored", reloaded_bank_account.last_four == "1234")
            check(
                "external_account_identifier can be stored",
                reloaded_bank_account.external_account_identifier == "000111222333",
            )

            # --- 7. legal_entity_id behavior ---------------------------------
            check(
                "legal_entity_id behavior remains intact",
                reloaded_bank_account.legal_entity_id == legal_entity.id
                and reloaded_bank_account.legal_entity.legal_name == "Test Legal Entity",
            )

            # --- 9. source_system_id behavior --------------------------------
            reloaded_paypal = session.get(m.PaymentInstrument, paypal.id)
            check(
                "source_system_id behavior remains intact",
                reloaded_paypal.source_system_id == source_system.id
                and reloaded_paypal.source_system.code == "PAYPAL",
            )

            # --- 10. status behavior ------------------------------------------
            check("status defaults to ACTIVE", reloaded_bank_account.status == "ACTIVE")
            reloaded_bank_account.status = "INACTIVE"
            session.commit()
            check(
                "status can transition to INACTIVE",
                session.get(m.PaymentInstrument, bank_account.id).status == "INACTIVE",
            )

        # --- 8. linked_instrument_id behavior (self-referential FK) -----------
        with session_factory() as session:
            legal_entity = m.LegalEntity(legal_name="Linked Instrument Test Entity", status="ACTIVE")
            session.add(legal_entity)
            session.flush()

            bank_account = m.PaymentInstrument(
                legal_entity_id=legal_entity.id,
                instrument_type="BANK_ACCOUNT",
                display_name="Settlement Bank Account",
            )
            session.add(bank_account)
            session.flush()

            paypal = m.PaymentInstrument(
                legal_entity_id=legal_entity.id,
                instrument_type="PAYPAL",
                display_name="Linked PayPal Account",
                linked_instrument_id=bank_account.id,
            )
            session.add(paypal)
            session.commit()

            reloaded_paypal = session.get(m.PaymentInstrument, paypal.id)
            check(
                "linked_instrument_id behavior remains intact",
                reloaded_paypal.linked_instrument_id == bank_account.id
                and reloaded_paypal.linked_instrument.display_name == "Settlement Bank Account",
            )

        # --- instrument_type CHECK constraint (no speculative types) ----------
        with session_factory() as session:
            legal_entity = m.LegalEntity(legal_name="Constraint Test Entity", status="ACTIVE")
            session.add(legal_entity)
            session.flush()
            invalid = m.PaymentInstrument(
                legal_entity_id=legal_entity.id,
                instrument_type="CRYPTO_WALLET",
                display_name="Should be rejected",
            )
            session.add(invalid)
            rejected = False
            try:
                session.commit()
            except IntegrityError:
                rejected = True
                session.rollback()
            check("instrument_type rejects an unapproved value (no speculative types)", rejected)

    finally:
        engine.dispose()
        cleanup_disposable_test_database_url(url)

    if not checks_failed:
        print(f"PaymentInstrument Phase 1 tests: SUCCESS ({len(checks_passed)}/{len(checks_passed)} checks passed)")
        return 0

    print(
        f"PaymentInstrument Phase 1 tests: FAILURE "
        f"({len(checks_passed)} passed, {len(checks_failed)} failed)"
    )
    for description in checks_failed:
        print(f"  FAILED: {description}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
