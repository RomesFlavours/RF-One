"""Candidate Communication service (Task 5D) — the ONE place a
Communication Template is rendered and actually sent, and the ONE place
Selection's existing Stage/Outcome engines are read (never modified) to
decide WHETHER an automatic communication fires. Communication is always a
CONSEQUENCE of a decision already recorded by `stage_service`/
`outcome_service` (task §10) — nothing here ever calls `apply_outcome`
except the one explicit, restaurant-configured NO RESPONSE automation
(task §18), and even that goes through the existing authoritative
`outcome_service.apply_outcome`, never a bespoke lifecycle write.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from string import Template

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import communication_providers as providers
from . import communication_template_service as tmpl_svc
from . import outcome_service as outcome_svc
from .core import communication_model as cm
from .core import stage_model as stgm


# ---------------------------------------------------------------------------
# Rendering (task §3 — SMS text / Email subject / Email body). `$name`-style
# placeholders via `string.Template.safe_substitute`, deliberately forgiving
# of an unknown/missing key (leaves the literal `$placeholder` rather than
# raising) since a template is restaurant-authored free text, not code.
# ---------------------------------------------------------------------------

def _render(text: str | None, context: dict) -> str | None:
    if text is None:
        return None
    return Template(text).safe_substitute(context)


def _build_context(session: Session, application: m.Application, *, extra: dict | None = None) -> dict:
    candidate = application.candidate
    restaurant = session.get(m.Restaurant, application.restaurant_id) if application.restaurant_id else None
    context = {
        "candidate_name": (candidate.full_name if candidate else None) or "Candidate",
        "role": application.target_role or "the role",
        "restaurant_name": (restaurant.name if restaurant else None) or "",
        "scheduling_link": "",
    }
    if extra:
        context.update({k: v for k, v in extra.items() if v is not None})
    return context


def _preferred_language(application: m.Application) -> str | None:
    """No structured candidate-language-preference field exists anywhere
    else in Selection today (Task 2A's `Candidate.languages` is free text
    describing spoken languages, not a single preferred-communication
    code) — an honestly-scoped gap (see the Task 5D report's Known
    Limitations). Returning `None` here means every lookup below falls back
    to the restaurant's default-language template (task §5)."""

    return None


# ---------------------------------------------------------------------------
# Sending (task §2/§4/§30) — the ONE function every trigger below funnels
# through, so every sent communication is recorded identically.
# ---------------------------------------------------------------------------

