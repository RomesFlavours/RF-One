"""Phone Interview framework — service layer (Task 4A). Runtime
orchestration combining Selection Core's Phone Interview vocabulary
(`core/phone_interview_model.py`) with the existing Fit Assessment
(`fit_assessment_service.py`) and Selection Signal (`signal_service.py`)
evidence models — the same role those two modules already play for
résumé-stage evidence. Flask routes should call into this module rather
than touching `.. models` directly.

Fundamental boundaries this module enforces:

- A Phone Interview Plan stays pinned to the SAME immutable
  `RequirementSetSnapshot`/`FitAssessment` already used at résumé stage
  (task §1) — it never silently repoints to a newer live Requirement Set.
- Core Questions (restaurant-configured, `PhoneInterviewQuestionDefinition`)
  and Dynamic Questions (candidate-specific, generated here from existing
  Fit Assessment/Signal evidence) are structurally separate sources feeding
  ONE plan (task §2/§11) — a Dynamic Question never replaces a restaurant's
  mandatory Core Question.
- A Question's `importance`/`is_sine_qua_non` order PRESENTATION only —
  nothing here ever produces a candidate score, rank, or automatic hiring
  decision (task §4/§25). A failed Gate never auto-rejects an Application
  (task §6/§7) — only the Selezionatore may activate the Escape Route.
- An interview answer becomes Fit Assessment/Signal EVIDENCE only through
  an explicit call into `fit_assessment_service.add_evidence()`/
  `signal_service.add_evidence()` (task §14/§15) — no parallel evidence
  system is introduced here.
- The post-Phone-Interview ADVANCE_TO_IN_PERSON/HOLD/STOP decision (task
  §22) is now routed through the Task 5A-FIX authoritative Stage/Outcome
  model (`workflow_projection_service.apply_legacy_workflow_action`) —
  ADVANCE_TO_IN_PERSON becomes a Stage transition to IN_PERSON_PRACTICAL;
  HOLD/STOP apply this restaurant's configured HOLD/STOP Outcome.
  `Application.workflow_status` is refreshed only as a resulting
  PROJECTION, never written independently — the Phone Interview Plan's own
  `status` field remains a DIFFERENT thing (the interview PROCESS status,
  task §21) and is never confused with either.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as m
from . import application_service as app_svc
from . import fit_assessment_service as fa_svc
from . import signal_service as sig_svc
from . import workflow_projection_service as wf_svc
from .core import application_model as apm
from .core import fit_assessment_model as fam
from .core import phone_interview_model as pim
from .core import requirement_model as rm
from .core import signal_model as sm


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _validate_importance(value: str) -> None:
    if value not in pim.IMPORTANCE_LEVELS:
        raise ValueError(f"Unknown importance {value!r}; expected one of {pim.IMPORTANCE_LEVELS}")


def _validate_assessment_stages(values: list[str]) -> None:
    unknown = [v for v in values if v not in rm.ASSESSMENT_STAGES]
    if unknown:
        raise ValueError(f"Unknown assessment stage(s) {unknown!r}; expected one of {rm.ASSESSMENT_STAGES}")


def _next_display_order(session: Session, plan_id: int) -> int:
    """A fresh COUNT query, deliberately not a loaded relationship
    collection — see `requirements_service.add_requirement`'s own matching
    comment for why: a sibling row added earlier in this session via a raw
    FK assignment never updates an already-loaded collection in memory."""

    return session.scalar(
        select(func.count()).select_from(m.PhoneInterviewQuestionInstance)
        .where(m.PhoneInterviewQuestionInstance.plan_id == plan_id)
    ) or 0


# ---------------------------------------------------------------------------
# Core Question Definitions (task §3/§18/§24) — restaurant-configurable
# library. `is_courtesy=True` marks a short Escape Route closing question
# (task §7) rather than an ordinary Core Question; both share this table
# since they are structurally identical configuration data.
# ---------------------------------------------------------------------------

def create_question_definition(
    session: Session, *, restaurant_id: int | None, question_text: str, importance: str = pim.MEDIUM,
    target_role: str | None = None, objective: str | None = None, linked_requirement_ids: list[int] | None = None,
    linked_signal_definition_ids: list[int] | None = None, is_sine_qua_non: bool = False,
    mandatory_within_selection_process: bool = False, assessment_stages: list[str] | None = None,
    follow_up_guidance: str | None = None, is_courtesy: bool = False, display_order: int | None = None,
) -> m.PhoneInterviewQuestionDefinition:
    _validate_importance(importance)
    assessment_stages = list(assessment_stages or [rm.PHONE_INTERVIEW])
    _validate_assessment_stages(assessment_stages)

    if display_order is None:
        display_order = session.scalar(
            select(func.count()).select_from(m.PhoneInterviewQuestionDefinition)
            .where(m.PhoneInterviewQuestionDefinition.restaurant_id == restaurant_id)
        )

    definition = m.PhoneInterviewQuestionDefinition(
        restaurant_id=restaurant_id, target_role=target_role, question_text=question_text, objective=objective,
        linked_requirement_ids=list(linked_requirement_ids or []),
        linked_signal_definition_ids=list(linked_signal_definition_ids or []), importance=importance,
        is_sine_qua_non=is_sine_qua_non, mandatory_within_selection_process=mandatory_within_selection_process,
        assessment_stages=assessment_stages, follow_up_guidance=follow_up_guidance, is_courtesy=is_courtesy,
        display_order=display_order,
    )
    session.add(definition)
    session.flush()
    return definition


def list_question_definitions(
    session: Session, *, restaurant_id: int | None = None, target_role: str | None = None,
    is_courtesy: bool | None = None, active_only: bool = True,
) -> list[m.PhoneInterviewQuestionDefinition]:
    stmt = select(m.PhoneInterviewQuestionDefinition).order_by(m.PhoneInterviewQuestionDefinition.display_order)
    if restaurant_id is not None:
        stmt = stmt.where(m.PhoneInterviewQuestionDefinition.restaurant_id == restaurant_id)
    if target_role is not None:
        stmt = stmt.where(m.PhoneInterviewQuestionDefinition.target_role == target_role)
    if is_courtesy is not None:
        stmt = stmt.where(m.PhoneInterviewQuestionDefinition.is_courtesy.is_(is_courtesy))
    if active_only:
        stmt = stmt.where(m.PhoneInterviewQuestionDefinition.is_active.is_(True))
    return list(session.scalars(stmt).all())


def get_question_definition(session: Session, definition_id: int) -> m.PhoneInterviewQuestionDefinition | None:
    return session.get(m.PhoneInterviewQuestionDefinition, definition_id)


def update_question_definition(session: Session, definition_id: int, **fields) -> m.PhoneInterviewQuestionDefinition:
    definition = session.get(m.PhoneInterviewQuestionDefinition, definition_id)
    if definition is None:
        raise ValueError(f"No PhoneInterviewQuestionDefinition with id {definition_id}")

    allowed = {
        "target_role", "question_text", "objective", "linked_requirement_ids", "linked_signal_definition_ids",
        "importance", "is_sine_qua_non", "mandatory_within_selection_process", "assessment_stages",
        "follow_up_guidance", "is_courtesy", "display_order", "is_active",
    }
    for key in fields:
        if key not in allowed:
            raise ValueError(f"Cannot set {key!r} on a PhoneInterviewQuestionDefinition through update_question_definition")
    if "importance" in fields:
        _validate_importance(fields["importance"])
    if "assessment_stages" in fields:
        _validate_assessment_stages(fields["assessment_stages"])
        fields["assessment_stages"] = list(fields["assessment_stages"])
    if "linked_requirement_ids" in fields:
        fields["linked_requirement_ids"] = list(fields["linked_requirement_ids"])
    if "linked_signal_definition_ids" in fields:
        fields["linked_signal_definition_ids"] = list(fields["linked_signal_definition_ids"])

    for key, value in fields.items():
        setattr(definition, key, value)
    if fields:
        definition.version += 1
    session.flush()
    return definition


def deactivate_question_definition(session: Session, definition_id: int) -> m.PhoneInterviewQuestionDefinition:
    return update_question_definition(session, definition_id, is_active=False)


def reactivate_question_definition(session: Session, definition_id: int) -> m.PhoneInterviewQuestionDefinition:
    return update_question_definition(session, definition_id, is_active=True)


# ---------------------------------------------------------------------------
# Phone Interview Plan (task §1) — begins when an Application reaches
# ADVANCE_TO_PHONE. Pinned to the SAME immutable snapshot/Fit Assessment
# already in use; never repointed to a newer live Requirement Set.
# ---------------------------------------------------------------------------

def get_plan(session: Session, plan_id: int) -> m.PhoneInterviewPlan | None:
    return session.get(m.PhoneInterviewPlan, plan_id)


def get_plan_for_application(session: Session, application_id: int) -> m.PhoneInterviewPlan | None:
    stmt = select(m.PhoneInterviewPlan).where(m.PhoneInterviewPlan.application_id == application_id)
    return session.scalars(stmt).first()


def create_plan(session: Session, application_id: int) -> m.PhoneInterviewPlan:
    """Creates (or returns the already-existing) Phone Interview Plan for
    this Application (task §1/test A) — idempotent, mirroring
    `application_service.create_application`'s own dedupe convention.
    Requires an existing Fit Assessment for this Application's Candidate
    (the plan's whole point is staying bound to the SAME immutable snapshot
    a Fit Assessment already established — task §1); the most recently
    created Fit Assessment is used when more than one exists."""

    existing = get_plan_for_application(session, application_id)
    if existing is not None:
        return existing

    application = session.get(m.Application, application_id)
    if application is None:
        raise ValueError(f"No Application with id {application_id}")

    fit_assessments = fa_svc.list_fit_assessments_for_candidate(session, application.candidate_id)
    if not fit_assessments:
        raise ValueError(
            "Cannot create a Phone Interview Plan before a Fit Assessment exists for this Application "
            "(the plan must stay bound to the same immutable Requirement Set snapshot the Fit Assessment used)."
        )
    fit_assessment = fit_assessments[0]

    plan = m.PhoneInterviewPlan(
        application_id=application.id, person_id=application.person_id, candidate_id=application.candidate_id,
        restaurant_id=application.restaurant_id, requirement_set_snapshot_id=fit_assessment.requirement_set_snapshot_id,
        fit_assessment_id=fit_assessment.id,
    )
    session.add(plan)
    session.flush()

    generate_plan_questions(session, plan.id)
    return plan


def refresh_plan(session: Session, plan_id: int) -> m.PhoneInterviewPlan:
    """Task §23 — allows the plan to refresh if new evidence is added
    before the interview begins. Once the interview has meaningfully
    started (`plan.status` in `PLAN_STARTED_STATUSES`), this only APPENDS
    missing Core Questions / new Dynamic Questions among the remaining
    (NOT_ASKED) ones — it never deletes, reorders, or otherwise touches an
    already-asked question's own row."""

    plan = session.get(m.PhoneInterviewPlan, plan_id)
    if plan is None:
        raise ValueError(f"No PhoneInterviewPlan with id {plan_id}")

    if plan.status == pim.NOT_STARTED:
        # Nothing has been asked yet in this state by definition — safe to
        # drop every still-NOT_ASKED auto-generated question and rebuild
        # from scratch against current evidence/library. Human-added
        # FOLLOW_UP/COURTESY instances cannot exist yet either (they are
        # only ever created once an interview is under way), so nothing of
        # substance is ever discarded here.
        stale = session.scalars(
            select(m.PhoneInterviewQuestionInstance).where(
                m.PhoneInterviewQuestionInstance.plan_id == plan.id,
                m.PhoneInterviewQuestionInstance.source_type.in_([pim.CORE, pim.DYNAMIC]),
                m.PhoneInterviewQuestionInstance.status == pim.NOT_ASKED,
            )
        ).all()
        for instance in stale:
            session.delete(instance)
        session.flush()

    generate_plan_questions(session, plan.id)
    return plan


