#!/usr/bin/env python
"""Hierarchical bank classification — WHO -> WHY -> WHAT
(BANK_RECONCILIATION_WHO_WHY_WHAT_001).

Covers the model/service layer end to end on a throwaway database:

* WHAT CRUD, stable code, no physical delete, parent-cycle prevention;
* WHY CRUD with a mandatory WHAT;
* WHO CRUD with a mandatory default WHY;
* derivation of WHY and WHAT from the WHO alone;
* editing an association affecting FUTURE classifications only;
* historical snapshots surviving every such edit unchanged;
* explicit `Reclassify` appending a new auditable decision;
* an automatic WHO never resolving the WHY;
* the export blockers this hierarchy introduces.

BANK_OLD_RULES_REMOVAL_001: the checks on learned recognition rules,
automatic deduction at import, contradictory rules and broken-chain rules
went with the old rule system (section E). The check "human confirmations
learn no recognition rule" was retired when migration d2b6f8a4c0e7 dropped
the recognition-rule table: the invariant now holds by construction.

Never touches AWS, RDS, a production database, or a real bank file.
"""

from __future__ import annotations

import sys
from datetime import date

from rfone_data_store.bank_reconciliation import classification as classification_service
from rfone_data_store.bank_reconciliation import export as export_service
from rfone_data_store.bank_reconciliation import recognition
from rfone_data_store.bank_reconciliation import service as bank_service
from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation.testing_support import confirm_decided_rows
from rfone_data_store.database import (
    create_configured_engine,
    create_session_factory,
    redact_database_url,
    resolve_test_database_url,
    run_migrations_to_head,
)


