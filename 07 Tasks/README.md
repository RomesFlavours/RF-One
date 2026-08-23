# RF-One Tasks

## Purpose

`07 Tasks/` holds approved work instructions, implementation history, Product Owner decisions, execution reports, and the legacy-reconciliation backlog.

---

# Authority

Tasks record **why and how** changes were made, but they do not replace current canonical Core/Domain/Product/Strategy documentation. When a Task result conflicts with what a canonical document currently says, the canonical document is authoritative — the Task is historical record of a decision, not a live specification.

A historical Task may legitimately contain paths or claims that were true when it ran and are no longer current; that is expected and is not an error to silently "fix."

---

# Structure

| Location | Purpose |
|---|---|
| `07 Tasks/*.md` | Task specifications themselves (e.g. `TASK_CORE_001_...md`), kept directly under `07 Tasks/`. |
| `07 Tasks/Reports/` | Execution reports produced after completing a Task (e.g. `TASK_CORE_005_REPORT.md`). |
| `07 Tasks/Backlog/` | Binding, Product-Owner-approved backlogs that track follow-up work without themselves being canonical architecture (e.g. `LEGACY_KNOWLEDGE_RECONCILIATION_BACKLOG.md`). |

# What belongs here

- Task specifications, their execution reports, and approved backlogs.

# What does not belong here

- Canonical architecture itself — a Task may propose or record a change, but the change lives in `00 Core/`, `01 Domains/`, `02 Products/` or `09 Strategy/` once approved and implemented.
