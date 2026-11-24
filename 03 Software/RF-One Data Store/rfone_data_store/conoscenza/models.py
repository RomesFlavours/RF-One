"""Conoscenza tables (`10 System/Conoscenza/README.md`).

Conoscenza is the persistent project-knowledge register shared by the
Product Owner (Pino) and the three AI environments he uses on RF-One
(ChatGPT, Claude, Codex). It keeps decisions, motivated corrections and
work updates so that a new chat — of any of the three AIs — can retrieve
them before proposing or resuming work.

The tables live on their OWN declarative base, not on the shared
`rfone_data_store.models.Base`: the first release runs on a provisional
project-relative store (see README, "Storage") and must not alter the
operational schema or its Alembic chain. Every column avoids
SQLite-specific constructs, so the same models can move into the canonical
PostgreSQL (or AWS RDS) by changing only the URL and adding a migration.

- `KnowledgeItem`      — one decision, correction or work update, in one
  version. A change of decision is a NEW row in the same `series_id`; the
  replaced row becomes SUPERSEDED, so exactly one row per series is CURRENT.
- `KnowledgeEvidence`  — verifiable evidence of a work update (commit,
  test, release, document).
- `KnowledgeLink`      — a typed relation between two series (an amendment
  that does not replace, or a plain relation).
- `KnowledgeClient`    — the authenticated clients (one token per AI
  environment). The recording AI is taken from the token, never declared.
- `KnowledgeAccess`    — every read, search and write, with its client,
  session reference and outcome: the evidence that a session consulted the
  register BEFORE answering.

Codes are English; the Italian labels shown to Pino live in `service.py`.
Timestamps are written explicitly in UTC (SQLite returns them naive).
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

KINDS = ("DECISION", "CORRECTION", "WORK_UPDATE")
# PO_EXPLICIT: decision taken or approved by the register owner (Pino);
# PROPOSAL: a person's proposal not (yet) approved; AI_HYPOTHESIS: the AI's own
# reading, never a decision; EVIDENCE: a work outcome resting on evidence.
AUTHORITIES = ("PO_EXPLICIT", "PROPOSAL", "AI_HYPOTHESIS", "EVIDENCE")
STATUSES = ("CURRENT", "SUPERSEDED", "WITHDRAWN")
RATIONALE_STATUSES = ("KNOWN", "UNKNOWN")
SOURCE_TYPES = ("CHAT_SESSION", "DECISION_LOG", "REPORT", "REPOSITORY_DOC", "IMPORTED_EXTRACT")
WORK_STAGES = ("DESIGNED", "IMPLEMENTED", "VERIFIED", "RELEASED")
EVIDENCE_KINDS = ("COMMIT", "TEST", "RELEASE", "DOCUMENT", "FILE", "OTHER")
LINK_RELATIONS = ("AMENDS", "RELATES")
CLIENTS = ("CLAUDE", "CODEX", "CHATGPT", "IMPORTER")
ACCESS_OPERATIONS = ("BRIEF", "SEARCH", "READ", "WRITE", "SUPERSEDE", "WORK", "LINK", "STATUS", "APPROVE",
                     "AUTH")
PERMISSIONS = ("READ", "CONTRIBUTE", "APPROVE")
PERSON_STATUSES = ("ACTIVE", "INACTIVE")
ACCESS_OUTCOMES = ("OK", "DUPLICATE", "REFUSED", "FAILED")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


class ConoscenzaBase(DeclarativeBase):
    pass


class KnowledgePerson(ConoscenzaBase):
    """A person who may consult or contribute. The owner (Pino) decides; the
    other people's decisions are PROPOSALs until he approves them."""

    __tablename__ = "conoscenza_people"
    __table_args__ = (CheckConstraint(_in("status", PERSON_STATUSES), name="ck_conoscenza_people_status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    is_owner: Mapped[bool] = mapped_column(default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class KnowledgeAccessRule(ConoscenzaBase):
    """What a non-owner person may READ, CONTRIBUTE to or APPROVE, per domain
    (`*` = every domain, otherwise a domain prefix such as `Restaurant/Tips`).
    The owner needs no rule. No rule = no access. Rules are defined by the owner."""

    __tablename__ = "conoscenza_access_rules"
    __table_args__ = (
        CheckConstraint(_in("permission", PERMISSIONS), name="ck_conoscenza_access_rules_permission"),
        UniqueConstraint("person_id", "permission", "domain_pattern", name="uq_conoscenza_access_rules"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("conoscenza_people.id"), nullable=False, index=True)
    permission: Mapped[str] = mapped_column(String(12), nullable=False)
    domain_pattern: Mapped[str] = mapped_column(String(120), nullable=False)
    active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class KnowledgeClient(ConoscenzaBase):
    """A credential: one person using one tool. Every operation is attributed
    to both."""

    __tablename__ = "conoscenza_clients"
    __table_args__ = (CheckConstraint(_in("client", CLIENTS), name="ck_conoscenza_clients_client"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client: Mapped[str] = mapped_column(String(16), nullable=False)
    person_id: Mapped[int | None] = mapped_column(ForeignKey("conoscenza_people.id"), nullable=True, index=True)
    token_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class KnowledgeItem(ConoscenzaBase):
    __tablename__ = "conoscenza_items"
    __table_args__ = (
        CheckConstraint(_in("kind", KINDS), name="ck_conoscenza_items_kind"),
        CheckConstraint(_in("authority", AUTHORITIES), name="ck_conoscenza_items_authority"),
        CheckConstraint(_in("status", STATUSES), name="ck_conoscenza_items_status"),
        CheckConstraint(_in("rationale_status", RATIONALE_STATUSES), name="ck_conoscenza_items_rationale"),
        CheckConstraint(_in("source_type", SOURCE_TYPES), name="ck_conoscenza_items_source_type"),
        CheckConstraint(_in("recorded_by", CLIENTS), name="ck_conoscenza_items_recorded_by"),
        CheckConstraint("work_stage IS NULL OR " + _in("work_stage", WORK_STAGES),
                        name="ck_conoscenza_items_work_stage"),
        # A work update always states its stage; a decision/correction never does.
        CheckConstraint("(kind = 'WORK_UPDATE' AND work_stage IS NOT NULL) OR "
                        "(kind <> 'WORK_UPDATE' AND work_stage IS NULL)",
                        name="ck_conoscenza_items_stage_kind"),
        # A work update rests on evidence; a decision/correction on Pino or on an AI hypothesis.
        CheckConstraint("(kind = 'WORK_UPDATE') = (authority = 'EVIDENCE')", name="ck_conoscenza_items_authority_kind"),
        CheckConstraint("version >= 1", name="ck_conoscenza_items_version"),
        UniqueConstraint("series_id", "version", name="uq_conoscenza_items_series_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # All versions of the same decision share `series_id` (= id of version 1).
    series_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    supersedes_id: Mapped[int | None] = mapped_column(ForeignKey("conoscenza_items.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)

    kind: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    authority: Mapped[str] = mapped_column(String(16), nullable=False)
    domain: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    rationale_status: Mapped[str] = mapped_column(String(8), nullable=False)
    validity_conditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    exceptions: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Alternative words the recording AI expects people to use (synonyms,
    # other languages); used by search, never shown as part of the rule.
    keywords: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Who provided the contribution (person), who took/approved the decision
    # (person). NULL = unknown (kept unknown for undocumented history).
    contributed_by_person_id: Mapped[int | None] = mapped_column(ForeignKey("conoscenza_people.id"), nullable=True)
    decided_by_person_id: Mapped[int | None] = mapped_column(ForeignKey("conoscenza_people.id"), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    decided_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    recorded_by: Mapped[str] = mapped_column(String(16), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    session_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)

    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    source_ref: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    source_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)

    work_ref: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    work_stage: Mapped[str | None] = mapped_column(String(12), nullable=True)

    # Safe repetition: the same request key never creates a second row.
    request_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)


class KnowledgeEvidence(ConoscenzaBase):
    __tablename__ = "conoscenza_evidence"
    __table_args__ = (CheckConstraint(_in("kind", EVIDENCE_KINDS), name="ck_conoscenza_evidence_kind"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("conoscenza_items.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(12), nullable=False)
    reference: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class KnowledgeLink(ConoscenzaBase):
    __tablename__ = "conoscenza_links"
    __table_args__ = (
        CheckConstraint(_in("relation", LINK_RELATIONS), name="ck_conoscenza_links_relation"),
        UniqueConstraint("from_series_id", "to_series_id", "relation", name="uq_conoscenza_links"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    from_series_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    to_series_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    relation: Mapped[str] = mapped_column(String(12), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by: Mapped[str] = mapped_column(String(16), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class KnowledgeApproval(ConoscenzaBase):
    """The owner's approval of a proposal: the proposal row stays (SUPERSEDED)
    and the approved PO_EXPLICIT version points back to it."""

    __tablename__ = "conoscenza_approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    proposal_item_id: Mapped[int] = mapped_column(ForeignKey("conoscenza_items.id"), nullable=False, unique=True)
    approved_item_id: Mapped[int] = mapped_column(ForeignKey("conoscenza_items.id"), nullable=False, unique=True)
    approved_by_person_id: Mapped[int] = mapped_column(ForeignKey("conoscenza_people.id"), nullable=False)
    via_client: Mapped[str] = mapped_column(String(16), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OAuthClient(ConoscenzaBase):
    """An OAuth client registered dynamically (RFC 7591) — ChatGPT's connector."""

    __tablename__ = "conoscenza_oauth_clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    client_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    redirect_uris: Mapped[str] = mapped_column(Text, nullable=False)  # JSON list
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OAuthGrant(ConoscenzaBase):
    """Authorization codes, access and refresh tokens (hashed). Each grant is
    bound to the credential (person + tool) that authorized it."""

    __tablename__ = "conoscenza_oauth_grants"
    __table_args__ = (CheckConstraint("kind IN ('CODE', 'ACCESS', 'REFRESH')", name="ck_conoscenza_oauth_kind"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    token_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    oauth_client_id: Mapped[str] = mapped_column(String(80), nullable=False)
    credential_id: Mapped[int] = mapped_column(ForeignKey("conoscenza_clients.id"), nullable=False)
    redirect_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    code_challenge: Mapped[str | None] = mapped_column(String(128), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class KnowledgeAccess(ConoscenzaBase):
    __tablename__ = "conoscenza_access_log"
    __table_args__ = (
        CheckConstraint(_in("operation", ACCESS_OPERATIONS), name="ck_conoscenza_access_operation"),
        CheckConstraint(_in("outcome", ACCESS_OUTCOMES), name="ck_conoscenza_access_outcome"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    person_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    session_ref: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    operation: Mapped[str] = mapped_column(String(12), nullable=False)
    query: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_item_ids: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[str] = mapped_column(String(10), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


ALL_TABLES = [t.__table__ for t in (KnowledgePerson, KnowledgeAccessRule, KnowledgeClient, KnowledgeItem,
                                    KnowledgeEvidence, KnowledgeLink, KnowledgeApproval, OAuthClient, OAuthGrant,
                                    KnowledgeAccess)]
