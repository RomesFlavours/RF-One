# Workforce

**Version:** 0.1
**Status:** Placeholder (module boundary only — no concept modeling)
**Module:** Domain / Personnel Management / Workforce

---

## Purpose

Workforce represents the organization's current human structure: who currently occupies, or can occupy, organizational roles.

> Workforce describes who currently occupies or can occupy organizational roles.

---

## Module boundary

Workforce answers **"who"** — the structural question of current occupancy. It is distinct from the other Personnel Management modules:

- [Selection](../Selection/README.md) answers "who else is a credible alternative";
- [Training](../Training/README.md) answers "how do we close an evidenced gap";
- [Performance](../Performance/README.md) answers "what did the person actually produce";
- [Personnel Decisions](../Personnel%20Decisions/README.md) answers "what should be done about the person currently in the role."

Potential future concepts include Person/Worker, Role, Position, Assignment, Responsibility, Availability, Schedule and Employment Relationship. These are not defined by this document.

---

## Relationship to other Personnel Management modules

Selection, Training, Performance and Personnel Decisions each depend on Workforce concepts (e.g. Role, Assignment) as external dependencies without this module defining them yet — the same dependency already recorded in [../Selection/README.md](../Selection/README.md), "Future Workforce dependency."

---

## Relationship to Core

Workforce will build on Core Subject, Entity, Relationship, Assignment and Ownership (see [../../../00 Core/Relationship.md](../../../00%20Core/Relationship.md), [../../../00 Core/Entity.md](../../../00%20Core/Entity.md)) without redefining them.

---

## Relationship to technical Domains

Workforce consumes role and position context from whichever technical Domain the role belongs to (e.g. Restaurant's Operational Areas and role responsibilities — see [../../Restaurant/README.md](../../Restaurant/README.md)); it does not duplicate that Domain's knowledge.

---

## Deferred

Detailed modeling of Workforce entities, relationships, business rules and data requirements is deferred to a future task.
