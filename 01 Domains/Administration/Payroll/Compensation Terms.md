# Compensation Terms

**Version:** 1.0
**Status:** Approved
**Module:** Administration Domain / Payroll
**Origin:** TASK_PAYROLL_001

---

## Definition

A **Compensation Term** is a temporal, Employee-specific compensation configuration.

```text
Compensation belongs to the Employee's employment arrangement,
not universally to the RestaurantRole.
```

Two Employees performing the same function may legitimately have different compensation. Compensation history is never overwritten.

---

## Temporal semantics

```text
valid_from  (required)
valid_to    (nullable — open-ended/current)
```

A compensation change creates a **new** valid interval; the prior row's `valid_to` is closed, never rewritten in place. This is required to reconstruct historical payroll in case of dispute — mirroring the existing `EmployeeAssignment` temporal pattern (`01 Domains/Restaurant/Organization/Employee Assignment.md`).

---

## Multiple functions / multiple rates

One Employee may perform multiple functions with different compensation, concurrently:

```text
Employee X

Function A: restaurant service
  hourly rate A, hours from POS Shift/source account

Function B: social media
  hourly rate B, hours supplied manually
```

Multiple functions are **not** a conflict. The model supports more than one concurrently applicable Compensation Term for one Employee. One Employee is never required to have exactly one hourly rate.

The smallest provider-independent way to distinguish concurrent Compensation Terms is a configured label/code per term (`function_label`) — Payroll does not create a universal role ontology of its own. Where the current Restaurant Role/Employee Assignment can be referenced safely as optional provenance for a term, that reference is optional — Payroll never becomes semantically dependent on Restaurant to be internally valid.

---

## Compensation basis

Supported at least:

```text
HOURLY
SALARIED
```

- **HOURLY** — `rate` = amount per hour.
- **SALARIED** — the Product Owner wants Payroll to operate on the **actual base-pay amount for the Payroll Period**, not an annual salary conversion. A Compensation Term therefore carries `base pay per Payroll Period` directly. Annual contractual salary may exist elsewhere as administrative/contract information; Payroll does not require it to process a period, and it is never a required runtime field here.

A single Compensation Term is exactly one basis; it never mixes an hourly rate and a per-period base amount.

---

## Mid-period compensation changes

The Domain may represent a temporal compensation change at any instant — nothing prevents a `valid_from`/`valid_to` boundary from falling inside a Payroll Period.

However, the current provider workflow (ADP, manual entry) may not cleanly represent a mid-period rate change. For the first operational implementation:

```text
if more than one incompatible Compensation Term applies inside one
Payroll Period in a way the current provider output cannot represent
safely
→ MANUAL_REVIEW_REQUIRED
```

Provider behavior is never invented to resolve this automatically. The data model stays temporally correct regardless, so this limitation can be removed once a richer provider integration exists.

---

## Business Rules

- A Compensation Term always references exactly one Employee. It is never attached to a `RestaurantRole` as a universal rate.
- `valid_from` is required; `valid_to` is nullable and represents an open-ended/current term when null.
- A compensation change is represented as a new Compensation Term row with its own `valid_from` — never an in-place update that erases the prior value.
- Multiple concurrent Compensation Terms for one Employee (different `function_label`) are permitted and are not treated as a conflict.
- Exactly one of `hourly_rate` / `salaried_period_amount` is populated per term, matching `compensation_basis`.
- Two Employees may share the same `function_label` with different rates — this is not a uniqueness violation.
