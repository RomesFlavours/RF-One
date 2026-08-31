# Tip Allocation

**Version:** 1.3
**Status:** Approved
**Module:** Restaurant Domain / Tips
**Origin:** TASK_TIPS_001; Shift-Location evidence TASK_TIPS_003; real resolver and Shift-Location epistemic correction TASK_TIPS_004; FAILED Payment evidence exclusion TASK_RESTAURANT_STRUCTURE_001

---

## Definition

A **Tip Allocation** is one atomic, auditable unit of Tip money credited to one Employee, produced by applying a valid Tip Policy Component to one recorded Tip.

Every Tip Allocation traces, without ambiguity, to:

```text
source PaymentTip
parent Payment
Order
Payment timestamp
Tip Policy valid at that time
Tip Policy Component
recipient basis
eligible Employee set
split method
rounding rule
final amount
```

RF-One never persists an opaque total with no traceable derivation. "Why did Employee X receive $Y from PaymentTip Z?" must always be reconstructable from the chain above.

---

## Service-attribution boundary

The single most important architectural boundary in this Domain: **the Employee(s) responsible for an Order's service are resolved through an explicit, configurable interface — never assumed from `Order.employee` or `Payment.employee`.**

```text
service-attribution resolver: Order -> RESOLVED | UNRESOLVED | AMBIGUOUS
```

- **RESOLVED** — one or more Employees are confidently identified as responsible for the service.
- **UNRESOLVED** — available data cannot reliably identify anyone.
- **AMBIGUOUS** — more than one candidate exists with no rule to disambiguate.

The concrete resolution strategy (which fields, which business rule, which external configuration) belongs to Restaurant/Profile/source configuration — it is never hard-coded as universal Tips semantics. When a resolver cannot confidently resolve an Order, the engine surfaces the unresolved/ambiguous state as an explicit calculation issue rather than guessing from `Order.employee`/`Payment.employee`.

**First real resolver (TASK_TIPS_004):** `OrderEmployeeServiceAttributionResolver` (`rfone_data_store/tips/resolvers.py`) is a generic, provider-independent resolution strategy — not a Rome's Flavours-specific mapping — built entirely from evidence the canonical Sales model already contains. It reads `Order.employee_id` (the single-value field the source POS associates with an Order) and cross-checks it against every **economically valid** `Payment.employee_id` already recorded under that same Order: agreement resolves to that Employee (corroborated by one or more independent POS observations); a NULL `Order.employee_id` is UNRESOLVED; a disagreement between `Order.employee_id` and any qualifying `Payment.employee_id` is AMBIGUOUS. The `TableServiceEmployee` participation relationship (this document's original, broader intended answer) remains structurally supported but is not the basis for this resolver, since no Restaurant using this Domain has ever ingested Table Service reconstruction data — a resolver built on it would resolve every real Order to UNRESOLVED.

**FAILED Payments are excluded from evidence (Product Owner decision, TASK_RESTAURANT_STRUCTURE_001).** A Payment only "corroborates or contradicts" `Order.employee_id` when its `result` is the canonical economically-valid value `SUCCESS` — the same value `rfone_data_store/tips/engine.py` already treats as the sole economically valid Payment state for a Tip to be allocated at all (`ISSUE_FAILED_PAYMENT_WITH_TIP`). A failed payment attempt (`Payment.result = FAIL`, the canonical failure value used throughout ingestion/reconciliation — see `03 Software/RF-One Data Store/rfone_data_store/ingestion/clover/reconciliation.py`) or a Payment whose `result` is otherwise unknown is evidence that a payment was *attempted*, never authoritative evidence of who actually served the table — reason: it is not authoritative service-attribution evidence, only settlement evidence. Concretely, a FAILED Payment can never: confirm the Service Owner, create AMBIGUOUS, override an otherwise-RESOLVED Order, or turn a RESOLVED Order into UNRESOLVED.

---

## Post-hoc temporal eligibility

For a recorded Tip attached to Payment `P`, the temporal anchor is always `T = P`'s own source payment timestamp (`Tip.md`, "Temporal anchor") — never the time a server later entered or adjusted the Tip, and never "now" (the time the calculation happens to run).

When a policy component requires presence-based eligibility (`ROLE_PRESENT_AT_PAYMENT`), eligible Employees are derived, at query time, from:

```text
Shifts active at T
∩ Employee Assignments valid at T
  (matching the component's Restaurant Role and Restaurant scope)
```

This is never a stored "employees present at payment time" snapshot — it is recomputed from source facts (Shift, Employee Assignment) whenever a calculation runs, so it always reflects the current state of that source data. `Employee.active` and the current Employee roster play no role in this determination — see `01 Domains/Restaurant/Organization/Employee Assignment.md`, "The critical rule for Tips and Payroll."

