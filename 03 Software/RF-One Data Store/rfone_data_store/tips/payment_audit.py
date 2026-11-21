"""Tips payment audit trail (CLOVER_MULTISITE_001, Product Owner 2026-11-21).

The one place that writes `TipPaymentAuditEvent` rows: who (the signed-in
RF-One account, or a system identity for an automatic step) and when each
payment step happened — preparation, approval, execution of each instruction,
and every retry attempt. Called only by `payment_cycle_service`, inside the
same transaction as the step it records, so a rolled-back step leaves no
audit row and a committed step always has one.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..financial_authorization import ACCOUNT_IDENTITY_PROVIDER

SYSTEM_FALLBACK_LABEL = "RF-One System"


def _actor(session: Session, acting_identity: "m.ActingIdentity | None") -> tuple[str, int | None, str]:
    """(actor_kind, account_id, actor_label) for an Acting Identity.

    An identity bound to an RF-One account (provider `rfone-account`) is that
    account; every other identity (the SYSTEM identity of the scheduler, a
    script) — or none at all — is recorded as SYSTEM."""
    if acting_identity is not None and acting_identity.authentication_provider == ACCOUNT_IDENTITY_PROVIDER:
        try:
            account = session.get(m.RFOneAccount, int(acting_identity.external_subject_id))
        except (TypeError, ValueError):
            account = None
        if account is not None:
            label = (account.display_name or "").strip() or account.username
            return m.TIP_PAYMENT_AUDIT_ACTOR_ACCOUNT, account.id, label
    label = acting_identity.display_name if acting_identity is not None else SYSTEM_FALLBACK_LABEL
    return m.TIP_PAYMENT_AUDIT_ACTOR_SYSTEM, None, label


def record(
    session: Session, *, event: str, cycle: "m.TipPaymentCycle",
    acting_identity: "m.ActingIdentity | None", instruction: "m.TipPaymentInstruction | None" = None,
    outcome: str | None = None, detail: str | None = None, now: datetime | None = None,
) -> "m.TipPaymentAuditEvent":
    """Appends one audit row; never updates or deletes an existing one."""
    if event not in m.TIP_PAYMENT_AUDIT_EVENTS:
        raise ValueError(f"Unknown Tips payment audit event {event!r}.")
    actor_kind, account_id, label = _actor(session, acting_identity)
    row = m.TipPaymentAuditEvent(
        payment_cycle_id=cycle.id, payment_instruction_id=instruction.id if instruction is not None else None,
        event=event, actor_kind=actor_kind, account_id=account_id,
        acting_identity_id=acting_identity.id if acting_identity is not None else None,
        actor_label=label[:255], occurred_at=now or datetime.now(timezone.utc), outcome=outcome, detail=detail,
    )
    session.add(row)
    return row


def events_for_cycle(session: Session, cycle_id: int) -> list["m.TipPaymentAuditEvent"]:
    """The cycle's audit trail, oldest first (read-only)."""
    return list(session.scalars(
        select(m.TipPaymentAuditEvent).where(m.TipPaymentAuditEvent.payment_cycle_id == cycle_id)
        .order_by(m.TipPaymentAuditEvent.occurred_at, m.TipPaymentAuditEvent.id)
    ))
