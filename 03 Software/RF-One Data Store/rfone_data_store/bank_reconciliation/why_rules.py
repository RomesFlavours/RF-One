"""Deterministic WHY rules of WHO Classification (BANK_CLASSIFICATION_LEARNING_001).

A WHY rule applies only to a transaction whose WHO is ALREADY known: within
that WHO's scope, simple conditions on the transaction's own bank evidence
(a contained description phrase, a direction, an instrument type) name the
WHY. It never chooses a WHO. It exists only by explicit human approval
(normally of a Classification Learning suggestion); at runtime it is plain
matching — no AI, no model, no network.

Runtime (`apply_to_new_transaction`) is the import step that follows WHO
recognition: when the current automatic decision names a WHO but no WHY, the
most specific matching ACTIVE rule records the WHY (WHAT derived from it).
Never touched: a HUMAN decision, a Standard decision, a decision that already
has a WHY. Two matching rules of equal specificity naming different WHY:
nothing is recorded — a person decides.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import recognition

ACTIVE = "ACTIVE"


@dataclass(frozen=True)
class Evidence:
    """The raw facts a WHY rule may test — never the refined truth."""
    normalized_description: str
    direction: str
    instrument_type: str | None


def evidence_of(txn: "m.FinancialTransaction", instrument_type: str | None) -> Evidence:
    return Evidence(recognition.normalize_description_for_recognition(txn.description_original or ""),
                    recognition.direction_for_amount(txn.amount_minor), instrument_type)


def matches(rule, ev: Evidence) -> bool:
    """`rule` may be a `BankWhyRule` or any object with the same condition fields."""
    if rule.description_contains and rule.description_contains not in ev.normalized_description:
        return False
    if rule.direction and rule.direction != ev.direction:
        return False
    if rule.instrument_type and rule.instrument_type != ev.instrument_type:
        return False
    return True


def specificity(rule) -> int:
    return sum(1 for value in (rule.description_contains, rule.direction, rule.instrument_type) if value)


def choose(rules, ev: Evidence):
    """The single WHY the most specific matching rules agree on, or None."""
    hits = [r for r in rules if matches(r, ev)]
    if not hits:
        return None
    best = max(specificity(r) for r in hits)
    top = {r.transaction_reason_id for r in hits if specificity(r) == best}
    if len(top) != 1:
        return None
    return next(r for r in hits if specificity(r) == best)


def active_by_who(session: Session) -> dict[int, list["m.BankWhyRule"]]:
    out: dict[int, list] = {}
    for rule in session.scalars(select(m.BankWhyRule).where(m.BankWhyRule.status == ACTIVE)):
        out.setdefault(rule.occurrence_id, []).append(rule)
    return out


def create_rule(session: Session, *, occurrence_id: int, transaction_reason_id: int,
                description_contains: str | None, direction: str | None, instrument_type: str | None,
                approved_by_account_id: int | None, evidence: dict | None, origin: str = "PATTERN_DISCOVERY",
                approved_at=None) -> "m.BankWhyRule":
    who = session.get(m.BankOccurrence, occurrence_id)
    if who is None or who.status != "ACTIVE":
        raise ValueError("A WHY rule needs an active WHO.")
    reason = session.get(m.BankTransactionReason, transaction_reason_id)
    # Bank reconciliation is WHO + WHY; a WHY needs no WHAT to be decided
    # (BANK_WHY_WITHOUT_WHAT_001). Its WHAT, when it has one, follows it.
    if reason is None or reason.status != "ACTIVE":
        raise ValueError("A WHY rule needs an active WHY.")
    phrase = recognition.normalize_description_for_recognition(description_contains or "") or None
    for existing in session.scalars(select(m.BankWhyRule).where(
            m.BankWhyRule.occurrence_id == occurrence_id, m.BankWhyRule.status == ACTIVE)):
        if (existing.description_contains, existing.direction, existing.instrument_type) == \
                (phrase, direction, instrument_type):
            if existing.transaction_reason_id != transaction_reason_id:
                raise ValueError("An active WHY rule with the same conditions names a different WHY.")
            return existing
    rule = m.BankWhyRule(occurrence_id=occurrence_id, transaction_reason_id=transaction_reason_id,
                         description_contains=phrase, direction=direction, instrument_type=instrument_type,
                         status=ACTIVE, origin=origin, approved_by_account_id=approved_by_account_id,
                         approved_at=approved_at, evidence_summary=json.dumps(evidence) if evidence else None)
    session.add(rule)
    session.flush()
    return rule


class ImportContext:
    def __init__(self, session: Session):
        self.rules = active_by_who(session)
        self.instrument_types = dict(session.execute(
            select(m.PaymentInstrument.id, m.PaymentInstrument.instrument_type)).all())


def import_context(session: Session) -> ImportContext | None:
    context = ImportContext(session)
    return context if context.rules else None


def apply_to_new_transaction(session: Session, txn: "m.FinancialTransaction",
                             context: ImportContext | None) -> bool:
    if context is None:
        return False
    current = recognition.get_current_explanation(session, financial_transaction_id=txn.id)
    if (current is None or current.occurrence_id is None or current.transaction_reason_id is not None
            or current.decision_source == "HUMAN" or current.reconciliation_standard_id is not None):
        return False
    rule = choose(context.rules.get(current.occurrence_id, []),
                  evidence_of(txn, context.instrument_types.get(txn.payment_instrument_id)))
    if rule is None:
        return False
    recognition._create_decision_row(
        session, txn, occurrence_id=current.occurrence_id, transaction_reason_id=rule.transaction_reason_id,
        recognition_rule_id=current.recognition_rule_id, decision_source="RULE",
        decision_status=current.decision_status, confidence=current.confidence,
        explanation_notes=(f"WHY from approved WHY rule #{rule.id} (WHO scope #{rule.occurrence_id}"
                           + (f", description contains {rule.description_contains!r}" if rule.description_contains else "")
                           + (f", {rule.direction}" if rule.direction else "")
                           + (f", {rule.instrument_type}" if rule.instrument_type else "")
                           + f"). WHO carried over from decision #{current.id}."),
    )
    return True
