# Operational Area (Restaurant Organization)

**Version:** 1.0
**Status:** Approved
**Module:** Restaurant Domain / Organization
**Origin:** TASK_RESTAURANT_001
**Relates to:** `Model/OperationalArea.md` (Core-inherited specialization) — see "Relationship to `Model/OperationalArea.md`" below

---

## Definition

An **Operational Area** is a functional organizational grouping configured by a specific Restaurant.

It answers:

> In which functional part of the restaurant is this work being performed?

Examples a Restaurant might configure include `FOH`, `BOH`, `BAR`, `MANAGEMENT` — but these are illustrative, not a hard-coded universal Restaurant Domain enumeration. Every Operational Area belongs to exactly one Restaurant's configuration and is created only by an explicit Restaurant/Product-Owner configuration action.

---

## Distinct from Physical Area

Operational Area is a **functional** grouping, not a place. `Patio` is not an Operational Area; it is a `Physical Area` (see `Physical Area.md`). A given Employee's Operational Area (e.g. `FOH`) and Physical Area (e.g. `Patio`) are independent facts that may combine (an FOH Employee may work the Patio one shift and the Dining Room another), which is precisely why they are modeled as two separate concepts rather than one.

---

## Relationship to `Model/OperationalArea.md`

`Model/OperationalArea.md` defines how Core's `Operational Area` (see `00 Core/OperationalArea.md`) specializes for the Restaurant Domain in general — inherited identity, the Operational Unit membership rule, and an illustrative Area Type taxonomy (Physical / Logical / Hybrid). This document does not redefine that inheritance.

It does correct one specific overlap: `Model/OperationalArea.md`'s "Physical" Area Type (with examples Kitchen, Bar, Dining Room, Patio) described a place using the word "Area" without a separate Physical Area concept to hold it. This document's Operational Area, and the sibling `Physical Area.md`, together replace that single Area-Type axis with two independent concepts. A Restaurant configuring `FOH`/`BOH`/`BAR`/`MANAGEMENT` as Operational Areas, and `Dining Room`/`Patio`/`Kitchen` as Physical Areas, is the concrete instance of that correction.

---

## Relationships

```text
Restaurant
└── (1:N) Operational Area
             └── (M:N, via OperationalAreaRole) Restaurant Role
```

An Operational Area does not itself hold Employee Assignments — an Employee is assigned to an (Operational Area, Restaurant Role) pair via `Employee Assignment`, not to the Operational Area alone.

---

## Multi-role capability

An Operational Area is not restricted to a single Restaurant Role. A Restaurant may configure `FOH` to allow both `Host` and `Manager`, for example. See `Restaurant Role.md` for the reciprocal case (one Role valid in more than one Area) and `03 Software/RF-One Data Store/DATABASE_SCHEMA.md` §4a for the `OperationalAreaRole` M:N table that represents these allowed combinations.

---

## Hierarchy (optional)

An Operational Area may canonically have a parent Operational Area, expressing functional containment/classification (e.g. `Dining` and `Bar` under a broader `Guest Operations`) — never physical containment. Hierarchy is optional, not required; a Restaurant Profile that never sets a parent is simply one where every Operational Area is a root. See `../Restaurant Semantic Model.md` § 5.2 for the full parent-child semantics, root-Area meaning, and cycle prohibition. Not yet reflected in the runtime schema (`operational_areas` has no `parent_id`) — documented as future work, not a current contradiction, since no Restaurant Profile is configured yet to need it.

## Business Rules

- Every Operational Area belongs to exactly one Restaurant.
- Operational Area names/values are Restaurant configuration, never a hard-coded universal enum.
- An Operational Area may allow more than one Restaurant Role (M:N via `OperationalAreaRole`).
- `OperationalAreaRole` defines what combination is *possible*; it is not the Employee assignment itself — see `Employee Assignment.md`.
- No Operational Area is inferred from a Clover named Role (see `README.md`, "Relationship to Clover source semantics").
