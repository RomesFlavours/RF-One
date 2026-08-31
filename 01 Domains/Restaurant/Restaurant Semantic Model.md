# Restaurant Semantic Model

**Version:** 1.1
**Status:** Approved
**Module:** Restaurant Domain
**Origin:** TASK_RESTAURANT_002; Corporate/Brand/Location resolution TASK_RESTAURANT_STRUCTURE_001

---

## 1. Purpose

This document is the canonical, high-level map of the Restaurant Domain's operational semantics. It defines **what concepts exist, what each concept means, how concepts may relate, and what invariants must remain true** — independently of any specific restaurant's configuration.

It exists because `01 Domains/Restaurant/Organization/` (TASK_RESTAURANT_001) and `01 Domains/Restaurant/Model/` document individual concepts and their implementation, but no single document previously stated the Domain-level principle that makes the whole structure coherent:

> A Restaurant configuration may vary arbitrarily in naming and granularity while remaining semantically coherent as long as each configured element preserves the meaning of the canonical concept it instantiates.

This document states that principle explicitly and is the authoritative reference for it. It does not duplicate the detailed content of `Organization/*.md` — it points to those files for full definitions, business rules, and implementation notes, and adds the semantics that were previously implicit: the Domain/Profile/Instance separation, Area hierarchy, and the consolidated invariant list.

---

## 2. Domain vs Profile vs Instance

```text
Restaurant Domain
→ canonical concepts, their meaning, and the relationships/invariants
  that must hold between them, regardless of any specific restaurant

Restaurant Profile
→ one Restaurant's configuration of those concepts: which Operational
  Areas it recognizes, which Physical Areas it recognizes, which
  Restaurant Roles it recognizes, and which Area↔Role combinations it
  permits

Specific Restaurant (instance)
→ one concrete Restaurant, operating under one Restaurant Profile,
  with real Employees temporally assigned into it
```

This mirrors, at Domain scope, the distinction CLAUDE.md draws between Core, Domain, Product and Runtime: a concept existing at one level does not imply a specific value at the level below it. The Restaurant Domain never hard-codes `FOH`, `BOH`, `Bar`, `Server`, `Host`, `Cook`, or `Manager` — those are illustrations of what a Restaurant Profile *might* contain, never a mandatory universal enumeration. Any Restaurant Profile that preserves the meaning of each canonical concept it instantiates is valid, no matter how it names or subdivides things — see § 14.

This document defines the Domain (concepts, meaning, relationships, invariants). `01 Domains/Restaurant/Organization/` documents how a Profile is structured and implemented. No document in this Domain enumerates what a specific Restaurant Profile must contain — that is Product Owner / Restaurant configuration, out of scope for both.

---

## 3. Restaurant

**Restaurant** is the operational context in which restaurant activities are organized and performed.

Restaurant is **not**:

```text
a POS Merchant
a Clover account
a Location
a legal entity by definition
a fixed organizational chart
```

A Restaurant may be associated with one or more Locations over time (`Organization/Restaurant Profile.md`, "Restaurant ↔ Location"), and it defines its own configured operational and physical structure (its Restaurant Profile) rather than inheriting one from any source system.

Three distinct things must not be conflated:

```text
Restaurant identity
→ the canonical business/operational restaurant itself (e.g. its name);
  see Organization/Restaurant Profile.md

Restaurant configuration
→ that Restaurant's Restaurant Profile — its Operational Areas, Physical
  Areas, Restaurant Roles, and allowed Area↔Role combinations

Restaurant operational reality
→ what actually happens: real Shifts, real Employee Assignments, real
  Orders, real Table Services — evidence, not configuration
```

A Restaurant's *identity* can exist before its *configuration* is defined (a newly onboarded Restaurant with no Areas/Roles configured yet is still a valid Restaurant identity), and its configuration can exist before *operational reality* accumulates against it. None of the three is inferable from either of the others.

**Note on `Model/OU-Restaurant.md`:** that document places Restaurant within Core's `Corporate → Brand → Operational Unit` hierarchy for governance/ownership purposes — a different axis from the one this document addresses. This document does not require every Restaurant instance to carry a populated Brand/Corporate relationship to be semantically valid; per CLAUDE.md's Core/Domain/Runtime separation, a Core-inherited relationship existing conceptually does not imply every Runtime instance must populate it. The current single-Restaurant RF-One deployment (`03 Software/RF-One Data Store/`) has no `Corporate`/`Brand` runtime tables at all, and that is not a contradiction — it is an unimplemented, not-yet-needed axis.

