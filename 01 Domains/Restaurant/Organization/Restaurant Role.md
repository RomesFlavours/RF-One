# Restaurant Role

**Version:** 1.0
**Status:** Approved
**Module:** Restaurant Domain / Organization
**Origin:** TASK_RESTAURANT_001

---

## Definition

A **Restaurant Role** is the RF-One canonical operational role performed by a person, as configured by a specific Restaurant.

Examples a Restaurant might configure include `Server`, `Host`, `Bartender`, `Cook`, `Dishwasher`, `Manager` — illustrative, not a hard-coded universal enum. Every Restaurant Role belongs to exactly one Restaurant's configuration.

---

## Distinct from Clover named Role, Clover systemRole, and personnel identity

This is the single most important boundary this document exists to draw:

```text
Clover named Role      (SourceRole: Server, Host, Admin, BOH, ...)
      ≠
Clover systemRole       (Employee.system_role: EMPLOYEE, MANAGER, ADMIN)
      ≠
RF-One Restaurant Role  (this concept)
      ≠
Personnel identity      (who the person is)
```

`SourceRole` (`03 Software/RF-One Data Store/DATABASE_SCHEMA.md` §4) is Clover source evidence: the named Role the Clover UI shows for an Employee, empirically confirmed via `Employee.roles.elements[]` / `Role.employeesRef.elements[]` (TASK_CLOVER_004, verified again by TASK_EMPLOYEE_002). It is retained because it is real, useful evidence — but it is not automatically the Restaurant Role. A Clover Role named `"Server"` does not automatically create or populate an RF-One `RestaurantRole` named `"Server"`; a Restaurant/Product Owner may **choose** to initialize its Restaurant Role configuration by looking at SourceRole names, but that is a controlled configuration action (`EmployeeAssignment.assignment_source = SOURCE_ROLE_MAPPING`), never an automatic inference (task §7, §19).

`Employee.system_role` (Clover's systemRole tier — `EMPLOYEE`/`MANAGER`/`ADMIN`) is broader still and was already established (TASK_CLOVER_003/TASK_DATABASE_003) as insufficient to represent a specific operational role. It remains untouched and is never overwritten by Restaurant Role assignment.

---

## Multi-area capability

A Restaurant Role is not forced to belong to exactly one Operational Area. A `Manager` Role may be configured as valid in both `FOH` and `MANAGEMENT`, for example — see `Operational Area.md` and the `OperationalAreaRole` M:N table (`03 Software/RF-One Data Store/DATABASE_SCHEMA.md` §4a).

---

## Relationships

```text
Restaurant
└── (1:N) Restaurant Role
             └── (M:N, via OperationalAreaRole) Operational Area
                       └── (via Employee Assignment) Employee
```

---

## Business Rules

- Every Restaurant Role belongs to exactly one Restaurant.
- Restaurant Role names/values are Restaurant configuration, never a hard-coded universal enum.
- A Restaurant Role may be valid in more than one Operational Area (M:N via `OperationalAreaRole`).
- A Restaurant Role is never automatically equated with a Clover named Role (`SourceRole`) or a Clover `systemRole`.
- `Employee.system_role` is never overwritten by Restaurant Role assignment.
