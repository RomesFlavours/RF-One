# Personnel Cost

**Version:** 1.0
**Status:** Approved
**Module:** Administration Domain (transversal — not owned by Payroll)
**Origin:** TASK_LABOR_COST_001

---

## Purpose

This document defines the canonical economic-cost model for people: **Total Employee Cost** and **Total Personnel Cost**. It resolves the previously open question of whether generic personnel-related overhead may be allocated to individual Employees (`OpenQuestions.md`) and replaces the earlier, now-rejected `Direct Employee Labor Cost + Allocated Labor Overhead = Fully Loaded Labor Cost` framing.

This concept sits at Administration-level, not inside `Payroll/`, because Employee cost is not exclusively a payroll concern — Payroll is one major source/component among others (see §6, "Payroll boundary").

---

## 1. Canonical principle: Employee-attributable cost is causal

A cost belongs to a specific Employee only when it is causally attributable to that Employee.

Canonical counterfactual test:

```text
If Employee X did not exist / were not in that employment relationship,
would this cost disappear or change in an identifiable way?

YES
→ Employee-attributable cost

NO / UNKNOWN
→ not an Employee cost
```

This is the primary semantic boundary for everything below. A cost is never classified as Employee-attributable merely because it is generally related to personnel.

Examples that may be Employee-attributable when supported by facts (illustrative, not a closed taxonomy):

```text
wages, salary, overtime, bonus
employer-side payroll taxes/liabilities
employee-specific benefit cost
company vehicle assigned to the Employee
vehicle insurance attributable to that assignment
fuel attributable to that Employee/assigned asset
per-Employee software/license fee
other costs that genuinely change because of that specific Employee
```

---

## 2. Total Employee Cost

```text
Total Employee Cost
```

means: the total economic cost that is causally attributable to one specific Employee for a defined analysis period.

It is derived from atomic cost facts and temporal attribution evidence (§4, §5) — it is never persisted as a canonical stored aggregate (see §8, "Persistence invariant").

`Total Employee Cost` is the canonical semantic term. `Fully Loaded Labor Cost` (`Payroll/Labor Cost.md`) is retained only as a non-canonical/legacy/business synonym for the same Employee-attributable total; it never implies loading arbitrary shared overhead onto an Employee.

### Rejected: Allocated Labor Overhead

The earlier model:

```text
Direct Employee Labor Cost
+
Allocated Labor Overhead
=
Fully Loaded Labor Cost
```

is rejected. If a cost can genuinely be attributed to an Employee, it is already an Employee-attributable cost under §1 — no separate "allocation" step is needed. If it cannot be attributed to an Employee, artificially dividing it among Employees creates false economic evidence. `Allocated Labor Overhead` is therefore never a canonical component of Employee Cost, and RF-One defines no allocation rule whose only purpose is to force generic personnel cost onto individual Employees.

---

## 3. Unallocated Personnel Cost

```text
Unallocated Personnel Cost
```

means: a real personnel-related economic cost that cannot currently be causally attributed to any specific Employee (e.g. a genuinely fixed/shared personnel-related expense with no Employee-specific causal link).

```text
Known Employee attribution
→ Total Employee Cost component

Unknown / non-causal Employee attribution
→ Unallocated Personnel Cost
```

`Unallocated Personnel Cost` is never distributed across Employees merely to make per-Employee totals add up. It may later be reclassified toward a specific Employee only when new evidence establishes genuine causal attribution — the reclassification is a new fact, not a retroactive rewrite of the original cost fact.

---

## 4. Total Personnel Cost

```text
Total Personnel Cost
=
Σ Total Employee Cost
+
Unallocated Personnel Cost
```

for the relevant organizational scope and analysis period. This preserves both company-wide personnel economics and truthful, uninflated Employee-level economics without falsifying Employee-to-Employee comparisons.

---

## 5. Economic Cost vs. Cash Movement

```text
Economic Cost
≠
Cash Movement
```

A payment is a cash fact. An economic cost belongs to the period in which it is economically incurred/earned/consumed.

```text
production bonus earned in December
paid in January

→ Employee Cost: December
→ Cash Movement: January
```

Cash timing never determines Employee Cost timing. This is a semantic boundary only — no Cash Flow model is implemented here.

A bank/card transaction is likewise a source fact, not automatically an Employee Cost:

```text
bank/card transaction
→ fuel purchase
→ Vehicle / Employee attribution if supported
→ Employee Cost only when causally attributable
```

If a source provides a real transaction/economic date, RF-One uses it. If only the cash posting date is known and the economic date is unknown, the uncertainty is preserved — RF-One never invents a more precise economic date. A future, stronger source may add better attribution/economic-date evidence without rewriting the original bank fact.

---

## 6. Multi-period costs: calendar-day derivation

For a cost whose economic coverage spans multiple days/months, RF-One persists the atomic facts:

```text
source cost amount
coverage_start
coverage_end
Employee / asset attribution evidence
assignment interval if relevant
```

Derived cost for an analysis period is based on **actual calendar-day overlap** between the coverage interval and the analysis period (and, where relevant, the assignment interval — see §7). RF-One does not use a 30-day standard month, a 360-day accounting year, or synthetic equal months for Employee-cost attribution, unless a future source/legal rule explicitly requires such a convention.

```text
Insurance cost: 2,400
Coverage: Jan 1 → Dec 31

Employee assignment to covered vehicle:
Mar 10 → Sep 20
```

