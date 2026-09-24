#!/usr/bin/env python
"""Service-level (DB-backed) tests for Bank Reconciliation import,
idempotency, duplicate detection, and Kermali export blocking.

Canonical Financial Model Convergence — Phase 3/4 (FINANCIAL_MODEL_
CONVERGENCE_001): adapted from the proven V1 test suite
(`feature/bank-reconciliation-mvp`) to use the canonical
`PaymentInstrument`/`FinancialTransaction` models. Phase 4 restores the
Kermali export/Supplier-Receiving classification coverage Phase 3
deferred.

Mirrors `test_payroll_engine.py`: a disposable SQLite database, migrated
to head, always cleaned up. Never touches a real/shared database.

Usage:
    python test_bank_reconciliation_service.py
"""

from __future__ import annotations

import sys
from datetime import date

from rfone_data_store.bank_reconciliation import card_configuration
from rfone_data_store.bank_reconciliation import export, recognition, service
from rfone_data_store.database import (
    cleanup_disposable_test_database_url,
    create_configured_engine,
    create_session_factory,
    redact_database_url,
    resolve_test_database_url,
    run_migrations_to_head,
)
from rfone_data_store import models as m

CHASE_BANK_CSV_A = (
    "Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #\n"
    "DEBIT,04/05/2026,SEASONS 52,-24.05,ACH_DEBIT,1000.00,\n"
)

CHASE_CARD_1057_FILE_1 = (
    "Card,Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n"
    "1057,07/29/2026,07/30/2026,UBER *TRIP,Travel,Sale,-3.00,\n"
)

# A DIFFERENT download of the same card containing the SAME logical row —
# different bytes (extra blank line), same content -> must be flagged as a
# candidate duplicate at the NORMALIZED level, never merged/deleted.
CHASE_CARD_1057_FILE_2 = (
    "Card,Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n"
    "1057,07/29/2026,07/30/2026,UBER *TRIP,Travel,Sale,-3.00,\n"
    "\n"
)

CHASE_CARD_NO_CARD_CSV = (
    "Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n"
    "03/30/2026,03/31/2026,PY *WINE BY GEORGE,Shopping,Sale,-14.18,\n"
)


