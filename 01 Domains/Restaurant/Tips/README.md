# Restaurant Tips

**Version:** 1.0
**Status:** Approved
**Module:** Restaurant Domain / Tips
**Origin:** TASK_TIPS_001

---

## Purpose

This section defines the canonical semantics of **Tips** in RF-One: an observable economic fact attached to a `Payment`, and a **post-hoc**, data-driven method for allocating that fact to the Employees whose service it rewards.

Central principle:

```text
RF-One does not observe or control the POS at payment time.

It calculates later, from persisted source facts:

Payment
→ recorded Tip
→ Order context
→ Payment timestamp
→ Shifts intersecting that timestamp
→ Employee Assignment / Restaurant Role valid at that timestamp
→ Tip Policy
→ atomic allocations
```

This is Restaurant-independent and POS-independent at the Domain level. Nothing here prescribes Rome's Flavours percentages, role names, or Clover-specific semantics as universal rules — see `01 Domains/Restaurant/Restaurant Semantic Model.md` §14, "Examples as configuration, not ontology," which applies equally to Tip Policy configuration.

---

## Files in this section

| File | Concept |
|---|---|
| [Tip.md](Tip.md) | The observable Tip fact itself, attached to Payment |
| [Tip Policy.md](Tip%20Policy.md) | Restaurant-configured, temporally valid allocation rules |
| [Tip Allocation.md](Tip%20Allocation.md) | The atomic, auditable result of applying a Tip Policy |

---

## The ten load-bearing facts

```text
1.  Tip is an observable economic fact attached to Payment.
2.  Payment employee is not necessarily service owner.
3.  Order employee is not necessarily service owner.
4.  Tip allocation is post-hoc.
5.  Payment timestamp is the temporal anchor for presence-based eligibility.
6.  Presence is derived from Shift data.
7.  Role is derived from EmployeeAssignment valid at the relevant time.
8.  Multiple eligible employees are supported.
9.  SourceRole is not silently mapped to RestaurantRole.
10. Unobserved cash Tip is outside automatic allocation.
    Tip ≠ Service Charge.
    Allocation results are derived, atomic, auditable, and reproducible.
```

Every one of these is enforced structurally by the schema and engine documented under `03 Software/RF-One Data Store/` (see `RESTAURANT_PROFILE.md` §3 for the original statement of this contract, and `DATABASE_SCHEMA.md` §4b for the implemented tables) — not merely asserted here.

---

## Relationship to the Restaurant Semantic Model

Tips consumes, but does not redefine:

```text
Restaurant                (Restaurant Semantic Model.md §3)
Restaurant Profile         (§4)
Operational Area           (§5)
Restaurant Role            (§7)
Employee Assignment        (§8-9)
```

The activity/presence invariant this Domain relies on most heavily is `Restaurant Semantic Model.md` §9:

> `Employee Assignment ≠ Employee worked during a period`

Tips is the first concrete consumer of the resolution path that invariant describes: `period → Shifts intersecting the period → Employees actually present → Employee Assignment valid at the relevant time → Operational Area + Restaurant Role → applicable rule`. Payroll and Scheduling are expected future consumers of the identical path — Tips does not invent a parallel one.

---

## Relationship to Clover source semantics

```text
Clover named Role (SourceRole)   ≠ Restaurant Role
Clover systemRole                ≠ Restaurant Role
Payment.employee                ≠ Service Employee / Tip recipient
Order.employee                  ≠ Service Employee
Clover Gratuity / order-fee Service Charge   ≠ Payment Tip
```

`Payment.employee` and `Order.employee` are POS-operational associations (who processed the payment, who the order was opened under) — evidence about POS operations, never universal service-ownership semantics. Which Employee(s) are actually responsible for the service an Order represents is resolved through an explicit, configurable **service-attribution boundary** (see `Tip Allocation.md`), never inferred from either field.

---

## Relationship to Personnel Management

Tips is Restaurant-specific operational calculation; it does not belong to, and does not redefine, Personnel Management's Workforce/Selection/Training/Performance/Personnel Decisions modules (`01 Domains/Personnel Management/README.md`). Realized Tip Allocation is documented Service Quality evidence for the Restaurant Domain's own `Server Performance` module (`01 Domains/Restaurant/Server Performance/Perceived Service Quality.md`, TASK_SERVER_PERFORMANCE_001) — Tips itself still makes no Performance judgment, and Server Performance does not redefine Tip allocation.

---

## Related documents

- [../Restaurant Semantic Model.md](../Restaurant%20Semantic%20Model.md) — Domain vs. Profile vs. Instance, Operational Area/Restaurant Role/Employee Assignment semantics
- [../Organization/README.md](../Organization/README.md) — Restaurant Profile implementation this Domain consumes
- `03 Software/RF-One Data Store/RESTAURANT_PROFILE.md` §3 — the original Tips/Payroll future contract this task implements
- `03 Software/RF-One Data Store/DATABASE_SCHEMA.md` §4b — implemented Tip Policy / Calculation schema
- `07 Tasks/Reports/TASK_TIPS_001_REPORT.md` — implementation history
