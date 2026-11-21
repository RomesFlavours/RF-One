"""Linking or changing where an employee's tips are paid (CLOVER_MULTISITE_001, Product Owner 2026-11-21).

The one service behind Payment Control's "link recipient": it requires the specific authority
`financial_authorization.TIPS_MANAGE_RECIPIENTS` for the restaurant (restaurant access in Tips, an
operational site, the account's own grant), checks that the employee belongs to that restaurant
(Registry: an assignment there, or a Clover identity of one of its sites), refuses while a payment of
that employee is awaiting reconciliation, and records who changed what and when
(`TipPaymentRecipientChange`). The previous reference is deactivated, never deleted.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import financial_authorization
from .. import models as m
from . import payment_audit
from . import payment_instruction as pi_svc
from .money_lock import lock_restaurant


class RecipientChangeRefused(ValueError):
    """The recipient was not changed; the message says why."""


def employee_belongs_to_restaurant(session: Session, employee_id: int, restaurant_id: int) -> bool:
    """Registry links the person to the restaurant: an assignment there, or a Clover identity (Directory
    link) of one of its sites."""
    if session.scalar(select(m.EmployeeAssignment.id).where(
            m.EmployeeAssignment.employee_id == employee_id,
            m.EmployeeAssignment.restaurant_id == restaurant_id).limit(1)) is not None:
        return True
    locations = select(m.RestaurantLocation.location_id).where(m.RestaurantLocation.restaurant_id == restaurant_id)
    return session.scalar(select(m.EmployeeCloverLink.id).where(
        m.EmployeeCloverLink.employee_id == employee_id,
        m.EmployeeCloverLink.location_id.in_(locations)).limit(1)) is not None


def change_recipient(
    session: Session, *, account, employee_id: int, restaurant_id: int, connector_code: str,
    provider_recipient_id: str, now: datetime | None = None,
) -> "m.EmployeeExternalPaymentAccount":
    """Makes `provider_recipient_id` the employee's active recipient for `connector_code`. The caller
    resolved the provider recipient (by exact name, never created) and commits."""
    try:
        identity = financial_authorization.require(
            session, account=account, permission=financial_authorization.TIPS_MANAGE_RECIPIENTS,
            restaurant_id=restaurant_id)
    except financial_authorization.FinancialAuthorizationError as exc:
        raise RecipientChangeRefused(f"{exc} (changing a payment recipient needs its own authorization)") from exc
    if session.get(m.Employee, employee_id) is None:
        raise RecipientChangeRefused("Employee not found.")
    if not employee_belongs_to_restaurant(session, employee_id, restaurant_id):
        raise RecipientChangeRefused(
            f"Employee {employee_id} is not linked to this restaurant in Registry: the recipient was not changed.")
    lock_restaurant(session, restaurant_id)
    instruction_ids = select(m.TipPaymentInstruction.id).where(m.TipPaymentInstruction.employee_id == employee_id)
    awaiting = session.scalar(select(m.TipPaymentInstruction.id).where(
        m.TipPaymentInstruction.employee_id == employee_id,
        m.TipPaymentInstruction.status == pi_svc.STATUS_SUBMITTING).limit(1)) or session.scalar(
        select(m.TipPaymentSubmission.id).where(
            m.TipPaymentSubmission.payment_instruction_id.in_(instruction_ids),
            m.TipPaymentSubmission.state.in_(m.TIP_SUBMISSION_OPEN_STATES)).limit(1))
    if awaiting is not None:
        raise RecipientChangeRefused(
            f"A payment of employee {employee_id} is awaiting reconciliation with the provider: the recipient "
            "cannot change until its outcome is known.")
    now = now or datetime.now(timezone.utc)
    previous = session.scalars(select(m.EmployeeExternalPaymentAccount).where(
        m.EmployeeExternalPaymentAccount.employee_id == employee_id,
        m.EmployeeExternalPaymentAccount.provider == connector_code,
        m.EmployeeExternalPaymentAccount.is_active.is_(True))).all()
    for row in previous:
        row.is_active = False
    reference = m.EmployeeExternalPaymentAccount(
        employee_id=employee_id, provider=connector_code, provider_recipient_id=provider_recipient_id,
        is_active=True)
    session.add(reference)
    session.flush()
    actor_kind, account_id, _label = payment_audit._actor(session, identity)
    session.add(m.TipPaymentRecipientChange(
        employee_id=employee_id, restaurant_id=restaurant_id, provider=connector_code,
        previous_reference_id=previous[0].id if previous else None, new_reference_id=reference.id,
        provider_recipient_id=provider_recipient_id, actor_kind=actor_kind, account_id=account_id,
        acting_identity_id=identity.id, changed_at=now))
    session.flush()
    return reference
