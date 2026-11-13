#!/usr/bin/env python
"""Settlement configuration repair and recovery
(BANK_SETTLEMENT_UI_AND_MODAL_REPAIR_001).

Covers the service-layer half of the repair:

* a settlement account saved through the legacy `linked_instrument_id`
  field is recovered into the historized table, dated from the card's
  earliest imported transaction;
* the recovery is idempotent, never touches a card already configured
  through the canonical path, and never recovers toward a non-BANK_ACCOUNT;
* a card with no transactions is reported for a human rather than dated
  on a guess;
* the historized record and the compatibility projection stay in step;
* deduplication is recomputed after a settlement change, and rows that
  were previously un-evaluable become evaluable.

Never touches AWS, RDS, a production database, or a real bank file.
"""

from __future__ import annotations

import sys
from datetime import date

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import accounting_dedup
from rfone_data_store.bank_reconciliation import card_configuration as cards
from rfone_data_store.database import (
    create_configured_engine,
    create_session_factory,
    redact_database_url,
    resolve_test_database_url,
    run_migrations_to_head,
)


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        if condition:
            passed.append(description)
        else:
            failed.append(description)
            print(f"FAILED: {description}" + (f" ({detail})" if detail else ""))

    url = resolve_test_database_url("bank_settlement_ui_repair")
    print(f"Database URL: {redact_database_url(url)}")
    run_migrations_to_head(url)
    engine = create_configured_engine(url)

    try:
        session_factory = create_session_factory(engine)
        with session_factory() as s:
            entity = m.LegalEntity(legal_name="Repair LLC", status="ACTIVE")
            s.add(entity)
            s.flush()

            checking = m.PaymentInstrument(
                legal_entity_id=entity.id, instrument_type="BANK_ACCOUNT",
                display_name="Checking", institution="CHASE", last_four="0001",
            )
            s.add(checking)
            s.flush()

            def card(name, last_four, linked=None):
                instrument = m.PaymentInstrument(
                    legal_entity_id=None, instrument_type="CREDIT_CARD",
                    display_name=name, institution="CHASE", last_four=last_four,
                    linked_instrument_id=linked,
                )
                s.add(instrument)
                s.flush()
                return instrument

            # Exactly the shape the QA database was found in: the settlement
            # account saved ONLY into the legacy column.
            legacy_mother = card("Legacy Mother", "1057", linked=checking.id)
            legacy_child = card("Legacy Child", "4482", linked=checking.id)
            already_historized = card("Already Configured", "7777", linked=checking.id)
            no_transactions = card("No Transactions", "0000", linked=checking.id)
            linked_to_card = card("Linked To A Card", "5555", linked=legacy_mother.id)
            s.flush()

            cards.assign_settlement_account(
                s, credit_card_payment_instrument_id=already_historized.id,
                settlement_bank_account_id=checking.id, valid_from=date(2025, 1, 1),
                notes="Entered by a human through the canonical path",
            )

            def txn(instrument, day, amount, description, month=5):
                row = m.FinancialTransaction(
                    payment_instrument_id=instrument.id,
                    bank_source="CHASE_CREDIT_CARD_WITH_CARD",
                    posting_date=date(2026, month, day), description_original=description,
                    description_normalized=description.upper(), amount_minor=amount,
                    status="COMPLETED", duplicate_status="NONE", review_status="REQUIRES_REVIEW",
                )
                s.add(row)
                s.flush()
                return row

            # The mother card's earliest transaction is in March; the later
            # ones must not become the recovered start date.
            earliest = txn(legacy_mother, 9, -41250, "US FOODS INC #4821", month=3)
            txn(legacy_mother, 5, -41250, "US FOODS INC #4821", month=5)
            mirror = txn(legacy_child, 5, -41250, "US FOODS INC #4821", month=5)
            txn(already_historized, 5, -999, "SOMETHING ELSE", month=5)
            txn(linked_to_card, 5, -888, "ANOTHER THING", month=5)
            s.commit()

            before = accounting_dedup.recompute_accounting_dedup(s)
            s.commit()
            # A legacy-configured card DOES resolve today, through the
            # undated `linked_instrument_id` fallback — which is exactly why
            # the split configuration went unnoticed. What it cannot do is
            # attribute a transaction to the account that was in force on
            # its posting date, because the legacy column carries no date at
            # all. The defect being repaired is therefore the MISSING
            # HISTORY, not an unresolved row.
            check(
                "before the repair, the legacy cards have no historized settlement row at all",
                s.query(m.BankCardSettlementAccount).filter(
                    m.BankCardSettlementAccount.credit_card_payment_instrument_id.in_(
                        [legacy_mother.id, legacy_child.id]
                    )
                ).count() == 0,
            )
            check(
                "before the repair, only the card linked to a non-bank instrument is un-evaluable",
                before.unresolved_transactions == 1,
                detail=f"unresolved={before.unresolved_transactions}",
            )
            raw_before = s.query(m.RawBankTransaction).count()
            transactions_before = s.query(m.FinancialTransaction).count()

            # ---------------------------------------------------------
            # 1-5. The recovery plan
            # ---------------------------------------------------------
            plan = cards.plan_legacy_settlement_recovery(s)
            by_card = {c.credit_card_id: c for c in plan}

            check(
                "4. a card already configured through the canonical path is not in the plan",
                already_historized.id not in by_card,
            )
            check(
                "1. a card configured only through the legacy field IS in the plan",
                legacy_mother.id in by_card and legacy_child.id in by_card,
            )
            check(
                "2. valid_from is the card's EARLIEST transaction, not its latest",
                by_card[legacy_mother.id].valid_from == earliest.posting_date
                and by_card[legacy_mother.id].valid_from == date(2026, 3, 9),
                detail=str(by_card[legacy_mother.id].valid_from),
            )
            check(
                "the plan reports how many transactions each card carries",
                by_card[legacy_mother.id].transaction_count == 2,
            )
            check(
                "5. a card linked to another CARD is reported, never recovered",
                linked_to_card.id in by_card
                and not by_card[linked_to_card.id].recoverable
                and "not a BANK_ACCOUNT" in (by_card[linked_to_card.id].skip_reason or ""),
                detail=str(by_card[linked_to_card.id].skip_reason),
            )
            check(
                "a card with no transaction is reported for a human, never dated on a guess",
                no_transactions.id in by_card
                and not by_card[no_transactions.id].recoverable
                and by_card[no_transactions.id].valid_from is None,
            )

            # ---------------------------------------------------------
            # Apply
            # ---------------------------------------------------------
            written = cards.apply_legacy_settlement_recovery(s)
            s.commit()
            check(
                "only the recoverable cards are written",
                {c.credit_card_id for c in written} == {legacy_mother.id, legacy_child.id},
            )
            rows = s.query(m.BankCardSettlementAccount).all()
            check(
                "1b. the recovered rows carry the recognisable technical note",
                all(
                    r.notes == cards.RECOVERY_NOTE
                    for r in rows if r.credit_card_payment_instrument_id in
                    (legacy_mother.id, legacy_child.id)
                ),
            )
            check(
                "4b. the pre-existing canonical assignment is untouched",
                s.query(m.BankCardSettlementAccount).filter_by(
                    credit_card_payment_instrument_id=already_historized.id
                ).one().notes == "Entered by a human through the canonical path",
            )

            # ---------------------------------------------------------
            # 3. Idempotence
            # ---------------------------------------------------------
            count_after_first = s.query(m.BankCardSettlementAccount).count()
            second = cards.apply_legacy_settlement_recovery(s)
            s.commit()
            check(
                "3. a second run creates nothing and changes nothing",
                second == []
                and s.query(m.BankCardSettlementAccount).count() == count_after_first,
            )

            # ---------------------------------------------------------
            # 7-9. Projection, recompute, previously un-evaluable rows
            # ---------------------------------------------------------
            after = accounting_dedup.recompute_accounting_dedup(s)
            s.commit()
            check(
                "9. after the repair every card with a real bank account is evaluable, and the "
                "one linked to a card still is not — it is reported, never guessed",
                after.unresolved_transactions == 1
                and s.query(m.FinancialTransaction).filter_by(
                    payment_instrument_id=linked_to_card.id,
                    accounting_status=accounting_dedup.UNRESOLVED_NO_SETTLEMENT_ACCOUNT,
                ).count() == 1,
                detail=f"unresolved={after.unresolved_transactions}",
            )
            check(
                "9b. the recovered configuration now carries a real date, which the legacy "
                "column never could",
                s.query(m.BankCardSettlementAccount).filter_by(
                    credit_card_payment_instrument_id=legacy_mother.id
                ).one().valid_from == date(2026, 3, 9),
            )
            check(
                "9c. a transaction posted before the recovered period still resolves through "
                "the compatibility fallback rather than losing its account",
                cards.settlement_account_on(
                    s, credit_card_payment_instrument_id=legacy_mother.id,
                    on_date=date(2020, 1, 1),
                ) is not None,
            )
            s.refresh(mirror)
            check(
                "the mother card's and the child card's identical rows now deduplicate",
                mirror.accounting_status == accounting_dedup.DUPLICATE_SUPPRESSED,
                detail=str(mirror.accounting_status),
            )
            check(
                "10. no raw row and no transaction is created or deleted by the repair",
                s.query(m.RawBankTransaction).count() == raw_before
                and s.query(m.FinancialTransaction).count() == transactions_before,
            )

            # 7. Historized record and compatibility projection stay in step.
            cards.assign_settlement_account(
                s, credit_card_payment_instrument_id=legacy_mother.id,
                settlement_bank_account_id=checking.id, valid_from=date(2026, 9, 1),
            )
            s.flush()
            open_rows = [
                r for r in s.query(m.BankCardSettlementAccount).filter_by(
                    credit_card_payment_instrument_id=legacy_mother.id
                ).all() if r.valid_to is None
            ]
            check(
                "7. exactly one open period survives a reassignment, and history is kept",
                len(open_rows) == 1
                and s.query(m.BankCardSettlementAccount).filter_by(
                    credit_card_payment_instrument_id=legacy_mother.id
                ).count() == 2,
            )
            s.refresh(legacy_mother)
            check(
                "7b. the compatibility projection matches the open historized row",
                legacy_mother.linked_instrument_id == open_rows[0].settlement_bank_account_id,
            )
            s.commit()
    finally:
        engine.dispose()

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
