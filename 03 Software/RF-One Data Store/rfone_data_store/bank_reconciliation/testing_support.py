"""Test support for BANK_RECONCILIATION_STANDARDS_001 — not used by the
application.

Since that task a WHO/WHY decision alone leaves a transaction NEEDS REVIEW;
the Monthly Export runs only when every row is CONFIRMED or AUTOMATIC. Tests
written before it reach "fully resolved" through decisions alone, so they
call `confirm_decided_rows` at that point: it performs, for each decided row,
exactly the row confirmation the Reconciliation page performs — one HUMAN,
COMPLETE allocation for the whole amount carrying the decision's WHY and
destination — without appending any new decision row (so decision-history
assertions stay valid)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import economic_allocation
from . import export
from . import recognition
from . import reporting_entity


def confirm_decided_rows(session: Session, *, year: int, month: int) -> int:
    entity = session.scalar(select(m.ReportingEntity).where(m.ReportingEntity.status == "ACTIVE")
                            .order_by(m.ReportingEntity.id))
    if entity is None:
        entity = reporting_entity.create_virtual_entity(session, code="RE_TEST_CONFIRMATION", name="Test entity")
    confirmed = 0
    for transaction in export.in_scope_transactions(session, year, month):
        decision = recognition.get_current_explanation(session, financial_transaction_id=transaction.id)
        if (decision is None or decision.occurrence_id is None or decision.transaction_reason_id is None
                or decision.accounting_classification_id is None
                or decision.decision_status not in recognition.RESOLVED_DECISION_STATUSES):
            continue
        if economic_allocation.get_allocations(session, financial_transaction_id=transaction.id):
            continue
        economic_allocation.set_allocations(
            session, financial_transaction_id=transaction.id,
            specs=[economic_allocation.AllocationSpec(
                amount_minor=transaction.amount_minor, reporting_entity_id=entity.id,
                transaction_reason_id=decision.transaction_reason_id,
                accounting_classification_id=decision.accounting_classification_id,
                status=economic_allocation.COMPLETE, decision_source="HUMAN",
            )],
        )
        confirmed += 1
    session.flush()
    return confirmed
