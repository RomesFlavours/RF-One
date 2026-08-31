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

Optionally, an Assignment may also carry a **Location** (`location_id`, TASK_ORGANIZATION_002) — see "Location-specific Assignment" below.

This is the structure future Tips, Payroll, Scheduling, Performance and Training reasoning must resolve through when they need to know "what Role/Area applied to this Employee at this moment" — see the Tips/Payroll contract below and `03 Software/RF-One Data Store/RESTAURANT_PROFILE.md`.

---

## Location-specific Assignment (TASK_ORGANIZATION_002)

An Employee Assignment MAY optionally reference a canonical **Location** — the Location the Assignment applies to, when Location-specific organizational responsibility genuinely exists. This is necessary for real multi-Location operation:

```text
Employee: Giovanna
Assignment A: Role = Server,  Location = Winter Park
Assignment B: Role = Manager, Location = Mount Dora
```

Both Assignments are valid and may be concurrently open — the same Employee identity, no duplication, two independent organizational facts.

**The Location relationship belongs to the Assignment, not to the person's identity.** RF-One never creates a second `Employee` row merely because the same person works at two Locations; the distinguishing fact — which Location a given Role applies to, and when — lives on `EmployeeAssignment`, exactly like Operational Area and Restaurant Role already do.

`location_id` is **nullable** — a NULL Location means the Assignment applies **Restaurant-wide**, across every Location associated with the Restaurant (e.g. a CEO or other corporate/restaurant-wide Role). Location is never forced onto an Assignment that genuinely spans the whole Restaurant; conversely, it is never omitted for an Assignment that is genuinely Location-specific, merely for convenience.

A change in Location is temporal, exactly like a change in Role or Area (see "Temporal semantics" above): it closes the prior Assignment row (`valid_to` set) and opens a new one — it is never an in-place update of the prior row's `location_id`.

### `Employee.location_id` is a different fact — do not confuse them

`Employee.location_id` (required, non-nullable) is the Location under which that Employee's underlying record was ingested/observed by the current source system (Clover) — effectively source provenance / the Employee's current administrative "home" Location in the source, not a canonical, temporal statement of where any particular organizational Role applies. It predates, and is structurally unrelated to, `EmployeeAssignment.location_id`:

```text
Employee.location_id
→ which Location this Employee record originates from in the source
  system; single-valued, non-temporal, not itself a business decision

EmployeeAssignment.location_id
→ which Location a SPECIFIC, temporally bounded Role/Area Assignment
  fact applies to; optional, may differ Assignment by Assignment, is
  the canonical answer to "where does this Role apply"
```

Because these are different facts with different reliability, RF-One does not infer or backfill `EmployeeAssignment.location_id` from `Employee.location_id` for **existing** Assignment rows created before this distinction existed — an existing row with `location_id IS NULL` is left as `NULL` (Restaurant-wide/unknown) rather than guessed, per the general principle that Unknown is always preferable to a fabricated certainty (`03 Software/RF-One Data Store/TASK_ORGANIZATION_002_REPORT.md` § C/§ L). Going forward, when the Restaurant Profile bootstrap engine creates a **new** Assignment for a current Employee, it deterministically copies that Employee's own `location_id` onto the new Assignment — this is not a guess, because the Employee was itself selected as being in scope for this Restaurant's Location(s), so its own `location_id` is exactly the Location its current source evidence (SourceRole membership) is scoped to.

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
- multiple **concurrent** Assignments for one Employee where real operations require it (e.g. a Manager valid in both `FOH` and `MANAGEMENT` at the same time, or the same Role held concurrently at two different Locations — see "Location-specific Assignment" above).

No uniqueness constraint assumes an Employee can only have one Role globally or at a given instant — only an exact duplicate row (same Employee, Area, Role, Location, and start instant) is rejected, to avoid accidental double-entry. A Location difference alone (e.g. Manager at Winter Park vs. Manager at Mount Dora, same Area/Role/instant) is never treated as a duplicate (TASK_ORGANIZATION_002) — see `03 Software/RF-One Data Store/DATABASE_SCHEMA.md` §4a for the exact implemented rule, including the separate partial-uniqueness rule needed for the Restaurant-wide (`location_id IS NULL`) case.

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
  → (optional) Location
  → (optional) Physical Area
```

---

## Business Rules

- An Employee Assignment always references exactly one Employee, one Restaurant, one Operational Area, and one Restaurant Role.
- An Employee Assignment MAY reference exactly one Location (`location_id`, TASK_ORGANIZATION_002); `NULL` means the Assignment applies Restaurant-wide, across every Location associated with the Restaurant. Location is never forced onto a genuinely Restaurant-wide Assignment, and never omitted for a genuinely Location-specific one.
- `valid_from` is required; `valid_to` is nullable and represents an open-ended/current assignment when null.
- A Role/Area/Location change is represented as a new Employee Assignment row with its own `valid_from`, closing the prior row's `valid_to` — never as an in-place update that erases the prior value.
- Multiple concurrent Employee Assignments for one Employee are permitted, including the same Role held concurrently at two different Locations.
- `assignment_source` must be present and must distinguish manually confirmed assignments from source-derived ones.
- Employee Assignment is never used, alone, to determine who was operationally active in a period — see "The critical rule for Tips and Payroll" above.
- `Employee.active` is never used to determine who was operationally active in a period.
- `Employee.location_id` is a different fact from `EmployeeAssignment.location_id` (source-ingestion/current-home Location vs. canonical Assignment-scoped Location) and is never treated as equivalent to it — see "Location-specific Assignment" above.
