# Tip Allocation

**Version:** 1.0
**Status:** Approved
**Module:** Restaurant Domain / Tips
**Origin:** TASK_TIPS_001

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
