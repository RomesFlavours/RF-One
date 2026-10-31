"""AI interview before the in-person interview (SELECTION_POSITION_PROFILES_001).

After reading the ranked list and calling a candidate, the recruiter selects
**AI Interview Requested** and confirms. That one action creates the
candidate's personal interview link and queues ONE invitation through the
existing RMAED.it outbox (`mail_delivery.enqueue`, source key
`ai-interview:<id>`): a second click finds the existing interview and sends
nothing. The confirmation is the manager's approval of the standard text.

On the link, the candidate has a short written conversation with the AI. The
steps come from the CV screening (`profile_screening.interview_steps`):
availability and hours, the commute when unknown, the résumé's flags, and
the position's own questions. The server decides which step is next and when
to close; the AI only words the questions and records what the candidate
said, with their own words as quotes (checked against the transcript).
When it ends, the status becomes **AI Interview Completed** and the full
transcript is on the candidate page.

Same AI seam and permission as the CV evaluation (`cv_evaluation` for the
position); nothing is sent to AI when it is off.
"""

from __future__ import annotations

import json
from datetime import timedelta

from flask import abort, redirect, render_template, request, url_for
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column

from rfone_data_store.models import Base
from rfone_data_store.selection import persistence, workspace_models as ws
from rfone_data_store.selection.parsing.ai_client import AIProviderUnavailable

from . import ai_adapter, mail_delivery, position_profiles, position_settings, profile_screening

REQUESTED, IN_PROGRESS, COMPLETED = "REQUESTED", "IN_PROGRESS", "COMPLETED"
STATUS_LABELS = {REQUESTED: "AI Interview Requested", IN_PROGRESS: "AI Interview in progress",
                 COMPLETED: "AI Interview Completed"}
FINDING_LABELS = {"CLEAR": "Clear answer", "PARTLY": "Partly answered", "OPEN": "Still open"}
MAX_MINUTES = 20
CANDIDATE_ACTOR = "Candidate (AI interview link)"

PRIORITIES = {"HIGH": "High", "MEDIUM": "Medium", "LOW": "Low"}
# Recruiter priority overrides the proposed groups; within each, the screening order is kept.
PRIORITY_ORDER = {"HIGH": 0, "MEDIUM": 1, None: 2, "LOW": 3}


class AIInterview(Base):
    __tablename__ = "selection_workspace_ai_interviews"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    position_candidate_id: Mapped[int] = mapped_column(
        ForeignKey("selection_workspace_position_candidates.id"), nullable=False, unique=True)
    token: Mapped[str] = mapped_column(String(64), nullable=False, default=ws.new_token, unique=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=REQUESTED)
    steps_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    transcript_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # [{"who","text","at"}]
    findings_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")    # {step_id: {status, quote, note}}
    profile_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    outbox_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requested_by_account_id: Mapped[int] = mapped_column(Integer, nullable=False)
    requested_by_name: Mapped[str] = mapped_column(String(255), nullable=False)
    requested_at: Mapped[object] = mapped_column(DateTime, nullable=False, default=ws.utcnow)
    started_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)

    steps = property(lambda self: json.loads(self.steps_json or "[]"))
    transcript = property(lambda self: json.loads(self.transcript_json or "[]"))
    findings = property(lambda self: json.loads(self.findings_json or "{}"))


class RecruiterPriority(Base):
    """The recruiter's High / Medium / Low priority for one candidate of one position (current value)."""
    __tablename__ = "selection_workspace_priorities"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    position_candidate_id: Mapped[int] = mapped_column(
        ForeignKey("selection_workspace_position_candidates.id"), nullable=False, unique=True)
    priority: Mapped[str | None] = mapped_column(String(8), nullable=True)
    set_by_name: Mapped[str] = mapped_column(String(255), nullable=False)
    set_at: Mapped[object] = mapped_column(DateTime, nullable=False, default=ws.utcnow)


def for_pc(db, pc_id: int) -> AIInterview | None:
    return db.scalars(select(AIInterview).where(AIInterview.position_candidate_id == pc_id)).first()


def priority_for(db, pc_id: int) -> str | None:
    row = db.scalars(select(RecruiterPriority).where(RecruiterPriority.position_candidate_id == pc_id)).first()
    return row.priority if row else None


def set_priority(db, *, position, pc, priority: str | None, actor) -> None:
    row = db.scalars(select(RecruiterPriority).where(RecruiterPriority.position_candidate_id == pc.id)).first()
    if row is None:
        row = RecruiterPriority(position_candidate_id=pc.id, set_by_name=actor.name)
        db.add(row)
    row.priority, row.set_by_name, row.set_at = priority, actor.name, ws.utcnow()
    candidate = persistence.get_candidate(db, pc.candidate_id)
    ws.log_event(db, position_id=position.id, position_candidate_id=pc.id, kind="PRIORITY", actor_id=actor.id,
                 actor_name=actor.name, detail=f"{candidate.full_name or pc.declared_name or 'Candidate'}: priority "
                                                f"{PRIORITIES.get(priority, 'cleared')}")


