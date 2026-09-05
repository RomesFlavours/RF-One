"""Interview Scheduling service (Task 5D §11-§15/§31; revised by Task
5D-MICRO-FIX §1-§9). The NORMAL/default scope of an
`InterviewSchedulingWindow` is a Selection Session + Interview Stage —
offered ONCE and shared by every eligible Application in that Session
(task 5D-MICRO-FIX §1: "Do NOT require the Selezionatore to recreate
identical windows for every candidate"). An Application-specific window
(`application_id` set) remains supported as an optional, genuinely
exceptional override (task §3). `InterviewAppointment` stays
Application-specific and always books against the SHARED capacity of
whichever window it targets — `_window_applies_to_application` and the
capacity check in `book_slot` are the two places that resolve "shared"
correctly, everything else is unchanged from Task 5D.

The candidate-facing web page (`03 Software/Selection/app.py`'s
`/schedule/<token>` route) talks to this module only through an opaque
`CandidateSchedulingToken`, never a raw `application_id`/`session_id`
(task §31).
"""

from __future__ import annotations

import secrets
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models as m
from .core import communication_model as cm


# ---------------------------------------------------------------------------
# Scheduling windows (task §11; 5D-MICRO-FIX §1/§3).
# ---------------------------------------------------------------------------

def create_scheduling_window(
    session: Session, *, interview_stage: str, window_date: date, start_time: time, end_time: time,
    session_id: int | None = None, application_id: int | None = None, slot_duration_minutes: int = 30,
    capacity_per_slot: int = 1, timezone: str = "America/New_York", created_by: str | None = None,
    notes: str | None = None,
) -> m.InterviewSchedulingWindow:
    """5D-MICRO-FIX §1/§3 — the NORMAL call passes `session_id` (a window
    shared by every eligible Application in that Selection Session).
    `application_id` alone (a genuinely exceptional override — task §3)
    remains supported; passing neither is rejected, exactly like the new
    `ck_scheduling_window_session_or_application` DB constraint. Passing
    both is allowed (an override scoped for extra clarity to one
    Application within one Session) but `application_id`, when present,
    always wins in `_window_applies_to_application` below."""

    cm.validate_schedulable_stage(interview_stage)
    if session_id is None and application_id is None:
        raise ValueError(
            "A scheduling window must belong to a Selection Session or, as an explicit override, to one "
            "specific Application."
        )
    if end_time <= start_time:
        raise ValueError("A scheduling window's end_time must be after its start_time.")
    if slot_duration_minutes <= 0:
        raise ValueError("slot_duration_minutes must be positive.")

    if session_id is not None and session.get(m.SelectionSession, session_id) is None:
        raise ValueError(f"No Selection Session with id {session_id}")
    if application_id is not None and session.get(m.Application, application_id) is None:
        raise ValueError(f"No Application with id {application_id}")

    window = m.InterviewSchedulingWindow(
        session_id=session_id, application_id=application_id, interview_stage=interview_stage,
        window_date=window_date, start_time=start_time, end_time=end_time,
        slot_duration_minutes=slot_duration_minutes, capacity_per_slot=capacity_per_slot, timezone=timezone,
        created_by=created_by, notes=notes,
    )
    session.add(window)
    session.flush()
    return window


def list_windows_for_session(
    session: Session, session_id: int, *, interview_stage: str | None = None, active_only: bool = True,
) -> list[m.InterviewSchedulingWindow]:
    """5D-MICRO-FIX §8 — the primary listing a Selection Session page uses
    (task's own "Selection Session shows scheduling windows")."""

    stmt = select(m.InterviewSchedulingWindow).where(m.InterviewSchedulingWindow.session_id == session_id)
    if interview_stage is not None:
        stmt = stmt.where(m.InterviewSchedulingWindow.interview_stage == interview_stage)
    if active_only:
        stmt = stmt.where(m.InterviewSchedulingWindow.is_active.is_(True))
    stmt = stmt.order_by(m.InterviewSchedulingWindow.window_date, m.InterviewSchedulingWindow.start_time)
    return list(session.scalars(stmt).all())


def list_windows_for_application(
    session: Session, application_id: int, *, interview_stage: str | None = None, active_only: bool = True,
) -> list[m.InterviewSchedulingWindow]:
    """5D-MICRO-FIX — returns only this Application's own OVERRIDE windows
    (`application_id` set to this exact id), never the Session-shared pool
    — see `list_applicable_windows_for_application` for the combined view a
    candidate/Application actually sees."""

    stmt = select(m.InterviewSchedulingWindow).where(m.InterviewSchedulingWindow.application_id == application_id)
    if interview_stage is not None:
        stmt = stmt.where(m.InterviewSchedulingWindow.interview_stage == interview_stage)
    if active_only:
        stmt = stmt.where(m.InterviewSchedulingWindow.is_active.is_(True))
    stmt = stmt.order_by(m.InterviewSchedulingWindow.window_date, m.InterviewSchedulingWindow.start_time)
    return list(session.scalars(stmt).all())


