# TASK_LABOR_COST_001 — Report

Formalize Employee Cost and Personnel Cost semantics: canonical `Total Employee Cost`, `Unallocated Personnel Cost`, `Total Personnel Cost`; rejection of artificial `Allocated Labor Overhead`; calendar-day-based multi-period derivation; asset-mediated attribution; Location reporting as a derived view; Payroll/Personnel Management/Replacement-decision boundaries. Documentation only.

---

## A. Summary

The prior provisional model — `Direct Employee Labor Cost + Allocated Labor Overhead = Fully Loaded Labor Cost`, recorded as an open question in `OpenQuestions.md` — is rejected. It is replaced by a single causal principle: a cost is `Employee Cost` only if it is causally attributable to that specific Employee (a counterfactual "would this cost disappear/change if this Employee didn't exist" test); otherwise it is `Unallocated Personnel Cost`, never distributed across Employees. The canonical concept `Total Employee Cost` (and, at the organizational level, `Total Personnel Cost = Σ Total Employee Cost + Unallocated Personnel Cost`) is now defined in a new Administration-level document, `01 Domains/Administration/Personnel Cost.md`. `Payroll Employer Cost` (`Payroll/Labor Cost.md`) is repositioned as one component/source of that broader model rather than the whole of it; `Fully Loaded Labor Cost` survives only as a non-canonical legacy synonym. `OpenQuestions.md`'s allocation question is resolved and moved to a `Resolved` section. No software, schema, or Runtime change was made.

---

## B. Canonical Employee Cost definition

`Total Employee Cost` = the total economic cost causally attributable to one specific Employee for a defined analysis period, derived from atomic cost facts and temporal attribution evidence — never persisted as a canonical aggregate. Defined in `Personnel Cost.md` §2. `Fully Loaded Labor Cost` (`Payroll/Labor Cost.md`) is retained only as its non-canonical/legacy/business synonym and is explicitly stated to never imply arbitrary shared-overhead loading.

The rejected model (`Direct Employee Labor Cost + Allocated Labor Overhead`) and the `Allocated Labor Overhead` concept itself are documented as rejected, with the reasoning: a genuinely attributable cost is already an Employee cost under the causal test; a non-attributable cost, if forced onto Employees, creates false economic evidence (`Personnel Cost.md` §2).

---

## C. Causal attribution test

```text
If Employee X did not exist / were not in that employment relationship,
would this cost disappear or change in an identifiable way?

YES → Employee-attributable cost
NO / UNKNOWN → not an Employee cost
```

Documented as the primary semantic boundary in `Personnel Cost.md` §1, with the same illustrative (non-closed) example list as the task specification (wages, salary, overtime, bonus, employer-side payroll liabilities, employee-specific benefits, assigned vehicle/insurance/fuel, per-Employee licenses).

---

## D. Unallocated Personnel Cost

Defined in `Personnel Cost.md` §3 as a real personnel-related economic cost that cannot currently be causally attributed to any specific Employee. Never distributed across Employees to make per-Employee totals reconcile; may be reclassified later only as a new fact when genuine causal attribution evidence appears, never as a retroactive rewrite of the original cost fact.

---

## E. Total Personnel Cost

```text
Total Personnel Cost = Σ Total Employee Cost + Unallocated Personnel Cost
```

Defined in `Personnel Cost.md` §4, for a given organizational scope and analysis period, explicitly preserving both company-wide personnel economics and truthful per-Employee economics.

---

## F. Economic-cost vs. cash boundary

`Personnel Cost.md` §5 preserves `Economic Cost ≠ Cash Movement` (December-earned/January-paid bonus example) and extends the same boundary to bank/card-sourced facts (`Cash Movement ≠ Cost Attribution`): a transaction is a source fact, attributable only when causal evidence supports it; an unknown economic date is preserved as uncertainty, never invented. No Cash Flow model is implemented — semantic boundary only, per task scope.

---

## G. Temporal coverage / calendar-day derivation

`Personnel Cost.md` §6 requires persisting atomic facts (amount, `coverage_start`/`coverage_end`, attribution evidence, assignment interval) and deriving the Employee-attributable portion of a multi-period cost from **actual calendar-day overlap** between coverage and assignment intervals — never a 30-day month, 360-day year, or synthetic equal months, reproducing the task's insurance/vehicle-assignment worked example. Derived monthly/period shares are calculations, never stored truth.

---

## H. Asset-mediated attribution

`Personnel Cost.md` §7 documents the canonical path `Cost Fact → Asset → Asset Assignment → Employee`, with the vehicle-insurance example from the task, calendar-day overlap governing the attributable portion, and no invented sharing ratio when attribution isn't factual. `Asset`/`Asset Assignment` are documented as an attribution *pattern* here, not a modeled entity — no schema is introduced (task §19); a future task would define them once a real asset-cost source is integrated.

