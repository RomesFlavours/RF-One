"""Bank Reconciliation incremental recognition expert system
(BANK_RECONCILIATION_EXPERT_SYSTEM_001).

For every normalized bank transaction, determines:

1. WHO or WHAT is involved (`BankOccurrence`);
2. the TYPE of that subject (`BankOccurrenceType` — `Supplier` is only one
   possible value, never assumed by default);
3. WHY the movement exists (`BankTransactionReason`).

Confirmed human decisions become reusable knowledge (`BankRecognitionRule`).
When no rule matches, or compatible rules disagree, the transaction is
routed to `NEEDS_HUMAN_REVIEW` — never guessed. No opaque model or external
AI service is used: every outcome is explainable from stored rules alone.

This module never derives cost family, cost type, or purchase composition
— those remain exclusively an invoice-side concern (Invoice Intake/
Purchased); `BankOccurrence`/`BankTransactionReason` carry no such field.

Canonical Financial Model Convergence — Phase 4 (FINANCIAL_MODEL_
CONVERGENCE_001): operates on canonical `FinancialTransaction`/
`PaymentInstrument` (was `NormalizedFinancialTransaction`/
`FinancialAccount`); `BankRecognitionRule.payment_instrument_id` (was
`financial_account_id`) is the account/instrument scope.

Phase 4B (Product Owner Decision 1): the decision this module produces is
now the ONE canonical reconciliation decision — every decision row also
captures an immutable Kermali export snapshot (Decision 8) and keeps
`FinancialTransaction.explanation_id` pointed at whichever row is current
(Decision 6). Rule matching, confidence, and the append-only audit
history are otherwise unchanged."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m

UTC = timezone.utc

EXACT_NORMALIZED_DESCRIPTION = "EXACT_NORMALIZED_DESCRIPTION"
CONTAINS_TEXT = "CONTAINS_TEXT"
PREFIX = "PREFIX"
_VALID_MATCH_TYPES = (EXACT_NORMALIZED_DESCRIPTION, CONTAINS_TEXT, PREFIX)

DEBIT = "DEBIT"
CREDIT = "CREDIT"

# Exportable/resolved decision states — everything else blocks export.
RESOLVED_DECISION_STATUSES = ("AUTO_APPLIED", "HUMAN_CONFIRMED", "HUMAN_OVERRIDDEN")

_MATCH_TYPE_SPECIFICITY = {EXACT_NORMALIZED_DESCRIPTION: 0, PREFIX: 1, CONTAINS_TEXT: 2}

# "Prudent" punctuation normalization: characters that vary between export
# formats of the SAME merchant/description (Chase inserts `*`, `#`, extra
# dots/commas inconsistently — spec §3, observed real-file evidence) are
# collapsed to a single space. Digits are never touched — an order number,
# invoice number, or store number may be exactly what distinguishes two
# otherwise-identical descriptions.
_PUNCTUATION_NOISE_RE = re.compile(r"[^A-Z0-9 ]+")
_WHITESPACE_RE = re.compile(r"\s+")


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
# Rule matching
# ---------------------------------------------------------------------------


def _rule_matches(rule: "m.BankRecognitionRule", normalized_description: str) -> bool:
    if rule.match_type == EXACT_NORMALIZED_DESCRIPTION:
        return rule.normalized_pattern == normalized_description
    if rule.match_type == PREFIX:
        return normalized_description.startswith(rule.normalized_pattern)
    if rule.match_type == CONTAINS_TEXT:
        return rule.normalized_pattern in normalized_description
    return False


def _specificity_sort_key(rule: "m.BankRecognitionRule") -> tuple:
    """Lower sorts first (= more specific / higher priority). Compatibility
    is already filtered before this is used (spec step 5: "compatibilità;
    specificità; priority")."""
    return (
        _MATCH_TYPE_SPECIFICITY.get(rule.match_type, 99),
        0 if rule.payment_instrument_id is not None else 1,
        0 if rule.direction is not None else 1,
        -len(rule.normalized_pattern),
        -rule.priority,
        rule.id,
    )


def find_candidate_rules(
    session: Session, *, normalized_description: str, payment_instrument_id: int, direction: str,
) -> list["m.BankRecognitionRule"]:
    """Only ACTIVE rules are ever considered (spec step 2) — a rule at
    `NEEDS_REVIEW` or `INACTIVE` never matches until a human reactivates
    it. Respects the rule's own instrument scope (step 3) and direction
    scope (step 4). Returned ordered most-specific/highest-priority
    first."""
    rules = session.scalars(
        select(m.BankRecognitionRule).where(m.BankRecognitionRule.status == "ACTIVE")
    ).all()
    compatible = [
        rule for rule in rules
        if (rule.payment_instrument_id is None or rule.payment_instrument_id == payment_instrument_id)
        and (rule.direction is None or rule.direction == direction)
        and _rule_matches(rule, normalized_description)
    ]
    compatible.sort(key=_specificity_sort_key)
    return compatible


# ---------------------------------------------------------------------------
# Deduction engine
# ---------------------------------------------------------------------------


def _capture_snapshot(
    session: Session, *, occurrence_id: int | None, transaction_reason_id: int | None,
) -> dict:
    """Canonical Financial Model Convergence — Phase 4B (Product Owner
    Decision 8). Reads `BankOccurrence.canonical_name` and the selected
    Reason's `BankTransactionReasonExportMapping` (if any) ONCE, at
    decision time, and returns them as plain values to be stored on the
    new decision row. Never re-read from those tables afterward — a later
    rename/edit of either must never change an already-decided
    transaction's historical Kermali output. Absence of a value (no
    Occurrence, or a Reason with no configured Export Mapping yet) is
    preserved as NULL, never guessed."""
    occurrence_name_snapshot = None
    if occurrence_id is not None:
        occurrence = session.get(m.BankOccurrence, occurrence_id)
        if occurrence is not None:
            occurrence_name_snapshot = occurrence.canonical_name

    food_cost_snapshot = operative_snapshot = deductible_snapshot = what_label_snapshot = None
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

    return {
        "occurrence_name_snapshot": occurrence_name_snapshot,
        "food_cost_snapshot": food_cost_snapshot,
        "operative_snapshot": operative_snapshot,
        "deductible_snapshot": deductible_snapshot,
        "what_label_snapshot": what_label_snapshot,
    }


def _create_decision_row(
    session: Session, txn: "m.FinancialTransaction", *,
    occurrence_id: int | None, transaction_reason_id: int | None, recognition_rule_id: int | None,
    decision_source: str, decision_status: str, confidence: str | None, explanation_notes: str,
    confirmed_by_account_id: int | None = None, confirmed_at: datetime | None = None,
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
    snapshot = _capture_snapshot(session, occurrence_id=occurrence_id, transaction_reason_id=transaction_reason_id)
    row = m.BankTransactionExplanation(
        financial_transaction_id=txn.id,
        occurrence_id=occurrence_id,
        transaction_reason_id=transaction_reason_id,
        recognition_rule_id=recognition_rule_id,
        decision_source=decision_source,
        decision_status=decision_status,
        confidence=confidence,
        explanation_notes=explanation_notes,
        confirmed_by_account_id=confirmed_by_account_id,
        confirmed_at=confirmed_at,
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


def deduce_for_transaction(
    session: Session, txn: "m.FinancialTransaction",
) -> "m.BankTransactionExplanation":
    """Runs once for every newly normalized transaction (called from
    `service._normalize_rows`). Never invoked for a transaction that
    already has a human decision — `service.py` only calls this at
    creation time, before any human has looked at the row."""
    normalized = normalize_description_for_recognition(txn.description_original)
    direction = direction_for_amount(txn.amount_minor)
    candidates = find_candidate_rules(
        session, normalized_description=normalized,
        payment_instrument_id=txn.payment_instrument_id, direction=direction,
    )

    if not candidates:
        notes = (
            f"No ACTIVE recognition rule matched. Normalized description: {normalized!r}. "
            f"Payment Instrument: {txn.payment_instrument_id}. Direction: {direction}."
        )
        return _create_decision_row(
            session, txn, occurrence_id=None, transaction_reason_id=None, recognition_rule_id=None,
            decision_source="RULE", decision_status="NEEDS_HUMAN_REVIEW", confidence=None,
            explanation_notes=notes,
        )

    outcome_groups: dict[tuple[int, int], list["m.BankRecognitionRule"]] = {}
    for rule in candidates:
        outcome_groups.setdefault((rule.occurrence_id, rule.transaction_reason_id), []).append(rule)

    if len(outcome_groups) > 1:
        summary = "; ".join(
            f"rule #{group[0].id} ({group[0].match_type} -> occurrence={occ_id}, reason={reason_id})"
            for (occ_id, reason_id), group in outcome_groups.items()
        )
        notes = (
            f"{len(candidates)} compatible ACTIVE rule(s) produced {len(outcome_groups)} different, "
            f"contradictory outcomes — cannot resolve automatically: {summary}."
        )
        return _create_decision_row(
            session, txn, occurrence_id=None, transaction_reason_id=None, recognition_rule_id=None,
            decision_source="RULE", decision_status="NEEDS_HUMAN_REVIEW", confidence=None,
            explanation_notes=notes,
        )

    best_rule = candidates[0]  # most specific among the agreeing candidates
    if best_rule.auto_apply_enabled:
        decision_status = "AUTO_APPLIED"
        confidence = "HIGH" if best_rule.match_type == EXACT_NORMALIZED_DESCRIPTION else "MEDIUM"
        notes = (
            f"Applied rule #{best_rule.id} ({best_rule.match_type}, "
            f"pattern={best_rule.normalized_pattern!r}, priority={best_rule.priority}) — single "
            f"non-contradictory outcome among {len(candidates)} compatible ACTIVE rule(s)."
        )
    else:
        decision_status = "SUGGESTED"
        confidence = "LOW"
        notes = (
            f"Rule #{best_rule.id} ({best_rule.match_type}, pattern={best_rule.normalized_pattern!r}) "
            "matches but auto_apply_enabled=False — suggested only, requires human confirmation."
        )

    return _create_decision_row(
        session, txn, occurrence_id=best_rule.occurrence_id, transaction_reason_id=best_rule.transaction_reason_id,
        recognition_rule_id=best_rule.id, decision_source="RULE", decision_status=decision_status,
        confidence=confidence, explanation_notes=notes,
    )


# ---------------------------------------------------------------------------
# Human-guided learning
# ---------------------------------------------------------------------------


def create_or_reuse_rule(
    session: Session, *, match_type: str, normalized_pattern: str,
    occurrence_id: int, transaction_reason_id: int,
    payment_instrument_id: int | None, direction: str | None,
    auto_apply_enabled: bool, created_from_transaction_id: int | None, priority: int = 0,
) -> "m.BankRecognitionRule":
    """`CONTAINS_TEXT`/`PREFIX` rules are created ONLY when the human
    explicitly chose that broader match type (spec: "devono essere create
    o abilitate esplicitamente dall'Umano") — this function itself applies
    no restriction on WHICH match_type may be passed; the caller (the
    human-decision route) is what enforces "EXACT is the safe default,
    CONTAINS/PREFIX require an explicit separate choice".

    `auto_apply_enabled` may only be true here as a direct, explicit human
    decision passed by the caller — no confirmation/contradiction count is
    read or computed to decide it."""
    if match_type not in _VALID_MATCH_TYPES:
        raise ValueError(f"Invalid match_type: {match_type!r}")

    existing = session.scalars(
        select(m.BankRecognitionRule).where(
            m.BankRecognitionRule.match_type == match_type,
            m.BankRecognitionRule.normalized_pattern == normalized_pattern,
            m.BankRecognitionRule.payment_instrument_id.is_(payment_instrument_id) if payment_instrument_id is None
            else m.BankRecognitionRule.payment_instrument_id == payment_instrument_id,
            m.BankRecognitionRule.direction.is_(direction) if direction is None
            else m.BankRecognitionRule.direction == direction,
        )
    ).first()
    if existing is not None:
        if existing.occurrence_id == occurrence_id and existing.transaction_reason_id == transaction_reason_id:
            existing.human_confirmations += 1
            if auto_apply_enabled:
                existing.auto_apply_enabled = True
            session.flush()
            return existing
        # An existing rule with the same pattern/scope but a DIFFERENT
        # outcome is contradicted by this new human decision — never
        # silently overwritten (spec: "non sovrascrivere silenziosamente
        # una decisione umana precedente"); flagged for review instead.
        existing.human_contradictions += 1
        existing.status = "NEEDS_REVIEW"
        session.flush()

    rule = m.BankRecognitionRule(
        match_type=match_type, normalized_pattern=normalized_pattern,
        payment_instrument_id=payment_instrument_id, direction=direction,
        occurrence_id=occurrence_id, transaction_reason_id=transaction_reason_id,
        priority=priority, status="ACTIVE", auto_apply_enabled=auto_apply_enabled,
        human_confirmations=1 if auto_apply_enabled else 0,
        created_from_transaction_id=created_from_transaction_id,
    )
    session.add(rule)
    session.flush()
    return rule


@dataclass
class HumanDecisionRequest:
    transaction_id: int
    occurrence_id: int
    transaction_reason_id: int
    confirmed_by_account_id: int | None
    reuse_for_future: bool = False
    # Only set when the human explicitly chose a broader rule (spec step 6).
    broaden_match_type: str | None = None  # CONTAINS_TEXT or PREFIX
    broaden_pattern: str | None = None
    scope_to_account: bool = False
    scope_to_direction: bool = False
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
    reason = session.get(m.BankTransactionReason, request.transaction_reason_id)
    if reason is None:
        raise ValueError(f"BankTransactionReason {request.transaction_reason_id} not found")

    previous = get_current_explanation(session, financial_transaction_id=txn.id)

    # "Confirm" = the human's chosen occurrence/reason matches what was
    # already proposed (whether that proposal was a firm AUTO_APPLIED
    # result or merely SUGGESTED) — HUMAN_CONFIRMED either way.
    # "Correct" = previous had a concrete proposed answer (i.e. was not
    # NEEDS_HUMAN_REVIEW, which proposes nothing) and the human chose a
    # DIFFERENT occurrence/reason — HUMAN_OVERRIDDEN.
    same_outcome_as_previous = (
        previous is not None
        and previous.occurrence_id == request.occurrence_id
        and previous.transaction_reason_id == request.transaction_reason_id
    )
    is_correction = (
        previous is not None
        and not same_outcome_as_previous
        and previous.occurrence_id is not None
        and previous.transaction_reason_id is not None
    )

    decision_status = "HUMAN_OVERRIDDEN" if is_correction else "HUMAN_CONFIRMED"

    notes_parts = [request.notes] if request.notes else []
    if previous is not None:
        notes_parts.append(
            f"Previous decision: id={previous.id}, source={previous.decision_source}, "
            f"status={previous.decision_status}, occurrence={previous.occurrence_id}, "
            f"reason={previous.transaction_reason_id}, rule={previous.recognition_rule_id}."
        )
    else:
        notes_parts.append("No previous decision existed for this transaction.")

    if is_correction and previous.recognition_rule_id is not None:
        rule = session.get(m.BankRecognitionRule, previous.recognition_rule_id)
        if rule is not None:
            rule.human_contradictions += 1
            # Only an AUTO_APPLIED rule is demoted — it acted autonomously
            # and got it wrong, which is itself sufficient evidence it is
            # "no longer safe" (spec), with no invented numeric threshold.
            if previous.decision_status == "AUTO_APPLIED":
                rule.status = "NEEDS_REVIEW"
            session.flush()
            notes_parts.append(
                f"Contradicts rule #{rule.id} (human_contradictions now {rule.human_contradictions})"
                + (", rule set to NEEDS_REVIEW." if previous.decision_status == "AUTO_APPLIED" else ".")
            )

    confirmed_at = datetime.now(UTC)
    recognition_rule_id = None

    if request.reuse_for_future or request.broaden_match_type:
        normalized_pattern = normalize_description_for_recognition(txn.description_original)
        direction = direction_for_amount(txn.amount_minor)
        instrument_scope = txn.payment_instrument_id if request.scope_to_account else None
        direction_scope = direction if request.scope_to_direction else None

        if request.broaden_match_type:
            if request.broaden_match_type not in (CONTAINS_TEXT, PREFIX):
                raise ValueError(
                    f"broaden_match_type must be CONTAINS_TEXT or PREFIX, got {request.broaden_match_type!r}"
                )
            pattern = request.broaden_pattern or normalized_pattern
            rule = create_or_reuse_rule(
                session, match_type=request.broaden_match_type, normalized_pattern=pattern,
                occurrence_id=request.occurrence_id, transaction_reason_id=request.transaction_reason_id,
                payment_instrument_id=instrument_scope, direction=direction_scope,
                auto_apply_enabled=True, created_from_transaction_id=txn.id,
            )
        else:
            rule = create_or_reuse_rule(
                session, match_type=EXACT_NORMALIZED_DESCRIPTION, normalized_pattern=normalized_pattern,
                occurrence_id=request.occurrence_id, transaction_reason_id=request.transaction_reason_id,
                payment_instrument_id=instrument_scope, direction=direction_scope,
                auto_apply_enabled=True, created_from_transaction_id=txn.id,
            )
        recognition_rule_id = rule.id
        notes_parts.append(f"Reusable rule #{rule.id} ({rule.match_type}, pattern={rule.normalized_pattern!r}) created/confirmed.")

    return _create_decision_row(
        session, txn, occurrence_id=request.occurrence_id, transaction_reason_id=request.transaction_reason_id,
        recognition_rule_id=recognition_rule_id, decision_source="HUMAN", decision_status=decision_status,
        confidence="HIGH", explanation_notes=" ".join(notes_parts),
        confirmed_by_account_id=request.confirmed_by_account_id, confirmed_at=confirmed_at,
    )
