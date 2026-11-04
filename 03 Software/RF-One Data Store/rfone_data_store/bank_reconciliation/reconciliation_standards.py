"""Reconciliation Standards (BANK_RECONCILIATION_STANDARDS_001).

A Standard is HUMAN-APPROVED reconciliation knowledge:

    recognition signature -> WHO -> WHY -> accounting destination -> For Whom

It exists only because a person reviewed a transaction and chose "Set as
Standard". It is not a confidence score and not a `BankRecognitionRule`:
recognition rules stay WHO-only (BANK_WHO_WHY_INVARIANT_001); a Standard may
supply the WHY only because a human approved that complete combination.

One recognition semantics, not two: a Standard's signature has the same
dimensions as a recognition rule and is matched by the same function
(`recognition._rule_matches`), with the same instrument and direction scope
rules as `recognition.find_candidate_rules`.

A transaction becomes AUTOMATIC only at import (`apply_to_transaction`,
called for each newly normalized transaction) and only when the matching
ACTIVE Standards agree on one complete, still-valid result. Nothing is
applied retroactively to transactions already imported.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import economic_allocation
from . import recognition

CONFLICT_MESSAGE = (
    "This transaction cannot become a separate Standard because RF-One has no distinct "
    "recognition pattern for this variation: an active Standard with the same pattern gives a "
    "different result. Save it as an individual exception instead (Save — keep Standard unchanged)."
)


@dataclass(frozen=True)
class Signature:
    match_type: str
    normalized_pattern: str
    match_field: str
    payment_instrument_id: int | None
    direction: str | None


@dataclass(frozen=True)
class Result:
    occurrence_id: int
    transaction_reason_id: int
    accounting_classification_id: int
    reporting_entity_id: int


def result_of(standard: "m.BankReconciliationStandard") -> Result:
    return Result(standard.occurrence_id, standard.transaction_reason_id,
                  standard.accounting_classification_id, standard.reporting_entity_id)


def signature_for(session: Session, transaction: "m.FinancialTransaction") -> Signature:
    """The signature a Standard created from THIS transaction gets.

    If one identifiable recognition rule produced the recognition basis —
    the rule named by the current decision, otherwise the single ACTIVE rule
    matching the transaction — its match type, pattern and field are reused.
    Otherwise: the transaction's exact normalized description. Either way the
    Standard is scoped to this Account / Card and this direction."""
    direction = recognition.direction_for_amount(transaction.amount_minor)
    explanation = recognition.get_current_explanation(session, financial_transaction_id=transaction.id)
    rule = None
    if explanation is not None and explanation.recognition_rule_id is not None:
        rule = session.get(m.BankRecognitionRule, explanation.recognition_rule_id)
    if rule is None:
        candidates = recognition.find_candidate_rules(
            session,
            normalized_description=recognition.normalize_description_for_recognition(transaction.description_original),
            payment_instrument_id=transaction.payment_instrument_id, direction=direction,
            normalized_memo=recognition.normalize_memo_for_recognition(transaction.source_memo),
        )
        if len(candidates) == 1:
            rule = candidates[0]
    if rule is not None:
        return Signature(rule.match_type, rule.normalized_pattern, rule.match_field,
                         transaction.payment_instrument_id, direction)
    pattern = recognition.normalize_description_for_recognition(transaction.description_original)
    if not pattern:
        raise ValueError("This transaction has no description to recognise it by, so it cannot become a Standard.")
    return Signature(recognition.EXACT_NORMALIZED_DESCRIPTION, pattern, recognition.DESCRIPTION,
                     transaction.payment_instrument_id, direction)


def _active_with_signature(session: Session, signature: Signature) -> "m.BankReconciliationStandard | None":
    s = m.BankReconciliationStandard
    return session.scalar(select(s).where(
        s.status == "ACTIVE",
        s.match_type == signature.match_type,
        s.normalized_pattern == signature.normalized_pattern,
        s.match_field == signature.match_field,
        s.payment_instrument_id.is_(None) if signature.payment_instrument_id is None
        else s.payment_instrument_id == signature.payment_instrument_id,
        s.direction.is_(None) if signature.direction is None else s.direction == signature.direction,
    ))


def _validate_result(session: Session, result: Result) -> None:
    who = session.get(m.BankOccurrence, result.occurrence_id)
    if who is None or who.status != "ACTIVE":
        raise ValueError("A Standard needs an active WHO.")
    why = session.get(m.BankTransactionReason, result.transaction_reason_id)
    if why is None or why.status != "ACTIVE" or why.accounting_classification_id is None:
        raise ValueError("A Standard needs an active WHY with an accounting destination.")
    destination = session.get(m.BankAccountingClassification, result.accounting_classification_id)
    if destination is None or not destination.is_posting_account:
        raise ValueError("A Standard needs a valid accounting destination.")
    if not (destination.is_what or destination.id == why.accounting_classification_id):
        raise ValueError(
            f"{destination.code} — {destination.name} is neither a P&L WHAT nor this WHY's own destination."
        )
    entity = session.get(m.ReportingEntity, result.reporting_entity_id)
    if entity is None or entity.status != "ACTIVE":
        raise ValueError("A Standard needs an active For Whom entity.")


def create_or_reuse(
    session: Session, *, signature: Signature, result: Result, approved_by_account_id: int | None,
    created_from_transaction_id: int | None,
) -> tuple["m.BankReconciliationStandard", bool]:
    """Same active signature + same result: the existing Standard, reused.
    Same active signature + a different result: refused — two
    indistinguishable Standards could never be told apart. The existing
    Standard is never modified."""
    existing = _active_with_signature(session, signature)
    if existing is not None:
        if result_of(existing) == result:
            return existing, False
        raise ValueError(CONFLICT_MESSAGE)
    _validate_result(session, result)
    standard = m.BankReconciliationStandard(
        match_type=signature.match_type, normalized_pattern=signature.normalized_pattern,
        match_field=signature.match_field, payment_instrument_id=signature.payment_instrument_id,
        direction=signature.direction,
        occurrence_id=result.occurrence_id, transaction_reason_id=result.transaction_reason_id,
        accounting_classification_id=result.accounting_classification_id,
        reporting_entity_id=result.reporting_entity_id,
        status="ACTIVE", approved_by_account_id=approved_by_account_id,
        approved_at=datetime.now(timezone.utc), created_from_transaction_id=created_from_transaction_id,
    )
    session.add(standard)
    session.flush()
    return standard, True


def matching_standards(session: Session, transaction: "m.FinancialTransaction") -> list["m.BankReconciliationStandard"]:
    """ACTIVE Standards whose signature matches, most specific first — the
    same matching and scoping as `recognition.find_candidate_rules`."""
    normalized = recognition.normalize_description_for_recognition(transaction.description_original)
    memo = recognition.normalize_memo_for_recognition(transaction.source_memo)
    direction = recognition.direction_for_amount(transaction.amount_minor)
    standards = session.scalars(
        select(m.BankReconciliationStandard).where(m.BankReconciliationStandard.status == "ACTIVE")
    ).all()
    matches = [
        s for s in standards
        if (s.payment_instrument_id is None or s.payment_instrument_id == transaction.payment_instrument_id)
        and (s.direction is None or s.direction == direction)
        and recognition._rule_matches(s, normalized, memo)
    ]
    matches.sort(key=_specificity)
    return matches


def _specificity(standard: "m.BankReconciliationStandard") -> tuple:
    """Most specific first, with the same order `recognition` uses for its
    rules (match type, instrument scope, direction scope, pattern length);
    a Standard has no priority column, so its id breaks ties."""
    return (
        recognition._MATCH_TYPE_SPECIFICITY.get(standard.match_type, 99),
        0 if standard.payment_instrument_id is not None else 1,
        0 if standard.direction is not None else 1,
        -len(standard.normalized_pattern),
        standard.id,
    )


def applicable_standard(session: Session, transaction: "m.FinancialTransaction") -> "m.BankReconciliationStandard | None":
    """The one Standard that may complete this transaction, or None: no
    match, matches that disagree on the result, or a result that is no
    longer valid (inactive WHO / WHY / entity) — all of which leave the
    transaction in NEEDS REVIEW. Nothing is guessed."""
    matches = matching_standards(session, transaction)
    if not matches or len({result_of(s) for s in matches}) != 1:
        return None
    standard = matches[0]
    try:
        _validate_result(session, result_of(standard))
    except ValueError:
        return None
    return standard


def apply_to_transaction(session: Session, transaction: "m.FinancialTransaction") -> "m.BankReconciliationStandard | None":
    """Complete ONE newly imported transaction from its Standard, if exactly
    one complete result applies: a RULE decision and a RULE, COMPLETE
    allocation, both with `accounting_destination_source = STANDARD` and the
    Standard's id. A transaction a human already decided, or one that
    already has allocations, is left alone."""
    current = recognition.get_current_explanation(session, financial_transaction_id=transaction.id)
    if current is not None and current.decision_source == "HUMAN":
        return None
    if economic_allocation.get_allocations(session, financial_transaction_id=transaction.id):
        return None
    standard = applicable_standard(session, transaction)
    if standard is None:
        return None
    recognition._create_decision_row(
        session, transaction, occurrence_id=standard.occurrence_id,
        transaction_reason_id=standard.transaction_reason_id, recognition_rule_id=None,
        decision_source="RULE", decision_status="AUTO_APPLIED", confidence=None,
        explanation_notes=(
            f"Completed by approved Reconciliation Standard #{standard.id} "
            f"({standard.match_type} {standard.normalized_pattern!r}): WHO, WHY, accounting "
            "destination and For Whom as a human approved them."
        ),
        accounting_classification_id=standard.accounting_classification_id,
        accounting_destination_source=m.DESTINATION_SOURCE_STANDARD,
        reconciliation_standard_id=standard.id,
    )
    economic_allocation.set_allocations(
        session, financial_transaction_id=transaction.id,
        specs=[economic_allocation.AllocationSpec(
            amount_minor=transaction.amount_minor, reporting_entity_id=standard.reporting_entity_id,
            transaction_reason_id=standard.transaction_reason_id,
            accounting_classification_id=standard.accounting_classification_id,
            reconciliation_standard_id=standard.id,
            status=economic_allocation.COMPLETE, decision_source="RULE",
            notes=f"Automatic: Reconciliation Standard #{standard.id}.",
        )],
    )
    transaction.review_status = "REVIEWED"
    session.flush()
    return standard
