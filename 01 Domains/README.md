# RF-One Domains

## Purpose

`01 Domains/` holds canonical knowledge for reusable Application Domains built on top of the RF-One Core.

A Domain applies and, where necessary, specializes Core concepts (Subject, Reality, Desire, Goal, Decision, Entity, Relationship, Process, and others — see `00 Core/`) for a specific field, without redefining what those concepts mean.

See [Domain Architecture.md](Domain%20Architecture.md) for the current cross-Domain conclusions on the Restaurant boundary, the transversal Domain **Personnel Management** (with modules Workforce, Selection, Training, Performance, Personnel Decisions), and the remaining transversal Domain candidates (Customer Feedback, Review).

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
| `Restaurant/` | Business knowledge required to model, operate and continuously improve a restaurant. See `Restaurant/README.md` and `Restaurant/Roadmap.md`. |
| `Personnel Management/` | Transversal Domain for managing people across industries, built on Core 2.0. Restaurant and other technical Domains are its application contexts, not its architectural owner. See `Personnel Management/README.md`. Its modules are Workforce, Selection, Training, Performance and Personnel Decisions; Selection is the only module documented in depth so far (`Personnel Management/Selection/README.md`, migrated from the former top-level `Selection/` Domain). |
| `_Shared/` | Domain-independent-but-not-universal shared knowledge reused across multiple Domains (currently `Environment/`). |

A Domain should not automatically equal a Product. Future transversal Domain candidates (e.g. Customer Feedback, Review) are anticipated by [Domain Architecture.md](Domain%20Architecture.md) but are not created by this migration.

---

# Business capability is not automatically a Domain

RF-One's commercial ambition may span many business capability areas — financial performance, sales, marketing, personnel, and more. A capability or coverage area existing in a historical planning taxonomy, in `CLAUDE.md`'s Domain examples, or in commercial strategy does **not** by itself make it a modern architectural Domain.

The historical `Knowledge Domains` taxonomy inherited from the legacy repository (`90 Archive/Legacy Repository/X00 Knowledge Repository/05 Knowledge Domains/README.md`) was a business knowledge/capability/coverage planning list, not the current architectural definition of Domain. It has been reconciled and classified area-by-area in `09 Strategy/04_Business_Capability_Coverage.md`; some of its areas belong to Restaurant (see `Restaurant/Roadmap.md`), some are Shared Domain candidates (not yet created), and others are Strategy, Product, or Software capability rather than Domain knowledge at all.

`_Shared/` may host reusable business/environment knowledge once a concept is shown to genuinely apply across multiple Domains, not merely because it was listed in a legacy taxonomy or seems generically useful.
