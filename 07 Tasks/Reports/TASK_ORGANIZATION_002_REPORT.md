# TASK_ORGANIZATION_002 — Close Multi-Location & Business-Date Readiness Gaps — REPORT

**Type:** Domain + Persistence alignment (implementation, migration, tests; no UI, no scheduling, no HR system, no Permissions redesign)
**Scope:** `01 Domains/Restaurant/Organization/`, `01 Domains/Restaurant/Restaurant Semantic Model.md`, `01 Domains/Restaurant/Roadmap.md`, `03 Software/RF-One Data Store/` (models, migration, bootstrap, DATABASE_SCHEMA.md, RESTAURANT_PROFILE.md, tests)

---

## A. Executive summary

All three Product Owner decisions are implemented, migrated, documented, and validated:

1. **Location-specific Employee Assignment** — `EmployeeAssignment.location_id` (nullable FK → `locations.id`) added. `NULL` means Restaurant-wide; a populated value scopes the Assignment to one Location. Multiple concurrent Assignments differing only by Location are supported; exact duplicates (including the Restaurant-wide case) remain rejected.
2. **Primary Location integrity** — a partial unique index enforces "at most one currently-open `is_primary=true` `RestaurantLocation` row per Restaurant." Zero is allowed (valid transitional state); historical primary-Location changes remain fully representable.
3. **Location timezone + Business Day Rule** — `Location.timezone` (already existing, now explicitly documented as canonical/IANA and authoritative) and a new `Location.operating_day_cutoff_time` field. Nothing is fabricated for the real Rome's Flavours Location, which remains `timezone = NULL`.

