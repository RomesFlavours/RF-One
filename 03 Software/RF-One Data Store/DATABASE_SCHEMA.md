# RF-One Data Store — Database Schema

TASK_DATABASE_001 — the first physical RF-One canonical Restaurant operational database, implemented in `rfone_data_store/models.py` (SQLAlchemy 2.x, `Mapped`/`mapped_column` declarative style). Verified against a synthetic (non-Clover) fixture — see `schema_validation.py` and the task report. 61 tables as of TASK_PAYROLL_001 (50 tables as of TASK_RESTAURANT_003 — 46 tables as of TASK_TIPS_001 — 41 tables as of TASK_RESTAURANT_001 — 34 tables as of TASK_CLOVER_004's `source_roles`/`employee_source_roles`, § 4, plus 7 Restaurant Organization tables, § 4a — plus 5 Tips tables, § 4b — plus 4 Restaurant Profile bootstrap tables: `restaurant_profile_source_controls`, `source_role_mappings`, `profile_bootstrap_runs`, `restaurant_profile_reconciliation_issues` — § 4c — plus 11 Payroll tables — § 4d).

This document is about the **physical schema**, not restaurant business meaning — the canonical business model is `01 Domains/Restaurant/Sales/Restaurant Sales Model.md`; the Clover-specific source facts this schema is built from are `03 Software/Clover Data Explorer/CLOVER_DATA_CAPABILITY_MATRIX.md`, `CLOVER_SOURCE_RELATIONSHIP_MAP.md`, `CLOVER_ATOMIC_DERIVED_FACTS.md`, and `CLOVER_RESTAURANT_DATA_MAPPING.md`.

---

## 0. Conventions

- **Table names** are plural snake_case (`orders`, `order_items`); **class names** are singular PascalCase (`Order`, `OrderItem`). `order` is a reserved SQL keyword in most dialects — pluralizing every table name (not just `orders`) keeps the convention uniform rather than special-casing one table.
- **Primary keys**: every table has an RF-One surrogate `id` (`Integer`, autoincrement). No external/source ID is ever the primary key (multi-source future — task §5, §F).
- **Source provenance**: external identity lives in explicit `source_system_id` (FK → `source_systems.id`) and `source_*_id` (string) columns, with `UniqueConstraint(source_system_id, source_*_id)` wherever the source guarantees uniqueness (see § 9).
- **Money**: integer minor units (cents), never floating point. See README.md "Numeric conventions".
- **Quantity**: `Numeric(12, 4)`, independent of money — must represent fractional sold units (TASK_CLOVER_003 finding).
- **Rates/percentages**: canonical decimal `Numeric` values (e.g. `0.065000` = 6.5%), not any source system's internal integer encoding.
- **Timestamps**: `DateTime(timezone=True)`, UTC-normalized at the application/ingestion boundary — never hard-coded to Eastern time, never inventing a Location timezone the source never confirmed.
- **Nullability is a first-class modeling decision**, not an oversight — every "why nullable" is documented per table below, grounded in TASK_CLOVER_003's empirical coverage measurements wherever a real number exists.

---

## 1. Source-system provenance

### `source_systems`

**Purpose:** every source RF-One can ingest from (e.g. `CLOVER`). Never hard-coded elsewhere as the only possible source (task §33).
**PK:** `id`. **Notable columns:** `code` (unique, e.g. `"CLOVER"`), `name`, `active`.
**Cardinality:** referenced by nearly every other table's `source_system_id` (1:N from here outward).

### `ingestion_runs`

**Purpose:** one execution of a source ingestion process — supports future incremental imports and auditability. No ingestion logic is implemented by this task.
**PK:** `id`. **FKs:** `source_system_id` → `source_systems` (required), `location_id` → `locations` (nullable — a run may be merchant-wide before a Location is even known).
**Direct fields:** `started_at` (required), `finished_at`, `status`, `source_window_start/end`, `notes`.
**Nullable and why:** everything except `started_at`/`status`/`source_system_id` — a run may still be in progress (`finished_at` null) or unwindowed (a full historical backfill has no natural window).

### `source_records`

**Purpose:** lightweight raw-provenance record — traceability, not a duplicate data warehouse. Large raw exports (e.g. Clover's existing `data/raw/` JSON) may remain on disk and be referenced via `raw_path` rather than duplicated as `raw_json` (task §35).
**PK:** `id`. **FKs:** `ingestion_run_id`, `source_system_id` (both required).
**Direct fields:** `entity_type`, `source_id`, `retrieved_at` (all required); `payload_hash`, `raw_path`, `raw_json` (all nullable — the task explicitly does not require both `raw_path` and `raw_json` together).
**Index:** `(source_system_id, entity_type, source_id)` — non-unique (the same source record may legitimately be retrieved across multiple ingestion runs, producing multiple `SourceRecord` rows over time; this is history, not a duplicate to be prevented).

---

## 2. Merchant / Location

### `merchants`

**Purpose:** the highest-level canonical business entity.
**PK:** `id`. **Direct fields:** `name` (required), `active`.
**Provenance addition beyond the task's literal suggested field list:** `source_system_id`/`source_merchant_id` (both nullable), with `UniqueConstraint(source_system_id, source_merchant_id)`. The task's §6 suggested field list for Merchant did not include source fields, but modeling principle F ("every canonical entity should have an RF-One primary key and optional source references") applies to Merchant like any other entity currently sourced from Clover — this is a deliberate, documented extension, not a deviation.

### `locations`

**Purpose:** a physical/operational location of a Merchant — modeled as its own entity even though the current Clover source is single-merchant/single-location, because the schema must support future multiple locations (task §6).
**PK:** `id`. **FK:** `merchant_id` → `merchants` (required).
**Direct fields:** `name` (required), `timezone`, `currency`, `active`.
**Nullable and why:** `timezone` — TASK_CLOVER_003 confirmed **no timezone field exists anywhere on the current Clover Merchant object**; this database must never pretend it received a timezone from Clover, so the column stays null until a genuinely source-confirmed or operator-confirmed value exists. `currency` is nullable for the same reason of caution, even though the current Clover Order data is 100% `USD`.
**Provenance addition:** same rationale as Merchant — `source_system_id`/`source_location_id`, unique together.

---

## 3. Physical Table / Table Service

### `physical_tables`

**Purpose:** a persistent restaurant resource (task §7).
**PK:** `id`. **FK:** `location_id` → `locations` (required).
**Direct fields:** `table_number`, `name`, `seat_capacity`, `area`, `indoor_outdoor`, `section` — **all nullable**, because Clover currently exposes no structured Table entity at all (TASK_CLOVER_003 § F: NO for physical table identity, seat capacity, floor/layout as structured Clover data). No source provenance columns exist on this table by design — there is currently no source record to be provenance for; values here, if any, are RF-One/operator-curated, not ingested. **Values are never invented by parsing `Order.title_raw`** — that parsing, if ever implemented, is future ingestion/reconstruction logic, explicitly out of scope here (task §7).

### `table_services`

**Purpose:** the canonical operational service event — "one real service occasion involving a group of guests." Not the physical table, not the POS Order (Restaurant Sales Model §2).
**PK:** `id`. **FK:** `location_id` → `locations` (required).
**Direct/derived split:**
- `declared_guest_count`, `derived_guest_count`, `declared_guest_count_source` — both counts are **independently nullable and intentionally retained side by side**; neither is ever computed from or overwrites the other at the schema level (Restaurant Sales Model §11-12; TASK_CLOVER_003 § G found real orders where they diverge in both directions).
- `reconstruction_status`, `reconstruction_confidence` — placeholders for **future** Table Service reconstruction logic (explicitly not implemented by this task, task §45). Left as an unconstrained `String`/`Numeric(5,4)` rather than a DB-enforced enum, since encoding specific status values now would itself be a form of implementing that logic prematurely.
- `created_at`/`updated_at` — RF-One record-lifecycle timestamps (server-default `now()`), not sourced from Clover.
**Cardinality:** `TableService` is **not** forced 1:1 with `Order` — see `orders.table_service_id` below (1:N, nullable).

### `table_service_physical_tables` (M:N)

**Purpose:** implements `TableService ↔ PhysicalTable` M:N (task §9). Composite PK `(table_service_id, physical_table_id)` — pure association, no extra attributes. **No mandatory primary table** — a Table Service may have zero Physical Tables (e.g. To Go), one, or several (joined tables).

---

## 4. Employee / Table Service ↔ Employee / Shift

### `employees`

**Purpose:** a person who may participate in service, orders, payments, or shifts.
**PK:** `id`. **FK:** `location_id` → `locations` (required).
**Direct fields:** `display_name`, `custom_id`, `system_role`, `active`, `source_created_at`, `source_modified_at` — all nullable.
**Why `active` is nullable, not defaulted:** TASK_CLOVER_003 confirmed **no active/inactive boolean field exists anywhere on Clover's Employee object** — defaulting to `True` would fabricate a fact Clover never supplied.
**Why `system_role` is a free string, not an FK to a Role catalog:** the task explicitly instructs not to invent a precise restaurant role from Clover's `systemRole`; TASK_CLOVER_003 additionally found that Clover's `employee.role` only resolves to a `systemRole` **tier** (`EMPLOYEE`/`MANAGER`/`ADMIN`), never to one of the several distinctly-named Roles sharing that tier — modeling a hard FK to a Role catalog here would overstate what the source actually supports. A future Personnel/Workforce integration may enrich this entity (task §10).
**Provenance:** `source_system_id`/`source_employee_id`, unique together.

### `source_roles`

**Purpose:** a source system's own named operational Role catalog entry (e.g. Clover's `Server`/`Host`/`BOH`/`Admin` — TASK_CLOVER_004). Distinct from `employees.system_role`, which preserves only the source's broader system-tier string (`EMPLOYEE`/`MANAGER`/`ADMIN`).
**PK:** `id`. **FK:** `location_id` → `locations` (required).
**Direct fields:** `name` (required), `source_system_role` (nullable) — the same tier concept as `employees.system_role`, but as a catalog attribute of the named Role itself (e.g. Clover's `Role.systemRole`), not of any one Employee's membership in it.
**Provenance:** `source_system_id`/`source_role_id`, unique together.

### `employee_source_roles`

**Purpose:** Employee ↔ named source Role membership (TASK_CLOVER_004), as resolved via Clover's `employees?expand=role` / `roles?expand=employees` relationship — confirmed to return the SPECIFIC named Role, not merely the systemRole tier (correcting TASK_CLOVER_003's earlier "unresolvable" conclusion; see `03 Software/Clover Data Explorer/CLOVER_DATA_CAPABILITY_MATRIX.md` § C and `07 Tasks/Reports/TASK_CLOVER_004_REPORT.md`).
**PK:** `id`. **FKs:** `employee_id` → `employees` (required, indexed), `source_role_id` → `source_roles` (required, indexed).
**Direct fields:** `observed_at` (required, server-default now) — the ingestion-time fact "this membership was observed as of this snapshot," nothing more.
**Why no `valid_from`/`valid_to`:** Clover exposes this relationship only as a CURRENT-STATE snapshot — no historical role-assignment log was found (an id no longer in the current `/employees` collection 404s on `?expand=role`, matching Employee's own current-snapshot-only behavior). Inventing a validity window the source does not support would fabricate a fact Clover never supplied (task §4C principle).
**`employees.system_role` is never overwritten by this table**, and no RF-One Restaurant Area is inferred from it — both explicit constraints from TASK_CLOVER_004.
**Cardinality:** `UniqueConstraint(employee_id, source_role_id)` prevents a duplicate membership row, but does not itself force "exactly one Role per Employee" — Clover's own `roles.elements[]` field shape is a collection, structurally capable of more than one. Empirically, this merchant's data shows exactly 1 named Role for all 24/24 current employees (100% cross-checked against `employees.system_role`); a second real-world merchant with a genuinely multi-Role employee would simply add a second row, not require a schema change.

### `table_service_employees` (M:N)

Composite PK `(table_service_id, employee_id)`. Distinct from the source-level single observations `Order.employee`/`Payment.employee`, which remain their own fields elsewhere — this table is the broader participation relationship (task §11).

### `shifts`

**Purpose:** atomic clock in/out facts only.
**PK:** `id`. **FK:** `employee_id` → `employees` (required, indexed).
**Direct fields:** `clock_in`, `clock_out`, `override_in_employee_id`/`override_in_time`, `override_out_employee_id`/`override_out_time` (the two override-employee columns are themselves FKs to `employees`), `server_banking` — all nullable, matching real Clover coverage (~99% clock in/out; ~4-5% overrides; `server_banking` present-with-value on only ~1.3% of records, per TASK_CLOVER_003).
**Explicitly NOT stored (derived, not atomic):** `elapsed_hours`, `employee_week_total` — task §12 forbids storing these as primary facts.

---

## 4a. Restaurant Profile / Organization (TASK_RESTAURANT_001)

Canonical RF-One business/operational context — see `01 Domains/Restaurant/Organization/` for the Domain-level definitions. Nothing in this section is ever auto-populated from Clover; every row (other than the single bootstrap `Restaurant` row described below) requires an explicit Restaurant/Product-Owner configuration action.

**Layer separation preserved by every table below:**

```text
Clover named Role (SourceRole, § 4)      — source evidence only
Clover systemRole (Employee.system_role) — source's broad tier string
RF-One Restaurant Role (restaurant_roles)      — canonical operational role
RF-One Operational Area (operational_areas)    — canonical functional grouping
RF-One Physical Area (physical_areas)          — canonical physical zone
```

### `restaurants`

**Purpose:** the canonical business/operational restaurant RF-One models — not merely a Clover `Merchant` object (task §11). Deliberately narrow: does not duplicate every `Merchant`/`Location` field.
**PK:** `id`. **Direct fields:** `name` (required), `legal_name`, `status`, `default_currency`, `default_timezone` (all nullable — none is fabricated beyond what repository data confirms), `created_at`/`updated_at` (RF-One record-lifecycle timestamps).
**No source provenance columns** — Restaurant is RF-One/business-configured identity, not a source-ingested entity (unlike `Merchant`/`Location`, which do carry `source_system_id`/`source_*_id`).

### `restaurant_locations`

**Purpose:** Restaurant ↔ Location (task §12), normalized rather than a direct FK on `restaurants` so one Restaurant can have one primary Location now and multiple Locations over time later without a schema change.
**PK:** `id`. **FKs:** `restaurant_id` → `restaurants` (required, indexed), `location_id` → `locations` (required, indexed).
**Direct fields:** `valid_from`, `valid_to`, `is_primary` — all nullable. No `UniqueConstraint(restaurant_id, location_id)`: a Restaurant could legitimately re-associate with the same Location again after a gap; overlap/primary-uniqueness validation is an application concern, not a blanket DB constraint (mirrors the reasoning already applied to `order_discounts`/`order_item_discounts` source ids, § 12 below).

### `operational_areas`

**Purpose:** a Restaurant-configured functional organizational grouping (task §13) — e.g. `FOH`/`BOH`/`BAR`/`MANAGEMENT`. Never a hard-coded universal enum.
**PK:** `id`. **FK:** `restaurant_id` → `restaurants` (required, indexed). **Direct fields:** `name` (required), `code`, `description`, `active` (all nullable except `name`).
**Unique:** `(restaurant_id, name)` — prevents accidental duplicate area names within one Restaurant's own configuration; does not prevent two different Restaurants from both configuring `"FOH"`.

### `physical_areas`

**Purpose:** a Restaurant-configured physical place/zone (task §14) — e.g. `Dining Room`, `Patio`, `Bar Counter`, `Kitchen`, `Private Room`. Distinct from `OperationalArea` (functional grouping, not a place) and from `PhysicalTable` (a single persistent table resource that may optionally sit inside a Physical Area).
**PK:** `id`. **FK:** `restaurant_id` → `restaurants` (required, indexed). **Direct fields:** `name` (required), `area_type`, `description`, `active` (all nullable except `name`).
**Unique:** `(restaurant_id, name)`, same rationale as `operational_areas`.

### `restaurant_roles`

**Purpose:** a Restaurant-configured canonical operational role (task §15) — e.g. `Server`, `Host`, `Bartender`, `Cook`, `Dishwasher`, `Manager`. Never a hard-coded universal enum, and never automatically equated with a Clover `SourceRole` or `Employee.system_role` (see `01 Domains/Restaurant/Organization/Restaurant Role.md`).
**PK:** `id`. **FK:** `restaurant_id` → `restaurants` (required, indexed). **Direct fields:** `name` (required), `code`, `description`, `active` (all nullable except `name`).
**Unique:** `(restaurant_id, name)`, same rationale as `operational_areas`.

### `operational_area_roles`

**Purpose:** M:N (task §16) — which Restaurant Role/Operational Area combinations a Restaurant's configuration allows (e.g. `Manager` valid in both `FOH` and `MANAGEMENT`; `FOH` allowing both `Host` and `Manager`). **Not** the Employee assignment itself — see `employee_assignments`. A Restaurant Role is deliberately never forced to belong to exactly one Operational Area (task §5).
**PK:** composite `(operational_area_id, restaurant_role_id)`, both FKs required.

### `employee_assignments`

**Purpose:** a temporally bounded fact describing how an Employee participates in a Restaurant (task §17) — the structure future Tips/Payroll/Scheduling/Performance/Training must resolve through. See `01 Domains/Restaurant/Organization/Employee Assignment.md` for the full Domain-level rule, including the explicit Tips/Payroll resolution path (period → Shifts intersecting the period → Employees actually present → valid Employee Assignment → Operational Area + Restaurant Role → applicable rule) and the explicit prohibition on using `Employee.active` to determine period participation.
**PK:** `id`. **FKs:** `employee_id` → `employees` (required, indexed), `restaurant_id` → `restaurants` (required, indexed), `operational_area_id` → `operational_areas` (required, indexed), `restaurant_role_id` → `restaurant_roles` (required, indexed), `physical_area_id` → `physical_areas` (**nullable** — only populated where a stable physical-area assignment is genuinely meaningful; never forced when physical working location varies shift by shift, task §17).
**Direct fields:** `valid_from` (required), `valid_to` (nullable — `NULL` represents an open-ended/current assignment, task §4), `assignment_source` (required string; conceptual values `MANUAL`/`SOURCE_ROLE_MAPPING`/`IMPORT`/`OTHER`, task §18 — not a DB enum, matching this schema's existing convention of leaving evolving classification fields as unconstrained strings, e.g. `TableService.reconstruction_status`), `source_note` (nullable), `created_at`/`updated_at` (RF-One record-lifecycle timestamps).
**Cardinality:** deliberately **not** constrained to one Role/Area per Employee, globally or at a given instant (task §5-6) — multiple concurrent Assignments are legitimate (e.g. a Manager valid in both `FOH` and `MANAGEMENT` at once). `UniqueConstraint(employee_id, operational_area_id, restaurant_role_id, valid_from)` rejects only an exact duplicate row (same Employee, Area, Role and start instant); it does not forbid legitimate concurrency (a different Area/Role or a different `valid_from` is still permitted). A Role/Area change is represented as a new row with its own `valid_from`, never as an in-place update of the prior row — history is never rewritten.

### `physical_tables.physical_area_id` (schema correction, task §14)

**Addition:** a nullable FK `physical_area_id` → `physical_areas.id`, added to the existing `physical_tables` table (§ 3 above) via Alembic migration (batch mode — SQLite cannot `ALTER TABLE ADD CONSTRAINT` directly). No `PhysicalTable` row is invented to populate this link; the current RF-One data has zero `PhysicalTable` rows (Clover exposes no structured Table entity, TASK_CLOVER_003 §F), so this remains a structural capability only, not populated data.

---

## 4b. Tips (TASK_TIPS_001)

The canonical Tip fact itself is **not** redefined here — it remains `PaymentTip` (§ 10), attached to `Payment`. This section adds only the post-hoc *calculation* apparatus: a temporally-scoped, Restaurant-configured Tip Policy, and the atomic, auditable results of running that policy over already-recorded PaymentTips. **No table below carries its own Tip timestamp** — every one reaches "when" through the parent Payment (`payments.created_at`), never a duplicated column. See `01 Domains/Restaurant/Tips/` for the Domain-level definitions and `03 Software/RF-One Data Store/RESTAURANT_PROFILE.md` § 3 for the original Tips/Payroll contract this implements.

### `tip_policies`

**Purpose:** a Restaurant-configured, temporally valid Tip allocation policy (task §9). Never defaults to a universal percentage/role split.
**PK:** `id`. **FKs:** `restaurant_id` → `restaurants` (required, indexed), `location_id` → `locations` (**nullable** — `NULL` means the policy applies across every Location associated with the Restaurant, not just one).
**Direct fields:** `name` (required), `code` (nullable), `status` (required free string — conceptual values `DRAFT`/`ACTIVE`/`RETIRED`), `valid_from` (required), `valid_to` (nullable — open-ended), `source_note` (nullable), `created_at`/`updated_at`.

### `tip_policy_components`

**Purpose:** one share of a `TipPolicy` (task §9-12). **PK:** `id`. **FK:** `tip_policy_id` → `tip_policies` (required, indexed).
**Direct fields:** `sequence` (ordering/tie-break), `recipient_basis` (required free string — `SERVICE_OWNER` or `ROLE_PRESENT_AT_PAYMENT`), `restaurant_role_id` (FK → `restaurant_roles`, **nullable** — required only when `recipient_basis = ROLE_PRESENT_AT_PAYMENT`, enforced by `CheckConstraint ck_tip_policy_components_role_present_requires_role`), `share_percentage` (`Numeric(7,4)`, same convention as `DiscountDefinition.percentage` — never a binary float), `split_method` (required free string — `EQUAL_ELIGIBLE_HEADCOUNT` is the only one the engine implements; the column stays a free string so `PRO_RATA_WORKED_TIME`/`WEIGHTED_ROLE`/`CONTRIBUTION_BASED` can be added later without a schema change), `no_eligible_behavior` (required free string — `RETURN_TO_SERVICE_OWNER`/`REDISTRIBUTE_TO_ELIGIBLE_COMPONENTS`/`LEAVE_UNALLOCATED`), `active` (nullable).

### `tip_calculation_runs`

**Purpose:** one execution of the post-hoc calculation engine over a requested period (task §17, §20, §27-28).
**PK:** `id`. **FK:** `restaurant_id` → `restaurants` (required, indexed).
**Direct fields:** `period_start`/`period_end` (required — the Payment-timestamp-selected period, never a Tip-entry-time selector), `started_at`/`completed_at`, `status` (`RUNNING`/`COMPLETE`/`FAILED`), `mode` (`DRY_RUN`/`PERSIST` — task §27's safe-by-default dry-run behavior), `calculation_version` (free string, for reproducibility), `notes` (nullable summary).

### `tip_allocations`

**Purpose:** one atomic, auditable unit of allocated Tip money (task §17, §28).
**PK:** `id`. **FKs:** `calculation_run_id` → `tip_calculation_runs` (required, indexed), `payment_tip_id` → `payment_tips.payment_id` (required, indexed — `PaymentTip`'s own PK), `payment_id` → `payments` (required, indexed), `order_id` → `orders` (required, indexed), `policy_component_id` → `tip_policy_components` (required, indexed), `employee_id` → `employees` (required, indexed). `payment_id`/`order_id` are denormalized (reachable via `payment_tip_id`/`payment_id` respectively) purely so an allocation can be reported without a join, per the task's explicit field list.
**Direct fields:** `allocated_amount_minor` (Integer, minor units — same money convention as every other amount in this schema), `reason` (nullable human-readable derivation trail), `created_at`.
**Unique:** `(calculation_run_id, payment_tip_id, policy_component_id, employee_id)` — when money is redistributed from an empty component to another component's eligible employee, the row is attributed to the **originating** (empty) component, not the receiving one, so a single employee can still separately earn a component's own share and a redistributed share from a different component without violating this constraint (see `rfone_data_store/tips/engine.py`, `BEHAVIOR_REDISTRIBUTE`).

### `tip_calculation_issues`

**Purpose:** a blocking or warning condition raised while calculating Tips (task §18) — the engine's explicit alternative to guessing.
**PK:** `id`. **FK:** `calculation_run_id` → `tip_calculation_runs` (required, indexed). **Nullable FKs:** `payment_tip_id`/`payment_id`/`order_id` (some issues, e.g. a Restaurant with no associated Location at all, are run-scoped rather than tied to one PaymentTip).
**Direct fields:** `issue_type` (required free string — `NO_VALID_POLICY`, `SERVICE_OWNER_UNRESOLVED`, `SERVICE_OWNER_AMBIGUOUS`, `NO_ELIGIBLE_RECIPIENT`, `SHIFT_ASSIGNMENT_GAP`, `CONFLICTING_ASSIGNMENTS` (reserved, not currently raised — see below), `FAILED_PAYMENT_WITH_TIP`, `REFUND_REVIEW_REQUIRED`, `ALLOCATION_RECONCILIATION_FAILURE` — only the subset actually produced by real engine logic is ever written), `severity` (`BLOCKING`/`WARNING`), `details` (required text), `status` (nullable — reserved for a future review workflow, always left `NULL`/"unreviewed" by this task's engine), `created_at`.

### Eligibility resolution (not a stored table)

`ROLE_PRESENT_AT_PAYMENT` eligibility (Shift active at `T` ∩ Employee Assignment valid at `T`, matching the component's Restaurant Role/Restaurant scope) is **always recomputed live** from `shifts` and `employee_assignments` — task §7 explicitly forbids persisting an "employees present at payment time" snapshot. An Employee is eligible whenever at least one matching Assignment exists at `T`; a **concurrent** `EmployeeAssignment` under a **different** `restaurant_role_id` — in the same or a different `operational_area_id` (e.g. Manager + Server at once) — does **not** disqualify them (TASK_TIPS_002, correcting TASK_TIPS_001's over-restrictive same-Area conflict check — see `07 Tasks/Reports/TASK_TIPS_002_REPORT.md`). An Employee holding more than one matching Assignment at `T` (e.g. the same Role valid in two Areas) is still counted **once** — deduplicated by Employee identity, never given two headcount shares. `CONFLICTING_ASSIGNMENTS` remains a reserved `issue_type` value for a genuine future ambiguity the engine cannot resolve (e.g. a policy that explicitly requires mutually exclusive role resolution); it is not raised by current engine logic. `SHIFT_ASSIGNMENT_GAP` is raised when a Shift-active Employee has **zero** valid Assignment at `T` at all (an epistemic gap, distinct from "confirmed nobody in this role").

### Managed-history boundary (task §21)

No new schema field was introduced for this. A `TipPolicy`'s own `valid_from` already delimits when a Restaurant's Tips configuration reliably begins (`NO_VALID_POLICY` before that point), and an Employee Assignment gap is already surfaced structurally (`SHIFT_ASSIGNMENT_GAP`/empty eligibility) — together these make a separate "managed history start" column unnecessary. As of TASK_RESTAURANT_003, `employee_assignments` is populated (24 rows, prospective from its own `T0` — see § 4c) but `tip_policies` remains empty, so every historical Payment still falls outside managed Tips history for the independent reason that no `TipPolicy` has been configured yet — see `validate_tips_readiness.py`.

---

## 4c. Restaurant Profile bootstrap from source configuration (TASK_RESTAURANT_003)

Adds the source-control / mapping / reconciliation layer needed to instantiate a Restaurant Profile FROM a source system's (Clover's) current configuration, while preserving the same boundary § 4a already enforces: `SourceRole ≠ RestaurantRole`, even when the initial configured names coincide — the two are connected only by an explicit, Restaurant-scoped `SourceRoleMapping` row, never a name-based equivalence. See `01 Domains/Restaurant/Organization/README.md`, "Profile bootstrap from source configuration," and `RESTAURANT_PROFILE.md` § 6 for the Domain/Software-layer statement of the `T0` contract this implements.

### `restaurant_profile_source_controls`

**Purpose:** records the explicit `T0` — the timestamp at which RF-One begins managing a source-derived Restaurant Profile for one (Restaurant, SourceSystem) pair (task §4). Before `managed_from`, RF-One makes no automatic claim that today's source role mapping was historically true; at/after it, RF-One maintains temporal Restaurant Profile history prospectively.
**PK:** `id`. **FKs:** `restaurant_id` → `restaurants` (required, indexed), `source_system_id` → `source_systems` (required, indexed).
**Direct fields:** `managed_from` (required — persisted `T0`, never file-modification/process-startup time), `status` (required free string — conceptual values `ACTIVE`/`RETIRED`), `snapshot_note` (nullable), `created_at`/`updated_at`.
**No DB-enforced singleton:** the bootstrap engine reuses the existing `status = ACTIVE` row for a given (restaurant_id, source_system_id) rather than creating a second one on every run (idempotency, task §14).

### `source_role_mappings`

**Purpose:** explicit, temporally-valid `SourceRole -> RestaurantRole` mapping, scoped to one Restaurant (task §5).
**PK:** `id`. **FKs:** `restaurant_id` → `restaurants` (required, indexed), `source_system_id` → `source_systems` (required), `source_role_id` → `source_roles` (required, indexed), `restaurant_role_id` → `restaurant_roles` (required, indexed).
**Direct fields:** `valid_from`/`valid_to` (temporal validity — future Clover configuration changes create a new mapping row rather than rewriting this one, task §5), `mapping_status` (required free string — `ACTIVE`/`RETIRED`), `mapping_source` (required free string — `CLOVER_SOURCE_ROLE_BOOTSTRAP` for this task's rows), `notes` (nullable), `created_at`/`updated_at`.
**Unique:** `(restaurant_id, source_role_id, valid_from)` — rejects an exact duplicate row, never legitimate re-mapping over time.

### `profile_bootstrap_runs`

**Purpose:** one execution of the bootstrap/sync engine (task §15), mirroring `tip_calculation_runs`' dry-run/persist pattern exactly.
**PK:** `id`. **FKs:** `restaurant_id` → `restaurants` (required, indexed), `source_system_id` → `source_systems` (required).
**Direct fields:** `started_at`/`completed_at`, `status` (`RUNNING`/`COMPLETE`/`FAILED`), `mode` (`DRY_RUN`/`PERSIST`), `notes` (nullable summary).

### `restaurant_profile_reconciliation_issues`

**Purpose:** a source→profile congruence problem, surfaced rather than silently corrected (task §9).
**PK:** `id`. **FK:** `bootstrap_run_id` → `profile_bootstrap_runs` (required, indexed), `restaurant_id` → `restaurants` (required, indexed). **Nullable FKs:** `employee_id` → `employees`, `source_role_id` → `source_roles`, `restaurant_role_id` → `restaurant_roles`, `mapping_id` → `source_role_mappings` (whichever are relevant to the specific issue).
**Direct fields:** `issue_type` (required free string — `CURRENT_EMPLOYEE_WITHOUT_SOURCE_ROLE`, `SOURCE_ROLE_WITHOUT_PROFILE_MAPPING`, `PROFILE_MAPPING_WITHOUT_CURRENT_SOURCE_ROLE`, `CURRENT_EMPLOYEE_WITH_UNMAPPED_SOURCE_ROLE`, `EMPLOYEE_ASSIGNMENT_MISSING_AFTER_BOOTSTRAP`, `SOURCE_ROLE_RELATIONSHIP_INCONSISTENT`, `DUPLICATE_OR_OVERLAPPING_MAPPING` — only the subset actually produced by real engine logic is ever written), `severity` (`BLOCKING`/`WARNING`), `details` (required text — references entities by internal RF-One integer id only, never an Employee display name or raw Clover source id, task §22), `status` (nullable — reserved for a future review workflow; also the dedup key's "still open" test, see below), `detected_at`.
**Idempotency:** before creating a new row, the engine checks for an existing row with the same `(restaurant_id, issue_type, employee_id, source_role_id, restaurant_role_id, mapping_id)` key and `status IS NULL`; if found, it is reused rather than duplicated (task §14).

### Bootstrap algorithm (not a stored table)

For every current-scope `SourceRole` (matching this Restaurant's `RestaurantLocation`(s) and `source_system_id`): reuse or create a `RestaurantRole` of the same name, associate it with the single root `OperationalArea` via `OperationalAreaRole`, and reuse or create an ACTIVE `SourceRoleMapping` (`valid_from = T0`). For every current Employee (`display_name IS NOT NULL`): resolve each `EmployeeSourceRole` through its ACTIVE mapping to a `restaurant_role_id`, then reconcile the Employee's open `EmployeeAssignment` set against that desired set — open any missing one (`valid_from = T0` if the Employee has never had an Assignment before, otherwise `valid_from = ` the current sync time, task §13), and close any open one no longer supported by a current SourceRole (`valid_to = ` the current sync time). Historical stubs (`display_name IS NULL`) are never queried for source roles and never touched. See `rfone_data_store/profile/bootstrap.py`.

---

## 4d. Payroll (TASK_PAYROLL_001)

Administration Domain, transversal — independent from Restaurant, Personnel Management, ADP, and jurisdiction-specific labor law. See `01 Domains/Administration/Payroll/` for the Domain-level definitions and `PAYROLL.md` for the runtime/import workflow. Money is minor units (cents), matching the rest of this schema; every total (Payroll Employer Cost, run totals) is computed from the atomic fact tables below at query time, never stored as a redundant column.

### `payroll_schedules`

**Purpose:** the configured recurring cadence under which normal Payroll Periods are generated (task §5). **PK:** `id`. **FK:** `restaurant_id` → `restaurants` (required, indexed). **Direct fields:** `schedule_type` (required free string — `WEEKLY`/`BIWEEKLY`/`MONTHLY`, validated by `rfone_data_store/payroll/schedule.py`, never a hard-coded universal default), `code`/`name`/`active` (nullable). **Unique:** `(restaurant_id, code)`.

### `workweek_definitions`

**Purpose:** a Restaurant-configured recurring legal/compensation evaluation interval (task §7) — deliberately **not** derived from `payroll_schedules`. **PK:** `id`. **FK:** `restaurant_id` → `restaurants` (required, indexed). **Direct fields:** `start_weekday` (required, 0=Monday..6=Sunday), `valid_from` (required), `valid_to`/`notes` (nullable). No row here is ever inferred from a `PayrollSchedule` row — a BIWEEKLY schedule change never implies a Workweek boundary change, and vice versa.

### `employee_compensation_terms`

**Purpose:** Employee-specific, temporal compensation (task §10-13). **PK:** `id`. **FKs:** `employee_id` → `employees` (required, indexed); `restaurant_role_id` → `restaurant_roles` (**nullable** — optional provenance only, task §11's explicit "keep that dependency optional" instruction). **Direct fields:** `function_label` (required — the smallest provider-independent way to distinguish concurrent terms, never a role ontology owned by Payroll), `compensation_basis` (required — `HOURLY`/`SALARIED`), `hourly_rate_minor`/`salaried_period_amount_minor` (each nullable, enforced mutually exclusive-and-matching by `ck_employee_compensation_terms_basis_matches_amount`), `valid_from` (required), `valid_to` (nullable — open-ended), `source_note`, `created_at`/`updated_at`. **Unique:** `(employee_id, function_label, valid_from)` — rejects only an exact duplicate row, never legitimate concurrency (two different `function_label`s) or a legitimate re-rate (a new `valid_from`).

### `payroll_runs`

**Purpose:** one actual administrative payroll processing event (task §18). **PK:** `id`. **FKs:** `restaurant_id` → `restaurants`, `source_system_id` → `source_systems` (both required, indexed); `payroll_schedule_id` → `payroll_schedules` (**nullable** — null for `SPECIAL` runs); `superseded_by_payroll_run_id` → `payroll_runs.id` (self-referential, nullable — populated only when an explicitly confirmed corrected import supersedes this run). **Direct fields:** `period_start`/`period_end` (nullable only for `SPECIAL` runs — never inferred from `pay_date`), `pay_date` (required), `run_type` (required — `REGULAR`/`SPECIAL`), `provider_reference`/`status` (free strings — conceptual `status` values `OPEN`/`COMPLETE`/`SUPERSEDED`), `created_at`/`updated_at`.

### `payroll_provider_employee_identities`

**Purpose:** explicit, provider-scoped external Employee identity mapping (task §28) — never an ADP-specific column on `employees`. **PK:** `id`. **FKs:** `source_system_id` → `source_systems`, `restaurant_id` → `restaurants` (both required, indexed); `employee_id` → `employees` (**nullable** — null while `UNRESOLVED`/`AMBIGUOUS`, indexed). **Direct fields:** `external_employee_key` (required — a deterministic structural name-key, never a fuzzy/similarity value, produced by `rfone_data_store/payroll/adp_importer.py`), `external_display_reference` (nullable — already-masked provider evidence only, e.g. a partial SSN as the source itself presents it; never a full SSN/tax id), `mapping_status` (required — `RESOLVED`/`UNRESOLVED`/`AMBIGUOUS`), `resolution_method`/`resolved_at`/`notes` (nullable), `created_at`/`updated_at`. **Unique:** `(source_system_id, restaurant_id, external_employee_key)`.

### `employee_payroll_results`

**Purpose:** one Employee's externally processed result context for a `PayrollRun` (task §22). Prefers identifiers/atomic child facts over redundant totals — carries no stored earnings/liability/payment total of its own. **PK:** `id`. **FKs:** `payroll_run_id` → `payroll_runs`, `employee_id` → `employees` (both required, indexed); `compensation_term_id` → `employee_compensation_terms` (**nullable** — optional provenance only). **Direct fields:** `source_pay_frequency_label` (nullable, raw provenance only), `review_status` (nullable — conceptual values `OK`/`MANUAL_REVIEW_REQUIRED`), `source_note`, `created_at`. **Unique:** `(payroll_run_id, employee_id)` — one result row per Employee per Run.

### `payroll_earning_facts`

**Purpose:** a provider-reported earning/reporting line (task §22). **PK:** `id`. **FK:** `employee_payroll_result_id` → `employee_payroll_results` (required, indexed). **Direct fields:** `earning_type` (required — normalized generically from the source label, e.g. "Cash tips* " -> `CASH_TIPS`, never a hard-coded whitelist — an unseen label is never rejected), `source_label` (required, verbatim), `quantity`/`unit`/`rate_minor` (all independently nullable — not every payable item is measured in hours), `amount_minor` (required), `paid_to_employee` (required — parsed from the provider's own "* Items Not Paid To Employee" convention; `false` lines are structurally excluded from Payroll Employer Cost's earnings component), `excluded_from_taxable_wages` (nullable — parsed from a "**" suffix, independent of `paid_to_employee`), `sequence` (nullable, provenance only), `created_at`.

### `payroll_employer_liability_facts`

**Purpose:** a provider-reported employer-side liability/cost line (task §22) — e.g. employer Social Security/Medicare. **PK:** `id`. **FK:** `employee_payroll_result_id` → `employee_payroll_results` (required, indexed). **Direct fields:** `liability_type`/`source_label` (required), `amount_minor` (required), `created_at`. **No employee-withholding table exists anywhere in this schema** — employee tax withholding is deliberately not modeled (task §23), so it structurally cannot be misclassified as employer labor cost.

### `payroll_payment_facts`

**Purpose:** a provider-reported employee payment fact (task §22) — reconstructs actual employee-level payment independent of an aggregate bank debit. **PK:** `id`. **FK:** `employee_payroll_result_id` → `employee_payroll_results` (required, indexed). **Direct fields:** `pay_date` (required), `payment_method` (nullable, free string), `payment_amount_minor` (required), `provider_payment_reference` (nullable — already masked/redacted by the provider itself, e.g. a partial account number; never enriched beyond what the provider already redacted), `sequence` (nullable), `created_at`.

### `payroll_import_runs`

**Purpose:** one execution of the ADP `Payroll Detail` Excel importer (task §29) — auditability and idempotency by file hash, mirroring `tip_calculation_runs`' dry-run/persist pattern. **PK:** `id`. **FKs:** `restaurant_id` → `restaurants`, `source_system_id` → `source_systems` (both required, indexed); `payroll_run_id` → `payroll_runs` (nullable); `supersedes_import_run_id` → `payroll_import_runs.id` (self-referential, nullable — populated only when the operator explicitly passes `--supersedes-run`, never inferred). **Direct fields:** `source_file_name` (required — file name only, never a full local filesystem path), `source_file_hash` (required, SHA-256), `imported_at`, `mode` (`DRY_RUN`/`PERSIST`), `status` (`COMPLETE`/`PARTIAL`/`FAILED`), `employees_represented_count`/`unresolved_employee_count` (nullable), `notes`. **Unique:** `(source_system_id, restaurant_id, source_file_hash)` — re-importing the identical file is detected and reused, never duplicated.

### `payroll_import_issues`

**Purpose:** a blocking or warning condition raised while importing a Payroll provider result (task §28-29) — the importer's explicit alternative to guessing, mirroring `tip_calculation_issues`. **PK:** `id`. **FK:** `import_run_id` → `payroll_import_runs` (required, indexed). **Direct fields:** `issue_type` (required free string — `UNRESOLVED_EMPLOYEE_MAPPING`, `AMBIGUOUS_EMPLOYEE_MAPPING`, `UNPARSED_SOURCE_ROW`, `MID_PERIOD_COMPENSATION_CONFLICT` — only the subset actually produced by real importer logic is ever written), `severity` (`BLOCKING`/`WARNING`), `details` (required — never a full SSN/tax id/bank reference), `status` (nullable, reserved), `created_at`.

### Payroll Employer Cost (not a stored table)

Always computed at query time by `rfone_data_store/payroll/labor_cost.py`: `sum(payroll_earning_facts.amount_minor where paid_to_employee) + sum(payroll_employer_liability_facts.amount_minor)`, per `EmployeePayrollResult` and summed per `PayrollRun`. No `payroll_employer_cost_total`-shaped column exists anywhere in this schema.

---

## 5. Order Type / Order

### `order_types`

**Purpose:** configuration/catalog data (e.g. "Table", "To Go"). **PK:** `id`. **FK:** `location_id` (required).
**Direct fields:** `name` (required), `min_order_amount`, `max_order_amount`, `configured_fee`, `average_order_time`, `active` — all money-like fields are integer minor units, all nullable (Clover's own `order_types.json` shows several of these fields null/absent for hidden order types).

### `orders`

**Purpose:** a commercial/POS grouping of sold units and settlements — **not** assumed to be 1:1 with Table Service, Payment, or a single physical unit per line (Restaurant Sales Model §5, §13; TASK_CLOVER_003).
**PK:** `id`. **FKs:** `location_id` (required), `table_service_id` → `table_services` (**nullable** — Table Service reconstruction is not implemented by this task, task §14/§45), `employee_id` → `employees` (nullable), `order_type_id` → `order_types` (nullable), `device_id` → `devices` (nullable).
**Required source fields:** `source_system_id`, `source_order_id` (`UniqueConstraint` together), `created_at`.
**`source_employee_id` (nullable string) alongside `employee_id` (nullable FK):** the raw source employee reference is preserved even if/before it is resolved to a canonical `Employee` row.
**`device_id` (nullable FK, added by TASK_DATABASE_002's pre-ingestion schema review) alongside `device_source_id` (nullable string):** TASK_DATABASE_001 originally left Device linkage as a raw string only, reasoning it mirrored `source_employee_id`'s pattern. TASK_DATABASE_002 revisited this before real ingestion: since `Device` is already a canonical catalog entity resolvable from Clover's small, stable `/devices` collection, a resolved FK materially improves queryability (e.g. joining Orders to Device without an application-level lookup) at negligible cost. Both columns are retained — `device_id` is populated only when the source device can actually be resolved to a canonical `Device` row; `device_source_id` always preserves the raw source reference regardless of resolution.
**Money fields** (`subtotal`, `discount_total`, `tax_total`, `total`) are all nullable integer minor units — Clover's own `Order.total` is 100% present but the others are frequently derived/absent depending on source completeness.
**`title_raw`** is preserved **verbatim** and is **never parsed inside this model** — TASK_CLOVER_003 found this field very likely encodes a table number + seating zone as free text (e.g. `"#4 - Inside"`); any future parsing belongs to ingestion/reconstruction logic, not the schema (task §14).
**Booleans** (`test_mode`, `manual_transaction`, `tax_removed`, `is_vat`) are nullable, matching that Clover always returns them but a future source might not.

---

## 6. Item / Category / Modifier catalog

### `items`

**Purpose:** anything sellable — explicitly **not** "current menu item" (Restaurant Sales Model §8; TASK_CLOVER_003 § I confirmed Clover's real catalog mixes food/beverage, technical, and fee-adjacent Items).
**PK:** `id`. **FK:** `location_id` (required). **Required:** `source_system_id`, `source_item_id` (unique together), `name`.
**Why `sku`/`code` are nullable despite sitting next to `name` in the task's suggested field grouping:** TASK_CLOVER_003 measured real coverage at 98.1%/99.8%, not 100% — forcing `NOT NULL` would directly contradict the empirical evidence and violate the "missing ≠ zero/absent-as-default" principle (task §4C).
**`item_nature`** is an explicit RF-One classification field, nullable, **never auto-derived from the Item name** (task §15) — it exists so a future classification pass has somewhere to write its conclusion without needing a migration.

### `categories` / `item_categories`

`categories`: `id` PK, `location_id` FK, `source_system_id`+`source_category_id` (required, unique together), `name` (required).
`item_categories`: composite PK `(item_id, category_id)` — **M:N is required, not optional**, because TASK_CLOVER_003 empirically found real Items with 0, 1, 2, and even 15 Categories (task §16).

### `modifier_groups` / `modifiers` / `item_modifiers`

`modifier_groups`: `id` PK, `location_id` FK, `source_system_id`+`source_modifier_group_id` (required, unique together), `name` (required).
`modifiers`: `id` PK, `location_id` FK, `modifier_group_id` → `modifier_groups` (**nullable** — a Modifier need not belong to a group), `source_system_id`+`source_modifier_id` (required, unique together), `name` (required), `alternate_name`/`price_delta`/`active` (nullable).
**Semantic nature deliberately not encoded:** no `PRODUCT_VARIANT` vs. `SERVICE_INSTRUCTION` column exists — TASK_CLOVER_003 confirmed this distinction remains unresolved from Clover data alone (task §17).
`item_modifiers`: composite PK `(item_id, modifier_id)` — catalog **availability** (Modifiers associated with an Item), explicitly distinct from a Modifier actually **selected** on a sale (`order_item_modifiers`, § 7 below) — task §18.

---

## 7. Order Item / Order Item ↔ Modifier

### `order_items`

**Purpose:** the most granular source sales line available.
**PK:** `id`. **FKs:** `order_id` → `orders` (required, indexed), `item_id` → `items` (**nullable, indexed** — fee/technical lines carry no catalog Item, matching Clover's own ~1.6-1.9% Item-absent rate on fee lines).
**Required:** `source_system_id`, `source_line_item_id` (unique together).
**Quantity — the task's central correction:** `quantity` is `Numeric(12, 4)`, **nullable, never defaulted to 1**. TASK_CLOVER_003 found Clover Order Items are **not** guaranteed to represent exactly one physical unit — 308 real revenue line items carried a fractional `unitQty` (halves, thirds, quarters). Forcing an integer or defaulting a missing value to `1` would silently misrepresent real sales.
**Guest evidence:** `guest_number` (nullable, **indexed**) is the atomic per-item guest/seat assignment; `guest_label_raw` preserves the original free-text POS evidence (e.g. Clover's `binName`) it was parsed from. **The Clover field name `binName` itself does not appear anywhere in this canonical schema** — only in raw source metadata (`SourceRecord.raw_json`) if ever persisted there — per task §21.
**`created_at` is nullable here** (unlike `orders.created_at`), matching the task's own §19 field list — an individual line's own timestamp may not always be resolvable independently of its parent Order's.
**Other nullable fields** (`source_name`, `quantity_decimal_digits`, `unit_name`, `historical_unit_price`, `item_code_raw`, `is_revenue`, `is_order_fee`, `printed`, `refunded_flag`, `exchanged_flag`, `line_item_info_json`) all mirror real, measured Clover coverage rather than an assumption of completeness.
**Historical-value principle:** `historical_unit_price` and `source_name` preserve the sale as it actually happened; a later change to the `Item` catalog definition never rewrites these (task §4D, §9 of the Restaurant Sales Model).

### `order_item_modifiers`

**Purpose:** a Modifier actually selected on a historical Order Item.
**PK:** `id`. **FK:** `order_item_id` → `order_items` (required, indexed); `modifier_id` → `modifiers` (**nullable**) — preserves enough source identity (`name_raw`, `amount`, `source_modification_id`) to audit a modification even where the catalog Modifier cannot be resolved (task §20).

---

## 8. Discounts

### `discount_definitions`

**Purpose:** optional catalog discount definition. **PK:** `id`. **FK:** `location_id` (required). Required: `source_system_id`+`source_discount_id` (unique together), `name`. `percentage`/`amount`/`active` nullable — a catalog definition is typically one or the other, never both, but neither is forced.

### `order_discounts` / `order_item_discounts`

**Purpose:** Order-level and Order-Item-level applied discounts — **structurally distinct tables, never collapsed** (task §18/§24 of the Restaurant Sales Model and this task's §24).
**PK:** `id` each. **FK:** `discount_definition_id` (**nullable** — TASK_CLOVER_003 confirmed real ad hoc/manual discounts exist with no catalog reference at all).
**`percentage` and `amount` are both independently nullable — this is the schema's direct answer to a TASK_CLOVER_003 finding:** real applied discounts come in (at least) three shapes — catalog-referenced percentage, ad hoc percentage, and **ad hoc fixed amount** (one confirmed real example: `"$50.00 Off"` → `amount: -5000` cents). A schema that only had a `percentage` column would silently be unable to represent the amount-shaped case, exactly the gap TASK_CLOVER_003 flagged in the existing Clover export-reconstruction logic.
**`raw_shape_json`** preserves the exact applied-discount element as observed, so a future reviewer can audit which shape actually produced a given row without re-deriving it from `percentage`/`amount` alone.
**`source_discount_id` is nullable**, interpreted as "the source system's own id for this applied-discount element" (present on every Clover example seen, but not assumed to exist for every future source).

---

## 9. Tax / Fee

### `tax_rates`

**PK:** `id`. **FK:** `location_id` (required). Required: `source_system_id`+`source_tax_rate_id` (unique together), `name`, `rate` (canonical decimal fraction, `NOT NULL` — a Tax Rate catalog entry without a rate is not meaningful). `active` nullable.

### `order_item_taxes`

**Purpose:** line-item tax detail, preserved for reconciliation/analysis. **`Order.tax_total` remains the order-level tax total** — this table does not replace it (task §26).
**PK:** `id`. **FK:** `order_item_id` → `order_items` (required, indexed); `tax_rate_id` → `tax_rates` (nullable — the applicable rate may not always be resolvable to a catalog row, e.g. an untaxed item with an empty per-item override, per TASK_CLOVER_003's confirmed "empty list means 0%, not fallback to default" rule). `amount`/`rate_applied` nullable.
**Tax ownership principle preserved:** Payment-level tax is never treated as conceptual tax ownership — see `payments.tax_amount_source` below, deliberately named to make clear it is a **settlement-side observation**, not the source of truth for Order tax.

### `order_fees`

**Purpose:** supports native fee mechanisms (e.g. Clover's synthetic "Gratuity"/Service Charge line item) while preserving provenance to the source line that produced it.
**PK:** `id`. **FK:** `order_id` → `orders` (required). `source_line_item_id` is a **raw string reference**, not a hard FK to `order_items` — the synthetic fee line is also separately ingested as its own `OrderItem` row (with `is_order_fee=true`); this column is provenance-only, linking the two representations for audit without forcing a rigid 1:1 assumption (task §27).
**`amount` is required** (a Fee without an amount is not a fee); `fee_type`, `name_raw`, `percentage`, `source_fee_id` nullable. Ordinary Items are never auto-classified as fees by name — that remains an RF-One classification decision made elsewhere, if ever.

---

## 10. Tender / Payment / Payment Tip / Refund

### `tenders`

**PK:** `id`. **FK:** `location_id` (required). Required: `source_system_id`+`source_tender_id` (unique together), `label`. `source_type` is preserved as-is but is **explicitly not used as a cash/card classification** — TASK_CLOVER_003 disproved `opensCashDrawer` as a reliable structural signal for the current merchant (it was `False` on every tender including `Cash`); the free-text `label` remains the practical source of truth, and this schema does not pretend otherwise (task §28).

### `payments`

**Purpose:** an independent atomic settlement entity. **One Order may have many Payments — including FAILED ones.**
**PK:** `id`. **FK:** `order_id` → `orders` (required, indexed). Required: `source_system_id`+`source_payment_id` (unique together), `created_at`, `amount`.
**Why this matters structurally:** TASK_CLOVER_003 confirmed Clover's own nested `Order.payments` collection **silently excludes failed payment attempts** (a precisely reconciled finding: the 36-payment gap between nested and top-level Payments equals exactly the `FAIL`-result count). This schema does not replicate that gap — `payments` is designed to be populated from the complete top-level Payments collection by a future ingestion pipeline, not the nested one, so failed Payments remain representable. No ingestion code is implemented here; this is a schema-level readiness note.
**`tax_amount_source`** (not `tax_amount`) is deliberately named to signal it is the payment's own reported figure, distinct from — and not authoritative over — `orders.tax_total`/`order_item_taxes` (task §26/§38).
**`device_id`** (nullable FK → `devices`, added by TASK_DATABASE_002) alongside **`device_source_id`** (nullable raw string) — see § 5's Order entry for the rationale; identical pattern here.

### `payment_tips`

**Purpose:** the schema's direct answer to the task's core Tip requirement — **1:0..1 with Payment**, via `payment_id` as both PK and FK.
**`source_present`** (`Boolean`, `NOT NULL`) distinguishes "tip field explicitly present and `0`" (`source_present=true, amount=0`) from "tip field absent from source" (**no `PaymentTip` row exists at all** for that Payment — not a row with `amount=null`). This mirrors exactly what TASK_CLOVER_003 found in real Clover data: a missing `tipAmount` key is not the same fact as a present-and-zero one, and the two must never be conflated (task §30).
**Service Charge is never derived into Tip here** — `order_fees` is the only home for Service Charge amounts.

### `refunds`

**Purpose:** a **mandatory, first-class entity** — not optional, not inferable.
**PK:** `id`. **FKs:** `order_id`/`payment_id`/`employee_id` — all **nullable**, because TASK_CLOVER_003's real confirmed examples show a Refund is reachable and meaningful even before/without full resolution to every related canonical entity. **One Payment may have multiple Refunds** — `payment_id` is a plain FK (not unique), matching the task's explicit "allow multiple Refunds per Payment" instruction (§31), even though only full-amount refunds were observed in the current evidence.
**Why this table must never be inferred from other tables:** TASK_CLOVER_003's single most important finding — two real refunds exist that are **completely invisible** in `orders.payment_state` (stays `"PAID"`), `payments.result` (stays `"SUCCESS"`), and `order_items.refunded_flag` (stays `false`), confirmed by exact ID cross-reference. This table exists precisely because those other fields cannot be trusted to reveal a refund.
**Required:** `source_system_id`+`source_refund_id` (unique together), `created_at`, `amount`. `tax_amount`, `tip_amount`, `status`, `voided`, `device_id` (FK → `devices`, added by TASK_DATABASE_002), `device_source_id` all nullable.

---

## 11. Device

### `devices`

**PK:** `id`. **FK:** `location_id` (required). Required: `source_system_id`+`source_device_id` (unique together). `name`/`model`/`device_type` nullable. **Hardware configuration fields are deliberately not stored** (e.g. Clover's `pinDisabled`, `offlinePayments*`, `secureId`) — task §32 asks for a lightweight entity only, and TASK_CLOVER_003 classified this detail as vendor configuration noise, not business data.

---

## 12. Referential integrity and indexing

### Unique constraints (task §36)

The five explicitly required, plus catalog/reference entities where TASK_CLOVER_003 confirmed the source `id` is genuinely unique per collection (not "false uniqueness" — each is grounded in real, inspected Clover data):

```text
(source_system_id, source_order_id)          orders
(source_system_id, source_payment_id)        payments
(source_system_id, source_line_item_id)      order_items
(source_system_id, source_item_id)           items
(source_system_id, source_refund_id)         refunds

(source_system_id, source_merchant_id)       merchants
(source_system_id, source_location_id)       locations
(source_system_id, source_employee_id)       employees
(source_system_id, source_role_id)           source_roles
(source_system_id, source_shift_id)          shifts
(source_system_id, source_order_type_id)     order_types
(source_system_id, source_category_id)       categories
(source_system_id, source_modifier_group_id) modifier_groups
(source_system_id, source_modifier_id)       modifiers
(source_system_id, source_discount_id)       discount_definitions
(source_system_id, source_tax_rate_id)       tax_rates
(source_system_id, source_tender_id)         tenders
(source_system_id, source_device_id)         devices
```

**No uniqueness constraint exists on `order_discounts.source_discount_id`, `order_item_discounts.source_discount_id`, or `order_item_modifiers.source_modification_id`** — these are applied-instance records, not catalog rows, and the source evidence does not establish a uniqueness guarantee for them (task §36's explicit caution against "false uniqueness").

**Restaurant Organization tables (TASK_RESTAURANT_001) — RF-One-configuration uniqueness, not source uniqueness:**

```text
(restaurant_id, name)                                             operational_areas
(restaurant_id, name)                                             physical_areas
(restaurant_id, name)                                             restaurant_roles
(employee_id, operational_area_id, restaurant_role_id, valid_from) employee_assignments
```

No uniqueness constraint exists on `restaurant_locations(restaurant_id, location_id)` — a Restaurant may legitimately re-associate with the same Location after a gap (§ 4a).

**Tips tables (TASK_TIPS_001):**

```text
(calculation_run_id, payment_tip_id, policy_component_id, employee_id)   tip_allocations
```

No uniqueness constraint exists on `tip_policies`/`tip_policy_components` names/codes — a Restaurant may configure overlapping-looking policies across different periods; `TipPolicy.valid_from`/`valid_to` (application-resolved, not DB-enforced non-overlap) determine which one actually applies at a given timestamp (§ 4b).

**Payroll tables (TASK_PAYROLL_001):**

```text
(restaurant_id, code)                                        payroll_schedules
(employee_id, function_label, valid_from)                    employee_compensation_terms
(source_system_id, restaurant_id, external_employee_key)     payroll_provider_employee_identities
(payroll_run_id, employee_id)                                employee_payroll_results
(source_system_id, restaurant_id, source_file_hash)          payroll_import_runs
```

No uniqueness constraint exists on `payroll_runs` — a Restaurant may have more than one `SPECIAL` run on the same `pay_date` (e.g. a correction and a bonus run), and `superseded_by_payroll_run_id` (application-set, never DB-enforced) is what distinguishes a corrected run's history from a duplicate (§ 4d).

### Indexes (task §37)

Exactly the columns the task lists, implemented via `index=True` on the column or an explicit composite `Index`:

```text
orders.created_at, orders.table_service_id, orders.employee_id
order_items.order_id, order_items.item_id, order_items.guest_number, order_items.created_at
payments.order_id, payments.created_at, payments.employee_id
refunds.payment_id, refunds.order_id, refunds.created_at
shifts.employee_id, shifts.clock_in
table_services.opened_at
source_records(source_system_id, entity_type, source_id)

employee_assignments.employee_id, employee_assignments.restaurant_id,
employee_assignments.operational_area_id, employee_assignments.restaurant_role_id,
employee_assignments(employee_id, valid_from)     -- TASK_RESTAURANT_001
restaurant_locations.restaurant_id, restaurant_locations.location_id
operational_areas.restaurant_id, physical_areas.restaurant_id, restaurant_roles.restaurant_id
```

No additional speculative indexes were added (task §37's explicit caution).

---

## 13. Text ER relationship diagram

```text
source_systems ──< ingestion_runs ──< source_records
       │
       └─< (source_system_id referenced by nearly every table below)

merchants ──< locations
                  │
     ┌────────────┼─────────────────────────────────────────────┐
     │            │                                              │
physical_tables  employees ──< shifts (self-FK: override_in/out_employee_id)
     │            │  │
     │            │  ├─< table_service_employees >── table_services
     │            │  └─< employee_source_roles >── source_roles   (TASK_CLOVER_004)
     │            │
     └──< table_service_physical_tables >── table_services
                                                  │
                                                  ├─< orders
order_types ──< orders                           │
     │                                            │
     └────────────────────────────────────────────┘
orders
  ├─(N:1)→ employees (order-level employee observation)
  ├─(1:N)→ order_items ──(N:1)→ items ──(M:N)→ categories   [item_categories]
  │            │                    └─(M:N)→ modifiers      [item_modifiers]
  │            │                                  │
  │            ├─(1:N)→ order_item_modifiers ─────┘ (N:1, nullable)
  │            ├─(1:N)→ order_item_discounts ──(N:1, nullable)→ discount_definitions
  │            └─(1:N)→ order_item_taxes ──(N:1, nullable)→ tax_rates
  │
  ├─(1:N)→ order_discounts ──(N:1, nullable)→ discount_definitions
  ├─(1:N)→ order_fees
  ├─(1:N)→ payments
  │            ├─(N:1, nullable)→ employees, tenders, devices
  │            ├─(1:0..1)→ payment_tips
  │            └─(1:N)→ refunds  (also independently, nullable: refunds.order_id → orders)
  │
  ├─(N:1, nullable)→ devices
  └─(N:1, nullable)→ table_services  ← physical_tables (M:N), employees (M:N), orders (1:N)

devices — resolved via a canonical `device_id` FK on orders/payments/refunds where
          the source device can be resolved (added by TASK_DATABASE_002), with the
          raw `device_source_id` string always preserved alongside it (see § 5, § 10)
refunds.device_id / refunds.device_source_id — same pattern (see § 10)
```

Cardinalities not explicit above but confirmed in the module documentation: `Order 1:N OrderItem`, `Order 1:N Payment`, `Payment 1:N Refund`, `TableService M:N PhysicalTable`, `TableService M:N Employee`, `Item M:N Category`, `Item M:N Modifier`, `OrderItem 1:N OrderItemModifier`, `ModifierGroup 1:N Modifier`.

**Restaurant Profile / Organization (TASK_RESTAURANT_001), § 4a:**

```text
restaurants ──< restaurant_locations >── locations   (temporal, valid_from/valid_to, is_primary)
     │
     ├─< operational_areas ──< operational_area_roles >── restaurant_roles ─┐
     │                                                                      │
     ├─< physical_areas                                                    │
     │        └── (0:N, optional FK) physical_tables.physical_area_id      │
     │                                                                     │
     └─< restaurant_roles ────────────────────────────────────────────────┘

employees ──< employee_assignments >── restaurants
                       ├──(N:1)→ operational_areas
                       ├──(N:1)→ restaurant_roles
                       └──(N:1, nullable)→ physical_areas

employee_assignments is temporal (valid_from required, valid_to nullable/open-ended)
and independent of Shift/employees.active — see Organization/Employee Assignment.md
for the Tips/Payroll resolution path (period → Shift → Employee Assignment → Area/Role).
```

**Tips (TASK_TIPS_001), § 4b:**

```text
restaurants ──< tip_policies (temporal, valid_from/valid_to, optional location_id)
                     └─< tip_policy_components ──(N:1, nullable)→ restaurant_roles

restaurants ──< tip_calculation_runs
                     ├─< tip_allocations ──(N:1)→ payment_tips, payments, orders,
                     │                             tip_policy_components, employees
                     └─< tip_calculation_issues ──(N:1, nullable)→ payment_tips, payments, orders

payment_tips (unchanged, § 10) ← read-only source for tip_allocations/tip_calculation_issues;
never duplicated, never given its own timestamp — the anchor is always payments.created_at.
```

---

## 14. Direct vs. derived — summary

Every field in this schema is a **direct source/canonical fact**, never a KPI or aggregate — matching modeling principle B (task §4). The only borderline cases, called out explicitly so a future reviewer does not mistake them for atomic source facts:

- `table_services.derived_guest_count` — **derived** from atomic `order_items.guest_number` evidence (`MAX` within the appropriate grouping), but retained as a stored value because doing so materially improves validation, querying, and process-quality analysis (Restaurant Sales Model §11) — not computed inside this schema, expected to be written by a future reconstruction step.
- `table_services.reconstruction_status`/`reconstruction_confidence` — outputs of **future** reconstruction logic not implemented here; present as placeholders only.

Everything else — every Order, OrderItem, Payment, Refund, Tax, Fee, Discount, Shift, and catalog field — is a direct, atomic fact as observed (or, for `rate`/`percentage`, a canonical re-expression of a source-supplied number, never a computed aggregate).
