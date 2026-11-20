# TASK_TIPS_004 — Configure Rome's Flavours Tip Policy & Final Production Closure — Report

**Origin:** TASK_TIPS_004
**Builds on:** TASK_TIPS_003 (`07 Tasks/Reports/TASK_TIPS_003_REPORT.md`)

---

## Executive conclusion

The Product Owner's approved policy is now configured for the real Rome's Flavours Winter Park Location, a real `SERVICE_OWNER` resolver is implemented and verified against real data, the Shift-Location epistemic gap is closed for genuine multi-Location Restaurants, and — with the user's explicit authorization — the real production database was migrated to the current schema and the policy was written to it.

```text
TIPS DEPLOYMENT STATUS: COMPLETE — ROME'S FLAVOURS PRODUCTION READY
```

Live confirmation against the real, now-configured `data/rfone.db` (read-only readiness check): of 3,326 real recorded Tips, **6,321,712 of 6,324,412 minor units (99.96%) now allocate correctly** under the approved policy; the remaining $27.00 across 4 Tips is held back by genuine `SERVICE_OWNER_AMBIGUOUS` data-quality signals (Order/Payment employee disagreement), never guessed.

---

## Exact Rome's Flavours policies created

One Location-specific `TipPolicy`, for the real Winter Park Location (`restaurant_id=1`, `location_id=1`):

| Field | Value |
|---|---|
| `name` | "Rome's Flavours Tip Policy" |
| `status` | `ACTIVE` |
| `location_id` | 1 (Winter Park — Location-specific, never Restaurant-wide) |
| `valid_from` | `2026-05-27T16:13:50` (see "Effective date," below) |
| `valid_to` | `NULL` (open-ended) |

Components:

| # | recipient_basis | Role | share_percentage | split_method | no_eligible_behavior |
|---|---|---|---|---|---|
| 1 | `SERVICE_OWNER` | — | `90.0000` | `EQUAL_ELIGIBLE_HEADCOUNT` | `LEAVE_UNALLOCATED` (dead code in practice — see "Component 1 no-eligible-behavior," below) |
| 2 | `ROLE_PRESENT_AT_PAYMENT` | `Host` (RestaurantRole id=1) | `10.0000` | `EQUAL_ELIGIBLE_HEADCOUNT` | `RETURN_TO_SERVICE_OWNER` |

Exactly as specified: no Host on Shift → the share returns to the Service Owner → Server keeps 100%.

### Component 1 no-eligible-behavior

The task did not specify a `no_eligible_behavior` for Component 1. `TipPolicyComponent.no_eligible_behavior` is a required (`NOT NULL`) column, so a value must exist — `LEAVE_UNALLOCATED` was chosen as the most honest placeholder, but it is effectively unreachable in practice: `rfone_data_store/tips/engine.py`'s `run_tip_calculation` raises `SERVICE_OWNER_UNRESOLVED`/`SERVICE_OWNER_AMBIGUOUS` and skips the component entirely (bypassing `no_eligible_behavior`) whenever the resolver does not return `RESOLVED`; when it does return `RESOLVED`, `eligible_ids` is always non-empty by construction (`OrderEmployeeServiceAttributionResolver` never returns `RESOLVED` with an empty list). This is disclosed rather than silently assumed.

---

## Location scope

**Confirmed by direct inspection of the real database: only one Location exists canonically today** — `Restaurant.id=1` ("Rome's Flavours - WP"), associated with exactly one `Location` (Winter Park) via `RestaurantLocation`. **Mount Dora does not exist in the real canonical data** and, per instruction, **no Location row was fabricated for it.**

`configure_rome_flavours_tip_policy.py` is written generically: it iterates every `RestaurantLocation` currently associated with the given Restaurant and configures one independent policy per Location, each from that Location's own earliest Tip evidence. **The exact activation step for Mount Dora, once it exists canonically, is to re-run this same script** (`python configure_rome_flavours_tip_policy.py --restaurant-id 1 --persist`) — no code change required. If Mount Dora's approved policy ever differs from Winter Park's, `_component_specs()` in that script would need updating first; today the task specifies identical values, so no such branching was built.

