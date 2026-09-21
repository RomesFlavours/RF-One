#!/usr/bin/env python
"""Bank Recognition Expert System tests (BANK_RECONCILIATION_EXPERT_
SYSTEM_001).

Canonical Financial Model Convergence — Phase 4/4B (FINANCIAL_MODEL_
CONVERGENCE_001). No dedicated test suite for `recognition.py` existed on
the source branch (`feature/bank-reconciliation-mvp`) — this is new,
focused coverage for the ported Expert System, exercising it directly
against the canonical `PaymentInstrument`/`FinancialTransaction` models,
plus confirming that a CSV import (`service.import_csv`) now enters
Recognition automatically. Phase 4B adds coverage for the canonical
decision unification: `FinancialTransaction.explanation_id` synchronization,
immutable decision snapshots, and their stability against later Occurrence/
Export Mapping edits.

Mirrors `test_bank_reconciliation_service.py`: a disposable SQLite
database, migrated to head, always cleaned up. Never touches a real/shared
database.

Usage:
    python test_bank_recognition_expert_system.py
"""

from __future__ import annotations

import sys
from datetime import date

from rfone_data_store.bank_reconciliation import recognition, service
from rfone_data_store.database import (
    cleanup_disposable_test_database_url,
    create_configured_engine,
    create_session_factory,
    redact_database_url,
    resolve_test_database_url,
    run_migrations_to_head,
)
from rfone_data_store import models as m

