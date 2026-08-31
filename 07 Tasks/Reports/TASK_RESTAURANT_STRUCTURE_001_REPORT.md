# TASK_RESTAURANT_STRUCTURE_001 — Report

**Task:** Close Service Owner Evidence (FAILED Payments) + Rome's Flavours Multi-Location / Multi-Brand Boundary
**Status:** See final status line.

---

## A. Note on starting state

At the start of this task, the working tree already contained most of the required implementation and documentation changes, uncommitted (verified via `git diff` against `HEAD`, commit `209747c`) — the resolver fix, the CRITICAL A-H regression tests, the Corporate/Brand/Location reconciliation in `Restaurant Semantic Model.md` § 3, `RESTAURANT_PROFILE.md` § 0, and `Roadmap.md` § 5 were all present and already correctly attributed to `TASK_RESTAURANT_STRUCTURE_001` in their own text. This report does not claim to have originated that work from scratch; it verifies it against the task specification below, runs the full disposable-DB test matrix, closes the two items that were still missing (a `PROJECT_STATE.md` summary bullet, and the Future Intelligence Boundary documentation, § 3 of the spec), and records the result. No content already present was rewritten or reinterpreted.

---

## B. Resolver change — FAILED Payments excluded from SERVICE_OWNER evidence

**File:** `rfone_data_store/tips/resolvers.py`, `OrderEmployeeServiceAttributionResolver.resolve()`.

