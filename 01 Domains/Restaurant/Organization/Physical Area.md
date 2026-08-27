# Physical Area (Restaurant Organization)

**Version:** 1.0
**Status:** Approved
**Module:** Restaurant Domain / Organization
**Origin:** TASK_RESTAURANT_001

---

## Definition

A **Physical Area** is a physical place or zone configured by a specific Restaurant.

It answers:

> Where physically is activity occurring?

Examples a Restaurant might configure include `Dining Room`, `Patio`, `Bar Counter`, `Kitchen`, `Private Room` — illustrative, not a hard-coded universal enumeration. Every Physical Area belongs to exactly one Restaurant's configuration.

---

## Distinct from Operational Area

See `Operational Area.md` for the full reasoning. In short: Physical Area is about *where*, Operational Area is about *which functional part of the business*. The same Employee, the same shift, may have a stable Operational Area (`FOH`) while working a different Physical Area from one shift to the next (`Dining Room` one day, `Patio` the next) — collapsing the two into one concept would make that ordinary case unrepresentable without rewriting history.

---

## Distinct from Physical Table

A `Physical Area` is not a `PhysicalTable` (see `01 Domains/Restaurant/Sales/Restaurant Sales Model.md` §3 and `03 Software/RF-One Data Store/DATABASE_SCHEMA.md` §3). `PhysicalTable` is a single persistent restaurant resource (a specific table); `Physical Area` is the zone that one or more Physical Tables may sit within.

A `PhysicalTable` may optionally resolve to a `Physical Area` via a nullable `physical_area_id` — added by this task to the existing `physical_tables` schema (`03 Software/RF-One Data Store/DATABASE_SCHEMA.md` §3). No `PhysicalTable` row is invented by this task to populate that link; the current RF-One data has zero `PhysicalTable` rows (Clover exposes no structured Table entity — TASK_CLOVER_003 §F), so this remains a structural capability only, not populated data.

---

## Relationships

```text
Restaurant
└── (1:N) Physical Area
             └── (0:N, optional) Physical Table
```

Employee Assignment may optionally reference a Physical Area (`Employee Assignment.md`), but only where a stable physical-area assignment is genuinely meaningful — never forced when physical working location is expected to vary shift by shift (task §17).

---

## Hierarchy (optional)

A Physical Area may canonically have a parent Physical Area, expressing physical containment (e.g. `Main Dining Room` and `Patio` under a broader `Dining Floor`) — never functional/operational classification. Hierarchy is optional. See `../Restaurant Semantic Model.md` § 6.2 for the full parent-child semantics, root-Area meaning, and cycle prohibition. Not yet reflected in the runtime schema (`physical_areas` has no `parent_id`) — documented as future work, not a current contradiction.

## Business Rules

- Every Physical Area belongs to exactly one Restaurant.
- Physical Area names/values are Restaurant configuration, never a hard-coded universal enum.
- A Physical Table may optionally sit within one Physical Area; no Physical Table row is fabricated to establish this link.
- Physical Area is never conflated with Operational Area, even where a name might coincide in casual speech (e.g. "the bar" as both a Physical Area and, potentially, part of an Operational Area's remit).
