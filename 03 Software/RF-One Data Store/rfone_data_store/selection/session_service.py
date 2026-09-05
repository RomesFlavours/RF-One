"""Selection Session — service layer (Task 5C). The operational container
for selecting candidates for ONE role (`core/session_model.py`). Routes
should call into this module rather than touching `.. models` directly —
the same "routes are thin" discipline every other Selection service
follows.

A Session is NOT "operationally usable" merely because `status == ACTIVE`
(task §13/§24 — a Session must go through explicit Rule Set confirmation
first, every time, even when it starts from a previously-used Rule Set).
`assert_operational()` is the one gate every operational entry point
(`ownership_service.take_in_charge`, and any route performing a
substantive Application mutation) must call.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import application_service as app_svc
from .core import session_model as sesm

NOTE_CONTEXT_SESSION_NOTE = "SESSION_NOTE"
NOTE_CONTEXT_RULE_SET_CONFIRMATION = "RULE_SET_CONFIRMATION"
NOTE_CONTEXT_RULE_CHANGE = "RULE_CHANGE"


# ---------------------------------------------------------------------------
# Creation / retrieval
# ---------------------------------------------------------------------------

def create_session(
    session: Session, *, restaurant_id: int | None, name: str, target_role: str,
    location_label: str | None = None, start_date: datetime | None = None,
    planned_end_date: datetime | None = None, created_by: str | None = None,
    carry_forward_from_session_id: int | None = None,
) -> m.SelectionSession:
    """Creates a single-role Session (task §1/§2) in DRAFT status, and
    immediately builds its version-1 Rule Set — either carried forward from
    an explicitly given prior Session (task §23: "start from the COMPLETE
    CURRENT Rule Set that resulted from prior Session learning"), or, absent
    that, auto-detected as the most recent prior Session for the SAME
    restaurant/role, or else an empty envelope the Selezionatore populates
    during Rule Review. The new version is never pre-confirmed (task §24 —
    confirmation is always a fresh, explicit act)."""

    from . import rule_set_service as rs_svc

    selection_session = m.SelectionSession(
        name=name, restaurant_id=restaurant_id, location_label=location_label, target_role=target_role,
        start_date=start_date, planned_end_date=planned_end_date, status=sesm.DRAFT, created_by=created_by,
    )
    session.add(selection_session)
    session.flush()

    seed_id = carry_forward_from_session_id
    if seed_id is None:
        prior = find_latest_prior_session(
            session, restaurant_id=restaurant_id, target_role=target_role, exclude_session_id=selection_session.id,
        )
        seed_id = prior.current_rule_set_version_id if prior is not None else None

    rs_svc.create_initial_version(session, selection_session.id, seed_from_version_id=seed_id, created_by=created_by)
    session.flush()
    return selection_session


def get_session(session: Session, session_id: int) -> m.SelectionSession | None:
    return session.get(m.SelectionSession, session_id)


def list_sessions(
    session: Session, *, restaurant_id: int | None = None, target_role: str | None = None,
    status: str | None = None,
) -> list[m.SelectionSession]:
    stmt = select(m.SelectionSession).order_by(m.SelectionSession.created_at.desc())
    if restaurant_id is not None:
        stmt = stmt.where(m.SelectionSession.restaurant_id == restaurant_id)
    if target_role is not None:
        stmt = stmt.where(m.SelectionSession.target_role == target_role)
    if status is not None:
        stmt = stmt.where(m.SelectionSession.status == status)
    return list(session.scalars(stmt).all())


def find_latest_prior_session(
    session: Session, *, restaurant_id: int | None, target_role: str, exclude_session_id: int | None = None,
) -> m.SelectionSession | None:
    """Task §23 — the most recent OTHER Session for the same restaurant and
    role, preferring one whose current Rule Set version was actually
    confirmed (a Session abandoned before confirmation has nothing
    meaningful to hand down)."""

    stmt = select(m.SelectionSession).where(m.SelectionSession.target_role == target_role)
    if restaurant_id is not None:
        stmt = stmt.where(m.SelectionSession.restaurant_id == restaurant_id)
    if exclude_session_id is not None:
        stmt = stmt.where(m.SelectionSession.id != exclude_session_id)
    stmt = stmt.order_by(m.SelectionSession.id.desc())
    candidates = list(session.scalars(stmt).all())
    for candidate in candidates:
        if candidate.current_rule_set_version_id is not None:
            version = session.get(m.SelectionRuleSetVersion, candidate.current_rule_set_version_id)
            if version is not None and version.confirmed_at is not None:
                return candidate
    return candidates[0] if candidates else None


def update_session(session: Session, session_id: int, **fields) -> m.SelectionSession:
    selection_session = session.get(m.SelectionSession, session_id)
    if selection_session is None:
        raise ValueError(f"No SelectionSession with id {session_id}")

    allowed = {
        "name", "location_label", "start_date", "planned_end_date", "actual_close_date", "notes", "created_by",
    }
    for key in fields:
        if key not in allowed:
            raise ValueError(f"Cannot set {key!r} on a SelectionSession through update_session")
    for key, value in fields.items():
        setattr(selection_session, key, value)
    session.flush()
    return selection_session


def set_session_status(session: Session, session_id: int, new_status: str) -> m.SelectionSession:
    """Task §3 — a simple lifecycle, deliberately not a strict state
    machine (mirrors `stage_service.set_stage`'s own "total freedom");
    reaching ACTIVE the FIRST time is normally a side effect of
    `rule_set_service.confirm_rule_set_version` (task §13), not this
    function — this exists for the remaining transitions (PAUSED, CLOSED,
    back to RULES_REVIEW to prepare a rule change, etc.)."""

    sesm.validate_session_status(new_status)
    selection_session = session.get(m.SelectionSession, session_id)
    if selection_session is None:
        raise ValueError(f"No SelectionSession with id {session_id}")
    selection_session.status = new_status
    if new_status == sesm.CLOSED and selection_session.actual_close_date is None:
        selection_session.actual_close_date = datetime.utcnow()
    session.flush()
    return selection_session


# ---------------------------------------------------------------------------
# Operational gate (task §13/§24)
# ---------------------------------------------------------------------------

def is_confirmed(session: Session, session_id: int) -> bool:
    selection_session = session.get(m.SelectionSession, session_id)
    if selection_session is None or selection_session.current_rule_set_version_id is None:
        return False
    version = session.get(m.SelectionRuleSetVersion, selection_session.current_rule_set_version_id)
    return version is not None and version.confirmed_at is not None


def assert_operational(session: Session, session_id: int) -> m.SelectionSession:
    """The ONE gate every operational Selection action on a Session's
    Applications must pass (task §13: "the Rule Set for that Session must
    be explicitly reviewed and confirmed" before "take Application in
    charge... change candidate Outcome... Primary Screening decisions...
    make candidate decisions")."""

    selection_session = session.get(m.SelectionSession, session_id)
    if selection_session is None:
        raise ValueError(f"No SelectionSession with id {session_id}")
    if selection_session.status != sesm.ACTIVE or not is_confirmed(session, session_id):
        raise ValueError(
            f"Selection Session '{selection_session.name}' is not yet operational — its Rule Set must be "
            "explicitly reviewed and confirmed before candidate operational work can begin."
        )
    return selection_session


# ---------------------------------------------------------------------------
# Selezionatore assignment (task §4/§5)
# ---------------------------------------------------------------------------

def assign_selezionatore(
    session: Session, session_id: int, *, acting_identity_id: int, authority_level_id: int | None = None,
) -> m.SelectionSessionAssignment:
    """Assigns (or reactivates/re-configures) one Selezionatore on a
    Session, identified by a stable `ActingIdentity` (GLOBAL_INTEGRITY_FIX_002
    / C-1 — never a freely-typed name). `selezionatore_name` is still stored,
    but only ever DERIVED from `acting_identity.display_name` — it is display
    text, never independently authoritative. Never forces a single "primary
    selector" (task §4) — a Session may have any number of peer or
    hierarchically-related assignments."""

    identity = session.get(m.ActingIdentity, acting_identity_id)
    if identity is None or not identity.is_active:
        raise ValueError("Assigning a Selezionatore requires a valid, active Acting Identity.")

    existing = session.scalars(
        select(m.SelectionSessionAssignment).where(
            m.SelectionSessionAssignment.session_id == session_id,
            m.SelectionSessionAssignment.acting_identity_id == acting_identity_id,
        )
    ).first()
    if existing is not None:
        existing.is_active = True
        existing.deactivated_at = None
        existing.authority_level_id = authority_level_id
        existing.selezionatore_name = identity.display_name
        session.flush()
        return existing

    assignment = m.SelectionSessionAssignment(
        session_id=session_id, selezionatore_name=identity.display_name, acting_identity_id=identity.id,
        authority_level_id=authority_level_id,
    )
    session.add(assignment)
    session.flush()
    return assignment


def deactivate_assignment(session: Session, assignment_id: int) -> m.SelectionSessionAssignment:
    assignment = session.get(m.SelectionSessionAssignment, assignment_id)
    if assignment is None:
        raise ValueError(f"No SelectionSessionAssignment with id {assignment_id}")
    assignment.is_active = False
    assignment.deactivated_at = datetime.utcnow()
    session.flush()
    return assignment


def list_assignments(
    session: Session, session_id: int, *, active_only: bool = False,
) -> list[m.SelectionSessionAssignment]:
    stmt = select(m.SelectionSessionAssignment).where(m.SelectionSessionAssignment.session_id == session_id)
    if active_only:
        stmt = stmt.where(m.SelectionSessionAssignment.is_active.is_(True))
    stmt = stmt.order_by(m.SelectionSessionAssignment.id)
    return list(session.scalars(stmt).all())


def get_assignment_for_selezionatore(
    session: Session, session_id: int, selezionatore_name: str,
) -> m.SelectionSessionAssignment | None:
    """Legacy, display-text-only lookup — kept for historical rows created
    before GLOBAL_INTEGRITY_FIX_002 that never received an
    `acting_identity_id`. Never used for an authority/authorization
    comparison (see `get_assignment_for_identity` for that) — a name is
    ambiguous (two different identities could share a display name) in a
    way an id is not."""

    stmt = select(m.SelectionSessionAssignment).where(
        m.SelectionSessionAssignment.session_id == session_id,
        m.SelectionSessionAssignment.selezionatore_name == selezionatore_name,
        m.SelectionSessionAssignment.is_active.is_(True),
    )
    return session.scalars(stmt).first()


def get_assignment_for_identity(
    session: Session, session_id: int, acting_identity_id: int | None,
) -> m.SelectionSessionAssignment | None:
    """GLOBAL_INTEGRITY_FIX_002 / C-1/I-4 — the authoritative, identity-based
    lookup `authority_service`'s authority-order comparison uses; the ONLY
    correct way to find "this Acting Identity's assignment in this Session"
    once an assignment carries an `acting_identity_id`."""

    if acting_identity_id is None:
        return None
    stmt = select(m.SelectionSessionAssignment).where(
        m.SelectionSessionAssignment.session_id == session_id,
        m.SelectionSessionAssignment.acting_identity_id == acting_identity_id,
        m.SelectionSessionAssignment.is_active.is_(True),
    )
    return session.scalars(stmt).first()


# ---------------------------------------------------------------------------
# Application <-> Session linkage (task §22/§26)
# ---------------------------------------------------------------------------

def link_application_to_session(session: Session, application_id: int, session_id: int) -> m.Application:
    """Links an Application to a Session and stamps it with the Session's
    THEN-current Rule Set version (task §22) — the exact version this
    Application is traceable to from now on, never silently rewritten by a
    later Rule Change (see `rule_change_service.py`). An Application
    already linked to a DIFFERENT Session is refused (never silently moved
    between Sessions); linking to the SAME Session again is a no-op."""

    application = session.get(m.Application, application_id)
    if application is None:
        raise ValueError(f"No Application with id {application_id}")
    if application.session_id is not None and application.session_id != session_id:
        raise ValueError(
            f"Application {application_id} is already linked to a different Selection Session "
            f"({application.session_id})."
        )
    selection_session = session.get(m.SelectionSession, session_id)
    if selection_session is None:
        raise ValueError(f"No SelectionSession with id {session_id}")

    application.session_id = session_id
    application.rule_set_version_id = selection_session.current_rule_set_version_id
    session.flush()
    return application


def list_applications_for_session(session: Session, session_id: int) -> list[m.Application]:
    stmt = select(m.Application).where(m.Application.session_id == session_id).order_by(m.Application.id)
    return list(session.scalars(stmt).all())


# ---------------------------------------------------------------------------
# Notes (task §33) — reuses the existing unified ApplicationNote table
# (widened in this task to also carry `session_id`), never a new table.
# ---------------------------------------------------------------------------

def add_session_note(
    session: Session, session_id: int, note_text: str, *, context_type: str | None = None,
    context_id: int | None = None,
) -> m.ApplicationNote:
    selection_session = session.get(m.SelectionSession, session_id)
    if selection_session is None:
        raise ValueError(f"No SelectionSession with id {session_id}")
    note = m.ApplicationNote(
        session_id=session_id, application_id=None, note_text=note_text, context_type=context_type,
        context_id=context_id,
    )
    session.add(note)
    session.flush()
    return note


def list_session_notes(session: Session, session_id: int) -> list[m.ApplicationNote]:
    stmt = (
        select(m.ApplicationNote)
        .where(m.ApplicationNote.session_id == session_id)
        .order_by(m.ApplicationNote.id.desc())
    )
    return list(session.scalars(stmt).all())
