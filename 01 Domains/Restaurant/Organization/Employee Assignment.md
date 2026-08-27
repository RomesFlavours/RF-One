# Employee Assignment

**Version:** 1.0
**Status:** Approved
**Module:** Restaurant Domain / Organization
**Origin:** TASK_RESTAURANT_001

---

## Definition

An **Employee Assignment** is a temporally bounded fact describing how an Employee participates in a Restaurant.

At minimum:

```text
Employee
Restaurant
Operational Area
Restaurant Role
valid_from
valid_to (nullable — open-ended/current)
```

This is the structure future Tips, Payroll, Scheduling, Performance and Training reasoning must resolve through when they need to know "what Role/Area applied to this Employee at this moment" — see the Tips/Payroll contract below and `03 Software/RF-One Data Store/RESTAURANT_PROFILE.md`.

---

## Temporal semantics

Area and Role assignments are temporal. Changing function does not overwrite history:

```text
Employee A
2026-01-01 → 2026-03-31
FOH / Host

Employee A
2026-04-01 → NULL
FOH / Server
```

`valid_to = NULL` represents an open-ended/current assignment. `valid_from`/`valid_to` are never automatically inferred from Clover data — Clover's own Employee↔Role relationship is a current-state snapshot only, with no historical assignment log (TASK_CLOVER_004, TASK_DATABASE_003). Assignments created manually by RF-One/business configuration preserve provenance via `assignment_source`.

---

## Assignment provenance

`assignment_source` distinguishes, at minimum, conceptually:

```text
MANUAL              — a human/business configuration decision
SOURCE_ROLE_MAPPING — seeded from a confirmed Clover SourceRole, via an
                      explicit, controlled mapping action (never automatic)
IMPORT              — bulk-loaded from another system/process
OTHER
```

A source-derived assignment is never treated as equivalent to a manually confirmed one without this provenance being visible.

---

## Multi-role / multi-area capability

A Restaurant Role is not forced to belong to exactly one Operational Area, and an Employee is not forced to hold exactly one Assignment. The model supports:

- multiple Assignments over time for one Employee (a career/tenure history);
- multiple **concurrent** Assignments for one Employee where real operations require it (e.g. a Manager valid in both `FOH` and `MANAGEMENT` at the same time).

No uniqueness constraint assumes an Employee can only have one Role globally or at a given instant — only an exact duplicate row (same Employee, Area, Role, and start instant) is rejected, to avoid accidental double-entry.

---

## The critical rule for Tips and Payroll

**Employee Assignment is never used to decide who was operationally present in a period, and `Employee.active` is never used for that purpose either.**

The correct resolution path is:

```text
requested period
→ Shifts intersecting the period
→ Employees actually present (from Shift evidence, not from a registry filter)
→ Employee Assignment valid for the relevant time
→ Operational Area + Restaurant Role
→ applicable Tips / Payroll rule
```

An Employee may remain in the registry — and may even hold a current Employee Assignment — while having no Shift in a given period; that Employee is correctly excluded from that period's Tips/Payroll resolution, not because of any Assignment or `active` flag, but because no Shift evidence places them in the period. Conversely, an Employee with a Shift in the period but no Employee Assignment valid at that time must surface as an **unresolved classification** — never silently guessed (task §23).

This is documented as the explicit Restaurant/Personnel integration principle. See `03 Software/RF-One Data Store/RESTAURANT_PROFILE.md`, "Tips / Payroll future contract," for the full algorithmic statement. **Tips and Payroll calculations themselves are not implemented by this task.**

---

## Optional Physical Area

`Employee Assignment` may optionally carry a `physical_area_id` (see `Physical Area.md`), but only where a stable physical-area assignment is genuinely meaningful for that Restaurant. It is never forced when physical working location is expected to vary shift by shift — the preferred, minimum-viable shape remains `Employee + Restaurant + Operational Area + Restaurant Role + time interval`.

---

## Relationships

```text
Employee (Restaurant Sales Model / DATABASE_SCHEMA.md §4)
  ↕ (1:N over time)
Employee Assignment
  → Restaurant
  → Operational Area
  → Restaurant Role
  → (optional) Physical Area
```

---

## Business Rules

- An Employee Assignment always references exactly one Employee, one Restaurant, one Operational Area, and one Restaurant Role.
- `valid_from` is required; `valid_to` is nullable and represents an open-ended/current assignment when null.
- A Role/Area change is represented as a new Employee Assignment row with its own `valid_from`, closing the prior row's `valid_to` — never as an in-place update that erases the prior value.
- Multiple concurrent Employee Assignments for one Employee are permitted.
- `assignment_source` must be present and must distinguish manually confirmed assignments from source-derived ones.
- Employee Assignment is never used, alone, to determine who was operationally active in a period — see "The critical rule for Tips and Payroll" above.
- `Employee.active` is never used to determine who was operationally active in a period.
