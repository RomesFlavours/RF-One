#!/usr/bin/env python
"""Bank release blockers B1-B4 (BANK_FINAL_RELEASE_BLOCKERS_001).

B1  A Who never decides a Why: `BankOccurrence.default_transaction_reason_id`
    drives no live path (Who assignment, Reclassify, the recognition-decision
    service).
B2  BANK_RULES_RESET_001: import, reprocess and instrument reassignment make
    no automatic decision (only AI rules may decide a new movement), so a
    newly imported movement has NO decision.
B3  Reprocess never overwrites a decision (human or an existing automatic
    one), decides nothing new, and is idempotent.
B4  The instrument edit path cannot change the lifecycle state; the monthly
    CLOSED / STILL_ACTIVE workflow still can.

BANK_OLD_RULES_REMOVAL_001: checks 5b, 6, 7, 8, 8b, 8c (the structural WHY
engine and the retired description rules answering directly) and 2 (the
receivers Approve of the receiver-candidate list) went with the old rule
system; B3 and 11 keep only their "no automatic decision" half. The other
numbers are unchanged.

Every check runs through the real services on a disposable database. Never
touches AWS, RDS or a production database.
"""

from __future__ import annotations

import sys

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import classification as classification_service
from rfone_data_store.bank_reconciliation import monthly_source as ms
from rfone_data_store.bank_reconciliation import recognition
from rfone_data_store.bank_reconciliation import service as bank_service
from rfone_data_store.database import (
    create_configured_engine,
    create_session_factory,
    redact_database_url,
    resolve_test_database_url,
    run_migrations_to_head,
)

CHASE_HEAD = "Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #\n"