The query that collects corroborating/contradicting `Payment.employee_id` values now filters `Payment.result == "SUCCESS"` (the canonical economically-valid value, matching `tips/engine.py`'s `ISSUE_FAILED_PAYMENT_WITH_TIP` usage) in addition to `employee_id IS NOT NULL`. A `FAIL` Payment (the canonical failure value used throughout ingestion/reconciliation — `"FAIL"`, not `"FAILED"`) or a Payment with an unrecognized/NULL `result` is excluded from the evidence set entirely:

- It can never confirm the Service Owner.
- It can never create `AMBIGUOUS`.
- It can never override an otherwise-`RESOLVED` Order.
- It can never turn a `RESOLVED` Order into `UNRESOLVED`.

`Order.employee_id` remains the primary evidence; only `SUCCESS` Payments corroborate or contradict it. The docstring and `Tip Allocation.md` were updated to state this invariant explicitly, citing this task.

---

## C. Tests

### C.1 Direct resolver regression (`sales_validation.py`, scenarios A-H)

All eight required scenarios are implemented as direct `resolver.resolve()` calls against synthetic Sales facts (not the end-to-end engine):

| # | Scenario | Expected | Result |
|---|---|---|---|
| A | Order=A + SUCCESS Payment=A | RESOLVED A | PASS |
| B | Order=A + FAILED Payment=B | RESOLVED A | PASS |
| C | Order=A + FAILED Payment=A | RESOLVED A (0 agreeing) | PASS |
| D | Order=A + SUCCESS Payment=B | AMBIGUOUS | PASS |
| E | Order=A + FAILED Payment=B + SUCCESS Payment=A | RESOLVED A | PASS |
| F | Multiple SUCCESS Payments all=A | RESOLVED A | PASS |
| G | Conflicting SUCCESS Payments | AMBIGUOUS | PASS |
| H | No Order.employee_id + only FAILED Payment=A | UNRESOLVED | PASS |

### C.2 End-to-end engine regression (`tips_validation.py`)

One additional scenario runs the real `OrderEmployeeServiceAttributionResolver` (not the synthetic Static/Null resolvers used elsewhere in that file) through the full `run_tip_calculation` engine: Order.employee_id=ServiceOwner + a disagreeing FAILED Payment → asserts `RESOLVED`, not `AMBIGUOUS`.

### C.3 Full suite run (disposable DB only)

A fresh SQLite database was created in the session scratchpad directory (never `data/rfone.db`), migrated to head via Alembic (14 migrations, 75 tables), and every suite run against it:

| Suite | Result |
|---|---|
| Schema validation (`create_database.py`) | **29/29 PASS** |
| Sales validation (`sales_validation.py`) | **27/27 PASS** (24 from TASK_REPOSITORY_STABILIZATION_001 + 3 additional CRITICAL checks: C's "0 agreeing" detail assertion, F, G counted individually) |
| Tips engine (`tips_validation.py`) | **54/54 PASS** (53 + 1 new FAILED-disagree end-to-end check) |
| Organization validation | **14/14 PASS** |
| Payroll engine | **52/52 PASS** |
| Restaurant Profile bootstrap | **14/14 PASS** |
| Purchasing engine (own disposable `data/purchasing_test.db`, its established convention) | **24/24 PASS** |
| **Total** | **214/214 PASS, 0 failures** |

`data/rfone.db` MD5 checksum verified unchanged before and after: `c0b08fb19bfffdf816fef68baacfd80a` (matches the checksum recorded at TASK_TIPS_004 / TASK_REPOSITORY_STABILIZATION_001).

---

## D. Corporate / Brand / Location — mapping to current entities

No new entity or migration was needed. The existing schema already expresses the approved hierarchy:

```text
Core concept    Runtime entity                              Cardinality today
------------    -------------------------------------------  ------------------
Corporate       (none — implicit; exactly one Corporate has   1 (implicit)
                 ever existed, so leaving it unmodeled
                 creates no ambiguity)
Brand           `restaurants` row ("Rome's Flavours")          1 (Rome's Flavours)
Location        `locations` row, via `restaurant_locations`    1 today (Winter Park);
                 ("Winter Park", future "Mount Dora")           Mount Dora not yet onboarded
```

`RestaurantLocation` (built by TASK_ORGANIZATION_002 specifically to let one `Restaurant` hold many `Location`s over time) already is the Brand↔Location association. Every configuration table that matters for Tips/Organization (`TipPolicy`, `EmployeeAssignment`, `OperationalArea`, `RestaurantRole`) is scoped by `restaurant_id` — i.e., by Brand, not by Corporate or by Location alone — which is exactly the isolation a future second Brand would need.

**Genuinely misleading fact found, not corrected:** the real production `restaurants.name` value is `"Rome's Flavours - WP"`, baking the Winter Park Location suffix into the Brand-level name field. This is flagged (not fixed — no production write was made) as a recommended follow-up, ideally executed as part of Mount Dora onboarding with explicit Product Owner authorization: rename to `"Rome's Flavours"`.

---

## E. Whether schema changes were needed

**No.** The existing `restaurants` / `locations` / `restaurant_locations` structure already supports Corporate-implicit / Brand (`Restaurant`) / Location (`Location`) without any new table, column, or migration. No schema change was made or is recommended now. A runtime `Corporate`/`Brand` table above `Restaurant` remains a deliberately deferred, evidence-triggered future item (§ G below) — not built, because only one Brand has ever existed and "reuse must be earned" (the same principle already applied elsewhere in this repository, e.g. Commercial Catalog extraction).

---

## F. Mount Dora onboarding decision

**Resolved:** Mount Dora is a second `Location` of the *same* Rome's Flavours `Restaurant`(=Brand) row Winter Park already belongs to — never a separate `Restaurant`/Brand. This closes what was previously an open Product Owner confirmation (`TASK_REPOSITORY_STABILIZATION_001_REPORT.md` § N item 3).

`Roadmap.md` § 5's six-step checklist (now seven, with the `Restaurant.name` correction added as step 7, marked recommended/optional) records the onboarding path once real production data exists:

1. Create/ingest the canonical Mount Dora `Location`.
2. Attach it to the *same* `Restaurant` row via a second `RestaurantLocation` row.
3. Confirm Shift Location ingestion populates `Shift.location_id` for Mount Dora shifts.
4. Configure an independent Mount-Dora-specific `TipPolicy`.
5. Even if WP and MD policy values are identical, store them as separate `TipPolicy` rows scoped to their own `location_id` — never an implicit Restaurant-wide policy.
6. Validate Sales/Organization/Tips/Payroll/Performance end-to-end against real Mount Dora data.
7. (Recommended, not required) correct `restaurants.name` from `"Rome's Flavours - WP"` to `"Rome's Flavours"`.

No Mount Dora production row was fabricated by this task.

---

## G. Future multi-Brand compatibility

Documented, not implemented, in `Roadmap.md` § "Future multi-Brand compatibility": a future genuinely different Brand under the same Corporate owner becomes a second, fully independent `restaurants` row — no schema change required, since every relevant configuration table is already scoped by `restaurant_id`. What is not built: a runtime `Corporate`/`Brand` table above `Restaurant`, and any cross-Brand shared-resource model. Trigger to revisit: a second real Brand confirmed by the Product Owner. Mount Dora does not trigger this (it is a Location, not a Brand).

**Future Intelligence Boundary (document only, per task § 3 — not implemented):** added as a new subsection in `Roadmap.md` — Brand Playbook belongs to the Brand; Location supplies local operational context; Customer Intelligence, Server Performance, and Service Copilot must eventually distinguish Brand-level expectations from Location-level context, and Service Copilot must scope guidance to the Brand/Location actually being served, not the Corporate owner. Not currently observable or testable with exactly one Location; becomes load-bearing only once a second Location carries real data. No Server Performance, Customer Intelligence, or Service Copilot code exists yet (all remain conceptual-only).

---

## H. Files changed

**Modified** (resolver/tests/docs; all already present at task start except the two `PROJECT_STATE.md`/`Roadmap.md` additions made in this session):

- `03 Software/RF-One Data Store/rfone_data_store/tips/resolvers.py` — FAILED Payment exclusion.
- `03 Software/RF-One Data Store/rfone_data_store/tips_validation.py` — one additional end-to-end regression check.
- `03 Software/RF-One Data Store/RESTAURANT_PROFILE.md` — § 0 Corporate/Brand/Location mapping; Area-split precondition note (from the prior stabilization task, left as-is).
- `01 Domains/Restaurant/Restaurant Semantic Model.md` — § 3 Corporate/Brand/Location resolution.
- `01 Domains/Restaurant/Roadmap.md` — § 5 Mount Dora onboarding tracking (approved structure), "Future multi-Brand compatibility," and this session's new "Future intelligence boundary" subsection.
- `01 Domains/Restaurant/Tips/Tip Allocation.md` — FAILED Payment evidence exclusion documented.
- `01 Domains/Restaurant/Model/OU-Restaurant.md` — note reconciling the Core-hierarchy "Restaurant" sense with the Runtime `Restaurant`(=Brand) entity.
- `PROJECT_STATE.md` — this session: new summary bullet for this task's two Product Owner decisions.
- Other modified files present at task start (`CLAUDE.md`, `OpenQuestions.md`, `00 Core/ConceptualArchitecture/01_Subject_and_Reality.md`, `Personnel Management/Selection/*`, `Restaurant/Organization/Restaurant Profile.md`, `Restaurant/Sales/Restaurant Sales Model.md`, `Restaurant/Server Performance/*`, `07 Tasks/Backlog/LEGACY_KNOWLEDGE_RECONCILIATION_BACKLOG.md`) belong to the prior `TASK_REPOSITORY_STABILIZATION_001` and were left untouched — out of this task's scope.

**Created** (present at task start):

- `03 Software/RF-One Data Store/rfone_data_store/sales_validation.py` — Sales validation suite, including CRITICAL A-H.
- `03 Software/RF-One Data Store/test_sales_validation.py` — its runner.
- `07 Tasks/Reports/TASK_REPOSITORY_STABILIZATION_001_REPORT.md` — the prior task's own report (untracked at task start; not authored by this task).

**Created by this task:**

- `07 Tasks/Reports/TASK_RESTAURANT_STRUCTURE_001_REPORT.md` (this report).

No production database, backup, credential, `.env`, or key/certificate file was touched. No file was deleted. No `git add`, `git commit`, or `git push` was performed.

---

## I. Product Owner questions — resolved this task

1. **FAILED Payments as SERVICE_OWNER evidence?** → **NO.** Implemented and tested (§ B, C).
2. **Mount Dora a separate Restaurant/Brand?** → **NO.** It is another Location of Rome's Flavours (§ D, F).
3. **May Corporate contain multiple Brands?** → **YES**, architecturally supported without schema change; no second Brand exists today (§ E, G).

## J. Genuinely unresolved items

- **`restaurants.name` = `"Rome's Flavours - WP"`** conflates Brand and Location identity. Not corrected (would require a production write). Recommended as part of Mount Dora onboarding, with explicit Product Owner authorization first.
- **Mount Dora production data** does not exist yet; onboarding remains fully dependent on it becoming available. No timeline implied.
- Carried over, unaffected by this task: Taxation/Purchasing jurisdiction rules (`OpenQuestions.md`), Sales' `business_date`/Void-Cancellation persistence gaps (`TASK_SALES_002_REPORT.md` § L).

None of these block calling this task complete.

---

## K. Git status

No `git add`, `git commit`, or `git push` was performed. `git status` at the end of this task shows 19 modified files and 3 untracked files (the two Sales validation files and this report), all uncommitted, matching the state left by the prior `TASK_REPOSITORY_STABILIZATION_001` plus this task's own resolver/documentation work — ready for Product Owner review before the next commit.

---

## FINAL STATUS

RESTAURANT STRUCTURE STATUS: COMPLETE — MULTI-LOCATION / MULTI-BRAND BOUNDARY DEFINED
