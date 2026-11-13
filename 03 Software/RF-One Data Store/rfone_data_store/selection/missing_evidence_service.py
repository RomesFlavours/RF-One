"""Missing-Evidence Pre-Screening service (Task 5E Parts D/E, §28-§30).
Enforces the product principle that missing evidence must never become
negative evidence (task §19): a Criterion with no usable evidence yet stays
`INSUFFICIENT_EVIDENCE`/`NOT_EVALUATED` (the existing Task 3D vocabulary),
never a fabricated level. Generates a candidate-SPECIFIC questionnaire only
for genuinely missing, importance-flagged Criteria (task §22/§23), sends it
automatically through the existing Task 5D Communication engine (task §24/
§30 — no separate reminder system), and moves an Application into the
existing `SelectionQueue` mechanism for READY FOR PHONE REVIEW once (and
only once) enough early-stage evidence exists — which never itself performs
`ADVANCE_TO_PHONE` (task §29, exclusively a Selezionatore Outcome/Stage
action, untouched by this module).
"""

from __future__ import annotations

import secrets
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import communication_service as comm_svc
from . import communication_template_service as tmpl_svc
from . import primary_screening_service as ps_svc
from . import queue_service as queue_svc
from .core import communication_model as cm
from .core import job_posting_model as jpm
from .core import primary_screening_model as psm
from .core import queue_model as qm

READY_FOR_PHONE_REVIEW_QUEUE_NAME = "Ready for Phone Review"


# ---------------------------------------------------------------------------
# Readiness (task §28/§29) — reuses the existing SelectionQueue/
# ApplicationQueueMovement mechanism (Task 5A-FIX) rather than inventing a
# new lifecycle field; never touches Stage or Outcome.
# ---------------------------------------------------------------------------

def _required_unresolved_criteria(
    session: Session, run: m.PrimaryScreeningRun,
) -> list[m.PrimaryScreeningCriterion]:
    """Criteria this restaurant flagged `required_for_phone_review` whose
    CURRENT evaluation in this Run is still `NOT_EVALUATED`/
    `INSUFFICIENT_EVIDENCE` — task §22's "important information needed for
    the current stage decision... still missing"."""

    unresolved = []
    for evaluation in ps_svc.list_evaluations(session, run.id):
        snapshot = evaluation.criterion_snapshot
        if not snapshot.required_for_phone_review:
            continue
        if evaluation.status in (psm.NOT_EVALUATED, psm.INSUFFICIENT_EVIDENCE):
            criterion = session.get(m.PrimaryScreeningCriterion, snapshot.criterion_id)
            if criterion is not None:
                unresolved.append(criterion)
    return unresolved


def get_or_create_ready_for_phone_review_queue(session: Session, restaurant_id: int | None) -> m.SelectionQueue:
    existing = session.scalars(
        select(m.SelectionQueue).where(
            m.SelectionQueue.restaurant_id == restaurant_id, m.SelectionQueue.name == READY_FOR_PHONE_REVIEW_QUEUE_NAME,
        )
    ).first()
    if existing is not None:
        return existing
    return queue_svc.create_queue(
        session, restaurant_id=restaurant_id, name=READY_FOR_PHONE_REVIEW_QUEUE_NAME,
        description="Enough early-stage evidence exists for a Selezionatore to decide whether to invest in a "
        "Phone Interview. This is NOT an advance-to-Phone-Interview decision.",
    )


def is_ready_for_phone_review(session: Session, application_id: int) -> bool:
    stmt = select(m.ApplicationQueueMovement).join(
        m.SelectionQueue, m.ApplicationQueueMovement.new_queue_id == m.SelectionQueue.id,
    ).where(
        m.ApplicationQueueMovement.application_id == application_id,
        m.SelectionQueue.name == READY_FOR_PHONE_REVIEW_QUEUE_NAME,
    )
    return session.scalars(stmt).first() is not None


def _move_to_ready_for_phone_review(session: Session, application: m.Application) -> None:
    queue = get_or_create_ready_for_phone_review_queue(session, application.restaurant_id)
    queue_svc.move_to_queue(
        session, application.id, queue.id, source=qm.AUTOMATIC_READINESS,
        reason="Sufficient early-stage evidence is available for a Phone Interview decision.",
        performed_by="SYSTEM_AUTOMATIC", require_active=False,
    )


# ---------------------------------------------------------------------------
# Questionnaire generation (task §22-§25) — candidate-specific, only the
# genuinely missing questions, automatic send, no prior approval required.
# ---------------------------------------------------------------------------

def list_questionnaires_for_application(session: Session, application_id: int) -> list[m.MissingEvidenceQuestionnaire]:
    stmt = (
        select(m.MissingEvidenceQuestionnaire)
        .where(m.MissingEvidenceQuestionnaire.application_id == application_id)
        .order_by(m.MissingEvidenceQuestionnaire.id)
    )
    return list(session.scalars(stmt).all())


def get_pending_questionnaire(session: Session, application_id: int) -> m.MissingEvidenceQuestionnaire | None:
    stmt = select(m.MissingEvidenceQuestionnaire).where(
        m.MissingEvidenceQuestionnaire.application_id == application_id,
        m.MissingEvidenceQuestionnaire.status == jpm.QUESTIONNAIRE_PENDING,
    )
    return session.scalars(stmt).first()