def send_communication(
    session: Session, application: m.Application, template: m.CommunicationTemplate, *, trigger_event: str,
    related_outcome_decision_id: int | None = None, related_stage_transition_id: int | None = None,
    performed_by: str | None = None, extra_context: dict | None = None, is_reminder: bool = False,
    reminder_sequence_number: int | None = None, parent_communication_id: int | None = None,
    track_response: bool = True,
) -> m.CandidateCommunication:
    snapshot = tmpl_svc.get_or_create_template_snapshot(session, template.id)
    context = _build_context(session, application, extra=extra_context)

    rendered_sms = _render(snapshot.sms_text, context)
    rendered_subject = _render(snapshot.email_subject, context)
    rendered_body = _render(snapshot.email_body, context)

    candidate = application.candidate
    recipient_phone = (candidate.phone if candidate else None) or application.person.primary_phone
    recipient_email = (candidate.email if candidate else None) or application.person.primary_email

    channel_sms_used = bool(recipient_phone and rendered_sms)
    channel_email_used = bool(recipient_email and (rendered_subject or rendered_body))

    sms_status = cm.DELIVERY_NOT_APPLICABLE
    sms_ref = None
    if channel_sms_used:
        result = providers.get_sms_provider().send(to_phone=recipient_phone, text=rendered_sms)
        sms_status = cm.DELIVERY_SENT if result.success else cm.DELIVERY_FAILED
        sms_ref = result.provider_ref

    email_status = cm.DELIVERY_NOT_APPLICABLE
    email_ref = None
    if channel_email_used:
        result = providers.get_email_provider().send(
            to_email=recipient_email, subject=rendered_subject or "", body=rendered_body or "",
        )
        email_status = cm.DELIVERY_SENT if result.success else cm.DELIVERY_FAILED
        email_ref = result.provider_ref

    reminder_policy = None
    final_deadline_at = None
    awaiting_response = False
    if track_response and not is_reminder:
        reminder_policy = find_reminder_policy(
            session, restaurant_id=application.restaurant_id, trigger_event=trigger_event,
            stage=application.current_stage, role=application.target_role,
        )
        if reminder_policy is not None:
            awaiting_response = True
            if reminder_policy.final_deadline_hours is not None:
                final_deadline_at = datetime.utcnow() + timedelta(hours=reminder_policy.final_deadline_hours)

    communication = m.CandidateCommunication(
        application_id=application.id, template_snapshot_id=snapshot.id, trigger_event=trigger_event,
        channel_sms_used=channel_sms_used, channel_email_used=channel_email_used,
        recipient_phone=recipient_phone if channel_sms_used else None,
        recipient_email=recipient_email if channel_email_used else None,
        rendered_sms_text=rendered_sms if channel_sms_used else None,
        rendered_email_subject=rendered_subject if channel_email_used else None,
        rendered_email_body=rendered_body if channel_email_used else None,
        language_used=snapshot.language,
        sms_status=sms_status, sms_provider_ref=sms_ref, email_status=email_status, email_provider_ref=email_ref,
        is_reminder=is_reminder, reminder_sequence_number=reminder_sequence_number,
        parent_communication_id=parent_communication_id,
        awaiting_response=awaiting_response, reminder_policy_id=reminder_policy.id if reminder_policy else None,
        final_deadline_at=final_deadline_at,
        related_outcome_decision_id=related_outcome_decision_id,
        related_stage_transition_id=related_stage_transition_id,
        performed_by=performed_by,
    )
    session.add(communication)
    session.flush()
    return communication


# ---------------------------------------------------------------------------
# Automatic triggers (task §6-§9) — each reads an event that ALREADY
# happened through the existing authoritative Stage/Outcome services; if no
# active Template is configured for the context, nothing is sent (an
# honestly-scoped "restaurant hasn't configured this yet," never a
# fabricated default message).
# ---------------------------------------------------------------------------

def on_stage_transition(
    session: Session, application: m.Application, transition: m.ApplicationStageTransition, *,
    communication_mode: str | None = None, performed_by: str | None = None,
) -> m.CandidateCommunication | None:
    """Task §7/§9 — fires when the Selezionatore advances to PHONE_INTERVIEW
    (mode-dependent) or to IN_PERSON_PRACTICAL (task §9's ADVANCE_TO_IN_PERSON).
    Any OTHER Stage transition (backward, repeated, to APPLICATION_RECEIVED/
    PRIMARY_SCREENING) triggers no automatic communication — never
    implemented/requested by the task."""

    trigger_event: str
    if transition.new_stage == stgm.PHONE_INTERVIEW:
        if communication_mode is None:
            return None
        cm.validate_phone_advance_mode(communication_mode)
        trigger_event = (
            cm.TRIGGER_ADVANCE_TO_PHONE_SCHEDULING if communication_mode == cm.PHONE_ADVANCE_MODE_SCHEDULING
            else cm.TRIGGER_ADVANCE_TO_PHONE_CONTACT
        )
    elif transition.new_stage == stgm.IN_PERSON_PRACTICAL:
        trigger_event = cm.TRIGGER_ADVANCE_TO_IN_PERSON
    else:
        return None

    template = tmpl_svc.find_best_template(
        session, restaurant_id=application.restaurant_id, trigger_event=trigger_event,
        stage=transition.new_stage, role=application.target_role, language=_preferred_language(application),
    )
    if template is None:
        return None

    extra_context = None
    if trigger_event == cm.TRIGGER_ADVANCE_TO_PHONE_SCHEDULING:
        from . import scheduling_service as sched_svc
        extra_context = {
            "scheduling_link": sched_svc.build_scheduling_link(session, application.id, interview_stage=stgm.PHONE_INTERVIEW),
        }

    return send_communication(
        session, application, template, trigger_event=trigger_event, related_stage_transition_id=transition.id,
        performed_by=performed_by or "SYSTEM_AUTOMATIC", extra_context=extra_context,
    )


