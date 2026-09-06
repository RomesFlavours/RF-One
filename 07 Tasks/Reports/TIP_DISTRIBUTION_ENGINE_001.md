# TIP_DISTRIBUTION_ENGINE_001 — Implementation Report

Scope: the first operational version of the generic Tip Distribution Engine —
configurable Distribution Rules (extended), Order-level Gross Earned Tips,
Settlement-Time-based rule-version selection, ACTIVE_AT_SETTLEMENT
eligibility from persisted Shift facts, EQUAL distribution, atomic
allocation results, Rome's Flavours' initial Host rule, and a basic
Calculate/Review/drill-down web UI. Per
`01 Domains/Business Domain/Restaurant/Functional Specifications/
TIP_DISTRIBUTION_ENGINE_FUNCTIONAL_SPEC_001.md`.

---

## Files changed

**Schema**
- `rfone_data_store/models.py` — `TipDistributionRuleVersion` gains four new
  columns (`eligibility_mode`, `distribution_method`,
  `no_eligible_recipient_behavior`, `transaction_scope`); two new tables,
  `TipDistributionCalculationRun` and `TipDistributionAllocation`.
- `migrations/versions/d8f3a6c1e9b4_add_tip_distribution_engine_schema.py`
  (new) — additive; head is now `d8f3a6c1e9b4` (was `c4e8a1f6b3d9`).

**Service / engine**
- `rfone_data_store/tips/distribution_rule_service.py` — `create_rule`/
  `create_new_version` extended with the four new fields (defaulted to the
  only values the engine implements, so every existing caller keeps working
  unchanged) plus their validators.
- `rfone_data_store/tips/distribution_engine.py` (new) — the calculation
  engine itself: Gross Earned Tips, Settlement-Time rule selection,
  ACTIVE_AT_SETTLEMENT eligibility, EQUAL allocation, recalculation
  safety, Employee Review aggregation, Order drill-down.

**UI**
- `Tips/app.py` — three new routes: `GET /calculate-tips`,
  `POST /calculate-tips/run`, `GET /calculate-tips/order/<id>`.
- `Tips/templates/calculate_tips.html` (new), `Tips/templates/
  order_drilldown.html` (new), `Tips/templates/base.html` (new nav tab).

**Tests**
- `rfone_data_store/tips_distribution_engine_validation.py` (new),
  `test_tips_distribution_engine.py` (new).

## Existing distribution code reused

Per task §1's explicit instruction, inspected first and reused rather than
duplicated:
- `tips/distribution_rule_service.py` / `TipDistributionRule`/
  `TipDistributionRuleVersion` (TIPS_DISTRIBUTION_RULES_001) — the rule
  configuration/versioning layer this task's engine reads. `list_rules`,
  `get_version_effective_at` are called directly, unmodified in behavior.