The Employee-attributable portion is derived from the actual overlapping calendar days between the coverage interval and the assignment interval. The derived monthly/payroll-period share is a calculation performed on demand, never stored canonical truth.

---

## 7. Asset-mediated Employee attribution

A cost may become Employee-attributable through an assigned asset. Canonical attribution path:

```text
Cost Fact
→ Asset
→ Asset Assignment
→ Employee
```

```text
vehicle insurance
→ Vehicle A
→ assigned to Employee X during interval T
→ Employee-attributable only for the valid overlap
```

The original source cost fact is never duplicated or rewritten — the Employee attribution is temporal and derived from the assignment evidence (calendar-day overlap, §6). If an asset cost cannot be attributed to one Employee under the available evidence, it remains outside that Employee's total (and is `Unallocated Personnel Cost`, §3, if no other Employee attribution applies) until attribution becomes factual. RF-One never invents a sharing ratio across multiple candidate Employees.

`Asset` and `Asset Assignment` here name the attribution *pattern*, not a modeled entity: no Asset/Asset Assignment schema is introduced by this task (see `07 Tasks/TASK_LABOR_COST_001_...md` §19). A future task defines the minimal Asset/Asset Assignment representation once a real asset-cost source (e.g. a company vehicle registry) is integrated.

---

## 8. Persistence invariant

> Persist source facts, events, assignments, configuration, and evidence. Derive calculations.

RF-One does not store canonical:

```text
monthly Employee cost shares
Payroll-period Employee cost shares
Location shares
Total Employee Cost aggregate
Total Personnel Cost aggregate
```

when they can be recalculated from atomic facts. Actual external events are persisted when they happened, including actual Payroll results/payments (`Payroll/Payroll Provider Result.md`). A derived calculation may exist as ephemeral output or an explicit calculation/audit run if needed later, but never becomes the canonical source of truth.

---

## 9. Location reporting is derived, not owned

The canonical cost fact remains:

```text
Cost
→ Employee
```

A person-specific cost never becomes a Location cost merely because reporting later needs a Location view. Location context (e.g. a Restaurant in the Restaurant Domain, or an equivalent operating unit in another Domain) is derived through the Employee's valid assignment(s) to that Location — e.g. `Restaurant/Organization/Employee Assignment.md` for the Restaurant Domain.

For a reporting view where one Employee is associated with multiple Locations over the analysis period:

```text
if a real allocation measure exists
→ derive the Location view using that measure
   e.g. actual worked time by Location

if no real measure exists
→ equal split across the Employee's valid Location assignments,
   for that derived reporting view only
```

This is a derived reporting distribution of an already Employee-attributable cost — it is not an allocation of generic Personnel overhead to Employees, and it must never be confused with §2's rejected `Allocated Labor Overhead`. Derived Location shares are never persisted as canonical cost facts (§8).

---

## 10. Payroll boundary

`Payroll Employer Cost` (`Payroll/Labor Cost.md`) is one major source/component of `Total Employee Cost` — Payroll does not own all Employee Cost.

```text
Payroll atomic facts
→ employer-paid earnings
→ employer-side liabilities
→ Payroll Employer Cost

Payroll Employer Cost
+ other Employee-attributable economic cost facts (asset-mediated or direct)
→ Total Employee Cost
```

Examples of Employee-attributable cost outside Payroll may include a company vehicle, insurance, fuel, or other Employee-specific benefits/costs. These concepts are never moved into Payroll solely because they affect `Total Employee Cost` — Payroll remains the administrative executor of compensation (`Payroll/README.md`), not the owner of vehicle/fuel/benefit economics.

---

## 11. Personnel Management boundary

Personnel Management (`01 Domains/Personnel Management/README.md`) may consume `Total Employee Cost` as evidence — for example when a Personnel Decision compares the current person's expected value against an alternative's. Personnel Cost supplies facts; Personnel Management owns the decision.

The reason the Employee Cost model must remain causally truthful:

```text
generic shared cost that does not change when Employee A is replaced by
Candidate B must not be artificially attached to Employee A
```

If RF-One attached generic overhead to Employee A but not to Candidate B (who has none yet), any Selection/Personnel Decision comparison between them would be built on false comparative evidence. This is the architectural reason §2's `Allocated Labor Overhead` is rejected, not merely a modeling preference.

No Selection or Personnel Decision logic is modeled by this document.

---

## 12. Replacement Decision Cost is separate

```text
Employee Cost
≠
Replacement Decision Cost
```

Costs caused by the act of replacing/changing personnel — recruiting, hiring/onboarding, transition, vacancy effects, severance — do not become intrinsic historical cost of either the incumbent or the candidate merely because they participate in the decision. They belong to the Personnel Decision that caused them, not to `Total Employee Cost`. This boundary is recorded here only to prevent semantic contamination of Employee Cost; Replacement Decision Cost is not further modeled by this document.

---

## Related documents

- [README.md](README.md) — Administration Domain
- [Payroll/Labor Cost.md](Payroll/Labor%20Cost.md) — `Payroll Employer Cost`, the Payroll-sourced component of `Total Employee Cost`
- [Payroll/README.md](Payroll/README.md) — Payroll module boundary
- [../Personnel Management/README.md](../Personnel%20Management/README.md) — the consumer of `Total Employee Cost` as decision evidence
- [../../OpenQuestions.md](../../OpenQuestions.md) — resolution record for the generic-overhead-allocation question
- `07 Tasks/Reports/TASK_LABOR_COST_001_REPORT.md` — task that produced this document
