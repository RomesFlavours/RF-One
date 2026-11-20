"""Bank Reconciliation decisions (BANK_RECONCILIATION_EXPERT_SYSTEM_001).

The ONE place a reconciliation decision row is written — WHO
(`BankOccurrence`), WHY (`BankTransactionReason`) and the WHAT derived from
that WHY — for a person (`record_human_decision`, `reclassify_transaction`)
and for an AI rule (`ai_rule_operations`, through `_create_decision_row`).

Since BANK_RULES_RESET_001 Bank classifies only through AI Rules and by a
person. The old deterministic recognition engine that used to live here
(recognition rules learned from confirmations, rule matching, the automatic
proposal at import) was removed with the rest of the old rule system; the
text normalization below is kept because the AI rules and the WHO tools
still read it.

This module never derives cost family, cost type, or purchase composition
— those remain exclusively an invoice-side concern (Invoice Intake/
Purchased); `BankOccurrence`/`BankTransactionReason` carry no such field.

Phase 4B (Product Owner Decision 1): every decision row also captures an
immutable Kermali export snapshot (Decision 8) and keeps
`FinancialTransaction.explanation_id` pointed at whichever row is current
(Decision 6); the decision history is append-only.

BANK_RECONCILIATION_WHO_WHY_WHAT_001 — hierarchical classification:

* WHO never determines WHY (BANK_WHO_WHY_INVARIANT_001): a person chooses
  the WHY of each transaction, and `BankOccurrence.default_transaction_
  reason_id` is never applied as the resolution;
* every decision row snapshots the WHY name and the WHAT (id, code, name,
  statement type) alongside the Occurrence/Kermali snapshot, so an
  already-confirmed transaction never changes meaning when the vocabulary
  is edited;
* a human may apply an updated chain to a historical transaction only
  through `reclassify_transaction`, which appends a new HUMAN_RECLASSIFIED
  decision and never rewrites the one it supersedes."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import classification as classification_service
from . import why_catalog

UTC = timezone.utc

EXACT_NORMALIZED_DESCRIPTION = "EXACT_NORMALIZED_DESCRIPTION"
CONTAINS_TEXT = "CONTAINS_TEXT"
PREFIX = "PREFIX"

DEBIT = "DEBIT"
CREDIT = "CREDIT"

# Exportable/resolved decision states — everything else blocks export.
RESOLVED_DECISION_STATUSES = (
    "AUTO_APPLIED", "HUMAN_CONFIRMED", "HUMAN_OVERRIDDEN", "HUMAN_RECLASSIFIED",
)

# "Prudent" punctuation normalization: characters that vary between export
# formats of the SAME merchant/description (Chase inserts `*`, `#`, extra
# dots/commas inconsistently — spec §3, observed real-file evidence) are
# collapsed to a single space. Digits are never touched — an order number,
# invoice number, or store number may be exactly what distinguishes two
# otherwise-identical descriptions.
_PUNCTUATION_NOISE_RE = re.compile(r"[^A-Z0-9 ]+")
_WHITESPACE_RE = re.compile(r"\s+")


# Which text a rule reads (BANK_MEMO_PURPOSE_CLASSIFICATION_001).
DESCRIPTION = "DESCRIPTION"
MEMO = "MEMO"


def normalize_memo_for_recognition(raw: str | None) -> str:
    """The same normalization the description gets, applied to the memo.

    Separate function so the two are never accidentally concatenated: a
    memo rule must match memo text and nothing else."""
    return normalize_description_for_recognition(raw or "")


def normalize_description_for_recognition(raw: str) -> str:
    """Deterministic, testable normalization used ONLY for recognition
    matching (spec §3 of this task) — a DIFFERENT function from
    `service.normalize_description` (duplicate-detection fingerprinting),
    which must keep its own existing behavior unchanged. The original
    `description_original` on the transaction is never modified by this
    function or its caller."""
    text = (raw or "").strip().upper()
    text = _PUNCTUATION_NOISE_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text


def direction_for_amount(amount_minor: int) -> str:
    return DEBIT if amount_minor < 0 else CREDIT


# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------


def _capture_snapshot(
    session: Session, *, occurrence_id: int | None, transaction_reason_id: int | None,
    accounting_classification_id: int | None = None,
) -> dict:
    """Canonical Financial Model Convergence — Phase 4B (Product Owner
    Decision 8). Reads `BankOccurrence.canonical_name` and the selected
    Reason's `BankTransactionReasonExportMapping` (if any) ONCE, at
    decision time, and returns them as plain values to be stored on the
    new decision row. Never re-read from those tables afterward — a later
    rename/edit of either must never change an already-decided
    transaction's historical Kermali output. Absence of a value (no
    Occurrence, or a Reason with no configured Export Mapping yet) is
    preserved as NULL, never guessed.

    BANK_RECONCILIATION_WHO_WHY_WHAT_001 extends the same rule to the
    WHY name and the WHAT: the accounting classification's id, code,
    name and statement type are captured here too, so editing the
    WHO -> WHY or WHY -> WHAT association later changes only FUTURE
    classifications. An absent WHAT stays NULL and is never invented.

    BANK_RECONCILIATION_STANDARDS_001: `accounting_classification_id`, when
    given, is the EFFECTIVE destination a human chose for this transaction or
    a Standard supplied — snapshotted instead of the WHY's own mapping, which
    is never modified. The caller records which of the two it is in
    `accounting_destination_source`."""
    chosen_destination_id = accounting_classification_id
    occurrence_name_snapshot = None
    if occurrence_id is not None:
        occurrence = session.get(m.BankOccurrence, occurrence_id)
        if occurrence is not None:
            occurrence_name_snapshot = occurrence.canonical_name

    food_cost_snapshot = operative_snapshot = deductible_snapshot = what_label_snapshot = None
    transaction_reason_name_snapshot = None
    accounting_classification_id = None
    accounting_classification_code_snapshot = None
    accounting_classification_name_snapshot = None
    accounting_statement_type_snapshot = None
    if transaction_reason_id is not None:
        mapping = session.scalars(
            select(m.BankTransactionReasonExportMapping).where(
                m.BankTransactionReasonExportMapping.bank_transaction_reason_id == transaction_reason_id,
            )
        ).first()
        if mapping is not None:
            food_cost_snapshot = mapping.food_cost
            operative_snapshot = mapping.operative
            deductible_snapshot = mapping.deductible
            what_label_snapshot = mapping.what_label

        reason = session.get(m.BankTransactionReason, transaction_reason_id)
        if reason is not None:
            transaction_reason_name_snapshot = reason.name
            destination_id = (chosen_destination_id if chosen_destination_id is not None
                              else reason.accounting_classification_id)
            what = (
                session.get(m.BankAccountingClassification, destination_id)
                if destination_id is not None else None
            )
            if what is not None:
                accounting_classification_id = what.id
                accounting_classification_code_snapshot = what.code
                accounting_classification_name_snapshot = what.name
                accounting_statement_type_snapshot = what.statement_type

    return {
        "occurrence_name_snapshot": occurrence_name_snapshot,
        "food_cost_snapshot": food_cost_snapshot,
        "operative_snapshot": operative_snapshot,
        "deductible_snapshot": deductible_snapshot,
        "what_label_snapshot": what_label_snapshot,
        "transaction_reason_name_snapshot": transaction_reason_name_snapshot,
        "accounting_classification_id": accounting_classification_id,
        "accounting_classification_code_snapshot": accounting_classification_code_snapshot,
        "accounting_classification_name_snapshot": accounting_classification_name_snapshot,
        "accounting_statement_type_snapshot": accounting_statement_type_snapshot,
    }


def _create_decision_row(
    session: Session, txn: "m.FinancialTransaction", *,
    occurrence_id: int | None, transaction_reason_id: int | None,
    decision_source: str, decision_status: str, confidence: str | None, explanation_notes: str,
    confirmed_by_account_id: int | None = None, confirmed_at: datetime | None = None,
    accounting_classification_id: int | None = None,
    accounting_destination_source: str = m.DESTINATION_SOURCE_WHY,
) -> "m.BankTransactionExplanation":
    """Always INSERTs a new row — never updates an existing one in place.
    This is what makes the decision history an audit trail: a transaction's
    "current" decision is simply its highest-id row (`get_current_explanation`).

    Canonical Financial Model Convergence — Phase 4B (Product Owner
    Decision 6): this is the ONE place a canonical decision row is ever
    created, for both RULE and HUMAN decisions — so it is also the ONE
    place that captures the immutable snapshot (Decision 8) and keeps
    `FinancialTransaction.explanation_id` pointed at whichever row is now
    current (Decision 6). No prior row is ever updated."""
    snapshot = _capture_snapshot(
        session, occurrence_id=occurrence_id, transaction_reason_id=transaction_reason_id,
        accounting_classification_id=accounting_classification_id,
    )
    row = m.BankTransactionExplanation(
        financial_transaction_id=txn.id,
        occurrence_id=occurrence_id,
        transaction_reason_id=transaction_reason_id,
        decision_source=decision_source,
        decision_status=decision_status,
        confidence=confidence,
        explanation_notes=explanation_notes,
        confirmed_by_account_id=confirmed_by_account_id,
        confirmed_at=confirmed_at,
        accounting_destination_source=accounting_destination_source,
        **snapshot,
    )
    session.add(row)
    session.flush()
    txn.explanation_id = row.id
    session.flush()
    return row


def get_current_explanation(
    session: Session, *, financial_transaction_id: int,
) -> "m.BankTransactionExplanation | None":
    """The transaction's current decision — the most recently created
    per-decision row, if any. Older rows are never deleted or updated;
    they remain queryable as history (spec: "conserva evidenza della
    regola precedente")."""
    return session.scalars(
        select(m.BankTransactionExplanation)
        .where(m.BankTransactionExplanation.financial_transaction_id == financial_transaction_id)
        .order_by(m.BankTransactionExplanation.id.desc())
    ).first()


@dataclass
class HumanDecisionRequest:
    """A human decision on one transaction. The human names the WHO, and the
    WHY when they choose one; the WHAT always derives from that Why. A Who's
    default Why is never applied (BANK_FINAL_RELEASE_BLOCKERS_001): with no
    Why chosen the decision records the Who and leaves the Why open."""

    transaction_id: int
    occurrence_id: int
    confirmed_by_account_id: int | None
    # BANK_CANONICAL_WHY_AND_WHO_RELATIONSHIPS_001 §21-§23 — the WHY the
    # operator chose for THIS transaction.
    #
    # When set, that Why is used and the WHO <-> WHY association is
    # recorded, so the same Why is offered first next time. The WHAT then
    # DERIVES from the Why and is never chosen separately: if the mapping
    # is wrong the central Why definition is fixed, not this transaction.
    #
    # When None, only the Who is recorded; the Why stays for a human.
    transaction_reason_id: int | None = None
    # BANK_RECONCILIATION_STANDARDS_001 — the EFFECTIVE accounting destination
    # the operator chose for THIS transaction, if any. When it equals the
    # WHY's own mapping the decision is recorded as WHY-derived; when it
    # differs it is a transaction-level exception (TRANSACTION). The WHY's
    # master mapping is never changed by it.
    accounting_classification_id: int | None = None
    notes: str | None = None


def record_human_decision(session: Session, request: HumanDecisionRequest) -> "m.BankTransactionExplanation":
    """The single entry point for every human confirm/correct action (spec
    FASE 5). Determines CONFIRMED vs OVERRIDDEN by comparing to the
    transaction's current decision; never edits a prior row, never
    retroactively touches any other transaction."""
    txn = session.get(m.FinancialTransaction, request.transaction_id)
    if txn is None:
        raise ValueError(f"FinancialTransaction {request.transaction_id} not found")
    occurrence = session.get(m.BankOccurrence, request.occurrence_id)
    if occurrence is None:
        raise ValueError(f"BankOccurrence {request.occurrence_id} not found")
    if occurrence.status != "ACTIVE":
        raise ValueError(
            f"Who {occurrence.canonical_name!r} is inactive. Reactivate it in Bank > "
            "Classification, or choose another Who."
        )

    # The WHY is either the one the operator chose for this transaction, or
    # the Who's default chain. The WHAT is DERIVED from that Why in both
    # cases — never chosen independently, and never taken from the Who.
    if request.transaction_reason_id is not None:
        reason = session.get(m.BankTransactionReason, request.transaction_reason_id)
        if reason is None:
            raise ValueError(f"Why {request.transaction_reason_id} does not exist.")
        if reason.status != "ACTIVE":
            raise ValueError(f"Why {reason.code} — {reason.name} is inactive.")
        # Read by id, not through the relationship: a mapping edited earlier
        # in this same session must be the one used.
        what = (session.get(m.BankAccountingClassification, reason.accounting_classification_id)
                if reason.accounting_classification_id is not None else None)
        # BANK_WHY_WITHOUT_WHAT_001 — a WHY with no accounting destination yet
        # is a complete Bank answer (WHO + WHY); the decision's WHAT stays NULL
        # until bookkeeping assigns one. Never invented.
        if what is not None and not what.is_posting_account:
            raise ValueError(
                f"Why {reason.code} resolves to {what.code}, a reporting group, which "
                "nothing may be posted to."
            )
        # An explicit choice IS the human confirming this purpose for this
        # counterparty: recorded additively, never replacing another.
        why_catalog.associate(
            session, occurrence_id=request.occurrence_id,
            transaction_reason_id=reason.id, source="HUMAN",
        )
        destination_source = m.DESTINATION_SOURCE_WHY
        if (request.accounting_classification_id is not None
                and (what is None or request.accounting_classification_id != what.id)):
            chosen = session.get(m.BankAccountingClassification, request.accounting_classification_id)
            if chosen is None:
                raise ValueError(f"WHAT {request.accounting_classification_id} does not exist.")
            current = get_current_explanation(session, financial_transaction_id=txn.id)
            keeps_current = (current is not None
                             and current.accounting_classification_id == chosen.id)
            # A transaction-level choice is a P&L WHAT. The only other value
            # accepted is the destination this transaction ALREADY has (e.g. a
            # preserved Balance Sheet destination), so nothing is converted.
            if not (chosen.is_what or keeps_current):
                raise ValueError(
                    f"{chosen.code} — {chosen.name} is not a P&L WHAT that can be chosen for a "
                    "transaction."
                )
            what = chosen
            destination_source = m.DESTINATION_SOURCE_TRANSACTION
        chain = classification_service.ResolvedChain(
            occurrence, transaction_reason=reason, accounting_classification=what,
        )
    else:
        # BANK_FINAL_RELEASE_BLOCKERS_001 — WHO DOES NOT DETERMINE WHY. With
        # no Why chosen, the human has confirmed WHO the counterparty is and
        # nothing else: the Who's default Why is never applied. The decision
        # records the Who and leaves the Why for a human (NEEDS_HUMAN_REVIEW).
        reason = what = None
        destination_source = m.DESTINATION_SOURCE_WHY

    previous = get_current_explanation(session, financial_transaction_id=txn.id)

    # "Confirm" = the human's chosen Who matches what was already proposed
    # (whether that proposal was a firm AUTO_APPLIED result or merely
    # SUGGESTED) — HUMAN_CONFIRMED either way.
    # "Correct" = previous had a concrete proposed Who (i.e. was not
    # NEEDS_HUMAN_REVIEW, which proposes nothing) and the human chose a
    # DIFFERENT one — HUMAN_OVERRIDDEN.
    same_outcome_as_previous = (
        previous is not None and previous.occurrence_id == request.occurrence_id
    )
    is_correction = (
        previous is not None
        and not same_outcome_as_previous
        and previous.occurrence_id is not None
    )

    decision_status = "HUMAN_OVERRIDDEN" if is_correction else "HUMAN_CONFIRMED"
    if reason is None:
        decision_status = "NEEDS_HUMAN_REVIEW"

    notes_parts = [request.notes] if request.notes else []
    if previous is not None:
        notes_parts.append(
            f"Previous decision: id={previous.id}, source={previous.decision_source}, "
            f"status={previous.decision_status}, occurrence={previous.occurrence_id}, "
            f"reason={previous.transaction_reason_id}."
        )
    else:
        notes_parts.append("No previous decision existed for this transaction.")

    confirmed_at = datetime.now(UTC)

    if reason is not None:
        notes_parts.append(
            f"Chosen: Who {occurrence.canonical_name!r} -> Why {reason.name!r} "
            + (f"-> What {what.code} ({what.name}, {what.statement_type})." if what is not None
               else "-> no accounting destination yet (bookkeeping pending).")
        )
    else:
        notes_parts.append(
            f"Who {occurrence.canonical_name!r} confirmed. No Why was chosen and none is taken "
            "from the Who: the Why of this transaction still needs a human decision."
        )

    return _create_decision_row(
        session, txn, occurrence_id=request.occurrence_id,
        transaction_reason_id=reason.id if reason is not None else None,
        decision_source="HUMAN", decision_status=decision_status,
        confidence="HIGH" if reason is not None else None, explanation_notes=" ".join(notes_parts),
        confirmed_by_account_id=request.confirmed_by_account_id, confirmed_at=confirmed_at,
        # An explicit destination only for a TRANSACTION exception; otherwise
        # the snapshot derives it from the WHY exactly as before.
        accounting_classification_id=(what.id if destination_source == m.DESTINATION_SOURCE_TRANSACTION
                                      else None),
        accounting_destination_source=destination_source,
    )


# ---------------------------------------------------------------------------
# Explicit reclassification of an already-decided transaction
# ---------------------------------------------------------------------------


def reclassify_transaction(
    session: Session, *, transaction_id: int, confirmed_by_account_id: int | None,
    occurrence_id: int | None = None, notes: str | None = None,
) -> "m.BankTransactionExplanation":
    """BANK_RECONCILIATION_WHO_WHY_WHAT_001 — the `Reclassify` action.

    Editing a Who -> Why or a Why -> What association changes FUTURE
    classifications only; an already-confirmed transaction keeps the
    snapshot it was decided with, and nothing ever changes it silently.
    This function is the one explicit way a human applies the CURRENT
    chain to a historical transaction — and it does so by APPENDING a new
    `HUMAN_RECLASSIFIED` decision row, leaving the superseded decision
    exactly as it was, still queryable as history.

    `occurrence_id` defaults to the transaction's current Who: the normal
    case is "same Who, re-resolved through the chain as it is now".
    Passing a different Who is a correction, which
    `record_human_decision` already covers — so it is refused here, to
    keep the two actions distinguishable in the audit trail."""
    txn = session.get(m.FinancialTransaction, transaction_id)
    if txn is None:
        raise ValueError(f"FinancialTransaction {transaction_id} not found")

    previous = get_current_explanation(session, financial_transaction_id=txn.id)
    if previous is None or previous.occurrence_id is None:
        raise ValueError(
            "This transaction has no confirmed Who to reclassify. Select a Who first."
        )
    if occurrence_id is not None and occurrence_id != previous.occurrence_id:
        raise ValueError(
            "Reclassify re-resolves the SAME Who through the current chain. "
            "To change the Who itself, confirm a different Who instead."
        )
    # BANK_RECONCILIATION_STANDARDS_001 — only a destination DERIVED from the
    # WHY may be re-derived. One a human chose for this transaction is never
    # reset silently to the WHY's mapping.
    if previous.accounting_destination_source != m.DESTINATION_SOURCE_WHY:
        raise ValueError(
            "This transaction's accounting destination was chosen explicitly for this transaction; "
            "Reclassify only re-derives a destination that came from the WHY, so it was left unchanged."
        )

    occurrence = session.get(m.BankOccurrence, previous.occurrence_id)
    if occurrence is None:
        raise ValueError(f"BankOccurrence {previous.occurrence_id} no longer exists")

    # BANK_FINAL_RELEASE_BLOCKERS_001 — the Why is the one ALREADY decided
    # for this transaction; only its CURRENT Why -> What mapping is re-read.
    # The Who's default Why is never consulted.
    reason = (session.get(m.BankTransactionReason, previous.transaction_reason_id)
              if previous.transaction_reason_id is not None else None)
    if reason is None:
        raise ValueError(
            "This transaction has no Why yet. Choose its Why — a Who's default is never applied."
        )
    what = reason.accounting_classification
    if reason.status != "ACTIVE" or what is None or not what.is_posting_account:
        raise ValueError(
            f"Why {reason.code} — {reason.name} is inactive or has no postable accounting "
            "destination; fix the Why before reclassifying."
        )

    notes_parts = [notes] if notes else []
    notes_parts.append(
        f"Explicit reclassification of the existing Why {reason.name!r} (Who "
        f"{occurrence.canonical_name!r}) through its current mapping: What {what.code} ({what.name})."
    )
    notes_parts.append(
        f"Superseded decision: id={previous.id}, status={previous.decision_status}, "
        f"reason={previous.transaction_reason_id}, "
        f"what={previous.accounting_classification_code_snapshot or '—'}. That row is unchanged."
    )

    return _create_decision_row(
        session, txn, occurrence_id=occurrence.id, transaction_reason_id=reason.id,
        decision_source="HUMAN", decision_status="HUMAN_RECLASSIFIED",
        confidence="HIGH", explanation_notes=" ".join(notes_parts),
        confirmed_by_account_id=confirmed_by_account_id, confirmed_at=datetime.now(UTC),
    )