# ---------------------------------------------------------------------------
# Request and invitation (internal side; the route lives in routes.py)
# ---------------------------------------------------------------------------

GENERIC_STEPS = [
    {"id": "availability", "ask": "Evening and weekend availability, and desired and minimum weekly hours.",
     "context": "Not stated in the résumé."},
    {"id": "commute", "ask": "Roughly how long their drive to the restaurant would be.", "context": "Unknown."},
    {"id": "experience", "ask": "Their most relevant restaurant experience for this position.", "context": ""},
]


def invitation_text(position, first_name: str | None, link: str) -> str:
    return (f"Hi {first_name or 'there'},\n\nThank you for your application for the {position.title} position at "
            f"Rome's Flavours, {position.location_label}.\n\nAs the next step, please complete a short written "
            f"interview online. It takes about 10 to 15 minutes and you can do it from your phone:\n{link}\n\n"
            "The interview is run by an AI assistant for our hiring team, who will read your answers. "
            "If you would rather talk to a person, just reply to this email.\n\nBest regards,\nRome's Flavours")


def request_interview(db, *, position, pc, actor, link_for) -> tuple[AIInterview, bool]:
    """Create the interview and queue its one invitation. Returns (interview, created).
    Raises ValueError (nothing saved) when the candidate has no valid email address."""
    existing = for_pc(db, pc.id)
    if existing is not None:
        return existing, False
    if not mail_delivery.email_for(db, pc):
        raise ValueError("The candidate does not have a valid email address: no interview was requested.")
    from . import engine
    profile = position_profiles.for_role(position.role_code)
    screening = engine.current_proposals(db, pc.id).get(profile_screening.SOURCE)
    steps = (profile_screening.interview_steps(screening.payload, profile) if profile and screening
             else GENERIC_STEPS)
    interview = AIInterview(position_candidate_id=pc.id, steps_json=json.dumps(steps),
                            profile_version=profile["version"] if profile else None,
                            requested_by_account_id=actor.id, requested_by_name=actor.name)
    db.add(interview)
    db.flush()
    candidate = persistence.get_candidate(db, pc.candidate_id)
    name = (candidate.full_name or pc.declared_name or "").strip()
    row = mail_delivery.enqueue(db, pc=pc, source_key=f"ai-interview:{interview.id}",
                                subject=f"Rome's Flavours — {position.title}: short online interview",
                                body=invitation_text(position, name.split()[0].title() if name else None,
                                                     link_for(interview.token)))
    interview.outbox_id = row.id
    ws.log_event(db, position_id=position.id, position_candidate_id=pc.id, kind="AI_INTERVIEW", actor_id=actor.id,
                 actor_name=actor.name, detail=f"{name or 'Candidate'}: AI Interview Requested, invitation queued")
    return interview, True


# ---------------------------------------------------------------------------
# The conversation
# ---------------------------------------------------------------------------

_PROMPT = """You are the interviewer for Rome's Flavours, a traditional Italian restaurant in {location}, Florida.
This is a short written interview for the {title} position, BEFORE the in-person interview. The hiring team
reads everything; you do not decide anything and you never say whether the candidate will be hired.
Output ONLY a JSON object, no markdown.

Steps to cover, in this order (id: what to find out — what the résumé screening already knows):
{steps}

Already covered: {covered}
{instruction}

Conversation so far:
{transcript}

Rules for "reply": warm, plain English, short (at most 3 sentences), ONE question at a time, no lists, no emoji,
no step ids. Ask about the situation, never about {protected}. Never ask about pay. If the candidate gives a
personal reason for something, accept it and do not dig. Do not repeat a question already answered.
For "findings": one entry per step the candidate's LAST message answered, with "quote" copied EXACTLY from the
candidate's own words, status CLEAR (answered), PARTLY (partly) or OPEN (avoided or unclear), and a short
neutral note for the hiring team.

JSON shape: {{"reply": "...", "findings": [{{"step_id": "...", "status": "CLEAR|PARTLY|OPEN", "quote": "...",
"note": "..."}}]}}
"""


def _transcript_text(transcript: list[dict]) -> str:
    return "\n".join(f"{'Interviewer' if t['who'] == 'AI' else 'Candidate'}: {t['text']}" for t in transcript) or "(not started)"


def _closing(interview: AIInterview) -> bool:
    steps, findings = interview.steps, interview.findings
    started = interview.started_at or ws.utcnow()
    answered = sum(1 for t in interview.transcript if t["who"] == "CANDIDATE")
    return (all(s["id"] in findings for s in steps) or answered >= len(steps) + 4
            or ws.utcnow() - started > timedelta(minutes=MAX_MINUTES))


