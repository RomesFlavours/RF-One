"""Selection Requirement Framework — service layer (Task 3A). Runtime
orchestration combining Selection Core's requirement vocabulary
(`core/requirement_model.py`) with persistence (`.. models`) — the same
role `persistence.py`/`import_pipeline.py`/`normalization.py` already play
for the résumé pipeline. Flask routes (`03 Software/Selection/app.py`)
should call into this module rather than touching `.. models` directly
(task §14: "Avoid putting all business logic directly inside Flask
routes.").

Defines WHAT a restaurant is looking for. Never touches a `Candidate` row,
never matches, never scores — that boundary (task §16) is enforced simply
by this module never importing `persistence.py`'s candidate-side functions
or `core/profile.py`.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as m
from .core import requirement_model as rm


def _validate_criticality(value: str) -> None:
    if value not in rm.CRITICALITY_LEVELS:
        raise ValueError(f"Unknown criticality {value!r}; expected one of {rm.CRITICALITY_LEVELS}")


def _validate_trainability(value: str) -> None:
    if value not in rm.TRAINABILITY_LEVELS:
        raise ValueError(f"Unknown trainability {value!r}; expected one of {rm.TRAINABILITY_LEVELS}")


def _validate_assessment_stages(stages: list[str]) -> None:
    unknown = [s for s in stages if s not in rm.ASSESSMENT_STAGES]
    if unknown:
        raise ValueError(f"Unknown assessment stage(s) {unknown!r}; expected one of {rm.ASSESSMENT_STAGES}")


# ---------------------------------------------------------------------------
# Templates (task §8/§9) — RF-One-provided starting points. Read-mostly from
# the Flask app; `create_template`/`add_template_item` exist for seeding
# sample templates and for a future template-authoring UI, not because
# Task 3A requires restaurants to author templates themselves.
# ---------------------------------------------------------------------------

def list_templates(session: Session, *, intended_role: str | None = None, active_only: bool = True) -> list[m.RequirementTemplate]:
    stmt = select(m.RequirementTemplate).order_by(m.RequirementTemplate.name)
    if active_only:
        stmt = stmt.where(m.RequirementTemplate.is_active.is_(True))
    if intended_role:
        stmt = stmt.where(m.RequirementTemplate.intended_role == intended_role)
    return list(session.scalars(stmt).all())


def get_template(session: Session, template_id: int) -> m.RequirementTemplate | None:
    return session.get(m.RequirementTemplate, template_id)


def create_template(
    session: Session, *, name: str, description: str | None = None, intended_role: str | None = None,
) -> m.RequirementTemplate:
    template = m.RequirementTemplate(name=name, description=description, intended_role=intended_role)
    session.add(template)
    session.flush()
    return template


def add_template_item(
    session: Session, template_id: int, *, name: str, criticality: str, trainability: str,
    assessment_stages: list[str], description: str | None = None, category: str | None = None,
    evidence_positive: str | None = None, evidence_contrary: str | None = None,
    evidence_insufficient: str | None = None, guidance_notes: str | None = None,
    display_order: int = 0,
) -> m.RequirementTemplateItem:
    _validate_criticality(criticality)
    _validate_trainability(trainability)
    _validate_assessment_stages(assessment_stages)

    item = m.RequirementTemplateItem(
        template_id=template_id, name=name, description=description, category=category,
        criticality=criticality, trainability=trainability, assessment_stages=list(assessment_stages),
        evidence_positive=evidence_positive, evidence_contrary=evidence_contrary,
        evidence_insufficient=evidence_insufficient, guidance_notes=guidance_notes,
        display_order=display_order,
    )
    session.add(item)
    session.flush()
    return item


# ---------------------------------------------------------------------------
# Requirement Sets (task §1/§11) — restaurant-owned, independently editable.
# ---------------------------------------------------------------------------

def create_requirement_set(
    session: Session, *, restaurant_id: int | None, name: str, description: str | None = None,
    location_label: str | None = None, target_role: str | None = None,
) -> m.RequirementSet:
    """Builds a Requirement Set from scratch — no template. Requirements are
    added afterward via `add_requirement`."""

    requirement_set = m.RequirementSet(
        restaurant_id=restaurant_id, name=name, description=description,
        location_label=location_label, target_role=target_role, source_template_id=None,
    )
    session.add(requirement_set)
    session.flush()
    return requirement_set


def instantiate_requirement_set_from_template(
    session: Session, *, template_id: int, restaurant_id: int | None, name: str,
    description: str | None = None, location_label: str | None = None, target_role: str | None = None,
) -> m.RequirementSet:
    """Clones a template's items into a brand-new, independent
    `RequirementSet` (task §11: "RF-One Template -> restaurant selects
    template -> independent restaurant Requirement Set created"). Every
    field is copied by value — nothing in the new set references the
    template's own `RequirementTemplateItem` rows, so editing the restaurant
    set can never alter the shared template (task §8: "Changes to a
    restaurant's Requirement Set must NOT modify the original shared
    template."). `source_template_id` is kept only for traceability."""

    template = session.get(m.RequirementTemplate, template_id)
    if template is None:
        raise ValueError(f"No RequirementTemplate with id {template_id}")

    requirement_set = m.RequirementSet(
        restaurant_id=restaurant_id, name=name, description=description or template.description,
        location_label=location_label, target_role=target_role or template.intended_role,
        source_template_id=template.id,
    )
    session.add(requirement_set)
    session.flush()

    for item in template.items:
        if not item.is_active:
            continue
        session.add(
            m.Requirement(
                requirement_set_id=requirement_set.id, name=item.name, description=item.description,
                category=item.category, criticality=item.criticality, trainability=item.trainability,
                assessment_stages=list(item.assessment_stages or []),
                evidence_positive=item.evidence_positive, evidence_contrary=item.evidence_contrary,
                evidence_insufficient=item.evidence_insufficient, guidance_notes=item.guidance_notes,
                display_order=item.display_order,
            )
        )
    session.flush()
    return requirement_set


def list_requirement_sets(
    session: Session, *, restaurant_id: int | None = None, active_only: bool = False,
) -> list[m.RequirementSet]:
    stmt = select(m.RequirementSet).order_by(m.RequirementSet.updated_at.desc())
    if restaurant_id is not None:
        stmt = stmt.where(m.RequirementSet.restaurant_id == restaurant_id)
    if active_only:
        stmt = stmt.where(m.RequirementSet.is_active.is_(True))
    return list(session.scalars(stmt).all())


def get_requirement_set(session: Session, requirement_set_id: int) -> m.RequirementSet | None:
    return session.get(m.RequirementSet, requirement_set_id)


def get_active_requirement_set(
    session: Session, *, restaurant_id: int | None, target_role: str,
) -> m.RequirementSet | None:
    """"Retrieving the active Requirement Set for later use" (task §14).
    Simplest reasonable selection rule for when more than one active set
    matches: most recently updated wins — there is no concept yet (Task 3A)
    of a single canonical/default set beyond that."""

    stmt = (
        select(m.RequirementSet)
        .where(m.RequirementSet.target_role == target_role, m.RequirementSet.is_active.is_(True))
        .order_by(m.RequirementSet.updated_at.desc())
    )
    if restaurant_id is not None:
        stmt = stmt.where(m.RequirementSet.restaurant_id == restaurant_id)
    return session.scalars(stmt).first()


def update_requirement_set(
    session: Session, requirement_set_id: int, *, bump_version: bool = True, **fields,
) -> m.RequirementSet:
    """Updates name/description/location_label/target_role/is_active.
    `bump_version=True` (default) increments `RequirementSet.version` —
    Task 3A's practical change-safety marker (task §12); pass False only for
    a non-structural touch (there is none today, but the flag keeps the
    common case — an actual edit — the default)."""

    requirement_set = session.get(m.RequirementSet, requirement_set_id)
    if requirement_set is None:
        raise ValueError(f"No RequirementSet with id {requirement_set_id}")

    allowed = {"name", "description", "location_label", "target_role", "is_active"}
    for key, value in fields.items():
        if key not in allowed:
            raise ValueError(f"Cannot set {key!r} on a RequirementSet through update_requirement_set")
        setattr(requirement_set, key, value)

    if bump_version and fields:
        requirement_set.version += 1
    session.flush()
    return requirement_set


# ---------------------------------------------------------------------------
# Individual Requirements (task §2)
# ---------------------------------------------------------------------------

def add_requirement(
    session: Session, requirement_set_id: int, *, name: str, criticality: str, trainability: str,
    assessment_stages: list[str], description: str | None = None, category: str | None = None,
    evidence_positive: str | None = None, evidence_contrary: str | None = None,
    evidence_insufficient: str | None = None, guidance_notes: str | None = None,
    display_order: int | None = None,
) -> m.Requirement:
    _validate_criticality(criticality)
    _validate_trainability(trainability)
    _validate_assessment_stages(assessment_stages)

    requirement_set = session.get(m.RequirementSet, requirement_set_id)
    if requirement_set is None:
        raise ValueError(f"No RequirementSet with id {requirement_set_id}")

    if display_order is None:
        # A fresh COUNT query, deliberately NOT `len(requirement_set.requirements)`:
        # once that relationship has been loaded once in this session, a
        # sibling Requirement added elsewhere via a raw FK assignment (as
        # this function itself does, a few lines down) never updates the
        # already-loaded collection in memory — reading it here would
        # silently under-count and hand out a colliding `display_order` to
        # every Requirement added after the first in one session. A COUNT
        # query is always correct regardless of what has or hasn't been
        # loaded.
        display_order = session.scalar(
            select(func.count()).select_from(m.Requirement).where(m.Requirement.requirement_set_id == requirement_set_id)
        )

    requirement = m.Requirement(
        requirement_set_id=requirement_set_id, name=name, description=description, category=category,
        criticality=criticality, trainability=trainability, assessment_stages=list(assessment_stages),
        evidence_positive=evidence_positive, evidence_contrary=evidence_contrary,
        evidence_insufficient=evidence_insufficient, guidance_notes=guidance_notes,
        display_order=display_order,
    )
    session.add(requirement)
    requirement_set.version += 1
    session.flush()
    return requirement


def update_requirement(session: Session, requirement_id: int, **fields) -> m.Requirement:
    """Edits name/description/category/criticality/trainability/
    assessment_stages/evidence_*/guidance_notes/display_order/is_active on
    one Requirement — never touches `original_job_title`-equivalent Candidate
    data (there is none here; a Requirement never references a candidate).
    Always bumps the parent Requirement Set's `version`."""

    requirement = session.get(m.Requirement, requirement_id)
    if requirement is None:
        raise ValueError(f"No Requirement with id {requirement_id}")

    allowed = {
        "name", "description", "category", "criticality", "trainability", "assessment_stages",
        "evidence_positive", "evidence_contrary", "evidence_insufficient", "guidance_notes",
        "display_order", "is_active",
    }
    for key in fields:
        if key not in allowed:
            raise ValueError(f"Cannot set {key!r} on a Requirement through update_requirement")

    if "criticality" in fields:
        _validate_criticality(fields["criticality"])
    if "trainability" in fields:
        _validate_trainability(fields["trainability"])
    if "assessment_stages" in fields:
        _validate_assessment_stages(fields["assessment_stages"])
        fields["assessment_stages"] = list(fields["assessment_stages"])

    for key, value in fields.items():
        setattr(requirement, key, value)

    if fields:
        requirement.requirement_set.version += 1
    session.flush()
    return requirement


def deactivate_requirement(session: Session, requirement_id: int) -> m.Requirement:
    """Soft-deactivation only (task §12/test L) — the row, and the
    historical structure it represents, is never deleted."""
    return update_requirement(session, requirement_id, is_active=False)


def reactivate_requirement(session: Session, requirement_id: int) -> m.Requirement:
    return update_requirement(session, requirement_id, is_active=True)


# ---------------------------------------------------------------------------
# Immutable snapshots (TASK 3A-FIX) — a point-in-time copy of a
# `RequirementSet` and every `Requirement` it held, so a later Fit
# Assessment (Task 3B) can stay bound to the exact definitions used even as
# the live Requirement Set keeps evolving. Every function below either
# CREATES a new snapshot row or READS an existing one — none of them ever
# writes to a `RequirementSetSnapshot`/`RequirementSnapshotItem` that
# already exists; that immutability is the entire point of this section.
# ---------------------------------------------------------------------------

def create_requirement_set_snapshot(session: Session, requirement_set_id: int) -> m.RequirementSetSnapshot:
    """Captures the CURRENT state of a `RequirementSet` (and every
    Requirement it holds, active or not) as an immutable snapshot tied to
    its current `version`. Idempotent per version (task §3: "avoid
    unnecessary duplicates") — calling this again before the live set's
    version has advanced returns the same snapshot rather than creating a
    duplicate; the `(requirement_set_id, version)` unique constraint backs
    this up at the database level too."""

    requirement_set = session.get(m.RequirementSet, requirement_set_id)
    if requirement_set is None:
        raise ValueError(f"No RequirementSet with id {requirement_set_id}")

    existing = get_snapshot_by_version(session, requirement_set_id, requirement_set.version)
    if existing is not None:
        return existing

    snapshot = m.RequirementSetSnapshot(
        requirement_set_id=requirement_set.id, version=requirement_set.version,
        restaurant_id=requirement_set.restaurant_id, source_template_id=requirement_set.source_template_id,
        name=requirement_set.name, description=requirement_set.description,
        location_label=requirement_set.location_label, target_role=requirement_set.target_role,
        was_active=requirement_set.is_active,
    )
    session.add(snapshot)
    session.flush()

    # A fresh, explicitly-ordered query — deliberately NOT
    # `requirement_set.requirements` (see the matching comment in
    # `add_requirement`): if that relationship was already loaded earlier in
    # this session, it would not reflect a Requirement added afterward via a
    # raw FK assignment, and the snapshot would silently capture too few
    # items.
    requirements = session.scalars(
        select(m.Requirement)
        .where(m.Requirement.requirement_set_id == requirement_set_id)
        .order_by(m.Requirement.display_order)
    ).all()
    for requirement in requirements:
        session.add(
            m.RequirementSnapshotItem(
                snapshot_id=snapshot.id, source_requirement_id=requirement.id,
                name=requirement.name, description=requirement.description, category=requirement.category,
                criticality=requirement.criticality, trainability=requirement.trainability,
                assessment_stages=list(requirement.assessment_stages or []),
                evidence_positive=requirement.evidence_positive, evidence_contrary=requirement.evidence_contrary,
                evidence_insufficient=requirement.evidence_insufficient, guidance_notes=requirement.guidance_notes,
                display_order=requirement.display_order, was_active=requirement.is_active,
            )
        )
    session.flush()
    return snapshot


def get_snapshot(session: Session, snapshot_id: int) -> m.RequirementSetSnapshot | None:
    return session.get(m.RequirementSetSnapshot, snapshot_id)


def get_snapshot_by_version(
    session: Session, requirement_set_id: int, version: int,
) -> m.RequirementSetSnapshot | None:
    stmt = select(m.RequirementSetSnapshot).where(
        m.RequirementSetSnapshot.requirement_set_id == requirement_set_id,
        m.RequirementSetSnapshot.version == version,
    )
    return session.scalars(stmt).first()


def get_latest_snapshot(session: Session, requirement_set_id: int) -> m.RequirementSetSnapshot | None:
    stmt = (
        select(m.RequirementSetSnapshot)
        .where(m.RequirementSetSnapshot.requirement_set_id == requirement_set_id)
        .order_by(m.RequirementSetSnapshot.version.desc())
    )
    return session.scalars(stmt).first()


def list_snapshots(session: Session, requirement_set_id: int) -> list[m.RequirementSetSnapshot]:
    stmt = (
        select(m.RequirementSetSnapshot)
        .where(m.RequirementSetSnapshot.requirement_set_id == requirement_set_id)
        .order_by(m.RequirementSetSnapshot.version.desc())
    )
    return list(session.scalars(stmt).all())


def serialize_requirement_set_snapshot(snapshot: m.RequirementSetSnapshot) -> dict:
    """Deterministic plain-dict representation of one immutable snapshot
    (task §7) — field order is fixed and `requirements` is always explicitly
    sorted by `display_order` here (never relying on however the ORM
    relationship happens to have loaded it), so the same snapshot always
    serializes identically. Suitable for auditing/testing/a future Fit
    Assessment to persist alongside its own record, or plain debugging."""

    return {
        "snapshot_id": snapshot.id,
        "requirement_set_id": snapshot.requirement_set_id,
        "version": snapshot.version,
        "restaurant_id": snapshot.restaurant_id,
        "source_template_id": snapshot.source_template_id,
        "name": snapshot.name,
        "description": snapshot.description,
        "location_label": snapshot.location_label,
        "target_role": snapshot.target_role,
        "was_active": snapshot.was_active,
        "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
        "requirements": [
            {
                "source_requirement_id": item.source_requirement_id,
                "name": item.name,
                "description": item.description,
                "category": item.category,
                "criticality": item.criticality,
                "trainability": item.trainability,
                "assessment_stages": list(item.assessment_stages or []),
                "evidence_positive": item.evidence_positive,
                "evidence_contrary": item.evidence_contrary,
                "evidence_insufficient": item.evidence_insufficient,
                "guidance_notes": item.guidance_notes,
                "display_order": item.display_order,
                "was_active": item.was_active,
            }
            for item in sorted(snapshot.items, key=lambda i: i.display_order)
        ],
    }
