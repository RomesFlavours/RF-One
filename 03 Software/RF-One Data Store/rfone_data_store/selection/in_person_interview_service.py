"""In-Person Interview + Practical Assessment + Consistency Engine —
service layer (Task 4B). Runtime orchestration combining Selection Core's
In-Person vocabulary (`core/in_person_interview_model.py`) with the
existing Fit Assessment (`fit_assessment_service.py`) and Selection Signal
(`signal_service.py`) evidence models, plus the Task 4A Phone Interview
framework (`phone_interview_service.py`) for carry-forward. Flask routes
should call into this module rather than touching `.. models` directly.

Fundamental boundaries this module enforces:

- An In-Person Interview Plan stays pinned to the SAME immutable
  `RequirementSetSnapshot`/`FitAssessment` already used at résumé (and, if
  present, Phone Interview) stage — never repointed to a newer live
  Requirement Set (task §1).
- Interview structure (Sections + Assessment Items) is entirely
  restaurant-configured (task §2/§3/§24) — nothing here hard-codes one
  universal interview sequence.
- An interview answer/observation/practical result becomes Fit Assessment/
  Signal EVIDENCE only through an explicit call into
  `fit_assessment_service.add_evidence()`/`signal_service.add_evidence()`
  (task §8/§17/§18) — no parallel evidence system is introduced here.
- The Consistency Engine (task §8-§14) compares raw statements across
  sources and records a NEUTRAL comparison status plus a plain factual
  explanation — it NEVER concludes dishonesty, deception, or manipulation
  (task §12); that judgment, if any, belongs to the Selezionatore alone.
- Nothing here produces a numeric score, rank, or automatic hiring
  decision (task §25/§26) — Task 4B stops at complete evidence collection.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as m
from . import application_service as app_svc
from . import fit_assessment_service as fa_svc
from . import phone_interview_service as pi_svc
from . import signal_service as sig_svc
from .core import application_model as apm  # noqa: F401  (re-exported convenience for callers)
from .core import fit_assessment_model as fam
from .core import in_person_interview_model as ipm
from .core import phone_interview_model as pim
from .core import requirement_model as rm


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _validate_importance(value: str) -> None:
    if value not in ipm.IMPORTANCE_LEVELS:
        raise ValueError(f"Unknown importance {value!r}; expected one of {ipm.IMPORTANCE_LEVELS}")


def _validate_section_kind(value: str) -> None:
    if value not in ipm.SECTION_KINDS:
        raise ValueError(f"Unknown Section kind {value!r}; expected one of {ipm.SECTION_KINDS}")


def _validate_item_type(value: str) -> None:
    if value not in ipm.ASSESSMENT_ITEM_TYPES:
        raise ValueError(f"Unknown Assessment Item type {value!r}; expected one of {ipm.ASSESSMENT_ITEM_TYPES}")


# ---------------------------------------------------------------------------
# In-Person Interview Section Definitions (task §2/§24) — restaurant-
# configurable, reorderable, activatable/deactivatable, by role/context.
# ---------------------------------------------------------------------------

def create_section_definition(
    session: Session, *, restaurant_id: int | None, name: str, section_kind: str = ipm.OTHER_SECTION_KIND,
    target_role: str | None = None, description: str | None = None, display_order: int | None = None,
) -> m.InPersonInterviewSectionDefinition:
    _validate_section_kind(section_kind)
    if display_order is None:
        display_order = session.scalar(
            select(func.count()).select_from(m.InPersonInterviewSectionDefinition)
            .where(m.InPersonInterviewSectionDefinition.restaurant_id == restaurant_id)
        )
    section = m.InPersonInterviewSectionDefinition(
        restaurant_id=restaurant_id, name=name, section_kind=section_kind, target_role=target_role,
        description=description, display_order=display_order,
    )
    session.add(section)
    session.flush()
    return section


def list_section_definitions(
    session: Session, *, restaurant_id: int | None = None, target_role: str | None = None, active_only: bool = True,
) -> list[m.InPersonInterviewSectionDefinition]:
    stmt = select(m.InPersonInterviewSectionDefinition).order_by(m.InPersonInterviewSectionDefinition.display_order)
    if restaurant_id is not None:
        stmt = stmt.where(m.InPersonInterviewSectionDefinition.restaurant_id == restaurant_id)
    if target_role is not None:
        stmt = stmt.where(m.InPersonInterviewSectionDefinition.target_role == target_role)
    if active_only:
        stmt = stmt.where(m.InPersonInterviewSectionDefinition.is_active.is_(True))
    return list(session.scalars(stmt).all())


def get_section_definition(session: Session, section_id: int) -> m.InPersonInterviewSectionDefinition | None:
    return session.get(m.InPersonInterviewSectionDefinition, section_id)


def update_section_definition(session: Session, section_id: int, **fields) -> m.InPersonInterviewSectionDefinition:
    section = session.get(m.InPersonInterviewSectionDefinition, section_id)
    if section is None:
        raise ValueError(f"No InPersonInterviewSectionDefinition with id {section_id}")

    allowed = {"name", "section_kind", "target_role", "description", "display_order", "is_active"}
    for key in fields:
        if key not in allowed:
            raise ValueError(f"Cannot set {key!r} on an InPersonInterviewSectionDefinition through update_section_definition")
    if "section_kind" in fields:
        _validate_section_kind(fields["section_kind"])

    for key, value in fields.items():
        setattr(section, key, value)
    if fields:
        section.version += 1
    session.flush()
    return section


def deactivate_section_definition(session: Session, section_id: int) -> m.InPersonInterviewSectionDefinition:
    return update_section_definition(session, section_id, is_active=False)


def reactivate_section_definition(session: Session, section_id: int) -> m.InPersonInterviewSectionDefinition:
    return update_section_definition(session, section_id, is_active=True)


# ---------------------------------------------------------------------------
# Assessment Item Definitions (task §3/§24) — belong to one Section.
# ---------------------------------------------------------------------------

def create_item_definition(
    session: Session, section_id: int, *, item_type: str, title_or_question: str, instruction: str | None = None,
    scenario: str | None = None, objective: str | None = None, linked_requirement_ids: list[int] | None = None,
    linked_signal_definition_ids: list[int] | None = None, importance: str = ipm.IMPORTANCE_LEVELS[2],
    mandatory_within_selection_process: bool = False, evidence_expected: str | None = None,
    evidence_positive: str | None = None, evidence_contrary: str | None = None,
    evidence_insufficient: str | None = None, selezionatore_instructions: str | None = None,
    display_order: int | None = None,
) -> m.AssessmentItemDefinition:
    _validate_item_type(item_type)
    _validate_importance(importance)

    section = session.get(m.InPersonInterviewSectionDefinition, section_id)
    if section is None:
        raise ValueError(f"No InPersonInterviewSectionDefinition with id {section_id}")

    if display_order is None:
        display_order = session.scalar(
            select(func.count()).select_from(m.AssessmentItemDefinition)
            .where(m.AssessmentItemDefinition.section_id == section_id)
        )

    item = m.AssessmentItemDefinition(
        section_id=section_id, item_type=item_type, title_or_question=title_or_question, instruction=instruction,
        scenario=scenario, objective=objective, linked_requirement_ids=list(linked_requirement_ids or []),
        linked_signal_definition_ids=list(linked_signal_definition_ids or []), importance=importance,
        mandatory_within_selection_process=mandatory_within_selection_process, evidence_expected=evidence_expected,
        evidence_positive=evidence_positive, evidence_contrary=evidence_contrary,
        evidence_insufficient=evidence_insufficient, selezionatore_instructions=selezionatore_instructions,
        display_order=display_order,
    )
    session.add(item)
    session.flush()
    return item


def list_item_definitions(
    session: Session, *, section_id: int | None = None, active_only: bool = True,
) -> list[m.AssessmentItemDefinition]:
    stmt = select(m.AssessmentItemDefinition).order_by(m.AssessmentItemDefinition.display_order)
    if section_id is not None:
        stmt = stmt.where(m.AssessmentItemDefinition.section_id == section_id)
    if active_only:
        stmt = stmt.where(m.AssessmentItemDefinition.is_active.is_(True))
    return list(session.scalars(stmt).all())


def get_item_definition(session: Session, item_id: int) -> m.AssessmentItemDefinition | None:
    return session.get(m.AssessmentItemDefinition, item_id)


def update_item_definition(session: Session, item_id: int, **fields) -> m.AssessmentItemDefinition:
    item = session.get(m.AssessmentItemDefinition, item_id)
    if item is None:
        raise ValueError(f"No AssessmentItemDefinition with id {item_id}")

    allowed = {
        "item_type", "title_or_question", "instruction", "scenario", "objective", "linked_requirement_ids",
        "linked_signal_definition_ids", "importance", "mandatory_within_selection_process", "evidence_expected",
        "evidence_positive", "evidence_contrary", "evidence_insufficient", "selezionatore_instructions",
        "display_order", "is_active",
    }
    for key in fields:
        if key not in allowed:
            raise ValueError(f"Cannot set {key!r} on an AssessmentItemDefinition through update_item_definition")
    if "item_type" in fields:
        _validate_item_type(fields["item_type"])
    if "importance" in fields:
        _validate_importance(fields["importance"])
    if "linked_requirement_ids" in fields:
        fields["linked_requirement_ids"] = list(fields["linked_requirement_ids"])
    if "linked_signal_definition_ids" in fields:
        fields["linked_signal_definition_ids"] = list(fields["linked_signal_definition_ids"])

    for key, value in fields.items():
        setattr(item, key, value)
    if fields:
        item.version += 1
    session.flush()
    return item


def deactivate_item_definition(session: Session, item_id: int) -> m.AssessmentItemDefinition:
    return update_item_definition(session, item_id, is_active=False)


def reactivate_item_definition(session: Session, item_id: int) -> m.AssessmentItemDefinition:
    return update_item_definition(session, item_id, is_active=True)


# ---------------------------------------------------------------------------
# In-Person Interview Plan (task §1)
# ---------------------------------------------------------------------------

def get_plan(session: Session, plan_id: int) -> m.InPersonInterviewPlan | None:
    return session.get(m.InPersonInterviewPlan, plan_id)


def get_plan_for_application(session: Session, application_id: int) -> m.InPersonInterviewPlan | None:
    stmt = select(m.InPersonInterviewPlan).where(m.InPersonInterviewPlan.application_id == application_id)
    return session.scalars(stmt).first()


def _next_display_order(session: Session, plan_id: int) -> int:
    """A fresh COUNT query, deliberately not a loaded relationship
    collection — see `requirements_service.add_requirement`'s own matching
    comment for why."""

    return session.scalar(
        select(func.count()).select_from(m.AssessmentItemInstance)
        .where(m.AssessmentItemInstance.plan_id == plan_id)
    ) or 0


def _resolve_snapshot_requirement_ids(snapshot: m.RequirementSetSnapshot, live_requirement_ids: list[int]) -> list[int]:
    """Same best-effort resolution `phone_interview_service.py` uses: an
    Assessment Item Definition links LIVE `Requirement` rows; an Assessment
    Item INSTANCE must instead point at this plan's own immutable
    `RequirementSnapshotItem` rows."""

    if not live_requirement_ids:
        return []
    wanted = set(live_requirement_ids)
    return [item.id for item in snapshot.items if item.source_requirement_id in wanted]


def create_plan(session: Session, application_id: int) -> m.InPersonInterviewPlan:
    """Creates (or returns the already-existing) In-Person Interview Plan
    for this Application (task §1/test A) — idempotent, mirroring
    `phone_interview_service.create_plan`'s own dedupe convention. Requires
    an existing Fit Assessment (same precondition Phone Interview uses);
    links the existing Phone Interview Plan, where one exists, so its
    unresolved items can be carried forward (task §4)."""

    existing = get_plan_for_application(session, application_id)
    if existing is not None:
        return existing

    application = session.get(m.Application, application_id)
    if application is None:
        raise ValueError(f"No Application with id {application_id}")

    fit_assessments = fa_svc.list_fit_assessments_for_candidate(session, application.candidate_id)
    if not fit_assessments:
        raise ValueError(
            "Cannot create an In-Person Interview Plan before a Fit Assessment exists for this Application "
            "(the plan must stay bound to the same immutable Requirement Set snapshot the Fit Assessment used)."
        )
    fit_assessment = fit_assessments[0]
    phone_plan = pi_svc.get_plan_for_application(session, application_id)

    plan = m.InPersonInterviewPlan(
        application_id=application.id, person_id=application.person_id, candidate_id=application.candidate_id,
        restaurant_id=application.restaurant_id, requirement_set_snapshot_id=fit_assessment.requirement_set_snapshot_id,
        fit_assessment_id=fit_assessment.id, phone_interview_plan_id=(phone_plan.id if phone_plan else None),
    )
    session.add(plan)
    session.flush()

    generate_plan_items(session, plan.id)
    return plan


# Phone Interview statuses eligible for automatic carry-forward into the
# In-Person plan (task §4) — the same statuses Task 4A's own carry-forward
# logic targets, plus CARRIED_FORWARD itself (already flagged unresolved by
# a completed Phone Interview).
_PHONE_CARRY_FORWARD_STATUSES = (pim.NOT_ASKED, pim.PARTIALLY_ANSWERED, pim.UNRESOLVED, pim.CARRIED_FORWARD)


def _add_carry_forward_items(session: Session, plan: m.InPersonInterviewPlan) -> list[m.AssessmentItemInstance]:
    """Task §4 — automatically brings forward relevant Phone Interview
    items left NOT_ASKED/PARTIALLY_ANSWERED/UNRESOLVED/CARRIED_FORWARD,
    preserving the original question, original answer (if any), why it
    remains unresolved, its Requirement/Signal link, and its original
    importance. Never loses the Phone Interview's own evidence — the
    Phone Interview Question Instance row itself is left completely
    untouched."""

    if plan.phone_interview_plan_id is None:
        return []

    already_carried: set[int] = set(
        session.scalars(
            select(m.AssessmentItemInstance.source_phone_question_instance_id).where(
                m.AssessmentItemInstance.plan_id == plan.id,
                m.AssessmentItemInstance.source_type == ipm.CARRY_FORWARD_ITEM,
            )
        ).all()
    )

    phone_items = [
        q for q in pi_svc.list_question_instances(session, plan.phone_interview_plan_id)
        if q.status in _PHONE_CARRY_FORWARD_STATUSES and q.source_type != pim.COURTESY
        and q.id not in already_carried
    ]

    created = []
    for phone_item in phone_items:
        reason = phone_item.carried_forward_reason or (
            f"Carried forward from the Phone Interview (was {phone_item.status})."
        )
        instance = m.AssessmentItemInstance(
            plan_id=plan.id, source_type=ipm.CARRY_FORWARD_ITEM, source_phone_question_instance_id=phone_item.id,
            section_name="Carry-Forward from Phone Interview", section_kind=ipm.CARRY_FORWARD,
            section_display_order=-1,  # Always first (task §4: "should appear early").
            title_or_question=phone_item.question_text, objective=phone_item.objective,
            linked_requirement_ids=list(phone_item.linked_requirement_ids or []),
            linked_signal_definition_ids=list(phone_item.linked_signal_definition_ids or []),
            importance=phone_item.importance, mandatory_within_selection_process=phone_item.mandatory_within_selection_process,
            display_order=_next_display_order(session, plan.id), reason_for_inclusion=reason,
            raw_response=phone_item.answer_text,
        )
        session.add(instance)
        session.flush()
        created.append(instance)
    return created


def _add_section_items(session: Session, plan: m.InPersonInterviewPlan) -> list[m.AssessmentItemInstance]:
    """Task §2/§3 — every active, role-matching restaurant Section's active
    Assessment Items not already present in this plan."""

    application = session.get(m.Application, plan.application_id)
    snapshot = session.get(m.RequirementSetSnapshot, plan.requirement_set_snapshot_id)

    already_present = set(
        session.scalars(
            select(m.AssessmentItemInstance.source_item_definition_id).where(
                m.AssessmentItemInstance.plan_id == plan.id,
                m.AssessmentItemInstance.source_item_definition_id.is_not(None),
            )
        ).all()
    )

    sections = [
        s for s in list_section_definitions(session, restaurant_id=plan.restaurant_id, active_only=True)
        if s.target_role is None or s.target_role == application.target_role
    ]

    created = []
    for section in sections:
        for definition in list_item_definitions(session, section_id=section.id, active_only=True):
            if definition.id in already_present:
                continue
            instance = m.AssessmentItemInstance(
                plan_id=plan.id, source_type=definition.item_type, source_item_definition_id=definition.id,
                section_name=section.name, section_kind=section.section_kind,
                section_display_order=section.display_order, title_or_question=definition.title_or_question,
                instruction=definition.instruction, scenario=definition.scenario, objective=definition.objective,
                linked_requirement_ids=_resolve_snapshot_requirement_ids(snapshot, definition.linked_requirement_ids),
                linked_signal_definition_ids=list(definition.linked_signal_definition_ids or []),
                importance=definition.importance,
                mandatory_within_selection_process=definition.mandatory_within_selection_process,
                selezionatore_instructions=definition.selezionatore_instructions,
                display_order=_next_display_order(session, plan.id),
                reason_for_inclusion="Restaurant-configured Assessment Item.",
            )
            session.add(instance)
            session.flush()
            created.append(instance)
    return created


def generate_plan_items(session: Session, plan_id: int) -> m.InPersonInterviewPlan:
    """Populates (or tops up) a plan's Carry-Forward + Section items. Safe
    to call more than once — every sub-generator only ever ADDS instances
    not already present."""

    plan = session.get(m.InPersonInterviewPlan, plan_id)
    if plan is None:
        raise ValueError(f"No InPersonInterviewPlan with id {plan_id}")

    _add_carry_forward_items(session, plan)
    _add_section_items(session, plan)
    session.flush()
    return plan


def refresh_plan(session: Session, plan_id: int) -> m.InPersonInterviewPlan:
    """Mirrors `phone_interview_service.refresh_plan`'s own §23 discipline:
    while the interview has not started, safe to drop and rebuild every
    still-NOT_DONE auto-generated item; once started, only appends items
    not already present — an already-answered item's row is never touched."""

    plan = session.get(m.InPersonInterviewPlan, plan_id)
    if plan is None:
        raise ValueError(f"No InPersonInterviewPlan with id {plan_id}")

    if plan.status == ipm.NOT_STARTED:
        stale = session.scalars(
            select(m.AssessmentItemInstance).where(
                m.AssessmentItemInstance.plan_id == plan.id,
                m.AssessmentItemInstance.status == ipm.NOT_DONE,
            )
        ).all()
        for instance in stale:
            session.delete(instance)
        session.flush()

    generate_plan_items(session, plan.id)
    return plan