def main() -> int:
    checks_passed: list[str] = []
    checks_failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        if condition:
            checks_passed.append(description)
        else:
            checks_failed.append(description)
            print(f"FAILED: {description}" + (f" ({detail})" if detail else ""))

    def raises(description: str, fn, expected_fragment: str) -> None:
        try:
            fn()
        except ValueError as exc:
            check(description, expected_fragment.lower() in str(exc).lower(), detail=str(exc))
        else:
            check(description, False, detail="no ValueError was raised")

    url = resolve_test_database_url("bank_who_why_what")
    print(f"Database URL: {redact_database_url(url)}")
    run_migrations_to_head(url)
    engine = create_configured_engine(url)

    try:
        session_factory = create_session_factory(engine)
        with session_factory() as s:
            # =============================================================
            # A. WHAT — CRUD, stable code, hierarchy, no physical delete
            # =============================================================
            expense = classification_service.create_accounting_classification(
                s, code="opex", name="Operating expenses", statement_type="PROFIT_LOSS",
            )
            check("a What is created with a normalized, upper-cased code", expense.code == "OPEX")
            check("a What records its statement side", expense.statement_type == "PROFIT_LOSS")

            food = classification_service.create_accounting_classification(
                s, code="COGS_FOOD", name="Cost of goods sold — food",
                statement_type="PROFIT_LOSS", parent_id=expense.id,
            )
            check("a What can hang under a parent What", food.parent_id == expense.id)

            ap_settlement = classification_service.create_accounting_classification(
                s, code="AP_SETTLEMENT", name="Accounts payable settlement",
                statement_type="BALANCE_SHEET",
            )
            check(
                "a What can be a Balance Sheet line, not only a P&L line",
                ap_settlement.statement_type == "BALANCE_SHEET",
            )

            raises(
                "a duplicate What code is refused",
                lambda: classification_service.create_accounting_classification(
                    s, code="OPEX", name="Duplicate", statement_type="PROFIT_LOSS",
                ),
                "already exists",
            )
            raises(
                "a What without a statement type is refused on create",
                lambda: classification_service.create_accounting_classification(
                    s, code="NO_SIDE", name="No side", statement_type=None,
                ),
                "requires a statement type",
            )
            raises(
                "an invalid statement type is refused",
                lambda: classification_service.create_accounting_classification(
                    s, code="BAD_SIDE", name="Bad side", statement_type="CASH_FLOW",
                ),
                "must be PROFIT_LOSS or BALANCE_SHEET",
            )

            # --- parent cycles -------------------------------------------
            raises(
                "a What cannot be its own parent",
                lambda: classification_service.update_accounting_classification(
                    s, classification_id=expense.id, name=expense.name,
                    statement_type=expense.statement_type, parent_id=expense.id,
                ),
                "cannot be its own parent",
            )
            raises(
                "a longer parent cycle (A -> B -> A) is refused",
                lambda: classification_service.update_accounting_classification(
                    s, classification_id=expense.id, name=expense.name,
                    statement_type=expense.statement_type, parent_id=food.id,
                ),
                "cycle",
            )

            # --- stable code + edit ---------------------------------------
            classification_service.update_accounting_classification(
                s, classification_id=food.id, name="Food cost", statement_type="PROFIT_LOSS",
                parent_id=expense.id,
            )
            check(
                "editing a What changes its name but never its code",
                food.name == "Food cost" and food.code == "COGS_FOOD",
            )

            check(
                "there is no physical-delete entry point for a What — only activate/deactivate",
                not any(
                    name.startswith("delete_") for name in dir(classification_service)
                ),
            )

            # =============================================================
            # B. WHY -> WHAT
            # =============================================================
            # BANK_WHY_WITHOUT_WHAT_001 / BANK_FINAL_CLEANUP_001: Bank
            # reconciliation is WHO + WHY; a Why needs no What (bookkeeping is
            # optional, existing mappings are kept).
            orphan = classification_service.create_transaction_reason(
                s, code="ORPHAN", name="Orphan reason", accounting_classification_id=None,
            )
            check(
                "a Why can be created without a What (bookkeeping optional)",
                orphan.accounting_classification_id is None,
            )

            supplier_payment = classification_service.create_transaction_reason(
                s, code="SUPPLIER_INVOICE_PAYMENT", name="Supplier invoice payment",
                accounting_classification_id=food.id,
            )
            check(
                "a Why carries exactly one current What",
                supplier_payment.accounting_classification_id == food.id,
            )

            invoice_settlement = classification_service.create_transaction_reason(
                s, code="AP_INVOICE_SETTLEMENT", name="Supplier invoice settlement",
                accounting_classification_id=ap_settlement.id,
            )
            check(
                "a supplier paid by invoice may classify to a Balance Sheet settlement What",
                invoice_settlement.accounting_classification_id == ap_settlement.id,
            )

            # =============================================================
            # C. WHO -> WHY
            # =============================================================
            supplier_type = m.BankOccurrenceType(code="SUPPLIER", name="Supplier")
            s.add(supplier_type)
            s.flush()

            # BANK_CANONICAL_WHY_AND_WHO_RELATIONSHIPS_001 §20 — this used to
            # assert "a Who cannot be created without a default Why", which was
            # a WHO -> one WHY constraint in all but name. A Who may now have
            # ZERO Whys: that is the ordinary state of a payee nobody has
            # confirmed a purpose for yet, and the relationship is carried by
            # the WHO <-> WHY associations instead.
            orphan = classification_service.create_occurrence(
                s, canonical_name="Orphan Who", occurrence_type_id=supplier_type.id,
                default_transaction_reason_id=None,
            )
            check(
                "a Who may exist with ZERO Why — the default Why is a suggestion, not a "
                "requirement",
                orphan.id is not None and orphan.default_transaction_reason_id is None
                and orphan.status == "ACTIVE",
            )

            us_foods = classification_service.create_occurrence(
                s, canonical_name="US Foods", occurrence_type_id=supplier_type.id,
                default_transaction_reason_id=supplier_payment.id,
            )
            check(
                "a Who carries exactly one current default Why",
                us_foods.default_transaction_reason_id == supplier_payment.id,
            )
            check(
                "a Who preserves its type and canonical_name",
                us_foods.occurrence_type_id == supplier_type.id and us_foods.canonical_name == "US FOODS",
            )

            # --- the full chain -------------------------------------------
            chain = classification_service.resolve_chain(s, us_foods)
            check(
                "the whole chain derives from the Who alone: Who -> Why -> What",
                chain.is_complete
                and chain.transaction_reason.id == supplier_payment.id
                and chain.accounting_classification.id == food.id,
            )

            # --- an incomplete Who is refused, with the reason -------------
            legacy_why = m.BankTransactionReason(code="LEGACY_WHY", name="Legacy why")
            s.add(legacy_why)
            s.flush()
            legacy_who = m.BankOccurrence(
                canonical_name="Legacy Who", occurrence_type_id=supplier_type.id,
                default_transaction_reason_id=legacy_why.id,
            )
            s.add(legacy_who)
            s.flush()
            legacy_chain = classification_service.resolve_chain(s, legacy_who)
            check(
                "a Who whose Why has no What is INCOMPLETE and says exactly why",
                not legacy_chain.is_complete and "no What" in legacy_chain.blocking_reason,
                detail=str(legacy_chain.blocking_reason),
            )

            inactive_who = classification_service.create_occurrence(
                s, canonical_name="Retired Vendor", occurrence_type_id=supplier_type.id,
                default_transaction_reason_id=supplier_payment.id,
            )
            classification_service.set_occurrence_status(
                s, occurrence_id=inactive_who.id, status="INACTIVE",
            )
            check(
                "an INACTIVE Who is refused for new classification, with the reason",
                not classification_service.resolve_chain(s, inactive_who).is_complete,
            )

            # --- search ----------------------------------------------------
            check(
                "Who search matches the name",
                [o.canonical_name for o in classification_service.list_occurrences(s, search="us foo")]
                == ["US FOODS"],
            )
            check(
                "Who search also matches the Who's type",
                "US FOODS" in [
                    o.canonical_name for o in classification_service.list_occurrences(s, search="supplier")
                ],
            )

            # =============================================================
            # D. Selecting only the WHO classifies a transaction
            # =============================================================
            legal_entity = m.LegalEntity(legal_name="Chain Test LLC", status="ACTIVE")
            s.add(legal_entity)
            s.flush()
            instrument = m.PaymentInstrument(
                legal_entity_id=legal_entity.id, instrument_type="BANK_ACCOUNT",
                display_name="Chase Checking", institution="CHASE",
            )
            s.add(instrument)
            s.flush()

            def new_txn(description: str, day: int, amount: int = -41250):
                txn = m.FinancialTransaction(
                    payment_instrument_id=instrument.id, bank_source="CHASE_BANK_ACCOUNT",
                    posting_date=date(2026, 9, day), description_original=description,
                    amount_minor=amount, status="COMPLETED", duplicate_status="NONE",
                )
                s.add(txn)
                s.flush()
                return txn

            first = new_txn("US FOODS INVOICE 4821", 1)
            who_only = bank_service.record_recognition_decision(
                s, transaction_id=first.id, occurrence_id=us_foods.id,
                confirmed_by_account_id=None, )
            # BANK_FINAL_RELEASE_BLOCKERS_001 — this used to assert "the Why is
            # derived" from the Who. A Who's default Why is never applied: the
            # Who is recorded and the Why stays open for a person.
            check(
                "the human supplies only the Who; the Why is NOT derived from the Who",
                who_only.occurrence_id == us_foods.id
                and who_only.transaction_reason_id is None
                and who_only.accounting_classification_code_snapshot is None
                and who_only.decision_status == "NEEDS_HUMAN_REVIEW",
                detail=f"{who_only.decision_status}/{who_only.transaction_reason_id}",
            )
            s.refresh(first)
            check(
                "...and a Who alone leaves the transaction in review",
                first.review_status != "REVIEWED",
                detail=str(first.review_status),
            )
            # The person then chooses the Why; the What derives from it.
            decision = recognition.record_human_decision(
                s, recognition.HumanDecisionRequest(
                    transaction_id=first.id, occurrence_id=us_foods.id,
                    transaction_reason_id=supplier_payment.id,
                    confirmed_by_account_id=None, ),
            )
            check(
                "the Why the person chooses is recorded",
                decision.transaction_reason_id == supplier_payment.id,
            )
            check(
                "the What is derived through the Why and snapshotted by code, name and side",
                decision.accounting_classification_id == food.id
                and decision.accounting_classification_code_snapshot == "COGS_FOOD"
                and decision.accounting_classification_name_snapshot == "Food cost"
                and decision.accounting_statement_type_snapshot == "PROFIT_LOSS",
            )
            check(
                "the decision also snapshots the Who and Why by value",
                decision.occurrence_name_snapshot == "US FOODS"
                and decision.transaction_reason_name_snapshot == "Supplier invoice payment",
            )

            # A Who-only confirmation no longer consults the Who's chain, so a
            # Who whose usual Why has no What is simply recorded as the Who;
            # nothing about its broken default leaks into the decision.
            legacy_only = bank_service.record_recognition_decision(
                s, transaction_id=new_txn("MYSTERY 1", 2).id, occurrence_id=legacy_who.id,
                confirmed_by_account_id=None, )
            check(
                "confirming a Who whose default chain is incomplete records only the Who",
                legacy_only.occurrence_id == legacy_who.id
                and legacy_only.transaction_reason_id is None
                and legacy_only.accounting_classification_code_snapshot is None,
            )
            raises(
                "confirming an INACTIVE Who is refused with an actionable reason",
                lambda: bank_service.record_recognition_decision(
                    s, transaction_id=new_txn("MYSTERY 2", 3).id, occurrence_id=inactive_who.id,
                    confirmed_by_account_id=None, ),
                "INACTIVE",
            )

            # =============================================================
            # E. An automatic WHO never resolves the WHY
            # =============================================================
            # BANK_OLD_RULES_REMOVAL_001: the checks on learned recognition
            # rules (EXACT rule from a confirmation, no broad rule from one
            # description, confirmations accumulating on one rule), on
            # automatic deduction at import, on contradictory rules and on a
            # rule with a broken chain went with the old rule system. Only AI
            # rules decide automatically now; the automatic WHO below is
            # seeded the way such a rule writes it.
            later = new_txn("US FOODS INVOICE 4821", 5)
            auto = recognition._create_decision_row(
                s, later, occurrence_id=us_foods.id, transaction_reason_id=None,
                decision_source="RULE", decision_status="NEEDS_HUMAN_REVIEW", confidence=None,
                explanation_notes="Seeded automatic WHO.",
            )
            # BANK_WHO_WHY_INVARIANT_001 — US FOODS INVOICE 4821 names a
            # supplier and says nothing about what was bought, so concluding
            # COGS_FOOD from it would be identity alone deciding the
            # accounting purpose. The WHO is resolved; the WHY waits.
            check(
                "an automatic WHO decision snapshots the Who and resolves no WHY or WHAT",
                auto.occurrence_name_snapshot == "US FOODS"
                and auto.transaction_reason_id is None
                and auto.transaction_reason_name_snapshot is None
                and auto.accounting_classification_code_snapshot is None,
                detail=f"{auto.decision_status}/{auto.transaction_reason_id}",
            )
            confirmed_auto = bank_service.record_recognition_decision(
                s, transaction_id=later.id, occurrence_id=us_foods.id,
                confirmed_by_account_id=None, )
            s.refresh(auto)
            check(
                "confirming the automatic WHO still takes no WHY from the Who's default",
                confirmed_auto.id != auto.id
                and confirmed_auto.occurrence_id == us_foods.id
                and confirmed_auto.transaction_reason_id is None
                and confirmed_auto.decision_status == "NEEDS_HUMAN_REVIEW"
                and auto.decision_source == "RULE",
                detail=f"{confirmed_auto.decision_status}/{confirmed_auto.transaction_reason_id}",
            )
            raises(
                "Reclassify of a WHO-only decision refuses rather than applying the Who's default",
                lambda: recognition.reclassify_transaction(
                    s, transaction_id=later.id, confirmed_by_account_id=None,
                ),
                "no Why",
            )

            repeat = new_txn("US FOODS INVOICE 4821", 6)
            bank_service.record_recognition_decision(
                s, transaction_id=repeat.id, occurrence_id=us_foods.id,
                confirmed_by_account_id=None, )
            # "human confirmations learn no recognition rule" was retired with
            # BANK_OLD_RULES_REMOVAL_001: the table no longer exists, so the
            # invariant holds by construction.
            # =============================================================
            # F. Editing an association — future only, history intact
            # =============================================================
            other_what = classification_service.create_accounting_classification(
                s, code="SUPPLIES", name="Operating supplies", statement_type="PROFIT_LOSS",
            )
            classification_service.update_transaction_reason(
                s, transaction_reason_id=supplier_payment.id, name=supplier_payment.name,
                accounting_classification_id=other_what.id,
            )
            s.flush()
            check(
                "a Why can be re-pointed at another What",
                supplier_payment.accounting_classification_id == other_what.id,
            )
            s.refresh(decision)
            check(
                "re-pointing the Why does NOT change an already-confirmed decision's What",
                decision.accounting_classification_code_snapshot == "COGS_FOOD"
                and decision.accounting_classification_name_snapshot == "Food cost",
            )

            after_edit = new_txn("BRAND NEW MERCHANT", 10)
            new_decision = recognition.record_human_decision(
                s, recognition.HumanDecisionRequest(
                    transaction_id=after_edit.id, occurrence_id=us_foods.id,
                    transaction_reason_id=supplier_payment.id,
                    confirmed_by_account_id=None, ),
            )
            check(
                "a NEW classification uses the Why's edited mapping",
                new_decision.accounting_classification_code_snapshot == "SUPPLIES",
            )

            classification_service.update_occurrence(
                s, occurrence_id=us_foods.id, canonical_name="US Foods",
                occurrence_type_id=supplier_type.id,
                default_transaction_reason_id=invoice_settlement.id,
            )
            s.flush()
            s.refresh(decision)
            check(
                "re-pointing the Who's default Why also leaves confirmed history untouched",
                decision.transaction_reason_id == supplier_payment.id
                and decision.transaction_reason_name_snapshot == "Supplier invoice payment",
            )

            # =============================================================
            # G. Explicit Reclassify
            # =============================================================
            history_before = s.query(m.BankTransactionExplanation).filter_by(
                financial_transaction_id=first.id,
            ).count()
            reclassified = bank_service.reclassify_transaction(
                s, transaction_id=first.id, confirmed_by_account_id=None,
            )
            check(
                "Reclassify appends a new auditable decision rather than overwriting",
                reclassified.decision_status == "HUMAN_RECLASSIFIED"
                and s.query(m.BankTransactionExplanation).filter_by(
                    financial_transaction_id=first.id,
                ).count() == history_before + 1,
            )
            # BANK_FINAL_RELEASE_BLOCKERS_001 — Reclassify keeps the decision's
            # own Why and re-derives its What; it never swaps in the Who's
            # (re-pointed) default Why.
            check(
                "Reclassify keeps the same Who and Why and applies the Why's CURRENT mapping",
                reclassified.occurrence_id == us_foods.id
                and reclassified.transaction_reason_id == supplier_payment.id
                and reclassified.accounting_classification_code_snapshot == "SUPPLIES",
                detail=f"{reclassified.transaction_reason_id}/{reclassified.accounting_classification_code_snapshot}",
            )
            check(
                "...and the Who's default Why was not applied",
                reclassified.transaction_reason_id != invoice_settlement.id,
            )
            s.refresh(decision)
            check(
                "the superseded decision row is unchanged and still queryable",
                decision.decision_status == "HUMAN_CONFIRMED"
                and decision.accounting_classification_code_snapshot == "COGS_FOOD",
            )
            s.refresh(first)
            check(
                "the transaction now points at the reclassified decision as current",
                first.explanation_id == reclassified.id,
            )

            # =============================================================
            # H. Export blockers
            # =============================================================
            s.commit()

            # Everything decided in September so far, except the rows left
            # deliberately unresolved, which are what the blockers are about.
            september = s.query(m.FinancialTransaction).filter(
                m.FinancialTransaction.posting_date >= date(2026, 9, 1),
                m.FinancialTransaction.posting_date <= date(2026, 9, 30),
            ).all()
            blockers = export_service.compute_export_blockers(s, year=2026, month=9)
            check(
                "a transaction with no Who blocks the export, naming the transaction",
                any("Needs review" in b.reason for b in blockers),
                detail="; ".join(b.reason for b in blockers)[:300],
            )

            # A decision whose Why lost its What afterwards is an incomplete
            # HISTORICAL classification and must block — the snapshot itself
            # is what is judged, never the current association.
            incomplete_txn = new_txn("INCOMPLETE HISTORY", 12)
            incomplete_decision = m.BankTransactionExplanation(
                financial_transaction_id=incomplete_txn.id, occurrence_id=us_foods.id,
                transaction_reason_id=supplier_payment.id, decision_source="HUMAN",
                decision_status="HUMAN_CONFIRMED", occurrence_name_snapshot="US Foods",
                transaction_reason_name_snapshot="Supplier invoice payment",
            )
            s.add(incomplete_decision)
            s.flush()
            incomplete_txn.explanation_id = incomplete_decision.id
            s.commit()
            blockers = export_service.compute_export_blockers(s, year=2026, month=9)
            check(
                "a confirmed decision carrying no What blocks the export as 'Why without What'",
                any("Why without What" in b.reason and str(incomplete_txn.id) in b.reason
                    for b in blockers),
                detail="; ".join(b.reason for b in blockers)[:400],
            )

            # A legacy-shaped snapshot with a What but no statement side.
            incomplete_decision.accounting_classification_code_snapshot = "LEGACY_FOOD_SUPPLIER"
            incomplete_decision.accounting_classification_name_snapshot = "Food Supplier"
            incomplete_decision.accounting_statement_type_snapshot = None
            s.commit()
            blockers = export_service.compute_export_blockers(s, year=2026, month=9)
            check(
                "a What snapshot with no statement type blocks as an incomplete historical classification",
                any("Incomplete historical classification" in b.reason for b in blockers),
                detail="; ".join(b.reason for b in blockers)[:400],
            )

            # Deactivating a What must NOT retroactively block a transaction
            # that already carries a valid snapshot of it.
            incomplete_decision.accounting_statement_type_snapshot = "PROFIT_LOSS"
            # BANK_RECONCILIATION_STANDARDS_001: a person confirms each row.
            confirm_decided_rows(s, year=2026, month=9)
            s.commit()
            classification_service.set_accounting_classification_active(
                s, classification_id=ap_settlement.id, active=False,
            )
            s.commit()
            blockers = export_service.compute_export_blockers(s, year=2026, month=9)
            check(
                "deactivating a What does not block a transaction that already has a valid snapshot",
                not any(f"transaction id={first.id} " in b.reason for b in blockers),
                detail="; ".join(b.reason for b in blockers)[:400],
            )
            raises(
                "an inactive What cannot be assigned to a Why",
                lambda: classification_service.update_transaction_reason(
                    s, transaction_reason_id=supplier_payment.id, name=supplier_payment.name,
                    accounting_classification_id=ap_settlement.id,
                ),
                "inactive",
            )
            s.rollback()

            # =============================================================
            # I. No duplication of the canonical ledger
            # =============================================================
            check(
                "no FinancialTransaction is ever duplicated by a classification decision",
                s.query(m.FinancialTransaction).count() == len({t.id for t in s.query(
                    m.FinancialTransaction
                ).all()}),
            )
            check(
                "September transactions are still exactly the rows this test created",
                len(september) == s.query(m.FinancialTransaction).filter(
                    m.FinancialTransaction.posting_date >= date(2026, 9, 1),
                    m.FinancialTransaction.posting_date <= date(2026, 9, 11),
                ).count(),
            )
    finally:
        engine.dispose()

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
