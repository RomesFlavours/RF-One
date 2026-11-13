"""First-Screening Application Question service (Task 5E Part C). A
DIFFERENT concept from Phone Interview Questions (`phone_interview_service`)
and In-Person Interview items (`in_person_interview_service`) — task §17's
own explicit separation; no table or route here is shared with those.
Question wording/existence is always restaurant-authored (task §16's own
"do NOT hard-code those questions universally").
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import primary_screening_service as ps_svc
from .core import job_posting_model as jpm


def create_question(
    session: Session, *, restaurant_id: int | None, question_text: str, session_id: int | None = None,
    target_role: str | None = None, response_type: str = jpm.RESPONSE_TEXT, is_required: bool = False,
    related_criterion_id: int | None = None, answer_level_map: dict | None = None, display_order: int | None = None,
) -> m.ApplicationQuestionDefinition:
    jpm.validate_response_type(response_type)
    if display_order is None:
        from sqlalchemy import func
        display_order = session.scalar(
            select(func.count()).select_from(m.ApplicationQuestionDefinition)
            .where(m.ApplicationQuestionDefinition.restaurant_id == restaurant_id)
        )
    question = m.ApplicationQuestionDefinition(
        restaurant_id=restaurant_id, session_id=session_id, target_role=target_role, question_text=question_text,
        response_type=response_type, is_required=is_required, related_criterion_id=related_criterion_id,
        answer_level_map=dict(answer_level_map or {}), display_order=display_order,
    )
    session.add(question)
    session.flush()
    return question


def update_question(session: Session, question_id: int, **fields) -> m.ApplicationQuestionDefinition:
    question = session.get(m.ApplicationQuestionDefinition, question_id)
    if question is None:
        raise ValueError(f"No ApplicationQuestionDefinition with id {question_id}")
    allowed = {
        "question_text", "response_type", "is_required", "display_order", "related_criterion_id",
        "answer_level_map", "is_active", "target_role", "session_id",
    }
    for key in fields:
        if key not in allowed:
            raise ValueError(f"Cannot set {key!r} on an ApplicationQuestionDefinition through update_question")
    if "response_type" in fields:
        jpm.validate_response_type(fields["response_type"])
    if "answer_level_map" in fields:
        fields["answer_level_map"] = dict(fields["answer_level_map"])
    for key, value in fields.items():
        setattr(question, key, value)
    if fields:
        question.version += 1
    session.flush()
    return question


def list_questions_for_context(
    session: Session, *, restaurant_id: int | None, session_id: int | None = None, target_role: str | None = None,
    active_only: bool = True,
) -> list[m.ApplicationQuestionDefinition]:
    """Task §16 — every question APPLICABLE to this Session/Role: matches
    an exact `session_id` first; questions scoped to no Session at all
    (`session_id IS NULL`) but matching `target_role` (or scoped to
    neither) also apply — the same "any `None` scoping field means any"
    convention `CommunicationTemplate` already established."""

    stmt = select(m.ApplicationQuestionDefinition)
    if restaurant_id is not None:
        stmt = stmt.where(m.ApplicationQuestionDefinition.restaurant_id == restaurant_id)
    if active_only:
        stmt = stmt.where(m.ApplicationQuestionDefinition.is_active.is_(True))
    candidates = [
        q for q in session.scalars(stmt).all()
        if (q.session_id is None or q.session_id == session_id)
        and (q.target_role is None or q.target_role == target_role)
    ]
    candidates.sort(key=lambda q: q.display_order)
    return candidates


def record_answer(
    session: Session, application_id: int, question_definition_id: int, *, raw_answer: str,
) -> m.ApplicationQuestionAnswer:
    """Task §18 — preserves the raw answer as CANDIDATE SELF-REPORTED
    evidence; never independently verified fact."""

    question = session.get(m.ApplicationQuestionDefinition, question_definition_id)
    if question is None:
        raise ValueError(f"No ApplicationQuestionDefinition with id {question_definition_id}")
    answer = m.ApplicationQuestionAnswer(
        application_id=application_id, question_definition_id=question_definition_id,
        question_version=question.version, raw_answer=raw_answer,
    )
    session.add(answer)
    session.flush()
    return answer


def list_answers_for_application(session: Session, application_id: int) -> list[m.ApplicationQuestionAnswer]:
    stmt = (
        select(m.ApplicationQuestionAnswer)
        .where(m.ApplicationQuestionAnswer.application_id == application_id)
        .order_by(m.ApplicationQuestionAnswer.id)
    )
    return list(session.scalars(stmt).all())


def apply_answers_to_screening(session: Session, application_id: int, run_id: int) -> None:
    """Task §18/Part D — the ONE place a first-screening answer becomes
    Primary Screening evidence: for every answer whose question names a
    `related_criterion_id`, look up that criterion's Evaluation in this
    Run and record the answer as evidence (`primary_screening_service.
    apply_self_reported_evidence`). A level is set ONLY when the
    restaurant's own `answer_level_map` resolves one for this exact raw
    answer (mirrors `PrimaryScreeningCriterion.auto_evaluation_level_map`'s
    restaurant-configured-mapping discipline) — otherwise the answer is
    still recorded as evidence text, never a fabricated level."""

    for answer in list_answers_for_application(session, application_id):
        question = answer.question_definition
        if question.related_criterion_id is None:
            continue
        evaluation = ps_svc.get_evaluation_for_criterion(session, run_id, question.related_criterion_id)
        if evaluation is None:
            continue
        level = question.answer_level_map.get(answer.raw_answer)
        ps_svc.apply_self_reported_evidence(
            session, evaluation.id, evidence_text=f"Application Question — \"{question.question_text}\": {answer.raw_answer}",
            level=level,
        )
