#!/usr/bin/env python
"""Classification bootstrap — What import and receiver review
(BANK_CLASSIFICATION_BOOTSTRAP_001).

Covers the service layer:

* parsing a chart of accounts from CSV and XLSX, keeping P&L and Balance
  Sheet apart, preserving hierarchy, and refusing amounts as codes;
* total and heading rows reported and skipped, never turned into accounts;
* deterministic technical codes when the plan carries none;
* preview writing nothing, confirmation writing exactly what was previewed,
  re-import idempotent, a code with a different meaning a conflict;
* receiver candidates built only from canonical, non-transfer, non-copy
  transactions, grouped on the exact normalized payee, with similar
  descriptions suggested but never merged;
* approval creating or reusing a Who, deriving Why and What, writing
  append-only snapshots, recording an exact rule, skipping human
  decisions, refusing ambiguity, and behaving atomically.

Never touches AWS, RDS, a production database, or a real bank file.
"""

from __future__ import annotations

import io
import sys
from datetime import date

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import accounting_dedup
from rfone_data_store.bank_reconciliation import card_configuration as cards
from rfone_data_store.bank_reconciliation import classification as classification_service
from rfone_data_store.bank_reconciliation import receiver_candidates as rc
from rfone_data_store.bank_reconciliation import recognition
from rfone_data_store.bank_reconciliation import what_catalog_import as wci
from rfone_data_store.database import (
    create_configured_engine,
    create_session_factory,
    redact_database_url,
    resolve_test_database_url,
    run_migrations_to_head,
)

CSV_PLAN = b"""Statement Type,Code,Name,Parent,Level
P&L,TEST-4000,Revenue,,0
P&L,TEST-4100,Food sales,TEST-4000,1
P&L,TEST-5000,Cost of goods sold,,0
P&L,TEST-5100,Food cost,TEST-5000,1
P&L,,Total cost of goods sold,,0
Balance Sheet,TEST-2000,Liabilities,,0
Balance Sheet,TEST-2100,Accounts payable,TEST-2000,1
"""

CSV_NO_CODES = b"""Name,Level
Operating expenses,0
Marketing,1
Payroll,1
Total operating expenses,0
"""