def on_outcome_decision(
    session: Session, application: m.Application, decision: m.SelectionOutcomeDecision,
) -> m.CandidateCommunication | None:
    """Task §6/§8/§9 — fires when a Selezionatore Outcome decision is
    applied (Primary Screening Stop, Phone Hold/Stop, In-Person Hold/Stop/
    Hirable...). Which specific communication (if any) fires is entirely
    determined by whether the restaurant configured a Template naming BOTH
    this exact Outcome Definition and the Application's current Stage
    (`communication_template_service.find_template_for_outcome_event`) —
    this function itself hard-codes no restaurant-specific Outcome name."""

    outcome_definition_id = decision.outcome_definition_snapshot.definition_id
    stage = application.current_stage
    template = tmpl_svc.find_template_for_outcome_event(
        session, restaurant_id=application.restaurant_id, outcome_definition_id=outcome_definition_id,
        stage=stage, role=application.target_role, language=_preferred_language(application),
    )
    if template is None:
        return None
    return send_communication(
        session, application, template, trigger_event=template.trigger_event,
        related_outcome_decision_id=decision.id, performed_by="SYSTEM_AUTOMATIC",
    )


# ---------------------------------------------------------------------------
# Appointment confirmation (task §13) — always automatic, no Selezionatore
# approval; called by `scheduling_service.book_slot` right after a slot is
# confirmed.
# ---------------------------------------------------------------------------

def send_appointment_confirmation(
    session: Session, application: m.Application, appointment: m.InterviewAppointment,
) -> m.CandidateCommunication | None:
    template = tmpl_svc.find_best_template(
        session, restaurant_id=application.restaurant_id, trigger_event=cm.TRIGGER_APPOINTMENT_CONFIRMATION,
        stage=appointment.interview_stage, role=application.target_role, language=_preferred_language(application),
    )
    if template is None:
        return None
    extra_context = {
        "appointment_date": appointment.slot_start_at.strftime("%A, %B %d"),
        "appointment_time": appointment.slot_start_at.strftime("%I:%M %p"),
    }
    return send_communication(
        session, application, template, trigger_event=cm.TRIGGER_APPOINTMENT_CONFIRMATION,
        performed_by="SYSTEM_AUTOMATIC", extra_context=extra_context, track_response=False,
    )


# ---------------------------------------------------------------------------
# Reminder Policy lookup (task §16) — same restaurant/branch/role/stage
# scoping discipline as `find_best_template`.
# ---------------------------------------------------------------------------

def find_reminder_policy(
    session: Session, *, restaurant_id: int | None, trigger_event: str, stage: str | None = None,
    role: str | None = None, location_label: str | None = None,
) -> m.CommunicationReminderPolicy | None:
    stmt = select(m.CommunicationReminderPolicy).where(
        m.CommunicationReminderPolicy.is_active.is_(True),
        m.CommunicationReminderPolicy.trigger_event == trigger_event,
    )
    if restaurant_id is not None:
        stmt = stmt.where(m.CommunicationReminderPolicy.restaurant_id == restaurant_id)
    candidates = [
        p for p in session.scalars(stmt).all()
        if (p.stage is None or p.stage == stage)
        and (p.role is None or p.role == role)
        and (p.location_label is None or p.location_label == location_label)
    ]
    if not candidates:
        return None

    def _specificity(p: m.CommunicationReminderPolicy) -> int:
        return sum(1 for v in (p.stage, p.role, p.location_label) if v is not None)

    best_specificity = max(_specificity(p) for p in candidates)
    return next(p for p in candidates if _specificity(p) == best_specificity)


