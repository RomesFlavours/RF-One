# TASK_LABOR_COST_001 — Formalize Employee Cost and Personnel Cost Semantics

## 1. Purpose

Formalize the RF-One semantic model for Employee Cost and total Personnel Cost based on the completed analysis interview.

This task is **documentation-first**.

Do not expand into Personnel Selection, training economics, replacement decisions, accounting, cash-flow implementation, or benefit-provider integrations.

The objective is to make the cost semantics canonical and remove the earlier, now-rejected assumption that generic personnel overhead should be artificially allocated to Employees.

---

## 2. Read first

Read `CLAUDE.md` completely.

Then read at minimum:

```text
OpenQuestions.md

01 Domains/Administration/README.md
01 Domains/Administration/Payroll/README.md
01 Domains/Administration/Payroll/Labor Cost.md
01 Domains/Administration/Payroll/Payroll Provider Result.md
01 Domains/Administration/Payroll/Payroll Processing.md

01 Domains/Personnel Management/README.md

07 Tasks/Reports/TASK_PAYROLL_001_REPORT.md
```

Inspect the current wording before editing.

Do not assume the current `Fully Loaded Labor Cost` wording is still correct. This task explicitly revises that concept.

---

## 3. Canonical principle: Employee-attributable cost is causal

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

This is the primary semantic boundary.

Examples that may be Employee-attributable when supported by facts:

```text
wages
salary
overtime
bonus
employer-side payroll taxes/liabilities
employee-specific benefit cost
company vehicle assigned to the Employee
vehicle insurance attributable to that assignment
fuel attributable to that Employee/assigned asset
per-Employee software/license fee
other costs that genuinely change because of that specific Employee
```

The list is illustrative, not a closed taxonomy.

Do not classify a cost as Employee-attributable merely because it is generally related to personnel.

---

## 4. Canonical Employee cost concept

Use a clear canonical concept such as:

```text
Total Employee Cost
```

meaning:

> the total economic cost that is causally attributable to one specific Employee for a defined analysis period.

It is derived from atomic cost facts and temporal attribution evidence.

Do not persist a redundant `Total Employee Cost` aggregate as canonical truth when it can be recalculated.

If existing documentation uses `Fully Loaded Labor Cost`, revise it so that it cannot imply arbitrary allocation of generic overhead.

Preferred outcome:

```text
Total Employee Cost
```

is the canonical semantic term.

If `Fully Loaded Labor Cost` is retained at all, document it only as a non-canonical/legacy/business synonym for the same Employee-attributable total and explicitly state that RF-One does **not** load arbitrary shared overhead onto an Employee.

---

## 5. Remove artificial Allocated Labor Overhead from Employee cost

The earlier model:

```text
Direct Employee Labor Cost
+
Allocated Labor Overhead
=
Fully Loaded Labor Cost
```

is rejected.

Reason:

If a cost can genuinely be attributed to an Employee, it is already an Employee-attributable cost.

If it cannot be attributed to an Employee, artificially dividing it among Employees creates false economic evidence.

Therefore do **not** use:

```text
Allocated Labor Overhead
```

as a canonical component of Employee Cost.

Do not create allocation rules whose only purpose is to force generic personnel cost onto individual Employees.

---

## 6. Unallocated Personnel Cost

Create/define:

```text
Unallocated Personnel Cost
```

Meaning:

> a real personnel-related economic cost that cannot currently be causally attributed to any specific Employee.

Examples may include genuinely fixed/shared personnel-related expenses where no Employee-specific causal attribution exists.

Canonical behavior:

```text
Known Employee attribution
→ Total Employee Cost component

Unknown / non-causal Employee attribution
→ Unallocated Personnel Cost
```

Do not distribute `Unallocated Personnel Cost` across Employees merely to make per-Employee totals add up.

---

## 7. Total Personnel Cost

Define:

```text
Total Personnel Cost
=
Σ Total Employee Cost
+
Unallocated Personnel Cost
```

for the relevant organizational scope and analysis period.

This allows RF-One to preserve both:

```text
company-wide personnel economics
```

and:

```text
truthful Employee-level economics
```

without falsifying Employee comparisons.

---

## 8. Economic cost vs cash movement