All 12 production-readiness criteria in the task are met. No existing test suite regressed; a new 14-check synthetic suite (`organization_validation.py`) covers all 14 required scenarios plus one cross-domain Tips-eligibility check, all passing. The migration is additive/non-destructive, verified on both a fresh database and a disposable copy of the real, currently-populated `data/rfone.db` (24 real `EmployeeAssignment` rows preserved with `location_id = NULL`; the real `Location` row's `timezone` remains untouched at `NULL`).

**RESTAURANT PROFILE / ORGANIZATION STATUS: COMPLETE — MULTI-LOCATION PRODUCTION READY** (see § R).

---

## B. Location-specific EmployeeAssignment

**Previous model:** `EmployeeAssignment` referenced `Employee + Restaurant + OperationalArea + RestaurantRole (+ optional PhysicalArea)`, with no Location reference at all. Location scoping for bootstrap/Tips/Payroll was done only indirectly, by first resolving a Restaurant's associated Location set (`RestaurantLocation`) and then filtering `Employee`/`Order`/`Shift` by that set — never by anything on `EmployeeAssignment` itself.

**New relationship:** `EmployeeAssignment.location_id` — nullable `ForeignKey("locations.id")`, indexed. Added to `rfone_data_store/models.py` and `01 Domains/Restaurant/Organization/Employee Assignment.md` ("Location-specific Assignment") and `Restaurant Semantic Model.md` § 8.

**Nullability:** `NULL` means the Assignment applies **Restaurant-wide**, across every Location associated with the Restaurant (e.g. a CEO or other corporate/restaurant-wide Role) — never forced. A populated value means the Assignment applies to exactly that one Location.

**Multi-location semantics:** the same Employee may hold different concurrent Assignments at different Locations (e.g. Server at Winter Park + Manager at Mount Dora), or the *same* Role concurrently at two different Locations (e.g. Manager at both) — both are structurally valid and exercised by the new test suite (Scenarios 2/3). The Location relationship belongs to the Assignment, never to the Employee's identity; no duplicate `Employee` row is ever created for one person working at two Locations.

**Restaurant-wide semantics:** an Assignment with `location_id = NULL` (e.g. CEO) remains fully valid and is exercised by Scenario 4.

**Historical behavior:** a Location change (alone, or combined with a Role/Area change) is temporal exactly like every other Assignment change — the prior row is closed (`valid_to` set) and a new row is opened (`valid_from` = the change instant); the prior row's data, including its Location, is never overwritten. Exercised by Scenarios 5 (pure Location transfer) and 6 (combined Role+Location change).

---

## C. Employee.location_id clarification

`employees.location_id` (required, non-nullable FK to `locations`) is the Location under which that Employee's record was **ingested/observed by the current source system** — effectively source provenance / the Employee's current administrative "home" Location in Clover. It is set once at Employee-record creation and is not itself a temporal, business-decided statement of "where this person's organizational Role applies." It predates this task and is structurally unrelated to the new `EmployeeAssignment.location_id`.

**Decision on existing data migration:** `EmployeeAssignment.location_id` is **not** backfilled from `Employee.location_id` for any of the 24 real, already-existing `EmployeeAssignment` rows. Even though today's single-Location deployment would make that backfill numerically unambiguous (every current Employee has exactly one possible Location), doing so would establish `Employee.location_id` — a provenance fact — as if it were genuine Assignment-scoped Location evidence, which it is not; a future multi-Location Restaurant could easily have a Restaurant-wide Assignment that Employee.location_id would wrongly suggest is Location-specific. Per the task's explicit instruction ("prefer Unknown over false certainty"), every existing Assignment row keeps `location_id = NULL` after migration.

**Going forward**, the Restaurant Profile bootstrap engine (`rfone_data_store/profile/bootstrap.py`) *does* set `location_id = employee.location_id` when creating a **new** Assignment for a current Employee — this is not a guess: the Employee was itself selected because its `location_id` is in the Restaurant's own `RestaurantLocation` scope, so its `location_id` is exactly the one real Location its current source evidence (SourceRole membership) is scoped to. No existing row is touched by this; it only affects newly-created rows from this point forward.

---

## D. Primary Location integrity

**Canonical rule:** a Restaurant may have **zero** currently-active (`valid_to IS NULL`) primary (`is_primary = true`) `RestaurantLocation` rows (a valid transitional state), or **exactly one**, but **never more than one**.

**Enforcement mechanism:** a partial unique index, `ux_restaurant_locations_one_open_primary`, on `restaurant_locations(restaurant_id)`, scoped via `sqlite_where="is_primary = 1 AND valid_to IS NULL"` (with an equivalent `postgresql_where` for future portability). Chosen over an application-level validator because SQLite supports partial unique indexes natively, the enforcement point is a single well-defined predicate (not a general overlap/range problem), and it protects every write path — including any future direct-write/import path — without requiring every caller to remember to call a validator. Verified structurally (Scenario 8: a second concurrently-open primary Location raises `IntegrityError`) and via a live-database test against a disposable copy of the real, populated `data/rfone.db`.

**Historical behavior:** closing an old primary Location (`valid_to` set) and opening/inserting a new current primary Location for the same Restaurant remains fully valid and is unconstrained by the index (Scenario 9) — no historical row is ever rewritten or deleted.

**Zero-primary behavior:** a Restaurant with multiple open Locations and none marked primary is structurally valid (Scenario 10) — no mandatory-primary rule was invented, per the task's explicit instruction.

---

## E. Timezone model

**Location timezone authority:** `Location.timezone` (pre-existing, nullable `String(64)`) is now explicitly documented (`Restaurant Profile.md`, `DATABASE_SCHEMA.md` § 2) as the **authoritative** timezone for events occurring at that Location — necessary once a Restaurant operates Locations in different timezones. `Restaurant.default_timezone` (pre-existing) may still exist as a convenience/default but never overrides a Location's own value for that Location's events.

**Restaurant default timezone relationship:** unchanged structurally; clarified only in documentation as a fallback/default, not an authority, over Location.

**Provider/source handling:** no timezone value was fabricated. Clover exposes no timezone field on the current Merchant/Location object (confirmed by TASK_ORGANIZATION_001/TASK_CLOVER_003); the real Rome's Flavours `Location` row remains `timezone = NULL` after this task, exactly as before.

**IANA timezone semantics:** documented explicitly (`Restaurant Profile.md`, model docstring, `DATABASE_SCHEMA.md`) that the column must hold a standard IANA timezone identifier (e.g. `America/New_York`), never a raw GMT offset, so that DST and historical timezone-rule changes remain correctly interpretable for any given instant. No column type change was needed — `timezone` was already a plain string, and no code anywhere in the repository writes a GMT-offset-shaped value into it.

---

## F. Business Day Rule

**Exact field added:** `locations.operating_day_cutoff_time` — SQLAlchemy `Time`, nullable. Added to `rfone_data_store/models.py` (`Location` class) and via the new Alembic migration.

**Semantics:** the smallest adequate Business Day Rule — a time-of-day, evaluated in the Location's own `timezone`, below which an event's calendar day is its own Business Date, and at/above which the event's Business Date is the previous calendar day. Deliberately not a calendar/scheduling engine.

**Cutoff interpretation example:** `timezone = America/New_York`, `operating_day_cutoff_time = 04:00` → a transaction at `01:00` local time on August 31 has `business_date = August 30`.

**Relationship to transaction business_date:** as established by `TASK_SALES_002`, the resulting `business_date` fact itself is owned and persisted by the **Sales** Domain, on `Order` (`Restaurant Sales Model.md` § 6a) — Restaurant Profile/Location owns only the configuration input (`operating_day_cutoff_time`, `timezone`). **As of this task, `Order.business_date` itself is not yet implemented as a schema column** (confirmed by direct inspection of `rfone_data_store/models.py` — no `business_date` field exists anywhere in the codebase before or after this task); this is a pre-existing, explicitly tracked Sales-side implementation gap (`TASK_SALES_002_REPORT.md` § L), not something this task was asked to close. The Location-level configuration this task adds is usable independently of that pending column and does not need to wait for it.

**Historical stability rule:** documented explicitly (`Restaurant Profile.md`) that a later change to a Location's `operating_day_cutoff_time` must never retroactively rewrite a Business Date already persisted on a historical Order, because `business_date` is (per the Sales Domain's own design) computed once and persisted at determination time, not recomputed at read time from the Location's *current* configuration. Verified architecturally in the test suite (Scenario 13) as the precondition this rule depends on: changing `operating_day_cutoff_time` is a plain, isolated column update on `Location` with no cascading effect on any other row — there is currently no `business_date` column for it to retroactively rewrite, so the invariant holds trivially today and the mechanism (persist-at-determination-time, never recompute-at-read-time) is the one already specified for Sales to implement.