def _resolve_snapshot_requirement_ids(snapshot: m.RequirementSetSnapshot, live_requirement_ids: list[int]) -> list[int]:
    """Core Question Definitions link LIVE `Requirement` rows (task §3);
    a Question INSTANCE must instead point at THIS plan's own immutable
    `RequirementSnapshotItem` rows (same discipline `FitAssessment` itself
    follows). Best-effort: a live Requirement not present in this
    particular snapshot (e.g. added after the snapshot was captured)
    simply is not linked — never an error, never a fabricated link."""

    if not live_requirement_ids:
        return []
    wanted = set(live_requirement_ids)
    return [item.id for item in snapshot.items if item.source_requirement_id in wanted]


def _add_core_questions(session: Session, plan: m.PhoneInterviewPlan) -> list[m.PhoneInterviewQuestionInstance]:
    """Task §2A/§3/§11 — every active, role-matching restaurant Core
    Question not already present in this plan. A Dynamic Question never
    replaces one of these (task §11)."""

    application = session.get(m.Application, plan.application_id)
    snapshot = session.get(m.RequirementSetSnapshot, plan.requirement_set_snapshot_id)

    already_present = set(
        session.scalars(
            select(m.PhoneInterviewQuestionInstance.source_question_definition_id).where(
                m.PhoneInterviewQuestionInstance.plan_id == plan.id,
                m.PhoneInterviewQuestionInstance.source_type == pim.CORE,
            )
        ).all()
    )

    definitions = list_question_definitions(
        session, restaurant_id=plan.restaurant_id, is_courtesy=False, active_only=True,
    )
    relevant = [
        d for d in definitions
        if d.id not in already_present and (d.target_role is None or d.target_role == application.target_role)
    ]

    created = []
    for definition in relevant:
        instance = m.PhoneInterviewQuestionInstance(
            plan_id=plan.id, source_type=pim.CORE, source_question_definition_id=definition.id,
            question_text=definition.question_text, objective=definition.objective,
            linked_requirement_ids=_resolve_snapshot_requirement_ids(snapshot, definition.linked_requirement_ids),
            linked_signal_definition_ids=list(definition.linked_signal_definition_ids or []),
            importance=definition.importance, is_sine_qua_non=definition.is_sine_qua_non,
            mandatory_within_selection_process=definition.mandatory_within_selection_process,
            display_order=_next_display_order(session, plan.id),
            reason_for_inclusion="Restaurant Core Question.",
            gate_evaluation=(pim.NOT_ASKED_GATE if definition.is_sine_qua_non else None),
        )
        session.add(instance)
        session.flush()
        created.append(instance)
    return created


