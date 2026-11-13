"""Selection Stage service (Task 5A §2/§3). WHERE an Application currently
is in the Selection process — kept structurally separate from
`outcome_service.py` (WHAT operational decision applies) and from the
legacy `application_service.set_workflow_status` (Task 5A-FIX §1/§2: no
longer independently authoritative — `set_stage` below now refreshes it as
a derived PROJECTION automatically, so it can never diverge through this
function).

No "allowed next Stage" validation exists anywhere here: the Selezionatore
has total freedom to move forward, backward, repeat, or skip Stages (task
§2/§10/§32) — `set_stage` accepts any of `core.stage_model.STAGES` as the
new Stage regardless of the current one.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import application_service as app_svc
from . import workflow_projection_service as wf_svc
from .core import stage_model as stgm

NOTE_CONTEXT_STAGE_TRANSITION = "STAGE_TRANSITION"


def set_stage(
    session: Session, application_id: int, new_stage: str, *,
    performed_by: str | None = None, note_text: str | None = None, performed_by_identity_id: int | None = None,
) -> m.ApplicationStageTransition:
    """Records a Stage movement (task §3) and updates the Application's
    convenience `current_stage` pointer. Always creates a NEW transition
    row — never overwrites a prior one, even when moving back to a Stage
    the Application has already been at before (task's own "repeat a
    Stage"). Task 5A-FIX §1/§2: finishes by refreshing the legacy
    `workflow_status` projection so it always reflects the new authoritative
    Stage — this is the ONLY way `set_stage` ever touches that field."""

    stgm.validate_stage(new_stage)
    application = session.get(m.Application, application_id)
    if application is None:
        raise ValueError(f"No Application with id {application_id}")

    transition = m.ApplicationStageTransition(
        application_id=application_id, previous_stage=application.current_stage, new_stage=new_stage,
        performed_by=performed_by, performed_by_identity_id=performed_by_identity_id,
    )
    session.add(transition)
    application.current_stage = new_stage
    session.flush()

    if note_text:
        app_svc.add_note(
            session, application_id, note_text,
            context_type=NOTE_CONTEXT_STAGE_TRANSITION, context_id=transition.id,
        )

    wf_svc.refresh_legacy_workflow_status(session, application_id)
    return transition


def get_current_stage(session: Session, application_id: int) -> str:
    application = session.get(m.Application, application_id)
    if application is None:
        raise ValueError(f"No Application with id {application_id}")
    return application.current_stage


def list_stage_history(session: Session, application_id: int) -> list[m.ApplicationStageTransition]:
    """Every Stage transition for this Application, oldest first — the
    permanent historical record (task §3's own "the historical transitions
    remain permanent"), independent of whatever `current_stage` says now."""

    stmt = (
        select(m.ApplicationStageTransition)
        .where(m.ApplicationStageTransition.application_id == application_id)
        .order_by(m.ApplicationStageTransition.id)
    )
    return list(session.scalars(stmt).all())
