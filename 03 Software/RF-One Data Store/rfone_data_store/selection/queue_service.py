"""Operational Queue/List service (Task 5A-FIX §7-§14). A queue/list is a
restaurant-configurable, PURELY ORGANIZATIONAL concept — never a hiring
decision (task §14). Mirrors `stage_service.py`'s exact shape: a small,
fixed set of restaurant-owned rows, an append-only movement-history table,
and a convenience "current" pointer on the Application that is never the
sole record of truth.

Two ways an Application moves between queues, both recorded identically
(distinguished only by `source`):
  - `move_to_queue(..., source=qm.MANUAL)` — a direct, independent
    Selezionatore action (task §12) — never changes Stage or Outcome.
  - `move_to_queue(..., source=qm.OUTCOME_ACTION)` — called by
    `outcome_service.apply_outcome()` when the applied Outcome's snapshot
    has a `target_queue_id` configured (task §10). Never invents a queue
    move when none is configured (task §11).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import application_service as app_svc
from .core import queue_model as qm

NOTE_CONTEXT_QUEUE_MOVEMENT = "QUEUE_MOVEMENT"


# ---------------------------------------------------------------------------
# Queue CRUD (task §8/§15) — restaurant-configurable.
# ---------------------------------------------------------------------------

def create_queue(
    session: Session, *, restaurant_id: int | None, name: str, description: str | None = None,
    display_order: int | None = None,
) -> m.SelectionQueue:
    if display_order is None:
        from sqlalchemy import func
        display_order = session.scalar(
            select(func.count()).select_from(m.SelectionQueue).where(m.SelectionQueue.restaurant_id == restaurant_id)
        )
    queue = m.SelectionQueue(restaurant_id=restaurant_id, name=name, description=description, display_order=display_order)
    session.add(queue)
    session.flush()
    return queue


def list_queues(session: Session, *, restaurant_id: int | None = None, active_only: bool = True) -> list[m.SelectionQueue]:
    stmt = select(m.SelectionQueue).order_by(m.SelectionQueue.display_order)
    if restaurant_id is not None:
        stmt = stmt.where(m.SelectionQueue.restaurant_id == restaurant_id)
    if active_only:
        stmt = stmt.where(m.SelectionQueue.is_active.is_(True))
    return list(session.scalars(stmt).all())


def get_queue(session: Session, queue_id: int) -> m.SelectionQueue | None:
    return session.get(m.SelectionQueue, queue_id)


def update_queue(session: Session, queue_id: int, **fields) -> m.SelectionQueue:
    queue = session.get(m.SelectionQueue, queue_id)
    if queue is None:
        raise ValueError(f"No SelectionQueue with id {queue_id}")
    allowed = {"name", "description", "display_order", "is_active"}
    for key in fields:
        if key not in allowed:
            raise ValueError(f"Cannot set {key!r} on a SelectionQueue through update_queue")
    for key, value in fields.items():
        setattr(queue, key, value)
    session.flush()
    return queue


def deactivate_queue(session: Session, queue_id: int) -> m.SelectionQueue:
    return update_queue(session, queue_id, is_active=False)


def reactivate_queue(session: Session, queue_id: int) -> m.SelectionQueue:
    return update_queue(session, queue_id, is_active=True)


# ---------------------------------------------------------------------------
# Queue movement (task §9/§10/§12) — append-only history + a convenience
# "current" pointer, mirroring `stage_service.set_stage()` exactly.
# ---------------------------------------------------------------------------

def move_to_queue(
    session: Session, application_id: int, queue_id: int, *, source: str = qm.MANUAL, reason: str | None = None,
    note_text: str | None = None, performed_by: str | None = None, originating_outcome_decision_id: int | None = None,
    require_active: bool = True,
) -> m.ApplicationQueueMovement | None:
    """Task §9 — records a queue move and updates `Application.
    current_queue_id` as a convenience pointer only; the full history is
    always available via `list_queue_history()`. Never touches Stage or
    Outcome (task §12/§13).

    `require_active=True` (the default, used for a fresh MANUAL move —
    task §X: "inactive queue cannot be newly selected") rejects a
    deactivated target queue outright. An Outcome-triggered move
    (`source=OUTCOME_ACTION`) passes `require_active=False`: if the
    Outcome's configured queue has since been deactivated, the queue move
    is silently skipped (returns `None`) rather than blocking the Outcome
    itself from applying — the Outcome (lifecycle effect, Note/reason,
    reminder, Flag) is the primary action; the queue move is a secondary,
    best-effort one."""

    qm.validate_source(source)
    application = session.get(m.Application, application_id)
    if application is None:
        raise ValueError(f"No Application with id {application_id}")
    queue = session.get(m.SelectionQueue, queue_id)
    if queue is None:
        if require_active:
            raise ValueError(f"No SelectionQueue with id {queue_id}")
        return None
    if not queue.is_active:
        if require_active:
            raise ValueError(f"Queue '{queue.name}' is inactive and cannot be newly selected.")
        return None

    movement = m.ApplicationQueueMovement(
        application_id=application_id, previous_queue_id=application.current_queue_id, new_queue_id=queue_id,
        source=source, reason=reason, originating_outcome_decision_id=originating_outcome_decision_id,
        performed_by=performed_by,
    )
    session.add(movement)
    application.current_queue_id = queue_id
    session.flush()

    if note_text and note_text.strip():
        app_svc.add_note(
            session, application_id, note_text, context_type=NOTE_CONTEXT_QUEUE_MOVEMENT, context_id=movement.id,
        )

    return movement


def get_current_queue(session: Session, application_id: int) -> m.SelectionQueue | None:
    application = session.get(m.Application, application_id)
    if application is None or application.current_queue_id is None:
        return None
    return session.get(m.SelectionQueue, application.current_queue_id)


def list_queue_history(session: Session, application_id: int) -> list[m.ApplicationQueueMovement]:
    stmt = (
        select(m.ApplicationQueueMovement)
        .where(m.ApplicationQueueMovement.application_id == application_id)
        .order_by(m.ApplicationQueueMovement.id)
    )
    return list(session.scalars(stmt).all())
