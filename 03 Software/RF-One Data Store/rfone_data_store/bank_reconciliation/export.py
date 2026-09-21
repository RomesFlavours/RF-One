"""Kermali Monthly Accountant Export — `RfBank_YYYY_MM.xlsx`.

`RfBank.xlsx` is an OUTPUT format this module reproduces; it is never read
or written as a runtime datastore (spec: "Non usare Excel come datastore
runtime"). The 12-column order below is fixed by the accountant's existing
process, not by this schema's own model — `models.py`'s
`FinancialTransaction` may evolve independently of it.

Canonical Financial Model Convergence — Phase 4B (FINANCIAL_MODEL_
CONVERGENCE_001, Product Owner Decisions 1, 6, 8, 12, 13): reads the ONE
canonical reconciliation decision via `FinancialTransaction.explanation_id`
-> the current `BankTransactionExplanation` row, produced by the Bank
Recognition Expert System (`bank_reconciliation/recognition.py`) — there
is no longer a second, independent legacy classification mechanism.
Every Kermali column sourced from the decision (Supplier/Receiving,
Food $, Oper, Deduct, What) is read from that row's immutable snapshot
fields ONLY, never from the live `BankOccurrence`/`BankTransactionReason
ExportMapping` — so a later rename/edit of either never changes a
transaction's already-exported historical values.

BANK_RECONCILIATION_WHO_WHY_WHAT_001: the same rule now also governs the
hierarchical WHO -> WHY -> WHAT classification. The export reads the
decision's `accounting_classification_*_snapshot` values, never the
current `BankOccurrence.default_transaction_reason_id` /
`BankTransactionReason.accounting_classification_id` associations, which
are editable at any time. The blockers below therefore check the CHAIN
for anything not yet decided, and the SNAPSHOT for anything already
decided — an inactive What blocks nothing that already carries a valid
snapshot of it.

Supplier settlement stays a bank-side fact: a supplier paid by invoice
may legitimately classify to an Accounts Payable settlement What
(a Balance Sheet line). This module never infers the Food/Operating
composition of that invoice's lines from the bank movement — that
classification continues to come from the invoice (Invoice Intake/
Purchased), exactly as before."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from io import BytesIO

import openpyxl
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import models as m
from . import recognition

KERMALI_COLUMNS = (
    "Account", "Date", "Description", "Amount", "Supplier/Receiving",
    "Food $", "Oper", "Deduct", "What", "Month", "Year", "Company",
)


def month_bounds(year: int, month: int) -> tuple[date, date]:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def _in_scope_transactions(session: Session, year: int, month: int) -> list["m.FinancialTransaction"]:
    start, end = month_bounds(year, month)
    return list(session.scalars(
        select(m.FinancialTransaction).where(
            m.FinancialTransaction.posting_date >= start,
            m.FinancialTransaction.posting_date <= end,
            m.FinancialTransaction.duplicate_status != "CONFIRMED_DUPLICATE",
        ).order_by(m.FinancialTransaction.posting_date, m.FinancialTransaction.id)
    ).all())


@dataclass
class ExportBlocker:
    reason: str


def _confirmed_internal_transfer_ids(
    session: Session, transactions: list["m.FinancialTransaction"],
) -> set[int]:
    """Ids among `transactions` that are a CONFIRMED internal transfer
    (Financial Model Convergence Phase 6B, Product Owner Decisions A/B):
    `classification == 'INTERNAL_TRANSFER'` is never trusted alone — a
    genuine, confirmed `FinancialTransactionMatch` of type
    `INTERNAL_TRANSFER` involving the transaction must also exist.
    `bank_reconciliation/matching.py` is the only place that ever creates
    such a match or sets this classification, so this is the ONE
    authoritative check both `compute_export_blockers` and
    `build_kermali_workbook` use — never re-derived independently."""
    candidate_ids = {t.id for t in transactions if t.classification == "INTERNAL_TRANSFER"}
    if not candidate_ids:
        return set()
    matches = session.scalars(
        select(m.FinancialTransactionMatch).where(
            m.FinancialTransactionMatch.match_type == "INTERNAL_TRANSFER",
            or_(
                m.FinancialTransactionMatch.transaction_a_id.in_(candidate_ids),
                m.FinancialTransactionMatch.transaction_b_id.in_(candidate_ids),
            ),
        )
    ).all()
    confirmed: set[int] = set()
    for match in matches:
        if match.transaction_a_id in candidate_ids:
            confirmed.add(match.transaction_a_id)
        if match.transaction_b_id in candidate_ids:
            confirmed.add(match.transaction_b_id)
    return confirmed


def _classification_blockers(
    session: Session, *, transactions: list["m.FinancialTransaction"],
    transfer_ids: set[int], resolved_explanation_ids: set[int],
) -> list[ExportBlocker]:
    """BANK_RECONCILIATION_WHO_WHY_WHAT_001 — every way the hierarchical
    classification can be incomplete for a month, stated as the concrete
    thing a human must go and fix.

    The rule that keeps this honest: an already-decided transaction is
    judged on its OWN SNAPSHOT, never on the live chain. So re-pointing a
    Why at another What, or deactivating a What, never retroactively
    blocks a month that was already correctly classified — only a
    transaction whose snapshot is itself incomplete does. Applying the
    new chain to such a transaction is the explicit `Reclassify` action,
    never an automatic consequence of an edit."""
    blockers: list[ExportBlocker] = []

    explanations_by_id = {}
    explanation_ids = {t.explanation_id for t in transactions if t.explanation_id is not None}
    if explanation_ids:
        explanations_by_id = {
            e.id: e for e in session.scalars(
                select(m.BankTransactionExplanation)
                .where(m.BankTransactionExplanation.id.in_(explanation_ids))
            ).all()
        }

    for txn in transactions:
        if txn.id in transfer_ids:
            continue
        if txn.explanation_id is None or txn.explanation_id not in resolved_explanation_ids:
            continue  # already reported as "Missing Who" above
        explanation = explanations_by_id.get(txn.explanation_id)
        if explanation is None:
            continue

        where = (
            f"transaction id={txn.id} ({txn.posting_date.isoformat()}, "
            f"{txn.description_original!r})"
        )

        if explanation.occurrence_id is None and not explanation.occurrence_name_snapshot:
            blockers.append(ExportBlocker(f"Missing Who: {where} has a decision that records no Who."))
            continue
        if explanation.transaction_reason_id is None:
            blockers.append(ExportBlocker(
                f"Who without Why: {where} was decided for Who "
                f"{explanation.occurrence_name_snapshot or explanation.occurrence_id!r} but records no Why. "
                "Give that Who a default Why in Bank > Classification, then Reclassify this transaction."
            ))
            continue
        if not explanation.accounting_classification_code_snapshot:
            blockers.append(ExportBlocker(
                f"Why without What: {where} was decided for Why "
                f"{explanation.transaction_reason_name_snapshot or explanation.transaction_reason_id!r} "
                "but its decision records no What (accounting classification). This is an incomplete "
                "historical classification — assign the Why a What in Bank > Classification, then "
                "Reclassify this transaction."
            ))
            continue
        if explanation.accounting_statement_type_snapshot is None:
            blockers.append(ExportBlocker(
                f"Incomplete historical classification: {where} carries What "
                f"{explanation.accounting_classification_code_snapshot} with no statement type "
                "(Profit & Loss or Balance Sheet). Complete that What in Bank > Classification, "
                "then Reclassify this transaction."
            ))

    return blockers


def compute_export_blockers(session: Session, *, year: int, month: int) -> list[ExportBlocker]:
    """Every reason this export cannot run, precisely stated (spec: "Mostra
    sempre il motivo preciso del blocco"). An empty list means the export
    may proceed."""
    blockers: list[ExportBlocker] = []
    start, end = month_bounds(year, month)

    unresolved_batches = session.scalars(
        select(m.BankImportBatch).where(m.BankImportBatch.payment_instrument_id.is_(None))
    ).all()
    for batch in unresolved_batches:
        overlaps_month = (
            batch.date_range_start is None or batch.date_range_end is None
            or (batch.date_range_start <= end and batch.date_range_end >= start)
        )
        if overlaps_month:
            blockers.append(ExportBlocker(
                f"Unresolved instrument for batch {batch.original_file_name!r} "
                f"(id={batch.id}) — its Payment Instrument must be resolved before export."
            ))

    error_batches = session.scalars(
        select(m.BankImportBatch).where(m.BankImportBatch.error_summary.is_not(None))
    ).all()
    for batch in error_batches:
        overlaps_month = (
            batch.date_range_start is None or batch.date_range_end is None
            or (batch.date_range_start <= end and batch.date_range_end >= start)
        )
        if overlaps_month:
            blockers.append(ExportBlocker(
                f"Parsing errors in batch {batch.original_file_name!r} (id={batch.id}): {batch.error_summary}"
            ))

    transactions = _in_scope_transactions(session, year, month)

    undecided_duplicates = [t for t in transactions if t.duplicate_status == "CANDIDATE_DUPLICATE"]
    for txn in undecided_duplicates:
        blockers.append(ExportBlocker(
            f"Undecided candidate duplicate: transaction id={txn.id} "
            f"({txn.posting_date.isoformat()}, {txn.description_original!r}, "
            f"{txn.amount_minor / 100:.2f}) requires a human duplicate decision."
        ))

    # Canonical Financial Model Convergence — Phase 4B (Decision 13): a
    # transaction blocks export unless it has a sufficiently resolved
    # canonical reconciliation decision — no pointer at all (Recognition
    # never ran, e.g. pre-Phase-4B data awaiting migration), or a pointer
    # to a decision still awaiting HUMAN review, both block equally. A
    # legacy catalog row no longer existing is not a distinct blocker —
    # that mechanism has been retired (Decision 1/10).
    explanation_ids_needing_check = {t.explanation_id for t in transactions if t.explanation_id is not None}
    resolved_explanation_ids: set[int] = set()
    if explanation_ids_needing_check:
        resolved_explanation_ids = set(session.scalars(
            select(m.BankTransactionExplanation.id).where(
                m.BankTransactionExplanation.id.in_(explanation_ids_needing_check),
                m.BankTransactionExplanation.decision_status.in_(recognition.RESOLVED_DECISION_STATUSES),
            )
        ).all())

    # Canonical Financial Model Convergence — Phase 6B (Product Owner
    # Decision B): a CONFIRMED internal transfer is sufficient economic
    # classification on its own (Decision A) — Kermali is an output
    # consumer, never the source of RF-One's own reconciliation semantics,
    # so it must not force a fake Occurrence/Reason/Explanation onto a
    # transaction that already has a genuine, confirmed
    # FinancialTransactionMatch. The exemption requires BOTH conditions
    # together (`_confirmed_internal_transfer_ids`) — classification alone
    # is never sufficient.
    transfer_ids = _confirmed_internal_transfer_ids(session, transactions)

    unresolved = [
        t for t in transactions
        if (t.explanation_id is None or t.explanation_id not in resolved_explanation_ids)
        and t.id not in transfer_ids
    ]
    for txn in unresolved:
        blockers.append(ExportBlocker(
            f"Missing Who: transaction id={txn.id} "
            f"({txn.posting_date.isoformat()}, {txn.description_original!r}) has no resolved "
            "Who -> Why -> What decision (Recognition still needs human review)."
        ))

    blockers.extend(_classification_blockers(
        session, transactions=transactions, transfer_ids=transfer_ids,
        resolved_explanation_ids=resolved_explanation_ids,
    ))

    instruments_in_scope = {t.payment_instrument_id for t in transactions}
    if instruments_in_scope:
        instruments = session.scalars(
            select(m.PaymentInstrument).where(m.PaymentInstrument.id.in_(instruments_in_scope))
        ).all()
        for instrument in instruments:
            if instrument.legal_entity_id is None:
                blockers.append(ExportBlocker(
                    f"Missing required Company/Legal Entity for instrument "
                    f"{instrument.display_name!r} (id={instrument.id})."
                ))

    return blockers


def build_kermali_workbook(session: Session, *, year: int, month: int) -> bytes:
    """Builds the `.xlsx` bytes. Caller MUST call `compute_export_blockers`
    first and refuse to call this while any blocker exists — this function
    itself does not re-check (single responsibility: building, not
    gating)."""
    transactions = _in_scope_transactions(session, year, month)

    instrument_ids = {t.payment_instrument_id for t in transactions}
    instruments = {
        i.id: i for i in session.scalars(
            select(m.PaymentInstrument).where(m.PaymentInstrument.id.in_(instrument_ids))
        ).all()
    } if instrument_ids else {}
    legal_entity_ids = {i.legal_entity_id for i in instruments.values() if i.legal_entity_id is not None}
    legal_entities = {
        le.id: le for le in session.scalars(
            select(m.LegalEntity).where(m.LegalEntity.id.in_(legal_entity_ids))
        ).all()
    } if legal_entity_ids else {}
    explanation_ids = {t.explanation_id for t in transactions if t.explanation_id is not None}
    explanations = {
        e.id: e for e in session.scalars(
            select(m.BankTransactionExplanation).where(m.BankTransactionExplanation.id.in_(explanation_ids))
        ).all()
    } if explanation_ids else {}
    # Canonical Financial Model Convergence — Phase 6B (Product Owner
    # Decisions A/B/D): a CONFIRMED internal transfer has no Supplier/
    # Receiving, Food $, Oper, Deduct, or What — none is invented to fill
    # the row. RF-One itself retains both transactions and the
    # `FinancialTransactionMatch` internally regardless; Kermali, as an
    # external accountant-classification output, simply never receives a
    # row it has no genuine classification to report.
    transfer_ids = _confirmed_internal_transfer_ids(session, transactions)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Bank"
    ws.append(list(KERMALI_COLUMNS))

    for txn in transactions:
        if txn.id in transfer_ids:
            continue
        instrument = instruments.get(txn.payment_instrument_id)
        legal_entity = legal_entities.get(instrument.legal_entity_id) if instrument and instrument.legal_entity_id else None
        explanation = explanations.get(txn.explanation_id) if txn.explanation_id else None

        amount = Decimal(txn.amount_minor) / 100
        amount_float = float(amount)

        # Canonical Financial Model Convergence — Phase 4B (Decision 8):
        # read ONLY the immutable decision snapshot, never the live
        # BankOccurrence/BankTransactionReasonExportMapping.
        food_value = amount_float if (explanation and explanation.food_cost_snapshot) else None
        oper_value = amount_float if (explanation and explanation.operative_snapshot) else None
        deduct_value = amount_float if (explanation and explanation.deductible_snapshot) else None

        ws.append([
            instrument.display_name if instrument else None,        # Account
            txn.posting_date,                                        # Date — real Excel date, not a string
            txn.description_original,                                # Description
            amount_float,                                            # Amount — numeric, no formula
            explanation.occurrence_name_snapshot if explanation else None,  # Supplier/Receiving
            food_value,                                              # Food $
            oper_value,                                              # Oper
            deduct_value,                                            # Deduct
            _what_cell(explanation),                                 # What
            txn.posting_date.month,                                  # Month — derived from Date
            txn.posting_date.year,                                   # Year — derived from Date
            legal_entity.legal_name if legal_entity else None,        # Company
        ])

    date_col = 2  # "Date"
    for row in ws.iter_rows(min_row=2, min_col=date_col, max_col=date_col):
        for cell in row:
            cell.number_format = "MM/DD/YYYY"

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _what_cell(explanation: "m.BankTransactionExplanation | None") -> str | None:
    """The Kermali `What` column. A decision taken under the hierarchical
    WHO -> WHY -> WHAT model reports its accounting classification; a
    decision that predates it keeps reporting exactly the Kermali
    `what_label` it was exported with before, so no historical row's
    output changes. Both are read from the decision's own snapshot."""
    if explanation is None:
        return None
    return explanation.accounting_classification_name_snapshot or explanation.what_label_snapshot


def export_file_name(*, year: int, month: int) -> str:
    return f"RfBank_{year:04d}_{month:02d}.xlsx"