def chase_csv(rows) -> bytes:
    """A Chase bank-account export: (details, MM/DD/YYYY, description, amount)."""
    return (CHASE_HEAD + "".join(
        f"{d},{p},\"{desc}\",{a},ACH_{d},1000.00,,\n" for d, p, desc, a in rows
    )).encode()


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}"
              + ("" if condition or not detail else f" ({detail})"))

    url = resolve_test_database_url("bank_final_release_blockers")
    print(f"Database URL: {redact_database_url(url)}")
    run_migrations_to_head(url)
    engine = create_configured_engine(url)
    try:
        with create_session_factory(engine)() as s:
            def reason(code):
                return s.query(m.BankTransactionReason).filter_by(code=code).one()

            related_out = reason("RELATED_PARTY_TRANSFER_OUT")
            internal = reason("INTERNAL_BANK_TRANSFER")
            settlement = reason("CREDIT_CARD_SETTLEMENT")
            sales_tax = reason("SALES_TAX_REMITTANCE")

            le_a = m.LegalEntity(legal_name="Entity A LLC", status="ACTIVE")
            le_b = m.LegalEntity(legal_name="Entity B LLC", status="ACTIVE")
            s.add_all([le_a, le_b])
            s.flush()

            def instrument(name, last_four, entity, kind="BANK_ACCOUNT", status="ACTIVE"):
                inst = m.PaymentInstrument(
                    instrument_type=kind, display_name=name, institution="CHASE",
                    last_four=last_four, legal_entity_id=entity.id, status=status,
                )
                s.add(inst)
                s.flush()
                return inst

            a_checking = instrument("A Checking", "3376", le_a)
            a_saving = instrument("A Saving", "7129", le_a)
            b_checking = instrument("B Checking", "3583", le_b)
            b_other = instrument("B Other", "8801", le_b)

            supplier_type = m.BankOccurrenceType(code="SUPPLIER", name="Supplier")
            s.add(supplier_type)
            s.flush()
            # A Who whose configured usual Why is the WRONG answer for the
            # transactions below: if anything still derived a Why from the
            # Who, it would show up as SALES_TAX_REMITTANCE.
            who = classification_service.create_occurrence(
                s, canonical_name="Sister Company", occurrence_type_id=supplier_type.id,
                default_transaction_reason_id=sales_tax.id,
            )
            s.commit()

            # =============================================================
            # 5. Import makes no automatic decision (BANK_RULES_RESET_001)
            # =============================================================
            imported = bank_service.import_csv(
                s, file_bytes=chase_csv([
                    ("DEBIT", "09/02/2026", "Online Transfer to CHK ...3583 transaction#: 111", "-100.00"),
                    ("DEBIT", "09/03/2026", "Online Transfer to SAV ...7129 transaction#: 112", "-200.00"),
                    ("DEBIT", "09/04/2026", "Online Transfer to CHK ...4444 transaction#: 113", "-300.00"),
                    ("DEBIT", "09/05/2026", "Payment Thank You - Web", "-400.00"),
                    ("DEBIT", "09/06/2026", "US FOODS INVOICE 4821", "-500.00"),
                ]),
                original_file_name="release-blockers.csv", uploaded_by_account_id=None,
                payment_instrument_id=a_checking.id,
            )
            s.commit()
            txns = {t.description_original.split(" transaction#")[0]: t for t in s.query(
                m.FinancialTransaction).filter_by(import_batch_id=imported.batch.id)}
            cross = txns["Online Transfer to CHK ...3583"]
            same = txns["Online Transfer to SAV ...7129"]
            unknown = txns["Online Transfer to CHK ...4444"]
            debit_thank_you = txns["Payment Thank You - Web"]
            supplier = txns["US FOODS INVOICE 4821"]

            def current(txn):
                return recognition.get_current_explanation(s, financial_transaction_id=txn.id)

            check("5. import makes no automatic decision (the old engines no longer run at import)",
                  all(current(t) is None for t in txns.values()),
                  detail=str({k: current(t) and current(t).decision_status for k, t in txns.items()}))
            # 5b-8c (the structural engine and the retired description rules
            # answering directly) went with BANK_OLD_RULES_REMOVAL_001.

            # =============================================================
            # 1, 4. Who assignment / recognition decision assign no Why
            # =============================================================
            who_decision = bank_service.record_recognition_decision(
                s, transaction_id=supplier.id, occurrence_id=who.id,
                confirmed_by_account_id=None, )
            s.commit()
            check("1. assigning a Who never assigns a Why",
                  who_decision.occurrence_id == who.id and who_decision.transaction_reason_id is None
                  and who_decision.accounting_classification_code_snapshot is None)
            check("4. the recognition-decision service does not derive the Why from the Who's default",
                  who_decision.transaction_reason_id != sales_tax.id
                  and who_decision.decision_status == "NEEDS_HUMAN_REVIEW"
                  and s.get(m.FinancialTransaction, supplier.id).review_status != "REVIEWED")

            # =============================================================
            # 3. Reclassify never derives the Why from the Who's default
            # =============================================================
            try:
                recognition.reclassify_transaction(s, transaction_id=supplier.id, confirmed_by_account_id=None)
                refused = False
            except ValueError as exc:
                refused = "no Why" in str(exc)
            s.rollback()
            check("3. Reclassify of a Who-only decision refuses rather than applying the Who's default",
                  refused)
            human = recognition.record_human_decision(s, recognition.HumanDecisionRequest(
                transaction_id=cross.id, occurrence_id=who.id, transaction_reason_id=related_out.id,
                confirmed_by_account_id=None, ))
            s.commit()
            reclassified = recognition.reclassify_transaction(
                s, transaction_id=cross.id, confirmed_by_account_id=None,
            )
            s.commit()
            check("3b. Reclassify keeps the decision's own Why, never the Who's default",
                  reclassified.transaction_reason_id == related_out.id
                  and reclassified.decision_status == "HUMAN_RECLASSIFIED",
                  detail=str(reclassified.transaction_reason_id))

            # 2 (receivers Approve) went with BANK_OLD_RULES_REMOVAL_001.

            # =============================================================
            # 9, 10. Reprocess: human preserved, automatic idempotent
            # =============================================================
            # An existing automatic decision, as an automatic rule would leave
            # it (BANK_RULES_RESET_001: imports make none now).
            recognition._create_decision_row(
                s, same, occurrence_id=None, transaction_reason_id=internal.id, decision_source="RULE", decision_status="AUTO_APPLIED", confidence=None,
                explanation_notes="Seeded as an existing automatic decision.",
                accounting_classification_id=internal.accounting_classification_id,
            )
            s.commit()
            rows_before = s.query(m.BankTransactionExplanation).count()
            auto_before = current(same).id
            bank_service.reprocess_batch(s, batch_id=imported.batch.id)
            s.commit()
            bank_service.reprocess_batch(s, batch_id=imported.batch.id)
            s.commit()
            check("9. reprocess preserves the human Why (the reclassified decision stays current)",
                  current(cross).id == reclassified.id and current(cross).transaction_reason_id == related_out.id)
            check("10. reprocess of an existing AUTO_APPLIED Why keeps it: same decision, same Why",
                  current(same).id == auto_before and current(same).transaction_reason_id == internal.id)
            check("10a. reprocess decides nothing new: an undecided transaction stays undecided",
                  current(unknown) is None and current(debit_thank_you) is None)
            check("10b. repeated reprocess appends nothing (deterministic / idempotent)",
                  s.query(m.BankTransactionExplanation).count() == rows_before,
                  detail=f"{rows_before} -> {s.query(m.BankTransactionExplanation).count()}")

            # B3 — a second cross-entity transfer, never decided by anyone.
            second = bank_service.import_csv(
                s, file_bytes=chase_csv([
                    ("DEBIT", "09/09/2026", "Online Transfer to CHK ...3583 transaction#: 114", "-150.00"),
                ]),
                original_file_name="release-blockers-2.csv", uploaded_by_account_id=None,
                payment_instrument_id=a_checking.id,
            )
            s.commit()
            disputed = s.query(m.FinancialTransaction).filter_by(import_batch_id=second.batch.id).one()
            decision_before = current(disputed)
            bank_service.reprocess_batch(s, batch_id=second.batch.id)
            s.commit()
            check("B3. an undecided transfer gets no automatic Why, neither at import nor on reprocess",
                  decision_before is None and current(disputed) is None,
                  detail=f"{decision_before} -> {current(disputed)}")

            # =============================================================
            # 11. Instrument reassignment no longer re-decides
            # (BANK_RULES_RESET_001)
            # =============================================================
            bank_service.reassign_transaction_instrument(
                s, transaction_id=disputed.id, payment_instrument_id=b_other.id,
                reason="test: the transfer was on Entity B's other account",
            )
            s.commit()
            check("11. instrument reassignment writes no automatic decision",
                  current(disputed) is None
                  and s.get(m.FinancialTransaction, disputed.id).payment_instrument_id == b_other.id,
                  detail=str(current(disputed)))

            # =============================================================
            # 12. The instrument edit path cannot change the lifecycle
            # =============================================================
            try:
                bank_service.update_payment_instrument(s, instrument_id=b_other.id, status="INACTIVE")
                edit_refused = False
            except ValueError as exc:
                edit_refused = "lifecycle" in str(exc)
            s.rollback()
            check("12. editing an instrument cannot close it (ACTIVE -> INACTIVE refused server-side)",
                  edit_refused and s.get(m.PaymentInstrument, b_other.id).status == "ACTIVE")
            dormant = instrument("Dormant", "6060", le_a, status="INACTIVE")
            s.commit()
            try:
                bank_service.update_payment_instrument(s, instrument_id=dormant.id, status="ACTIVE")
                revive_refused = False
            except ValueError:
                revive_refused = True
            s.rollback()
            check("12b. ...nor reactivate one (INACTIVE -> ACTIVE refused)",
                  revive_refused and s.get(m.PaymentInstrument, dormant.id).status == "INACTIVE")
            bank_service.update_payment_instrument(
                s, instrument_id=b_other.id, display_name="B Other (renamed)", status="ACTIVE",
            )
            s.commit()
            check("12c. non-lifecycle fields still edit (unchanged status is accepted)",
                  s.get(m.PaymentInstrument, b_other.id).display_name == "B Other (renamed)")

            # =============================================================
            # 13. CLOSED / STILL_ACTIVE still work through Monthly Sources
            # =============================================================
            period = ms.get_or_create_period(s, 2026, 9)
            ms.refresh_coverage(s, period)
            s.commit()
            coverage = {c.payment_instrument_id: c for c in ms.coverages(s, period)}
            ms.resolve_coverage(s, coverage=coverage[b_checking.id], resolution=m.RESOLUTION_CLOSED)
            s.commit()
            closed = s.get(m.PaymentInstrument, b_checking.id)
            check("13. CLOSED through Monthly Sources still ends the instrument",
                  closed.status == "INACTIVE" and closed.lifecycle_end_reason == m.RESOLUTION_CLOSED)
            if dormant.id in coverage:
                ms.resolve_coverage(s, coverage=coverage[dormant.id], resolution=m.RESOLUTION_STILL_ACTIVE)
                s.commit()
                check("13b. STILL_ACTIVE through Monthly Sources still confirms an INACTIVE instrument alive",
                      s.get(m.PaymentInstrument, dormant.id).status == "ACTIVE")
            else:
                check("13b. the INACTIVE instrument has a September coverage row to resolve", False,
                      detail=str(sorted(coverage)))
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
