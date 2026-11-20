"""Inbound Candidate Communication service (Task 5D §21-§25) — persists
every inbound message verbatim, classifies it with a real, deterministic,
non-fabricating rule-based classifier (the same honest convention
`parsing/deterministic_parser.py` already established for résumé parsing:
never invents confidence it doesn't have), and links it back to the open
response-tracking cycle it answers (`communication_service.
process_reminders_and_deadlines`'s counterpart on the inbound side).
Classification never changes an Outcome by itself (task §24) — the only
substantive effect it has here is the alert flag.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from .core import communication_model as cm

# ---------------------------------------------------------------------------
# Deterministic keyword classifier. Ordered from most-specific/least-
# ambiguous intent to most-generic; the FIRST rule whose keywords appear in
# the message wins UNLESS more than one distinct rule matches, in which case
# the signal is genuinely mixed and the message stays AMBIGUOUS_OR_UNCLEAR
# (task §23 — "do not fabricate certainty").
# ---------------------------------------------------------------------------

_RULES: list[tuple[str, tuple[str, ...], float]] = [
    (cm.CLASS_WITHDRAWAL, (
        "withdraw", "no longer interested", "not interested anymore", "please remove me", "pull my application",
    ), 0.9),
    (cm.CLASS_DECLINED, (
        "decline", "won't be able to accept", "can't accept", "turning down", "not accepting the offer",
    ), 0.9),
    (cm.CLASS_RESCHEDULE_REQUESTED, (
        "reschedule", "different time", "another time", "can we move", "change the time", "move the appointment",
    ), 0.85),
    (cm.CLASS_AVAILABILITY_CONFLICT, (
        "can't make it", "cannot make it", "won't be able to make", "double booked", "something came up",
        "conflict with",
    ), 0.85),
    (cm.CLASS_APPOINTMENT_SELECTED_OR_CONFIRMED, (
        "i'll be there", "i will be there", "see you then", "i will attend", "i'll come", "confirmed, see you",
    ), 0.85),
    (cm.CLASS_AVAILABILITY_CONFIRMED, (
        "i am available", "i'm available", "that time works", "available then", "works for me",
    ), 0.8),
    (cm.CLASS_INFORMATION_REQUESTED, (
        "what should i", "where is", "how do i", "can you tell me", "what time is", "what do i need",
    ), 0.75),
    (cm.CLASS_NEGATIVE_GENERIC_RESPONSE, (
        "not happy", "disappointed", "unhappy", "no thanks", "not good",
    ), 0.6),
    (cm.CLASS_POSITIVE_GENERIC_RESPONSE, (
        "thank you", "thanks", "sounds good", "great, thanks", "ok thanks", "okay thanks", "yes thank you",
    ), 0.6),
]


def classify_inbound_text(raw_text: str) -> tuple[str, float]:
    """Returns `(classification, confidence)`. Confidence is a plain
    0.0-1.0 float, never fabricated: an empty/unmatched message is
    `UNCLASSIFIED` at 0.0; a message matching more than one distinct rule is
    `AMBIGUOUS_OR_UNCLEAR` (genuinely mixed signal, not a guess)."""

    lowered = (raw_text or "").strip().lower()
    if not lowered:
        return cm.CLASS_UNCLASSIFIED, 0.0

    matches: list[tuple[str, float]] = []
    for classification, keywords, confidence in _RULES:
        if any(keyword in lowered for keyword in keywords):
            matches.append((classification, confidence))

    distinct = {classification for classification, _ in matches}
    if not distinct:
        return cm.CLASS_UNCLASSIFIED, 0.0
    if len(distinct) > 1:
        return cm.CLASS_AMBIGUOUS_OR_UNCLEAR, 0.4

    classification, confidence = matches[0]
    if confidence < cm.MIN_CONFIDENT_CLASSIFICATION_SCORE:
        return cm.CLASS_AMBIGUOUS_OR_UNCLEAR, confidence
    return classification, confidence


# ---------------------------------------------------------------------------
# Response-cycle linking (task §16-§20's inbound-side counterpart).
# ---------------------------------------------------------------------------

def find_open_response_cycle(session: Session, application_id: int) -> m.CandidateCommunication | None:
    """The most recent outbound communication still awaiting a response for
    this Application — regardless of whether an automatic NO RESPONSE Stop
    has already been applied to it (task §20: a late response must still be
    linkable back to the cycle it answers, purely for record-keeping; it
    never reopens anything by itself)."""

    stmt = (
        select(m.CandidateCommunication)
        .where(
            m.CandidateCommunication.application_id == application_id,
            m.CandidateCommunication.awaiting_response.is_(True),
            m.CandidateCommunication.response_received_at.is_(None),
        )
        .order_by(m.CandidateCommunication.id.desc())
    )
    return session.scalars(stmt).first()


def record_inbound(
    session: Session, application_id: int, *, channel: str, raw_text: str, source: str | None = None,
    received_at: datetime | None = None,
) -> m.InboundCommunication:
    """Task §21/§22 — preserves the raw message verbatim, classifies it,
    and (task §20) if the open response cycle was already closed by an
    automatic NO RESPONSE Stop, force-overrides the effective classification
    to `LATE_RESPONSE_AFTER_NO_RESPONSE_STOP` regardless of what the text
    itself says — that fact is more operationally important than the
    message's ordinary content, and always carries a mandatory alert."""

    application = session.get(m.Application, application_id)
    if application is None:
        raise ValueError(f"No Application with id {application_id}")

    system_classification, confidence = classify_inbound_text(raw_text)
    open_cycle = find_open_response_cycle(session, application_id)

    effective_classification = system_classification
    if open_cycle is not None and open_cycle.no_response_stop_applied:
        effective_classification = cm.CLASS_LATE_RESPONSE_AFTER_NO_RESPONSE_STOP

    inbound = m.InboundCommunication(
        application_id=application_id, channel=channel, raw_text=raw_text,
        received_at=received_at or datetime.utcnow(), source=source,
        classification_system=system_classification, classification_confidence=confidence,
        classification_effective=effective_classification,
        related_outgoing_communication_id=open_cycle.id if open_cycle is not None else None,
        alert_required=cm.default_requires_alert(effective_classification),
        alert_reason=effective_classification if cm.default_requires_alert(effective_classification) else None,
    )
    session.add(inbound)
    session.flush()

    if open_cycle is not None and open_cycle.response_received_at is None:
        open_cycle.response_received_at = inbound.received_at
        open_cycle.response_inbound_id = inbound.id
        open_cycle.awaiting_response = False
        session.flush()

    return inbound


