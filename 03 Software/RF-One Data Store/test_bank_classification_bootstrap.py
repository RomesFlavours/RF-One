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
* a WHO decision never applying the Who's default Why, a Why decision
  writing the full Who/Why/What snapshot, decisions appending and never
  rewriting.

BANK_OLD_RULES_REMOVAL_001: the receiver-candidate checks (13-20, 23-27,
24b, 26b, 27b, 34 — grouping, bulk approval, learned exact rules,
ambiguity, the candidate summary) went with the old rule system. Check 21
now uses the WHO step of the Bank Review. Check 22c ("a human decision
learns no recognition rule") was then retired too, at migration
d2b6f8a4c0e7, when the recognition-rule table itself was dropped — the
invariant now holds by construction. The other numbers are unchanged.

Never touches AWS, RDS, a production database, or a real bank file.
"""

from __future__ import annotations

import io
import sys
from datetime import date

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import accounting_dedup
from rfone_data_store.bank_reconciliation import classification as classification_service
from rfone_data_store.bank_reconciliation import recognition
from rfone_data_store.bank_reconciliation import service
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
            # BANK_WHY_WITHOUT_WHAT_001: Bank reconciliation needs WHO + WHY; a
            # Why may exist without a What, and none is invented for it.
            pending_why = classification_service.create_transaction_reason(
                s, code="PENDING_BOOKKEEPING", name="Pending bookkeeping", accounting_classification_id=None,
            )
            check("12. a Why may exist without a What (no destination is invented)",
                  pending_why.id is not None and pending_why.accounting_classification_id is None)
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
            # 13-20, 23-27, 34. Receiver candidates and their approval went
            # with BANK_OLD_RULES_REMOVAL_001 (the receiver-candidate list,
            # bulk approval, learned exact rules and ambiguity detection
            # belonged to the old rule system).
            # =============================================================
            entity = m.LegalEntity(legal_name="Bootstrap LLC", status="ACTIVE")
            s.add(entity)
            s.flush()
            checking = m.PaymentInstrument(
                legal_entity_id=entity.id, instrument_type="BANK_ACCOUNT",
                display_name="Checking", institution="CHASE", last_four="0001",
                currency="USD",
            )
            s.add(checking)
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
            a2 = txn(checking, 2, -20000, "US Foods Inc. *4821")
            s.commit()
            accounting_dedup.recompute_accounting_dedup(s)
            s.commit()

            supplier_type = m.BankOccurrenceType(code="SUPPLIER", name="Supplier")
            s.add(supplier_type)
            s.commit()
            us_foods_who = classification_service.create_occurrence(
                s, canonical_name="US Foods", occurrence_type_id=supplier_type.id,
                default_transaction_reason_id=food_why.id,
            )
            s.commit()

            # 21. A person names the WHO only (the Bank Review WHO step).
            for row in (a1, a2):
                service.record_recognition_decision(
                    s, transaction_id=row.id, occurrence_id=us_foods_who.id,
                    confirmed_by_account_id=None,
                )
            s.commit()
            # BANK_FINAL_RELEASE_BLOCKERS_001 — the Why and What are never
            # derived from the Who: "US FOODS INC 4821" names a supplier, not
            # what was bought.
            who_rows = s.query(m.BankTransactionExplanation).filter(
                m.BankTransactionExplanation.financial_transaction_id.in_([a1.id, a2.id]),
                m.BankTransactionExplanation.decision_source == "HUMAN",
            ).all()
            check(
                "21. a WHO decision records the Who; the Who's default Why is NOT applied",
                len(who_rows) == 2
                and all(
                    e.occurrence_name_snapshot == "US FOODS"
                    and e.transaction_reason_id is None
                    and e.accounting_classification_code_snapshot is None
                    for e in who_rows
                ),
            )
            check(
                "21b. ...and those transactions stay in review until their Why is decided",
                all(s.get(m.FinancialTransaction, t).review_status != "REVIEWED"
                    for t in (a1.id, a2.id)),
            )
            # The append-only property is asserted by adding further decisions
            # and checking the first survives untouched beside them.
            first_decision = recognition.get_current_explanation(
                s, financial_transaction_id=a1.id,
            )
            why_decision = recognition.record_human_decision(
                s, recognition.HumanDecisionRequest(
                    transaction_id=a1.id, occurrence_id=us_foods_who.id,
                    transaction_reason_id=food_why.id,
                    confirmed_by_account_id=None, ),
            )
            s.commit()
            check(
                "22. the person's Why decision carries the full Who/Why/What snapshot",
                why_decision.occurrence_name_snapshot == "US FOODS"
                and why_decision.transaction_reason_name_snapshot == "Food purchase"
                and why_decision.accounting_classification_code_snapshot == "TEST-5100"
                and why_decision.accounting_statement_type_snapshot == wci.PROFIT_LOSS,
            )
            check(
                "22a. the Who-only row was left as it was",
                first_decision.occurrence_name_snapshot == "US FOODS"
                and first_decision.transaction_reason_id is None
                and first_decision.accounting_classification_code_snapshot is None,
            )
            count_before_second = s.query(m.BankTransactionExplanation).filter_by(
                financial_transaction_id=a1.id
            ).count()
            recognition.reclassify_transaction(
                s, transaction_id=a1.id, confirmed_by_account_id=None,
            )
            s.commit()
            s.refresh(first_decision)
            s.refresh(why_decision)
            check(
                "22b. a further decision APPENDS — the earlier rows are untouched",
                s.query(m.BankTransactionExplanation).filter_by(
                    financial_transaction_id=a1.id
                ).count() == count_before_second + 1
                and first_decision.transaction_reason_id is None
                and why_decision.decision_status == "HUMAN_CONFIRMED"
                and why_decision.accounting_classification_code_snapshot == "TEST-5100",
            )
            # 22c (no recognition rule learned) was retired with
            # BANK_OLD_RULES_REMOVAL_001: the table no longer exists, so the
            # invariant holds by construction.

            # 33. Nothing was destroyed.
            check(
                "33. no raw row and no transaction was created or deleted by classification",
                s.query(m.RawBankTransaction).count() == 0
                and s.query(m.FinancialTransaction).count() == 2,
                detail=str(s.query(m.FinancialTransaction).count()),
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