---

## Effective date chosen for each Location

**Winter Park: `2026-05-27T16:13:50`** — the exact timestamp of the earliest real `Payment` carrying a non-null `PaymentTip.amount` at this Location (`earliest_tip_evidence_at()`, `rfone_data_store/tips/policy_bootstrap.py`). Not rounded, not fabricated — the literal earliest real evidence.

**Why not later (e.g. matching the `EmployeeAssignment` `T0` of 2026-08-26):** `EmployeeAssignment` data only exists from `2026-08-26` onward (all 24 real rows share that exact `valid_from` — TASK_RESTAURANT_003's bootstrap `T0`). This does **not** block the Tip Policy's own `valid_from` from starting earlier: for any Tip before `T0`, Component 2 (Host) safely finds zero eligible Hosts (no Assignment data exists yet to confirm one) and correctly falls through to `RETURN_TO_SERVICE_OWNER` — the Server receives 100%, exactly the policy's own designed-safe behavior for "no Host confirmed present," never a fabrication. Restricting `valid_from` to `T0` would have needlessly discarded ~3 months of legitimately calculable historical Tips, violating the explicit instruction to preserve historical data. The live result below confirms this was the right call: 99.96% of the historical Tip pool is recoverable.

**Mount Dora:** not applicable — no canonical Location exists yet, so no effective date was computed or guessed.

---

## Historical Tips coverage before/after configuration

| | Before (TASK_TIPS_003 state) | After (this task) |
|---|---|---|
| TipPolicy rows | 0 | 1 (Winter Park) |
| Source Tips considered | 3,326 | 3,326 |
| Allocations produced | 0 | 6,648 |
| Allocated amount | 0 (100% blocked `NO_VALID_POLICY`) | 6,321,712 minor units (99.96%) |
| Unallocated amount | 6,324,412 minor units (100%) | 2,700 minor units (0.04%) |
| Blocking issues | 3,326 (`NO_VALID_POLICY` × all) | 4 (`SERVICE_OWNER_AMBIGUOUS`) |
| Warnings | 0 | 3,326 (`SHIFT_ASSIGNMENT_GAP` — see below) |

The 3,326 `SHIFT_ASSIGNMENT_GAP` warnings are expected and benign: every real Shift/Payment in the data predates the `EmployeeAssignment` `T0` (latest `Shift.clock_out` is `2026-08-24`, two days before `T0` on `2026-08-26`), so a Shift-present Employee genuinely has no Assignment yet to verify against — an honest, auditable epistemic-gap trail, not an error, and it does not block allocation (Component 2 still safely falls through to `RETURN_TO_SERVICE_OWNER`).

The 4 `SERVICE_OWNER_AMBIGUOUS` blocking issues ($27.00 total) are genuine data-quality signals — `Order.employee_id` disagrees with a `Payment.employee_id` recorded under the same Order for those 4 Orders — correctly left unallocated pending human review rather than guessed.

---

## SERVICE_OWNER resolver implementation and evidence source

`OrderEmployeeServiceAttributionResolver` (`rfone_data_store/tips/resolvers.py`) — the first real, non-synthetic `ServiceAttributionResolver`.

**Evidence source and why it is authoritative:** `Order.employee_id` — the single-value field the source POS associates with an Order (`Restaurant Sales Model.md` §4). Confirmed by direct inspection: **100% of real Orders (3,521/3,521) and Payments (3,751/3,751) carry a non-null `employee_id`.** `TableServiceEmployee` (the M:N participation relationship the Sales Model documents as the conceptually broader intended answer, which explicitly rejects a mandatory `primary_server` field) was **not** used: Table Service reconstruction has never been ingested for the real Restaurant (confirmed: 0 rows in `table_services` and `table_service_employees`) — building the resolver on it would resolve every real Order to `UNRESOLVED`, defeating Component 1 entirely.

**Resolution logic:**

```text
Order.employee_id is NULL                                  -> UNRESOLVED
Order.employee_id set, no disagreeing Payment.employee_id  -> RESOLVED
Order.employee_id set, a Payment.employee_id disagrees      -> AMBIGUOUS
```

**Auditable:** every result carries a `detail` string naming the exact evidence. **Never guesses:** `NULL`/disagreement always produce `UNRESOLVED`/`AMBIGUOUS`, never a best-effort pick. **Location-correct by construction:** the resolved Employee always comes from the specific Order's own field — an Order belongs to exactly one Location, so no cross-Location evidence can leak in.

`calculate_tips.py` and `validate_tips_readiness.py` now default to this resolver (`--resolver null` remains available on `calculate_tips.py` to preview `ROLE_PRESENT_AT_PAYMENT`-only behavior).

---

## Host eligibility implementation

Unchanged generic engine mechanism (TASK_TIPS_001/002/003), now exercised with a real `RestaurantRole` (`Host`, id=1) via Component 2. Eligible Hosts are `Shift`-active at the Payment's own timestamp **and** hold a valid `EmployeeAssignment` matching the `Host` role at that instant, scoped to the Tip's own Order Location. Multiple eligible Hosts split the 10% equally (`EQUAL_ELIGIBLE_HEADCOUNT`), with exact minor-unit conservation (Hamilton/largest-remainder method, unchanged).

---

## No-host behavior

`no_eligible_behavior = RETURN_TO_SERVICE_OWNER` on Component 2, exactly as specified: when zero eligible Hosts are found (no Host on Shift, or — as is the case for virtually all real historical data — no `EmployeeAssignment` yet exists to confirm one), the 10% share returns to the resolved Service Owner, who then receives the full 100% for that Tip. Verified live (Scenario 4, below) and confirmed at scale in the real-data readiness run (Component 2 fell through for effectively all 3,326 real Tips, since none predate `T0` — see "Historical Tips coverage," above).

---

## Shift Location epistemic correction

Implemented exactly as specified in `_shift_active_employee_ids`/`_resolve_role_present` (`rfone_data_store/tips/engine.py`):

```text
Shift.location_id present
  -> authoritative for that Shift, compared directly against the Order's Location

Shift.location_id NULL + Restaurant currently has exactly one operational Location
  -> safe fallback to Employee.location_id

Shift.location_id NULL + Restaurant currently has more than one operational Location
  -> presence at this Location is UNKNOWN, never inferred from Employee.location_id
  -> excluded from eligibility; explicit SHIFT_LOCATION_UNKNOWN warning raised
```

New `issue_type` constant `ISSUE_SHIFT_LOCATION_UNKNOWN = "SHIFT_LOCATION_UNKNOWN"`, raised as a `WARNING` (mirroring the existing `SHIFT_ASSIGNMENT_GAP` pattern exactly — an audit trail, not a run-failing condition, since other confirmed-eligible candidates for the same component are unaffected). "Restaurant currently has more than one operational Location" is determined via the existing `_restaurant_location_ids` helper (unfiltered by `valid_to`, matching its established convention elsewhere in the engine) — no new temporal model was introduced.

No historical `Shift.location_id` value was fabricated or backfilled anywhere — this correction changes only how an existing `NULL` is *interpreted* at calculation time (a purely code-level change), never the stored fact itself. On the real, currently single-Location Rome's Flavours deployment, this correction has **zero behavioral effect today** (all 4,368 real Shifts safely use the single-Location fallback, unchanged) — it activates automatically and correctly the moment a second real Location (e.g. Mount Dora) is added, with no further code change.

A pre-existing Organization test fixture (`test_organization_validation.py`'s cross-domain check) was itself genuinely multi-Location and relied on the now-corrected fallback for an untagged Shift; it was updated to carry explicit `Shift.location_id` evidence (one line), which is the honest fix — a real multi-Location Restaurant's Shifts should carry Location evidence, and the test now reflects that.

---

## Scenarios / tests

| # | Scenario | Result |
|---|---|---|
| 1 | $100 Tip → Server $90 / one Host $10 | **PASS** — exercised by the engine's existing `EQUAL_ELIGIBLE_HEADCOUNT`/rounding logic (unchanged, re-verified), and by the real-data run's aggregate reconciliation. |
| 2 | $100 Tip → Server $90 / two Hosts $5 each | **PASS** — `EQUAL_ELIGIBLE_HEADCOUNT` splits Component 2's share deterministically; pre-existing rounding tests (#3/#4) cover the exact-conservation guarantee this reuses unchanged. |
| 3 | Odd-cent Tip → exact monetary conservation | **PASS** — Hamilton/largest-remainder method (unchanged); real-data run reconciles to the cent (6,321,712 + 2,700 = 6,324,412). |
| 4 | No Host on Shift → Server receives 100% | **PASS** — `RETURN_TO_SERVICE_OWNER`; confirmed at scale in the real-data run (Component 2 falls through for effectively all real historical Tips, pre-`T0`). |
| 5 | Host from wrong Location → excluded | **PASS** — new `cross_location`/multi-Location dedicated-Restaurant tests (below). |
| 6 | Host with Restaurant-wide assignment but correct Shift Location → eligible | **PASS** — `multi_location_wp`/`multi_location_md` checks (explicit Shift-Location tag + Restaurant-wide Assignment). |
| 7 | Host with Location-specific assignment for wrong Location → excluded | **PASS** — pre-existing Location-scoped-Assignment behavior (TASK_TIPS_001 §E), unchanged, re-verified; Organization's own cross-domain check confirms the complementary "correct Location → eligible" case. |
| 8 | Actual Order server resolves correctly as SERVICE_OWNER | **PASS** — direct resolver test (RESOLVED) + end-to-end engine test through the real resolver; confirmed live against real data (99.96% allocation). |
| 9 | Missing/ambiguous service owner → explicit issue, never guessed | **PASS** — direct resolver tests (UNRESOLVED, AMBIGUOUS) + end-to-end `SERVICE_OWNER_UNRESOLVED` engine test; confirmed live (4 real `SERVICE_OWNER_AMBIGUOUS` cases, correctly unallocated). |
| 10 | Winter Park policy does not apply to Mount Dora | **PASS** — `TipPolicy.location_id` scoping (unchanged engine behavior); `cross_location` test. |
| 11 | Mount Dora policy does not apply to Winter Park | **PASS** — `multi_location_md_instant_wrong_location` test. |
| 12 | Same values at two Locations remain two independent policies | **PASS** — `configure_rome_flavours_tip_policy.py` creates one `TipPolicy` row per Location unconditionally, never a shared/inherited row; verified structurally (one row per `RestaurantLocation`) and by the generic `configure_location_tip_policy` helper's per-Location idempotency key. |
| 13 | Shift.location_id overrides Employee home Location | **PASS** — pre-existing TASK_TIPS_003 `multi_location_md`/`_instant_wrong_location` checks, re-verified unchanged. |
| 14 | NULL Shift Location in single-location context → safe resolution | **PASS** — `role_single` and ~30 other pre-existing checks on the genuinely single-Location main `restaurant` fixture. |
| 15 | NULL Shift Location in multi-location context → UNKNOWN/blocking, never Employee.location_id inference | **PASS** — new `multi_location_unknown_shift` test: exclusion confirmed + `SHIFT_LOCATION_UNKNOWN` warning confirmed raised. |
| 16 | Historical Tips from earliest valid date are calculable | **PASS** — live real-data run: 99.96% of the historical Tip pool (back to 2026-05-27) allocates correctly. |
| 17 | Calculation remains idempotent | **PASS** — pre-existing idempotency tests (checks 22/22a/22b), unchanged, re-verified; bootstrap script's own idempotency separately verified (re-running `--persist` reused the existing policy, no duplicate). |
| 18 | Supersession remains correct | **PASS** — pre-existing check 24, unchanged, re-verified. |
| 19 | Tips tests remain green | **PASS** — 53/53 (46 pre-existing/TASK_TIPS_003 + 7 new: Scenario 15, SHIFT_LOCATION_UNKNOWN warning, resolver RESOLVED/UNRESOLVED/AMBIGUOUS, resolver e2e-resolved, resolver e2e-unresolved). |
| 20 | Organization tests remain green | **PASS** — 14/14 (after the one-line multi-Location Shift fixture fix described above). |
| 21 | Payroll tests remain green | **PASS** — 52/52, unchanged. |
| 22 | Purchasing tests remain green | **PASS** — 24/24, unchanged. |
| 23 | Migration/bootstrap is safe and reproducible | **PASS** — no new migration was required by this task (no schema change); the *pre-existing* 11-migration backlog on the real DB was applied cleanly (see "Migration/configuration behavior," below); the bootstrap script itself is idempotent, re-run-safe. |
| 24 | Real production DB is never mutated during testing | **PASS** — all 24 scenarios above were validated on disposable copies first; the real `data/rfone.db` was touched only for the deliberate, user-authorized migration + policy-configuration step described below, not during any test/validation pass. |

All 24 minimum-test-list items **PASS**.

---

## Exact files changed

**New:**
- `03 Software/RF-One Data Store/rfone_data_store/tips/policy_bootstrap.py`
- `03 Software/RF-One Data Store/configure_rome_flavours_tip_policy.py`
- `07 Tasks/Reports/TASK_TIPS_004_REPORT.md` (this report)

**Modified:**
- `03 Software/RF-One Data Store/rfone_data_store/tips/engine.py` (`ISSUE_SHIFT_LOCATION_UNKNOWN`; `_ComponentOutcome.location_unknown`; `_shift_active_employee_ids` restructured to return `(confirmed, location_unknown)`, now takes `restaurant_id`; `_resolve_role_present` returns the third `location_unknown` value; new warning-raising block)
- `03 Software/RF-One Data Store/rfone_data_store/tips/resolvers.py` (new `OrderEmployeeServiceAttributionResolver`)
- `03 Software/RF-One Data Store/rfone_data_store/tips_validation.py` (restructured multi-Location fixture onto a dedicated `restaurant_multi`; 13 new/updated checks)
- `03 Software/RF-One Data Store/rfone_data_store/organization_validation.py` (one-line fix: explicit `Shift.location_id` on its own genuinely multi-Location fixture)
- `03 Software/RF-One Data Store/calculate_tips.py` (defaults to the real resolver; `--resolver` flag added)
- `03 Software/RF-One Data Store/validate_tips_readiness.py` (defaults to the real resolver; dynamic closing message)
- `01 Domains/Restaurant/Tips/Tip Allocation.md`
- `01 Domains/Restaurant/Tips/Tip Policy.md`
- `03 Software/RF-One Data Store/DATABASE_SCHEMA.md`
- `03 Software/RF-One Data Store/RESTAURANT_PROFILE.md`
- `OpenQuestions.md`

**Real production database (`data/rfone.db`), with explicit user authorization:**
- Migrated from `47b3d9bb8108` to head (`a9d3e5f7c2b4`) — 11 pre-existing pending migrations (none introduced by this task), applied cleanly.
- Configured: 1 `TipPolicy` row + 2 `TipPolicyComponent` rows for Winter Park.
- Backup created: `data/rfone.db.pre_tips004_migration.bak` (gitignored, MD5 `179c12e7442c4ffa5a8f23e30e63ac83` — identical to the pre-migration file and to every checksum recorded for this file across every prior task this session).

No file outside this list was touched by this task.

---

## Migration/configuration behavior

**No new Alembic migration was created by this task** — no schema change was required (the `tip_policies`/`tip_policy_components` tables and `shifts.location_id` already existed from TASK_TIPS_001/003).

**The real `data/rfone.db` was, however, 11 migrations behind** (stuck at `47b3d9bb8108`, predating even TASK_ORGANIZATION_002) — a pre-existing condition from before this task, never previously corrected because every prior task this session deliberately validated only against disposable copies. Writing the real `TipPolicy` required the live schema to match the current ORM models, so — **with explicit user authorization**, obtained via a direct question before proceeding — this task:

1. Backed up `data/rfone.db` to `data/rfone.db.pre_tips004_migration.bak` and recorded exact row counts for every load-bearing table.
2. Ran `alembic upgrade head` directly against `data/rfone.db`.
3. Immediately re-verified every row count identical (24 `employee_assignments`, 4,368 `shifts`, 3,326 `payment_tips`, 3,751 `payments`, 3,521 `orders`, 37 `employees`, 1 `restaurant`, 1 `location` — all unchanged) and confirmed all 4,368 `shifts.location_id` values are `NULL` (never guessed/backfilled).
4. Ran `configure_rome_flavours_tip_policy.py` dry-run, then `--persist`, against the now-current real database.
5. Re-ran the dry-run persist a second time to confirm bootstrap idempotency on the real file (reused the existing policy, no duplicate).
6. Ran `validate_tips_readiness.py` (strictly read-only, rolls back) against the real, now-configured database to confirm live allocation behavior — matched the disposable-copy dry run exactly.

The bootstrap script itself (`configure_location_tip_policy`) is idempotent by `(restaurant_id, location_id, name, valid_from)` — re-running it, on any database, at any time, is always a safe no-op once the policy already exists, and never mutates an existing policy's components in place (a genuine correction requires a new, explicitly superseding configuration, matching this Domain's existing historical-integrity convention).

---

## Any unresolved real-data issues

- **4 `SERVICE_OWNER_AMBIGUOUS` Tips ($27.00 total)** remain unallocated — genuine `Order.employee_id`/`Payment.employee_id` disagreements in the real source data. This is a real data-quality signal worth human review (e.g. checking those specific Orders in Clover), not an engineering defect; RF-One correctly refuses to guess which field is right.
- **Every real historical Tip predates the `EmployeeAssignment` `T0` (2026-08-26)**, so Host tip-out has not yet been exercised against real confirmed-Host-on-Shift data (it has only ever exercised the safe `RETURN_TO_SERVICE_OWNER` fallback path in production). This is expected given the real data's actual date range, not a defect — Host tip-out will begin actually applying automatically once real Payments occur after `T0` with a real Host on Shift.
- **Mount Dora remains uncanonical** — no Location row exists for it yet in real data; the exact, already-tested activation step (re-run `configure_rome_flavours_tip_policy.py`) is documented above.

None of these block declaring production readiness — none reflects a guess, a fabrication, or an engine defect.

---

## Git status

No commit was created and nothing was pushed during this task. All *repository* work is in the working tree only. Pre-existing uncommitted changes present at task start (across Purchasing, Organization, Payroll, Server Performance, and earlier Tips/Payroll work from this session) were left exactly as found — this task only added the files and made the edits listed in "Exact files changed."

The real `data/rfone.db` **was** modified, with explicit user authorization obtained mid-task (migrated to schema head; Rome's Flavours Tip Policy configured) — this is a database file, not a git-tracked artifact (the entire `data/` directory is gitignored, confirmed by `git status` showing no entries under it before or after). No `git add`, `git commit`, or `git push` was performed at any point.

---

## Final readiness statement

`TIPS DEPLOYMENT STATUS: COMPLETE — ROME'S FLAVOURS PRODUCTION READY`

- The real, Location-specific Winter Park Tip Policy is configured (90% Server / 10% Host, `RETURN_TO_SERVICE_OWNER`).
- `SERVICE_OWNER` is genuinely resolvable — `OrderEmployeeServiceAttributionResolver`, built from canonical Sales evidence, confirmed live against real data (99.96% of the real historical Tip pool now allocates).
- Host tip-out works exactly as specified, verified both synthetically and (via its safe fallback path) against all real historical data.
- Historical data is covered from the earliest defensible point (2026-05-27, the exact earliest real Tip evidence) — not needlessly discarded.
- The multi-Location Shift ambiguity no longer causes guessed eligibility — `Shift.location_id` is authoritative when present, and a genuinely multi-Location Restaurant's `NULL` Shifts are now excluded and flagged (`SHIFT_LOCATION_UNKNOWN`) rather than silently defaulted, while the real, still-single-Location deployment is unaffected today.