CSV_AMOUNT_AS_CODE = b"""Statement Type,Code,Name
P&L,1234567.89,Suspicious row
P&L,6000,Good row
"""


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

    url = resolve_test_database_url("bank_classification_bootstrap")
    print(f"Database URL: {redact_database_url(url)}")
    run_migrations_to_head(url)
    engine = create_configured_engine(url)

    try:
        session_factory = create_session_factory(engine)
        with session_factory() as s:
            # BANK_CANONICAL_ACCOUNTING_CATALOG_001: the ordinary migration now
            # seeds the canonical RF-One chart, so an empty catalog is no
            # longer the starting point. Every count below is measured
            # against that baseline rather than against zero — the property
            # under test is what the IMPORTER does, not how many accounts
            # happened to exist first.
            baseline_whats = s.query(m.BankAccountingClassification).count()

            # =============================================================
            # 1-7. Parsing and preview
            # =============================================================
            parsed = wci.parse(CSV_PLAN, file_name="plan.csv")
            check("1. a CSV chart of accounts parses", not parsed.file_anomalies,
                  detail=str(parsed.file_anomalies))
            check(
                "3. P&L and Balance Sheet rows keep their own statement type",
                {r.statement_type for r in parsed.importable_rows}
                == {wci.PROFIT_LOSS, wci.BALANCE_SHEET},
            )
            check(
                "5. a Total row is reported and never becomes an account",
                len(parsed.total_rows) == 1
                and "Total cost of goods sold" not in [r.name for r in parsed.importable_rows],
            )
            by_code = {r.code: r for r in parsed.importable_rows}
            check(
                "4. parent/child hierarchy is preserved",
                by_code["TEST-4100"].parent_code == "TEST-4000"
                and by_code["TEST-2100"].parent_code == "TEST-2000",
            )
            check(
                "7. the preview writes nothing",
                s.query(m.BankAccountingClassification).count() == baseline_whats,
            )

            # XLSX
            import openpyxl
            workbook = openpyxl.Workbook()
            sheet = workbook.active
            sheet.title = "Plan"
            for row in (
                ("Statement Type", "Code", "Name", "Parent", "Level"),
                ("P&L", "7000", "Utilities", "", 0),
                ("P&L", "7100", "Electricity", "7000", 1),
            ):
                sheet.append(list(row))
            buffer = io.BytesIO()
            workbook.save(buffer)
            parsed_xlsx = wci.parse(buffer.getvalue(), file_name="plan.xlsx", sheet_name="Plan")
            check(
                "2. an XLSX chart of accounts parses, from the named sheet",
                not parsed_xlsx.file_anomalies
                and len(parsed_xlsx.importable_rows) == 2
                and parsed_xlsx.sheet_name == "Plan",
                detail=str(parsed_xlsx.file_anomalies),
            )

            # 6. Deterministic technical codes.
            first = wci.parse(CSV_NO_CODES, file_name="nocodes.csv",
                              default_statement_type=wci.PROFIT_LOSS)
            second = wci.parse(CSV_NO_CODES, file_name="nocodes.csv",
                               default_statement_type=wci.PROFIT_LOSS)
            check(
                "6. a plan with no codes gets stable technical codes, identical across parses",
                [r.code for r in first.importable_rows] == [r.code for r in second.importable_rows]
                and all(r.code_is_generated for r in first.importable_rows)
                and all(r.code.startswith(wci.GENERATED_CODE_PREFIX) for r in first.importable_rows),
            )
            check(
                "6b. the total row is still excluded when codes are generated",
                "Total operating expenses" not in [r.name for r in first.importable_rows],
            )

            # Amount in the code column.
            amount_parse = wci.parse(CSV_AMOUNT_AS_CODE, file_name="amounts.csv")
            suspicious = [r for r in amount_parse.rows if r.name == "Suspicious row"][0]
            check(
                "an amount in the code column is rejected, never imported as an account code",
                suspicious.anomalies and "amount" in suspicious.anomalies[0].lower(),
                detail=str(suspicious.anomalies),
            )

            # No statement type anywhere -> refused.
            no_statement = wci.parse(b"Code,Name\n1,One\n", file_name="bare.csv")
            check(
                "a file with no statement type and none stated is refused, never defaulted",
                no_statement.file_anomalies
                and "statement type" in no_statement.file_anomalies[0].lower(),
            )

            # =============================================================
            # 8-11. Import, idempotence, conflict
            # =============================================================
            outcome = wci.apply_import(s, parsed)
            s.commit()
            check(
                "8. confirming the preview imports exactly the account rows",
                len(outcome.created) == 6
                and s.query(m.BankAccountingClassification).count() == baseline_whats + 6,
                detail=f"created={len(outcome.created)}",
            )
            check(
                "8b. hierarchy survives the import",
                s.query(m.BankAccountingClassification).filter_by(code="TEST-4100").one().parent_id
                == s.query(m.BankAccountingClassification).filter_by(code="TEST-4000").one().id,
            )
            generated = wci.apply_import(s, first)
            s.commit()
            marked = s.query(m.BankAccountingClassification).filter(
                m.BankAccountingClassification.code.startswith(wci.GENERATED_CODE_PREFIX)
            ).all()
            check(
                "8c. a generated code is recorded AND marked as generated in the row itself",
                len(generated.created) == 3 and len(marked) == 3
                and all(wci.GENERATED_CODE_MARKER in (row.description or "") for row in marked),
                detail=f"created={len(generated.created)} marked={len(marked)}",
            )

            # Everything imported so far is the new baseline for the
            # idempotence checks below.
            after_imports = s.query(m.BankAccountingClassification).count()
            again = wci.apply_import(s, wci.parse(CSV_PLAN, file_name="plan.csv"))
            s.commit()
            check(
                "9. re-importing the same catalog changes nothing",
                not again.created and len(again.unchanged) == 6
                and s.query(m.BankAccountingClassification).count() == after_imports,
            )

            conflicting = wci.parse(
                b"Statement Type,Code,Name\nP&L,TEST-4000,Something completely different\n",
                file_name="conflict.csv",
            )
            conflict_outcome = wci.apply_import(s, conflicting)
            s.commit()
            check(
                "10. a code that already means something else is a conflict, not an overwrite",
                conflict_outcome.has_conflicts
                and s.query(m.BankAccountingClassification).filter_by(code="TEST-4000").one().name
                == "Revenue",
            )

            raises(
                "11. a file that cannot be read imports nothing",
                lambda: wci.apply_import(s, wci.parse(b"", file_name="empty.csv")),
                "cannot be imported",
            )
            check(
                "11b. no synthetic What is created when a plan is unusable",
                s.query(m.BankAccountingClassification).count() == after_imports,
            )

            # =============================================================
            # 12. Why requires a What
            # =============================================================
            cogs = s.query(m.BankAccountingClassification).filter_by(code="TEST-5100").one()
            payable = s.query(m.BankAccountingClassification).filter_by(code="TEST-2100").one()
            raises(
                "12. a Why cannot exist without a What",
                lambda: classification_service.create_transaction_reason(
                    s, code="ORPHAN", name="Orphan", accounting_classification_id=None,
                ),
                "requires a What",
            )
            food_why = classification_service.create_transaction_reason(
                s, code="FOOD_PURCHASE", name="Food purchase",
                accounting_classification_id=cogs.id,
            )
            ap_why = classification_service.create_transaction_reason(
                s, code="AP_SETTLEMENT", name="Supplier invoice settlement",
                accounting_classification_id=payable.id,
            )
            s.commit()

            # =============================================================
            # 13-17. Candidates
            # =============================================================
            entity = m.LegalEntity(legal_name="Bootstrap LLC", status="ACTIVE")
            s.add(entity)
            s.flush()
            checking = m.PaymentInstrument(
                legal_entity_id=entity.id, instrument_type="BANK_ACCOUNT",
                display_name="Checking", institution="CHASE", last_four="0001",
                currency="USD",
            )
            paypal = m.PaymentInstrument(
                legal_entity_id=entity.id, instrument_type="PAYPAL",
                display_name="PayPal", currency="USD",
            )
            s.add_all([checking, paypal])
            s.flush()
            paypal.linked_instrument_id = checking.id
            card = m.PaymentInstrument(
                legal_entity_id=None, instrument_type="CREDIT_CARD",
                display_name="Card", institution="CHASE", last_four="1057",
            )
            s.add(card)
            s.flush()
            cards.assign_settlement_account(
                s, credit_card_payment_instrument_id=card.id,
                settlement_bank_account_id=checking.id, valid_from=date(2026, 1, 1),
            )
            s.commit()

            def txn(instrument, day, amount, description, month=5):
                row = m.FinancialTransaction(
                    payment_instrument_id=instrument.id, bank_source="CHASE_BANK_ACCOUNT",
                    posting_date=date(2026, month, day), description_original=description,
                    description_normalized=description.upper(), amount_minor=amount,
                    status="COMPLETED", duplicate_status="NONE", review_status="REQUIRES_REVIEW",
                )
                s.add(row)
                s.flush()
                return row

            a1 = txn(checking, 1, -10000, "US FOODS INC #4821")
            a2 = txn(checking, 2, -20000, "US Foods Inc. *4821")   # same payee once normalized
            b1 = txn(checking, 3, -5000, "PUBLIX 1488")
            b2 = txn(checking, 4, -6000, "PUBLIX 1661")            # similar, NOT the same
            copy = txn(card, 1, -10000, "US FOODS INC #4821")      # accounting duplicate of a1
            transfer_out = txn(checking, 9, -7000, "ONLINE TRANSFER")
            transfer_in = m.FinancialTransaction(
                payment_instrument_id=paypal.id, posting_date=date(2026, 5, 9),
                description_original="ONLINE TRANSFER", description_normalized="ONLINE TRANSFER",
                amount_minor=7000, status="COMPLETED", duplicate_status="NONE",
                external_transaction_id="PP-TRANSFER-1",
            )
            s.add(transfer_in)
            s.flush()
            s.commit()

            accounting_dedup.recompute_accounting_dedup(s)
            s.commit()

            from rfone_data_store.bank_reconciliation import matching
            matching.confirm_match(s, transfer_out.id, transfer_in.id, confirmed_by="tester")
            s.commit()

            candidates = rc.build_candidates(s)
            by_payee = {c.payee_normalized: c for c in candidates}

            check(
                "16. transactions with the same exact normalized payee form ONE group",
                "US FOODS INC 4821" in by_payee
                and by_payee["US FOODS INC 4821"].transaction_count == 2
                and set(by_payee["US FOODS INC 4821"].transaction_ids) == {a1.id, a2.id},
                detail=str(sorted(by_payee)),
            )
            check(
                "14. the suppressed accounting copy is not a candidate of its own",
                copy.accounting_status == accounting_dedup.DUPLICATE_SUPPRESSED
                and copy.id not in by_payee["US FOODS INC 4821"].transaction_ids,
            )
            check(
                "15. a confirmed internal transfer is excluded entirely",
                "ONLINE TRANSFER" not in by_payee,
            )
            check(
                "13. only canonical transactions are represented",
                all(
                    s.get(m.FinancialTransaction, tid).accounting_status
                    == accounting_dedup.CANONICAL
                    for c in candidates for tid in c.transaction_ids
                ),
            )
            check(
                "17. similar descriptions are suggested, never merged",
                "PUBLIX 1488" in by_payee and "PUBLIX 1661" in by_payee
                and by_payee["PUBLIX 1488"].similar
                and by_payee["PUBLIX 1488"].similar[0].payee_normalized == "PUBLIX 1661",
            )
            check(
                "17b. the suggestion explains itself",
                "numeric" in by_payee["PUBLIX 1488"].similar[0].reason.lower(),
            )
            check(
                "the group reports period, totals, company and instrument",
                by_payee["US FOODS INC 4821"].first_date == date(2026, 5, 1)
                and by_payee["US FOODS INC 4821"].total_minor == -30000
                and by_payee["US FOODS INC 4821"].absolute_total_minor == 30000
                and "Bootstrap LLC" in by_payee["US FOODS INC 4821"].legal_entity_names,
            )

            # =============================================================
            # 18-27. Approval
            # =============================================================
            supplier_type = m.BankOccurrenceType(code="SUPPLIER", name="Supplier")
            s.add(supplier_type)
            s.commit()

            # BANK_CANONICAL_WHY_AND_WHO_RELATIONSHIPS_001 §20 — a Who may now
            # be CREATED with zero Whys, so the refusal no longer comes from
            # `create_occurrence`. The property this check exists for is
            # unchanged and still enforced: bulk approval resolves the chain
            # BEFORE writing any decision row, and a Who that cannot resolve a
            # What stops the whole operation.
            raises(
                "26. an incomplete Who is refused BEFORE anything is written",
                lambda: rc.approve_candidates(
                    s, payee_keys=["DEBIT|US FOODS INC 4821"],
                    new_occurrence_name="Broken", occurrence_type_id=supplier_type.id,
                    default_transaction_reason_id=None,
                ),
                "has no default Why",
            )
            s.rollback()
            check(
                "26b. the refused approval classified nothing",
                s.query(m.BankTransactionExplanation).filter(
                    m.BankTransactionExplanation.decision_source == "HUMAN"
                ).count() == 0,
            )

            outcome = rc.approve_candidates(
                s, payee_keys=["DEBIT|US FOODS INC 4821"],
                new_occurrence_name="US Foods", occurrence_type_id=supplier_type.id,
                default_transaction_reason_id=food_why.id, learn_description=True,
            )
            s.commit()
            check(
                "18. approving a candidate creates the Who and classifies the whole group",
                outcome.transactions_classified == 2
                and s.query(m.BankOccurrence).filter_by(canonical_name="US Foods").count() == 1,
            )
            check(
                "21. Why and What are derived from the Who, not chosen per transaction",
                all(
                    e.transaction_reason_id == food_why.id
                    and e.accounting_classification_code_snapshot == "TEST-5100"
                    for e in s.query(m.BankTransactionExplanation).filter(
                        m.BankTransactionExplanation.financial_transaction_id.in_([a1.id, a2.id]),
                        m.BankTransactionExplanation.decision_source == "HUMAN",
                    ).all()
                ),
            )
            # These transactions were created directly rather than imported,
            # so approval writes their FIRST decision — the append-only
            # property is asserted by adding a second one and checking the
            # first survives untouched beside it.
            first_decision = recognition.get_current_explanation(
                s, financial_transaction_id=a1.id,
            )
            check(
                "22. the decision carries the full Who/Why/What snapshot",
                first_decision.occurrence_name_snapshot == "US Foods"
                and first_decision.transaction_reason_name_snapshot == "Food purchase"
                and first_decision.accounting_classification_code_snapshot == "TEST-5100"
                and first_decision.accounting_statement_type_snapshot == wci.PROFIT_LOSS,
            )
            count_before_second = s.query(m.BankTransactionExplanation).filter_by(
                financial_transaction_id=a1.id
            ).count()
            recognition.reclassify_transaction(
                s, transaction_id=a1.id, confirmed_by_account_id=None,
            )
            s.commit()
            s.refresh(first_decision)
            check(
                "22b. a further decision APPENDS — the earlier row is untouched",
                s.query(m.BankTransactionExplanation).filter_by(
                    financial_transaction_id=a1.id
                ).count() == count_before_second + 1
                and first_decision.decision_status == "HUMAN_CONFIRMED"
                and first_decision.accounting_classification_code_snapshot == "TEST-5100",
            )
            check(
                "23. an exact-match rule is recorded for future imports",
                len(outcome.rules_created) == 1
                and s.query(m.BankRecognitionRule).filter_by(
                    normalized_pattern="US FOODS INC 4821",
                    match_type=recognition.EXACT_NORMALIZED_DESCRIPTION,
                ).count() == 1,
            )
            check(
                "34. the suppressed copy was NOT classified",
                recognition.get_current_explanation(s, financial_transaction_id=copy.id) is None
                or recognition.get_current_explanation(
                    s, financial_transaction_id=copy.id
                ).decision_source != "HUMAN",
            )
            check(
                "27. the group is now ASSIGNED and out of the unclassified list",
                {c.payee_normalized for c in rc.build_candidates(s, include_assigned=False)}
                .isdisjoint({"US FOODS INC 4821"}),
            )

            # 19-20. An existing Who, several groups at once.
            us_foods = s.query(m.BankOccurrence).filter_by(canonical_name="US Foods").one()
            multi = rc.approve_candidates(
                s, payee_keys=["DEBIT|PUBLIX 1488", "DEBIT|PUBLIX 1661"],
                occurrence_id=us_foods.id, learn_description=True,
            )
            s.commit()
            check(
                "19/20. several groups can be approved onto one EXISTING Who in one operation",
                multi.occurrence_id == us_foods.id
                and multi.transactions_classified == 2
                and len(multi.payees) == 2,
            )

            # 25. A human decision is never overwritten.
            other_who = classification_service.create_occurrence(
                s, canonical_name="Sysco", occurrence_type_id=supplier_type.id,
                default_transaction_reason_id=ap_why.id,
            )
            s.commit()
            before = recognition.get_current_explanation(s, financial_transaction_id=b1.id)
            again = rc.approve_candidates(
                s, payee_keys=["DEBIT|PUBLIX 1488"], occurrence_id=other_who.id,
                learn_description=False,
            )
            s.commit()
            after = recognition.get_current_explanation(s, financial_transaction_id=b1.id)
            check(
                "25. a transaction a human already decided is skipped, never overwritten",
                again.transactions_skipped_human == 1
                and again.transactions_classified == 0
                and after.id == before.id,
            )

            # 24. Contradiction -> ambiguous, never an automatic choice.
            c1 = txn(checking, 15, -1000, "AMBIGUOUS MERCHANT")
            c2 = txn(checking, 16, -1000, "AMBIGUOUS MERCHANT")
            s.commit()
            accounting_dedup.recompute_accounting_dedup(s)
            s.commit()
            recognition.record_human_decision(
                s, recognition.HumanDecisionRequest(
                    transaction_id=c1.id, occurrence_id=us_foods.id,
                    confirmed_by_account_id=None, learn_description=False,
                ),
            )
            recognition.record_human_decision(
                s, recognition.HumanDecisionRequest(
                    transaction_id=c2.id, occurrence_id=other_who.id,
                    confirmed_by_account_id=None, learn_description=False,
                ),
            )
            s.commit()
            ambiguous = {
                c.payee_normalized: c for c in rc.build_candidates(s)
            }.get("AMBIGUOUS MERCHANT")
            check(
                "24. two different Who values for one payee produce AMBIGUOUS, never a guess",
                ambiguous is not None and ambiguous.status == rc.STATUS_AMBIGUOUS
                and ambiguous.suggested_occurrence_id is None,
            )
            raises(
                "24b. an ambiguous group cannot be bulk-approved",
                lambda: rc.approve_candidates(
                    s, payee_keys=["DEBIT|AMBIGUOUS MERCHANT"], occurrence_id=us_foods.id,
                ),
                "ambiguous",
            )

            # 33. Nothing was destroyed.
            check(
                "33. no raw row and no transaction was created or deleted by classification",
                s.query(m.RawBankTransaction).count() == 0
                and s.query(m.FinancialTransaction).count() == 9,
                detail=str(s.query(m.FinancialTransaction).count()),
            )
            summary = rc.summary(s)
            check(
                "27b. the summary counts groups and transactions consistently",
                summary["groups"] == len(rc.build_candidates(s))
                and summary["suppressed_copies"] == 1,
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
