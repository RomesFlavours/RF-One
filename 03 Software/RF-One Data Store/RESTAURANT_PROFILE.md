# RF-One Data Store — Restaurant Profile

TASK_RESTAURANT_001 — the runtime/database implementation of the Restaurant Profile documented conceptually at `01 Domains/Restaurant/Organization/`. This document is the Software-layer counterpart to that Domain documentation: it explains how the schema in `DATABASE_SCHEMA.md` §4a is populated and used, and states — without implementing — the algorithmic contract future Tips/Payroll work must follow.

For the conceptual definitions (Restaurant, Operational Area, Physical Area, Restaurant Role, Employee Assignment) and their business rules, see `01 Domains/Restaurant/Organization/README.md` and its sibling files. This document does not repeat those definitions. For the Domain-level semantics that make those definitions coherent across arbitrarily different Restaurant configurations (Domain vs. Profile vs. Instance, Area hierarchy semantics, the consolidated invariant list), see `01 Domains/Restaurant/Restaurant Semantic Model.md` (TASK_RESTAURANT_002).

---

## 1. Layer separation

```text
Restaurant Domain semantics        (01 Domains/Restaurant/Organization/)
        ≠
Clover source semantics            (SourceRole, Employee.system_role)
        ≠
database/runtime implementation    (this document, DATABASE_SCHEMA.md §4a)
```

The current Clover named Role (`SourceRole`, see `DATABASE_SCHEMA.md` §4) is source evidence only. It is never automatically equated with an RF-One `RestaurantRole`, and a Clover Role is never automatically used to infer an RF-One `OperationalArea`. A Restaurant/Product Owner may later choose to seed `RestaurantRole`/`EmployeeAssignment` configuration from `SourceRole` evidence — that remains a controlled, explicit configuration action (`EmployeeAssignment.assignment_source = SOURCE_ROLE_MAPPING`), never source truth.

---

## 2. Schema summary

See `DATABASE_SCHEMA.md` §4a for full column-level documentation. In summary:

```text
restaurants                 canonical business identity
restaurant_locations        Restaurant ↔ Location, temporal
operational_areas           Restaurant-configured functional grouping (FOH/BOH/...)
physical_areas              Restaurant-configured physical zone (Dining Room/Patio/...)
restaurant_roles            Restaurant-configured canonical operational role
operational_area_roles      M:N — which Role/Area combinations this Restaurant allows
employee_assignments        temporal Employee ↔ Restaurant ↔ Operational Area ↔
                             Restaurant Role fact (+ optional Physical Area)
physical_tables.physical_area_id   optional link from an existing PhysicalTable
                                    to a canonical PhysicalArea
```

None of these tables (other than the single bootstrap `restaurants` row — § 4 below) are auto-populated from Clover. Every `OperationalArea`, `PhysicalArea`, `RestaurantRole`, `OperationalAreaRole`, and `EmployeeAssignment` row requires an explicit Restaurant/Product-Owner configuration action.

---

## 3. Tips / Payroll future contract

**Not implemented by this task (TASK_RESTAURANT_001).** Documented here so future Tips/Payroll work has a single, unambiguous algorithmic contract to follow, per the Restaurant/Personnel integration principle. **Update (TASK_TIPS_001):** the Tips half of this contract is now implemented — see `01 Domains/Restaurant/Tips/`, `DATABASE_SCHEMA.md` §4b, and `rfone_data_store/tips/engine.py`. Payroll remains not implemented. The algorithmic contract below is preserved unchanged as the statement this implementation follows, not superseded by it.

```text
requested period
→ Shifts intersecting the period
→ Employees actually present (derived from Shift evidence for that period,
  never from a static Employee list or from Employee.active)
→ Employee Assignment valid for the relevant time (valid_from <= t < valid_to,
  or valid_to IS NULL for an open-ended assignment)
→ Operational Area + Restaurant Role obtained from that Employee Assignment
→ the applicable Tips / Payroll rule (not defined by this task)
```

Future algorithmic contract, stated precisely:

```text
for each Shift intersecting the requested period:
    resolve Employee (Shift.employee_id)
    resolve EmployeeAssignment valid for the relevant time
        (an assignment whose [valid_from, valid_to) interval contains the
        relevant instant/interval of the Shift)
    obtain Restaurant Role + Operational Area from that EmployeeAssignment
    apply the applicable Tips/Payroll rule (future work)

if no EmployeeAssignment is valid for the worked time:
    do NOT silently guess a Role/Area
    surface an unresolved classification instead
```

**`Employee.active` plays no role in this contract.** It is never populated by Clover (TASK_CLOVER_003) and, even where it might be populated by a future source, it is not the mechanism by which RF-One decides who was operationally present in a period — that is exclusively a Shift-evidence question. An Employee may remain in the registry, and may even hold a current `EmployeeAssignment`, while having no Shift in a given period; such an Employee is correctly excluded from that period's Tips/Payroll resolution because no Shift places them there — not because of any Assignment or `active` value.

---

## 4. Current runtime configuration

**Update (TASK_RESTAURANT_003):** the Restaurant Profile described as intentionally empty below has since been bootstrapped from Clover's current configuration — see § 6. The original TASK_RESTAURANT_001 state is preserved here as history:

Exactly one row exists, created by this task, because the repository's existing Clover-sourced evidence unambiguously establishes it (task §19's narrow allowance):

```text
restaurants:          1 row  — name = the current canonical Location's own name
                                (identical to the current canonical Merchant's name)
restaurant_locations:  1 row  — links that Restaurant to the current canonical Location,
                                is_primary = true, valid_from/valid_to left NULL
                                (the association is known to be current; no specific
                                start date is established by any source evidence, so
                                none is fabricated)
```

