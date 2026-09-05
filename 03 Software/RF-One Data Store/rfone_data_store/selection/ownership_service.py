"""Application Ownership — service layer (Task 5C §6-§10). ONE active
operational owner per Application at a time (task §10 — never competing
concurrent owners); non-owner Selezionatori assigned to the same Session
remain read-only (task §8) until ownership is explicitly transferred
(task §9). Authority for reassignment reuses `SelectionAuthorityLevel`
(`governance_service.py`) rather than a parallel permission system
(task §32).

`assert_can_operate()` is the ONE reusable guard a route should call before
performing a substantive Application mutation on a Session-linked
Application (task §8's own explicit list: change Outcome, override a
decision, edit Screening evaluation, edit Trainable Gap, modify Application
workflow). It is a no-op (always permits) for an Application that does not
belong to a Session, or that belongs to a Session but has no claimed owner
yet — Task 5C is additive governance, not a retroactive lock on every
Application that predates it.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import application_service as app_svc
from . import governance_service as gov_svc
from . import session_service as sess_svc

NOTE_CONTEXT_APPLICATION_OWNERSHIP = "APPLICATION_OWNERSHIP"
NOTE_CONTEXT_REASSIGNMENT = "REASSIGNMENT"


# ---------------------------------------------------------------------------
# Take in charge (task §7) — an explicit operational action; never implied
# merely by viewing an Application in read-only mode.
# ---------------------------------------------------------------------------

def take_in_charge(session: Session, application_id: int, *, owner_name: str) -> m.ApplicationOwnership:
    if not owner_name or not owner_name.strip():
        raise ValueError("Taking an Application in charge requires identifying the Selezionatore.")

    application = session.get(m.Application, application_id)
    if application is None:
        raise ValueError(f"No Application with id {application_id}")
    if application.session_id is None:
        raise ValueError("This Application does not belong to a Selection Session — ownership does not apply.")
    sess_svc.assert_operational(session, application.session_id)

    current = get_current_owner(session, application_id)
    if current is not None:
        if current.owner_name == owner_name:
            return current
        raise ValueError(
            f"This Application is already taken in charge by {current.owner_name}. Use reassignment instead."
        )

    ownership = m.ApplicationOwnership(
        application_id=application_id, session_id=application.session_id, owner_name=owner_name,
        assigned_by=owner_name, is_active=True, stage_at_time=application.current_stage,
    )
    session.add(ownership)
    session.flush()

    app_svc.add_note(
        session, application_id, f"Taken in charge by {owner_name}.",
        context_type=NOTE_CONTEXT_APPLICATION_OWNERSHIP, context_id=ownership.id,
    )
    return ownership


def get_current_owner(session: Session, application_id: int) -> m.ApplicationOwnership | None:
    stmt = (
        select(m.ApplicationOwnership)
        .where(m.ApplicationOwnership.application_id == application_id, m.ApplicationOwnership.is_active.is_(True))
        .order_by(m.ApplicationOwnership.id.desc())
    )
    return session.scalars(stmt).first()


def list_ownership_history(session: Session, application_id: int) -> list[m.ApplicationOwnership]:
    stmt = (
        select(m.ApplicationOwnership)
        .where(m.ApplicationOwnership.application_id == application_id)
        .order_by(m.ApplicationOwnership.id)
    )
    return list(session.scalars(stmt).all())


# ---------------------------------------------------------------------------
# Authority comparison (task §5/§32) — reuses SelectionAuthorityLevel;
# undefined dependency (either side has no configured level) means peers.
# ---------------------------------------------------------------------------

def _authority_order(session: Session, session_id: int, selezionatore_name: str) -> int | None:
    assignment = sess_svc.get_assignment_for_selezionatore(session, session_id, selezionatore_name)
    if assignment is None or assignment.authority_level_id is None:
        return None
    level = gov_svc.get_authority_level(session, assignment.authority_level_id)
    return level.level_order if level is not None else None


def can_reassign(session: Session, application_id: int, requester_name: str) -> bool:
    """Task §9/checks K/L/M — the current owner may always reassign;
    otherwise the requester must have a STRICTLY higher configured
    authority level than the current owner WITHIN this Session. Two
    Selezionatori with no configured level (or with the requester's level
    not strictly above the owner's) are peers — a peer may never reassign
    another owner's Application (task's own explicit "unless allowed by
    explicit existing authority")."""

    application = session.get(m.Application, application_id)
    if application is None or application.session_id is None:
        return False
    current = get_current_owner(session, application_id)
    if current is None:
        return False
    if requester_name == current.owner_name:
        return True

    requester_order = _authority_order(session, application.session_id, requester_name)
    owner_order = _authority_order(session, application.session_id, current.owner_name)
    if requester_order is None or owner_order is None:
        return False
    return requester_order > owner_order


def reassign(
    session: Session, application_id: int, *, new_owner: str, performed_by: str, reason: str,
) -> m.ApplicationOwnership:
    """Task §9/§10/§21 — closes the previous active ownership record and
    creates a new one historically; NEVER overwrites the prior row.
    Requires a free-text reason (task §9's own "Require a free-text reason
    for reassignment") and authorization per `can_reassign()`."""

    if not reason or not reason.strip():
        raise ValueError("Reassigning Application ownership requires a reason.")
    if not new_owner or not new_owner.strip():
        raise ValueError("Reassigning Application ownership requires identifying the new owner.")

    application = session.get(m.Application, application_id)
    if application is None:
        raise ValueError(f"No Application with id {application_id}")
    if application.session_id is None:
        raise ValueError("This Application does not belong to a Selection Session — ownership does not apply.")
    sess_svc.assert_operational(session, application.session_id)

    current = get_current_owner(session, application_id)
    if current is None:
        raise ValueError("This Application has no current owner to reassign — use Take In Charge instead.")
    if not can_reassign(session, application_id, performed_by):
        raise ValueError(
            f"{performed_by} is not authorized to reassign this Application — not the current owner "
            f"({current.owner_name}), and not a Selezionatore with configured superior authority over them."
        )

    current.is_active = False
    current.ended_at = datetime.utcnow()
    session.flush()

    new_ownership = m.ApplicationOwnership(
        application_id=application_id, session_id=application.session_id, owner_name=new_owner,
        assigned_by=performed_by, reason=reason, previous_ownership_id=current.id, is_active=True,
        stage_at_time=application.current_stage,
    )
    session.add(new_ownership)
    session.flush()

    app_svc.add_note(
        session, application_id,
        f"Ownership reassigned from {current.owner_name} to {new_owner} by {performed_by}. Reason: {reason}",
        context_type=NOTE_CONTEXT_REASSIGNMENT, context_id=new_ownership.id,
    )
    return new_ownership


# ---------------------------------------------------------------------------
# Write-authority guard (task §8) — the single reusable enforcement point.
# ---------------------------------------------------------------------------

def can_write(session: Session, application_id: int, actor_name: str | None) -> bool:
    application = session.get(m.Application, application_id)
    if application is None or application.session_id is None:
        return True  # Not Session-governed — Task 5C ownership does not apply.
    current = get_current_owner(session, application_id)
    if current is None:
        return True  # Unclaimed — no owner yet to be read-only against.
    return bool(actor_name) and actor_name == current.owner_name


def assert_can_operate(session: Session, application_id: int, actor_name: str | None) -> None:
    """The one guard `app.py` calls at the top of a substantive Application
    mutation route (task §8's own explicit examples: change Outcome,
    override a decision, edit Screening evaluation, edit Trainable Gap,
    modify Application workflow). Also enforces task §13's operational gate
    for Session-linked Applications, so a mutation can never slip through
    on a Session whose Rule Set has not yet been confirmed."""

    application = session.get(m.Application, application_id)
    if application is None:
        raise ValueError(f"No Application with id {application_id}")
    if application.session_id is None:
        return  # Not Session-governed.

    sess_svc.assert_operational(session, application.session_id)

    if not can_write(session, application_id, actor_name):
        current = get_current_owner(session, application_id)
        owner = current.owner_name if current else "another Selezionatore"
        raise ValueError(
            f"{actor_name or 'This Selezionatore'} has read-only access to this Application — it is "
            f"currently taken in charge by {owner}. Reassign ownership first."
        )