_CRITICALITY_TO_IMPORTANCE = {
    rm.MUST_HAVE: pim.CRITICAL, rm.DISQUALIFIER: pim.CRITICAL, rm.PREFERRED: pim.HIGH, rm.OPTIONAL: pim.MEDIUM,
}


def _add_dynamic_requirement_questions(session: Session, plan: m.PhoneInterviewPlan) -> list[m.PhoneInterviewQuestionInstance]:
    """Task §10 — Dynamic Questions from NOT_ASSESSED_AT_THIS_STAGE
    Requirements now assessable by PHONE_INTERVIEW, PARTIALLY_EVIDENCED
    Requirements, and CONFLICTING_EVIDENCE Requirements. Every generated
    question retains its source Requirement Snapshot Item and the exact
    reason it was asked (task §10's own "never invent facts")."""

    already_linked_item_ids: set[int] = set()
    for existing in session.scalars(
        select(m.PhoneInterviewQuestionInstance).where(
            m.PhoneInterviewQuestionInstance.plan_id == plan.id,
            m.PhoneInterviewQuestionInstance.source_type == pim.DYNAMIC,
        )
    ):
        already_linked_item_ids.update(existing.linked_requirement_ids or [])

    created = []
    for requirement_assessment in fa_svc.list_requirement_assessments(session, plan.fit_assessment_id):
        item = requirement_assessment.requirement_snapshot_item
        if rm.PHONE_INTERVIEW not in (item.assessment_stages or []):
            continue
        if item.id in already_linked_item_ids:
            continue

        status = requirement_assessment.effective_status
        if status == fam.NOT_ASSESSED_AT_THIS_STAGE:
            question_text = (
                f"Regarding \"{item.name}\": "
                f"{item.description or 'can you tell me more about your experience with this?'}"
            )
            reason = f"'{item.name}' was not assessable from the résumé alone and is now assessable at Phone Interview."
        elif status == fam.PARTIALLY_EVIDENCED:
            question_text = f"I have partial information about \"{item.name}\" from your résumé — can you tell me more?"
            reason = f"'{item.name}' is currently only PARTIALLY_EVIDENCED from the résumé."
        elif status == fam.CONFLICTING_EVIDENCE:
            question_text = (
                f"I noticed some inconsistency in what I have on file related to \"{item.name}\" — "
                f"can you help me understand it?"
            )
            reason = f"'{item.name}' currently has CONFLICTING_EVIDENCE from the résumé."
        else:
            continue

        instance = m.PhoneInterviewQuestionInstance(
            plan_id=plan.id, source_type=pim.DYNAMIC, question_text=question_text,
            objective=f"Assess Requirement '{item.name}'" + (f" ({item.category})." if item.category else "."),
            linked_requirement_ids=[item.id], linked_signal_definition_ids=[],
            importance=_CRITICALITY_TO_IMPORTANCE.get(item.criticality, pim.MEDIUM), is_sine_qua_non=False,
            mandatory_within_selection_process=item.criticality in (rm.MUST_HAVE, rm.DISQUALIFIER),
            display_order=_next_display_order(session, plan.id), reason_for_inclusion=reason,
        )
        session.add(instance)
        session.flush()
        created.append(instance)
    return created


