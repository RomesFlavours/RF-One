# RF-One Archive

## Purpose

`90 Archive/` holds historical/non-authoritative material.

---

# Authority

> **Nothing under `90 Archive/` is current canonical RF-One authority, regardless of historical `Approved` or similar status text inside archived documents.**

An archived document may say "Status: Approved" internally — that status reflected its authority at the time it was written, before Core 2.0 and the canonical repository migration. It does **not** mean the document is currently authoritative. Authority is determined by **location** (is it under `00 Core/`, `01 Domains/`, `02 Products/`, or `09 Strategy/`?), not by text inside the file.

Developers and AI agents must never treat a document under `90 Archive/` as defining current Core, Domain, Product or Strategy meaning. If archived material appears valuable, it must go through explicit reconciliation and be incorporated into a canonical location before it can be relied upon.

---

# What belongs here

- Superseded or historical repository structures and documentation.
- Legacy material preserved for its historical/conceptual value, per Product Owner instruction to retain rather than delete.

# What does not belong here

- Anything still in current use — that belongs in its proper canonical layer.

---

# Current contents

| Location | Description |
|---|---|
| `Legacy Repository/X00 Knowledge Repository/` | The full pre-Core-2.0 knowledge repository, preserved with its original internal hierarchy (`00 Vision/` … `09 Interviews/`). Moved here by `90 Archive/Task History/Tasks/TASK_CORE_005_Canonical_Repository_Migration.md` after the legacy-reconciliation review (`90 Archive/Task History/Tasks/TASK_CORE_004_Legacy_Knowledge_Reconciliation_Review.md`) and the approved backlog at `07 Tasks/Backlog/LEGACY_KNOWLEDGE_RECONCILIATION_BACKLOG.md`. |
| `Task History/` | Completed RF-One task specifications and execution reports, moved out of the active `07 Tasks/` workspace once reviewed and committed. Historical/non-authoritative, per `90 Archive/Task History/README.md`. |

Files under `Legacy Repository/` are preserved unmodified in their original relative context and should remain unmodified whenever possible.