# ---------------------------------------------------------------------------
# Retrieval / ordering (task §19)
# ---------------------------------------------------------------------------

def list_item_instances(session: Session, plan_id: int) -> list[m.AssessmentItemInstance]:
    stmt = (
        select(m.AssessmentItemInstance)
        .where(m.AssessmentItemInstance.plan_id == plan_id)
        .order_by(m.AssessmentItemInstance.display_order)
    )
    return list(session.scalars(stmt).all())


def get_ordered_remaining_items(session: Session, plan_id: int) -> list[m.AssessmentItemInstance]:
    """Task §19 — orders the still-NOT_DONE items by the restaurant's own
    configured Section order, then importance within a section. Once an
    item has been acted on, it keeps its place in `list_item_instances`'s
    stable history and is never reordered."""

    instances = [q for q in list_item_instances(session, plan_id) if q.status == ipm.NOT_DONE]
    return sorted(
        instances,
        key=lambda q: ipm.item_sort_key(
            section_display_order=q.section_display_order, importance=q.importance, item_display_order=q.display_order,
        ),
    )


def list_incomplete_items(session: Session, plan_id: int) -> list[m.AssessmentItemInstance]:
    """Task §19/§10 — every item left NOT_DONE/PARTIAL/UNRESOLVED, visible
    before any future Final Selection Decision."""

    stmt = (
        select(m.AssessmentItemInstance)
        .where(
            m.AssessmentItemInstance.plan_id == plan_id,
            m.AssessmentItemInstance.status.in_(list(ipm.INCOMPLETE_ITEM_STATUSES)),
        )
        .order_by(m.AssessmentItemInstance.display_order)
    )
    return list(session.scalars(stmt).all())