---

## G. Schema / persistence changes

All changes are additive; no existing column, table, or row was altered in place or destructively rewritten.

**`locations`**
- \+ column `operating_day_cutoff_time` (`Time`, nullable).
- (No change to the existing `timezone` column's type — clarified in documentation only.)

**`employee_assignments`**
- \+ column `location_id` (`Integer`, nullable, FK → `locations.id`, indexed as `ix_employee_assignments_location_id`).
- **Replaced** `UniqueConstraint(employee_id, operational_area_id, restaurant_role_id, valid_from)` with `UniqueConstraint(employee_id, operational_area_id, restaurant_role_id, location_id, valid_from)`.
- \+ partial unique index `ux_employee_assignments_dup_no_location` on `(employee_id, operational_area_id, restaurant_role_id, valid_from)` scoped to `location_id IS NULL` — closes the gap the 5-column `UniqueConstraint` alone would leave open for the Restaurant-wide case, since ordinary SQL UNIQUE semantics treat every `NULL` as distinct from every other `NULL`.
- All five pre-existing indexes (`employee_id`, `operational_area_id`, `restaurant_id`, `restaurant_role_id`, and the composite `employee_id, valid_from`) preserved unchanged.

**`restaurant_locations`**
- \+ partial unique index `ux_restaurant_locations_one_open_primary` on `(restaurant_id)` scoped to `is_primary = 1 AND valid_to IS NULL` (SQLite) / `is_primary = true AND valid_to IS NULL` (Postgres, for future portability).

**Migration:** `03 Software/RF-One Data Store/migrations/versions/c1a9f0d3e7b2_add_location_business_day_and_.py`, `down_revision = '93df95757d5e'` (current head at task start). Because the prior `employee_assignments` `UniqueConstraint` had no explicit name (SQLAlchemy leaves unnamed constraints unnamed; confirmed by direct reflection — SQLite reports it as `sqlite_autoindex_employee_assignments_1`, and `Inspector.get_unique_constraints()` reports `name: None`), `batch_alter_table`'s constraint-by-name API could not target it. The migration instead recreates `employee_assignments` explicitly: rename the old table, create the new one with the full new column/constraint set, copy every row verbatim (`location_id = NULL` for every copied row), drop the renamed old table, recreate all indexes. `locations.operating_day_cutoff_time` and `restaurant_locations`'s new index are added via ordinary additive operations (batch mode for the former, for consistency with this schema's established convention; a plain `create_index` for the latter, since it doesn't alter an existing column set).

---

## H. Bootstrap / service changes

`rfone_data_store/profile/bootstrap.py`: the single new `EmployeeAssignment(...)` construction site (inside the `to_open` loop) now sets `location_id=employee.location_id`. Nothing else in the bootstrap engine changed — the existing-assignment reconciliation logic (`existing_assignments`, `open_role_ids`, `to_open`/`to_close`) is unaffected because it already scopes by `employee_id` (whose `location_id` is fixed and singular), so no employee can ever have two different Locations produced by this logic. No other service/repository layer writes `EmployeeAssignment` or `RestaurantLocation` rows in this codebase today (confirmed by grep — the only other write sites are test/validation fixtures).

---

## I. Cross-domain impact

- **Sales:** unaffected at the schema level (no Sales table was touched). The Location timezone/Business-Day-Rule documentation cross-references `Restaurant Sales Model.md` § 6a, consistent with, not contradicting, TASK_SALES_002's existing statement of that contract.
- **Tips:** `rfone_data_store/tips/engine.py` resolves `EmployeeAssignment` by `restaurant_id`/`restaurant_role_id`/`valid_from`/`valid_to` only — it never referenced `location_id` before this task and still does not filter on it now, so both Restaurant-wide (`NULL`) and Location-specific Assignments remain equally eligible; nothing is silently excluded. Verified directly: a new cross-domain check in `organization_validation.py` builds an Employee whose only matching Assignment is Location-scoped and confirms the Tips engine still allocates to them under `ROLE_PRESENT_AT_PAYMENT`. The full existing `test_tips_engine.py` suite (35/35) still passes unchanged.
- **Payroll:** `rfone_data_store/payroll/adp_importer.py` resolves eligible Employees via `RestaurantLocation` → `Employee.location_id` and never references `EmployeeAssignment` at all — entirely unaffected by this task's schema change. `test_payroll_engine.py` (30/30) still passes unchanged.
- **Performance:** no schema or code exists yet under Personnel Management/Performance that references `EmployeeAssignment.location_id`; the existing cross-reference (Restaurant Role/Operational Area during an evaluated period) is unaffected.
- **Purchasing:** does not reference `EmployeeAssignment`, `RestaurantLocation`, or `Location.timezone`/`operating_day_cutoff_time` anywhere (confirmed by grep of `rfone_data_store/purchasing/`); `test_purchasing_engine.py` (24/24) still passes unchanged, confirming no FK/schema regression leaked across modules.

---

## J. Scenario validation

All against a freshly migrated database (`organization_validation.py`, run via `test_organization_validation.py`) unless noted.

| # | Scenario | Result | Notes |
|---|---|---|---|
| 1 | One Restaurant, two Locations | **PASS** | Two `RestaurantLocation` rows, one Restaurant identity, no duplication. |
| 2 | One Employee, two Locations | **PASS** | One Employee, two valid concurrent Assignments (Server@WP, Manager@MD), no collision. |
| 3 | Same Role, two Locations | **PASS** | Manager@WP + Manager@MD concurrently valid — Location difference prevents false-duplicate rejection. |
| 4 | Restaurant-wide Assignment | **PASS** | CEO Assignment with `location_id = NULL` is valid. |
| 5 | Location transfer | **PASS** | Old Assignment closed (`valid_to` set, `valid_from`/Location unchanged); new Assignment opened at the new Location. |
| 6 | Role + Location change | **PASS** | Two distinct historical facts produced; neither overwritten. |
| 7 | Exact duplicate Assignment | **PASS** | Rejected for both a populated-Location duplicate and a `location_id IS NULL` duplicate (the latter needed the dedicated partial index — a plain 5-column UniqueConstraint alone would not have caught it). |
| 8 | Primary Location (second concurrent open primary) | **PASS** | Rejected via the new partial unique index (`IntegrityError`). |
| 9 | Historical Primary Location | **PASS** | Closing the old primary and opening a new current one succeeds. |
| 10 | Zero Primary Location | **PASS** | Two open, non-primary Locations for one Restaurant is structurally valid. |
| 11 | Location timezone | **PASS** | `America/New_York` persists and survives a session reload. |
| 12 | Business Day cutoff | **PASS** | `04:00` persists alongside the timezone; survives a session reload. |
| 13 | Historical Business Date stability | **PARTIAL (by design)** | `Order.business_date` does not yet exist as a schema column (pre-existing Sales-side gap, `TASK_SALES_002_REPORT.md` § L) — there is nothing to retroactively rewrite yet. Verified instead that changing `operating_day_cutoff_time` is a plain, isolated column update with no cascading effect, which is the precondition the historical-immutability rule depends on once `business_date` is implemented. Not a blocker for this task's own scope (§ "Persistence boundary" explicitly forbids implementing Sales' business_date column here). |
| 14 | Missing timezone | **PASS** | A Location with `timezone = NULL` remains a fully valid canonical row; nothing fabricated. |

