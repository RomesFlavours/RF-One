"""Selection Application service layer (Task 3C — RF-One Selection 3C
Concept Note, §1: "CANDIDATE = the person, APPLICATION = one specific
application by that person for a specific role/context/date").

Naming note, read before touching this module: it deliberately does NOT
rename or restructure the existing `Candidate` table (Task 2A) — that table
keeps its established meaning (one résumé/CV dataset) and now plays the
role of "one Application's CV snapshot." `CandidatePerson` is the NEW
person-level identity this concept introduces. Renaming `Candidate` itself
— read/written throughout Task 2A/2B/3A/3B — was judged riskier than adding
this layer alongside it; a documented, deliberate scope decision.

Identity resolution (Task 3C-FIX — see `identity_service.py`) is
confidence-based: an exact normalized email or phone match resolves
automatically; a name-only match is never enough on its own and instead
surfaces a `PersonMatchCandidate` suggestion for the Selezionatore.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from .. import models as m
from . import identity_service as identity_svc
from .core import application_model as apm
from .core import signal_model as sm


def get_or_create_person_for_candidate(
    session: Session, candidate_id: int, *, restaurant_id: int | None,
) -> tuple[m.CandidatePerson, bool]:
    """Resolves (or creates) the `CandidatePerson` a given `Candidate`
    (résumé/CV snapshot) row belongs to — thin wrapper around
    `identity_service.resolve_or_create_person`. Returns `(person,
    is_new)`; `create_application` below uses `is_new` to decide whether
    name-based match suggestions need to be generated."""

    candidate = session.get(m.Candidate, candidate_id)
    if candidate is None:
        raise ValueError(f"No Candidate with id {candidate_id}")

    return identity_svc.resolve_or_create_person(
        session, restaurant_id=restaurant_id, full_name=candidate.full_name,
        email=candidate.email, phone=candidate.phone,
    )


def create_application(
    session: Session, *, candidate_id: int, restaurant_id: int | None,
    requirement_set_id: int | None = None, target_role: str | None = None,
) -> m.Application:
    """Creates the Application wrapping one already-imported `Candidate`
    (résumé) row, resolving/creating its `CandidatePerson` first. One
    Application per Candidate row (a unique constraint backs this up) —
    calling this again for the same `candidate_id` returns the existing
    Application rather than creating a duplicate. When identity resolution
    could only create a brand-new person (no VERY_STRONG contact match),
    any STRONG/POSSIBLE name-based matches are recorded as pending
    suggestions against the new Application (Task 3C-FIX §1)."""

    existing = session.scalars(select(m.Application).where(m.Application.candidate_id == candidate_id)).first()
    if existing is not None:
        return existing

    candidate = session.get(m.Candidate, candidate_id)
    if candidate is None:
        raise ValueError(f"No Candidate with id {candidate_id}")

    person, is_new_person = get_or_create_person_for_candidate(session, candidate_id, restaurant_id=restaurant_id)

    application = m.Application(
        person_id=person.id, candidate_id=candidate_id, restaurant_id=restaurant_id,
        requirement_set_id=requirement_set_id, target_role=target_role or candidate.target_role,
    )
    session.add(application)
    session.flush()

    if is_new_person:
        identity_svc.create_pending_suggestions_for_application(
            session, application_id=application.id, new_person=person,
        )

    return application


def get_application(session: Session, application_id: int) -> m.Application | None:
    return session.get(m.Application, application_id)


def get_application_for_candidate(session: Session, candidate_id: int) -> m.Application | None:
    stmt = select(m.Application).where(m.Application.candidate_id == candidate_id)
    return session.scalars(stmt).first()


_SORT_COLUMNS = {
    "applied_at": m.Application.applied_at,
    "target_role": m.Application.target_role,
    "status": m.Application.workflow_status,
}

# Task 3C-MICRO-FIX: the Review Queue's operational priority order is fixed
# (HIGH_PRIORITY -> INTERESTING -> STANDARD -> LOW_PRIORITY), never the
# category string's alphabetical order. `sm.REVIEW_PRIORITY_CATEGORIES` is
# already defined in this exact operational order — reused here rather than
# re-declared, so the two can never drift apart.
_REVIEW_PRIORITY_ORDER = {category: index for index, category in enumerate(sm.REVIEW_PRIORITY_CATEGORIES)}


def list_applications(
    session: Session, *, restaurant_id: int | None = None, priority: str | None = None,
    workflow_status: str | None = None, target_role: str | None = None, repeated_only: bool = False,
    sort_by: str = "applied_at", descending: bool = True,
) -> list[m.Application]:
    """The Review Queue's own query (Task 3C-FIX §6, priority-order corrected
    by Task 3C-MICRO-FIX) — filterable/sortable, but never re-orders into
    rank positions. `sort_by="priority"` orders Applications by the fixed
    operational severity HIGH_PRIORITY -> INTERESTING -> STANDARD ->
    LOW_PRIORITY (never the category string alphabetically), always reading
    the EFFECTIVE Review Priority (`Application.review_priority_effective`,
    which already reflects any Selezionatore override). Within the same
    priority category, Applications are ordered by application date (newest
    first), then by Application id (descending) as a deterministic
    tie-breaker — a display/order policy only, never a candidate ranking."""

    stmt = select(m.Application)
    if restaurant_id is not None:
        stmt = stmt.where(m.Application.restaurant_id == restaurant_id)
    if priority:
        stmt = stmt.where(m.Application.review_priority_effective == priority)
    if workflow_status:
        stmt = stmt.where(m.Application.workflow_status == workflow_status)
    if target_role:
        stmt = stmt.where(m.Application.target_role == target_role)

    if sort_by == "priority":
        priority_rank = case(
            *_REVIEW_PRIORITY_ORDER.items(), value=m.Application.review_priority_effective,
            else_=len(_REVIEW_PRIORITY_ORDER),
        )
        rank_order = priority_rank.asc() if descending else priority_rank.desc()
        stmt = stmt.order_by(rank_order, m.Application.applied_at.desc(), m.Application.id.desc())
    else:
        column = _SORT_COLUMNS.get(sort_by, m.Application.applied_at)
        stmt = stmt.order_by(column.desc() if descending else column.asc())

    applications = list(session.scalars(stmt).all())
    if repeated_only:
        applications = [a for a in applications if list_prior_applications(session, a.id)]
    return applications


def list_applications_for_person(session: Session, person_id: int) -> list[m.Application]:
    stmt = select(m.Application).where(m.Application.person_id == person_id).order_by(m.Application.id)
    return list(session.scalars(stmt).all())


def list_prior_applications(session: Session, application_id: int) -> list[m.Application]:
    """Every OTHER Application by the same person, submitted before this
    one (concept note §1: "Application history must therefore remain
    visible and usable"). Ordered/filtered by `id` rather than
    `applied_at` — safer than a timestamp column whose default precision
    can tie when two Applications are created moments apart."""

    application = session.get(m.Application, application_id)
    if application is None:
        return []
    stmt = (
        select(m.Application)
        .where(m.Application.person_id == application.person_id, m.Application.id < application.id)
        .order_by(m.Application.id)
    )
    return list(session.scalars(stmt).all())


def set_outcome(session: Session, application_id: int, outcome: str) -> m.Application:
    """GLOBAL_INTEGRITY_FIX_003 / C-2 §3/§4 — LEGACY, COMPATIBILITY-ONLY.
    No live route calls this anymore (the ungoverned `/applications/<id>/
    outcome` HTTP mutation path was retired — see `Selection/app.py`'s own
    comment at that route's former location); it is kept only so a
    pre-existing Task 3C-era structural regression check
    (`selection_validation.py`'s "3C-O") and any other non-HTTP caller can
    still exercise/set this historical field directly. This is NEVER the
    authoritative Outcome — see `outcome_service.apply_outcome`/
    `outcome_service.get_effective_application_outcome` for that."""

    if outcome not in sm.APPLICATION_OUTCOMES:
        raise ValueError(f"Unknown outcome {outcome!r}; expected one of {sm.APPLICATION_OUTCOMES}")
    application = session.get(m.Application, application_id)
    if application is None:
        raise ValueError(f"No Application with id {application_id}")
    application.outcome = outcome
    session.flush()
    return application


def set_target_role(session: Session, application_id: int, target_role: str | None) -> m.Application:
    """Corrects/sets which SPECIFIC role this Application is for —
    independent of whatever `Candidate.target_role` the résumé parser
    defaulted to (Task 2A's `resolve.py` defaults every parsed résumé to
    "SERVER" absent an explicit statement otherwise, which would otherwise
    make every Application look like it targets the same role, silently
    defeating concept note §1's premise that Applications over time may
    target genuinely different roles)."""

    application = session.get(m.Application, application_id)
    if application is None:
        raise ValueError(f"No Application with id {application_id}")
    application.target_role = target_role
    session.flush()
    return application


def add_note(
    session: Session, application_id: int, note_text: str, *,
    context_type: str | None = None, context_id: int | None = None, event_type: str | None = None,
    reported_by: str | None = None, original_source: str | None = None, stage_at_time: str | None = None,
) -> m.ApplicationNote:
    """Appends one Selezionatore note (Task 3C-FIX §11) — append-only
    history, never a single overwritten field. Deliberately separate from
    evidence: adding a note never touches a Signal Observation, a Fit
    Assessment, or Review Priority.

    `context_type`/`context_id` (Task 3D-FIX §16) optionally tag WHERE in
    the Selection journey this note was entered (e.g. one specific Primary
    Screening Run or Criterion Evaluation) — both `None` (the default)
    means a general Application-level note, Task 3C-FIX's original
    behavior, unchanged. This is the one notes mechanism every later
    Selection stage reuses rather than inventing its own.

    `event_type`/`reported_by`/`original_source`/`stage_at_time` (Task
    5A-ALIGN §3/§15) are used only by `record_information_event()` below,
    for `context_type="INFORMATION_EVENT"` rows — an ordinary Selezionatore
    note leaves all four `None`."""

    application = session.get(m.Application, application_id)
    if application is None:
        raise ValueError(f"No Application with id {application_id}")
    note = m.ApplicationNote(
        application_id=application_id, note_text=note_text, context_type=context_type, context_id=context_id,
        event_type=event_type, reported_by=reported_by, original_source=original_source,
        stage_at_time=stage_at_time,
    )
    session.add(note)
    session.flush()
    return note


NOTE_CONTEXT_INFORMATION_EVENT = "INFORMATION_EVENT"


def record_information_event(
    session: Session, application_id: int, *, description: str, event_type: str | None = None,
    reported_by: str | None = None, original_source: str | None = None,
) -> m.ApplicationNote:
    """Task 5A-ALIGN §3/§15 — a factual INFORMATION/EVENT, distinct from a
    Selezionatore DECISION (`outcome_service.apply_outcome`). Example: "a
    server received a phone call from a candidate saying they are
    withdrawing." This function does exactly one thing — append one
    `ApplicationNote` row tagged `context_type="INFORMATION_EVENT"` — and
    NOTHING else: it never touches `Application.current_stage`,
    `.lifecycle_state`, `.workflow_status`, or any Outcome Decision. The
    Selezionatore alone decides what (if anything) to do with this
    information, via a completely separate, explicit
    `outcome_service.apply_outcome()` call."""

    application = session.get(m.Application, application_id)
    stage_at_time = application.current_stage if application is not None else None
    return add_note(
        session, application_id, description, context_type=NOTE_CONTEXT_INFORMATION_EVENT, event_type=event_type,
        reported_by=reported_by, original_source=original_source, stage_at_time=stage_at_time,
    )


def list_notes(
    session: Session, application_id: int, *, context_type: str | None = None, context_id: int | None = None,
) -> list[m.ApplicationNote]:
    """All notes for this Application, most recent first — optionally
    filtered down to one source/context (Task 3D-FIX §16), so a Primary
    Screening Run or Criterion Evaluation can show only its own notes while
    a future Final Selection Decision screen can still read every note for
    the Application regardless of context."""

    stmt = select(m.ApplicationNote).where(m.ApplicationNote.application_id == application_id)
    if context_type is not None:
        stmt = stmt.where(m.ApplicationNote.context_type == context_type)
    if context_id is not None:
        stmt = stmt.where(m.ApplicationNote.context_id == context_id)
    stmt = stmt.order_by(m.ApplicationNote.id.desc())
    return list(session.scalars(stmt).all())


def set_workflow_status(
    session: Session, application_id: int, new_status: str, *, reason: str | None = None,
) -> m.Application:
    """The ONLY place `Application.workflow_status` is ever written (Task
    3C-FIX §7/§10). Nothing in `signal_service.py` calls this; Review
    Priority never sets or implies a workflow status.

    Task 5A-FIX §1/§2: `workflow_status` is no longer an independently
    authoritative decision — the authoritative Selection state is
    `current_stage` + the current Outcome's `lifecycle_state`
    (`stage_service.py`/`outcome_service.py`). This function itself is
    UNCHANGED (kept for backward compatibility with any code that still
    reads/writes the field directly), but it is now called ONLY by
    `workflow_projection_service.refresh_legacy_workflow_status()` as a
    derived projection — no Selection UI action should call it directly
    with an arbitrary value anymore; see `workflow_projection_service.
    apply_legacy_workflow_action()` for the supported compatibility path."""

    if new_status not in apm.WORKFLOW_STATUSES:
        raise ValueError(f"Unknown workflow status {new_status!r}; expected one of {apm.WORKFLOW_STATUSES}")
    application = session.get(m.Application, application_id)
    if application is None:
        raise ValueError(f"No Application with id {application_id}")
    application.workflow_status = new_status
    application.workflow_status_reason = reason
    application.workflow_status_updated_at = datetime.utcnow()
    session.flush()
    return application


def get_application_change_summary(session: Session, application_id: int):
    """Task 3C-FIX §10 — a concise, facts-only comparison against this
    person's most recent PRIOR Application (the one immediately before
    this one), or `None` for a first-time applicant. See
    `core/application_comparison.py` for what is and is not compared."""

    from . import persistence
    from .core.application_comparison import compare_applications

    application = session.get(m.Application, application_id)
    if application is None:
        raise ValueError(f"No Application with id {application_id}")

    prior_applications = list_prior_applications(session, application_id)
    if not prior_applications:
        return None
    most_recent_prior = prior_applications[-1]

    return compare_applications(
        prior_profile=persistence.to_profile(most_recent_prior.candidate), prior_target_role=most_recent_prior.target_role,
        current_profile=persistence.to_profile(application.candidate), current_target_role=application.target_role,
    )