Preserve the distinction:

```text
Economic Cost
≠
Cash Movement
```

A payment is a cash fact.

An economic cost belongs to the period in which it is economically incurred/earned/consumed.

Example:

```text
production bonus earned in December
paid in January

→ Employee Cost: December
→ Cash Movement: January
```

Do not make cash timing determine Employee Cost timing.

This task should document the semantic boundary only; do not implement Cash Flow.

---

## 9. Multi-period costs and coverage

For a cost whose economic coverage spans multiple days/months, persist the atomic facts:

```text
source cost amount
coverage_start
coverage_end
Employee / asset attribution evidence
assignment interval if relevant
```

Do not persist monthly or Payroll-Period allocations as canonical truth.

Derived cost for an analysis period is based on actual temporal overlap.

Use **real calendar days**.

Do not use:

```text
30-day standard month
360-day accounting year
synthetic equal months
```

for Employee-cost attribution unless a future source/legal rule explicitly requires such a convention.

Example:

```text
Insurance cost: 2,400
Coverage: Jan 1 → Dec 31

Employee assignment to covered vehicle:
Mar 10 → Sep 20
```

RF-One derives the Employee-attributable portion from the actual overlapping calendar days.

The derived monthly/payroll-period shares are calculations, not stored truth.

---

## 10. Asset-mediated Employee attribution

A cost may become Employee-attributable through an assigned asset.

Canonical path:

```text
Cost Fact
→ Asset
→ Asset Assignment
→ Employee
```

Example:

```text
vehicle insurance
→ Vehicle A
→ assigned to Employee X during interval T
→ Employee-attributable only for the valid overlap
```

Do not duplicate or rewrite the original source cost.

The Employee attribution is temporal and derived from the assignment evidence.

If an asset cost cannot be attributed to one Employee under the available evidence, it remains outside the Employee total until attribution becomes factual.

Do not invent sharing ratios.

---

## 11. Variable costs originating from bank/card data

A bank/card transaction is a source fact, not automatically an Employee Cost.

Preserve:

```text
Cash Movement
≠
Cost Attribution
```

Example:

```text
bank/card transaction
→ fuel purchase
→ Vehicle / Employee attribution if supported
→ Employee Cost only when causally attributable
```

If the source provides a real transaction/economic date, use it.

If only the cash posting date is known and the economic date is unknown, preserve the uncertainty.

Do not invent a more precise economic date.

A future better source may add stronger attribution/economic-date evidence without rewriting the original bank fact.

---

## 12. Location views are derived from Employee context

Do not make a person-specific cost a Location cost merely because reporting later needs a Location view.

Canonical fact remains:

```text
Cost
→ Employee
```

Location context is derived through the Employee's valid assignment(s).

For a reporting view where one Employee is associated with multiple Locations:

```text
if a real allocation measure exists
→ derive Location view using that measure
   e.g. actual worked time by Location

if no real measure exists
→ equal split across the Employee's valid Location assignments
```

This is a **derived reporting distribution of an already Employee-attributable cost**.

It is not an allocation of generic Personnel overhead to Employees.

Do not persist the derived Location shares as canonical cost facts.

---

## 13. Payroll boundary

`Payroll Employer Cost` is one major source/component of `Total Employee Cost`.

Canonical relationship:

```text
Payroll atomic facts
→ employer-paid earnings
→ employer-side liabilities
→ Payroll Employer Cost

Payroll Employer Cost
+ other Employee-attributable economic cost facts
→ Total Employee Cost
```

Payroll does not own all Employee Cost.

Examples outside Payroll may include:

```text
company vehicle
insurance
fuel
other Employee-specific benefits/costs
```

Do not move those concepts into Payroll solely because they affect Total Employee Cost.

---

## 14. Personnel Management boundary

Personnel Management may consume `Total Employee Cost` as evidence.

Do not implement Selection or Personnel Decisions in this task.

Document only the reason the Employee Cost model must remain causally truthful:

```text
generic shared cost that does not change when Employee A is replaced by Candidate B
must not be artificially attached to Employee A
```

Otherwise RF-One would create false comparative evidence.

The cost model supplies facts.

Personnel Management owns the later decision.

---

## 15. Replacement / transition decision costs are separate