_DYNAMIC_SIGNAL_FAMILIES = (sm.READINESS_RECENCY, sm.MOTIVATION_PERSONAL, sm.MOTIVATION_PROFESSIONAL)
_SIGNAL_STATUS_TO_IMPORTANCE = {sm.CONFLICTING: pim.HIGH, sm.POSSIBLE: pim.MEDIUM}


def _add_dynamic_signal_questions(session: Session, plan: m.PhoneInterviewPlan) -> list[m.PhoneInterviewQuestionInstance]:
    """Task §10 — Dynamic Questions from important Readiness/Recency and
    Motivation Signals still POSSIBLE or CONFLICTING. Never generates a
    psychological diagnosis (task §10/§12) — only a plain clarifying prompt
    that quotes the Signal's own recorded rationale, never an invented one."""

    already_linked_signal_ids: set[int] = set()
    for existing in session.scalars(
        select(m.PhoneInterviewQuestionInstance).where(
            m.PhoneInterviewQuestionInstance.plan_id == plan.id,
            m.PhoneInterviewQuestionInstance.source_type == pim.DYNAMIC,
        )
    ):
        already_linked_signal_ids.update(existing.linked_signal_definition_ids or [])

    created = []
    for observation in sig_svc.list_observations(session, plan.application_id):
        definition = observation.signal_definition
        if definition.signal_family not in _DYNAMIC_SIGNAL_FAMILIES:
            continue
        if observation.status not in (sm.POSSIBLE, sm.CONFLICTING):
            continue
        if definition.id in already_linked_signal_ids:
            continue

        clarifier = observation.rationale or definition.description or definition.name
        question_text = (
            f"I'd like to better understand something related to \"{definition.name}\". "
            f"{clarifier} Can you tell me more?"
        )
        instance = m.PhoneInterviewQuestionInstance(
            plan_id=plan.id, source_type=pim.DYNAMIC, question_text=question_text,
            objective=f"Clarify the '{definition.name}' Signal (currently {observation.status}).",
            linked_requirement_ids=[], linked_signal_definition_ids=[definition.id],
            importance=_SIGNAL_STATUS_TO_IMPORTANCE.get(observation.status, pim.MEDIUM), is_sine_qua_non=False,
            mandatory_within_selection_process=False, display_order=_next_display_order(session, plan.id),
            reason_for_inclusion=f"Signal '{definition.name}' observed as {observation.status}.",
        )
        session.add(instance)
        session.flush()
        created.append(instance)
    return created


_REPEAT_APPLICATION_QUESTION_TEXT = "What changed professionally since your previous application?"


