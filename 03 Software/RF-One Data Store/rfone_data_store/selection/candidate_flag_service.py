"""Candidate Flag service (Task 5A §16-§19/§29). A persistent, PERSON-level
marker (never Application-level, since its whole purpose is surfacing on a
LATER Application by the same person) that never causes an automatic
rejection — `operational_effect` caps out at requiring Selezionatore
attention (task §18/§28). History is preserved by never deleting a flag
row; `is_active`/`expires_at` describe current state only (task §29).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import application_service as app_svc
from .core import outcome_model as om

NOTE_CONTEXT_CANDIDATE_FLAG = "CANDIDATE_FLAG"


def create_flag(
    session: Session, *, person_id: int, restaurant_id: int | None, name: str, description: str | None = None,
    originating_application_id: int | None = None, originating_outcome_decision_id: int | None = None,
    reason: str | None = None, scope: str = om.DEFAULT_FLAG_SCOPE, role_scope: str | None = None,
    location_scope: str | None = None, operational_effect: str = om.DEFAULT_FLAG_OPERATIONAL_EFFECT,
    note: str | None = None, expires_after_days: int | None = None, expires_at: datetime | None = None,
    created_by: str | None = None,
) -> m.CandidateFlag:
    om.validate_flag_scope(scope)
    om.validate_flag_operational_effect(operational_effect)
    person = session.get(m.CandidatePerson, person_id)
    if person is None:
        raise ValueError(f"No CandidatePerson with id {person_id}")

    if expires_at is None and expires_after_days is not None:
        expires_at = datetime.utcnow() + timedelta(days=expires_after_days)

    flag = m.CandidateFlag(
        person_id=person_id, restaurant_id=restaurant_id, name=name, description=description,
        originating_application_id=originating_application_id,
        originating_outcome_decision_id=originating_outcome_decision_id, reason=reason, scope=scope,
        role_scope=role_scope, location_scope=location_scope, operational_effect=operational_effect, note=note,
        expires_at=expires_at, created_by=created_by,
    )
    session.add(flag)
    session.flush()

    # Task 5A §20/§21 — when a Flag originates from a specific Application,
    # also mirror its note into that Application's unified Notes History
    # (reusing ApplicationNote, never a second/duplicate notes system).
    if note and originating_application_id is not None:
        app_svc.add_note(
            session, originating_application_id, note, context_type=NOTE_CONTEXT_CANDIDATE_FLAG, context_id=flag.id,
        )

    return flag


def deactivate_flag(session: Session, flag_id: int) -> m.CandidateFlag:
    """Task §29 — the row is kept (history), only its CURRENT active state
    changes."""

    flag = session.get(m.CandidateFlag, flag_id)
    if flag is None:
        raise ValueError(f"No CandidateFlag with id {flag_id}")
    flag.is_active = False
    session.flush()
    return flag


def reactivate_flag(session: Session, flag_id: int) -> m.CandidateFlag:
    flag = session.get(m.CandidateFlag, flag_id)
    if flag is None:
        raise ValueError(f"No CandidateFlag with id {flag_id}")
    flag.is_active = True
    session.flush()
    return flag


def is_flag_currently_effective(flag: m.CandidateFlag, *, as_of: datetime | None = None) -> bool:
    """Task §17/§19 — active AND not expired. An expired flag remains in
    history (never deleted) but produces no active effect."""

    as_of = as_of or datetime.utcnow()
    if not flag.is_active:
        return False
    if flag.expires_at is not None and flag.expires_at <= as_of:
        return False
    return True


def list_flags_for_person(session: Session, person_id: int, *, active_only: bool = False) -> list[m.CandidateFlag]:
    """Every Flag ever recorded for this person, most recent first — the
    full history (task §29). `active_only` additionally filters to
    currently-effective ones (active AND not expired)."""

    stmt = select(m.CandidateFlag).where(m.CandidateFlag.person_id == person_id).order_by(m.CandidateFlag.id.desc())
    flags = list(session.scalars(stmt).all())
    if active_only:
        flags = [f for f in flags if is_flag_currently_effective(f)]
    return flags


def list_active_flags_for_application(session: Session, application_id: int) -> list[m.CandidateFlag]:
    """Task §19 — active, applicable Candidate Flags to surface on THIS
    Application: same person, currently effective (active + not expired),
    and scope-compatible (a ROLE_SPECIFIC flag only applies when its
    `role_scope` matches this Application's `target_role`; a
    LOCATION_SPECIFIC flag is included regardless of location match here
    since Selection does not yet carry a location on the Application itself
    — shown for Selezionatore judgment rather than silently hidden).
    Restaurant-scoped: a flag recorded at a DIFFERENT restaurant than this
    Application never surfaces here."""

    application = session.get(m.Application, application_id)
    if application is None:
        return []

    candidates = list_flags_for_person(session, application.person_id, active_only=True)
    applicable = []
    for flag in candidates:
        if flag.restaurant_id is not None and application.restaurant_id is not None and flag.restaurant_id != application.restaurant_id:
            continue
        if flag.scope == om.FLAG_ROLE_SPECIFIC and flag.role_scope and application.target_role:
            if flag.role_scope != application.target_role:
                continue
        applicable.append(flag)
    return applicable
