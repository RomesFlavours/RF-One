# TASK_TIPS_003 — Rome's Flavours Tips Production Deployment Closure — Report

**Origin:** TASK_TIPS_003
**Builds on:** TASK_TIPS_001 (`07 Tasks/Reports/TASK_TIPS_001_REPORT.md`, `COMPLETE — PRODUCTION READY`)

---

## Executive conclusion

**Engine and configuration architecture: COMPLETE.** **Real Rome's Flavours activation: BLOCKED on business-policy input.**

Part B (Shift-level Location evidence) is fully implemented, tested, and closes the residual half of TASK_TIPS_001's Scenario 9. Part A found that no approved Rome's Flavours Tip Policy exists anywhere in the repository — this was confirmed by direct inspection, not assumed — so, per this task's explicit instruction, none was fabricated. A precise decision checklist is provided below instead.

```text
TIPS DEPLOYMENT STATUS: PARTIAL — WAITING FOR PRODUCT OWNER POLICY INPUT
```

---

## Exact findings

### Part A — no approved Tip Policy exists

Searched the entire repository (domain docs, task reports, `RESTAURANT_PROFILE.md`, `OpenQuestions.md`, `06 Meetings/`) for any previously approved percentage, eligible-role list, allocation method, or effective date. Every place that could plausibly contain one instead explicitly disclaims it:

- `01 Domains/Restaurant/Tips/Tip Policy.md`: "no percentage, role name, or component structure in this document ... is a default, a universal rule, or a Rome's Flavours value."
- `03 Software/RF-One Data Store/RESTAURANT_PROFILE.md` §6/§7: "No `TipPolicy`, service-attribution resolver, or Rome's Flavours Tip percentage was configured by this task" (TASK_RESTAURANT_003, explicit non-goal, repeated).
- `07 Tasks/Reports/TASK_TIPS_001_REPORT.md`: real `tip_calculation_runs`/`tip_policies` hold zero rows; Scenario/Product-Owner-decisions section explicitly recorded "no current data to validate a decision against."

Direct inspection of a disposable copy of the real database (never the live file) confirms this is still true today: **0** `TipPolicy` rows, **0** `TipPolicyComponent` rows, **3,326** `PaymentTip` rows all blocked `NO_VALID_POLICY`.

**Conclusion: no approved policy exists. None was fabricated, per instruction.** See "Part A — Product Owner decision checklist" below.

### Part B — Shift had no Location field

Confirmed by direct schema inspection (`rfone_data_store/models.py`, pre-task): `Shift` carried `employee_id`, `clock_in`/`clock_out`, override fields, and `server_banking` — no Location field of any kind. `_shift_active_employee_ids` (`rfone_data_store/tips/engine.py`) used `Employee.location_id` (a single, fixed "home Location") as the only available presence proxy, correctly scoped to the Order's own Location (TASK_TIPS_001's own fix), but unable to distinguish which specific Shift occurred at which Location for an Employee who genuinely works more than one. This was documented as TASK_TIPS_001 Scenario 9 = `PARTIAL` and listed as a non-blocking Future Enhancement (§O of that report) — not a production blocker for the current single-Location deployment, but the exact gap this task was asked to close.

---

## Exact changes

### Part B implementation