def _add_dynamic_repeat_application_question(session: Session, plan: m.PhoneInterviewPlan) -> m.PhoneInterviewQuestionInstance | None:
    """Task §2/§10 — one Dynamic Question when a facts-only comparison
    against the person's prior Application shows a material change (Task
    3C-FIX's own `core/application_comparison.py`); never infers motivation
    or personality from the mere fact of reapplying."""

    exists = session.scalars(
        select(m.PhoneInterviewQuestionInstance).where(
            m.PhoneInterviewQuestionInstance.plan_id == plan.id,
            m.PhoneInterviewQuestionInstance.question_text == _REPEAT_APPLICATION_QUESTION_TEXT,
        )
    ).first()
    if exists is not None:
        return None

    summary = app_svc.get_application_change_summary(session, plan.application_id)
    if summary is None or not summary.has_material_change:
        return None

    instance = m.PhoneInterviewQuestionInstance(
        plan_id=plan.id, source_type=pim.DYNAMIC, question_text=_REPEAT_APPLICATION_QUESTION_TEXT,
        objective="Understand what changed professionally since the candidate's previous Application.",
        linked_requirement_ids=[], linked_signal_definition_ids=[], importance=pim.MEDIUM, is_sine_qua_non=False,
        mandatory_within_selection_process=False, display_order=_next_display_order(session, plan.id),
        reason_for_inclusion=" ".join(summary.changes),
    )
    session.add(instance)
    session.flush()
    return instance


def generate_plan_questions(session: Session, plan_id: int) -> m.PhoneInterviewPlan:
    """Populates (or tops up) a plan's Core + Dynamic questions. Safe to
    call more than once — every sub-generator only ever ADDS instances not
    already present (task §23's own "append, never delete/reorder")."""

    plan = session.get(m.PhoneInterviewPlan, plan_id)
    if plan is None:
        raise ValueError(f"No PhoneInterviewPlan with id {plan_id}")

    _add_core_questions(session, plan)
    _add_dynamic_requirement_questions(session, plan)
    _add_dynamic_signal_questions(session, plan)
    _add_dynamic_repeat_application_question(session, plan)
    session.flush()
    return plan


# ---------------------------------------------------------------------------
# Retrieval / ordering (task §8/§9/§16)
# ---------------------------------------------------------------------------

def list_question_instances(session: Session, plan_id: int) -> list[m.PhoneInterviewQuestionInstance]:
    stmt = (
        select(m.PhoneInterviewQuestionInstance)
        .where(m.PhoneInterviewQuestionInstance.plan_id == plan_id)
        .order_by(m.PhoneInterviewQuestionInstance.display_order)
    )
    return list(session.scalars(stmt).all())


def get_ordered_remaining_questions(session: Session, plan_id: int) -> list[m.PhoneInterviewQuestionInstance]:
    """Task §8 — GATE QUESTIONS -> CRITICAL -> HIGH -> MEDIUM -> LOW, the
    order in which the SELEZIONATORE should present what remains. Only
    NOT_ASKED questions are reordered this way (task §23 — once asked, a
    question's row is never reordered); use `list_question_instances` for
    the full, stable, insertion-order view (the interview's own history).
    COURTESY questions are excluded — they are offered separately, only
    once the Escape Route is active (`get_courtesy_questions`), never
    intermixed with the ordinary priority-ordered queue."""

    instances = [
        q for q in list_question_instances(session, plan_id)
        if q.status == pim.NOT_ASKED and q.source_type != pim.COURTESY
    ]
    return sorted(
        instances,
        key=lambda q: pim.question_sort_key(
            is_sine_qua_non=q.is_sine_qua_non, importance=q.importance, display_order=q.display_order,
        ),
    )


def get_courtesy_questions(session: Session, plan_id: int) -> list[m.PhoneInterviewQuestionInstance]:
    stmt = (
        select(m.PhoneInterviewQuestionInstance)
        .where(m.PhoneInterviewQuestionInstance.plan_id == plan_id, m.PhoneInterviewQuestionInstance.source_type == pim.COURTESY)
        .order_by(m.PhoneInterviewQuestionInstance.display_order)
    )
    return list(session.scalars(stmt).all())


def get_carried_forward_questions(session: Session, plan_id: int) -> list[m.PhoneInterviewQuestionInstance]:
    stmt = (
        select(m.PhoneInterviewQuestionInstance)
        .where(
            m.PhoneInterviewQuestionInstance.plan_id == plan_id,
            m.PhoneInterviewQuestionInstance.status == pim.CARRIED_FORWARD,
        )
        .order_by(m.PhoneInterviewQuestionInstance.display_order)
    )
    return list(session.scalars(stmt).all())


# ---------------------------------------------------------------------------
# Interview lifecycle (task §8/§9/§21/§23) — the Selezionatore drives every
# transition; nothing here ever fires on its own.
# ---------------------------------------------------------------------------

def _touch_in_progress(session: Session, plan: m.PhoneInterviewPlan) -> None:
    if plan.status == pim.NOT_STARTED:
        plan.status = pim.IN_PROGRESS
        session.flush()


def start_interview(session: Session, plan_id: int) -> m.PhoneInterviewPlan:
    plan = session.get(m.PhoneInterviewPlan, plan_id)
    if plan is None:
        raise ValueError(f"No PhoneInterviewPlan with id {plan_id}")
    _touch_in_progress(session, plan)
    return plan