CHASE_CARD_CSV = (
    "Card,Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n"
    "1057,08/01/2026,08/02/2026,US FOODS INC #4821,Food,Sale,-450.00,\n"
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

    url = resolve_test_database_url("bank_recognition_expert_system")
    print(f"Database URL: {redact_database_url(url)}")
    run_migrations_to_head(url)
    engine = create_configured_engine(url)
    try:
        session_factory = create_session_factory(engine)
        with session_factory() as s:
            # --- 1-3. BankOccurrenceType / BankOccurrence / BankTransactionReason
            supplier_type = m.BankOccurrenceType(code="SUPPLIER", name="Supplier")
            payroll_type = m.BankOccurrenceType(code="PAYROLL_PROVIDER", name="Payroll Provider")
            s.add_all([supplier_type, payroll_type])
            s.flush()
            check("BankOccurrenceType creation/use", supplier_type.id is not None and payroll_type.id is not None)

            # BANK_RECONCILIATION_WHO_WHY_WHAT_001: WHAT first, then WHY
            # (which requires a WHAT), then WHO (which requires a WHY) —
            # the chain is what makes a Who usable at all, so the fixture
            # builds it in that order rather than creating orphans.
            cost_of_goods = m.BankAccountingClassification(
                code="COGS_FOOD", name="Cost of goods sold — food", statement_type="PROFIT_LOSS",
            )
            payroll_expense = m.BankAccountingClassification(
                code="PAYROLL_EXPENSE", name="Payroll expense", statement_type="PROFIT_LOSS",
            )
            s.add_all([cost_of_goods, payroll_expense])
            s.flush()
            check(
                "BankAccountingClassification (What) creation/use",
                cost_of_goods.statement_type == "PROFIT_LOSS" and payroll_expense.id is not None,
            )

            supplier_invoice_payment = m.BankTransactionReason(
                code="SUPPLIER_INVOICE_PAYMENT", name="Supplier Invoice Payment",
                accounting_classification_id=cost_of_goods.id,
            )
            payroll_reason = m.BankTransactionReason(
                code="PAYROLL", name="Payroll", accounting_classification_id=payroll_expense.id,
            )
            s.add_all([supplier_invoice_payment, payroll_reason])
            s.flush()
            check("BankTransactionReason creation/use", supplier_invoice_payment.id is not None)
            check(
                "Why -> What association is stored on the Reason itself",
                supplier_invoice_payment.accounting_classification_id == cost_of_goods.id,
            )

            us_foods = m.BankOccurrence(
                canonical_name="US Foods", occurrence_type_id=supplier_type.id,
                default_transaction_reason_id=supplier_invoice_payment.id,
            )
            adp = m.BankOccurrence(
                canonical_name="ADP", occurrence_type_id=payroll_type.id,
                default_transaction_reason_id=payroll_reason.id,
            )
            s.add_all([us_foods, adp])
            s.flush()
            check(
                "BankOccurrence creation/use",
                us_foods.occurrence_type_id == supplier_type.id and adp.occurrence_type_id == payroll_type.id,
            )
            check(
                "Who -> Why association is stored on the Occurrence itself",
                us_foods.default_transaction_reason_id == supplier_invoice_payment.id,
            )

            legal_entity = m.LegalEntity(legal_name="Recognition Test LLC", status="ACTIVE")
            s.add(legal_entity)
            s.flush()
            instrument_a = m.PaymentInstrument(
                legal_entity_id=legal_entity.id, instrument_type="CREDIT_CARD",
                display_name="Chase Card 1057", institution="CHASE", last_four="1057",
            )
            instrument_b = m.PaymentInstrument(
                legal_entity_id=legal_entity.id, instrument_type="BANK_ACCOUNT",
                display_name="Chase Checking 0214", institution="CHASE",
            )
            s.add_all([instrument_a, instrument_b])
            s.flush()

            # --- 4. BankRecognitionRule can be globally scoped -----------------
            global_rule = recognition.create_or_reuse_rule(
                s, match_type=recognition.CONTAINS_TEXT, normalized_pattern="US FOODS",
                occurrence_id=us_foods.id, transaction_reason_id=supplier_invoice_payment.id,
                payment_instrument_id=None, direction=None,
                auto_apply_enabled=True, created_from_transaction_id=None,
            )
            check(
                "BankRecognitionRule can be globally scoped (payment_instrument_id=None)",
                global_rule.payment_instrument_id is None,
            )

            # --- 5. BankRecognitionRule can be scoped to PaymentInstrument -----
            scoped_rule = recognition.create_or_reuse_rule(
                s, match_type=recognition.EXACT_NORMALIZED_DESCRIPTION, normalized_pattern="ADP PAYROLL",
                occurrence_id=adp.id, transaction_reason_id=payroll_reason.id,
                payment_instrument_id=instrument_b.id, direction=None,
                auto_apply_enabled=True, created_from_transaction_id=None,
            )
            check(
                "BankRecognitionRule can be scoped to PaymentInstrument",
                scoped_rule.payment_instrument_id == instrument_b.id,
            )

            # --- 6-7. Recognition reads FinancialTransaction, uses
            # payment_instrument_id --------------------------------------------
            txn = m.FinancialTransaction(
                payment_instrument_id=instrument_a.id,
                bank_source="CHASE_CREDIT_CARD_WITH_CARD",
                posting_date=date(2026, 8, 2),
                description_original="US FOODS INC #4821",
                description_normalized="US FOODS INC 4821",
                amount_minor=-45000,
                status="UNKNOWN",
            )
            s.add(txn)
            s.flush()
            explanation = recognition.deduce_for_transaction(s, txn)
            # BANK_WHO_WHY_INVARIANT_001 — what this check proves is rule
            # SCOPING, which is unchanged. What changed is the outcome of a
            # match: the rule resolves the WHO, and the WHY waits for the
            # transaction's own purpose evidence or for a human.
            check(
                "Recognition reads FinancialTransaction and uses payment_instrument_id "
                "(global rule matches instrument_a)",
                explanation.occurrence_id == us_foods.id
                and explanation.recognition_rule_id is not None,
                detail=f"occurrence={explanation.occurrence_id}",
            )
            check(
                "a matched rule resolves the WHO and leaves the WHY unresolved when the "
                "transaction proves no purpose",
                explanation.decision_status == "NEEDS_HUMAN_REVIEW"
                and explanation.transaction_reason_id is None,
                detail=f"{explanation.decision_status}/{explanation.transaction_reason_id}",
            )

            # --- 8. Matching rule produces the same source behavior as before:
            # a CONTAINS_TEXT global rule matches regardless of instrument -----
            txn_on_other_instrument = m.FinancialTransaction(
                payment_instrument_id=instrument_b.id,
                bank_source="CHASE_BANK_ACCOUNT",
                posting_date=date(2026, 8, 5),
                description_original="US FOODS INC #9911 ACH",
                description_normalized="US FOODS INC 9911 ACH",
                amount_minor=-12000,
                status="UNKNOWN",
            )
            s.add(txn_on_other_instrument)
            s.flush()
            other_explanation = recognition.deduce_for_transaction(s, txn_on_other_instrument)
            check(
                "A globally-scoped rule matches on any Payment Instrument",
                other_explanation.occurrence_id == us_foods.id
                and other_explanation.recognition_rule_id is not None,
                detail=f"occurrence={other_explanation.occurrence_id}",
            )

            # A rule scoped to instrument_b never matches instrument_a.
            adp_txn_wrong_instrument = m.FinancialTransaction(
                payment_instrument_id=instrument_a.id,
                bank_source="CHASE_CREDIT_CARD_WITH_CARD",
                posting_date=date(2026, 8, 6),
                description_original="ADP PAYROLL",
                description_normalized="ADP PAYROLL",
                amount_minor=-500000,
                status="UNKNOWN",
            )
            s.add(adp_txn_wrong_instrument)
            s.flush()
            wrong_instrument_explanation = recognition.deduce_for_transaction(s, adp_txn_wrong_instrument)
            check(
                "An instrument-scoped rule does not match a different instrument",
                wrong_instrument_explanation.decision_status == "NEEDS_HUMAN_REVIEW",
            )

            # --- 9. Insufficient evidence does NOT invent a match/explanation --
            unmatched_txn = m.FinancialTransaction(
                payment_instrument_id=instrument_a.id,
                bank_source="CHASE_CREDIT_CARD_WITH_CARD",
                posting_date=date(2026, 8, 7),
                description_original="UNKNOWN MERCHANT XYZ",
                description_normalized="UNKNOWN MERCHANT XYZ",
                amount_minor=-999,
                status="UNKNOWN",
            )
            s.add(unmatched_txn)
            s.flush()
            no_match_explanation = recognition.deduce_for_transaction(s, unmatched_txn)
            check(
                "Insufficient evidence routes to NEEDS_HUMAN_REVIEW, never invents a match",
                no_match_explanation.decision_status == "NEEDS_HUMAN_REVIEW"
                and no_match_explanation.occurrence_id is None
                and no_match_explanation.transaction_reason_id is None,
            )

            # --- 10. HUMAN decision can be recorded -----------------------------
            operator = m.RFOneAccount(username="recognition_operator", display_name="Operator", password_hash="x", status="ACTIVE")
            s.add(operator)
            s.flush()
            human_decision = recognition.record_human_decision(
                s,
                recognition.HumanDecisionRequest(
                    transaction_id=unmatched_txn.id, occurrence_id=us_foods.id,
                    confirmed_by_account_id=operator.id, learn_description=False,
                ),
            )
            check(
                "HUMAN decision can be recorded",
                human_decision.decision_source == "HUMAN" and human_decision.decision_status == "HUMAN_CONFIRMED",
            )

            # --- 11. Explanation history remains auditable/append-only ---------
            all_rows_for_txn = s.query(m.BankTransactionExplanation).filter_by(
                financial_transaction_id=unmatched_txn.id
            ).order_by(m.BankTransactionExplanation.id).all()
            check(
                "Explanation history is append-only (both the RULE and HUMAN rows survive)",
                len(all_rows_for_txn) == 2
                and all_rows_for_txn[0].decision_source == "RULE"
                and all_rows_for_txn[1].decision_source == "HUMAN",
            )

            # --- 12. Current explanation can be resolved ------------------------
            current = recognition.get_current_explanation(s, financial_transaction_id=unmatched_txn.id)
            check(
                "The current explanation resolves to the most recent (HUMAN) row",
                current is not None and current.id == human_decision.id,
            )

            # --- 13. Newly imported CSV transaction enters Recognition ---------
            upload = service.import_csv(
                s, file_bytes=CHASE_CARD_CSV.encode("utf-8"),
                original_file_name="chase1057_recognition.csv", uploaded_by_account_id=None,
            )
            s.commit()
            imported_txn = s.query(m.FinancialTransaction).filter_by(
                import_batch_id=upload.batch.id
            ).one()
            imported_explanation = recognition.get_current_explanation(
                s, financial_transaction_id=imported_txn.id,
            )
            check(
                "A newly imported CSV transaction enters Recognition automatically",
                imported_explanation is not None and imported_explanation.decision_source == "RULE"
                and imported_explanation.occurrence_id == us_foods.id,
                detail="no explanation" if imported_explanation is None else
                       f"{imported_explanation.decision_source}/{imported_explanation.occurrence_id}",
            )

            # -----------------------------------------------------------------
            # Phase 4B — canonical decision unification.
            # -----------------------------------------------------------------

            # --- 1-2. A RULE decision creates one canonical Explanation, and
            # FinancialTransaction.explanation_id points to it. -------------------
            check(
                "One RULE decision creates one canonical Explanation",
                s.query(m.BankTransactionExplanation).filter_by(financial_transaction_id=txn.id).count() == 1,
            )
            check(
                "FinancialTransaction.explanation_id points to that current RULE decision",
                txn.explanation_id == explanation.id,
            )

            # --- 7-8. Occurrence + Export Mapping snapshots are captured. -------
            export_mapping = m.BankTransactionReasonExportMapping(
                bank_transaction_reason_id=supplier_invoice_payment.id,
                food_cost=True, what_label="Food Supplier",
            )
            s.add(export_mapping)
            s.flush()

            snapshot_txn = m.FinancialTransaction(
                payment_instrument_id=instrument_a.id,
                bank_source="CHASE_CREDIT_CARD_WITH_CARD",
                posting_date=date(2026, 8, 10),
                description_original="US FOODS INC #5555",
                description_normalized="US FOODS INC 5555",
                amount_minor=-2000,
                status="UNKNOWN",
            )
            s.add(snapshot_txn)
            s.flush()
            # BANK_WHO_WHY_INVARIANT_001 — recorded as a HUMAN decision so
            # that a WHY is actually resolved. Automatic recognition no
            # longer resolves a WHY from the Who alone, and a snapshot of
            # an unresolved WHY would prove nothing about immutability.
            # A human choosing this Who for this transaction IS a
            # transaction-level decision, which the invariant permits.
            snapshot_decision = recognition.record_human_decision(
                s, recognition.HumanDecisionRequest(
                    transaction_id=snapshot_txn.id, occurrence_id=us_foods.id,
                    confirmed_by_account_id=None, learn_description=False,
                ),
            )
            check(
                "Occurrence snapshot is captured at decision time",
                snapshot_decision.occurrence_name_snapshot == "US Foods",
            )
            check(
                "Export Mapping snapshot is captured at decision time",
                snapshot_decision.food_cost_snapshot is True
                and snapshot_decision.what_label_snapshot == "Food Supplier",
            )

            # --- 9-10. Later Occurrence rename / Export Mapping change does NOT
            # change the already-captured historical snapshot. -------------------
            us_foods.canonical_name = "US Foods Inc (renamed)"
            export_mapping.food_cost = False
            export_mapping.what_label = "Renamed — must not appear in history"
            s.flush()
            check(
                "A later Occurrence rename does not change the historical snapshot",
                snapshot_decision.occurrence_name_snapshot == "US Foods",
            )
            check(
                "A later Export Mapping change does not change the historical snapshot",
                snapshot_decision.food_cost_snapshot is True
                and snapshot_decision.what_label_snapshot == "Food Supplier",
            )

            # --- 3-6. HUMAN confirmation vs. override both create new append-only
            # rows, and explanation_id always moves to whichever is current. -----
            confirm_txn = m.FinancialTransaction(
                payment_instrument_id=instrument_a.id,
                bank_source="CHASE_CREDIT_CARD_WITH_CARD",
                posting_date=date(2026, 8, 11),
                description_original="AMBIGUOUS MERCHANT",
                description_normalized="AMBIGUOUS MERCHANT",
                amount_minor=-333,
                status="UNKNOWN",
            )
            s.add(confirm_txn)
            s.flush()
            first_decision = recognition.deduce_for_transaction(s, confirm_txn)  # NEEDS_HUMAN_REVIEW
            check(
                "Previous decisions remain queryable before a human acts",
                s.query(m.BankTransactionExplanation).filter_by(financial_transaction_id=confirm_txn.id).count() == 1,
            )

            # --- 16. No requested reuse does not create a rule. -------------------
            rule_count_before = s.query(m.BankRecognitionRule).count()
            confirm_decision = recognition.record_human_decision(
                s,
                recognition.HumanDecisionRequest(
                    transaction_id=confirm_txn.id, occurrence_id=adp.id,
                    confirmed_by_account_id=operator.id, learn_description=False,
                ),
            )
            check(
                "HUMAN confirmation creates a new append-only row",
                confirm_decision.decision_source == "HUMAN" and confirm_decision.id != first_decision.id,
            )
            check(
                "explanation_id moves to the new current (HUMAN) decision",
                confirm_txn.explanation_id == confirm_decision.id,
            )
            check(
                "Declining description learning does not create a BankRecognitionRule",
                s.query(m.BankRecognitionRule).count() == rule_count_before,
            )

            override_decision = recognition.record_human_decision(
                s,
                recognition.HumanDecisionRequest(
                    transaction_id=confirm_txn.id, occurrence_id=us_foods.id,
                    confirmed_by_account_id=operator.id, learn_description=False,
                ),
            )
            check(
                "HUMAN override creates a new append-only row",
                override_decision.decision_source == "HUMAN"
                and override_decision.decision_status == "HUMAN_OVERRIDDEN"
                and override_decision.id != confirm_decision.id,
            )
            check(
                "explanation_id moves to the new current (overridden) decision",
                confirm_txn.explanation_id == override_decision.id,
            )
            check(
                "All three historical decisions for this transaction remain queryable",
                s.query(m.BankTransactionExplanation).filter_by(financial_transaction_id=confirm_txn.id).count() == 3,
            )

    finally:
        engine.dispose()
        cleanup_disposable_test_database_url(url)

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
