#!/usr/bin/env python
"""The canonical WHY catalog and WHO <-> WHY
(BANK_CANONICAL_WHY_AND_WHO_RELATIONSHIPS_001).

    WHO   who the money concerns.
    WHY   what kind of business purpose it served — RF-One's management
          language. A Who may have ZERO, ONE or MANY.
    WHAT  the official P&L posting category, DERIVED from the Why and
          never chosen per transaction.

Every P&L Why resolves to exactly one WHAT. Every non-P&L Why resolves to
a Balance Sheet accounting destination and has NO WHAT — which is a
statement about the P&L, not a gap.

And the productivity model the whole thing exists for: associating a Why
with a Who teaches "Amazon has been this", never "Amazon means this".

Never touches AWS, RDS, a production database, Clover, ADP or Mercury.
"""

from __future__ import annotations

import sys
from datetime import date

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import accounting_dedup
from rfone_data_store.bank_reconciliation import canonical_catalog as cc
from rfone_data_store.bank_reconciliation import classification as classification_service
from rfone_data_store.bank_reconciliation import recognition
from rfone_data_store.bank_reconciliation import why_catalog as wc
from rfone_data_store.database import (
    create_configured_engine,
    create_session_factory,
    redact_database_url,
    resolve_test_database_url,
    run_migrations_to_head,
)

EXPECTED_WHY = 77
EXPECTED_PL_WHY = 59
EXPECTED_NON_PL_WHY = 18
EXPECTED_GROUPS = 14
EXPECTED_WHAT = 72
EXPECTED_ACCOUNTS = 136

# §28.17-25 — the mappings the Product Owner named.
DERIVES_WHAT = (
    ("BOH_REGULAR_PAYROLL", "6210"),
    ("BOH_CONTRACT_LABOR", "6800"),
    ("FOH_REGULAR_PAYROLL", "6110"),
    ("FOOD_PURCHASES", "5100"),
    ("WINE_PURCHASES", "5230"),
    ("FACILITY_MAINTENANCE", "7320"),
    ("EQUIPMENT_REPAIR", "7310"),
    ("ACCOUNTING_BOOKKEEPING", "7610"),
    ("LEGAL", "7620"),
    ("MARKETING_ADVERTISING", "7500"),
)

# §28.15-16 — destination, not WHAT.
DERIVES_DESTINATION = (
    ("TIPS_SETTLEMENT", "2300"),
    ("SALES_TAX_REMITTANCE", "2200"),
    ("EQUIPMENT_PURCHASE_CAPEX", "1520"),
    ("LEASEHOLD_IMPROVEMENT", "1530"),
    ("OWNER_PERSONAL_HOME", "3400"),
)