Preserve the boundary:

```text
Employee Cost
≠
Replacement Decision Cost
```

Costs caused by the act of replacing/changing personnel do not become intrinsic historical cost of either the incumbent or candidate merely because they participate in the decision.

Examples may include:

```text
recruiting
hiring/onboarding
transition
vacancy effects
severance
```

Do not model these further in this task.

Only document the boundary if needed to prevent semantic contamination of Employee Cost.

---

## 16. Persistence principle

Strong invariant:

> Persist source facts, events, assignments, configuration, and evidence. Derive calculations.

Do not store canonical:

```text
monthly Employee cost shares
Payroll-period Employee cost shares
Location shares
Total Employee Cost aggregate
Total Personnel Cost aggregate
```

when they can be recalculated from atomic facts.

Persist actual external events when they happened, including actual Payroll results/payments.

A derived calculation may exist as ephemeral output or explicit calculation/audit run if needed later, but must not become the canonical source of truth.

---

## 17. OpenQuestions.md

The current unresolved question about whether generic Personnel cost should be allocated to Employees is now resolved.

Update root:

```text
OpenQuestions.md
```

accordingly.

The resolution is:

```text
If a cost is causally attributable to an Employee
→ Employee Cost

If it is not causally attributable
→ Unallocated Personnel Cost

No artificial Employee allocation.
```

Remove the resolved question from the active Open Questions section or move it to a concise Resolved section according to the file's current convention.

Do not add speculative new questions.

---

## 18. Documentation placement

Use the smallest clean documentation change.

Preferred:

```text
01 Domains/Administration/Personnel Cost.md
```

for the transversal concept if the current structure supports it cleanly.

Then update:

```text
01 Domains/Administration/README.md
01 Domains/Administration/Payroll/Labor Cost.md
```

so Payroll clearly supplies `Payroll Employer Cost` into the broader Personnel Cost model.

If repository conventions strongly favor another filename/location, preserve the semantic ownership:

```text
Payroll Employer Cost
⊂ Employee Cost / Personnel Cost
```

and do not make Payroll the owner of vehicle/fuel/benefit economics.

---

## 19. Software/database scope

Documentation only.

Do **not** create:

```text
new SQLAlchemy models
new tables
Alembic migrations
importers
allocation engines
bank integration
asset subsystem
benefit subsystem
Personnel Selection logic
```

The ontology must be fixed first.

A later task can implement the minimum Runtime representation once real cost sources are identified.

---

## 20. Report

Create:

```text
07 Tasks/Reports/TASK_LABOR_COST_001_REPORT.md
```

Include:

```text
A. Summary
B. Canonical Employee Cost definition
C. Causal attribution test
D. Unallocated Personnel Cost
E. Total Personnel Cost
F. Economic-cost vs cash boundary
G. Temporal coverage / calendar-day derivation
H. Asset-mediated attribution
I. Location reporting derivation
J. Payroll boundary
K. Personnel Management boundary
L. Replacement-decision boundary
M. Persistence invariant
N. OpenQuestions resolution
O. Exact documentation changed
P. Git scope confirmation
```

---

## 21. Git scope

Do not run:

```text
git add
git commit
git push
```

---

## 22. Acceptance criteria

Complete when:

- Employee Cost is defined causally;
- `Total Employee Cost` represents only genuinely Employee-attributable economic costs;
- artificial `Allocated Labor Overhead` is removed/rejected;
- `Unallocated Personnel Cost` is explicitly defined;
- `Total Personnel Cost = Σ Total Employee Cost + Unallocated Personnel Cost`;
- economic cost timing is separated from cash timing;
- multi-period costs derive from actual calendar-day overlap;
- asset assignment can mediate Employee attribution;
- derived period/month/location shares are not persisted as canonical truth;
- Location views derive from Employee assignments rather than duplicating cost ownership;
- Payroll Employer Cost is correctly positioned as one component/source of broader Employee Cost;
- generic personnel cost is not loaded onto Employees for comparison/Selection;
- replacement decision costs are explicitly outside Employee Cost;
- root `OpenQuestions.md` reflects the resolved allocation question;
- no database/software implementation is introduced;
- no git add/commit/push is run.
