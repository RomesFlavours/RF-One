# Registry — local performance correction

Date: November 12, 2026. No AWS deployment, migration, account or permission changes.

## Changes

- Resolve account-to-person links once per render through the existing authoritative resolver; reuse that result only for page presentation.
- Load current company memberships and role assignments in bulk rather than querying them for every person.
- Build the People table and dismissal list only on the People tab. Shared profile summaries load only when requested by a template.
- Scan mirrored Clover shifts once per location for the pending queue; check already-attributed shifts in batches. Preserve SQL matching, latest snapshot per external ID, location boundaries and employee overrides.
- All POST handlers, authentication and effective-permission services remain unchanged by this correction. No cross-request authorization cache was added.

## Reproducible disposable SQLite fixture

Same fixture with 40 additional linked people/accounts; HTTP render and SQL query count, before and after:

| Tab | Queries before | Queries after | Seconds before | Seconds after |
|---|---:|---:|---:|---:|
| People | 8,962 | 160 | 5.0419 | 0.2816 |
| Roles | 8,950 | 17 | 5.7298 | 0.0141 |
| Areas | 8,950 | 17 | 3.3551 | 0.0082 |
| Companies | 8,950 | 17 | 3.8534 | 0.0105 |

People HTML SHA-256 is identical before and after. Other tabs omit unused People data from their hidden editor payload; their visible functions remain covered by HTTP acceptance checks. These measurements are local, not production response guarantees.

## Existing local PostgreSQL copy

On http://127.0.0.1:5094/admin/roles all four tabs return HTTP 200. Before restart: People 2.672 s, Roles 1.467 s, Areas 1.368 s, Companies 1.326 s. After restart: People 1.744 s, Roles 0.096 s, Areas 0.041 s, Companies 0.053 s. A subsequent warm pass: 0.190 / 0.037 / 0.032 / 0.032 s. First-render/template initialization affects these timings; warm and cold results are reported separately.

## Verification

- Registry HTTP workflow: 192 checks passed, including edits, contacts, role/company assignments, dismissal, direct and role-derived permission grants and revocations, company scope and Training downgrade/revocation.
- Role/company service: 15 tests passed.
- Clover confirmation: 4 tests passed, including attribution, duplicate confirmation rejection, invalid target rollback, CSRF and access denial.
- Performance regression suite: 10 tests passed (including inherited Clover cases); query budgets and batched-versus-original mirror equivalence verified.
- Standalone permission checks: Tips 27, Kitchen 24, Selection 16 passed.

Measurements, baseline snapshots, focused patches and hashes are saved under tmp/registry-performance. Application changes are limited to role_profile_routes.py and registry_clover.py, plus tests/test_registry_performance.py. Existing unrelated checkout changes were preserved.
