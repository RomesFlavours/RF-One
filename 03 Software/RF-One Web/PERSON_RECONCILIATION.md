# Canonical person identity and explicit reconciliation (local)

## Scope

Implements the first two Registry/Training correction items: one persistent person reference and explicit reconciliation of existing links. This work is local only. It does not publish, change grants, enroll learners, send invitations, reset credentials or move learning history.

## Existing identity reused

`CandidatePerson` / `candidate_persons` remains the canonical person. The existing `people_registry` contracts (`person_account_links`, `person_employee_links`) and `student_registry.TrainingPersonLink` (`training_person_links`) are reused from the other local development line, rather than introducing a new person-name table. The person can have multiple employee/source records across sites. The existing one-account and one-Training-identity-per-person constraints are retained; conflicting historical accounts require review, not an automatic merge.

The read-only `person_reconciliation.IdentityGraph` follows confirmed person links, EmployeeContextLink, RF1-to-Training links, Training acting identities, Training student employee references and retired employee aliases. Names and email never become graph edges. Name/email suggestions (including reordered names) require a human choice.

`person_for_source(db, kind, id)` is the shared lookup API. Registry exposes `central_person_id` and conflict status. Training roster reads expose the same ID and `central_person_name`, while preserving domain-owned names, contacts and training record IDs. A conflict is reported, not resolved by whichever source was read last. No Selection assessment content is exposed.

## Review workflow

Open Registry -> Identity reconciliation (`/admin/registry/identity-reconciliation`). Existing central people are listed separately from operational records without a person. Review source IDs and names, then explicitly select an existing person or explicitly create a central person. GET and audit commands never write.

Confirmation validates the current review fingerprint, checks source and destination identity chains, locks source records, rechecks after locking, and uses a savepoint. PostgreSQL confirmations also serialize through a transaction-scoped advisory lock. Conflicting links, duplicate account/Training identities, missing records and stale reviews are rejected without partial links. Shared person and Training link writers use the same conflict guard. No source record is deleted or silently reassigned. `person_reconciliation_events` records actor, person and source IDs.

A student-only identity remains external: no Employee or RF1 account is created by reconciliation. Linking identity does not grant access. Repairing missing RF1/Training enrollment bridges, lifecycle enforcement, company authorization boundaries and replacing legacy login flows remain the next correction stages.

## Local schema and migration

The additive migration is `r1a120261112`, following this checkout's `t9a120261110`. Its DDL is frozen and repeatable; it does not guess historical associations or modify source data. Schema setup is explicit, never performed by startup or a page GET. This branch must be reconciled with the other development line and the actual shared migration head before any future AWS deployment.

For the existing dedicated loopback PostgreSQL copy, the five link/audit tables were created explicitly with checkfirst. The shared Alembic marker was not advanced. Employee, account, permission, RF1/Training bridge and learning-history table counts and hashes remained identical. The immutable AWS backup was not edited.

The read-only CLI is `python -m rfone_data_store.person_reconciliation_audit --output <local-file.json>` with an explicitly configured loopback RFONE_DATABASE_URL. Non-loopback database URLs are refused. Output files may contain private identity/contact information and must remain local.

## Verification

- 11 service/migration tests: read-only audit, no name/email auto-match, reuse, repeated confirmation, multi-employee person, stale review, conflicting people/accounts, non-admin refusal, external learners, shared writer conflict guards and repeatable populated migration.
- 10 HTTP/browser tests (including the existing navigation cases): administrator/CSRF checks, read-only GET, explicit browser confirmation, and existing Registry return flows.
- 192 Registry workflow and permission checks passed.
- 10 query-growth/Clover regression tests passed; the previous performance correction remains in place.
- Migration-chain validation passed with AWS's recorded revision remaining an ancestor. No AWS check or deploy is part of this task.
