# RF-One Tasks

## Purpose

`07 Tasks/` holds the **active** task workspace: currently active task specifications, active execution reports awaiting Product Owner review/commit, and active backlog/planning material.

Once a task's outcome has been reviewed and committed, its specification and report are moved out of this active workspace into `90 Archive/Task History/` — see below.

---

# Authority

Tasks record **why and how** changes were made, but they do not replace current canonical Core/Domain/Product/Strategy documentation. When a Task result conflicts with what a canonical document currently says, the canonical document is authoritative — the Task is historical record of a decision, not a live specification.

A historical Task may legitimately contain paths or claims that were true when it ran and are no longer current; that is expected and is not an error to silently "fix."

---

# Structure

| Location | Purpose |
|---|---|
| `07 Tasks/*.md` | Currently active task specifications (e.g. `TASK_CORE_011_...md`), kept directly under `07 Tasks/`. |
| `07 Tasks/Reports/` | Active execution reports, produced after completing a task and awaiting Product Owner review/commit (e.g. `TASK_CORE_011_REPORT.md`). |
| `07 Tasks/Backlog/` | Binding, Product-Owner-approved backlogs that track follow-up work without themselves being canonical architecture (e.g. `LEGACY_KNOWLEDGE_RECONCILIATION_BACKLOG.md`). |

# What belongs here

- Currently active task specifications, their active execution reports, and approved backlogs.

# What does not belong here

- Canonical architecture itself — a Task may propose or record a change, but the change lives in `00 Core/`, `01 Domains/`, `02 Products/` or `09 Strategy/` once approved and implemented.
- Completed, reviewed/committed historical task specifications and reports — those are archived under `90 Archive/Task History/` (see `90 Archive/Task History/README.md`), which is historical/non-authoritative provenance material.