def record_answer(
    session: Session, question_instance_id: int, *, status: str, answer_text: str | None = None,
    selezionatore_note: str | None = None,
) -> m.PhoneInterviewQuestionInstance:
    """The ONE mutation point for a Question Instance's progress (task §9/
    §13) — the exact raw `answer_text` is preserved as entered, never
    rewritten; `selezionatore_note` stays a separate field (task §13: "keep
    raw response and interpretation separate"). Automatically flips the
    Plan from NOT_STARTED to IN_PROGRESS on first use (task §21)."""

    if status not in pim.QUESTION_INSTANCE_STATUSES:
        raise ValueError(f"Unknown Question Instance status {status!r}; expected one of {pim.QUESTION_INSTANCE_STATUSES}")

    instance = session.get(m.PhoneInterviewQuestionInstance, question_instance_id)
    if instance is None:
        raise ValueError(f"No PhoneInterviewQuestionInstance with id {question_instance_id}")

    if instance.asked_at is None:
        instance.asked_at = datetime.utcnow()
    instance.status = status
    if answer_text is not None:
        instance.answer_text = answer_text
    if selezionatore_note is not None:
        instance.selezionatore_note = selezionatore_note
    if status in (pim.ANSWERED, pim.PARTIALLY_ANSWERED, pim.UNRESOLVED, pim.SKIPPED):
        instance.answered_at = datetime.utcnow()

    plan = session.get(m.PhoneInterviewPlan, instance.plan_id)
    _touch_in_progress(session, plan)
    session.flush()
    return instance


def set_gate_evaluation(
    session: Session, question_instance_id: int, *, gate_evaluation: str, note: str | None = None,
) -> m.PhoneInterviewQuestionInstance:
    """Task §6 — a Gate Question's own evaluation, kept separate from the
    raw answer. Never rejects the Application by itself (task §7) — only
    the Selezionatore's explicit `activate_escape_route` does anything with
    a FAILED gate."""

    if gate_evaluation not in pim.GATE_EVALUATIONS:
        raise ValueError(f"Unknown Gate Evaluation {gate_evaluation!r}; expected one of {pim.GATE_EVALUATIONS}")
    instance = session.get(m.PhoneInterviewQuestionInstance, question_instance_id)
    if instance is None:
        raise ValueError(f"No PhoneInterviewQuestionInstance with id {question_instance_id}")
    if not instance.is_sine_qua_non:
        raise ValueError("Gate Evaluation only applies to a Sine Qua Non Question.")

    instance.gate_evaluation = gate_evaluation
    if note:
        instance.selezionatore_note = note

    plan = session.get(m.PhoneInterviewPlan, instance.plan_id)
    _touch_in_progress(session, plan)
    session.flush()
    return instance


def add_follow_up_question(
    session: Session, parent_question_instance_id: int, *, question_text: str, objective: str | None = None,
    importance: str | None = None,
) -> m.PhoneInterviewQuestionInstance:
    """Task §12 — a follow-up question suggested by the answer just given.
    Captures evidence first; it never labels the candidate (e.g.
    "conflictual", "unreliable") anywhere in the framework itself — that
    judgment, if any, stays with the Selezionatore (task §12's own
    boundary)."""

    parent = session.get(m.PhoneInterviewQuestionInstance, parent_question_instance_id)
    if parent is None:
        raise ValueError(f"No PhoneInterviewQuestionInstance with id {parent_question_instance_id}")
    if importance is not None:
        _validate_importance(importance)

    instance = m.PhoneInterviewQuestionInstance(
        plan_id=parent.plan_id, source_type=pim.FOLLOW_UP, parent_question_instance_id=parent.id,
        question_text=question_text, objective=objective,
        linked_requirement_ids=list(parent.linked_requirement_ids or []),
        linked_signal_definition_ids=list(parent.linked_signal_definition_ids or []),
        importance=importance or parent.importance, is_sine_qua_non=False, mandatory_within_selection_process=False,
        display_order=_next_display_order(session, parent.plan_id),
        reason_for_inclusion=f"Follow-up to: \"{parent.question_text}\"",
    )
    session.add(instance)
    session.flush()
    return instance


def set_notes(session: Session, plan_id: int, note_text: str | None) -> m.PhoneInterviewPlan:
    plan = session.get(m.PhoneInterviewPlan, plan_id)
    if plan is None:
        raise ValueError(f"No PhoneInterviewPlan with id {plan_id}")
    plan.notes = note_text
    session.flush()
    return plan


# ---------------------------------------------------------------------------
# Evidence capture (task §13/§14/§15) — bridges an interview answer into
# the EXISTING Fit Assessment / Selection Signal evidence models. No
# parallel evidence system is introduced.
# ---------------------------------------------------------------------------