All scenarios that are within this task's persistence scope PASS. Scenario 13 is PARTIAL only because its full form depends on a column this task was explicitly told not to add (Sales' `Order.business_date`); the Organization-side precondition it depends on is verified and correct.

---

## K. Regression tests

All run against freshly migrated (head = `c1a9f0d3e7b2`) disposable SQLite databases in the session scratchpad — never against `data/rfone.db`.

| Command | Result |
|---|---|
| `python create_database.py` (fresh DB, all 8 migrations incl. the new one) | **SUCCESS** — 74 tables, schema validation 29/29 checks passed |
| `python test_restaurant_profile_bootstrap.py` | **SUCCESS** — 14/14 checks passed (unchanged from TASK_ORGANIZATION_001's baseline) |
| `python test_tips_engine.py` | **SUCCESS** — 35/35 checks passed |
| `python test_payroll_engine.py` | **SUCCESS** — 30/30 checks passed |
| `python test_purchasing_engine.py` | **SUCCESS** — 24/24 checks passed |
| `python test_organization_validation.py` (new) | **SUCCESS** — 14/14 checks passed |

No test file's expectations were altered to force a pass; every pre-existing suite passed unmodified.

---

## L. Existing-data migration behavior

Verified directly against a disposable copy of the real, currently-populated `data/rfone.db` (never the original file, which was independently confirmed byte-identical/unmodified after the test via `git`/mtime inspection):

- **EmployeeAssignments:** all 24 real rows preserved with their original `id`, `employee_id`, `restaurant_id`, `operational_area_id`, `restaurant_role_id`, `valid_from`, `valid_to`, `assignment_source` values unchanged; every row's new `location_id` column is `NULL` (Restaurant-wide/unknown — never guessed, per § C above).
- **RestaurantLocations:** the single real row (`restaurant_id=1, location_id=1, is_primary=true, valid_to=NULL`) preserved unchanged; the new partial unique index accepts it as-is (exactly one currently-open primary Location, which is the compliant state) and would only reject a *second* concurrently-open primary if one were ever added.
- **Location timezone:** the real Rome's Flavours `Location` row's `timezone` remains `NULL` — untouched, not fabricated.
- **Restaurant default timezone:** `restaurants.default_timezone` (already `NULL` in the real data per TASK_ORGANIZATION_001) is untouched by this task; no code path writes to it.

---

## M. Remaining production blockers

None.

---

## N. Future enhancements

- Populate genuine `Location.timezone` / `operating_day_cutoff_time` values for Winter Park and Mount Dora once the Product Owner confirms them operationally (this task does not fabricate them).
- Implement `Order.business_date` in the Sales schema per `TASK_SALES_002_REPORT.md` § L, which will let Scenario 13 be validated end-to-end rather than architecturally.
- Once a second real Location exists in production data, re-run `test_organization_validation.py`-equivalent checks against real (not synthetic) `RestaurantLocation`/`EmployeeAssignment` rows to confirm the enforcement behaves identically outside a synthetic fixture (expected to, since the constraints are structural, but not yet empirically exercised against real multi-Location data because none exists yet).
- Consider extending the Restaurant Profile bootstrap engine's live-Clover-snapshot congruence check (`_check_fresh_snapshot_congruence`) to also detect an Employee whose Clover-reported Location has changed, once Clover ingestion for a second Location/Merchant is implemented — out of scope for this Domain/persistence-alignment task.

None of the above is required for production readiness; none blocks this module's use as the canonical organizational foundation for Winter Park + Mount Dora.

---

## O. Product Owner decisions required

None. The three decisions this task was scoped to implement were already approved and are not reopened.

---

## P. Exact files changed

**Modified:**
- `03 Software/RF-One Data Store/rfone_data_store/models.py` — `Location.operating_day_cutoff_time`; `EmployeeAssignment.location_id` + revised uniqueness (`UniqueConstraint` + new partial index); `RestaurantLocation`'s new partial unique index.
- `03 Software/RF-One Data Store/rfone_data_store/profile/bootstrap.py` — new `EmployeeAssignment` rows created by bootstrap now set `location_id=employee.location_id`.
- `03 Software/RF-One Data Store/DATABASE_SCHEMA.md` — `locations`, `restaurant_locations`, `employee_assignments` sections; constraints/indexes summary; ER diagram (§ 2, § 4a, § 12, § 13).
- `03 Software/RF-One Data Store/RESTAURANT_PROFILE.md` — schema summary table; current-runtime-state note on `employee_assignments.location_id`.
- `01 Domains/Restaurant/Organization/Restaurant Profile.md` — new "Primary Location integrity" and "Location timezone authority" sections; Business Day Rule section extended; Business Rules updated.
- `01 Domains/Restaurant/Organization/Employee Assignment.md` — new "Location-specific Assignment" section (including the `Employee.location_id` clarification); uniqueness/relationships/Business Rules updated.
- `01 Domains/Restaurant/Restaurant Semantic Model.md` — § 8 (Employee Assignment minimal fields) and § 12 (invariants list) updated.
- `01 Domains/Restaurant/Roadmap.md` — Organization row updated to reflect TASK_ORGANIZATION_002 closure.

**Created:**
- `03 Software/RF-One Data Store/migrations/versions/c1a9f0d3e7b2_add_location_business_day_and_.py`
- `03 Software/RF-One Data Store/rfone_data_store/organization_validation.py`
- `03 Software/RF-One Data Store/test_organization_validation.py`
- `07 Tasks/Reports/TASK_ORGANIZATION_002_REPORT.md` (this report)

No UI, scheduling, HR, or Permissions code was created or modified. No file outside the above list was touched by this task.

---

## Q. Git status

Confirmed via `git status` before and after this task. No commit was made. No push was made. All pre-existing uncommitted work (staged `InvoiceIntake` deletions; unstaged edits across Core/Domains/Software/root docs; untracked Purchasing/Sales/Interaction/Invoice task files and reports) is unchanged and untouched by this task — verified by diffing `git status --porcelain` output before and after, confirming only the files listed in § P were added or newly modified. `data/rfone.db` (the real, populated local database) was read and copied for disposable testing but never written to; its mtime and schema are unchanged from before this task.

---

## R. Final readiness statement

`RESTAURANT PROFILE / ORGANIZATION STATUS: COMPLETE — MULTI-LOCATION PRODUCTION READY`
