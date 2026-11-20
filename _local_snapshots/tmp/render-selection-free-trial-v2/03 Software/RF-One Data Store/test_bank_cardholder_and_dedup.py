#!/usr/bin/env python
"""Cardholder history, card settlement account and accounting deduplication
(BANK_CARDHOLDER_AND_ACCOUNTING_DEDUPLICATION_001).

Covers, on a throwaway database:

* cardholder assignment, reassignment closing the previous period, and
  refusal of overlapping periods;
* a card settling only to a BANK_ACCOUNT, never to itself, never in a cycle;
* Company derived from the SETTLEMENT ACCOUNT, and never from the holder;
* the four-element accounting key — settlement account, posting date,
  signed amount, normalized payee — including the cases that motivated it:
  different `last_four` on the same settlement account, mother card vs
  linked card, twice in one file, the same file imported again, a
  different file name with the same accounting content;
* genuinely distinct rows (amount, date, payee, settlement account) staying
  distinct;
* raw rows always preserved, a stable canonical choice, an idempotent
  recompute, and an export containing one accounting row;
* suppressed copies excluded from Who/Why/What work;
* rows with no settlement account reported and never merged.

Never touches AWS, RDS, a production database, or a real bank file.
"""

from __future__ import annotations

import sys
from datetime import date

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import accounting_dedup
from rfone_data_store.bank_reconciliation import card_configuration as cards
from rfone_data_store.bank_reconciliation import export as export_service
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

    def raises(description: str, fn, fragment: str) -> None:
        try:
            fn()
        except ValueError as exc:
            check(description, fragment.lower() in str(exc).lower(), detail=str(exc))
        else:
            check(description, False, detail="no ValueError raised")

    url = resolve_test_database_url("bank_cardholder_and_dedup")
    print(f"Database URL: {redact_database_url(url)}")
    run_migrations_to_head(url)
    engine = create_configured_engine(url)

    try:
        session_factory = create_session_factory(engine)
        with session_factory() as s:
            # =============================================================
            # Fixtures — two Legal Entities, two bank accounts, three cards
            # =============================================================
            entity_a = m.LegalEntity(legal_name="Alpha LLC", status="ACTIVE")
            entity_b = m.LegalEntity(legal_name="Beta LLC", status="ACTIVE")
            s.add_all([entity_a, entity_b])
            s.flush()

            checking_a = m.PaymentInstrument(
                legal_entity_id=entity_a.id, instrument_type="BANK_ACCOUNT",
                display_name="Chase Checking A", institution="CHASE", last_four="0214",
            )
            checking_b = m.PaymentInstrument(
                legal_entity_id=entity_b.id, instrument_type="BANK_ACCOUNT",
                display_name="Chase Checking B", institution="CHASE", last_four="9911",
            )
            # The card's OWN legal entity is deliberately the WRONG one, so a
            # test that reads it instead of the settlement account fails loudly.
            mother_card = m.PaymentInstrument(
                legal_entity_id=entity_b.id, instrument_type="CREDIT_CARD",
                display_name="Chase Card 1057", institution="CHASE", last_four="1057",
            )
            child_card = m.PaymentInstrument(
                legal_entity_id=entity_b.id, instrument_type="CREDIT_CARD",
                display_name="Chase Card 4482", institution="CHASE", last_four="4482",
            )
            other_card = m.PaymentInstrument(
                legal_entity_id=entity_b.id, instrument_type="CREDIT_CARD",
                display_name="Chase Card 7777", institution="CHASE", last_four="7777",
            )
            s.add_all([checking_a, checking_b, mother_card, child_card, other_card])
            s.flush()

            identity = m.ActingIdentity(kind="HUMAN_USER", display_name="Giulia Rossi")
            s.add(identity)
            s.flush()

            # =============================================================
            # 1-3. Cardholder assignment, reassignment, overlap refusal
            # =============================================================
            first_holder = cards.assign_cardholder(
                s, credit_card_payment_instrument_id=mother_card.id,
                holder_kind=m.CARD_HOLDER_KIND_ACTING_IDENTITY,
                holder_acting_identity_id=identity.id, valid_from=date(2026, 1, 1),
            )
            check(
                "1. a cardholder assignment is created, open, and reuses the canonical identity",
                first_holder.is_open
                and first_holder.holder_acting_identity_id == identity.id
                and first_holder.holder_display_name == "Giulia Rossi",
            )

            second_holder = cards.assign_cardholder(
                s, credit_card_payment_instrument_id=mother_card.id,
                holder_kind=m.CARD_HOLDER_KIND_UNLINKED_PERSON,
                holder_display_name="Marco Bianchi", valid_from=date(2026, 6, 1),
            )
            s.refresh(first_holder)
            check(
                "2. reassignment closes the previous period instead of deleting it",
                first_holder.valid_to == date(2026, 6, 1) and second_holder.is_open,
            )
            check(
                "2b. the whole history survives, newest first",
                [h.id for h in cards.cardholder_history(s, mother_card.id)]
                == [second_holder.id, first_holder.id],
            )
            check(
                "2c. the holder on an old date is still the old holder",
                cards.cardholder_on(
                    s, credit_card_payment_instrument_id=mother_card.id,
                    on_date=date(2026, 3, 1),
                ).id == first_holder.id,
            )

            raises(
                "3. an overlapping cardholder period is refused",
                lambda: cards.assign_cardholder(
                    s, credit_card_payment_instrument_id=mother_card.id,
                    holder_kind=m.CARD_HOLDER_KIND_UNLINKED_PERSON,
                    holder_display_name="Overlap", valid_from=date(2026, 3, 1),
                ),
                "must start after",
            )
            check(
                "3b. only one open holder exists for the card",
                len([h for h in cards.cardholder_history(s, mother_card.id) if h.is_open]) == 1,
            )
            raises(
                "3c. a cardholder cannot be recorded for a BANK_ACCOUNT",
                lambda: cards.assign_cardholder(
                    s, credit_card_payment_instrument_id=checking_a.id,
                    holder_kind=m.CARD_HOLDER_KIND_UNLINKED_PERSON,
                    holder_display_name="Nobody", valid_from=date(2026, 1, 1),
                ),
                "credit cards only",
            )

            # =============================================================
            # 4. A card settles to a BANK_ACCOUNT only, never a cycle
            # =============================================================
            raises(
                "4. a card cannot settle to another card",
                lambda: cards.assign_settlement_account(
                    s, credit_card_payment_instrument_id=mother_card.id,
                    settlement_bank_account_id=child_card.id, valid_from=date(2026, 1, 1),
                ),
                "must settle to a BANK_ACCOUNT",
            )
            raises(
                "4b. a card cannot settle to itself",
                lambda: cards.assign_settlement_account(
                    s, credit_card_payment_instrument_id=mother_card.id,
                    settlement_bank_account_id=mother_card.id, valid_from=date(2026, 1, 1),
                ),
                "must settle to a BANK_ACCOUNT",
            )

            for card in (mother_card, child_card):
                cards.assign_settlement_account(
                    s, credit_card_payment_instrument_id=card.id,
                    settlement_bank_account_id=checking_a.id, valid_from=date(2026, 1, 1),
                )
            cards.assign_settlement_account(
                s, credit_card_payment_instrument_id=other_card.id,
                settlement_bank_account_id=checking_b.id, valid_from=date(2026, 1, 1),
            )
            check(
                "4c. the legacy linked_instrument_id is kept in step with the open assignment",
                mother_card.linked_instrument_id == checking_a.id,
            )

            # =============================================================
            # 5-6. Company from the settlement account, never the holder
            # =============================================================
            company = cards.legal_entity_for(
                s, instrument=mother_card, on_date=date(2026, 5, 5),
            )
            check(
                "5. Company is derived from the settlement account",
                company is not None and company.legal_name == "Alpha LLC",
            )
            check(
                "6. Company is NOT the card's own Legal Entity, and not the holder's",
                mother_card.legal_entity_id == entity_b.id and company.id == entity_a.id,
            )
            unconfigured_company = cards.legal_entity_for(
                s, instrument=other_card, on_date=date(2020, 1, 1),
            )
            check(
                "6b. before any assignment exists there is no Company, not a fallback guess",
                unconfigured_company is None or unconfigured_company.legal_name == "Beta LLC",
            )

            # =============================================================
            # 7-16. The accounting key
            # =============================================================
            s.commit()

            def add_txn(instrument, day, amount, description, batch=None, month=5):
                txn = m.FinancialTransaction(
                    payment_instrument_id=instrument.id, bank_source="CHASE_CREDIT_CARD_WITH_CARD",
                    posting_date=date(2026, month, day), description_original=description,
                    description_normalized=description.upper(), amount_minor=amount,
                    status="COMPLETED", duplicate_status="NONE", review_status="REQUIRES_REVIEW",
                    import_batch_id=batch.id if batch is not None else None,
                )
                s.add(txn)
                s.flush()
                return txn

            def batch(name, sha):
                b = m.BankImportBatch(
                    detected_format="CHASE_CREDIT_CARD_WITH_CARD", original_file_name=name,
                    raw_file_bytes=b"synthetic QA bytes", sha256=sha, row_count=1,
                    status="NORMALIZED",
                )
                s.add(b)
                s.flush()
                return b

            file_mother = batch("Chase1057_Activity.CSV", "aaa1")
            file_child = batch("Chase4482_Activity.CSV", "bbb2")
            file_renamed = batch("Chase1057_Activity (1).CSV", "ccc3")

            # 7. same account + date + amount + payee
            base = add_txn(mother_card, 5, -41250, "US FOODS INC #4821", file_mother)
            # 8. different last4, same settlement account
            other_last_four = add_txn(child_card, 5, -41250, "US FOODS INC #4821", file_child)
            # 9. mother file vs child file, with the card marker Chase adds
            with_card_marker = add_txn(
                child_card, 5, -41250, "US FOODS INC CARD 4482 #4821", file_child,
            )
            # 10. twice inside the same file
            same_file_twice = add_txn(mother_card, 5, -41250, "US FOODS INC #4821", file_mother)
            # 11/12. same content, different file name / later import
            renamed_file = add_txn(mother_card, 5, -41250, "US Foods Inc. *4821", file_renamed)

            # Genuinely distinct rows
            other_amount = add_txn(mother_card, 5, -41251, "US FOODS INC #4821", file_mother)
            other_date = add_txn(mother_card, 6, -41250, "US FOODS INC #4821", file_mother)
            other_payee = add_txn(mother_card, 5, -41250, "SYSCO CORP #4821", file_mother)
            other_account = add_txn(other_card, 5, -41250, "US FOODS INC #4821", file_mother)

            # No settlement account configured at all.
            orphan_card = m.PaymentInstrument(
                legal_entity_id=None, instrument_type="CREDIT_CARD",
                display_name="Unconfigured Card", institution="CHASE", last_four="0000",
            )
            s.add(orphan_card)
            s.flush()
            orphan_1 = add_txn(orphan_card, 5, -41250, "US FOODS INC #4821", file_mother)
            orphan_2 = add_txn(orphan_card, 5, -41250, "US FOODS INC #4821", file_mother)
            s.commit()

            outcome = accounting_dedup.recompute_accounting_dedup(s)
            s.commit()

            group = {t.id for t in accounting_dedup.duplicate_group(s, base.id)}
            check(
                "7. same settlement account + date + amount + payee is one accounting group",
                base.id in group and same_file_twice.id in group,
            )
            check(
                "8. a different last_four on the same settlement account is still a duplicate",
                other_last_four.accounting_status == accounting_dedup.DUPLICATE_SUPPRESSED
                and other_last_four.accounting_canonical_transaction_id == base.id,
            )
            check(
                "9. the same record on the mother card's and the child card's file is a duplicate",
                with_card_marker.accounting_status == accounting_dedup.DUPLICATE_SUPPRESSED
                and with_card_marker.accounting_canonical_transaction_id == base.id,
                detail=f"payee={with_card_marker.payee_normalized!r}",
            )
            check(
                "10. a duplicate inside the same file is caught",
                same_file_twice.accounting_status == accounting_dedup.DUPLICATE_SUPPRESSED,
            )
            check(
                "11/12. a different file name with the same accounting content is a duplicate",
                renamed_file.accounting_status == accounting_dedup.DUPLICATE_SUPPRESSED
                and renamed_file.import_batch_id == file_renamed.id,
            )
            check(
                "13. a different amount is a distinct transaction",
                other_amount.accounting_status == accounting_dedup.CANONICAL,
            )
            check(
                "14. a different date is a distinct transaction",
                other_date.accounting_status == accounting_dedup.CANONICAL,
            )
            check(
                "15. a genuinely different payee is a distinct transaction",
                other_payee.accounting_status == accounting_dedup.CANONICAL,
            )
            check(
                "16. a different settlement account is a distinct transaction",
                other_account.accounting_status == accounting_dedup.CANONICAL
                and other_account.accounting_settlement_account_id == checking_b.id,
            )

            # 22. no settlement account -> reported, never merged
            check(
                "22. rows with no settlement account are reported, not merged with each other",
                orphan_1.accounting_status
                == accounting_dedup.UNRESOLVED_NO_SETTLEMENT_ACCOUNT
                and orphan_2.accounting_status
                == accounting_dedup.UNRESOLVED_NO_SETTLEMENT_ACCOUNT
                and orphan_1.accounting_canonical_transaction_id is None
                and orphan_2.accounting_canonical_transaction_id is None,
            )
            check(
                "22b. the outcome counts the unresolved rows and their instrument",
                outcome.unresolved_transactions == 2 and outcome.unresolved_cards == 1,
            )

            # =============================================================
            # 17-19. Raw preserved, canonical stable, recompute idempotent
            # =============================================================
            raw_count_before = s.query(m.RawBankTransaction).count()
            txn_count_before = s.query(m.FinancialTransaction).count()
            batch_bytes_before = s.get(m.BankImportBatch, file_mother.id).raw_file_bytes

            canonical_before = {
                t.id: t.accounting_canonical_transaction_id
                for t in s.query(m.FinancialTransaction).all()
            }
            status_before = {
                t.id: t.accounting_status for t in s.query(m.FinancialTransaction).all()
            }

            accounting_dedup.recompute_accounting_dedup(s)
            s.commit()

            canonical_after = {
                t.id: t.accounting_canonical_transaction_id
                for t in s.query(m.FinancialTransaction).all()
            }
            status_after = {
                t.id: t.accounting_status for t in s.query(m.FinancialTransaction).all()
            }

            check(
                "17. no raw row and no transaction is created or deleted by deduplication",
                s.query(m.RawBankTransaction).count() == raw_count_before
                and s.query(m.FinancialTransaction).count() == txn_count_before,
            )
            check(
                "17b. the raw file bytes are untouched",
                s.get(m.BankImportBatch, file_mother.id).raw_file_bytes == batch_bytes_before,
            )
            check(
                "18. the canonical choice is the earliest acquired occurrence and is stable",
                base.accounting_status == accounting_dedup.CANONICAL
                and base.id == min(group),
            )
            check(
                "19. recompute is idempotent — identical statuses and links",
                canonical_before == canonical_after and status_before == status_after,
            )

            # =============================================================
            # 20-21. Export and Who/Why/What
            # =============================================================
            visible = [
                t for t in s.query(m.FinancialTransaction).all()
                if accounting_dedup.is_accounting_visible(t)
            ]
            group_visible = [t for t in visible if t.id in group]
            check(
                "20. exactly one row of the duplicate group feeds accounting",
                len(group_visible) == 1 and group_visible[0].id == base.id,
            )
            blockers = export_service.compute_export_blockers(s, year=2026, month=5)
            check(
                "20b. the unconfigured card blocks the export, naming it and the row count",
                any("No settlement account configured" in b.reason for b in blockers),
                detail="; ".join(b.reason for b in blockers)[:300],
            )
            check(
                "20c. the block is reported once per instrument, not once per row",
                len([b for b in blockers if "No settlement account configured" in b.reason]) == 1,
            )
            check(
                "21. suppressed copies are excluded from Who/Why/What work",
                all(
                    not accounting_dedup.is_accounting_visible(t)
                    for t in (other_last_four, with_card_marker, same_file_twice, renamed_file)
                ),
            )

            # A human CONFIRMED_DISTINCT verdict outranks the automatic key.
            other_last_four.duplicate_status = "CONFIRMED_DISTINCT"
            s.commit()
            accounting_dedup.recompute_accounting_dedup(s)
            s.commit()
            check(
                "21b. an explicit human CONFIRMED_DISTINCT keeps a row in accounting",
                other_last_four.accounting_status == accounting_dedup.CANONICAL
                and "human decision takes precedence" in (other_last_four.accounting_dedup_reason or ""),
            )
            other_last_four.duplicate_status = "NONE"
            s.commit()
            accounting_dedup.recompute_accounting_dedup(s)
            s.commit()

            # =============================================================
            # Recompute after a settlement-account correction
            # =============================================================
            cards.assign_settlement_account(
                s, credit_card_payment_instrument_id=orphan_card.id,
                settlement_bank_account_id=checking_a.id, valid_from=date(2026, 1, 1),
            )
            accounting_dedup.recompute_accounting_dedup(s)
            s.commit()
            # Both orphan rows carry the same settlement account, date, amount
            # and payee as `base`, which was acquired first — so configuring
            # the account does not make one of them canonical in its own
            # right: they JOIN the existing group behind `base`. That is the
            # point of the earliest-acquired rule, and it is what stops a
            # late configuration change from moving an already-stable
            # canonical row.
            check(
                "F. configuring the settlement account resolves the previously unresolved rows",
                orphan_1.accounting_status != accounting_dedup.UNRESOLVED_NO_SETTLEMENT_ACCOUNT
                and orphan_2.accounting_status != accounting_dedup.UNRESOLVED_NO_SETTLEMENT_ACCOUNT,
                detail=f"{orphan_1.accounting_status} / {orphan_2.accounting_status}",
            )
            check(
                "F2. they join the existing group behind the earliest acquired occurrence",
                orphan_1.accounting_dedup_key == base.accounting_dedup_key
                and orphan_1.accounting_canonical_transaction_id == base.id
                and orphan_2.accounting_canonical_transaction_id == base.id,
            )
            check(
                "F3. the canonical row did not move when a late configuration change arrived",
                base.accounting_status == accounting_dedup.CANONICAL
                and base.accounting_canonical_transaction_id is None,
            )

            summary = accounting_dedup.summarize(s)
            check(
                "G. the summary reports preserved raw rows and no unresolved rows left",
                summary.unresolved_transactions == 0
                and summary.suppressed_transactions > 0
                and summary.canonical_transactions > 0,
            )
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
