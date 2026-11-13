from pathlib import Path
p=Path('tmp/git-anagrafica-release/03 Software/RF-One Web/PERSON_RECONCILIATION.md')
p.write_text('''# Canonical person identity and explicit reconciliation (local)

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
''',encoding='utf-8',newline='\n')
report=Path('output/reports/Registry-Training-Identity-Local-2026-11-12.md');report.write_text('''# Registry / Training identity foundation - local result

The canonical person model is the existing CandidatePerson, with the existing person-account, person-employee and person-Training link contracts. A new administrator review page is available at http://127.0.0.1:5094/admin/registry/identity-reconciliation, linked from Registry.

## Existing local data audit

- 143 central person records, currently without confirmed operational links.
- 76 operational identity groups still unlinked to a central person.
- 0 groups with conflicting confirmed central-person links; 0 dangling explicit links.
- No suggested name/email matches in this particular snapshot. This does not establish that no real-world duplicates exist: human review is still required.
- Existing protected counts: 70 employees; 7 RF1 accounts; 3 Training identities; 2 RF1/Training bridges; 65 direct domain grants; 1 item grant; 2 Training needs; 56 assignments; 0 quiz attempts.

The additive schema setup preserved counts and SHA-256 fingerprints of the protected tables. No historical identity was automatically linked and no new central person was inserted into the existing database. Only disposable test databases received test confirmations.

## Delivered

Read-only graph audit and shared central-person lookup, Registry/Training reference fields, guarded atomic confirmations, stale-review checks, immutable confirmation events, explicit local migration, read-only loopback-only audit CLI, and an administrator/CSRF-protected review interface. No automatic merge, source deletion, credentials change or grant change.

11 service/migration tests, 10 HTTP/browser tests, 192 Registry checks and 10 performance/Clover regression tests passed. Sources and operational details: 03 Software/RF-One Web/PERSON_RECONCILIATION.md in the local development checkout. Private audit evidence: tmp/person-reconciliation.

This completes the local identity/reconciliation foundation, not the full Training correction program. The 76 groups await explicit human reconciliation. Training enrollment/access enablement, unified recipient selection, company boundaries, lifecycle and credential-management corrections remain separate steps. No AWS deployment or Git push was performed.
''',encoding='utf-8',newline='\n');print(report.resolve())
