# Workforce

**Version:** 0.1
**Status:** Placeholder (module boundary only — no concept modeling)
**Module:** Domain / Personnel Management (Shared Domain) / Workforce

---

## Purpose

Workforce represents the organization's current human structure: who currently occupies, or can occupy, organizational roles.

> Workforce describes who currently occupies or can occupy organizational roles.

---

## Module boundary

Workforce answers **"who"** — the structural question of current occupancy. It is distinct from Personnel Management's other module and from the sibling Selection/Continuous Productivity Development/Performance Shared Domains:

- [Selection](../../Selection/README.md) (sibling Shared Domain) answers "who else is a credible alternative";
- [Continuous Productivity Development](../../Continuous%20Productivity%20Development/README.md) (sibling Shared Domain) answers "how do we close an evidenced gap or capture an opportunity";
- [Performance](../../Performance/README.md) (sibling Shared Domain) answers "what did the person actually produce";
- [Personnel Decisions](../Personnel%20Decisions/README.md) (the other Personnel Management module) answers "what should be done about the person currently in the role."

Potential future concepts include Person/Worker, Role, Position, Assignment, Responsibility, Availability, Schedule and Employment Relationship. These are not defined by this document.

---

## Relationship to Personnel Decisions, Selection, Continuous Productivity Development and Performance

Personnel Decisions (the other Personnel Management module) and the sibling Selection, Continuous Productivity Development and Performance Shared Domains each depend on Workforce concepts (e.g. Role, Assignment) as external dependencies without this module defining them yet — the same dependency already recorded in [../Selection/README.md](../../Selection/README.md), "Future Workforce dependency."

---

## Relationship to Core

Workforce will build on Core Subject, Entity, Relationship, Assignment and Ownership (see [../../../00 Core/Relationship.md](../../../../00%20Core/Relationship.md), [../../../00 Core/Entity.md](../../../../00%20Core/Entity.md)) without redefining them.

---

## Relationship to technical Domains

Workforce consumes role and position context from whichever technical Domain the role belongs to (e.g. Restaurant's Operational Areas and role responsibilities — see [../../Restaurant/README.md](../../../Business%20Domain/Restaurant/README.md)); it does not duplicate that Domain's knowledge.

---

## Deferred

Detailed modeling of Workforce entities, relationships, business rules and data requirements is deferred to a future task.
