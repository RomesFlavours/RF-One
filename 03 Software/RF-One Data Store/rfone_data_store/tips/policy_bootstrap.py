"""Tip Policy configuration bootstrap (TASK_TIPS_004).

Generic, reusable infrastructure for idempotently configuring a Location-
specific `TipPolicy` and its `TipPolicyComponent` rows. This module knows
nothing about any specific Restaurant's approved percentages, roles, or
behaviors — those live only in the caller (e.g. `configure_rome_flavours_
tip_policy.py`), never here and never in `rfone_data_store/tips/engine.py`.
Mirrors the existing `rfone_data_store/profile/bootstrap.py`
(`bootstrap_restaurant_profile`) dry-run/persist pattern.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m

MODE_DRY_RUN = "DRY_RUN"
MODE_PERSIST = "PERSIST"


@dataclass
class ComponentSpec:
    sequence: int
    recipient_basis: str
    share_percentage: Decimal
    split_method: str
    no_eligible_behavior: str
    restaurant_role_id: int | None = None


@dataclass
class PolicyBootstrapResult:
    policy_id: int | None
    created: bool
    component_ids: list[int] = field(default_factory=list)


def earliest_tip_evidence_at(session: Session, *, location_id: int) -> datetime | None:
    """The earliest `Payment.created_at` for which a real `PaymentTip` (with
    a non-null amount) exists at this Location — the earliest instant a Tip
    Policy covering this Location could legitimately apply to any real
    evidence. Returns `None` when no such evidence exists yet (e.g. a
    Location with no recorded Tips at all)."""
    return session.scalar(
        select(m.Payment.created_at)
        .join(m.Order, m.Order.id == m.Payment.order_id)
        .join(m.PaymentTip, m.PaymentTip.payment_id == m.Payment.id)
        .where(
            m.Order.location_id == location_id,
            m.PaymentTip.amount.is_not(None),
        )
        .order_by(m.Payment.created_at.asc())
        .limit(1)
    )


def configure_location_tip_policy(
    session: Session,
    *,
    restaurant_id: int,
    location_id: int,
    name: str,
    valid_from: datetime,
    components: list[ComponentSpec],
    mode: str = MODE_DRY_RUN,
) -> PolicyBootstrapResult:
    """Idempotently configures ONE Location-specific `TipPolicy` + its
    components.

    Idempotent by `(restaurant_id, location_id, name, valid_from)`:
    re-running with identical inputs reuses the existing policy unchanged —
    never a duplicate. A genuinely different configuration (a different
    `valid_from`, a different component structure) is always a NEW policy
    row; this function never mutates an existing `TipPolicy`'s components in
    place, matching this Domain's historical-integrity convention
    (`Tip Policy.md`: "history is never silently recalculated"). Correcting
    an already-active policy is a Product Owner decision requiring an
    explicit new policy version, not something this bootstrap does
    automatically.

    `mode=DRY_RUN` (default) never writes anything, matching every other
    bootstrap/import entry point in this repository.
    """
    existing = session.scalars(
        select(m.TipPolicy).where(
            m.TipPolicy.restaurant_id == restaurant_id,
            m.TipPolicy.location_id == location_id,
            m.TipPolicy.name == name,
            m.TipPolicy.valid_from == valid_from,
        )
    ).first()
    if existing is not None:
        component_ids = list(
            session.scalars(
                select(m.TipPolicyComponent.id).where(m.TipPolicyComponent.tip_policy_id == existing.id)
            ).all()
        )
        return PolicyBootstrapResult(policy_id=existing.id, created=False, component_ids=component_ids)

    if mode == MODE_DRY_RUN:
        return PolicyBootstrapResult(policy_id=None, created=True, component_ids=[])

    policy = m.TipPolicy(
        restaurant_id=restaurant_id, location_id=location_id, name=name,
        status="ACTIVE", valid_from=valid_from,
    )
    session.add(policy)
    session.flush()

    component_ids: list[int] = []
    for spec in components:
        component = m.TipPolicyComponent(
            tip_policy_id=policy.id, sequence=spec.sequence, recipient_basis=spec.recipient_basis,
            restaurant_role_id=spec.restaurant_role_id, share_percentage=spec.share_percentage,
            split_method=spec.split_method, no_eligible_behavior=spec.no_eligible_behavior,
        )
        session.add(component)
        session.flush()
        component_ids.append(component.id)

    return PolicyBootstrapResult(policy_id=policy.id, created=True, component_ids=component_ids)