# ---------------------------------------------------------------------------
# Interview lifecycle (task §9/§19/§21) — the Selezionatore drives every
# transition; nothing here fires on its own. No Escape Route / post-
# interview HOLD-STOP decision exists here (task §26 — not yet built).
# ---------------------------------------------------------------------------

def _touch_in_progress(session: Session, plan: m.InPersonInterviewPlan) -> None:
    if plan.status == ipm.NOT_STARTED:
        plan.status = ipm.IN_PROGRESS
        session.flush()


def start_interview(session: Session, plan_id: int) -> m.InPersonInterviewPlan:
    plan = session.get(m.InPersonInterviewPlan, plan_id)
    if plan is None:
        raise ValueError(f"No InPersonInterviewPlan with id {plan_id}")
    _touch_in_progress(session, plan)
    return plan


def record_response(
    session: Session, item_instance_id: int, *, status: str, raw_response: str | None = None,
    selezionatore_note: str | None = None, confidence: str | None = None,
) -> m.AssessmentItemInstance:
    """The ONE mutation point for an Assessment Item's progress (task §16)
    — RAW INPUT (`raw_response`) is preserved exactly as entered, never
    rewritten; `selezionatore_note` is the separate INTERPRETATION layer.
    Serves every item type uniformly (a candidate answer, a direct
    observation, or a practical-test performance note are all the same
    RAW INPUT concept — task's own grouping). Auto-flips the Plan from
    NOT_STARTED to IN_PROGRESS on first use."""

    if status not in ipm.ASSESSMENT_ITEM_STATUSES:
        raise ValueError(f"Unknown Assessment Item status {status!r}; expected one of {ipm.ASSESSMENT_ITEM_STATUSES}")

    instance = session.get(m.AssessmentItemInstance, item_instance_id)
    if instance is None:
        raise ValueError(f"No AssessmentItemInstance with id {item_instance_id}")

    if instance.started_at is None:
        instance.started_at = datetime.utcnow()
    instance.status = status
    if raw_response is not None:
        instance.raw_response = raw_response
    if selezionatore_note is not None:
        instance.selezionatore_note = selezionatore_note
    if confidence is not None:
        instance.confidence = confidence
    if status in (ipm.DONE, ipm.PARTIAL, ipm.UNRESOLVED, ipm.SKIPPED):
        instance.completed_at = datetime.utcnow()

    plan = session.get(m.InPersonInterviewPlan, instance.plan_id)
    _touch_in_progress(session, plan)
    session.flush()
    return instance