**Resolved (TASK_RESTAURANT_STRUCTURE_001):** the Product Owner has now confirmed the concrete business structure this axis must express — one owning Corporate may operate multiple Brands/restaurant concepts in the future; Rome's Flavours is one such Brand; Winter Park and Mount Dora are two Locations of that *same* Brand, not two separate Brands. This maps onto the existing Runtime schema without any new table, by recognizing which existing entity already plays which Core-hierarchy role:

```text
Core hierarchy            Runtime entity (03 Software/RF-One Data Store/rfone_data_store/models.py)
--------------             ------------------------------------------------------------------------
Corporate                  not yet a runtime table — exactly one, implicit (Core/Corporate.md
                            §Business Rules: "Every RF-ONE installation contains exactly one
                            Corporate"); no ambiguity is created by leaving it unmodeled while
                            only one Corporate has ever existed
Brand                      `Restaurant` (already the "one or more Locations" level — see § 3
                            above, "A Restaurant may be associated with one or more Locations
                            over time"; NOT the runtime entity `Location`)
Operational Unit / site    `Location`, associated to its Brand via `RestaurantLocation`
```

This is not a new interpretation invented by this task — `Restaurant`'s own docstring in `models.py` already calls it "canonical business identity," and `RestaurantLocation` was already built (TASK_ORGANIZATION_002) specifically so one `Restaurant` row can hold many `Location` rows over time. Mount Dora onboarding therefore requires no new `Restaurant`/Brand row — Mount Dora becomes a second `RestaurantLocation` under the *same* `Restaurant` row Winter Park already belongs to (see `Restaurant/Roadmap.md` § 5). A future, genuinely different Brand under the same Corporate (not decided or scheduled now) would become a *second* `Restaurant` row, entirely independent of the first by construction — nothing in the schema today couples one `Restaurant`'s configuration (`TipPolicy`, `EmployeeAssignment`, `OperationalArea`, etc., all scoped by `restaurant_id`) to another's.