Where a Restaurant operates more than one Location, this resolution is also scoped to the specific Location of the Tip's own Order — never the Restaurant's full multi-Location set (`Tip Policy.md`, "Policy components"). `Shift.location_id` (TASK_TIPS_003), when populated, is the authoritative evidence of where that specific Shift occurred, and is compared directly against the Order's Location. This lets one Employee who genuinely works more than one Location be correctly eligible per-Shift — a Winter Park-tagged Shift is never eligible for a Mount Dora Tip, and vice versa.

**Shift-Location epistemic correction (TASK_TIPS_004):** when a Shift's own `location_id` is `NULL`, resolution depends on how many operational Locations the Restaurant currently has:

```text
Restaurant has exactly one operational Location
  -> safe fallback to Employee.location_id (there is no other Location it
     could plausibly be)

Restaurant has more than one operational Location
  -> presence at this Order's Location is UNKNOWN, never inferred from
     Employee.location_id — excluded from eligibility, with an explicit
     SHIFT_LOCATION_UNKNOWN warning raised (never silently guessed and
     never silently dropped without a trace)
```

**UNKNOWN IS NOT A FACT.** Once a Restaurant is multi-Location, an Employee's single, fixed home Location (`Employee.location_id`) is not evidence of where any *particular* Shift occurred — the fallback that was safe for a single-Location Restaurant becomes an unjustified guess the moment a second Location exists, even for a Shift whose Employee's home Location happens to agree with the Order's Location. Historical Shifts with `location_id IS NULL` are never fabricated or backfilled — this correction changes only how that existing `NULL` is *interpreted* at calculation time, never the stored fact itself.

Concurrent Employee Assignments may be legitimate (`01 Domains/Restaurant/Restaurant Semantic Model.md` §9 — e.g. an Employee holding both a `Manager` and a `Server` Assignment at once, in the same or different Operational Areas). Tip eligibility for a component is evaluated only against that component's own required Role: the presence of another, concurrent Assignment matching a different Role does not by itself invalidate eligibility. Concurrent Assignments are not automatically a conflict.

---

## Multiple eligible employees

A recipient group may contain zero, one, or many eligible Employees. Where more than one is eligible, the configured split method (`EQUAL_ELIGIBLE_HEADCOUNT` in this first implementation) divides the component's share among them, with deterministic minor-unit rounding — no example role or headcount is universal; the same mechanism applies to whatever `RestaurantRole` a Restaurant has actually configured. Within one `EQUAL_ELIGIBLE_HEADCOUNT` component, an Employee is counted once regardless of how many matching Assignment rows exist (e.g. the same Role valid in two Operational Areas at once still yields one headcount share, never two).

An Employee eligible for one component is not thereby excluded from another: whether the same Employee may receive allocations from more than one component of the same Tip Policy is a Tip Policy configuration decision (its components' recipient bases and shares), never a universal Tips-engine exclusion rule. The generic engine does not suppress a component's allocation merely because the same Employee also qualified for a different component.

---

## Deterministic rounding

Every allocation must reconcile exactly, in minor currency units, to the amount it was apportioned from — never losing or creating a cent, and always producing the same result for the same input. RF-One uses the largest-remainder (Hamilton) method with a fixed tie-break rule (see `03 Software/RF-One Data Store/rfone_data_store/tips/rounding.py`), applied at two levels: apportioning a recorded Tip across a policy's components, and apportioning a component's amount across its eligible Employees.

---

## Payment validity and refunds

Only economically valid Payments (the source's own success/result semantics — e.g. Clover's `SUCCESS`, never `FAIL`) produce allocatable Tips; a failed Payment's recorded Tip is never allocated. Where a Refund exists against a Payment, RF-One only treats the Tip itself as affected when the source data provides explicit evidence of that (e.g. a non-null, non-zero `Refund.tip_amount`) — otherwise it surfaces a refund-review condition rather than silently interpreting the Refund either way. See `Tip.md`, "Refunds and corrections."

---

## Calculation issues

Ambiguous or missing data always becomes an explicit, typed calculation issue — attached to the calculation run and, where applicable, to the specific PaymentTip/Payment/Order — distinguishing blocking conditions from warnings. RF-One never silently continues through a blocking ambiguity, and never silently picks a default when a Restaurant's configuration has not stated one.

---

## Auditability and reproducibility

Every calculation run records what it actually used (which policy, which period, a calculation version label) so the same source data and policy always produce the same atomic allocation results. Nothing here recalculates or overwrites a prior run's rows — a later run is a new, independently auditable set of facts, preserving the architectural ability to handle future corrections, reversals, and refunds without silently mutating history.

## Idempotency and supersession

A calculation run that would create a payable allocation set (mode `PERSIST`) is refused when its period overlaps an existing, unsuperseded `PERSIST`/`COMPLETE` run for the same Restaurant — a repeated calculation command must never silently create a second independently payable allocation set for the same Tips. A deliberate correction or redo (e.g. later evidence changes a Refund/Tip amount, per "Payment validity and refunds" above) is represented by explicitly superseding the prior run, never by silently re-running over it: the prior run's rows remain in place, unmodified, and are marked superseded by the new run — auditable history is preserved in both directions.
