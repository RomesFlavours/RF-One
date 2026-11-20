"""Application Ownership — service layer (Task 5C §6-§10). ONE active
operational owner per Application at a time (task §10 — never competing
concurrent owners); non-owner Selezionatori assigned to the same Session
remain read-only (task §8) until ownership is explicitly transferred
(task §9). Authority for reassignment reuses `SelectionAuthorityLevel` via
the consolidated `authority_service` (GLOBAL_INTEGRITY_FIX_002 / I-4)
rather than a parallel permission system (task §32).

GLOBAL_INTEGRITY_FIX_002 / C-1 — the highest-priority part of that fix:
every function in this module that used to compare or accept a free-text
name (`owner_name == actor_name`) as PROOF of who is acting now takes a
stable `ActingIdentity` id instead. `owner_name`/`assigned_by` are still
written, but purely as display text derived FROM the resolved identity —
never independently authoritative, and never accepted directly from an
HTTP form field as identity proof (see `acting_identity_service`'s module
docstring and `Selection/app.py`'s `_current_identity()`).

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
from . import authority_service as auth_svc
from . import session_service as sess_svc

NOTE_CONTEXT_APPLICATION_OWNERSHIP = "APPLICATION_OWNERSHIP"
NOTE_CONTEXT_REASSIGNMENT = "REASSIGNMENT"


def _require_active_identity(session: Session, identity_id: int | None, *, purpose: str) -> m.ActingIdentity:
    identity = session.get(m.ActingIdentity, identity_id) if identity_id is not None else None
    if identity is None or not identity.is_active:
        raise ValueError(f"{purpose} requires a valid, active Acting Identity.")
    return identity


# ---------------------------------------------------------------------------
# Take in charge (task §7) — an explicit operational action; never implied
# merely by viewing an Application in read-only mode.
# ---------------------------------------------------------------------------

def take_in_charge(session: Session, application_id: int, *, acting_identity_id: int) -> m.ApplicationOwnership:
    identity = _require_active_identity(session, acting_identity_id, purpose="Taking an Application in charge")

    application = session.get(m.Application, application_id)
    if application is None:
        raise ValueError(f"No Application with id {application_id}")
    if application.session_id is None:
        raise ValueError("This Application does not belong to a Selection Session — ownership does not apply.")
    sess_svc.assert_operational(session, application.session_id)

    current = get_current_owner(session, application_id)
    if current is not None:
        if current.acting_identity_id == identity.id:
            return current
        raise ValueError(
            f"This Application is already taken in charge by {current.owner_name}. Use reassignment instead."
        )

    ownership = m.ApplicationOwnership(
        application_id=application_id, session_id=application.session_id,
        owner_name=identity.display_name, acting_identity_id=identity.id,
        assigned_by=identity.display_name, assigned_by_identity_id=identity.id,
        is_active=True, stage_at_time=application.current_stage,
    )
    session.add(ownership)
    session.flush()

    app_svc.add_note(
        session, application_id, f"Taken in charge by {identity.display_name}.",
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
# Authority comparison (task §9/§32) — delegates entirely to the
# consolidated `authority_service` (GLOBAL_INTEGRITY_FIX_002 / I-4); this
# module no longer holds its own private authority-order helper.
# ---------------------------------------------------------------------------

def can_reassign(session: Session, application_id: int, requester_identity_id: int | None) -> bool:
    """Task §9/checks K/L/M — the current owner may always reassign;
    otherwise the requester must have a STRICTLY higher configured
    authority level than the current owner WITHIN this Session (task's own
    explicit "unless allowed by explicit existing authority" — two peers may
    never reassign each other). A historical ownership row with no recorded
    `acting_identity_id` (created before this fix) can never be matched or
    out-ranked by identity — Historical Integrity: honest uncertainty, never
    a fabricated identity comparison."""

    application = session.get(m.Application, application_id)
    if application is None or application.session_id is None:
        return False
    current = get_current_owner(session, application_id)
    if current is None or requester_identity_id is None:
        return False
    if current.acting_identity_id is not None and requester_identity_id == current.acting_identity_id:
        return True
    if current.acting_identity_id is None:
        return False

    return auth_svc.is_strictly_superior(
        session, application.session_id, requester_identity_id, current.acting_identity_id,
    )


def reassign(
    session: Session, application_id: int, *, new_owner_identity_id: int, performed_by_identity_id: int, reason: str,
) -> m.ApplicationOwnership:
    """Task §9/§10/§21 — closes the previous active ownership record and
    creates a new one historically; NEVER overwrites the prior row.
    Requires a free-text reason (task §9's own "Require a free-text reason
    for reassignment") and authorization per `can_reassign()`, now keyed by
    stable Acting Identity ids (GLOBAL_INTEGRITY_FIX_002 / C-1)."""

    if not reason or not reason.strip():
        raise ValueError("Reassigning Application ownership requires a reason.")

    new_identity = _require_active_identity(
        session, new_owner_identity_id, purpose="Reassigning Application ownership (new owner)",
    )
    performer = _require_active_identity(
        session, performed_by_identity_id, purpose="Reassigning Application ownership (performer)",
    )

    application = session.get(m.Application, application_id)
    if application is None:
        raise ValueError(f"No Application with id {application_id}")
    if application.session_id is None:
        raise ValueError("This Application does not belong to a Selection Session — ownership does not apply.")
    sess_svc.assert_operational(session, application.session_id)

    current = get_current_owner(session, application_id)
    if current is None:
        raise ValueError("This Application has no current owner to reassign — use Take In Charge instead.")
    if not can_reassign(session, application_id, performer.id):
        raise ValueError(
            f"{performer.display_name} is not authorized to reassign this Application — not the current owner "
            f"({current.owner_name}), and not a Selezionatore with configured superior authority over them."
        )

    current.is_active = False
    current.ended_at = datetime.utcnow()
    session.flush()

    new_ownership = m.ApplicationOwnership(
        application_id=application_id, session_id=application.session_id,
        owner_name=new_identity.display_name, acting_identity_id=new_identity.id,
        assigned_by=performer.display_name, assigned_by_identity_id=performer.id,
        reason=reason, previous_ownership_id=current.id, is_active=True,
        stage_at_time=application.current_stage,
    )
    session.add(new_ownership)
    session.flush()

    app_svc.add_note(
        session, application_id,
        f"Ownership reassigned from {current.owner_name} to {new_identity.display_name} by "
        f"{performer.display_name}. Reason: {reason}",
        context_type=NOTE_CONTEXT_REASSIGNMENT, context_id=new_ownership.id,
    )
    return new_ownership


# ---------------------------------------------------------------------------
# Write-authority guard (task §8) — the single reusable enforcement point.
# ---------------------------------------------------------------------------

def can_write(session: Session, application_id: int, actor_identity_id: int | None) -> bool:
    application = session.get(m.Application, application_id)
    if application is None or application.session_id is None:
        return True  # Not Session-governed — Task 5C ownership does not apply.
    current = get_current_owner(session, application_id)
    if current is None:
        return True  # Unclaimed — no owner yet to be read-only against.
    if actor_identity_id is None:
        return False
    if current.acting_identity_id is None:
        # A historical row with no recorded identity — Historical Integrity:
        # never guess whether today's caller IS that unrecorded owner.
        return False
    return actor_identity_id == current.acting_identity_id


def assert_can_operate(session: Session, application_id: int, actor_identity_id: int | None) -> None:
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

    if not can_write(session, application_id, actor_identity_id):
        current = get_current_owner(session, application_id)
        owner = current.owner_name if current else "another Selezionatore"
        raise ValueError(
            f"This Acting Identity has read-only access to this Application — it is currently taken in charge "
            f"by {owner}. Reassign ownership first."
        )