def record_answer_as_fit_evidence(
    session: Session, question_instance_id: int, *, requirement_snapshot_item_id: int, evidence_relationship: str,
    evidence_classification: str = fam.FACT, confidence: str = fam.CONFIDENCE_MEDIUM, explanation: str | None = None,
) -> m.EvidenceItem:
    """Turns this Question Instance's already-captured `answer_text` into
    one `EvidenceItem` on the matching `RequirementAssessment` within the
    plan's own pinned Fit Assessment (task §14) — via
    `fit_assessment_service.add_evidence()` directly, never a parallel
    mechanism. Earlier résumé evidence is untouched (append-only)."""

    instance = session.get(m.PhoneInterviewQuestionInstance, question_instance_id)
    if instance is None:
        raise ValueError(f"No PhoneInterviewQuestionInstance with id {question_instance_id}")
    plan = session.get(m.PhoneInterviewPlan, instance.plan_id)

    requirement_assessment = session.scalars(
        select(m.RequirementAssessment).where(
            m.RequirementAssessment.fit_assessment_id == plan.fit_assessment_id,
            m.RequirementAssessment.requirement_snapshot_item_id == requirement_snapshot_item_id,
        )
    ).first()
    if requirement_assessment is None:
        raise ValueError("No RequirementAssessment for this snapshot item within the plan's own Fit Assessment.")

    return fa_svc.add_evidence(
        session, requirement_assessment.id, source_type=fam.PHONE_INTERVIEW_RESPONSE,
        evidence_classification=evidence_classification, evidence_relationship=evidence_relationship,
        confidence=confidence, evidence_text=instance.answer_text, source_stage=rm.PHONE_INTERVIEW,
        source_reference=f"PhoneInterviewQuestionInstance#{instance.id}", explanation=explanation,
        is_system_generated=False,
    )


def record_answer_as_signal_evidence(
    session: Session, question_instance_id: int, *, signal_definition_id: int, evidence_relationship: str,
    evidence_classification: str = fam.FACT, confidence: str = fam.CONFIDENCE_MEDIUM, explanation: str | None = None,
) -> m.SignalEvidenceItem:
    """Task §15 — the Signal-framework counterpart of
    `record_answer_as_fit_evidence`. Recomputes Review Priority afterward
    (same as every other Signal-evidence-adding path in this codebase) —
    never overwrites previous evidence."""

    instance = session.get(m.PhoneInterviewQuestionInstance, question_instance_id)
    if instance is None:
        raise ValueError(f"No PhoneInterviewQuestionInstance with id {question_instance_id}")
    plan = session.get(m.PhoneInterviewPlan, instance.plan_id)

    observation = sig_svc.get_or_create_observation(session, plan.application_id, signal_definition_id)
    evidence = sig_svc.add_evidence(
        session, observation.id, source_type=fam.PHONE_INTERVIEW_RESPONSE, evidence_classification=evidence_classification,
        evidence_relationship=evidence_relationship, confidence=confidence, evidence_text=instance.answer_text,
        source_stage=rm.PHONE_INTERVIEW, source_reference=f"PhoneInterviewQuestionInstance#{instance.id}",
        explanation=explanation, is_system_generated=False,
    )
    sig_svc.compute_and_apply_review_priority(session, plan.application_id)
    return evidence


# ---------------------------------------------------------------------------
# Escape Route (task §7) — an explicit Selezionatore choice only.
# ---------------------------------------------------------------------------

_FALLBACK_COURTESY_QUESTIONS = (
    "Thank you for taking the time to speak with me today — do you have any questions for us?",
    "Is there anything else you'd like us to know before we wrap up?",
)


def _generate_courtesy_questions(session: Session, plan: m.PhoneInterviewPlan) -> list[m.PhoneInterviewQuestionInstance]:
    if get_courtesy_questions(session, plan.id):
        return []  # already generated for this Escape Route activation

    application = session.get(m.Application, plan.application_id)
    definitions = list_question_definitions(session, restaurant_id=plan.restaurant_id, is_courtesy=True, active_only=True)
    relevant = sorted(
        (d for d in definitions if d.target_role is None or d.target_role == application.target_role),
        key=lambda d: d.display_order,
    )[:3]

    created = []
    if relevant:
        for definition in relevant:
            instance = m.PhoneInterviewQuestionInstance(
                plan_id=plan.id, source_type=pim.COURTESY, source_question_definition_id=definition.id,
                question_text=definition.question_text, objective=definition.objective, importance=definition.importance,
                display_order=_next_display_order(session, plan.id),
                reason_for_inclusion="Escape Route — restaurant-configured Courtesy Question.",
            )
            session.add(instance)
            session.flush()
            created.append(instance)
    else:
        # No restaurant-configured Courtesy Question exists yet — a
        # generic, professional closing (task §7.3), never a substitute for
        # restaurant-authored content once it exists.
        for text in _FALLBACK_COURTESY_QUESTIONS:
            instance = m.PhoneInterviewQuestionInstance(
                plan_id=plan.id, source_type=pim.COURTESY, question_text=text, importance=pim.LOW,
                objective="Close the call professionally.", display_order=_next_display_order(session, plan.id),
                reason_for_inclusion=(
                    "Escape Route — no restaurant-configured Courtesy Question available; generic professional "
                    "closing used."
                ),
            )
            session.add(instance)
            session.flush()
            created.append(instance)
    return created


