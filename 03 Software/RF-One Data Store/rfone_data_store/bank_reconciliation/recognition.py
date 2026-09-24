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
history are otherwise unchanged.

BANK_RECONCILIATION_WHO_WHY_WHAT_001 — hierarchical classification. WHO
is now the ONLY thing a human (or a rule) ever chooses: WHY comes from
the WHO's default Reason and WHAT from that Reason's accounting
classification (`bank_reconciliation/classification.py`). Consequences
here:

* a recognition rule recognizes a WHO; its stored `transaction_reason_id`
  is the reason derived when the rule was created, kept as history, and
  the CURRENT chain is what a later application of that rule resolves —
  so re-pointing a WHO at another WHY immediately affects new
  transactions without touching a single rule;
* a chain that ends on a GROUP account auto-applies nothing — a
  reporting node is never an automatic classification destination
  (BANK_ACCOUNTING_CLASSIFICATION_SEMANTICS_001 §6);
* a matched rule names the WHO and stops there. The WHY and the WHAT
  come from the TRANSACTION's own purpose evidence — its memo, purpose
  wording in its description, or a deterministic description rule — and
  never from the fact that this counterparty was classified some way
  before (BANK_WHO_WHY_INVARIANT_001). That is what lets the SAME payee
  be Tips on one payment and 1099 contract labour on the next without
  either result being learned as a property of the payee, and it is why
  `BankOccurrence.default_transaction_reason_id` is read here as a
  SUGGESTION shown to the human, never as the resolution;
* contradiction between candidate rules is judged on the WHO, because
  two rules agreeing on the WHO can no longer disagree on the WHY;
* every decision row snapshots the WHY name and the WHAT (id, code, name,
  statement type) alongside the existing Occurrence/Kermali snapshot, so
  an already-confirmed transaction never changes meaning when the
  vocabulary is edited;
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
from . import purpose_evidence as pe
from . import why_catalog

UTC = timezone.utc

EXACT_NORMALIZED_DESCRIPTION = "EXACT_NORMALIZED_DESCRIPTION"
CONTAINS_TEXT = "CONTAINS_TEXT"
PREFIX = "PREFIX"
_VALID_MATCH_TYPES = (EXACT_NORMALIZED_DESCRIPTION, CONTAINS_TEXT, PREFIX)

DEBIT = "DEBIT"
CREDIT = "CREDIT"

# Exportable/resolved decision states — everything else blocks export.
RESOLVED_DECISION_STATUSES = (
    "AUTO_APPLIED", "HUMAN_CONFIRMED", "HUMAN_OVERRIDDEN", "HUMAN_RECLASSIFIED",
)

_MATCH_TYPE_SPECIFICITY = {EXACT_NORMALIZED_DESCRIPTION: 0, PREFIX: 1, CONTAINS_TEXT: 2}

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
# Rule matching
# ---------------------------------------------------------------------------


def _rule_matches(
    rule: "m.BankRecognitionRule", normalized_description: str,
    normalized_memo: str | None = None,
) -> bool:
    """Whether this rule matches, against the text the rule says it reads.

    `match_field` selects DESCRIPTION (every rule before
    BANK_MEMO_PURPOSE_CLASSIFICATION_001, and still the default) or MEMO.
    A MEMO rule on a transaction with no memo matches nothing — it is not
    silently retried against the description, because the whole point of a
    memo rule is that it carries no identity."""
    if rule.match_field == MEMO:
        text = normalized_memo or ""
        if not text:
            return False
    else:
        text = normalized_description
    if rule.match_type == EXACT_NORMALIZED_DESCRIPTION:
        return rule.normalized_pattern == text
    if rule.match_type == PREFIX:
        return text.startswith(rule.normalized_pattern)
    if rule.match_type == CONTAINS_TEXT:
        return rule.normalized_pattern in text
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
    normalized_memo: str | None = None,
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
        and _rule_matches(rule, normalized_description, normalized_memo)
    ]
    compatible.sort(key=_specificity_sort_key)
    return compatible


# ---------------------------------------------------------------------------
# Purpose evidence
# ---------------------------------------------------------------------------


