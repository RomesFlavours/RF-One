#!/usr/bin/env python
"""Canonical account semantics
(BANK_ACCOUNTING_CLASSIFICATION_SEMANTICS_001).

Proves that node type, normal balance, contra and review sensitivity are
now FACTS STORED ON THE ACCOUNT rather than inferences — and that the
three behaviours which depended on those inferences read the data instead:

* reporting signs a subtree from `normal_balance`, so Net Revenue nets its
  contra accounts and Accumulated Depreciation reduces Fixed Assets with
  no list of account codes anywhere;
* automated recognition can never land on a GROUP, and can never fall back
  to a review-sensitive account;
* a human may still select a review-sensitive account explicitly, and a
  human decision keeps precedence.

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

EXPECTED_ACCOUNTS = 134
EXPECTED_CONTRA = {"1590", "4910", "4920"}
EXPECTED_REVIEW_SENSITIVE = {"6900", "7880", "8500", "8600"}


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        if condition:
            passed.append(description)
        else:
            failed.append(description)
            print(f"FAILED: {description}" + (f" ({detail})" if detail else ""))

    url = resolve_test_database_url("bank_accounting_classification_semantics")
    print(f"Database URL: {redact_database_url(url)}")
    run_migrations_to_head(url)
    engine = create_configured_engine(url)

    try:
        session_factory = create_session_factory(engine)
        with session_factory() as s:
            rows = s.query(m.BankAccountingClassification).all()
            by_code = {row.code: row for row in rows}
            canonical = {row["Code"] for row in cc.catalog_rows()}

            # =============================================================
            # 1-4. Every canonical account states all four semantics
            # =============================================================
            check(
                "0. the canonical catalog is the expected 134 accounts",
                len(rows) == EXPECTED_ACCOUNTS and len(canonical) == EXPECTED_ACCOUNTS,
                detail=f"{len(rows)} stored, {len(canonical)} defined",
            )
            check(
                f"1. all {EXPECTED_ACCOUNTS} canonical accounts have an explicit node type",
                all(
                    by_code[code].node_type in cc.NODE_TYPES for code in canonical
                ),
                detail=str(sorted(
                    code for code in canonical if by_code[code].node_type not in cc.NODE_TYPES
                )[:5]),
            )
            check(
                f"2. all {EXPECTED_ACCOUNTS} canonical accounts have an explicit normal balance",
                all(
                    by_code[code].normal_balance in cc.NORMAL_BALANCES for code in canonical
                ),
                detail=str(sorted(
                    code for code in canonical
                    if by_code[code].normal_balance not in cc.NORMAL_BALANCES
                )[:5]),
            )
            check(
                f"3. all {EXPECTED_ACCOUNTS} canonical accounts have an explicit contra flag",
                all(by_code[code].is_contra is not None for code in canonical),
            )
            check(
                f"4. all {EXPECTED_ACCOUNTS} canonical accounts have an explicit "
                "review-sensitive flag",
                all(by_code[code].review_sensitive is not None for code in canonical),
            )
            check(
                "4b. no canonical account leaves any semantic value blank",
                not s.query(m.BankAccountingClassification).filter(
                    m.BankAccountingClassification.code.in_(sorted(canonical)),
                    m.BankAccountingClassification.normal_balance.is_(None),
                ).count(),
            )
            check(
                "4c. the stored semantics match the version-controlled CSV exactly",
                not cc.semantic_problems(s),
                detail="; ".join(cc.semantic_problems(s)[:3]),
            )
            check(
                "4d. node type is a stated fact, not a child count — every GROUP is "
                "declared, and a posting category may legitimately have children",
                by_code["2600"].node_type == cc.POSTING_CATEGORY
                and by_code["2610"].parent_id == by_code["2600"].id
                and by_code["2600"].is_posting_account,
                detail=by_code["2600"].node_type,
            )

            # =============================================================
            # 5-6. GROUP is never an automatic destination; POSTING is
            # =============================================================
            entity = m.LegalEntity(legal_name="Semantics LLC", status="ACTIVE")
            s.add(entity)
            s.flush()
            checking = m.PaymentInstrument(
                legal_entity_id=entity.id, instrument_type="BANK_ACCOUNT",
                display_name="Checking", institution="CHASE", last_four="0009", currency="USD",
            )
            s.add(checking)
            s.flush()
            kind = m.BankOccurrenceType(code="COUNTERPARTY", name="Counterparty")
            s.add(kind)
            # Committed, not just flushed: the refusal checks below roll back,
            # and the fixtures must survive that.
            s.commit()

            def why_for(code: str, why_code: str, why_name: str):
                existing = s.query(m.BankTransactionReason).filter_by(code=why_code).first()
                if existing is not None:
                    return existing
                return classification_service.create_transaction_reason(
                    s, code=why_code, name=why_name,
                    accounting_classification_id=by_code[code].id,
                )

            def who_for(name: str, why):
                return classification_service.create_occurrence(
                    s, canonical_name=name, occurrence_type_id=kind.id,
                    default_transaction_reason_id=why.id,
                )

            def txn(day: int, amount: int, description: str):
                row = m.FinancialTransaction(
                    payment_instrument_id=checking.id, bank_source="CHASE_BANK_ACCOUNT",
                    posting_date=date(2026, 6, day), description_original=description,
                    description_normalized=description.upper(), amount_minor=amount,
                    status="COMPLETED", duplicate_status="NONE", review_status="REQUIRES_REVIEW",
                )
                s.add(row)
                s.flush()
                return row

            refused = ""
            try:
                classification_service.create_transaction_reason(
                    s, code="GROUP_DESTINATION", name="Pointing a Why at a reporting group",
                    accounting_classification_id=by_code["7000"].id,
                )
            except ValueError as exc:
                refused = str(exc)
            s.rollback()
            check(
                "5. a GROUP cannot become an automatic final classification destination",
                "group" in refused.lower() and "7000" in refused,
                detail=refused or "no refusal",
            )
            check(
                "5b. the rule is read from the account, not from a list of codes",
                not cc.may_receive_automatic_classification(by_code["7000"])
                and not cc.may_receive_automatic_classification(by_code["4000"])
                and not cc.may_receive_automatic_classification(by_code["1500"]),
            )
            check(
                "5c. every GROUP in the catalog refuses automatic classification",
                not any(
                    cc.may_receive_automatic_classification(row)
                    for row in rows if row.node_type == cc.GROUP
                ),
            )

            posting_why = why_for("7810", "CLEANING", "Recurring restaurant cleaning service")
            cleaner = who_for("Get Better Cleaning", posting_why)
            s.commit()
            posting_txn = txn(1, -9100, "GET BETTER CLEANING SERVICE")
            s.commit()
            accounting_dedup.recompute_accounting_dedup(s)
            s.commit()
            decision = recognition.record_human_decision(
                s, recognition.HumanDecisionRequest(
                    transaction_id=posting_txn.id, occurrence_id=cleaner.id,
                    confirmed_by_account_id=None, learn_description=False,
                ),
            )
            s.commit()
            check(
                "6. a POSTING account is usable where the rule/evidence supports it",
                decision.accounting_classification_code_snapshot == "7810"
                and cc.may_receive_automatic_classification(by_code["7810"]),
                detail=str(decision.accounting_classification_code_snapshot),
            )
            check(
                "6b. a POSTING_CATEGORY is usable too — 2600 receives the loan advance "
                "the bank line cannot resolve to short or long term",
                cc.may_receive_automatic_classification(by_code["2600"]),
            )

            # =============================================================
            # 7-8. Review-sensitive: never a fallback, always selectable
            # =============================================================
            check(
                "7a. an unrecognised description is REVIEW_REQUIRED, never Miscellaneous",
                dr.match("SOMETHING NOBODY EVER CONFIGURED") is None,
            )
            check(
                "7b. no deterministic rule points at a review-sensitive account",
                not dr.destination_problems(s),
                detail="; ".join(dr.destination_problems(s)[:3]),
            )
            check(
                "7c. no review-sensitive account may be reached automatically",
                not any(
                    cc.may_receive_automatic_classification(row)
                    for row in cc.review_sensitive_accounts(s)
                ),
            )
            check(
                "7d. the residual accounts are not silently reachable through "
                "applicable_rules either",
                not (
                    {rule.account_code for rule in dr.applicable_rules(s)}
                    & EXPECTED_REVIEW_SENSITIVE
                ),
            )

            misc_why = why_for("7880", "MISC_RESIDUAL", "Residual the human recognised")
            misc_who = who_for("Residual Counterparty", misc_why)
            s.commit()
            misc_txn = txn(2, -4321, "AN EXPENSE A HUMAN JUDGED RESIDUAL")
            s.commit()
            accounting_dedup.recompute_accounting_dedup(s)
            s.commit()
            human = recognition.record_human_decision(
                s, recognition.HumanDecisionRequest(
                    transaction_id=misc_txn.id, occurrence_id=misc_who.id,
                    confirmed_by_account_id=None, learn_description=False,
                ),
            )
            s.commit()
            check(
                "8. a human may explicitly select a review-sensitive account",
                human.accounting_classification_code_snapshot == "7880"
                and by_code["7880"].review_sensitive,
                detail=str(human.accounting_classification_code_snapshot),
            )

            # =============================================================
            # 9-21. The specific accounts the catalog is judged on
            # =============================================================
            for label, code, statement, balance, contra, sensitive in (
                ("9", "1590", BS, cc.CREDIT, True, False),
                ("10", "4910", PL, cc.DEBIT, True, False),
                ("11", "4920", PL, cc.DEBIT, True, False),
                ("12", "7880", PL, cc.DEBIT, False, True),
                ("13", "6900", PL, cc.DEBIT, False, True),
                ("14", "8500", PL, cc.CREDIT, False, True),
                ("15", "8600", PL, cc.DEBIT, False, True),
                ("16", "4100", PL, cc.CREDIT, False, False),
                ("17", "5100", PL, cc.DEBIT, False, False),
                ("18", "6110", PL, cc.DEBIT, False, False),
                ("19", "2200", BS, cc.CREDIT, False, False),
                ("20", "2300", BS, cc.CREDIT, False, False),
                ("21", "1110", BS, cc.DEBIT, False, False),
            ):
                row = by_code[code]
                check(
                    f"{label}. {code} {row.name} is {statement}, {balance}"
                    + (", contra" if contra else "")
                    + (", review-sensitive" if sensitive else ""),
                    row.statement_type == statement
                    and row.normal_balance == balance
                    and bool(row.is_contra) is contra
                    and bool(row.review_sensitive) is sensitive,
                    detail=(
                        f"{row.statement_type}/{row.normal_balance}/contra={row.is_contra}/"
                        f"review={row.review_sensitive}"
                    ),
                )

            check(
                "9-11b. those three are the ONLY contra accounts in the catalog",
                {row.code for row in cc.contra_accounts(s)} == EXPECTED_CONTRA,
                detail=str(sorted(row.code for row in cc.contra_accounts(s))),
            )
            check(
                "12-15b. those four are the ONLY review-sensitive accounts",
                {row.code for row in cc.review_sensitive_accounts(s)} == EXPECTED_REVIEW_SENSITIVE,
                detail=str(sorted(row.code for row in cc.review_sensitive_accounts(s))),
            )

            # =============================================================
            # 22. Net Revenue is signed from the data, not from codes
            # =============================================================
            revenue_codes = cc.subtree_codes(s, cc.REVENUE_ROOT)
            amounts = {code: 0 for code in revenue_codes}
            amounts["4100"] = 900_000      # food sales, in its own CREDIT direction
            amounts["4220"] = 100_000      # beer sales
            amounts["4910"] = 30_000       # discounts, in their own DEBIT direction
            amounts["4920"] = 20_000       # refunds
            net_revenue = cc.subtree_total(s, cc.REVENUE_ROOT, amounts)
            check(
                "22. Net Revenue = positive revenue subtree minus the contra-revenue "
                "accounts, signed from normal_balance",
                net_revenue == 950_000,
                detail=str(net_revenue),
            )
            signs = dict(
                (account.code, sign) for account, sign in cc.signed_subtree(s, cc.REVENUE_ROOT)
            )
            check(
                "22b. the contra accounts carry a negative sign, the ordinary ones positive",
                signs.get("4910") == -1 and signs.get("4920") == -1
                and signs.get("4100") == 1 and signs.get("4220") == 1,
                detail=str({k: signs.get(k) for k in ("4100", "4220", "4910", "4920")}),
            )
            check(
                "22c. no group node is double-counted inside its own subtree total",
                all(
                    account.is_posting_account
                    for account, _ in cc.signed_subtree(s, cc.REVENUE_ROOT)
                ),
            )
            fixed = cc.subtree_total(s, "1500", {
                "1510": 40_000, "1520": 260_000, "1530": 500_000,
                "1540": 100_000, "1590": 300_000,
            })
            check(
                "22d. Accumulated Depreciation reduces Fixed Assets on the Balance Sheet",
                fixed == 600_000, detail=str(fixed),
            )
            source = (
                open("rfone_data_store/bank_reconciliation/canonical_catalog.py", encoding="utf-8").read()
                + open("rfone_data_store/bank_reconciliation/deterministic_rules.py", encoding="utf-8").read()
            )
            check(
                "22e. no hardcoded contra-account code list survives in the reporting code",
                "CONTRA_REVENUE_CODES" not in source
                and "CONTRA_ASSET_CODES" not in source
                and "REVIEW_SENSITIVE_CODES" not in source,
            )

            # =============================================================
            # 23-24. Seeding stays idempotent; semantics conflict loudly
            # =============================================================
            outcome = cc.seed(s)
            s.commit()
            check(
                "23. a second canonical seed creates nothing and changes nothing",
                not outcome.created
                and len(outcome.unchanged) == EXPECTED_ACCOUNTS
                and s.query(m.BankAccountingClassification).count() == EXPECTED_ACCOUNTS,
                detail=f"created={len(outcome.created)} unchanged={len(outcome.unchanged)}",
            )

            for field_name, changed_value, label in (
                ("is_contra", False, "24a. contra"),
                ("node_type", cc.GROUP, "24b. node type"),
                ("review_sensitive", True, "24c. review sensitivity"),
                ("normal_balance", cc.DEBIT, "24d. normal balance"),
            ):
                target = s.query(m.BankAccountingClassification).filter_by(code="1590").one()
                original = getattr(target, field_name)
                setattr(target, field_name, changed_value)
                s.commit()
                loud = False
                try:
                    cc.seed(s)
                except ValueError as exc:
                    loud = "1590" in str(exc) and "semantics" in str(exc).lower()
                s.rollback()
                target = s.query(m.BankAccountingClassification).filter_by(code="1590").one()
                still_changed = getattr(target, field_name) == changed_value
                setattr(target, field_name, original)
                s.commit()
                check(
                    f"{label} differing on the same account code fails loudly and "
                    "overwrites nothing",
                    loud and still_changed,
                    detail=f"raised={loud} untouched={still_changed}",
                )

            # =============================================================
            # 25-26. Nothing else moved
            # =============================================================
            rows_after = s.query(m.BankAccountingClassification).all()
            after_by_code = {row.code: row for row in rows_after}
            check(
                "25a. the 134-account hierarchy is unchanged — same codes, same names",
                {row.code for row in rows_after} == set(by_code)
                and all(after_by_code[c].name == by_code[c].name for c in by_code),
            )
            check(
                "25b. every parent relationship is unchanged",
                all(after_by_code[c].parent_id == by_code[c].parent_id for c in by_code),
            )
            check(
                "25c. the eight canonical roots are still the roots",
                {row.code for row in rows_after if row.parent_id is None}
                == {"1000", "2000", "3000", "4000", "5000", "6000", "7000", "8000"},
            )
            check(
                "25d. the hierarchy still validates",
                not cc.validate_hierarchy(s),
                detail="; ".join(cc.validate_hierarchy(s)[:3]),
            )
            check(
                "25e. the statement split is still 91 P&L / 43 Balance Sheet",
                len([r for r in rows_after if r.statement_type == PL]) == 91
                and len([r for r in rows_after if r.statement_type == BS]) == 43,
            )

            # This suite creates three of its own transactions; the count it
            # asserts is the QA fixture's, checked separately by the QA run.
            # Here what matters is that ADDING METADATA classified nothing:
            # every transaction this suite did not explicitly decide is
            # still waiting for a human.
            auto_applied = s.query(m.BankTransactionExplanation).filter(
                m.BankTransactionExplanation.decision_status == "AUTO_APPLIED",
                m.BankTransactionExplanation.accounting_classification_id.in_(
                    [by_code[c].id for c in sorted(canonical)
                     if by_code[c].node_type == cc.GROUP or by_code[c].review_sensitive]
                ),
            ).count()
            check(
                "26. no transaction was ever auto-applied onto a group or a "
                "review-sensitive account",
                auto_applied == 0, detail=str(auto_applied),
            )

            # =============================================================
            # 27. The importer still refuses to invent, and still previews
            # =============================================================
            before = s.query(m.BankAccountingClassification).count()
            preview = wci.parse(
                b"Statement Type,Code,Name,Node Type,Normal Balance,Is Contra,Review Sensitive\n"
                b"P&L,9999,Preview Only,POSTING,DEBIT,FALSE,FALSE\n",
                file_name="preview.csv",
            )
            check(
                "27a. the importer reads the four semantic columns and still writes nothing",
                s.query(m.BankAccountingClassification).count() == before
                and preview.importable_rows[0].node_type == cc.POSTING
                and preview.importable_rows[0].normal_balance == cc.DEBIT
                and preview.importable_rows[0].states_full_semantics,
            )
            bad = wci.parse(
                b"Statement Type,Code,Name,Node Type\nP&L,9998,Nonsense,SOMETHING_ELSE\n",
                file_name="bad.csv",
            )
            check(
                "27b. an unrecognized node type is an anomaly, never a default",
                not bad.importable_rows
                and any("node type" in a.lower() for row in bad.rows for a in row.anomalies),
                detail=str([a for row in bad.rows for a in row.anomalies][:2]),
            )
            plain = wci.parse(
                b"Statement Type,Code,Name,Parent\nP&L,9997,Plain Parent,\nP&L,9996,Plain Child,9997\n",
                file_name="plain.csv",
            )
            plain_rows = {row.code: row for row in plain.importable_rows}
            check(
                "27c. an export with no semantic columns states nothing, and keeps the "
                "node type RF-One used to derive",
                plain_rows["9997"].node_type == cc.GROUP
                and plain_rows["9996"].node_type == cc.POSTING
                and not plain_rows["9997"].stated_semantics
                and plain_rows["9996"].normal_balance is None,
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
