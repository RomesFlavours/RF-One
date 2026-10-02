"""The ONE definition of a transaction's reconciliation status
(BANK_RECONCILIATION_STANDARDS_001).

Exactly three statuses, each derived from persisted facts only — never
from a page label or browser state:

* CONFIRMED — a human accepted this transaction: its allocation set is
  COMPLETE and HUMAN, balances the transaction, carries no Standard
  lineage, and a single allocation matches the current decision's WHY and
  accounting destination (the decision names the WHO).
* AUTOMATIC — an approved Reconciliation Standard completed it: exactly one
  allocation, COMPLETE, decision source RULE, destination source STANDARD,
  and the CURRENT decision names the SAME Standard with the same WHY and
  destination (and a WHO).
* NEEDS REVIEW — anything else, including an automatic suggestion no human
  or Standard approved.

AUTOMATIC and CONFIRMED are exportable; NEEDS REVIEW is not. The
Reconciliation page and the Monthly Export both read this module, so the
two can never disagree about what is done.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m

NEEDS_REVIEW = "Needs review"
AUTOMATIC = "Automatic"
CONFIRMED = "Confirmed"
EXPORTABLE = (AUTOMATIC, CONFIRMED)

_COMPLETE = m.ALLOCATION_COMPLETE


def status_of(
    transaction: "m.FinancialTransaction", explanation: "m.BankTransactionExplanation | None",
    allocations: list["m.BankTransactionAllocation"],
) -> str:
    if explanation is None or explanation.occurrence_id is None or explanation.transaction_reason_id is None:
        return NEEDS_REVIEW
    if not allocations or sum(a.amount_minor for a in allocations) != transaction.amount_minor:
        return NEEDS_REVIEW
    if any(a.status != _COMPLETE for a in allocations):
        return NEEDS_REVIEW

    if len(allocations) == 1:
        a = allocations[0]
        if a.reporting_entity_id is None or a.transaction_reason_id != explanation.transaction_reason_id:
            return NEEDS_REVIEW
        if a.accounting_classification_id != explanation.accounting_classification_id:
            return NEEDS_REVIEW
        if a.decision_source == "HUMAN" and a.reconciliation_standard_id is None:
            return CONFIRMED
        if (a.decision_source == "RULE"
                and a.accounting_destination_source == m.DESTINATION_SOURCE_STANDARD
                and a.reconciliation_standard_id is not None
                and explanation.reconciliation_standard_id == a.reconciliation_standard_id
                and explanation.accounting_destination_source == m.DESTINATION_SOURCE_STANDARD):
            return AUTOMATIC
        return NEEDS_REVIEW

    # A split (several allocations, e.g. from invoice lines) is confirmed only
    # when every line is a human, Standard-free, complete decision.
    if all(a.decision_source == "HUMAN" and a.reconciliation_standard_id is None
           and a.reporting_entity_id is not None for a in allocations):
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