def add_follow_up_item(
    session: Session, parent_item_instance_id: int, *, title_or_question: str, objective: str | None = None,
    importance: str | None = None,
) -> m.AssessmentItemInstance:
    """Task §15 — a follow-up item generated from an incomplete/
    contradictory/vague answer, new evidence, an unresolved Requirement/
    Signal, or a practical performance. Preserves why it was generated via
    `reason_for_inclusion`; the caller decides that text (this function
    never infers a reason on its own)."""

    parent = session.get(m.AssessmentItemInstance, parent_item_instance_id)
    if parent is None:
        raise ValueError(f"No AssessmentItemInstance with id {parent_item_instance_id}")
    if importance is not None:
        _validate_importance(importance)

    instance = m.AssessmentItemInstance(
        plan_id=parent.plan_id, source_type=ipm.QUESTION, section_name=parent.section_name,
        section_kind=parent.section_kind, section_display_order=parent.section_display_order,
        title_or_question=title_or_question, objective=objective,
        linked_requirement_ids=list(parent.linked_requirement_ids or []),
        linked_signal_definition_ids=list(parent.linked_signal_definition_ids or []),
        importance=importance or parent.importance, mandatory_within_selection_process=False,
        display_order=_next_display_order(session, parent.plan_id),
        reason_for_inclusion=f"Follow-up to: \"{parent.title_or_question}\"",
    )
    session.add(instance)
    session.flush()
    return instance


