#!/usr/bin/env python
"""The structural Why vocabulary
(BANK_RESTORE_STRUCTURAL_WHY_BASELINE_001).

Five transaction PURPOSES are structural Bank vocabulary: RF-One knows
what a foreign transaction fee, a card settlement, a loan advance, an
internal transfer and a sales-tax remittance are. They arrive with an
ordinary migration, before any data exists.

The distinction this suite exists to hold:

    WHY VOCABULARY EXISTING  !=  TRANSACTION CLASSIFIED

A Why says the purpose is understood. It never says a transaction has it.
The interpreter must still prove the purpose from the transaction's own
text, and WHO resolves nothing — seeding vocabulary does not weaken
BANK_WHO_WHY_INVARIANT_001 by one inch.

The purpose resolutions below are checked against UNPERSISTED transaction
objects: nothing is inserted, so the check is genuinely read-only.

Never touches AWS, RDS, a production database, Clover, ADP or Mercury.
"""

from __future__ import annotations

import sys

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import canonical_catalog as cc
from rfone_data_store.bank_reconciliation import deterministic_rules as dr
from rfone_data_store.bank_reconciliation import purpose_evidence as pe
from rfone_data_store.bank_reconciliation import receiver_candidates as rc
from rfone_data_store.bank_reconciliation import recognition
from rfone_data_store.bank_reconciliation import structural_why as sw
from rfone_data_store.database import (
    create_configured_engine,
    create_session_factory,
    redact_database_url,
    resolve_test_database_url,
    run_migrations_to_head,
)

# The Product Owner's five, spelled out here independently of the module
# under test so a silent edit to either side fails this suite.
EXPECTED = (
    ("FOREIGN_TRANSACTION_FEE", "7230"),
    ("CREDIT_CARD_SETTLEMENT", "2500"),
    ("LOAN_ADVANCE", "2600"),
    ("INTERNAL_BANK_TRANSFER", "1110"),
    ("SALES_TAX_REMITTANCE", "2200"),
)

# §4 — descriptions that carry their own accounting meaning.
# §4 — proven purposes, read by the ONE automatic engine
# (`structural_why`, BANK_FINAL_RELEASE_BLOCKERS_001): (description, source
# layout, amount, payer, expected Why, expected account). Structure decides,
# so the layout, the direction and the instruments involved all matter.
_CARD = sw.InstrumentInfo(9, 1, "CREDIT_CARD")
_LE1 = sw.InstrumentInfo(6, 1, "BANK_ACCOUNT")
_LE1_SAVING = sw.InstrumentInfo(4, 1, "BANK_ACCOUNT")
_LE2 = sw.InstrumentInfo(5, 2, "BANK_ACCOUNT")
_REGISTERED = {"3376": _LE1, "7129": _LE1_SAVING, "3583": _LE2}
RESOLVES = (
    ("FOREIGN TRANSACTION FEE", "CHASE_CREDIT_CARD_NO_CARD", -300, _CARD, "FOREIGN_TRANSACTION_FEE", "7230"),
    ("Payment Thank You - Web", "CHASE_CREDIT_CARD_NO_CARD", 50000, _CARD, "CREDIT_CARD_SETTLEMENT", "2500"),
    ("Online Transfer to SAV ...7129 transaction#: 30078026756", "CHASE_BANK_ACCOUNT", -10000, _LE1,
     "INTERNAL_BANK_TRANSFER", "1110"),
    ("Online Transfer to CHK ...3583 transaction#: 30078026756", "CHASE_BANK_ACCOUNT", -10000, _LE1,
     "RELATED_PARTY_TRANSFER_OUT", "1610"),
    ("CREDIT MEMORANDUM REF: ADVANCE ON LOAN TRN: 0798736999DM", "CHASE_BANK_ACCOUNT", 1000000, _LE1,
     "LOAN_ADVANCE", "2600"),
)
# Structure that proves nothing: a debit "payment thank you", a transfer to
# an account RF-One has not registered, a tax authority named without a tax.
RESOLVES_NOTHING_STRUCTURALLY = (
    ("Payment Thank You - Web", "CHASE_CREDIT_CARD_NO_CARD", -50000, _CARD),
    ("Online Transfer to CHK ...4444 transaction#: 30078026756", "CHASE_BANK_ACCOUNT", -10000, _LE1),
    ("FLA DEPT REVENUE C01 ****6811", "FIRST_CITIZENS", -397918, _LE1),
)

