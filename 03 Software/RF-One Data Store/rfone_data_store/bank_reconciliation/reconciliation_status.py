"""Canonical reconciliation statuses for manual decisions and validated photos.

A human-confirmed complete allocation remains Confirmed. A complete decision
from an explicitly validated photo is Reconciled and exportable. A photo with
WHO/WHY/WHOM but no accounting destination is Reconciled · accounting pending;
it remains blocked from accounting export. Historical automatic suggestions
never gain either status. Both Review and Export read this one definition.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m

NEEDS_REVIEW = "Needs review"
CONFIRMED = "Confirmed"
RECONCILED = "Reconciled"
RECONCILED_ACCOUNTING_PENDING = "Reconciled · accounting pending"
EXPORTABLE = (CONFIRMED, RECONCILED)

_COMPLETE = m.ALLOCATION_COMPLETE


def status_of(
    transaction: "m.FinancialTransaction", explanation: "m.BankTransactionExplanation | None",
    allocations: list["m.BankTransactionAllocation"],
) -> str:
    if explanation is None or explanation.occurrence_id is None or explanation.transaction_reason_id is None:
        return NEEDS_REVIEW
    if not allocations or sum(a.amount_minor for a in allocations) != transaction.amount_minor:
        return NEEDS_REVIEW
    # An approved photo is an explicit human policy, with its own audited application.
    # Keep this distinct from human confirmation and from historical AI suggestions.
    if (len(allocations) == 1 and explanation.decision_status == "AUTO_APPLIED"
            and (explanation.explanation_notes or "").startswith(("Foto segnaletica #", "Reconciliation run #"))
            and transaction.review_status == "ACCEPTED"):
        a = allocations[0]
        if (a.decision_source == "RULE" and a.reporting_entity_id is not None
                and a.transaction_reason_id == explanation.transaction_reason_id):
            if a.status == _COMPLETE and a.accounting_classification_id == explanation.accounting_classification_id:
                return RECONCILED
            if a.accounting_classification_id is None:
                return RECONCILED_ACCOUNTING_PENDING
    if any(a.status != _COMPLETE for a in allocations):
        return NEEDS_REVIEW

    if len(allocations) == 1:
        a = allocations[0]
        if a.reporting_entity_id is None or a.transaction_reason_id != explanation.transaction_reason_id:
            return NEEDS_REVIEW
        if a.accounting_classification_id != explanation.accounting_classification_id:
            return NEEDS_REVIEW
        if a.decision_source == "HUMAN":
            return CONFIRMED
        return NEEDS_REVIEW

    # A split (several allocations, e.g. from invoice lines) is confirmed only
    # when every line is a human, complete decision.
    if all(a.decision_source == "HUMAN" and a.reporting_entity_id is not None for a in allocations):
        return CONFIRMED
    return NEEDS_REVIEW


def statuses_for(session: Session, transactions: list["m.FinancialTransaction"]) -> dict[int, str]:
    """`status_of` for many transactions with two queries in total."""
    explanation_ids = [t.explanation_id for t in transactions if t.explanation_id is not None]
    explanations = {
        e.id: e for e in session.scalars(
            select(m.BankTransactionExplanation).where(m.BankTransactionExplanation.id.in_(explanation_ids))
        )
    } if explanation_ids else {}
    allocations: dict[int, list] = {}
    ids = [t.id for t in transactions]
    if ids:
        for a in session.scalars(
            select(m.BankTransactionAllocation)
            .where(m.BankTransactionAllocation.financial_transaction_id.in_(ids))
            .order_by(m.BankTransactionAllocation.allocation_index)
        ):
            allocations.setdefault(a.financial_transaction_id, []).append(a)
    return {
        t.id: status_of(t, explanations.get(t.explanation_id), allocations.get(t.id, []))
        for t in transactions
    }