def take_turn(db, interview: AIInterview, position, message: str | None) -> None:
    """Append the candidate's message (if any), ask the AI for the next reply, record findings; may complete."""
    transcript, findings = interview.transcript, interview.findings
    if message:
        transcript.append({"who": "CANDIDATE", "text": message[:2000], "at": ws.utcnow().isoformat(timespec="seconds")})
    interview.transcript_json = json.dumps(transcript)
    closing = message is not None and _closing(interview)
    todo = [s for s in interview.steps if s["id"] not in findings]
    if not transcript:
        instruction = ("Start: greet them by first name if known, say in one sentence that this is a short written "
                       "interview read by the hiring team, then ask about the first step.")
    elif closing:
        instruction = ("CLOSE NOW: thank them warmly, say the hiring team will read their answers and contact them "
                       "about the next step, and ask NO new question. Still record findings for their last message.")
    else:
        instruction = f"NEXT STEP to ask about: {todo[0]['id']}." if todo else "Ask nothing new; close politely."
    prompt = _PROMPT.format(
        location=position.location_label, title=position.title,
        steps="\n".join(f"- {s['id']}: {s['ask']} ({s['context']})" for s in interview.steps),
        covered=", ".join(findings) or "nothing yet", instruction=instruction, transcript=_transcript_text(transcript),
        protected=ai_adapter._PROTECTED.replace(", address or where the person lives", ""))
    data = ai_adapter._transport(prompt, "AI interview")
    reply = str(data.get("reply") or "").strip() if isinstance(data, dict) else ""
    if not reply:
        raise AIProviderUnavailable("The AI returned no reply.")
    said = ai_adapter._normalized(" ".join(t["text"] for t in transcript if t["who"] == "CANDIDATE"))
    known = {s["id"] for s in interview.steps}
    for f in (data.get("findings") or []) if message else []:
        if not isinstance(f, dict) or f.get("step_id") not in known or f.get("status") not in FINDING_LABELS:
            continue
        quote = str(f.get("quote") or "").strip()
        if not quote or ai_adapter._normalized(quote) not in said:
            continue  # only the candidate's own words count
        previous = findings.get(f["step_id"])
        if previous and list(FINDING_LABELS).index(previous["status"]) <= list(FINDING_LABELS).index(f["status"]):
            continue  # the clearest answer wins
        findings[f["step_id"]] = {"status": f["status"], "quote": quote[:500], "note": str(f.get("note") or "")[:300]}
    transcript.append({"who": "AI", "text": reply.replace("—", ",")[:2000], "at": ws.utcnow().isoformat(timespec="seconds")})
    interview.transcript_json, interview.findings_json = json.dumps(transcript), json.dumps(findings)
    if interview.status == REQUESTED:
        interview.status, interview.started_at = IN_PROGRESS, ws.utcnow()
    if closing:
        complete(db, interview, position)


def complete(db, interview: AIInterview, position) -> None:
    if interview.status == COMPLETED:
        return
    interview.status, interview.completed_at = COMPLETED, ws.utcnow()
    pc = db.get(ws.PositionCandidate, interview.position_candidate_id)
    candidate = persistence.get_candidate(db, pc.candidate_id)
    ws.log_event(db, position_id=position.id, position_candidate_id=pc.id, kind="AI_INTERVIEW", actor_id=None,
                 actor_name=CANDIDATE_ACTOR,
                 detail=f"{candidate.full_name or pc.declared_name or 'Candidate'}: AI Interview Completed")


def install():
    """Public page on the careers blueprint: the link IS the access (like the time-selection link)."""
    from . import careers
    from .routes import _cfg

    @careers.bp.route("/ai-interview/<token>", methods=["GET", "POST"])
    def ai_interview_page(token):
        with _cfg.SessionFactory() as db:
            interview = db.scalars(select(AIInterview).where(AIInterview.token == token).with_for_update()).first()
            if interview is None:
                abort(404)
            pc = db.get(ws.PositionCandidate, interview.position_candidate_id)
            position = db.get(ws.Position, pc.position_id)
            error = None
            if interview.status != COMPLETED:
                position_settings.bind(position)
                try:
                    if not ai_adapter.current_policy().allows("cv_evaluation"):
                        raise AIProviderUnavailable("AI is not enabled for this position.")
                    if request.method == "POST" and request.form.get("action") == "finish":
                        complete(db, interview, position)
                    elif request.method == "POST":
                        text = (request.form.get("message") or "").strip()
                        if text:
                            take_turn(db, interview, position, text)
                    elif not interview.transcript:
                        take_turn(db, interview, position, None)
                    db.commit()
                except AIProviderUnavailable:
                    db.rollback()
                    error = "The interview is not available right now. Please try again in a few minutes."
                if request.method == "POST" and not error:
                    return redirect(url_for("careers.ai_interview_page", token=token) + "#end")
            return render_template("careers/ai_interview.html", position=position, candidate=None,
                                   interview=interview, error=error, done=interview.status == COMPLETED)
