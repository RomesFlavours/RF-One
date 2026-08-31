# TASK_ORGANIZATION_001 — Restaurant Profile / Organization Completion & Production Readiness Audit — REPORT

**Type:** Audit (read-only inspection + test execution against disposable databases; no schema/domain redesign)
**Scope:** `01 Domains/Restaurant/Organization/`, `01 Domains/Restaurant/Restaurant Semantic Model.md`, `01 Domains/Restaurant/Model/OU-Restaurant.md` + `OperationalArea.md`, `03 Software/RF-One Data Store/` (models, migrations, bootstrap engine, Tips/Payroll consumers), current runtime database (`data/rfone.db`, read-only inspection)

---

## A. Executive conclusion

**PRODUCTION READY WITH MINOR FIXES**

---

## B. Canonical model found

The Organization module (TASK_RESTAURANT_001/002/003, `01 Domains/Restaurant/Organization/` + `Restaurant Semantic Model.md`) already exists in depth and is implemented end-to-end in the RF-One Data Store. Canonical entities:

| Entity | Table | Responsibility |
|---|---|---|
| Restaurant | `restaurants` | Canonical business/operational identity (name, legal_name, status, default_currency, default_timezone) — not a Clover Merchant, not a Location. |
| Restaurant Location | `restaurant_locations` | Temporal Restaurant ↔ Location association (`valid_from`/`valid_to`/`is_primary`) — deliberately normalized, not a single FK, so one Restaurant supports one or many Locations over time. |
| Operational Area | `operational_areas` | Restaurant-configured *functional* grouping (e.g. FOH/BOH) — free string, Restaurant-scoped, never a hard-coded enum. |
| Physical Area | `physical_areas` | Restaurant-configured *physical* zone (e.g. Dining Room/Patio) — structurally independent from Operational Area. |
| Restaurant Role | `restaurant_roles` | Restaurant-configured canonical operational role (Server/Host/Manager/...), independent from Clover `SourceRole` and `Employee.system_role`. |
| Operational Area ↔ Role | `operational_area_roles` | M:N — which Role/Area combinations a Restaurant permits (not the assignment itself). |
| Employee Assignment | `employee_assignments` | Temporal fact: Employee + Restaurant + Operational Area + Restaurant Role (+ optional Physical Area), `valid_from`/`valid_to`, `assignment_source` provenance. |
| Source-control/mapping layer (TASK_RESTAURANT_003) | `restaurant_profile_source_controls`, `source_role_mappings`, `profile_bootstrap_runs`, `restaurant_profile_reconciliation_issues` | Explicit, auditable `SourceRole → RestaurantRole` mapping and a persisted `T0` (the moment RF-One begins managing a Restaurant's Profile prospectively from source evidence) — never a name-based equivalence. |

`Employee` itself (`employees` table, FK'd to `locations`) is not re-defined by Organization — it is the single canonical Employee identity already established for Sales, and Organization, Tips and Payroll all reference it by the same integer FK.

---

## C. Business / Restaurant identity

**Status: Sound.** `restaurants.id` is the stable RF-One identity. `name`/`legal_name`/`status`/`default_currency`/`default_timezone` are distinguished from Clover `Merchant`/`Location` fields — the model does not duplicate every source field, only genuine business identity. No source-provenance columns exist on `Restaurant` (correct — it is RF-One/business-configured identity, not an ingested entity). Currently exactly one row exists (`Rome's Flavours - WP`), created once from unambiguous Clover evidence; no code path in the ingestion pipeline (`rfone_data_store/ingestion/clover/*`) creates `Restaurant` rows automatically — only test/validation fixtures ever instantiate `Restaurant`. This rules out silent duplicate-Restaurant creation in production.

---

## D. Location model

**Status: Sound, multi-location-ready, timezone-capable but currently unpopulated.**

- `restaurant_locations` correctly separates Restaurant identity from Location association, with `valid_from`/`valid_to`/`is_primary` — a second Location can be added without any schema change (Winter Park + Mount Dora is directly representable).
- `locations.timezone` and `restaurants.default_timezone` both exist and are nullable — honestly `NULL` today because Clover exposes no timezone field on the current Merchant (documented, not fabricated). No business-date/calendar logic exists anywhere in the codebase yet (confirmed by grep — no `zoneinfo`/`pytz`/business-date helpers); Tips/Payroll currently operate on raw UTC-normalized timestamps, not timezone-aware business dates. This is a real, but currently non-blocking, gap — see § J/L.
- **Cross-domain scoping is correctly implemented, not just documented**: `rfone_data_store/profile/bootstrap.py`, `rfone_data_store/tips/engine.py`, and `rfone_data_store/payroll/adp_importer.py` all independently resolve a Restaurant's Location set via `RestaurantLocation` before touching `Employee`/`SourceRole`/`Payment` — the same pattern implemented three times, consistently, across three modules.

---

## E. People / Employee identity

**Status: Sound.** `employees` is the single canonical Employee identity (FK'd to `locations`), reused unmodified by Sales (`orders.employee_id`, `payments.employee_id`), Organization (`employee_assignments.employee_id`), Tips (`tip_allocations.employee_id`), and Payroll (`employee_compensation_terms.employee_id`, `payroll_provider_employee_identities.employee_id`). No parallel Employee concept exists anywhere in the schema. `Employee.active` is nullable (Clover exposes no such field) and is explicitly, correctly documented and enforced-by-convention as **never** the basis for period-participation decisions — that determination is Shift-evidence-only (`Restaurant Semantic Model.md` § 9). Historical Employee stubs (`display_name IS NULL`) are never touched by the bootstrap engine — verified in both the domain doc and the code (`bootstrap.py`, `historical_stubs_skipped` counter, test Case 6).

---

## F. Roles / Assignments

**Status: Sound, verified by passing synthetic tests.** Role/Area changes never overwrite history: a change closes the prior `EmployeeAssignment` row (`valid_to` set) and opens a new one (`valid_from` = the change instant) — enforced by application logic and directly exercised by the bootstrap engine's synthetic test suite (Case 10/11, passing — see § O). Multiple concurrent assignments for one Employee are supported (e.g. Manager valid in both FOH and Management at once — Case 7, passing) and correctly deduplicated by Employee identity in Tips eligibility resolution. The only DB-level uniqueness constraint (`employee_id, operational_area_id, restaurant_role_id, valid_from`) rejects exact duplicate rows only, never legitimate concurrency or re-assignment — this is a deliberate, documented, and tested design choice, not an oversight.

---

## G. External-system mappings

**Status: Sound.** `SourceRole ≠ RestaurantRole` is enforced structurally (separate tables, separate PK sequences — asserted directly by a passing test, `profile_validation.py` Case 3/4) and connected only through an explicit `source_role_mappings` row, never a name-based equivalence, even when the Restaurant's initial Role names happen to match Clover's Role names. `Employee.system_role` (Clover's systemRole tier) is never overwritten. No RF-One primary key is ever a raw external ID — external identifiers are always separate nullable columns/mapping tables (`source_system_id`/`source_*_id` pairs, `payroll_provider_employee_identities`), leaving room for a second/future POS or payroll provider to coexist without displacing canonical identity (Scenario 9).

---

## H. Cross-domain identity

**Verified, not merely asserted**, by direct inspection of `models.py` and the ingestion/engine code:

- **Restaurant**: referenced by `employee_assignments`, `tip_policies`, `tip_calculation_runs`, `payroll_schedules`, `payroll_runs`, `workweek_definitions`, `employee_compensation_terms` (indirectly via role), and **Purchasing's `suppliers.restaurant_id`** — Purchasing does not invent a competing Restaurant/Location concept.
- **Location**: referenced consistently by `employees`, `orders`, `items`, `physical_tables`, `tax_rates`, etc. — one canonical `locations` table throughout.
- **Employee**: one canonical table, referenced identically by Sales, Tips, Payroll and Organization (§ E above).
- **Restaurant Role**: shared by `operational_area_roles`, `employee_assignments`, **and** `tip_policy_components.restaurant_role_id`, **and** `employee_compensation_terms.restaurant_role_id` (Payroll) — Sales/Tips/Payroll do not each invent their own Role concept; all reference the one Organization-owned `restaurant_roles` table.

No architectural duplication (Category C) was found. This is the single strongest finding of this audit: the "master data foundation" claim in the task brief is actually true in the implemented code, not just in documentation.

---

## I. Scenario validation

| # | Scenario | Result | Notes |
|---|---|---|---|
| 1 | Single-location restaurant | **PASS** | Exactly this — current real runtime state. |
| 2 | Multi-location restaurant | **PASS** | Structurally supported (`restaurant_locations` 1:N); scoping logic verified in bootstrap/Tips/Payroll code. Not yet exercised with real second-Location data (none exists) — see § J for the one related minor gap (primary-location uniqueness not enforced). |
| 3 | Employee works two locations | **PASS** | `Employee.location_id` is single, but `EmployeeAssignment` is Restaurant/Area/Role-scoped and unlimited per Employee; an Employee at Location A can hold Assignments under any Operational Area the owning Restaurant configures across its Locations. No duplicate Person required. |
| 4 | Employee changes role | **PASS** | Verified by passing synthetic test (Case 10/11): old Assignment closed (`valid_to` set, `valid_from` untouched), new Assignment opened, never an in-place overwrite. |
| 5 | Employee leaves | **PASS** | `Employee.active` supported as an administrative field but never used for period-resolution (Shift evidence only) — historical Sales/Tips/Payroll records remain valid regardless of current `active` value. No destructive deletion path exists. |
| 6 | Location closes | **PASS** | `locations.active` (non-nullable, defaults `True`) supports deactivation without deletion; no cascade delete is configured anywhere (SQLite `PRAGMA foreign_keys=ON`, no `ondelete=CASCADE` on any historical FK), so a Location cannot be deleted while historical Orders/Employees reference it — the DB itself blocks that destructive path. |
| 7 | Restaurant/location rename | **PASS** | `name` is a plain mutable column; no historical record anywhere stores a denormalized copy of Restaurant/Location name, so a rename cannot desynchronize history. |
| 8 | Clover employee mapping | **PASS** | `employees.source_system_id`/`source_employee_id` are separate from `employees.id`; RF-One identity is independent. |
| 9 | Future second POS | **PASS** | Provenance columns are nullable and scoped per source system (`UniqueConstraint(source_system_id, source_*_id)`); nothing assumes exactly one source system. |
| 10 | Missing external identity | **PASS** | Every `source_system_id`/`source_*_id` pair is nullable; a manually created canonical entity with no source mapping is a structurally valid row. |
| 11 | Manager responsibility (reports-to / location responsibility) | **OUTSIDE DOMAIN BY DESIGN** | No `manager_id`/`reports_to`/"responsible for Location" concept exists anywhere in the schema (confirmed by direct grep). Nothing currently consuming Organization (Tips, Payroll, Purchasing's `BusinessPermissions.md`) requires it. A `Manager` **Restaurant Role** exists and can be assigned to an Operational Area, which is a different, already-modeled fact ("this person functions as Manager here"), not an org-chart responsibility edge. Per CLAUDE.md's instruction not to build an org-chart system speculatively, this is correctly left unbuilt, not a missed requirement. |

---

## J. Production blockers

**None.**

No Category A (Critical Domain Gap) or Category C (Cross-Domain Identity Gap) issue was found. The items below are real but non-blocking (Category B/D/E, and one deliberate-scope item), listed for completeness — none prevents the current single-location, single-timezone production deployment, and none requires an architectural change:

1. **(Category B, minor)** No DB- or application-level enforcement of "at most one `is_primary = true`, currently-open `RestaurantLocation` row per Restaurant." Currently moot (exactly one Location, one `RestaurantLocation` row exists), but should be addressed with a small validation helper (mirroring the existing `_restaurant_location_ids` scoping pattern already used by three modules) before a second real Location is onboarded — see § L.
2. **(Category D, minor, honestly documented rather than hidden)** `Location.timezone`/`Restaurant.default_timezone` are structurally present but unpopulated (Clover supplies no timezone field), and no business-date/timezone-aware calendar logic exists yet anywhere in the codebase. Not a blocker for the current single-timezone deployment; becomes relevant only once a second Location in a different timezone, or timezone-sensitive business-date logic (e.g. a "which business day did this Shift belong to" rule), is actually needed.
3. **(Category E, documentation only)** Several approved Organization/Software documents cite `07 Tasks/Reports/TASK_RESTAURANT_001_REPORT.md`, `TASK_RESTAURANT_002_REPORT.md`, `TASK_RESTAURANT_003_REPORT.md`, `TASK_CLOVER_004_REPORT.md`, `TASK_DATABASE_003_REPORT.md`, `TASK_EMPLOYEE_002` — none of these report files exist anywhere in the working tree, `90 Archive/`, or git history. This is explained by a previously documented, unrelated incident (`07 Tasks/Reports/PRE_COMMIT_AUDIT.md` § D.1: an out-of-band filesystem event that removed `07 Tasks/` contents before the current commit `a24e133` was made), not a defect introduced by the Organization work itself, and not something this audit can restore (content unknown). Dangling references only — the actual domain content they describe is present, consistent, and implemented.

---

## K. Minor fixes performed

**None.** No code, schema, or documentation edits were made. Every check performed (schema validation, the Restaurant Profile bootstrap synthetic test suite, the Tips and Payroll engine synthetic test suites, direct inspection of the production database) passed without revealing a defect that met the bar for an in-scope, unambiguous, minimal fix. The three items in § J are real but each requires either a small forward-looking addition with no current data to validate it against (item 1) or a Product-Owner-confirmed input this audit cannot fabricate (item 2, a real timezone value) or is out of this task's edit scope (item 3, approved-document cross-references pointing at genuinely lost files). Per CLAUDE.md, none was force-fixed speculatively.

---

## L. Future enhancements

- Add a small application-level validation helper enforcing "at most one open, primary `RestaurantLocation` per Restaurant" before a second real Location is onboarded (Category B item above) — mirrors the existing Restaurant-scoping helper pattern already used identically in `profile/bootstrap.py`, `tips/engine.py`, and `payroll/adp_importer.py`.
- Populate `locations.timezone`/`restaurants.default_timezone` with a Product-Owner-confirmed value once a genuine source (operator input, or a future POS/provider that exposes it) is available; build business-date logic only when a real consumer (e.g. Scheduling, a business-day-bounded Tips/Payroll period) actually needs it.
- Optional `parent_id` on `operational_areas`/`physical_areas` (hierarchy already specified in `Restaurant Semantic Model.md` § 5.2/6.2 but not yet in the runtime schema) — explicitly documented as deferred until a real Restaurant Profile needs it; not required now.
- Resolve the dangling `TASK_RESTAURANT_00x`/`TASK_CLOVER_004`/`TASK_DATABASE_003` report references (§ J item 3) — either by Product Owner confirming the content can be reconstructed, or by a small documentation task replacing the citations with a note that the originating reports were lost.

None of the above is required for production readiness; none should block the module's use as the canonical organizational foundation.

---

## M. Product Owner decisions required

**None.** No genuine architectural ambiguity blocked this audit. The one item with alternatives (exact semantics of "primary Location" enforcement — e.g. whether a Restaurant may legitimately have zero primary Locations mid-transition) is a small, well-scoped follow-up, not a decision blocking today's production readiness.

---

## N. Exact files changed

**None.** This was a read-only audit. No file in the repository was created, modified, or deleted by this task. All test execution was performed against disposable, gitignored copies of the database in the session scratchpad directory (never `data/rfone.db`), each rolled back or discarded after use.

---

## O. Tests and validation

All commands below were run against a **freshly migrated, empty database** created via `create_database.py` (Alembic `upgrade head`, 7 revisions applied cleanly) at `<scratchpad>/rfone_fresh_test.db` — never against the real `data/rfone.db`.

| Command | Result |
|---|---|
| `python create_database.py` (fresh DB, all 7 migrations) | **SUCCESS** — 74 tables created, schema validation 29/29 checks passed |
| `python test_restaurant_profile_bootstrap.py` | **SUCCESS** — 14/14 checks passed (covers: T0 establishment, SourceRole≠RestaurantRole separation, Assignment starts at T0 not before, historical-stub exclusion, concurrent-Assignment support, unmapped-SourceRole issue surfacing, role-change history preservation without overwrite, idempotent re-run, dry-run leaves zero persisted rows, Tips engine still requires an explicit Policy after Assignments exist) |
| `python test_tips_engine.py` | **SUCCESS** — 35/35 checks passed (Tips is the primary real consumer of `EmployeeAssignment`) |
| `python test_payroll_engine.py` | **SUCCESS** — 30/30 checks passed (Payroll is the other real consumer of `RestaurantRole`) |

**Real production database inspection (read-only, `sqlite3` direct query, no writes):**

```text
restaurants: 1   restaurant_locations: 1   operational_areas: 1   physical_areas: 0
restaurant_roles: 7   operational_area_roles: 7   employee_assignments: 24
employees: 37 (24 current + 13 historical stubs, matching bootstrap's own accounting)
source_role_mappings: 7   restaurant_profile_source_controls: 1
restaurant_profile_reconciliation_issues: 0
```

This matches `RESTAURANT_PROFILE.md` § 6's documented bootstrapped state exactly — no drift between documentation and the real database, and zero unresolved reconciliation issues.

**Code-path inspection (no hardcoded production assumptions found):**
- `bootstrap_restaurant_profile.py` and `calculate_tips.py` both require `--restaurant-id` as an explicit CLI argument; no script defaults to `restaurant_id=1`.
- `grep` for `m.Restaurant(` across the codebase shows Restaurant rows are only ever instantiated by test/validation fixtures — no ingestion or bootstrap code path auto-creates a `Restaurant` row.
- No `ondelete=CASCADE` exists on any foreign key touching historical data; SQLite's `PRAGMA foreign_keys=ON` is enabled (`database.py`), so a delete of a referenced Location/Employee/Restaurant is rejected by the database itself rather than silently cascading.
- No `manager_id`/`reports_to`/`supervisor` column exists anywhere in `models.py`.

---

## P. Git status

Confirmed via `git status` at the start and no writes were made during this task. Pre-existing uncommitted work (staged `InvoiceIntake` deletions; unstaged edits across Core/Domains/Software; untracked Purchasing task files and reports) is **unchanged and untouched** by this audit. **No commit was made.**

---

## Q. Final readiness statement

`RESTAURANT PROFILE / ORGANIZATION STATUS: PRODUCTION READY`

The module is production ready for its intended role as the canonical organizational foundation, for the current single-location deployment today, and is architecturally ready (not merely "intended to be ready") for multi-location use. The "WITH MINOR FIXES" qualifier in § A reflects two small, non-blocking follow-ups worth completing soon rather than any defect blocking go-live:

1. Add primary-Location uniqueness validation before a second real Location is onboarded (§ J.1, § L).
2. Populate genuine timezone data once available (§ J.2, § L) — needed only when a second timezone or business-date-sensitive logic is actually introduced.

Neither withholds production use of the module as it stands today.