- `tips/clover_import_service.get_order_settlement_time` — the canonical
  Settlement Time helper, reused verbatim (task §5's explicit instruction).
- `tips/rounding.equal_split` — the existing deterministic residual-cent
  EQUAL-split helper (task §12), reused verbatim; no new rounding logic was
  written for the outbound recipient split.

**Explicitly NOT reused**: `tips/engine.py` / `TipPolicy` /
`TipCalculationRun` / `TipAllocation` — a separate, still-operational,
pre-existing engine with a different primary unit (Payment, not Order), a
different temporal anchor (`Payment.created_at`, not Settlement Time), and a
different role-resolution/no-eligible-recipient model
(SERVICE_OWNER/ROLE_PRESENT_AT_PAYMENT, redistribute-to-components). Its own
code comments already state this task's engine ("the universal engine")
does not reconcile, merge, or build on it. Flagging this per the Challenge
Rules: **two coexisting Tip-calculation subsystems now exist in this
codebase.** They do not conflict at the schema or runtime level (entirely
separate tables, `tip_calculation_runs`/`tip_allocations` vs.
`tip_distribution_calculation_runs`/`tip_distribution_allocations`), but a
future Product Owner decision is needed on whether the legacy engine should
be retired once this one covers Rome's Flavours' real needs — not decided
here, and no code from either was changed to affect the other.

## Rule model / versioning

`TipDistributionRuleVersion` now also carries `eligibility_mode`,
`distribution_method`, `no_eligible_recipient_behavior`, `transaction_scope`
(task §6) — free-string columns (no DB CheckConstraint), matching this
schema's existing convention for evolving classification fields
(`TipPolicyComponent.no_eligible_behavior`). `distribution_rule_service`'s
validators currently accept exactly one value per axis
(`ACTIVE_AT_SETTLEMENT`/`EQUAL`/`SOURCE_RETAINS`/`ALL`) — the only ones the
engine can compute — so a rule can never be configured with a mode nothing
can honor. Broadening these is a code change, never a migration.

Versioning itself is unchanged: `create_new_version` still closes only the
prior open version's `effective_to`; `get_version_effective_at` still
selects by the timestamp's containment in `[effective_from, effective_to)`.
The engine always resolves the applicable version using the **Order's own
Settlement Time**, never "now" — verified by test (a version created after
a historical Order's settlement time never alters that Order's
calculation).

## Rome's Flavours initial configuration

`seed_tip_distribution_rules.py` (existing, from prior work) needed **no
changes** — its call to `rule_svc.create_rule(...)` doesn't pass the four
new fields, so it picks up the new defaults, which are exactly Rome's
Flavours' spec: Source Role SERVER, Recipient Role HOST, Calculation Base
TIP_PLUS_GRATUITY, Rate 10% (editable — proven configurable by test #15,
which creates a second version at 25% and confirms it is used, never a
hardcoded 10%), Eligibility ACTIVE_AT_SETTLEMENT, Distribution Method EQUAL,
No Eligible Recipient SOURCE_RETAINS, Transaction Scope ALL.

## Gross Tip calculation

Order-level, per spec §3: `voluntary tips (SUCCESS Payments only) +
automatic gratuity (OrderFee, already deduplicated once-per-Order by the
ingestion layer)`. One deliberate interpretation beyond the spec's literal
text: a Payment's recorded tip is only counted when `Payment.result ==
"SUCCESS"` — a FAILED payment never actually settled, so its `tipAmount`
was never real collected money. Verified by tests #1-4 (voluntary-only,
gratuity-only, both, split-payment-counts-gratuity-once) and #5 (Order.
employee owns Gross Tips regardless of a differing Payment.employee).

## Settlement Time use

Every rule-version-selection, eligibility, and period-inclusion decision
uses `get_order_settlement_time` — never `Payment.modifiedTime` or
`Order.created_at`/`modified_at`. One implementation note: SQLite round-trips
`DateTime(timezone=True)` as offset-naive; `distribution_engine._aware_utc`
normalizes the settlement-time value back to aware UTC immediately after
computing it, so every downstream comparison stays consistent regardless of
whether a caller's period bounds came from a fresh Python value or a
reloaded ORM attribute.

## Eligibility (ACTIVE_AT_SETTLEMENT)

Implements task §9's literal formula: `clock_in <= settlement_time AND
(clock_out IS NULL OR settlement_time < clock_out)`. Role-holding reuses the
existing `EmployeeAssignment` structure (task §10's "use existing RF-One
employee/role/source-role structures") rather than inventing a new
membership concept — the same mechanism `tips/engine.py`'s legacy engine
already uses for the same purpose. Verified by tests #6-#9 (host-count
scenarios) and #10-#12 (clock-out-before/clock-in-after/open-shift edge
cases).

**Deliberate scope reduction vs. the legacy engine**: Shift-Location
matching here is a simple "`Shift.location_id` matches the Order's Location,
or is NULL" rule — it does not reproduce the legacy engine's fuller
multi-Location epistemic-gap handling (TASK_TIPS_004's `location_unknown`
tracking). Rome's Flavours is single-Location today, and task §10 explicitly
forbids "broad architecture/integrity reviews" and redesigning Personnel/
Organization; this is flagged as a genuine gap to revisit if/when a second
Location is onboarded, not hidden.

## EQUAL allocation / rounding

Recipient split reuses `rounding.equal_split` unchanged: verified with the
spec's own literal example (pool 1000 cents / 3 recipients → 333/333/334,
reconciling exactly — test #8/#17). The pool itself (`base_amount × rate /
100`) is rounded once, deterministically, via `Decimal` + `ROUND_HALF_UP` to
the nearest cent — never floating point, and always the same output for the
same input.

## Atomic result model

`TipDistributionAllocation` — one row per (calculation run, Order, Rule
Version, recipient), including the SOURCE_RETAINS case as one explicit row
with `recipient_employee_id IS NULL`, `no_eligible_recipient = True`,
`allocated_amount_minor = 0`, and `pool_amount_minor` still populated (task
§11/§14 — "the fact that nobody was eligible" is never silently omitted).
Every field task §14 lists is present: run, Order, source employee, Rule
Version (+ a calculation_base/rate snapshot for audit resilience), base
amount, rate, pool, recipient, eligibility basis (free text), allocated
amount, Settlement Time, and `created_at`.

Independent rules (task §13) verified directly: a Host 10% rule and a
Bartender 5% rule on the same Order both compute from the *same* original
10000-cent base (1000 and 500 respectively) — never 5% of a post-Host
9000-cent remainder (test #16).

## Employee aggregation

`build_employee_review` derives Gross/Outbound/Inbound/Net fresh from
persisted facts on every call — nothing is stored as a redundant summary
table (task §19's explicit "do not replace atomic data with these
summaries"). Verified to reconcile exactly against a hand-summed pass over
the same run's `TipDistributionAllocation` rows (test #18). Refunds surface
as a warning on the affected employee's row (never an automatic reversal —
test #20); a `no_eligible_recipient` allocation also surfaces as a warning
("pool retained").

## Recalculation behavior

Recalculating the **exact same** `restaurant_id`/`period_start`/
`period_end` as an existing COMPLETE, unsuperseded run auto-supersedes the
prior run (`superseded_by_calculation_run_id` set, its rows never deleted or
rewritten) and produces a fresh, equally-sized allocation set under a new
run id — verified by test #19. A **different, only partially-overlapping**
period is refused (`FAILED` status with an explanatory `notes`) rather than
silently guessed at, since this task's UI has no explicit "supersede run
#N" control. `get_latest_unsuperseded_run` is what the Review UI queries, so
it always shows the current, non-superseded answer for an exact period.

## UI added

Three new routes/pages under a new "Calculate Tips" nav tab:
- **Calculate Tips** (`/calculate-tips`) — From/Through form + "Calculate
  Tips" button; below it, the Employee Review table (Employee, Gross
  Earned Tips, Outbound, Inbound, Net, a warning badge with hover detail,
  and links to every Order touching that Employee).
- **Order drill-down** (`/calculate-tips/order/<id>`) — Settlement Time,
  Voluntary Tip/Gratuity/Gross breakdown, a Refund banner if applicable, and
  a table of every applied Rule (Rule Version, Calculation Base, Rate, Base
  Amount, Generated Pool, Recipient, Allocated, and the eligibility basis
  text).
- No manual-adjustment UI, no approve/lock controls — out of scope.

Verified end-to-end via Flask's test client against a disposable database
(no real browser is available in this environment): GET before/after
calculation, POST to calculate, GET the Order drill-down, and a same-period
recalculation — all returned HTTP 200 with the expected content (Gross
$10.00, pool $1.00, `ACTIVE_AT_SETTLEMENT` eligibility text).

## Tests / results

New suite `test_tips_distribution_engine.py` — **29/29 checks passed**,
covering all 21 numbered scenarios from task §23 plus reconciliation,
recalculation-safety, refund, and drill-down checks.

Regression — every suite task §24 names, all still passing unchanged:
- `test_tips_engine.py` (legacy engine): 54/54.
- `test_tips_clover_import.py`: 38/38.
- `test_tips_import_concurrency_guard.py`: 15/15.
- `test_tips_distribution_rules.py`: 24/24 (the new optional rule-config
  fields default to values every existing test call already implies).

`test_tips_engine.py` internally exercises `schema_validation.py` (the
shared cross-Domain schema check) as part of its own fixture setup, so the
additive `models.py` changes are confirmed not to break schema validation
without a separate broad-suite run (task §24: "only run broader suites if
genuinely required" — it wasn't).

All suites provision their own disposable SQLite database and never touch
the shared operational database or contact Clover.

## Remaining items (explicitly not implemented)

- **Manual adjustments** — no adjustment entity, no UI. `Net (before
  adjustments)` is exactly that; a later task would add the ± adjustment
  layer spec §19 describes.
- **Review → Approve → Lock workflow** — `TipDistributionCalculationRun.
  status` only reaches `RUNNING`/`COMPLETE`/`FAILED`. The
  `superseded_by_calculation_run_id` mechanism is deliberately structured so
  a future `LOCKED` status could refuse superseding without a schema
  change, but no lock enforcement exists yet.
- **Payment Batch** — no payout/disbursement concept of any kind.
- **Automatic POS/batch scheduling** — calculation is only ever
  user-triggered from the "Calculate Tips" button; nothing runs on a
  schedule.
- **HOURS_PROPORTIONAL / WEIGHTED_HOURS / PERIOD_HOURS** — not implemented;
  the schema does not prevent adding them later (free-string columns), but
  `distribution_rule_service`'s validators currently reject any rule
  configuration naming them.
- **TOTAL_SALES / FOOD_SALES / BEVERAGE_SALES** — remain valid, storable
  Calculation Base configuration (existing CheckConstraint already allows
  them), but the engine reports a clear `NOT_IMPLEMENTED` allocation row
  rather than computing them if one is ever configured.

## Open question for the Product Owner

Should the legacy `tips/engine.py`/`TipPolicy` calculation path be retired
now that an Order-level, Settlement-Time-based engine exists, or kept
running in parallel for some other purpose? Not decided or acted on by this
task.