def main() -> int:
    checks_passed: list[str] = []
    checks_failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        if condition:
            checks_passed.append(description)
        else:
            checks_failed.append(description)
            print(f"FAILED: {description}" + (f" ({detail})" if detail else ""))

    url = resolve_test_database_url("bank_reconciliation")
    print(f"Database URL: {redact_database_url(url)}")
    run_migrations_to_head(url)
    engine = create_configured_engine(url)
    try:
        session_factory = create_session_factory(engine)
        with session_factory() as s:
            chase_instrument = m.PaymentInstrument(
                institution="CHASE", display_name="Chase Card 1057",
                instrument_type="CREDIT_CARD", last_four="1057",
            )
            s.add(chase_instrument)
            s.flush()

            # -----------------------------------------------------------
            # Idempotency: same bytes uploaded twice -> same batch, no
            # duplicate rows, no second batch row.
            # -----------------------------------------------------------
            result1 = service.import_csv(
                s, file_bytes=CHASE_BANK_CSV_A.encode("utf-8"),
                original_file_name="chase_0214.csv", uploaded_by_account_id=None,
            )
            s.commit()
            batch_count_after_first = s.query(m.BankImportBatch).count()
            result_again = service.import_csv(
                s, file_bytes=CHASE_BANK_CSV_A.encode("utf-8"),
                original_file_name="chase_0214_renamed.csv", uploaded_by_account_id=None,
            )
            s.commit()
            batch_count_after_second = s.query(m.BankImportBatch).count()
            check(
                "Re-uploading identical bytes reuses the existing batch (created=False)",
                result_again.created is False and result_again.batch.id == result1.batch.id,
            )
            check(
                "Re-uploading identical bytes creates no second BankImportBatch row",
                batch_count_after_first == batch_count_after_second,
            )

            # -----------------------------------------------------------
            # Chase bank account file: instrument cannot be auto-resolved
            # (spec §3.2) -> batch REQUIRES_REVIEW, no normalized rows yet.
            # -----------------------------------------------------------
            check(
                "Chase bank account batch with no configured instrument is REQUIRES_REVIEW",
                result1.batch.status == "REQUIRES_REVIEW" and result1.batch.payment_instrument_id is None,
            )
            check("No normalized rows exist before instrument resolution", result1.normalized_row_count == 0)

            bank_instrument = m.PaymentInstrument(
                institution="CHASE", display_name="Chase Checking 0214", instrument_type="BANK_ACCOUNT",
            )
            s.add(bank_instrument)
            s.flush()
            resolved = service.resolve_batch_instrument(
                s, batch_id=result1.batch.id, payment_instrument_id=bank_instrument.id,
            )
            s.commit()
            check(
                "resolve_batch_instrument normalizes the previously-unresolved batch",
                resolved.normalized_row_count == 1 and resolved.batch.status == "NORMALIZED",
            )
            try:
                service.resolve_batch_instrument(
                    s, batch_id=result1.batch.id, payment_instrument_id=bank_instrument.id,
                )
                check("resolve_batch_instrument refuses to re-resolve an already-resolved batch", False)
            except ValueError:
                check("resolve_batch_instrument refuses to re-resolve an already-resolved batch", True)

            # -----------------------------------------------------------
            # Cross-file overlap (spec §7.2 pattern): two DIFFERENT files
            # (different sha256) carrying the same logical Chase card row.
            # -----------------------------------------------------------
            first_upload = service.import_csv(
                s, file_bytes=CHASE_CARD_1057_FILE_1.encode("utf-8"),
                original_file_name="chase1057_a.csv", uploaded_by_account_id=None,
            )
            s.commit()
            check(
                "Chase card Variant A auto-resolves the instrument from Card",
                first_upload.batch.payment_instrument_id == chase_instrument.id,
            )
            check("First upload of a unique row has no candidate duplicate", first_upload.candidate_duplicate_count == 0)

            second_upload = service.import_csv(
                s, file_bytes=CHASE_CARD_1057_FILE_2.encode("utf-8"),
                original_file_name="chase1057_b.csv", uploaded_by_account_id=None,
            )
            s.commit()
            check(
                "A different file with an overlapping sha256 is a distinct batch",
                second_upload.batch.id != first_upload.batch.id,
            )
            check(
                "Cross-file overlap is caught as a CANDIDATE_DUPLICATE at the transaction level",
                second_upload.candidate_duplicate_count == 1
                and second_upload.batch.status == "REQUIRES_REVIEW",
            )
            candidate = s.query(m.FinancialTransaction).filter_by(
                import_batch_id=second_upload.batch.id
            ).one()
            check(
                "The candidate duplicate points back at the earlier transaction, never deletes it",
                candidate.duplicate_status == "CANDIDATE_DUPLICATE" and candidate.duplicate_of_transaction_id is not None,
            )
            original_still_present = s.get(m.FinancialTransaction, candidate.duplicate_of_transaction_id)
            check("The original (first-uploaded) row is never deleted", original_still_present is not None)

            decided = service.resolve_duplicate_decision(
                s, transaction_id=candidate.id, decision="CONFIRMED_DUPLICATE",
            )
            s.commit()
            check("A human decision is recorded without deleting the row", decided.duplicate_status == "CONFIRMED_DUPLICATE")

            # -----------------------------------------------------------
            # Identical rows WITHIN the same file/batch (spec §7.3) must
            # both be preserved, with occurrence metadata, not silently
            # collapsed into one row.
            # -----------------------------------------------------------
            same_file_dup_csv = (
                "Card,Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n"
                "1057,04/17/2026,04/18/2026,UBER *TRIP,Travel,Sale,-6.50,\n"
                "1057,04/17/2026,04/18/2026,UBER *TRIP,Travel,Sale,-6.50,\n"
            )
            within_file = service.import_csv(
                s, file_bytes=same_file_dup_csv.encode("utf-8"),
                original_file_name="chase1057_c.csv", uploaded_by_account_id=None,
            )
            s.commit()
            check(
                "Two identical rows in the same file both produce a normalized row (never collapsed)",
                within_file.normalized_row_count == 2,
            )
            rows = s.query(m.FinancialTransaction).filter_by(
                import_batch_id=within_file.batch.id
            ).order_by(m.FinancialTransaction.source_row_number).all()
            check(
                "Occurrence metadata distinguishes the two identical rows (1 of 2, 2 of 2)",
                rows[0].occurrence_index_in_batch == 1 and rows[1].occurrence_index_in_batch == 2
                and rows[0].occurrence_count_in_batch == 2 and rows[1].occurrence_count_in_batch == 2,
            )
            check(
                "The second identical occurrence is flagged CANDIDATE_DUPLICATE, the first is not",
                rows[0].duplicate_status == "NONE" and rows[1].duplicate_status == "CANDIDATE_DUPLICATE",
            )

            # -----------------------------------------------------------
            # Missing/unresolved instrument (Chase card Variant B) blocks
            # normalization until a human resolves it.
            # -----------------------------------------------------------
            no_card_upload = service.import_csv(
                s, file_bytes=CHASE_CARD_NO_CARD_CSV.encode("utf-8"),
                original_file_name="chase_card_no_id.csv", uploaded_by_account_id=None,
            )
            s.commit()
            check(
                "Chase credit card Variant B (no Card) cannot be auto-resolved and requires review",
                no_card_upload.batch.payment_instrument_id is None
                and no_card_upload.batch.status == "REQUIRES_REVIEW",
            )

            # -----------------------------------------------------------
            # Canonical FinancialTransaction status mapping (Phase 3):
            # First Citizens' free-text Status column (the only CSV source
            # that supplies one) maps into the canonical vocabulary without
            # inventing a redundant POSTED status.
            # -----------------------------------------------------------
            check(
                "A Chase row with no source status maps to canonical UNKNOWN",
                rows[0].status == "UNKNOWN",
            )

            first_citizens_instrument = m.PaymentInstrument(
                institution="FIRST_CITIZENS", display_name="First Citizens 7470", instrument_type="BANK_ACCOUNT",
                external_account_identifier="7470",
            )
            s.add(first_citizens_instrument)
            s.flush()
            first_citizens_csv = (
                "Account Number,Post Date,Check,Description,Debit,Credit,Status,Balance\n"
                "7470,05/01/2026,,VENDOR PAYMENT,50.00,,Pending,900.00\n"
                "7470,05/02/2026,,DEPOSIT,,75.00,Posted,975.00\n"
            )
            fc_upload = service.import_csv(
                s, file_bytes=first_citizens_csv.encode("utf-8"),
                original_file_name="first_citizens_7470.csv", uploaded_by_account_id=None,
            )
            s.commit()
            fc_rows = s.query(m.FinancialTransaction).filter_by(
                import_batch_id=fc_upload.batch.id
            ).order_by(m.FinancialTransaction.source_row_number).all()
            check(
                "First Citizens 'Pending' status maps to canonical PENDING",
                fc_rows[0].status == "PENDING",
            )
            check(
                "First Citizens 'Posted' status maps to canonical COMPLETED (no redundant POSTED status)",
                fc_rows[1].status == "COMPLETED",
            )

            # -----------------------------------------------------------
            # Kermali export blocking reasons (Phase 4B canonical decision).
            # March 2026 has the unresolved Chase card Variant B batch;
            # April 2026 has the within-file candidate duplicate and
            # transactions whose Recognition decision is still
            # NEEDS_HUMAN_REVIEW (Recognition runs automatically on every
            # normalized transaction but finds no matching rule here).
            # -----------------------------------------------------------
            march_blockers = export.compute_export_blockers(s, year=2026, month=3)
            check(
                "March 2026 export is blocked by the unresolved Chase card Variant B batch",
                any("Unresolved instrument" in b.reason for b in march_blockers),
            )

            april_blockers = export.compute_export_blockers(s, year=2026, month=4)
            check(
                "April 2026 export is blocked by an undecided candidate duplicate and a missing reconciliation decision",
                any("candidate duplicate" in b.reason for b in april_blockers)
                and any("Missing Who" in b.reason for b in april_blockers),
            )

            occurrence_type = m.BankOccurrenceType(code="RIDE_SHARE_PROVIDER", name="Ride Share Provider")
            s.add(occurrence_type)
            s.flush()
            # BANK_RECONCILIATION_WHO_WHY_WHAT_001: a Who is usable only
            # through a complete chain — Who -> Why -> What — so the What and
            # the two associations are configured here before any decision.
            # The Kermali export mapping remains a separate, unchanged fact.
            what = m.BankAccountingClassification(
                code="OPERATING_TRAVEL", name="Operating travel", statement_type="PROFIT_LOSS",
            )
            s.add(what)
            s.flush()
            reason = m.BankTransactionReason(
                code="OPERATIONAL_TRAVEL", name="Operational Travel",
                accounting_classification_id=what.id,
            )
            s.add(reason)
            s.flush()
            occurrence = m.BankOccurrence(
                canonical_name="Uber", occurrence_type_id=occurrence_type.id,
                default_transaction_reason_id=reason.id,
            )
            s.add(occurrence)
            s.flush()
            export_mapping = m.BankTransactionReasonExportMapping(
                bank_transaction_reason_id=reason.id, operative=True, what_label="Operational travel",
            )
            s.add(export_mapping)
            s.flush()

            for txn in s.query(m.FinancialTransaction).filter(
                m.FinancialTransaction.posting_date >= date(2026, 4, 1),
                m.FinancialTransaction.posting_date <= date(2026, 4, 30),
            ).all():
                if txn.duplicate_status == "CANDIDATE_DUPLICATE":
                    service.resolve_duplicate_decision(s, transaction_id=txn.id, decision="CONFIRMED_DISTINCT")
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

            april_blockers_after = export.compute_export_blockers(s, year=2026, month=4)
            check(
                "Missing Company/Legal Entity still blocks April 2026 export after the reconciliation decision is complete",
                any("Missing required Company" in b.reason for b in april_blockers_after),
            )

            legal_entity = m.LegalEntity(legal_name="Verification LLC", status="ACTIVE")
            s.add(legal_entity)
            s.flush()
            # Both instruments appear in April 2026's scope (bank_instrument
            # via the resolved Chase-bank-account row, chase_instrument via
            # the within-file-duplicate rows) — both need Company configured.
            chase_instrument.legal_entity_id = legal_entity.id
            bank_instrument.legal_entity_id = legal_entity.id
            s.commit()

            # BANK_CARDHOLDER_AND_ACCOUNTING_DEDUPLICATION_001: a credit card
            # now also needs the bank account it settles to. That account is
            # what gives its transactions a Company and what scopes accounting
            # deduplication, so "fully configured" legitimately means more
            # than it did before this task.
            card_configuration.assign_settlement_account(
                s, credit_card_payment_instrument_id=chase_instrument.id,
                settlement_bank_account_id=bank_instrument.id, valid_from=date(2026, 1, 1),
            )
            service.recompute_accounting_deduplication(s)
            s.commit()

            final_blockers = export.compute_export_blockers(s, year=2026, month=4)
            check("April 2026 export has no remaining blockers once fully classified/configured", final_blockers == [])

            # -----------------------------------------------------------
            # Build the workbook and verify column order + real types.
            # -----------------------------------------------------------
            xlsx_bytes = export.build_kermali_workbook(s, year=2026, month=4)
            import openpyxl
            from io import BytesIO
            wb = openpyxl.load_workbook(BytesIO(xlsx_bytes))
            ws = wb.active
            header = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
            check("Export column order matches the required 12 columns exactly", header == list(export.KERMALI_COLUMNS))

            data_rows = list(ws.iter_rows(min_row=2, values_only=True))
            check("Export contains at least one data row", len(data_rows) >= 1)
            first_data_row = data_rows[0]
            check(
                "Export Date column is a real date (not a string)",
                hasattr(first_data_row[1], "year") and hasattr(first_data_row[1], "month"),
            )
            check(
                "Export Amount column is numeric (not a string, not a formula)",
                isinstance(first_data_row[3], (int, float)) and not str(first_data_row[3]).startswith("="),
            )
            check(
                "Export Supplier/Receiving column carries the decided Occurrence's name",
                any(row[4] == "Uber" for row in data_rows),
            )
            check(
                "Export file name follows the RfBank_YYYY_MM.xlsx convention",
                export.export_file_name(year=2026, month=4) == "RfBank_2026_04.xlsx",
            )

            # -----------------------------------------------------------
            # Historical stability (Decision 8): renaming the Occurrence
            # and editing the Export Mapping AFTER a decision was made must
            # never change that decision's already-exported snapshot.
            # -----------------------------------------------------------
            occurrence.canonical_name = "Uber Technologies Inc (renamed)"
            export_mapping.operative = False
            export_mapping.what_label = "Renamed label — must not appear in history"
            s.commit()

            xlsx_bytes_after_rename = export.build_kermali_workbook(s, year=2026, month=4)
            wb_after_rename = openpyxl.load_workbook(BytesIO(xlsx_bytes_after_rename))
            ws_after_rename = wb_after_rename.active
            data_rows_after_rename = list(ws_after_rename.iter_rows(min_row=2, values_only=True))
            check(
                "Renaming the Occurrence after the decision does NOT change the historical export snapshot",
                any(row[4] == "Uber" for row in data_rows_after_rename)
                and not any(row[4] == "Uber Technologies Inc (renamed)" for row in data_rows_after_rename),
            )
            # BANK_RECONCILIATION_WHO_WHY_WHAT_001: the `What` column now
            # reports the decision's accounting classification (the What of
            # the Who -> Why -> What chain) for anything decided under the
            # hierarchical model, and falls back to the Kermali `what_label`
            # only for decisions that predate it. Both are read from the
            # decision's OWN snapshot, so the point under test is unchanged:
            # editing the live mapping afterwards changes nothing historical.
            check(
                "Editing the Export Mapping after the decision does NOT change the historical Oper/What snapshot",
                any(row[6] is not None and row[8] == "Operating travel" for row in data_rows_after_rename)
                and not any(
                    row[8] == "Renamed label — must not appear in history"
                    for row in data_rows_after_rename
                ),
            )

    finally:
        engine.dispose()
        cleanup_disposable_test_database_url(url)

    print()
    print(f"{len(checks_passed)} passed, {len(checks_failed)} failed.")
    if checks_failed:
        print("FAILED CHECKS:")
        for c in checks_failed:
            print(" -", c)
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