# ---------------------------------------------------------------------------
# Reminder / no-response processing (task §16-§20) — computed on demand,
# exactly like `outcome_service.list_due_reminders`; no separate scheduler
# exists anywhere in this codebase (by design). Safe to call repeatedly.
# ---------------------------------------------------------------------------

def _last_reminder(session: Session, root_id: int) -> m.CandidateCommunication | None:
    stmt = (
        select(m.CandidateCommunication)
        .where(m.CandidateCommunication.parent_communication_id == root_id)
        .order_by(m.CandidateCommunication.id.desc())
    )
    return session.scalars(stmt).first()


def process_reminders_and_deadlines(
    session: Session, *, restaurant_id: int | None = None, as_of: datetime | None = None,
) -> dict:
    """Task §16-§20 — for every open response-tracking cycle: send the next
    due reminder, or, once every configured reminder has been sent and the
    final deadline has passed with no response, apply the configured
    NO RESPONSE Outcome through the existing authoritative
    `outcome_service.apply_outcome` (task §18 — "not an AI judgment... a
    configured rule"). Returns a small summary dict for callers/tests."""

    as_of = as_of or datetime.utcnow()
    stmt = select(m.CandidateCommunication).where(
        m.CandidateCommunication.awaiting_response.is_(True),
        m.CandidateCommunication.response_received_at.is_(None),
        m.CandidateCommunication.no_response_stop_applied.is_(False),
    )
    cycles = list(session.scalars(stmt).all())
    if restaurant_id is not None:
        cycles = [c for c in cycles if c.application.restaurant_id == restaurant_id]

    reminders_sent = 0
    stops_applied = 0

    for comm in cycles:
        policy = session.get(m.CommunicationReminderPolicy, comm.reminder_policy_id) if comm.reminder_policy_id else None
        if policy is None:
            continue
        application = comm.application

        if comm.reminders_sent_count < policy.reminder_count:
            if comm.reminders_sent_count == 0:
                due_at = comm.created_at + timedelta(hours=policy.first_reminder_delay_hours or 0)
            else:
                last = _last_reminder(session, comm.id)
                base = last.created_at if last is not None else comm.created_at
                due_at = base + timedelta(hours=policy.reminder_interval_hours or 0)

            if as_of >= due_at:
                template = tmpl_svc.find_best_template(
                    session, restaurant_id=application.restaurant_id, trigger_event=cm.TRIGGER_REMINDER,
                    stage=application.current_stage, role=application.target_role,
                    language=_preferred_language(application),
                )
                sequence = comm.reminders_sent_count + 1
                if template is not None:
                    send_communication(
                        session, application, template, trigger_event=cm.TRIGGER_REMINDER, is_reminder=True,
                        reminder_sequence_number=sequence, parent_communication_id=comm.id,
                        performed_by="SYSTEM_AUTOMATIC",
                    )
                    reminders_sent += 1
                comm.reminders_sent_count = sequence
                session.flush()
            continue

        if comm.final_deadline_at is not None and as_of >= comm.final_deadline_at:
            if policy.auto_stop_enabled and policy.auto_stop_outcome_definition_id:
                decision = outcome_svc.apply_outcome(
                    session, application.id, policy.auto_stop_outcome_definition_id,
                    reason="NO RESPONSE", performed_by="SYSTEM_AUTOMATIC_NO_RESPONSE",
                )
                comm.no_response_stop_applied = True
                comm.no_response_stop_outcome_decision_id = decision.id
                session.flush()
                stops_applied += 1

    return {"reminders_sent": reminders_sent, "stops_applied": stops_applied}


# ---------------------------------------------------------------------------
# History (task §complete communication history requirement).
# ---------------------------------------------------------------------------

def list_communications_for_application(session: Session, application_id: int) -> list[m.CandidateCommunication]:
    stmt = (
        select(m.CandidateCommunication)
        .where(m.CandidateCommunication.application_id == application_id)
        .order_by(m.CandidateCommunication.created_at, m.CandidateCommunication.id)
    )
    return list(session.scalars(stmt).all())
