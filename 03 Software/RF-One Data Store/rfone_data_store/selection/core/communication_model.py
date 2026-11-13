"""Candidate Communication + Interview Scheduling vocabulary (Task 5D).
Mirrors every other `core/*_model.py` module's role: fixed vocabulary +
validation only, no persistence, no restaurant-specific content. The
restaurant configures WHAT is said (`models.CommunicationTemplate`); this
module defines the fixed, universal STRUCTURE of when/why a communication
fires and how an inbound message is classified.

Communication is a CONSEQUENCE of an existing Selection decision/event
(task §10), never itself a decision. Every `TRIGGER_EVENT` below corresponds
to exactly one place in the service layer that fires it
(`communication_service.py`) — this is a deliberately small, fixed set,
never a general workflow/rule engine.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Channels (task §2) — RF-One sends SMS + Email simultaneously when both
# contact methods are available; never voice calling/voicemail.
# ---------------------------------------------------------------------------

CHANNEL_SMS = "SMS"
CHANNEL_EMAIL = "EMAIL"
CHANNELS = (CHANNEL_SMS, CHANNEL_EMAIL)


def validate_channel(value: str) -> None:
    if value not in CHANNELS:
        raise ValueError(f"Unknown communication channel {value!r}; expected one of {CHANNELS}")


# ---------------------------------------------------------------------------
# Advance-to-Phone-Interview communication mode (task §7) — a Selezionatore
# choice at the moment of advancing an Application to PHONE_INTERVIEW, never
# a persisted Application field of its own (it only ever selects which of
# the two triggers below fires once).
# ---------------------------------------------------------------------------

PHONE_ADVANCE_MODE_SCHEDULING = "SCHEDULING"
PHONE_ADVANCE_MODE_CONTACT = "CONTACT"
PHONE_ADVANCE_MODES = (PHONE_ADVANCE_MODE_SCHEDULING, PHONE_ADVANCE_MODE_CONTACT)


def validate_phone_advance_mode(value: str) -> None:
    if value not in PHONE_ADVANCE_MODES:
        raise ValueError(f"Unknown Phone Interview advance mode {value!r}; expected one of {PHONE_ADVANCE_MODES}")


# ---------------------------------------------------------------------------
# Trigger events (task §6-§9/§16) — WHY a communication was sent. A
# Communication Template names exactly one of these. Each is fired from
# exactly one place in `communication_service.py`:
#   PRIMARY_SCREENING_STOP        <- outcome_service.apply_outcome, while
#                                     current_stage in (APPLICATION_RECEIVED,
#                                     PRIMARY_SCREENING) and the applied
#                                     Outcome is the template's configured
#                                     `outcome_definition_id`.
#   ADVANCE_TO_PHONE_SCHEDULING/
#   ADVANCE_TO_PHONE_CONTACT      <- an explicit Selezionatore mode choice
#                                     when advancing to PHONE_INTERVIEW.
#   PHONE_HOLD/PHONE_STOP         <- apply_outcome while current_stage ==
#                                     PHONE_INTERVIEW.
#   ADVANCE_TO_IN_PERSON          <- stage_service.set_stage to
#                                     IN_PERSON_PRACTICAL.
#   IN_PERSON_HOLD/IN_PERSON_STOP/
#   HIRABLE                       <- apply_outcome while current_stage ==
#                                     IN_PERSON_PRACTICAL.
#   REMINDER                      <- a configured follow-up for a trigger
#                                     awaiting a candidate response.
#   APPOINTMENT_CONFIRMATION      <- automatic, on candidate slot selection.
# ---------------------------------------------------------------------------

TRIGGER_PRIMARY_SCREENING_STOP = "PRIMARY_SCREENING_STOP"
TRIGGER_ADVANCE_TO_PHONE_SCHEDULING = "ADVANCE_TO_PHONE_SCHEDULING"
TRIGGER_ADVANCE_TO_PHONE_CONTACT = "ADVANCE_TO_PHONE_CONTACT"
TRIGGER_PHONE_HOLD = "PHONE_HOLD"
TRIGGER_PHONE_STOP = "PHONE_STOP"
TRIGGER_ADVANCE_TO_IN_PERSON = "ADVANCE_TO_IN_PERSON"
TRIGGER_IN_PERSON_HOLD = "IN_PERSON_HOLD"
TRIGGER_IN_PERSON_STOP = "IN_PERSON_STOP"
TRIGGER_HIRABLE = "HIRABLE"
TRIGGER_REMINDER = "REMINDER"
TRIGGER_APPOINTMENT_CONFIRMATION = "APPOINTMENT_CONFIRMATION"
# Task 5E §25 — "Thank you for your application, there are a few things we
# could not determine from your CV..." fires automatically alongside a
# generated Missing-Evidence Questionnaire (`missing_evidence_service.py`);
# reuses this exact Template/render/send machinery, never a bespoke message.
TRIGGER_MISSING_EVIDENCE_QUESTIONNAIRE = "MISSING_EVIDENCE_QUESTIONNAIRE"

TRIGGER_EVENTS = (
    TRIGGER_PRIMARY_SCREENING_STOP, TRIGGER_ADVANCE_TO_PHONE_SCHEDULING, TRIGGER_ADVANCE_TO_PHONE_CONTACT,
    TRIGGER_PHONE_HOLD, TRIGGER_PHONE_STOP, TRIGGER_ADVANCE_TO_IN_PERSON, TRIGGER_IN_PERSON_HOLD,
    TRIGGER_IN_PERSON_STOP, TRIGGER_HIRABLE, TRIGGER_REMINDER, TRIGGER_APPOINTMENT_CONFIRMATION,
    TRIGGER_MISSING_EVIDENCE_QUESTIONNAIRE,
)

# Triggers that normally open a "candidate is expected to respond" cycle
# (task §16's own reminder/no-response scope) — used only as a sensible
# default when configuring a Reminder Policy; a restaurant may configure a
# policy for any trigger it chooses.
RESPONSE_AWAITED_TRIGGERS = (
    TRIGGER_ADVANCE_TO_PHONE_SCHEDULING, TRIGGER_ADVANCE_TO_PHONE_CONTACT, TRIGGER_MISSING_EVIDENCE_QUESTIONNAIRE,
)


def validate_trigger_event(value: str) -> None:
    if value not in TRIGGER_EVENTS:
        raise ValueError(f"Unknown communication trigger event {value!r}; expected one of {TRIGGER_EVENTS}")


# ---------------------------------------------------------------------------
# Per-channel delivery status (task §30 — a mockable/injectable provider
# seam; no real SMS/Email credentials required to reach any of these).
# ---------------------------------------------------------------------------

DELIVERY_SENT = "SENT"
DELIVERY_FAILED = "FAILED"
DELIVERY_NOT_APPLICABLE = "NOT_APPLICABLE"  # contact method not available for this Application

DELIVERY_STATUSES = (DELIVERY_SENT, DELIVERY_FAILED, DELIVERY_NOT_APPLICABLE)


# ---------------------------------------------------------------------------
# Interview stages a scheduling window/appointment may target — deliberately
# the SAME two Stages `core.stage_model` already defines that a candidate is
# ever scheduled for; never a parallel Stage vocabulary.
# ---------------------------------------------------------------------------

SCHEDULABLE_STAGES = ("PHONE_INTERVIEW", "IN_PERSON_PRACTICAL")


def validate_schedulable_stage(value: str) -> None:
    if value not in SCHEDULABLE_STAGES:
        raise ValueError(f"Unknown schedulable interview stage {value!r}; expected one of {SCHEDULABLE_STAGES}")


# ---------------------------------------------------------------------------
# Appointment status (task §11-§15).
# ---------------------------------------------------------------------------

APPOINTMENT_CONFIRMED = "CONFIRMED"
APPOINTMENT_RESCHEDULED = "RESCHEDULED"
APPOINTMENT_CANCELLED = "CANCELLED"

APPOINTMENT_STATUSES = (APPOINTMENT_CONFIRMED, APPOINTMENT_RESCHEDULED, APPOINTMENT_CANCELLED)


# ---------------------------------------------------------------------------
# Inbound message classification (task §22) — a clean, stable internal
# vocabulary; visible labels may be localized/configured elsewhere, this
# module is the authoritative internal set.
# ---------------------------------------------------------------------------

CLASS_APPOINTMENT_SELECTED_OR_CONFIRMED = "APPOINTMENT_SELECTED_OR_CONFIRMED"
CLASS_RESCHEDULE_REQUESTED = "RESCHEDULE_REQUESTED"
CLASS_DECLINED = "DECLINED"
CLASS_WITHDRAWAL = "NO_LONGER_INTERESTED_WITHDRAWAL"
CLASS_INFORMATION_REQUESTED = "INFORMATION_REQUESTED"
CLASS_AVAILABILITY_CONFIRMED = "AVAILABILITY_CONFIRMED"
CLASS_AVAILABILITY_CONFLICT = "AVAILABILITY_CONFLICT"
CLASS_POSITIVE_GENERIC_RESPONSE = "POSITIVE_GENERIC_RESPONSE"
CLASS_NEGATIVE_GENERIC_RESPONSE = "NEGATIVE_GENERIC_RESPONSE"
CLASS_LATE_RESPONSE_AFTER_NO_RESPONSE_STOP = "LATE_RESPONSE_AFTER_NO_RESPONSE_STOP"
CLASS_AMBIGUOUS_OR_UNCLEAR = "AMBIGUOUS_OR_UNCLEAR"
CLASS_UNCLASSIFIED = "UNCLASSIFIED"

INBOUND_CLASSIFICATIONS = (
    CLASS_APPOINTMENT_SELECTED_OR_CONFIRMED, CLASS_RESCHEDULE_REQUESTED, CLASS_DECLINED, CLASS_WITHDRAWAL,
    CLASS_INFORMATION_REQUESTED, CLASS_AVAILABILITY_CONFIRMED, CLASS_AVAILABILITY_CONFLICT,
    CLASS_POSITIVE_GENERIC_RESPONSE, CLASS_NEGATIVE_GENERIC_RESPONSE, CLASS_LATE_RESPONSE_AFTER_NO_RESPONSE_STOP,
    CLASS_AMBIGUOUS_OR_UNCLEAR, CLASS_UNCLASSIFIED,
)

# Task §25 — classifications that record only, with no mandatory alert.
# Every other classification requires a Selezionatore-visible alert; this is
# an explicit allow-list so a new classification defaults to "alert" (the
# safer default) rather than silently going unnoticed.
NO_ALERT_CLASSIFICATIONS = (
    CLASS_POSITIVE_GENERIC_RESPONSE, CLASS_AVAILABILITY_CONFIRMED, CLASS_APPOINTMENT_SELECTED_OR_CONFIRMED,
)


def validate_classification(value: str) -> None:
    if value not in INBOUND_CLASSIFICATIONS:
        raise ValueError(f"Unknown inbound classification {value!r}; expected one of {INBOUND_CLASSIFICATIONS}")


def default_requires_alert(classification: str) -> bool:
    """Task §24/§25 — classification alone never changes an Outcome; the
    only behavior it drives directly is whether a high-visibility
    Selezionatore alert is raised. `LATE_RESPONSE_AFTER_NO_RESPONSE_STOP` is
    always a mandatory alert (task §20/§25) purely by virtue of not being in
    the no-alert list above."""

    return classification not in NO_ALERT_CLASSIFICATIONS


# Confidence is a plain 0.0-1.0 float (task §23 — "preserve classification
# confidence... do not fabricate certainty"); below this, the classifier
# itself must resolve to AMBIGUOUS_OR_UNCLEAR/UNCLASSIFIED rather than
# guessing a specific classification with false confidence.
MIN_CONFIDENT_CLASSIFICATION_SCORE = 0.55