def set_notes(session: Session, plan_id: int, note_text: str | None) -> m.InPersonInterviewPlan:
    plan = session.get(m.InPersonInterviewPlan, plan_id)
    if plan is None:
        raise ValueError(f"No InPersonInterviewPlan with id {plan_id}")
    plan.notes = note_text
    session.flush()
    return plan


def stop_interview(session: Session, plan_id: int, *, plan_status: str) -> m.InPersonInterviewPlan:
    """Task §19/§21/§26 — the Selezionatore may stop at any point; this
    only records the Plan's own process status (COMPLETED/STOPPED_EARLY).
    No Application workflow status is touched and no Final Selection
    Decision is produced (task §26 — not yet built); uncompleted items
    simply stay exactly as they were left (NOT_DONE/PARTIAL/UNRESOLVED),
    visible via `list_incomplete_items`."""

    if plan_status not in ipm.PLAN_STATUSES:
        raise ValueError(f"Unknown In-Person Interview Plan status {plan_status!r}; expected one of {ipm.PLAN_STATUSES}")
    plan = session.get(m.InPersonInterviewPlan, plan_id)
    if plan is None:
        raise ValueError(f"No InPersonInterviewPlan with id {plan_id}")
    plan.status = plan_status
    session.flush()
    return plan


# ---------------------------------------------------------------------------
# Evidence capture (task §8/§17/§18) — bridges an In-Person/Practical
# response into the EXISTING Fit Assessment / Selection Signal evidence
# models. No parallel evidence system is introduced.
# ---------------------------------------------------------------------------

