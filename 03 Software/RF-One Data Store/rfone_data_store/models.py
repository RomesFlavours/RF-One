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

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


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
    # nullable, never defaulted, never invented.
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
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


class Restaurant(Base):
    """The canonical business/operational restaurant RF-One models — NOT
    merely a Clover Merchant object (task §11). Deliberately narrow: this is
    canonical business identity/context, not a duplicate of every Merchant/
    Location field."""

    __tablename__ = "restaurants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

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
    is an application/business-rule concern, not a blanket DB constraint."""

    __tablename__ = "restaurant_locations"

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
    Employee, Area, Role and start instant), not legitimate concurrency."""

    __tablename__ = "employee_assignments"
    __table_args__ = (
        UniqueConstraint(
            "employee_id", "operational_area_id", "restaurant_role_id", "valid_from"
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
# Tips (TASK_TIPS_001)
#
# The canonical Tip fact itself is NOT redefined here — it remains
# `PaymentTip`, attached to `Payment` (task §3). This section adds only the
# post-hoc *calculation* apparatus: a temporally-scoped, Restaurant-configured
# Tip Policy, and the atomic, auditable results of running that policy over
# already-recorded PaymentTips. No new Tip timestamp is introduced anywhere
# below — every table that needs "when" reaches it through the parent
# Payment (`payments.created_at`), never its own column.
# ---------------------------------------------------------------------------


class TipPolicy(Base):
    """A Restaurant-configured, temporally valid Tip allocation policy
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
    """One share of a `TipPolicy` (task §9-12). `recipient_basis` is never
    reduced to a hard-coded role/name — `SERVICE_OWNER` routes to whatever
    the service-attribution resolver returns for the Order (never
    `Order.employee`/`Payment.employee` directly, task §5-6);
    `ROLE_PRESENT_AT_PAYMENT` routes to whichever Employees the Restaurant's
    own `RestaurantRole`/`EmployeeAssignment` data say were both present
    (Shift) and assigned to that Role at the Payment timestamp (task §7)."""

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


class TipCalculationRun(Base):
    """One execution of the post-hoc Tip calculation engine over a requested
    period (task §17, §20, §27) — supports reproducibility/auditability
    (task §28) and safe dry-run-by-default operation (task §27)."""

    __tablename__ = "tip_calculation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("restaurants.id"), nullable=False, index=True
    )

    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Conceptual values: RUNNING, COMPLETE, FAILED.
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    # DRY_RUN (default/safe) or PERSIST (task §27) — a DRY_RUN run's
    # TipAllocation/TipCalculationIssue rows, if any are materialized at all,
    # are still real rows tagged to this run for inspection, but the CLI
    # never asks the caller to treat a DRY_RUN run's numbers as final.
    mode: Mapped[str] = mapped_column(String(16), nullable=False)

    # Human-readable summary of what this run actually used — e.g. which
    # TipPolicy id/version applied, for reproducibility (task §28). Never a
    # substitute for the FK-traceable detail on each TipAllocation/Issue row.
    calculation_version: Mapped[str] = mapped_column(String(64), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    allocations: Mapped[list["TipAllocation"]] = relationship(back_populates="calculation_run")
    issues: Mapped[list["TipCalculationIssue"]] = relationship(back_populates="calculation_run")


class TipAllocation(Base):
    """One atomic, auditable unit of allocated Tip money (task §17, §28) —
    "Employee X received $Y from PaymentTip Z because <policy component,
    recipient basis, eligible set, split method, rounding>." Never an opaque
    total: every row traces to exactly one `TipPolicyComponent` and one
    `PaymentTip`/`Payment`/`Order`."""

    __tablename__ = "tip_allocations"
    __table_args__ = (
        UniqueConstraint(
            "calculation_run_id", "payment_tip_id", "policy_component_id", "employee_id"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    calculation_run_id: Mapped[int] = mapped_column(
        ForeignKey("tip_calculation_runs.id"), nullable=False, index=True
    )

    # PaymentTip's own PK IS `payment_id` (1:0..1 with Payment) — referencing
    # it here does not duplicate anything; `payment_id`/`order_id` are also
    # stored directly (denormalized) purely so an allocation can be traced
    # and reported without a join, per task §17's explicit field list.
    payment_tip_id: Mapped[int] = mapped_column(
        ForeignKey("payment_tips.payment_id"), nullable=False, index=True
    )
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id"), nullable=False, index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)

    policy_component_id: Mapped[int] = mapped_column(
        ForeignKey("tip_policy_components.id"), nullable=False, index=True
    )
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id"), nullable=False, index=True
    )

    # Minor units (cents) — same money convention as every other amount in
    # this schema. Never floating point.
    allocated_amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)

    # Human-readable derivation trail (task §28) — e.g. "component #2
    # ROLE_PRESENT_AT_PAYMENT role=<id>, 2 eligible, EQUAL_ELIGIBLE_HEADCOUNT,
    # base=333 +1 remainder cent". Supplementary to, never a replacement for,
    # the FK trail itself.
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    calculation_run: Mapped[TipCalculationRun] = relationship(back_populates="allocations")


class TipCalculationIssue(Base):
    """A blocking or warning condition raised while calculating Tips for one
    calculation run (task §18) — the engine's explicit alternative to
    guessing. `payment_tip_id`/`payment_id`/`order_id` are nullable because
    some issues are run-scoped (e.g. `NO_VALID_POLICY` for the whole
    restaurant/period) rather than tied to one specific PaymentTip."""

    __tablename__ = "tip_calculation_issues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    calculation_run_id: Mapped[int] = mapped_column(
        ForeignKey("tip_calculation_runs.id"), nullable=False, index=True
    )

    payment_tip_id: Mapped[int | None] = mapped_column(
        ForeignKey("payment_tips.payment_id"), nullable=True, index=True
    )
    payment_id: Mapped[int | None] = mapped_column(
        ForeignKey("payments.id"), nullable=True, index=True
    )
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True, index=True)

    # Conceptual values (task §18): NO_VALID_POLICY, SERVICE_OWNER_UNRESOLVED,
    # SERVICE_OWNER_AMBIGUOUS, NO_ELIGIBLE_RECIPIENT, SHIFT_ASSIGNMENT_GAP,
    # CONFLICTING_ASSIGNMENTS (reserved — not currently raised; concurrent
    # Assignments under a different Role are not a conflict, TASK_TIPS_002),
    # FAILED_PAYMENT_WITH_TIP, REFUND_REVIEW_REQUIRED,
    # ALLOCATION_RECONCILIATION_FAILURE. Free string, not a DB enum — only
    # the subset actually produced by real engine logic is ever written.
    issue_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # Conceptual values: BLOCKING, WARNING (task §18).
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    details: Mapped[str] = mapped_column(Text, nullable=False)
    # Reserved for a future review workflow (task §17's suggested field
    # list) — nullable, unused by this task's engine logic beyond being
    # left NULL ("unreviewed") on every issue it creates.
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    calculation_run: Mapped[TipCalculationRun] = relationship(back_populates="issues")


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

    source_system_id: Mapped[int] = mapped_column(ForeignKey("source_systems.id"), nullable=False)
    source_order_id: Mapped[str] = mapped_column(String(128), nullable=False)

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

    source_system_id: Mapped[int] = mapped_column(ForeignKey("source_systems.id"), nullable=False)
    source_item_id: Mapped[str] = mapped_column(String(128), nullable=False)

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

    source_system_id: Mapped[int] = mapped_column(ForeignKey("source_systems.id"), nullable=False)
    source_category_id: Mapped[str] = mapped_column(String(128), nullable=False)

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

    source_system_id: Mapped[int] = mapped_column(ForeignKey("source_systems.id"), nullable=False)
    source_modifier_group_id: Mapped[str] = mapped_column(String(128), nullable=False)

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

    source_system_id: Mapped[int] = mapped_column(ForeignKey("source_systems.id"), nullable=False)
    source_modifier_id: Mapped[str] = mapped_column(String(128), nullable=False)

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

    source_system_id: Mapped[int] = mapped_column(ForeignKey("source_systems.id"), nullable=False)
    source_line_item_id: Mapped[str] = mapped_column(String(128), nullable=False)

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

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_item_id: Mapped[int] = mapped_column(
        ForeignKey("order_items.id"), nullable=False, index=True
    )
    modifier_id: Mapped[int | None] = mapped_column(ForeignKey("modifiers.id"), nullable=True)

    source_system_id: Mapped[int] = mapped_column(ForeignKey("source_systems.id"), nullable=False)
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

    source_system_id: Mapped[int] = mapped_column(ForeignKey("source_systems.id"), nullable=False)
    source_discount_id: Mapped[str] = mapped_column(String(128), nullable=False)

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

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False)
    discount_definition_id: Mapped[int | None] = mapped_column(
        ForeignKey("discount_definitions.id"), nullable=True
    )

    source_system_id: Mapped[int] = mapped_column(ForeignKey("source_systems.id"), nullable=False)
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

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_item_id: Mapped[int] = mapped_column(
        ForeignKey("order_items.id"), nullable=False, index=True
    )
    discount_definition_id: Mapped[int | None] = mapped_column(
        ForeignKey("discount_definitions.id"), nullable=True
    )

    source_system_id: Mapped[int] = mapped_column(ForeignKey("source_systems.id"), nullable=False)
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

    source_system_id: Mapped[int] = mapped_column(ForeignKey("source_systems.id"), nullable=False)
    source_tax_rate_id: Mapped[str] = mapped_column(String(128), nullable=False)

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

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_item_id: Mapped[int] = mapped_column(
        ForeignKey("order_items.id"), nullable=False, index=True
    )
    tax_rate_id: Mapped[int | None] = mapped_column(ForeignKey("tax_rates.id"), nullable=True)

    amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rate_applied: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)

    source_system_id: Mapped[int] = mapped_column(ForeignKey("source_systems.id"), nullable=False)
    source_tax_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)

    order_item: Mapped[OrderItem] = relationship(back_populates="taxes")


class OrderFee(Base):
    """Supports native fee mechanisms (e.g. Clover's synthetic Service
    Charge line item) while preserving provenance to the source line —
    task §27. Ordinary Items are never auto-classified as fees by name."""

    __tablename__ = "order_fees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False)

    source_system_id: Mapped[int] = mapped_column(ForeignKey("source_systems.id"), nullable=False)
    source_fee_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Raw reference to the synthetic OrderItem-shaped source line this fee
    # was reconstructed from, if any — provenance only, not a hard FK.
    source_line_item_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    fee_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)

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

    source_system_id: Mapped[int] = mapped_column(ForeignKey("source_systems.id"), nullable=False)
    source_tender_id: Mapped[str] = mapped_column(String(128), nullable=False)

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

    source_system_id: Mapped[int] = mapped_column(ForeignKey("source_systems.id"), nullable=False)
    source_payment_id: Mapped[str] = mapped_column(String(128), nullable=False)

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

    source_system_id: Mapped[int] = mapped_column(ForeignKey("source_systems.id"), nullable=False)
    source_refund_id: Mapped[str] = mapped_column(String(128), nullable=False)

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

    source_system_id: Mapped[int] = mapped_column(ForeignKey("source_systems.id"), nullable=False)
    source_device_id: Mapped[str] = mapped_column(String(128), nullable=False)

    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    device_type: Mapped[str | None] = mapped_column(String(64), nullable=True)


# ---------------------------------------------------------------------------
# Payroll (TASK_PAYROLL_001) — Administration Domain, transversal, independent
# from Restaurant / Personnel Management / ADP / jurisdiction labor law. See
# `01 Domains/Administration/Payroll/` for the Domain-level definitions this
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
    row with its own `valid_from`."""

    __tablename__ = "employee_compensation_terms"
    __table_args__ = (
        UniqueConstraint("employee_id", "function_label", "valid_from"),
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

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    employee_results: Mapped[list["EmployeePayrollResult"]] = relationship(back_populates="payroll_run")


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
    # local directory structure) plus its content hash for idempotency.
    source_file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_file_hash: Mapped[str] = mapped_column(String(128), nullable=False)

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


ALL_MODELS: tuple[type[Base], ...] = (
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
    TipCalculationRun,
    TipAllocation,
    TipCalculationIssue,
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
    PayrollProviderEmployeeIdentity,
    EmployeePayrollResult,
    PayrollEarningFact,
    PayrollEmployerLiabilityFact,
    PayrollPaymentFact,
    PayrollImportRun,
    PayrollImportIssue,
)
