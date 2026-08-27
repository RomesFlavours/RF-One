# Restaurant Organization

**Version:** 1.0
**Status:** Approved
**Module:** Restaurant Domain / Organization
**Origin:** TASK_RESTAURANT_001

---

## Purpose

This section defines the canonical **Restaurant Profile**: the organizational context a Restaurant configures for itself — its identity, its functional Operational Areas, its Physical Areas, the Restaurant Roles it recognizes, and how Employees are temporally assigned into that structure.

It exists because future capabilities — Tips, Payroll, Scheduling, Performance, Training, Sales analysis — all need to answer the same underlying question, and none of them should answer it independently or infer it from POS source data:

> For a given Employee, at a given moment, which functional part of the restaurant were they working in, and in what capacity?

**For the canonical, configuration-independent semantics behind this section** — the Domain-vs-Profile-vs-Instance distinction, Operational Area/Physical Area hierarchy semantics, and the consolidated invariant list — see [../Restaurant Semantic Model.md](../Restaurant%20Semantic%20Model.md) (TASK_RESTAURANT_002). This section (`Organization/`) documents each concept and its implementation in depth; the Semantic Model document is the authoritative statement of the principle that a Restaurant's naming/granularity choices are free as long as they preserve each canonical concept's meaning.

---

## Files in this section

| File | Concept |
|---|---|
| [Restaurant Profile.md](Restaurant%20Profile.md) | Restaurant identity and its relationship to Location |
| [Operational Area.md](Operational%20Area.md) | Functional organizational grouping (e.g. FOH, BOH) |
| [Physical Area.md](Physical%20Area.md) | Physical place/zone (e.g. Dining Room, Patio) |
| [Restaurant Role.md](Restaurant%20Role.md) | Canonical operational role performed by a person |
| [Employee Assignment.md](Employee%20Assignment.md) | Temporally bounded Employee ↔ Area ↔ Role fact |

---

## Relationship to the existing Restaurant business-profile model

`01 Domains/Restaurant/Model/OU-Restaurant.md` and `01 Domains/Restaurant/Model/OperationalArea.md` already document Restaurant as a specialization of Core `Operational Unit`, and Restaurant's Operational Area as a specialization of Core `Operational Area`, within the `Corporate → Brand → Operational Unit → Operational Area` hierarchy. This section does not replace or redefine that content.

The two sections answer different questions:

```text
Model/OU-Restaurant.md, Model/OperationalArea.md
→ where Restaurant and Operational Area sit in RF-One's Corporate/Brand/
  Operational Unit hierarchy; what a Restaurant inherits from Operational
  Unit; broad Area Type taxonomy (Physical / Logical / Hybrid)

Organization/ (this section)
→ the concrete, Restaurant-configured profile actually implemented in the
  RF-One Data Store: named Operational Areas, named Physical Areas, named
  Restaurant Roles, which Role/Area combinations are allowed, and the
  temporal Employee Assignment fact that ties an Employee to a specific
  Area/Role over a specific time interval
```

**One genuine refinement is introduced here and should be read as updating, not duplicating, `Model/OperationalArea.md`:** that document currently lists "Physical" as one of three Area Types (Physical / Logical / Hybrid) of Operational Area itself, with examples (Kitchen, Bar, Dining Room, Patio) that conflate a functional grouping with a physical place. This section makes that distinction explicit and structural — see [Operational Area.md](Operational%20Area.md) and [Physical Area.md](Physical%20Area.md) — an Operational Area (e.g. FOH) and a Physical Area (e.g. Patio) are independent concepts, and an Operational Area is never typed as "Physical" to mean a place. A short note has been added to `Model/OperationalArea.md` cross-referencing this section; its Core-inherited content and approval status are otherwise unchanged.

---

## Relationship to Clover source semantics

Nothing in this section is derived automatically from Clover. In particular:

```text
Clover named Role (SourceRole, e.g. "Server", "Host", "Admin", "BOH")
≠
RF-One Restaurant Role

Clover systemRole (Employee.system_role, e.g. EMPLOYEE/MANAGER/ADMIN)
≠
RF-One Restaurant Role

Clover Role
does not imply
RF-One Operational Area
```

`SourceRole` (documented in `03 Software/RF-One Data Store/DATABASE_SCHEMA.md` §4, TASK_CLOVER_004/TASK_DATABASE_003) is source evidence only — the Clover Role actually assigned to an Employee in the Clover UI. It remains a legitimate future input to a Product-Owner-configured mapping (`assignment_source = SOURCE_ROLE_MAPPING`), but such a mapping is a controlled configuration action, never an automatic inference.

### Profile bootstrap from source configuration (TASK_RESTAURANT_003)

A source system's current configuration (Clover's, so far) may be used as evidence to instantiate a specific Restaurant's Profile, but only through an explicit, auditable, Restaurant-scoped mapping layer, never an automatic ontology equivalence — `SourceRole ≠ RestaurantRole` remains true even when a Restaurant's initial configured `RestaurantRole` name is chosen to match a `SourceRole` name exactly. Bootstrapping such a Profile establishes an explicit `T0`: the moment RF-One begins managing that Restaurant's Profile prospectively. No historical truth is inferred before `T0` — a Restaurant's role history prior to that point is out of scope, per explicit Product Owner direction — and every future source configuration change (an Employee's Clover Role changing) creates new temporal `EmployeeAssignment` history rather than overwriting the old. Where the source provides no reliable structured functional-area evidence, a single minimal root Operational Area may be used instead of inferring `FOH`/`BOH`/`Bar`/`Kitchen`/etc. from Role names — this is documented minimal granularity, not a claim the Restaurant lacks internal functional areas. Congruence problems between the source and the instantiated Profile (an Employee with no current Role, a Role with no mapping, and similar) are surfaced explicitly, never silently corrected. See `03 Software/RF-One Data Store/RESTAURANT_PROFILE.md` § 6 for the full algorithmic contract and `03 Software/RF-One Data Store/DATABASE_SCHEMA.md` § 4c for the implemented schema.

---

## Relationship to Personnel Management

Personnel Management (`01 Domains/Personnel Management/`) owns broader workforce/personnel semantics that apply across industries — Workforce, Selection, Training, Performance, Personnel Decisions. This section does not duplicate that.

Restaurant Organization owns:

```text
restaurant-specific organizational context
operational areas
physical areas
restaurant roles
restaurant assignment context (Employee Assignment)
```

Personnel Management consumes this Restaurant-specific technical content (e.g. "this person's Restaurant Role and Operational Area during the evaluated period") the same way it consumes any other technical Domain's content, per `01 Domains/Personnel Management/README.md`, "Relationship to technical Domains" — it does not redefine Employee Assignment, Operational Area, Physical Area or Restaurant Role.

---

## Related documents

- [../README.md](../README.md) — Restaurant Domain purpose and scope
- [../Roadmap.md](../Roadmap.md) — Restaurant Domain knowledge coverage
- [../Model/OU-Restaurant.md](../Model/OU-Restaurant.md), [../Model/OperationalArea.md](../Model/OperationalArea.md) — Core-inherited business-profile model
- [../../Personnel Management/README.md](../../Personnel%20Management/README.md) — Personnel Management boundary
- `03 Software/RF-One Data Store/RESTAURANT_PROFILE.md` — runtime/database implementation of this section, including the future Tips/Payroll contract
- `03 Software/RF-One Data Store/DATABASE_SCHEMA.md` §4a — physical schema for `restaurants`, `restaurant_locations`, `operational_areas`, `physical_areas`, `restaurant_roles`, `operational_area_roles`, `employee_assignments`