**One genuinely misleading fact found and documented, not silently fixed:** the real production `Restaurant.name` value is currently `"Rome's Flavours - WP"` — it bakes the Winter Park Location suffix into the Brand-level name field, conflating Brand identity with Location identity (exactly the confusion this section now formally prohibits). This was reasonable when only one Location ever existed, but is no longer accurate now that the schema is confirmed to already support, and Mount Dora onboarding will exercise, one Brand with multiple Locations. **Not corrected by this task** (mutating the real production database is out of this task's scope) — recorded as a recommended follow-up: rename the real `Restaurant.name` row to `"Rome's Flavours"` (without the Location suffix), ideally as part of Mount Dora onboarding itself (`Restaurant/Roadmap.md` § 5), with explicit Product Owner authorization first (the same discipline used for every other real-database write in this repository's history, e.g. TASK_TIPS_004).

The prior open question recorded at `07 Tasks/Reports/TASK_RESTAURANT_002_REPORT.md` § O (a file that, on inspection, does not currently exist in this repository — its content is preserved only via this document's own summary of it) is answered by the above; it is not reopened.

---

## 4. Restaurant Profile

**Restaurant Profile** is the configured instantiation of Restaurant Domain concepts for a specific Restaurant.

A Restaurant Profile may define:

```text
Operational Areas
Physical Areas
Restaurant Roles
allowed Operational Area ↔ Restaurant Role combinations
other Restaurant-specific classifications
```

The Profile is not the Domain ontology — it is one Restaurant's answer to the ontology's open questions ("what Operational Areas do *you* have?"). It may evolve over time (Areas/Roles added, retired, or reconfigured); evolving the Profile is a configuration change, never a Domain change. See `Organization/Restaurant Profile.md` for the implemented structure.

---

## 5. Operational Structure

### 5.1 Operational Area

> A functional partition of Restaurant operations.

Operational Area answers:

> In which functional part of the Restaurant is this activity, responsibility, or assignment situated?

Illustrative-only examples: `FOH`, `BOH`, `Dining`, `Kitchen`, `Bar`, `Administration`. None of these is canonical; the Domain prescribes no name. A Restaurant may configure 2 broad Operational Areas or 10 highly specific ones — both satisfy the model, because granularity is a Profile decision, not a Domain constraint.

Operational Area is always distinct from Physical Area (§ 6) — see the invariant in § 12.

Full definition, business rules and the implemented schema: `Organization/Operational Area.md`.

### 5.2 Operational Area hierarchy

Hierarchy is **canonically supported, optionally used**:

```text
Operational Area
→ parent Operational Area (nullable)
```

Illustrative only:

```text
Guest Operations
├── Dining
├── Bar
└── Reception
```

Semantics, where a Restaurant Profile chooses to use hierarchy:

- **Parent-child meaning:** a child Operational Area is a more specific functional partition nested within its parent's functional scope — hierarchy expresses **functional containment/classification**, never physical containment. `Dining` being a child of `Guest Operations` says nothing about where `Dining` is physically located.
- **Root Area:** an Operational Area with no parent is a root of its own hierarchy. A Restaurant Profile with no hierarchy at all is simply one where every Operational Area is a root — hierarchy is additive, not mandatory.
- **Cycle prohibition:** an Operational Area may never be its own ancestor, directly or transitively. A parent assignment that would create a cycle is invalid.
- **Depth:** the Domain does not prescribe a maximum depth or a required uniform depth across sibling branches.

This is a Domain-semantics addition, not a database migration. The current schema (`operational_areas`, TASK_RESTAURANT_001) has no `parent_id` column — see § 20 of `07 Tasks/Reports/TASK_RESTAURANT_002_REPORT.md`/`Organization/Operational Area.md` for why that gap is documented as future work rather than forced now: no current Restaurant Profile exists yet (Rome's Flavours' Areas are not configured — TASK_RESTAURANT_001 §19), so there is no operational data the missing column could contradict.

---

## 6. Physical Structure

### 6.1 Physical Area

> A physically distinguishable portion of the Restaurant environment.

Physical Area answers:

> Where physically does activity occur?

Illustrative-only examples: `Dining Room`, `Patio`, `Kitchen`, `Storage`, `Bar Counter`, `Private Room`.

**Invariant: `Operational Area ≠ Physical Area`**, even when a configured Restaurant chooses similar names or near-identical boundaries (e.g. an Operational Area named `Bar` and a Physical Area named `Bar Counter` are two different facts that happen to correlate for this Restaurant — the correlation is not identity, and another Restaurant could easily configure them to diverge, e.g. a `Bar` Operational Area whose staff also work the `Patio` Physical Area during outdoor-service hours).

Full definition, business rules and the implemented schema: `Organization/Physical Area.md`.

### 6.2 Physical Area hierarchy

Optional, symmetric to § 5.2:

```text
Physical Area
→ parent Physical Area (nullable)
```

Illustrative only:

```text
Dining Floor
├── Main Dining Room
└── Patio
```

Same rules apply: parent-child expresses **physical containment** (a sub-zone within a larger physical zone), root Areas are simply parentless, and cycles are prohibited. Physical containment must never be read as implying functional/operational classification — a `Patio` nested under `Dining Floor` says nothing about which Operational Area(s) work there.

Not implemented in the current schema (`physical_areas`, TASK_RESTAURANT_001) for the same reason as § 5.2 — no current Restaurant Profile exists to contradict.

---

## 7. Restaurant Role

> A function or responsibility pattern that a human resource may perform within a Restaurant operational context.

Restaurant Role is **not**:

```text
a person
an Employee identity
a Clover SourceRole
a system permission tier
an Operational Area
```

Illustrative-only examples: `Server`, `Host`, `Bartender`, `Cook`, `Dishwasher`, `Manager`. A Restaurant Role may optionally carry semantic attributes such as purpose, responsibilities, capabilities, or authority expectations — none of these is required in a first runtime implementation; the current schema (`restaurant_roles`) stores `name`/`code`/`description`/`active` only, which remains a valid, minimal, non-contradictory instantiation.

**Operational Area ↔ Restaurant Role is many-to-many** (`operational_area_roles`, `Organization/Operational Area.md` § "Multi-role capability", `Organization/Restaurant Role.md` § "Multi-area capability"): a Restaurant Role is never permanently bound to exactly one Operational Area. The same Role may be relevant in multiple Areas (e.g. `Manager` valid in both `FOH` and `Management`), and the same Area may recognize multiple Roles (e.g. `FOH` allowing both `Host` and `Manager`).

Full definition and the implemented schema: `Organization/Restaurant Role.md`.

---

## 8. Employee Assignment

> A temporally situated fact that an Employee performs a configured Restaurant Role within an Operational Area of a Restaurant.

At minimum:

```text
Employee
Restaurant
Operational Area
Restaurant Role
valid_from
valid_to (nullable — open-ended)
```

Optionally, an Assignment may also reference a **Location** (`location_id`, TASK_ORGANIZATION_002) — the Location this specific Assignment applies to, when Location-specific organizational responsibility genuinely exists (e.g. "Server at Winter Park" vs. "Manager at Mount Dora", held concurrently by different or the same Employee). `location_id` is nullable: `NULL` means the Assignment applies Restaurant-wide, across every Location associated with the Restaurant (e.g. a Restaurant-wide/corporate Role). The Location relationship belongs to the Assignment, never to the Employee's identity — RF-One never creates a second Employee merely because one person works at two Locations. See `Organization/Employee Assignment.md`, "Location-specific Assignment," for the full rule, including why this is a different fact from `Employee.location_id` (source-ingestion/current-home Location).

Employee Assignment is **not**:

```text
Employee identity
Employee active/inactive state
Clover SourceRole
Shift attendance
```

**Assignment describes organizational placement/function. Shift describes observed work presence.** These are independent facts about an Employee: an Assignment can be valid for a period in which the Employee has no Shift at all (e.g. on leave, or simply not scheduled), and a Shift can occur without a valid Assignment covering it (an unresolved classification — see § 9). Neither implies the other. Full definition and the implemented schema: `Organization/Employee Assignment.md`.

---

## 9. Temporal semantics and the activity/presence invariant

Employee Assignment must preserve history. Illustrative only:

```text
Period 1 → Area A / Role X
Period 2 → Area A / Role Y
Period 3 → Area B / Role Y
```

A Role or Area change is a **new** Assignment row with its own `valid_from`; the prior row's data is never overwritten. The model allows: open-ended assignments (`valid_to IS NULL`), closed assignments, multiple assignments over time for one Employee, and legitimate concurrent assignments (more than one simultaneously valid Assignment for the same Employee — e.g. a Manager valid in both `FOH` and `Management` at once). Temporal validity (`valid_from`/`valid_to`) is a property of the Assignment; it is never derived from, or conflated with, Shift timestamps.

**Strong invariant:**

```text
Employee Assignment ≠ Employee worked during a period
```

For any operational calculation that needs to know who was actually present and in what capacity during a period — Tips and Payroll are the two named future consumers, but the principle is general — the resolution path is always:

```text
requested period
→ Shifts intersecting the period
→ Employees actually present (from Shift evidence)
→ Employee Assignment valid during the relevant worked time
→ Operational Area + Restaurant Role
→ applicable rule
```

**The current Employee list, and `Employee.active`, must never determine period participation.** An Employee may remain in the registry — and may even hold a current Employee Assignment — while having no Shift in a given period, and must be excluded from that period's resolution on that basis alone. Conversely, a Shift with no Employee Assignment valid at that time must surface as an unresolved classification, never a silent guess. This principle is shared by, and must not be reimplemented differently by, every future consumer (Tips, Payroll, Scheduling, Performance).

---

## 10. Source-system boundary

```text
Clover SourceRole       ≠ Restaurant Role
Clover systemRole       ≠ Restaurant Role
Clover SourceRole       ≠ Operational Area
```

A Clover named Role (`SourceRole`, e.g. `"Server"`) is source evidence — real, retained, and useful — but it is never silently equated with a Restaurant Role of the same label. A Restaurant may later choose to seed its Restaurant Role configuration by looking at `SourceRole` names, but that is a configured mapping decision (`EmployeeAssignment.assignment_source = SOURCE_ROLE_MAPPING`), made explicitly by the Restaurant/Product Owner, never an automatic inference performed by RF-One. The same applies to `Employee.system_role` (Clover's broader `EMPLOYEE`/`MANAGER`/`ADMIN` tier) and to any attempt to infer an Operational Area from a Clover Role. See `Organization/Restaurant Role.md` and `03 Software/RF-One Data Store/DATABASE_SCHEMA.md` § 4/§ 4a for the full implemented boundary.

---

## 11. Personnel Management boundary

**Restaurant Domain** owns Restaurant-specific operational semantics:

```text
Restaurant
Restaurant Profile
Operational Area
Physical Area
Restaurant Role
Employee Assignment in Restaurant context
```

**Personnel Management** (`01 Domains/Personnel Management/`) owns cross-industry workforce semantics:

```text
Workforce
Selection
Training
Performance
Personnel Decisions
```

Restaurant Domain does not duplicate or redefine any Personnel Management concept. Personnel Management consumes Restaurant's technical content (e.g. "this Employee's Restaurant Role and Operational Area during the evaluated period") as an input, the same way it consumes any other technical Domain's content — see `01 Domains/Personnel Management/README.md`, "Relationship to technical Domains," and `Organization/README.md`, "Relationship to Personnel Management."

---

## 12. Semantic invariants

```text
Restaurant Profile ≠ Restaurant Domain
Operational Area ≠ Physical Area
Restaurant Role ≠ Employee
Restaurant Role ≠ SourceRole
Employee Assignment ≠ Shift
Employee Assignment ≠ active/inactive
Employee Assignment.location_id ≠ Employee.location_id (Assignment-scoped Location fact vs. source-ingestion/current-home Location)
Area ↔ Role is M:N
Assignment is temporally situated
Assignment Location is optional — NULL means Restaurant-wide, never a forced/guessed Location
a Restaurant may have zero or one currently-open primary Location, never more than one
Location, not Restaurant, is authoritative for the timezone of events occurring at it
configuration names are not ontology
configuration granularity is Restaurant-specific
historical assignments must not be silently overwritten
source semantics must not silently become canonical semantics
Operational Area hierarchy (if used) expresses functional containment, not physical containment
Physical Area hierarchy (if used) expresses physical containment, not functional classification
an Operational Area/Physical Area/Restaurant Role hierarchy or set must never contain a cycle
```

Every document in `01 Domains/Restaurant/Organization/` and every table in `03 Software/RF-One Data Store/DATABASE_SCHEMA.md` § 4a is expected to remain consistent with this list. A future change that would violate one of these invariants must revise this document explicitly, not silently drift from it.

---

## 13. Extensibility

The same Restaurant semantic structure is intended to be able to contextualize future entities without requiring them to be modeled now:

```text
Physical Tables    → may reference a Physical Area (already implemented,
                     `physical_tables.physical_area_id`, TASK_RESTAURANT_001)
Equipment
Service Channels
Production Areas
Storage Areas
Processes
```

No speculative entity above is implemented by this document. The principle this section preserves is narrower and more durable: **future Restaurant concepts should reference the canonical `Operational Area` and/or `Physical Area` where a functional or physical location is relevant to them**, rather than each future module inventing its own parallel notion of "where"/"which part of the restaurant." This is the same reasoning already applied to `PhysicalTable` in TASK_RESTAURANT_001.

---

## 14. Examples as configuration, not ontology

Every named value in this document — `FOH`, `BOH`, `Dining`, `Kitchen`, `Bar`, `Administration`, `Dining Room`, `Patio`, `Storage`, `Bar Counter`, `Private Room`, `Server`, `Host`, `Bartender`, `Cook`, `Dishwasher`, `Manager` — is an illustration, not a Domain requirement. None of them is stored as a fixed enumeration anywhere in `rfone_data_store/models.py`; every one of `operational_areas.name`, `physical_areas.name`, and `restaurant_roles.name` is a free string, scoped only to the owning Restaurant (`UniqueConstraint(restaurant_id, name)`).

Two Restaurants may both conform fully to this Domain while using completely different Profiles:

```text
Restaurant A                          Restaurant B
Operational Areas:                    Operational Areas:
- FOH                                 - Guest Experience
- BOH                                 - Beverage
                                       - Production
                                       - Administration
```

Both are valid: each configured Operational Area satisfies the canonical meaning ("a functional partition of Restaurant operations") regardless of how many there are or what they are called. The same freedom applies to Restaurant Roles and Physical Areas. No canonical value list is required, expected, or enforced by this Domain, this Data Store schema, or any future Tips/Payroll/Scheduling consumer of Employee Assignment.

---

## Related documents

- [Organization/README.md](Organization/README.md) — Restaurant Organization section index and the Domain/Software split
- [Organization/Restaurant Profile.md](Organization/Restaurant%20Profile.md), [Organization/Operational Area.md](Organization/Operational%20Area.md), [Organization/Physical Area.md](Organization/Physical%20Area.md), [Organization/Restaurant Role.md](Organization/Restaurant%20Role.md), [Organization/Employee Assignment.md](Organization/Employee%20Assignment.md) — full concept-level definitions and business rules
- [Model/OU-Restaurant.md](Model/OU-Restaurant.md), [Model/OperationalArea.md](Model/OperationalArea.md) — Core-inherited Corporate/Brand/Operational Unit placement (a different axis — see § 3)
- [Sales/Restaurant Sales Model.md](Sales/Restaurant%20Sales%20Model.md) — Table Service, Order, and sales-side canonical model (does not reference Operational Area/Physical Area/Restaurant Role at this time)
- [../Personnel Management/README.md](../Personnel%20Management/README.md) — Personnel Management boundary
- `03 Software/RF-One Data Store/DATABASE_SCHEMA.md` § 4a, `03 Software/RF-One Data Store/RESTAURANT_PROFILE.md` — implemented schema and the Tips/Payroll future contract
- `07 Tasks/Reports/TASK_RESTAURANT_001_REPORT.md`, `07 Tasks/Reports/TASK_RESTAURANT_002_REPORT.md` — implementation and canonicalization history
