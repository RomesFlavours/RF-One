"""Unified Selection Notes History (Task 5A §20-§22). Every meaningful
Selection element already has (or gains, via this task) a Note field —
`ApplicationNote` covers the Application itself, Primary Screening Runs and
Criterion Evaluations (Task 3D-FIX), Stage transitions, Outcome decisions,
and Candidate Flags (all new here). Phone/In-Person Interview notes (Task
4A/4B) predate `ApplicationNote` and keep their own plain fields
(`PhoneInterviewPlan.notes`, `PhoneInterviewQuestionInstance.
selezionatore_note`, `InPersonInterviewPlan.notes`,
`AssessmentItemInstance.selezionatore_note`) — untouched, still fully
functional (task's own "do not redesign Phone Interview or
In-Person/Practical").

`get_selection_notes_history()` is the ONE place that reads across all of
these and returns one chronological list — never a second, disconnected
notes system (task §20's own "do not create unnecessary disconnected note
systems"). Every source here is read-only from this module's perspective;
notes are still written through their own existing mechanisms
(`application_service.add_note`, `stage_service.set_stage`,
`outcome_service.apply_outcome`, `candidate_flag_service.create_flag`,
or the pre-existing Phone/In-Person note fields).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import application_service as app_svc
from .core import stage_model as stgm

_CONTEXT_LABELS = {
    None: "Application",
    "STAGE_TRANSITION": "Stage Transition",
    "OUTCOME_DECISION": "Outcome Decision",
    "CANDIDATE_FLAG": "Candidate Flag",
    "PRIMARY_SCREENING_RUN": "Primary Screening",
    "PRIMARY_SCREENING_CRITERION_EVALUATION": "Primary Screening Criterion",
    "QUEUE_MOVEMENT": "Queue Movement",
    "INFORMATION_EVENT": "Information / Event",
    "TRAINABLE_GAP": "Trainable Gap",
}


@dataclass
class NoteEntry:
    created_at: datetime | None
    context_label: str
    note_text: str
    stage: str | None = None
    author: str | None = None


def _application_notes(session: Session, application_id: int) -> list[NoteEntry]:
    entries: list[NoteEntry] = []
    for note in app_svc.list_notes(session, application_id):
        author = None
        stage = None
        if note.context_type == "STAGE_TRANSITION" and note.context_id:
            transition = session.get(m.ApplicationStageTransition, note.context_id)
            if transition is not None:
                author = transition.performed_by
                stage = transition.new_stage
        elif note.context_type == "OUTCOME_DECISION" and note.context_id:
            decision = session.get(m.SelectionOutcomeDecision, note.context_id)
            if decision is not None:
                author = decision.performed_by
        elif note.context_type == "QUEUE_MOVEMENT" and note.context_id:
            movement = session.get(m.ApplicationQueueMovement, note.context_id)
            if movement is not None:
                author = movement.performed_by
        elif note.context_type == "PRIMARY_SCREENING_RUN" or note.context_type == "PRIMARY_SCREENING_CRITERION_EVALUATION":
            stage = stgm.PRIMARY_SCREENING

        note_text = note.note_text
        if note.context_type == "INFORMATION_EVENT":
            # Task 5A-ALIGN §3/§15 — an Information/Event entry is never a
            # decision; format it so it reads unmistakably as a raw,
            # reported fact rather than a Selezionatore conclusion.
            author = note.reported_by or author
            stage = note.stage_at_time or stage
            prefix = f"[{note.event_type}] " if note.event_type else "[Reported information] "
            suffix = f" (source: {note.original_source})" if note.original_source else ""
            note_text = f"{prefix}{note.note_text}{suffix}"

        entries.append(NoteEntry(
            created_at=note.created_at, context_label=_CONTEXT_LABELS.get(note.context_type, note.context_type),
            note_text=note_text, stage=stage, author=author,
        ))
    return entries


def _phone_interview_notes(session: Session, application_id: int) -> list[NoteEntry]:
    plan = session.scalars(
        select(m.PhoneInterviewPlan).where(m.PhoneInterviewPlan.application_id == application_id)
    ).first()
    if plan is None:
        return []
    entries: list[NoteEntry] = []
    if plan.notes:
        entries.append(NoteEntry(
            created_at=plan.updated_at, context_label="Phone Interview", note_text=plan.notes,
            stage=stgm.PHONE_INTERVIEW,
        ))
    for question in plan.question_instances:
        if question.selezionatore_note:
            entries.append(NoteEntry(
                created_at=question.answered_at or question.updated_at,
                context_label="Phone Interview Question", stage=stgm.PHONE_INTERVIEW,
                note_text=f"[{question.question_text[:80]}] {question.selezionatore_note}",
            ))
    return entries


def _in_person_interview_notes(session: Session, application_id: int) -> list[NoteEntry]:
    plan = session.scalars(
        select(m.InPersonInterviewPlan).where(m.InPersonInterviewPlan.application_id == application_id)
    ).first()
    if plan is None:
        return []
    entries: list[NoteEntry] = []
    if plan.notes:
        entries.append(NoteEntry(
            created_at=plan.updated_at, context_label="In-Person Interview", note_text=plan.notes,
            stage=stgm.IN_PERSON_PRACTICAL,
        ))
    for item in plan.item_instances:
        if item.selezionatore_note:
            entries.append(NoteEntry(
                created_at=item.updated_at, context_label="In-Person Assessment Item",
                stage=stgm.IN_PERSON_PRACTICAL,
                note_text=f"[{item.title_or_question[:80]}] {item.selezionatore_note}",
            ))
    return entries


def get_selection_notes_history(session: Session, application_id: int) -> list[NoteEntry]:
    """The Application's entire Selection Notes History, chronologically
    (task §21/§22) — one unified query spanning every context a note may
    have been entered in. `created_at` may be `None` for a legacy field
    with no per-entry timestamp (none currently exist); such entries sort
    last rather than crashing."""

    entries = (
        _application_notes(session, application_id)
        + _phone_interview_notes(session, application_id)
        + _in_person_interview_notes(session, application_id)
    )
    entries.sort(key=lambda e: e.created_at or datetime.max)
    return entries