def _evidence_source_type_for(instance: m.AssessmentItemInstance) -> str:
    return fam.PRACTICAL_ASSESSMENT_RESULT if instance.source_type == ipm.PRACTICAL_TEST else fam.IN_PERSON_OBSERVATION


def record_response_as_fit_evidence(
    session: Session, item_instance_id: int, *, requirement_snapshot_item_id: int, evidence_relationship: str,
    evidence_classification: str = fam.FACT, confidence: str = fam.CONFIDENCE_MEDIUM, explanation: str | None = None,
) -> m.EvidenceItem:
    """Turns this Assessment Item's already-captured `raw_response` into
    one `EvidenceItem` on the matching `RequirementAssessment` within the
    plan's own pinned Fit Assessment (task §8/§17) — via
    `fit_assessment_service.add_evidence()` directly. Source type is
    `PRACTICAL_ASSESSMENT_RESULT` for a Practical Test item, otherwise
    `IN_PERSON_OBSERVATION` — all prior résumé/Phone evidence is preserved
    (append-only)."""

    instance = session.get(m.AssessmentItemInstance, item_instance_id)
    if instance is None:
        raise ValueError(f"No AssessmentItemInstance with id {item_instance_id}")
    plan = session.get(m.InPersonInterviewPlan, instance.plan_id)

    requirement_assessment = session.scalars(
        select(m.RequirementAssessment).where(
            m.RequirementAssessment.fit_assessment_id == plan.fit_assessment_id,
            m.RequirementAssessment.requirement_snapshot_item_id == requirement_snapshot_item_id,
        )
    ).first()
    if requirement_assessment is None:
        raise ValueError("No RequirementAssessment for this snapshot item within the plan's own Fit Assessment.")

    source_type = _evidence_source_type_for(instance)
    return fa_svc.add_evidence(
        session, requirement_assessment.id, source_type=source_type, evidence_classification=evidence_classification,
        evidence_relationship=evidence_relationship, confidence=confidence, evidence_text=instance.raw_response,
        source_stage=rm.IN_PERSON_INTERVIEW if source_type == fam.IN_PERSON_OBSERVATION else rm.PRACTICAL_ASSESSMENT,
        source_reference=f"AssessmentItemInstance#{instance.id}", explanation=explanation, is_system_generated=False,
    )


def record_response_as_signal_evidence(
    session: Session, item_instance_id: int, *, signal_definition_id: int, evidence_relationship: str,
    evidence_classification: str = fam.FACT, confidence: str = fam.CONFIDENCE_MEDIUM, explanation: str | None = None,
) -> m.SignalEvidenceItem:
    """Task §18 — the Signal-framework counterpart of
    `record_response_as_fit_evidence`. Recomputes Review Priority
    afterward, same as every other Signal-evidence-adding path in this
    codebase; never overwrites previous evidence."""

    instance = session.get(m.AssessmentItemInstance, item_instance_id)
    if instance is None:
        raise ValueError(f"No AssessmentItemInstance with id {item_instance_id}")
    plan = session.get(m.InPersonInterviewPlan, instance.plan_id)

    source_type = _evidence_source_type_for(instance)
    observation = sig_svc.get_or_create_observation(session, plan.application_id, signal_definition_id)
    evidence = sig_svc.add_evidence(
        session, observation.id, source_type=source_type, evidence_classification=evidence_classification,
        evidence_relationship=evidence_relationship, confidence=confidence, evidence_text=instance.raw_response,
        source_stage=rm.IN_PERSON_INTERVIEW if source_type == fam.IN_PERSON_OBSERVATION else rm.PRACTICAL_ASSESSMENT,
        source_reference=f"AssessmentItemInstance#{instance.id}", explanation=explanation, is_system_generated=False,
    )
    sig_svc.compute_and_apply_review_priority(session, plan.application_id)
    return evidence


# ---------------------------------------------------------------------------
# Consistency Engine (task §8-§14) — a Consistency Thread compares one
# topic across multiple sources; a contradiction is evidence, never
# automatic proof of dishonesty.
# ---------------------------------------------------------------------------

def _validate_consistency_status(value: str) -> None:
    if value not in ipm.CONSISTENCY_STATUSES:
        raise ValueError(f"Unknown consistency status {value!r}; expected one of {ipm.CONSISTENCY_STATUSES}")