def process_application_readiness(
    session: Session, application_id: int,
) -> m.MissingEvidenceQuestionnaire | None:
    """Task's own end-to-end flow — call this right after a Primary
    Screening Run is (re)computed. Three possible outcomes, mutually
    exclusive:
      1. an active Hard Disqualifier is present -> the Application is
         "clearly to be stopped" (task §22's own qualifier); do nothing —
         the Selezionatore decides explicitly, exactly as Primary Screening
         already works, untouched here.
      2. required evidence is still missing -> generate/return the (at most
         one) PENDING Missing-Evidence Questionnaire, sending it
         automatically.
      3. nothing required is missing -> move to READY FOR PHONE REVIEW and
         return `None`.
    Never raises for a missing Run (returns `None`) — readiness simply
    cannot be assessed yet."""

    application = session.get(m.Application, application_id)
    if application is None:
        raise ValueError(f"No Application with id {application_id}")
    run = ps_svc.get_latest_run_for_application(session, application_id)
    if run is None:
        return None
    if run.has_active_hard_disqualifier:
        return None

    existing_pending = get_pending_questionnaire(session, application_id)
    if existing_pending is not None:
        return existing_pending

    missing_criteria = _required_unresolved_criteria(session, run)
    if not missing_criteria:
        _move_to_ready_for_phone_review(session, application)
        return None

    return _generate_and_send_questionnaire(session, application, run, missing_criteria)


def _generate_and_send_questionnaire(
    session: Session, application: m.Application, run: m.PrimaryScreeningRun,
    missing_criteria: list[m.PrimaryScreeningCriterion],
) -> m.MissingEvidenceQuestionnaire:
    questionnaire = m.MissingEvidenceQuestionnaire(
        application_id=application.id, primary_screening_run_id=run.id, token=secrets.token_urlsafe(24),
        status=jpm.QUESTIONNAIRE_PENDING,
    )
    session.add(questionnaire)
    session.flush()

    for order, criterion in enumerate(missing_criteria):
        question_text = criterion.missing_evidence_question_text or (
            f"We could not determine \"{criterion.name}\" from your application. Could you tell us more?"
        )
        session.add(m.MissingEvidenceQuestion(
            questionnaire_id=questionnaire.id, criterion_id=criterion.id, question_text=question_text,
            display_order=order,
        ))
    session.flush()

    # Task §24 — no prior Selezionatore approval required.
    template = tmpl_svc.find_best_template(
        session, restaurant_id=application.restaurant_id, trigger_event=cm.TRIGGER_MISSING_EVIDENCE_QUESTIONNAIRE,
        stage=application.current_stage, role=application.target_role,
    )
    if template is not None:
        comm_svc.send_communication(
            session, application, template, trigger_event=cm.TRIGGER_MISSING_EVIDENCE_QUESTIONNAIRE,
            performed_by="SYSTEM_AUTOMATIC",
            extra_context={"missing_evidence_link": f"/missing-evidence/{questionnaire.token}"},
        )
    return questionnaire


def resolve_questionnaire_token(session: Session, token: str) -> m.MissingEvidenceQuestionnaire | None:
    return session.scalars(
        select(m.MissingEvidenceQuestionnaire).where(m.MissingEvidenceQuestionnaire.token == token)
    ).first()


def list_questions(session: Session, questionnaire_id: int) -> list[m.MissingEvidenceQuestion]:
    stmt = (
        select(m.MissingEvidenceQuestion)
        .where(m.MissingEvidenceQuestion.questionnaire_id == questionnaire_id)
        .order_by(m.MissingEvidenceQuestion.display_order)
    )
    return list(session.scalars(stmt).all())


# ---------------------------------------------------------------------------
# Answer submission (task §27) — converts answers into Primary Screening
# evidence without ever overwriting what is already on record, then
# re-checks readiness.
# ---------------------------------------------------------------------------

def submit_answers(session: Session, questionnaire_id: int, answers: dict[int, str]) -> m.MissingEvidenceQuestionnaire:
    """`answers` maps `MissingEvidenceQuestion.id` -> raw candidate answer
    text. Task §27 — preserves each raw answer, converts it into Primary
    Screening evidence via `primary_screening_service.
    apply_self_reported_evidence` (a level is set only when this
    Criterion's own `missing_evidence_answer_level_map` resolves the exact
    raw answer — never fabricated otherwise), and never overwrites
    already-recorded evidence (that function's own guard against
    overwriting a HUMAN_* origin). Finishes by re-running the readiness
    check (task §28) — a second Missing-Evidence round is possible in
    principle, but never for a Criterion already answered once, since its
    Evaluation status will no longer be NOT_EVALUATED/INSUFFICIENT_EVIDENCE
    once a level was resolved."""

    questionnaire = session.get(m.MissingEvidenceQuestionnaire, questionnaire_id)
    if questionnaire is None:
        raise ValueError(f"No MissingEvidenceQuestionnaire with id {questionnaire_id}")

    for question in list_questions(session, questionnaire_id):
        raw_answer = answers.get(question.id)
        if raw_answer is None:
            continue
        session.add(m.MissingEvidenceAnswer(question_id=question.id, raw_answer=raw_answer))
        session.flush()

        evaluation = ps_svc.get_evaluation_for_criterion(session, questionnaire.primary_screening_run_id, question.criterion_id)
        if evaluation is not None:
            level = question.criterion.missing_evidence_answer_level_map.get(raw_answer)
            ps_svc.apply_self_reported_evidence(
                session, evaluation.id,
                evidence_text=f"Missing-Evidence Questionnaire — \"{question.question_text}\": {raw_answer}",
                level=level,
            )

    questionnaire.status = jpm.QUESTIONNAIRE_ANSWERED
    questionnaire.completed_at = datetime.utcnow()
    session.flush()

    process_application_readiness(session, questionnaire.application_id)
    return questionnaire
