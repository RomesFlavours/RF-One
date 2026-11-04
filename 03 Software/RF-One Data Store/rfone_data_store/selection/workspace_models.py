"""Selection position workspace (SELECTION_AI_INTEGRATION_001).

The operational layer of the Selection interface approved from the Selection
AI prototype: one open Position (a job opening to fill, not an Organization
`positions` row) groups the five functions — Position, Applications,
Evaluation, Interviews, Decisions.

It sits ON TOP of the existing Selection entities and never copies them:
résumés, candidates, persons and applications stay in `candidates`,
`candidate_persons` and `applications`; requirements and their approved
versions in `requirement_sets` / `requirement_set_snapshots`; evidence in the
Fit Assessment tables. These tables only add what the Selection Core had no
place for: the position itself, which application belongs to which position,
the candidate's online interview, the rule/AI proposal, the manager's
decisions, appointments, messages and the position history.

Also holds the external candidate identity (`CandidateAccount`): the people
who apply from the public pages. Deliberately separate from `rfone_accounts`
— a candidate is never an internal RF-One user and never enters a Domain.

All timestamps are naive UTC, the convention the prototype already used.
"""

from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from rfone_data_store.models import Base


def utcnow() -> datetime:
    """Naive UTC."""
    return datetime.now(UTC).replace(tzinfo=None)


def new_token() -> str:
    return secrets.token_urlsafe(18)


# Position status
DRAFT = "DRAFT"          # not approved yet
OPEN = "OPEN"            # approved: receiving and evaluating candidates
CLOSED = "CLOSED"        # closed manually
POSITION_STATUS_LABELS = {DRAFT: "Pending approval", OPEN: "Open", CLOSED: "Closed"}

# Acquisition channels (see the Selection app's `workspace/channels.py`)
MANUAL_UPLOAD = "MANUAL_UPLOAD"
PUBLIC_LINK = "PUBLIC_LINK"

# Proposal groups
G_INTERVIEW = "INTERVIEW"
G_DEEPEN = "DEEPEN"
G_ESSENTIALS_NOT_SHOWN = "ESSENTIALS_NOT_SHOWN"
GROUP_LABELS = {
    G_INTERVIEW: "To interview",
    G_DEEPEN: "Needs clarification",
    G_ESSENTIALS_NOT_SHOWN: "Must-have requirements not evidenced",
}
GROUP_ORDER = (G_INTERVIEW, G_DEEPEN, G_ESSENTIALS_NOT_SHOWN)

SOURCE_RULES = "RULES"
SOURCE_AI = "AI"
SOURCE_LABELS = {SOURCE_RULES: "Existing rule-based engines", SOURCE_AI: "AI"}

# Manager decisions: preselection steps, then the final outcome.
D_INTERVIEW = "INTERVIEW"
D_DEEPEN = "DEEPEN"
D_HIRED = "HIRED"
D_NOT_SELECTED = "NOT_SELECTED"
D_ON_HOLD = "ON_HOLD"
D_UNDECIDED = "UNDECIDED"
DECISION_LABELS = {
    D_INTERVIEW: "To interview",
    D_DEEPEN: "Needs clarification",
    D_HIRED: "Hired",
    D_NOT_SELECTED: "Not selected",
    D_ON_HOLD: "On hold",
    D_UNDECIDED: "Clear decision (return to proposal)",
}
PRESELECTION_DECISIONS = (D_INTERVIEW, D_DEEPEN)
FINAL_DECISIONS = (D_HIRED, D_NOT_SELECTED, D_ON_HOLD)
NOT_SELECTED_REASONS = {
    "ESSENTIAL_VERIFIED_MISSING": "Must-have requirement verified as unmet",
    "OTHER_CANDIDATE_CHOSEN": "Another candidate selected",
    "AVAILABILITY": "Availability incompatible (verified with candidate)",
    "CANDIDATE_DECLINED": "Candidate declined",
    "POSITION_FILLED": "Position filled",
    "OTHER": "Other (explain in note)",
}
DECISION_TO_GROUP = {D_INTERVIEW: G_INTERVIEW, D_DEEPEN: G_DEEPEN}

# Candidate application (public page)
A_CV_RECEIVED = "CV_RECEIVED"
A_SUBMITTED = "SUBMITTED"
APPLICATION_STATUS_LABELS = {A_CV_RECEIVED: "Interview incomplete", A_SUBMITTED: "Application complete"}

# Interviews
K_PHONE = "PHONE"
K_IN_PERSON = "IN_PERSON"
KIND_LABELS = {K_PHONE: "Phone", K_IN_PERSON: "In person"}

# Messages
MESSAGE_KINDS = {
    "STUDY": "Menu study invitation",
    "GENERAL": "General message",
    "CANCEL": "Appointment cancellation",
    "INVITE": "Interview invitation",
    "SLOTS": "Proposed times",
    "REJECTION": "Not selected",
    "HIRE": "Job offer",
    "ON_HOLD": "On hold",
}

