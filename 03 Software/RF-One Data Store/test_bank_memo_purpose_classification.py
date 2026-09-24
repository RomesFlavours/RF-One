#!/usr/bin/env python
"""WHO is not WHAT
(BANK_MEMO_PURPOSE_CLASSIFICATION_001).

The question this suite exists to answer:

    can RF-One record that the SAME PERSON was paid tips on one payment
    and 1099 contract labour on the next, without contradiction and
    without ever learning that the person's identity decides either?

Everything else here is in service of that. A Zelle line names a person
and nothing more; a memo names a purpose and carries no identity; and the
two are kept apart from the parser all the way to the learned rule.

Never touches AWS, RDS, a production database, Clover, ADP, Mercury or a
real bank file.
"""

from __future__ import annotations

import sys
from datetime import date

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import accounting_dedup
from rfone_data_store.bank_reconciliation import canonical_catalog as cc
from rfone_data_store.bank_reconciliation import classification as classification_service
from rfone_data_store.bank_reconciliation import parsers
from rfone_data_store.bank_reconciliation import purpose_evidence as pe
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

TIPS = "2300"
CONTRACT_LABOR = "6800"
SALES_TAX = "2200"


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        if condition:
            passed.append(description)
        else:
            failed.append(description)
            print(f"FAILED: {description}" + (f" ({detail})" if detail else ""))

    url = resolve_test_database_url("bank_memo_purpose_classification")
    print(f"Database URL: {redact_database_url(url)}")
    run_migrations_to_head(url)
    engine = create_configured_engine(url)

    try:
        session_factory = create_session_factory(engine)
        with session_factory() as s:
            accounts = {
                row.code: row for row in s.query(m.BankAccountingClassification).all()
            }

            # =============================================================
            # 12-14. The source text is preserved, and stays separable
            # =============================================================
            card_csv = (
                b"Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n"
                b"08/01/2026,08/02/2026,ZELLE TO MARIO ROSSI,Shopping,Sale,-100.00,1099 Kitchen Labor W38\n"
                b"08/03/2026,08/04/2026,COFFEE SUPPLY CO,Food,Sale,-8.00,\n"
            )
            parsed = parsers.parse_csv_bytes(card_csv)
            by_description = {row.description: row for row in parsed.rows}
            memo_row = by_description["ZELLE TO MARIO ROSSI"]
            blank_row = by_description["COFFEE SUPPLY CO"]
            check(
                "12. the original Description is preserved exactly as the source wrote it",
                memo_row.description == "ZELLE TO MARIO ROSSI"
                and memo_row.raw_fields["Description"] == "ZELLE TO MARIO ROSSI",
            )
            check(
                "13. the original Memo is preserved where the source supplies it, together "
                "with the name of the column it came from",
                memo_row.source_memo == "1099 Kitchen Labor W38"
                and memo_row.source_memo_field == "Memo",
                detail=f"{memo_row.source_memo!r} / {memo_row.source_memo_field!r}",
            )
            check(
                "13b. a memo column that exists but is blank records no purpose evidence",
                blank_row.source_memo is None and blank_row.source_memo_field is None,
            )
            check(
                "14. description and memo are two fields, never one flattened string — the "
                "memo is absent from the description and vice versa",
                memo_row.source_memo not in (memo_row.description or "")
                and (memo_row.description or "") not in memo_row.source_memo,
            )
            check(
                "14b. the raw source row keeps every column, so nothing is recoverable only "
                "through the normalized copy",
                set(memo_row.raw_fields) >= {"Description", "Memo", "Category", "Type"},
            )

            # =============================================================
            # 1-2. Person identity determines WHO, never WHAT
            # =============================================================
            zelle = "Zelle payment to Mario Rossi JPM99cu6r5b3"
            who = pe.who_evidence(zelle)
            check(
                "1. a person payment yields a counterparty — WHO is determined",
                who.channel == pe.ZELLE and who.counterparty_name == "Mario Rossi"
                and who.is_person_channel,
                detail=f"{who.channel}/{who.counterparty_name!r}",
            )
            check(
                "1b. ...and determines no account at all",
                pe.purpose_evidence(zelle, None).account_code is None,
            )
            check(
                "2. a person payment with a blank memo has NO purpose evidence",
                pe.purpose_evidence(zelle, None).status == pe.ABSENT
                and not pe.purpose_evidence(zelle, None).is_proven,
                detail=pe.purpose_evidence(zelle, None).status,
            )
            for suggestive in (
                "Zelle payment to Giovanna Wine Rep JPM99ctauxed",
                "Zelle payment to Isaac Ortiz - Electrician 30391759511",
                "Zelle payment to Michael Costruction JPM99cuz7v2p",
                "Zelle payment to GET BETTER CLEANING JPM99cucm44t",
            ):
                evidence = pe.purpose_evidence(suggestive, None)
                check(
                    f"2b. a name that suggests a trade proves nothing "
                    f"({pe.who_evidence(suggestive).counterparty_name})",
                    not evidence.is_proven and evidence.account_code is None,
                    detail=f"{evidence.status}/{evidence.account_code}",
                )

            # =============================================================
            # 3-4. An explicit memo may classify
            # =============================================================
            tip_evidence = pe.purpose_evidence(zelle, "Tips W38")
            check(
                "3. the same Zelle line with an explicit TIP memo proves Tips Payable (2300)",
                tip_evidence.is_proven and tip_evidence.account_code == TIPS
                and tip_evidence.source_field == pe.MEMO,
                detail=f"{tip_evidence.status}/{tip_evidence.account_code}",
            )
            labor_evidence = pe.purpose_evidence(zelle, "1099 Kitchen Labor W38")
            check(
                "4. the same Zelle line with an explicit 1099 memo proves Contract Labour (6800)",
                labor_evidence.is_proven and labor_evidence.account_code == CONTRACT_LABOR,
                detail=f"{labor_evidence.status}/{labor_evidence.account_code}",
            )
            for wording, expected in (
                ("TIP W38", TIPS), ("TIPS WEEK 38", TIPS), ("Tip distribution", TIPS),
                ("1099 LABOR", CONTRACT_LABOR), ("CONTRACT LABOR", CONTRACT_LABOR),
                ("Kitchen contractor", CONTRACT_LABOR),
                ("Sales tax", SALES_TAX), ("Card payment", "2500"),
                ("Rent September", "7110"), ("Owner draw", "3400"),
            ):
                evidence = pe.purpose_evidence(zelle, wording)
                check(
                    f"4b. memo {wording!r} -> {expected}",
                    evidence.account_code == expected,
                    detail=str(evidence.account_code),
                )
            for ambiguous in ("PAYROLL", "Reimbursement", "Payment", "Services rendered"):
                evidence = pe.purpose_evidence(zelle, ambiguous)
                check(
                    f"4c. ambiguous memo {ambiguous!r} is reported ambiguous, never guessed",
                    evidence.status == pe.AMBIGUOUS and evidence.account_code is None
                    and bool(evidence.rationale),
                    detail=f"{evidence.status}/{evidence.account_code}",
                )

            # =============================================================
            # Fixtures
            # =============================================================
            entity = m.LegalEntity(legal_name="Purpose LLC", status="ACTIVE")
            s.add(entity)
            s.flush()
            checking = m.PaymentInstrument(
                legal_entity_id=entity.id, instrument_type="BANK_ACCOUNT",
                display_name="Checking", institution="CHASE", last_four="0013", currency="USD",
            )
            s.add(checking)
            s.flush()
            kind = m.BankOccurrenceType(code="COUNTERPARTY", name="Counterparty")
            s.add(kind)
            s.commit()

            def why_for(code: str, why_code: str, why_name: str):
                existing = s.query(m.BankTransactionReason).filter_by(code=why_code).first()
                if existing is not None:
                    return existing
                return classification_service.create_transaction_reason(
                    s, code=why_code, name=why_name,
                    accounting_classification_id=accounts[code].id,
                )

            def who_for(name: str, why):
                existing = s.query(m.BankOccurrence).filter_by(canonical_name=name).first()
                if existing is not None:
                    return existing
                return classification_service.create_occurrence(
                    s, canonical_name=name, occurrence_type_id=kind.id,
                    default_transaction_reason_id=why.id,
                )

            day = [0]

            def txn(description: str, memo: str | None = None, amount: int = -50_000):
                day[0] += 1
                row = m.FinancialTransaction(
                    payment_instrument_id=checking.id, bank_source="CHASE_BANK_ACCOUNT",
                    posting_date=date(2026, 9, min(day[0], 28)),
                    description_original=description,
                    description_normalized=description.upper(),
                    source_memo=memo,
                    source_memo_field="Memo" if memo else None,
                    amount_minor=amount, status="COMPLETED", duplicate_status="NONE",
                    review_status="REQUIRES_REVIEW",
                )
                s.add(row)
                s.flush()
                return row

            tips_why = why_for(TIPS, "TIPS_SETTLEMENT", "Guest tips paid out to staff")
            labor_why = why_for(
                CONTRACT_LABOR, "CONTRACT_LABOR",
                "Temporary / contract restaurant labour invoiced by the worker",
            )
            s.commit()

            # =============================================================
            # 5. THE POINT: the same person, two different accounts
            # =============================================================
            mario = who_for("Mario Rossi", labor_why)
            s.commit()

            tips_txn = txn("Zelle payment to Mario Rossi JPM99aaa0001", "Tips W38")
            labor_txn = txn("Zelle payment to Mario Rossi JPM99aaa0002", "1099 Kitchen Labor W39")
            blank_txn = txn("Zelle payment to Mario Rossi JPM99aaa0003", None)
            s.commit()
            accounting_dedup.recompute_accounting_dedup(s)
            s.commit()

            # The human confirms the WHO on each; the WHAT follows the memo,
            # which is what a purpose-driven review does.
            tips_occurrence = who_for("Mario Rossi (tips)", tips_why)
            s.commit()
            tips_decision = recognition.record_human_decision(
                s, recognition.HumanDecisionRequest(
                    transaction_id=tips_txn.id, occurrence_id=tips_occurrence.id,
                    # The human chooses the Why explicitly; a Who's default is
                    # never applied on its own (BANK_FINAL_RELEASE_BLOCKERS_001).
                    transaction_reason_id=s.get(m.BankOccurrence, tips_occurrence.id).default_transaction_reason_id,
                    confirmed_by_account_id=None, learn_description=False,
                ),
            )
            labor_decision = recognition.record_human_decision(
                s, recognition.HumanDecisionRequest(
                    transaction_id=labor_txn.id, occurrence_id=mario.id,
                    # The human chooses the Why explicitly; a Who's default is
                    # never applied on its own (BANK_FINAL_RELEASE_BLOCKERS_001).
                    transaction_reason_id=s.get(m.BankOccurrence, mario.id).default_transaction_reason_id,
                    confirmed_by_account_id=None, learn_description=False,
                ),
            )
            s.commit()
            check(
                "5. ONE person, TWO payments, TWO different accounting answers: "
                "2300 Tips Payable and 6800 Contract Labour, both recorded, no contradiction",
                tips_decision.accounting_classification_code_snapshot == TIPS
                and labor_decision.accounting_classification_code_snapshot == CONTRACT_LABOR
                and pe.who_evidence(tips_txn.description_original).counterparty_name
                == pe.who_evidence(labor_txn.description_original).counterparty_name,
                detail=f"{tips_decision.accounting_classification_code_snapshot} / "
                       f"{labor_decision.accounting_classification_code_snapshot}",
            )
            check(
                "5b. and the two land on opposite sides of the books — a liability settled "
                "with no P&L effect, and a real Labor Cost",
                tips_decision.accounting_statement_type_snapshot == BS
                and labor_decision.accounting_statement_type_snapshot == PL,
            )

            # =============================================================
            # 6. Classifying one payment teaches nothing about the person
            # =============================================================
            learned = recognition.record_human_decision(
                s, recognition.HumanDecisionRequest(
                    transaction_id=labor_txn.id, occurrence_id=mario.id,
                    # The human chooses the Why explicitly; a Who's default is
                    # never applied on its own (BANK_FINAL_RELEASE_BLOCKERS_001).
                    transaction_reason_id=s.get(m.BankOccurrence, mario.id).default_transaction_reason_id,
                    confirmed_by_account_id=None, learn_description=True,
                ),
            )
            s.commit()
            rule = s.get(m.BankRecognitionRule, learned.recognition_rule_id)
            check(
                "6. learning from a person payment creates a WHO-ONLY rule — it may not "
                "decide the account",
                rule is not None and rule.determines_purpose is False
                and rule.match_field == "DESCRIPTION",
                detail="no rule" if rule is None else
                       f"determines_purpose={rule.determines_purpose}",
            )
            check(
                "6b. no rule anywhere claims that this person's identity determines an account",
                not [
                    r for r in s.query(m.BankRecognitionRule).all()
                    if r.determines_purpose
                    and r.match_field == "DESCRIPTION"
                    and "MARIO" in (r.normalized_pattern or "").upper()
                ],
            )

            # A later payment to the same person, with no memo, must stay open.
            later_blank = txn("Zelle payment to Mario Rossi JPM99aaa0002", None)
            s.commit()
            decision = recognition.deduce_for_transaction(s, later_blank)
            s.commit()
            check(
                "8. a later payment to the SAME person with a non-matching / absent memo "
                "stays unresolved",
                decision.decision_status == "NEEDS_HUMAN_REVIEW"
                and decision.transaction_reason_id is None,
                detail=f"{decision.decision_status}/{decision.transaction_reason_id}",
            )
            check(
                "8b. ...while still naming the Who the rule recognised, so the reviewer is "
                "not asked to identify the person again",
                decision.occurrence_id == mario.id,
                detail=str(decision.occurrence_id),
            )
            check(
                "8c. and the explanation says why it stopped",
                "identity alone never establishes" in (decision.explanation_notes or ""),
                detail=(decision.explanation_notes or "")[:120],
            )

            # =============================================================
            # 7. A purpose rule generalises; it carries no identity
            # =============================================================
            purpose_learn = recognition.record_human_decision(
                s, recognition.HumanDecisionRequest(
                    transaction_id=tips_txn.id, occurrence_id=tips_occurrence.id,
                    # The human chooses the Why explicitly; a Who's default is
                    # never applied on its own (BANK_FINAL_RELEASE_BLOCKERS_001).
                    transaction_reason_id=s.get(m.BankOccurrence, tips_occurrence.id).default_transaction_reason_id,
                    confirmed_by_account_id=None, learn_description=False,
                    learn_purpose_from_memo=True,
                ),
            )
            s.commit()
            memo_rules = [
                r for r in s.query(m.BankRecognitionRule).all() if r.match_field == "MEMO"
            ]
            check(
                "7. an explicit purpose rule is learned from the MEMO wording and may decide "
                "the account",
                len(memo_rules) == 1 and memo_rules[0].determines_purpose is True
                and "TIPS W38" in memo_rules[0].normalized_pattern.upper(),
                detail=str([(r.normalized_pattern, r.determines_purpose) for r in memo_rules]),
            )
            check(
                "7b. the purpose rule's pattern contains no person's name",
                "MARIO" not in memo_rules[0].normalized_pattern.upper(),
            )

            # A DIFFERENT person, same memo wording -> the purpose rule applies.
            other_txn = txn("Zelle payment to Someone Entirely Else JPM99bbb0001", "Tips W38")
            s.commit()
            matched = recognition.find_candidate_rules(
                s, normalized_description=recognition.normalize_description_for_recognition(
                    other_txn.description_original),
                payment_instrument_id=checking.id, direction="DEBIT",
                normalized_memo=recognition.normalize_memo_for_recognition(other_txn.source_memo),
            )
            check(
                "7c. that purpose rule matches a matching memo on a DIFFERENT counterparty — "
                "the knowledge is about the wording, not the person",
                any(r.match_field == "MEMO" for r in matched),
                detail=str([(r.match_field, r.normalized_pattern) for r in matched]),
            )
            no_memo_txn = txn("Zelle payment to Someone Entirely Else JPM99bbb0002", None)
            s.commit()
            unmatched = recognition.find_candidate_rules(
                s, normalized_description=recognition.normalize_description_for_recognition(
                    no_memo_txn.description_original),
                payment_instrument_id=checking.id, direction="DEBIT",
                normalized_memo=recognition.normalize_memo_for_recognition(no_memo_txn.source_memo),
            )
            check(
                "7d. and matches nothing when there is no memo — a memo rule is never retried "
                "against the description",
                not [r for r in unmatched if r.match_field == "MEMO"],
            )

            # =============================================================
            # 9-10. Human precedence, and suppressed rows
            # =============================================================
            human_txn = txn("Zelle payment to Mario Rossi JPM99aaa0009", "Tips W40")
            s.commit()
            accounting_dedup.recompute_accounting_dedup(s)
            s.commit()
            first = recognition.record_human_decision(
                s, recognition.HumanDecisionRequest(
                    transaction_id=human_txn.id, occurrence_id=mario.id,
                    # The human chooses the Why explicitly; a Who's default is
                    # never applied on its own (BANK_FINAL_RELEASE_BLOCKERS_001).
                    transaction_reason_id=s.get(m.BankOccurrence, mario.id).default_transaction_reason_id,
                    confirmed_by_account_id=None, learn_description=False,
                ),
            )
            s.commit()
            check(
                "9. a human decision overrides what the purpose evidence would have suggested",
                first.accounting_classification_code_snapshot == CONTRACT_LABOR
                and pe.purpose_evidence(
                    human_txn.description_original, human_txn.source_memo
                ).account_code == TIPS
                and recognition.get_current_explanation(
                    s, financial_transaction_id=human_txn.id).id == first.id,
                detail=first.accounting_classification_code_snapshot,
            )

            original = txn("Zelle payment to Carla Duplicate JPM99ddd0001", "Tips W41", -7_700)
            copy = txn("Zelle payment to Carla Duplicate JPM99ddd0001", "Tips W41", -7_700)
            copy.posting_date = original.posting_date
            s.commit()
            accounting_dedup.recompute_accounting_dedup(s)
            s.commit()
            check(
                "10. a duplicate-suppressed row is excluded from classification even when its "
                "memo proves a purpose",
                copy.accounting_status == accounting_dedup.DUPLICATE_SUPPRESSED
                and copy.id not in {
                    tid for c in rc.build_candidates(s) for tid in c.transaction_ids
                },
                detail=str(copy.accounting_status),
            )

            # =============================================================
            # 11. Bulk classification touches only what was selected
            # =============================================================
            bulk = [
                txn(f"Zelle payment to Tatiana Ceban JPM99eee000{i}", None, -30_000)
                for i in range(1, 4)
            ]
            untouched = txn("Zelle payment to Tatiana Ceban JPM99eee0009", None, -31_000)
            s.commit()
            accounting_dedup.recompute_accounting_dedup(s)
            s.commit()
            tatiana = who_for("Tatiana Ceban", tips_why)
            s.commit()
            selected_keys = [
                c.group_key for c in rc.build_candidates(s)
                if c.transaction_ids and c.transaction_ids[0] in {t.id for t in bulk}
            ]
            outcome = rc.approve_candidates(
                s, payee_keys=selected_keys, occurrence_id=tatiana.id,
                learn_description=True,
            )
            s.commit()
            check(
                "11. bulk approval classified exactly the selected transactions",
                outcome.transactions_classified == len(bulk),
                detail=f"{outcome.transactions_classified} of {len(bulk)}",
            )
            untouched_decision = recognition.get_current_explanation(
                s, financial_transaction_id=untouched.id)
            check(
                "11b. a payment to the SAME person that was not selected is untouched",
                untouched_decision is None
                or untouched_decision.decision_status == "NEEDS_HUMAN_REVIEW",
                detail="" if untouched_decision is None else untouched_decision.decision_status,
            )
            bulk_rules = [s.get(m.BankRecognitionRule, rid) for rid in outcome.rules_created]
            check(
                "11c. and the rules it left behind recognise WHO only — bulk approval never "
                "becomes \"Tatiana means tips forever\"",
                bulk_rules and all(r.determines_purpose is False for r in bulk_rules),
                detail=str([(r.normalized_pattern, r.determines_purpose) for r in bulk_rules]),
            )
            candidate_for_person = next(
                (c for c in rc.build_candidates(s) if c.is_person_channel), None,
            )
            check(
                "11d. the review UI states what a learned rule will use, before it is ticked",
                candidate_for_person is not None
                and "WHO only" in (candidate_for_person.learning_warning or ""),
                detail=(candidate_for_person.learning_warning or "")[:80]
                if candidate_for_person else "no person candidate",
            )

            # =============================================================
            # 15-18. The accounting-event boundary holds
            # =============================================================
            check(
                "15/17. a Tips payout settles a liability — Balance Sheet, no second P&L cost",
                accounts[TIPS].statement_type == BS
                and tips_decision.accounting_statement_type_snapshot == BS
                and TIPS not in cc.subtree_codes(s, "6000"),
            )
            check(
                "16. Sales Tax remains a Balance Sheet liability",
                accounts[SALES_TAX].statement_type == BS,
            )
            check(
                "18. Contract Labour remains a Profit & Loss Labor Cost",
                accounts[CONTRACT_LABOR].statement_type == PL
                and CONTRACT_LABOR in cc.subtree_codes(s, "6000"),
            )
            for code in ("2100", "2200", "2300", "2400", "2500"):
                check(
                    f"15b. {code} {accounts[code].name} is a liability, so settling it never "
                    "creates an expense",
                    accounts[code].statement_type == BS
                    and accounts[code].normal_balance == cc.CREDIT,
                )
            settlement_purposes = [
                rule for rule in pe.PURPOSE_RULES if rule.no_pl_effect
            ]
            check(
                "15c. every purpose rule that means \"a recorded liability is being settled\" "
                "points at a Balance Sheet account",
                all(
                    accounts[rule.account_code].statement_type == BS
                    for rule in settlement_purposes
                ),
                detail=str([r.account_code for r in settlement_purposes
                            if accounts[r.account_code].statement_type != BS]),
            )
            check(
                "15d. and every purpose rule points at an account that may actually receive "
                "an automatic classification",
                all(
                    accounts[rule.account_code].may_receive_automatic_classification
                    for rule in pe.PURPOSE_RULES
                ),
                detail=str([r.account_code for r in pe.PURPOSE_RULES
                            if not accounts[r.account_code].may_receive_automatic_classification]),
            )

            # =============================================================
            # 19. The catalog did not move
            # =============================================================
            check(
                "19. the canonical catalog is still the approved 136 accounts",
                len(accounts) == 136 and not cc.semantic_problems(s),
                detail=f"{len(accounts)} accounts",
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
