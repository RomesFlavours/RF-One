"""Minimal, standalone Restaurant Role (definition) management service.

`RestaurantRole` (task §15, `models.py`) is a Restaurant-configured
canonical operational role (Server, Host, Bartender, ...) — the ROLE
DEFINITION, deliberately distinct from `EmployeeAssignment` (which Employee
actually holds a role, when — the ASSIGNMENT). This module only manages
definitions; it never touches `EmployeeAssignment` and never invents or
pre-seeds a role/assignment that was not explicitly entered here.

One role list per Restaurant is reused for every purpose that needs a
Restaurant Role — Tip Distribution Rules use the SAME rows for both
"Source Role" and "Recipient Role" (two USES of a role within one rule,
never two separate registries). Lives at the top level of
`rfone_data_store`, not inside Tips or any other Domain/app package, so it
stays reusable from a future Domain-settings surface — mirrors
`legal_entity_service.py`'s own placement and shape."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m


class DuplicateRoleNameError(ValueError):
    """Raised when a Role name already exists for this Restaurant
    (`RestaurantRole`'s own `UniqueConstraint("restaurant_id", "name")`) —
    checked explicitly here so the caller gets a clear message instead of a
    raw `IntegrityError`."""


def list_roles(session: Session, restaurant_id: int) -> list[m.RestaurantRole]:
    return list(
        session.scalars(
            select(m.RestaurantRole)
            .where(m.RestaurantRole.restaurant_id == restaurant_id)
            .order_by(m.RestaurantRole.name)
        ).all()
    )


def get_role(session: Session, role_id: int) -> m.RestaurantRole | None:
    return session.get(m.RestaurantRole, role_id)


def _validate_name(
    session: Session, *, restaurant_id: int, name: str, exclude_role_id: int | None = None,
) -> str:
    name = (name or "").strip()
    if not name:
        raise ValueError("Role name is required.")
    stmt = select(m.RestaurantRole).where(
        m.RestaurantRole.restaurant_id == restaurant_id, m.RestaurantRole.name == name,
    )
    if exclude_role_id is not None:
        stmt = stmt.where(m.RestaurantRole.id != exclude_role_id)
    if session.scalars(stmt).first() is not None:
        raise DuplicateRoleNameError(f"A Role named {name!r} already exists for this Restaurant.")
    return name


def create_role(
    session: Session, *, restaurant_id: int, name: str, code: str | None = None,
    description: str | None = None, active: bool = True,
) -> m.RestaurantRole:
    name = _validate_name(session, restaurant_id=restaurant_id, name=name)
    role = m.RestaurantRole(
        restaurant_id=restaurant_id, name=name, code=(code or "").strip() or None,
        description=(description or "").strip() or None, active=active,
    )
    session.add(role)
    session.flush()
    return role


def update_role(
    session: Session, role: m.RestaurantRole, *, name: str, code: str | None = None,
    description: str | None = None, active: bool = True,
) -> m.RestaurantRole:
    name = _validate_name(
        session, restaurant_id=role.restaurant_id, name=name, exclude_role_id=role.id,
    )
    role.name = name
    role.code = (code or "").strip() or None
    role.description = (description or "").strip() or None
    role.active = active
    session.flush()
    return role