def purpose_reason_for(
    session: Session, txn: "m.FinancialTransaction",
) -> "tuple[m.BankTransactionReason | None, structural_why.WhyResult]":
    """The Why this transaction's OWN evidence proves, if any, through the one
    automatic WHY engine (`structural_why.recognize_transaction`) — the
    bank's structure first, then an explicit source memo
    (BANK_FINAL_RELEASE_BLOCKERS_001).

    Returns the engine's result whatever the outcome, so a caller can
    explain a refusal as readily as a match. A Why is returned only when the
    result is resolved, the Why exists and is ACTIVE, and its destination
    may receive an automatic classification. The counterparty is never
    consulted, and no Who's default ever is."""
    from . import structural_why
    result = structural_why.recognize_transaction(session, txn)
    return structural_why.usable_reason(session, result), result


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
    preserved as NULL, never guessed.

    BANK_RECONCILIATION_WHO_WHY_WHAT_001 extends the same rule to the
    WHY name and the WHAT: the accounting classification's id, code,
    name and statement type are captured here too, so editing the
    WHO -> WHY or WHY -> WHAT association later changes only FUTURE
    classifications. An absent WHAT stays NULL and is never invented."""
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
            what = (
                session.get(m.BankAccountingClassification, reason.accounting_classification_id)
                if reason.accounting_classification_id is not None else None
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


@dataclass(frozen=True)
class _Proposal:
    occurrence_id: int | None
    transaction_reason_id: int | None
    recognition_rule_id: int | None
    decision_status: str
    confidence: str | None
    notes: str


def _propose(session: Session, txn: "m.FinancialTransaction") -> _Proposal:
    """What the automatic engine concludes about one transaction. Writes nothing.

    Two separate questions, answered separately (BANK_FINAL_RELEASE_BLOCKERS_001):

      WHO — recognition rules name the counterparty (identity only);
      WHY — the ONE automatic engine, `structural_why.recognize_transaction`,
            from the transaction's own structure and memo.

    The WHO never gates, suggests or decides the WHY: a Who's default Why is
    not read at all."""
    from . import structural_why

    normalized = normalize_description_for_recognition(txn.description_original)
    normalized_memo = normalize_memo_for_recognition(txn.source_memo)
    direction = direction_for_amount(txn.amount_minor)
    candidates = find_candidate_rules(
        session, normalized_description=normalized,
        payment_instrument_id=txn.payment_instrument_id, direction=direction,
        normalized_memo=normalized_memo,
    )
    occurrence_id = rule_id = None
    if not candidates:
        who_note = (
            f"No ACTIVE recognition rule matched. Normalized description: {normalized!r}. "
            f"Payment Instrument: {txn.payment_instrument_id}. Direction: {direction}."
        )
    else:
        groups: dict[int, list["m.BankRecognitionRule"]] = {}
        for rule in candidates:
            groups.setdefault(rule.occurrence_id, []).append(rule)
        if len(groups) > 1:
            summary = "; ".join(
                f"rule #{group[0].id} ({group[0].match_type} -> occurrence={occ_id})"
                for occ_id, group in groups.items()
            )
            who_note = (
                f"{len(candidates)} compatible ACTIVE rule(s) recognized {len(groups)} different, "
                f"contradictory Who values — the Who is left to a human: {summary}."
            )
        else:
            best = candidates[0]
            occurrence = session.get(m.BankOccurrence, best.occurrence_id)
            occurrence_id, rule_id = best.occurrence_id, best.id
            who_note = (
                f"Rule #{best.id} ({best.match_type}, pattern={best.normalized_pattern!r}) "
                f"recognises Who {occurrence.canonical_name if occurrence else best.occurrence_id!r}."
            )
            usual = (session.get(m.BankTransactionReason, occurrence.default_transaction_reason_id)
                     if occurrence is not None and occurrence.default_transaction_reason_id else None)
            if usual is not None:
                # Shown to the reviewer, never applied: that this counterparty
                # is usually one thing is not evidence about this transaction.
                who_note += (
                    f" Suggestion only, from this Who's configured usual Why {usual.name!r}: "
                    "it is not evidence about this transaction and was not applied."
                )

    result = structural_why.recognize_transaction(session, txn)
    reason = structural_why.usable_reason(session, result)
    if reason is not None:
        return _Proposal(
            occurrence_id, reason.id, rule_id, "AUTO_APPLIED", result.confidence,
            f"{structural_why.tag(result.rule_code)} {result.tier} WHY {result.why_code}. "
            f"{result.evidence} The Why comes from this transaction's own evidence, not from the "
            f"counterparty. {who_note}",
        )
    refusal = result.evidence or "the source proves no purpose"
    if result.is_resolved:
        refusal = (f"the engine names {result.why_code}, but that Why is missing, inactive or "
                   "points where an automatic classification may not land")
    return _Proposal(
        occurrence_id, None, rule_id if occurrence_id is not None else None,
        "NEEDS_HUMAN_REVIEW", None,
        f"{who_note} The WHY and the WHAT are left unresolved: identity alone never establishes "
        f"the accounting purpose of a transaction. Automatic WHY engine: {refusal}",
    )


def deduce_for_transaction(
    session: Session, txn: "m.FinancialTransaction",
) -> "m.BankTransactionExplanation":
    """Runs once for every newly normalized transaction (called from
    `service._normalize_rows`) and records what the automatic engine
    concludes, as a RULE decision. Never invoked for a transaction a human
    has already decided."""
    proposal = _propose(session, txn)
    return _create_decision_row(
        session, txn, occurrence_id=proposal.occurrence_id,
        transaction_reason_id=proposal.transaction_reason_id,
        recognition_rule_id=proposal.recognition_rule_id, decision_source="RULE",
        decision_status=proposal.decision_status, confidence=proposal.confidence,
        explanation_notes=proposal.notes,
    )


def redecide_for_transaction(
    session: Session, txn: "m.FinancialTransaction",
) -> "m.BankTransactionExplanation | None":
    """Re-evaluate an automatic decision after something about the
    transaction changed (reprocess, instrument reassignment) — through the
    SAME engine as import.

    * a HUMAN decision is never touched;
    * a new RULE decision is appended only when the engine's WHY changes, or
      when it now recognises a different Who; otherwise the current decision
      stands — so reprocessing is idempotent and a structural decision is
      never replaced by an equivalent one, nor its Who dropped."""
    current = get_current_explanation(session, financial_transaction_id=txn.id)
    if current is not None and current.decision_source == "HUMAN":
        return current
    proposal = _propose(session, txn)
    if current is not None:
        same_why = (current.transaction_reason_id == proposal.transaction_reason_id
                    and current.decision_status == proposal.decision_status)
        who_unchanged = (proposal.occurrence_id is None
                         or proposal.occurrence_id == current.occurrence_id)
        if same_why and who_unchanged:
            return current
    return _create_decision_row(
        session, txn, occurrence_id=proposal.occurrence_id,
        transaction_reason_id=proposal.transaction_reason_id,
        recognition_rule_id=proposal.recognition_rule_id, decision_source="RULE",
        decision_status=proposal.decision_status, confidence=proposal.confidence,
        explanation_notes=proposal.notes,
    )


# ---------------------------------------------------------------------------
# Human-guided learning
# ---------------------------------------------------------------------------


def create_or_reuse_rule(
    session: Session, *, match_type: str, normalized_pattern: str,
    occurrence_id: int, transaction_reason_id: int,
    payment_instrument_id: int | None, direction: str | None,
    auto_apply_enabled: bool, created_from_transaction_id: int | None, priority: int = 0,
    match_field: str = DESCRIPTION, determines_purpose: bool | None = None,
) -> "m.BankRecognitionRule":
    """`CONTAINS_TEXT`/`PREFIX` rules are created ONLY when the human
    explicitly chose that broader match type (spec: "devono essere create
    o abilitate esplicitamente dall'Umano") — this function itself applies
    no restriction on WHICH match_type may be passed; the caller (the
    human-decision route) is what enforces "EXACT is the safe default,
    CONTAINS/PREFIX require an explicit separate choice".

    `auto_apply_enabled` may only be true here as a direct, explicit human
    decision passed by the caller — no confirmation/contradiction count is
    read or computed to decide it.

    `match_field` decides the rule's SCOPE, and `determines_purpose`
    follows from it rather than being chosen
    (BANK_WHO_WHY_INVARIANT_001):

    * a DESCRIPTION rule matches the bank's own text, which is where a
      counterparty is named. It recognises the WHO and may NEVER supply
      the WHAT. Passing `determines_purpose=True` with this scope raises;
    * a MEMO rule matches purpose wording a human wrote. It carries no
      identity — it would match the same memo on any counterparty — so it
      may supply the WHAT.

    Scope is part of a rule's IDENTITY here: a Who-only rule and a purpose
    rule over the same pattern are two different pieces of knowledge, so
    reusing one as the other would silently widen what the first was
    allowed to conclude."""
    if match_type not in _VALID_MATCH_TYPES:
        raise ValueError(f"Invalid match_type: {match_type!r}")
    if match_field not in (DESCRIPTION, MEMO):
        raise ValueError(f"Invalid match_field: {match_field!r}")

    if determines_purpose is None:
        determines_purpose = match_field == MEMO
    if determines_purpose and match_field != MEMO:
        # The single structural refusal that carries the invariant. A
        # caller asking for this is asking for "this counterparty always
        # means this account", which the Bank Domain does not have.
        raise ValueError(
            "A description rule recognises WHO and can never determine WHY: counterparty "
            "identity alone never establishes the accounting purpose of a transaction "
            "(BANK_WHO_WHY_INVARIANT_001). Learn the purpose from the memo wording instead."
        )

    existing = session.scalars(
        select(m.BankRecognitionRule).where(
            m.BankRecognitionRule.match_type == match_type,
            m.BankRecognitionRule.normalized_pattern == normalized_pattern,
            m.BankRecognitionRule.payment_instrument_id.is_(payment_instrument_id) if payment_instrument_id is None
            else m.BankRecognitionRule.payment_instrument_id == payment_instrument_id,
            m.BankRecognitionRule.direction.is_(direction) if direction is None
            else m.BankRecognitionRule.direction == direction,
            m.BankRecognitionRule.match_field == match_field,
            m.BankRecognitionRule.determines_purpose.is_(determines_purpose),
        )
    ).first()
    if existing is not None:
        # BANK_RECONCILIATION_WHO_WHY_WHAT_001: what a rule recognizes is
        # the WHO. Its `transaction_reason_id` is the WHY derived when the
        # rule was last confirmed — refreshed here so the stored history
        # stays readable, never used as the identity of the outcome.
        if existing.occurrence_id == occurrence_id:
            existing.human_confirmations += 1
            existing.transaction_reason_id = transaction_reason_id
            if auto_apply_enabled:
                existing.auto_apply_enabled = True
            if existing.status == "NEEDS_REVIEW":
                # A human has just reconfirmed exactly this pattern -> Who.
                existing.status = "ACTIVE"
            session.flush()
            return existing
        # An existing rule with the same pattern/scope but a DIFFERENT
        # WHO is contradicted by this new human decision — never
        # silently overwritten (spec: "non sovrascrivere silenziosamente
        # una decisione umana precedente"); flagged for review instead.
        # The new rule created below then becomes the one that applies,
        # and the contradicted one keeps its accumulated evidence.
        existing.human_contradictions += 1
        existing.status = "NEEDS_REVIEW"
        session.flush()

    rule = m.BankRecognitionRule(
        match_type=match_type, normalized_pattern=normalized_pattern,
        match_field=match_field, determines_purpose=determines_purpose,
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
    # Whether this confirmation teaches RF-One that THIS normalized
    # description means THIS Who. It is a learning control only: the
    # Who -> Why -> What associations themselves are stored on the
    # vocabulary and are never re-selected per transaction, so leaving it
    # off loses nothing but the description-level shortcut.
    learn_description: bool = True
    # Only set when the human explicitly chose a broader rule (spec step 6).
    broaden_match_type: str | None = None  # CONTAINS_TEXT or PREFIX
    broaden_pattern: str | None = None
    # BANK_MEMO_PURPOSE_CLASSIFICATION_001 §8.
    #
    # `learn_purpose_from_memo` teaches the MEMO WORDING, not the payee:
    # "a payment whose memo says TIP is a tips distribution". Such a rule
    # carries no identity and applies to anyone.
    #
    # There is deliberately NO counterpart that teaches "payments to THIS
    # counterparty are always this What". BANK_WHO_WHY_INVARIANT_001
    # removed the `who_determines_purpose` opt-in that once existed here:
    # WHO never determines WHY by itself, and a decision the domain
    # forbids must not be reachable by passing a flag.
    learn_purpose_from_memo: bool = False
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
        what = reason.accounting_classification
        if what is None:
            raise ValueError(
                f"Why {reason.code} — {reason.name} has no accounting destination yet."
            )
        if not what.is_posting_account:
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
        chain = classification_service.ResolvedChain(
            occurrence, transaction_reason=reason, accounting_classification=what,
        )
    else:
        # BANK_FINAL_RELEASE_BLOCKERS_001 — WHO DOES NOT DETERMINE WHY. With
        # no Why chosen, the human has confirmed WHO the counterparty is and
        # nothing else: the Who's default Why is never applied. The decision
        # records the Who and leaves the Why for a human (NEEDS_HUMAN_REVIEW).
        reason = what = None

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

    if reason is not None:
        notes_parts.append(
            f"Chosen: Who {occurrence.canonical_name!r} -> Why {reason.name!r} "
            f"-> What {what.code} ({what.name}, {what.statement_type})."
        )
    else:
        notes_parts.append(
            f"Who {occurrence.canonical_name!r} confirmed. No Why was chosen and none is taken "
            "from the Who: the Why of this transaction still needs a human decision."
        )
    # A rule's stored reason is a required column but decides nothing (the
    # engine never reads it); with no Why chosen, the Who's own default is
    # stored if it has one, otherwise no description rule is learned.
    rule_reason_id = reason.id if reason is not None else occurrence.default_transaction_reason_id

    # BANK_WHO_WHY_INVARIANT_001 — a confirmation on a description learns
    # the WHO and stops there, for everyone.
    #
    # The earlier version of this made that conditional on the channel: a
    # person's name was Who-only, a supplier's name could decide the
    # account. The Product Owner removed the distinction. Get Better
    # Cleaning having been cleaning nine times is evidence for a human,
    # not a logical rule that Get Better Cleaning can only ever mean
    # cleaning — the tenth payment may be an equipment purchase or a
    # deposit refund. So every learned description rule is Who-only, and
    # `create_or_reuse_rule` refuses to store anything else.
    if (request.learn_description or request.broaden_match_type) and rule_reason_id is None:
        notes_parts.append(
            "No description rule was learned: the Who has no stored Why to file it under, and "
            "none is invented."
        )
    elif request.learn_description or request.broaden_match_type:
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
                occurrence_id=request.occurrence_id, transaction_reason_id=rule_reason_id,
                payment_instrument_id=instrument_scope, direction=direction_scope,
                auto_apply_enabled=True, created_from_transaction_id=txn.id,
            )
        else:
            rule = create_or_reuse_rule(
                session, match_type=EXACT_NORMALIZED_DESCRIPTION, normalized_pattern=normalized_pattern,
                occurrence_id=request.occurrence_id, transaction_reason_id=rule_reason_id,
                payment_instrument_id=instrument_scope, direction=direction_scope,
                auto_apply_enabled=True, created_from_transaction_id=txn.id,
            )
        recognition_rule_id = rule.id
        notes_parts.append(
            f"Reusable rule #{rule.id} ({rule.match_type}, pattern={rule.normalized_pattern!r}) "
            "created/confirmed. Scope: WHO only — it recognises the counterparty and leaves "
            "the accounting purpose of each future transaction to that transaction's own "
            "evidence, or to a human."
        )

    # A PURPOSE rule is the reusable knowledge that actually generalises:
    # it is about the wording, applies to any counterparty, and never
    # mentions a person.
    if request.learn_purpose_from_memo:
        if reason is None:
            raise ValueError(
                "Choose the Why this memo proves before learning a purpose rule from it."
            )
        memo_pattern = normalize_memo_for_recognition(txn.source_memo)
        if not memo_pattern:
            raise ValueError(
                "This transaction carries no memo, so there is no purpose wording to learn. "
                "A rule cannot be created from an absent memo."
            )
        purpose_rule = create_or_reuse_rule(
            session, match_type=EXACT_NORMALIZED_DESCRIPTION, normalized_pattern=memo_pattern,
            occurrence_id=request.occurrence_id, transaction_reason_id=reason.id,
            payment_instrument_id=None, direction=None,
            auto_apply_enabled=True, created_from_transaction_id=txn.id,
            match_field=MEMO, determines_purpose=True,
        )
        notes_parts.append(
            f"Purpose rule #{purpose_rule.id} created/confirmed on the MEMO wording "
            f"{memo_pattern!r}. It carries no counterparty identity."
        )

    return _create_decision_row(
        session, txn, occurrence_id=request.occurrence_id,
        transaction_reason_id=reason.id if reason is not None else None,
        recognition_rule_id=recognition_rule_id, decision_source="HUMAN", decision_status=decision_status,
        confidence="HIGH" if reason is not None else None, explanation_notes=" ".join(notes_parts),
        confirmed_by_account_id=request.confirmed_by_account_id, confirmed_at=confirmed_at,
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
        recognition_rule_id=None, decision_source="HUMAN", decision_status="HUMAN_RECLASSIFIED",
        confidence="HIGH", explanation_notes=" ".join(notes_parts),
        confirmed_by_account_id=confirmed_by_account_id, confirmed_at=datetime.now(UTC),
    )
