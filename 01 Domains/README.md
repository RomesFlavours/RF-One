# RF-One Domains

## Purpose

`01 Domains/` holds canonical knowledge for reusable Application Domains built on top of the RF-One Core.

A Domain applies and, where necessary, specializes Core concepts (Subject, Reality, Desire, Goal, Decision, Entity, Relationship, Process, and others — see `00 Core/`) for a specific field, without redefining what those concepts mean.

---

# Authority

Each Domain is **canonical for its own field**, subject to the Core it is built on. Domain knowledge does not redefine universal Core concepts, and does not override Core principles.

A Domain must use only the Core concepts it actually requires — a concept existing in Core does not obligate every Domain to use it.

---

# What belongs here

- Business knowledge, entities, relationships and business rules specific to one reusable field of activity (e.g. `Restaurant/`).
- Domain-level specializations of Core concepts (e.g. a Domain's own `Operational Unit` specialization).
- Shared knowledge reused across multiple Domains, under `_Shared/` (e.g. `_Shared/Environment/` — geography, legal, fiscal, regulatory and standards context).

# What does not belong here

- Universal, domain-independent ontology — that belongs in `00 Core/`.
- Commercial/Product configurations that combine Domains for a specific customer offering — that belongs in `02 Products/`.
- RF-One's own commercial strategy as a company — that belongs in `09 Strategy/`.
- Runtime implementation/software behavior — that belongs in `03 Software/`.

---

# Current Domains

| Domain | Description |
|---|---|
| `Restaurant/` | Business knowledge required to model, operate and continuously improve a restaurant. See `Restaurant/README.md`. |
| `_Shared/` | Domain-independent-but-not-universal shared knowledge reused across multiple Domains (currently `Environment/`). |

A Domain should not automatically equal a Product. Future Domains (e.g. Workforce, Selection, Training) are anticipated by `CLAUDE.md` but are not created by this migration.