---

## I. Location reporting derivation

`Personnel Cost.md` §9: the canonical fact remains `Cost → Employee`; Location context is derived through the Employee's valid Location assignment(s) (e.g. `Restaurant/Organization/Employee Assignment.md` in the Restaurant Domain). A real allocation measure (e.g. actual worked time by Location) is preferred; equal split across valid Location assignments is used only for the derived reporting view when no real measure exists, and is explicitly distinguished from the rejected `Allocated Labor Overhead` (an allocation of an *already Employee-attributable* cost across Locations, not an allocation of generic overhead across Employees). Derived Location shares are never persisted.

---

## J. Payroll boundary

`Personnel Cost.md` §10 and the revised `Payroll/Labor Cost.md` state `Payroll Employer Cost + other Employee-attributable cost facts → Total Employee Cost`; Payroll does not own all Employee Cost, and vehicle/insurance/fuel/benefit concepts are not moved into Payroll merely because they affect `Total Employee Cost`. `Payroll/README.md`'s file table and Related-documents section now point to `Personnel Cost.md` as the concept `Payroll Employer Cost` feeds into.

---

## K. Personnel Management boundary

`Personnel Cost.md` §11 documents that Personnel Management may consume `Total Employee Cost` as decision evidence without Personnel Cost making the decision, and states explicitly why causal truthfulness matters here: a generic shared cost that would not change if Employee A were replaced by Candidate B must never be artificially attached to Employee A, or any Selection/Personnel Decision comparison built on it would be false. No Selection/Personnel Decision logic was modeled.

---

## L. Replacement-decision boundary

`Personnel Cost.md` §12 states `Employee Cost ≠ Replacement Decision Cost`: recruiting, hiring/onboarding, transition, vacancy effects, and severance belong to the Personnel Decision that caused them, never to the incumbent's or candidate's historical `Total Employee Cost`. Documented as a boundary only, not further modeled.

---

## M. Persistence invariant

`Personnel Cost.md` §8 restates the strong invariant (persist source facts, events, assignments, configuration, evidence; derive calculations) and lists the specific aggregates never persisted as canonical: monthly/Payroll-period Employee cost shares, Location shares, `Total Employee Cost`, `Total Personnel Cost`. Consistent with the pre-existing persistence discipline already established in `Payroll/Labor Cost.md` for `Payroll Employer Cost`.

---

## N. OpenQuestions resolution

`OpenQuestions.md`'s prior `## Labor Cost` / `### 1. Unallocated Labor Cost` question (whether/when an `Allocated Labor Overhead` rule is permitted) is removed from the active section and replaced by `## Resolved` / `### 1. Whether generic Personnel cost may be allocated to Employees — RESOLVED (TASK_LABOR_COST_001)`, stating the resolution rule and pointing to `Personnel Cost.md` as the canonical definition, per the file's own existing "Resolution rule" convention. No speculative new question was added.

---

## O. Exact documentation changed

**Created:**

```text
01 Domains/Administration/Personnel Cost.md
07 Tasks/Reports/TASK_LABOR_COST_001_REPORT.md
```

**Modified:**

```text
01 Domains/Administration/README.md          (module map: added Personnel Cost.md as
                                                Domain-level concept; Related documents)
01 Domains/Administration/Payroll/README.md   (Labor Cost.md file-table description and
                                                Related documents now point to Personnel Cost.md)
01 Domains/Administration/Payroll/Labor Cost.md (Fully Loaded Labor Cost section rewritten
                                                as legacy synonym for Total Employee Cost;
                                                Business Rules bullet updated)
01 Domains/README.md                          (Administration Domain description updated
                                                to reflect Personnel Cost as the canonical
                                                cost model, Payroll as one source)
OpenQuestions.md                              (allocation question resolved and moved to a
                                                Resolved section)
```

No file outside `01 Domains/Administration/`, `01 Domains/README.md`, `OpenQuestions.md`, and this report was modified. No database model, table, migration, importer, allocation engine, bank integration, asset subsystem, benefit subsystem, or Personnel Selection logic was created.

---

## P. Git scope confirmation

No `git add`, `git commit`, or `git push` was run at any point during this task.

---

## Unresolved issues / questions for the Product Owner

None required to complete this task. Two natural follow-ups are noted for future tasks, not raised as blockers:

1. When RF-One acquires a real Employee-attributable cost source outside Payroll (company vehicle, benefit, equipment), a future task should define the minimal `Asset`/`Asset Assignment` Runtime representation referenced conceptually in `Personnel Cost.md` §7.
2. When a multi-Location reporting need becomes concrete, a future task should confirm which real allocation measure (e.g. worked time by Location) is available before falling back to the equal-split derived view in `Personnel Cost.md` §9.
