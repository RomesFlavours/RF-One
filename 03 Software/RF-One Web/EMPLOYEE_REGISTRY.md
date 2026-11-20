# Employee registry — local first release

Business definition: `01 Domains/Business Domain/Restaurant/Organization/Employee Registry.md`.

The shared shell registers `/employees`, `/employees/initialize`, and
`/employees/<employee_id>`. All routes require the existing active administrator
session; all POSTs require the existing CSRF token. The Home Settings link uses
the same authorization. Full names are appropriate on these identity-management
screens; timestamps use each employee's Location timezone.

`employee_registry.py` uses Employee and EmployeeAssignment as canonical facts.
`employee_registry_profiles` stores source name/code/role observations, ownership
flags, review metadata and an optimistic version. `employee_registry_changes`
records source changes and operator corrections with the existing RF-One account.
Role changes lock the employee, validate Restaurant/Area/Role scope, close before
opening assignments, and reject overlapping history or stale edits. Sparse source
references cannot erase known facts. Current source role comparisons use only the
latest observation batch; an unresolved role catalogue cannot clear a snapshot.

Both shared Clover employee upsert paths call the same ownership service. Role
observation hooks cover bulk and historical imports. Existing profile bootstrap
skips operator-protected roles. No module uses a second employee identity.

## Local operation

From `03 Software/RF-One Web`:

```powershell
python employee_registry_local.py --initialize
python employee_registry_local.py --serve --operator rfone
```

The explicit launcher uses the existing `rfone_aws_copy` PostgreSQL database on
127.0.0.1:55434, with credentials read from its private existing connection file.
It creates no database, synthetic person or login account. The optional operator
argument opens a loopback-only preview session for an existing active admin;
omit it to use normal RF-One login. Local HTTP cookie transport is configured
only in this launcher; deployed shell authentication is unchanged. Port 5092
serves the same RF-One Web application, not a duplicate module implementation.

Initialization explicitly upgrades the deployed migration branch from
`d5a120261021` to additive revision `e6b220261026`, then creates review profiles
for the imported employees. It does not rerun unrelated migration branches.
The missing deployed migration ancestry was recovered verbatim from the existing
`rf-one-selection-english` checkout; its old migrations are not re-executed.
Use the explicit revision target while other historical branches remain separate.

AWS has not received these schema/code changes. The first local trial contains
64 source-derived employee profiles; names, statuses and role assignments remain
unchanged until an operator saves a correction. Initializing again is idempotent.
A fresh AWS-to-local overwrite would remove local-only registry data unless the
local migration and required trial changes are preserved/reapplied deliberately.

## Verification and recovery

`python -m unittest test_employee_registry test_clover_employee_history` from the
Data Store directory exercises disposable in-memory databases only. Engines are
disposed after each test; no test DB files or servers are retained.

The pre-registry backup is the verified pre-refresh local dump referenced by
`output/aws_local_data_alignment_20261026.txt`. The registry migration is additive;
downgrading to d5a120261021 removes the two registry tables, so export any operator
corrections before doing so. No other schema migration was applied during this task.