def _validate_source_stage(value: str) -> None:
    if value not in ipm.CONSISTENCY_SOURCE_STAGES:
        raise ValueError(f"Unknown consistency source stage {value!r}; expected one of {ipm.CONSISTENCY_SOURCE_STAGES}")


def create_consistency_thread(
    session: Session, application_id: int, *, topic: str, importance: str = ipm.IMPORTANCE_LEVELS[2],
) -> m.ConsistencyThread:
    """Task §8/§9 — one topic worth comparing for this Application. Starts
    UNRESOLVED (no comparison has been made yet); never assumes every
    possible topic must be compared — a thread is only ever created for a
    topic someone (a service caller or the Selezionatore) has actually
    identified as worth comparing."""

    _validate_importance(importance)
    application = session.get(m.Application, application_id)
    if application is None:
        raise ValueError(f"No Application with id {application_id}")

    thread = m.ConsistencyThread(
        application_id=application_id, topic=topic, importance=importance, comparison_status=ipm.CONSISTENCY_UNRESOLVED,
    )
    session.add(thread)
    session.flush()
    return thread


def get_thread(session: Session, thread_id: int) -> m.ConsistencyThread | None:
    return session.get(m.ConsistencyThread, thread_id)


def list_threads_for_application(session: Session, application_id: int) -> list[m.ConsistencyThread]:
    stmt = (
        select(m.ConsistencyThread)
        .where(m.ConsistencyThread.application_id == application_id)
        .order_by(m.ConsistencyThread.id)
    )
    return list(session.scalars(stmt).all())


def list_items_to_verify(session: Session, application_id: int) -> list[m.ConsistencyThread]:
    """Task §13 — the most important still-open discrepancies, never the
    full thread list."""

    threads = [
        t for t in list_threads_for_application(session, application_id)
        if t.comparison_status in ipm.CONSISTENCY_ITEMS_TO_VERIFY_STATUSES
    ]
    return sorted(threads, key=lambda t: pim.IMPORTANCE_ORDER.get(t.importance, len(pim.IMPORTANCE_ORDER)))


def add_statement(
    session: Session, thread_id: int, *, source_stage: str, raw_statement: str, source_reference: str | None = None,
    source_date: datetime | None = None, normalized_interpretation: str | None = None,
) -> m.ConsistencyStatement:
    """Appends one source statement — never overwrites or removes an
    existing one (task §10/§16: original statements are never destroyed or
    rewritten)."""

    _validate_source_stage(source_stage)
    thread = session.get(m.ConsistencyThread, thread_id)
    if thread is None:
        raise ValueError(f"No ConsistencyThread with id {thread_id}")

    statement = m.ConsistencyStatement(
        thread_id=thread_id, source_stage=source_stage, source_reference=source_reference, source_date=source_date,
        raw_statement=raw_statement, normalized_interpretation=normalized_interpretation,
    )
    session.add(statement)
    session.flush()
    return statement


def add_statement_from_phone_answer(session: Session, thread_id: int, phone_question_instance_id: int) -> m.ConsistencyStatement:
    """Convenience wrapper: pulls the exact raw answer already captured on
    a Phone Interview Question Instance (task §4/§16 — never re-typed)."""

    phone_item = session.get(m.PhoneInterviewQuestionInstance, phone_question_instance_id)
    if phone_item is None:
        raise ValueError(f"No PhoneInterviewQuestionInstance with id {phone_question_instance_id}")
    return add_statement(
        session, thread_id, source_stage=ipm.PHONE_INTERVIEW, raw_statement=phone_item.answer_text or "",
        source_reference=f"PhoneInterviewQuestionInstance#{phone_item.id}", source_date=phone_item.answered_at,
    )


def add_statement_from_in_person_item(session: Session, thread_id: int, item_instance_id: int) -> m.ConsistencyStatement:
    """Convenience wrapper: pulls the exact raw response already captured
    on an In-Person Assessment Item Instance."""

    item = session.get(m.AssessmentItemInstance, item_instance_id)
    if item is None:
        raise ValueError(f"No AssessmentItemInstance with id {item_instance_id}")
    return add_statement(
        session, thread_id, source_stage=ipm.IN_PERSON_INTERVIEW, raw_statement=item.raw_response or "",
        source_reference=f"AssessmentItemInstance#{item.id}", source_date=item.completed_at or item.started_at,
    )


def add_statement_from_application(
    session: Session, thread_id: int, application_id: int, *, raw_statement: str,
    normalized_interpretation: str | None = None, source_stage: str = ipm.CV_APPLICATION,
) -> m.ConsistencyStatement:
    """Convenience wrapper for a CV/Application (or prior-Application,
    passing `source_stage=PRIOR_APPLICATION`) statement — the statement
    text itself is supplied by the caller (e.g. a specific résumé line or a
    prior Application's own recorded target role), never invented here."""

    application = session.get(m.Application, application_id)
    if application is None:
        raise ValueError(f"No Application with id {application_id}")
    return add_statement(
        session, thread_id, source_stage=source_stage, raw_statement=raw_statement,
        source_reference=f"Application#{application.id}", source_date=application.applied_at,
        normalized_interpretation=normalized_interpretation,
    )


