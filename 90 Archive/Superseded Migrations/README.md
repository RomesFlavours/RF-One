# Superseded Migrations

Alembic migration files that must never run again, kept for traceability.
Nothing here is loaded by Alembic: only `03 Software/RF-One Data Store/migrations/versions/` is.
Do not move a file back into `versions/`; a needed change is a new migration on
the shared chain (see `03 Software/RF-One Data Store/MIGRATIONS.md`).

## interviews-prototype-20261101/

| File | SHA-256 (as archived from the working tree) |
|---|---|
| `f8d120261101_add_common_interview_sessions.py` | `e11abcb0050f90dce5a9f8f60bd60b9b7089b2f4de58ff3ac4947c7c131b3b78` |
| `f9e220261101_link_people_and_interviews.py` | `4e851f43ce33bebfde6dd1f58166f1810c46899f0e54ee90fba726da1ed864cb` |

- **Origin:** untracked files in the `handoff/2026-10-17` working tree, chained
  `d5a120261021 → e6b220261026 / b8e620261021 → f7c320261027 → f8d120261101 → f9e220261101`.
  Never committed, never applied on AWS; no local database was at either revision
  when they were archived (2026-11-01).
- **Why superseded:** the shared database received `e0a120261101` instead
  (rfone-web Interviews TEST, 2026-11-01). It creates the same `interview_sessions`
  table with `person_id` referencing the canonical `employees` directory, not
  `candidate_persons`, and does not create `person_account_links` /
  `person_employee_links` (see `03 Software/Infrastructure/deploy/rfone-interviews-test/README.md`).
  Applied on AWS, `f8d120261101` would fail (table exists) and `f9e220261101`
  would contradict the deployed person model.
- `f7c320261027` (merge revision) was **not** archived: the local Selection
  database depends on it until local database consolidation.
