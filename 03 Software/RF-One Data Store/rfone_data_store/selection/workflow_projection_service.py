"""Legacy `workflow_status` compatibility projection (Task 5A-FIX §1-§5).

From this fix onward, the AUTHORITATIVE current Selection state of an
Application is `current_stage` + the current Outcome's `lifecycle_state` —
never `Application.workflow_status`. That field (Task 3C-FIX/4A) is kept,
unchanged in shape, but is downgraded to a derived, one-directional
PROJECTION of the authoritative state:

    authoritative Stage/Outcome/lifecycle  -->  derive/refresh workflow_status

never the reverse. `compute_legacy_workflow_status()` is the ONE place
that mapping is defined; `refresh_legacy_workflow_status()` is called
automatically at the end of both `stage_service.set_stage()` and
`outcome_service.apply_outcome()`, so the legacy field can never drift out
of sync through any normal, supported action (task §22's own "source of
truth" guarantee) — it is still written through the existing
`application_service.set_workflow_status()` function (untouched), just
never called directly by a UI action choosing an arbitrary value anymore.

`apply_legacy_workflow_action()` is the compatibility bridge for the
handful of old UI/routes that still let a Selezionatore pick a legacy
value directly (task §5) — the Review Queue's workflow-status control, and
Phone Interview's post-interview decision (task §18). Each legacy choice
is translated into the equivalent Stage transition and/or Outcome
application using the Task 5A services, never into a direct `workflow_
status` write of its own.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import application_service as app_svc
from .core import application_model as apm
from .core import outcome_model as om
from .core import stage_model as stgm

# ---------------------------------------------------------------------------
# Mapping (task §3) — deliberately minimal. Where the old vocabulary
# cannot map perfectly, the closest legacy representation is chosen and
# documented here rather than left ambiguous:
#
# - CLOSED lifecycle (HIRE, STOP, WITHDRAWN, or any restaurant-authored
#   CLOSED Outcome alike) all collapse to legacy STOP — the only "this
#   Application is not moving forward" value the old vocabulary has; there
#   is no legacy "HIRED".
# - SUSPENDED lifecycle (HOLD, or any restaurant-authored SUSPENDED
#   Outcome) collapses to legacy HOLD.
# - Otherwise (still ACTIVE), the CURRENT STAGE decides: IN_PERSON_PRACTICAL
#   -> ADVANCE_TO_IN_PERSON, PHONE_INTERVIEW -> ADVANCE_TO_PHONE,
#   PRIMARY_SCREENING -> IN_REVIEW, APPLICATION_RECEIVED -> NEW (until the
#   Application has ANY recorded Stage/Outcome activity, at which point it
#   becomes IN_REVIEW instead of staying NEW forever).
# ---------------------------------------------------------------------------

_STAGE_TO_LEGACY_ACTIVE = {
    stgm.IN_PERSON_PRACTICAL: apm.ADVANCE_TO_IN_PERSON,
    stgm.PHONE_INTERVIEW: apm.ADVANCE_TO_PHONE,
    stgm.PRIMARY_SCREENING: apm.IN_REVIEW,
}

# The reverse of the Stage-driven half of the mapping above (task §5) —
# used by `apply_legacy_workflow_action` for the two legacy values that
# name a Stage rather than an Outcome.
_LEGACY_TO_STAGE = {
    apm.ADVANCE_TO_IN_PERSON: stgm.IN_PERSON_PRACTICAL,
    apm.ADVANCE_TO_PHONE: stgm.PHONE_INTERVIEW,
    apm.IN_REVIEW: stgm.PRIMARY_SCREENING,
    apm.NEW: stgm.APPLICATION_RECEIVED,
}

# Legacy values that name an OUTCOME-like decision rather than a Stage —
# resolved to a live Outcome Definition at call time (task §5's own
# examples: "legacy HOLD must apply the configured HOLD Outcome").
_LEGACY_TO_OUTCOME_LIFECYCLE = {
    apm.HOLD: om.SUSPENDED,
    apm.STOP: om.CLOSED,
}
_LEGACY_TO_PREFERRED_OUTCOME_NAMES = {
    apm.HOLD: ("Hold",),
    apm.STOP: ("Stop",),
}


def compute_legacy_workflow_status(session: Session, application_id: int) -> str:
    """The ONE place the Stage/Outcome -> legacy `workflow_status` mapping
    is computed (task §3) — read-only, never writes anything."""

    application = session.get(m.Application, application_id)
    if application is None:
        raise ValueError(f"No Application with id {application_id}")

    if application.lifecycle_state == om.CLOSED:
        return apm.STOP
    if application.lifecycle_state == om.SUSPENDED:
        return apm.HOLD

    stage = application.current_stage
    if stage in _STAGE_TO_LEGACY_ACTIVE:
        return _STAGE_TO_LEGACY_ACTIVE[stage]

    # APPLICATION_RECEIVED, still ACTIVE — NEW until the Application has
    # ANY recorded Stage/Outcome activity (task §6: never fabricate history,
    # but once real activity exists the projection must reflect it).
    has_stage_history = session.scalars(
        select(m.ApplicationStageTransition.id).where(m.ApplicationStageTransition.application_id == application_id)
    ).first() is not None
    has_outcome_history = session.scalars(
        select(m.SelectionOutcomeDecision.id).where(m.SelectionOutcomeDecision.application_id == application_id)
    ).first() is not None
    return apm.IN_REVIEW if (has_stage_history or has_outcome_history) else apm.NEW


def refresh_legacy_workflow_status(session: Session, application_id: int) -> m.Application:
    """Recomputes and, only if it actually changed, rewrites `workflow_
    status` to match the authoritative Stage/Outcome/lifecycle state.
    Called automatically at the end of `stage_service.set_stage()` and
    `outcome_service.apply_outcome()` — this is what makes divergence
    impossible through any normal, supported action (task §22)."""

    application = session.get(m.Application, application_id)
    if application is None:
        raise ValueError(f"No Application with id {application_id}")
    new_status = compute_legacy_workflow_status(session, application_id)
    if application.workflow_status != new_status:
        app_svc.set_workflow_status(session, application_id, new_status)
    return application


def _find_outcome_definition_for_legacy(
    session: Session, restaurant_id: int | None, legacy_status: str,
) -> m.SelectionOutcomeDefinition | None:
    from . import outcome_service as outcome_svc

    lifecycle_effect = _LEGACY_TO_OUTCOME_LIFECYCLE[legacy_status]
    definitions = outcome_svc.list_outcome_definitions(session, restaurant_id=restaurant_id, active_only=True)
    for name in _LEGACY_TO_PREFERRED_OUTCOME_NAMES[legacy_status]:
        match = next((d for d in definitions if d.name.strip().lower() == name.lower()), None)
        if match is not None:
            return match
    return next((d for d in definitions if d.lifecycle_effect == lifecycle_effect), None)


def apply_legacy_workflow_action(
    session: Session, application_id: int, new_status: str, *, reason: str | None = None,
    performed_by: str | None = None,
) -> m.Application:
    """Task 5A-FIX §5/§18/§19 — the ONE compatibility bridge translating a
    legacy `workflow_status` choice into the equivalent authoritative
    Stage transition and/or Outcome application. `workflow_status` itself
    is NEVER written directly here for a restaurant that HAS configured
    Outcomes — the underlying `stage_service.set_stage()`/`outcome_service.
    apply_outcome()` calls already refresh the projection themselves; this
    function's own final refresh call is a belt-and-suspenders
    confirmation, not a second source of truth.

    A HOLD/STOP choice for a restaurant with NO active SUSPENDED/CLOSED
    Outcome Definition configured yet (e.g. one that has never opened the
    Selection Outcomes page) falls back to the pre-5A-FIX direct
    `application_service.set_workflow_status()` write — an honest,
    documented compatibility boundary (task §2's own "existing routes/
    tests/code may still depend on it"), never a crash. Once that
    restaurant has ANY matching Outcome configured (every restaurant that
    has visited the Selection UI does, via idempotent seeding), this
    fallback is never reached again."""

    if new_status not in apm.WORKFLOW_STATUSES:
        raise ValueError(f"Unknown workflow status {new_status!r}; expected one of {apm.WORKFLOW_STATUSES}")
    application = session.get(m.Application, application_id)
    if application is None:
        raise ValueError(f"No Application with id {application_id}")

    if new_status in _LEGACY_TO_STAGE:
        from . import stage_service as stage_svc

        stage_svc.set_stage(
            session, application_id, _LEGACY_TO_STAGE[new_status], performed_by=performed_by,
            note_text=reason,
        )
    elif new_status in _LEGACY_TO_OUTCOME_LIFECYCLE:
        from . import outcome_service as outcome_svc

        definition = _find_outcome_definition_for_legacy(session, application.restaurant_id, new_status)
        if definition is None:
            # No restaurant-configured Outcome to apply yet — fall back to
            # the pre-5A-FIX direct write rather than blocking a
            # Selezionatore action outright (see docstring above).
            return app_svc.set_workflow_status(session, application_id, new_status, reason=reason)
        outcome_svc.apply_outcome(
            session, application_id, definition.id, reason=reason, note_text=reason, performed_by=performed_by,
        )
    else:
        raise ValueError(f"Unsupported legacy workflow status {new_status!r}")

    return refresh_legacy_workflow_status(session, application_id)