def list_applicable_windows_for_application(
    session: Session, application_id: int, *, interview_stage: str, active_only: bool = True,
) -> list[m.InterviewSchedulingWindow]:
    """5D-MICRO-FIX §2/§4 — every window that actually applies to this
    Application: its Selection Session's shared windows (when it belongs to
    one) PLUS any Application-specific override windows of its own. This is
    the one function `list_available_slots` and the candidate scheduling
    page read from — an Application never sees another Session's windows,
    and never sees another Application's override."""

    application = session.get(m.Application, application_id)
    if application is None:
        raise ValueError(f"No Application with id {application_id}")

    windows = list(list_windows_for_application(session, application_id, interview_stage=interview_stage, active_only=active_only))
    if application.session_id is not None:
        windows += list_windows_for_session(session, application.session_id, interview_stage=interview_stage, active_only=active_only)
    windows.sort(key=lambda w: (w.window_date, w.start_time))
    return windows


def _window_applies_to_application(window: m.InterviewSchedulingWindow, application: m.Application) -> bool:
    """5D-MICRO-FIX — the one place that decides whether a given window may
    be booked by a given Application. An explicit override (`application_id`
    set) always requires an exact match; a Session-scoped shared window
    requires the Application to belong to that same Session."""

    if window.application_id is not None:
        return window.application_id == application.id
    if window.session_id is not None:
        return application.session_id == window.session_id
    return False  # unreachable given the DB check constraint, kept as an honest guard


def deactivate_window(session: Session, window_id: int) -> m.InterviewSchedulingWindow:
    window = session.get(m.InterviewSchedulingWindow, window_id)
    if window is None:
        raise ValueError(f"No InterviewSchedulingWindow with id {window_id}")
    window.is_active = False
    session.flush()
    return window


def _generate_slots(window: m.InterviewSchedulingWindow) -> list[tuple[datetime, datetime]]:
    start_dt = datetime.combine(window.window_date, window.start_time)
    end_dt = datetime.combine(window.window_date, window.end_time)
    step = timedelta(minutes=window.slot_duration_minutes)
    slots = []
    cursor = start_dt
    while cursor + step <= end_dt:
        slots.append((cursor, cursor + step))
        cursor += step
    return slots


def _occupied_ordinals(session: Session, window_id: int, slot_start_at: datetime) -> set[int]:
    rows = session.scalars(
        select(m.InterviewAppointment.slot_ordinal).where(
            m.InterviewAppointment.scheduling_window_id == window_id,
            m.InterviewAppointment.slot_start_at == slot_start_at,
            m.InterviewAppointment.status == cm.APPOINTMENT_CONFIRMED,
        )
    ).all()
    return set(rows)


def list_available_slots(session: Session, application_id: int, *, interview_stage: str) -> list[dict]:
    """Task §12; 5D-MICRO-FIX §2/§4 — every bookable slot across every
    window APPLICABLE to this Application (its Session's shared windows +
    its own overrides), excluding slots already at capacity. Capacity is
    read from `scheduling_window_id` alone (task 5D-MICRO-FIX §5 — "bookings
    by different Applications must consume capacity from the SAME shared
    slot pool"), never scoped to one Application."""

    windows = list_applicable_windows_for_application(session, application_id, interview_stage=interview_stage)
    available: list[dict] = []
    for window in windows:
        for slot_start, slot_end in _generate_slots(window):
            occupied = _occupied_ordinals(session, window.id, slot_start)
            remaining = window.capacity_per_slot - len(occupied)
            if remaining > 0:
                available.append({
                    "window_id": window.id, "start": slot_start, "end": slot_end,
                    "remaining_capacity": remaining,
                })
    available.sort(key=lambda s: s["start"])
    return available


def book_slot(
    session: Session, application_id: int, *, interview_stage: str, window_id: int, slot_start_at: datetime,
) -> m.InterviewAppointment:
    """Task §13; 5D-MICRO-FIX §5/§6/§9 — validates the slot is genuinely
    offered and applicable to this Application, revalidates capacity
    against the SHARED pool (every Application booking against this same
    window), then confirms IMMEDIATELY (no approval step). The
    count-then-insert check is backed by a real DB-level guard
    (`ux_interview_appointment_slot_ordinal_confirmed`, a partial unique
    index on (window, slot start, ordinal) scoped to CONFIRMED rows): if two
    concurrent requests both pass the in-Python check for the same last free
    ordinal, only one INSERT succeeds and the other cleanly raises
    `ValueError` from the caught `IntegrityError` — the minimum clean
    database-level protection for this architecture (task §9), not a
    broader concurrency redesign."""

    window = session.get(m.InterviewSchedulingWindow, window_id)
    application = session.get(m.Application, application_id)
    if application is None:
        raise ValueError(f"No Application with id {application_id}")
    if window is None or not window.is_active or window.interview_stage != interview_stage:
        raise ValueError("This scheduling window is not valid for this Application/stage.")
    if not _window_applies_to_application(window, application):
        raise ValueError("This scheduling window does not apply to this Application.")

    valid_slots = {start: end for start, end in _generate_slots(window)}
    if slot_start_at not in valid_slots:
        raise ValueError("The requested time is not an offered slot for this window.")

    occupied = _occupied_ordinals(session, window_id, slot_start_at)
    free_ordinal = next((i for i in range(window.capacity_per_slot) if i not in occupied), None)
    if free_ordinal is None:
        raise ValueError("This slot is no longer available.")

    appointment = m.InterviewAppointment(
        application_id=application_id, interview_stage=interview_stage, scheduling_window_id=window_id,
        slot_start_at=slot_start_at, slot_end_at=valid_slots[slot_start_at], slot_ordinal=free_ordinal,
        status=cm.APPOINTMENT_CONFIRMED, confirmed_at=datetime.utcnow(),
    )
    session.add(appointment)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise ValueError("This slot is no longer available.")

    from . import communication_service as comm_svc  # deferred: avoids a service-layer import cycle
    comm_svc.send_appointment_confirmation(session, application, appointment)

    return appointment


