#!/usr/bin/env python
"""The two resolved canonical accounting questions
(BANK_CANONICAL_ACCOUNTING_CORRECTIONS_001).

Proves the Product Owner's two decisions are in the catalog and that
reporting follows from them rather than from anything hardcoded:

* 3400 Member Distributions / Draws is a Balance Sheet DEBIT CONTRA
  account, so Total Equity SUBTRACTS draws — 500k + 200k + 50k - 80k =
  670k, not 830k;
* 8400 Gain / Loss on Asset Disposal is a GROUP and is no longer a
  destination. 8410 Gain (CREDIT) and 8420 Loss (DEBIT) are the two
  posting accounts, so a disposal never needs its sign guessed from one
  mixed account.

Never touches AWS, RDS, a production database, or a real bank file.
"""

from __future__ import annotations

import sys
from datetime import date

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import accounting_dedup
from rfone_data_store.bank_reconciliation import canonical_catalog as cc
from rfone_data_store.bank_reconciliation import classification as classification_service
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

EXPECTED_ACCOUNTS = 136
EQUITY_ROOT = "3000"
DISPOSAL_ROOT = "8400"

# The production modules that compute or constrain accounting behaviour.
# None of them may name any of the four codes this task touched: the
# behaviour has to come from node_type / normal_balance / is_contra.
BEHAVIOUR_MODULES = (
    "rfone_data_store/bank_reconciliation/canonical_catalog.py",
    "rfone_data_store/bank_reconciliation/what_catalog_import.py",
    "rfone_data_store/bank_reconciliation/classification.py",
    "rfone_data_store/bank_reconciliation/deterministic_rules.py",
    "rfone_data_store/bank_reconciliation/recognition.py",
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

    url = resolve_test_database_url("bank_canonical_accounting_corrections")
    print(f"Database URL: {redact_database_url(url)}")
    run_migrations_to_head(url)
    engine = create_configured_engine(url)

    try:
        session_factory = create_session_factory(engine)
        with session_factory() as s:
            rows = s.query(m.BankAccountingClassification).all()
            by_code = {row.code: row for row in rows}

            # =============================================================
            # 1-3. Member distributions reduce equity
            # =============================================================
            draws = by_code["3400"]
            check(
                "1. 3400 Member Distributions / Draws is a Balance Sheet account",
                draws.statement_type == BS, detail=str(draws.statement_type),
            )
            check(
                "2. 3400 normal balance is DEBIT",
                draws.normal_balance == cc.DEBIT, detail=str(draws.normal_balance),
            )
            check(
                "3. 3400 is contra",
                bool(draws.is_contra) is True and bool(draws.review_sensitive) is False
                and draws.node_type == cc.POSTING,
                detail=f"contra={draws.is_contra} review={draws.review_sensitive} "
                       f"node={draws.node_type}",
            )
            check(
                "3b. the correction changed semantics only — code, name and parent are "
                "exactly what they were",
                draws.code == "3400"
                and draws.name == "Member Distributions / Draws"
                and draws.parent_id == by_code["3000"].id,
            )
            check(
                "3c. a contra account reverses its own reporting group, and the catalog "
                "validates on that",
                by_code["3000"].normal_balance == cc.CREDIT
                and not cc.semantic_problems(s),
                detail="; ".join(cc.semantic_problems(s)[:3]),
            )

            # =============================================================
            # 4. Total Equity subtracts the draws
            # =============================================================
            equity_amounts = {
                "3100": 500_000,   # Member / Owner Equity, in its own CREDIT direction
                "3200": 200_000,   # Retained Earnings
                "3300": 50_000,    # Member Contributions
                "3400": 80_000,    # Member Distributions / Draws, in its own DEBIT direction
            }
            total_equity = cc.subtree_total(s, EQUITY_ROOT, equity_amounts)
            check(
                "4. Total Equity = 500,000 + 200,000 + 50,000 - 80,000 = 670,000",
                total_equity == 670_000, detail=str(total_equity),
            )
            check(
                "4b. and emphatically not 830,000 — the draws are not added",
                total_equity != 830_000,
            )
            equity_signs = {
                account.code: sign for account, sign in cc.signed_subtree(s, EQUITY_ROOT)
            }
            check(
                "4c. the sign comes from normal_balance against the subtree root",
                equity_signs.get("3400") == -1
                and equity_signs.get("3100") == 1
                and equity_signs.get("3200") == 1
                and equity_signs.get("3300") == 1,
                detail=str(equity_signs),
            )

            # =============================================================
            # 5-6. 8400 is a group, and groups are not destinations
            # =============================================================
            disposal = by_code["8400"]
            check(
                "5. 8400 Gain / Loss on Asset Disposal is a GROUP",
                disposal.node_type == cc.GROUP and disposal.name == "Gain / Loss on Asset Disposal",
                detail=disposal.node_type,
            )
            check(
                "6a. 8400 may not receive an automatic final classification",
                not cc.may_receive_automatic_classification(disposal)
                and not disposal.is_posting_account,
            )

            entity = m.LegalEntity(legal_name="Corrections LLC", status="ACTIVE")
            s.add(entity)
            s.flush()
            checking = m.PaymentInstrument(
                legal_entity_id=entity.id, instrument_type="BANK_ACCOUNT",
                display_name="Checking", institution="CHASE", last_four="0011", currency="USD",
            )
            s.add(checking)
            s.flush()
            kind = m.BankOccurrenceType(code="COUNTERPARTY", name="Counterparty")
            s.add(kind)
            # Committed, not just flushed: the refusal check below rolls back.
            s.commit()

            refused = ""
            try:
                classification_service.create_transaction_reason(
                    s, code="DISPOSAL_MIXED", name="Pointing a Why at the disposal group",
                    accounting_classification_id=disposal.id,
                )
            except ValueError as exc:
                refused = str(exc)
            s.rollback()
            check(
                "6b. a Why cannot point at 8400, so nothing can land there automatically",
                "group" in refused.lower() and "8400" in refused,
                detail=refused or "no refusal",
            )

            # =============================================================
            # 7-8. The two posting accounts
            # =============================================================
            gain = by_code.get("8410")
            loss = by_code.get("8420")
            check(
                "7. 8410 Gain on Asset Disposal exists: P&L, POSTING, CREDIT, under 8400",
                gain is not None
                and gain.name == "Gain on Asset Disposal"
                and gain.statement_type == PL
                and gain.node_type == cc.POSTING
                and gain.normal_balance == cc.CREDIT
                and not gain.is_contra and not gain.review_sensitive
                and gain.parent_id == disposal.id,
                detail="missing" if gain is None else
                      f"{gain.statement_type}/{gain.node_type}/{gain.normal_balance}",
            )
            check(
                "8. 8420 Loss on Asset Disposal exists: P&L, POSTING, DEBIT, under 8400",
                loss is not None
                and loss.name == "Loss on Asset Disposal"
                and loss.statement_type == PL
                and loss.node_type == cc.POSTING
                and loss.normal_balance == cc.DEBIT
                and not loss.is_contra and not loss.review_sensitive
                and loss.parent_id == disposal.id,
                detail="missing" if loss is None else
                      f"{loss.statement_type}/{loss.node_type}/{loss.normal_balance}",
            )
            check(
                "8b. both are legitimate destinations a disposal workflow may choose",
                cc.may_receive_automatic_classification(gain)
                and cc.may_receive_automatic_classification(loss),
            )

            # =============================================================
            # 9. Other Income / Expense handles a gain and a loss
            # =============================================================
            disposal_signs = {
                account.code: sign for account, sign in cc.signed_subtree(s, DISPOSAL_ROOT)
            }
            check(
                "9a. inside the disposal group a gain adds and a loss subtracts",
                disposal_signs == {"8410": 1, "8420": -1},
                detail=str(disposal_signs),
            )
            net_disposal = cc.subtree_total(s, DISPOSAL_ROOT, {"8410": 30_000, "8420": 12_000})
            check(
                "9b. a 30,000 gain against a 12,000 loss nets to an 18,000 gain",
                net_disposal == 18_000, detail=str(net_disposal),
            )
            other_signs = {
                account.code: sign for account, sign in cc.signed_subtree(s, cc.OTHER_ROOT)
            }
            check(
                "9c. in Other Income / Expense a gain increases income and a loss reduces it",
                other_signs.get("8410") == 1 and other_signs.get("8420") == -1
                and other_signs.get("8100") == 1 and other_signs.get("8200") == -1,
                detail=str({k: other_signs.get(k) for k in ("8100", "8200", "8410", "8420")}),
            )
            check(
                "9d. the group node 8400 is not itself summed, so nothing is double-counted",
                "8400" not in other_signs and "8400" not in disposal_signs,
            )
            other_total = cc.subtree_total(s, cc.OTHER_ROOT, {
                "8100": 5_000, "8200": 9_000, "8300": 40_000,
                "8410": 30_000, "8420": 12_000,
            })
            check(
                "9e. Other Income / Expense = 5,000 - 9,000 - 40,000 + 30,000 - 12,000 "
                "= -26,000",
                other_total == -26_000, detail=str(other_total),
            )

            # =============================================================
            # 10. Nothing was special-cased by account code
            # =============================================================
            source = ""
            for path in BEHAVIOUR_MODULES:
                source += open(path, encoding="utf-8").read()
            offenders = [
                code for code in ("3400", "8400", "8410", "8420") if code in source
            ]
            check(
                "10. no hardcoded account-code sign exception was introduced",
                not offenders, detail=str(offenders),
            )

            # =============================================================
            # 11-12. The catalog is 136 accounts, and seeding is idempotent
            # =============================================================
            check(
                "11. the canonical catalog is 136 accounts — 134 plus 8410 and 8420",
                len(rows) == EXPECTED_ACCOUNTS
                and len(cc.catalog_rows()) == EXPECTED_ACCOUNTS,
                detail=f"{len(rows)} stored, {len(cc.catalog_rows())} defined",
            )
            check(
                "11b. the statement split is 93 Profit & Loss / 43 Balance Sheet",
                len([r for r in rows if r.statement_type == PL]) == 93
                and len([r for r in rows if r.statement_type == BS]) == 43,
            )
            check(
                "11c. node types are 32 GROUP / 101 POSTING / 3 POSTING_CATEGORY",
                len([r for r in rows if r.node_type == cc.GROUP]) == 32
                and len([r for r in rows if r.node_type == cc.POSTING]) == 101
                and len([r for r in rows if r.node_type == cc.POSTING_CATEGORY]) == 3,
            )
            check(
                "11d. the contra accounts are now 1590, 3400, 4910, 4920",
                {row.code for row in cc.contra_accounts(s)}
                == {"1590", "3400", "4910", "4920"},
                detail=str(sorted(row.code for row in cc.contra_accounts(s))),
            )
            check(
                "11e. the review-sensitive accounts are unchanged",
                {row.code for row in cc.review_sensitive_accounts(s)}
                == {"6900", "7880", "8500", "8600"},
            )
            check(
                "11f. the hierarchy still validates and the eight roots are unchanged",
                not cc.validate_hierarchy(s)
                and {row.code for row in rows if row.parent_id is None}
                == {"1000", "2000", "3000", "4000", "5000", "6000", "7000", "8000"},
                detail="; ".join(cc.validate_hierarchy(s)[:3]),
            )

            outcome = cc.seed(s)
            s.commit()
            check(
                "12. a second canonical seed creates nothing and changes nothing",
                not outcome.created
                and len(outcome.unchanged) == EXPECTED_ACCOUNTS
                and s.query(m.BankAccountingClassification).count() == EXPECTED_ACCOUNTS,
                detail=f"created={len(outcome.created)} unchanged={len(outcome.unchanged)}",
            )

            loud = False
            target = s.query(m.BankAccountingClassification).filter_by(code="3400").one()
            target.is_contra = False
            s.commit()
            try:
                cc.seed(s)
            except ValueError as exc:
                loud = "3400" in str(exc) and "semantics" in str(exc).lower()
            s.rollback()
            target = s.query(m.BankAccountingClassification).filter_by(code="3400").one()
            still_wrong = target.is_contra is False
            target.is_contra = True
            s.commit()
            check(
                "12b. a database that disagrees about 3400 being contra fails loudly and "
                "is not overwritten",
                loud and still_wrong, detail=f"raised={loud} untouched={still_wrong}",
            )

            # =============================================================
            # 13. Nothing about the transactions moved
            # =============================================================
            before_txn = s.query(m.FinancialTransaction).count()
            before_decisions = s.query(m.BankTransactionExplanation).count()

            gain_why = classification_service.create_transaction_reason(
                s, code="ASSET_DISPOSAL_GAIN", name="Equipment sold above its book value",
                accounting_classification_id=by_code["8410"].id,
            )
            buyer = classification_service.create_occurrence(
                s, canonical_name="Equipment Buyer", occurrence_type_id=kind.id,
                default_transaction_reason_id=gain_why.id,
            )
            s.commit()
            sale = m.FinancialTransaction(
                payment_instrument_id=checking.id, bank_source="CHASE_BANK_ACCOUNT",
                posting_date=date(2026, 7, 1), description_original="EQUIPMENT BUYER PROCEEDS",
                description_normalized="EQUIPMENT BUYER PROCEEDS", amount_minor=30_000,
                status="COMPLETED", duplicate_status="NONE", review_status="REQUIRES_REVIEW",
            )
            s.add(sale)
            s.commit()
            accounting_dedup.recompute_accounting_dedup(s)
            s.commit()
            decision = recognition.record_human_decision(
                s, recognition.HumanDecisionRequest(
                    transaction_id=sale.id, occurrence_id=buyer.id,
                    # The human chooses the Why explicitly; a Who's default is
                    # never applied on its own (BANK_FINAL_RELEASE_BLOCKERS_001).
                    transaction_reason_id=s.get(m.BankOccurrence, buyer.id).default_transaction_reason_id,
                    confirmed_by_account_id=None, learn_description=False,
                ),
            )
            s.commit()
            check(
                "13a. a disposal is classified to 8410 or 8420 by what it economically was, "
                "never to the mixed 8400",
                decision.accounting_classification_code_snapshot == "8410"
                and decision.accounting_statement_type_snapshot == PL,
                detail=str(decision.accounting_classification_code_snapshot),
            )
            check(
                "13b. this suite added exactly the one transaction and the one decision it "
                "meant to; nothing was reclassified in bulk",
                s.query(m.FinancialTransaction).count() == before_txn + 1
                and s.query(m.BankTransactionExplanation).count() == before_decisions + 1,
            )
            check(
                "13c. no transaction was ever auto-applied onto a group or a "
                "review-sensitive account",
                s.query(m.BankTransactionExplanation).filter(
                    m.BankTransactionExplanation.decision_status == "AUTO_APPLIED",
                    m.BankTransactionExplanation.accounting_classification_id.in_(
                        [row.id for row in rows
                         if row.node_type == cc.GROUP or row.review_sensitive]
                    ),
                ).count() == 0,
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
