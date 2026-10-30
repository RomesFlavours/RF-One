# REPORT — Included RF-One person foundation and domain integration

Date: 2026-10-29 (America/New_York).
Status: implementation verified locally; subsequently published on AWS on 2026-10-29.
See PERSON_FOUNDATION_003_AWS_REPORT.md and PERSON_FOUNDATION_003_RELEASE.json.
Supersedes the person/POS ownership and derived-active-state assumptions in
EMPLOYEE_DIRECTORY_CONSUMERS_001_REPORT.md and EMPLOYEE_DIRECTORY_SELECTORS_002_REPORT.md.
Baseline: 9764ef6; earlier step 1/2 working-tree changes are retained and refined.

## 1. Approved ownership and commercialization

The shared base directory is included in every Domain combination. RF-One owns
reference person identity; a POS is a source observation to reconcile. Existing
Employee.id is retained as the compatibility person ID, avoiding a parallel
registry or historical FK rewrite. A person need not have a POS, location,
account or employment relationship. Name/email/phone and directory visibility are
reference attributes. Workforce owns assignments/employment, Compensation owns
terms/results, Bank owns card-holder periods, Selection owns applications,
Training owns its accounts/attempts, and Identity & Access owns authority/access.
Links never grant access; included capability is distinct from permissions.

## 2. Revised steps 1 and 2

- All unknown Clover records stay pending, even without suggestions. RF-One
  creation or association requires explicit approval. Historical unknowns follow
  the same boundary. Existing confirmed people and IDs remain unchanged.
- RF-One-native creation and reference email/phone editing are available from the
  directory with existing directory-manager access and CSRF.
- Multiple POS accounts at the SAME merchant may explicitly link to one person.
  Current duplicate-account anomalies are derived from complete current reads;
  removed duplicates stop producing a site-absence alarm when another account
  still represents that person there. Historical links/events remain retained.
- Disappeared, never-used unconfirmed accounts leave the current review queue.
  Unknown historical work references remain visible until attributed. Work is
  not imported under an invented person; failure leaves the pending observation.
- Reversed names are suggestions only. Source name/email/custom ID/roles never
  overwrite reference or domain-management facts.
- Directory active/archive state is explicitly RF-One-owned. POS absence never
  archives a person, terminates employment or disables an account. This changes
  the former derived Dismissis display policy: only explicit false is archived.
- Canonical selectors include optional Workforce-owned assignment site evidence,
  without copying it. Current assignment sites feed current selection;
  historical selection retains former sites. Native people appear without POS.
- POS role bootstrap does not close/overwrite open manual RF-One assignments.
- Roles/Compensation sections on the directory detail respect those domains'
  existing access instead of exposing domain data merely through directory access.

## 3. Completed remaining integrations

### Bank

New holder decisions resolve retired person IDs and explicitly linked human
identities to the canonical person. Candidates suppress only genuinely confirmed
identity equivalence, never equal names. SYSTEM/AI identities cannot hold a card.
Existing dated holder assignments, stored labels and financial history are not
rewritten merely by creating a context link.

### Accounts, Training and Selection

EmployeeContextLink has one unique context target per row: RFOneAccount, human
ActingIdentity, TrainingAccount, CandidatePerson or ProjectResponsible. Foreign
keys and an exactly-one-target check protect integrity. Existing authenticated
account↔Training↔human-identity associations are followed when resolving a person;
conflicting person associations are refused. No account, grant, candidate merge,
Selection outcome or Training attempt is created or moved by the bridge.

Directory context link/unlink actions require CSRF, explicit confirmation,
directory-management authority AND target-management authority. Account/actor
links require RF-One administration; Training/Selection/Projects targets require
their domain-management permission. Cross-domain choices are hidden otherwise.
Creating a NEW project responsible referencing a person follows existing project
creation permissions; it does not reassign an existing domain identity.

Profile, candidate application and Training views expose the relevant confirmed
reference name while retaining domain/source labels. Training student detail
identifies that student's linked person, distinct from the trainer's own profile.

