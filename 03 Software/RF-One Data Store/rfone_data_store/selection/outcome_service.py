"""Selection Outcome service (Task 5A §4-§13/§26-§28). WHAT operational
decision currently applies to an Application — restaurant-configurable,
applicable at ANY moment, never technically irreversible. Kept structurally
separate from `stage_service.py` (WHERE the Application is) and from the
pre-existing `application_service.set_workflow_status` (unchanged).

Mirrors `primary_screening_service.py`'s exact shape: Outcome Definition
CRUD, an immutable-snapshot pattern (`get_or_create_outcome_definition_
snapshot`, identical idempotent-per-version discipline to
`get_or_create_criterion_snapshot`), and an append-only decision/history
table with a convenience "current" pointer on the Application
(`lifecycle_state`) — never the sole record of truth.

Composable actions (task §11) an applied Outcome may execute — deliberately
a SMALL, FIXED set, never a general workflow engine:
  - set `Application.lifecycle_state` (task §6, always)
  - require/validate a Note and/or a reason (task §5/§13)
  - create a `SelectionReminder` (task §5/§11)
  - create a `CandidateFlag` on the person (task §5/§11/§16)
`target_queue_label`/`future_contact_policy` are recorded on the snapshot
and surfaced for display — informational, never an enforced routing/
contact-blocking mechanism (no such infrastructure exists in Selection).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import application_service as app_svc
from . import queue_service as queue_svc
from . import workflow_projection_service as wf_svc
from .core import outcome_model as om
from .core import queue_model as qm

NOTE_CONTEXT_OUTCOME_DECISION = "OUTCOME_DECISION"
NOTE_CONTEXT_CANDIDATE_FLAG = "CANDIDATE_FLAG"


# ---------------------------------------------------------------------------
# Validation helpers.
# ---------------------------------------------------------------------------

def _validate_lifecycle_effect(value: str) -> None:
    om.validate_lifecycle_state(value)


def _validate_future_contact_policy(value: str) -> None:
    if value not in om.FUTURE_CONTACT_POLICIES:
        raise ValueError(f"Unknown future-contact policy {value!r}; expected one of {om.FUTURE_CONTACT_POLICIES}")


def _validate_flag_config(creates_flag: bool, scope: str | None, effect: str | None) -> None:
    if not creates_flag:
        return
    if scope is not None:
        om.validate_flag_scope(scope)
    if effect is not None:
        om.validate_flag_operational_effect(effect)


# ---------------------------------------------------------------------------
# Outcome Definition CRUD (task §4/§5/§30) — restaurant-configurable.
# ---------------------------------------------------------------------------

def create_outcome_definition(
    session: Session, *, restaurant_id: int | None, name: str, description: str | None = None,
    lifecycle_effect: str = om.ACTIVE, is_reopenable: bool = True, requires_note: bool = False,
    requires_reason: bool = False, reason_choices: list[str] | None = None, target_queue_label: str | None = None,
    target_queue_id: int | None = None, creates_reminder: bool = False, reminder_days: int | None = None,
    future_contact_policy: str = om.CONTACT_ALLOWED, creates_candidate_flag: bool = False,
    candidate_flag_name: str | None = None, candidate_flag_scope: str | None = None,
    candidate_flag_operational_effect: str | None = None, candidate_flag_default_reason: str | None = None,
    candidate_flag_expires_after_days: int | None = None, authority_label: str | None = None,
    driven_by: str | None = None, display_order: int | None = None,
) -> m.SelectionOutcomeDefinition:
    _validate_lifecycle_effect(lifecycle_effect)
    _validate_future_contact_policy(future_contact_policy)
    _validate_flag_config(creates_candidate_flag, candidate_flag_scope, candidate_flag_operational_effect)

    if display_order is None:
        from sqlalchemy import func
        display_order = session.scalar(
            select(func.count()).select_from(m.SelectionOutcomeDefinition)
            .where(m.SelectionOutcomeDefinition.restaurant_id == restaurant_id)
        )

    definition = m.SelectionOutcomeDefinition(
        restaurant_id=restaurant_id, name=name, description=description, lifecycle_effect=lifecycle_effect,
        is_reopenable=is_reopenable, requires_note=requires_note, requires_reason=requires_reason,
        reason_choices=list(reason_choices or []), target_queue_label=target_queue_label,
        target_queue_id=target_queue_id,
        creates_reminder=creates_reminder, reminder_days=reminder_days, future_contact_policy=future_contact_policy,
        creates_candidate_flag=creates_candidate_flag, candidate_flag_name=candidate_flag_name,
        candidate_flag_scope=candidate_flag_scope, candidate_flag_operational_effect=candidate_flag_operational_effect,
        candidate_flag_default_reason=candidate_flag_default_reason,
        candidate_flag_expires_after_days=candidate_flag_expires_after_days, authority_label=authority_label,
        driven_by=driven_by, display_order=display_order,
    )
    session.add(definition)
    session.flush()
    return definition


def list_outcome_definitions(
    session: Session, *, restaurant_id: int | None = None, active_only: bool = True,
) -> list[m.SelectionOutcomeDefinition]:
    stmt = select(m.SelectionOutcomeDefinition).order_by(m.SelectionOutcomeDefinition.display_order)
    if restaurant_id is not None:
        stmt = stmt.where(m.SelectionOutcomeDefinition.restaurant_id == restaurant_id)
    if active_only:
        stmt = stmt.where(m.SelectionOutcomeDefinition.is_active.is_(True))
    return list(session.scalars(stmt).all())


def get_outcome_definition(session: Session, definition_id: int) -> m.SelectionOutcomeDefinition | None:
    return session.get(m.SelectionOutcomeDefinition, definition_id)


def update_outcome_definition(session: Session, definition_id: int, **fields) -> m.SelectionOutcomeDefinition:
    definition = session.get(m.SelectionOutcomeDefinition, definition_id)
    if definition is None:
        raise ValueError(f"No SelectionOutcomeDefinition with id {definition_id}")

    allowed = {
        "name", "description", "lifecycle_effect", "is_reopenable", "requires_note", "requires_reason",
        "reason_choices", "target_queue_label", "target_queue_id", "creates_reminder", "reminder_days",
        "future_contact_policy", "creates_candidate_flag", "candidate_flag_name", "candidate_flag_scope",
        "candidate_flag_operational_effect", "candidate_flag_default_reason", "candidate_flag_expires_after_days",
        "authority_label", "driven_by", "display_order", "is_active",
    }
    for key in fields:
        if key not in allowed:
            raise ValueError(f"Cannot set {key!r} on a SelectionOutcomeDefinition through update_outcome_definition")
    if "lifecycle_effect" in fields:
        _validate_lifecycle_effect(fields["lifecycle_effect"])
    if "future_contact_policy" in fields:
        _validate_future_contact_policy(fields["future_contact_policy"])
    if "reason_choices" in fields:
        fields["reason_choices"] = list(fields["reason_choices"])
    creates_flag = fields.get("creates_candidate_flag", definition.creates_candidate_flag)
    scope = fields.get("candidate_flag_scope", definition.candidate_flag_scope)
    effect = fields.get("candidate_flag_operational_effect", definition.candidate_flag_operational_effect)
    _validate_flag_config(creates_flag, scope, effect)

    for key, value in fields.items():
        setattr(definition, key, value)
    if fields:
        definition.version += 1
    session.flush()
    return definition


def deactivate_outcome_definition(session: Session, definition_id: int) -> m.SelectionOutcomeDefinition:
    return update_outcome_definition(session, definition_id, is_active=False)


def reactivate_outcome_definition(session: Session, definition_id: int) -> m.SelectionOutcomeDefinition:
    return update_outcome_definition(session, definition_id, is_active=True)


# ---------------------------------------------------------------------------
# Immutable snapshots (task §28) — mirrors
# `primary_screening_service.get_or_create_criterion_snapshot()` exactly.
# ---------------------------------------------------------------------------

def get_or_create_outcome_definition_snapshot(session: Session, definition_id: int) -> m.SelectionOutcomeDefinitionSnapshot:
    definition = session.get(m.SelectionOutcomeDefinition, definition_id)
    if definition is None:
        raise ValueError(f"No SelectionOutcomeDefinition with id {definition_id}")

    existing = session.scalars(
        select(m.SelectionOutcomeDefinitionSnapshot).where(
            m.SelectionOutcomeDefinitionSnapshot.definition_id == definition_id,
            m.SelectionOutcomeDefinitionSnapshot.version == definition.version,
        )
    ).first()
    if existing is not None:
        return existing

    snapshot = m.SelectionOutcomeDefinitionSnapshot(
        definition_id=definition.id, version=definition.version, restaurant_id=definition.restaurant_id,
        name=definition.name, description=definition.description, lifecycle_effect=definition.lifecycle_effect,
        is_reopenable=definition.is_reopenable, requires_note=definition.requires_note,
        requires_reason=definition.requires_reason, reason_choices=list(definition.reason_choices or []),
        target_queue_label=definition.target_queue_label, target_queue_id=definition.target_queue_id,
        creates_reminder=definition.creates_reminder,
        reminder_days=definition.reminder_days, future_contact_policy=definition.future_contact_policy,
        creates_candidate_flag=definition.creates_candidate_flag, candidate_flag_name=definition.candidate_flag_name,
        candidate_flag_scope=definition.candidate_flag_scope,
        candidate_flag_operational_effect=definition.candidate_flag_operational_effect,
        candidate_flag_default_reason=definition.candidate_flag_default_reason,
        candidate_flag_expires_after_days=definition.candidate_flag_expires_after_days,
        authority_label=definition.authority_label, driven_by=definition.driven_by,
        was_active=definition.is_active,
    )
    session.add(snapshot)
    session.flush()
    return snapshot


def get_snapshot(session: Session, snapshot_id: int) -> m.SelectionOutcomeDefinitionSnapshot | None:
    return session.get(m.SelectionOutcomeDefinitionSnapshot, snapshot_id)


# ---------------------------------------------------------------------------
# Applying an Outcome (task §8/§9/§11/§26) — the ONE function that both
# `apply_outcome` (any lifecycle effect) and `reopen_application` (below)
# funnel through, so every Outcome Decision is created the same way.
# ---------------------------------------------------------------------------

def apply_outcome(
    session: Session, application_id: int, outcome_definition_id: int, *,
    reason: str | None = None, note_text: str | None = None, performed_by: str | None = None,
    performed_by_identity_id: int | None = None,
) -> m.SelectionOutcomeDecision:
    """Applies a restaurant-configured Outcome to an Application (task §9:
    at ANY time, regardless of Stage/completion state). Enforces the
    Outcome's OWN `requires_note`/`requires_reason` configuration (task
    §13) — restaurant-configurable, applies to the FIRST decision made for
    an Application. Executes the Outcome's composable actions (task §11)
    after recording the decision. Never blocks on the Application's
    current Stage (task §10).

    Task 5A-MICRO-FIX §1 — a SEPARATE, non-configurable RF-One governance
    rule layered on top: whenever this call would CHANGE an Application's
    existing effective decision to a genuinely different Outcome (i.e. a
    `SelectionOutcomeDecision` already exists and names a different
    `SelectionOutcomeDefinition` than the one being applied now), a
    non-empty reason is mandatory — regardless of whether the TARGET
    Outcome itself normally requires one (so even reaching HIRABLE, which
    needs no reason on a first decision, requires one when it is reached by
    CHANGING an existing different decision). Re-applying/confirming the
    SAME Outcome again is not a "change" and is unaffected. This mirrors
    `reopen_application`'s own pre-existing "STOP -> reopened" case exactly,
    since a reopen is just one more `apply_outcome` call under the hood."""

    application = session.get(m.Application, application_id)
    if application is None:
        raise ValueError(f"No Application with id {application_id}")

    snapshot = get_or_create_outcome_definition_snapshot(session, outcome_definition_id)
    reason_provided = bool(reason and reason.strip())

    current_decision = get_current_outcome_decision(session, application_id)
    is_changing_existing_decision = (
        current_decision is not None
        and current_decision.outcome_definition_snapshot.definition_id != outcome_definition_id
    )

    if snapshot.requires_reason and not reason_provided:
        raise ValueError(f"The Outcome '{snapshot.name}' requires a reason to be selected.")
    if is_changing_existing_decision and not reason_provided:
        raise ValueError(
            f"Changing the Application's existing decision ('{current_decision.outcome_definition_snapshot.name}' "
            f"-> '{snapshot.name}') requires a reason, regardless of whether '{snapshot.name}' itself normally "
            "requires one."
        )
    if snapshot.requires_note and not (note_text and note_text.strip()):
        raise ValueError(f"The Outcome '{snapshot.name}' requires a Note to be entered.")

    is_reopen_event = application.lifecycle_state == om.CLOSED and snapshot.lifecycle_effect != om.CLOSED

    decision = m.SelectionOutcomeDecision(
        application_id=application_id, outcome_definition_snapshot_id=snapshot.id, reason=reason,
        is_reopen_event=is_reopen_event, performed_by=performed_by,
        performed_by_identity_id=performed_by_identity_id,
    )
    session.add(decision)
    application.lifecycle_state = snapshot.lifecycle_effect
    session.flush()

    if note_text and note_text.strip():
        app_svc.add_note(
            session, application_id, note_text,
            context_type=NOTE_CONTEXT_OUTCOME_DECISION, context_id=decision.id,
        )

    if snapshot.creates_reminder:
        due_date = None
        if snapshot.reminder_days is not None:
            due_date = datetime.utcnow() + timedelta(days=snapshot.reminder_days)
        session.add(m.SelectionReminder(
            application_id=application_id, outcome_decision_id=decision.id, due_date=due_date,
            note_text=f"Follow-up scheduled by Outcome '{snapshot.name}'.",
        ))

    if snapshot.creates_candidate_flag:
        from . import candidate_flag_service as flag_svc

        flag_svc.create_flag(
            session, person_id=application.person_id, restaurant_id=application.restaurant_id,
            name=snapshot.candidate_flag_name or snapshot.name,
            description=f"Automatically created by Outcome '{snapshot.name}'.",
            originating_application_id=application_id, originating_outcome_decision_id=decision.id,
            reason=reason or snapshot.candidate_flag_default_reason,
            scope=snapshot.candidate_flag_scope or om.DEFAULT_FLAG_SCOPE,
            operational_effect=snapshot.candidate_flag_operational_effect or om.DEFAULT_FLAG_OPERATIONAL_EFFECT,
            expires_after_days=snapshot.candidate_flag_expires_after_days, created_by=performed_by,
        )

    # Task 5A-FIX §10/§11 — the target-queue action: only when THIS
    # Outcome's snapshot actually configures one (never invent a queue
    # move otherwise). `require_active=False` — a since-deactivated queue
    # never blocks the Outcome itself from applying (see
    # `queue_service.move_to_queue`'s own docstring).
    if snapshot.target_queue_id:
        queue_svc.move_to_queue(
            session, application_id, snapshot.target_queue_id, source=qm.OUTCOME_ACTION, reason=reason,
            performed_by=performed_by, originating_outcome_decision_id=decision.id, require_active=False,
        )

    session.flush()
    # Task 5A-FIX §1/§2 — the ONLY way apply_outcome ever touches
    # `workflow_status`: a pure, derived refresh of the legacy projection.
    wf_svc.refresh_legacy_workflow_status(session, application_id)
    return decision


def reopen_application(
    session: Session, application_id: int, outcome_definition_id: int, *,
    reason: str | None = None, note_text: str | None = None, performed_by: str | None = None,
    performed_by_identity_id: int | None = None,
) -> m.SelectionOutcomeDecision:
    """Task §7/§10 — a deliberate Selezionatore action that always remains
    possible, even for a CLOSED Application; no Outcome configuration can
    technically block it. The chosen Outcome must itself resolve to ACTIVE
    (an application isn't "reopened" into SUSPENDED/CLOSED) — this is the
    only extra check beyond what `apply_outcome` already enforces."""

    snapshot = get_or_create_outcome_definition_snapshot(session, outcome_definition_id)
    if snapshot.lifecycle_effect != om.ACTIVE:
        raise ValueError(
            f"Reopening requires selecting an Outcome whose lifecycle effect is ACTIVE; "
            f"'{snapshot.name}' resolves to {snapshot.lifecycle_effect}."
        )
    return apply_outcome(
        session, application_id, outcome_definition_id, reason=reason, note_text=note_text, performed_by=performed_by,
        performed_by_identity_id=performed_by_identity_id,
    )


# ---------------------------------------------------------------------------
# Current Outcome + history (task §8) — the current effective Outcome is
# always the most recent decision; never a separately-maintained pointer
# that could drift from the append-only history.
# ---------------------------------------------------------------------------

def get_current_outcome_decision(session: Session, application_id: int) -> m.SelectionOutcomeDecision | None:
    stmt = (
        select(m.SelectionOutcomeDecision)
        .where(m.SelectionOutcomeDecision.application_id == application_id)
        .order_by(m.SelectionOutcomeDecision.id.desc())
    )
    return session.scalars(stmt).first()


def list_outcome_history(session: Session, application_id: int) -> list[m.SelectionOutcomeDecision]:
    stmt = (
        select(m.SelectionOutcomeDecision)
        .where(m.SelectionOutcomeDecision.application_id == application_id)
        .order_by(m.SelectionOutcomeDecision.id)
    )
    return list(session.scalars(stmt).all())


# ---------------------------------------------------------------------------
# Effective Outcome read model (GLOBAL_INTEGRITY_FIX_003 / C-2 §12) — the ONE
# place any consumer (AI evaluator, Dossier/Application display) asks "what
# is/was this Application's Outcome", so no code path reads the stale legacy
# `Application.outcome` scalar directly and mistakes it for current truth.
# ---------------------------------------------------------------------------

SOURCE_GOVERNED_DECISION = "GOVERNED_DECISION"
SOURCE_LEGACY_FIELD = "LEGACY_FIELD"
SOURCE_NONE = "NONE"


@dataclass(frozen=True)
class EffectiveOutcome:
    """`label` is always a display string (or `None` if there is nothing to
    show). `source` makes explicit which record it came from (task §12's
    own "make the source explicit where relevant") — a caller that cares
    about the distinction (e.g. the AI evaluator marking historical
    evidence as legacy) can branch on it; one that doesn't can just render
    `label`."""

    label: str | None
    source: str
    decision: m.SelectionOutcomeDecision | None = None
    legacy_value: str | None = None


def get_effective_application_outcome(session: Session, application_id: int) -> EffectiveOutcome:
    """1. prefer the latest authoritative `SelectionOutcomeDecision`; 2. fall
    back to the historical legacy `Application.outcome` scalar ONLY when no
    governed decision exists at all (task §12/§15 — never fabricate a
    governed decision from the legacy value, never let the legacy value
    outrank a real one)."""

    decision = get_current_outcome_decision(session, application_id)
    if decision is not None:
        return EffectiveOutcome(
            label=decision.outcome_definition_snapshot.name, source=SOURCE_GOVERNED_DECISION, decision=decision,
        )

    application = session.get(m.Application, application_id)
    legacy_value = application.outcome if application is not None else None
    if legacy_value:
        return EffectiveOutcome(label=legacy_value, source=SOURCE_LEGACY_FIELD, legacy_value=legacy_value)

    return EffectiveOutcome(label=None, source=SOURCE_NONE)


def list_reminders_for_application(session: Session, application_id: int, *, unresolved_only: bool = False) -> list[m.SelectionReminder]:
    stmt = select(m.SelectionReminder).where(m.SelectionReminder.application_id == application_id)
    if unresolved_only:
        stmt = stmt.where(m.SelectionReminder.is_resolved.is_(False))
    stmt = stmt.order_by(m.SelectionReminder.id)
    return list(session.scalars(stmt).all())


def list_due_reminders(
    session: Session, restaurant_id: int | None, *, as_of: datetime | None = None,
) -> list[m.SelectionReminder]:
    """Task 5A-ALIGN §6 — the "bring the Application back to the
    Selezionatore's attention" mechanism for a TIME-BASED HOLD: every
    unresolved reminder, across the whole restaurant, whose `due_date` has
    been reached. RF-One only ever SURFACES these — it never makes a
    substantive decision on its own (task's own explicit prohibition).
    A CONDITION-BASED hold (a reminder with no `due_date`) is never
    "due" by this query — nothing in Selection can detect when an
    external condition resolves, so it stays visible only via the
    Application's own unresolved-reminders list until the Selezionatore
    checks and resolves it manually."""

    as_of = as_of or datetime.utcnow()
    stmt = (
        select(m.SelectionReminder)
        .join(m.Application, m.SelectionReminder.application_id == m.Application.id)
        .where(
            m.SelectionReminder.is_resolved.is_(False), m.SelectionReminder.due_date.is_not(None),
            m.SelectionReminder.due_date <= as_of,
        )
    )
    if restaurant_id is not None:
        stmt = stmt.where(m.Application.restaurant_id == restaurant_id)
    stmt = stmt.order_by(m.SelectionReminder.due_date)
    return list(session.scalars(stmt).all())


def resolve_reminder(session: Session, reminder_id: int) -> m.SelectionReminder:
    reminder = session.get(m.SelectionReminder, reminder_id)
    if reminder is None:
        raise ValueError(f"No SelectionReminder with id {reminder_id}")
    reminder.is_resolved = True
    session.flush()
    return reminder