# External candidate identity
CANDIDATE_PENDING = "PENDING_VERIFICATION"
CANDIDATE_ACTIVE = "ACTIVE"
CHANNEL_EMAIL = "EMAIL"
CHANNEL_SMS = "SMS"


class CandidateAccount(Base):
    """An external candidate's own identity, created by registering on a
    public position page and verified by a code sent, at the candidate's
    choice, by email or by text message (at least one must be verified).
    Never an RF-One account. The password is stored only as a Werkzeug hash
    and will also serve the candidate's future personal page."""

    __tablename__ = "selection_candidate_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)  # normalized, lower case
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=CANDIDATE_PENDING)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)  # E.164, e.g. +14075550101
    phone_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class CandidateEmailCode(Base):
    """One verification code, sent by email or by text message (`channel`)
    to `target`. Only its HMAC (keyed by the server secret) is stored; the
    plaintext is never persisted or logged. (The table name predates the
    text-message channel.)"""

    __tablename__ = "selection_candidate_email_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_account_id: Mapped[int] = mapped_column(
        ForeignKey("selection_candidate_accounts.id"), nullable=False, index=True)
    code_hmac: Mapped[str] = mapped_column(String(64), nullable=False)
    channel: Mapped[str] = mapped_column(String(8), nullable=False, default=CHANNEL_EMAIL)
    target: Mapped[str | None] = mapped_column(String(320), nullable=True)  # the address or number it was sent to
    request_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attempts_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class WorkspacePosition(Base):
    __tablename__ = "selection_workspace_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    role_code: Mapped[str] = mapped_column(String(64), nullable=False)
    location_label: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=DRAFT)
    headcount: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    job_ad_en: Mapped[str] = mapped_column(Text, nullable=False, default="")
    questions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    # What the public page shows: copies taken at approval, never the unapproved draft.
    approved_job_ad_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_questions_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    manager_account_id: Mapped[int] = mapped_column(ForeignKey("rfone_accounts.id"), nullable=False, index=True)
    created_by_account_id: Mapped[int] = mapped_column(ForeignKey("rfone_accounts.id"), nullable=False)
    requirement_set_id: Mapped[int] = mapped_column(ForeignKey("requirement_sets.id"), nullable=False)
    approved_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("requirement_set_snapshots.id"), nullable=True)
    approved_by_account_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    public_token: Mapped[str] = mapped_column(String(64), nullable=False, default=new_token, unique=True)
    organization_context_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    @property
    def questions(self) -> list[str]:
        return json.loads(self.questions_json or "[]")

    @property
    def approved_questions(self) -> list[str]:
        return json.loads(self.approved_questions_json or "[]")


class WorkspacePositionCandidate(Base):
    """One existing Selection Application considered for one Position."""

    __tablename__ = "selection_workspace_position_candidates"
    __table_args__ = (UniqueConstraint("position_id", "application_id", name="uq_sel_ws_pc_position_application"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    position_id: Mapped[int] = mapped_column(
        ForeignKey("selection_workspace_positions.id"), nullable=False, index=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), nullable=False)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False)
    # Set for applications sent from the public page by a verified candidate.
    candidate_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("selection_candidate_accounts.id"), nullable=True, index=True)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    added_by_account_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    declared_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    declared_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    declared_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    import_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    added_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class WorkspaceCandidateApplication(Base):
    """The candidate's own side of a public application: the online
    interview, resumable while the candidate is signed in."""

    __tablename__ = "selection_workspace_candidate_applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    position_candidate_id: Mapped[int] = mapped_column(
        ForeignKey("selection_workspace_position_candidates.id"), nullable=False, unique=True)
    token: Mapped[str] = mapped_column(String(64), nullable=False, default=new_token, unique=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=A_CV_RECEIVED)
    questions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # [{"text","source"}]
    consent_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    @property
    def questions(self) -> list[dict]:
        return json.loads(self.questions_json or "[]")