def reschedule_appointment(
    session: Session, appointment_id: int, *, new_window_id: int, new_slot_start_at: datetime,
    reason: str | None = None,
) -> m.InterviewAppointment:
    """Task §15 — never deletes/overwrites the prior appointment: marks it
    RESCHEDULED and books a brand-new row referencing it, exactly like
    `ApplicationOwnership.reassign`'s own append-only chain. 5D-MICRO-FIX
    §7 — the new slot may come from the same shared Session/stage pool as
    any other applicable window, not only from the original window."""

    previous = session.get(m.InterviewAppointment, appointment_id)
    if previous is None:
        raise ValueError(f"No InterviewAppointment with id {appointment_id}")

    previous.status = cm.APPOINTMENT_RESCHEDULED
    previous.cancellation_reason = reason
    session.flush()

    new_appointment = book_slot(
        session, previous.application_id, interview_stage=previous.interview_stage,
        window_id=new_window_id, slot_start_at=new_slot_start_at,
    )
    new_appointment.previous_appointment_id = previous.id
    session.flush()
    return new_appointment


def cancel_appointment(session: Session, appointment_id: int, *, reason: str | None = None) -> m.InterviewAppointment:
    appointment = session.get(m.InterviewAppointment, appointment_id)
    if appointment is None:
        raise ValueError(f"No InterviewAppointment with id {appointment_id}")
    appointment.status = cm.APPOINTMENT_CANCELLED
    appointment.cancellation_reason = reason
    session.flush()
    return appointment


def get_current_appointment(session: Session, application_id: int, *, interview_stage: str) -> m.InterviewAppointment | None:
    stmt = (
        select(m.InterviewAppointment)
        .where(
            m.InterviewAppointment.application_id == application_id,
            m.InterviewAppointment.interview_stage == interview_stage,
            m.InterviewAppointment.status == cm.APPOINTMENT_CONFIRMED,
        )
        .order_by(m.InterviewAppointment.id.desc())
    )
    return session.scalars(stmt).first()


def list_appointment_history(session: Session, application_id: int) -> list[m.InterviewAppointment]:
    stmt = (
        select(m.InterviewAppointment)
        .where(m.InterviewAppointment.application_id == application_id)
        .order_by(m.InterviewAppointment.id)
    )
    return list(session.scalars(stmt).all())


# ---------------------------------------------------------------------------
# Secure candidate-facing token (task §31).
# ---------------------------------------------------------------------------

def issue_scheduling_token(
    session: Session, application_id: int, *, interview_stage: str, expires_at: datetime | None = None,
) -> m.CandidateSchedulingToken:
    cm.validate_schedulable_stage(interview_stage)
    existing = session.scalars(
        select(m.CandidateSchedulingToken).where(
            m.CandidateSchedulingToken.application_id == application_id,
            m.CandidateSchedulingToken.interview_stage == interview_stage,
            m.CandidateSchedulingToken.is_active.is_(True),
        )
    ).first()
    if existing is not None:
        return existing

    token_row = m.CandidateSchedulingToken(
        token=secrets.token_urlsafe(24), application_id=application_id, interview_stage=interview_stage,
        expires_at=expires_at,
    )
    session.add(token_row)
    session.flush()
    return token_row


def build_scheduling_link(session: Session, application_id: int, *, interview_stage: str) -> str:
    """Returns the relative candidate-facing URL path (task §12/§31) — the
    Flask app owns the base URL/host; this module only owns issuing and
    resolving the opaque token."""

    token_row = issue_scheduling_token(session, application_id, interview_stage=interview_stage)
    return f"/schedule/{token_row.token}"


def resolve_token(session: Session, token: str) -> m.CandidateSchedulingToken | None:
    row = session.scalars(
        select(m.CandidateSchedulingToken).where(
            m.CandidateSchedulingToken.token == token, m.CandidateSchedulingToken.is_active.is_(True),
        )
    ).first()
    if row is None:
        return None
    if row.expires_at is not None and row.expires_at < datetime.utcnow():
        return None
    return row
