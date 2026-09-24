#!/usr/bin/env python
"""Tests for Phase 6B — operationalizing canonical internal-transfer
matching (FINANCIAL_MODEL_CONVERGENCE_001 Phase 6B).

Phase 6 (`bank_reconciliation/matching.py`) already implements the
deterministic AUTO/HUMAN matching engine itself — see
`test_cross_ledger_matching.py`, which this suite does not duplicate.
This suite proves the Phase 6B additions specifically:

1. the canonical, source-neutral post-acquisition hook
   (`matching.on_financial_transaction_acquired`) delegates to that
   existing engine without duplicating its logic or setting
   classification itself;
2. Bank CSV acquisition (`service.import_csv`) and PayPal acquisition
   (`technical/connectors/paypal/ingest.ingest_transaction_details`) both
   invoke that ONE shared hook automatically, regardless of which side of
   an internal transfer is acquired first (order independence);
3. the `compute_export_blockers`/`build_kermali_workbook` INTERNAL_
   TRANSFER exemption (Product Owner Decisions A/B): a CONFIRMED internal
   transfer is exempt from the "Missing reconciliation decision" blocker
   and from Kermali workbook rows, but classification alone (without a
   confirmed match) is never trusted.

Always targets its own disposable, self-provisioned SQLite database (never
`RFONE_DATABASE_URL`/the shared local `data/rfone.db`) — same convention as
the other Bank Reconciliation test scripts in this directory.

Usage:
    python test_internal_transfer_matching_6b.py
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from io import BytesIO

import openpyxl
from sqlalchemy import select

from rfone_data_store.bank_reconciliation import export, matching, recognition, service
from rfone_data_store.database import (
    cleanup_disposable_test_database_url,
    create_configured_engine,
    create_disposable_test_database_url,
    create_session_factory,
)
from rfone_data_store import models as m
from rfone_data_store.technical.connectors.paypal import ingest

UTC = timezone.utc

CHASE_BANK_CSV_HEADER = "Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #\n"
CHASE_CARD_CSV_HEADER = "Card,Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n"


def _chase_bank_row(*, posting_date: str, description: str, amount: str, balance: str = "1000.00") -> str:
    return f"DEBIT,{posting_date},{description},{amount},ACH_DEBIT,{balance},\n"


def _chase_card_row(*, card: str, txn_date: str, post_date: str, description: str, amount: str) -> str:
    return f"{card},{txn_date},{post_date},{description},Travel,Sale,{amount},\n"


def _paypal_transfer_out_raw(transaction_id: str, *, iso_datetime: str, amount: str) -> dict:
    return {
        "transaction_info": {
            "transaction_id": transaction_id,
            "transaction_event_code": "T0400",
            "transaction_initiation_date": iso_datetime,
            "transaction_amount": {"currency_code": "USD", "value": amount},
            "transaction_status": "S",
            "transaction_subject": "Withdraw to bank",
        },
        "payer_info": {},
    }


class Result:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[str] = []

    def check(self, description: str, condition: bool) -> None:
        (self.passed if condition else self.failed).append(description)


def main() -> int:
    url = create_disposable_test_database_url("internal_transfer_matching_6b")
    result = Result()
    try:
        engine = create_configured_engine(url)
        session_factory = create_session_factory(engine)
        with session_factory() as s:
            legal_entity = m.LegalEntity(legal_name="Phase 6B Test LE", status="ACTIVE")
            s.add(legal_entity)
            s.flush()

            bank = m.PaymentInstrument(
                legal_entity_id=legal_entity.id, instrument_type="BANK_ACCOUNT",
                display_name="Operating Checking", currency="USD",
            )
            s.add(bank)
            s.flush()

            paypal = m.PaymentInstrument(
                legal_entity_id=legal_entity.id, instrument_type="PAYPAL",
                display_name="PayPal Business", currency="USD", linked_instrument_id=bank.id,
            )
            credit_card = m.PaymentInstrument(
                legal_entity_id=legal_entity.id, instrument_type="CREDIT_CARD",
                display_name="Business Amex", currency="USD", linked_instrument_id=bank.id,
            )
            unlinked_paypal = m.PaymentInstrument(
                legal_entity_id=legal_entity.id, instrument_type="PAYPAL",
                display_name="Unlinked PayPal (no configured settlement account)", currency="USD",
            )
            s.add_all([paypal, credit_card, unlinked_paypal])
            s.commit()

            # =================================================================
            # Section 18 — canonical hook itself: delegation, no duplicated
            # logic, no self-set classification, ambiguity/no-candidate cases.
            # =================================================================

            # No candidate at all -> hook returns None, delegating entirely to
            # auto_match_transaction (which itself returns None for zero
            # candidates) rather than any independent logic in the hook.
            lonely = m.FinancialTransaction(
                payment_instrument_id=bank.id, transaction_datetime=datetime(2026, 8, 1, 9, 0, tzinfo=UTC),
                amount_minor=-42, classification="UNKNOWN",
            )
            s.add(lonely)
            s.flush()
            hook_result_none = matching.on_financial_transaction_acquired(s, lonely)
            result.check(
                "hook with zero candidates returns None (delegates to auto_match_transaction, §18.4)",
                hook_result_none is None,
            )
            s.refresh(lonely)
            result.check(
                "hook never sets classification itself when no match is created (§18.3)",
                lonely.classification == "UNKNOWN",
            )

            # A transaction the CSV duplicate-detection pipeline already
            # marked CANDIDATE_DUPLICATE is not eligible for matching at all
            # — the hook itself must recognize this, never matching.py.
            dup_paypal = m.PaymentInstrument(
                legal_entity_id=legal_entity.id, instrument_type="PAYPAL",
                display_name="Dup-check PayPal", currency="USD", linked_instrument_id=bank.id,
            )
            s.add(dup_paypal)
            s.flush()
            counterpart_for_dup = m.FinancialTransaction(
                payment_instrument_id=bank.id, transaction_datetime=datetime(2026, 8, 2, 9, 0, tzinfo=UTC),
                amount_minor=500, classification="UNKNOWN",
            )
            s.add(counterpart_for_dup)
            s.flush()
            candidate_duplicate_txn = m.FinancialTransaction(
                payment_instrument_id=dup_paypal.id, transaction_datetime=datetime(2026, 8, 2, 9, 0, tzinfo=UTC),
                amount_minor=-500, classification="UNKNOWN", duplicate_status="CANDIDATE_DUPLICATE",
            )
            s.add(candidate_duplicate_txn)
            s.flush()
            hook_result_dup = matching.on_financial_transaction_acquired(s, candidate_duplicate_txn)
            result.check(
                "hook refuses a CANDIDATE_DUPLICATE transaction even though a perfect candidate exists (§18, task §6)",
                hook_result_dup is None,
            )
            result.check(
                "the CANDIDATE_DUPLICATE row was never matched (still eligible for human duplicate review first)",
                not matching.is_matched(s, candidate_duplicate_txn.id),
            )

            # Ambiguous evidence (two equally-valid linked candidates) -> hook
            # must not choose one arbitrarily; delegates the "no AUTO match"
            # outcome from find_cross_ledger_candidates/auto_match_transaction.
            ambiguous_bank_1 = m.FinancialTransaction(
                payment_instrument_id=bank.id, transaction_datetime=datetime(2026, 8, 3, 9, 0, tzinfo=UTC),
                amount_minor=1000, classification="UNKNOWN",
            )
            ambiguous_bank_2 = m.FinancialTransaction(
                payment_instrument_id=bank.id, transaction_datetime=datetime(2026, 8, 3, 9, 5, tzinfo=UTC),
                amount_minor=1000, classification="UNKNOWN",
            )
            s.add_all([ambiguous_bank_1, ambiguous_bank_2])
            s.flush()
            ambiguous_paypal_out = m.FinancialTransaction(
                payment_instrument_id=paypal.id, transaction_datetime=datetime(2026, 8, 3, 9, 2, tzinfo=UTC),
                amount_minor=-1000, classification="UNKNOWN",
            )
            s.add(ambiguous_paypal_out)
            s.flush()
            hook_result_ambiguous = matching.on_financial_transaction_acquired(s, ambiguous_paypal_out)
            result.check(
                "hook with 2 plausible candidates does NOT auto-match (ambiguity preserved, §10/§18.5)",
                hook_result_ambiguous is None,
            )
            s.commit()

            # =================================================================
            # Section 19 / 22 — CSV second side: PayPal transfer-out already
            # exists; a matching Bank CSV deposit arrives later via the real
            # service.import_csv path (not calling matching.py directly).
            # =================================================================
            paypal_run_1 = ingest.ingest_transaction_details(
                s, payment_instrument_id=paypal.id,
                raw_transaction_details=[
                    _paypal_transfer_out_raw(
                        "PP-6B-TRANSFER-1", iso_datetime="2026-08-05T09:00:00.000Z", amount="-412.50",
                    ),
                ],
            )
            s.commit()
            paypal_side_1 = s.scalars(
                select(m.FinancialTransaction).filter_by(external_transaction_id="PP-6B-TRANSFER-1")
            ).first()
            result.check(
                "PayPal-side transfer-out created before its Bank counterpart (§19 setup)",
                paypal_side_1 is not None and not matching.is_matched(s, paypal_side_1.id),
            )

            bank_csv_1 = CHASE_BANK_CSV_HEADER + _chase_bank_row(
                posting_date="08/05/2026", description="PAYPAL TRANSFER", amount="412.50",
            )
            csv_import_1 = service.import_csv(
                s, file_bytes=bank_csv_1.encode("utf-8"), original_file_name="chase_6b_1.csv",
                uploaded_by_account_id=None, payment_instrument_id=bank.id,
            )
            s.commit()
            result.check(
                "CSV import created exactly one normalized row (§19)",
                csv_import_1.normalized_row_count == 1,
            )
            bank_side_1 = s.scalars(
                select(m.FinancialTransaction).where(
                    m.FinancialTransaction.import_batch_id == csv_import_1.batch.id,
                )
            ).first()
            result.check(
                "the CSV-acquired Bank deposit was AUTO-matched automatically — no explicit matching.py call (§19)",
                matching.is_matched(s, bank_side_1.id),
            )
            s.refresh(paypal_side_1)
            s.refresh(bank_side_1)
            result.check(
                "both sides became INTERNAL_TRANSFER once the second (CSV) side was acquired (§19)",
                paypal_side_1.classification == "INTERNAL_TRANSFER" and bank_side_1.classification == "INTERNAL_TRANSFER",
            )
            result.check(
                "CSV provenance (import_batch_id, source_row_number) preserved on the matched row (§19)",
                bank_side_1.import_batch_id == csv_import_1.batch.id and bank_side_1.source_row_number == 2,
            )
            result.check(
                "PayPal provenance (external_transaction_id) preserved on its side (§19)",
                paypal_side_1.external_transaction_id == "PP-6B-TRANSFER-1",
            )

            # =================================================================
            # Section 20 / 22 — PayPal second side: Bank CSV transaction
            # already exists; a matching PayPal transfer arrives later.
            # Together with the block above, this proves order independence:
            # PayPal-then-Bank (above) and Bank-then-PayPal (below) both
            # converge on the same outcome for equivalent evidence.
            # =================================================================
            bank_csv_2 = CHASE_BANK_CSV_HEADER + _chase_bank_row(
                posting_date="08/10/2026", description="ACH WITHDRAWAL PAYPAL", amount="-88.00",
            )
            csv_import_2 = service.import_csv(
                s, file_bytes=bank_csv_2.encode("utf-8"), original_file_name="chase_6b_2.csv",
                uploaded_by_account_id=None, payment_instrument_id=bank.id,
            )
            s.commit()
            bank_side_2 = s.scalars(
                select(m.FinancialTransaction).where(
                    m.FinancialTransaction.import_batch_id == csv_import_2.batch.id,
                )
            ).first()
            result.check(
                "Bank-side transaction created before its PayPal counterpart, unmatched so far (§20 setup)",
                bank_side_2 is not None and not matching.is_matched(s, bank_side_2.id),
            )

            paypal_run_2 = ingest.ingest_transaction_details(
                s, payment_instrument_id=paypal.id,
                raw_transaction_details=[
                    _paypal_transfer_out_raw(
                        "PP-6B-TRANSFER-2", iso_datetime="2026-08-10T09:00:00.000Z", amount="88.00",
                    ),
                ],
            )
            s.commit()
            paypal_side_2 = s.scalars(
                select(m.FinancialTransaction).filter_by(external_transaction_id="PP-6B-TRANSFER-2")
            ).first()
            result.check(
                "the PayPal-acquired row was AUTO-matched automatically — no explicit matching.py call (§20)",
                matching.is_matched(s, paypal_side_2.id),
            )
            s.refresh(bank_side_2)
            s.refresh(paypal_side_2)
            result.check(
                "both sides became INTERNAL_TRANSFER once the second (PayPal) side was acquired (§20)",
                bank_side_2.classification == "INTERNAL_TRANSFER" and paypal_side_2.classification == "INTERNAL_TRANSFER",
            )
            result.check(
                "PayPal provenance (SourceRecord under this IngestionRun) preserved (§20)",
                s.scalars(
                    select(m.SourceRecord).filter_by(ingestion_run_id=paypal_run_2.id, source_id="PP-6B-TRANSFER-2")
                ).first() is not None,
            )

            # =================================================================
            # Section 21 — Bank Account <-> Credit Card, no PayPal involved.
            # =================================================================
            bank_csv_3 = CHASE_BANK_CSV_HEADER + _chase_bank_row(
                posting_date="08/15/2026", description="AMEX PAYMENT", amount="-250.00",
            )
            csv_import_3 = service.import_csv(
                s, file_bytes=bank_csv_3.encode("utf-8"), original_file_name="chase_6b_3.csv",
                uploaded_by_account_id=None, payment_instrument_id=bank.id,
            )
            s.commit()
            card_csv_3 = CHASE_CARD_CSV_HEADER + _chase_card_row(
                card="9021", txn_date="08/15/2026", post_date="08/16/2026",
                description="AUTOPAY PAYMENT - THANK YOU", amount="250.00",
            )
            csv_import_4 = service.import_csv(
                s, file_bytes=card_csv_3.encode("utf-8"), original_file_name="amex_6b_1.csv",
                uploaded_by_account_id=None, payment_instrument_id=credit_card.id,
            )
            s.commit()
            bank_side_3 = s.scalars(
                select(m.FinancialTransaction).where(m.FinancialTransaction.import_batch_id == csv_import_3.batch.id)
            ).first()
            card_side_3 = s.scalars(
                select(m.FinancialTransaction).where(m.FinancialTransaction.import_batch_id == csv_import_4.batch.id)
            ).first()
            result.check(
                "Bank <-> Credit Card AUTO-matched via two ordinary CSV imports, no PayPal instrument involved (§21)",
                matching.is_matched(s, bank_side_3.id) and matching.is_matched(s, card_side_3.id)
                and paypal.id not in (bank_side_3.payment_instrument_id, card_side_3.payment_instrument_id)
                and paypal.id not in (bank_side_3.payment_instrument_id, card_side_3.payment_instrument_id),
            )
            s.refresh(bank_side_3)
            s.refresh(card_side_3)
            result.check(
                "both Bank and Credit Card sides classified INTERNAL_TRANSFER (§21)",
                bank_side_3.classification == "INTERNAL_TRANSFER" and card_side_3.classification == "INTERNAL_TRANSFER",
            )

            # =================================================================
            # Section 23 — idempotency: repeated acquisition creates no
            # duplicate match; the same pair remains ONE FinancialTransactionMatch.
            # =================================================================
            match_count_before = len(s.scalars(
                select(m.FinancialTransactionMatch).where(
                    m.FinancialTransactionMatch.transaction_a_id.in_([paypal_side_1.id, bank_side_1.id]),
                    m.FinancialTransactionMatch.transaction_b_id.in_([paypal_side_1.id, bank_side_1.id]),
                )
            ).all())

            # Repeated PayPal sync with the SAME transaction_id (idempotent upsert).
            ingest.ingest_transaction_details(
                s, payment_instrument_id=paypal.id,
                raw_transaction_details=[
                    _paypal_transfer_out_raw(
                        "PP-6B-TRANSFER-1", iso_datetime="2026-08-05T09:00:00.000Z", amount="-412.50",
                    ),
                ],
            )
            s.commit()
            result.check(
                "re-syncing the same PayPal transaction_id updates the existing row, still exactly one match (§23)",
                len(s.scalars(select(m.FinancialTransaction).filter_by(external_transaction_id="PP-6B-TRANSFER-1")).all()) == 1,
            )

            # Repeated CSV import with the SAME bytes (idempotent by sha256).
            repeat_csv_import = service.import_csv(
                s, file_bytes=bank_csv_1.encode("utf-8"), original_file_name="chase_6b_1_reupload.csv",
                uploaded_by_account_id=None, payment_instrument_id=bank.id,
            )
            s.commit()
            result.check(
                "re-uploading the same CSV bytes reuses the existing batch, creates nothing new (§23)",
                repeat_csv_import.created is False and repeat_csv_import.batch.id == csv_import_1.batch.id,
            )

            # Calling the hook again directly on an already-matched transaction.
            hook_repeat = matching.on_financial_transaction_acquired(s, bank_side_1)
            result.check(
                "invoking the hook again on an already-matched transaction is harmless (returns None, §23)",
                hook_repeat is None,
            )

            match_count_after = len(s.scalars(
                select(m.FinancialTransactionMatch).where(
                    m.FinancialTransactionMatch.transaction_a_id.in_([paypal_side_1.id, bank_side_1.id]),
                    m.FinancialTransactionMatch.transaction_b_id.in_([paypal_side_1.id, bank_side_1.id]),
                )
            ).all())
            result.check(
                "the pair remains exactly ONE FinancialTransactionMatch after all repeats (§23)",
                match_count_before == 1 and match_count_after == 1,
            )

            # =================================================================
            # Section 16 — existing Recognition history is preserved when a
            # transaction later becomes INTERNAL_TRANSFER.
            # =================================================================
            occurrence_type = m.BankOccurrenceType(code="MISC_6B", name="Misc 6B")
            s.add(occurrence_type)
            s.flush()
            # BANK_RECONCILIATION_WHO_WHY_WHAT_001: the Who needs a complete
            # Who -> Why -> What chain before it can classify anything.
            what = m.BankAccountingClassification(
                code="OPERATING_6B", name="Operating 6B", statement_type="PROFIT_LOSS",
            )
            s.add(what)
            s.flush()
            reason = m.BankTransactionReason(
                code="OPERATIONAL_6B", name="Operational 6B", accounting_classification_id=what.id,
            )
            s.add(reason)
            s.flush()
            occurrence = m.BankOccurrence(
                canonical_name="Some Vendor", occurrence_type_id=occurrence_type.id,
                default_transaction_reason_id=reason.id,
            )
            s.add(occurrence)
            s.flush()

            pre_recognized_bank = m.FinancialTransaction(
                payment_instrument_id=bank.id, transaction_datetime=datetime(2026, 8, 20, 9, 0, tzinfo=UTC),
                amount_minor=-6000, classification="UNKNOWN", duplicate_status="NONE",
            )
            s.add(pre_recognized_bank)
            s.flush()
            explanation_before = service.record_recognition_decision(
                s, transaction_id=pre_recognized_bank.id, occurrence_id=occurrence.id,
                confirmed_by_account_id=None, learn_description=False,
            )
            s.commit()
            explanation_before_id = explanation_before.id

            pre_recognized_paypal = m.FinancialTransaction(
                payment_instrument_id=paypal.id, transaction_datetime=datetime(2026, 8, 20, 9, 3, tzinfo=UTC),
                amount_minor=6000, classification="UNKNOWN",
            )
            s.add(pre_recognized_paypal)
            s.flush()
            hook_after_recognition = matching.on_financial_transaction_acquired(s, pre_recognized_paypal)
            s.commit()
            result.check(
                "a transaction with an EXISTING Recognition decision can still become matched later (§16)",
                hook_after_recognition is not None,
            )
            s.refresh(pre_recognized_bank)
            result.check(
                "the pre-existing BankTransactionExplanation row is NOT deleted (§16)",
                s.get(m.BankTransactionExplanation, explanation_before_id) is not None,
            )
            result.check(
                "the pre-existing decision's explanation_id link is untouched — no fabricated new WHO/WHY (§16)",
                pre_recognized_bank.explanation_id == explanation_before_id,
            )
            result.check(
                "classification became INTERNAL_TRANSFER via the matching service, alongside the preserved decision (§16)",
                pre_recognized_bank.classification == "INTERNAL_TRANSFER",
            )

            s.commit()

            # =================================================================
            # Section 25 — export-blocker INTERNAL_TRANSFER exemption.
            # =================================================================
            year, month = 2026, 8

            # A: confirmed INTERNAL_TRANSFER + confirmed match -> NOT flagged
            # as "Missing reconciliation decision", regardless of whether
            # Recognition (Phase 4B, unrelated to Phase 6B) already left its
            # own NEEDS_HUMAN_REVIEW placeholder decision on the row before
            # the match was ever created — Phase 6B fabricates nothing.
            blockers_a = export.compute_export_blockers(s, year=year, month=month)
            blocker_reasons_a = [b.reason for b in blockers_a]
            result.check(
                "confirmed INTERNAL_TRANSFER transactions do NOT trigger the missing-Who blocker (§25.A)",
                not any(
                    f"transaction id={bank_side_1.id} " in reason and "Missing Who" in reason
                    for reason in blocker_reasons_a
                )
                and not any(
                    f"transaction id={paypal_side_1.id} " in reason and "Missing Who" in reason
                    for reason in blocker_reasons_a
                ),
            )

            # B: classification == INTERNAL_TRANSFER WITHOUT a confirmed match
            # -> exemption NOT granted (classification alone is never trusted).
            fake_transfer = m.FinancialTransaction(
                payment_instrument_id=bank.id, transaction_datetime=datetime(2026, 8, 22, 9, 0, tzinfo=UTC),
                posting_date=date(2026, 8, 22), amount_minor=-999, classification="INTERNAL_TRANSFER",
                duplicate_status="NONE", description_original="FAKE TRANSFER (no real match)",
            )
            s.add(fake_transfer)
            s.commit()
            result.check(
                "the unmatched fake-classification row really has no FinancialTransactionMatch (§25.B setup)",
                not matching.is_matched(s, fake_transfer.id),
            )
            blockers_b = export.compute_export_blockers(s, year=year, month=month)
            result.check(
                "classification == INTERNAL_TRANSFER WITHOUT a confirmed match is STILL blocked (§25.B)",
                any(f"transaction id={fake_transfer.id} " in b.reason for b in blockers_b),
            )

            # C: an ordinary unresolved transaction -> existing blocker unchanged.
            ordinary_unresolved = m.FinancialTransaction(
                payment_instrument_id=bank.id, transaction_datetime=datetime(2026, 8, 23, 9, 0, tzinfo=UTC),
                posting_date=date(2026, 8, 23), amount_minor=-7500, classification="UNKNOWN",
                duplicate_status="NONE", description_original="ORDINARY UNRESOLVED EXPENSE",
            )
            s.add(ordinary_unresolved)
            s.commit()
            blockers_c = export.compute_export_blockers(s, year=year, month=month)
            result.check(
                "an ordinary unresolved (non-transfer) transaction is still blocked exactly as before (§25.C)",
                any(f"transaction id={ordinary_unresolved.id} " in b.reason for b in blockers_c),
            )

            # D: no fake Occurrence/Reason was ever invented for the confirmed
            # transfers to force an artificial "resolved" decision — the only
            # BankTransactionExplanation rows on these transactions (if any)
            # are Recognition's own pre-existing, unrelated NEEDS_HUMAN_REVIEW
            # placeholder (no occurrence_id/transaction_reason_id at all),
            # never something Phase 6B fabricated to satisfy the exemption.
            transfer_explanations = s.scalars(
                select(m.BankTransactionExplanation).where(
                    m.BankTransactionExplanation.financial_transaction_id.in_([paypal_side_1.id, bank_side_1.id])
                )
            ).all()
            result.check(
                "no confirmed-transfer transaction has a fabricated WHO (Occurrence)/WHY (Reason) decision (§25.D/§1.A)",
                all(e.occurrence_id is None and e.transaction_reason_id is None for e in transfer_explanations),
            )

            # =================================================================
            # Section 26 — Kermali workbook output.
            # =================================================================
            # Resolve the ordinary/fake transactions above so ONLY the
            # confirmed-transfer exemption itself is what remains under test —
            # every unrelated blocker must be resolved first, exactly the same
            # way test_bank_reconciliation_service.py's own export flow does.
            for txn in (fake_transfer, ordinary_unresolved):
                # The person chooses the Why explicitly; a Who alone leaves it
                # open (BANK_FINAL_RELEASE_BLOCKERS_001).
                recognition.record_human_decision(
                    s, recognition.HumanDecisionRequest(
                        transaction_id=txn.id, occurrence_id=occurrence.id,
                        transaction_reason_id=occurrence.default_transaction_reason_id,
                        confirmed_by_account_id=None, learn_description=False,
                    ),
                )
                txn.review_status = "REVIEWED"
            s.commit()

            final_blockers = export.compute_export_blockers(s, year=year, month=month)
            result.check(
                "no remaining blockers once every non-transfer transaction is resolved (§26 setup)",
                final_blockers == [],
            )

            xlsx_bytes = export.build_kermali_workbook(s, year=year, month=month)
            wb = openpyxl.load_workbook(BytesIO(xlsx_bytes))
            ws = wb.active
            header = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
            result.check(
                "workbook columns are unchanged by Phase 6B (§26)",
                header == list(export.KERMALI_COLUMNS),
            )
            data_rows = list(ws.iter_rows(min_row=2, values_only=True))
            descriptions_in_export = {row[2] for row in data_rows}
            result.check(
                "confirmed INTERNAL_TRANSFER rows (PayPal transfer / Bank deposit) do NOT appear in the workbook (§26/§14)",
                "PAYPAL TRANSFER" not in descriptions_in_export
                and bank_side_1.description_original not in descriptions_in_export,
            )
            result.check(
                "unrelated, resolved (non-transfer) transactions still appear in the workbook (§26)",
                fake_transfer.description_original in descriptions_in_export
                and ordinary_unresolved.description_original in descriptions_in_export,
            )
    finally:
        cleanup_disposable_test_database_url(url)

    total = len(result.passed) + len(result.failed)
    if result.failed:
        print(f"FAILURE ({len(result.passed)}/{total} checks passed)")
        for description in result.failed:
            print(f"  FAILED: {description}")
        return 1
    print(f"SUCCESS ({len(result.passed)}/{total} checks passed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