class WorkspaceAnswer(Base):
    __tablename__ = "selection_workspace_answers"
    __table_args__ = (UniqueConstraint("candidate_application_id", "question_index",
                                       name="uq_sel_ws_answer_application_question"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_application_id: Mapped[int] = mapped_column(
        ForeignKey("selection_workspace_candidate_applications.id"), nullable=False, index=True)
    question_index: Mapped[int] = mapped_column(Integer, nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    question_source: Mapped[str] = mapped_column(String(16), nullable=False)  # STANDARD | AI
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    input_mode: Mapped[str] = mapped_column(String(8), nullable=False, default="TEXT")  # TEXT | VOICE
    answered_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class WorkspaceProposal(Base):
    """A preselection proposal for one candidate against one approved
    requirement snapshot. Never a decision; the newest per source is current."""

    __tablename__ = "selection_workspace_proposals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    position_candidate_id: Mapped[int] = mapped_column(
        ForeignKey("selection_workspace_position_candidates.id"), nullable=False, index=True)
    snapshot_id: Mapped[int] = mapped_column(Integer, nullable=False)
    fit_assessment_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    group_code: Mapped[str] = mapped_column(String(32), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    provider_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    @property
    def payload(self) -> dict:
        return json.loads(self.payload_json)


class WorkspaceDecision(Base):
    """Append-only: the current preselection step and the current final
    outcome are the newest rows of each kind."""

    __tablename__ = "selection_workspace_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    position_candidate_id: Mapped[int] = mapped_column(
        ForeignKey("selection_workspace_position_candidates.id"), nullable=False, index=True)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposal_group: Mapped[str | None] = mapped_column(String(32), nullable=True)
    proposal_source: Mapped[str | None] = mapped_column(String(16), nullable=True)
    differs_from_proposal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    actor_account_id: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class WorkspaceAppointment(Base):
    __tablename__ = "selection_workspace_appointments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    position_candidate_id: Mapped[int] = mapped_column(
        ForeignKey("selection_workspace_position_candidates.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)  # UTC
    duration_min: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    place: Mapped[str | None] = mapped_column(String(255), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="CONFIRMED")  # CONFIRMED | CANCELLED
    booked_by: Mapped[str] = mapped_column(String(16), nullable=False, default="MANAGER")  # MANAGER | CANDIDATE
    created_by_account_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class WorkspaceSlotOffer(Base):
    __tablename__ = "selection_workspace_slot_offers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    position_candidate_id: Mapped[int] = mapped_column(
        ForeignKey("selection_workspace_position_candidates.id"), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(64), nullable=False, default=new_token, unique=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    slots_json: Mapped[str] = mapped_column(Text, nullable=False)  # ["YYYY-MM-DDTHH:MM" UTC]
    duration_min: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    place: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="OPEN")  # OPEN | CHOSEN | CANCELLED
    appointment_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by_account_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    @property
    def slots(self) -> list[datetime]:
        return [datetime.fromisoformat(s) for s in json.loads(self.slots_json)]


class WorkspaceMessage(Base):
    """A communication to the candidate, always approved by the manager.
    Approved content can be queued explicitly; transport and receipts live
    in Selection's email outbox, separately from content approval."""

    __tablename__ = "selection_workspace_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    position_candidate_id: Mapped[int] = mapped_column(
        ForeignKey("selection_workspace_position_candidates.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)  # TEMPLATE | AI
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT")  # DRAFT | APPROVED
    approved_by_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class WorkspaceEvent(Base):
    """Position history, in plain words."""

    __tablename__ = "selection_workspace_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    position_id: Mapped[int] = mapped_column(
        ForeignKey("selection_workspace_positions.id"), nullable=False, index=True)
    position_candidate_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kind: Mapped[str] = mapped_column(String(48), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    actor_account_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor_name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class WorkspacePositionDraft(Base):
    """An AI proposal for a position (requirements, headcount, English ad), waiting for the manager."""

    __tablename__ = "selection_workspace_position_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    position_id: Mapped[int] = mapped_column(
        ForeignKey("selection_workspace_positions.id"), nullable=False, index=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    provider_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PROPOSED")  # PROPOSED|USED|DISCARDED
    created_by_account_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    @property
    def payload(self) -> dict:
        return json.loads(self.payload_json)


class WorkspaceCompanyProfile(Base):
    """Company facts written by the owner, used (with Organization facts) when drafting positions."""

    __tablename__ = "selection_workspace_company_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_by_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


# Short names used by the Selection workspace code. The mapped classes carry the
# `Workspace` prefix because SQLAlchemy's registry is shared by every RF-One model
# (Organization already has a `Position`).
Position = WorkspacePosition
PositionCandidate = WorkspacePositionCandidate
CandidateApplication = WorkspaceCandidateApplication
Answer = WorkspaceAnswer
Proposal = WorkspaceProposal
Decision = WorkspaceDecision
Appointment = WorkspaceAppointment
SlotOffer = WorkspaceSlotOffer
Message = WorkspaceMessage
Event = WorkspaceEvent
PositionDraft = WorkspacePositionDraft
CompanyProfile = WorkspaceCompanyProfile


def log_event(session, *, position_id: int, kind: str, detail: str, actor_id: int | None, actor_name: str,
              position_candidate_id: int | None = None) -> None:
    session.add(WorkspaceEvent(position_id=position_id, position_candidate_id=position_candidate_id, kind=kind,
                      detail=detail, actor_account_id=actor_id, actor_name=actor_name))