# §4 — identity, which resolves nothing however suggestive.
RESOLVES_NOTHING = (
    "Zelle payment to Mario Rossi JPM99cu6r5b3",
    "Zelle payment to Giovanna Wine Rep JPM99ctauxed",
    "Zelle payment to GET BETTER CLEANING JPM99cucm44t",
    "US FOODS INVOICE 4821",
    "COSTCO WHOLESALE 1234",
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

    url = resolve_test_database_url("bank_structural_why_baseline")
    print(f"Database URL: {redact_database_url(url)}")
    run_migrations_to_head(url)
    engine = create_configured_engine(url)

    try:
        session_factory = create_session_factory(engine)
        with session_factory() as s:
            reasons = {r.code: r for r in s.query(m.BankTransactionReason).all()}
            accounts = {a.id: a for a in s.query(m.BankAccountingClassification).all()}

            # =============================================================
            # 1-3. The five exist, from an ordinary migration
            # =============================================================
            # BANK_CANONICAL_WHY_AND_WHO_RELATIONSHIPS_001 widened the seeded
            # vocabulary from these five to the full 77-purpose management
            # catalog. The five are now a SUBSET — still seeded by an ordinary
            # migration, still pointing where this task fixed them, and still
            # reused rather than duplicated by the later revision.
            check(
                "1. an ordinary `alembic upgrade head` leaves the five structural purposes "
                "present — no script, no prior import",
                {code for code, _ in EXPECTED} <= set(reasons),
                detail=str(sorted({code for code, _ in EXPECTED} - set(reasons))),
            )
            check(
                "1b. they were reused, not duplicated, by the canonical WHY catalog",
                all(
                    len([r for r in reasons.values() if r.code == code]) == 1
                    for code, _ in EXPECTED
                ),
            )
            for code, account_code in EXPECTED:
                reason = reasons.get(code)
                held = accounts.get(reason.accounting_classification_id) if reason else None
                check(
                    f"2. {code} -> {account_code}",
                    reason is not None and held is not None and held.code == account_code
                    and reason.status == "ACTIVE",
                    detail="missing" if reason is None else
                           f"-> {held.code if held else None} [{reason.status}]",
                )
            check(
                "3. every structural Why points at an account that may actually receive an "
                "automatic classification",
                all(
                    accounts[reasons[code].accounting_classification_id]
                    .may_receive_automatic_classification
                    for code, _ in EXPECTED
                ),
            )
            check(
                "3b. the liability-settling purposes point at Balance Sheet accounts, so they "
                "add no P&L cost",
                all(
                    accounts[reasons[code].accounting_classification_id].statement_type
                    == "BALANCE_SHEET"
                    for code in ("CREDIT_CARD_SETTLEMENT", "LOAN_ADVANCE",
                                 "INTERNAL_BANK_TRANSFER", "SALES_TAX_REMITTANCE")
                ),
            )

            # =============================================================
            # The frozen migration copy still matches the live definition
            # =============================================================
            live = {r.why_code: r.account_code for r in dr.structural_why_baseline()}
            check(
                "3c. the live definition in `deterministic_rules` matches what the frozen "
                "migration seeded — no drift between the two",
                live == dict(EXPECTED), detail=str(live),
            )
            check(
                "3d. the baseline is a subset of the deterministic rules, resolved by code "
                "so name and account are written in exactly one place",
                set(dr.STRUCTURAL_WHY_CODES)
                <= {rule.why_code for rule in dr.DETERMINISTIC_RULES},
            )

            # =============================================================
            # 4. Idempotence and loud conflict
            # =============================================================
            outcome = dr.seed_structural_reasons(s)
            s.commit()
            before = s.query(m.BankTransactionReason).count()
            check(
                "4. re-seeding creates nothing: 0 created, 5 unchanged, and the rest of the "
                "WHY catalog is left alone",
                not outcome.created and len(outcome.unchanged) == 5
                and s.query(m.BankTransactionReason).count() == before,
                detail=f"created={len(outcome.created)} unchanged={len(outcome.unchanged)}",
            )
            target = s.query(m.BankTransactionReason).filter_by(
                code="SALES_TAX_REMITTANCE").one()
            original = target.accounting_classification_id
            target.accounting_classification_id = cc.by_code(s, "7880").id
            s.commit()
            loud = False
            try:
                dr.seed_structural_reasons(s)
            except ValueError as exc:
                loud = "SALES_TAX_REMITTANCE" in str(exc) and "2200" in str(exc)
            s.rollback()
            target = s.query(m.BankTransactionReason).filter_by(
                code="SALES_TAX_REMITTANCE").one()
            still_wrong = target.accounting_classification_id != original
            target.accounting_classification_id = original
            s.commit()
            check(
                "4b. a Why pointing somewhere else fails loudly and is NOT repointed",
                loud and still_wrong, detail=f"raised={loud} untouched={still_wrong}",
            )

            # =============================================================
            # §4. Proven purpose resolves; identity never does
            # =============================================================
            def unsaved(description: str, memo: str | None = None):
                """A transaction object that is never added to the session —
                so this whole section writes nothing at all."""
                return m.FinancialTransaction(
                    description_original=description, source_memo=memo, amount_minor=-1000,
                )

            reasons_by_code = {r.code: r for r in s.query(m.BankTransactionReason).all()}
            for description, layout, amount, payer, expected_why, expected_account in RESOLVES:
                result = sw.recognize_why(description, sw.WhyContext(
                    detected_format=layout, amount_minor=amount, instrument=payer,
                    registered_last_four=_REGISTERED, settlement_of=lambda _card: _LE1))
                reason = sw.usable_reason(s, result, reasons_by_code)
                what = accounts.get(reason.accounting_classification_id) if reason else None
                check(
                    f"§4 {description[:34]!r} -> WHY {expected_why} -> WHAT {expected_account}",
                    reason is not None and reason.code == expected_why
                    and what is not None and what.code == expected_account,
                    detail=f"why={result.why_code} tier={result.tier} what={what.code if what else None}",
                )
            for description, layout, amount, payer in RESOLVES_NOTHING_STRUCTURALLY:
                result = sw.recognize_why(description, sw.WhyContext(
                    detected_format=layout, amount_minor=amount, instrument=payer,
                    registered_last_four=_REGISTERED, settlement_of=lambda _card: _LE1))
                check(
                    f"§4 structure proves nothing: {description[:34]!r} ({amount})",
                    not result.is_resolved, detail=f"{result.tier} {result.why_code}",
                )

            for description in RESOLVES_NOTHING:
                reason, evidence = recognition.purpose_reason_for(s, unsaved(description))
                check(
                    f"§4 identity alone resolves no WHY: {description[:40]!r}",
                    reason is None and not evidence.is_resolved,
                    detail=f"why={reason.code if reason else None} ev={evidence.tier}",
                )

            check(
                "§4 a Zelle payment with no purpose evidence stays unresolved — WHO may be "
                "recognised later, WHY may not",
                recognition.purpose_reason_for(
                    s, unsaved("Zelle payment to Mario Rossi JPM99cu6r5b3"))[0] is None
                and pe.who_evidence(
                    "Zelle payment to Mario Rossi JPM99cu6r5b3").counterparty_name
                == "Mario Rossi",
            )
            check(
                "§1 vocabulary is not evidence: the same Zelle line resolves a WHY only once "
                "its own memo proves one",
                recognition.purpose_reason_for(
                    s, unsaved("Zelle payment to Mario Rossi JPM99x", "Sales tax"),
                )[0].code == "SALES_TAX_REMITTANCE",
            )

            # =============================================================
            # §5. No QA learning was reintroduced
            # =============================================================
            check("§5 WHO remains 0", s.query(m.BankOccurrence).count() == 0)
            check("§5 recognition rules remain 0",
                  s.query(m.BankRecognitionRule).count() == 0)
            check("§5 transactions remain 0",
                  s.query(m.FinancialTransaction).count() == 0
                  and s.query(m.RawBankTransaction).count() == 0)
            check("§5 human decisions / explanations remain 0",
                  s.query(m.BankTransactionExplanation).count() == 0)
            check("§5 receiver candidates remain 0", len(rc.build_candidates(s)) == 0)
            check(
                "§5 no rule carries a `created_from_transaction_id` from old QA data",
                s.query(m.BankRecognitionRule).filter(
                    m.BankRecognitionRule.created_from_transaction_id.isnot(None)
                ).count() == 0,
            )
            check(
                "§5 no Who points at a structural Why — the vocabulary was seeded alone",
                s.query(m.BankOccurrence).filter(
                    m.BankOccurrence.default_transaction_reason_id.isnot(None)
                ).count() == 0,
            )

            # =============================================================
            # Structure untouched
            # =============================================================
            check(
                "the canonical catalog is still the approved 136 accounts",
                s.query(m.BankAccountingClassification).count() == 136
                and not cc.semantic_problems(s),
            )
            check(
                "all eight deterministic rules still have a valid destination",
                not dr.destination_problems(s),
                detail="; ".join(dr.destination_problems(s)[:2]),
            )
            applicable = {rule.account_code for rule in dr.applicable_rules(s)}
            check(
                "the five structural purposes are now resolvable, and the three deterministic "
                "purposes outside the baseline are reported as still needing a Why",
                {"7230", "2500", "2600", "1110", "2200"} <= applicable,
                detail=str(sorted(applicable)),
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
