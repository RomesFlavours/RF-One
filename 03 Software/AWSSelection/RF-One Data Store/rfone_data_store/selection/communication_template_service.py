"""Communication Template service (Task 5D §3/§4/§5) — CRUD for the
restaurant-configurable message content, plus the immutable per-version
snapshot every sent `CandidateCommunication` pins to. Mirrors
`outcome_service.py`'s exact Definition/Snapshot shape (`create_outcome_
definition`/`get_or_create_outcome_definition_snapshot`).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from .core import communication_model as cm


def create_template(
    session: Session, *, restaurant_id: int | None, trigger_event: str, location_label: str | None = None,
    role: str | None = None, stage: str | None = None, outcome_definition_id: int | None = None,
    purpose: str | None = None, language: str = "en", sms_text: str | None = None,
    email_subject: str | None = None, email_body: str | None = None,
) -> m.CommunicationTemplate:
    cm.validate_trigger_event(trigger_event)
    template = m.CommunicationTemplate(
        restaurant_id=restaurant_id, location_label=location_label, role=role, stage=stage,
        trigger_event=trigger_event, outcome_definition_id=outcome_definition_id, purpose=purpose,
        language=language, sms_text=sms_text, email_subject=email_subject, email_body=email_body,
    )
    session.add(template)
    session.flush()
    return template


def update_template(session: Session, template_id: int, **fields) -> m.CommunicationTemplate:
    """Task §4 — editing a Template bumps its version; every ALREADY-SENT
    `CandidateCommunication` keeps pointing at the OLD `CommunicationTemplate
    Snapshot` (created for the prior version), so its exact rendered text
    never changes."""

    template = session.get(m.CommunicationTemplate, template_id)
    if template is None:
        raise ValueError(f"No CommunicationTemplate with id {template_id}")

    allowed = {
        "location_label", "role", "stage", "trigger_event", "outcome_definition_id", "purpose", "language",
        "sms_text", "email_subject", "email_body", "notes", "is_active",
    }
    for key in fields:
        if key not in allowed:
            raise ValueError(f"Cannot set {key!r} on a CommunicationTemplate through update_template")
    if "trigger_event" in fields:
        cm.validate_trigger_event(fields["trigger_event"])

    for key, value in fields.items():
        setattr(template, key, value)
    if fields:
        template.version += 1
    session.flush()
    return template


def deactivate_template(session: Session, template_id: int) -> m.CommunicationTemplate:
    return update_template(session, template_id, is_active=False)


def list_templates(
    session: Session, *, restaurant_id: int | None = None, trigger_event: str | None = None,
    active_only: bool = True,
) -> list[m.CommunicationTemplate]:
    stmt = select(m.CommunicationTemplate)
    if restaurant_id is not None:
        stmt = stmt.where(m.CommunicationTemplate.restaurant_id == restaurant_id)
    if trigger_event is not None:
        stmt = stmt.where(m.CommunicationTemplate.trigger_event == trigger_event)
    if active_only:
        stmt = stmt.where(m.CommunicationTemplate.is_active.is_(True))
    stmt = stmt.order_by(m.CommunicationTemplate.id)
    return list(session.scalars(stmt).all())


def get_or_create_template_snapshot(session: Session, template_id: int) -> m.CommunicationTemplateSnapshot:
    template = session.get(m.CommunicationTemplate, template_id)
    if template is None:
        raise ValueError(f"No CommunicationTemplate with id {template_id}")

    existing = session.scalars(
        select(m.CommunicationTemplateSnapshot).where(
            m.CommunicationTemplateSnapshot.template_id == template_id,
            m.CommunicationTemplateSnapshot.version == template.version,
        )
    ).first()
    if existing is not None:
        return existing

    snapshot = m.CommunicationTemplateSnapshot(
        template_id=template.id, version=template.version, restaurant_id=template.restaurant_id,
        location_label=template.location_label, role=template.role, stage=template.stage,
        trigger_event=template.trigger_event, outcome_definition_id=template.outcome_definition_id,
        purpose=template.purpose, language=template.language, sms_text=template.sms_text,
        email_subject=template.email_subject, email_body=template.email_body, was_active=template.is_active,
    )
    session.add(snapshot)
    session.flush()
    return snapshot


def find_best_template(
    session: Session, *, restaurant_id: int | None, trigger_event: str, stage: str | None = None,
    role: str | None = None, location_label: str | None = None, outcome_definition_id: int | None = None,
    language: str | None = None,
) -> m.CommunicationTemplate | None:
    """Task §16's own "configurable by Company/Restaurant, Branch, Role,
    Stage" scoping — picks the single MOST SPECIFIC active template
    matching this context. A template field of `None` means "matches any"
    for that dimension; a non-`None` field must match exactly. Specificity
    is the count of non-`None` scoping fields on the template (role/stage/
    location/outcome), so a template narrowed to this exact role beats one
    that applies to every role. When `language` is given and more than one
    equally-specific template exists, the one in that language wins;
    otherwise falls back to the restaurant's default-language template
    (task §5 — "fallback to default language")."""

    candidates = [
        t for t in list_templates(session, restaurant_id=restaurant_id, trigger_event=trigger_event, active_only=True)
        if (t.stage is None or t.stage == stage)
        and (t.role is None or t.role == role)
        and (t.location_label is None or t.location_label == location_label)
        and (t.outcome_definition_id is None or t.outcome_definition_id == outcome_definition_id)
    ]
    if not candidates:
        return None

    def _specificity(t: m.CommunicationTemplate) -> int:
        return sum(1 for v in (t.stage, t.role, t.location_label, t.outcome_definition_id) if v is not None)

    best_specificity = max(_specificity(t) for t in candidates)
    most_specific = [t for t in candidates if _specificity(t) == best_specificity]

    if language:
        language_matches = [t for t in most_specific if t.language == language]
        if language_matches:
            return language_matches[0]
    # Fallback to default language (task §5) — prefer "en" among the
    # equally-specific set, else whichever is available.
    default_language_matches = [t for t in most_specific if t.language == "en"]
    if default_language_matches:
        return default_language_matches[0]
    return most_specific[0]


def find_template_for_outcome_event(
    session: Session, *, restaurant_id: int | None, outcome_definition_id: int, stage: str | None,
    role: str | None = None, location_label: str | None = None, language: str | None = None,
) -> m.CommunicationTemplate | None:
    """Task §6-§9 — the lookup an applied Outcome uses: WHICH of the
    restaurant's own Outcome Definitions was just applied, and at WHICH
    Stage, together identify the template (and therefore its
    `trigger_event`, e.g. "Phone Stop" vs. "In-Person Stop" for the SAME
    underlying "Stop" Outcome Definition) — never a hard-coded guess at
    which trigger name applies. Unlike `find_best_template`, `trigger_event`
    is an OUTPUT here (read off the matched template), not a filter,
    because the restaurant is free to name it however it configured the
    template; `outcome_definition_id` is the one dimension that is always a
    required exact match (never a wildcard) — an outcome-triggered template
    with no named Outcome would fire for every Outcome, which is never the
    intent."""

    stmt = select(m.CommunicationTemplate).where(
        m.CommunicationTemplate.is_active.is_(True),
        m.CommunicationTemplate.outcome_definition_id == outcome_definition_id,
    )
    if restaurant_id is not None:
        stmt = stmt.where(m.CommunicationTemplate.restaurant_id == restaurant_id)
    candidates = [
        t for t in session.scalars(stmt).all()
        if (t.stage is None or t.stage == stage)
        and (t.role is None or t.role == role)
        and (t.location_label is None or t.location_label == location_label)
    ]
    if not candidates:
        return None

    def _specificity(t: m.CommunicationTemplate) -> int:
        return sum(1 for v in (t.stage, t.role, t.location_label) if v is not None)

    best_specificity = max(_specificity(t) for t in candidates)
    most_specific = [t for t in candidates if _specificity(t) == best_specificity]

    if language:
        language_matches = [t for t in most_specific if t.language == language]
        if language_matches:
            return language_matches[0]
    default_language_matches = [t for t in most_specific if t.language == "en"]
    if default_language_matches:
        return default_language_matches[0]
    return most_specific[0]