No `OperationalArea`, `PhysicalArea`, `RestaurantRole`, `OperationalAreaRole`, or `EmployeeAssignment` row existed at that time. See the report `07 Tasks/Reports/TASK_RESTAURANT_001_REPORT.md`, § M, for the same statement with full reasoning.

---

## 5. Explicit non-goals (TASK_RESTAURANT_001)

Tips calculation, Payroll calculation, gratuity allocation, wage calculation, Scheduling, automatic creation of `FOH`/`BOH`/`Server`/`Host`/etc. from Clover, inference of Operational Area from a Clover named Role, overwriting `Employee.system_role` or any existing `SourceRole`/`EmployeeSourceRole` row, deletion of historical Employee stubs. None of these were implemented by that task.

---

## 6. Restaurant Profile bootstrap from Clover (TASK_RESTAURANT_003)

The Restaurant Profile is no longer empty. It was populated by an explicit, auditable, idempotent bootstrap — never automatic inference from Clover data — using the source-control/mapping/reconciliation layer documented at `DATABASE_SCHEMA.md` § 4c and implemented in `rfone_data_store/profile/bootstrap.py`. Preserves the same boundary as § 1 above: Clover configuration is *evidence used to instantiate* this Restaurant's Profile through explicit mapping rows, never an automatic equivalence.

### The `T0` contract

`RestaurantProfileSourceControl.managed_from` is the persisted moment RF-One began managing this Restaurant's Profile from Clover evidence:

```text
before T0  -> no automatic claim that today's Clover role mapping was
              historically true; RF-One does not reconstruct history
at/after T0 -> RF-One maintains Restaurant Profile temporal history
              prospectively (new EmployeeAssignment rows, closed/opened
              as source role changes are detected)
```

Per the Product Owner's explicit instruction (§ 1 above), historical role reconstruction before `T0` is not required and was not attempted. Every `EmployeeAssignment` created by the first bootstrap run has `valid_from = T0`; nothing was backdated further.

### Bootstrap algorithm summary

```text
current SourceRole (this Restaurant's Location(s), this SourceSystem)
  -> reuse-or-create RestaurantRole of the same initial name
  -> associate with the single root OperationalArea (OperationalAreaRole)
  -> reuse-or-create an ACTIVE SourceRoleMapping (valid_from = T0)

current Employee (display_name IS NOT NULL)
  -> each EmployeeSourceRole -> its ACTIVE SourceRoleMapping -> restaurant_role_id
  -> reconcile against the Employee's open EmployeeAssignment set:
       open a missing desired role  (valid_from = T0 on first-ever bootstrap
                                      for that Employee, else = current sync time)
       close an open role no longer supported by a current SourceRole
                                     (valid_to = current sync time)
  -> a current Employee with zero current SourceRoles gets no guessed
     Assignment; a CURRENT_EMPLOYEE_WITHOUT_SOURCE_ROLE issue is raised instead

historical Employee stub (display_name IS NULL)
  -> never queried for source roles, never touched
```

Idempotent by construction: rerunning with unchanged Clover configuration reuses the existing `T0`, mappings, RestaurantRoles, root Area, and Assignments, creating nothing new — verified against the real database (two consecutive `--persist` runs; the second created 0 of everything).

### Minimal root Operational Area

Clover does not expose reliable structured Operational Area evidence. Rather than inferring `FOH`/`BOH`/`Bar`/`Kitchen`/`Management` from Restaurant Role names (explicitly forbidden, task §7), the bootstrap creates exactly **one** root `OperationalArea` (`code = ROOT`, `name = "Restaurant Operations"`) representing the whole Restaurant operational context, and associates every bootstrapped `RestaurantRole` with it. This is documented as minimal profile granularity, not a claim that Rome's Flavours has no internal functional areas — it can be refined into a more granular, explicitly Product-Owner-configured Area structure later without invalidating any Assignment created against the root Area now.

### Congruence checking

The bootstrap engine detects and surfaces (never silently corrects) source→profile congruence problems as `RestaurantProfileReconciliationIssue` rows — see `DATABASE_SCHEMA.md` § 4c for the full issue-type list. It optionally cross-checks the canonical, already-ingested `EmployeeSourceRole` facts against a **fresh, read-only** Clover snapshot (`03 Software/Clover Data Explorer/fetch_profile_bootstrap_snapshot.py`, GET-only, no write capability) to detect drift between what was last ingested and Clover's live current state, without re-ingesting anything itself.

### Current runtime state (as bootstrapped)

```text
restaurant_profile_source_controls: 1 row  (T0 established)
source_role_mappings:               7 rows (one per current Clover named Role)
restaurant_roles:                   7 rows (Server/Host/Admin/BOH/Team Leader/Manager/Employee)
operational_areas:                  1 row  (root, code=ROOT)
operational_area_roles:             7 rows (every RestaurantRole <-> the root Area)
employee_assignments:              24 rows (one per current Employee — none had a
                                             concurrent second current SourceRole)
```

No `TipPolicy`, service-attribution resolver, or Rome's Flavours Tip percentage was configured by this task — see `01 Domains/Restaurant/Tips/` and `07 Tasks/Reports/TASK_RESTAURANT_003_REPORT.md` § O.

---

## 7. Explicit non-goals (TASK_RESTAURANT_003)

Rome's Flavours Tip percentages, a TipPolicy, a real service-attribution resolver, BOH-exclusion logic (hardcoded or otherwise) in the generic Tips engine, inferred FOH/BOH/Bar/Kitchen Operational Areas, historical role reconstruction before `T0`, Payroll, Clover write operations. None of these are implemented here.
