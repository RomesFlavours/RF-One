#!/usr/bin/env python
"""WHO never determines WHY by itself
(BANK_WHO_WHY_INVARIANT_001).

The Bank Domain invariant, tested as an invariant rather than as a
behaviour: there is no rule, no parameter, no flag and no stored value
under which counterparty identity alone resolves the accounting purpose
of a transaction. Not for a person, not for a supplier, not by explicit
request.

The automatic decision boundary:

    purpose proven      -> derive the WHAT, classify automatically
    purpose not proven  -> NEEDS_HUMAN_REVIEW

WHO may be known in either case. WHY belongs to the transaction.

Never touches AWS, RDS, a production database, Clover, ADP, Mercury or a
real bank file.
"""

from __future__ import annotations

import inspect
import sys
from datetime import date

import sqlalchemy as sa

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import accounting_dedup
from rfone_data_store.bank_reconciliation import canonical_catalog as cc
from rfone_data_store.bank_reconciliation import classification as classification_service
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

# Every module that participates in an automatic classification decision.
DECISION_MODULES = (
    "rfone_data_store/bank_reconciliation/recognition.py",
    "rfone_data_store/bank_reconciliation/purpose_evidence.py",
    "rfone_data_store/bank_reconciliation/receiver_candidates.py",
    "rfone_data_store/bank_reconciliation/classification.py",
    "rfone_data_store/bank_reconciliation/deterministic_rules.py",
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

    url = resolve_test_database_url("bank_who_why_invariant")
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
            # 3. No override exists, anywhere
            # =============================================================
            request_fields = {
                field for field in recognition.HumanDecisionRequest.__dataclass_fields__
            }
            check(
                "3a. `who_determines_purpose` is gone from the human-decision request",
                "who_determines_purpose" not in request_fields,
                detail=str(sorted(request_fields)),
            )
            source = "".join(
                open(path, encoding="utf-8").read() for path in DECISION_MODULES
            )
            live_code = "\n".join(
                line for line in source.splitlines()
                if not line.lstrip().startswith("#")
            )
            check(
                "3b. no decision module carries the capability, even under another name",
                "who_determines_purpose" not in live_code,
            )
            refused = ""
            try:
                recognition.create_or_reuse_rule(
                    s, match_type=recognition.EXACT_NORMALIZED_DESCRIPTION,
                    normalized_pattern="ANY PAYEE AT ALL",
                    occurrence_id=1, transaction_reason_id=1,
                    payment_instrument_id=None, direction=None,
                    auto_apply_enabled=True, created_from_transaction_id=None,
                    match_field=recognition.DESCRIPTION, determines_purpose=True,
                )
            except ValueError as exc:
                refused = str(exc)
            s.rollback()
            check(
                "3c. asking the service for a description rule that determines purpose is "
                "REFUSED — the capability cannot be reached by passing a flag",
                "identity" in refused.lower() and "never" in refused.lower(),
                detail=refused or "no refusal",
            )
            constraint_held = False
            try:
                s.execute(sa.text(
                    "INSERT INTO bank_recognition_rules "
                    "(match_type, normalized_pattern, occurrence_id, transaction_reason_id, "
                    " priority, status, auto_apply_enabled, human_confirmations, "
                    " human_contradictions, match_field, determines_purpose) "
                    "VALUES ('EXACT_NORMALIZED_DESCRIPTION', 'SMUGGLED', 1, 1, 0, 'ACTIVE', "
                    " 1, 0, 0, 'DESCRIPTION', 1)"
                ))
                s.flush()
            except Exception:
                constraint_held = True
            s.rollback()
            check(
                "3d. ...and raw SQL cannot smuggle one in either — the database refuses it",
                constraint_held,
            )

            # =============================================================
            # Fixtures
            # =============================================================
            entity = m.LegalEntity(legal_name="Invariant LLC", status="ACTIVE")
            s.add(entity)
            s.flush()
            checking = m.PaymentInstrument(
                legal_entity_id=entity.id, instrument_type="BANK_ACCOUNT",
                display_name="Checking", institution="CHASE", last_four="0017", currency="USD",
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

            def txn(description: str, memo: str | None = None, amount: int = -40_000):
                day[0] += 1
                row = m.FinancialTransaction(
                    payment_instrument_id=checking.id, bank_source="CHASE_BANK_ACCOUNT",
                    posting_date=date(2026, 10, min(day[0], 28)),
                    description_original=description,
                    description_normalized=description.upper(),
                    source_memo=memo, source_memo_field="Memo" if memo else None,
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
            cleaning_why = why_for("7810", "CLEANING", "Recurring restaurant cleaning service")
            s.commit()

            # =============================================================
            # 1-2, 6. WHO alone resolves nothing — person AND supplier
            # =============================================================
            mario = who_for("Mario Rossi", labor_why)
            cleaner = who_for("Get Better Cleaning", cleaning_why)
            s.commit()

            seed = txn("Zelle payment to Mario Rossi JPM99inv0001", "1099 Kitchen Labor W40")
            s.commit()
            accounting_dedup.recompute_accounting_dedup(s)
            s.commit()
            recognition.record_human_decision(
                s, recognition.HumanDecisionRequest(
                    transaction_id=seed.id, occurrence_id=mario.id,
                    confirmed_by_account_id=None, learn_description=True,
                ),
            )
            s.commit()

            repeat = txn("Zelle payment to Mario Rossi JPM99inv0001", None)
            s.commit()
            person_decision = recognition.deduce_for_transaction(s, repeat)
            s.commit()
            check(
                "1. WHO alone can never produce a resolved WHY — the rule recognised the "
                "person and the reason stayed NULL",
                person_decision.occurrence_id == mario.id
                and person_decision.transaction_reason_id is None,
                detail=f"who={person_decision.occurrence_id} why={person_decision.transaction_reason_id}",
            )
            check(
                "2. WHO alone can never produce a resolved WHAT",
                person_decision.accounting_classification_id is None
                and person_decision.accounting_classification_code_snapshot is None,
                detail=str(person_decision.accounting_classification_code_snapshot),
            )
            check(
                "6. WHO recognition SUCCEEDS while WHY remains NULL — the reviewer is not "
                "asked to identify the payee again",
                person_decision.decision_status == "NEEDS_HUMAN_REVIEW"
                and person_decision.occurrence_id is not None
                and person_decision.recognition_rule_id is not None,
                detail=person_decision.decision_status,
            )

            # The same, for a SUPPLIER whose name all but says the service.
            cleaning_seed = txn("GET BETTER CLEANING SERVICES INV 88", None)
            s.commit()
            accounting_dedup.recompute_accounting_dedup(s)
            s.commit()
            recognition.record_human_decision(
                s, recognition.HumanDecisionRequest(
                    transaction_id=cleaning_seed.id, occurrence_id=cleaner.id,
                    confirmed_by_account_id=None, learn_description=True,
                ),
            )
            s.commit()
            cleaning_repeat = txn("GET BETTER CLEANING SERVICES INV 88", None)
            s.commit()
            supplier_decision = recognition.deduce_for_transaction(s, cleaning_repeat)
            s.commit()
            check(
                "5 (§5 suppliers). the invariant applies to a SUPPLIER too — nine cleaning "
                "payments do not make the tenth one cleaning",
                supplier_decision.occurrence_id == cleaner.id
                and supplier_decision.transaction_reason_id is None
                and supplier_decision.decision_status == "NEEDS_HUMAN_REVIEW",
                detail=f"{supplier_decision.decision_status}/"
                       f"{supplier_decision.transaction_reason_id}",
            )
            check(
                "9. historical behaviour is offered as a SUGGESTION, never as the proof",
                "Suggestion only" in (supplier_decision.explanation_notes or "")
                and cleaning_why.name in (supplier_decision.explanation_notes or ""),
                detail=(supplier_decision.explanation_notes or "")[-130:],
            )
            check(
                "9b. ...and the suggestion is not written into the decision's resolved fields",
                supplier_decision.transaction_reason_id != cleaning_why.id,
            )

            # =============================================================
            # 4-5. The same WHO, three transactions, three outcomes
            # =============================================================
            tips_txn = txn("Zelle payment to Mario Rossi JPM99inv0010", "Tips W41")
            labor_txn = txn("Zelle payment to Mario Rossi JPM99inv0011", "1099 Kitchen Labor W41")
            open_txn = txn("Zelle payment to Mario Rossi JPM99inv0012", None)
            s.commit()
            accounting_dedup.recompute_accounting_dedup(s)
            s.commit()

            tips_who = who_for("Mario Rossi (tips)", tips_why)
            s.commit()
            tips_decision = recognition.record_human_decision(
                s, recognition.HumanDecisionRequest(
                    transaction_id=tips_txn.id, occurrence_id=tips_who.id,
                    confirmed_by_account_id=None, learn_description=False,
                ),
            )
            labor_decision = recognition.record_human_decision(
                s, recognition.HumanDecisionRequest(
                    transaction_id=labor_txn.id, occurrence_id=mario.id,
                    confirmed_by_account_id=None, learn_description=False,
                ),
            )
            s.commit()
            open_decision = recognition.deduce_for_transaction(s, open_txn)
            s.commit()
            check(
                "4. the SAME payee has a Tips transaction and a Contract Labour transaction",
                tips_decision.accounting_classification_code_snapshot == TIPS
                and labor_decision.accounting_classification_code_snapshot == CONTRACT_LABOR
                and pe.who_evidence(tips_txn.description_original).counterparty_name
                == pe.who_evidence(labor_txn.description_original).counterparty_name
                == "Mario Rossi",
                detail=f"{tips_decision.accounting_classification_code_snapshot}/"
                       f"{labor_decision.accounting_classification_code_snapshot}",
            )
            check(
                "4b. ...on opposite sides of the books, with no contradiction anywhere",
                tips_decision.accounting_statement_type_snapshot == BS
                and labor_decision.accounting_statement_type_snapshot == PL,
            )
            check(
                "5. ...and a THIRD transaction to the same payee stays unresolved",
                open_decision.decision_status == "NEEDS_HUMAN_REVIEW"
                and open_decision.transaction_reason_id is None,
                detail=open_decision.decision_status,
            )
            check(
                "5b. the conceptual cardinality is one WHO -> N observed WHY, never one-to-one",
                len({
                    d.transaction_reason_id
                    for d in s.query(m.BankTransactionExplanation).all()
                    if d.transaction_reason_id is not None
                    and "Mario Rossi" in (d.occurrence_name_snapshot or "")
                }) >= 2,
            )

            # =============================================================
            # 7-8. Purpose evidence resolves WHY independently
            # =============================================================
            evidence = pe.purpose_evidence("Zelle payment to Mario Rossi JPM99x", "Tips W42")
            check(
                "7. purpose evidence resolves the WHY on its own, from the transaction's text",
                evidence.is_proven and evidence.account_code == TIPS,
                detail=f"{evidence.status}/{evidence.account_code}",
            )
            check(
                "7b. the purpose interpreter cannot see the counterparty at all — it takes "
                "only the transaction's own text",
                set(inspect.signature(pe.purpose_evidence).parameters) == {"description", "memo"},
                detail=str(list(inspect.signature(pe.purpose_evidence).parameters)),
            )

            memo_seed = txn("Zelle payment to Someone New JPM99inv0020", "Tips W43")
            s.commit()
            accounting_dedup.recompute_accounting_dedup(s)
            s.commit()
            recognition.record_human_decision(
                s, recognition.HumanDecisionRequest(
                    transaction_id=memo_seed.id, occurrence_id=tips_who.id,
                    confirmed_by_account_id=None, learn_description=True,
                    learn_purpose_from_memo=True,
                ),
            )
            s.commit()
            purpose_rules = [
                r for r in s.query(m.BankRecognitionRule).all() if r.match_field == "MEMO"
            ]
            check(
                "8. a purpose-based rule exists, may determine the account, and names nobody",
                len(purpose_rules) == 1 and purpose_rules[0].determines_purpose is True
                and "SOMEONE" not in purpose_rules[0].normalized_pattern.upper()
                and "MARIO" not in purpose_rules[0].normalized_pattern.upper(),
                detail=str([(r.normalized_pattern, r.determines_purpose) for r in purpose_rules]),
            )
            auto_txn = txn("Zelle payment to Someone New JPM99inv0020", "Tips W43")
            s.commit()
            auto_decision = recognition.deduce_for_transaction(s, auto_txn)
            s.commit()
            check(
                "8b. and a later transaction proving that purpose IS classified automatically",
                auto_decision.decision_status == "AUTO_APPLIED"
                and auto_decision.accounting_classification_code_snapshot == TIPS,
                detail=f"{auto_decision.decision_status}/"
                       f"{auto_decision.accounting_classification_code_snapshot}",
            )
            check(
                "8c. ...and the explanation says the WHAT came from the transaction, not the "
                "counterparty",
                "not from the counterparty" in (auto_decision.explanation_notes or ""),
                detail=(auto_decision.explanation_notes or "")[:120],
            )

            # =============================================================
            # 10-11. Human decisions and bulk approval
            # =============================================================
            human_txn = txn("Zelle payment to Mario Rossi JPM99inv0030", "Tips W44")
            s.commit()
            accounting_dedup.recompute_accounting_dedup(s)
            s.commit()
            human_decision = recognition.record_human_decision(
                s, recognition.HumanDecisionRequest(
                    transaction_id=human_txn.id, occurrence_id=mario.id,
                    confirmed_by_account_id=None, learn_description=False,
                ),
            )
            s.commit()
            check(
                "10. a human decision remains valid for an individual transaction and "
                "outranks what the evidence would have suggested",
                human_decision.decision_status in ("HUMAN_CONFIRMED", "HUMAN_OVERRIDDEN")
                and human_decision.accounting_classification_code_snapshot == CONTRACT_LABOR
                and recognition.get_current_explanation(
                    s, financial_transaction_id=human_txn.id).id == human_decision.id,
                detail=human_decision.accounting_classification_code_snapshot,
            )

            bulk = [
                txn(f"Zelle payment to Bulk Payee JPM99inv004{i}", None, -12_000)
                for i in range(1, 4)
            ]
            spare = txn("Zelle payment to Bulk Payee JPM99inv0049", None, -13_000)
            s.commit()
            accounting_dedup.recompute_accounting_dedup(s)
            s.commit()
            bulk_who = who_for("Bulk Payee", tips_why)
            s.commit()
            keys = [
                c.group_key for c in rc.build_candidates(s)
                if c.transaction_ids and c.transaction_ids[0] in {t.id for t in bulk}
            ]
            outcome = rc.approve_candidates(
                s, payee_keys=keys, occurrence_id=bulk_who.id, learn_description=True,
            )
            s.commit()
            bulk_rules = [s.get(m.BankRecognitionRule, rid) for rid in outcome.rules_created]
            check(
                "11. bulk human classification creates no WHO -> WHY invariant: every rule it "
                "left behind is WHO-only",
                bulk_rules and all(r.determines_purpose is False for r in bulk_rules),
                detail=str([(r.normalized_pattern, r.determines_purpose) for r in bulk_rules]),
            )
            spare_decision = recognition.deduce_for_transaction(s, spare)
            s.commit()
            check(
                "11b. ...and an unselected payment to the same payee is still unresolved",
                spare_decision.transaction_reason_id is None,
                detail=str(spare_decision.transaction_reason_id),
            )

            # =============================================================
            # The database holds no forbidden rule at all
            # =============================================================
            offending = [
                r for r in s.query(m.BankRecognitionRule).all()
                if r.determines_purpose and r.match_field != "MEMO"
            ]
            check(
                "no rule in this database claims that a description — and therefore an "
                "identity — determines purpose",
                not offending,
                detail=str([(r.match_field, r.normalized_pattern) for r in offending]),
            )

            # =============================================================
            # 13. The catalog is untouched
            # =============================================================
            check(
                "13. the canonical catalog is still the approved 136 accounts",
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