AMBIGUOUS_LEGACY = (
    "Company Cars", "Company Tax", "Da Verificare", "Incoming", "Incoming RFG",
    "Mount Dora Start up", "Personal Deductable", "Products-Pers", "RF Gelati",
    "Utility Morse/Central",
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

    url = resolve_test_database_url("bank_canonical_why_and_who")
    print(f"Database URL: {redact_database_url(url)}")
    run_migrations_to_head(url)
    engine = create_configured_engine(url)

    try:
        session_factory = create_session_factory(engine)
        with session_factory() as s:
            reasons = {r.code: r for r in s.query(m.BankTransactionReason).all()}
            pl = [r for r in reasons.values() if r.is_profit_loss]
            non_pl = [r for r in reasons.values() if not r.is_profit_loss]

            # =============================================================
            # 1-3. The WHY -> WHAT invariant
            # =============================================================
            check(
                f"0. the canonical WHY catalog is {EXPECTED_WHY} purposes in "
                f"{EXPECTED_GROUPS} management groups",
                len(reasons) == EXPECTED_WHY and len(wc.groups(s)) == EXPECTED_GROUPS,
                detail=f"{len(reasons)} WHY, {len(wc.groups(s))} groups",
            )
            check(
                f"1. every P&L WHY has exactly one WHAT ({EXPECTED_PL_WHY} of them)",
                len(pl) == EXPECTED_PL_WHY
                and all(r.what is not None and r.accounting_destination is None for r in pl),
                detail=str([r.code for r in pl if r.what is None][:3]),
            )
            check(
                f"2. no non-P&L WHY is classified as WHAT ({EXPECTED_NON_PL_WHY} of them "
                "carry a destination instead)",
                len(non_pl) == EXPECTED_NON_PL_WHY
                and all(
                    r.what is None and r.accounting_destination is not None for r in non_pl
                ),
                detail=str([r.code for r in non_pl if r.what is not None][:3]),
            )
            check(
                "3. no WHY points at a P&L GROUP",
                not [
                    r for r in reasons.values()
                    if r.accounting_classification is not None
                    and r.accounting_classification.node_type == cc.GROUP
                ],
            )
            check(
                "3b. the catalog validator reports no invariant violation",
                not wc.catalog_problems(s), detail="; ".join(wc.catalog_problems(s)[:3]),
            )
            check(
                "3c. several WHY may share one WHAT — management granularity above P&L "
                "structure (BOH/FOH contract labour both -> 6800; janitorial and hood "
                "cleaning both -> 7810)",
                reasons["BOH_CONTRACT_LABOR"].what.code
                == reasons["FOH_CONTRACT_LABOR"].what.code == "6800"
                and reasons["JANITORIAL_CLEANING"].what.code
                == reasons["HOOD_CLEANING"].what.code == "7810",
            )

            # =============================================================
            # 14-25. The named derivations
            # =============================================================
            for code, account_code in DERIVES_WHAT:
                reason = reasons.get(code)
                check(
                    f"14-25. {code} derives WHAT {account_code}",
                    reason is not None and reason.what is not None
                    and reason.what.code == account_code
                    and reason.accounting_destination is None
                    and reason.resolution_label.startswith("WHAT:"),
                    detail="missing" if reason is None else reason.resolution_label,
                )
            for code, account_code in DERIVES_DESTINATION:
                reason = reasons.get(code)
                check(
                    f"15-16. {code} derives DESTINATION {account_code}, not a WHAT",
                    reason is not None and reason.what is None
                    and reason.accounting_destination is not None
                    and reason.accounting_destination.code == account_code
                    and reason.resolution_label.startswith("ACCOUNTING DESTINATION:"),
                    detail="missing" if reason is None else reason.resolution_label,
                )

            # =============================================================
            # 26-28. Legacy labels
            # =============================================================
            check(
                "17§. the unambiguous legacy labels normalize",
                wc.normalize_legacy_label("Products-Wine") == "WINE_PURCHASES"
                and wc.normalize_legacy_label("Payroll - BOH") == "BOH_REGULAR_PAYROLL"
                and wc.normalize_legacy_label("Tips") == "TIPS_SETTLEMENT"
                and wc.normalize_legacy_label("New Appliances") == "EQUIPMENT_PURCHASE_CAPEX",
            )
            for label in AMBIGUOUS_LEGACY:
                check(
                    f"26-28. {label!r} does NOT auto-map, and says why",
                    wc.normalize_legacy_label(label) is None
                    and wc.legacy_label_needs_human(label) is not None
                    and label not in reasons,
                    detail=str(wc.normalize_legacy_label(label)),
                )
            check(
                "27. 'Da Verificare' is not a canonical WHY — it is a review status",
                "Da Verificare" not in reasons
                and wc.by_code(s, "Da Verificare") is None,
            )
            check(
                "28. 'Mount Dora Start up' maps to no WHAT at all",
                wc.normalize_legacy_label("Mount Dora Start up") is None,
            )

            # =============================================================
            # Fixtures
            # =============================================================
            entity = m.LegalEntity(legal_name="Why LLC", status="ACTIVE")
            s.add(entity)
            s.flush()
            checking = m.PaymentInstrument(
                legal_entity_id=entity.id, instrument_type="BANK_ACCOUNT",
                display_name="Checking", institution="CHASE", last_four="0021", currency="USD",
            )
            s.add(checking)
            s.flush()
            kind = m.BankOccurrenceType(code="COUNTERPARTY", name="Counterparty")
            s.add(kind)
            s.commit()

            def who(name: str, default_why: str | None = None):
                existing = s.query(m.BankOccurrence).filter_by(canonical_name=name).first()
                if existing is not None:
                    return existing
                return classification_service.create_occurrence(
                    s, canonical_name=name, occurrence_type_id=kind.id,
                    default_transaction_reason_id=(
                        reasons[default_why].id if default_why else None
                    ),
                )

            day = [0]

            def txn(description: str, amount: int = -25_000):
                day[0] += 1
                row = m.FinancialTransaction(
                    payment_instrument_id=checking.id, bank_source="CHASE_BANK_ACCOUNT",
                    posting_date=date(2026, 11, min(day[0], 28)),
                    description_original=description,
                    description_normalized=description.upper(),
                    amount_minor=amount, status="COMPLETED", duplicate_status="NONE",
                    review_status="REQUIRES_REVIEW",
                )
                s.add(row)
                s.flush()
                return row

            # =============================================================
            # 4-7. WHO <-> WHY is many to many
            # =============================================================
            nobody = who("Brand New Counterparty")
            s.commit()
            check(
                "4. a WHO may have ZERO WHY",
                wc.reasons_for_occurrence(s, nobody.id) == [],
            )

            amazon = who("Amazon")
            s.commit()
            wc.associate(
                s, occurrence_id=amazon.id,
                transaction_reason_id=reasons["RESTAURANT_OPERATING_SUPPLIES"].id,
            )
            s.commit()
            check(
                "5. a WHO may have ONE WHY",
                [r.code for r in wc.reasons_for_occurrence(s, amazon.id)]
                == ["RESTAURANT_OPERATING_SUPPLIES"],
            )
            for code in ("OFFICE_SUPPLIES", "FOOD_PURCHASES", "EQUIPMENT_PURCHASE_CAPEX"):
                wc.associate(
                    s, occurrence_id=amazon.id, transaction_reason_id=reasons[code].id,
                )
            s.commit()
            amazon_why = {r.code for r in wc.reasons_for_occurrence(s, amazon.id)}
            check(
                "6. a WHO may have MANY WHY — Amazon keeps all four",
                amazon_why == {
                    "RESTAURANT_OPERATING_SUPPLIES", "OFFICE_SUPPLIES",
                    "FOOD_PURCHASES", "EQUIPMENT_PURCHASE_CAPEX",
                },
                detail=str(sorted(amazon_why)),
            )
            check(
                "30. associating a second WHY never replaces the first",
                "RESTAURANT_OPERATING_SUPPLIES" in amazon_why and len(amazon_why) == 4,
            )

            costco = who("Costco")
            s.commit()
            wc.associate(
                s, occurrence_id=costco.id, transaction_reason_id=reasons["FOOD_PURCHASES"].id,
            )
            s.commit()
            check(
                "7. the same WHY may belong to many WHO — Food Purchases reaches both",
                {o.canonical_name for o in
                 wc.occurrences_for_reason(s, reasons["FOOD_PURCHASES"].id)}
                == {"Amazon", "Costco"},
            )
            check(
                "20§. re-associating an existing pair counts a confirmation rather than "
                "duplicating the row",
                wc.associate(
                    s, occurrence_id=costco.id,
                    transaction_reason_id=reasons["FOOD_PURCHASES"].id,
                ).confirmation_count == 2
                and s.query(m.BankOccurrenceReasonAssociation).filter_by(
                    occurrence_id=costco.id,
                    transaction_reason_id=reasons["FOOD_PURCHASES"].id,
                ).count() == 1,
            )

            # =============================================================
            # 8-12. What the two selectors contain
            # =============================================================
            dropdown = wc.reasons_for_occurrence(s, amazon.id)
            check(
                "8. the ordinary WHY dropdown shows ONLY the WHY associated with this WHO "
                "— four, not the whole catalog of 77",
                len(dropdown) == 4 and len(dropdown) < len(reasons),
                detail=str(len(dropdown)),
            )
            check(
                "9. the ordinary dropdown contains no management group",
                not any(isinstance(item, m.BankReasonGroup) for item in dropdown)
                and all(isinstance(item, m.BankTransactionReason) for item in dropdown),
            )
            check(
                "10-11. '+ New' opens the COMPLETE canonical catalog, which is a different "
                "query from the dropdown",
                sum(len(items) for _, items in wc.catalog_by_group(s)) == EXPECTED_WHY,
                detail=str(sum(len(items) for _, items in wc.catalog_by_group(s))),
            )
            grouped = wc.catalog_by_group(s)
            check(
                "12. the modal groups WHY by management group, in display order",
                [g.code for g, _ in grouped][:4]
                == ["KITCHEN_LABOR", "FOH_LABOR", "PEOPLE", "PRODUCT_COST"]
                and len(grouped) == EXPECTED_GROUPS,
                detail=str([g.code for g, _ in grouped][:4]),
            )
            check(
                "12b. every group in the modal is non-empty and every WHY appears once",
                all(items for _, items in grouped)
                and len({r.code for _, items in grouped for r in items}) == EXPECTED_WHY,
            )

            # =============================================================
            # 13-14, 29. Choosing a WHY on a transaction
            # =============================================================
            cleaner = who("Get Better Cleaning")
            s.commit()
            first = txn("GET BETTER CLEANING AUGUST")
            s.commit()
            accounting_dedup.recompute_accounting_dedup(s)
            s.commit()
            decision = recognition.record_human_decision(
                s, recognition.HumanDecisionRequest(
                    transaction_id=first.id, occurrence_id=cleaner.id,
                    confirmed_by_account_id=None, learn_description=False,
                    transaction_reason_id=reasons["JANITORIAL_CLEANING"].id,
                ),
            )
            s.commit()
            check(
                "13. choosing a WHY creates the WHO <-> WHY association",
                [r.code for r in wc.reasons_for_occurrence(s, cleaner.id)]
                == ["JANITORIAL_CLEANING"],
            )
            check(
                "14. ...and the WHAT is derived automatically from that WHY",
                decision.transaction_reason_id == reasons["JANITORIAL_CLEANING"].id
                and decision.accounting_classification_code_snapshot == "7810",
                detail=str(decision.accounting_classification_code_snapshot),
            )

            second = txn("GET BETTER CLEANING HOOD SEPTEMBER")
            s.commit()
            accounting_dedup.recompute_accounting_dedup(s)
            s.commit()
            recognition.record_human_decision(
                s, recognition.HumanDecisionRequest(
                    transaction_id=second.id, occurrence_id=cleaner.id,
                    confirmed_by_account_id=None, learn_description=False,
                    transaction_reason_id=reasons["FACILITY_MAINTENANCE"].id,
                ),
            )
            s.commit()
            check(
                "24§. the dropdown for that WHO now offers both, exactly as the example says",
                {r.name for r in wc.reasons_for_occurrence(s, cleaner.id)}
                == {"Janitorial / Cleaning", "Building / Facility Maintenance"},
                detail=str(sorted(r.name for r in wc.reasons_for_occurrence(s, cleaner.id))),
            )

            # 29 — one WHO, a Tips transaction, a contract-labour transaction,
            # and a third left unresolved.
            worker = who("Mario Rossi")
            s.commit()
            tips_txn = txn("Zelle payment to Mario Rossi JPM99why001")
            labor_txn = txn("Zelle payment to Mario Rossi JPM99why002")
            open_txn = txn("Zelle payment to Mario Rossi JPM99why003")
            s.commit()
            accounting_dedup.recompute_accounting_dedup(s)
            s.commit()
            tips_decision = recognition.record_human_decision(
                s, recognition.HumanDecisionRequest(
                    transaction_id=tips_txn.id, occurrence_id=worker.id,
                    confirmed_by_account_id=None, learn_description=False,
                    transaction_reason_id=reasons["TIPS_SETTLEMENT"].id,
                ),
            )
            labor_decision = recognition.record_human_decision(
                s, recognition.HumanDecisionRequest(
                    transaction_id=labor_txn.id, occurrence_id=worker.id,
                    confirmed_by_account_id=None, learn_description=False,
                    transaction_reason_id=reasons["BOH_CONTRACT_LABOR"].id,
                ),
            )
            s.commit()
            open_decision = recognition.get_current_explanation(
                s, financial_transaction_id=open_txn.id)
            check(
                "29. the SAME WHO has a Tips transaction, a Contract Labour transaction and "
                "a third still unresolved",
                tips_decision.accounting_classification_code_snapshot == "2300"
                and labor_decision.accounting_classification_code_snapshot == "6800"
                and (open_decision is None
                     or open_decision.decision_status == "NEEDS_HUMAN_REVIEW"),
                detail=f"{tips_decision.accounting_classification_code_snapshot}/"
                       f"{labor_decision.accounting_classification_code_snapshot}",
            )
            check(
                "29b. ...on opposite sides of the books — a liability settled, and a real "
                "Labor Cost",
                tips_decision.accounting_statement_type_snapshot == "BALANCE_SHEET"
                and labor_decision.accounting_statement_type_snapshot == "PROFIT_LOSS",
            )
            check(
                "31. no WHO identity alone proves WHY — the association is a shortcut, and "
                "no recognition rule claims otherwise",
                len(wc.reasons_for_occurrence(s, worker.id)) == 2
                and not [
                    r for r in s.query(m.BankRecognitionRule).all()
                    if r.determines_purpose and r.match_field == "DESCRIPTION"
                ],
            )

            # =============================================================
            # 32-34. Nothing else moved
            # =============================================================
            check(
                f"32-33. the catalog is still {EXPECTED_ACCOUNTS} accounts and "
                f"{EXPECTED_WHAT} WHAT",
                s.query(m.BankAccountingClassification).count() == EXPECTED_ACCOUNTS
                and len(cc.what_catalog(s)) == EXPECTED_WHAT
                and not cc.what_catalog_problems(s),
            )
            check(
                "34. this suite created no raw rows, no import batches and no learned rules",
                s.query(m.RawBankTransaction).count() == 0
                and s.query(m.BankImportBatch).count() == 0
                and s.query(m.BankRecognitionRule).count() == 0,
            )
            check(
                "§20 `default_transaction_reason_id` is not required for any of this — the "
                "associations carry the relationship",
                s.query(m.BankOccurrenceReasonAssociation).count() >= 8
                and wc.reasons_for_occurrence(s, amazon.id),
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