def set_comparison_status(
    session: Session, thread_id: int, *, status: str, explanation: str | None = None,
    confidence: str | None = None, resolution: str | None = None,
) -> m.ConsistencyThread:
    """Task §11/§12 — the ONLY place a Consistency Thread's status is set.
    A deliberate, explicit call (by the Selezionatore, or by a narrow
    deterministic auto-classifier for STRUCTURED facts —
    `generate_cross_application_consistency_threads` below) — free-text
    statement comparison is never auto-judged by this codebase (the same
    conservative rule every prior Selection task already follows: no
    LLM/NLP-based inference). `explanation` must stay a plain factual
    description (task's own example) — never a dishonesty/psychological
    conclusion; this function does not police the text content (that
    would itself require exactly the kind of inference this codebase
    avoids), but nothing in this codebase ever generates such wording."""

    _validate_consistency_status(status)
    thread = session.get(m.ConsistencyThread, thread_id)
    if thread is None:
        raise ValueError(f"No ConsistencyThread with id {thread_id}")

    thread.comparison_status = status
    if explanation is not None:
        thread.explanation = explanation
    if confidence is not None:
        thread.confidence = confidence
    if resolution is not None:
        thread.selezionatore_resolution = resolution
    session.flush()
    return thread


def generate_clarification_item(
    session: Session, plan_id: int, thread_id: int, *, question_text: str | None = None,
) -> m.AssessmentItemInstance:
    """Task §13/§15 — turns a Consistency Thread's own open discrepancy
    into a CONSISTENCY_CHECK Assessment Item the Selezionatore can actually
    ask, preserving both/all original statements via the thread link
    (task's own example clarification-question shape). If `question_text`
    is not supplied, a plain templated one is built by quoting each
    statement's raw text verbatim — never inventing what was said."""

    thread = session.get(m.ConsistencyThread, thread_id)
    if thread is None:
        raise ValueError(f"No ConsistencyThread with id {thread_id}")
    plan = session.get(m.InPersonInterviewPlan, plan_id)
    if plan is None:
        raise ValueError(f"No InPersonInterviewPlan with id {plan_id}")

    if question_text is None:
        quotes = "; ".join(
            f"{s.source_stage.replace('_', ' ').title()}: \"{s.raw_statement}\"" for s in thread.statements
        )
        question_text = (
            f"Regarding {thread.topic.lower()}, I'd like to understand something better. {quotes}. "
            "Can you help me understand how these fit together?"
        )

    instance = m.AssessmentItemInstance(
        plan_id=plan.id, source_type=ipm.CONSISTENCY_CHECK, consistency_thread_id=thread.id,
        section_name="Consistency Check", section_kind=ipm.OTHER_SECTION_KIND, section_display_order=0,
        title_or_question=question_text, objective=f"Clarify the '{thread.topic}' Consistency Thread.",
        importance=thread.importance, display_order=_next_display_order(session, plan.id),
        reason_for_inclusion=thread.explanation or f"Open Consistency Thread: {thread.topic}.",
    )
    session.add(instance)
    session.flush()
    return instance


def generate_cross_application_consistency_threads(session: Session, application_id: int) -> list[m.ConsistencyThread]:
    """Task §14 — deterministic cross-Application comparison, reusing Task
    3C-FIX's own facts-only `application_comparison.compare_applications()`
    (structured, normalized profile facts only — never free-text NLP
    judgment). Each concrete change becomes one thread with a prior/current
    statement pair, classified NEW_INFORMATION (a change is NOT
    automatically negative — task's own instruction); the Selezionatore may
    later reclassify to MATERIAL_INCONSISTENCY via `set_comparison_status`
    if the change itself turns out to matter."""

    from . import persistence
    from .core.application_comparison import compare_applications

    application = session.get(m.Application, application_id)
    if application is None:
        raise ValueError(f"No Application with id {application_id}")

    prior_applications = app_svc.list_prior_applications(session, application_id)
    if not prior_applications:
        return []
    most_recent_prior = prior_applications[-1]

    summary = compare_applications(
        prior_profile=persistence.to_profile(most_recent_prior.candidate), prior_target_role=most_recent_prior.target_role,
        current_profile=persistence.to_profile(application.candidate), current_target_role=application.target_role,
    )
    if not summary.has_material_change:
        return []

    existing_topics = {t.topic for t in list_threads_for_application(session, application_id)}
    created = []
    for change_line in summary.changes:
        topic = f"Cross-Application: {change_line}"
        if topic in existing_topics:
            continue
        thread = create_consistency_thread(session, application_id, topic=topic, importance=ipm.IMPORTANCE_LEVELS[2])
        add_statement_from_application(
            session, thread.id, most_recent_prior.id, raw_statement=change_line, source_stage=ipm.PRIOR_APPLICATION,
        )
        add_statement_from_application(session, thread.id, application.id, raw_statement=change_line)
        set_comparison_status(
            session, thread.id, status=ipm.NEW_INFORMATION,
            explanation=f"New information on a prior Application compared to this one: {change_line}",
        )
        created.append(thread)
    return created
