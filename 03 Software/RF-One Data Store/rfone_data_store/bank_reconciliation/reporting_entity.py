"""Reporting entities and the perimeter they consolidate into
(BANK_ECONOMIC_ALLOCATION_FOUNDATION_001).

A `ReportingEntity` answers FOR WHOM an economic result is reported. It is
not the same question as which LLC signed the contract, and it is not the
same question as which instrument paid.

Two kinds, and the boundary between them is the reason this module exists:

* `LEGAL`   — stands for exactly one real `LegalEntity`. Its P&L is that
              LLC's P&L.
* `VIRTUAL` — a management/reporting entity that is NOT a legal
              organization. It gets a real management P&L and belongs to
              the reporting perimeter, but it is not an LLC, it never
              becomes one, and no `LegalEntity` row is ever created for it.

`LegalEntity` keeps its single, narrow meaning: a genuine juridical entity.
Nothing in this module writes to it, and the one function that could be
mistaken for doing so — `create_virtual_entity` — is the one that provably
does not.

NOTHING IS SEEDED anywhere in this module. Which entities and which
perimeter RF-One actually has is a Product Owner configuration decision.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m


# ---------------------------------------------------------------------------
# Reporting group — the consolidation perimeter
# ---------------------------------------------------------------------------


def create_reporting_group(
    session: Session, *, code: str, name: str, description: str | None = None,
) -> "m.ReportingGroup":
    """Create a consolidation perimeter. Deliberately not called a
    Corporate — see `ReportingGroup`'s own docstring for why an approved
    Core concept is not being quietly redefined here."""
    code = (code or "").strip()
    name = (name or "").strip()
    if not code:
        raise ValueError("A reporting group needs a stable code.")
    if not name:
        raise ValueError("A reporting group needs a name.")
    if session.scalar(select(m.ReportingGroup).where(m.ReportingGroup.code == code)) is not None:
        raise ValueError(f"A reporting group with code {code!r} already exists.")

    group = m.ReportingGroup(code=code, name=name, description=description, status="ACTIVE")
    session.add(group)
    session.flush()
    return group


def entities_in_group(session: Session, *, reporting_group_id: int) -> list["m.ReportingEntity"]:
    """Every entity consolidating into this perimeter — any number of
    them, legal and virtual alike."""
    return list(
        session.scalars(
            select(m.ReportingEntity)
            .where(m.ReportingEntity.reporting_group_id == reporting_group_id)
            .order_by(m.ReportingEntity.code)
        )
    )


# ---------------------------------------------------------------------------
# Reporting entities
# ---------------------------------------------------------------------------


def create_legal_entity_reporting_entity(
    session: Session,
    *,
    code: str,
    name: str,
    legal_entity_id: int,
    reporting_group_id: int | None = None,
    description: str | None = None,
) -> "m.ReportingEntity":
    """A reporting entity that IS a real LLC.

    `legal_entity_id` is required and must name an existing `LegalEntity`.
    A LEGAL reporting entity with no Legal Entity is refused here and
    would be refused by the database anyway; a second one pointing at an
    LLC that is already represented is refused too, because a consolidated
    total must never contain the same LLC twice."""
    code = (code or "").strip()
    name = (name or "").strip()
    if not code or not name:
        raise ValueError("A reporting entity needs both a stable code and a name.")
    if legal_entity_id is None:
        raise ValueError(
            "A LEGAL reporting entity must name exactly one real Legal Entity. "
            "Create a VIRTUAL reporting entity instead if there is no LLC."
        )

    legal_entity = session.get(m.LegalEntity, legal_entity_id)
    if legal_entity is None:
        raise ValueError(f"Legal Entity {legal_entity_id} does not exist.")

    _assert_code_available(session, code)

    already = session.scalar(
        select(m.ReportingEntity).where(m.ReportingEntity.legal_entity_id == legal_entity_id)
    )
    if already is not None:
        raise ValueError(
            f"Legal Entity {legal_entity.legal_name!r} is already represented by reporting "
            f"entity {already.code!r}. One Legal Entity has exactly one LEGAL reporting entity."
        )

    _assert_group_exists(session, reporting_group_id)

    entity = m.ReportingEntity(
        code=code,
        name=name,
        entity_type=m.REPORTING_ENTITY_LEGAL,
        legal_entity_id=legal_entity_id,
        reporting_group_id=reporting_group_id,
        description=description,
        status="ACTIVE",
    )
    session.add(entity)
    session.flush()
    return entity


def create_virtual_entity(
    session: Session,
    *,
    code: str,
    name: str,
    reporting_group_id: int | None = None,
    description: str | None = None,
) -> "m.ReportingEntity":
    """A management/reporting entity that is NOT a legal organization.

    This function creates ONE row, in `reporting_entities`. It does not
    create a `LegalEntity`, does not copy one, and cannot be given one:
    `legal_entity_id` stays NULL and the database's own CHECK constraint
    keeps it that way. A virtual entity that quietly became an LLC would
    corrupt every legal report RF-One produces, so the schema refuses it
    rather than trusting this code to remember."""
    code = (code or "").strip()
    name = (name or "").strip()
    if not code or not name:
        raise ValueError("A reporting entity needs both a stable code and a name.")

    _assert_code_available(session, code)
    _assert_group_exists(session, reporting_group_id)

    entity = m.ReportingEntity(
        code=code,
        name=name,
        entity_type=m.REPORTING_ENTITY_VIRTUAL,
        legal_entity_id=None,
        reporting_group_id=reporting_group_id,
        description=description,
        status="ACTIVE",
    )
    session.add(entity)
    session.flush()
    return entity


def assign_to_group(
    session: Session, *, reporting_entity_id: int, reporting_group_id: int | None,
) -> "m.ReportingEntity":
    """Move an entity into a perimeter, or out of every perimeter
    (`None`). Changing the perimeter changes future consolidation only —
    no allocation is rewritten, because an allocation records who bore a
    cost, not how the group was organized that day."""
    entity = session.get(m.ReportingEntity, reporting_entity_id)
    if entity is None:
        raise ValueError(f"Reporting Entity {reporting_entity_id} does not exist.")
    _assert_group_exists(session, reporting_group_id)
    entity.reporting_group_id = reporting_group_id
    session.flush()
    return entity


def reporting_entity_for_legal_entity(
    session: Session, *, legal_entity_id: int,
) -> "m.ReportingEntity | None":
    """The LEGAL reporting entity representing this LLC, if one has been
    configured. Returns None rather than creating one on demand — an
    unconfigured entity must be visibly unconfigured."""
    return session.scalar(
        select(m.ReportingEntity).where(m.ReportingEntity.legal_entity_id == legal_entity_id)
    )


def _assert_code_available(session: Session, code: str) -> None:
    if (
        session.scalar(select(m.ReportingEntity).where(m.ReportingEntity.code == code))
        is not None
    ):
        raise ValueError(f"A reporting entity with code {code!r} already exists.")


def _assert_group_exists(session: Session, reporting_group_id: int | None) -> None:
    if reporting_group_id is None:
        return
    if session.get(m.ReportingGroup, reporting_group_id) is None:
        raise ValueError(f"Reporting Group {reporting_group_id} does not exist.")