1. **Schema** (`rfone_data_store/models.py`): `Shift.location_id` — nullable `Integer` FK to `locations.id`, indexed. Never guessed/backfilled; carries an explicit docstring stating it is populated only by a future, genuinely deterministic per-Shift source.
2. **Migration** (`migrations/versions/d7e21f4a9c3b_add_shift_location.py`): additive `ADD COLUMN` + FK + index on `shifts`, via `batch_alter_table` (SQLite requirement, matching the existing `09631adaed4d`/`b4f3c8a1d6e2` pattern). `downgrade()` cleanly reverses it.
3. **Engine** (`rfone_data_store/tips/engine.py`, `_shift_active_employee_ids`): now prefers `Shift.location_id` when populated (compared directly against the Order's Location, ignoring `Employee.location_id` for that Shift entirely); falls back to the pre-existing `Employee.location_id` proxy only when a Shift's own `location_id` is `NULL`. `_resolve_role_present`'s docstring updated to state this precedence. No other function changed — `_assignment_employee_ids`, `_valid_policy_at`, the redistribution/no-eligible-behavior logic, rounding, and idempotency/supersession are all untouched.
4. **Documentation:** `01 Domains/Restaurant/Tips/Tip Allocation.md` ("Post-hoc temporal eligibility") and `Tip Policy.md` ("Policy components") updated to describe the new precedence rule; `03 Software/RF-One Data Store/DATABASE_SCHEMA.md`'s `shifts` table entry updated with the new column.
5. **Tests** (`rfone_data_store/tips_validation.py`): `make_shift` gained an optional `shift_location` parameter (`None` = unknown, matching every pre-existing call site unchanged); `make_scenario` gained an optional `at_location` parameter (defaults to the existing Winter Park fixture Location, so every pre-existing scenario is byte-for-byte unaffected). Five new checks added (see Scenario validation, below), bringing the suite from 41 to 46 checks.

### Part A

No code or schema change — a `TipPolicy`/`TipPolicyComponent` row was **not** created (no approved values exist to configure it with). `OpenQuestions.md` gained one new tracked entry pointing to this report's checklist, matching the repository's existing convention for tracked open business-policy decisions.

---

## TipPolicy status

Unchanged: **0 rows**, exactly as before this task, on both the disposable test copy and the real database (verified — see "Production validation" below). This is the correct, honest outcome per this task's own explicit instruction not to fabricate a policy.

---

## Shift/Location solution

```text
Shift.location_id (nullable FK to locations, TASK_TIPS_003)

populated (non-NULL)  → authoritative for THAT Shift; compared directly
                         against the Tip's Order Location; Employee.location_id
                         is never consulted for that Shift
NULL (unknown)         → falls back to Employee.location_id, exactly as
                         before this task (historical default — never guessed)
```

This is the smallest canonical solution consistent with the existing model: it extends the same "Location scoping" pattern TASK_TIPS_001 already applied to `EmployeeAssignment` (`location_id IS NULL` = Restaurant-wide/unknown-scoped, a specific value = scoped) to `Shift`, rather than inventing a new mechanism. `EmployeeAssignment.location_id` semantics (Restaurant-wide vs. Location-specific) are completely untouched by this task.

---

## Migration behavior

Additive, non-destructive, `batch_alter_table`-based (required for SQLite `ADD COLUMN` + `ADD CONSTRAINT` in one non-transactional-DDL step, matching the existing `09631adaed4d` and `b4f3c8a1d6e2` migrations' pattern). Verified:

- Fresh database: `create_database.py` applies all 10 migrations (including this one) cleanly; schema validation 29/29.
- Disposable copy of the real, populated `data/rfone.db`: `alembic upgrade head` succeeds; all **4,368** real `Shift` rows preserved exactly, every one now carrying `location_id = NULL` (never guessed); all **24** `EmployeeAssignment` rows and all **3,326** `PaymentTip` rows unaffected.
- Downgrade/upgrade round-trip (`alembic downgrade -1` / `upgrade head`) on a disposable copy: clean in both directions.
- Original `data/rfone.db`: confirmed byte-identical (MD5 `179c12e7442c4ffa5a8f23e30e63ac83`) before and after every step above — never written to.

---

## Scenario validation

| # | Scenario | Result |
|---|---|---|
| 1 | Employee works only Winter Park | **PASS** — covered by the large majority of pre-existing checks (all default fixture Orders are at Winter Park; unaffected). |
| 2 | Employee works only Mount Dora | **PASS** — TASK_TIPS_001's existing `cross_location` check (exclusion at Winter Park) plus this task's new `md_home_eligible_at_md` check (positive inclusion at Mount Dora, same Employee). |
| 3 | Same Employee has separate Shifts at both Locations | **PASS** — new `multi_location_wp`/`multi_location_md` checks: one Employee, two explicitly Location-tagged Shifts, correctly eligible for a Winter Park Tip during the Winter-Park-tagged Shift and a Mount Dora Tip during the Mount-Dora-tagged Shift. |
| 4 | Restaurant-wide eligible Assignment | **PASS** — unaffected; exercised by every pre-existing check (`location_id IS NULL` default) plus all new checks (the new Employee's own Assignment is Restaurant-wide). |
| 5 | Location-specific Assignment | **PASS** — unaffected pre-existing behavior (TASK_TIPS_001 §E), re-verified by the full regression run; `EmployeeAssignment.location_id` scoping logic was not touched by this task. |
| 6 | Shift Location conflicts with Employee home Location | **PASS** — new `multi_location_md`/`multi_location_md_instant_wrong_location` checks: an Employee whose home `Employee.location_id` is Winter Park is eligible for a Mount Dora Tip during a Shift explicitly tagged Mount Dora, and simultaneously **not** eligible for a Winter Park Tip at that same instant — the Shift's own evidence overrides the home-Location proxy rather than merely supplementing it. |
| 7 | Historical Shift with NULL Location | **PASS** — every pre-existing Shift fixture (`role_single`, `double_shift`, `cross_location`'s own Shift, etc.) continues to pass `location_id = NULL` and resolves exactly as before this task via the `Employee.location_id` fallback; explicitly re-asserted by a new regression check. |
| 8 | Existing Tips tests remain green | **PASS** — 46/46 (41 pre-existing + 5 new). |
| 9 | Organization tests remain green | **PASS** — 14/14, unchanged. |
| 10 | Payroll tests remain green | **PASS** — 39/39, unchanged. |
| 11 | Purchasing tests remain green | **PASS** — 24/24, unchanged. |
| 12 | Migration upgrade/downgrade works on disposable DB | **PASS** — clean round-trip, both on a fresh disposable DB and a disposable copy of the real, populated DB. |
| 13 | Real data is never modified during validation | **PASS** — MD5 checksum of `data/rfone.db` identical before and after every step in this task. |

All 13 minimum-test-list items **PASS**.

---

## Production validation

Three distinct readiness questions, kept separate as instructed:

```text
Engine readiness         → COMPLETE. The calculation engine, idempotency/supersession
                            safeguard, rounding, provenance, and now Shift-level Location
                            evidence are all implemented and tested (46/46).

Configuration readiness   → COMPLETE (architecturally). The TipPolicy/TipPolicyComponent
                            model, once populated with approved values, requires no further
                            code change to produce a real calculation. The Shift-level
                            Location evidence added by this task means a future Location
                            (e.g. Mount Dora) could be onboarded without any Tips code
                            change, as long as its Shifts carry (or are backfilled with)
                            genuine per-Shift Location evidence.

Real Rome's Flavours      → NOT READY. 0 TipPolicy rows exist. Re-running the exact same
activation readiness       readiness check this task ran against a disposable copy of the
                            real database reproduces TASK_TIPS_001's finding unchanged: all
                            3,326 real Tips remain blocked NO_VALID_POLICY. This is the
                            correct, honest, expected outcome — not a defect.
```

`validate_tips_readiness.py`, re-run against a disposable copy of the real, populated database (never the live file) after applying this task's migration:

```text
source Tips considered:   3326
allocations produced:     0
blocking issues:          3326
NO_VALID_POLICY: 3326
```

Identical to TASK_TIPS_001's finding — confirming this task introduced no behavioral change for the real, current single-Location deployment (exactly as expected: Shift-level Location evidence only changes behavior once a Shift actually carries it, and no real Shift does yet).

---

## Part A — Product Owner decision checklist

**Nothing below is invented. Every field listed is a real, already-implemented column on `TipPolicy`/`TipPolicyComponent` (`01 Domains/Restaurant/Tips/Tip Policy.md`) that currently has no approved value.** Once Pino supplies these, configuring the real `TipPolicy`/`TipPolicyComponent` rows is a data-entry step, not a development task — **with one caveat, flagged separately below, if any component uses `SERVICE_OWNER`.**

### 1. Policy scope

- **Restaurant-wide, or Winter-Park-specific?** Today there is only one real Location, so this has no immediate effect — but it determines whether a future second Location (e.g. Mount Dora) automatically inherits this policy or needs its own. *Recommendation: Restaurant-wide (`location_id = NULL`), unless Pino specifically wants a different policy per Location from day one.*

### 2. Effective date

- **`valid_from`: what date should this policy be treated as having been in force since?** This is the single highest-impact decision: only Tips whose Payment timestamp falls on/after `valid_from` (and before any `valid_to`) can ever be calculated under this policy. Every one of the 3,326 already-recorded historical Tips predating `valid_from` will remain permanently `NO_VALID_POLICY` unless Pino explicitly confirms this policy's shares were *actually* the real-world practice back to an earlier date, in which case `valid_from` can be backdated to match. **RF-One will not assume the current/future policy also describes past practice — Pino must state this explicitly.**

### 3. Policy components — for each one:

| Field | What Pino must decide | Options |
|---|---|---|
| **Recipient basis** | Who does this share go to? | `SERVICE_OWNER` (the Order's resolved service owner) or `ROLE_PRESENT_AT_PAYMENT` (whoever holds a given Restaurant Role and was clocked in at Payment time) |
| **Restaurant Role** (only if `ROLE_PRESENT_AT_PAYMENT`) | Which of Rome's Flavours' actual 7 configured Roles is eligible for this share? | `Host`, `Team Leader`, `Server`, `BOH`, `Admin`, `Manager`, `Employee` (exact real names, confirmed by direct inspection of the real database — no other role names exist) |
| **Share percentage** | Exact decimal percent of the Tip this component receives | e.g. `80.0000` — components across one policy must not exceed 100% |
| **Split method** | How is this share divided among multiple eligible people? | Only `EQUAL_ELIGIBLE_HEADCOUNT` is implemented today — confirm this is acceptable, or state a different method Pino wants (would require new engineering work, out of this task's scope) |
| **No-eligible-recipient behavior** | What happens if nobody qualifies for this share at the relevant moment? | `RETURN_TO_SERVICE_OWNER`, `REDISTRIBUTE_TO_ELIGIBLE_COMPONENTS`, or `LEAVE_UNALLOCATED` |

A Tip Policy needs at least one component; a common shape (illustrative only, per `Tip Policy.md`'s own explicit caution — **not a suggestion of Rome's Flavours' actual numbers**) is one `SERVICE_OWNER` component plus one or more `ROLE_PRESENT_AT_PAYMENT` components for support roles. Pino must state the real structure.

### 4. Caveat: `SERVICE_OWNER` requires a real service-attribution resolver

If **any** component uses `SERVICE_OWNER`, one additional prerequisite exists beyond entering policy values: `calculate_tips.py` today always uses `NullServiceAttributionResolver` (always reports UNRESOLVED — the deliberate, honest placeholder, per `Tip Allocation.md`'s "service-attribution boundary"). A real resolver (which field(s) determine "who served this table" for Rome's Flavours — `Order.employee`? something else?) has never been implemented or approved, and this task does not implement one (out of scope — Part A concerns Tip Policy values, not the resolver). **If Pino's policy uses only `ROLE_PRESENT_AT_PAYMENT` components, this caveat does not apply and entering the checklist values above is sufficient.** If any component is `SERVICE_OWNER`, a small, separate, already-scoped follow-up task is needed to wire a real resolver before that component can ever allocate anything.

---

## Tests

All run against fresh or disposable databases (never the live `data/rfone.db`), scratch-directory only:

| Command | Result |
|---|---|
| `create_database.py` (fresh DB, 10 migrations incl. this task's new one) | **SUCCESS** — 74 tables, schema validation 29/29 |
| `test_tips_engine.py` | **SUCCESS** — 46/46 (41 pre-existing + 5 new) |
| `test_organization_validation.py` | **SUCCESS** — 14/14, unchanged |
| `test_payroll_engine.py` | **SUCCESS** — 39/39, unchanged |
| `test_restaurant_profile_bootstrap.py` | **SUCCESS** — 14/14, unchanged |
| `test_purchasing_engine.py` | **SUCCESS** — 24/24, unchanged |
| `alembic downgrade -1` / `upgrade head` (disposable DB) | **SUCCESS** — clean round-trip |
| `alembic upgrade head` on a disposable copy of the real, populated `data/rfone.db` | **SUCCESS** — 4,368 real Shift rows preserved, all `location_id = NULL`; 24 EmployeeAssignments and 3,326 PaymentTips unaffected |
| `validate_tips_readiness.py` on that same disposable copy | Unchanged from TASK_TIPS_001: 3,326 real Tips, all `NO_VALID_POLICY` |
| MD5 of `data/rfone.db` before/after all of the above | **Identical** (`179c12e7442c4ffa5a8f23e30e63ac83`) — never written to |

---

## Exact files changed

**Modified:**
- `03 Software/RF-One Data Store/rfone_data_store/models.py` (only the `Shift` class — new `location_id` column)
- `03 Software/RF-One Data Store/rfone_data_store/tips/engine.py`
- `03 Software/RF-One Data Store/rfone_data_store/tips_validation.py`
- `03 Software/RF-One Data Store/DATABASE_SCHEMA.md`
- `01 Domains/Restaurant/Tips/Tip Allocation.md`
- `01 Domains/Restaurant/Tips/Tip Policy.md`
- `OpenQuestions.md` (new tracked entry pointing to this report's checklist)

**Created:**
- `03 Software/RF-One Data Store/migrations/versions/d7e21f4a9c3b_add_shift_location.py`
- `07 Tasks/Reports/TASK_TIPS_003_REPORT.md` (this report)

No file outside this list was touched by this task. `01 Domains/Restaurant/Tips/README.md` was already modified earlier in this session by a separate, unrelated task (TASK_SERVER_PERFORMANCE_001, cross-referencing the new Server Performance module) — not re-touched here. No UI, Mercury/payment execution, Payroll execution logic, Sales, or Organization redesign code was created or modified.

---

## Product Owner decisions required

**Yes — see "Part A — Product Owner decision checklist" above.** This is the one and only open item: the real Rome's Flavours Tip Policy structure (scope, effective date, components, shares, split method, no-eligible-recipient behavior), and, if any component is `SERVICE_OWNER`, confirmation that a follow-up resolver task should be scoped.

No decision is required for Part B — the Shift-Location solution was fully specified by this task's own instructions and required no business-policy input.

---

## Remaining future enhancements

- Wiring a real service-attribution resolver for `SERVICE_OWNER` components (see Part A caveat) — separate, small, already-bounded follow-up.
- A genuine per-Shift Location ingestion source (Clover or otherwise) to actually populate `Shift.location_id` going forward — this task only adds the column and the engine's ability to consume it; no ingestion pipeline writes to it yet, since Rome's Flavours has only one real Location today and no genuine multi-Location Shift data exists to ingest.
- Everything already listed as non-blocking in TASK_TIPS_001 §O that this task did not touch (optional `--location-id` CLI filter, additional allocation methods, wiring an actual Payroll consumer of `TipAllocation`, the dangling `TASK_TIPS_002_REPORT.md` reference).

---

## Git status

No commit was created and nothing was pushed during this task. All work is in the working tree only. Pre-existing uncommitted changes present at task start (across Purchasing, Organization, InvoiceIntake, Core documentation, and this session's own earlier Payroll Payment-Execution-Provider and Server Performance work) were left exactly as found — this task only added the two new files and made the seven scoped edits listed in "Exact files changed," all Tips/Shift-related.

---

## Final readiness statement

`TIPS DEPLOYMENT STATUS: PARTIAL — WAITING FOR PRODUCT OWNER POLICY INPUT`

Minimum values Pino must provide (see "Part A — Product Owner decision checklist" for full detail):

1. Policy scope — Restaurant-wide or Winter-Park-specific.
2. Effective date (`valid_from`) — including whether it should be backdated to cover any of the 3,326 already-recorded historical Tips.
3. For each policy component: recipient basis (`SERVICE_OWNER` / `ROLE_PRESENT_AT_PAYMENT`), the specific Restaurant Role if `ROLE_PRESENT_AT_PAYMENT` (`Host`/`Team Leader`/`Server`/`BOH`/`Admin`/`Manager`/`Employee`), exact share percentage, split method, and no-eligible-recipient behavior.
4. If any component is `SERVICE_OWNER`: confirmation to scope a follow-up task for a real service-attribution resolver.
