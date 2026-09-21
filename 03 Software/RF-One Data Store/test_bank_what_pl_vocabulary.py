#!/usr/bin/env python
"""WHAT is the official Profit & Loss vocabulary
(BANK_WHAT_PL_VOCABULARY_001).

The Product Owner fixed what the word means:

    WHAT  = the official P&L posting category a transaction falls into.
            72 of them. RF-One's P&L language, given to the accountant
            rather than taken from one.

    NOT WHAT, though still canonical accounts:
      * the 21 P&L GROUP nodes — presentation hierarchy, never a
        destination;
      * all 43 Balance Sheet accounts — accounting destinations where a
        non-P&L Why settles. Such a transaction has a destination and NO
        WHAT, and that absence is a statement about the P&L rather than a
        gap to be filled.

The vocabulary is DERIVED from the canonical catalog, never stored a
second time: this suite asserts the derivation and the boundary, not a
copied list.

Never touches AWS, RDS, a production database, Clover, ADP or Mercury.
"""

from __future__ import annotations

import sys

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import canonical_catalog as cc
from rfone_data_store.bank_reconciliation import receiver_candidates as rc
from rfone_data_store.database import (
    create_configured_engine,
    create_session_factory,
    redact_database_url,
    resolve_test_database_url,
    run_migrations_to_head,
)

EXPECTED_WHAT = 72
EXPECTED_PL_GROUPS = 21
EXPECTED_PL_NODES = 93
EXPECTED_ACCOUNTS = 136
EXPECTED_BS_NODES = 43

# The Product Owner's list, written out independently of the query under
# test so that a change to either side fails this suite.
APPROVED_WHAT = set("""
4100 4210 4220 4230 4240 4310 4320 4910 4920
5100 5210 5220 5230 5240 5300 5400
6110 6120 6210 6220 6310 6400 6500 6600 6700 6800 6900
7110 7120 7130 7210 7220 7230 7310 7320
7410 7420 7430 7440 7450 7500
7610 7620 7630 7640 7710 7720 7730 7740 7750
7810 7820 7830 7840 7850 7860 7870 7880
7910 7920 7930 7940 7950 7960 7970
8100 8200 8300 8410 8420 8500 8600
""".split())

APPROVED_PL_GROUPS = set("""
4000 4200 4300 4900 5000 5200 6000 6100 6200 6300
7000 7100 7200 7300 7400 7600 7700 7800 7900 8000 8400
""".split())

REVIEW_SENSITIVE_WHAT = {"6900", "7880", "8500", "8600"}

