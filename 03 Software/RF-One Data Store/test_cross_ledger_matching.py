#!/usr/bin/env python
"""Tests for the canonical cross-ledger internal-transfer matching engine
(`rfone_data_store/bank_reconciliation/matching.py`) — FINANCIAL_MODEL_
CONVERGENCE_001 Phase 6: matching two `FinancialTransaction` rows on
different `PaymentInstrument`s that represent the two sides of the same
internal transfer, classifying a matched pair as `INTERNAL_TRANSFER`
(never revenue/expense), preserving a PayPal fee as a distinct, un-merged
fact, and refusing to auto-match ambiguous/insufficient evidence.

Ported/adapted from `feature/purchased-invoice-intake-alignment`'s
`test_bank_reconciliation.py`, retargeted from that branch's
`PaymentInstrumentTransaction` to canonical `FinancialTransaction`. Adds
explicit coverage this Phase 6 task requires beyond the source suite:
incompatible currency, outside-date-tolerance, same-sign non-match,
reversed-pair duplicate protection, and mixed date/time-precision matching
(a PayPal row with only `transaction_datetime` against a CSV-style row with
only `posting_date`).

`FinancialTransaction` rows are created directly here (not through the
PayPal connector or CSV normalization), to isolate matching logic from
parsing logic — see `test_paypal_connector.py` for the connector tests and
`test_bank_reconciliation_service.py` for CSV normalization.

Always targets its own disposable, self-provisioned SQLite database (never
`RFONE_DATABASE_URL`/the shared local `data/rfone.db`).

Usage:
    python test_cross_ledger_matching.py
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone

from rfone_data_store.database import (
    cleanup_disposable_test_database_url,
    create_configured_engine,
    create_disposable_test_database_url,
    create_session_factory,
)
from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import matching

UTC = timezone.utc


class Result:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[str] = []

    def check(self, description: str, condition: bool) -> None:
        (self.passed if condition else self.failed).append(description)


def _txn(
    session, *, instrument_id: int, external_id: str, amount_minor: int,
    classification: str = "UNKNOWN",
    transaction_datetime: datetime | None = None,
    posting_date: date | None = None,
    transaction_date: date | None = None,
    **extra,
) -> m.FinancialTransaction:
    txn = m.FinancialTransaction(
        payment_instrument_id=instrument_id,
        external_transaction_id=external_id,
        transaction_datetime=transaction_datetime,
        posting_date=posting_date,
        transaction_date=transaction_date,
        amount_minor=amount_minor,
        classification=classification,
        **extra,
    )
    session.add(txn)
    session.flush()
    return txn


def main() -> int:
    url = create_disposable_test_database_url("cross_ledger_matching")
    result = Result()
    try:
        engine = create_configured_engine(url)
        session_factory = create_session_factory(engine)
        with session_factory() as session:
            legal_entity = m.LegalEntity(legal_name="Cross-Ledger Matching Test LE", status="ACTIVE")
            session.add(legal_entity)
            session.flush()

            bank = m.PaymentInstrument(
                legal_entity_id=legal_entity.id, instrument_type="BANK_ACCOUNT",
                display_name="Operating Checking", currency="USD",
            )
            session.add(bank)
            session.flush()

            paypal = m.PaymentInstrument(
                legal_entity_id=legal_entity.id, instrument_type="PAYPAL",
                display_name="PayPal Business", currency="USD", linked_instrument_id=bank.id,
            )
            credit_card = m.PaymentInstrument(
                legal_entity_id=legal_entity.id, instrument_type="CREDIT_CARD",
                display_name="Business Amex", currency="USD", linked_instrument_id=bank.id,
            )
            unlinked_paypal = m.PaymentInstrument(
                legal_entity_id=legal_entity.id, instrument_type="PAYPAL",
                display_name="Unlinked PayPal (no configured settlement account)", currency="USD",
            )
            eur_card = m.PaymentInstrument(
                legal_entity_id=legal_entity.id, instrument_type="CREDIT_CARD",
                display_name="EUR Card", currency="EUR", linked_instrument_id=bank.id,
            )
            session.add_all([paypal, credit_card, unlinked_paypal, eur_card])
            session.commit()

            day1 = datetime(2026, 8, 2, 9, 0, tzinfo=UTC)
            day1_plus5 = day1 + timedelta(minutes=5)

            # --- §21: PayPal -> Bank transfer matching (task §21) ---
            paypal_transfer_out = _txn(
                session, instrument_id=paypal.id, external_id="PP-TRANSFER-1",
                transaction_datetime=day1, amount_minor=-1250,
            )
            bank_deposit = _txn(
                session, instrument_id=bank.id, external_id="BANK-DEP-1",
                transaction_datetime=day1_plus5, amount_minor=1250,
            )
            session.commit()

            match_a = matching.auto_match_transaction(session, paypal_transfer_out)
            session.commit()
            result.check("PayPal transfer <-> Bank deposit auto-matches (§21.5)", match_a is not None)
            result.check("auto match method is AUTO", match_a is not None and match_a.match_method == "AUTO")
            result.check("matched_amount_minor == 1250", match_a is not None and match_a.matched_amount_minor == 1250)
            result.check(
                "both original transactions remain present (§21.7)",
                session.get(m.FinancialTransaction, paypal_transfer_out.id) is not None
                and session.get(m.FinancialTransaction, bank_deposit.id) is not None,
            )
            session.refresh(paypal_transfer_out)
            session.refresh(bank_deposit)
            result.check(
                "PayPal transfer classified INTERNAL_TRANSFER (§21.6)",
                paypal_transfer_out.classification == "INTERNAL_TRANSFER",
            )
            result.check(
                "Bank deposit classified INTERNAL_TRANSFER (§21.6)",
                bank_deposit.classification == "INTERNAL_TRANSFER",
            )
            result.check(
                "PayPal side external_transaction_id/provenance fields untouched (§21.8)",
                paypal_transfer_out.external_transaction_id == "PP-TRANSFER-1"
                and paypal_transfer_out.payment_instrument_id == paypal.id,
            )
            result.check(
                "Bank side external_transaction_id/provenance fields untouched (§21.9)",
                bank_deposit.external_transaction_id == "BANK-DEP-1"
                and bank_deposit.payment_instrument_id == bank.id,
            )

            # Idempotent re-match: same pair, no duplicate match row.
            match_a_again = matching.auto_match_transaction(session, paypal_transfer_out)
            result.check(
                "re-attempting an already-matched transaction returns None (already matched)",
                match_a_again is None,
            )

            # --- §22: Bank -> Credit Card payment matching ---
            day2 = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)
            cc_payment_received = _txn(
                session, instrument_id=credit_card.id, external_id="CC-PMT-1",
                transaction_datetime=day2, amount_minor=4000,
            )
            bank_cc_payment = _txn(
                session, instrument_id=bank.id, external_id="BANK-CC-PMT-1",
                transaction_datetime=day2, amount_minor=-4000,
            )
            session.commit()

            match_b = matching.auto_match_transaction(session, bank_cc_payment)
            session.commit()
            result.check("Bank -> Credit Card payment auto-matches (§22.5)", match_b is not None)
            session.refresh(cc_payment_received)
            session.refresh(bank_cc_payment)
            result.check(
                "Credit Card side classified INTERNAL_TRANSFER, not REVENUE/EXPENSE (§22.6)",
                cc_payment_received.classification == "INTERNAL_TRANSFER"
                and cc_payment_received.classification not in ("REVENUE", "EXPENSE"),
            )
            result.check(
                "Bank side classified INTERNAL_TRANSFER, not REVENUE/EXPENSE (§22.7)",
                bank_cc_payment.classification == "INTERNAL_TRANSFER"
                and bank_cc_payment.classification not in ("REVENUE", "EXPENSE"),
            )
            result.check(
                "Bank<->Credit Card matching required no PayPal instrument at all (generic foundation works)",
                paypal.id not in (cc_payment_received.payment_instrument_id, bank_cc_payment.payment_instrument_id),
            )

            # --- §24: PayPal fee remains separate from the settlement ---
            day3 = datetime(2026, 8, 10, 8, 0, tzinfo=UTC)
            customer_payment = _txn(
                session, instrument_id=paypal.id, external_id="PP-CUSTPMT-1",
                transaction_datetime=day3, amount_minor=9700,
                gross_amount_minor=10000, fee_amount_minor=-300, net_amount_minor=9700,
            )
            paypal_settlement_out = _txn(
                session, instrument_id=paypal.id, external_id="PP-SETTLE-1",
                transaction_datetime=day3 + timedelta(days=1), amount_minor=-9700,
            )
            bank_settlement_in = _txn(
                session, instrument_id=bank.id, external_id="BANK-SETTLE-1",
                transaction_datetime=day3 + timedelta(days=1), amount_minor=9700,
            )
            session.commit()

            settlement_match = matching.auto_match_transaction(session, paypal_settlement_out)
            session.commit()
            result.check("PayPal settlement <-> Bank deposit auto-matches (§24)", settlement_match is not None)
            result.check(
                "settlement match amount is 97.00 (9700), not the 100.00 gross (§24: fee not absorbed)",
                settlement_match is not None and settlement_match.matched_amount_minor == 9700,
            )

            session.refresh(customer_payment)
            result.check(
                "the ORIGINAL customer payment (with its fee) is untouched by the settlement match (§24)",
                customer_payment.classification == "UNKNOWN" and not matching.is_matched(session, customer_payment.id),
            )
            result.check(
                "the $3.00 PayPal fee is still present on the customer payment row, never absorbed (§24)",
                customer_payment.fee_amount_minor == -300 and customer_payment.gross_amount_minor == 10000
                and customer_payment.net_amount_minor == 9700,
            )

            # --- §23.1: equal amount but unrelated (unlinked) instrument -> NO AUTO MATCH ---
            day4 = datetime(2026, 8, 15, 10, 0, tzinfo=UTC)
            unlinked_out = _txn(
                session, instrument_id=unlinked_paypal.id, external_id="UNLINKED-1",
                transaction_datetime=day4, amount_minor=-5000,
            )
            coincidental_bank_in = _txn(
                session, instrument_id=bank.id, external_id="COINCIDENCE-1",
                transaction_datetime=day4, amount_minor=5000,
            )
            session.commit()
            no_match = matching.auto_match_transaction(session, unlinked_out)
            result.check(
                "equal-and-opposite amounts on an UNLINKED instrument pair do NOT auto-match (§23.1)",
                no_match is None,
            )
            result.check(
                "the unlinked candidate transaction remains unresolved (no false match)",
                not matching.is_matched(session, unlinked_out.id)
                and not matching.is_matched(session, coincidental_bank_in.id),
            )

            # --- §23.2: equal amount, linked instruments, SAME sign -> NO MATCH ---
            day4b = datetime(2026, 8, 16, 10, 0, tzinfo=UTC)
            same_sign_paypal = _txn(
                session, instrument_id=paypal.id, external_id="SAMESIGN-PP-1",
                transaction_datetime=day4b, amount_minor=-3000,
            )
            same_sign_bank = _txn(
                session, instrument_id=bank.id, external_id="SAMESIGN-BANK-1",
                transaction_datetime=day4b, amount_minor=-3000,
            )
            session.commit()
            same_sign_match = matching.auto_match_transaction(session, same_sign_paypal)
            result.check(
                "equal amount, linked instruments, SAME sign -> no match (§23.2)",
                same_sign_match is None,
            )

            # --- §23.3: incompatible currency -> NO AUTO MATCH ---
            day4c = datetime(2026, 8, 17, 10, 0, tzinfo=UTC)
            eur_charge = _txn(
                session, instrument_id=eur_card.id, external_id="EUR-CHG-1",
                transaction_datetime=day4c, amount_minor=2000,
            )
            usd_bank_payment = _txn(
                session, instrument_id=bank.id, external_id="USD-BANK-PMT-1",
                transaction_datetime=day4c, amount_minor=-2000,
            )
            session.commit()
            currency_mismatch_match = matching.auto_match_transaction(session, usd_bank_payment)
            result.check(
                "incompatible currency (USD bank vs EUR card) -> no auto match (§23.3)",
                currency_mismatch_match is None,
            )

            # --- §23.4: outside date tolerance -> NO AUTO MATCH ---
            day5a = datetime(2026, 8, 20, 10, 0, tzinfo=UTC)
            day5b = day5a + timedelta(days=10)  # well outside the 3-day tolerance
            stale_paypal_out = _txn(
                session, instrument_id=paypal.id, external_id="STALE-PP-1",
                transaction_datetime=day5a, amount_minor=-1500,
            )
            late_bank_in = _txn(
                session, instrument_id=bank.id, external_id="LATE-BANK-1",
                transaction_datetime=day5b, amount_minor=1500,
            )
            session.commit()
            stale_match = matching.auto_match_transaction(session, stale_paypal_out)
            result.check(
                "outside the date tolerance window -> no auto match (§23.4)",
                stale_match is None,
            )

            # --- §23.5 / §25: ambiguous candidates -> NO AUTO MATCH, HUMAN resolves ---
            day6 = datetime(2026, 8, 25, 10, 0, tzinfo=UTC)
            ambiguous_paypal_1 = _txn(
                session, instrument_id=paypal.id, external_id="AMBIG-PP-1",
                transaction_datetime=day6, amount_minor=-5000,
            )
            ambiguous_paypal_2 = _txn(
                session, instrument_id=paypal.id, external_id="AMBIG-PP-2",
                transaction_datetime=day6, amount_minor=-5000,
            )
            ambiguous_bank = _txn(
                session, instrument_id=bank.id, external_id="AMBIG-BANK-1",
                transaction_datetime=day6, amount_minor=5000,
            )
            session.commit()
            ambiguous_match = matching.auto_match_transaction(session, ambiguous_bank)
            result.check(
                "two equally-valid linked candidates (genuine ambiguity) do NOT auto-match (§23.5)",
                ambiguous_match is None,
            )
            result.check(
                "ambiguous candidate not classified INTERNAL_TRANSFER before confirmation (§25.1)",
                ambiguous_paypal_1.classification == "UNKNOWN" and ambiguous_paypal_2.classification == "UNKNOWN",
            )

            human_match = matching.confirm_match(
                session, ambiguous_bank.id, ambiguous_paypal_1.id, confirmed_by="reviewer@example.com",
                note="Confirmed against PayPal dashboard - AMBIG-PP-2 is a different, still-pending transfer.",
            )
            session.commit()
            result.check("HUMAN can explicitly confirm a valid pair (§25.2)", human_match is not None)
            result.check("human-confirmed match_method is HUMAN (§25.3)", human_match.match_method == "HUMAN")
            result.check(
                "confirmed_by is preserved (§25.4)", human_match.confirmed_by == "reviewer@example.com",
            )
            session.refresh(ambiguous_paypal_1)
            session.refresh(ambiguous_bank)
            result.check(
                "only after confirmation do both transactions become INTERNAL_TRANSFER (§25.5)",
                ambiguous_paypal_1.classification == "INTERNAL_TRANSFER"
                and ambiguous_bank.classification == "INTERNAL_TRANSFER",
            )
            result.check(
                "the OTHER ambiguous candidate remains unresolved (not swept into the human's match)",
                not matching.is_matched(session, ambiguous_paypal_2.id),
            )

            # --- §23.6 / §23.7: duplicate / reversed-pair protection ---
            duplicate_attempt = matching.create_match(
                session, ambiguous_bank, ambiguous_paypal_1, match_method="HUMAN", match_basis="duplicate attempt",
            )
            result.check(
                "same pair (A,B) cannot be inserted twice - returns the existing row (§23.6)",
                duplicate_attempt.id == human_match.id,
            )
            reversed_attempt = matching.create_match(
                session, ambiguous_paypal_1, ambiguous_bank, match_method="HUMAN", match_basis="reversed attempt",
            )
            result.check(
                "reversed pair (B,A) cannot be inserted as a duplicate - returns the same existing row (§23.7)",
                reversed_attempt.id == human_match.id,
            )
            session.commit()

            # --- §8: mixed date/time precision - PayPal (transaction_datetime only)
            # vs CSV-style Bank row (posting_date only, no transaction_datetime) ---
            day7 = datetime(2026, 9, 1, 14, 30, tzinfo=UTC)
            precise_paypal_out = _txn(
                session, instrument_id=paypal.id, external_id="PRECISE-PP-1",
                transaction_datetime=day7, amount_minor=-8800,
            )
            date_only_bank_in = _txn(
                session, instrument_id=bank.id, external_id="DATEONLY-BANK-1",
                posting_date=date(2026, 9, 2), amount_minor=8800,
            )
            session.commit()
            mixed_precision_match = matching.auto_match_transaction(session, precise_paypal_out)
            result.check(
                "mixed precision (transaction_datetime vs posting_date-only) still matches within tolerance (§8)",
                mixed_precision_match is not None,
            )

            # A transaction with no date fact at all cannot be matched (insufficient evidence).
            no_date_paypal_out = _txn(
                session, instrument_id=paypal.id, external_id="NODATE-PP-1", amount_minor=-2200,
            )
            no_date_bank_in = _txn(
                session, instrument_id=bank.id, external_id="NODATE-BANK-1", amount_minor=2200,
            )
            session.commit()
            no_date_match = matching.auto_match_transaction(session, no_date_paypal_out)
            result.check(
                "a transaction with no date/time fact at all cannot be auto-matched (never guessed)",
                no_date_match is None,
            )

            # --- Pre-existing (non-PayPal) reconciliation regression check ---
            plain_bank_txn = _txn(
                session, instrument_id=bank.id, external_id="PLAIN-BANK-1",
                transaction_datetime=day6, amount_minor=12345,
            )
            session.commit()
            result.check(
                "a plain, unrelated Bank Account transaction can still be created/queried normally",
                plain_bank_txn.id is not None and plain_bank_txn.classification == "UNKNOWN",
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
