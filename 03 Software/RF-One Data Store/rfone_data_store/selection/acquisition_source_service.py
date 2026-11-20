"""Acquisition Source service (Task 5D §1) — WHERE a candidate found out
about the role (Indeed, LinkedIn, Referral, Walk-In...), a restaurant-
configurable lookup list, deliberately distinct from Communication Channel
(`communication_service.py`) and from `Candidate.source` (Task 2A's résumé-
acquisition-mechanism field). Mirrors `SignalDefinition`'s minimal CRUD
shape — no versioning/snapshot mechanism, since a rename here never rewrites
the meaning of a historical decision the way an Outcome or Communication
Template edit could."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m

DEFAULT_ACQUISITION_SOURCE_NAMES = (
    "Indeed", "ZipRecruiter", "LinkedIn", "Facebook", "Instagram", "X / Twitter",
    "Company Website", "Branch Website", "Referral", "Employee Referral", "Walk-In",
    "Craigslist", "Hospitality Job Board", "School / College / Culinary School",
    "Staffing Agency / Recruiter", "QR Code", "Community Group", "Direct Outreach", "Other",
)


def seed_default_acquisition_sources(session: Session, *, restaurant_id: int | None) -> dict[str, int]:
    """Idempotent (matches by restaurant + name), mirrors every other
    `seed_default_*` helper in `industry/restaurant_templates.py`. These are
    RF-One's own example sources, not a rigid universal enum (task §1) — a
    restaurant may rename, deactivate, or add to this list freely."""

    existing = {
        d.name: d.id for d in session.scalars(
            select(m.AcquisitionSourceDefinition).where(m.AcquisitionSourceDefinition.restaurant_id == restaurant_id)
        ).all()
    }
    result: dict[str, int] = dict(existing)
    for order, name in enumerate(DEFAULT_ACQUISITION_SOURCE_NAMES):
        if name in existing:
            continue
        definition = m.AcquisitionSourceDefinition(
            restaurant_id=restaurant_id, name=name, display_order=order,
        )
        session.add(definition)
        session.flush()
        result[name] = definition.id
    return result


def create_acquisition_source(
    session: Session, *, restaurant_id: int | None, name: str, description: str | None = None,
    display_order: int | None = None,
) -> m.AcquisitionSourceDefinition:
    if display_order is None:
        from sqlalchemy import func
        display_order = session.scalar(
            select(func.count()).select_from(m.AcquisitionSourceDefinition)
            .where(m.AcquisitionSourceDefinition.restaurant_id == restaurant_id)
        )
    definition = m.AcquisitionSourceDefinition(
        restaurant_id=restaurant_id, name=name, description=description, display_order=display_order,
    )
    session.add(definition)
    session.flush()
    return definition


def list_acquisition_sources(
    session: Session, *, restaurant_id: int | None = None, active_only: bool = True,
) -> list[m.AcquisitionSourceDefinition]:
    stmt = select(m.AcquisitionSourceDefinition).order_by(m.AcquisitionSourceDefinition.display_order)
    if restaurant_id is not None:
        stmt = stmt.where(m.AcquisitionSourceDefinition.restaurant_id == restaurant_id)
    if active_only:
        stmt = stmt.where(m.AcquisitionSourceDefinition.is_active.is_(True))
    return list(session.scalars(stmt).all())


def set_application_acquisition_source(
    session: Session, application_id: int, *, acquisition_source_id: int | None, other_text: str | None = None,
) -> m.Application:
    """Task §1 — one Application may have its own Acquisition Source,
    independent of any other Application by the same person (a returning
    candidate may have found the role a second time through a different
    source)."""

    application = session.get(m.Application, application_id)
    if application is None:
        raise ValueError(f"No Application with id {application_id}")
    application.acquisition_source_id = acquisition_source_id
    application.acquisition_source_other_text = other_text
    session.flush()
    return application