# §13.13-16 — the four the Product Owner named explicitly.
NOT_WHAT = (
    ("2300", "Tips Payable"),
    ("2200", "Sales Tax Payable"),
    ("2500", "Credit Cards Payable"),
    ("1110", "Operating Bank Accounts"),
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

    url = resolve_test_database_url("bank_what_pl_vocabulary")
    print(f"Database URL: {redact_database_url(url)}")
    run_migrations_to_head(url)
    engine = create_configured_engine(url)

    try:
        session_factory = create_session_factory(engine)
        with session_factory() as s:
            what = cc.what_catalog(s)
            groups = cc.what_groups(s)
            destinations = cc.accounting_destinations(s)
            by_code = {a.code: a for a in s.query(m.BankAccountingClassification).all()}
            what_codes = {a.code for a in what}

            # =============================================================
            # 1-4. The vocabulary and its boundary
            # =============================================================
            check(
                f"1. the official WHAT vocabulary is exactly {EXPECTED_WHAT} categories",
                len(what) == EXPECTED_WHAT, detail=str(len(what)),
            )
            check(
                "1b. ...and it is exactly the list the Product Owner approved",
                what_codes == APPROVED_WHAT,
                detail=f"missing={sorted(APPROVED_WHAT - what_codes)} "
                       f"unexpected={sorted(what_codes - APPROVED_WHAT)}",
            )
            check(
                "2. every WHAT is PROFIT_LOSS",
                all(a.statement_type == "PROFIT_LOSS" for a in what),
                detail=str([a.code for a in what if a.statement_type != "PROFIT_LOSS"]),
            )
            check(
                "3. no GROUP node appears as WHAT",
                not [a for a in what if a.node_type == "GROUP"]
                and not (what_codes & APPROVED_PL_GROUPS),
                detail=str([a.code for a in what if a.node_type == "GROUP"]),
            )
            check(
                "4. no Balance Sheet account appears as WHAT",
                not [a for a in what if a.statement_type == "BALANCE_SHEET"]
                and not any(code[0] in "123" for code in what_codes),
                detail=str(sorted(c for c in what_codes if c[0] in "123")),
            )
            check(
                "4b. every WHAT is active, has a normal balance, a code and a name",
                all(
                    a.active and a.normal_balance in cc.NORMAL_BALANCES
                    and (a.code or "").strip() and (a.name or "").strip()
                    for a in what
                ),
            )
            check(
                "4c. the catalog service reports no vocabulary problems",
                not cc.what_catalog_problems(s),
                detail="; ".join(cc.what_catalog_problems(s)[:3]),
            )

            # =============================================================
            # 5-12. The categories the Product Owner named
            # =============================================================
            for label, code, name in (
                ("5", "5100", "Food COGS"),
                ("6", "5230", "Wine COGS"),
                ("7", "6210", "BOH Regular Wages"),
                ("8", "6110", "FOH Regular Wages"),
                ("9a", "7310", "Equipment Repairs & Maintenance"),
                ("9b", "7320", "Building / Facility Maintenance"),
                ("10", "7610", "Accounting / Bookkeeping"),
                ("11", "7620", "Legal Fees"),
                ("12", "7500", "Marketing & Advertising"),
            ):
                account = by_code.get(code)
                check(
                    f"{label}. {code} {name} is a WHAT",
                    account is not None and account.name == name
                    and account.is_what and code in what_codes,
                    detail="missing" if account is None else
                           f"name={account.name!r} is_what={account.is_what}",
                )

            # =============================================================
            # 13-16. The four that are NOT WHAT
            # =============================================================
            for code, name in NOT_WHAT:
                account = by_code.get(code)
                check(
                    f"13-16. {code} {name} is NOT a WHAT — it is an accounting destination",
                    account is not None and not account.is_what
                    and code not in what_codes
                    and account.statement_type == "BALANCE_SHEET"
                    and account.is_accounting_destination,
                    detail="missing" if account is None else
                           f"is_what={account.is_what} dest={account.is_accounting_destination}",
                )
            check(
                "13-16b. ...and all four are reachable under the separate destination concept",
                {code for code, _ in NOT_WHAT} <= {a.code for a in destinations},
            )
            check(
                "13-16c. WHAT and accounting destinations do not overlap at all",
                not (what_codes & {a.code for a in destinations}),
            )

            # =============================================================
            # 17. Review-sensitive WHAT
            # =============================================================
            flagged = {a.code for a in what if a.review_sensitive}
            check(
                "17. the four review-sensitive categories remain valid WHAT and remain flagged",
                flagged == REVIEW_SENSITIVE_WHAT and REVIEW_SENSITIVE_WHAT <= what_codes,
                detail=str(sorted(flagged)),
            )
            check(
                "17b. ...and none of them may be reached automatically — never UNKNOWN -> 7880",
                not any(
                    by_code[code].may_receive_automatic_classification
                    for code in REVIEW_SENSITIVE_WHAT
                ),
            )

            # =============================================================
            # 18-19. The hierarchy and the catalog are unchanged
            # =============================================================
            pl_nodes = [
                a for a in by_code.values() if a.statement_type == "PROFIT_LOSS"
            ]
            bs_nodes = [
                a for a in by_code.values() if a.statement_type == "BALANCE_SHEET"
            ]
            check(
                f"18. the P&L hierarchy is still {EXPECTED_PL_NODES} nodes",
                len(pl_nodes) == EXPECTED_PL_NODES, detail=str(len(pl_nodes)),
            )
            check(
                f"18b. {EXPECTED_WHAT} WHAT + {EXPECTED_PL_GROUPS} GROUP = "
                f"{EXPECTED_PL_NODES} P&L nodes",
                len(what) + len(groups) == len(pl_nodes)
                and len(groups) == EXPECTED_PL_GROUPS,
                detail=f"{len(what)} + {len(groups)}",
            )
            check(
                "18c. the P&L group nodes are exactly the approved reporting hierarchy",
                {g.code for g in groups} == APPROVED_PL_GROUPS,
                detail=str(sorted({g.code for g in groups} ^ APPROVED_PL_GROUPS)),
            )
            check(
                f"19. the canonical catalog is still {EXPECTED_ACCOUNTS} accounts "
                f"({EXPECTED_BS_NODES} Balance Sheet)",
                len(by_code) == EXPECTED_ACCOUNTS and len(bs_nodes) == EXPECTED_BS_NODES
                and not cc.semantic_problems(s) and not cc.validate_hierarchy(s),
                detail=f"{len(by_code)} accounts, {len(bs_nodes)} BS",
            )
            check(
                "19b. no schema change was needed — WHAT is derived, not a second table",
                not [
                    t for t in m.Base.metadata.tables
                    if "what" in t.lower() and t != "bank_accounting_classifications"
                ],
                detail=str([t for t in m.Base.metadata.tables if "what" in t.lower()]),
            )

            # =============================================================
            # 20. Bank is still clean
            # =============================================================
            check(
                "20. Bank clean-state counts remain zero",
                s.query(m.FinancialTransaction).count() == 0
                and s.query(m.RawBankTransaction).count() == 0
                and s.query(m.BankTransactionExplanation).count() == 0
                and s.query(m.BankOccurrence).count() == 0
                and s.query(m.BankRecognitionRule).count() == 0
                and s.query(m.BankImportBatch).count() == 0
                and len(rc.build_candidates(s)) == 0,
            )
            check(
                "20b. the structural Why baseline is preserved (5 purposes)",
                s.query(m.BankTransactionReason).count() == 5,
                detail=str(s.query(m.BankTransactionReason).count()),
            )
            # §8 — every structural Why that settles a liability points at a
            # DESTINATION, and none of those destinations is a WHAT.
            settling = {
                "SALES_TAX_REMITTANCE": "2200",
                "CREDIT_CARD_SETTLEMENT": "2500",
                "INTERNAL_BANK_TRANSFER": "1110",
                "LOAN_ADVANCE": "2600",
            }
            for why_code, destination_code in settling.items():
                reason = s.query(m.BankTransactionReason).filter_by(code=why_code).one()
                check(
                    f"20c/§8. {why_code} points at {destination_code}, a destination and "
                    "NOT a WHAT — that transaction has no WHAT at all",
                    reason.accounting_classification_id == by_code[destination_code].id
                    and destination_code not in what_codes
                    and by_code[destination_code].is_accounting_destination,
                    detail=f"-> {destination_code} in_what={destination_code in what_codes}",
                )
            # ...while a P&L Why does resolve to a real WHAT.
            fee = s.query(m.BankTransactionReason).filter_by(
                code="FOREIGN_TRANSACTION_FEE").one()
            check(
                "20d/§7. a P&L Why resolves to a WHAT — FOREIGN_TRANSACTION_FEE -> 7230, "
                "which IS in the vocabulary",
                fee.accounting_classification_id == by_code["7230"].id
                and "7230" in what_codes and by_code["7230"].is_what,
            )

            # =============================================================
            # Human-facing label
            # =============================================================
            check(
                "§5 a WHAT displays as '5100 — Food COGS', meaning first, code attached",
                by_code["5100"].display_label == "5100 — Food COGS",
                detail=by_code["5100"].display_label,
            )
            check(
                "§5b every WHAT has a display label carrying both code and name",
                all(
                    a.code in a.display_label and a.name in a.display_label for a in what
                ),
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