def correct_classification(
    session: Session, inbound_id: int, *, new_classification: str, corrected_by: str, reason: str | None = None,
) -> m.InboundCommunication:
    """Task §23 — the Selezionatore may correct the EFFECTIVE classification
    without ever losing the original system classification (`classification_
    system` is never written here)."""

    cm.validate_classification(new_classification)
    inbound = session.get(m.InboundCommunication, inbound_id)
    if inbound is None:
        raise ValueError(f"No InboundCommunication with id {inbound_id}")

    inbound.classification_effective = new_classification
    inbound.classification_corrected_by = corrected_by
    inbound.classification_corrected_at = datetime.utcnow()
    inbound.classification_correction_reason = reason
    inbound.alert_required = cm.default_requires_alert(new_classification)
    inbound.alert_reason = new_classification if inbound.alert_required else None
    session.flush()
    return inbound


def acknowledge_alert(session: Session, inbound_id: int, *, acknowledged_by: str) -> m.InboundCommunication:
    inbound = session.get(m.InboundCommunication, inbound_id)
    if inbound is None:
        raise ValueError(f"No InboundCommunication with id {inbound_id}")
    inbound.alert_acknowledged_by = acknowledged_by
    inbound.alert_acknowledged_at = datetime.utcnow()
    session.flush()
    return inbound


def list_inbound_for_application(session: Session, application_id: int) -> list[m.InboundCommunication]:
    stmt = (
        select(m.InboundCommunication)
        .where(m.InboundCommunication.application_id == application_id)
        .order_by(m.InboundCommunication.received_at, m.InboundCommunication.id)
    )
    return list(session.scalars(stmt).all())


def list_open_alerts(session: Session, *, restaurant_id: int | None = None) -> list[m.InboundCommunication]:
    stmt = select(m.InboundCommunication).where(
        m.InboundCommunication.alert_required.is_(True), m.InboundCommunication.alert_acknowledged_at.is_(None),
    )
    rows = list(session.scalars(stmt).all())
    if restaurant_id is not None:
        rows = [r for r in rows if r.application.restaurant_id == restaurant_id]
    return rows
