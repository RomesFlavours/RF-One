"""RF-One canonical Restaurant operational database schema (TASK_DATABASE_001).

This module defines the physical schema only. It does not ingest data and
does not compute derived/KPI values.

Conventions (see DATABASE_SCHEMA.md for full rationale):

- Table names are plural snake_case; class names are singular PascalCase.
- Every canonical entity has an RF-One surrogate integer primary key (`id`).
  External source identity lives in explicit `source_system_id` /
  `source_*_id` fields, never as the primary key (multi-source future).
- Money is stored as integer minor units (cents) — never floating point.
- Quantity is stored as `Numeric(12, 4)` — independently of money, and
  capable of representing fractional sold units (TASK_CLOVER_003 finding).
- Rates/percentages are stored as canonical decimal `Numeric` values, not
  in any source-specific encoding (e.g. Clover's own `rate / 10_000_000`).
- Timestamps are `DateTime(timezone=True)`; the application/ingestion layer
  is responsible for normalizing to UTC before persisting (§39 of the task).
- A field is nullable whenever the empirical Clover evidence (or general
  multi-source caution) shows it is not always present — "missing" is a
  distinct, preserved state, never silently coerced to zero/false/"".
"""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Shared Identity & Authority substrate (GLOBAL_INTEGRITY_FIX_002 / C-1, I-4)
#
# Per `00 Core/ConceptualArchitecture/09_Identity_Authority_and_Accountability.md`
# and Core Principle 21 ("No Domain or Module may define its own independent
# identity, authority or audit mechanism"), ActingIdentity is the ONE stable
# "who is acting" concept every Domain consumes — never redefined per-Domain.
# It deliberately does not implement Authentication (no password/session/MFA
# here): `authentication_provider`/`external_subject_id` are only the seam a
# future real Authentication provider (e.g. Cognito) attaches through. Until
# that exists, `acting_identity_service.get_current_acting_identity()` is the
# ONE place that resolves "who is currently acting" from a trusted
# server-side mechanism — never from client-supplied HTTP input — see that
# module's own docstring for the explicit temporary/pre-production scope.
# ---------------------------------------------------------------------------

HUMAN_USER = "HUMAN_USER"
SYSTEM = "SYSTEM"
AI_AGENT = "AI_AGENT"
EXTERNAL_SERVICE = "EXTERNAL_SERVICE"
ACTING_IDENTITY_KINDS = (HUMAN_USER, SYSTEM, AI_AGENT, EXTERNAL_SERVICE)


class ActingIdentity(Base):
    """The stable, permanent-identifier "who" behind a Decision or Action
    (Core doc §2 "Acting Identity" — Entity assuming the Actor role).
    `display_name` is a configurable Attribute, never the identity itself
    (Core doc §2.1: "changing a label must never be capable of silently
    changing what the identity is accountable for") — every FK reference to
    this table is what carries authority/ownership meaning, not the name.
    `authentication_provider`/`external_subject_id` are nullable and unused
    until a real Authentication provider is connected; a `HUMAN_USER`
    identity created by today's pre-auth development resolver simply leaves
    both `None`."""

    __tablename__ = "acting_identities"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('HUMAN_USER', 'SYSTEM', 'AI_AGENT', 'EXTERNAL_SERVICE')",
            name="ck_acting_identity_kind",
        ),
        UniqueConstraint(
            "authentication_provider", "external_subject_id", name="uq_acting_identity_external_subject"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    authentication_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    external_subject_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )


# Authority scope kinds — the Core organizational context chain
# (00 Core/Corporate.md, Operational Unit.md, OperationalArea.md, Brand.md):
# Corporate -> Brand -> Operational Unit -> Operational Area. Only Restaurant
# (a Domain-level entity, not this chain) and Restaurant's own, narrower
# `OperationalArea` (kitchen/dining zones — a Domain specialization, NOT this
# Core concept) are persisted anywhere in RF-One today; Corporate/Brand/
# Operational Unit have no table of their own yet (00 Core defines them;
# nothing has implemented them — see CLAUDE.md "Core ≠ Domain ≠ Product").
# `AuthorityGrant.scope_id` is therefore a plain integer with NO foreign key
# to any of these — a grant is already scoped generically by whichever
# concrete table eventually backs each `scope_type`, with zero redesign of
# this table when that happens. GLOBAL is the one scope with no `scope_id`.
SCOPE_CORPORATE = "CORPORATE"
SCOPE_BRAND = "BRAND"
SCOPE_OPERATIONAL_UNIT = "OPERATIONAL_UNIT"
SCOPE_OPERATIONAL_AREA = "OPERATIONAL_AREA"
SCOPE_GLOBAL = "GLOBAL"
AUTHORITY_SCOPE_KINDS = (SCOPE_CORPORATE, SCOPE_BRAND, SCOPE_OPERATIONAL_UNIT, SCOPE_OPERATIONAL_AREA, SCOPE_GLOBAL)

# The one wildcard `authority_service.authorize()` understands for `module`/
# `action` — never for `domain` or `scope_type`/`scope_id` (Authority is
# always evaluated in an explicit context, never globally-guessed; task
# requirement "never infer tenant from a global singleton").
AUTHORITY_WILDCARD = "*"


class AuthorityGrant(Base):
    """One bounded grant of Authority (00 Core/ConceptualArchitecture/
    09_Identity_Authority_and_Accountability.md §3) to an `ActingIdentity`,
    over an explicit `domain`/`module`/`action`/scope context — never a flat
    global permission. Evaluated exclusively by `authority_service.
    authorize()`; no Domain queries this table directly (Core Principle 21 /
    Architecture doc §1: shared infrastructure, never a Domain-owned
    mechanism).

    `module`/`action` may be the literal wildcard `'*'` (a grant over every
    Module within a Domain, or every Action within a Module/Domain) —
    `domain` and `scope_type`/`scope_id` may NOT: this keeps every grant
    explicitly tenant/context-scoped by construction, never globally
    inferred. A grant is revoked by setting `revoked_at` — never deleted and
    never reused for a different Acting Identity/scope (Historical
    Integrity: a revoked grant remains provable as having once existed).

    `granted_by_identity_id` and `granted_at` are this table's own minimal
    Delegation record (Core doc §4: "who granted it, when" — Delegation
    revocation beyond this is deliberately out of scope for this
    foundation)."""

    __tablename__ = "authority_grants"
    __table_args__ = (
        CheckConstraint(
            "scope_type IN ('CORPORATE', 'BRAND', 'OPERATIONAL_UNIT', 'OPERATIONAL_AREA', 'GLOBAL')",
            name="ck_authority_grant_scope_type",
        ),
        CheckConstraint(
            "scope_type = 'GLOBAL' OR scope_id IS NOT NULL", name="ck_authority_grant_scope_id_required",
        ),
        Index("ix_authority_grants_lookup", "acting_identity_id", "domain", "action"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    acting_identity_id: Mapped[int] = mapped_column(
        ForeignKey("acting_identities.id"), nullable=False, index=True
    )

    domain: Mapped[str] = mapped_column(String(64), nullable=False)
    module: Mapped[str] = mapped_column(String(64), nullable=False, default=AUTHORITY_WILDCARD)
    action: Mapped[str] = mapped_column(String(64), nullable=False)

    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    granted_by_identity_id: Mapped[int | None] = mapped_column(
        ForeignKey("acting_identities.id"), nullable=True
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    acting_identity: Mapped["ActingIdentity"] = relationship(foreign_keys=[acting_identity_id])
    granted_by_identity: Mapped["ActingIdentity | None"] = relationship(foreign_keys=[granted_by_identity_id])


# The three documented RF-One Operational Signature assurance levels
# (03 Software/Identity Authority and Security Architecture.md §10) — a
# risk-based, layered model, never a uniform one.
NORMAL_AUTHENTICATED_ACTION = "NORMAL_AUTHENTICATED_ACTION"
EXPLICIT_CONFIRMATION = "EXPLICIT_CONFIRMATION"
STEP_UP_AUTHENTICATION = "STEP_UP_AUTHENTICATION"
OPERATIONAL_SIGNATURE_ASSURANCE_LEVELS = (
    NORMAL_AUTHENTICATED_ACTION, EXPLICIT_CONFIRMATION, STEP_UP_AUTHENTICATION,
)


class OperationalSignature(Base):
    """The RF-One Operational Signature (Identity Authority and Security
    Architecture.md §9-10) — the append-only evidence record that makes an
    authenticated, authorized action itself stand in for a handwritten
    signature on ordinary operational Decisions. Written exclusively through
    `operational_signature_service.record_operational_signature()`; no
    Domain writes this table directly.

    Append-only by construction: no code anywhere in this codebase updates
    an existing row's evidentiary columns after insert (Historical
    Integrity, 00 Core/ArchitecturePrinciples.md — exactly the same
    discipline `TipDistributionCalculationRun`/`IngestionRun` already follow
    elsewhere in this schema). A correction is a NEW row whose own
    `corrects_signature_id` points back at the row it corrects; the original
    row's columns are never touched.

    `actor_kind` is a deliberate denormalized copy of `ActingIdentity.kind`
    AT THE TIME of signing (Core doc §5.1 / Architecture doc §6: every
    AI-touched Action must record whether the actor was Human/System/AI
    Agent/External Service) — the evidence must remain readable exactly as
    captured even if the identity row were ever altered later.

    `object_type`/`object_id` are plain strings, deliberately with no
    foreign key: the objects Domains sign over vary in table and key shape,
    and this shared table must not depend on every future Domain's schema."""

    __tablename__ = "operational_signatures"
    __table_args__ = (
        CheckConstraint(
            "assurance_level IN ('NORMAL_AUTHENTICATED_ACTION', 'EXPLICIT_CONFIRMATION', 'STEP_UP_AUTHENTICATION')",
            name="ck_operational_signature_assurance_level",
        ),
        CheckConstraint(
            "actor_kind IN ('HUMAN_USER', 'SYSTEM', 'AI_AGENT', 'EXTERNAL_SERVICE')",
            name="ck_operational_signature_actor_kind",
        ),
        Index("ix_operational_signatures_lookup", "domain", "object_type", "object_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    acting_identity_id: Mapped[int] = mapped_column(
        ForeignKey("acting_identities.id"), nullable=False, index=True
    )
    actor_kind: Mapped[str] = mapped_column(String(24), nullable=False)

    action: Mapped[str] = mapped_column(String(128), nullable=False)
    domain: Mapped[str] = mapped_column(String(64), nullable=False)
    module: Mapped[str | None] = mapped_column(String(64), nullable=True)

    scope_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    scope_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    object_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    object_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    before_state: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    after_state: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)

    applicable_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    authority_used: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    assurance_level: Mapped[str] = mapped_column(String(40), nullable=False)

    # The Decision/Action's own moment in time vs. when this evidence was
    # durably persisted — kept as two separate columns from day one (even
    # though identical today) so persistence can later become asynchronous
    # (task requirement "audit scalability") without changing either this
    # table's shape or any Domain caller's own signature.
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    corrects_signature_id: Mapped[int | None] = mapped_column(
        ForeignKey("operational_signatures.id"), nullable=True
    )

    acting_identity: Mapped["ActingIdentity"] = relationship(foreign_keys=[acting_identity_id])


# ---------------------------------------------------------------------------
# Organizational Responsibility + Attention Management shared runtime
# (TASK_ATTENTION_ORG_RUNTIME; 00 Core/Organizational Responsibility.md,
# 00 Core/ConceptualArchitecture/12_Attention_Management.md).
#
# Same placement rationale as ActingIdentity/AuthorityGrant/
# OperationalSignature immediately above: this is shared, cross-Domain
# infrastructure, not owned by whichever Domain integrates it first
# (Tips included) — see `organizational_responsibility_service.py` and
# `attention_service.py`'s own "foundation, not integration" module
# docstrings.
#
# Position's Scope reuses AuthorityGrant's own established pattern —
# `scope_type` + a generic, non-foreign-keyed `scope_id` for dimensions with
# no table of their own yet (CORPORATE/BRAND), a REAL `scope_id` for
# dimensions that do have one today (RESTAURANT, LEGAL_ENTITY,
# OPERATIONAL_AREA, OPERATIONAL_UNIT — see note below; deliberately still
# no DB-level ForeignKey, for the identical reason AuthorityGrant's own
# docstring already gives: one generic column must keep working unchanged
# as more scope kinds gain real tables) — plus a string-keyed `scope_key`
# for the dimensions Core defines without any canonical numeric-id registry
# existing anywhere in this schema (DOMAIN/MODULE/PROCESS/PROCESS_PHASE),
# mirroring exactly how `OperationalSignature.domain`/`module`/`object_type`
# above are already plain strings with no FK for the identical reason.
#
# RESTAURANT vs OPERATIONAL_UNIT (TASK_ORG_RUNTIME_CONSISTENCY_FIXES,
# verified against the Restaurant Domain's own canonical docs before
# concluding anything — CLAUDE.md "NON assumere"): the runtime `Restaurant`
# table's docstring, and this schema's own `LegalEntity` docstring, call
# `Restaurant` "an Operational Unit" (a looser sense, contrasting it with
# being a Legal Entity, citing `01 Domains/Business Domain/Restaurant/Model/
# OU-Restaurant.md`'s "Extends: Operational Unit"). `01 Domains/Business
# Domain/Restaurant/Restaurant Semantic Model.md` §3 later reconciles this
# more precisely for the ACTUAL Core-hierarchy level each runtime row plays:
# runtime `Restaurant` = **Brand**; runtime `Location` = **Operational
# Unit/site**. These two statements are not reconciled with each other
# anywhere in the Restaurant Domain's own documentation — a pre-existing
# Restaurant-Domain terminology question, out of this Foundation's scope to
# resolve. This Foundation therefore deliberately does NOT treat
# `POSITION_SCOPE_RESTAURANT` and `POSITION_SCOPE_OPERATIONAL_UNIT` as
# interchangeable/matching — they remain independently scoped, and
# `POSITION_SCOPE_OPERATIONAL_UNIT.scope_id` is presented in the admin UI as
# a `Location` reference (the more specific reconciliation's own mapping),
# never merged with `RESTAURANT`'s own id space.
# ---------------------------------------------------------------------------

POSITION_SCOPE_CORPORATE = "CORPORATE"
POSITION_SCOPE_BRAND = "BRAND"
POSITION_SCOPE_LEGAL_ENTITY = "LEGAL_ENTITY"
POSITION_SCOPE_OPERATIONAL_UNIT = "OPERATIONAL_UNIT"
POSITION_SCOPE_RESTAURANT = "RESTAURANT"
POSITION_SCOPE_OPERATIONAL_AREA = "OPERATIONAL_AREA"
POSITION_SCOPE_DOMAIN = "DOMAIN"
POSITION_SCOPE_MODULE = "MODULE"
POSITION_SCOPE_PROCESS = "PROCESS"
POSITION_SCOPE_PROCESS_PHASE = "PROCESS_PHASE"
POSITION_SCOPE_GLOBAL = "GLOBAL"
POSITION_SCOPE_KINDS = (
    POSITION_SCOPE_CORPORATE, POSITION_SCOPE_BRAND, POSITION_SCOPE_LEGAL_ENTITY, POSITION_SCOPE_OPERATIONAL_UNIT,
    POSITION_SCOPE_RESTAURANT, POSITION_SCOPE_OPERATIONAL_AREA, POSITION_SCOPE_DOMAIN, POSITION_SCOPE_MODULE,
    POSITION_SCOPE_PROCESS, POSITION_SCOPE_PROCESS_PHASE, POSITION_SCOPE_GLOBAL,
)
# Which kinds carry their value in `scope_id` (an integer — real or, today,
# generic/tableless) vs. `scope_key` (a string) — `GLOBAL` carries neither.
POSITION_SCOPE_ID_KINDS = (
    POSITION_SCOPE_CORPORATE, POSITION_SCOPE_BRAND, POSITION_SCOPE_LEGAL_ENTITY, POSITION_SCOPE_OPERATIONAL_UNIT,
    POSITION_SCOPE_RESTAURANT, POSITION_SCOPE_OPERATIONAL_AREA,
)
POSITION_SCOPE_KEY_KINDS = (
    POSITION_SCOPE_DOMAIN, POSITION_SCOPE_MODULE, POSITION_SCOPE_PROCESS, POSITION_SCOPE_PROCESS_PHASE,
)

# Process.md, "Phases of Execution" — a chronological decomposition of
# Process execution, never a mandatory subdivision (a Process need not name
# a phase at all; `ProcessOwnership.phase IS NULL` means "owns the whole
# Process, not one specific phase").
PROCESS_PHASE_PLANNING = "PLANNING"
PROCESS_PHASE_SCHEDULING_PROGRAMMING = "SCHEDULING_PROGRAMMING"
PROCESS_PHASE_MANAGEMENT = "MANAGEMENT"
PROCESS_PHASE_OPERATIONS = "OPERATIONS"
PROCESS_PHASES = (
    PROCESS_PHASE_PLANNING, PROCESS_PHASE_SCHEDULING_PROGRAMMING, PROCESS_PHASE_MANAGEMENT, PROCESS_PHASE_OPERATIONS,
)

ATTENTION_PRIORITY_CRITICAL = "CRITICAL"
ATTENTION_PRIORITY_HIGH = "HIGH"
ATTENTION_PRIORITY_MEDIUM = "MEDIUM"
ATTENTION_PRIORITY_LOW = "LOW"
ATTENTION_PRIORITIES = (
    ATTENTION_PRIORITY_CRITICAL, ATTENTION_PRIORITY_HIGH, ATTENTION_PRIORITY_MEDIUM, ATTENTION_PRIORITY_LOW,
)

ATTENTION_STATUS_OPEN = "OPEN"
ATTENTION_STATUS_ACKNOWLEDGED = "ACKNOWLEDGED"
ATTENTION_STATUS_RESOLVED = "RESOLVED"
ATTENTION_STATUS_CANCELLED = "CANCELLED"
ATTENTION_STATUSES = (
    ATTENTION_STATUS_OPEN, ATTENTION_STATUS_ACKNOWLEDGED, ATTENTION_STATUS_RESOLVED, ATTENTION_STATUS_CANCELLED,
)


class Position(Base):
    """A stable organizational responsibility, independent of who currently
    occupies it (`Organizational Responsibility.md` §2) — NEVER derived
    automatically from a job title, a Clover/Tips Role, Domain Access, or an
    Employee's function (task §3): those are different concepts a Product
    Owner may choose to relate to a Position later, never a source this
    Foundation infers one from.

    No effective-dating on Position itself — `is_active` is a simple current-
    state toggle, matching `ActingIdentity.is_active`'s own pattern. The
    TEMPORAL dimension Core actually asks for (`Organizational Responsibility.
    md` §3: "a person occupies a Position for a period of time") lives on
    `PositionAssignment`/`PositionTemporaryCoverage` below, not here — a
    Position's own identity does not start/stop, only who occupies it does.

    Seed/demo Positions are a Product Owner configuration act, never
    auto-generated by this Foundation (task §14) — no row here names a real
    Rome's Flavours person or role unless the Product Owner creates it."""

    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_position_id: Mapped[int | None] = mapped_column(ForeignKey("positions.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Opt-in policy flag (TASK_ORG_CHART_ADMIN_PAGE §12): an admin marks a
    # specific Position as requiring at least one active Backup Position —
    # never assumed true for every Position (that would invent a Business
    # Rule no organization has actually stated). The Organizational
    # Coverage Check only flags a missing backup for Positions where this
    # is explicitly True.
    backup_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    parent_position: Mapped["Position | None"] = relationship(remote_side=[id])
    scopes: Mapped[list["PositionScope"]] = relationship(back_populates="position")


class PositionScope(Base):
    """One scope STATEMENT for a Position (`Organizational Responsibility.
    md` §2: "the Corporate/Brand/Operational Unit/Operational Area/Domain/
    Module/Process context within which its responsibility applies"). A
    Position may carry zero, one, or several of these (task §4: "NON è
    obbligatorio che ogni Position usi tutte queste dimensioni") — the
    Position's overall operating perimeter is the SET of its own
    `PositionScope` rows, never a single wide multi-column row (which would
    not compose cleanly when a Position spans e.g. two Restaurants)."""

    __tablename__ = "position_scopes"
    __table_args__ = (
        CheckConstraint(f"scope_type IN {POSITION_SCOPE_KINDS!r}", name="ck_position_scope_type"),
        CheckConstraint(
            "scope_type = 'GLOBAL' OR scope_id IS NOT NULL OR scope_key IS NOT NULL",
            name="ck_position_scope_value_required",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    position_id: Mapped[int] = mapped_column(ForeignKey("positions.id"), nullable=False, index=True)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scope_key: Mapped[str | None] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    position: Mapped["Position"] = relationship(back_populates="scopes")


class PositionAssignment(Base):
    """Position -> Occupant (Acting Identity), effective-dated
    (`Organizational Responsibility.md` §3). `valid_to IS NULL` means
    currently occupying. A Position with no row here at all — or none
    currently active — is VACANT (task §5), never silently treated as
    unowned or as an error. The same Acting Identity may occupy more than
    one Position (no uniqueness constraint on `acting_identity_id` alone);
    a Position may be reassigned over time (multiple rows, non-overlapping
    by convention of the service layer, never enforced by deleting or
    overwriting a prior row — Historical Integrity)."""

    __tablename__ = "position_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    position_id: Mapped[int] = mapped_column(ForeignKey("positions.id"), nullable=False, index=True)
    acting_identity_id: Mapped[int] = mapped_column(
        ForeignKey("acting_identities.id"), nullable=False, index=True
    )
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    position: Mapped["Position"] = relationship()
    acting_identity: Mapped["ActingIdentity"] = relationship()


class PositionTemporaryCoverage(Base):
    """Temporary coverage of one Position's responsibility by another
    Position OR directly by an Acting Identity (`Organizational
    Responsibility.md` §3: "a form of Delegation... explicit Grantor, a
    bounded scope and duration, auditable"). Exactly one of
    `delegate_position_id`/`delegate_acting_identity_id` is set — Core
    itself leaves open which shape a coverage takes (task §6); this
    Foundation supports both without preferring one.

    This is the SAME Delegation concept `AuthorityGrant` above already
    implements for Authority specifically (explicit Grantor via
    `granted_by_identity_id`, bounded duration, revocable via `revoked_at`
    rather than deleted) — never a second, parallel Delegation semantics
    (task §6). It is a distinct TABLE because what is being delegated here
    (occupancy of a Position) is shaped differently from what
    `AuthorityGrant` delegates (a domain/module/action permission), not
    because the underlying concept differs."""

    __tablename__ = "position_temporary_coverages"
    __table_args__ = (
        CheckConstraint(
            "(delegate_position_id IS NOT NULL) != (delegate_acting_identity_id IS NOT NULL)",
            name="ck_position_temporary_coverage_delegate_xor",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    covered_position_id: Mapped[int] = mapped_column(ForeignKey("positions.id"), nullable=False, index=True)
    delegate_position_id: Mapped[int | None] = mapped_column(ForeignKey("positions.id"), nullable=True)
    delegate_acting_identity_id: Mapped[int | None] = mapped_column(
        ForeignKey("acting_identities.id"), nullable=True
    )

    granted_by_identity_id: Mapped[int | None] = mapped_column(
        ForeignKey("acting_identities.id"), nullable=True
    )
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    covered_position: Mapped["Position"] = relationship(foreign_keys=[covered_position_id])
    delegate_position: Mapped["Position | None"] = relationship(foreign_keys=[delegate_position_id])
    delegate_acting_identity: Mapped["ActingIdentity | None"] = relationship(
        foreign_keys=[delegate_acting_identity_id]
    )
    granted_by_identity: Mapped["ActingIdentity | None"] = relationship(foreign_keys=[granted_by_identity_id])


class ProcessOwnership(Base):
    """Process (or Process Phase) -> responsible Position
    (`Organizational Responsibility.md` §4). `domain`/`module`/
    `process_name` are plain strings with no foreign key — deliberately:
    there is no canonical, cross-Domain Process registry table anywhere in
    this schema today (each Domain names its own Run/Process concept
    independently, e.g. `TipDistributionCalculationRun`), so this mirrors
    `OperationalSignature.domain`/`module`/`object_type`'s own, identical,
    already-established choice rather than inventing a competing Process
    registry (task §7: "NON creare Business Process definitions duplicati").

    `phase IS NULL` means this Position owns the Process as a whole; a
    different row per phase is legitimate but never mandatory (task §7 —
    "NON obbligare ogni Process ad avere quattro owner distinti").

    `scope_type`/`scope_id`/`scope_key` are an OPTIONAL override, same
    shape as `PositionScope` — when set, this specific ownership applies
    only within that scope (e.g. "Position A owns this Process, but only
    for Restaurant Y"); when NULL, the owning Position's own general
    `PositionScope` rows govern applicability instead. No uniqueness
    constraint is enforced across (domain, module, process_name, phase,
    scope): more than one candidate row is a normal, resolvable situation
    (`organizational_responsibility_service.resolve_process_owner` picks
    the one whose scope actually matches the caller's context) — an
    unresolvable ambiguity is surfaced as such, never guessed (task §9)."""

    __tablename__ = "process_ownerships"
    __table_args__ = (
        CheckConstraint(
            f"scope_type IS NULL OR scope_type IN {POSITION_SCOPE_KINDS!r}", name="ck_process_ownership_scope_type",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    domain: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    module: Mapped[str | None] = mapped_column(String(64), nullable=True)
    process_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    phase: Mapped[str | None] = mapped_column(String(32), nullable=True)

    position_id: Mapped[int] = mapped_column(ForeignKey("positions.id"), nullable=False, index=True)

    scope_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    scope_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scope_key: Mapped[str | None] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    position: Mapped["Position"] = relationship()


class AttentionItem(Base):
    """A cross-Domain "something requires human attention" record (Core
    `12_Attention_Management.md`) — NEVER a general report/dashboard row
    (task §8): it exists only for decisions required, authorizations
    required, exceptions, and problems to resolve.

    `source_domain`/`source_module`/`source_process_name`/`source_phase`
    identify what raised it, in the SAME plain-string shape `ProcessOwnership`
    uses to identify a Process (no competing identifier shape). `source_
    reference` is a free-form pointer to the originating Domain row (e.g.
    `"TipPaymentInstruction:123"`) — deliberately untyped, since the objects
    that can raise Attention vary by Domain and this shared table must not
    depend on every Domain's own schema (same rationale as `OperationalSignature.
    object_type`/`object_id` above).

    `reason` is the concise synthetic message (Core doc 12 §7's "I
    interrupted you for X. I would do Y."); `detail`/`proposed_action` carry
    the fuller technical context separately, so a consumer can show the
    short form first (task §8's "technical detail separato dal messaggio
    sintetico").

    Routing outcome is recorded, never silently discarded: `resolved_*`
    columns are populated when `attention_service.route_attention` succeeds;
    `routing_unresolved_reason` is populated instead when it cannot
    determine an effective recipient — the item stays OPEN either way (task
    §9: never assigned arbitrarily)."""

    __tablename__ = "attention_items"
    __table_args__ = (
        CheckConstraint(f"priority IN {ATTENTION_PRIORITIES!r}", name="ck_attention_item_priority"),
        CheckConstraint(f"status IN {ATTENTION_STATUSES!r}", name="ck_attention_item_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    source_domain: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_module: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_process_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_phase: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)

    reason: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposed_action: Mapped[str | None] = mapped_column(Text, nullable=True)

    priority: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=ATTENTION_STATUS_OPEN)

    # The context `attention_service.route_attention` resolves against —
    # same optional-override shape as `ProcessOwnership.scope_*` (e.g. which
    # Restaurant this specific Attention concerns), so routing can pick the
    # right Process Ownership candidate among several.
    scope_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    scope_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scope_key: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # CURRENT/latest routing outcome only — a convenience snapshot for
    # "who does this reach right now," never the audit trail. Overwritten by
    # every explicit `route_attention()` call (TASK_ORG_RUNTIME_CONSISTENCY_
    # FIXES §5): each such call ALSO appends an immutable
    # `AttentionRoutingResolution` row below, so a prior resolution is never
    # lost, only superseded here for quick reading. Nothing re-routes
    # automatically when a Position/Occupant changes — these fields change
    # only when something explicitly calls `route_attention()` again.
    resolved_process_owner_position_id: Mapped[int | None] = mapped_column(
        ForeignKey("positions.id"), nullable=True
    )
    resolved_recipient_acting_identity_id: Mapped[int | None] = mapped_column(
        ForeignKey("acting_identities.id"), nullable=True
    )
    # Conceptual values: DIRECT_OCCUPANT, TEMPORARY_COVERAGE, BACKUP_POSITION,
    # ORGANIZATIONAL_FALLBACK (TASK_ORG_CHART_ADMIN_PAGE §15 — "which fallback
    # would be used" must be visible, not just the final recipient). NULL
    # until routed, or when routing is unresolved.
    resolution_path: Mapped[str | None] = mapped_column(String(32), nullable=True)
    routing_unresolved_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by_identity_id: Mapped[int | None] = mapped_column(
        ForeignKey("acting_identities.id"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by_identity_id: Mapped[int | None] = mapped_column(ForeignKey("acting_identities.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    resolved_process_owner_position: Mapped["Position | None"] = relationship(
        foreign_keys=[resolved_process_owner_position_id]
    )
    resolved_recipient_acting_identity: Mapped["ActingIdentity | None"] = relationship(
        foreign_keys=[resolved_recipient_acting_identity_id]
    )
    acknowledged_by_identity: Mapped["ActingIdentity | None"] = relationship(
        foreign_keys=[acknowledged_by_identity_id]
    )
    resolved_by_identity: Mapped["ActingIdentity | None"] = relationship(foreign_keys=[resolved_by_identity_id])


class AttentionRoutingResolution(Base):
    """One IMMUTABLE record of a single `route_attention()` evaluation for
    an `AttentionItem` (TASK_ORG_RUNTIME_CONSISTENCY_FIXES §5) — the actual
    audit trail task §21's own audit requirements name, distinct from
    `AttentionItem`'s own `resolved_*`/`resolution_path` columns (a
    convenience snapshot of the LATEST evaluation only). Never updated once
    inserted — the same append-only discipline `OperationalSignature`
    already establishes above, applied here to routing evaluations
    specifically: a re-evaluation (whether from the "Re-evaluate routing
    now" admin action, or any future automated caller) always INSERTS a new
    row, never overwrites a prior one, so "when did routing happen, to
    whom, via which path, why, and was it re-routed later" all remain
    reconstructable. Nothing here causes a historical resolution to change
    on its own — a new row is created only when `route_attention()` is
    actually called again, never automatically when a Position/Occupant/
    Coverage changes elsewhere."""

    __tablename__ = "attention_routing_resolutions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attention_item_id: Mapped[int] = mapped_column(ForeignKey("attention_items.id"), nullable=False, index=True)

    resolved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    owner_position_id: Mapped[int | None] = mapped_column(ForeignKey("positions.id"), nullable=True)
    resolved_recipient_acting_identity_id: Mapped[int | None] = mapped_column(
        ForeignKey("acting_identities.id"), nullable=True
    )
    # Same conceptual values as `AttentionItem.resolution_path` — see there.
    resolution_path: Mapped[str | None] = mapped_column(String(32), nullable=True)
    unresolved_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    attention_item: Mapped["AttentionItem"] = relationship()
    owner_position: Mapped["Position | None"] = relationship()
    resolved_recipient_acting_identity: Mapped["ActingIdentity | None"] = relationship()


class PositionBackup(Base):
    """One entry in a Position's ORDERED Backup Position chain
    (TASK_ORG_CHART_ADMIN_PAGE §8) — distinct from `PositionTemporaryCoverage`
    above: a Backup Position is a STANDING organizational fact ("if this
    Position's normal resolution path fails, try this other Position next"),
    never date-bounded and never itself implying the backup is currently
    acting — whereas Temporary Coverage is an active, time-bounded
    Delegation that PRECEDES normal resolution entirely (task §9: a
    Position's own active coverage is still checked first, before ever
    consulting its backup chain).

    A Backup Position is NOT required to be the parent Position, a manager,
    or otherwise hierarchically superior (task §8) — `backup_position_id`
    may be any other Position the organization considers sufficiently
    authorized. `sequence` orders a chain when more than one backup is
    configured (1 = tried first); this Foundation does NOT recurse into a
    backup's OWN backup chain (task §8's "NON inventare escalation
    automatica verticale universale") — only the covered Position's own
    ordered list is walked."""

    __tablename__ = "position_backups"
    __table_args__ = (
        CheckConstraint("covered_position_id != backup_position_id", name="ck_position_backup_not_self"),
        UniqueConstraint("covered_position_id", "sequence", name="uq_position_backup_sequence"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    covered_position_id: Mapped[int] = mapped_column(ForeignKey("positions.id"), nullable=False, index=True)
    backup_position_id: Mapped[int] = mapped_column(ForeignKey("positions.id"), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    covered_position: Mapped["Position"] = relationship(foreign_keys=[covered_position_id])
    backup_position: Mapped["Position"] = relationship(foreign_keys=[backup_position_id])


class OrganizationalFallbackPolicy(Base):
    """A company-configured "if nothing else resolves, use this Position"
    rule (TASK_ORG_CHART_ADMIN_PAGE §14) — explicitly ORGANIZATIONAL POLICY,
    never a Core rule: Core does not fix "Unowned Attention -> CEO" or any
    other universal fallback (`Organizational Responsibility.md` §5,
    `12_Attention_Management.md` §9). For Rome's Flavours, the Product
    Owner may configure exactly this by creating one row here with
    `scope_type=GLOBAL` and `fallback_position_id` pointing at a
    Product-Owner-created "CEO" Position — no such row is created
    automatically by this Foundation.

    `scope_type`/`scope_id`/`scope_key` follow the same shape as
    `PositionScope`/`ProcessOwnership`'s own scope override — a policy may
    be scoped narrowly (e.g. only for one Restaurant) or apply via
    `GLOBAL`."""

    __tablename__ = "organizational_fallback_policies"
    __table_args__ = (
        CheckConstraint(f"scope_type IN {POSITION_SCOPE_KINDS!r}", name="ck_organizational_fallback_scope_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scope_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    fallback_position_id: Mapped[int] = mapped_column(ForeignKey("positions.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    fallback_position: Mapped["Position"] = relationship()


# ---------------------------------------------------------------------------
# Source-system provenance (task §33-35)
# ---------------------------------------------------------------------------


class SourceSystem(Base):
    """A source POS/system RF-One can ingest from (e.g. CLOVER). Never
    hard-coded elsewhere as the only possible source."""

    __tablename__ = "source_systems"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class IngestionRun(Base):
    """One execution of a source ingestion process. Supports future
    incremental imports and auditability; no ingestion logic lives here."""

    __tablename__ = "ingestion_runs"
    __table_args__ = (
        Index("ix_ingestion_runs_lock_key", "lock_key", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_system_id: Mapped[int] = mapped_column(
        ForeignKey("source_systems.id"), nullable=False
    )
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)

    source_window_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_window_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # TIPS_IMPORT_CONCURRENCY_GUARD_001 §5 — the execution token. Non-NULL
    # only while status == "RUNNING"; a UNIQUE index (see migration) makes
    # "another same-scope import is already RUNNING" a DB-enforced
    # constraint rather than an application-level check-then-act race — two
    # concurrent inserts for the same key can never both succeed, even
    # against SQLite's single-writer file lock. Set back to NULL the moment
    # the run reaches COMPLETE/PARTIAL/FAILED, releasing the guard.
    lock_key: Mapped[str | None] = mapped_column(String(128), nullable=True)

    source_system: Mapped[SourceSystem] = relationship()
    source_records: Mapped[list["SourceRecord"]] = relationship(back_populates="ingestion_run")


class SourceRecord(Base):
    """Lightweight raw-provenance record: what was retrieved, when, and
    where the full payload can be found. Not a duplicate data warehouse —
    large raw exports may remain on disk and be referenced via `raw_path`."""

    __tablename__ = "source_records"
    __table_args__ = (
        Index(
            "ix_source_records_system_entity_source",
            "source_system_id",
            "entity_type",
            "source_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ingestion_run_id: Mapped[int] = mapped_column(
        ForeignKey("ingestion_runs.id"), nullable=False
    )
    source_system_id: Mapped[int] = mapped_column(
        ForeignKey("source_systems.id"), nullable=False
    )

    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str] = mapped_column(String(128), nullable=False)

    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    raw_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    raw_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)

    ingestion_run: Mapped[IngestionRun] = relationship(back_populates="source_records")


# ---------------------------------------------------------------------------
# Merchant / Location (task §6)
# ---------------------------------------------------------------------------


class Merchant(Base):
    """The highest-level canonical business entity. Source provenance is
    added beyond the task's literal suggested field list, consistent with
    modeling principle F ("every canonical entity should have ... optional
    source references") — see DATABASE_SCHEMA.md."""

    __tablename__ = "merchants"
    __table_args__ = (UniqueConstraint("source_system_id", "source_merchant_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_system_id: Mapped[int | None] = mapped_column(
        ForeignKey("source_systems.id"), nullable=True
    )
    source_merchant_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    locations: Mapped[list["Location"]] = relationship(back_populates="merchant")


class Location(Base):
    """A physical/operational location of a Merchant. The current Clover
    source is single-merchant/single-location; this schema does not assume
    that remains true."""

    __tablename__ = "locations"
    __table_args__ = (UniqueConstraint("source_system_id", "source_location_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    merchant_id: Mapped[int] = mapped_column(ForeignKey("merchants.id"), nullable=False)
    source_system_id: Mapped[int | None] = mapped_column(
        ForeignKey("source_systems.id"), nullable=True
    )
    source_location_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Not source-confirmed for the current Clover merchant (TASK_CLOVER_003 §A) —
    # nullable, never defaulted, never invented. IANA timezone identifier
    # (e.g. "America/New_York"), never a raw GMT offset — DST/historical
    # timezone rules must remain interpretable (TASK_ORGANIZATION_002).
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Location Business Day Rule (TASK_SALES_002 / TASK_ORGANIZATION_002):
    # the smallest adequate Business Day Rule — a time-of-day, evaluated in
    # this Location's own `timezone`, AT OR ABOVE which an event's calendar
    # day is its own Business Date, and BELOW which the event's Business
    # Date is the previous calendar day (e.g. cutoff 04:00: a 23:45 event is
    # attributed to that same calendar day; a 00:30 event on the following
    # calendar day is attributed to the PRIOR calendar day — the Restaurant
    # Sales Model §6a worked example). Corrected wording (Business Date
    # Foundation task) — an earlier version of this comment, and of Sales
    # Model §6a's prose (not its worked example), stated the cutoff
    # direction inverted, which would have attributed nearly an entire
    # operating day to the wrong Business Date; the worked example and
    # ordinary "late-night operating day" semantics were used to resolve
    # this, not a new Product Owner decision. Nullable: a Location may exist
    # before this configuration is known; never fabricated from geography or
    # any other inference. The resulting `business_date` fact itself is
    # owned and persisted by Sales on `Order` (Restaurant Sales Model §6a;
    # `rfone_data_store/business_date.py`) — this column is only the
    # Location-level configuration input.
    operating_day_cutoff_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    merchant: Mapped[Merchant] = relationship(back_populates="locations")


# ---------------------------------------------------------------------------
# Physical Table / Table Service (task §7-9)
# ---------------------------------------------------------------------------


class PhysicalTable(Base):
    """A persistent restaurant resource. All attributes are nullable because
    Clover currently exposes no structured Table entity (TASK_CLOVER_003 §F)
    — values here are never invented by parsing `Order.title_raw`."""

    __tablename__ = "physical_tables"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)
    # Nullable FK (added by TASK_RESTAURANT_001) — a PhysicalTable MAY sit in a
    # canonical PhysicalArea (e.g. "Patio"), but no row is invented here; this
    # only becomes populated by a future, explicit RF-One configuration step.
    physical_area_id: Mapped[int | None] = mapped_column(
        ForeignKey("physical_areas.id"), nullable=True
    )

    table_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    seat_capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    area: Mapped[str | None] = mapped_column(String(128), nullable=True)
    indoor_outdoor: Mapped[str | None] = mapped_column(String(32), nullable=True)
    section: Mapped[str | None] = mapped_column(String(128), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class TableService(Base):
    """The canonical operational service event: one real service occasion
    involving a group of guests. Not the physical table; not the POS Order —
    see Restaurant Sales Model §2 and §5."""

    __tablename__ = "table_services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)

    opened_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Intentionally both retained — different evidence, never overwritten
    # from one another (Restaurant Sales Model §11-12; TASK_CLOVER_003 §G).
    declared_guest_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    derived_guest_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Illustrative values (not DB-enforced): NATIVE_POS_FIELD, TECHNICAL_ITEM,
    # MANUAL, OTHER, UNKNOWN — see Restaurant Sales Model §11.
    declared_guest_count_source: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Placeholders for future Table Service reconstruction logic (not
    # implemented by this task) — free-form, not constrained to an enum yet.
    reconstruction_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reconstruction_confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    physical_tables: Mapped[list["PhysicalTable"]] = relationship(
        secondary="table_service_physical_tables"
    )
    employees: Mapped[list["Employee"]] = relationship(secondary="table_service_employees")
    orders: Mapped[list["Order"]] = relationship(back_populates="table_service")


class TableServicePhysicalTable(Base):
    """M:N association. A Table Service may have zero, one, or several
    Physical Tables (e.g. joined tables, or none for a To Go service) — no
    mandatory primary table is modeled."""

    __tablename__ = "table_service_physical_tables"

    table_service_id: Mapped[int] = mapped_column(
        ForeignKey("table_services.id"), primary_key=True
    )
    physical_table_id: Mapped[int] = mapped_column(
        ForeignKey("physical_tables.id"), primary_key=True
    )


# ---------------------------------------------------------------------------
# Employee / Table Service ↔ Employee / Shift (task §10-12)
# ---------------------------------------------------------------------------


class Employee(Base):
    """A person who may participate in service, orders, payments, or
    shifts. `system_role` preserves only the source's own role/tier value —
    RF-One does not infer a precise restaurant role from it (task §10)."""

    __tablename__ = "employees"
    __table_args__ = (UniqueConstraint("source_system_id", "source_employee_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)

    source_system_id: Mapped[int | None] = mapped_column(
        ForeignKey("source_systems.id"), nullable=True
    )
    source_employee_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    custom_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    system_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # No active/inactive field is exposed by Clover (TASK_CLOVER_003 §B) —
    # nullable, never defaulted to True/False from an absent source signal.
    active: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    source_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_modified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class SourceRole(Base):
    """A source system's own named operational Role catalog entry (e.g.
    Clover's `Server`/`Host`/`BOH`/`Admin`) — TASK_CLOVER_004. Distinct from
    `Employee.system_role`, which preserves only the source's broader
    system-tier string (`EMPLOYEE`/`MANAGER`/`ADMIN`); `source_system_role`
    here is the same tier concept but as an attribute of the named Role
    catalog entry itself, not of any one Employee's membership in it."""

    __tablename__ = "source_roles"
    __table_args__ = (UniqueConstraint("source_system_id", "source_role_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)

    source_system_id: Mapped[int] = mapped_column(ForeignKey("source_systems.id"), nullable=False)
    source_role_id: Mapped[str] = mapped_column(String(128), nullable=False)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_system_role: Mapped[str | None] = mapped_column(String(32), nullable=True)


class EmployeeSourceRole(Base):
    """Employee <-> named source Role membership (TASK_CLOVER_004), as
    resolved via Clover's `employees?expand=role` / `roles?expand=employees`
    relationship — confirmed to return the SPECIFIC named Role, not merely
    the systemRole tier (correcting TASK_CLOVER_003's earlier conclusion
    that this was unresolvable). Clover exposes this only as a CURRENT-STATE
    snapshot — no historical role-assignment log was found — so no
    `valid_from`/`valid_to` validity window is invented here; `observed_at`
    is the ingestion-time fact "this membership was observed as of this
    snapshot," nothing more. `Employee.system_role` is never overwritten by
    this table, and no RF-One Restaurant Area is inferred from it."""

    __tablename__ = "employee_source_roles"
    __table_args__ = (UniqueConstraint("employee_id", "source_role_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id"), nullable=False, index=True
    )
    source_role_id: Mapped[int] = mapped_column(
        ForeignKey("source_roles.id"), nullable=False, index=True
    )

    source_system_id: Mapped[int] = mapped_column(ForeignKey("source_systems.id"), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TableServiceEmployee(Base):
    """M:N association. Distinct from the source-level Order.employee /
    Payment.employee single observations (task §11) — this is the broader
    participation relationship."""

    __tablename__ = "table_service_employees"

    table_service_id: Mapped[int] = mapped_column(
        ForeignKey("table_services.id"), primary_key=True
    )
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), primary_key=True)


class Shift(Base):
    """Atomic clock-in/out facts. Elapsed hours and employee totals are
    derived and are deliberately NOT stored here (task §12)."""

    __tablename__ = "shifts"
    __table_args__ = (UniqueConstraint("source_system_id", "source_shift_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id"), nullable=False, index=True
    )

    source_system_id: Mapped[int | None] = mapped_column(
        ForeignKey("source_systems.id"), nullable=True
    )
    source_shift_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    clock_in: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    clock_out: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    override_in_employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )
    override_in_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    override_out_employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )
    override_out_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    server_banking: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # The canonical Location where this specific Shift actually occurred
    # (TASK_TIPS_003), when deterministically known — distinct from
    # `Employee.location_id` (that Employee's source-ingestion/current-home
    # Location, used only as a presence-proxy fallback when a Shift itself
    # carries no Location evidence — see `rfone_data_store/tips/engine.py`,
    # `_shift_active_employee_ids`). NULL means unknown. RF-One never
    # backfills or infers this value from `Employee.location_id`, from
    # another Shift, or from any other source — it is populated only when a
    # future ingestion/configuration source provides genuine per-Shift
    # Location evidence. An Employee who legitimately works more than one
    # Location can therefore have some Shifts explicitly at one Location and
    # some at another, without ever changing `Employee.location_id`.
    location_id: Mapped[int | None] = mapped_column(
        ForeignKey("locations.id"), nullable=True, index=True
    )

    source_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_modified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


# ---------------------------------------------------------------------------
# Restaurant Profile / Organization (TASK_RESTAURANT_001)
#
# Canonical RF-One business/operational context — distinct from, and never
# equated with, Clover source semantics:
#
#   Clover named Role (SourceRole)   — source evidence only (TASK_CLOVER_004)
#   Clover systemRole (Employee.system_role) — source's broad tier string
#   RF-One Restaurant Role           — canonical operational role (this task)
#   RF-One Operational Area          — canonical functional grouping (this task)
#   RF-One Physical Area             — canonical physical zone (this task)
#
# No row in this section is ever auto-derived from Clover data. Restaurant,
# OperationalArea, PhysicalArea, RestaurantRole and OperationalAreaRole are
# Restaurant-specific configuration, created only by an explicit RF-One /
# Product Owner action (task §7, §19) — never inferred from SourceRole names.
# ---------------------------------------------------------------------------


class LegalEntity(Base):
    """The canonical juridical/employing/payroll entity (Product Owner
    decision, correcting the earlier `Restaurant`-as-Legal-Entity mapping —
    read-only verification confirmed `Restaurant` is formally an Operational
    Unit, per the approved `01 Domains/Business Domain/Restaurant/Model/
    OU-Restaurant.md`, "Extends: Operational Unit", never the juridical
    entity itself).

    Conceptually: `Corporate -> LegalEntity -> Restaurant (Operational Unit)
    -> Location`. No Corporate table is persisted anywhere in this schema —
    this MVP does not invent one merely to satisfy that conceptual chain,
    and `LegalEntity` exists independently here without requiring it. Brand
    (a separate, commercial/identity concept — `00 Core/Corporate.md`) is
    never repurposed as Legal Entity either.

    One `LegalEntity` may own many `Restaurant`s (`Restaurant.legal_entity_id`
    below); a Restaurant belongs to exactly one `LegalEntity` at a time in
    this MVP (no historical entity-change tracking yet). Compensation / Income
    Composition (`CompensationPreparationRun`, `EmployeeCompensationTerm`) is
    scoped by `legal_entity_id`, never by `restaurant_id` — an Employee
    working across several Restaurants owned by the same LegalEntity can
    therefore eventually be paid under one combined Compensation Preparation
    Run (not implemented by this MVP — see `rfone_data_store/payroll_calculation`
    module docstring).

    No tax ID/EIN, payroll-provider, or ownership/governance field is added
    here — this task establishes canonical identity and relationships only."""

    __tablename__ = "legal_entities"
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name="ck_legal_entities_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class Restaurant(Base):
    """The canonical business/operational restaurant RF-One models — NOT
    merely a Clover Merchant object (task §11). Deliberately narrow: this is
    canonical business identity/context, not a duplicate of every Merchant/
    Location field.

    `Restaurant` is an Operational Unit, never the Legal Entity itself
    (`01 Domains/Business Domain/Restaurant/Model/OU-Restaurant.md`,
    "Extends: Operational Unit") — `legal_entity_id` records which
    `LegalEntity` actually employs/pays people at this Restaurant.
    `legal_name` above remains this Restaurant's own business/context
    field (e.g. a local DBA name) and is never reinterpreted as the
    canonical `LegalEntity.legal_name`. Nullable only because existing
    Restaurant rows predate this column — never guessed for those."""

    __tablename__ = "restaurants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    legal_entity_id: Mapped[int | None] = mapped_column(
        ForeignKey("legal_entities.id"), nullable=True, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    default_currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    default_timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class RestaurantLocation(Base):
    """Restaurant <-> Location (task §12). Normalized rather than a direct FK
    on Restaurant so one Restaurant can be associated with one primary
    Location now and multiple Locations over time later, without a schema
    change. No uniqueness constraint on (restaurant_id, location_id) alone —
    a Restaurant could legitimately re-associate with the same Location again
    after a gap (e.g. `valid_to` closed, then reopened); overlap validation
    is an application/business-rule concern, not a blanket DB constraint.

    Primary Location integrity (TASK_ORGANIZATION_002): a Restaurant may have
    zero currently-active (`valid_to IS NULL`) primary (`is_primary = true`)
    Locations, or exactly one, but never more than one. This is enforced
    structurally below by a partial unique index scoped to open, primary
    rows only — historical rows (closed `valid_to`, or `is_primary` false/
    unset) are never constrained by it, so changing the primary Location
    over time (close the old row, open/insert the new one) remains fully
    representable without rewriting history."""

    __tablename__ = "restaurant_locations"
    __table_args__ = (
        Index(
            "ux_restaurant_locations_one_open_primary",
            "restaurant_id",
            unique=True,
            sqlite_where=text("is_primary = 1 AND valid_to IS NULL"),
            postgresql_where=text("is_primary = true AND valid_to IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("restaurants.id"), nullable=False, index=True
    )
    location_id: Mapped[int] = mapped_column(
        ForeignKey("locations.id"), nullable=False, index=True
    )

    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_primary: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class OperationalArea(Base):
    """A Restaurant-configured functional organizational area (task §13) —
    e.g. FOH/BOH/BAR/MANAGEMENT. These values are NEVER hard-coded as a
    universal Restaurant Domain enumeration; they exist only once a Restaurant
    (or its Product Owner) actually configures them. Answers: "in which
    functional part of the restaurant is this work performed?" — distinct
    from `PhysicalArea` ("where physically is it performed?")."""

    __tablename__ = "operational_areas"
    __table_args__ = (UniqueConstraint("restaurant_id", "name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("restaurants.id"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class PhysicalArea(Base):
    """A Restaurant-configured physical place/zone (task §14) — e.g. Dining
    Room, Patio, Bar Counter, Kitchen, Private Room. Distinct from
    `OperationalArea` (functional grouping) and from `PhysicalTable` (a single
    persistent table resource, which may optionally sit inside a
    PhysicalArea via `PhysicalTable.physical_area_id`). No PhysicalTable row
    is ever invented by this task to populate that link (task §14)."""

    __tablename__ = "physical_areas"
    __table_args__ = (UniqueConstraint("restaurant_id", "name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("restaurants.id"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    area_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class RestaurantRole(Base):
    """A Restaurant-configured canonical operational role (task §15) — e.g.
    Server, Host, Bartender, Cook, Dishwasher, Manager. These values are
    Restaurant configuration, never a hard-coded universal enum, and are
    distinct from `SourceRole` (Clover named Role — source evidence only),
    `Employee.system_role` (Clover systemRole tier) and personnel identity."""

    __tablename__ = "restaurant_roles"
    __table_args__ = (UniqueConstraint("restaurant_id", "name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("restaurants.id"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class OperationalAreaRole(Base):
    """M:N (task §16): which Restaurant Role/Operational Area combinations
    this Restaurant's configuration allows. NOT the Employee assignment
    itself (see `EmployeeAssignment`) — this only defines what is possible,
    e.g. a Manager Role being configured as valid in both FOH and Management.
    A Restaurant Role is deliberately NOT forced to belong to exactly one
    Operational Area (task §5)."""

    __tablename__ = "operational_area_roles"

    operational_area_id: Mapped[int] = mapped_column(
        ForeignKey("operational_areas.id"), primary_key=True
    )
    restaurant_role_id: Mapped[int] = mapped_column(
        ForeignKey("restaurant_roles.id"), primary_key=True
    )


class EmployeeAssignment(Base):
    """A temporally bounded fact describing how an Employee participates in
    a Restaurant (task §17): Employee + Restaurant + OperationalArea +
    RestaurantRole + time interval. This is the structure future Tips/Payroll
    must resolve through — see RESTAURANT_PROFILE.md's Tips/Payroll contract.

    Deliberately NOT used to decide who is "active" in a period —
    `Employee.active` (itself never populated by Clover, TASK_CLOVER_003) has
    no bearing on this table's meaning, and this table has no bearing on
    which Employees actually worked a given period either: that comes from
    Shift evidence (task §3). This table only resolves, for an Employee known
    to have worked via a Shift, what Role/Area applied at that time.

    Temporal, never overwritten in place (task §4): a Role/Area change closes
    the prior row's `valid_to` and opens a new row — history is preserved.
    `valid_to IS NULL` represents an open-ended/current assignment.

    Multiple concurrent assignments are allowed (task §5-6, e.g. a Manager
    valid in both FOH and Management at the same time) — no constraint forces
    one Employee to have only one Role/Area globally or at a given instant.
    The unique constraint below only rejects an exact duplicate row (same
    Employee, Area, Role, Location and start instant), not legitimate
    concurrency — a Location difference (e.g. Manager at Winter Park vs.
    Manager at Mount Dora, same Area/Role/instant) is never treated as a
    duplicate (TASK_ORGANIZATION_002).

    `location_id` participates in the uniqueness rule below, but ordinary SQL
    UNIQUE semantics treat every NULL as distinct from every other NULL, so a
    plain `UniqueConstraint` including a nullable `location_id` would not by
    itself catch an exact duplicate *Restaurant-wide* Assignment (both rows
    `location_id IS NULL`). The second, partial unique index below closes
    that gap for the `location_id IS NULL` case specifically, without
    constraining the location-specific rows a second time."""

    __tablename__ = "employee_assignments"
    __table_args__ = (
        UniqueConstraint(
            "employee_id", "operational_area_id", "restaurant_role_id", "location_id", "valid_from"
        ),
        Index(
            "ux_employee_assignments_dup_no_location",
            "employee_id", "operational_area_id", "restaurant_role_id", "valid_from",
            unique=True,
            sqlite_where=text("location_id IS NULL"),
            postgresql_where=text("location_id IS NULL"),
        ),
        Index("ix_employee_assignments_employee_valid_from", "employee_id", "valid_from"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id"), nullable=False, index=True
    )
    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("restaurants.id"), nullable=False, index=True
    )
    operational_area_id: Mapped[int] = mapped_column(
        ForeignKey("operational_areas.id"), nullable=False, index=True
    )
    restaurant_role_id: Mapped[int] = mapped_column(
        ForeignKey("restaurant_roles.id"), nullable=False, index=True
    )
    # Optional (TASK_ORGANIZATION_002): which canonical Location this
    # specific Assignment applies to, when Location-specific assignment is
    # operationally meaningful (e.g. "Server at Winter Park"). NULL means the
    # Assignment applies Restaurant-wide across every Location associated
    # with the Restaurant (e.g. a CEO/corporate-wide Role) — never forced.
    # This is the Assignment's own fact, distinct from `Employee.location_id`
    # (that Employee's source-ingestion/current-home Location; see
    # Employee Assignment.md) — a temporal Location change here (e.g. an
    # Employee moving from one Location to another) closes the prior
    # Assignment row and opens a new one, exactly like a Role/Area change.
    location_id: Mapped[int | None] = mapped_column(
        ForeignKey("locations.id"), nullable=True, index=True
    )
    # Optional (task §17): only if a stable physical-area assignment is
    # meaningful — NOT forced when physical working location varies shift by
    # shift. No PhysicalArea/PhysicalTable row is invented to populate this.
    physical_area_id: Mapped[int | None] = mapped_column(
        ForeignKey("physical_areas.id"), nullable=True
    )

    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Provenance (task §18): distinguishes a manually confirmed assignment
    # from one seeded by a future source-role mapping/import — never treated
    # as equivalent. Free-form string, not a rigid DB enum, matching this
    # schema's existing convention (e.g. `TableService.reconstruction_status`)
    # of leaving evolving classification fields unconstrained at the DB
    # level. Documented conceptual values: MANUAL, SOURCE_ROLE_MAPPING,
    # IMPORT, OTHER.
    assignment_source: Mapped[str] = mapped_column(String(32), nullable=False)
    source_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


# ---------------------------------------------------------------------------
# Tips — LEGACY, NON-CANONICAL, READ-ONLY (TASK_TIPS_001, retired by
# TIPS_LEGACY_ENGINE_RETIREMENT_001)
#
# `TipPolicy`/`TipPolicyComponent` were the ORIGINAL Payment-level tip
# calculation configuration, read by the now-DELETED `tips/engine.py`. That
# engine has been fully retired in favor of the canonical, Order-level Tip
# Distribution Engine (`tips/distribution_engine.py`, reading
# `TipDistributionRule`/`TipDistributionRuleVersion` below).
#
# These two classes are kept ONLY because their tables hold real historical
# configuration data (Rome's Flavours / Winter Park's actual approved Tip
# Policy, `configure_rome_flavours_tip_policy.py`'s output — 1 `tip_policies`
# row + 2 `tip_policy_components` rows, confirmed non-empty in the
# operational database at the time of retirement). No runtime code writes to
# or reads from these tables anymore, and no new write path may be added
# against them — they exist purely as inspectable historical record. The
# sibling `TipCalculationRun`/`TipAllocation`/`TipCalculationIssue` tables
# (the legacy engine's own *results*) were confirmed EMPTY at retirement time
# and were dropped outright (see migration
# `e2c7b4a9f1d6_drop_legacy_tip_calculation_tables.py`) — their model classes
# no longer exist.
# ---------------------------------------------------------------------------


class TipPolicy(Base):
    """LEGACY / NON-CANONICAL / READ-ONLY — see the module-section comment
    above. A Restaurant-configured, temporally valid Tip allocation policy
    (task §9). Never defaults to a universal percentage/role split — a
    Restaurant with no configured TipPolicy simply has no valid policy for
    any timestamp, which the calculation engine surfaces as an explicit
    `NO_VALID_POLICY` issue rather than silently picking one."""

    __tablename__ = "tip_policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("restaurants.id"), nullable=False, index=True
    )
    # Optional narrower scope (task §17 "optional location scope if
    # consistent with current RestaurantLocation design") — NULL means the
    # policy applies across every Location currently/historically associated
    # with the Restaurant, not just one.
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Free string, not a DB enum, matching this schema's existing convention
    # for evolving classification fields (e.g. `EmployeeAssignment.assignment_source`).
    # Conceptual values: DRAFT, ACTIVE, RETIRED.
    status: Mapped[str] = mapped_column(String(32), nullable=False)

    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    source_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    components: Mapped[list["TipPolicyComponent"]] = relationship(
        back_populates="tip_policy", order_by="TipPolicyComponent.sequence"
    )


class TipPolicyComponent(Base):
    """LEGACY / NON-CANONICAL / READ-ONLY — see the module-section comment
    above `TipPolicy`. One share of a `TipPolicy` (task §9-12)."""

    __tablename__ = "tip_policy_components"
    __table_args__ = (
        CheckConstraint(
            "recipient_basis <> 'ROLE_PRESENT_AT_PAYMENT' OR restaurant_role_id IS NOT NULL",
            name="ck_tip_policy_components_role_present_requires_role",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tip_policy_id: Mapped[int] = mapped_column(
        ForeignKey("tip_policies.id"), nullable=False, index=True
    )

    sequence: Mapped[int] = mapped_column(Integer, nullable=False)

    # Conceptual values: SERVICE_OWNER, ROLE_PRESENT_AT_PAYMENT (task §9).
    # Free string (not a DB enum) so a Restaurant/future task can extend the
    # set without a migration, matching this schema's existing convention.
    recipient_basis: Mapped[str] = mapped_column(String(32), nullable=False)
    # Required when recipient_basis == ROLE_PRESENT_AT_PAYMENT (enforced by
    # the CheckConstraint above); NULL when recipient_basis == SERVICE_OWNER,
    # since a service owner is resolved per-Order, not per-Role.
    restaurant_role_id: Mapped[int | None] = mapped_column(
        ForeignKey("restaurant_roles.id"), nullable=True
    )

    # Canonical decimal percent value (e.g. 80.0000 = 80%), same convention
    # as `DiscountDefinition.percentage` — never a binary float (task §10).
    # These are illustrative-only in every example; no default is asserted
    # at the schema level, and no row is ever inserted by this task.
    share_percentage: Mapped[Decimal] = mapped_column(Numeric(7, 4), nullable=False)

    # Conceptual values: EQUAL_ELIGIBLE_HEADCOUNT (task §12; the only method
    # actually implemented by the engine this task adds). Free string so a
    # future PRO_RATA_WORKED_TIME/WEIGHTED_ROLE/CONTRIBUTION_BASED method can
    # be added without a schema change or rewriting this economic model.
    split_method: Mapped[str] = mapped_column(String(64), nullable=False)

    # Conceptual values: RETURN_TO_SERVICE_OWNER, REDISTRIBUTE_TO_ELIGIBLE_COMPONENTS,
    # LEAVE_UNALLOCATED (task §11). No universal default — every TipPolicyComponent
    # must state its own behavior explicitly.
    no_eligible_behavior: Mapped[str] = mapped_column(String(64), nullable=False)

    active: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    tip_policy: Mapped[TipPolicy] = relationship(back_populates="components")


# ---------------------------------------------------------------------------
# Tip Distribution Rule (TIPS_DISTRIBUTION_RULES_001) — restaurant-
# configurable Source-Role -> Recipient-Role tip-OUT configuration, per
# `01 Domains/Business Domain/Restaurant/Functional Specifications/
# TIP_DISTRIBUTION_ENGINE_FUNCTIONAL_SPEC_001.md` §7-§9/§16 ("Host -> 10% of
# Tip + Gratuity", etc.). Deliberately a SEPARATE concept from
# `TipPolicy`/`TipPolicyComponent` above (which allocates a single Payment's
# own tip among SERVICE_OWNER/ROLE_PRESENT_AT_PAYMENT recipients) — this
# task does not reconcile, merge, or build on top of that engine.
#
# No calculation, eligibility, or allocation logic is implemented anywhere
# near these two tables (task's own explicit boundary) — they are pure
# restaurant-configurable DATA the universal engine will read once it
# exists. The universal engine itself must never hard-code Rome's Flavours'
# SERVER -> HOST 10% rule; that exists only as a seeded data row.
# ---------------------------------------------------------------------------

CALC_BASE_VOLUNTARY_TIP = "VOLUNTARY_TIP"
CALC_BASE_GRATUITY = "GRATUITY"
CALC_BASE_TIP_PLUS_GRATUITY = "TIP_PLUS_GRATUITY"
CALC_BASE_TOTAL_SALES = "TOTAL_SALES"
CALC_BASE_FOOD_SALES = "FOOD_SALES"
CALC_BASE_BEVERAGE_SALES = "BEVERAGE_SALES"
# The exact, closed vocabulary the functional spec §8 gives — not extended
# by this task ("do not invent additional Calculation Base types unless the
# specification explicitly requires them").
TIP_DISTRIBUTION_CALCULATION_BASES = (
    CALC_BASE_VOLUNTARY_TIP, CALC_BASE_GRATUITY, CALC_BASE_TIP_PLUS_GRATUITY,
    CALC_BASE_TOTAL_SALES, CALC_BASE_FOOD_SALES, CALC_BASE_BEVERAGE_SALES,
)
# TIP_DISTRIBUTION_ENGINE_001 §6/§8 — of the closed vocabulary above, only
# these three are actually computable by `tips/distribution_engine.py` today
# (TOTAL_SALES/FOOD_SALES/BEVERAGE_SALES remain valid, storable rule
# configuration — the schema must not prevent them — but the engine reports
# a clear NOT_IMPLEMENTED anomaly rather than guessing if one is ever used).
TIP_DISTRIBUTION_ENGINE_IMPLEMENTED_CALCULATION_BASES = (
    CALC_BASE_VOLUNTARY_TIP, CALC_BASE_GRATUITY, CALC_BASE_TIP_PLUS_GRATUITY,
)

# TIP_DISTRIBUTION_ENGINE_001 §6/§9/§12/§14 — the only Eligibility Mode /
# Distribution Method / No-Eligible-Recipient Behavior the engine implements
# yet. Free-string columns (not DB CheckConstraints), matching this schema's
# existing convention for evolving classification fields (e.g.
# `TipPolicyComponent.no_eligible_behavior`) — so a future Eligibility Mode
# (spec §12's PERIOD_HOURS) or Distribution Method (spec §13's
# HOURS_PROPORTIONAL/WEIGHTED_HOURS) can be added without a migration; the
# engine itself is what currently only recognizes the one value below.
ELIGIBILITY_MODE_ACTIVE_AT_SETTLEMENT = "ACTIVE_AT_SETTLEMENT"
DISTRIBUTION_METHOD_EQUAL = "EQUAL"
NO_ELIGIBLE_RECIPIENT_SOURCE_RETAINS = "SOURCE_RETAINS"
TRANSACTION_SCOPE_ALL = "ALL"


class TipDistributionRule(Base):
    """The stable identity of one restaurant-configured tip-out rule (spec
    §7) — e.g. "Server -> Host". `is_active` is a simple, non-versioned
    on/off switch (task item #10), deliberately separate from the versioned
    configuration in `TipDistributionRuleVersion` below (task item #9):
    deactivating a rule never itself creates a new version, and editing the
    rule's configuration never touches this flag."""

    __tablename__ = "tip_distribution_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(ForeignKey("restaurants.id"), nullable=False, index=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    versions: Mapped[list["TipDistributionRuleVersion"]] = relationship(
        back_populates="rule", order_by="TipDistributionRuleVersion.version_number"
    )


class TipDistributionRuleVersion(Base):
    """One effective-dated, complete configuration snapshot of a
    `TipDistributionRule` (spec §16) — append-only. NEVER updated or deleted
    once created (task's own explicit "never rewrite historical rule
    versions"); editing a rule creates a new version here and closes the
    PREVIOUS version's own `effective_to` only — no other column on a prior
    version row is ever touched. Historical periods remain reconstructable
    by selecting whichever version's `[effective_from, effective_to)` window
    contains the timestamp in question."""

    __tablename__ = "tip_distribution_rule_versions"
    __table_args__ = (
        UniqueConstraint("rule_id", "version_number", name="uq_tip_distribution_rule_version_number"),
        CheckConstraint(
            "calculation_base IN ('VOLUNTARY_TIP','GRATUITY','TIP_PLUS_GRATUITY','TOTAL_SALES','FOOD_SALES',"
            "'BEVERAGE_SALES')",
            name="ck_tip_distribution_rule_version_calculation_base",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("tip_distribution_rules.id"), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # Restaurant-configured operational roles (task items #3/#4) — reuses
    # the existing `RestaurantRole` catalog (already restaurant-scoped,
    # already populated for Rome's Flavours) rather than a parallel
    # free-text role concept.
    source_role_id: Mapped[int] = mapped_column(ForeignKey("restaurant_roles.id"), nullable=False)
    recipient_role_id: Mapped[int] = mapped_column(ForeignKey("restaurant_roles.id"), nullable=False)

    calculation_base: Mapped[str] = mapped_column(String(32), nullable=False)
    # Canonical decimal PERCENT value (e.g. 10.0000 = 10%), same convention
    # as `TipPolicyComponent.share_percentage`/`DiscountDefinition.percentage`
    # — never a binary float (task's own explicit "do not introduce
    # floating-point business logic").
    rate: Mapped[Decimal] = mapped_column(Numeric(7, 4), nullable=False)

    # TIP_DISTRIBUTION_ENGINE_001 §6-§9/§11/§21 — how the engine determines
    # recipients, splits the pool among them, what happens with zero eligible
    # recipients, and which transactions this rule applies to. Conceptual
    # values today: eligibility_mode=ACTIVE_AT_SETTLEMENT (spec §12),
    # distribution_method=EQUAL (spec §13), no_eligible_recipient_behavior=
    # SOURCE_RETAINS (spec §14), transaction_scope=ALL (spec §11) — see the
    # `*_validate_*` functions in `distribution_rule_service.py` for what is
    # actually accepted today.
    eligibility_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    distribution_method: Mapped[str] = mapped_column(String(32), nullable=False)
    no_eligible_recipient_behavior: Mapped[str] = mapped_column(String(32), nullable=False)
    transaction_scope: Mapped[str] = mapped_column(String(32), nullable=False)

    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Free text, matching this schema's pre-ActingIdentity convention for
    # this kind of provenance field (e.g. legacy `SelectionRuleSetVersion.
    # confirmed_by`) — this task does not integrate ActingIdentity, which
    # was not requested here.
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    rule: Mapped[TipDistributionRule] = relationship(back_populates="versions")
    source_role: Mapped["RestaurantRole"] = relationship(foreign_keys=[source_role_id])
    recipient_role: Mapped["RestaurantRole"] = relationship(foreign_keys=[recipient_role_id])


# ---------------------------------------------------------------------------
# Tip Distribution Engine (TIP_DISTRIBUTION_ENGINE_001) — the atomic
# calculation/allocation apparatus that READS `TipDistributionRule`/
# `TipDistributionRuleVersion` above (never hard-codes Rome's Flavours'
# SERVER -> HOST 10% rule) and Order-level source facts, and WRITES the
# results below. Deliberately named/tabled distinctly from the legacy
# `TipCalculationRun`/`TipAllocation`/`TipCalculationIssue` above, which
# belong to a different, still-operational engine
# (`tips/engine.py`/`TipPolicy`) with a different primary unit (Payment, not
# Order), a different temporal anchor (`Payment.created_at`, not Settlement
# Time) and a different role-resolution model — that engine is untouched by
# this task (task §22 "existing operational data" / §1 "do not create a
# parallel distribution-rule implementation" refers to `TipDistributionRule`/
# `distribution_rule_service.py`, reused as-is below, not to the legacy
# TipPolicy engine, which this task does not reconcile, merge, or build on).
# ---------------------------------------------------------------------------


class TipDistributionCalculationRun(Base):
    """One execution of the Tip Distribution Engine over a requested
    Restaurant/period (task §15) — the minimum calculation-run/period
    structure needed to choose From/Through, calculate, group atomic
    results, and distinguish one run from another. Stops at a clean
    CALCULATED/REVIEWABLE state (`status` reaches COMPLETE or FAILED) —
    the later OPEN -> CALCULATED -> REVIEWED -> APPROVED/LOCKED workflow
    (spec §20) is explicitly out of scope for this task."""

    __tablename__ = "tip_distribution_calculation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(ForeignKey("restaurants.id"), nullable=False, index=True)

    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Conceptual values: RUNNING, COMPLETE, FAILED.
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Task §16 "recalculation safety": an explicit, auditable replacement
    # strategy — a recalculation creates a NEW run and sets the PRIOR run's
    # own `superseded_by_calculation_run_id` to it; the prior run's
    # allocations are never deleted or rewritten. Mirrors the existing
    # `TipCalculationRun.superseded_by_calculation_run_id` convention
    # (legacy engine), application-set rather than DB-enforced, so a future
    # LOCKED status can refuse superseding without a schema change.
    superseded_by_calculation_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("tip_distribution_calculation_runs.id"), nullable=True
    )

    allocations: Mapped[list["TipDistributionAllocation"]] = relationship(back_populates="calculation_run")


class TipDistributionAllocation(Base):
    """One atomic, auditable unit of the Tip Distribution Engine's output
    (task §14) — "Order X's Rule Version Y produced a pool of Z, of which
    Employee W received/would-have-received this amount, because
    <eligibility basis>." Never an opaque per-employee total: every row
    traces to exactly one Order and one `TipDistributionRuleVersion`.

    Exactly one row per (calculation run, Order, Rule Version, recipient) —
    including the SOURCE_RETAINS case, represented as a single row with
    `recipient_employee_id IS NULL`, `no_eligible_recipient = True`, and
    `allocated_amount_minor = 0` (task §11's "result must explicitly record
    that no recipient was eligible" — never silently omitted)."""

    __tablename__ = "tip_distribution_allocations"
    __table_args__ = (
        UniqueConstraint(
            "calculation_run_id", "order_id", "rule_version_id", "recipient_employee_id",
            name="uq_tip_distribution_allocation_recipient",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    calculation_run_id: Mapped[int] = mapped_column(
        ForeignKey("tip_distribution_calculation_runs.id"), nullable=False, index=True
    )
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)
    # Order.employee_id at calculation time (task §4's tip owner) — snapshot
    # here rather than re-joined through Order every time, and nullable
    # because Order.employee_id itself is nullable (an unresolved source
    # owner is a real, if rare, source-data state, not one this engine
    # invents a value for).
    source_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True, index=True)

    rule_version_id: Mapped[int] = mapped_column(
        ForeignKey("tip_distribution_rule_versions.id"), nullable=False, index=True
    )
    # Snapshot of the Rule Version's own configuration at calculation time
    # (task §14's explicit field list) — never re-derived by joining back to
    # a rule version that could, in principle, be a different row shape in
    # the future; `TipDistributionRuleVersion` rows are themselves already
    # immutable once created, so this is redundant-but-explicit, matching
    # the task's own explainability requirement.
    calculation_base: Mapped[str] = mapped_column(String(32), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(7, 4), nullable=False)

    # Minor units (cents) throughout — same money convention as every other
    # amount in this schema. Never floating point.
    base_amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    pool_amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)

    # NULL exactly when `no_eligible_recipient` is True (SOURCE_RETAINS).
    recipient_employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True, index=True
    )
    recipient_eligibility_basis: Mapped[str] = mapped_column(Text, nullable=False)
    no_eligible_recipient: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    allocated_amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)

    # The Order's Settlement Time used for this calculation (task §5/§14) —
    # snapshot, since eligibility/rule-version selection both derived from
    # it at the moment this row was created.
    settlement_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    calculation_run: Mapped[TipDistributionCalculationRun] = relationship(back_populates="allocations")
    order: Mapped["Order"] = relationship()
    source_employee: Mapped["Employee | None"] = relationship(foreign_keys=[source_employee_id])
    recipient_employee: Mapped["Employee | None"] = relationship(foreign_keys=[recipient_employee_id])
    rule_version: Mapped[TipDistributionRuleVersion] = relationship()


# ---------------------------------------------------------------------------
# Tip Payment Execution (TASK_TIPS_CORE2_PILOT) — Core 2.0 Process-First pilot
#
# Payment Instruction identity and outcome tracking for paying out a
# TipDistributionCalculationRun's finalized per-Employee net amount through
# an external Payment Executor (Mercury — `rfone_data_store.technical.
# connectors.mercury`). RF-One's own idempotency (`uq_tip_payment_instruction_
# run_employee` below) is the PRIMARY duplicate-payment guard — Mercury's own
# duplicate protection is a safety net only, never relied upon for
# correctness (`01 Domains/Business Domain/Restaurant/Tips/Tips Payment
# Execution.md`, "Idempotency").
#
# `EmployeeExternalPaymentAccount` is the stable Employee <-> external-
# provider-recipient reference (task §7): RF-One never stores routing/account
# numbers here or anywhere else — only the provider's own opaque recipient
# id, which the provider (Mercury) resolves to real bank details on its own
# side. Scoped to Tips ownership for this pilot; a second Domain needing the
# same pattern (e.g. a future Payroll Mercury path) would promote this to a
# shared location rather than duplicate it — not done here since Tips is the
# only consumer today.
# ---------------------------------------------------------------------------


class EmployeeExternalPaymentAccount(Base):
    """One stable reference from an Employee to their payment destination at
    an external Payment Executor. `provider_recipient_id` is Mercury's own
    opaque recipient id (a UUID) — never a routing/account number, which
    stays exclusively on Mercury's side (task §7, §6 "Sensitive Data").

    An Employee may have at most one ACTIVE reference per provider at a
    time — `is_active` is a soft toggle (never deleted) so history of which
    external recipient an Employee's payouts went to over time is
    preserved, consistent with Historical Integrity."""

    __tablename__ = "employee_external_payment_accounts"
    __table_args__ = (
        CheckConstraint("provider IN ('MERCURY')", name="ck_employee_external_payment_accounts_provider"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    provider_recipient_id: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    employee: Mapped["Employee"] = relationship()


class TipPaymentInstruction(Base):
    """One Payment Instruction: "pay this Employee this amount for this
    finalized TipDistributionCalculationRun" — RF-One's own canonical
    identity for a Tip payout, independent of Mercury's own Transaction
    identity (`provider_transaction_id` below is evidence of what Mercury
    did with this instruction, never the instruction's own identity).

    `uq_tip_payment_instruction_run_employee` is the primary double-payment
    guard (task §5): at most one Payment Instruction ever exists for a given
    (calculation_run_id, employee_id) pair — created once
    (`payment_instruction.get_or_create_payment_instructions_for_run`) and
    never duplicated, regardless of how many times a Process Activation
    re-evaluates a Business Date's readiness.

    Conceptual status values (task §3 — concepts preserved, exact strings
    chosen to fit this codebase's existing UPPER_SNAKE convention):

        READY            -> instruction exists, not yet submitted to Mercury
        SUBMITTED        -> POST accepted by Mercury; Transaction id known
        SENT             -> observed Mercury status `sent`/`pending` with no
                             failure yet (Outcome not yet fully verified —
                             see `postedAt`/`provider_status` for detail)
        OUTCOME_VERIFIED -> `provider_status == 'sent'` AND `posted_at` is
                             set (task §10) — the strongest state this pilot
                             asserts; still re-checkable, never immutable
        NEEDS_ATTENTION  -> a failure class (task §11 A/B/C/E) or a REVERSED
                             transition (task §10's "Outcome Reopened") —
                             `failure_class`/`reason_for_failure`/`priority`
                             describe why
        CANCELLED        -> Mercury reported `cancelled`/`blocked` for this
                             Transaction
    """

    __tablename__ = "tip_payment_instructions"
    __table_args__ = (
        UniqueConstraint(
            "calculation_run_id", "employee_id", name="uq_tip_payment_instruction_run_employee",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    calculation_run_id: Mapped[int] = mapped_column(
        ForeignKey("tip_distribution_calculation_runs.id"), nullable=False, index=True
    )
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)

    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)

    # Deterministically derived from (calculation_run_id, employee_id,
    # ACTIVE recipient reference id) — `payment_instruction.
    # build_idempotency_key` — computed and persisted at first submit
    # attempt, not at instruction creation (NULL until then, since no
    # recipient reference may exist yet). Reused unchanged on every retry
    # against the SAME resolved recipient (a transient-failure retry must
    # stay deduplicated); a NEW key is derived only when the active
    # reference itself changes (a genuine correction, e.g. a wrong
    # recipient was linked and then fixed). This split was forced by
    # empirical Mercury sandbox behavior (TASK_TIPS_CORE2_PILOT): resending
    # the SAME idempotencyKey after the underlying payload's `recipientId`
    # changed returns HTTP 409, not a safe idempotent replay — reusing the
    # instruction's original key across a recipient correction would
    # therefore have permanently wedged that instruction. Unique once set,
    # as a second, independent structural guard against ever submitting two
    # different instructions under the same key.
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)

    # Conceptual values: READY, SUBMITTED, SENT, OUTCOME_VERIFIED,
    # NEEDS_ATTENTION, CANCELLED — see class docstring.
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="READY")

    provider: Mapped[str] = mapped_column(String(16), nullable=False, default="MERCURY")
    provider_account_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_recipient_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_transaction_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Mercury's OWN transaction status verbatim (pending/sent/cancelled/
    # failed/reversed/blocked) — never remapped/renamed, so a human
    # inspecting this row can cross-check it directly against Mercury's own
    # dashboard (`Tips Payment Execution.md`, "Use Mercury's real states").
    provider_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Task §11 — WHY `status` became NEEDS_ATTENTION/CANCELLED. Conceptual
    # values: SYNCHRONOUS_VALIDATION, DUPLICATE_PROTECTION, PROVIDER_STATUS_
    # FAILURE, PROVIDER_UNAVAILABLE, OUTCOME_REOPENED, RECIPIENT_NOT_
    # CONFIGURED — set by `payment_instruction.py`, never guessed from
    # `reason_for_failure` text by any OTHER module (task §11's "isola la
    # provider-specific interpretation nel connector").
    failure_class: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reason_for_failure: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Conceptual values: CRITICAL, HIGH, MEDIUM, LOW (Core 2.0, `12_Attention_
    # Management.md` §3) — set contextually by `payment_instruction.py`
    # (task §13), never a fixed event->priority table. NULL until this
    # instruction first needs attention.
    priority: Mapped[str | None] = mapped_column(String(16), nullable=True)

    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    calculation_run: Mapped[TipDistributionCalculationRun] = relationship()
    employee: Mapped["Employee"] = relationship()


# `TipCalculationRun`/`TipAllocation`/`TipCalculationIssue` — the legacy
# engine's own RESULT tables — were removed entirely (models + tables) by
# TIPS_LEGACY_ENGINE_RETIREMENT_001: confirmed empty (0 rows each) in the
# operational database at retirement time, so unlike `TipPolicy`/
# `TipPolicyComponent` above there was no historical data to preserve. See
# migration `e2c7b4a9f1d6_drop_legacy_tip_calculation_tables.py`.


# ---------------------------------------------------------------------------
# Restaurant Profile bootstrap from source configuration (TASK_RESTAURANT_003)
#
# Adds the source-control / mapping / reconciliation layer needed to
# instantiate a Restaurant Profile FROM a source system's (e.g. Clover)
# current configuration, while preserving the same boundary the rest of the
# Organization section already enforces:
#
#   SourceRole ≠ RestaurantRole, even when the initial configured names
#   happen to coincide (never a DB-level equivalence, only an explicit,
#   Restaurant-scoped SourceRoleMapping row).
#
#   Source configuration ≠ canonical Restaurant semantics — a source system
#   is evidence used to instantiate a specific Restaurant's Profile through
#   explicit mappings, never an automatic ontology mapping.
#
# Nothing here is Rome's-Flavours-specific schema — every row is scoped by
# restaurant_id/source_system_id, but no Restaurant-specific column or enum
# is added to any of these tables.
# ---------------------------------------------------------------------------


class RestaurantProfileSourceControl(Base):
    """Records the explicit `T0` at which RF-One begins managing a
    source-derived Restaurant Profile for one (Restaurant, SourceSystem)
    pair (task §4). Before `managed_from`, RF-One makes no automatic claim
    that today's source role mapping was historically true; at/after it,
    RF-One maintains temporal Restaurant Profile history prospectively —
    see `EmployeeAssignment` and `SourceRoleMapping` below, both of which
    anchor their first-ever row to this timestamp (never file-modification
    time or process-startup time — always this persisted column).

    Not a DB-enforced singleton: the bootstrap engine reuses the existing
    row with `status = ACTIVE` for a given (restaurant_id, source_system_id)
    rather than creating a second one on every run (idempotency, task §14).
    A second row could legitimately exist in the future if a Restaurant
    ever re-baselines against a replacement source system."""

    __tablename__ = "restaurant_profile_source_controls"
    __table_args__ = (
        Index(
            "ix_profile_source_controls_restaurant_source",
            "restaurant_id",
            "source_system_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("restaurants.id"), nullable=False, index=True
    )
    source_system_id: Mapped[int] = mapped_column(
        ForeignKey("source_systems.id"), nullable=False, index=True
    )

    managed_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Free string, matching this schema's existing convention for evolving
    # classification fields. Conceptual values: ACTIVE, RETIRED.
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    snapshot_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class SourceRoleMapping(Base):
    """Explicit, temporally-valid `SourceRole -> RestaurantRole` mapping,
    scoped to one Restaurant (task §5). Preserves `SourceRole ≠
    RestaurantRole` even when the initial configured names are identical —
    the mapping row is the only thing that connects them, never an implicit
    name match. A Restaurant Profile configuration decision, never universal
    across Restaurants (a second Restaurant importing the same Clover
    merchant, hypothetically, would need its own mapping rows)."""

    __tablename__ = "source_role_mappings"
    __table_args__ = (
        UniqueConstraint("restaurant_id", "source_role_id", "valid_from"),
        Index("ix_source_role_mappings_restaurant_source_role", "restaurant_id", "source_role_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("restaurants.id"), nullable=False, index=True
    )
    source_system_id: Mapped[int] = mapped_column(
        ForeignKey("source_systems.id"), nullable=False
    )
    source_role_id: Mapped[int] = mapped_column(
        ForeignKey("source_roles.id"), nullable=False, index=True
    )
    restaurant_role_id: Mapped[int] = mapped_column(
        ForeignKey("restaurant_roles.id"), nullable=False, index=True
    )

    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Conceptual values: ACTIVE, RETIRED.
    mapping_status: Mapped[str] = mapped_column(String(32), nullable=False)
    # Conceptual values: CLOVER_SOURCE_ROLE_BOOTSTRAP (this task), MANUAL,
    # OTHER — free string, not a DB enum, same convention as
    # `EmployeeAssignment.assignment_source`.
    mapping_source: Mapped[str] = mapped_column(String(64), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ProfileBootstrapRun(Base):
    """One execution of the Restaurant Profile bootstrap/sync engine (task
    §15), mirroring `TipCalculationRun`'s dry-run/persist pattern: the
    engine always builds its rows inside the caller's session and never
    commits — the caller decides `DRY_RUN` (rollback) vs `PERSIST` (commit)."""

    __tablename__ = "profile_bootstrap_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("restaurants.id"), nullable=False, index=True
    )
    source_system_id: Mapped[int] = mapped_column(
        ForeignKey("source_systems.id"), nullable=False
    )

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Conceptual values: RUNNING, COMPLETE, FAILED.
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    # Conceptual values: DRY_RUN, PERSIST.
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    issues: Mapped[list["RestaurantProfileReconciliationIssue"]] = relationship(
        back_populates="bootstrap_run"
    )


class RestaurantProfileReconciliationIssue(Base):
    """A source→profile congruence problem, surfaced rather than silently
    corrected (task §9) — RF-One must not silently copy a malformed POS
    configuration into canonical Restaurant Profile assumptions. Scoped to
    the `ProfileBootstrapRun` that detected it; the bootstrap engine
    deduplicates against any still-unresolved (`status IS NULL`) issue with
    the same (restaurant_id, issue_type, employee_id, source_role_id,
    restaurant_role_id, mapping_id) key before creating a new row, so a
    reconciliation issue is never duplicated by repeated idempotent runs
    (task §14)."""

    __tablename__ = "restaurant_profile_reconciliation_issues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bootstrap_run_id: Mapped[int] = mapped_column(
        ForeignKey("profile_bootstrap_runs.id"), nullable=False, index=True
    )
    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("restaurants.id"), nullable=False, index=True
    )

    # Conceptual values (task §9): CURRENT_EMPLOYEE_WITHOUT_SOURCE_ROLE,
    # SOURCE_ROLE_WITHOUT_PROFILE_MAPPING, PROFILE_MAPPING_WITHOUT_CURRENT_SOURCE_ROLE,
    # CURRENT_EMPLOYEE_WITH_UNMAPPED_SOURCE_ROLE, EMPLOYEE_ASSIGNMENT_MISSING_AFTER_BOOTSTRAP,
    # SOURCE_ROLE_RELATIONSHIP_INCONSISTENT, DUPLICATE_OR_OVERLAPPING_MAPPING.
    # Free string, not a DB enum — only the subset actually produced by real
    # engine logic is ever written.
    issue_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # Conceptual values: BLOCKING, WARNING.
    severity: Mapped[str] = mapped_column(String(16), nullable=False)

    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    source_role_id: Mapped[int | None] = mapped_column(ForeignKey("source_roles.id"), nullable=True)
    restaurant_role_id: Mapped[int | None] = mapped_column(
        ForeignKey("restaurant_roles.id"), nullable=True
    )
    mapping_id: Mapped[int | None] = mapped_column(
        ForeignKey("source_role_mappings.id"), nullable=True
    )

    details: Mapped[str] = mapped_column(Text, nullable=False)
    # Reserved for a future review workflow — nullable, left NULL
    # ("unresolved") by the bootstrap engine; used only as the dedup key's
    # "still open" test described above.
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)

    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    bootstrap_run: Mapped[ProfileBootstrapRun] = relationship(back_populates="issues")


# ---------------------------------------------------------------------------
# Order Type / Order (task §13-14)
# ---------------------------------------------------------------------------


class OrderType(Base):
    """Configuration/catalog data (e.g. Table, To Go, Delivery)."""

    __tablename__ = "order_types"
    __table_args__ = (UniqueConstraint("source_system_id", "source_order_type_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)

    source_system_id: Mapped[int | None] = mapped_column(
        ForeignKey("source_systems.id"), nullable=True
    )
    source_order_type_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    min_order_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_order_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    configured_fee: Mapped[int | None] = mapped_column(Integer, nullable=True)
    average_order_time: Mapped[int | None] = mapped_column(Integer, nullable=True)

    active: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class Order(Base):
    """A commercial/POS grouping of sold units and settlements — the
    canonical model does NOT assume 1 Order = 1 Table Service, 1 Payment, or
    1 physical unit per line (Restaurant Sales Model §5, §13; TASK_CLOVER_003)."""

    __tablename__ = "orders"
    __table_args__ = (UniqueConstraint("source_system_id", "source_order_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)
    # Nullable: Table Service reconstruction is not implemented by this task.
    table_service_id: Mapped[int | None] = mapped_column(
        ForeignKey("table_services.id"), nullable=True, index=True
    )

    # Nullable (RFONE_OPERATIONAL_DATA_MODEL_001) — modeling principle F
    # ("every canonical entity should have an RF-One primary key and
    # optional source references"), already applied to Merchant/Location/
    # Employee/Shift; Order previously required a source system/external id
    # for every row, which would have structurally prevented a future
    # natively-created RF-One Order (e.g. from an RF-One POS) from ever
    # existing without inventing a fake external identity. An
    # externally-sourced Order (the only kind that exists today) still
    # always carries both.
    source_system_id: Mapped[int | None] = mapped_column(ForeignKey("source_systems.id"), nullable=True)
    source_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    source_employee_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True, index=True
    )
    order_type_id: Mapped[int | None] = mapped_column(ForeignKey("order_types.id"), nullable=True)
    # Canonical resolved FK (added by TASK_DATABASE_002's pre-ingestion schema
    # review), alongside the raw source reference — see device_source_id.
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id"), nullable=True)
    device_source_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    client_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    modified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # The canonical Business Date (operating day) this Order is attributed
    # to — owned by Sales/Order, per `01 Domains/Business Domain/Restaurant/
    # Sales/Restaurant Sales Model.md` §6a. Computed ONCE, from this Order's
    # Settlement Time (`rfone_data_store.business_date.
    # get_order_settlement_time` — reused, not redefined) and the Location's
    # Business Day Rule (`Location.timezone` + `Location.
    # operating_day_cutoff_time`) in effect at that time, then persisted here
    # — never recomputed at read time, and never retroactively rewritten by
    # a later change to the Location's own cutoff configuration (Sales
    # Model §6a, "Historical immutability"). Tips, Compensation, Performance,
    # and any other Domain MUST reuse this field for "which operating day does
    # this Order belong to" — none of them may independently compute or
    # redefine a competing business-date rule (Sales Model §6a, "Cross-
    # domain use"). Nullable: existing/historical Orders predate this
    # capability, and a Business Date is never invented when the required
    # inputs (Settlement Time, Location, Location timezone, Location
    # operating_day_cutoff_time) are not all resolvable — see
    # `rfone_data_store/business_date.py`.
    business_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payment_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pay_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)

    # Minor units (cents) — see money convention in module docstring.
    subtotal: Mapped[int | None] = mapped_column(Integer, nullable=True)
    discount_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tax_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Preserved verbatim; Clover currently uses this for table/zone-like free
    # text (TASK_CLOVER_003 §F). Never parsed inside this model (task §14).
    title_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    test_mode: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    manual_transaction: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    tax_removed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_vat: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    table_service: Mapped[TableService | None] = relationship(back_populates="orders")
    order_items: Mapped[list["OrderItem"]] = relationship(back_populates="order")
    payments: Mapped[list["Payment"]] = relationship(back_populates="order")
    order_discounts: Mapped[list["OrderDiscount"]] = relationship(back_populates="order")
    order_fees: Mapped[list["OrderFee"]] = relationship(back_populates="order")


# ---------------------------------------------------------------------------
# Item / Category / Modifier catalog (task §15-18)
# ---------------------------------------------------------------------------


class Item(Base):
    """Anything sellable — NOT "current menu item" (Restaurant Sales Model §8;
    TASK_CLOVER_003 §I). `item_nature` is an RF-One classification and is
    never auto-derived from the item name."""

    __tablename__ = "items"
    __table_args__ = (UniqueConstraint("source_system_id", "source_item_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)

    # Nullable (CANONICAL_OPERATIONAL_DB_FINALIZATION_001) — modeling
    # principle F, same rationale as Order's own comment.
    source_system_id: Mapped[int | None] = mapped_column(ForeignKey("source_systems.id"), nullable=True)
    source_item_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Nullable despite appearing alongside `name` in the task's suggested
    # field list: TASK_CLOVER_003 measured sku/code at 98.1%/99.8% coverage,
    # not 100% — forcing NOT NULL would contradict the empirical evidence.
    sku: Mapped[str | None] = mapped_column(String(128), nullable=True)
    code: Mapped[str | None] = mapped_column(String(128), nullable=True)

    current_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_without_vat: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    item_type: Mapped[str | None] = mapped_column(String(32), nullable=True)

    item_nature: Mapped[str | None] = mapped_column(String(64), nullable=True)

    active: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    source_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_modified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    categories: Mapped[list["Category"]] = relationship(secondary="item_categories")
    modifiers: Mapped[list["Modifier"]] = relationship(secondary="item_modifiers")


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("source_system_id", "source_category_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)

    # Nullable (CANONICAL_OPERATIONAL_DB_FINALIZATION_001) — modeling
    # principle F, same rationale as Order's own comment.
    source_system_id: Mapped[int | None] = mapped_column(ForeignKey("source_systems.id"), nullable=True)
    source_category_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)


class ItemCategory(Base):
    """M:N. TASK_CLOVER_003 empirically confirmed an Item may belong to
    zero, one, or several Categories (up to 15 observed) — task §16."""

    __tablename__ = "item_categories"

    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), primary_key=True)


class ModifierGroup(Base):
    __tablename__ = "modifier_groups"
    __table_args__ = (UniqueConstraint("source_system_id", "source_modifier_group_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)

    # Nullable (CANONICAL_OPERATIONAL_DB_FINALIZATION_001) — modeling
    # principle F, same rationale as Order's own comment.
    source_system_id: Mapped[int | None] = mapped_column(ForeignKey("source_systems.id"), nullable=True)
    source_modifier_group_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)

    modifiers: Mapped[list["Modifier"]] = relationship(back_populates="modifier_group")


class Modifier(Base):
    """A POS-defined variant/option. Semantic nature (true product variant
    vs. service instruction, e.g. "Extra mozzarella" vs. "First") is
    deliberately NOT encoded here — task §17, TASK_CLOVER_003 §K."""

    __tablename__ = "modifiers"
    __table_args__ = (UniqueConstraint("source_system_id", "source_modifier_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)
    modifier_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("modifier_groups.id"), nullable=True
    )

    # Nullable (CANONICAL_OPERATIONAL_DB_FINALIZATION_001) — modeling
    # principle F, same rationale as Order's own comment.
    source_system_id: Mapped[int | None] = mapped_column(ForeignKey("source_systems.id"), nullable=True)
    source_modifier_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    alternate_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    price_delta: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    modifier_group: Mapped[ModifierGroup | None] = relationship(back_populates="modifiers")


class ItemModifier(Base):
    """M:N — Modifiers available/associated with an Item (catalog
    availability), distinct from a Modifier actually selected on a
    historical sale (`OrderItemModifier`) — task §18."""

    __tablename__ = "item_modifiers"

    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), primary_key=True)
    modifier_id: Mapped[int] = mapped_column(ForeignKey("modifiers.id"), primary_key=True)


# ---------------------------------------------------------------------------
# Order Item / Order Item ↔ Modifier (task §19-20)
# ---------------------------------------------------------------------------


class OrderItem(Base):
    """The most granular source sales line available. Quantity is NOT
    guaranteed to be exactly one physical unit (TASK_CLOVER_003, correcting
    an earlier assumption) — stored as `Numeric` to preserve fractions, and
    never defaulted to 1 when missing."""

    __tablename__ = "order_items"
    __table_args__ = (UniqueConstraint("source_system_id", "source_line_item_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)
    item_id: Mapped[int | None] = mapped_column(
        ForeignKey("items.id"), nullable=True, index=True
    )

    # Nullable — see Order's own comment (RFONE_OPERATIONAL_DATA_MODEL_001 /
    # modeling principle F).
    source_system_id: Mapped[int | None] = mapped_column(ForeignKey("source_systems.id"), nullable=True)
    source_line_item_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    # The line's own name as observed at sale time — independent of the
    # catalog Item's current name (historical-value principle, task §4D).
    source_name: Mapped[str | None] = mapped_column(Text, nullable=True)

    quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    quantity_decimal_digits: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unit_name: Mapped[str | None] = mapped_column(String(64), nullable=True)

    historical_unit_price: Mapped[int | None] = mapped_column(Integer, nullable=True)

    guest_number: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    guest_label_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)

    item_code_raw: Mapped[str | None] = mapped_column(String(128), nullable=True)

    is_revenue: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_order_fee: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    printed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    refunded_flag: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    exchanged_flag: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    line_item_info_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)

    order: Mapped[Order] = relationship(back_populates="order_items")
    item: Mapped[Item | None] = relationship()
    modifiers: Mapped[list["OrderItemModifier"]] = relationship(back_populates="order_item")
    discounts: Mapped[list["OrderItemDiscount"]] = relationship(back_populates="order_item")
    taxes: Mapped[list["OrderItemTax"]] = relationship(back_populates="order_item")


class OrderItemModifier(Base):
    """A Modifier actually selected on a historical Order Item. Preserves
    enough source identity to audit modifications even where a catalog
    Modifier cannot be resolved (`modifier_id` nullable) — task §20."""

    __tablename__ = "order_item_modifiers"
    __table_args__ = (UniqueConstraint("order_item_id", "source_modification_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_item_id: Mapped[int] = mapped_column(
        ForeignKey("order_items.id"), nullable=False, index=True
    )
    modifier_id: Mapped[int | None] = mapped_column(ForeignKey("modifiers.id"), nullable=True)

    # Nullable (CANONICAL_OPERATIONAL_DB_FINALIZATION_001) — modeling
    # principle F, same rationale as Order's own comment: a native (non-
    # externally-sourced) OrderItemModifier must remain creatable.
    source_system_id: Mapped[int | None] = mapped_column(ForeignKey("source_systems.id"), nullable=True)
    source_modification_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    name_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    amount: Mapped[int | None] = mapped_column(Integer, nullable=True)

    order_item: Mapped[OrderItem] = relationship(back_populates="modifiers")


# ---------------------------------------------------------------------------
# Discounts (task §22-24)
# ---------------------------------------------------------------------------


class DiscountDefinition(Base):
    """Optional catalog discount definition. Not every applied discount
    references one — TASK_CLOVER_003 confirmed ad hoc discounts exist."""

    __tablename__ = "discount_definitions"
    __table_args__ = (UniqueConstraint("source_system_id", "source_discount_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)

    # Nullable (CANONICAL_OPERATIONAL_DB_FINALIZATION_001) — modeling
    # principle F, same rationale as Order's own comment.
    source_system_id: Mapped[int | None] = mapped_column(ForeignKey("source_systems.id"), nullable=True)
    source_discount_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Canonical decimal percent value (e.g. 50.0000 = 50%), independent of
    # any source-specific integer encoding.
    percentage: Mapped[Decimal | None] = mapped_column(Numeric(7, 4), nullable=True)
    amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class OrderDiscount(Base):
    """An Order-level applied discount. `percentage` and `amount` are both
    independently nullable — TASK_CLOVER_003 found catalog-referenced,
    ad hoc percentage, AND ad hoc fixed-amount shapes, all real (task §23)."""

    __tablename__ = "order_discounts"
    __table_args__ = (UniqueConstraint("order_id", "source_discount_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False)
    discount_definition_id: Mapped[int | None] = mapped_column(
        ForeignKey("discount_definitions.id"), nullable=True
    )

    # Nullable (CANONICAL_OPERATIONAL_DB_FINALIZATION_001) — modeling
    # principle F, same rationale as Order's own comment.
    source_system_id: Mapped[int | None] = mapped_column(ForeignKey("source_systems.id"), nullable=True)
    # The source's own id for this applied-discount element (present on every
    # Clover example observed, but kept nullable for sources that may not
    # supply one).
    source_discount_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    name_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    percentage: Mapped[Decimal | None] = mapped_column(Numeric(7, 4), nullable=True)
    amount: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Preserves the exact applied-discount element as observed, so a future
    # reviewer can audit which of the confirmed shapes (catalog-referenced /
    # ad hoc percentage / ad hoc amount) actually produced this row.
    raw_shape_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)

    order: Mapped[Order] = relationship(back_populates="order_discounts")


class OrderItemDiscount(Base):
    """An Order Item-level applied discount. Kept structurally distinct
    from `OrderDiscount` — never collapsed together (task §24)."""

    __tablename__ = "order_item_discounts"
    __table_args__ = (UniqueConstraint("order_item_id", "source_discount_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_item_id: Mapped[int] = mapped_column(
        ForeignKey("order_items.id"), nullable=False, index=True
    )
    discount_definition_id: Mapped[int | None] = mapped_column(
        ForeignKey("discount_definitions.id"), nullable=True
    )

    # Nullable (CANONICAL_OPERATIONAL_DB_FINALIZATION_001) — modeling
    # principle F, same rationale as Order's own comment.
    source_system_id: Mapped[int | None] = mapped_column(ForeignKey("source_systems.id"), nullable=True)
    source_discount_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    name_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    percentage: Mapped[Decimal | None] = mapped_column(Numeric(7, 4), nullable=True)
    amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_shape_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)

    order_item: Mapped[OrderItem] = relationship(back_populates="discounts")


# ---------------------------------------------------------------------------
# Tax / Fee (task §25-27)
# ---------------------------------------------------------------------------


class TaxRate(Base):
    __tablename__ = "tax_rates"
    __table_args__ = (UniqueConstraint("source_system_id", "source_tax_rate_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)

    # Nullable (CANONICAL_OPERATIONAL_DB_FINALIZATION_001) — modeling
    # principle F, same rationale as Order's own comment.
    source_system_id: Mapped[int | None] = mapped_column(ForeignKey("source_systems.id"), nullable=True)
    source_tax_rate_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Canonical decimal fraction (e.g. 0.065000 = 6.5%), not Clover's own
    # `rate / 10_000_000` integer encoding (canonical model ≠ Clover model).
    rate: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    active: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class OrderItemTax(Base):
    """Order-level tax total remains on `Order.tax_total`; this table
    preserves line-item tax detail for reconciliation/analysis, without
    treating Payment-level tax as conceptual ownership (task §26)."""

    __tablename__ = "order_item_taxes"
    __table_args__ = (UniqueConstraint("order_item_id", "source_tax_reference"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_item_id: Mapped[int] = mapped_column(
        ForeignKey("order_items.id"), nullable=False, index=True
    )
    tax_rate_id: Mapped[int | None] = mapped_column(ForeignKey("tax_rates.id"), nullable=True)

    amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rate_applied: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)

    # Nullable (CANONICAL_OPERATIONAL_DB_FINALIZATION_001) — modeling
    # principle F, same rationale as Order's own comment.
    source_system_id: Mapped[int | None] = mapped_column(ForeignKey("source_systems.id"), nullable=True)
    source_tax_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)

    order_item: Mapped[OrderItem] = relationship(back_populates="taxes")


class OrderFee(Base):
    """Supports native fee mechanisms (e.g. Clover's synthetic Service
    Charge line item) while preserving provenance to the source line —
    task §27. Ordinary Items are never auto-classified as fees by name."""

    __tablename__ = "order_fees"
    # CANONICAL_OPERATIONAL_DB_FINALIZATION_001 — matches the exact composite
    # key both ingestion paths (acquisition.py's `_ingest_fee_line_items` and
    # ingest.py's bulk pipeline) already use to look up an existing row.
    __table_args__ = (UniqueConstraint("order_id", "source_line_item_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False)

    # Nullable — see Order's own comment (RFONE_OPERATIONAL_DATA_MODEL_001 /
    # modeling principle F). `source_fee_id` was already nullable.
    source_system_id: Mapped[int | None] = mapped_column(ForeignKey("source_systems.id"), nullable=True)
    source_fee_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Raw reference to the synthetic OrderItem-shaped source line this fee
    # was reconstructed from, if any — provenance only, not a hard FK.
    source_line_item_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    fee_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # CLOVER_TIPS_INGESTION_001 — the raw Clover `note` string the line item
    # carried (e.g. "Service Charge"), preserved verbatim alongside the
    # derived `fee_type` classification. `fee_type` answers "what RF-One
    # classified this as"; `note_raw` answers "what did the source actually
    # say", so a future reviewer can audit the classification rule itself
    # without needing to re-fetch Clover.
    note_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)

    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    percentage: Mapped[Decimal | None] = mapped_column(Numeric(7, 4), nullable=True)

    order: Mapped[Order] = relationship(back_populates="order_fees")


# ---------------------------------------------------------------------------
# Tender / Payment / Payment Tip / Refund (task §28-31)
# ---------------------------------------------------------------------------


class Tender(Base):
    """`source_type` preserves whatever structural type the source
    supplies, but is NOT used as a cash/card classification —
    TASK_CLOVER_003 disproved `opensCashDrawer` as a reliable signal for
    the current merchant (task §28)."""

    __tablename__ = "tenders"
    __table_args__ = (UniqueConstraint("source_system_id", "source_tender_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)

    # Nullable (CANONICAL_OPERATIONAL_DB_FINALIZATION_001) — modeling
    # principle F, same rationale as Order's own comment.
    source_system_id: Mapped[int | None] = mapped_column(ForeignKey("source_systems.id"), nullable=True)
    source_tender_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    label: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    active: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class Payment(Base):
    """An independent atomic settlement entity. One Order may have many
    Payments, including FAILED ones — TASK_CLOVER_003 confirmed Clover's own
    nested `Order.payments` silently excludes failed attempts; this table is
    populated from the top-level Payments collection, not the nested one
    (an ingestion-layer concern, not modeled here, but the schema must not
    make failed Payments unrepresentable) — task §29."""

    __tablename__ = "payments"
    __table_args__ = (UniqueConstraint("source_system_id", "source_payment_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)

    # Nullable — see Order's own comment (RFONE_OPERATIONAL_DATA_MODEL_001 /
    # modeling principle F).
    source_system_id: Mapped[int | None] = mapped_column(ForeignKey("source_systems.id"), nullable=True)
    source_payment_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True, index=True
    )
    source_employee_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    tender_id: Mapped[int | None] = mapped_column(ForeignKey("tenders.id"), nullable=True)
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id"), nullable=True)
    device_source_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    client_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    modified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    # Source-reported tax figure on the Payment itself — kept distinct from
    # `Order.tax_total` and `OrderItemTax`, per the tax-ownership principle
    # (task §26, §38): Payment does not own Tax, it settles it.
    tax_amount_source: Mapped[int | None] = mapped_column(Integer, nullable=True)

    cash_tendered: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cashback_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)

    result: Mapped[str | None] = mapped_column(String(32), nullable=True)
    offline: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)

    order: Mapped[Order] = relationship(back_populates="payments")
    tip: Mapped["PaymentTip | None"] = relationship(
        back_populates="payment", uselist=False, cascade="all, delete-orphan"
    )
    refunds: Mapped[list["Refund"]] = relationship(back_populates="payment")


class PaymentTip(Base):
    """1:0..1 with Payment. `source_present` distinguishes "tip field
    absent from source" from "tip explicitly present and 0" — task §30,
    TASK_CLOVER_003's core Tip finding. Service Charge is never derived
    into Tip here."""

    __tablename__ = "payment_tips"

    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id"), primary_key=True)
    amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_present: Mapped[bool] = mapped_column(Boolean, nullable=False)

    payment: Mapped[Payment] = relationship(back_populates="tip")


class Refund(Base):
    """Mandatory, first-class entity. TASK_CLOVER_003 confirmed refunds are
    available only through Clover's dedicated Refund resource and are
    invisible from Order.payment_state / Payment.result / OrderItem's
    refunded flag — this table must never be inferred from those (task §31).
    One Payment may have multiple Refunds (e.g. future partial refunds)."""

    __tablename__ = "refunds"
    __table_args__ = (UniqueConstraint("source_system_id", "source_refund_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Nullable — see Order's own comment (RFONE_OPERATIONAL_DATA_MODEL_001 /
    # modeling principle F).
    source_system_id: Mapped[int | None] = mapped_column(ForeignKey("source_systems.id"), nullable=True)
    source_refund_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id"), nullable=True, index=True
    )
    payment_id: Mapped[int | None] = mapped_column(
        ForeignKey("payments.id"), nullable=True, index=True
    )
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)

    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id"), nullable=True)
    device_source_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    tax_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tip_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    voided: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    order: Mapped[Order | None] = relationship()
    payment: Mapped[Payment | None] = relationship(back_populates="refunds")


# ---------------------------------------------------------------------------
# Device (task §32)
# ---------------------------------------------------------------------------


class Device(Base):
    """Lightweight POS terminal identity. Hardware configuration fields
    (e.g. Clover's `pinDisabled`, `offlinePayments*`) are deliberately not
    stored — task §32."""

    __tablename__ = "devices"
    __table_args__ = (UniqueConstraint("source_system_id", "source_device_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)

    # Nullable (CANONICAL_OPERATIONAL_DB_FINALIZATION_001) — modeling
    # principle F, same rationale as Order's own comment.
    source_system_id: Mapped[int | None] = mapped_column(ForeignKey("source_systems.id"), nullable=True)
    source_device_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    device_type: Mapped[str | None] = mapped_column(String(64), nullable=True)


# ---------------------------------------------------------------------------
# Payroll (TASK_PAYROLL_001) — Administration Domain, transversal, independent
# from Restaurant / Personnel Management / ADP / jurisdiction labor law. See
# `01 Domains/Shared Domains/Administration/Payroll/` for the Domain-level definitions this
# schema implements without redefining. Money is minor units (cents), never
# floating point, matching the rest of this schema; every total (Payroll
# Employer Cost, run totals) is computed from the atomic fact tables below,
# never stored as a redundant column.
# ---------------------------------------------------------------------------


class PayrollSchedule(Base):
    """The configured recurring cadence under which normal Payroll Periods
    are generated for a Restaurant/company (Payroll Schedule and Period.md).
    Supports at least WEEKLY/BIWEEKLY/MONTHLY; never a hard-coded universal
    default — a Restaurant/company chooses the one its payroll provider and
    operating policy support. Deliberately independent of `WorkweekDefinition`
    below — changing payroll frequency never implies a different legal
    Workweek boundary, and vice versa."""

    __tablename__ = "payroll_schedules"
    __table_args__ = (UniqueConstraint("restaurant_id", "code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("restaurants.id"), nullable=False, index=True
    )

    # Conceptual values: WEEKLY, BIWEEKLY, MONTHLY. Free string, not a DB
    # enum, matching this schema's existing convention for evolving
    # classification fields (e.g. `EmployeeAssignment.assignment_source`).
    schedule_type: Mapped[str] = mapped_column(String(16), nullable=False)
    code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    active: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class WorkweekDefinition(Base):
    """A Restaurant/company-configured recurring legal/compensation
    evaluation interval — NOT determined by `PayrollSchedule` (Payroll
    Schedule and Period.md, "The canonical invariant this corrects": a
    biweekly Payroll Period is never treated as an 80-hour overtime
    evaluation window; overtime, where it is ever computed, must be
    evaluated per Workweek by a future jurisdiction/labor-rule layer, not by
    this table or by any generic Payroll code). Rome's Flavours' current
    configuration is Monday -> Sunday; one BIWEEKLY PayrollPeriod contains
    two Workweeks under that configuration."""

    __tablename__ = "workweek_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("restaurants.id"), nullable=False, index=True
    )

    # 0=Monday .. 6=Sunday (Python `date.weekday()` convention).
    start_weekday: Mapped[int] = mapped_column(Integer, nullable=False)

    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EmployeeCompensationTerm(Base):
    """Employee-specific, temporal compensation configuration (Compensation
    Terms.md). Never attached to a RestaurantRole as a universal rate — two
    Employees performing the same function may legitimately have different
    compensation, and one Employee may hold more than one concurrently
    applicable term (different `function_label`) — multiple functions are
    never treated as a conflict. History is never overwritten: a
    compensation change closes the prior row's `valid_to` and opens a new
    row with its own `valid_from`.

    `legal_entity_id` is the Legal Entity dimension required by the
    Compensation & Income Composition functional specification (`01 Domains/
    Shared Domains/Personnel Management/Compensation/
    COMPENSATION_AND_INCOME_COMPOSITION_001.md` §5) — the same Employee
    may legitimately hold concurrently-effective terms for different Legal
    Entities (e.g. Server at $12/hour for Legal Entity A and Server at
    $15/hour for Legal Entity B, same effective dates) and this is never a
    conflict, the same way multiple `function_label`s are never a conflict.
    Product Owner correction: an earlier version of this column was named
    `restaurant_id` and pointed at `restaurants.id` — read-only verification
    then confirmed `Restaurant` is formally an Operational Unit, never the
    Legal Entity, so it has been replaced with `legal_entity_id` pointing at
    the canonical `LegalEntity` model instead; `restaurant_id` never shipped
    (this table's own change was itself still uncommitted). Nullable only
    because historical rows created before this column existed never had a
    value to record — never guessed for those (same convention as
    `PayrollImportRun.acquisition_method`); the Payroll Calculation Engine's
    validation requires it to be set and to match the calculation run's
    Legal Entity before using a term — a NULL `legal_entity_id` is always
    rejected, since it cannot prove which Legal Entity the term belongs to
    (a data-readiness/backfill condition, not a model contradiction).
    Distinct from `restaurant_role_id` below, which remains optional
    provenance-only and carries no Legal Entity meaning; Restaurant/
    Operational Unit is deliberately NOT part of this canonical compensation
    identity."""

    __tablename__ = "employee_compensation_terms"
    __table_args__ = (
        UniqueConstraint("employee_id", "legal_entity_id", "function_label", "valid_from"),
        CheckConstraint(
            "(compensation_basis = 'HOURLY' AND hourly_rate_minor IS NOT NULL "
            "AND salaried_period_amount_minor IS NULL) "
            "OR (compensation_basis = 'SALARIED' AND salaried_period_amount_minor IS NOT NULL "
            "AND hourly_rate_minor IS NULL)",
            name="ck_employee_compensation_terms_basis_matches_amount",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    legal_entity_id: Mapped[int | None] = mapped_column(
        ForeignKey("legal_entities.id"), nullable=True, index=True
    )

    # Smallest provider-independent way to distinguish concurrent terms for
    # one Employee (Compensation Terms.md, "Multiple functions / multiple
    # rates") — never a universal role ontology owned by Payroll.
    function_label: Mapped[str] = mapped_column(String(255), nullable=False)
    # Optional provenance only — where the current Restaurant Role/Employee
    # Assignment can be referenced safely, this stays optional so Payroll
    # never becomes semantically dependent on Restaurant to be valid.
    restaurant_role_id: Mapped[int | None] = mapped_column(
        ForeignKey("restaurant_roles.id"), nullable=True
    )

    # Conceptual values: HOURLY, SALARIED (Compensation Terms.md).
    compensation_basis: Mapped[str] = mapped_column(String(16), nullable=False)
    # Minor units (cents) per hour. NULL unless compensation_basis == HOURLY
    # (enforced by the CheckConstraint above).
    hourly_rate_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Minor units (cents) of BASE PAY PER PAYROLL PERIOD — never an annual
    # salary; annual contractual salary, if it exists, lives elsewhere as
    # administrative/contract information (Compensation Terms.md explicitly
    # rejects making it a required runtime field here). NULL unless
    # compensation_basis == SALARIED.
    salaried_period_amount_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)

    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    source_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class PayrollRun(Base):
    """One actual administrative payroll processing event (Payroll
    Processing.md). `period_start`/`period_end` are nullable only for
    SPECIAL runs that genuinely have no Payroll Period (e.g. a one-off
    bonus/correction) — never nulled out for a REGULAR run, and never
    inferred from `pay_date` (Payroll Schedule and Period.md)."""

    __tablename__ = "payroll_runs"
    __table_args__ = (
        CheckConstraint(
            "payment_execution_provider IS NULL OR payment_execution_provider IN "
            "('ADP_DIRECT_DEPOSIT', 'MERCURY_ACH')",
            name="ck_payroll_runs_payment_execution_provider",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("restaurants.id"), nullable=False, index=True
    )
    source_system_id: Mapped[int] = mapped_column(
        ForeignKey("source_systems.id"), nullable=False, index=True
    )
    payroll_schedule_id: Mapped[int | None] = mapped_column(
        ForeignKey("payroll_schedules.id"), nullable=True
    )

    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pay_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Conceptual values: REGULAR, SPECIAL (Payroll Processing.md).
    run_type: Mapped[str] = mapped_column(String(16), nullable=False)
    provider_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Conceptual values: OPEN, COMPLETE, SUPERSEDED (a corrected provider
    # report replaced this run's authority without deleting it — Payroll
    # Provider Result.md, "Import provenance and idempotency").
    status: Mapped[str] = mapped_column(String(32), nullable=False)

    # Self-referential: populated only when an explicitly confirmed
    # corrected import supersedes this run. Never inferred automatically.
    superseded_by_payroll_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("payroll_runs.id"), nullable=True
    )

    # Explicit, auditable Payment Execution Provider (Payment Execution.md).
    # NULL = not yet assigned (never guessed for historical rows). Once set
    # to a non-null value it is never reassigned to a *different* value by
    # any RF-One code path (double-payment prevention) — see
    # `rfone_data_store/payroll/payment_execution.py`,
    # `assign_payment_execution_provider`. Conceptual values:
    # ADP_DIRECT_DEPOSIT (current production; ADP moves the funds, RF-One
    # never initiates a second payment) and MERCURY_ACH (future; not
    # implemented — no RF-One code calls a Mercury API or sends an ACH
    # instruction). Whether payment was actually *executed* is never stored
    # here — it is always derived from `PayrollPaymentFact` evidence
    # (Payment Execution.md, "Payment evidence vs. payment execution status").
    payment_execution_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    employee_results: Mapped[list["EmployeePayrollResult"]] = relationship(back_populates="payroll_run")


class PayrollExecutionConfiguration(Base):
    """Restaurant-scoped, temporally valid statement of which Payment
    Execution Provider is APPROVED for new PayrollRuns during a window
    (TASK_PAYROLL_003, `Payment Execution.md`). Distinct from
    `PayrollRun.payment_execution_provider` itself — this is the standing
    business configuration a new Run's provider may be DERIVED from when
    not explicitly selected at import/acquisition time. Mirrors the
    existing `EmployeeCompensationTerm`/`TipPolicy` temporal-configuration
    pattern: a change closes the prior row's `valid_to` and opens a new
    row — history is never overwritten in place, so a future transition
    from `ADP_DIRECT_DEPOSIT` to `MERCURY_ACH` never alters which provider
    an already-created historical PayrollRun was assigned (that assignment
    is separately immutable — see
    `rfone_data_store/payroll/payment_execution.py`,
    `assign_payment_execution_provider`)."""

    __tablename__ = "payroll_execution_configurations"
    __table_args__ = (
        CheckConstraint(
            "provider IN ('ADP_DIRECT_DEPOSIT', 'MERCURY_ACH')",
            name="ck_payroll_execution_configurations_provider",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("restaurants.id"), nullable=False, index=True
    )

    provider: Mapped[str] = mapped_column(String(32), nullable=False)

    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    source_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class PayrollProviderEmployeeIdentity(Base):
    """Explicit, provider-scoped external Employee identity mapping (Payroll
    Provider Result.md, "Employee mapping"). Never an ADP-specific column on
    `employees` — this is the smallest generic structure a provider whose
    export carries only names (no stable Employee id) requires. A row with
    `employee_id IS NULL` is UNRESOLVED/AMBIGUOUS and blocks import for that
    external key until a human explicitly resolves it — never guessed."""

    __tablename__ = "payroll_provider_employee_identities"
    __table_args__ = (
        UniqueConstraint("source_system_id", "restaurant_id", "external_employee_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_system_id: Mapped[int] = mapped_column(
        ForeignKey("source_systems.id"), nullable=False, index=True
    )
    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("restaurants.id"), nullable=False, index=True
    )

    # Deterministic, structural normalization of the provider's own Employee
    # identity evidence (e.g. a "first:last" name key) — never a fuzzy/
    # similarity-scored value. See `rfone_data_store/payroll/adp_importer.py`.
    external_employee_key: Mapped[str] = mapped_column(String(255), nullable=False)
    # Human-readable evidence of what produced the key, for audit — never a
    # full SSN/tax id (the ADP source itself never provides one; only a
    # masked last-4-digits reference, safe to retain as evidence).
    external_display_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)

    employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True, index=True
    )
    # Conceptual values: RESOLVED, UNRESOLVED, AMBIGUOUS.
    mapping_status: Mapped[str] = mapped_column(String(16), nullable=False)
    # Conceptual values: EXACT_NAME_KEY_UNIQUE_MATCH, MANUAL_REVIEW.
    resolution_method: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class EmployeePayrollResult(Base):
    """One Employee's externally processed result context for a PayrollRun
    (Payroll Provider Result.md). Prefers identifiers/references and atomic
    child facts over redundant totals — carries no stored earnings/liability/
    payment total of its own; every total is computed from its child facts
    at query time (Labor Cost.md)."""

    __tablename__ = "employee_payroll_results"
    __table_args__ = (UniqueConstraint("payroll_run_id", "employee_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payroll_run_id: Mapped[int] = mapped_column(
        ForeignKey("payroll_runs.id"), nullable=False, index=True
    )
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    # Optional provenance only — which Compensation Term this result is
    # believed to correspond to, where resolvable. Never required.
    compensation_term_id: Mapped[int | None] = mapped_column(
        ForeignKey("employee_compensation_terms.id"), nullable=True
    )

    # Raw provenance from the provider report (e.g. "Biweekly") — never used
    # to construct or infer a PayrollSchedule automatically.
    source_pay_frequency_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Conceptual values: OK, MANUAL_REVIEW_REQUIRED (Compensation Terms.md,
    # "Mid-period compensation changes").
    review_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    payroll_run: Mapped[PayrollRun] = relationship(back_populates="employee_results")
    earning_facts: Mapped[list["PayrollEarningFact"]] = relationship(
        back_populates="employee_payroll_result"
    )
    liability_facts: Mapped[list["PayrollEmployerLiabilityFact"]] = relationship(
        back_populates="employee_payroll_result"
    )
    payment_facts: Mapped[list["PayrollPaymentFact"]] = relationship(
        back_populates="employee_payroll_result"
    )


class PayrollEarningFact(Base):
    """A provider-reported earning/reporting line (Payroll Provider
    Result.md). `earning_type`/`source_label` are free strings, never a DB
    enum, so a provider label RF-One has never seen before (REGULAR,
    OVERTIME, SALARY, BONUS, CASH_TIPS, PTO, or anything future) is stored
    without a schema change. `quantity`/`unit`/`rate_minor` are independently
    nullable — not every payable item is measured in hours (Payroll
    Processing.md, "Worked Time vs. paid non-work time")."""

    __tablename__ = "payroll_earning_facts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_payroll_result_id: Mapped[int] = mapped_column(
        ForeignKey("employee_payroll_results.id"), nullable=False, index=True
    )

    # Normalized classification derived from the provider's own label (e.g.
    # "Regular " -> REGULAR, "Cash tips* " -> CASH_TIPS) — never a hardcoded
    # whitelist rejection of an unrecognized label; an unseen label is
    # normalized generically instead of blocking import (task §26).
    earning_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # The provider's own text, verbatim, for audit.
    source_label: Mapped[str] = mapped_column(String(255), nullable=False)

    quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    rate_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)

    # Parsed from the provider's own "* Items Not Paid To Employee"
    # convention (Payroll Provider Result.md) — false means this line was
    # reported/taxed but not disbursed to the Employee through payroll, and
    # it must never be summed into Payroll Employer Cost's earnings
    # component (Labor Cost.md).
    paid_to_employee: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # Parsed from the provider's "** ... Excluded From Some Wages" footnote,
    # where present — independent from `paid_to_employee` (a line can be
    # unpaid to the Employee yet still count toward some tax wage base).
    excluded_from_taxable_wages: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # Which "Earning N" column group on the source row this came from —
    # provenance/ordering only, never business meaning.
    sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    employee_payroll_result: Mapped[EmployeePayrollResult] = relationship(
        back_populates="earning_facts"
    )


class PayrollEmployerLiabilityFact(Base):
    """A provider-reported employer-side liability/cost line (Payroll
    Provider Result.md) — e.g. employer Social Security, employer Medicare.
    Employee tax withholding is never modeled here or anywhere in this
    schema (Labor Cost.md) — it is not employer labor cost."""

    __tablename__ = "payroll_employer_liability_facts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_payroll_result_id: Mapped[int] = mapped_column(
        ForeignKey("employee_payroll_results.id"), nullable=False, index=True
    )

    liability_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_label: Mapped[str] = mapped_column(String(255), nullable=False)
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    employee_payroll_result: Mapped[EmployeePayrollResult] = relationship(
        back_populates="liability_facts"
    )


class PayrollPaymentFact(Base):
    """A provider-reported employee payment fact (Payroll Provider
    Result.md) — what lets RF-One reconstruct actual employee-level payment
    independent of an aggregate bank debit ("Actual payment
    reconstruction")."""

    __tablename__ = "payroll_payment_facts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_payroll_result_id: Mapped[int] = mapped_column(
        ForeignKey("employee_payroll_results.id"), nullable=False, index=True
    )

    pay_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payment_method: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payment_amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    # Already masked/redacted by the provider itself (e.g. "Account No:
    # XXXXXX8058") — never a full account number, never enriched beyond what
    # the provider itself already redacted.
    provider_payment_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    employee_payroll_result: Mapped[EmployeePayrollResult] = relationship(
        back_populates="payment_facts"
    )


class PayrollImportRun(Base):
    """One execution of the ADP Payroll Details Excel importer (Payroll
    Provider Result.md, "Import provenance and idempotency") — auditability
    and idempotency by file hash, mirroring `TipCalculationRun`'s dry-run/
    persist pattern."""

    __tablename__ = "payroll_import_runs"
    __table_args__ = (
        UniqueConstraint("source_system_id", "restaurant_id", "source_file_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("restaurants.id"), nullable=False, index=True
    )
    source_system_id: Mapped[int] = mapped_column(
        ForeignKey("source_systems.id"), nullable=False, index=True
    )
    payroll_run_id: Mapped[int | None] = mapped_column(ForeignKey("payroll_runs.id"), nullable=True)

    # File name only (never a full local filesystem path, which could leak
    # local directory structure) plus its content hash for idempotency. For
    # a non-file acquisition (e.g. SFTP, a future API), this holds a
    # descriptive source identifier (e.g. the remote filename) — the content
    # hash still governs idempotency, never the identifier string.
    source_file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_file_hash: Mapped[str] = mapped_column(String(128), nullable=False)

    # How this import's bytes actually reached RF-One (TASK_PAYROLL_003,
    # Payroll Result Acquisition.md) — free string, matching this schema's
    # existing convention for evolving classification fields (e.g.
    # `EmployeeAssignment.assignment_source`). Conceptual values today:
    # ADP_XLSX_FILE (manual/local file — the existing, fully supported
    # fallback path), ADP_SFTP_AES (ADP's Automatic Export Service delivering
    # a report to a customer-controlled SFTP endpoint). Nullable only because
    # historical rows created before this column existed never had a value
    # to record — never guessed for those.
    acquisition_method: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Explicitly confirmed correction chain — never inferred automatically
    # (Payroll Provider Result.md). NULL unless the operator passed
    # `--supersedes-run` confirming this import corrects a specific prior one.
    supersedes_import_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("payroll_import_runs.id"), nullable=True
    )

    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # Conceptual values: DRY_RUN, PERSIST.
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    # Conceptual values: COMPLETE, PARTIAL, FAILED.
    status: Mapped[str] = mapped_column(String(32), nullable=False)

    employees_represented_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unresolved_employee_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    issues: Mapped[list["PayrollImportIssue"]] = relationship(back_populates="import_run")


class PayrollImportIssue(Base):
    """A blocking or warning condition raised while importing a Payroll
    provider result (Payroll Provider Result.md, "Employee mapping") — the
    importer's explicit alternative to guessing, mirroring
    `TipCalculationIssue`'s pattern."""

    __tablename__ = "payroll_import_issues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    import_run_id: Mapped[int] = mapped_column(
        ForeignKey("payroll_import_runs.id"), nullable=False, index=True
    )

    # Conceptual values: UNRESOLVED_EMPLOYEE_MAPPING,
    # AMBIGUOUS_EMPLOYEE_MAPPING, UNPARSED_SOURCE_ROW,
    # MID_PERIOD_COMPENSATION_CONFLICT. Free string — only the subset
    # actually produced by real importer logic is ever written.
    issue_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    # Never includes a full SSN/tax id/bank reference — only RF-One-internal
    # identifiers and the already-masked provider evidence.
    details: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    import_run: Mapped[PayrollImportRun] = relationship(back_populates="issues")


# ---------------------------------------------------------------------------
# Compensation Preparation (formerly "Payroll Calculation Engine") — RF-One's
# internal EXPECTED payroll (Product Owner decision, corrected Option C;
# `PayrollCalculationRun` renamed to `CompensationPreparationRun` by a later
# Product Owner decision — RF-One does not perform Payroll).
#
# Distinct from the Administration/Payroll domain/schema above, which
# continues to mean exactly what it always meant: what the external payroll
# provider (ADP) actually processed (`payroll_runs`, `employee_payroll_results`,
# and their fact tables). Nothing in that section is redefined, renamed, or
# reused for a different meaning here.
#
# Conceptual relationship:
#
#   RF-One Expected Compensation (this section)
#   -> External Payroll Provider / ADP
#   -> Payroll Actual Result (`payroll_runs` / `employee_payroll_results`)
#   -> Variance / reconciliation (not implemented yet)
#
# Reuses the existing canonical `Employee` identity and the existing
# `EmployeeCompensationTerm` effective-dated compensation records — no second
# Employee or compensation master is created. Bonus is out of scope here: no
# bonus formula is computed by this engine, matching the same "externally
# supplied amount" boundary the Administration/Payroll domain already applies
# (`Payroll Processing.md`, "Bonus boundary") — `bonus_amount` is always an
# input fact, acceptable as zero for this MVP.
# ---------------------------------------------------------------------------


class CompensationPreparationRun(Base):
    """One RF-One internal compensation-preparation cycle — the period over
    which `EmployeePayrollCalculation` rows are produced. Formerly named
    `PayrollCalculationRun`; renamed by explicit Product Owner decision
    (nomenclature/ownership resolution only — no lifecycle/behavior change):
    RF-One does not perform Payroll, so this internal preparation cycle must
    not carry "Payroll" in its name. Named distinctly from the
    Administration/Payroll domain's own Payroll Period/`PayrollRun.period_start`/
    `period_end` concept (`Payroll Schedule and Period.md`) to avoid
    colliding with it: this run represents RF-One's own expected Compensation
    preparation, never the actual provider-processed payroll. Physical table
    name (`payroll_calculation_runs`) is intentionally left unchanged — see
    the Data Store's DB-naming caution; this rename is Python/domain-side
    only.

    `legal_entity_id` is the Legal Entity dimension required by the
    Compensation & Income Composition functional specification (`01 Domains/
    Shared Domains/Personnel Management/Compensation/
    COMPENSATION_AND_INCOME_COMPOSITION_001.md` §3). Product Owner
    correction: an earlier version of this column was named `restaurant_id`
    and pointed at `restaurants.id` — read-only verification then confirmed
    `Restaurant` is formally an Operational Unit, never the Legal Entity
    (`01 Domains/Business Domain/Restaurant/Model/OU-Restaurant.md`,
    "Extends: Operational Unit"), so a `Restaurant`-owning `LegalEntity`
    could legitimately span several Restaurants — scoping by `restaurant_id`
    would have incorrectly split one Legal Entity's compensation across its
    Restaurants. `legal_entity_id` now points at the canonical `LegalEntity`
    model instead. Required (never nullable) — every preparation run belongs
    to exactly one Legal Entity, and results for different Legal Entities
    are never combined into one run."""

    __tablename__ = "payroll_calculation_runs"
    __table_args__ = (
        CheckConstraint("period_end >= period_start", name="ck_payroll_calculation_runs_period"),
        # Conceptual values: OPEN (created, not yet calculated), CALCULATED
        # (employee results have been produced for this run — the software
        # state equivalent to the functional spec's "PREPARED"; not renamed,
        # per Product Owner decision, Compensation V1 Task 1 — this is
        # documented terminology, not behavior, debt), APPROVED (Compensation
        # V1 Task 1 — an authorized actor approved this run and an
        # `ApprovedCompensationSnapshot` now exists for it; see
        # `rfone_data_store/payroll_calculation/approval.py`). EXPORTED/CLOSED
        # (functional spec §19) are not implemented yet — deliberately out of
        # scope for this task.
        CheckConstraint(
            "status IN ('OPEN', 'CALCULATED', 'APPROVED')", name="ck_payroll_calculation_runs_status"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    legal_entity_id: Mapped[int] = mapped_column(
        ForeignKey("legal_entities.id"), nullable=False, index=True
    )

    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    employee_calculations: Mapped[list["EmployeePayrollCalculation"]] = relationship(
        back_populates="calculation_run"
    )


class EmployeePayrollCalculation(Base):
    """One Employee's RF-One-calculated EXPECTED payroll SUMMARY for a
    `CompensationPreparationRun` — the aggregate of that employee's
    `EmployeePayrollCalculationEarningLine` rows (Product Owner correction:
    an Employee may legitimately work at more than one hourly rate within
    the same calculation run, e.g. Server hours and Manager hours, so no
    single `hourly_rate_used`/rate-bearing field lives on this summary
    anymore — only the aggregated totals). Later changes to compensation or
    bonus rules never alter an already-persisted row here (Product Owner
    decision, rule 9).

    Named distinctly from the Administration/Payroll domain's `EmployeePayrollResult`
    (provider-reported facts, no stored total) — this table is the opposite:
    an RF-One-computed total, not an externally reported one. The two must
    never be merged or treated as interchangeable.

    `tips_amount` and `bonus_amount` are input facts to this engine, not
    computed here, and are never split into earning lines — Tips
    calculation logic and Bonus formulas both remain entirely outside this
    table (Product Owner decision, rules 3 and 8).

    `incentive_recognized_amount` (Compensation V1 manual handoff) is
    MAX(0, SUM(`IncentiveContribution.amount`)) for this Employee/run —
    computed by `rfone_data_store.payroll_calculation.incentives.
    calculate_recognized_incentive` from the persisted positive/negative
    Contributions, never a separate "Disincentive" value (functional spec
    §14). `tip_credit_makeup_amount` stays NULL until a value is explicitly
    supplied — NULL means "to be completed by the Payroll Provider", never a
    false zero (functional spec §22, Payroll Provider boundary). Neither
    field is included in `gross_pay` automatically beyond
    `incentive_recognized_amount` (see below) — Tip Credit Make-Up is
    preserved for handoff, never composed into an RF-One-computed total.

    Legal Entity is never duplicated here — it is inherited through
    `calculation_run_id` -> `CompensationPreparationRun.legal_entity_id`. The
    `uq_employee_payroll_calculation` constraint below is therefore already
    Legal-Entity-scoped: one employee has only one summary per calculation
    run, and a run belongs to exactly one Legal Entity."""

    __tablename__ = "employee_payroll_calculations"
    __table_args__ = (
        UniqueConstraint(
            "calculation_run_id", "employee_id", name="uq_employee_payroll_calculation"
        ),
        CheckConstraint("regular_hours >= 0", name="ck_employee_payroll_calc_regular_hours"),
        CheckConstraint("regular_pay >= 0", name="ck_employee_payroll_calc_regular_pay"),
        CheckConstraint("tips_amount >= 0", name="ck_employee_payroll_calc_tips_amount"),
        CheckConstraint("bonus_amount >= 0", name="ck_employee_payroll_calc_bonus_amount"),
        CheckConstraint(
            "incentive_recognized_amount >= 0",
            name="ck_employee_payroll_calc_incentive_recognized_amount",
        ),
        CheckConstraint(
            "tip_credit_makeup_amount IS NULL OR tip_credit_makeup_amount >= 0",
            name="ck_employee_payroll_calc_tip_credit_makeup_amount",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    calculation_run_id: Mapped[int] = mapped_column(
        ForeignKey("payroll_calculation_runs.id"), nullable=False, index=True
    )
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)

    # SUM(earning_lines.regular_hours) / SUM(earning_lines.regular_pay) —
    # hours follow this schema's existing fractional-quantity convention
    # (`Numeric(12, 4)` — see module docstring, "Quantity").
    regular_hours: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    regular_pay: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    tips_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    bonus_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    incentive_recognized_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    tip_credit_makeup_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    gross_pay: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    calculation_run: Mapped[CompensationPreparationRun] = relationship(
        back_populates="employee_calculations"
    )
    employee: Mapped["Employee"] = relationship()
    earning_lines: Mapped[list["EmployeePayrollCalculationEarningLine"]] = relationship(
        back_populates="employee_calculation"
    )


class EmployeePayrollCalculationEarningLine(Base):
    """One homogeneous block of hours paid at one specific hourly rate,
    within one `EmployeePayrollCalculation` summary (Product Owner
    correction — an Employee may work, e.g., 20 Server hours at $12/hour and
    15 Manager hours at $22/hour within the same calculation run; each
    combination is its own line, never averaged/blended into the summary).

    `compensation_term_id` records exactly which `EmployeeCompensationTerm`
    produced `hourly_rate_used` — a historical calculation snapshot: if that
    term later changes (or is superseded by a new temporal row, per the
    existing compensation-history convention), this line's own
    `hourly_rate_used`/`regular_pay` never change (Product Owner decision,
    rule 5)."""

    __tablename__ = "employee_payroll_calculation_earning_lines"
    __table_args__ = (
        CheckConstraint("regular_hours >= 0", name="ck_employee_payroll_calc_line_regular_hours"),
        CheckConstraint("hourly_rate_used >= 0", name="ck_employee_payroll_calc_line_hourly_rate"),
        CheckConstraint("regular_pay >= 0", name="ck_employee_payroll_calc_line_regular_pay"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_payroll_calculation_id: Mapped[int] = mapped_column(
        ForeignKey("employee_payroll_calculations.id"), nullable=False, index=True
    )
    # Nullable for now (Product Owner decision, rule 2) — this MVP's input
    # may be period-level (no day-by-day breakdown) rather than day-level; a
    # future caller that does have day-level worked-time facts can populate
    # it without a schema change.
    work_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    compensation_term_id: Mapped[int] = mapped_column(
        ForeignKey("employee_compensation_terms.id"), nullable=False, index=True
    )

    regular_hours: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    # Snapshot of the selected EmployeeCompensationTerm's
    # `hourly_rate_minor`, converted to decimal currency, at calculation
    # time — never re-derived later from a possibly-changed term.
    hourly_rate_used: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    regular_pay: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    employee_calculation: Mapped[EmployeePayrollCalculation] = relationship(
        back_populates="earning_lines"
    )
    compensation_term: Mapped["EmployeeCompensationTerm"] = relationship()


class IncentiveContribution(Base):
    """One positive or negative Incentive Contribution entered for an
    Employee within a `CompensationPreparationRun` (functional spec §14 —
    "an Incentive is variable compensation produced by one or more
    measurable positive or negative contributions"). Compensation V1 has no
    Event Log / Incentive Rule engine (spec §10-13 remain conceptual/
    documented only) — a human enters each Contribution directly, exactly as
    the manual Payroll Provider communication this task completes requires.

    `amount` may be negative. The Recognized Incentive is always
    `MAX(0, SUM(amount))` for one Employee/run — computed by
    `rfone_data_store.payroll_calculation.incentives.
    calculate_recognized_incentive`, never stored as a separate
    "Disincentive" concept (spec §14: "There is no separate economic concept
    called Disincentive"). A negative Contribution here can only ever reduce
    the Incentive being evaluated — nothing in this schema or in
    `payroll_calculation.engine` ever lets it reduce `regular_pay`,
    `tips_amount`, or any other owed compensation.

    Legal Entity is never duplicated here — it is inherited through
    `calculation_run_id` -> `CompensationPreparationRun.legal_entity_id`, the
    same convention `EmployeePayrollCalculation` already uses. Editable only
    while the run is `OPEN`/`CALCULATED` — once a run is `APPROVED`, its
    Incentive detail is immutable (see `ApprovedIncentiveContributionLine`,
    copied once at approval time by `payroll_calculation.approval`)."""

    __tablename__ = "incentive_contributions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    calculation_run_id: Mapped[int] = mapped_column(
        ForeignKey("payroll_calculation_runs.id"), nullable=False, index=True
    )
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)

    label: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    source_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    calculation_run: Mapped[CompensationPreparationRun] = relationship()
    employee: Mapped["Employee"] = relationship()


# ---------------------------------------------------------------------------
# Approved Compensation Snapshot foundation (Compensation V1 Task 1, Product
# Owner decision; extended by the Compensation V1 manual Payroll Handoff
# task with Recognized Incentive/Tip Credit Make-Up detail, export
# confirmation and reconciliation — see below). Immutable-by-convention,
# mirroring this schema's existing "no update path exposed" pattern (e.g.
# Purchasing's `repository.py`): no service function anywhere updates or
# deletes a row in these tables once created — see
# `rfone_data_store/payroll_calculation/approval.py`, the ONLY code that
# ever writes them. RF-One does not process Payroll — the snapshot preserves
# what RF-One approved for later handoff to the Payroll Provider (`01
# Domains/Shared Domains/Personnel Management/Compensation/
# COMPENSATION_AND_INCOME_COMPOSITION_001.md` §19-20); it never contains a
# calculated statutory Regular Rate, Overtime premium, tax, withholding,
# deduction, employer liability, or net pay — those belong to the Payroll
# Provider. Authorized Adjustments remain out of scope (conceptual/
# documented only) — this task did not extend the snapshot for them.
# ---------------------------------------------------------------------------


class ApprovedCompensationSnapshot(Base):
    """The immutable header of one APPROVED `CompensationPreparationRun` —
    created exactly once per run (Product Owner decision: "one canonical
    Approved Compensation Snapshot per approved Compensation Preparation").
    `legal_entity_id`/`period_start`/`period_end` are copied from the run at
    approval time rather than joined at read time — the snapshot must remain
    reconstructable even if a future change ever touched the source run row.

    Never updated or deleted by any code once created — a later recalculation
    of the source `CompensationPreparationRun`/`EmployeeCompensationTerm`/
    worked-time inputs/Tips source data never alters an already-created
    snapshot (functional spec §20, "Later rule changes must never alter the
    snapshot")."""

    __tablename__ = "approved_compensation_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "compensation_preparation_run_id", name="uq_approved_compensation_snapshot_run"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    compensation_preparation_run_id: Mapped[int] = mapped_column(
        ForeignKey("payroll_calculation_runs.id"), nullable=False, index=True
    )
    legal_entity_id: Mapped[int] = mapped_column(ForeignKey("legal_entities.id"), nullable=False)

    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # The authorized actor/reference supplied to the approval operation
    # (Product Owner decision: no Identity & Access authorization rules are
    # built by this task — the approval service receives this as a plain
    # input, never resolves or validates it against an identity table).
    approved_by: Mapped[str] = mapped_column(String(255), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    compensation_preparation_run: Mapped[CompensationPreparationRun] = relationship()
    employee_results: Mapped[list["ApprovedEmployeeCompensationResult"]] = relationship(
        back_populates="snapshot"
    )


class ApprovedEmployeeCompensationResult(Base):
    """One Employee's immutable, approved compensation totals within an
    `ApprovedCompensationSnapshot` — a VALUE copy of the corresponding
    `EmployeePayrollCalculation` row at approval time, not a pointer to it.
    `source_employee_calculation_id` is kept only for audit traceability
    ("which source row was this copied from") — the snapshot's own columns,
    never that source row, are the values later handoff/consumption must
    read; the source row remains free to be recalculated/changed afterward
    without affecting this one."""

    __tablename__ = "approved_employee_compensation_results"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_id", "employee_id", name="uq_approved_employee_compensation_result"
        ),
        CheckConstraint(
            "regular_hours >= 0", name="ck_approved_employee_compensation_result_regular_hours"
        ),
        CheckConstraint(
            "regular_pay >= 0", name="ck_approved_employee_compensation_result_regular_pay"
        ),
        CheckConstraint(
            "tips_amount >= 0", name="ck_approved_employee_compensation_result_tips_amount"
        ),
        CheckConstraint(
            "bonus_amount >= 0", name="ck_approved_employee_compensation_result_bonus_amount"
        ),
        # Note: prefixed "ck_approved_emp_comp_result_..." rather than the
        # fuller "ck_approved_employee_compensation_result_..." used above —
        # PostgreSQL truncates/rejects identifiers over 63 bytes
        # (NAMEDATALEN), and the fuller prefix combined with either suffix
        # below exceeds that (verified against real RDS PostgreSQL).
        CheckConstraint(
            "incentive_recognized_amount >= 0",
            name="ck_approved_emp_comp_result_incentive_recognized_amt",
        ),
        CheckConstraint(
            "tip_credit_makeup_amount IS NULL OR tip_credit_makeup_amount >= 0",
            name="ck_approved_emp_comp_result_tip_credit_makeup_amt",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("approved_compensation_snapshots.id"), nullable=False, index=True
    )
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    source_employee_calculation_id: Mapped[int | None] = mapped_column(
        ForeignKey("employee_payroll_calculations.id"), nullable=True
    )

    regular_hours: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    regular_pay: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    tips_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    bonus_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    # Value-copied at approval time from `EmployeePayrollCalculation`, same
    # as every other column here — see that model's own docstring for what
    # each means (Compensation V1 manual Payroll Handoff task).
    incentive_recognized_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    tip_credit_makeup_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    gross_pay: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    snapshot: Mapped[ApprovedCompensationSnapshot] = relationship(back_populates="employee_results")
    employee: Mapped["Employee"] = relationship()
    earning_lines: Mapped[list["ApprovedEmployeeEarningLine"]] = relationship(
        back_populates="employee_result"
    )
    incentive_contribution_lines: Mapped[list["ApprovedIncentiveContributionLine"]] = relationship(
        back_populates="employee_result"
    )


class ApprovedEmployeeEarningLine(Base):
    """One immutable, approved earning-line fact within an
    `ApprovedEmployeeCompensationResult` — a VALUE copy of the corresponding
    `EmployeePayrollCalculationEarningLine` at approval time.
    `compensation_term_id` is preserved as a reference (which
    `EmployeeCompensationTerm` produced the rate), matching the source
    line's own convention — but the snapshot's own `hourly_rate_used`/
    `regular_pay` are what must be trusted going forward, never a re-join
    through that reference, since the term itself may later change."""

    __tablename__ = "approved_employee_earning_lines"
    __table_args__ = (
        CheckConstraint("hours >= 0", name="ck_approved_employee_earning_line_hours"),
        CheckConstraint(
            "hourly_rate_used >= 0", name="ck_approved_employee_earning_line_hourly_rate"
        ),
        CheckConstraint("regular_pay >= 0", name="ck_approved_employee_earning_line_regular_pay"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    approved_employee_result_id: Mapped[int] = mapped_column(
        ForeignKey("approved_employee_compensation_results.id"), nullable=False, index=True
    )
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    source_earning_line_id: Mapped[int | None] = mapped_column(
        ForeignKey("employee_payroll_calculation_earning_lines.id"), nullable=True
    )

    work_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    compensation_term_id: Mapped[int] = mapped_column(
        ForeignKey("employee_compensation_terms.id"), nullable=False, index=True
    )

    hours: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    hourly_rate_used: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    regular_pay: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    employee_result: Mapped[ApprovedEmployeeCompensationResult] = relationship(
        back_populates="earning_lines"
    )


class ApprovedIncentiveContributionLine(Base):
    """One immutable, approved Incentive Contribution detail line within an
    `ApprovedEmployeeCompensationResult` — a VALUE copy of the corresponding
    `IncentiveContribution` at approval time (mirrors
    `ApprovedEmployeeEarningLine`'s existing convention). Preserving
    positive AND negative Contribution detail, never only the Recognized
    Incentive total, is required by functional spec §20 ("Incentive detail
    (positive/negative Contributions and the Recognized Incentive)")."""

    __tablename__ = "approved_incentive_contribution_lines"
    __table_args__ = (
        # Explicit short index name — the table+column-derived default
        # ("ix_approved_incentive_contribution_lines_approved_employee_result_id")
        # exceeds PostgreSQL's 63-byte identifier limit (verified against
        # real RDS PostgreSQL).
        Index("ix_approved_incentive_lines_result_id", "approved_employee_result_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    approved_employee_result_id: Mapped[int] = mapped_column(
        ForeignKey("approved_employee_compensation_results.id"), nullable=False
    )
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    source_contribution_id: Mapped[int | None] = mapped_column(
        ForeignKey("incentive_contributions.id"), nullable=True
    )

    label: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    employee_result: Mapped[ApprovedEmployeeCompensationResult] = relationship(
        back_populates="incentive_contribution_lines"
    )


# ---------------------------------------------------------------------------
# Compensation V1 manual Payroll Handoff Connector (`01 Domains/Cross
# Domain/Personnel Management/Compensation/PAYROLL_HANDOFF_CONNECTOR.md`):
# a human operator communicates one `ApprovedCompensationSnapshot`'s data to
# the Payroll Provider and records that this happened
# (`CompensationExportConfirmation`) — never itself evidence that payroll
# was processed or paid. `CompensationReconciliation`/
# `CompensationReconciliationLine` compare that Snapshot against the
# Provider's actual result, once manually recorded into the EXISTING
# Administration/Payroll return model (`PayrollRun`/`EmployeePayrollResult`/
# `PayrollEarningFact` — see `rfone_data_store/payroll_calculation/
# reconciliation.py`), restricted to semantically comparable components —
# never Provider net pay against a Compensation total (Compensation
# README.md, "Provider Reconciliation"; `Administration/Payroll/Payment
# Execution.md`).
# ---------------------------------------------------------------------------


class CompensationExportConfirmation(Base):
    """One human confirmation that an `ApprovedCompensationSnapshot`'s data
    was actually communicated to the Payroll Provider (manual Payroll
    Handoff Connector — `PAYROLL_HANDOFF_CONNECTOR.md`, "A human operator
    entering RF-One's approved values into ADP or another Payroll Provider
    is a valid Connector implementation"). Recording this confirmation is
    never itself evidence that payroll was processed or paid — see
    `PayrollRun`/`PayrollEarningFact` (Administration/Payroll) for what the
    Provider actually returned, and `CompensationReconciliation` for
    comparing the two. More than one confirmation may exist for the same
    snapshot (e.g. a re-communication after a correction) — never
    overwritten, always appended."""

    __tablename__ = "compensation_export_confirmations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("approved_compensation_snapshots.id"), nullable=False, index=True
    )

    communicated_by: Mapped[str] = mapped_column(String(255), nullable=False)
    communicated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    snapshot: Mapped[ApprovedCompensationSnapshot] = relationship()


class CompensationReconciliation(Base):
    """One comparison pass between an `ApprovedCompensationSnapshot` (what
    RF-One approved) and a `PayrollRun` (what the Payroll Provider actually
    processed, manually recorded — see
    `rfone_data_store.payroll_calculation.reconciliation.
    record_manual_provider_result`). Never compares Provider net pay to a
    Compensation total — only semantically matching components (Regular Pay
    to Regular Pay, Tips to Tips, Recognized Incentive to a Provider-
    reported bonus/incentive line — see `CompensationReconciliationLine`).
    Neither the Snapshot nor the PayrollRun is ever modified by creating a
    reconciliation — differences are recorded as
    `CompensationReconciliationLine` rows, never merged back into either
    source. Idempotent per (snapshot, run) pair (`uq_compensation_reconciliation`)
    — re-reconciling the same pair returns the existing pass rather than
    creating a duplicate one with possibly-reopened lines."""

    __tablename__ = "compensation_reconciliations"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "payroll_run_id", name="uq_compensation_reconciliation"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("approved_compensation_snapshots.id"), nullable=False, index=True
    )
    payroll_run_id: Mapped[int] = mapped_column(ForeignKey("payroll_runs.id"), nullable=False, index=True)

    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    snapshot: Mapped[ApprovedCompensationSnapshot] = relationship()
    payroll_run: Mapped["PayrollRun"] = relationship()
    lines: Mapped[list["CompensationReconciliationLine"]] = relationship(back_populates="reconciliation")


class CompensationReconciliationLine(Base):
    """One semantically-comparable component's comparison result for one
    Employee within a `CompensationReconciliation`. `rfone_value`/
    `provider_value` are independently nullable — a component present only
    on one side is a MISSING_IN_PROVIDER/MISSING_IN_RFONE line, never a
    fabricated zero on the missing side (MISSING_IN_RFONE also covers a
    Provider-reported component RF-One has no matching component for at
    all — "voci aggiunte... dal provider"). `status` is derived once, at
    creation time, from comparing the two values — never recomputed
    automatically afterward, so an explained/accepted difference is never
    silently reopened by re-running reconciliation; a new reconciliation
    pass against a different Provider result creates a new
    `CompensationReconciliation` (and new lines) instead."""

    __tablename__ = "compensation_reconciliation_lines"
    __table_args__ = (
        CheckConstraint(
            "status IN ('MATCH','DIFFERENT','MISSING_IN_PROVIDER','MISSING_IN_RFONE')",
            name="ck_compensation_reconciliation_line_status",
        ),
        CheckConstraint(
            "resolution_status IN ('OPEN','EXPLAINED','ACCEPTED')",
            name="ck_compensation_reconciliation_line_resolution_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reconciliation_id: Mapped[int] = mapped_column(
        ForeignKey("compensation_reconciliations.id"), nullable=False, index=True
    )
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)

    component_label: Mapped[str] = mapped_column(String(64), nullable=False)
    rfone_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    provider_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)

    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_status: Mapped[str] = mapped_column(String(16), nullable=False, default="OPEN")
    resolved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    reconciliation: Mapped[CompensationReconciliation] = relationship(back_populates="lines")
    employee: Mapped["Employee"] = relationship()


# ---------------------------------------------------------------------------
# Overtime Rule Matrix foundation (Product Owner decision) — schema +
# metadata only. NO overtime is calculated anywhere in this schema or by
# any code in this repository; see `OvertimeRule`'s own docstring below and
# `01 Domains/Shared Domains/Personnel Management/Compensation/
# OVERTIME_RULE_MATRIX_001.md` for the full functional boundary.
# ---------------------------------------------------------------------------


class OvertimeRule(Base):
    """One canonical, effective-dated legal/statutory overtime rule fact —
    WHAT the rule is, never a calculation. RF-One does not calculate
    statutory Overtime compensation: the Payroll Provider determines which
    rule(s) apply to actual worked time, which hours trigger them, the
    applicable regular rate, and the incremental premium owed. This table
    stores none of that — it stores only the legal rule metadata RF-One
    preserves and supplies (with the required worked-time/compensation
    context) so the Payroll Provider can apply it.

    Deliberately NOT attached to `LegalEntity` — the applicable overtime
    law depends on the jurisdiction where work is performed, not on
    employer identity, so `LegalEntity` and `OvertimeRule` jurisdiction
    remain separate dimensions. A future Worked Time fact may supply the
    jurisdiction/location needed to select applicable rules; that linkage
    is not implemented here.

    `total_rate_multiplier` is the TOTAL statutory pay-rate multiplier
    (e.g. `1.5`, `2.0`) — never an incremental "premium owed on top of
    straight time already paid" figure. The Payroll Provider may derive an
    incremental premium (e.g. `0.5 x regular_rate` when straight time is
    already included in regular earnings and the total multiplier is
    `1.5`); that derivation is not performed or stored here, and RF-One
    does not perform it.

    `regular_rate_method` and `overlap_method` name legal METHODS the
    Payroll Provider applies — no regular rate is calculated and no overlap
    is resolved by this table or by any code in this repository.

    Historical rule versions are represented as distinct rows with distinct
    `rule_code`s (e.g. a version/year suffix) rather than a separate
    version column — the smallest design able to preserve legal history
    without overwriting an old rule when law changes, mirroring this
    schema's existing temporal-configuration pattern (`EmployeeCompensationTerm`,
    `TipDistributionRuleVersion`): a change never overwrites a prior rule
    in place, it closes the prior row's `effective_to` and adds a new row
    under its own `rule_code`.

    IMPORTANT — Worked Time dependency: `WORKDAY`, `CONSECUTIVE_HOURS` and
    `CONSECUTIVE_DAY` rule scopes cannot be evaluated reliably from
    aggregate payroll-period hours alone (`EmployeePayrollCalculationEarningLine`
    is not modified by this task to solve this). `CONSECUTIVE_HOURS` in
    particular may require actual time boundaries (clock-in/clock-out
    instants), not merely a `work_date`. Worked Time ownership remains
    entirely outside Payroll Calculation; Payroll Calculation only ever
    consumes already-validated Worked Time facts, and RF-One only ever
    supplies them onward to the Payroll Provider for statutory evaluation.

    IMPORTANT — regular-rate numerator boundary: the Payroll Provider must
    distinguish which compensation components belong in the statutory
    regular-rate numerator (e.g. hourly straight-time earnings, shift
    differentials, nondiscretionary incentives/bonuses, discretionary
    bonuses, commissions, customer tips, service charges, other statutory
    inclusions/exclusions). No such classification is implemented here, and
    neither Tips nor Incentive structures are changed by this task."""

    __tablename__ = "overtime_rules"
    __table_args__ = (
        UniqueConstraint("rule_code"),
        CheckConstraint(
            "jurisdiction_level IN ('FEDERAL', 'STATE', 'LOCAL')",
            name="ck_overtime_rules_jurisdiction_level",
        ),
        CheckConstraint(
            "rule_scope IN ('WORKWEEK', 'WORKDAY', 'CONSECUTIVE_HOURS', 'CONSECUTIVE_DAY')",
            name="ck_overtime_rules_rule_scope",
        ),
        CheckConstraint(
            "regular_rate_method IN ('WEIGHTED_REGULAR_RATE', 'RATE_IN_EFFECT', 'NOT_APPLICABLE')",
            name="ck_overtime_rules_regular_rate_method",
        ),
        CheckConstraint(
            "overlap_method IN ('NON_STACKING_MAXIMUM', 'STACKING', 'INDEPENDENT')",
            name="ck_overtime_rules_overlap_method",
        ),
        CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name="ck_overtime_rules_status"),
        CheckConstraint(
            "threshold_hours IS NULL OR threshold_hours >= 0", name="ck_overtime_rules_threshold_hours"
        ),
        CheckConstraint(
            "threshold_day_number IS NULL OR threshold_day_number > 0",
            name="ck_overtime_rules_threshold_day_number",
        ),
        CheckConstraint("total_rate_multiplier >= 1", name="ck_overtime_rules_total_rate_multiplier"),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_overtime_rules_effective_range",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    rule_code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    jurisdiction_level: Mapped[str] = mapped_column(String(16), nullable=False)
    # Compact canonical string (e.g. "US", "CA", "FL") — never a full
    # Jurisdiction table; no state/local rule set is exhaustively populated
    # by this task.
    jurisdiction_code: Mapped[str] = mapped_column(String(16), nullable=False)

    rule_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    # Hours follow this schema's existing fractional-quantity convention
    # (`Numeric(12, 4)` — see module docstring, "Quantity").
    threshold_hours: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    threshold_day_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_rate_multiplier: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    regular_rate_method: Mapped[str] = mapped_column(String(32), nullable=False)
    overlap_method: Mapped[str] = mapped_column(String(32), nullable=False)

    # Future filtering metadata only — no exemption engine, no employee
    # classification taxonomy, no industry/occupation taxonomy is built by
    # this task. Free strings, matching this schema's existing convention
    # for evolving classification fields not yet backed by a canonical list.
    employee_classification: Mapped[str | None] = mapped_column(String(64), nullable=True)
    industry_code: Mapped[str | None] = mapped_column(String(32), nullable=True)

    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


# ---------------------------------------------------------------------------
# Purchasing — Restaurant Domain, Purchasing module (TASK_PURCHASING_004)
#
# Implements the canonical model already approved, documentation-only, by
# TASK_PURCHASING_001-003 (`01 Domains/Business Domain/Restaurant/Purchasing/`). This section
# adds the first persistent schema for it; it does not redefine any Domain
# concept. Money follows this schema's existing minor-units convention;
# quantity follows the existing `Numeric(12, 4)` convention (see "Numeric
# conventions" in README.md). Status/decision/trigger fields that the Domain
# documents as a small closed vocabulary (e.g. Purchase Line `line_type`,
# Alert `trigger`) get a `CheckConstraint` — the same structural-enforcement
# choice TASK_PAYROLL_001 made for `employee_compensation_terms` — while
# fields the Domain leaves open-ended (e.g. `status` on Supplier/Purchase
# Order) stay free strings, matching every other evolving classification
# field in this schema (e.g. `EmployeeAssignment.assignment_source`).
#
# Historical integrity (Purchasing/DataDictionary.md, "Persist Facts —
# Derive Calculations"; Purchasing/BusinessRules.md, Rules 2, 11, 23, 36) is
# enforced at the repository layer (`rfone_data_store/purchasing/
# repository.py` exposes no function that updates a persisted Purchase
# Line, Purchase Document header fact, or Receiving Line once inserted) and,
# where a single-row condition makes it possible, structurally here via
# CheckConstraint — see `PurchaseLine` (Supplier Product Relationship, Rule
# 3) and `ReceivingLine` (mandatory photo evidence, Rules 29-30).
#
# `Effective Product Cost`, allocation shares, category totals,
# `ReconciliationOutcome`, and Expected Supplier Credit's
# `RecognizedAmount`/`OutstandingAmount` are documented as derived, never
# persisted as canonical truth — none of them is a column anywhere below;
# see `rfone_data_store/purchasing/reconciliation.py` and `repository.py`
# for the on-demand derivation.
#
# No `Ingredient`/`Product`/`Specification` table exists yet anywhere in
# this schema (Recipe/Food Cost/Inventory are out of this task's scope, per
# TASK_PURCHASING_004, "Software boundary") — `SupplierProduct.ingredient_id`
# is therefore an un-constrained placeholder integer, not a real FK, so it
# never blocks Purchasing on a module this task does not build. See
# PURCHASING.md, "Remaining gaps."
# ---------------------------------------------------------------------------


class Supplier(Base):
    """A commercial organization that supplies products to the Restaurant
    (Purchasing/EntityDefinitions.md, "Supplier"). Restaurant-scoped, like
    every other Restaurant-configured entity in this schema (e.g.
    `RestaurantRole`, `TipPolicy`) — a Supplier is this Restaurant's own
    purchasing configuration, never a cross-Restaurant catalog row."""

    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("restaurants.id"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Free string (ACTIVE/INACTIVE illustrative), matching this schema's
    # convention for evolving classification fields.
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    acquisition_methods: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class SupplierAlias(Base):
    """A historical/source name a Supplier has been known by ("Purchased
    Supplier Training — Phase 2", canonical Supplier cleanup). Correcting
    `Supplier.name` in place (e.g. "PRIME LINE DISTRIBUTORS INVOICE" ->
    "Prime Line Distributors") must never discard the prior spelling —
    Purchased/README.md, "Supplier identity": "The original text/code as it
    appeared in the source must always remain available as source
    provenance, even after resolution to a canonical Supplier." This is the
    minimum needed to represent that — canonical Supplier + known source
    aliases — nothing else (no per-alias usage counters, no fuzzy-matching
    configuration)."""

    __tablename__ = "supplier_aliases"
    __table_args__ = (UniqueConstraint("supplier_id", "alias_name", name="uq_supplier_aliases_supplier_id_alias_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), nullable=False, index=True)
    alias_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Free text (illustrative, not an enum): e.g. "previous canonical name",
    # "source filename match" — why this alias is on file, not a
    # confidence score.
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PurchaseOrder(Base):
    """The Restaurant's purchasing request to a Supplier
    (Purchasing/EntityDefinitions.md, "Purchase Order"). Deliberately
    minimal: the Order/Purchase Support module that would create/manage
    these is explicitly not designed by TASK_PURCHASING_001-004 — this table
    exists only so Purchase Recording has an "Order" side to reconcile
    against (Purchasing/BusinessRules.md, Rule 26)."""

    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    supplier_id: Mapped[int] = mapped_column(
        ForeignKey("suppliers.id"), nullable=False, index=True
    )

    order_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PurchaseOrderLine(Base):
    """One requested item on a Purchase Order — the minimum information
    Purchase Recording needs for reconciliation (Purchasing/
    EntityDefinitions.md, "Purchase Order Line"): Supplier Product (when
    resolved) or a recognizable free-text description, plus the requested
    quantity. Never itself the Order/Purchase Support module."""

    __tablename__ = "purchase_order_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    purchase_order_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_orders.id"), nullable=False, index=True
    )
    supplier_product_id: Mapped[int | None] = mapped_column(
        ForeignKey("supplier_products.id"), nullable=True
    )

    item_description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SupplierProduct(Base):
    """The commercial product as defined by one specific Supplier
    (Purchasing/EntityDefinitions.md, "Supplier Product"). `(supplier_id,
    supplier_code)` is the "Supplier Product memory" key (Purchasing/
    EntityDefinitions.md: "the pair (Supplier, Supplier Item Code)
    identifies a Supplier Product across purchases over time") — enforced
    here as a unique constraint so the repository's get-or-create lookup is
    race-safe, not merely an application convention. `economic_classification`
    is the CURRENT confirmed value, reused for future Purchase Lines; a
    later correction updates this row only — it never rewrites a
    `PurchaseLine.economic_classification` already recorded under the prior
    value (Purchasing/DataDictionary.md, "Attribute Principles")."""

    __tablename__ = "supplier_products"
    __table_args__ = (UniqueConstraint("supplier_id", "supplier_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    supplier_id: Mapped[int] = mapped_column(
        ForeignKey("suppliers.id"), nullable=False, index=True
    )

    supplier_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    supplier_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    packaging: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # FOOD / DRINK / SUPPLIES / OTHER (Purchasing/EntityDefinitions.md,
    # "Merchandise / Economic Classification") — free string: the Domain
    # explicitly anticipates "future categories as required by reality."
    economic_classification: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Un-constrained placeholder — see the module-level note above; no
    # `ingredients` table exists yet anywhere in this schema.
    ingredient_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class PurchaseDocument(Base):
    """The source commercial document of a purchase — Invoice, Receipt,
    Credit Note, API purchase record, or other real document
    (Purchasing/EntityDefinitions.md, "Purchase Document"); the central
    entity of the Purchasing module. Immutable by convention (Purchasing/
    BusinessRules.md, Rule 2): the repository never updates a row here
    except `status` (business processing status, not a source fact).

    Ownership (Align legacy Invoice Intake with Purchased): this table is the
    Purchase Fact `01 Domains/Shared Domains/Purchased/README.md` canonically
    owns (capture + normalize + publish) — Restaurant/Purchasing consumes it
    rather than owning it. A supplier-side correction (credit memo, corrected
    invoice, return credit, adjustment) is its own new row referencing the
    original by `document_number`/`supplier_id`, never a rewrite of a prior
    row (Purchased/README.md, "Supplier-side corrections"). NORMALIZED/HUMAN
    functional state is derived, not a column — see
    `purchasing/repository.py`'s `get_document_functional_status`.
    `destination_location` is stored as the Supplier's own disclosed text,
    not resolved against the canonical `locations` table — the source may
    name a ship-to address this Restaurant's own Location catalog does not
    contain, and Purchasing must not invent that resolution (Purchasing/
    EntityDefinitions.md: "extract what the source knows")."""

    __tablename__ = "purchase_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    supplier_id: Mapped[int] = mapped_column(
        ForeignKey("suppliers.id"), nullable=False, index=True
    )
    purchase_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("purchase_orders.id"), nullable=True
    )

    document_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Invoice / Receipt / Credit Note / API / Other — free string per
    # Purchasing/EntityDefinitions.md ("or other real document").
    document_type: Mapped[str] = mapped_column(String(32), nullable=False)
    issue_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivery_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    destination_location: Mapped[str | None] = mapped_column(String(500), nullable=True)
    customer_account_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # OCR / PDF / API / XML / EDI / Manual (Purchasing/DataAcquisition.md).
    acquisition_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    total_amount_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payment_terms: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Reference to the preserved original document (e.g. a path under
    # InvoiceIntake's `uploads/`), never the document content itself — same
    # "reference, not a duplicate blob store" choice as `SourceRecord.raw_path`.
    source_reference: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    source_provenance: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    lines: Mapped[list["PurchaseLine"]] = relationship(back_populates="purchase_document")


class PurchaseLine(Base):
    """One real line of a Purchase Document (Purchasing/EntityDefinitions.md,
    "Purchase Line") — a purchased product, a document-level surcharge, or a
    document-level discount. Immutable by convention (Rule 2, Rule 11): the
    repository never updates a row here once inserted.

    Both CheckConstraints below make Purchasing/BusinessRules.md Rule 3
    ("Supplier Product Relationship Depends on Line Type" — only a `PRODUCT`
    line may reference a Supplier Product or carry an economic
    classification) a structural database guarantee, not merely an
    application convention that could be bypassed by a future caller.

    Ownership (Align legacy Invoice Intake with Purchased): a `PRODUCT` line
    here is a Purchased Line (`01 Domains/Shared Domains/Purchased/README.md`).
    Non-goods `SURCHARGE`/`DISCOUNT` lines are kept as their own rows for
    source evidence but are never Purchased Lines in their own right —
    Purchased's canonical output allocates them across the `PRODUCT` lines
    instead (see `purchasing/repository.py`'s
    `get_purchased_lines_with_allocation`)."""

    __tablename__ = "purchase_lines"
    __table_args__ = (
        CheckConstraint("line_type IN ('PRODUCT', 'SURCHARGE', 'DISCOUNT')", name="ck_purchase_lines_line_type"),
        CheckConstraint(
            "line_type = 'PRODUCT' OR supplier_product_id IS NULL",
            name="ck_purchase_lines_supplier_product_requires_product_type",
        ),
        CheckConstraint(
            "line_type = 'PRODUCT' OR economic_classification IS NULL",
            name="ck_purchase_lines_classification_requires_product_type",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    purchase_document_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_documents.id"), nullable=False, index=True
    )

    line_type: Mapped[str] = mapped_column(String(16), nullable=False)
    source_line_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_description: Mapped[str] = mapped_column(String(1000), nullable=False)
    # Minor units; sign preserved exactly as disclosed (a DISCOUNT line's
    # sign/semantics are a source fact, Purchasing/DataDictionary.md).
    source_amount_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # PRODUCT-only attributes (Purchasing/DataDictionary.md) — nullable for
    # every row; the CheckConstraints above enforce the two that also carry
    # Domain-relationship meaning (SupplierProductId, EconomicClassification).
    supplier_product_id: Mapped[int | None] = mapped_column(
        ForeignKey("supplier_products.id"), nullable=True
    )
    supplier_item_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    supplier_category_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_section: Mapped[str | None] = mapped_column(String(255), nullable=True)
    manufacturer_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    purchase_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pack_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Preserved as disclosed (e.g. "500 g") rather than split into a
    # separate value/unit pair — Purchasing/DataDictionary.md documents
    # PackSize as one disclosed source fact, and splitting it would invent
    # structure the source does not necessarily provide.
    pack_size: Mapped[str | None] = mapped_column(String(64), nullable=True)
    product_variant: Mapped[str | None] = mapped_column(String(255), nullable=True)
    grade: Mapped[str | None] = mapped_column(String(128), nullable=True)
    unit_price_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # FOOD / DRINK / SUPPLIES / OTHER, once known and human-confirmed — a
    # persisted fact per Purchase Line (Purchasing/DataDictionary.md), not
    # merely inherited live from SupplierProduct.economic_classification.
    economic_classification: Mapped[str | None] = mapped_column(String(16), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    purchase_document: Mapped[PurchaseDocument] = relationship(back_populates="lines")


class ConfiguredExpectation(Base):
    """Approved operational knowledge about the normal/acceptable commercial
    configuration(s) for a Supplier Product (Purchasing/EntityDefinitions.md,
    "Configured Expectation"). Changes only prospectively (Rule 23): the
    repository never updates a row's `acceptable_configurations` in place —
    a change inserts a new row with `status = ACTIVE` and marks the prior
    Active row (if any) `status = SUPERSEDED`, so the full approval history
    is preserved rather than overwritten (mirrors `EmployeeAssignment`'s
    close-and-open pattern for a temporal fact elsewhere in this schema)."""

    __tablename__ = "configured_expectations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    supplier_product_id: Mapped[int] = mapped_column(
        ForeignKey("supplier_products.id"), nullable=False, index=True
    )

    # List of accepted configuration dicts (e.g. [{"pack_count": 20,
    # "pack_size": "500 g"}, {"pack_count": 10, "pack_size": "1 kg"}]) — the
    # Domain deliberately leaves this schema-free ("do not define a DB
    # schema now," TASK_PURCHASING_002 §6/T.3); JSON preserves that.
    acceptable_configurations: Mapped[list] = mapped_column(JSON, nullable=False)
    # ACTIVE / SUPERSEDED.
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    approved_by_employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )

    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ReceivingRecord(Base):
    """The Restaurant's own observation of what physically arrived
    (Purchasing/EntityDefinitions.md, "Receiving Record") — evidence, not a
    Purchasing Decision. `location_id` reuses the canonical POS `locations`
    table (the same "where" every other physical-presence fact in this
    schema resolves to, e.g. `Employee.location_id`) rather than inventing a
    second Location concept; nullable because Receiving Is Mobile-First and
    Fallback-Capable can begin before a Location is confirmed."""

    __tablename__ = "receiving_records"
    __table_args__ = (
        CheckConstraint(
            "capture_method IN ('LABEL_BASED', 'ORDER_BASED', 'MANUAL')",
            name="ck_receiving_records_capture_method",
        ),
        CheckConstraint("status IN ('IN_PROGRESS', 'COMPLETED')", name="ck_receiving_records_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    supplier_id: Mapped[int] = mapped_column(
        ForeignKey("suppliers.id"), nullable=False, index=True
    )
    purchase_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("purchase_orders.id"), nullable=True
    )
    purchase_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("purchase_documents.id"), nullable=True
    )
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    receiving_user_employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )

    receiving_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    capture_method: Mapped[str] = mapped_column(String(16), nullable=False)
    source_provenance: Mapped[str | None] = mapped_column(Text, nullable=True)
    # IN_PROGRESS / COMPLETED — independent of related Alert status (Rule 32).
    status: Mapped[str] = mapped_column(String(16), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    lines: Mapped[list["ReceivingLine"]] = relationship(back_populates="receiving_record")


class ReceivingLine(Base):
    """One observed item on a Receiving Record (Purchasing/
    EntityDefinitions.md, "Receiving Line"). No `purchase_order_line_id` ⇒
    Extra/Unexpected Item, by definition — never a separate entity/flag
    (same document, same "do not overmodel" instruction TASK_PURCHASING_003
    §6 gave the Domain). The two CheckConstraints below make Rules 29-30's
    mandatory-photo requirement a structural guarantee rather than an
    application convention: an Extra/Unexpected Item (no Purchase Order
    Line) or a damaged quantity cannot be inserted without photo evidence."""

    __tablename__ = "receiving_lines"
    __table_args__ = (
        CheckConstraint(
            "purchase_order_line_id IS NOT NULL OR photo_evidence IS NOT NULL",
            name="ck_receiving_lines_extra_item_requires_photo",
        ),
        CheckConstraint(
            "damaged_quantity IS NULL OR damaged_quantity = 0 OR photo_evidence IS NOT NULL",
            name="ck_receiving_lines_damaged_requires_photo",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    receiving_record_id: Mapped[int] = mapped_column(
        ForeignKey("receiving_records.id"), nullable=False, index=True
    )
    purchase_order_line_id: Mapped[int | None] = mapped_column(
        ForeignKey("purchase_order_lines.id"), nullable=True
    )
    purchase_line_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_lines.id"), nullable=True)
    supplier_product_id: Mapped[int | None] = mapped_column(
        ForeignKey("supplier_products.id"), nullable=True
    )

    raw_description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    observed_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    observed_pack_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    observed_pack_size: Mapped[str | None] = mapped_column(String(64), nullable=True)
    observed_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    observed_brand: Mapped[str | None] = mapped_column(String(255), nullable=True)
    observed_variant: Mapped[str | None] = mapped_column(String(255), nullable=True)
    observed_grade: Mapped[str | None] = mapped_column(String(128), nullable=True)
    damaged_quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    # Reference (e.g. an uploaded file path), never the image blob itself —
    # same convention as `PurchaseDocument.source_reference`.
    photo_evidence: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    capture_method: Mapped[str | None] = mapped_column(String(24), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    receiving_record: Mapped[ReceivingRecord] = relationship(back_populates="lines")


class PurchasingAlert(Base):
    """A case where RF-One knows what happened but observed Reality
    deviates from an operational expectation and requires human attention
    (Purchasing/EntityDefinitions.md, "Alert"). Named `PurchasingAlert`
    (table `purchasing_alerts`), not the bare `Alert`, since Alert is a
    cross-cutting Interaction Architecture concept (`03 Software/User
    Interaction Architecture.md` §7.1) that this task implements only for
    Purchasing — a future cross-module Alert table should not collide with
    this name. `reconciliation_context` is a human-readable snapshot only
    (e.g. "SHORT: ordered 4, invoiced 4, received 3") — Purchasing/
    DataDictionary.md documents `ReconciliationOutcome` as derived, never
    persisted as canonical truth, so no column here is ever treated as
    authoritative; a discrepancy is always resolved by recomputing from
    Order/Invoice/Receiving facts (`rfone_data_store/purchasing/
    reconciliation.py`), never by reading this note back."""

    __tablename__ = "purchasing_alerts"
    __table_args__ = (
        CheckConstraint(
            "trigger IN ('CONFIGURATION_DEVIATION', 'RECEIVING_DISCREPANCY')",
            name="ck_purchasing_alerts_trigger",
        ),
        CheckConstraint(
            "comparison_basis IS NULL OR comparison_basis IN ('CONFIGURED_EXPECTATION', 'PREVIOUS_PURCHASE')",
            name="ck_purchasing_alerts_comparison_basis",
        ),
        CheckConstraint(
            "status IN ('OPEN', 'ACKNOWLEDGED', 'DECIDED', 'CLOSED')",
            name="ck_purchasing_alerts_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Named "trigger" per Purchasing/EntityDefinitions.md, "Alert Trigger" —
    # quoted in the CheckConstraint text above since it is a SQL reserved
    # word in some dialects; SQLAlchemy quotes the identifier automatically.
    trigger: Mapped[str] = mapped_column(String(24), nullable=False)

    purchase_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("purchase_documents.id"), nullable=True, index=True
    )
    purchase_line_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_lines.id"), nullable=True)
    supplier_product_id: Mapped[int | None] = mapped_column(
        ForeignKey("supplier_products.id"), nullable=True
    )
    purchase_order_line_id: Mapped[int | None] = mapped_column(
        ForeignKey("purchase_order_lines.id"), nullable=True
    )
    receiving_record_id: Mapped[int | None] = mapped_column(
        ForeignKey("receiving_records.id"), nullable=True
    )
    receiving_line_id: Mapped[int | None] = mapped_column(ForeignKey("receiving_lines.id"), nullable=True)

    # Applicable when trigger = CONFIGURATION_DEVIATION.
    comparison_basis: Mapped[str | None] = mapped_column(String(24), nullable=True)
    expected_configuration: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    observed_configuration: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Applicable when trigger = RECEIVING_DISCREPANCY — descriptive only,
    # see the class docstring.
    reconciliation_context: Mapped[str | None] = mapped_column(Text, nullable=True)

    responsible_user_employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    # CONFIGURATION_DEVIATION vocabulary: ACCEPT_THIS_PURCHASE_ONLY /
    # ACCEPT_AS_ALTERNATIVE / CHANGE_EXPECTATION / MODULE_CAPABILITY_GAP.
    # RECEIVING_DISCREPANCY vocabulary: ACCEPT / REJECT_RETURN. Free string
    # (not a single combined CheckConstraint) since the valid set depends on
    # `trigger`, matching this schema's existing convention of leaving a
    # trigger-dependent vocabulary unconstrained at the DB level.
    human_decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    decided_by_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ExpectedSupplierCredit(Base):
    """The operational expectation that a Supplier owes an economic
    correction, created only when a REJECT/RETURN decision applies to
    already-invoiced merchandise (Purchasing/EntityDefinitions.md, "Expected
    Supplier Credit"). `RecognizedAmount`/`OutstandingAmount` are documented
    as derived (Purchasing/DataDictionary.md) — no column for either exists
    here; `rfone_data_store/purchasing/repository.py` computes them on
    demand from `SupplierCreditReference` rows. No arbitrary expiration
    (Rule 40) is enforced anywhere — nothing in this schema or the
    repository ever auto-closes a row here."""

    __tablename__ = "expected_supplier_credits"
    __table_args__ = (
        CheckConstraint(
            "status IN ('OPEN', 'PARTIALLY_RESOLVED', 'RESOLVED')",
            name="ck_expected_supplier_credits_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_id: Mapped[int] = mapped_column(
        ForeignKey("purchasing_alerts.id"), nullable=False, index=True
    )
    purchase_document_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_documents.id"), nullable=False
    )
    purchase_line_id: Mapped[int] = mapped_column(ForeignKey("purchase_lines.id"), nullable=False)

    rejected_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    expected_amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    credit_references: Mapped[list["SupplierCreditReference"]] = relationship(
        back_populates="expected_supplier_credit"
    )


class SupplierCreditReference(Base):
    """One later Supplier Purchase Document/credit-adjustment line
    recognized as satisfying an Expected Supplier Credit in whole or in
    part (Purchasing/DataDictionary.md, `LinkedCreditReferences`) — the
    join/detail table `ExpectedSupplierCredit` needs so
    `RecognizedAmount`/`OutstandingAmount` can be derived rather than
    persisted (Rule 38). Credit Note remains the sole canonical
    credit-document type (`PurchaseDocument.document_type`); no second
    credit-document ontology is introduced here (Rule 37)."""

    __tablename__ = "supplier_credit_references"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    expected_supplier_credit_id: Mapped[int] = mapped_column(
        ForeignKey("expected_supplier_credits.id"), nullable=False, index=True
    )
    # The crediting Purchase Document (typically a Credit Note) and/or its
    # specific line — independently nullable since a Supplier's credit
    # evidence is not always line-itemized (Rule 39).
    purchase_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("purchase_documents.id"), nullable=True
    )
    purchase_line_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_lines.id"), nullable=True)

    applied_amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    expected_supplier_credit: Mapped[ExpectedSupplierCredit] = relationship(
        back_populates="credit_references"
    )


class PurchasingValidationLogEntry(Base):
    """One recorded anomaly detected during acquisition, normalization,
    classification, mapping or validation (Purchasing/EntityDefinitions.md,
    "Validation Log"). Named with a `Purchasing` prefix (table
    `purchasing_validation_log_entries`) since Validation Log is a Core-level
    pattern this task implements only for Purchasing — see the
    `PurchasingAlert` docstring for the same naming rationale. Rows are
    never deleted; `status` moves OPEN → APPROVED/REJECTED → CLOSED without
    ever modifying `message`/`suggested_action` (Rule 13)."""

    __tablename__ = "purchasing_validation_log_entries"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('INFORMATION', 'WARNING', 'ERROR')",
            name="ck_purchasing_validation_log_entries_severity",
        ),
        CheckConstraint(
            "status IN ('OPEN', 'APPROVED', 'REJECTED', 'CLOSED')",
            name="ck_purchasing_validation_log_entries_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    purchase_document_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_documents.id"), nullable=False, index=True
    )
    purchase_line_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_lines.id"), nullable=True)

    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    human_decision: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PurchasedFieldCorrection(Base):
    """Purchased Human Review's own audit trail ("Purchased Human Review +
    Supplier Format Training UI"): one row per field a human reviewed —
    confirmed as `CORRECT`, or corrected from `original_value` to
    `corrected_value` after being classified `INCORRECT`/`UNREAD`/
    `AMBIGUOUS` (the same four Human Review Model classifications
    `supplier_format_training.py` already uses — Task requirement 6).

    **Never overwrites `PurchaseDocument`/`PurchaseLine`'s own columns** —
    those stay exactly as originally extracted, forever (Task requirement
    5: "La source evidence resta immutabile"; also preserves the existing
    "no function updates a source-fact column once inserted" invariant
    documented at the top of this repository module). This table is purely
    additive: one INSERT per review action, oldest-first is the complete
    history, and the LATEST row for a given (document, line, field) is the
    "effective" reviewed value — see `03 Software/InvoiceIntake/
    human_review.py`'s `effective_document_view()`, which merges these on
    top of the immutable original columns for display/re-validation.
    Nothing here is ever deleted or updated in place.

    `field_name` is free text (illustrative, not an enum) — matches
    whichever header/line field the review screen showed: `"supplier"`,
    `"document_number"`, `"issue_date"`, `"total_amount"`, `"description"`,
    `"normalized_item"`, `"quantity"`, `"unit_of_measure"`, `"unit_price"`,
    `"line_amount"`."""

    __tablename__ = "purchased_field_corrections"
    __table_args__ = (
        CheckConstraint(
            "classification IN ('CORRECT', 'INCORRECT', 'UNREAD', 'AMBIGUOUS')",
            name="ck_purchased_field_corrections_classification",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    purchase_document_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_documents.id"), nullable=False, index=True
    )
    # NULL for a header-level field; set for a line-level field.
    purchase_line_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_lines.id"), nullable=True, index=True)

    field_name: Mapped[str] = mapped_column(String(64), nullable=False)
    classification: Mapped[str] = mapped_column(String(16), nullable=False)
    original_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrected_value: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Free text, not a User FK -- Identity & Access is currently frozen (see
    # `10 System/Identity & Access/README.md`) and no Domain integrates
    # with it yet; recording a plain reviewer name/identifier here is the
    # minimum viable "who reviewed" audit trail (Task requirement 17)
    # without building against the frozen foundation.
    reviewed_by: Mapped[str] = mapped_column(String(255), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PurchasedLineAddition(Base):
    """Audit trail for a `PurchaseLine` added during Purchased Human Review
    because the original OCR/parser extraction never created one at all
    ("Close Purchased Human Review Reliability Gaps", §3: "impossibilità di
    aggiungere Purchase Lines mancanti").

    The referenced `PurchaseLine` (`purchase_line_id`) IS a genuine row in
    `purchase_lines` — inserted once, through the same immutable-by-
    convention discipline every other `PurchaseLine` follows — so it
    participates in `get_purchased_lines_with_allocation()`/non-goods
    allocation and every other Effective Purchased View consumer exactly
    like an originally-extracted line (Task §4/§5: "I consumer BD devono
    vederle esattamente come le altre Purchased Lines effettive"). This
    table is the ONLY way to tell the two apart: a `PurchaseLine` with a
    matching row here was never produced by the original capture — the
    source/raw view uses this to say so (Task §4: "La source/raw view deve
    continuare a mostrare che la riga non esisteva nell'estrazione
    originale") — every other `PurchaseLine` is original source evidence,
    unchanged. One row per ADD_LINE action; never updated or deleted.

    `reviewed_by`/`added_at` are this action's own audit fields (Task §3:
    "reviewer, timestamp, action = ADD_LINE") — "action" itself is implicit
    in this table's very existence (a row here always means ADD_LINE; no
    other action is ever recorded by it), matching the same "free text
    reviewer identifier, no User FK" convention `PurchasedFieldCorrection`
    already uses (Identity & Access is frozen)."""

    __tablename__ = "purchased_line_additions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    purchase_document_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_documents.id"), nullable=False, index=True
    )
    purchase_line_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_lines.id"), nullable=False, unique=True, index=True
    )
    added_by: Mapped[str] = mapped_column(String(255), nullable=False)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# ---------------------------------------------------------------------------
# Selection module — Resume Screening (TASK_SELECTION_001)
#
# Persists only Facts (01 Domains/Shared Domains/Selection/
# ResumeScreening/EvidenceModel.md): the candidate's declared/résumé-stated
# information and the raw résumé it came from. Derived Information, Flags
# and Indicators are never persisted here — they are recomputed on every
# read by `rfone_data_store/selection/analysis.py` from these Facts, so a
# revisit is always internally consistent and never stale relative to
# whatever the analysis engine currently computes.
# ---------------------------------------------------------------------------


class RawResume(Base):
    """A résumé as acquired from its ResumeSource, before parsing
    (ResumeScreening/CandidateCVProfile.md, "Resume Source architecture":
    ResumeSource -> RawResume -> ResumeParser -> CandidateCVProfile).
    `source_type` keeps this open to a future non-file ResumeSource (e.g. an
    API feed) without any schema change — `storage_path` is nullable and is
    only ever populated for a file-based source such as local upload."""

    __tablename__ = "raw_resumes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    restaurant_id: Mapped[int | None] = mapped_column(
        ForeignKey("restaurants.id"), nullable=True, index=True
    )

    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    storage_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Best-effort duplicate-detection signal (TASK_SELECTION_002) — a hash of
    # the extracted raw text, or of the filename when no text could be
    # extracted (see `selection/parsing/dedup.py`). Nullable because it is
    # only ever computed by the batch-import path; never used to identify a
    # candidate on its own, only to flag a likely re-upload of the same file.
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Candidate(Base):
    """A candidate's CV Profile (ResumeScreening/CandidateCVProfile.md,
    "CANDIDATE"). `restaurant_id` is nullable — Selection Core is
    client-agnostic by design (ResumeScreening/README.md, "Domain
    architecture") — but is populated here for the current single-client
    Runtime deployment, the same scoping convention every other
    Restaurant-configured entity in this schema already uses."""

    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    restaurant_id: Mapped[int | None] = mapped_column(
        ForeignKey("restaurants.id"), nullable=True, index=True
    )
    raw_resume_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_resumes.id"), nullable=True, index=True
    )

    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    languages: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    declared_availability: Mapped[str | None] = mapped_column(String(255), nullable=True)

    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_file: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Who/what acquired the résumé within `source` (e.g. "manual" for today's
    # LOCAL_UPLOAD; a future API integration would set its provider name
    # here without any schema change — TASK_SELECTION_002 §3).
    source_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # "REAL_AI", "RULE_BASED" or "DEMO" — never disguised (task §18; Task 2A
    # §11 removed the fabricated-fixture DEMO fallback from the production
    # import path — DEMO now only appears on synthetic test fixtures).
    # Always shown in the UI.
    parsing_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="DEMO")
    parser_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Task 2A additions — Facts only, extracted as stated, never invented.
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    other_profile_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    other_sections_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Contextual age/career information (ResumeScreening/ExperienceAndTrajectory.md,
    # "Contextual career / age information") — Facts/derived-context only,
    # deliberately outside every Indicator; never read by analysis.py's
    # indicator calculations.
    declared_age_context: Mapped[str | None] = mapped_column(String(64), nullable=True)
    derived_age_context_range: Mapped[str | None] = mapped_column(String(64), nullable=True)
    derived_age_context_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    derived_age_context_confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="NEW")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    education: Mapped[list["CandidateEducation"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan",
        order_by="CandidateEducation.start_date",
    )
    work_history: Mapped[list["CandidateWorkHistory"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan",
        order_by="CandidateWorkHistory.start_date",
    )
    skills: Mapped[list["CandidateSkill"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan", order_by="CandidateSkill.id",
    )
    certifications: Mapped[list["CandidateCertification"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan", order_by="CandidateCertification.id",
    )
    language_records: Mapped[list["CandidateLanguage"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan", order_by="CandidateLanguage.id",
    )


class CandidateEducation(Base):
    """One education record (ResumeScreening/CandidateCVProfile.md,
    "EDUCATION"). Every field is a Fact; nothing here is derived — INCLUDING
    `start_date`/`end_date`, which (Task 2B) are the NORMALIZED dates,
    always re-derived from `start_date_text`/`end_date_text` (the résumé's
    own text, untouched) by `selection/normalization.py`. They are stored
    facts of normalization, not Derived Information recomputed on every
    read — the same convention Task 2A already established for
    `CandidateWorkHistory.normalized_role` below."""

    __tablename__ = "candidate_education"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id"), nullable=False, index=True
    )

    institution: Mapped[str | None] = mapped_column(String(255), nullable=True)
    program: Mapped[str | None] = mapped_column(String(255), nullable=True)
    qualification: Mapped[str | None] = mapped_column(String(255), nullable=True)
    field: Mapped[str | None] = mapped_column(String(255), nullable=True)
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completion_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    certifications: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Task 2B — date normalization (see WorkHistoryRecord's matching Task 2B
    # columns below for the full rationale).
    start_date_text: Mapped[str | None] = mapped_column(String(64), nullable=True)
    end_date_text: Mapped[str | None] = mapped_column(String(64), nullable=True)
    start_date_precision: Mapped[str | None] = mapped_column(String(16), nullable=True)
    end_date_precision: Mapped[str | None] = mapped_column(String(16), nullable=True)
    date_normalization_confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)

    candidate: Mapped["Candidate"] = relationship(back_populates="education")


class CandidateWorkHistory(Base):
    """One employment record (ResumeScreening/CandidateCVProfile.md, "WORK
    HISTORY"). `normalized_role`/`start_date`/`end_date`/`is_current` and
    every Task 2B column below are Derived-but-stored, always re-derived
    from a Fact column on this same row (`original_job_title` for role
    fields; `start_date_text`/`end_date_text` for date fields) by
    `selection/normalization.py` — never overwriting the Fact they came
    from, and safe to recompute at any time via
    `normalization.reprocess_candidate()` (task "REPROCESSING EXISTING
    CANDIDATES"). `duration in months` is the one exception kept OUT of this
    table — it is always recomputed on read by `selection/core/
    experience_analysis.py.work_entry_duration_months()`, never stored,
    since date precision only ever gets more accurate over time (a future
    reprocess), never the reverse."""

    __tablename__ = "candidate_work_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id"), nullable=False, index=True
    )

    employer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    original_job_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    normalized_role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    responsibilities: Mapped[str | None] = mapped_column(Text, nullable=True)
    achievements: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason_for_leaving: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Task 2B — date normalization. `start_date_text`/`end_date_text` are
    # the résumé's own text, exactly as extracted (e.g. "Jan 2021",
    # "Present"); `start_date`/`end_date`/`is_current` above are always
    # re-derived from these two, never hand-set elsewhere.
    start_date_text: Mapped[str | None] = mapped_column(String(64), nullable=True)
    end_date_text: Mapped[str | None] = mapped_column(String(64), nullable=True)
    start_date_precision: Mapped[str | None] = mapped_column(String(16), nullable=True)
    end_date_precision: Mapped[str | None] = mapped_column(String(16), nullable=True)
    date_normalization_confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # Task 2B — role/title normalization. Always re-derived from
    # `original_job_title` above, never from each other.
    normalized_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role_family: Mapped[str | None] = mapped_column(String(64), nullable=True)
    seniority_level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    multi_role: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    title_normalization_confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)

    candidate: Mapped["Candidate"] = relationship(back_populates="work_history")


class CandidateSkill(Base):
    """One stated skill (ResumeScreening/CandidateCVProfile.md, "SKILLS").
    Task 2A: extracted exactly as stated — no inferred, normalized, or rated
    skills."""

    __tablename__ = "candidate_skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id"), nullable=False, index=True
    )
    skill: Mapped[str] = mapped_column(String(255), nullable=False)

    candidate: Mapped["Candidate"] = relationship(back_populates="skills")


class CandidateCertification(Base):
    """One certification/license (ResumeScreening/CandidateCVProfile.md,
    "CERTIFICATIONS / LICENSES"). Kept separate from
    `CandidateEducation.certifications` (free text tied to an education
    record) so a standalone certification is not lost."""

    __tablename__ = "candidate_certifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    issuer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    date_text: Mapped[str | None] = mapped_column(String(64), nullable=True)

    candidate: Mapped["Candidate"] = relationship(back_populates="certifications")


class CandidateLanguage(Base):
    """One language record (ResumeScreening/CandidateCVProfile.md,
    "LANGUAGES") — distinct from the coarser `Candidate.languages` free-text
    Fact, which remains a single-string summary a parser may also
    populate."""

    __tablename__ = "candidate_languages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id"), nullable=False, index=True
    )
    language: Mapped[str] = mapped_column(String(64), nullable=False)
    proficiency: Mapped[str | None] = mapped_column(String(64), nullable=True)

    candidate: Mapped["Candidate"] = relationship(back_populates="language_records")


# ---------------------------------------------------------------------------
# Selection module — Requirement Framework (TASK 3A)
#
# Defines WHAT a restaurant is looking for — never what a candidate is, and
# never whether a candidate fits (01 Domains/Shared Domains/Selection/SelectionRequirement.md).
# `RequirementTemplate`/`RequirementTemplateItem` are RF-One-provided,
# reusable starting points; `RequirementSet`/`Requirement` are the
# restaurant-owned, independently editable result of instantiating (cloning)
# a template — editing one never touches the other (`source_template_id` is
# traceability only, not a live link). No candidate/Fit-Assessment table
# exists here; this framework is completely separable from Candidate
# evidence, exactly as the task requires.
# ---------------------------------------------------------------------------


class RequirementTemplate(Base):
    """An RF-One-provided starting point (task §8) — e.g. "High-Volume
    Server". Never restaurant-specific data itself; a restaurant clones one
    into its own `RequirementSet` (`instantiate_requirement_set_from_template`
    in `selection/requirements_service.py`) and edits the clone freely.
    `intended_role` is a free-text/normalized-role hint for filtering the
    template list (task §9: multiple templates may target the same nominal
    role), not a hard constraint."""

    __tablename__ = "requirement_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    intended_role: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    items: Mapped[list["RequirementTemplateItem"]] = relationship(
        back_populates="template", cascade="all, delete-orphan", order_by="RequirementTemplateItem.display_order",
    )


class RequirementTemplateItem(Base):
    """One requirement inside a `RequirementTemplate` — the default shape a
    cloned `Requirement` starts from (task §8's "default criticality/
    trainability/assessment stages/evaluation guidance"). See `Requirement`
    below for what each field means; kept as a near-identical parallel
    structure deliberately, so cloning is a straightforward field-by-field
    copy (`selection/requirements_service.py`)."""

    __tablename__ = "requirement_template_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("requirement_templates.id"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    criticality: Mapped[str] = mapped_column(String(16), nullable=False)
    trainability: Mapped[str] = mapped_column(String(24), nullable=False)
    # List of assessment-stage codes (task §5: "a requirement may be
    # assessable at more than one stage") — JSON, same convention already
    # used elsewhere in this schema for a small string-list column (e.g.
    # `PurchasingAcceptableConfiguration.acceptable_configurations`).
    assessment_stages: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    evidence_positive: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_contrary: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_insufficient: Mapped[str | None] = mapped_column(Text, nullable=True)
    guidance_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    template: Mapped["RequirementTemplate"] = relationship(back_populates="items")


class RequirementSet(Base):
    """"What are we looking for for this specific hiring need?" (task §1) —
    restaurant-owned, independently editable once created, whether it came
    from a template or was built from scratch. `restaurant_id` mirrors the
    same nullable-FK convention `Candidate`/`RawResume` already use (Selection
    Core stays client-agnostic; populated for the current single-client
    Runtime deployment). `location_label` is a free-text hint (e.g. "Mount
    Dora"), not a FK to `locations` — a Requirement Set is a hiring-need
    concept, not tied to Restaurant's own location schema.

    `version` is incremented by `selection/requirements_service.py`
    whenever this set or its requirements are structurally edited (Task 3A
    §12). Since Task 3A-FIX, a version additionally identifies an immutable
    `RequirementSetSnapshot` — call `requirements_service.
    create_requirement_set_snapshot()` to capture the set's exact current
    state (and every Requirement's) before it changes further; a later Fit
    Assessment binds to that snapshot, not to these live, still-editable
    rows."""

    __tablename__ = "requirement_sets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    restaurant_id: Mapped[int | None] = mapped_column(
        ForeignKey("restaurants.id"), nullable=True, index=True
    )
    source_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("requirement_templates.id"), nullable=True, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_role: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    source_template: Mapped["RequirementTemplate | None"] = relationship()
    requirements: Mapped[list["Requirement"]] = relationship(
        back_populates="requirement_set", cascade="all, delete-orphan", order_by="Requirement.display_order",
    )


class Requirement(Base):
    """One individual Requirement inside a restaurant's `RequirementSet`
    (task §2) — e.g. "Ability to work effectively in a team." Defines WHAT
    the restaurant wants and HOW it may eventually be recognized
    (`evidence_*`/`guidance_notes`, task §6); it does not itself hold or
    reference any candidate evidence. `is_active=False` is Task 3A's
    deactivation mechanism (task §12/test L) — a requirement is never
    hard-deleted, so historical structure (what this set once required) is
    never silently lost."""

    __tablename__ = "requirements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    requirement_set_id: Mapped[int] = mapped_column(
        ForeignKey("requirement_sets.id"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    criticality: Mapped[str] = mapped_column(String(16), nullable=False)
    trainability: Mapped[str] = mapped_column(String(24), nullable=False)
    assessment_stages: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    evidence_positive: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_contrary: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_insufficient: Mapped[str | None] = mapped_column(Text, nullable=True)
    guidance_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    requirement_set: Mapped["RequirementSet"] = relationship(back_populates="requirements")


class RequirementSetSnapshot(Base):
    """An IMMUTABLE, point-in-time copy of a `RequirementSet` and every
    `Requirement` it held at the moment of capture (TASK 3A-FIX). Exists so
    a later Fit Assessment (Task 3B) can stay bound to the exact Requirement
    definitions used, even after the live `RequirementSet` keeps evolving —
    "LIVE REQUIREMENT SET may continue changing; HISTORICAL REQUIREMENT
    VERSION/SNAPSHOT must remain immutable once created."

    Every field here is a copy by value, captured once by
    `requirements_service.create_requirement_set_snapshot()` — never
    recomputed, never re-synced from the live `RequirementSet`/`Requirement`
    rows. `requirements_service.py` intentionally exposes no update
    operation for a snapshot or its items: once a row exists here, nothing
    in this codebase is allowed to write to it again.

    `(requirement_set_id, version)` is unique — `version` is the live
    `RequirementSet.version` AT CAPTURE TIME, so a snapshot is always
    addressable by "this Requirement Set, as of version N," and requesting
    a snapshot for a version that already has one returns the existing row
    instead of an unnecessary duplicate (task §3)."""

    __tablename__ = "requirement_set_snapshots"
    __table_args__ = (
        UniqueConstraint("requirement_set_id", "version", name="uq_requirement_set_snapshots_set_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    requirement_set_id: Mapped[int] = mapped_column(
        ForeignKey("requirement_sets.id"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    # Requirement Set-level fields, copied by value at capture time — never
    # re-read from the live `RequirementSet` row afterward.
    restaurant_id: Mapped[int | None] = mapped_column(nullable=True)
    source_template_id: Mapped[int | None] = mapped_column(nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    was_active: Mapped[bool] = mapped_column(Boolean, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    items: Mapped[list["RequirementSnapshotItem"]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan", order_by="RequirementSnapshotItem.display_order",
    )


class RequirementSnapshotItem(Base):
    """One `Requirement`'s state, copied by value into a
    `RequirementSetSnapshot` (TASK 3A-FIX). `source_requirement_id` is
    deliberately NOT a foreign key (unlike every other `*_id` column in this
    schema) — a snapshot must stay completely valid and unaffected even if
    the live `Requirement` row it was copied from is later changed,
    deactivated, or (were hard deletion ever added) removed entirely; a real
    FK would risk exactly the coupling this table exists to avoid."""

    __tablename__ = "requirement_snapshot_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("requirement_set_snapshots.id"), nullable=False, index=True
    )
    source_requirement_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    criticality: Mapped[str] = mapped_column(String(16), nullable=False)
    trainability: Mapped[str] = mapped_column(String(24), nullable=False)
    assessment_stages: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    evidence_positive: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_contrary: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_insufficient: Mapped[str | None] = mapped_column(Text, nullable=True)
    guidance_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    was_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    snapshot: Mapped["RequirementSetSnapshot"] = relationship(back_populates="items")


# ---------------------------------------------------------------------------
# Selection module — Fit Assessment (TASK 3B)
#
# Answers "for this candidate, against this exact immutable Requirement Set
# snapshot, what evidence do we have regarding each Requirement?" — never a
# hiring decision, never a score. Assessment always reads Requirement
# definitions from `RequirementSnapshotItem` (immutable, TASK 3A-FIX), never
# from live `Requirement` rows, so a Fit Assessment's meaning cannot be
# silently rewritten by later edits to the restaurant's live Requirement Set
# (01 Domains/Shared Domains/Selection/FitAssessment.md).
# ---------------------------------------------------------------------------


class FitAssessment(Base):
    """One evaluation run of one candidate against one immutable
    `RequirementSetSnapshot`. `requirement_set_id` is a denormalized copy of
    `snapshot.requirement_set_id`, kept only for convenient navigation back
    to the live Requirement Set (task §3) — it is never used to resolve
    Requirement definitions; `requirement_set_snapshot_id` alone is
    authoritative for that. Assessing the same candidate against a NEWER
    live version is always a NEW `FitAssessment` row bound to a NEW
    snapshot (task §21) — this row is never repointed to a different
    snapshot after creation."""

    __tablename__ = "fit_assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False, index=True)
    requirement_set_snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("requirement_set_snapshots.id"), nullable=False, index=True
    )
    requirement_set_id: Mapped[int | None] = mapped_column(
        ForeignKey("requirement_sets.id"), nullable=True, index=True
    )

    # The most advanced assessment stage this Fit Assessment currently
    # reflects (task §3) — "RESUME" after Task 3B's own generation; a later
    # (not-yet-built) stage advances this only when evidence for that stage
    # is actually added, never speculatively.
    current_stage: Mapped[str] = mapped_column(String(24), nullable=False, default="RESUME")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)  # Free-form human note — NEVER evidence.

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    candidate: Mapped["Candidate"] = relationship()
    requirement_set_snapshot: Mapped["RequirementSetSnapshot"] = relationship()
    requirement_assessments: Mapped[list["RequirementAssessment"]] = relationship(
        back_populates="fit_assessment", cascade="all, delete-orphan",
        order_by="RequirementAssessment.display_order",
    )


class RequirementAssessment(Base):
    """The fundamental unit (task §4): Candidate x RequirementSnapshotItem.
    Exactly one row per (fit_assessment, requirement_snapshot_item) — later
    evidence enriches this SAME row (via new `EvidenceItem` rows) rather
    than creating a duplicate, so reassessment never destroys prior-stage
    evidence (task §19).

    `system_status` is always what `core.fit_assessment_model.
    compute_status_from_evidence()` currently computes from this row's
    evidence — recalculated on every evidence change. `effective_status`
    starts equal to it, but a human override (task §17) can set
    `effective_status` independently; once `origin` is any HUMAN_* value,
    automatic recomputation stops touching `effective_status` (it keeps
    updating `system_status` for transparency, but never overwrites a
    human's recorded conclusion) — see `fit_assessment_service.py`."""

    __tablename__ = "requirement_assessments"
    __table_args__ = (
        UniqueConstraint(
            "fit_assessment_id", "requirement_snapshot_item_id", name="uq_requirement_assessment_fit_item"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fit_assessment_id: Mapped[int] = mapped_column(
        ForeignKey("fit_assessments.id"), nullable=False, index=True
    )
    requirement_snapshot_item_id: Mapped[int] = mapped_column(
        ForeignKey("requirement_snapshot_items.id"), nullable=False, index=True
    )

    stage: Mapped[str] = mapped_column(String(24), nullable=False, default="RESUME")
    system_status: Mapped[str] = mapped_column(String(32), nullable=False)
    effective_status: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)  # Free-form human note — NEVER evidence.
    origin: Mapped[str] = mapped_column(String(24), nullable=False, default="SYSTEM_GENERATED")

    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    overridden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    fit_assessment: Mapped["FitAssessment"] = relationship(back_populates="requirement_assessments")
    requirement_snapshot_item: Mapped["RequirementSnapshotItem"] = relationship()
    evidence_items: Mapped[list["EvidenceItem"]] = relationship(
        back_populates="requirement_assessment", cascade="all, delete-orphan", order_by="EvidenceItem.id",
    )


class EvidenceItem(Base):
    """One piece of evidence for one `RequirementAssessment` (task §7).
    Append-only by design — evidence is never edited or deleted once
    created (no `updated_at`), so multiple, even conflicting, evidence
    items always coexist (task §14) and later-stage evidence never
    destroys earlier evidence (task §19). `is_system_generated`
    distinguishes automatically produced evidence (safe to regenerate on
    refresh, task §21) from human-added evidence (never touched by an
    automatic refresh)."""

    __tablename__ = "evidence_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    requirement_assessment_id: Mapped[int] = mapped_column(
        ForeignKey("requirement_assessments.id"), nullable=False, index=True
    )

    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_stage: Mapped[str | None] = mapped_column(String(24), nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    evidence_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_classification: Mapped[str] = mapped_column(String(24), nullable=False)
    evidence_relationship: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False, default="UNKNOWN")
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_system_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    requirement_assessment: Mapped["RequirementAssessment"] = relationship(back_populates="evidence_items")


# ---------------------------------------------------------------------------
# Selection module — Selection Signals + Review Priority (TASK 3C)
#
# Concept note §1: CANDIDATE (the person) is distinct from APPLICATION (one
# specific application by that person for a specific role/context/date).
# `CandidatePerson` is the person-level identity Task 3C introduces;
# `Candidate` (above, Task 2A) keeps its existing meaning UNCHANGED — one
# parsed résumé/CV dataset — and now plays the role of "one Application's
# CV snapshot." `Application` links the two, plus the context (target role,
# Requirement Set, Review Priority) the concept note asks for. This naming
# is a deliberate, documented compromise: renaming the existing `Candidate`
# table (used throughout Task 2A/2B/3A/3B) was judged riskier than adding
# `CandidatePerson` alongside it — see `selection/application_service.py`'s
# own module docstring.
#
# Selection Signals mirror the Requirement Framework's architecture exactly
# (`SignalDefinition` ~ `Requirement`, restaurant-configurable, never
# hard-coded universal rules) and Signal Observations mirror Fit
# Assessment's evidence model (`SignalObservation` ~ `RequirementAssessment`,
# `SignalEvidenceItem` ~ `EvidenceItem`) — reusing the same vocabulary
# (`core/fit_assessment_model.py`'s evidence source/classification/
# relationship/confidence constants) rather than inventing a parallel one.
# `SignalEvidenceItem` is a structurally separate table from `EvidenceItem`
# (not a shared/polymorphic one) so Task 3B's tested, working table and its
# NOT NULL `requirement_assessment_id` never need to be loosened.
# ---------------------------------------------------------------------------


class CandidatePerson(Base):
    """The PERSON, across every Application they have ever submitted
    (concept note §1) — as distinct from `Candidate` above, which remains
    one résumé/CV dataset for one Application. `restaurant_id` mirrors the
    same nullable-FK, client-scoping convention every other Selection
    entity uses. Identity resolution (deciding whether a newly-imported
    résumé belongs to an already-known person) is a best-effort match on
    email — see `application_service.py` — never claimed to be perfect,
    the same honest caveat Task 2A's content-hash duplicate detection
    already carries for a related, but different, problem."""

    __tablename__ = "candidate_persons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    restaurant_id: Mapped[int | None] = mapped_column(
        ForeignKey("restaurants.id"), nullable=True, index=True
    )
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    primary_email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    primary_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Task 3C-FIX — identity-resolution improvements. `primary_phone` above
    # keeps the phone exactly as captured (display); this is the digits-only
    # form `identity_service.py` actually matches on. `normalized_name` is
    # used only for STRONG/POSSIBLE name-based match SUGGESTIONS — it is
    # never, on its own, grounds to auto-attach an Application to a person
    # (see identity_service.py's own docstring).
    primary_phone_normalized: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    normalized_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    applications: Mapped[list["Application"]] = relationship(
        back_populates="person", order_by="Application.applied_at",
    )
    # Task 5A — Candidate Flags are PERSON-level (they follow the person
    # across every Application, not just one), unlike everything else in
    # this file's Selection section, which is Application-scoped.
    flags: Mapped[list["CandidateFlag"]] = relationship(
        back_populates="person", cascade="all, delete-orphan", order_by="CandidateFlag.id",
    )


class Application(Base):
    """One specific application by one `CandidatePerson`, for a specific
    role/context/date (concept note §1) — the primary unit Review Priority
    and Selection Signals attach to, never the person directly and never
    the raw CV data directly. `candidate_id` is the résumé/CV snapshot this
    Application was submitted with (Task 2A's `Candidate` row) — one
    Application per `Candidate` row.

    `review_priority_system`/`review_priority_effective`/
    `review_priority_origin` mirror Task 3B's `RequirementAssessment`
    system/effective/origin pattern exactly (concept note §10: "System
    priority and Selezionatore override must remain distinguishable.")."""

    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("candidate_persons.id"), nullable=False, index=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id"), nullable=False, unique=True, index=True
    )
    restaurant_id: Mapped[int | None] = mapped_column(
        ForeignKey("restaurants.id"), nullable=True, index=True
    )
    requirement_set_id: Mapped[int | None] = mapped_column(
        ForeignKey("requirement_sets.id"), nullable=True, index=True
    )
    target_role: Mapped[str | None] = mapped_column(String(64), nullable=True)

    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # Historical outcome (concept note §11) — a record only; Task 3C
    # implements no learning/correlation logic from this field.
    outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)

    review_priority_system: Mapped[str | None] = mapped_column(String(16), nullable=True)
    review_priority_effective: Mapped[str | None] = mapped_column(String(16), nullable=True)
    review_priority_origin: Mapped[str] = mapped_column(String(24), nullable=False, default="SYSTEM_GENERATED")
    review_priority_override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_priority_overridden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Task 3C-FIX — the concise reasons behind `review_priority_system`,
    # exactly as `core.signal_model.compute_review_priority()` returned them
    # (never a score), so the Review Queue can show WHY without recomputing.
    review_priority_reasons: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)  # Selezionatore note — never evidence.

    # Task 3C-FIX §7 — operational workflow status, entirely separate from
    # Review Priority above. Only ever set by an explicit Selezionatore
    # action (`application_service.set_workflow_status`) — nothing in this
    # codebase sets it automatically from a Signal or a priority category.
    workflow_status: Mapped[str] = mapped_column(String(24), nullable=False, default="NEW")
    workflow_status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    workflow_status_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Task 3C-FIX §1/§2 — identity-resolution provenance. SYSTEM_RESOLVED
    # covers both an automatic VERY_STRONG contact match and a brand-new
    # person; HUMAN_CONFIRMED records that a Selezionatore explicitly
    # confirmed/corrected which CandidatePerson this Application belongs to.
    identity_origin: Mapped[str] = mapped_column(String(24), nullable=False, default="SYSTEM_RESOLVED")
    identity_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Task 5A — STAGE (where the Application currently is in the Selection
    # process) and OUTCOME's Application-lifecycle effect, deliberately
    # separate concepts from `workflow_status` above (kept, unchanged, for
    # backward compatibility — see `core/stage_model.py`/
    # `core/outcome_model.py` and `selection_validation.py`'s Task 5A
    # checks for exactly how the two coexist). Both are convenience fields
    # only — `current_stage` mirrors the latest `ApplicationStageTransition`
    # (task §3's own "the Application may expose one current Stage for
    # convenience, but the historical transitions remain permanent");
    # `lifecycle_state` mirrors the latest `SelectionOutcomeDecision`'s
    # snapshot `lifecycle_effect`. Neither is ever the sole record of truth
    # — full history always lives in the two append-only tables below.
    current_stage: Mapped[str] = mapped_column(String(32), nullable=False, default="APPLICATION_RECEIVED")
    lifecycle_state: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")
    # Task 5A-FIX §8 — convenience pointer to the current operational
    # queue/list, mirroring `current_stage`/`lifecycle_state` exactly:
    # never the sole record of truth, always derivable from the most
    # recent `ApplicationQueueMovement`. `None` means "no queue assigned"
    # (task §11 — never invent one when an applied Outcome configures none).
    current_queue_id: Mapped[int | None] = mapped_column(ForeignKey("selection_queues.id"), nullable=True, index=True)

    # Task 5C §26/§22 — the operational Session this Application belongs to
    # (nullable: an Application never HAS to belong to a Session — every
    # pre-5C Application, and any Application processed outside Session
    # governance, remains valid with `session_id=None`). `rule_set_version_id`
    # is stamped ONCE, when the Application is linked to its Session
    # (`session_service.link_application_to_session`), to the Session's
    # THEN-current Rule Set version — and is NEVER rewritten afterward, even
    # by a later Rule Change (task §18/§22: "already-processed Applications
    # remain tied to the Rule Set version under which they were evaluated" /
    # "do NOT retroactively rewrite prior results"). Whether this Application
    # was later affected by a retroactive Rule Change is answered by
    # `SelectionRuleChangeImpact`, never by mutating this column.
    session_id: Mapped[int | None] = mapped_column(ForeignKey("selection_sessions.id"), nullable=True, index=True)
    rule_set_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("selection_rule_set_versions.id"), nullable=True, index=True
    )

    # Task 5D §1 — WHERE the candidate found out about this role (Indeed,
    # Referral, Walk-In...), deliberately distinct from Communication
    # Channel (how RF-One later contacts them) and from `Candidate.source`
    # (Task 2A's résumé-ACQUISITION-mechanism field, e.g. LOCAL_UPLOAD).
    # Nullable — "where known" (task's own qualifier); `..._other_text` only
    # ever holds a value when the chosen source is the catch-all "Other."
    acquisition_source_id: Mapped[int | None] = mapped_column(
        ForeignKey("acquisition_source_definitions.id"), nullable=True, index=True
    )
    acquisition_source_other_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Task 5E §10/§14/§31 — the exact tracking-link-resolved placement this
    # Application arrived through, when known (nullable — most Applications
    # still arrive by direct upload, unrelated to any Job Posting). This is
    # the precise join key channel/publication/placement analytics reads;
    # `acquisition_source_id` above remains the coarser, always-present
    # attribution.
    channel_publication_id: Mapped[int | None] = mapped_column(
        ForeignKey("channel_publications.id"), nullable=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    person: Mapped["CandidatePerson"] = relationship(back_populates="applications")
    acquisition_source: Mapped["AcquisitionSourceDefinition | None"] = relationship()
    channel_publication: Mapped["ChannelPublication | None"] = relationship()
    candidate: Mapped["Candidate"] = relationship()
    requirement_set: Mapped["RequirementSet | None"] = relationship()
    signal_observations: Mapped[list["SignalObservation"]] = relationship(
        back_populates="application", cascade="all, delete-orphan", order_by="SignalObservation.id",
    )
    note_entries: Mapped[list["ApplicationNote"]] = relationship(
        back_populates="application", cascade="all, delete-orphan", order_by="ApplicationNote.id",
    )
    stage_transitions: Mapped[list["ApplicationStageTransition"]] = relationship(
        back_populates="application", cascade="all, delete-orphan", order_by="ApplicationStageTransition.id",
    )
    outcome_decisions: Mapped[list["SelectionOutcomeDecision"]] = relationship(
        back_populates="application", cascade="all, delete-orphan", order_by="SelectionOutcomeDecision.id",
    )
    queue_movements: Mapped[list["ApplicationQueueMovement"]] = relationship(
        back_populates="application", cascade="all, delete-orphan", order_by="ApplicationQueueMovement.id",
        foreign_keys="ApplicationQueueMovement.application_id",
    )
    current_queue: Mapped["SelectionQueue | None"] = relationship(foreign_keys=[current_queue_id])


class SignalDefinition(Base):
    """A restaurant-configurable Selection Signal definition (concept note
    §5) — mirrors `Requirement`'s shape closely (restaurant/client,
    assessment stage(s), evidence guidance, active/version) since a Signal
    is structurally the same kind of "what to look for, and how" object,
    just feeding Review Priority instead of a Fit Assessment. Never
    restaurant-specific logic hard-coded elsewhere — restaurants create
    their own rows here (concept note: "Do not hard-code Rome's Flavours
    Signals as universal RF-One rules.")."""

    __tablename__ = "signal_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    restaurant_id: Mapped[int | None] = mapped_column(
        ForeignKey("restaurants.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    signal_family: Mapped[str] = mapped_column(String(24), nullable=False)
    signal_subtype: Mapped[str | None] = mapped_column(String(64), nullable=True)
    assessment_stages: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evidence_sources_allowed: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    detection_guidance: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_positive: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_contrary: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_insufficient: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    policy_rules: Mapped[list["ReviewPriorityPolicyRule"]] = relationship(back_populates="signal_definition")


class SignalObservation(Base):
    """One (Application, SignalDefinition) unit (concept note §6) — the
    Signal-framework equivalent of Task 3B's `RequirementAssessment`.
    Exactly one row per pair; later evidence enriches this SAME row rather
    than creating a duplicate, exactly like `RequirementAssessment` does."""

    __tablename__ = "signal_observations"
    __table_args__ = (
        UniqueConstraint("application_id", "signal_definition_id", name="uq_signal_observation_app_def"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), nullable=False, index=True)
    signal_definition_id: Mapped[int] = mapped_column(
        ForeignKey("signal_definitions.id"), nullable=False, index=True
    )

    status: Mapped[str] = mapped_column(String(16), nullable=False, default="NOT_ASSESSED")
    confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_pattern: Mapped[str | None] = mapped_column(Text, nullable=True)
    origin: Mapped[str] = mapped_column(String(24), nullable=False, default="SYSTEM_GENERATED")
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    overridden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    application: Mapped["Application"] = relationship(back_populates="signal_observations")
    signal_definition: Mapped["SignalDefinition"] = relationship()
    evidence_items: Mapped[list["SignalEvidenceItem"]] = relationship(
        back_populates="signal_observation", cascade="all, delete-orphan", order_by="SignalEvidenceItem.id",
    )


class SignalEvidenceItem(Base):
    """One piece of evidence for one `SignalObservation` — structurally
    identical to Task 3B's `EvidenceItem` (append-only, same source/
    classification/relationship/confidence vocabulary from
    `core/fit_assessment_model.py`), kept as its own table rather than a
    shared/polymorphic one so `EvidenceItem`'s existing NOT NULL
    `requirement_assessment_id` never has to be loosened."""

    __tablename__ = "signal_evidence_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    signal_observation_id: Mapped[int] = mapped_column(
        ForeignKey("signal_observations.id"), nullable=False, index=True
    )

    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_stage: Mapped[str | None] = mapped_column(String(24), nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    evidence_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_classification: Mapped[str] = mapped_column(String(24), nullable=False)
    evidence_relationship: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False, default="UNKNOWN")
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_system_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    signal_observation: Mapped["SignalObservation"] = relationship(back_populates="evidence_items")


class ReviewPriorityPolicy(Base):
    """A named, restaurant-owned policy (concept note §9) that decides HOW
    MUCH a detected Signal affects Review Priority — kept structurally
    separate from `SignalDefinition` (WHAT is detected) so two restaurants
    can use the identical Signal Definition but weigh it differently, and
    so a restaurant can change its own priorities without touching Signal
    detection logic at all."""

    __tablename__ = "review_priority_policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    restaurant_id: Mapped[int | None] = mapped_column(
        ForeignKey("restaurants.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    rules: Mapped[list["ReviewPriorityPolicyRule"]] = relationship(
        back_populates="policy", cascade="all, delete-orphan", order_by="ReviewPriorityPolicyRule.id",
    )


class ReviewPriorityPolicyRule(Base):
    """One rule: for this `SignalDefinition`, observed at this status,
    contribute this QUALITATIVE tier toward Review Priority (concept note
    §9 — never a raw number). Unique per (policy, signal_definition,
    observed_status) so a policy cannot contradict itself for the same
    Signal/status pair."""

    __tablename__ = "review_priority_policy_rules"
    __table_args__ = (
        UniqueConstraint(
            "policy_id", "signal_definition_id", "observed_status", name="uq_priority_rule_policy_def_status"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy_id: Mapped[int] = mapped_column(ForeignKey("review_priority_policies.id"), nullable=False, index=True)
    signal_definition_id: Mapped[int] = mapped_column(
        ForeignKey("signal_definitions.id"), nullable=False, index=True
    )
    observed_status: Mapped[str] = mapped_column(String(16), nullable=False)
    contribution: Mapped[str] = mapped_column(String(24), nullable=False)
    # Task 3C-FIX §4 — a deactivated rule is kept (audit trail) but no
    # longer contributes; `signal_service.compute_and_apply_review_priority`
    # only reads active rules.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    policy: Mapped["ReviewPriorityPolicy"] = relationship(back_populates="rules")
    signal_definition: Mapped["SignalDefinition"] = relationship(back_populates="policy_rules")


class PersonMatchCandidate(Base):
    """A system-suggested POSSIBLE match between a brand-new `CandidatePerson`
    (just created for one incoming Application) and an already-existing
    `CandidatePerson`, produced when identity resolution finds supporting-
    but-inconclusive evidence — a name match without an exact email/phone
    match (Task 3C-FIX §1/§2). Never auto-merged: a Selezionatore must
    explicitly confirm or reject it. Confirming reassigns the Application to
    `suggested_person_id` (see `identity_service.confirm_match`); rejecting
    simply leaves the Application on `source_person_id` — both people stay
    intact either way."""

    __tablename__ = "person_match_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), nullable=False, index=True)
    source_person_id: Mapped[int] = mapped_column(ForeignKey("candidate_persons.id"), nullable=False, index=True)
    suggested_person_id: Mapped[int] = mapped_column(ForeignKey("candidate_persons.id"), nullable=False, index=True)

    confidence: Mapped[str] = mapped_column(String(16), nullable=False)  # STRONG | POSSIBLE
    match_basis: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    application: Mapped["Application"] = relationship()
    source_person: Mapped["CandidatePerson"] = relationship(foreign_keys=[source_person_id])
    suggested_person: Mapped["CandidatePerson"] = relationship(foreign_keys=[suggested_person_id])


class ApplicationNote(Base):
    """One free-form Selezionatore note on an Application (Task 3C-FIX
    §11) — append-only, so notes keep their history instead of overwriting
    each other (unlike the legacy `Application.notes` single-value field
    Task 3C introduced). Deliberately separate from `EvidenceItem`/
    `SignalEvidenceItem`: a note never becomes evidence and never changes a
    Fit Assessment or a Signal Observation on its own.

    Task 5C §33 — `application_id` was widened to nullable and `session_id`
    added so the SAME unified, append-only notes table can also carry a
    Session-level note (Rule Set confirmation, a Rule Change, general
    Session notes) rather than introducing a second notes table (task's own
    "do not create separate note tables unless absolutely necessary").
    Exactly one of `application_id`/`session_id` is set on any given row —
    enforced in the service layer (`session_service.add_session_note`),
    never here. Every pre-5C row keeps `application_id` set exactly as
    before; this widening changes nothing about existing behavior."""

    __tablename__ = "application_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int | None] = mapped_column(ForeignKey("applications.id"), nullable=True, index=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("selection_sessions.id"), nullable=True, index=True)
    note_text: Mapped[str] = mapped_column(Text, nullable=False)
    # Task 3D-FIX §16 — optional source/context tag so notes stay queryable
    # by WHERE in the Selection journey they were entered (e.g. one specific
    # Primary Screening Run or Criterion Evaluation), not just by
    # Application. `None`/`None` (both unset) means a general Application-
    # level note — Task 3C-FIX's original, still-supported behavior. A
    # future Final Selection Decision screen aggregating notes from the
    # whole journey can filter on these two columns directly.
    context_type: Mapped[str | None] = mapped_column(String(48), nullable=True, index=True)
    context_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    # Task 5A-ALIGN §3/§15 — an INFORMATION/EVENT LOG entry (context_type
    # ="INFORMATION_EVENT") reuses this same append-only table rather than
    # a parallel one, but carries its own extra fields so a factual report
    # from staff stays clearly distinguishable from a Selezionatore note or
    # decision: `event_type` (free text — e.g. "CANDIDATE_WITHDRAWAL_CLAIM"),
    # `reported_by` (who entered/reported it into Selection — may differ
    # from who the information came FROM), `original_source` (where the
    # information actually came from — e.g. "phone call from the
    # candidate"), and `stage_at_time` (the Application's Stage when the
    # event was recorded, captured as a plain value since Stage itself is
    # freely mutable and this is a point-in-time fact). All four are
    # nullable and unused by an ordinary note — recording an event NEVER
    # writes to `Application.current_stage`/`lifecycle_state` itself
    # (task's own "information must not automatically change Application
    # state").
    event_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reported_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    original_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    stage_at_time: Mapped[str | None] = mapped_column(String(32), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    application: Mapped["Application | None"] = relationship(back_populates="note_entries")
    session: Mapped["SelectionSession | None"] = relationship()


# ---------------------------------------------------------------------------
# Selection module — Phone Interview framework (TASK 4A)
#
# Begins when an Application reaches ADVANCE_TO_PHONE (Task 3C-FIX §7).
# `PhoneInterviewQuestionDefinition` mirrors `Requirement`/`SignalDefinition`
# exactly (restaurant-configurable Core/Courtesy Questions, never a fixed
# universal script — task §3/§18). `PhoneInterviewPlan` mirrors
# `FitAssessment`'s snapshot-binding discipline: it pins the SAME
# `RequirementSetSnapshot`/`FitAssessment` already used at résumé stage and
# never silently repoints to a newer live Requirement Set (task §1).
# `PhoneInterviewQuestionInstance` mirrors `RequirementAssessment`/
# `SignalObservation`'s "one persisted row per unit, evidence/answer
# enriches it" shape, but a raw interview answer is a live, Selezionatore-
# editable transcript (not append-only evidence) — evidence proper is
# still only ever added via `fit_assessment_service.add_evidence()`/
# `signal_service.add_evidence()` (task §14/§15 — no parallel evidence
# system). Post-Phone-Interview decisions reuse `Application.workflow_status`
# (`core/application_model.ADVANCE_TO_IN_PERSON`/HOLD/STOP, task §22) rather
# than a second, parallel decision field.
# ---------------------------------------------------------------------------


class PhoneInterviewQuestionDefinition(Base):
    """One restaurant-configured Core (or Courtesy) Question (task §3) —
    mirrors `Requirement`'s shape closely (restaurant/role scoping, active/
    version, display order). `is_courtesy=True` marks a short, professional-
    closing question a restaurant has prepared for the Escape Route (task
    §7) rather than an ordinary Core Question; both live in the same table
    since they are structurally identical configuration data, distinguished
    only by how `phone_interview_service.py` uses them. `linked_requirement_ids`/
    `linked_signal_definition_ids` reference LIVE `Requirement`/
    `SignalDefinition` rows (this Definition is authored once and reused
    across many Requirement Set versions over time, unlike a Question
    INSTANCE below, which is always resolved against one immutable
    snapshot)."""

    __tablename__ = "phone_interview_question_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    restaurant_id: Mapped[int | None] = mapped_column(
        ForeignKey("restaurants.id"), nullable=True, index=True
    )
    target_role: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    objective: Mapped[str | None] = mapped_column(Text, nullable=True)
    linked_requirement_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    linked_signal_definition_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    importance: Mapped[str] = mapped_column(String(16), nullable=False, default="MEDIUM")
    is_sine_qua_non: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    mandatory_within_selection_process: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    assessment_stages: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    follow_up_guidance: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_courtesy: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )


class PhoneInterviewPlan(Base):
    """One Application's Phone Interview (task §1) — pinned to the SAME
    immutable `RequirementSetSnapshot`/`FitAssessment` already used at
    résumé stage; never silently repointed to a newer live Requirement Set.
    `person_id`/`candidate_id`/`restaurant_id` are denormalized copies of
    `application.person_id`/`.candidate_id`/`.restaurant_id`, kept only for
    convenient navigation/scoping (same convention `FitAssessment.
    requirement_set_id` already uses) — `application_id` alone is
    authoritative. `status` is the INTERVIEW PROCESS status only
    (`core/phone_interview_model.py` — NOT_STARTED/IN_PROGRESS/
    ESCAPE_ROUTE/COMPLETED/STOPPED_EARLY); the post-interview
    ADVANCE_TO_IN_PERSON/HOLD/STOP DECISION is recorded on `Application.
    workflow_status` instead (task §21's own "do not confuse this with
    Application workflow status")."""

    __tablename__ = "phone_interview_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id"), nullable=False, unique=True, index=True
    )
    person_id: Mapped[int] = mapped_column(ForeignKey("candidate_persons.id"), nullable=False, index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False, index=True)
    restaurant_id: Mapped[int | None] = mapped_column(
        ForeignKey("restaurants.id"), nullable=True, index=True
    )
    requirement_set_snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("requirement_set_snapshots.id"), nullable=False, index=True
    )
    fit_assessment_id: Mapped[int] = mapped_column(ForeignKey("fit_assessments.id"), nullable=False, index=True)

    status: Mapped[str] = mapped_column(String(24), nullable=False, default="NOT_STARTED")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)  # Selezionatore note — never evidence.

    escape_route_activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    escape_route_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    application: Mapped["Application"] = relationship()
    person: Mapped["CandidatePerson"] = relationship()
    candidate: Mapped["Candidate"] = relationship()
    requirement_set_snapshot: Mapped["RequirementSetSnapshot"] = relationship()
    fit_assessment: Mapped["FitAssessment"] = relationship()
    question_instances: Mapped[list["PhoneInterviewQuestionInstance"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan", order_by="PhoneInterviewQuestionInstance.display_order",
    )


class PhoneInterviewQuestionInstance(Base):
    """One question actually placed into one `PhoneInterviewPlan` (task
    §9) — CORE/DYNAMIC/COURTESY/FOLLOW_UP, always a copy-by-value of its
    text/objective/importance at the moment it entered the plan (so a later
    edit to a live `PhoneInterviewQuestionDefinition` never rewrites
    history — the same immutability discipline `RequirementSnapshotItem`
    established for Requirements). `source_question_definition_id` is
    deliberately NOT a foreign key, exactly like `RequirementSnapshotItem.
    source_requirement_id` — this row must stay completely valid even if the
    live Definition it came from is later edited or deactivated.
    `linked_requirement_ids` here point to `RequirementSnapshotItem` rows
    (this plan's own pinned snapshot), not live `Requirement` rows.

    The raw `answer_text`/`selezionatore_note` are a live, Selezionatore-
    editable transcript — NOT append-only evidence (task §13: "keep raw
    response and interpretation separate"). Turning an answer into Fit
    Assessment/Signal evidence is a separate, explicit action
    (`phone_interview_service.record_answer_as_evidence`) that calls
    `fit_assessment_service.add_evidence()`/`signal_service.add_evidence()`
    directly — no parallel evidence table is introduced here."""

    __tablename__ = "phone_interview_question_instances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("phone_interview_plans.id"), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    source_question_definition_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parent_question_instance_id: Mapped[int | None] = mapped_column(
        ForeignKey("phone_interview_question_instances.id"), nullable=True, index=True
    )

    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    objective: Mapped[str | None] = mapped_column(Text, nullable=True)
    linked_requirement_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    linked_signal_definition_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    importance: Mapped[str] = mapped_column(String(16), nullable=False, default="MEDIUM")
    is_sine_qua_non: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    mandatory_within_selection_process: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reason_for_inclusion: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(24), nullable=False, default="NOT_ASKED")
    gate_evaluation: Mapped[str | None] = mapped_column(String(16), nullable=True)
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    selezionatore_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    carried_forward_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    asked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    plan: Mapped["PhoneInterviewPlan"] = relationship(back_populates="question_instances")
    follow_ups: Mapped[list["PhoneInterviewQuestionInstance"]] = relationship(
        back_populates="parent_question", cascade="all, delete-orphan",
    )
    parent_question: Mapped["PhoneInterviewQuestionInstance | None"] = relationship(
        remote_side=[id], back_populates="follow_ups",
    )


# ---------------------------------------------------------------------------
# Selection module — In-Person Interview + Practical Assessment +
# Consistency Engine (TASK 4B)
#
# `InPersonInterviewSectionDefinition`/`AssessmentItemDefinition` mirror
# `PhoneInterviewQuestionDefinition` exactly (restaurant-configurable,
# never a fixed universal sequence — task §2/§24). `InPersonInterviewPlan`
# mirrors `PhoneInterviewPlan`'s snapshot-binding discipline, additionally
# linking the Phone Interview Plan where one exists (task §1).
# `AssessmentItemInstance` is ONE unified, copy-by-value table serving
# every item type (QUESTION/OBSERVATION/PRACTICAL_TEST/ROLE_PLAY/
# CONSISTENCY_CHECK/CARRY_FORWARD/COURTESY) — the same "one instance table
# per plan, not one per item type" simplification
# `PhoneInterviewQuestionInstance` already established, since a Practical
# Test's "response/performance notes" and a Question's "answer" are the
# same RAW INPUT concept the task's own §16 groups together.
# `ConsistencyThread`/`ConsistencyStatement` are new: a thread compares one
# topic across multiple SOURCES (never rewriting an original statement —
# task §10/§16), and never carries an automatic dishonesty label (task
# §12) — only a neutral comparison status plus explanation text.
# ---------------------------------------------------------------------------


class InPersonInterviewSectionDefinition(Base):
    """One restaurant-configured In-Person Interview section (task §2) —
    e.g. "Work Personality." Mirrors `RequirementSet`'s restaurant-owned,
    independently reorderable shape; `section_kind` is an optional tag
    (`core/in_person_interview_model.SECTION_KINDS`) used only to trigger
    the two behaviorally special sections (automatic Phone carry-forward
    population into a CARRY_FORWARD-kind section; the Final Observation
    phase's "never automatic evidence" rule) — RF-One never assumes a
    section exists just because its kind is referenced."""

    __tablename__ = "in_person_interview_section_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    restaurant_id: Mapped[int | None] = mapped_column(
        ForeignKey("restaurants.id"), nullable=True, index=True
    )
    target_role: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    section_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="OTHER")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    items: Mapped[list["AssessmentItemDefinition"]] = relationship(
        back_populates="section", cascade="all, delete-orphan", order_by="AssessmentItemDefinition.display_order",
    )


class AssessmentItemDefinition(Base):
    """One restaurant-configured Assessment Item inside a Section (task
    §3/§24) — a Question, Observation, Practical Test, Role-Play, or
    Courtesy prompt. `linked_requirement_ids`/`linked_signal_definition_ids`
    reference LIVE `Requirement`/`SignalDefinition` rows, exactly like
    `PhoneInterviewQuestionDefinition` — resolved against a specific plan's
    own immutable snapshot only when copied into an `AssessmentItemInstance`."""

    __tablename__ = "assessment_item_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    section_id: Mapped[int] = mapped_column(
        ForeignKey("in_person_interview_section_definitions.id"), nullable=False, index=True
    )

    item_type: Mapped[str] = mapped_column(String(24), nullable=False)
    title_or_question: Mapped[str] = mapped_column(Text, nullable=False)
    instruction: Mapped[str | None] = mapped_column(Text, nullable=True)  # e.g. instructions TO the candidate.
    scenario: Mapped[str | None] = mapped_column(Text, nullable=True)  # Practical Test / Role-Play scenario text.
    objective: Mapped[str | None] = mapped_column(Text, nullable=True)
    linked_requirement_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    linked_signal_definition_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    importance: Mapped[str] = mapped_column(String(16), nullable=False, default="MEDIUM")
    mandatory_within_selection_process: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    evidence_expected: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_positive: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_contrary: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_insufficient: Mapped[str | None] = mapped_column(Text, nullable=True)
    selezionatore_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)  # What to observe/how to run it.

    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    section: Mapped["InPersonInterviewSectionDefinition"] = relationship(back_populates="items")


class InPersonInterviewPlan(Base):
    """One Application's In-Person Interview (task §1) — pinned to the SAME
    immutable `RequirementSetSnapshot`/`FitAssessment` the existing Fit
    Assessment (and, where one exists, the Phone Interview Plan) already
    use; never repointed to a newer live Requirement Set.
    `phone_interview_plan_id` is nullable — an In-Person Interview is not
    required to follow a Phone Interview in every deployment, but where one
    exists its unresolved items are carried forward automatically (task
    §4)."""

    __tablename__ = "in_person_interview_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id"), nullable=False, unique=True, index=True
    )
    person_id: Mapped[int] = mapped_column(ForeignKey("candidate_persons.id"), nullable=False, index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False, index=True)
    restaurant_id: Mapped[int | None] = mapped_column(
        ForeignKey("restaurants.id"), nullable=True, index=True
    )
    requirement_set_snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("requirement_set_snapshots.id"), nullable=False, index=True
    )
    fit_assessment_id: Mapped[int] = mapped_column(ForeignKey("fit_assessments.id"), nullable=False, index=True)
    phone_interview_plan_id: Mapped[int | None] = mapped_column(
        ForeignKey("phone_interview_plans.id"), nullable=True, index=True
    )

    status: Mapped[str] = mapped_column(String(24), nullable=False, default="NOT_STARTED")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)  # Selezionatore note — never evidence.

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    application: Mapped["Application"] = relationship()
    person: Mapped["CandidatePerson"] = relationship()
    candidate: Mapped["Candidate"] = relationship()
    requirement_set_snapshot: Mapped["RequirementSetSnapshot"] = relationship()
    fit_assessment: Mapped["FitAssessment"] = relationship()
    phone_interview_plan: Mapped["PhoneInterviewPlan | None"] = relationship()
    item_instances: Mapped[list["AssessmentItemInstance"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan", order_by="AssessmentItemInstance.display_order",
    )


class AssessmentItemInstance(Base):
    """One Assessment Item actually placed into one `InPersonInterviewPlan`
    (task §3/§9) — a single, unified table serving every item type,
    mirroring `PhoneInterviewQuestionInstance`'s own "one instance shape for
    every source type" simplification. Copy-by-value of its text/objective/
    importance at the moment it entered the plan (so a later edit to a live
    `AssessmentItemDefinition` never rewrites history).
    `source_item_definition_id` is deliberately NOT a foreign key, exactly
    like `PhoneInterviewQuestionInstance.source_question_definition_id`.

    `raw_response` is the RAW INPUT (task §16) — a candidate's answer, a
    Selezionatore's direct observation, or a practical-test performance
    note, depending on `source_type`; never rewritten once entered.
    `selezionatore_note` is the separate INTERPRETATION layer. Turning
    either into Fit Assessment/Signal evidence is a distinct, explicit
    action (`in_person_interview_service.record_response_as_*_evidence`)."""

    __tablename__ = "assessment_item_instances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("in_person_interview_plans.id"), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(24), nullable=False)
    source_item_definition_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_phone_question_instance_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    consistency_thread_id: Mapped[int | None] = mapped_column(
        ForeignKey("consistency_threads.id"), nullable=True, index=True
    )

    section_name: Mapped[str] = mapped_column(String(255), nullable=False)
    section_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="OTHER")
    section_display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    title_or_question: Mapped[str] = mapped_column(Text, nullable=False)
    instruction: Mapped[str | None] = mapped_column(Text, nullable=True)
    scenario: Mapped[str | None] = mapped_column(Text, nullable=True)
    objective: Mapped[str | None] = mapped_column(Text, nullable=True)
    linked_requirement_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    linked_signal_definition_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    importance: Mapped[str] = mapped_column(String(16), nullable=False, default="MEDIUM")
    mandatory_within_selection_process: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    selezionatore_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reason_for_inclusion: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(24), nullable=False, default="NOT_DONE")
    raw_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    selezionatore_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    plan: Mapped["InPersonInterviewPlan"] = relationship(back_populates="item_instances")
    consistency_thread: Mapped["ConsistencyThread | None"] = relationship()


class ConsistencyThread(Base):
    """One topic compared across multiple sources for one Application
    (task §8/§9) — CV/Application, prior Applications, Phone Interview,
    In-Person Interview, Practical Assessment, or Selezionatore-entered
    evidence. Scoped to the Application (not to one specific interview
    plan) since consistency spans the whole selection process. A
    contradiction found here is EVIDENCE, never automatic proof of
    dishonesty (task §12) — `comparison_status` is always one of the
    neutral `core/in_person_interview_model.CONSISTENCY_STATUSES`, and
    `explanation` must always be a plain factual description (task's own
    example: "Material inconsistency detected between Phone Interview and
    In-Person response regarding reason for leaving previous employment.") —
    never a psychological or legal conclusion."""

    __tablename__ = "consistency_threads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), nullable=False, index=True)

    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    importance: Mapped[str] = mapped_column(String(16), nullable=False, default="MEDIUM")
    comparison_status: Mapped[str] = mapped_column(String(24), nullable=False, default="UNRESOLVED")
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)
    selezionatore_resolution: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    application: Mapped["Application"] = relationship()
    statements: Mapped[list["ConsistencyStatement"]] = relationship(
        back_populates="thread", cascade="all, delete-orphan", order_by="ConsistencyStatement.id",
    )


class ConsistencyStatement(Base):
    """One source statement/evidence item feeding a `ConsistencyThread`
    (task §10) — append-only (no `updated_at`), so an original statement is
    never destroyed or rewritten (task's own explicit requirement) even
    after the thread's `comparison_status` changes (e.g. to
    EXPLAINED_DIFFERENCE)."""

    __tablename__ = "consistency_statements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thread_id: Mapped[int] = mapped_column(ForeignKey("consistency_threads.id"), nullable=False, index=True)

    source_stage: Mapped[str] = mapped_column(String(24), nullable=False)
    source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_statement: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_interpretation: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    thread: Mapped["ConsistencyThread"] = relationship(back_populates="statements")


# ---------------------------------------------------------------------------
# Selection module — Primary Screening Engine (TASK 3D)
#
# A much stronger, restaurant-configurable early-stage filter sitting
# BEFORE Phone Interview (concept: 200 Applications -> aggressive Primary
# Screening -> ~15-20 worth deeper attention -> Phone -> In-Person ->
# Final Selection Decision). `PrimaryScreeningCriterion` mirrors
# `Requirement`/`SignalDefinition` exactly (restaurant-configurable, never
# a fixed universal list — task §1/§10). `PrimaryScreeningCriterionSnapshot`
# mirrors `RequirementSnapshotItem`'s immutability discipline at the single-
# Criterion granularity (there is no natural "Set" grouping here, unlike
# Requirements). `PrimaryScreeningRun` + `PrimaryScreeningCriterionEvaluation`
# mirror `FitAssessment`/`RequirementAssessment`'s "one persisted row per
# unit, evidence enriches it, system vs effective, never silently level 0"
# shape — multiple runs may exist per Application over time (never unique,
# unlike the 1:1 Phone/In-Person Plans), each pinned to its own exact
# Criterion configuration snapshot, so a later restaurant edit never
# silently rewrites a historical screening result (task §16).
# ---------------------------------------------------------------------------


class PrimaryScreeningCriterion(Base):
    """One restaurant-configured Primary Screening Criterion (task §1) —
    RF-One supplies the structure (0-4 level scale, direction, coefficient,
    Hard Disqualifier mechanics); the restaurant supplies WHAT the
    Criterion is, WHAT each level 0-4 means for it, and HOW important it
    is. Never a fixed universal list (task §10) and never seeded with a
    protected personal characteristic (task §27). `level_descriptions` is
    a JSON object keyed by level string ("0".."4") -> restaurant-authored
    meaning text (task §2) — RF-One never invents a universal meaning for
    any level. `auto_evaluation_signal_definition_id`/
    `auto_evaluation_level_map` are an OPTIONAL, fully restaurant-configured
    deterministic shortcut (task §12/§18's "aggressive screening" need):
    when set, a Criterion Evaluation can be auto-populated straight from an
    existing Selection Signal Observation's status through the
    restaurant's OWN status->level mapping — mirroring
    `ReviewPriorityPolicyRule`'s exact "restaurant maps a known status to a
    restaurant-chosen outcome" pattern; RF-One still never invents what a
    level means or which status deserves it."""

    __tablename__ = "primary_screening_criteria"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    restaurant_id: Mapped[int | None] = mapped_column(
        ForeignKey("restaurants.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_role: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    location_label: Mapped[str | None] = mapped_column(String(255), nullable=True)

    coefficient: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    direction: Mapped[str] = mapped_column(String(16), nullable=False, default="POSITIVE")
    is_hard_disqualifier: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    hard_disqualifier_trigger_level: Mapped[int | None] = mapped_column(Integer, nullable=True)

    level_descriptions: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    evidence_sources_allowed: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evaluation_guidance: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_positive: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_contrary: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_insufficient: Mapped[str | None] = mapped_column(Text, nullable=True)

    auto_evaluation_signal_definition_id: Mapped[int | None] = mapped_column(
        ForeignKey("signal_definitions.id"), nullable=True
    )
    auto_evaluation_level_map: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Task 5E §21/§22/§28 — three minimal, additive fields (never a
    # redesign of the existing Criticality/coefficient/evidence_sources_
    # allowed shape above, which already carries Importance and Stage-
    # Reliability respectively). `required_for_phone_review` marks WHICH
    # Criteria's resolution is required before an Application may reach
    # READY_FOR_PHONE_REVIEW (task §28) — never every Criterion, only the
    # ones this restaurant flags. `missing_evidence_question_text`/
    # `missing_evidence_answer_level_map` are the OPTIONAL restaurant-
    # authored question/answer-mapping `missing_evidence_service.py` uses
    # when this Criterion is the reason a Missing-Evidence Questionnaire is
    # generated — mirrors `auto_evaluation_signal_definition_id`/
    # `auto_evaluation_level_map`'s own "restaurant maps a known input to a
    # restaurant-chosen level" pattern exactly, never an RF-One-invented
    # meaning.
    required_for_phone_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    missing_evidence_question_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    missing_evidence_answer_level_map: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    auto_evaluation_signal_definition: Mapped["SignalDefinition | None"] = relationship()


class PrimaryScreeningCriterionSnapshot(Base):
    """An IMMUTABLE, point-in-time copy of one `PrimaryScreeningCriterion`
    (task §16) — mirrors `RequirementSnapshotItem`'s own immutability
    discipline. `(criterion_id, version)` is unique — capturing again
    before the live Criterion's version has advanced returns the existing
    snapshot rather than an unnecessary duplicate (same idempotent-per-
    version rule `requirements_service.create_requirement_set_snapshot()`
    already established)."""

    __tablename__ = "primary_screening_criterion_snapshots"
    __table_args__ = (
        UniqueConstraint("criterion_id", "version", name="uq_primary_screening_criterion_snapshot_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    criterion_id: Mapped[int] = mapped_column(
        ForeignKey("primary_screening_criteria.id"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    restaurant_id: Mapped[int | None] = mapped_column(nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    location_label: Mapped[str | None] = mapped_column(String(255), nullable=True)

    coefficient: Mapped[float] = mapped_column(Float, nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    is_hard_disqualifier: Mapped[bool] = mapped_column(Boolean, nullable=False)
    hard_disqualifier_trigger_level: Mapped[int | None] = mapped_column(Integer, nullable=True)

    level_descriptions: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    evidence_sources_allowed: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evaluation_guidance: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_positive: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_contrary: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_insufficient: Mapped[str | None] = mapped_column(Text, nullable=True)

    auto_evaluation_signal_definition_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    auto_evaluation_level_map: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    required_for_phone_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    missing_evidence_question_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    missing_evidence_answer_level_map: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    was_active: Mapped[bool] = mapped_column(Boolean, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    criterion: Mapped["PrimaryScreeningCriterion"] = relationship()


class PrimaryScreeningRun(Base):
    """One Primary Screening pass over one Application (task §17) —
    binds a snapshot-frozen set of Criterion Evaluations together with the
    resulting INTERNAL `priority_index` (never exposed to the
    Selezionatore — task §5/§17), whether an active, un-overridden Hard
    Disqualifier is present, and a plain-language `explanation`. Multiple
    runs may exist for the same Application over time (never unique,
    unlike the 1:1 Phone/In-Person Interview Plans) — each stays tied to
    the exact Criterion configuration used (task §16); the most recent one
    is what the Primary Screening Queue displays."""

    __tablename__ = "primary_screening_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), nullable=False, index=True)
    restaurant_id: Mapped[int | None] = mapped_column(
        ForeignKey("restaurants.id"), nullable=True, index=True
    )

    priority_index: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    has_active_hard_disqualifier: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    application: Mapped["Application"] = relationship()
    evaluations: Mapped[list["PrimaryScreeningCriterionEvaluation"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="PrimaryScreeningCriterionEvaluation.id",
    )


class PrimaryScreeningCriterionEvaluation(Base):
    """One (Run, Criterion Snapshot) unit (task §13) — the Primary
    Screening counterpart of `RequirementAssessment`. `system_level` is
    whatever the (optional, restaurant-configured) automatic Signal-based
    evaluation last computed; `effective_level` is what actually feeds the
    Priority Index — a human override never silently gets recalculated
    away, mirroring `RequirementAssessment.system_status`/
    `.effective_status` exactly. An unresolved/uncertain Criterion is
    NEVER silently coerced to level 0 (task §14) — `status` says so
    explicitly, and `NON_CONTRIBUTING_STATUSES` are excluded from the
    Priority Index."""

    __tablename__ = "primary_screening_criterion_evaluations"
    __table_args__ = (
        UniqueConstraint(
            "run_id", "criterion_snapshot_id", name="uq_primary_screening_evaluation_run_snapshot"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("primary_screening_runs.id"), nullable=False, index=True)
    criterion_snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("primary_screening_criterion_snapshots.id"), nullable=False, index=True
    )

    status: Mapped[str] = mapped_column(String(24), nullable=False, default="NOT_EVALUATED")
    system_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    effective_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)
    evidence_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    evidence_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Task 3D-FIX §3/§4/§7 — the structured evidence list a generic/AI-
    # assisted evaluation is grounded in: `[{"source_type", "source_reference",
    # "evidence_text", "interpretation"}, ...]`. `evidence_source`/
    # `evidence_text` above stay populated too (a single-source summary) for
    # backward compatibility with Task 3D's deterministic Signal-mapping
    # path, which never populates this list.
    evidence_items: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    origin: Mapped[str] = mapped_column(String(24), nullable=False, default="SYSTEM_GENERATED")
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    overridden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    contribution: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    is_active_hard_disqualifier: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    hard_disqualifier_overridden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    hard_disqualifier_override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    hard_disqualifier_overridden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    run: Mapped["PrimaryScreeningRun"] = relationship(back_populates="evaluations")
    criterion_snapshot: Mapped["PrimaryScreeningCriterionSnapshot"] = relationship()


# ---------------------------------------------------------------------------
# Selection module — Outcome + Stage + Decision History Engine (TASK 5A)
#
# Deliberately separates three concepts the pre-5A codebase only partly
# distinguished: STAGE (`ApplicationStageTransition` + `Application.
# current_stage` — where the Application currently is, no enforced order),
# OUTCOME (`SelectionOutcomeDefinition`/`.Snapshot`/`SelectionOutcomeDecision`
# — the restaurant-configured operational decision, applicable at any time,
# never technically irreversible), and CANDIDATE FLAG (`CandidateFlag` — a
# person-level, never-auto-rejecting marker an Outcome may create). Mirrors
# established patterns throughout this file: `PrimaryScreeningCriterion`/
# `.Snapshot`'s restaurant-configurable/immutable-snapshot split, and
# `SignalObservation`'s append-only-history-with-one-current-pointer shape.
#
# `Application.workflow_status` (Task 3C-FIX/4A) is UNCHANGED and remains
# fully functional — see `selection_validation.py`'s Task 5A checks and the
# Task 5A report for exactly how the two coexist (workflow_status is not
# migrated into this new model; it continues to work exactly as before).
# ---------------------------------------------------------------------------


class ApplicationStageTransition(Base):
    """One Stage movement (task §3) — append-only; a Stage change NEVER
    overwrites a prior transition. `previous_stage` is `None` only for the
    very first transition a brand-new Application would get if one is ever
    recorded (most Applications simply start at `Application.
    current_stage`'s default without an explicit first transition row —
    this table records CHANGES, not the initial state). No "allowed next
    Stage" validation exists here or in `stage_service.py` — the
    Selezionatore has total freedom to move forward, backward, repeat, or
    skip (task §2)."""

    __tablename__ = "application_stage_transitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), nullable=False, index=True)
    previous_stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    new_stage: Mapped[str] = mapped_column(String(32), nullable=False)
    # No user/auth system exists in Selection (task §15 — Selection actions
    # belong to authorized Selection users, but no RBAC redesign is in
    # scope) — this is an honest, optional free-text field ready for a
    # future auth integration, never a fabricated user identity.
    performed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # GLOBAL_INTEGRITY_FIX_002 / C-1: authoritative actor reference for new
    # Stage transitions (explicitly a priority record per that fix's task
    # §10), resolved server-side; `performed_by` stays as display text /
    # historical fallback for rows created before this task.
    performed_by_identity_id: Mapped[int | None] = mapped_column(
        ForeignKey("acting_identities.id"), nullable=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    application: Mapped["Application"] = relationship(back_populates="stage_transitions")
    performed_by_identity: Mapped["ActingIdentity | None"] = relationship()


class SelectionOutcomeDefinition(Base):
    """A restaurant-configurable Selection Outcome (task §4/§5) — mirrors
    `PrimaryScreeningCriterion`'s shape closely (restaurant-owned,
    active/version, immutable snapshot below) since an Outcome Definition
    is structurally the same kind of "restaurant configures what this
    means and what it does" object. RF-One seeds a few examples (ACTIVE,
    HIRE, HOLD, STOP, WITHDRAWN — `industry/restaurant_templates.py`) but
    these are ordinary rows a restaurant can edit or ignore, never a fixed
    universal set (task §4's own "templates/default configuration, not the
    complete universal set").

    Fields correspond directly to the task §5/§6/§11 wizard questions —
    see `outcome_service.py`'s docstring for how each one is EXECUTED when
    the Outcome is applied to an Application."""

    __tablename__ = "selection_outcome_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    restaurant_id: Mapped[int | None] = mapped_column(ForeignKey("restaurants.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)  # conversational, task §5

    lifecycle_effect: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")  # task §6
    is_reopenable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)  # task §5/§7

    requires_note: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    requires_reason: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reason_choices: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Task 5A-FIX §7/§10/§15 — `target_queue_label` (above) is now LEGACY
    # display-only text, kept for backward compatibility with any Outcome
    # authored before this fix. `target_queue_id` is the OPERATIONAL
    # reference: when set, applying this Outcome actually moves the
    # Application into that configured queue (see `outcome_service.
    # apply_outcome`/`queue_service.move_to_queue`) — mirrors
    # `auto_evaluation_signal_definition_id`'s live-FK pattern on
    # `PrimaryScreeningCriterion`.
    target_queue_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_queue_id: Mapped[int | None] = mapped_column(ForeignKey("selection_queues.id"), nullable=True, index=True)

    creates_reminder: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reminder_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    future_contact_policy: Mapped[str] = mapped_column(String(16), nullable=False, default="ALLOWED")

    creates_candidate_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    candidate_flag_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    candidate_flag_scope: Mapped[str | None] = mapped_column(String(32), nullable=True)
    candidate_flag_operational_effect: Mapped[str | None] = mapped_column(String(24), nullable=True)
    candidate_flag_default_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    candidate_flag_expires_after_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Task 5A-ALIGN §14 — two informational, unenforced wizard fields (no
    # RBAC/authentication system exists in Selection to enforce either one
    # — same honest-placeholder rationale as `performed_by` throughout this
    # module): `authority_label` names WHO is expected to apply this
    # Outcome (e.g. "Selezionatore", "Trainer" — task §11's "the Trainer,
    # not the Selezionatore, is the authority for the Training Check
    # result"); `driven_by` records whether the Outcome is normally
    # RESTAURANT-initiated, CANDIDATE-initiated, or EITHER.
    authority_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    driven_by: Mapped[str | None] = mapped_column(String(24), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    target_queue: Mapped["SelectionQueue | None"] = relationship()


class SelectionOutcomeDefinitionSnapshot(Base):
    """Immutable, point-in-time copy of an Outcome Definition (task §28) —
    mirrors `PrimaryScreeningCriterionSnapshot`'s exact idempotent-per-
    version discipline (`outcome_service.get_or_create_outcome_definition_
    snapshot`). Every `SelectionOutcomeDecision` pins to one of these, never
    to the live, still-editable `SelectionOutcomeDefinition` row — a later
    edit to the live Outcome never rewrites what a historical decision
    meant at the moment it was made."""

    __tablename__ = "selection_outcome_definition_snapshots"
    __table_args__ = (
        UniqueConstraint("definition_id", "version", name="uq_outcome_definition_snapshot_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    definition_id: Mapped[int] = mapped_column(ForeignKey("selection_outcome_definitions.id"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    restaurant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    lifecycle_effect: Mapped[str] = mapped_column(String(16), nullable=False)
    is_reopenable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    requires_note: Mapped[bool] = mapped_column(Boolean, nullable=False)
    requires_reason: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason_choices: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    target_queue_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Deliberately NOT a foreign key (mirrors `auto_evaluation_signal_
    # definition_id` on `PrimaryScreeningCriterionSnapshot`) — this row
    # must stay completely valid even if the live Queue it referenced is
    # later renamed or deactivated (task §Y: a later Outcome Definition
    # edit must never rewrite a historical queue movement's meaning).
    target_queue_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    creates_reminder: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reminder_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    future_contact_policy: Mapped[str] = mapped_column(String(16), nullable=False)
    creates_candidate_flag: Mapped[bool] = mapped_column(Boolean, nullable=False)
    candidate_flag_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    candidate_flag_scope: Mapped[str | None] = mapped_column(String(32), nullable=True)
    candidate_flag_operational_effect: Mapped[str | None] = mapped_column(String(24), nullable=True)
    candidate_flag_default_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    candidate_flag_expires_after_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    authority_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    driven_by: Mapped[str | None] = mapped_column(String(24), nullable=True)
    was_active: Mapped[bool] = mapped_column(Boolean, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    definition: Mapped["SelectionOutcomeDefinition"] = relationship()


class SelectionOutcomeDecision(Base):
    """One Outcome application to one Application (task §8/§9) — the
    append-only Decision History. `Application.lifecycle_state` mirrors
    this row's snapshot `lifecycle_effect` for convenience only; the
    CURRENT effective Outcome is always derivable as the most recent
    (highest-`id`) decision for an Application (mirrors `PrimaryScreeningRun`'s
    own "most recent by id, no stored pointer needed" convention). A
    decision is never edited or deleted — reopening or changing the Outcome
    again always APPENDS a new decision (task §26)."""

    __tablename__ = "selection_outcome_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), nullable=False, index=True)
    outcome_definition_snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("selection_outcome_definition_snapshots.id"), nullable=False, index=True
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # True when this decision reopens an Application that was CLOSED/
    # SUSPENDED immediately beforehand (task §7 — "reopening creates NEW
    # history," never erasing the prior closure).
    is_reopen_event: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    performed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # GLOBAL_INTEGRITY_FIX_002 / C-1: authoritative actor reference for new
    # Outcome Decisions (explicitly a priority record per that fix's task
    # §10), resolved server-side; `performed_by` stays as display text /
    # historical fallback for rows created before this task.
    performed_by_identity_id: Mapped[int | None] = mapped_column(
        ForeignKey("acting_identities.id"), nullable=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    application: Mapped["Application"] = relationship(back_populates="outcome_decisions")
    outcome_definition_snapshot: Mapped["SelectionOutcomeDefinitionSnapshot"] = relationship()
    performed_by_identity: Mapped["ActingIdentity | None"] = relationship()


class SelectionReminder(Base):
    """A lightweight follow-up record an Outcome's `creates_reminder`
    configuration may generate (task §5/§11) — deliberately minimal (no
    notification/scheduling engine, task §14's "no separate Event Engine"
    spirit applied here too): a due date and a note, visible on the
    Decision Summary, that a Selezionatore can mark resolved."""

    __tablename__ = "selection_reminders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), nullable=False, index=True)
    outcome_decision_id: Mapped[int | None] = mapped_column(
        ForeignKey("selection_outcome_decisions.id"), nullable=True, index=True
    )
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    application: Mapped["Application"] = relationship()
    outcome_decision: Mapped["SelectionOutcomeDecision | None"] = relationship()


class CandidateFlag(Base):
    """A persistent, person-level marker (task §16) — e.g. "DO NOT REHIRE,"
    "RECONSIDER AFTER 6 MONTHS," "NOT FOR SERVER ROLE," "PREVIOUS STRONG
    CANDIDATE." Follows the `CandidatePerson`, not one Application, since
    its whole purpose is surfacing on a LATER Application by the same
    person (task §19). Never causes an automatic rejection (task §18/§28)
    — `operational_effect` caps out at OPERATIONAL_ACTION, defined as
    "requires Selezionatore attention," never "reject automatically."
    History is preserved by never deleting a flag row — `is_active`/
    `expires_at` describe CURRENT state; the row's existence, its original
    `reason`/`note`/`created_at`, are the permanent historical fact that it
    was created (task §29)."""

    __tablename__ = "candidate_flags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("candidate_persons.id"), nullable=False, index=True)
    restaurant_id: Mapped[int | None] = mapped_column(ForeignKey("restaurants.id"), nullable=True, index=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    originating_application_id: Mapped[int | None] = mapped_column(
        ForeignKey("applications.id"), nullable=True, index=True
    )
    originating_outcome_decision_id: Mapped[int | None] = mapped_column(
        ForeignKey("selection_outcome_decisions.id"), nullable=True, index=True
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    scope: Mapped[str] = mapped_column(String(32), nullable=False, default="INFORMATIONAL")
    role_scope: Mapped[str | None] = mapped_column(String(64), nullable=True)
    location_scope: Mapped[str | None] = mapped_column(String(255), nullable=True)
    operational_effect: Mapped[str] = mapped_column(String(24), nullable=False, default="INFORMATION_ONLY")

    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    start_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    person: Mapped["CandidatePerson"] = relationship(back_populates="flags")
    originating_application: Mapped["Application | None"] = relationship()
    originating_outcome_decision: Mapped["SelectionOutcomeDecision | None"] = relationship()


class SelectionQueue(Base):
    """A restaurant-configurable, PURELY ORGANIZATIONAL operational
    queue/list (Task 5A-FIX §7/§8) — e.g. "Active Review," "Call Later,"
    "Hold," "Reconsider," "Hired," "Closed." These are EXAMPLES only, never
    a fixed universal set — a restaurant creates and names its own.
    Deliberately minimal (name/description/active/display_order only) —
    this is NOT a general-purpose workflow engine, and queue placement is
    never itself a hiring decision (task §14): it only ever changes because
    the Selezionatore moved the Application there directly, or because an
    Outcome they chose was configured to do so."""

    __tablename__ = "selection_queues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    restaurant_id: Mapped[int | None] = mapped_column(ForeignKey("restaurants.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )


class ApplicationQueueMovement(Base):
    """One actual queue/list move (Task 5A-FIX §9) — append-only, exactly
    like `ApplicationStageTransition`; a move never overwrites a prior one.
    `source` (`core/queue_model.py` — MANUAL/OUTCOME_ACTION) distinguishes
    a direct Selezionatore move from one an applied Outcome triggered;
    `originating_outcome_decision_id` is set only for the latter, so the
    Outcome that caused a move stays traceable without making queue
    placement itself a decision source (task §14)."""

    __tablename__ = "application_queue_movements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), nullable=False, index=True)
    previous_queue_id: Mapped[int | None] = mapped_column(ForeignKey("selection_queues.id"), nullable=True)
    new_queue_id: Mapped[int | None] = mapped_column(ForeignKey("selection_queues.id"), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="MANUAL")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    originating_outcome_decision_id: Mapped[int | None] = mapped_column(
        ForeignKey("selection_outcome_decisions.id"), nullable=True, index=True
    )
    performed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    application: Mapped["Application"] = relationship(back_populates="queue_movements")
    previous_queue: Mapped["SelectionQueue | None"] = relationship(foreign_keys=[previous_queue_id])
    new_queue: Mapped["SelectionQueue | None"] = relationship(foreign_keys=[new_queue_id])
    originating_outcome_decision: Mapped["SelectionOutcomeDecision | None"] = relationship()


# ---------------------------------------------------------------------------
# Selection module — Selection Feedback Intelligence Foundation
#
# THE PAST IS IMMUTABLE. Every table below either (a) is append-only (a row,
# once created, is never UPDATEd or DELETEd by any service function — a
# later fact is always a NEW row, linked to the old one, never a rewrite of
# it), or (b) is an explicit live/immutable-snapshot pair mirroring
# `SelectionOutcomeDefinition`/`SelectionOutcomeDefinitionSnapshot`'s own
# exact discipline: a live, restaurant-editable row plus a `version`
# counter, and a separate, never-edited Snapshot row per version that
# everything downstream pins to by ID — so a later edit to the live
# Definition never rewrites what a historical Observation/Snapshot/Case
# Memory meant at the moment it was created.
#
# This is the MEMORY FOUNDATION only (task's own framing): no autonomous
# Pattern/Rule discovery, no automatic EMERGING->ESTABLISHED promotion, no
# automatic rule creation, no Training/Performance integration, and no
# similarity-search/predictive engine exist anywhere in this section — see
# `rfone_data_store/selection/pattern_service.py` and `case_memory_service.
# py`'s own module docstrings for exactly what IS and is NOT implemented.
# ---------------------------------------------------------------------------


class SelectionPatternDefinition(Base):
    """A reusable professional pattern RF-One knows how to recognize (task
    §3) — restaurant/organization-authored DATA, never a hard-coded
    universal vocabulary (mirrors `SelectionOutcomeDefinition`'s own "RF-One
    seeds examples, the Organization owns and edits them" convention).
    `scope` follows the GENERAL/BUSINESS_DOMAIN/ORGANIZATION/
    ROLE_OR_JOB_FAMILY hierarchy (task §3) — more specific knowledge may
    coexist with broader knowledge; no automatic conflict resolution exists
    (task's own explicit exclusion).

    `maturity` (EMERGING/ESTABLISHED) and `persistence_type` (STRUCTURAL/
    CONTEXT_SENSITIVE) are two INDEPENDENT dimensions from `status`
    (PROPOSED/ACTIVE/RETIRED) and from each other — never collapsed into
    one flag (task §4/§5). No automatic EMERGING->ESTABLISHED promotion and
    no decay logic exist anywhere in this codebase (task §4/§5/§29).

    `signature` is the Pattern Signature (task §6): a structured, JSON
    dimension list (see `core/pattern_model.SUGGESTED_SIGNATURE_DIMENSIONS`
    for the open, non-exhaustive seed vocabulary) describing WHICH
    dimensions make cases comparable for THIS pattern specifically — never
    generic candidate-to-candidate similarity. Deliberately versioned
    TOGETHER with the rest of the Definition (one `version` counter, not a
    separate one) — the smallest coherent representation that still lets a
    future task inspect exactly what Signature was in effect for any
    historical Observation/Comparison, via the immutable Snapshot below.

    `required_authority_level_id` is the governance-foundation hook (task
    §22/§23): which configured Authority Level, if any, a future Rule/
    Memory Governance workflow would require to modify this Definition.
    Nothing in this task enforces it — no approval workflow exists yet —
    this only prepares the reference so a later task can."""

    __tablename__ = "selection_pattern_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    restaurant_id: Mapped[int | None] = mapped_column(ForeignKey("restaurants.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    scope: Mapped[str] = mapped_column(String(24), nullable=False, default="GENERAL")
    applicability_context: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PROPOSED")
    maturity: Mapped[str] = mapped_column(String(16), nullable=False, default="EMERGING")
    persistence_type: Mapped[str] = mapped_column(String(24), nullable=False, default="STRUCTURAL")

    signature: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    creation_provenance: Mapped[str] = mapped_column(String(32), nullable=False, default="HUMAN_AUTHORED")
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    required_authority_level_id: Mapped[int | None] = mapped_column(
        ForeignKey("selection_authority_levels.id"), nullable=True, index=True
    )

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    required_authority_level: Mapped["SelectionAuthorityLevel | None"] = relationship()
    examples: Mapped[list["SelectionPatternExample"]] = relationship(
        back_populates="pattern_definition", cascade="all, delete-orphan", order_by="SelectionPatternExample.id",
    )


class SelectionPatternDefinitionSnapshot(Base):
    """Immutable, point-in-time copy of a Pattern Definition (including its
    Signature) — mirrors `SelectionOutcomeDefinitionSnapshot`'s exact
    idempotent-per-version discipline (`pattern_service.
    get_or_create_pattern_definition_snapshot`). Every Pattern Observation
    pins to one of these, never to the live, still-editable Definition row
    — a later edit to the live Definition never rewrites what a historical
    Observation/Comparison meant at the moment it was made."""

    __tablename__ = "selection_pattern_definition_snapshots"
    __table_args__ = (
        UniqueConstraint("definition_id", "version", name="uq_pattern_definition_snapshot_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    definition_id: Mapped[int] = mapped_column(
        ForeignKey("selection_pattern_definitions.id"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    restaurant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope: Mapped[str] = mapped_column(String(24), nullable=False)
    applicability_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    maturity: Mapped[str] = mapped_column(String(16), nullable=False)
    persistence_type: Mapped[str] = mapped_column(String(24), nullable=False)
    signature: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    creation_provenance: Mapped[str] = mapped_column(String(32), nullable=False)
    was_active: Mapped[bool] = mapped_column(Boolean, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    definition: Mapped["SelectionPatternDefinition"] = relationship()


class SelectionPatternExample(Base):
    """A permanent knowledge asset attached to a Pattern Definition (task
    §20) — original examples, later examples, confirming examples,
    counterexamples, exceptions, and the reasons the pattern exists.
    Append-only (never edited/deleted) and linked to the LIVE
    `pattern_definition_id` (not one specific snapshot) so examples survive
    every later Definition version and remain inspectable regardless of
    which version is currently active — `definition_version_at_capture`
    preserves exactly which version was current when each example was
    added, so history stays honest even as the live Definition evolves."""

    __tablename__ = "selection_pattern_examples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pattern_definition_id: Mapped[int] = mapped_column(
        ForeignKey("selection_pattern_definitions.id"), nullable=False, index=True
    )
    definition_version_at_capture: Mapped[int] = mapped_column(Integer, nullable=False)

    example_type: Mapped[str] = mapped_column(String(24), nullable=False, default="ORIGINAL")
    case_reference: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    provenance: Mapped[str] = mapped_column(String(32), nullable=False, default="HUMAN_AUTHORED")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    pattern_definition: Mapped["SelectionPatternDefinition"] = relationship(back_populates="examples")


class SelectionPatternCaseComparison(Base):
    """The classification of ONE historical case relative to ONE Pattern
    Definition (task §7 and §24's "historical stress-test foundation") —
    distinct from `SelectionPatternExample` (§20's curated, permanent
    knowledge asset): a Comparison is the raw, append-only OUTCOME of one
    comparison/stress-test act (system or human), while an Example is
    something a human has chosen to keep as a permanent reference. A future
    stress-test component (task §24, explicitly NOT built here) would
    create many `SelectionPatternCaseComparison` rows against a proposed
    Signature and summarize them; a human may then promote a particularly
    illustrative one to a permanent `SelectionPatternExample`.

    Deliberately NOT an artificial universal numeric similarity score
    (task §7) — `classification` (CONFIRMING_CASE/COUNTEREXAMPLE/
    PARTIAL_MATCH/NOT_COMPARABLE) plus `dimensions_compared`/`explanation`
    are authoritative. `internal_numeric_value` MAY hold an engineering-
    convenience number (e.g. a raw similarity metric an algorithm computed
    on its way to the classification above) but is never itself exposed as
    the authoritative result — no UI/service in this task treats it as
    such."""

    __tablename__ = "selection_pattern_case_comparisons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pattern_definition_id: Mapped[int] = mapped_column(
        ForeignKey("selection_pattern_definitions.id"), nullable=False, index=True
    )
    pattern_definition_snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("selection_pattern_definition_snapshots.id"), nullable=False, index=True
    )
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), nullable=False, index=True)

    classification: Mapped[str] = mapped_column(String(24), nullable=False)
    dimensions_compared: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    supporting_evidence_references: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    internal_numeric_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    provenance: Mapped[str] = mapped_column(String(32), nullable=False, default="SYSTEM_GENERATED")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    pattern_definition: Mapped["SelectionPatternDefinition"] = relationship()
    pattern_definition_snapshot: Mapped["SelectionPatternDefinitionSnapshot"] = relationship()
    application: Mapped["Application"] = relationship()


class SelectionPatternObservation(Base):
    """The statement that a Pattern Definition is observed in THIS
    candidate/Application at THIS point in Selection (task §8) — distinct
    from the reusable Pattern Definition concept itself. Pins the EXACT
    `pattern_definition_snapshot_id` used (task §7's own requirement,
    reused here) so a later Definition edit never rewrites what this
    Observation meant. `role` (POSITIVE/NEGATIVE/MODIFIER/NEUTRALIZER, task
    §8) means a pattern is never forced to be only positive or negative.

    Append-only: once created, an Observation's facts are never edited.
    While a Stage remains open, new evidence may make an Observation stale
    — `pattern_service.supersede_observation()` marks the OLD row
    `observation_status=SUPERSEDED` and creates a brand-new ACTIVE row,
    never mutates the old one in place (THE PAST IS IMMUTABLE, applied at
    the smallest possible grain). The WORKING Pattern Profile (task §10) is
    always just "every ACTIVE Observation for this Application at its
    current Stage" — computed on read by `pattern_service.
    compute_working_pattern_profile()`, never itself a separate stored,
    mutable row (avoids a second, possibly-diverging copy of the same
    live-and-changing truth)."""

    __tablename__ = "selection_pattern_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pattern_definition_id: Mapped[int] = mapped_column(
        ForeignKey("selection_pattern_definitions.id"), nullable=False, index=True
    )
    pattern_definition_snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("selection_pattern_definition_snapshots.id"), nullable=False, index=True
    )
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), nullable=False, index=True)
    person_id: Mapped[int | None] = mapped_column(ForeignKey("candidate_persons.id"), nullable=True, index=True)

    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    stage_occurrence_index: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    observation_status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")
    superseded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("selection_pattern_observations.id"), nullable=True
    )

    role: Mapped[str] = mapped_column(String(16), nullable=False)  # POSITIVE/NEGATIVE/MODIFIER/NEUTRALIZER
    relevance: Mapped[str] = mapped_column(String(16), nullable=False, default="MEDIUM")
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)

    evidence_references: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    rule_references: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    provenance: Mapped[str] = mapped_column(String(32), nullable=False, default="SYSTEM_GENERATED")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    application: Mapped["Application"] = relationship()
    person: Mapped["CandidatePerson | None"] = relationship()
    pattern_definition: Mapped["SelectionPatternDefinition"] = relationship()
    pattern_definition_snapshot: Mapped["SelectionPatternDefinitionSnapshot"] = relationship()


class SelectionStagePatternSnapshot(Base):
    """The IMMUTABLE freeze of the Working Pattern Profile at the moment a
    Selection Stage is completed/closed (task §11) — created ONLY for
    Stages actually traversed (never for a skipped Stage — the caller,
    never this table, decides when to freeze one). `stage_occurrence_index`
    supports a Stage that repeats (task §11's own requirement). Once
    created, never altered — `observation_ids` freezes exactly which
    `SelectionPatternObservation` rows were ACTIVE at that moment (by ID
    reference, never a duplicated copy of their content — the Observation
    rows themselves are already immutable per-row, so referencing them by
    ID is sufficient and never goes stale).

    `rf_one_judgment`/`selector_action`/`divergence_*`/`selector_note`
    together are the Selezionatore Note / Divergence representation (task
    §13) — normally optional (`selector_note` nullable), but
    `note_required` records whether this specific snapshot's divergence
    made a note mandatory (the architecture supports that; no sophisticated
    divergence DETECTOR exists yet — `case_memory_service.
    freeze_stage_pattern_snapshot()`'s caller supplies `divergence_occurred`
    explicitly, task's own "do not build a sophisticated divergence
    detector yet"). A case-level override recorded here never automatically
    modifies a Pattern Definition or any rule (task §13's own explicit
    boundary) — it becomes a Learning Trace instead (`case_memory_service.
    freeze_stage_pattern_snapshot()` always appends one when divergence
    occurred)."""

    __tablename__ = "selection_stage_pattern_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    stage_occurrence_index: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    observation_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    pattern_definition_versions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    rule_versions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evidence_references: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    resulting_priority_interpretation: Mapped[str | None] = mapped_column(String(64), nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)

    rf_one_judgment: Mapped[str | None] = mapped_column(Text, nullable=True)
    selector_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    divergence_occurred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    divergence_category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    note_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    selector_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    previous_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("selection_stage_pattern_snapshots.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    application: Mapped["Application"] = relationship()
    previous_snapshot: Mapped["SelectionStagePatternSnapshot | None"] = relationship(remote_side=[id])
    deltas: Mapped[list["SelectionStagePatternDelta"]] = relationship(
        back_populates="stage_snapshot", cascade="all, delete-orphan", order_by="SelectionStagePatternDelta.id",
    )


class SelectionStagePatternDelta(Base):
    """What changed for ONE Pattern Definition between a Stage Pattern
    Snapshot and its immediate previous one (task §12) — NEW_PATTERN/
    CONFIRMED/STRENGTHENED/WEAKENED/NEUTRALIZED/NO_LONGER_SUPPORTED/
    IMPORTANCE_INCREASED/IMPORTANCE_DECREASED, always with an explanation.
    Never derived from an opaque score (task's own explicit instruction) —
    `case_memory_service.compute_stage_delta()` derives each delta from the
    explicit `role`/`relevance` fields on the two Snapshots' Observations,
    never a numeric similarity computation."""

    __tablename__ = "selection_stage_pattern_deltas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stage_snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("selection_stage_pattern_snapshots.id"), nullable=False, index=True
    )
    pattern_definition_id: Mapped[int] = mapped_column(
        ForeignKey("selection_pattern_definitions.id"), nullable=False, index=True
    )
    delta_type: Mapped[str] = mapped_column(String(24), nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    stage_snapshot: Mapped["SelectionStagePatternSnapshot"] = relationship(back_populates="deltas")
    pattern_definition: Mapped["SelectionPatternDefinition"] = relationship()


class SelectionLearningTrace(Base):
    """Raw evidence of something potentially useful for future learning
    (task §14) — NOT automatically a rule. Append-only: no service function
    in this codebase ever updates or deletes a Learning Trace row.
    `event_type` is a plain, OPEN string (see `core/pattern_model.
    SUGGESTED_LEARNING_TRACE_TYPES` for seed spelling only) so a genuinely
    new kind of learning-relevant event never requires a schema change
    (task's own explicit instruction). `event_data` carries whatever
    structured payload that event type needs; `source_reference` points
    back at the record that caused this trace (e.g. an Outcome Decision, a
    Stage transition, a Note) without duplicating its content."""

    __tablename__ = "selection_learning_traces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int | None] = mapped_column(ForeignKey("applications.id"), nullable=True, index=True)
    person_id: Mapped[int | None] = mapped_column(ForeignKey("candidate_persons.id"), nullable=True, index=True)
    stage: Mapped[str | None] = mapped_column(String(32), nullable=True)

    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    source_reference: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    provenance: Mapped[str] = mapped_column(String(32), nullable=False, default="SYSTEM_GENERATED")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    application: Mapped["Application | None"] = relationship()
    person: Mapped["CandidatePerson | None"] = relationship()


class SelectionEffort(Base):
    """How much Selection effort was consumed to reach an Application's
    Outcome (task §15) — computed at Case Memory closure time
    (`case_memory_service.compute_selection_effort()`), from whatever is
    actually observable (Stage/Queue history, Notes) plus optional
    manually-supplied fields (`interviewer_time_minutes`,
    `preparation_notes`) that are never fabricated when unavailable —
    unobserved numeric fields stay `None`, never defaulted to 0 (task's own
    "do not invent unavailable time values").

    Deliberately APPEND-ONLY, one row per computation, NOT one row per
    Application (no unique constraint on `application_id`): if this were a
    single row reused/updated across a reopen-and-reclose cycle, computing
    fresh effort for Case Memory V2 would silently rewrite what V1's own
    `selection_effort_id` already points to — violating THE PAST IS
    IMMUTABLE. Each Case Memory version pins its OWN Effort row instead."""

    __tablename__ = "selection_efforts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id"), nullable=False, index=True
    )

    stages_traversed_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    repeated_stages_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    interviewer_time_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tests_administered_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    followups_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    preparation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    interactions_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    point_of_exit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    final_outcome: Mapped[str | None] = mapped_column(String(255), nullable=True)
    effort_elements: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    application: Mapped["Application"] = relationship()


class SelectionCaseMemory(Base):
    """The synthesized professional memory of one Application, created when
    it closes (task §16). References authoritative source records wherever
    appropriate (`final_stage_snapshot_id`, `selection_effort_id`,
    `outcome_decision_id`, plus JSON ID lists for Notes/Learning
    Traces/Stage Snapshots) rather than duplicating their content.
    `rf_one_final_judgment` and `selezionatore_final_decision` are
    DISTINCT fields (task's own explicit "RF-One evaluates. The
    Selezionatore decides.") — never merged into one.

    THE PAST IS IMMUTABLE (task §17): once created, a Case Memory row is
    never updated (no `updated_at`, no service function edits one).
    Reopening an Application never touches a prior Case Memory —
    `case_memory_service.close_case_memory()` always INSERTs a new row,
    linking `previous_case_memory_id` and incrementing `version`, and
    flips the OLD row's `is_current` to False in the same transaction
    (the only field-level change ever made to a prior Case Memory row, and
    it changes NOTHING about what that row records — only which one is
    currently authoritative for "what does RF-One currently believe about
    this Application")."""

    __tablename__ = "selection_case_memories"
    __table_args__ = (
        UniqueConstraint("application_id", "version", name="uq_case_memory_application_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), nullable=False, index=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("candidate_persons.id"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    previous_case_memory_id: Mapped[int | None] = mapped_column(
        ForeignKey("selection_case_memories.id"), nullable=True
    )
    reopening_event_reference: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    closed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    outcome_decision_id: Mapped[int] = mapped_column(
        ForeignKey("selection_outcome_decisions.id"), nullable=False, index=True
    )
    lifecycle_state_at_closure: Mapped[str] = mapped_column(String(16), nullable=False)

    essential_facts: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    selection_signals_summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    final_stage_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("selection_stage_pattern_snapshots.id"), nullable=True
    )
    stage_snapshot_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    materially_impactful_pattern_versions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    materially_impactful_rules: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    rf_one_final_judgment: Mapped[str | None] = mapped_column(Text, nullable=True)
    selezionatore_final_decision: Mapped[str | None] = mapped_column(Text, nullable=True)

    skill_findings: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    training_burden_estimate: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    trainable_gaps: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    selection_effort_id: Mapped[int | None] = mapped_column(ForeignKey("selection_efforts.id"), nullable=True)
    notes_reference: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    learning_trace_reference: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evidence_reference: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    application: Mapped["Application"] = relationship()
    person: Mapped["CandidatePerson"] = relationship()
    previous_case_memory: Mapped["SelectionCaseMemory | None"] = relationship(remote_side=[id])
    outcome_decision: Mapped["SelectionOutcomeDecision"] = relationship()
    final_stage_snapshot: Mapped["SelectionStagePatternSnapshot | None"] = relationship()
    selection_effort: Mapped["SelectionEffort | None"] = relationship()


class SelectionDownstreamOutcomeFeedback(Base):
    """Foundation ONLY for future append-only downstream Outcome Feedback
    (task §18) — no Training/Performance integration is implemented here;
    this table only provides the generic structure so a LATER task can
    append evidence from Training, Performance, another Shared Domain, or a
    Business Domain to a closed Selection case WITHOUT altering the
    historical Case Memory. `case_memory_id` is nullable (a feedback record
    may reference the Application generally rather than one specific
    closure version) but when set, it is never used to rewrite that Case
    Memory row — this table is structurally separate and append-only."""

    __tablename__ = "selection_downstream_outcome_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), nullable=False, index=True)
    case_memory_id: Mapped[int | None] = mapped_column(
        ForeignKey("selection_case_memories.id"), nullable=True, index=True
    )

    source_domain: Mapped[str] = mapped_column(String(64), nullable=False)
    source_record_reference: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    feedback_type: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_fact: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_reference: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    classification: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provenance: Mapped[str] = mapped_column(String(32), nullable=False, default="SYSTEM_GENERATED")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    application: Mapped["Application"] = relationship()
    case_memory: Mapped["SelectionCaseMemory | None"] = relationship()


class SelectionAuthorityLevel(Base):
    """One configured Selection governance authority level (task §22) —
    e.g. SELECTOR/SENIOR_SELECTOR/SELECTION_OWNER, but these labels are
    entirely restaurant-configured examples, never fixed or required.
    `level_order` (1 = lowest) is the only thing that matters structurally
    — an Organization may configure exactly 1, 2, or 3 (or more) levels;
    RF-One never invents or requires a missing level (task's own explicit
    instruction). `assigned_holders` is a plain JSON list of names/labels —
    no authentication/RBAC system exists in Selection (same honest-
    placeholder rationale as `performed_by` throughout this codebase)."""

    __tablename__ = "selection_authority_levels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    restaurant_id: Mapped[int | None] = mapped_column(ForeignKey("restaurants.id"), nullable=True, index=True)
    level_key: Mapped[str] = mapped_column(String(64), nullable=False)
    level_order: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    assigned_holders: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SelectionGovernanceRequirement(Base):
    """Which Selection Organization-Memory action types require which
    configured Authority Level (task §22/§23) — e.g. "approving a Pattern
    Definition for ACTIVE status requires SENIOR_SELECTOR." Deliberately
    just the configuration foundation: no approval-workflow UI/enforcement
    engine exists in this task (task §22's own "do not implement a complex
    approval UI... create the correct domain/configuration foundation").
    `action_type` is an open string (mirrors every other extensible-
    vocabulary field in this section) so a new governed action type never
    requires a schema change."""

    __tablename__ = "selection_governance_requirements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    restaurant_id: Mapped[int | None] = mapped_column(ForeignKey("restaurants.id"), nullable=True, index=True)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    required_authority_level_id: Mapped[int | None] = mapped_column(
        ForeignKey("selection_authority_levels.id"), nullable=True, index=True
    )
    requires_higher_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    required_authority_level: Mapped["SelectionAuthorityLevel | None"] = relationship()


# ---------------------------------------------------------------------------
# Selection module — Trainable Gap (TASK 5B)
#
# A Trainable Gap is a specific, persisted, evidence-linked record that one
# RequirementAssessment's gap (NOT_EVIDENCED/PARTIALLY_EVIDENCED, against a
# Requirement the restaurant marked TRAINABLE/PARTIALLY_TRAINABLE) is being
# tracked with an RF-One-proposed 0-4 initial level and, optionally, a
# Selezionatore's own corrected level. Mirrors the system/effective/origin/
# override_reason/overridden_at quadruple already used by
# `RequirementAssessment`, `Application.review_priority_*`,
# `PrimaryScreeningCriterionEvaluation`, and `SignalObservation` — see
# `01 Domains/Shared Domains/Selection/TrainableGap.md`.
#
# Exactly one row per RequirementAssessment (unique constraint) — the same
# discipline RequirementAssessment itself uses against (fit_assessment_id,
# requirement_snapshot_item_id): a later evidence/assessment refresh updates
# THIS row's lifecycle `status` (never its level fields) rather than
# creating a duplicate. `rf_one_initial_level` is set once at creation and
# NEVER modified by any later system or human write (task §5), mirroring
# `RequirementAssessment.system_status` never being touched by a human
# override.
#
# Deliberately NOT persisted here: a Training target level, curriculum,
# Training Step/Check, or Autonomy Level — those belong to a future Training
# Domain (task's own explicit "do not implement Training Domain").
# ---------------------------------------------------------------------------


class TrainableGap(Base):
    """One Trainable Gap (task §3/§4/§5) — a candidate gap against one
    `RequirementAssessment`, already evidenced as NOT_EVIDENCED or
    PARTIALLY_EVIDENCED, whose Requirement the restaurant considers
    TRAINABLE or PARTIALLY_TRAINABLE. `application_id`/`candidate_id`/
    `fit_assessment_id` are denormalized for direct querying (mirrors
    `PhoneInterviewPlan`/`InPersonInterviewPlan` denormalizing
    `person_id`/`candidate_id` alongside their own FK chain) — the
    authoritative link is always `requirement_assessment_id`, which in turn
    reaches the exact `RequirementSnapshotItem`/`RequirementSetSnapshot`
    this gap was identified against.

    `rf_one_initial_level` is proposed once at creation and NEVER modified
    afterward, by anything — the immutable RF-One value (task §5: "Never
    overwrite the RF-One original level"). `selezionatore_initial_level` is
    `None` until a Selezionatore records a level that DIFFERS from RF-One's
    (task §5: "If the Selezionatore agrees... no duplicate manual value is
    required"); `effective_initial_level` is always
    `selezionatore_initial_level if not None else rf_one_initial_level` —
    kept as its own column (mirrors `RequirementAssessment.effective_status`)
    so display never needs to recompute the fallback. `override_reason` is
    mandatory (enforced in `trainable_gap_service.py`, not here) whenever
    `selezionatore_initial_level` is set to a value different from
    `rf_one_initial_level`."""

    __tablename__ = "trainable_gaps"
    __table_args__ = (
        UniqueConstraint("requirement_assessment_id", name="uq_trainable_gap_requirement_assessment"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), nullable=False, index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False, index=True)
    fit_assessment_id: Mapped[int] = mapped_column(ForeignKey("fit_assessments.id"), nullable=False, index=True)
    requirement_assessment_id: Mapped[int] = mapped_column(
        ForeignKey("requirement_assessments.id"), nullable=False, index=True
    )

    # Denormalized, immutable copies of the state at the moment this gap was
    # identified (task §3's "preserve... linked Requirement, Requirement
    # trainability, source Fit status") — never re-read live off the
    # Requirement/RequirementAssessment after creation, so a later edit to
    # the live Requirement's trainability can never silently rewrite what
    # this Trainable Gap originally meant.
    missing_capability: Mapped[str] = mapped_column(Text, nullable=False)
    trainability: Mapped[str] = mapped_column(String(24), nullable=False)
    source_fit_status: Mapped[str] = mapped_column(String(32), nullable=False)
    importance: Mapped[str | None] = mapped_column(String(16), nullable=True)

    rf_one_initial_level: Mapped[int] = mapped_column(Integer, nullable=False)
    selezionatore_initial_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    effective_initial_level: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)

    origin: Mapped[str] = mapped_column(String(24), nullable=False, default="SYSTEM_GENERATED")
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    overridden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    overridden_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Lifecycle only (task §3's "preserve... status") — never a Training-
    # progress status. ACTIVE is the default; a later evidence refresh may
    # move a gap to WITHDRAWN (see `trainable_gap_service.
    # generate_trainable_gaps_for_fit_assessment`) when its underlying
    # RequirementAssessment is no longer evidenced as a gap at all — this
    # never touches the level fields above.
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    application: Mapped["Application"] = relationship()
    candidate: Mapped["Candidate"] = relationship()
    fit_assessment: Mapped["FitAssessment"] = relationship()
    requirement_assessment: Mapped["RequirementAssessment"] = relationship()


# ---------------------------------------------------------------------------
# Selection module — Selection Session + Application Ownership + Rule
# Governance (TASK 5C)
#
# SelectionSession is the operational container for ONE role (task §1/§2) —
# never itself a Fit Assessment, Decision, or ranking mechanism. It adds a
# governance/organizational layer ON TOP of the existing Application/
# CandidatePerson/FitAssessment/Outcome architecture; nothing below
# redefines or duplicates that architecture. `Application.session_id` is
# nullable specifically so every Application that predates this task, or
# that is processed outside Session governance, remains valid unchanged.
#
# Authority/dependency (task §5) deliberately reuses `SelectionAuthorityLevel`
# (Selection Feedback Intelligence Foundation task, `governance_service.py`)
# rather than inventing a parallel hierarchy concept — `SelectionSessionAssignment.
# authority_level_id` simply points a Session-scoped assignment at an
# existing, restaurant-configured level. Two assignments with no configured
# level (`authority_level_id is None`) are peers (task §5's own "If NO
# dependency is defined... all Selezionatori... are considered peers").
# ---------------------------------------------------------------------------


class SelectionSession(Base):
    """The operational container for selecting candidates for ONE role
    (task §1/§2) — e.g. "Server — Winter Park — September 2026". Never
    multi-role (task's own explicit prohibition); a hiring campaign needing
    several roles creates several Sessions. `current_rule_set_version_id`
    is a convenience pointer (mirrors `Application.current_stage`/
    `current_queue_id`'s own "never the sole record of truth" discipline)
    — the full version history always lives in `SelectionRuleSetVersion`,
    never only here. A Session is NOT "operationally active" merely because
    `status == ACTIVE`; `session_service.assert_operational()` additionally
    requires the current Rule Set version to carry a recorded confirmation
    (task §13) — status and confirmation are kept as two independently
    inspectable facts rather than collapsed into one flag."""

    __tablename__ = "selection_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    restaurant_id: Mapped[int | None] = mapped_column(ForeignKey("restaurants.id"), nullable=True, index=True)
    location_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_role: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    planned_end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_close_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[str] = mapped_column(String(24), nullable=False, default="DRAFT")
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)  # Legacy single-value convenience only — see ApplicationNote(session_id=...) for the real, append-only Session notes history.

    current_rule_set_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("selection_rule_set_versions.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    assignments: Mapped[list["SelectionSessionAssignment"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="SelectionSessionAssignment.id",
    )
    rule_set_versions: Mapped[list["SelectionRuleSetVersion"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="SelectionRuleSetVersion.version",
        foreign_keys="SelectionRuleSetVersion.session_id",
    )
    current_rule_set_version: Mapped["SelectionRuleSetVersion | None"] = relationship(
        foreign_keys=[current_rule_set_version_id], post_update=True,
    )


class SelectionSessionAssignment(Base):
    """One Selezionatore assigned to a Session (task §4) — never a single
    forced "primary selector." `selezionatore_name` is kept as the display
    text (originally a plain honest-placeholder string; as of
    GLOBAL_INTEGRITY_FIX_002 it is always set FROM `acting_identity.
    display_name` for new assignments, never independently typed) —
    `acting_identity_id` is the authoritative reference used for authority
    comparisons (`authority_service.get_authority_order_for_identity_in_
    session`), never the name. Nullable for historical rows created before
    this task (C-1/I-4 — additive migration, no fabricated identity
    mapping). `authority_level_id` is optional (task §5 — undefined
    dependency means peers); `is_active=False` deactivates an assignment
    without deleting its history (mirrors `CandidateFlag.is_active`'s own
    discipline)."""

    __tablename__ = "selection_session_assignments"
    __table_args__ = (
        UniqueConstraint(
            "session_id", "selezionatore_name", name="uq_session_assignment_session_selezionatore"
        ),
        UniqueConstraint(
            "session_id", "acting_identity_id", name="uq_session_assignment_session_identity"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("selection_sessions.id"), nullable=False, index=True)
    selezionatore_name: Mapped[str] = mapped_column(String(255), nullable=False)
    acting_identity_id: Mapped[int | None] = mapped_column(
        ForeignKey("acting_identities.id"), nullable=True, index=True
    )
    authority_level_id: Mapped[int | None] = mapped_column(
        ForeignKey("selection_authority_levels.id"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    session: Mapped["SelectionSession"] = relationship(back_populates="assignments")
    authority_level: Mapped["SelectionAuthorityLevel | None"] = relationship()
    acting_identity: Mapped["ActingIdentity | None"] = relationship()


class ApplicationOwnership(Base):
    """One period of operational "take in charge" ownership of an
    Application by one Selezionatore (task §6/§7/§10) — append-only
    history, exactly one `is_active=True` row per Application at a time
    (enforced in `ownership_service.py`, not by a DB constraint — the same
    "current = latest/only active row" discipline `SelectionOutcomeDecision`
    already established). Reassignment (task §9/§10) closes the previous
    active row (`is_active=False`, `ended_at` set) and creates a new one
    referencing it via `previous_ownership_id` — never overwrites or
    deletes the prior row.

    `owner_name`/`assigned_by` are display text, preserved verbatim for
    historical rows; `acting_identity_id`/`assigned_by_identity_id`
    (GLOBAL_INTEGRITY_FIX_002 / C-1, the highest-priority part of that fix)
    are the AUTHORITATIVE references every ownership/authority comparison
    (`ownership_service.can_write`/`can_reassign`) now uses — never the
    name. Nullable for rows created before this task; never backfilled by
    guessing an identity from old text (Historical Integrity — honest
    uncertainty, no fabricated mapping)."""

    __tablename__ = "application_ownerships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), nullable=False, index=True)
    # Denormalized convenience copy of `Application.session_id` at claim time.
    session_id: Mapped[int | None] = mapped_column(ForeignKey("selection_sessions.id"), nullable=True, index=True)
    owner_name: Mapped[str] = mapped_column(String(255), nullable=False)
    acting_identity_id: Mapped[int | None] = mapped_column(
        ForeignKey("acting_identities.id"), nullable=True, index=True
    )
    assigned_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    assigned_by_identity_id: Mapped[int | None] = mapped_column(
        ForeignKey("acting_identities.id"), nullable=True, index=True
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    stage_at_time: Mapped[str | None] = mapped_column(String(32), nullable=True)
    previous_ownership_id: Mapped[int | None] = mapped_column(
        ForeignKey("application_ownerships.id"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    application: Mapped["Application"] = relationship()
    session: Mapped["SelectionSession | None"] = relationship()
    previous_ownership: Mapped["ApplicationOwnership | None"] = relationship(remote_side=[id])
    acting_identity: Mapped["ActingIdentity | None"] = relationship(foreign_keys=[acting_identity_id])
    assigned_by_identity: Mapped["ActingIdentity | None"] = relationship(foreign_keys=[assigned_by_identity_id])


class SelectionRuleSetVersion(Base):
    """One immutable, versioned Rule Set envelope for a Session/role (task
    §11/§12) — references existing immutable snapshots and live
    configuration ids rather than duplicating their data (task's own "Do
    NOT duplicate all data if existing immutable snapshots can be
    referenced safely"). `requirement_set_snapshot_id` and each id inside
    `primary_screening_criterion_snapshot_ids` are captured as immutable
    snapshots AT THE MOMENT this version is built (`rule_set_service.
    build_rule_set_version`), so the envelope can never silently drift even
    if the live Requirement Set/Criteria are edited afterward.
    `signal_definition_ids`/`review_priority_policy_id`/
    `outcome_definition_ids`/`phone_interview_question_definition_ids`/
    `in_person_interview_section_definition_ids` reference LIVE
    configuration rows — no immutable snapshot mechanism exists yet for
    those (task §12's own "reference... where applicable"; an honestly-
    scoped limitation, see the Task 5C report). Confirmation fields (task
    §15) are folded directly onto this row rather than a separate table: a
    version is confirmed at most once, by one person, at one time."""

    __tablename__ = "selection_rule_set_versions"
    __table_args__ = (
        UniqueConstraint("session_id", "version", name="uq_rule_set_version_session_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("selection_sessions.id"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    requirement_set_id: Mapped[int | None] = mapped_column(ForeignKey("requirement_sets.id"), nullable=True)
    requirement_set_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("requirement_set_snapshots.id"), nullable=True
    )
    primary_screening_criterion_snapshot_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    signal_definition_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    review_priority_policy_id: Mapped[int | None] = mapped_column(
        ForeignKey("review_priority_policies.id"), nullable=True
    )
    outcome_definition_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    phone_interview_question_definition_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    in_person_interview_section_definition_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_from_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("selection_rule_set_versions.id"), nullable=True
    )
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    confirmed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # GLOBAL_INTEGRITY_FIX_002 / C-1: `confirmed_by` remains display text
    # (and the only field historical rows carry); `confirmed_by_identity_id`
    # is the authoritative reference for new confirmations, resolved
    # server-side (`acting_identity_service`), never client-supplied text.
    confirmed_by_identity_id: Mapped[int | None] = mapped_column(
        ForeignKey("acting_identities.id"), nullable=True, index=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmation_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    session: Mapped["SelectionSession"] = relationship(
        back_populates="rule_set_versions", foreign_keys=[session_id],
    )
    requirement_set: Mapped["RequirementSet | None"] = relationship()
    requirement_set_snapshot: Mapped["RequirementSetSnapshot | None"] = relationship()
    review_priority_policy: Mapped["ReviewPriorityPolicy | None"] = relationship()
    created_from_version: Mapped["SelectionRuleSetVersion | None"] = relationship(remote_side=[id])
    confirmed_by_identity: Mapped["ActingIdentity | None"] = relationship(foreign_keys=[confirmed_by_identity_id])


class SelectionRuleChange(Base):
    """One Rule Change EVENT during an ACTIVE Session (task §16-§21) —
    distinct from `SelectionRuleSetVersion` itself: this row records WHY
    and under what SCOPE a new version was created, never overwritten.
    `scope` is `core.rule_set_model.SUBSEQUENT_ONLY` or `ENTIRE_SESSION`
    (task §17 — never silently defaulted; `rule_change_service.py` rejects
    a missing/invalid scope). For `ENTIRE_SESSION`, one
    `SelectionRuleChangeImpact` row is created per Application already
    linked under an older Rule Set version (task §19/§21)."""

    __tablename__ = "selection_rule_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("selection_sessions.id"), nullable=False, index=True)
    previous_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("selection_rule_set_versions.id"), nullable=True
    )
    new_version_id: Mapped[int] = mapped_column(ForeignKey("selection_rule_set_versions.id"), nullable=False)

    rules_changed_summary: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(String(24), nullable=False)
    performed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # GLOBAL_INTEGRITY_FIX_002 / C-1: authoritative actor reference for new
    # Rule Changes, resolved server-side; `performed_by` stays as display
    # text / historical fallback.
    performed_by_identity_id: Mapped[int | None] = mapped_column(
        ForeignKey("acting_identities.id"), nullable=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    session: Mapped["SelectionSession"] = relationship()
    previous_version: Mapped["SelectionRuleSetVersion | None"] = relationship(foreign_keys=[previous_version_id])
    new_version: Mapped["SelectionRuleSetVersion"] = relationship(foreign_keys=[new_version_id])
    performed_by_identity: Mapped["ActingIdentity | None"] = relationship(foreign_keys=[performed_by_identity_id])
    impacts: Mapped[list["SelectionRuleChangeImpact"]] = relationship(
        back_populates="rule_change", cascade="all, delete-orphan", order_by="SelectionRuleChangeImpact.id",
    )


class SelectionRuleChangeImpact(Base):
    """One Application affected by an ENTIRE_SESSION-scope Rule Change
    (task §19/§20/§21) — never created for SUBSEQUENT_ONLY (task §18: prior
    Applications are explicitly NOT touched). `recalculation_status`/
    `review_status` are deliberately separate: a retroactive Rule Change
    may safely re-run a deterministic component (e.g. refreshing
    résumé-stage evidence via the existing, idempotent
    `fit_assessment_service.generate_resume_stage_assessment`, which
    already never overwrites a human-touched `effective_status` — task
    §20's own "must NOT... change an existing substantive Selezionatore
    decision") without that ever meaning the Application's human review is
    considered DONE — `review_status` starts at NEEDS_REVIEW and is only
    ever advanced by an explicit Selezionatore action."""

    __tablename__ = "selection_rule_change_impacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rule_change_id: Mapped[int] = mapped_column(ForeignKey("selection_rule_changes.id"), nullable=False, index=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), nullable=False, index=True)

    recalculation_status: Mapped[str] = mapped_column(String(24), nullable=False, default="PENDING")
    review_status: Mapped[str] = mapped_column(String(24), nullable=False, default="NEEDS_REVIEW")
    recalculated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    rule_change: Mapped["SelectionRuleChange"] = relationship(back_populates="impacts")
    application: Mapped["Application"] = relationship()


# ---------------------------------------------------------------------------
# Task 5D — Candidate Communication + Interview Scheduling. Acquisition
# Source (how the candidate found the role) is deliberately separate from
# Communication Channel (how RF-One contacts them) — see
# `core/communication_model.py`'s module docstring.
# ---------------------------------------------------------------------------

class AcquisitionSourceDefinition(Base):
    """A restaurant-configurable Acquisition Source (task §1) — e.g.
    Indeed, LinkedIn, Referral, Walk-In. Deliberately a restaurant-editable
    lookup table, not a hard-coded enum (task's own "do NOT make this a
    rigid universal enum if the current architecture supports configurable
    source definitions more cleanly") — mirrors `SignalDefinition`'s minimal
    "restaurant defines a small list" shape. NOT the same concept as
    `Candidate.source` (Task 2A's ResumeSource-acquisition-mechanism field,
    e.g. LOCAL_UPLOAD) and NOT a Communication Channel."""

    __tablename__ = "acquisition_source_definitions"
    __table_args__ = (
        UniqueConstraint("restaurant_id", "name", name="uq_acquisition_source_restaurant_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    restaurant_id: Mapped[int | None] = mapped_column(ForeignKey("restaurants.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CommunicationTemplate(Base):
    """A restaurant-configurable, versioned Communication Template (task
    §3/§4) — the Selezionatore never rewrites the standard message per
    candidate. `stage`/`trigger_event`/`outcome_definition_id` together
    identify WHEN this template fires (see `core/communication_model.py`'s
    `TRIGGER_EVENTS` docstring for exactly which service-layer call reads
    which combination); `outcome_definition_id` is a live reference (used
    only for OUTCOME-triggered events, where the restaurant names which of
    ITS OWN Outcome Definitions — e.g. its "Stop," its "Hold" — this
    template answers) and is left `None` for stage-advance/reminder/
    confirmation events. `restaurant_id`/`location_label`/`role` narrow
    which Application this template applies to; any of the three may be
    `None` to mean "any." Matching among several active candidates picks the
    most specific (see `communication_service.find_best_template`)."""

    __tablename__ = "communication_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    restaurant_id: Mapped[int | None] = mapped_column(ForeignKey("restaurants.id"), nullable=True, index=True)
    location_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    trigger_event: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    outcome_definition_id: Mapped[int | None] = mapped_column(
        ForeignKey("selection_outcome_definitions.id"), nullable=True
    )

    purpose: Mapped[str | None] = mapped_column(String(255), nullable=True)
    language: Mapped[str] = mapped_column(String(16), nullable=False, default="en")

    sms_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    email_subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    email_body: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    outcome_definition: Mapped["SelectionOutcomeDefinition | None"] = relationship()


class CommunicationTemplateSnapshot(Base):
    """Immutable, point-in-time copy of a Communication Template (task §4)
    — mirrors `SelectionOutcomeDefinitionSnapshot`'s exact idempotent-per-
    version discipline. Every `CandidateCommunication` pins to one of these,
    never to the live, still-editable `CommunicationTemplate` row — a later
    edit to the live template never rewrites what was actually sent to a
    candidate in the past (task's own "never reconstruct old communication
    from the current template")."""

    __tablename__ = "communication_template_snapshots"
    __table_args__ = (
        UniqueConstraint("template_id", "version", name="uq_communication_template_snapshot_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("communication_templates.id"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    restaurant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    location_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    trigger_event: Mapped[str] = mapped_column(String(48), nullable=False)
    # Deliberately NOT a foreign key (mirrors `SelectionOutcomeDefinitionSnapshot.
    # target_queue_id`) — stays valid even if the live Outcome Definition it
    # named is later renamed/deactivated.
    outcome_definition_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    purpose: Mapped[str | None] = mapped_column(String(255), nullable=True)
    language: Mapped[str] = mapped_column(String(16), nullable=False)
    sms_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    email_subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    email_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    was_active: Mapped[bool] = mapped_column(Boolean, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    template: Mapped["CommunicationTemplate"] = relationship()


class CommunicationReminderPolicy(Base):
    """Configurable no-response follow-up (task §16-§18), scoped by
    restaurant/branch/role/stage/`trigger_event` exactly like a Template.
    Reminder communications themselves are rendered through the ordinary
    Template lookup (`trigger_event=REMINDER`, same scoping fields) rather
    than a direct FK here — one restaurant-configurable Reminder Policy may
    legitimately use different Reminder templates per language/role without
    this table needing to know about each one individually.

    `auto_stop_enabled` is an explicit, restaurant-configured opt-in (task
    §18 — "this is not an AI judgment... execution of an explicit configured
    rule"); `auto_stop_outcome_definition_id` names exactly which of the
    restaurant's own Outcome Definitions is applied (through the existing
    authoritative `outcome_service.apply_outcome`) when the deadline is
    reached with no response."""

    __tablename__ = "communication_reminder_policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    restaurant_id: Mapped[int | None] = mapped_column(ForeignKey("restaurants.id"), nullable=True, index=True)
    location_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    trigger_event: Mapped[str] = mapped_column(String(48), nullable=False, index=True)

    reminder_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_reminder_delay_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reminder_interval_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    final_deadline_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)

    auto_stop_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auto_stop_outcome_definition_id: Mapped[int | None] = mapped_column(
        ForeignKey("selection_outcome_definitions.id"), nullable=True
    )

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    auto_stop_outcome_definition: Mapped["SelectionOutcomeDefinition | None"] = relationship()


class CandidateCommunication(Base):
    """One outbound communication event, fully linked to its Application
    (task §complete history requirement) — an "event" may render as SMS,
    Email, or both simultaneously (task §2), always recorded as ONE row so
    the two channels of the same message stay visibly one event. Preserves
    the EXACT rendered text actually sent (task §4), independent of any
    later Template edit, by pinning to a `CommunicationTemplateSnapshot`.

    `awaiting_response`/`response_received_at`/`reminder_policy_id`/
    `final_deadline_at`/`reminders_sent_count`/`no_response_stop_applied`
    together track ONE response-tracking cycle (task §16-§20); reminder
    communications are themselves ordinary rows with `is_reminder=True` and
    `parent_communication_id` pointing back to this row."""

    __tablename__ = "candidate_communications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), nullable=False, index=True)
    template_snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("communication_template_snapshots.id"), nullable=False, index=True
    )
    trigger_event: Mapped[str] = mapped_column(String(48), nullable=False, index=True)

    channel_sms_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    channel_email_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    recipient_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    recipient_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    rendered_sms_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    rendered_email_subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    rendered_email_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    language_used: Mapped[str] = mapped_column(String(16), nullable=False, default="en")

    sms_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    sms_provider_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    email_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    email_provider_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)

    is_reminder: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reminder_sequence_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parent_communication_id: Mapped[int | None] = mapped_column(
        ForeignKey("candidate_communications.id"), nullable=True, index=True
    )

    awaiting_response: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    response_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    response_inbound_id: Mapped[int | None] = mapped_column(
        ForeignKey("inbound_communications.id"), nullable=True
    )
    reminder_policy_id: Mapped[int | None] = mapped_column(
        ForeignKey("communication_reminder_policies.id"), nullable=True
    )
    final_deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reminders_sent_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    no_response_stop_applied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    no_response_stop_outcome_decision_id: Mapped[int | None] = mapped_column(
        ForeignKey("selection_outcome_decisions.id"), nullable=True
    )

    related_outcome_decision_id: Mapped[int | None] = mapped_column(
        ForeignKey("selection_outcome_decisions.id"), nullable=True
    )
    related_stage_transition_id: Mapped[int | None] = mapped_column(
        ForeignKey("application_stage_transitions.id"), nullable=True
    )
    performed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    application: Mapped["Application"] = relationship()
    template_snapshot: Mapped["CommunicationTemplateSnapshot"] = relationship()
    parent_communication: Mapped["CandidateCommunication | None"] = relationship(remote_side=[id])
    response_inbound: Mapped["InboundCommunication | None"] = relationship(foreign_keys=[response_inbound_id])


class InterviewSchedulingWindow(Base):
    """One offered scheduling window (task §11) — e.g. "Monday 2-6pm." Task
    5D-MICRO-FIX §1/§3: the NORMAL/default scope is a Selection Session +
    Interview Stage (`session_id` set, `application_id` NULL) — offered ONCE
    and shared by every eligible Application in that Session, never
    recreated per candidate. `application_id` (set, `session_id` typically
    left `None`) is the optional, genuinely-exceptional per-Application
    override (task §3's own "may remain possible as an optional override").
    Exactly one of the two scoping dimensions is required — enforced by the
    `ck_scheduling_window_session_or_application` check constraint below,
    never both left unset. `scheduling_service._window_applies_to_application`
    is the one place that resolves which windows apply to a given
    Application, whichever scope they use."""

    __tablename__ = "interview_scheduling_windows"
    __table_args__ = (
        CheckConstraint(
            "session_id IS NOT NULL OR application_id IS NOT NULL",
            name="ck_scheduling_window_session_or_application",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Task 5D-MICRO-FIX §1 — widened from NOT NULL (Task 5D's original,
    # too-narrow Application-only scope) to nullable: a Session-scoped
    # shared window (the normal case) has no single owning Application.
    application_id: Mapped[int | None] = mapped_column(ForeignKey("applications.id"), nullable=True, index=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("selection_sessions.id"), nullable=True, index=True)
    interview_stage: Mapped[str] = mapped_column(String(32), nullable=False)

    window_date: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    slot_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    capacity_per_slot: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="America/New_York")

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    application: Mapped["Application | None"] = relationship()
    session: Mapped["SelectionSession | None"] = relationship()


class InterviewAppointment(Base):
    """One booked interview appointment (task §13/§14) — created and
    CONFIRMED automatically the moment a candidate selects an available
    slot (task §13: "No Selezionatore approval is required"). Rescheduling
    (task §15) never deletes/overwrites the prior row: it is marked
    `RESCHEDULED` and a new row is created referencing it via
    `previous_appointment_id`, exactly like `ApplicationOwnership`'s own
    append-only reassignment chain.

    Task 5D-MICRO-FIX §5/§9 — `slot_ordinal` (0-indexed, `< scheduling_
    window.capacity_per_slot`) is the DB-enforced concurrency guard: the
    partial unique index below allows at most one CONFIRMED row per
    (window, slot start time, ordinal) — i.e. exactly `capacity_per_slot`
    CONFIRMED appointments per slot, shared across every Application that
    books against that window, never a per-Application capacity pool. The
    index is scoped to `status = 'CONFIRMED'` only, so a RESCHEDULED/
    CANCELLED row's ordinal is immediately free for reuse — the minimum
    clean database-level protection compatible with the existing
    check-then-insert service logic (`scheduling_service.book_slot`), not a
    broader concurrency-control redesign."""

    __tablename__ = "interview_appointments"
    __table_args__ = (
        Index(
            "ux_interview_appointment_slot_ordinal_confirmed",
            "scheduling_window_id", "slot_start_at", "slot_ordinal",
            unique=True,
            sqlite_where=text("status = 'CONFIRMED'"),
            postgresql_where=text("status = 'CONFIRMED'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), nullable=False, index=True)
    interview_stage: Mapped[str] = mapped_column(String(32), nullable=False)
    scheduling_window_id: Mapped[int] = mapped_column(
        ForeignKey("interview_scheduling_windows.id"), nullable=False, index=True
    )

    slot_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    slot_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    slot_ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="CONFIRMED")

    candidate_selected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    previous_appointment_id: Mapped[int | None] = mapped_column(
        ForeignKey("interview_appointments.id"), nullable=True
    )
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    application: Mapped["Application"] = relationship()
    scheduling_window: Mapped["InterviewSchedulingWindow"] = relationship()
    previous_appointment: Mapped["InterviewAppointment | None"] = relationship(remote_side=[id])


class CandidateSchedulingToken(Base):
    """A secure, opaque token for the candidate-facing scheduling page
    (task §31) — the SMS/Email link carries this token, never the internal
    `application_id` directly. Not single-use (a candidate may revisit the
    page to reschedule, task §15); `is_active=False` revokes it without
    losing history."""

    __tablename__ = "candidate_scheduling_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), nullable=False, index=True)
    interview_stage: Mapped[str] = mapped_column(String(32), nullable=False)

    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    application: Mapped["Application"] = relationship()


class InboundCommunication(Base):
    """One inbound candidate message, preserved verbatim (task §21 — "never
    replace the raw message with a summary"). `classification_system` is
    what the deterministic classifier produced; `classification_effective`
    starts equal to it and is the ONLY field a Selezionatore correction
    changes (task §23 — the system classification is never overwritten/
    lost). `alert_required`/`alert_reason` implement the high-visibility
    alert (task §20/§25); acknowledging an alert never itself changes any
    Outcome (task §24)."""

    __tablename__ = "inbound_communications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)

    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    source: Mapped[str | None] = mapped_column(String(32), nullable=True)

    classification_system: Mapped[str | None] = mapped_column(String(48), nullable=True)
    classification_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    classification_effective: Mapped[str | None] = mapped_column(String(48), nullable=True)
    classification_corrected_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    classification_corrected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    classification_correction_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    related_outgoing_communication_id: Mapped[int | None] = mapped_column(
        ForeignKey("candidate_communications.id"), nullable=True
    )

    alert_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    alert_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    alert_acknowledged_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    alert_acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    application: Mapped["Application"] = relationship()
    related_outgoing_communication: Mapped["CandidateCommunication | None"] = relationship(
        foreign_keys=[related_outgoing_communication_id],
    )


# ---------------------------------------------------------------------------
# Task 5E — Job Posting + Application Intake + Missing-Evidence
# Pre-Screening. Job Posting content and internal Screening Criteria are
# deliberately separate concepts (task §2's own "do NOT expose every
# internal Selection Rule") — nothing here references a
# PrimaryScreeningCriterion directly except through the small, additive
# fields already appended to that model above.
# ---------------------------------------------------------------------------

class JobPosting(Base):
    """One Job Posting generated for a Selection Session/Role (task §1) —
    the base, channel-neutral content. Always starts as a `DRAFT` RF-One
    auto-generates from existing structured Selection data (Session/Role/
    Rule Set) and is never auto-published (task's own "Do NOT publish the
    initial draft automatically"). `current_version`/`approved_version_id`
    are convenience pointers only — full editable/approved history always
    lives in `JobPostingVersion` (mirrors `SelectionRuleSetVersion`'s own
    "never the sole record of truth" discipline)."""

    __tablename__ = "job_postings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("selection_sessions.id"), nullable=False, index=True)
    restaurant_id: Mapped[int | None] = mapped_column(ForeignKey("restaurants.id"), nullable=True, index=True)
    location_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_set_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("selection_rule_set_versions.id"), nullable=True
    )

    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT")
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    approved_version_id: Mapped[int | None] = mapped_column(ForeignKey("job_posting_versions.id"), nullable=True)

    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    session: Mapped["SelectionSession"] = relationship()
    rule_set_version: Mapped["SelectionRuleSetVersion | None"] = relationship()
    versions: Mapped[list["JobPostingVersion"]] = relationship(
        back_populates="job_posting", cascade="all, delete-orphan", order_by="JobPostingVersion.version",
        foreign_keys="JobPostingVersion.job_posting_id",
    )
    approved_version: Mapped["JobPostingVersion | None"] = relationship(
        foreign_keys=[approved_version_id], post_update=True,
    )


class JobPostingVersion(Base):
    """One editable/approvable content snapshot of a base Job Posting (task
    §4) — every edit (system-generated draft, human edit, or a later
    change) creates a NEW row; nothing here is ever overwritten. Content is
    deliberately public-facing/descriptive only (task §2's own field list)
    — compensation/benefits/schedule are free text, never a numeric Rule."""

    __tablename__ = "job_posting_versions"
    __table_args__ = (
        UniqueConstraint("job_posting_id", "version", name="uq_job_posting_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_posting_id: Mapped[int] = mapped_column(ForeignKey("job_postings.id"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    branch_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    role_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    responsibilities: Mapped[str | None] = mapped_column(Text, nullable=True)
    minimum_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    preferred_experience: Mapped[str | None] = mapped_column(Text, nullable=True)
    availability_expectations: Mapped[str | None] = mapped_column(Text, nullable=True)
    schedule_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    compensation_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    benefits_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    application_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    other_info: Mapped[str | None] = mapped_column(Text, nullable=True)

    source: Mapped[str] = mapped_column(String(16), nullable=False, default="SYSTEM_GENERATED")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    job_posting: Mapped["JobPosting"] = relationship(back_populates="versions", foreign_keys=[job_posting_id])


class ChannelDefinition(Base):
    """A generic, restaurant-configurable publication Channel container
    (task §5/§8) — Indeed/LinkedIn/Facebook/Company Website/... are
    EXAMPLES a restaurant may create, never a hard-coded closed set. Every
    capability flag is descriptive only in this task (task's own "do NOT
    implement actual provider APIs") — no code branches on `is_connected`
    to call a real provider; a future connector owns that. `is_connected`
    distinguishes CONNECTED (a future connector may publish/update
    directly) from MANUAL (task §9) — both are supported identically at
    this generic-container stage. `default_acquisition_source_id` is the
    one live link to Task 5D's Acquisition Source: when set, an Application
    arriving through this Channel's tracking link is attributed
    automatically (task §10)."""

    __tablename__ = "channel_definitions"
    __table_args__ = (
        UniqueConstraint("restaurant_id", "name", name="uq_channel_definition_restaurant_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    restaurant_id: Mapped[int | None] = mapped_column(ForeignKey("restaurants.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_connected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supports_publish: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supports_update: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supports_pause: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supports_stop: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supports_metrics: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supports_cost_tracking: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_paid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    default_acquisition_source_id: Mapped[int | None] = mapped_column(
        ForeignKey("acquisition_source_definitions.id"), nullable=True
    )

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    default_acquisition_source: Mapped["AcquisitionSourceDefinition | None"] = relationship()


class JobPostingChannelVariant(Base):
    """One channel-specific variant of a Job Posting (task §5/§6) — created
    only after the base posting is approved. More than one variant MAY
    exist for the same Channel (task §34's own A/B-testing structure —
    comparing two distinct variant texts on the same Channel), never
    constrained to exactly one. `current_version`/`approved_version_id`
    mirror `JobPosting`'s own convenience-pointer discipline."""

    __tablename__ = "job_posting_channel_variants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_posting_id: Mapped[int] = mapped_column(ForeignKey("job_postings.id"), nullable=False, index=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channel_definitions.id"), nullable=False, index=True)

    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT")
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    approved_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("job_posting_channel_variant_versions.id"), nullable=True
    )

    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    job_posting: Mapped["JobPosting"] = relationship()
    channel: Mapped["ChannelDefinition"] = relationship()
    versions: Mapped[list["JobPostingChannelVariantVersion"]] = relationship(
        back_populates="variant", cascade="all, delete-orphan", order_by="JobPostingChannelVariantVersion.version",
        foreign_keys="JobPostingChannelVariantVersion.variant_id",
    )
    approved_version: Mapped["JobPostingChannelVariantVersion | None"] = relationship(
        foreign_keys=[approved_version_id], post_update=True,
    )


class JobPostingChannelVariantVersion(Base):
    """One version of one channel variant's content (task §6/§7) — a
    post-publication edit ALWAYS creates a new row here (task's own "do not
    overwrite prior versions") and, when the variant was already
    `APPROVED`/published, requires a preserved `reason` (validated in
    `job_posting_service.py`, mirroring `SelectionOutcomeDecision`'s own
    "changing an existing decision requires a reason" discipline)."""

    __tablename__ = "job_posting_channel_variant_versions"
    __table_args__ = (
        UniqueConstraint("variant_id", "version", name="uq_job_posting_channel_variant_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    variant_id: Mapped[int] = mapped_column(ForeignKey("job_posting_channel_variants.id"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    title_override: Mapped[str | None] = mapped_column(String(500), nullable=True)
    variant_text: Mapped[str] = mapped_column(Text, nullable=False)

    source: Mapped[str] = mapped_column(String(16), nullable=False, default="SYSTEM_GENERATED")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    variant: Mapped["JobPostingChannelVariant"] = relationship(back_populates="versions", foreign_keys=[variant_id])


class ChannelPublication(Base):
    """One specific placement of one approved channel-variant version
    (task §9/§10/§11) — e.g. "Facebook Group A" and "Facebook Group B" are
    two SEPARATE `ChannelPublication` rows for the same Facebook variant,
    each with its own tracking link, so traffic is never collapsed into one
    generic source when placement-level data is available (task §11).
    `is_connected` is copied from the Channel at creation time so a later
    Channel edit never rewrites what a historical publication actually
    was. Cost fields are integer minor-unit cents (this codebase's
    universal money convention) and stay `None` when unknown — never
    fabricated (task §32)."""

    __tablename__ = "channel_publications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    variant_version_id: Mapped[int] = mapped_column(
        ForeignKey("job_posting_channel_variant_versions.id"), nullable=False, index=True
    )
    channel_id: Mapped[int] = mapped_column(ForeignKey("channel_definitions.id"), nullable=False, index=True)
    placement_label: Mapped[str] = mapped_column(String(255), nullable=False)
    is_connected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT")
    publish_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    external_link: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    cost_amount_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_currency: Mapped[str | None] = mapped_column(String(8), nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    variant_version: Mapped["JobPostingChannelVariantVersion"] = relationship()
    channel: Mapped["ChannelDefinition"] = relationship()
    tracking_links: Mapped[list["ChannelTrackingLink"]] = relationship(
        back_populates="channel_publication", order_by="ChannelTrackingLink.id",
    )


class ChannelTrackingLink(Base):
    """A unique, opaque RF-One tracking link for exactly one
    `ChannelPublication` (task §10) — resolving it identifies Channel,
    specific publication/placement, Job Posting, variant/version, and
    Selection Session all at once (via `channel_publication`), and drives
    automatic Acquisition Source attribution on Application creation. Not
    single-use — a candidate may revisit it, mirrors
    `CandidateSchedulingToken`'s own discipline."""

    __tablename__ = "channel_tracking_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_publication_id: Mapped[int] = mapped_column(
        ForeignKey("channel_publications.id"), nullable=False, index=True
    )
    token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    channel_publication: Mapped["ChannelPublication"] = relationship(back_populates="tracking_links")


class ApplicationQuestionDefinition(Base):
    """One restaurant-configured, Session/Role-scoped first-screening
    question shown on the public Web Application Form (task §16/§37) —
    deliberately a DIFFERENT concept from Phone/In-Person Interview
    questions (task §17: never the same table, never the same UI). Either
    `session_id` or `target_role` (or both, or neither = applies broadly)
    may narrow which Application Form this appears on — mirrors
    `CommunicationTemplate`'s own "any scoping field may be `None` to mean
    any" convention. `related_criterion_id`/`answer_level_map` are OPTIONAL
    (task's own "linked to relevant Screening Criteria... where
    appropriate") — mirrors `PrimaryScreeningCriterion.
    auto_evaluation_level_map`'s exact restaurant-configured-mapping
    pattern, applied here to a candidate's own Application answer instead
    of a Signal."""

    __tablename__ = "application_question_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    restaurant_id: Mapped[int | None] = mapped_column(ForeignKey("restaurants.id"), nullable=True, index=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("selection_sessions.id"), nullable=True, index=True)
    target_role: Mapped[str | None] = mapped_column(String(64), nullable=True)

    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    response_type: Mapped[str] = mapped_column(String(16), nullable=False, default="TEXT")
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    related_criterion_id: Mapped[int | None] = mapped_column(
        ForeignKey("primary_screening_criteria.id"), nullable=True
    )
    answer_level_map: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    related_criterion: Mapped["PrimaryScreeningCriterion | None"] = relationship()


class ApplicationQuestionAnswer(Base):
    """One candidate answer to one first-screening Application Question
    (task §18) — preserved as CANDIDATE SELF-REPORTED evidence, never
    independently verified fact (task's own explicit warning).
    `question_version` freezes which version of the question was actually
    asked, without needing a full immutable-snapshot table for this
    simpler, single-field concept (task §37's own "keep it simple")."""

    __tablename__ = "application_question_answers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), nullable=False, index=True)
    question_definition_id: Mapped[int] = mapped_column(
        ForeignKey("application_question_definitions.id"), nullable=False, index=True
    )
    question_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    raw_answer: Mapped[str] = mapped_column(Text, nullable=False)
    answered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    application: Mapped["Application"] = relationship()
    question_definition: Mapped["ApplicationQuestionDefinition"] = relationship()


class MissingEvidenceQuestionnaire(Base):
    """One candidate-SPECIFIC Missing-Evidence Questionnaire (task Part E)
    — never a standard/universal questionnaire (task §22's own explicit
    distinction). Generated automatically, at most one PENDING at a time
    per Application (`missing_evidence_service.py` enforces this), naming
    exactly which Primary Screening Run identified the gaps. `token` is the
    secure opaque candidate-facing link (task §26/§31 — "consistent with
    Task 5D scheduling links")."""

    __tablename__ = "missing_evidence_questionnaires"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), nullable=False, index=True)
    primary_screening_run_id: Mapped[int] = mapped_column(
        ForeignKey("primary_screening_runs.id"), nullable=False, index=True
    )
    token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    application: Mapped["Application"] = relationship()
    primary_screening_run: Mapped["PrimaryScreeningRun"] = relationship()
    questions: Mapped[list["MissingEvidenceQuestion"]] = relationship(
        back_populates="questionnaire", cascade="all, delete-orphan", order_by="MissingEvidenceQuestion.display_order",
    )


class MissingEvidenceQuestion(Base):
    """One question generated for one Missing-Evidence Questionnaire (task
    §23) — always tied to exactly the live Criterion whose evidence was
    missing; RF-One generates ONLY these, never a fixed standard list
    (task's own "do NOT ask 10 standard questions when only 2 pieces of
    information are missing")."""

    __tablename__ = "missing_evidence_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    questionnaire_id: Mapped[int] = mapped_column(
        ForeignKey("missing_evidence_questionnaires.id"), nullable=False, index=True
    )
    criterion_id: Mapped[int] = mapped_column(ForeignKey("primary_screening_criteria.id"), nullable=False, index=True)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    questionnaire: Mapped["MissingEvidenceQuestionnaire"] = relationship(back_populates="questions")
    criterion: Mapped["PrimaryScreeningCriterion"] = relationship()


class MissingEvidenceAnswer(Base):
    """One candidate answer to one Missing-Evidence Question (task §27) —
    preserved exactly as given; converting it into Primary Screening
    evidence (`missing_evidence_service.submit_answers`) never overwrites
    any evidence already on record."""

    __tablename__ = "missing_evidence_answers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("missing_evidence_questions.id"), nullable=False, index=True)
    raw_answer: Mapped[str] = mapped_column(Text, nullable=False)
    answered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    question: Mapped["MissingEvidenceQuestion"] = relationship()


# ---------------------------------------------------------------------------
# Task 5F — Compliance / Rule Review + Explainability. Deliberately
# object-type-generic (task §1's own "do NOT hard-code the service only to
# one existing model") — `object_type`/`object_id`/`object_version` identify
# WHICH configured Selection object was reviewed without a dedicated FK per
# type, mirroring `ApplicationNote.context_type`/`context_id`'s own generic-
# reference pattern already established in this codebase.
# ---------------------------------------------------------------------------

class ComplianceReview(Base):
    """One immutable review pass over one Selection configuration object at
    one specific version (task §6) — never edited or overwritten; a later
    edit to the live object is reviewed by creating a brand NEW
    `ComplianceReview` row (task's own "do not overwrite prior Compliance
    Reviews"). `reviewed_text` freezes the EXACT text/configuration that was
    actually reviewed, independent of any later edit to the live object."""

    __tablename__ = "compliance_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    object_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    object_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    object_version: Mapped[int] = mapped_column(Integer, nullable=False)
    reviewed_text: Mapped[str] = mapped_column(Text, nullable=False)
    engine_version: Mapped[str] = mapped_column(String(64), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    warnings: Mapped[list["ComplianceWarning"]] = relationship(
        back_populates="review", cascade="all, delete-orphan", order_by="ComplianceWarning.id",
    )
    dispositions: Mapped[list["ComplianceDisposition"]] = relationship(
        back_populates="review", cascade="all, delete-orphan", order_by="ComplianceDisposition.id",
    )


class ComplianceWarning(Base):
    """One identified concern within a `ComplianceReview` (task §2/§6) —
    immutable, append-only alongside its parent Review. `explanation` is
    always conversational, never a bare category code (task §7); `severity`
    is always one of the three understandable levels; `suggested_rewrite`
    is a safer-framing SUGGESTION only — nothing ever applies it
    automatically (task §5)."""

    __tablename__ = "compliance_warnings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    review_id: Mapped[int] = mapped_column(ForeignKey("compliance_reviews.id"), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(48), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_rewrite: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    review: Mapped["ComplianceReview"] = relationship(back_populates="warnings")


class ComplianceDisposition(Base):
    """One human decision made in response to a `ComplianceReview` (task
    §5/§6/§8) — append-only; a rule may accumulate more than one over time
    (e.g. KEEP_ORIGINAL now, ACKNOWLEDGE_HIGH_CONCERN later when activation
    is actually attempted). `final_text` records what the object's
    reviewable text became as a RESULT of this human decision (for
    `ACCEPT_REWRITE`/`EDIT_MANUALLY`); for `KEEP_ORIGINAL`/`DEACTIVATE`/
    `ACKNOWLEDGE_HIGH_CONCERN` it stays `None` — the object's text is
    unchanged, only the disposition itself is new information. `reason` is
    required (enforced in `compliance_service.py`) for `KEEP_ORIGINAL`
    against a HIGH_CONCERN warning and always for `ACKNOWLEDGE_HIGH_CONCERN`
    (task §8's own "preserve... reason")."""

    __tablename__ = "compliance_dispositions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    review_id: Mapped[int] = mapped_column(ForeignKey("compliance_reviews.id"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    final_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    performed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # GLOBAL_INTEGRITY_FIX_002 / C-1: authoritative actor reference for new
    # dispositions, resolved server-side; `performed_by` stays as display
    # text / historical fallback.
    performed_by_identity_id: Mapped[int | None] = mapped_column(
        ForeignKey("acting_identities.id"), nullable=True, index=True
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    review: Mapped["ComplianceReview"] = relationship(back_populates="dispositions")
    performed_by_identity: Mapped["ActingIdentity | None"] = relationship()


# ---------------------------------------------------------------------------
# Shared Domain / Training (staff dish/wine "pill" learning — first operational
# version, 03 Software/Training/).
#
# `TrainingAccount` is Training's own login/authentication record (username,
# password hash, trainer/student role) — it is NOT RF-One's shared Authority
# engine. `AuthorityGrant`/`authority_service.authorize()` are the documented
# "one permission engine every Domain calls" (Core Principle 21), but Identity
# & Access development is explicitly FROZEN (`10 System/Identity & Access/
# README.md`: "Do not continue implementation against this area... until
# explicitly unfrozen") and `authorize()` currently has zero real Domain
# consumers ("No Domain is integrated by this module" — authority_service.py's
# own docstring); Training does not make itself the first live integration of
# a frozen substrate on its own initiative. `role` below is therefore a
# narrow, Training-local attribute for Training's own two areas, not a new
# generic authority mechanism.
#
# `acting_identity_id`, by contrast, DOES reuse the shared, already
# actively-consumed `ActingIdentity` roster (Selection's `/identity/register`
# already creates rows the same way via `acting_identity_service.create_
# identity()`) — that is Core Principle 21's "the ONE stable 'who is acting'
# concept every Domain consumes", and reusing it here (rather than a second,
# Training-only person table) is exactly what the principle asks for.
#
# Pill *content* (dish description, ingredients, sell phrases, wine pairings,
# allergens) is never duplicated into these tables — it stays the single
# canonical copy already living in `03 Software/Training/RF-One-Training.html`
# (read live by the Training web app's `dish_data.py` loader). `TrainingPill`
# only carries the metadata Training itself needs to assign/version/quiz
# against that content (slug matches the dish `id` in that JSON, so the two
# stay associated without a database foreign key across a Software-layer
# static file).
# ---------------------------------------------------------------------------


class TrainingAccount(Base):
    """Training's own login record for one person (trainer or student).
    `username`/`display_name` are never used as foreign keys elsewhere
    (`display_name` lives on the linked `ActingIdentity`, per that model's
    own "changing a label must never change what the identity is
    accountable for") — every other Training table references
    `TrainingAccount.id`. `password_hash` is produced by Werkzeug's
    `generate_password_hash` (already a Flask dependency — no new library
    added); the plaintext password is never persisted or logged anywhere.
    `failed_login_attempts`/`locked_until` implement a simple, self-
    contained login-attempt lockout (no new dependency for this either)."""

    __tablename__ = "training_accounts"
    __table_args__ = (
        CheckConstraint("role IN ('trainer', 'student')", name="ck_training_account_role"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    acting_identity_id: Mapped[int] = mapped_column(
        ForeignKey("acting_identities.id"), nullable=False, unique=True
    )
    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("training_accounts.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    acting_identity: Mapped["ActingIdentity"] = relationship()


class TrainingPill(Base):
    """One assignable unit of study (a "pill"). `slug` is the stable
    identifier matching the dish `id` in `RF-One-Training.html`'s
    `dish-data` JSON — the single source of the actual study content, never
    copied here. `content_version` is bumped by hand whenever that JSON's
    substantive content changes for this dish; quiz attempts snapshot the
    version that was current when the attempt was taken, so a later content
    edit never rewrites the meaning of a historical result."""

    __tablename__ = "training_pills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    learning_objectives: Mapped[str] = mapped_column(Text, nullable=False)
    content_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )


class TrainingQuestion(Base):
    """One static question in a pill's question bank. `kind` distinguishes
    the three separate, never-overlapping question sets a pill has —
    `self_check` (practice, ungraded — see `TrainingAccount`/attempt tables:
    deliberately no table records a self-check attempt at all), `final_quiz`
    (this pill's own graded quiz) and `overall_quiz` (this pill's 3
    questions when it contributes to the whole-path quiz). `category`
    records which of the three required angles the question tests
    (ingredients/characteristics, sales/pairing, allergen warnings).
    `correct_index` and `explanation` are never sent to the client for
    `final_quiz`/`overall_quiz` kinds before a submission exists for that
    quiz; `self_check` questions are sent to the client up front by design
    (an ungraded, immediate-feedback practice tool, never persisted as a
    result — see module docstring above)."""

    __tablename__ = "training_questions"
    __table_args__ = (
        UniqueConstraint("pill_id", "kind", "position", name="uq_training_question_pill_kind_position"),
        CheckConstraint(
            "kind IN ('self_check', 'final_quiz', 'overall_quiz')", name="ck_training_question_kind"
        ),
        CheckConstraint(
            "category IN ('ingredients', 'sales_pairing', 'allergen_warning')",
            name="ck_training_question_category",
        ),
        CheckConstraint("correct_index IN (0, 1, 2)", name="ck_training_question_correct_index"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pill_id: Mapped[int] = mapped_column(ForeignKey("training_pills.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    category: Mapped[str] = mapped_column(String(24), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    options_json: Mapped[str] = mapped_column(Text, nullable=False)
    correct_index: Mapped[int] = mapped_column(Integer, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)

    pill: Mapped["TrainingPill"] = relationship()


class TrainingNeed(Base):
    """A short, trainer-authored training need for one student (spec §2 —
    "inserire un bisogno formativo come breve testo"). `origin` is an
    optional free-form category of where the need came from; it is never
    used to automatically pull data from Selection or any other Domain
    (spec explicitly excludes that for this version)."""

    __tablename__ = "training_needs"
    __table_args__ = (
        CheckConstraint(
            "origin IS NULL OR origin IN ('selection', 'observation', 'sales', 'other')",
            name="ck_training_need_origin",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_account_id: Mapped[int] = mapped_column(
        ForeignKey("training_accounts.id"), nullable=False, index=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    origin: Mapped[str | None] = mapped_column(String(24), nullable=True)
    created_by_account_id: Mapped[int] = mapped_column(ForeignKey("training_accounts.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    student_account: Mapped["TrainingAccount"] = relationship(foreign_keys=[student_account_id])


class TrainingAssignment(Base):
    """One pill assigned to satisfy one need. The `(need_id, pill_id)`
    unique constraint is the actual guarantee against an unintended
    duplicate assignment of the same pill to the same need (spec §2); the
    same pill CAN still be assigned again under a *different* need for the
    same student — each such row tracks its own independent progress
    (spec §4, "stati della singola assegnazione"). `first_opened_at` is set
    the first time the assigned student opens this specific assignment's
    pill page — never inferred from time spent on the page."""

    __tablename__ = "training_assignments"
    __table_args__ = (
        UniqueConstraint("need_id", "pill_id", name="uq_training_assignment_need_pill"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    need_id: Mapped[int] = mapped_column(ForeignKey("training_needs.id"), nullable=False, index=True)
    pill_id: Mapped[int] = mapped_column(ForeignKey("training_pills.id"), nullable=False, index=True)
    assigned_by_account_id: Mapped[int] = mapped_column(ForeignKey("training_accounts.id"), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    first_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    need: Mapped["TrainingNeed"] = relationship()
    pill: Mapped["TrainingPill"] = relationship()


class TrainingAttempt(Base):
    """One submitted attempt at one assignment's final (graded) quiz.
    Deliberately denormalizes `student_account_id`/`pill_id`/
    `pill_content_version` directly onto the row (rather than requiring a
    join through `assignment` -> `need`) so a later change to the
    assignment/need never alters what a historical attempt is provable to
    have been (spec §7's historical-integrity rule, applied consistently
    here too). `questions_json`/`answers_json` snapshot exactly what was
    presented and answered — never recomputed from the live question bank
    later. `submission_token` is a single-use, per-page-load value; its
    UNIQUE constraint is what actually stops a double form submission (e.g.
    a double click or resubmit) from ever creating two rows for what was
    really one submission — see `training.service.record_final_attempt`."""

    __tablename__ = "training_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assignment_id: Mapped[int] = mapped_column(
        ForeignKey("training_assignments.id"), nullable=False, index=True
    )
    student_account_id: Mapped[int] = mapped_column(
        ForeignKey("training_accounts.id"), nullable=False, index=True
    )
    pill_id: Mapped[int] = mapped_column(ForeignKey("training_pills.id"), nullable=False)
    pill_content_version: Mapped[int] = mapped_column(Integer, nullable=False)
    quiz_version: Mapped[int] = mapped_column(Integer, nullable=False)
    questions_json: Mapped[str] = mapped_column(Text, nullable=False)
    answers_json: Mapped[str] = mapped_column(Text, nullable=False)
    points_earned: Mapped[int] = mapped_column(Integer, nullable=False)
    points_possible: Mapped[int] = mapped_column(Integer, nullable=False)
    submission_token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    assignment: Mapped["TrainingAssignment"] = relationship()


class TrainingOverallAttempt(Base):
    """One submitted attempt at a student's whole-path quiz (spec §7) —
    three questions per distinct pill assigned to the student at the time
    of the attempt. `pills_json` snapshots exactly which pills (id, slug,
    content_version) were included, so a later change to the student's
    assignments never alters what a historical attempt covered."""

    __tablename__ = "training_overall_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_account_id: Mapped[int] = mapped_column(
        ForeignKey("training_accounts.id"), nullable=False, index=True
    )
    pills_json: Mapped[str] = mapped_column(Text, nullable=False)
    questions_json: Mapped[str] = mapped_column(Text, nullable=False)
    answers_json: Mapped[str] = mapped_column(Text, nullable=False)
    points_earned: Mapped[int] = mapped_column(Integer, nullable=False)
    points_possible: Mapped[int] = mapped_column(Integer, nullable=False)
    submission_token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class RFOneAccount(Base):
    """The general RF-One login account — the ONE identity an operator uses
    to enter the RF-One shell (`03 Software/RF-One Web/`) itself,
    deliberately independent of any Domain-specific account (e.g.
    `TrainingAccount`) — see that model's own docstring for why Training
    keeps its own separate login instead of reusing this one.
    `RFOneAccountDomainAccess` rows (below) determine which Domains this
    account may enter; this table itself knows nothing about any Domain.
    `password_hash` is produced by Werkzeug's `generate_password_hash` —
    the plaintext password is never persisted or logged anywhere.

    `email`/`email_verified_at` back the ONE general password-recovery
    mechanism every RF-One-login Domain shares (never a per-Domain
    recovery) — see `rfone_recovery_service.py`. `email` may be non-NULL
    while `email_verified_at` is still NULL: that is the normal "on file,
    pending confirmation" state for a freshly created account or a
    profile email not yet confirmed, distinct from "no email at all"
    (both NULL). Self-service recovery requires `email_verified_at` to be
    set; an unverified or absent email falls back to the existing admin
    reset. `session_version` is the minimal mechanism this stateless,
    signed-cookie session needs to support remote revocation (task: "una
    versione di sessione verificata lato server") — bumped by
    `rfone_account_service.set_password` on every password change (self-
    service reset AND the existing admin/trainer reset alike), so a
    session cookie issued before the change stops matching on its very
    next request and is treated as logged out."""

    __tablename__ = "rfone_accounts"
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name="ck_rfone_account_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="ACTIVE")
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    session_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )


class RFOneAccountDomainAccess(Base):
    """Grants one `RFOneAccount` entry into one RF-One Domain (`domain_code`,
    matching `RF-One Web/domain_registry.py`'s canonical codes — never
    validated against a DB-side enum here, since that registry is the single
    source of truth for which Domains currently exist). `role_code` is
    optional, free-form, and meaningless to this table — only the Domain
    itself, once entered, interprets it (e.g. Training's own
    'TRAINER'/'STUDENT'). This table only stores and enforces WHETHER an
    account may enter a Domain; it implements no Domain-specific
    authorization of its own."""

    __tablename__ = "rfone_account_domain_access"
    __table_args__ = (
        UniqueConstraint("account_id", "domain_code", name="uq_rfone_account_domain_access_account_domain"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("rfone_accounts.id"), nullable=False, index=True)
    domain_code: Mapped[str] = mapped_column(String(32), nullable=False)
    role_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    account: Mapped["RFOneAccount"] = relationship()


class RFOneTrainingIdentityLink(Base):
    """The one persistent, univocal bridge between a general `RFOneAccount`
    and an existing `TrainingAccount` (RF-One Web / Training single-login
    integration). Both sides are UNIQUE — an `RFOneAccount` links to at most
    one `TrainingAccount` and vice versa — so this can never express a
    duplicate or silently-replaced link; creating a second link for either
    side must go through an explicit unlink first (not implemented in this
    first integration — task scope is additive only).

    Deliberately its own table, not a column on either `rfone_accounts` or
    `training_accounts`: it lives in the canonical RF-One Data Store because
    it is schema that references both, but the ORCHESTRATION logic that
    creates/uses it (`RF-One Web/training_integration.py`) stays local to
    the RF-One Web ↔ Training integration point — neither `RFOneAccount`
    nor `TrainingAccount`/Training's own service module is coupled to the
    other by this table's mere existence (Core Principle: a general
    account must not be coupled to any one Domain)."""

    __tablename__ = "rfone_training_identity_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rfone_account_id: Mapped[int] = mapped_column(
        ForeignKey("rfone_accounts.id"), nullable=False, unique=True
    )
    training_account_id: Mapped[int] = mapped_column(
        ForeignKey("training_accounts.id"), nullable=False, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    rfone_account: Mapped["RFOneAccount"] = relationship()
    training_account: Mapped["TrainingAccount"] = relationship()


class RFOneAccountVerificationCode(Base):
    """One issued 6-digit code for one `RFOneAccount`, scoped to exactly one
    `purpose` — the single mechanism behind BOTH email verification and
    password recovery (`rfone_recovery_service.py`), never a per-Domain or
    per-purpose duplicate table. A code issued for one purpose is never
    valid for the other (every lookup filters on `purpose` too).

    `code_hmac` is never the raw code nor a bare hash of it — it is an
    HMAC-SHA256 keyed with a value derived from the server's own
    `RFONE_FLASK_SECRET_KEY` (see `rfone_recovery_service._hash_code`), so
    a database-only compromise cannot brute-force this small (6-digit)
    space offline; the code's short life (`expires_at`, 10 minutes) and
    `attempts_used` cap (5) bound the ONLINE guessing surface. `target_email`
    is the address the code was actually sent to, denormalized here rather
    than read from `RFOneAccount.email` at verification time — so a
    profile email change started after a code was issued can never make an
    older, already-sent code silently apply to a different address.

    `consumed_at` and `invalidated_at` are separate and mutually exclusive
    in practice: `consumed_at` marks a code actually used to complete its
    purpose (set exactly once, inside a row lock, so two concurrent
    submissions of the same code can never both succeed);
    `invalidated_at` marks a code superseded before use (a resend,
    expiry, exhausted attempts, or an unrelated successful password reset/
    email change clearing out anything else still pending for the
    account)."""

    __tablename__ = "rfone_account_verification_codes"
    __table_args__ = (
        CheckConstraint(
            "purpose IN ('EMAIL_VERIFICATION', 'PASSWORD_RESET')", name="ck_rfone_verification_code_purpose",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("rfone_accounts.id"), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(24), nullable=False)
    target_email: Mapped[str] = mapped_column(String(255), nullable=False)
    code_hmac: Mapped[str] = mapped_column(String(64), nullable=False)
    attempts_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    request_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    account: Mapped["RFOneAccount"] = relationship()



# ---------------------------------------------------------------------------
# Canonical Financial Model Convergence — Phase 1 (FINANCIAL_MODEL_
# CONVERGENCE_001). `PaymentInstrument` is the single canonical identity for
# a financial/payment instrument — a Bank Account, a Credit Card, or a
# PayPal account. It absorbs the source-resolution fields
# (`institution`/`last_four`/`external_account_identifier`) an earlier,
# CSV-only `FinancialAccount` model used for the same purpose; that model
# is not migrated, modified, or retired by this phase — this table is
# additive only. Deliberately only these three `instrument_type` values
# (approved convergence plan — "Do not invent additional instrument
# types"); not a speculative plugin architecture for arbitrary future
# providers.
# ---------------------------------------------------------------------------


class PaymentInstrument(Base):
    """A financial/payment instrument that can originate reconciliation-
    participating transactions — a Bank Account, a Credit Card, or a
    PayPal account.

    `institution`/`last_four`/`external_account_identifier` are absorbed
    from the earlier `FinancialAccount` model's source-resolution fields
    (e.g. CHASE/FIRST_CITIZENS institution matching, last-four-digit and
    external-account-number matching a source file's own identifier to
    this instrument) — required by existing source-resolution behavior,
    not invented for this phase. `external_account_identifier` is the one
    canonical field for a source's external account identifier; it is not
    duplicated as a second, separately-named column.

    `linked_instrument_id` records a known settlement/funding relationship
    to another `PaymentInstrument` (e.g. a PayPal account's linked bank
    account, or a Credit Card's linked payment bank account) — self-
    referential, many-to-one (several instruments may settle to the same
    bank account). `source_system_id` names the connector this instrument
    is (or will be) synchronized from — NULL for an instrument reconciled
    only from manual/human-entered transactions."""

    __tablename__ = "payment_instruments"
    __table_args__ = (
        CheckConstraint(
            "instrument_type IN ('BANK_ACCOUNT', 'CREDIT_CARD', 'PAYPAL')",
            name="ck_pi_instrument_type",
        ),
        CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name="ck_pi_status"),
        Index("ix_pi_legal_entity_id", "legal_entity_id"),
        Index("ix_pi_linked_instrument_id", "linked_instrument_id"),
        Index("ix_pi_source_system_id", "source_system_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    legal_entity_id: Mapped[int | None] = mapped_column(ForeignKey("legal_entities.id"), nullable=True)

    instrument_type: Mapped[str] = mapped_column(String(16), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Source-resolution data absorbed from `FinancialAccount` (spec §3.2,
    # §5.2 of the earlier Bank Reconciliation V1 task) — used to
    # automatically match a source row to this instrument when the source
    # file/feed itself carries an identifier. Never used to invent a Legal
    # Entity or instrument identity on its own.
    institution: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_four: Mapped[str | None] = mapped_column(String(4), nullable=True)
    external_account_identifier: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)

    linked_instrument_id: Mapped[int | None] = mapped_column(
        ForeignKey("payment_instruments.id"), nullable=True
    )
    source_system_id: Mapped[int | None] = mapped_column(ForeignKey("source_systems.id"), nullable=True)

    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    legal_entity: Mapped["LegalEntity | None"] = relationship()
    linked_instrument: Mapped["PaymentInstrument | None"] = relationship(
        remote_side=[id], foreign_keys=[linked_instrument_id]
    )
    source_system: Mapped["SourceSystem | None"] = relationship()


# ---------------------------------------------------------------------------
# Canonical Financial Model Convergence — Phase 3 (FINANCIAL_MODEL_
# CONVERGENCE_001). `BankImportBatch`/`RawBankTransaction` are the CSV-
# specific, source-layer provenance models ported from the proven Bank
# Reconciliation V1 vertical slice (`feature/bank-reconciliation-mvp`) —
# whole-file preservation and per-row raw preservation. Their shape and
# behavior are unchanged from V1; only their identity references are
# retargeted to the canonical model: `financial_account_id` ->
# `payment_instrument_id` (-> `PaymentInstrument.id`), and
# `RawBankTransaction.normalized_transaction_id` -> `FinancialTransaction.id`
# (was `NormalizedFinancialTransaction.id`). Per Product Owner decision,
# these remain CSV-specific — a future connector-sourced acquisition
# (PayPal, Mercury) is not expected to use them, exactly as it does not use
# them on the source branch today.
# ---------------------------------------------------------------------------


class BankImportBatch(Base):
    """One manual CSV upload (spec §4, "Import Batch"). Idempotent by
    content hash (`sha256`, unique): re-uploading the exact same bytes must
    never create a second batch (spec §8, condition 1) — the caller reuses
    the existing row instead. `raw_file_bytes` is the durable, unmodified
    preservation of the file exactly as received (spec §4.1) — stored
    inline rather than on a new AWS resource (no new infrastructure was
    authorized for this vertical slice)."""

    __tablename__ = "bank_import_batches"
    __table_args__ = (
        UniqueConstraint("sha256", name="uq_bank_import_batches_sha256"),
        CheckConstraint(
            "detected_format IN ("
            "'CHASE_BANK_ACCOUNT', 'CHASE_CREDIT_CARD_WITH_CARD', "
            "'CHASE_CREDIT_CARD_NO_CARD', 'FIRST_CITIZENS')",
            name="ck_bank_import_batch_detected_format",
        ),
        CheckConstraint(
            "status IN ('RECEIVED', 'PARSED', 'NORMALIZED', 'REQUIRES_REVIEW', 'ACCEPTED', 'REJECTED')",
            name="ck_bank_import_batch_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    detected_format: Mapped[str] = mapped_column(String(48), nullable=False)
    # Resolved instrument for this batch. NULL until a human confirms it for
    # formats where the file itself carries no reliable identifier (Chase
    # bank accounts; Chase credit card Variant B) — spec §3.2: a file name
    # may be used only as a hint in the upload UI, never as the authoritative
    # identity of the instrument (never stored as authoritative resolution
    # here).
    payment_instrument_id: Mapped[int | None] = mapped_column(
        ForeignKey("payment_instruments.id"), nullable=True
    )

    original_file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_file_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    uploaded_by_account_id: Mapped[int | None] = mapped_column(ForeignKey("rfone_accounts.id"), nullable=True)

    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    date_range_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_range_end: Mapped[date | None] = mapped_column(Date, nullable=True)

    status: Mapped[str] = mapped_column(String(24), nullable=False, default="RECEIVED", server_default="RECEIVED")
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Informational only (spec §8, condition 3) — a later download's date
    # range overlapping an earlier accepted batch for the SAME instrument.
    # Never blocks the import; surfaced to the human reviewer as-is.
    overlap_warning: Mapped[str | None] = mapped_column(Text, nullable=True)

    payment_instrument: Mapped["PaymentInstrument | None"] = relationship()
    raw_rows: Mapped[list["RawBankTransaction"]] = relationship(back_populates="import_batch")


class RawBankTransaction(Base):
    """One row of a `BankImportBatch`, exactly as received (spec §4.1) —
    every original field is preserved in `raw_fields`, including columns
    unused by normalization. Never discarded, never overwritten."""

    __tablename__ = "raw_bank_transactions"
    __table_args__ = (
        UniqueConstraint("import_batch_id", "row_number", name="uq_raw_bank_transaction_batch_row"),
        CheckConstraint(
            "parse_status IN ('PARSED', 'ANOMALOUS', 'UNREADABLE')", name="ck_raw_bank_transaction_parse_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    import_batch_id: Mapped[int] = mapped_column(
        ForeignKey("bank_import_batches.id"), nullable=False, index=True
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # Every original column -> raw string value, verbatim (spec §4.1: unused
    # fields must not be discarded). Never re-derived from the normalized row.
    raw_fields: Mapped[dict] = mapped_column(JSON, nullable=False)
    row_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    parse_status: Mapped[str] = mapped_column(String(16), nullable=False)
    anomalies: Mapped[str | None] = mapped_column(Text, nullable=True)

    normalized_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("financial_transactions.id"), nullable=True
    )

    import_batch: Mapped["BankImportBatch"] = relationship(back_populates="raw_rows")
    normalized_transaction: Mapped["FinancialTransaction | None"] = relationship(
        foreign_keys=[normalized_transaction_id],
    )


# ---------------------------------------------------------------------------
# Canonical Financial Model Convergence — Phase 2/3 (FINANCIAL_MODEL_
# CONVERGENCE_001). `FinancialTransaction` is the single normalized
# transaction ledger for every financial-movement source (bank/credit-card
# CSV import, PayPal API, future connectors) — acquisition mechanism never
# determines transaction identity. Neither `NormalizedFinancialTransaction`
# nor `PaymentInstrumentTransaction` (the two pre-convergence ledgers this
# table replaces) is created or ported here — they do not exist on this
# branch and are not reintroduced.
#
# `explanation_id` remains deliberately OMITTED — `BankTransactionExplanation`
# has not been ported yet (Recognition is explicitly excluded from Phase 3),
# and a nullable FK to a table that does not exist would be unsafe. It is
# deferred to the phase that ports Recognition/Explanation.
#
# `import_batch_id` is now a proper FK to `bank_import_batches.id` (Phase 3
# ports `BankImportBatch`) — still nullable, since an API-sourced
# transaction (e.g. a future PayPal row) will not have a CSV import batch.
#
# Several fields proven necessary by the existing CSV Bank Reconciliation
# implementation (`bank_source`, `description_original`, `fingerprint`,
# `occurrence_index_in_batch`/`occurrence_count_in_batch`,
# `duplicate_status`, `review_status`, `source_row_number`) remain nullable,
# unlike their CSV-only predecessor, because an API-sourced transaction
# legitimately does not use the CSV-specific duplicate-detection/review
# mechanism.
# ---------------------------------------------------------------------------


class FinancialTransaction(Base):
    """The canonical, source-independent financial movement fact — the
    single ledger cross-ledger reconciliation, Bank Recognition, and
    internal-transfer matching will eventually all read and write,
    regardless of whether the movement arrived via CSV import or a
    connector API. Not yet written to by any code in this phase.

    Three separate date/time concepts are preserved per explicit Product
    Owner decision (FINANCIAL_MODEL_CONVERGENCE_001 §5) and never
    collapsed into one: `posting_date` (accounting/posting/settlement date
    when a source supplies it), `transaction_date` (business/source
    transaction date, when supplied separately from `posting_date`), and
    `transaction_datetime` (precise source timestamp, when available —
    particularly from API sources such as PayPal). All three are nullable:
    an API source may supply `transaction_datetime` without a distinct
    accounting posting date, and a future adapter decides which fields it
    populates — no adapter is implemented by this phase.

    `amount_minor` is the canonical signed amount in minor currency units
    (never floating point) — the one fact every source must supply.
    `gross_amount_minor`/`fee_amount_minor`/`net_amount_minor` remain
    nullable, for sources (e.g. PayPal) that provide an explicit
    gross/fee/net breakdown; none is inferred or calculated here.

    `classification` (WHAT kind of movement) lives directly on this table
    and defaults to `UNKNOWN` — the proven five-value vocabulary is
    preserved verbatim; no classification logic is implemented by this
    phase. Occurrence (WHO) and Reason (WHY) remain distinct concepts not
    represented on this table in Phase 2.

    `(payment_instrument_id, external_transaction_id)` is unique whenever
    `external_transaction_id` is not NULL — the same idempotency rule
    PayPal ingestion already relies on (standard SQL/SQLite semantics:
    multiple NULLs in a unique column never conflict with each other)."""

    __tablename__ = "financial_transactions"
    __table_args__ = (
        UniqueConstraint(
            "payment_instrument_id", "external_transaction_id",
            name="uq_ft_instrument_external_id",
        ),
        CheckConstraint(
            "classification IN ('REVENUE', 'EXPENSE', 'INTERNAL_TRANSFER', 'FEE', 'UNKNOWN')",
            name="ck_ft_classification",
        ),
        CheckConstraint(
            "status IN ('COMPLETED', 'PENDING', 'REVERSED', 'FAILED', 'UNKNOWN')",
            name="ck_ft_status",
        ),
        CheckConstraint(
            "duplicate_status IS NULL OR duplicate_status IN "
            "('NONE', 'CANDIDATE_DUPLICATE', 'CONFIRMED_DUPLICATE', 'CONFIRMED_DISTINCT')",
            name="ck_ft_duplicate_status",
        ),
        CheckConstraint(
            "review_status IS NULL OR review_status IN ('REQUIRES_REVIEW', 'REVIEWED', 'ACCEPTED')",
            name="ck_ft_review_status",
        ),
        Index("ix_ft_instrument_posting_date_amount", "payment_instrument_id", "posting_date", "amount_minor"),
        Index("ix_ft_instrument_datetime", "payment_instrument_id", "transaction_datetime"),
        Index("ix_ft_source_system_id", "source_system_id"),
        Index("ix_ft_fingerprint", "fingerprint"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # --- Core identity / provenance linkage --------------------------------
    payment_instrument_id: Mapped[int] = mapped_column(
        ForeignKey("payment_instruments.id"), nullable=False, index=True
    )
    source_system_id: Mapped[int | None] = mapped_column(ForeignKey("source_systems.id"), nullable=True)
    external_transaction_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # --- Bank/source facts ---------------------------------------------------
    bank_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    posting_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    transaction_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    transaction_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    description_original: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_normalized: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    native_transaction_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    balance_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="UNKNOWN")

    # --- CSV provenance linkage ----------------------------------------------
    import_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("bank_import_batches.id"), nullable=True
    )
    source_row_number: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # --- Duplicate-detection / occurrence fields ------------------------------
    fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    occurrence_index_in_batch: Mapped[int | None] = mapped_column(Integer, nullable=True)
    occurrence_count_in_batch: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duplicate_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    duplicate_of_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("financial_transactions.id"), nullable=True
    )

    # --- Review linkage ---------------------------------------------------
    review_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    # Canonical Financial Model Convergence — Phase 4B (Product Owner
    # Decision 6): the CURRENT canonical reconciliation decision — always
    # the same row `bank_reconciliation.recognition.get_current_
    # explanation` would resolve for this transaction. Every new current
    # decision row (RULE or HUMAN, via `recognition._create_decision_row`)
    # updates this pointer; Kermali export (`bank_reconciliation/
    # export.py`) reads that row's immutable snapshot fields through it.
    # Older decision rows remain queryable history but are never pointed
    # to by this column once superseded.
    explanation_id: Mapped[int | None] = mapped_column(
        ForeignKey("bank_transaction_explanations.id"), nullable=True
    )

    # --- PayPal/API-capable facts -------------------------------------------
    gross_amount_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fee_amount_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    net_amount_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    counterparty_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    counterparty_identifier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    related_external_transaction_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # --- Business classification (WHAT) ---------------------------------------
    classification: Mapped[str] = mapped_column(String(16), nullable=False, default="UNKNOWN")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    payment_instrument: Mapped["PaymentInstrument"] = relationship()
    source_system: Mapped["SourceSystem | None"] = relationship()
    import_batch: Mapped["BankImportBatch | None"] = relationship()
    duplicate_of: Mapped["FinancialTransaction | None"] = relationship(
        remote_side="FinancialTransaction.id",
    )
    # Explicit foreign_keys required since `bank_transaction_explanations`
    # also carries the opposite-direction `financial_transaction_id` FK
    # back to this table (BANK_RECONCILIATION_EXPERT_SYSTEM_001), making
    # the join otherwise ambiguous.
    explanation: Mapped["BankTransactionExplanation | None"] = relationship(foreign_keys=[explanation_id])


# ---------------------------------------------------------------------------
# Canonical Financial Model Convergence — Phase 6 (FINANCIAL_MODEL_
# CONVERGENCE_001). `FinancialTransactionMatch` is the canonical cross-
# ledger internal-transfer match, ported from `feature/purchased-invoice-
# intake-alignment`'s proven `PaymentInstrumentTransactionMatch` and
# retargeted to `FinancialTransaction.id` (that branch's
# `PaymentInstrumentTransaction` ledger is not present on this branch and
# is not reintroduced). Renamed from `PaymentInstrumentTransactionMatch` —
# the old name incorrectly implied the now-retired ledger; the canonical
# name reflects what it actually links today.
#
# `updated_at` is deliberately NOT carried over: the source model never had
# one, and a match row is either newly created or an idempotent re-match
# returns the pre-existing row unchanged (`bank_reconciliation/
# matching.py:create_match`) — no code path ever updates an existing match
# row in place, so there is nothing for an `updated_at` to track.
# ---------------------------------------------------------------------------


class FinancialTransactionMatch(Base):
    """One confirmed cross-ledger link between two `FinancialTransaction`
    rows on DIFFERENT Payment Instruments, representing the two sides of
    the same internal movement of funds (e.g. a PayPal "transfer to bank"
    row and the corresponding bank "PayPal transfer" deposit row, or a Bank
    Account "credit card payment" row and the corresponding Credit Card
    "payment received" row). Creating a match never deletes or merges
    either source transaction — both remain independently auditable; it
    only records the link and sets both transactions' `classification` to
    `'INTERNAL_TRANSFER'` (`bank_reconciliation/matching.py:create_match`)
    — never `'REVENUE'`/`'EXPENSE'`.

    `transaction_a_id < transaction_b_id` is DB-enforced so the pair has
    one canonical orientation — `uq_ftm_pair` then makes re-matching the
    same pair idempotent rather than silently allowed to duplicate in
    either order (A<->B and B<->A can never both exist).

    `match_method` distinguishes an automatic match (`auto_match_
    transaction`, created only when amount/direction/currency/date/
    instrument-link all hold exactly) from a human-confirmed one
    (`confirm_match`, the fallback for insufficient automatic evidence,
    e.g. no `linked_instrument_id` configured yet) — this distinction,
    plus `confirmed_by`, is the auditable record of how RF-One came to
    know the relationship."""

    __tablename__ = "financial_transaction_matches"
    __table_args__ = (
        UniqueConstraint("transaction_a_id", "transaction_b_id", name="uq_ftm_pair"),
        CheckConstraint("match_type IN ('INTERNAL_TRANSFER')", name="ck_ftm_match_type"),
        CheckConstraint("match_method IN ('AUTO', 'HUMAN')", name="ck_ftm_match_method"),
        CheckConstraint("transaction_a_id < transaction_b_id", name="ck_ftm_ordered_pair"),
        Index("ix_ftm_transaction_a_id", "transaction_a_id"),
        Index("ix_ftm_transaction_b_id", "transaction_b_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    transaction_a_id: Mapped[int] = mapped_column(
        ForeignKey("financial_transactions.id"), nullable=False
    )
    transaction_b_id: Mapped[int] = mapped_column(
        ForeignKey("financial_transactions.id"), nullable=False
    )

    match_type: Mapped[str] = mapped_column(String(24), nullable=False, default="INTERNAL_TRANSFER")
    match_method: Mapped[str] = mapped_column(String(8), nullable=False)
    match_basis: Mapped[str | None] = mapped_column(Text, nullable=True)
    matched_amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    confirmed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    transaction_a: Mapped["FinancialTransaction"] = relationship(foreign_keys=[transaction_a_id])
    transaction_b: Mapped["FinancialTransaction"] = relationship(foreign_keys=[transaction_b_id])


# ---------------------------------------------------------------------------
# Canonical Financial Model Convergence — Phase 4 (FINANCIAL_MODEL_
# CONVERGENCE_001). Bank Reconciliation — incremental expert system for WHO
# is involved in a bank movement and WHY it exists
# (BANK_RECONCILIATION_EXPERT_SYSTEM_001), ported from the preserved
# in-progress work on `feature/bank-reconciliation-mvp`. Explicitly NOT a
# cost-family/cost-type classifier: `BankOccurrence` and
# `BankTransactionReason` never carry Food Cost/Operative/Deductible-style
# fields — that classification comes from invoices (Invoice Intake/
# Purchased), never from a bank movement alone. `Supplier` is only one of
# several possible `BankOccurrenceType` values, never assumed by default.
#
# Canonical adaptation: `BankRecognitionRule.financial_account_id` ->
# `payment_instrument_id` (-> `PaymentInstrument.id`); `BankTransaction
# Explanation.normalized_financial_transaction_id` -> `financial_transaction_id`
# (-> `FinancialTransaction.id`, was `NormalizedFinancialTransaction.id`).
# No business behavior is changed by either rename.
# ---------------------------------------------------------------------------


class BankOccurrenceType(Base):
    """Controlled vocabulary for the TYPE of subject a bank movement
    involves (spec: "la tipologia del soggetto coinvolto"). Deliberately
    carries no cost-family/cost-type field of any kind — a type answers
    "what kind of party is this," never "what did this movement pay for.\""""

    __tablename__ = "bank_occurrence_types"
    __table_args__ = (
        UniqueConstraint("code", name="uq_bank_occurrence_type_code"),
        CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name="ck_bank_occurrence_type_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE", server_default="ACTIVE")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class BankOccurrence(Base):
    """The subject concretely recognized in a bank movement — "chi o cosa
    è coinvolto" — e.g. US Foods, ADP, Chase, Florida Department of
    Revenue. Never named/assumed to be a Supplier: its `occurrence_type`
    may be any `BankOccurrenceType` (spec: "Supplier è soltanto una
    possibile tipologia del soggetto coinvolto")."""

    __tablename__ = "bank_occurrences"
    __table_args__ = (
        UniqueConstraint("canonical_name", name="uq_bank_occurrence_canonical_name"),
        CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name="ck_bank_occurrence_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(255), nullable=False)
    occurrence_type_id: Mapped[int] = mapped_column(ForeignKey("bank_occurrence_types.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE", server_default="ACTIVE")
    optional_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    occurrence_type: Mapped["BankOccurrenceType"] = relationship()


class BankTransactionReason(Base):
    """Controlled vocabulary for WHY a bank movement exists (spec: "perché
    la transazione esiste") — e.g. SUPPLIER_INVOICE_PAYMENT, PAYROLL,
    TAX_PAYMENT. Independent of, and never a substitute for, invoice-side
    cost family/type/composition."""

    __tablename__ = "bank_transaction_reasons"
    __table_args__ = (
        UniqueConstraint("code", name="uq_bank_transaction_reason_code"),
        CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name="ck_bank_transaction_reason_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE", server_default="ACTIVE")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    export_mapping: Mapped["BankTransactionReasonExportMapping | None"] = relationship(
        back_populates="transaction_reason", uselist=False,
    )


class BankTransactionReasonExportMapping(Base):
    """Canonical Financial Model Convergence — Phase 4B (FINANCIAL_MODEL_
    CONVERGENCE_001, Product Owner Decision 4). The Kermali/accounting
    export attributes a Reason implies — `food_cost`/`operative`/
    `deductible`/`what_label` — are NOT Occurrence, NOT Reason semantics
    themselves, and NOT Explanation audit metadata: they are an export/
    accounting mapping associated with a Reason, kept in its own small,
    bounded model rather than placed directly on `BankTransactionReason`
    (Decision 3: Reason semantics must remain clean — strictly WHY).

    One-to-one with `BankTransactionReason` (`uq_btrem_reason_id`): each
    Reason has at most one export mapping, matching the proven Kermali
    requirement of exactly one Food $/Oper/Deduct/What outcome per
    reconciliation decision. Bank Reconciliation remains not authoritative
    for invoice-level cost-family composition (unchanged repository rule,
    restated on `BankOccurrence`/`BankTransactionReason`) — this mapping
    only feeds the existing Kermali export shape, nothing more.

    A decision row's own snapshot fields (`BankTransactionExplanation`)
    are captured FROM this mapping at decision time and never re-read
    from it afterward — editing a mapping here never changes a historical
    decision's already-exported values (Decision 8)."""

    __tablename__ = "bank_transaction_reason_export_mappings"
    __table_args__ = (
        UniqueConstraint("bank_transaction_reason_id", name="uq_btrem_reason_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bank_transaction_reason_id: Mapped[int] = mapped_column(
        ForeignKey("bank_transaction_reasons.id"), nullable=False
    )
    food_cost: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("0"))
    operative: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("0"))
    deductible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("0"))
    what_label: Mapped[str | None] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    transaction_reason: Mapped["BankTransactionReason"] = relationship(back_populates="export_mapping")


class BankRecognitionRule(Base):
    """Reusable knowledge learned from confirmed human decisions (spec:
    "le decisioni umane confermate devono diventare conoscenza
    riutilizzabile"). `auto_apply_enabled` can only become true as the
    direct result of an explicit human confirmation
    (`bank_reconciliation.recognition`) — it is never inferred from a
    confirmation/contradiction count (no numeric promotion threshold is
    implemented, by explicit Product Owner instruction).

    `CONTAINS_TEXT`/`PREFIX` rules may exist only because a human
    explicitly chose that broader match type; `EXACT_NORMALIZED_
    DESCRIPTION` is the only match type a plain "reuse this decision"
    confirmation may create on its own."""

    __tablename__ = "bank_recognition_rules"
    __table_args__ = (
        CheckConstraint(
            "match_type IN ('EXACT_NORMALIZED_DESCRIPTION', 'CONTAINS_TEXT', 'PREFIX')",
            name="ck_bank_recognition_rule_match_type",
        ),
        CheckConstraint(
            "direction IS NULL OR direction IN ('DEBIT', 'CREDIT')",
            name="ck_bank_recognition_rule_direction",
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'INACTIVE', 'NEEDS_REVIEW')",
            name="ck_bank_recognition_rule_status",
        ),
        Index("ix_bank_recognition_rule_pattern", "normalized_pattern"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_type: Mapped[str] = mapped_column(String(32), nullable=False)
    normalized_pattern: Mapped[str] = mapped_column(Text, nullable=False)
    # NULL = applies to any Payment Instrument; set = scoped to one instrument.
    payment_instrument_id: Mapped[int | None] = mapped_column(ForeignKey("payment_instruments.id"), nullable=True)
    # NULL = applies regardless of direction. DEBIT = amount_minor < 0,
    # CREDIT = amount_minor >= 0 (same sign convention as the normalized
    # Amount — spec §3.3).
    direction: Mapped[str | None] = mapped_column(String(8), nullable=True)
    occurrence_id: Mapped[int] = mapped_column(ForeignKey("bank_occurrences.id"), nullable=False, index=True)
    transaction_reason_id: Mapped[int] = mapped_column(ForeignKey("bank_transaction_reasons.id"), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE", server_default="ACTIVE")
    auto_apply_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("0"))
    human_confirmations: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    human_contradictions: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_from_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("financial_transactions.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    payment_instrument: Mapped["PaymentInstrument | None"] = relationship()
    occurrence: Mapped["BankOccurrence"] = relationship()
    transaction_reason: Mapped["BankTransactionReason"] = relationship()
    created_from_transaction: Mapped["FinancialTransaction | None"] = relationship()


class BankTransactionExplanation(Base):
    """The ONE canonical reconciliation decision/audit row for a
    `FinancialTransaction` (Canonical Financial Model Convergence — Phase
    4B, FINANCIAL_MODEL_CONVERGENCE_001, Product Owner Decision 1). One
    row per DECISION EVENT — never updated in place and never deleted, so
    a transaction's full decision history (rule-suggested, auto-applied,
    human-confirmed, human-overridden, ...) accumulates as multiple rows
    over time (BANK_RECONCILIATION_EXPERT_SYSTEM_001, "audit /
    non-overwrite"). The CURRENT decision for a transaction is the
    highest-`id` row with that `financial_transaction_id` — resolved by
    `bank_reconciliation.recognition.get_current_explanation` — and is
    kept in sync with `FinancialTransaction.explanation_id`, which every
    new current decision row updates (Decision 6).

    The legacy, pre-Phase-4B catalog-style generation of this table
    (`name`/`category`/`food_cost`/`operative`/`deductible`/`what_label`/
    `active`, standalone rows with no `financial_transaction_id`) has
    been retired (Decisions 1, 2, 4, 5) — `Supplier/Receiving` is now
    `BankOccurrence.canonical_name` (Decision 2), and the Kermali
    accounting/export attributes (`food_cost`/`operative`/`deductible`/
    `what_label`) now live on `BankTransactionReasonExportMapping`,
    associated with the canonical Reason (Decision 4) — never directly on
    this per-decision row as a live, editable value.

    **Immutable decision snapshot** (Decision 8): `occurrence_name_
    snapshot`/`food_cost_snapshot`/`operative_snapshot`/`deductible_
    snapshot`/`what_label_snapshot` are captured ONCE, at the moment this
    row is created, from `BankOccurrence.canonical_name` and the selected
    Reason's `BankTransactionReasonExportMapping` — never re-read from
    those tables afterward. Kermali export reads ONLY these snapshot
    fields, never the live `BankOccurrence`/`BankTransactionReasonExport
    Mapping` rows, so renaming an Occurrence or editing a Reason's export
    mapping later never changes a historical decision's already-exported
    values. This is a decision-time snapshot, not a second reusable
    catalog and not general historical versioning — `occurrence_id`/
    `transaction_reason_id` remain the canonical FKs for anything that
    needs the live, current vocabulary (e.g. Recognition rule matching).

    Per the Expert System task's explicit boundary: `Food $`/`Oper`/
    `Deduct` are never derived from `occurrence`/`transaction_reason`
    themselves — cost family/type/composition come from invoices (Invoice
    Intake/Purchased), never from Bank Reconciliation; the export mapping
    is a Reason-level accounting attribute, not a reconciliation
    semantic."""

    __tablename__ = "bank_transaction_explanations"
    __table_args__ = (
        CheckConstraint(
            "decision_source IS NULL OR decision_source IN ('HUMAN', 'RULE')",
            name="ck_bank_transaction_explanation_decision_source",
        ),
        CheckConstraint(
            "decision_status IS NULL OR decision_status IN "
            "('SUGGESTED', 'AUTO_APPLIED', 'HUMAN_CONFIRMED', 'HUMAN_OVERRIDDEN', 'NEEDS_HUMAN_REVIEW')",
            name="ck_bank_transaction_explanation_decision_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # --- Canonical decision linkage ----------------------------------------
    financial_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("financial_transactions.id"), nullable=True, index=True
    )
    occurrence_id: Mapped[int | None] = mapped_column(ForeignKey("bank_occurrences.id"), nullable=True)
    transaction_reason_id: Mapped[int | None] = mapped_column(ForeignKey("bank_transaction_reasons.id"), nullable=True)
    recognition_rule_id: Mapped[int | None] = mapped_column(ForeignKey("bank_recognition_rules.id"), nullable=True)
    # Conceptual values: HUMAN, RULE.
    decision_source: Mapped[str | None] = mapped_column(String(8), nullable=True)
    # Conceptual values: SUGGESTED, AUTO_APPLIED, HUMAN_CONFIRMED,
    # HUMAN_OVERRIDDEN, NEEDS_HUMAN_REVIEW. Only AUTO_APPLIED,
    # HUMAN_CONFIRMED and HUMAN_OVERRIDDEN are exportable/resolved states.
    decision_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    # Short descriptive label (e.g. "HIGH"/"MEDIUM"/"LOW"), never a
    # numeric score used to auto-promote a rule (Product Owner: "non
    # inventare una soglia numerica per promuovere autonomamente una
    # regola") — purely explanatory.
    confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Technical rationale sufficient to explain the outcome (e.g. which
    # rule matched, or why multiple candidates disagreed).
    explanation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmed_by_account_id: Mapped[int | None] = mapped_column(ForeignKey("rfone_accounts.id"), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- Immutable decision snapshot (Decision 8) — captured once at
    # creation from BankOccurrence.canonical_name and the selected
    # Reason's BankTransactionReasonExportMapping; never re-read from
    # those tables afterward. Kermali export reads these fields only. ----
    occurrence_name_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    food_cost_snapshot: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    operative_snapshot: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    deductible_snapshot: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    what_label_snapshot: Mapped[str | None] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, server_default=func.now(), onupdate=func.now()
    )

    financial_transaction: Mapped["FinancialTransaction | None"] = relationship(
        foreign_keys=[financial_transaction_id],
    )
    occurrence: Mapped["BankOccurrence | None"] = relationship()
    transaction_reason: Mapped["BankTransactionReason | None"] = relationship()
    recognition_rule: Mapped["BankRecognitionRule | None"] = relationship()

ALL_MODELS: tuple[type[Base], ...] = (
    ActingIdentity,
    AuthorityGrant,
    OperationalSignature,
    SourceSystem,
    IngestionRun,
    SourceRecord,
    Merchant,
    Location,
    PhysicalTable,
    TableService,
    TableServicePhysicalTable,
    Employee,
    SourceRole,
    EmployeeSourceRole,
    TableServiceEmployee,
    Shift,
    Restaurant,
    RestaurantLocation,
    OperationalArea,
    PhysicalArea,
    RestaurantRole,
    OperationalAreaRole,
    EmployeeAssignment,
    TipPolicy,
    TipPolicyComponent,
    OrderType,
    Order,
    Item,
    Category,
    ItemCategory,
    ModifierGroup,
    Modifier,
    ItemModifier,
    OrderItem,
    OrderItemModifier,
    DiscountDefinition,
    OrderDiscount,
    OrderItemDiscount,
    TaxRate,
    OrderItemTax,
    OrderFee,
    Tender,
    Payment,
    PaymentTip,
    Refund,
    Device,
    PayrollSchedule,
    WorkweekDefinition,
    EmployeeCompensationTerm,
    PayrollRun,
    PayrollExecutionConfiguration,
    PayrollProviderEmployeeIdentity,
    EmployeePayrollResult,
    PayrollEarningFact,
    PayrollEmployerLiabilityFact,
    PayrollPaymentFact,
    PayrollImportRun,
    PayrollImportIssue,
    CompensationPreparationRun,
    EmployeePayrollCalculation,
    EmployeePayrollCalculationEarningLine,
    IncentiveContribution,
    ApprovedCompensationSnapshot,
    ApprovedEmployeeCompensationResult,
    ApprovedEmployeeEarningLine,
    ApprovedIncentiveContributionLine,
    CompensationExportConfirmation,
    CompensationReconciliation,
    CompensationReconciliationLine,
    OvertimeRule,
    Supplier,
    PurchaseOrder,
    PurchaseOrderLine,
    SupplierProduct,
    PurchaseDocument,
    PurchaseLine,
    ConfiguredExpectation,
    ReceivingRecord,
    ReceivingLine,
    PurchasingAlert,
    ExpectedSupplierCredit,
    SupplierCreditReference,
    PurchasingValidationLogEntry,
    RawResume,
    Candidate,
    CandidateEducation,
    CandidateWorkHistory,
    CandidateSkill,
    CandidateCertification,
    CandidateLanguage,
    RequirementTemplate,
    RequirementTemplateItem,
    RequirementSet,
    Requirement,
    RequirementSetSnapshot,
    RequirementSnapshotItem,
    FitAssessment,
    RequirementAssessment,
    EvidenceItem,
    CandidatePerson,
    Application,
    SignalDefinition,
    SignalObservation,
    SignalEvidenceItem,
    ReviewPriorityPolicy,
    ReviewPriorityPolicyRule,
    PersonMatchCandidate,
    ApplicationNote,
    PhoneInterviewQuestionDefinition,
    PhoneInterviewPlan,
    PhoneInterviewQuestionInstance,
    InPersonInterviewSectionDefinition,
    AssessmentItemDefinition,
    InPersonInterviewPlan,
    AssessmentItemInstance,
    ConsistencyThread,
    ConsistencyStatement,
    PrimaryScreeningCriterion,
    PrimaryScreeningCriterionSnapshot,
    PrimaryScreeningRun,
    PrimaryScreeningCriterionEvaluation,
    ApplicationStageTransition,
    SelectionOutcomeDefinition,
    SelectionOutcomeDefinitionSnapshot,
    SelectionOutcomeDecision,
    SelectionReminder,
    CandidateFlag,
    SelectionQueue,
    ApplicationQueueMovement,
    SelectionPatternDefinition,
    SelectionPatternDefinitionSnapshot,
    SelectionPatternExample,
    SelectionPatternCaseComparison,
    SelectionPatternObservation,
    SelectionStagePatternSnapshot,
    SelectionStagePatternDelta,
    SelectionLearningTrace,
    SelectionEffort,
    SelectionCaseMemory,
    SelectionDownstreamOutcomeFeedback,
    SelectionAuthorityLevel,
    SelectionGovernanceRequirement,
    TrainableGap,
    SelectionSession,
    SelectionSessionAssignment,
    ApplicationOwnership,
    SelectionRuleSetVersion,
    SelectionRuleChange,
    SelectionRuleChangeImpact,
    AcquisitionSourceDefinition,
    CommunicationTemplate,
    CommunicationTemplateSnapshot,
    CommunicationReminderPolicy,
    CandidateCommunication,
    InterviewSchedulingWindow,
    InterviewAppointment,
    CandidateSchedulingToken,
    InboundCommunication,
    JobPosting,
    JobPostingVersion,
    ChannelDefinition,
    JobPostingChannelVariant,
    JobPostingChannelVariantVersion,
    ChannelPublication,
    ChannelTrackingLink,
    ApplicationQuestionDefinition,
    ApplicationQuestionAnswer,
    MissingEvidenceQuestionnaire,
    MissingEvidenceQuestion,
    MissingEvidenceAnswer,
    ComplianceReview,
    ComplianceWarning,
    ComplianceDisposition,
    TrainingAccount,
    TrainingPill,
    TrainingQuestion,
    TrainingNeed,
    TrainingAssignment,
    TrainingAttempt,
    TrainingOverallAttempt,
    RFOneAccount,
    RFOneAccountDomainAccess,
    RFOneTrainingIdentityLink,
    RFOneAccountVerificationCode,
    PaymentInstrument,
    FinancialTransaction,
    BankImportBatch,
    RawBankTransaction,
    BankOccurrenceType,
    BankOccurrence,
    BankTransactionReason,
    BankTransactionReasonExportMapping,
    BankRecognitionRule,
    BankTransactionExplanation,
    FinancialTransactionMatch,
)
