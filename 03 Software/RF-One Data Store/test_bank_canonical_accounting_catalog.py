#!/usr/bin/env python
"""The canonical RF-One restaurant accounting catalog
(BANK_CANONICAL_ACCOUNTING_CATALOG_001).

Proves the catalog itself — seeded, idempotent, structurally sound, free
of people and vendors — and the accounting rules that depend on it: that
sales tax, tips, card settlements, internal transfers and loan advances
produce no P&L effect, that a mixed supplier is never auto-classified, and
that every derived P&L total is computed from the hierarchy rather than
from a fake posting account.

Never touches AWS, RDS, a production database, or a real bank file.
"""

from __future__ import annotations

import sys
from datetime import date

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import accounting_dedup
from rfone_data_store.bank_reconciliation import canonical_catalog as cc
from rfone_data_store.bank_reconciliation import classification as classification_service
from rfone_data_store.bank_reconciliation import deterministic_rules as dr
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

PL = wci.PROFIT_LOSS
BS = wci.BALANCE_SHEET

# Names that must never appear as an account. People are WHO; shops are WHO.
FORBIDDEN_IN_CATALOG = (
    "anthony", "walter", "diego", "elia", "tatiana", "ceban", "pino", "giovanna",
    "costco", "publix", "instacart", "amazon", "sam's", "sams club", "cheney",
    "prime line", "walgreens", "geico", "acura", "mazda", "nissan",
    "gross profit", "prime cost", "ebitda", "operating profit", "net income",
    "net revenue", "total cogs", "total labor",
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

    url = resolve_test_database_url("bank_canonical_accounting_catalog")
    print(f"Database URL: {redact_database_url(url)}")
    run_migrations_to_head(url)
    engine = create_configured_engine(url)

    try:
        session_factory = create_session_factory(engine)
        with session_factory() as s:
            # =============================================================
            # 1-7. The catalog itself
            # =============================================================
            rows = s.query(m.BankAccountingClassification).all()
            check(
                "1. the canonical catalog is seeded by the ordinary migration",
                len(rows) == 134, detail=f"{len(rows)} accounts",
            )
            by_code = {row.code: row for row in rows}

            outcome = cc.seed(s)
            s.commit()
            check(
                "2/3. re-seeding creates nothing and changes nothing",
                not outcome.created and len(outcome.unchanged) == 134
                and s.query(m.BankAccountingClassification).count() == 134,
            )

            codes = [row.code for row in rows]
            check("4. accounting codes are unique", len(codes) == len(set(codes)))

            renamed = by_code["7210"]
            original_name = renamed.name
            renamed.name = "Deliberately different"
            s.commit()
            conflicted = False
            try:
                cc.seed(s)
            except ValueError as exc:
                conflicted = "conflict" in str(exc).lower() or "7210" in str(exc)
            s.rollback()
            renamed.name = original_name
            s.commit()
            check("5. a code that already means something else fails loudly", conflicted)
            check(
                "5b. the conflicting account was not overwritten",
                s.query(m.BankAccountingClassification).filter_by(code="7210").one().name
                == original_name,
            )

            check(
                "6. every account is Profit & Loss or Balance Sheet",
                all(row.statement_type in (PL, BS) for row in rows),
            )
            problems = cc.validate_hierarchy(s)
            check("7. the hierarchy validates", not problems, detail="; ".join(problems[:3]))
            check(
                "7b. the eight canonical roots exist and are top level",
                {row.code for row in rows if row.parent_id is None}
                == {"1000", "2000", "3000", "4000", "5000", "6000", "7000", "8000"},
            )

            # =============================================================
            # 8-16. Specific accounts land where accounting requires
            # =============================================================
            for code, statement, label in (
                ("2100", BS, "8. Accounts Payable"),
                ("2200", BS, "9. Sales Tax Payable"),
                ("2300", BS, "10. Tips Payable"),
                ("2500", BS, "11. Credit Cards Payable"),
                ("7210", PL, "12. Merchant Processing Fees"),
                ("7230", PL, "13. Foreign Transaction Fees"),
                ("7640", PL, "14. Corporate / Management Fees"),
            ):
                check(
                    f"{label} is {statement}",
                    by_code[code].statement_type == statement,
                    detail=by_code[code].statement_type,
                )
            check(
                "11b. the three liabilities sit under Liabilities, not under an expense group",
                all(by_code[c].parent_id == by_code["2000"].id for c in ("2100", "2200", "2300", "2500")),
            )
            check(
                "12b. the fee accounts sit under Operating Expenses, never under COGS",
                cc.subtree_codes(s, "7000") >= {"7210", "7220", "7230", "7640"}
                and not (cc.subtree_codes(s, "5000") & {"7210", "7640"}),
            )

            cogs = cc.subtree_codes(s, "5000")
            check(
                "15. 5100-5400 all belong to the COGS subtree",
                {"5100", "5200", "5210", "5220", "5230", "5240", "5300", "5400"} <= cogs,
            )
            labor = cc.subtree_codes(s, "6000")
            check(
                "16. the 6000 range all belongs to Labor",
                {"6110", "6120", "6210", "6220", "6310", "6400", "6500",
                 "6600", "6700", "6800", "6900"} <= labor,
            )
            check(
                "16b. COGS and Labor do not overlap",
                not (cogs & labor),
            )

            # =============================================================
            # 17-18. No people, no vendors, no calculated totals
            # =============================================================
            names = " | ".join(row.name.lower() for row in rows)
            offenders = [token for token in FORBIDDEN_IN_CATALOG if token in names]
            check(
                "17/18. no employee name, vendor name or calculated total is an account",
                not offenders, detail=str(offenders),
            )

            # =============================================================
            # Fixtures for the classification rules
            # =============================================================
            entity = m.LegalEntity(legal_name="Canonical LLC", status="ACTIVE")
            s.add(entity)
            s.flush()
            checking = m.PaymentInstrument(
                legal_entity_id=entity.id, instrument_type="BANK_ACCOUNT",
                display_name="Checking", institution="CHASE", last_four="0001", currency="USD",
            )
            s.add(checking)
            s.flush()
            kind = m.BankOccurrenceType(code="COUNTERPARTY", name="Counterparty")
            s.add(kind)
            s.flush()

            def account_why(code, why_code, why_name):
                why = s.query(m.BankTransactionReason).filter_by(code=why_code).first()
                if why is None:
                    why = classification_service.create_transaction_reason(
                        s, code=why_code, name=why_name,
                        accounting_classification_id=by_code[code].id,
                    )
                return why

            def who_for(name, why):
                return classification_service.create_occurrence(
                    s, canonical_name=name, occurrence_type_id=kind.id,
                    default_transaction_reason_id=why.id,
                )

            def txn(day, amount, description):
                row = m.FinancialTransaction(
                    payment_instrument_id=checking.id, bank_source="CHASE_BANK_ACCOUNT",
                    posting_date=date(2026, 5, day), description_original=description,
                    description_normalized=description.upper(), amount_minor=amount,
                    status="COMPLETED", duplicate_status="NONE", review_status="REQUIRES_REVIEW",
                )
                s.add(row)
                s.flush()
                return row

            # =============================================================
            # 19-23. Cash movements that must not touch the P&L
            # =============================================================
            cases = [
                ("2200", "SALES_TAX", "Sales tax remitted to the state",
                 "FLA DEPT REVENUE SALES TAX", "19. sales tax remittance"),
                ("2300", "TIPS_SETTLEMENT", "Guest tips paid out to staff",
                 "TIP PAYOUT SETTLEMENT", "20. tip settlement"),
                ("2500", "CARD_SETTLEMENT", "Credit card statement paid",
                 "PAYMENT THANK YOU WEB", "21. credit-card payment"),
                ("1110", "INTERNAL_TRANSFER", "Money moved between own accounts",
                 "ONLINE TRANSFER TO CHK 3583", "22. internal transfer"),
                ("2600", "LOAN_ADVANCE", "Loan principal advanced",
                 "CREDIT MEMORANDUM ADVANCE ON LOAN", "23. loan advance"),
            ]
            pl_codes = cc.subtree_codes(s, "4000") | cc.subtree_codes(s, "5000") \
                | cc.subtree_codes(s, "6000") | cc.subtree_codes(s, "7000") \
                | cc.subtree_codes(s, "8000")

            for index, (code, why_code, why_name, description, label) in enumerate(cases, start=1):
                why = account_why(code, why_code, why_name)
                who = who_for(f"Counterparty {why_code}", why)
                row = txn(index, -1000 if index != 5 else 3000000, description)
                s.commit()
                accounting_dedup.recompute_accounting_dedup(s)
                s.commit()
                decision = recognition.record_human_decision(
                    s, recognition.HumanDecisionRequest(
                        transaction_id=row.id, occurrence_id=who.id,
                        confirmed_by_account_id=None, learn_description=False,
                    ),
                )
                s.commit()
                check(
                    f"{label} classifies to a Balance Sheet account, so it has NO P&L effect",
                    decision.accounting_statement_type_snapshot == BS
                    and decision.accounting_classification_code_snapshot == code
                    and code not in pl_codes,
                    detail=str(decision.accounting_classification_code_snapshot),
                )

            check(
                "23b. a loan advance is never Revenue",
                "2600" not in cc.subtree_codes(s, "4000"),
            )

            # =============================================================
            # 24-25. Deterministic recognition and its refusals
            # =============================================================
            check(
                "25. a foreign transaction fee is recognised deterministically as 7230",
                (dr.match("FOREIGN TRANSACTION FEE") or None)
                and dr.match("FOREIGN TRANSACTION FEE").account_code == "7230",
            )
            for supplier in (
                "COSTCO WHOLESALE 1234", "SAMS CLUB COM", "IC INSTACART",
                "AMAZON MKTPL 5Q4M20ZT1", "PUBLIX 1488", "CHENEY BROTHERS",
                "PRIME LINE DISTRIBUTORS",
            ):
                check(
                    f"24. {supplier.split()[0]} is never auto-classified to COGS",
                    dr.match(supplier) is None and dr.is_mixed_supplier(supplier),
                )
            check(
                "24b. an unrecognised description is REVIEW_REQUIRED, never Miscellaneous",
                dr.match("SOME SHOP NOBODY CONFIGURED") is None,
            )
            check(
                "24c. the review-sensitive accounts are never a rule destination",
                not (
                    {rule.account_code for rule in dr.DETERMINISTIC_RULES}
                    & set(cc.REVIEW_SENSITIVE_CODES)
                ),
            )
            check(
                "historical Kermali mappings point only at real canonical accounts",
                all(code in by_code for code in dr.HISTORICAL_COST_TYPE_MAP.values()),
            )
            check(
                "ambiguous historical cost types are reported, never mapped",
                "Company Cars" in dr.HISTORICAL_UNRESOLVED
                and "Incoming" in dr.HISTORICAL_UNRESOLVED
                and "Personal Deductable" in dr.HISTORICAL_UNRESOLVED
                and not (set(dr.HISTORICAL_UNRESOLVED) & set(dr.HISTORICAL_COST_TYPE_MAP)),
            )

            # =============================================================
            # 26-28. Existing behaviour is untouched
            # =============================================================
            original = txn(20, -5000, "DUPLICATED MOVEMENT")
            copy = txn(20, -5000, "DUPLICATED MOVEMENT")
            s.commit()
            accounting_dedup.recompute_accounting_dedup(s)
            s.commit()
            check(
                "26. duplicate suppression still behaves as before",
                original.accounting_status == accounting_dedup.CANONICAL
                and copy.accounting_status == accounting_dedup.DUPLICATE_SUPPRESSED,
            )
            check(
                "27. a suppressed copy is not offered for classification",
                copy.id not in {
                    tid for c in rc.build_candidates(s) for tid in c.transaction_ids
                },
            )

            protected = txn(21, -7777, "HUMAN DECIDED MOVEMENT")
            s.commit()
            accounting_dedup.recompute_accounting_dedup(s)
            s.commit()
            why = account_why("7810", "CLEANING", "Recurring restaurant cleaning service")
            keeper = who_for("Get Better Cleaning", why)
            first = recognition.record_human_decision(
                s, recognition.HumanDecisionRequest(
                    transaction_id=protected.id, occurrence_id=keeper.id,
                    confirmed_by_account_id=None, learn_description=False,
                ),
            )
            s.commit()
            other_why = account_why("7880", "MISC", "Unclassified residual")
            other = who_for("Someone Else", other_why)
            again = rc.approve_candidates(
                s, payee_keys=["DEBIT|HUMAN DECIDED MOVEMENT"],
                occurrence_id=other.id, learn_description=False,
            )
            s.commit()
            check(
                "28. an existing human decision is never overwritten",
                again.transactions_skipped_human == 1
                and again.transactions_classified == 0
                and recognition.get_current_explanation(
                    s, financial_transaction_id=protected.id
                ).id == first.id,
            )

            # 29. The importer preview still writes nothing.
            before_count = s.query(m.BankAccountingClassification).count()
            wci.parse(
                b"Statement Type,Code,Name\nP&L,9999,Preview Only\n", file_name="preview.csv",
            )
            check(
                "29. the What importer preview performs no writes",
                s.query(m.BankAccountingClassification).count() == before_count,
            )

            # =============================================================
            # Derived P&L presentation — computed, never stored
            # =============================================================
            revenue = cc.subtree_codes(s, "4000")
            contra = set(cc.CONTRA_REVENUE_CODES)
            check(
                "the contra-revenue accounts are inside Revenue and identified as contra",
                contra <= revenue and all(by_code[c].statement_type == PL for c in contra),
            )
            derived = {
                "Net Revenue": (revenue - contra, contra),
                "Total COGS": (cc.subtree_codes(s, "5000"), set()),
                "Total Labor": (cc.subtree_codes(s, "6000"), set()),
                "Total Operating Expenses": (cc.subtree_codes(s, "7000"), set()),
                "Other Income / Expense": (cc.subtree_codes(s, "8000"), set()),
            }
            check(
                "every derived P&L total resolves to a real subtree, none of them empty",
                all(codes for codes, _ in derived.values()),
            )
            check(
                "Prime Cost is COGS + Labor, two real subtrees and no stored total",
                len(derived["Total COGS"][0] | derived["Total Labor"][0])
                == len(derived["Total COGS"][0]) + len(derived["Total Labor"][0]),
            )
            check(
                "Depreciation & Amortization is a real account inside Other, so Operating "
                "Profit before D&A is computable",
                "8300" in derived["Other Income / Expense"][0],
            )
            check(
                "no derived report total exists as a posting account",
                not any(
                    row.name.lower() in (
                        "net revenue", "gross profit", "prime cost", "total cogs",
                        "total labor", "operating profit", "net income", "ebitda",
                    ) for row in rows
                ),
            )

            # Posting vs group, derived from the hierarchy.
            check(
                "a group node is identifiable as non-postable",
                not cc.is_posting_account(s, by_code["7000"])
                and cc.is_posting_account(s, by_code["7230"]),
            )
            check(
                "the missing model capabilities are reported rather than invented",
                len(cc.MISSING_MODEL_CAPABILITIES) == 3
                and {name for name, _ in cc.MISSING_MODEL_CAPABILITIES}
                == {"node_type", "contra", "review_sensitive"},
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