def activate_escape_route(session: Session, plan_id: int, *, reason: str | None = None) -> m.PhoneInterviewPlan:
    """Task §7 — an explicit Selezionatore choice only, never automatic
    (a failed Gate alone never calls this). Stops presenting the full
    remaining plan, preserves every still-unanswered substantive question
    as UNRESOLVED (never deleted — task §16), and offers 2-3 short courtesy
    questions for a professional closing."""

    plan = session.get(m.PhoneInterviewPlan, plan_id)
    if plan is None:
        raise ValueError(f"No PhoneInterviewPlan with id {plan_id}")

    plan.status = pim.ESCAPE_ROUTE
    plan.escape_route_activated_at = datetime.utcnow()
    plan.escape_route_reason = reason
    session.flush()

    remaining = session.scalars(
        select(m.PhoneInterviewQuestionInstance).where(
            m.PhoneInterviewQuestionInstance.plan_id == plan.id,
            m.PhoneInterviewQuestionInstance.status == pim.NOT_ASKED,
            m.PhoneInterviewQuestionInstance.source_type.in_([pim.CORE, pim.DYNAMIC, pim.FOLLOW_UP]),
        )
    ).all()
    for instance in remaining:
        instance.status = pim.UNRESOLVED
    session.flush()

    _generate_courtesy_questions(session, plan)
    return plan


# ---------------------------------------------------------------------------
# Post-Phone-Interview decision + carry-forward (task §16/§17/§22) — the
# Selezionatore alone decides; nothing here fires on its own.
# ---------------------------------------------------------------------------

def _carry_forward_unresolved(session: Session, plan: m.PhoneInterviewPlan) -> list[m.PhoneInterviewQuestionInstance]:
    """Task §16 — every substantive (non-Courtesy) question still
    NOT_ASKED/PARTIALLY_ANSWERED/UNRESOLVED becomes CARRIED_FORWARD,
    preserving the original question, why it remains unresolved, its
    Requirement/Signal link, any prior answer, and its importance — nothing
    is dropped. Task 4A does not implement the In-Person Interview itself;
    this only prepares the carry-forward data cleanly (task §16's own
    scope boundary)."""

    eligible = session.scalars(
        select(m.PhoneInterviewQuestionInstance).where(
            m.PhoneInterviewQuestionInstance.plan_id == plan.id,
            m.PhoneInterviewQuestionInstance.status.in_(list(pim.CARRY_FORWARD_ELIGIBLE_STATUSES)),
            m.PhoneInterviewQuestionInstance.source_type != pim.COURTESY,
        )
    ).all()
    for instance in eligible:
        prior_status = instance.status
        instance.status = pim.CARRIED_FORWARD
        reason_bits = [f"Not resolved during Phone Interview (was {prior_status})."]
        if instance.mandatory_within_selection_process:
            reason_bits.append(
                "Marked mandatory-within-selection-process by the restaurant — must still be addressed "
                "before a final decision (task §17), even though it was not required on the phone call."
            )
        instance.carried_forward_reason = " ".join(reason_bits)
    session.flush()
    return eligible


def record_post_interview_decision(
    session: Session, plan_id: int, *, plan_status: str, application_decision: str, reason: str | None = None,
    performed_by: str | None = None, performed_by_identity_id: int | None = None,
) -> m.PhoneInterviewPlan:
    """The Selezionatore's explicit post-Phone-Interview decision (task
    §22) — never automatic. Closes out the Phone Interview Plan's own
    process status (task §21 — a DIFFERENT thing from the Application's own
    Stage/Outcome), records ADVANCE_TO_IN_PERSON/HOLD/STOP through the Task
    5A-FIX authoritative model (`workflow_projection_service.
    apply_legacy_workflow_action` — a Stage transition for
    ADVANCE_TO_IN_PERSON, the restaurant's configured HOLD/STOP Outcome
    otherwise; `Application.workflow_status` is only ever refreshed as the
    resulting projection, never written independently here), and carries
    every still-unresolved substantive question forward (task §16) so
    nothing important silently disappears. No numeric interview score is
    ever computed or stored (task §25).

    GLOBAL_INTEGRITY_FIX_003 / C-2 §5/§7 — `performed_by_identity_id` is
    forwarded to `apply_legacy_workflow_action` unchanged, so this
    substantive Stage/Outcome-mapped decision carries the same stable
    Acting Identity and triggers the same Candidate Communication
    consequence as the modern Dossier Stage/Outcome controls. The caller
    (`Selection/app.py`'s `phone_interview_decision` route) is responsible
    for resolving the actor and enforcing ownership/authority BEFORE
    calling this function — the same convention every other consequential
    Selection route already follows."""

    if plan_status not in pim.PLAN_STATUSES:
        raise ValueError(f"Unknown Phone Interview Plan status {plan_status!r}; expected one of {pim.PLAN_STATUSES}")
    if application_decision not in apm.POST_PHONE_INTERVIEW_DECISIONS:
        raise ValueError(
            f"Unknown post-Phone-Interview decision {application_decision!r}; "
            f"expected one of {apm.POST_PHONE_INTERVIEW_DECISIONS}"
        )

    plan = session.get(m.PhoneInterviewPlan, plan_id)
    if plan is None:
        raise ValueError(f"No PhoneInterviewPlan with id {plan_id}")

    plan.status = plan_status
    session.flush()
    _carry_forward_unresolved(session, plan)
    wf_svc.apply_legacy_workflow_action(
        session, plan.application_id, application_decision, reason=reason, performed_by=performed_by,
        performed_by_identity_id=performed_by_identity_id,
    )
    session.flush()
    return plan
