"""Selection Feedback Intelligence — Authority / Governance foundation
service (Selection Feedback Intelligence Foundation task, §22/§23).

Configurable support for UP TO THREE authority levels — but the three
levels are entirely OPTIONAL. An Organization may configure 1, 2, or 3 (or
any number) of levels; nothing in this module invents or requires a
missing level. `SelectionGovernanceRequirement` records which action types
require which configured level, but NO approval workflow/enforcement
engine is implemented here (task's own explicit "do not implement a
complex approval UI... create the correct domain/configuration foundation
only"). An ordinary case-level override (`outcome_service.apply_outcome`,
a Selezionatore Note) is never gated by this module — only a future,
explicit Organization-Memory-modification workflow would consult it
(task §23's "case-level decisions should remain operationally easy;
changing Organization Memory should be intentionally difficult")."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m


def create_authority_level(
    session: Session, *, restaurant_id: int | None, level_key: str, level_order: int,
    label: str | None = None, assigned_holders: list | None = None,
) -> m.SelectionAuthorityLevel:
    level = m.SelectionAuthorityLevel(
        restaurant_id=restaurant_id, level_key=level_key, level_order=level_order,
        label=label, assigned_holders=assigned_holders or [],
    )
    session.add(level)
    session.flush()
    return level


def list_authority_levels(
    session: Session, *, restaurant_id: int | None = None, is_active: bool | None = None,
) -> list[m.SelectionAuthorityLevel]:
    """Returns exactly the levels an Organization has configured — zero,
    one, two, three, or more. Nothing pads this list to a fixed size."""

    stmt = select(m.SelectionAuthorityLevel)
    if restaurant_id is not None:
        stmt = stmt.where(m.SelectionAuthorityLevel.restaurant_id == restaurant_id)
    if is_active is not None:
        stmt = stmt.where(m.SelectionAuthorityLevel.is_active == is_active)
    stmt = stmt.order_by(m.SelectionAuthorityLevel.level_order)
    return list(session.scalars(stmt).all())


def get_authority_level(session: Session, authority_level_id: int) -> m.SelectionAuthorityLevel | None:
    return session.get(m.SelectionAuthorityLevel, authority_level_id)


def deactivate_authority_level(session: Session, authority_level_id: int) -> m.SelectionAuthorityLevel:
    level = session.get(m.SelectionAuthorityLevel, authority_level_id)
    if level is None:
        raise ValueError(f"No SelectionAuthorityLevel with id {authority_level_id}")
    level.is_active = False
    session.flush()
    return level


def create_governance_requirement(
    session: Session, *, restaurant_id: int | None, action_type: str,
    required_authority_level_id: int | None = None, requires_higher_approval: bool = False,
) -> m.SelectionGovernanceRequirement:
    requirement = m.SelectionGovernanceRequirement(
        restaurant_id=restaurant_id, action_type=action_type,
        required_authority_level_id=required_authority_level_id,
        requires_higher_approval=requires_higher_approval,
    )
    session.add(requirement)
    session.flush()
    return requirement


def get_governance_requirement_for_action(
    session: Session, *, restaurant_id: int | None, action_type: str,
) -> m.SelectionGovernanceRequirement | None:
    """Returns the active governance requirement for one action type, if an
    Organization has configured one — `None` means no configured
    requirement exists, which is a perfectly valid state (task §22: "if
    only one authorized Selection role exists, governance works with that
    one role" — i.e. an unconfigured action type is never blocked by an
    invented requirement)."""

    stmt = select(m.SelectionGovernanceRequirement).where(
        m.SelectionGovernanceRequirement.action_type == action_type,
        m.SelectionGovernanceRequirement.is_active.is_(True),
    )
    if restaurant_id is not None:
        stmt = stmt.where(m.SelectionGovernanceRequirement.restaurant_id == restaurant_id)
    return session.scalars(stmt).first()


def list_governance_requirements(
    session: Session, *, restaurant_id: int | None = None,
) -> list[m.SelectionGovernanceRequirement]:
    stmt = select(m.SelectionGovernanceRequirement)
    if restaurant_id is not None:
        stmt = stmt.where(m.SelectionGovernanceRequirement.restaurant_id == restaurant_id)
    stmt = stmt.order_by(m.SelectionGovernanceRequirement.id)
    return list(session.scalars(stmt).all())