### Projects

Responsibles may remain external names or explicitly reference a native RF-One
person. Repeated selection reuses the same responsible. Live reference names are
read from the person while local labels/history remain. Equal names remain
separate identities; ambiguous typed names are refused and an ID selector is
available. Task assignment checks the responsible belongs to the same project.
Changing a linked reference name belongs to the directory. Deleting an unused
responsible audits/removes its context link, never the person. Existing task,
chapter, prerequisite, Gantt and print behavior is retained.

## 4. Migration and release boundary

Migration: d9e220261029, follows c8e1f4a7b2d6.
- employees.location_id becomes nullable; all existing IDs/rows are retained.
- Adds nullable reference email and phone.
- Adds employee_context_links, with target FKs, uniqueness and exactly-one check.
- No guessed backfill of account/candidate/project associations.

Populated previous-schema upgrade retained employees, shifts and compensation
terms. Downgrade refuses to discard native people, contacts or context links.
Startup verification now requires the new schema and includes the migration hash.
The normalized staged package passed artifact verification and isolated tests.

At completion of local implementation AWS was unchanged. The subsequent release
is recorded in PERSON_FOUNDATION_003_AWS_REPORT.md. Deployment must migrate the database and deploy every
consuming app/worker together, preserving the existing startup guard and worker
configuration. No outbound POS writer was introduced. A future return flow still
requires supported concrete operations, explicit approval and read-back checks.
The legacy fresh-staging bulk importer refuses unconfirmed references; it cannot
be used as an automatic person-registration shortcut.

## 5. Verification

All final checks use synthetic/disposable local databases or fake GET-only POS
clients. No AWS, Clover production, real personnel updates or payouts were used.

| Suite | Outcome |
| --- | --- |
| Directory + native-person/context + historical payments | 53 passed |
| Directory HTTP, permissions, populated migration and downgrade protection | 10 passed |
| Projects HTTP, including native person selection/task identity | 49 passed |
| Bank cardholder/accounting regression | 37 passed |
| Training single-login/access integration | 29 passed |
| Selection actor trust-boundary HTTP | 12 passed |
| Acquisition | 59 passed |
| Acquisition failure/rollback safety | 40 passed |
| Live Sync | 29 passed |
| Historical extractor | 29 passed |
| Correction Sync | passed |
| Role bootstrap | 14 passed |
| Payroll | 52 passed |
| Staged worker startup guard | 10 passed |

Regression coverage includes missing/failed collections, pending historical
identity persistence after rollback, same-merchant duplicates clearing,
source/reference separation, native people with Workforce sites, protected
manual assignments, no implicit grants, nonhuman refusal, auth-chain conflicts,
context unlink audit, alias resolution, homonyms and project scope.

Initial legacy fixture assumptions of automatic POS person creation were replaced
with explicit synthetic approvals. A pre-migration ORM insert was replaced by a
schema-appropriate SQL insert. A Windows CRLF-sensitive CSS assertion was
normalized; print CSS itself was not changed. These final checks passed.

## 6. Traceability and recovery

Architecture: Employee Directory README, Domain Architecture, Workforce README,
Products README, Project Management README, Identity & Access README.
Main implementation: employee_directory.py, models.py, person migration;
Bank card configuration; profile bootstrap; acquisition/ingest; project service;
directory/project/account/Selection/Training routes and their relevant templates.
Tests: test_employee_directory.py, test_person_foundation.py, directory/projects
HTTP tests and explicit-approval acquisition fixtures. Earlier step 1/2 files
remain part of the cumulative local change.

Staged guard package: %TEMP%/rfone-person-foundation-release-096ajgmu.
Test logs: %TEMP%/rfone-person-*.log. Startup manifest uses normalized LF bytes.
Recovery baseline: commit 9764ef6 and the prior deployed release records in
EMPLOYEE_DIRECTORY_UI_001_RELEASE.json. During local implementation no production backup was needed because
no production data or service was changed; the later AWS release has its own verified snapshot.
