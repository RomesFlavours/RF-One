# Project Manager

**Version:** 0.2 — 2026-10-25
**Status:** Component of the Management Shared Domain. **Approved by the Product Owner (2026-10-25):** Project Manager's mandate — planning, execution and verification of approved assignments (§1). The execution controls below keep their source status: functional reference, requiring practical specification.
**Module:** Domain / Management (Shared Domain) / Project Manager
**Sources:** M03 §§5–6, 8–10; C01 points 4–6, 9; O04 §4; P01 §§6, 10 (see [../SOURCES.md](../SOURCES.md)).

---

## 1. Mandate and scope

Project Manager plans, executes and verifies **approved assignments**. It supports ordinary/recurring processes, relevant unplanned work and finite projects, and guides responsible people through planning, execution and outcome verification. It reuses Organization's approved procedures and work structure ([../Organization/README.md](../Organization/README.md)). It does not assume a centralized management-controller function or make Pino the routine digital supervisor.

## 2. Relationship with MyRF Project Management

An approved, implemented tool already exists: **MyRF — Project Management (v1, minimal)**, "v1 approved by the Product Owner (2026-10-12)", access code `PROJECTS`, documented at `01 Domains/Business Domain/Restaurant/MyRF/Project Management/README.md`.

> **Branch note:** that document and its implementation exist on `origin/main` (and the `feature/project-management*` branches), **not in this checkout** (`handoff/2026-10-17`). It is referenced here by path, not linked, and was not modified or copied by this reorganization.

The two are kept distinct; neither replaces the other:

| | Project Manager (this component) | MyRF Project Management v1 |
|---|---|---|
| Nature | Management mandate: what planning, execution and verification of approved work must guarantee | The approved, implemented **presentation and tool in MyRF** through which a person records and reads a plan |
| Status | Mandate approved 2026-10-25; controls (§3–§7) proposed | v1 approved 2026-10-12; implemented in RF-One Web |
| Content | Assignment approval, plan approval, spending and checking, decision log, execution evidence, outcome verification | Projects, Chapters, Tasks, child activities, prerequisites, manual dates/percentages, Gantt and print, optional Task Responsible |
| Responsible person | The approved responsible person of an approved assignment (Organization §3, §9) | "Only a name": not linked to accounts, Employees or any person record; grants no access |
| Task vs Process | An execution links to its procedure/version | A Task is a unit of planned work, explicitly **not** the Core concept *Process* |

The MyRF v1 tool is a first, manual means of planning and recording progress within this mandate. It does not implement the two approvals, spending checks, decision log or outcome verification described below, and nothing here changes its approved scope, rules, data or access. MyRF Project Management describes itself as living under the Restaurant Business Domain "only because MyRF does today"; whether and how it should later be documented as the MyRF presentation of this Shared Domain component, and whether its Responsible should link to Position, Employee or Account, are open questions (G30, G31).

## 3. Two distinct approvals

1. **Assignment approval:** approved process/project responsibility and initial work structure appear in the responsible person's MyRF list and Project Manager.
2. **Plan approval:** the responsible person, assisted by AI, develops activities, sequence, priorities, timing, resources and success criteria, then requests approval.

An assignment-list entry does not authorize execution of the entire plan or spending beyond approved limits (M03 §5.1). Approver identity, authority scope and approval-change handling are unresolved. Do not invent a workflow state machine.

## 4. Spending and checking

| Rule | Status in M03 §5.2 |
|---|---|
| Identifiable approval before spending is committed | REPORTED-AGREED, classified as Legacy by source |
| No self-approval or self-check of spending | REPORTED-AGREED |
| Another person checks each person's purchases, crosswise between leads | REPORTED-AGREED company configuration |
| Written approval states item, model/size, quantity, price, purpose and stock already held | REPORTED-AGREED 20 October, company configuration |
| Timing of purchase checks, before or after | OPEN |

Approval limits and approvers are company configuration. Restaurant defaults may be offered, never assumed to be active authority. No actual thresholds are specified here. Reconcile "check before, not after" in L02 with the explicitly open timing in M03 before implementing a purchase check (G17).

## 5. Decision log

M03 §5.3 requires who decided, when, stage (**thinking, proposal, decision**) and who follows up. A changed decision records reason and owner's agreement. Those affected can consult it, subject to unresolved visibility rules. Earlier O02 also mentions an "Operational Rule" stage; do not silently add it to M03's stage set (G18).

## 6. Execution and evidence

**Agreed commitment → work performed → deliverable produced → outcome verified → deviations and causes.**

AI reuses available information, asks for missing information, identifies blockers/dependencies, routes requests to competent authority and verifies results. A closed task is not necessarily an achieved objective. Withheld approvals or missing resources must be attributed accurately.

An execution links to its procedure/version. Recurring replenishment/checks do not automatically create a new project each time. Outcome evidence informs [People](../People/README.md) and Organization without automatically rewriting approved roles or rules, and without becoming People assessment evidence automatically. People observation confidentiality still applies to task-specific observations.

## 7. Pending controls and pilot

M03 §5.5 explicitly defers checkpoints, autonomy thresholds, task approvals, warning recipients, escalation lists and reporting. Industry escalation examples are not configured company policy. The system attention-routing foundation supplies possible shared mechanisms but does not approve Management policies or deliver MyRF notifications by itself.

M03 §5.6/C01 point 9 **propose** the 30-day trial as the first live test, using Procedure 001 and 33 scenarios as acceptance criteria. A Procedure 001 Draft 0.3 file is only located and fingerprinted in the source manifest; scenarios v1.1 were not located; no pilot or acceptance success is asserted (G16, G19).

## 8. Related documents

- [../README.md](../README.md) — Management Shared Domain
- [../Organization/README.md](../Organization/README.md), [../People/README.md](../People/README.md) — sibling components
- [../CONFIGURATION_AND_MYRF.md](../CONFIGURATION_AND_MYRF.md) — MyRF list and configuration proposals
- [../DECISIONS_AND_GAPS.md](../DECISIONS_AND_GAPS.md) — open questions G16–G19, G30–G31
- `01 Domains/Business Domain/Restaurant/MyRF/Project Management/README.md` — MyRF Project Management v1 (on `origin/main`, not in this checkout)
