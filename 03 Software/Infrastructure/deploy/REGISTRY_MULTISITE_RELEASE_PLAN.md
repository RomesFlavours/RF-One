# Release and switch-over plan — new multi-site Registry (REGISTRY_MULTISITE_001)

Status: **prepared, not executed.** Nothing on AWS has been changed. Executing any step requires Codex's
independent review of branch `feature/registry-multisite` and the Product Owner's (Pino's) authorization.

Specification: `07 Tasks/REGISTRY_MULTISITE_001.md`. Code: `feature/registry-multisite`
(`4ab0b04` = unchanged port of the uncommitted OQ-7 Training work, `e8a44b5` = this change), based on
`feature/clover-multisite-registry` `acd44b2`.

## 0. Read-only findings on AWS (2026-11-22)

Two one-off `ecs run-task` reads of the existing task definition `rfone-clover-correction-sync:12`, session
`default_transaction_read_only=on` (tasks `1e52e2833af74c2ea6999ae496c54b10`, `05f22f499d0d4f36a38cc7db08076918`;
CloudWatch `/ecs/rfone-clover-correction-sync`). RDS revision `a1c220261121`.

| Question | Data on AWS | Conclusion |
|---|---|---|
| Are there MD assignments? | `employee_assignments`: 29 rows, **all** restaurant 1 (WP), source `CLOVER_ROLE_SYNC`; 0 at MD (restaurant 4) | no wrong MD assignment is saved |
| Clover links at MD? | 73 links, all merchant `PYQYB7SKB6V31` (WP); MD location 2 inactive, 0 links | nothing at MD |
| Company membership MD? | 4 memberships, all of account 4 (WP, MD, RF Gelati, RFGroup); 0 people | membership does not place people at MD |
| Cards' own site | all 72 employees `location_id = 1` | — |

**MD shows WP because of how the pages read, not because of saved data.** The live Registry list ignores
the company selector (an administrator always sees everybody), and the Anagrafica groups people by Clover
links and the card's `location_id`, which are WP for everyone. The new code lists a site only from explicit
assignments and never falls back to another site. The migration therefore has **no MD assignment to recover**
and copies nothing from WP to MD.

## 1. What the migration does

`c7d820261122` (down `b2c320261121`), **data only**: records the explicit EMPLOYEE status for every person
already linked to a card (`person_employee_links`), because a card alone no longer means Employee (a Trainee
has a card too) — **except** the Trainees whose card was linked by the new Training entry (card event
`TRAINING_LINK`, written only by the new code), so that a re-upgrade after a rollback never turns them into
Employees. The exact list is computed by the same SQL in the migration and in
`registry_multisite_migration_check.py` (`report` → `employee_status_to_record`, `snapshot` →
`employee_status_expected`); `compare` passes only if exactly that list is added. On the AWS data (read-only
export of 2026-11-22, loaded into a copy): 0 links → **expected list `[]`, added `[]`**. No identity,
assignment, Clover link or Tips row changes.

**Final revision and release order (resolved 2026-11-22).** `a1c220261121` (live) → `b2c320261121`
(CLOVER_MULTISITE_001) → **`c7d820261122`** (this release; final revision on AWS after it). REGISTRY_MULTISITE_001
ships before RF1 shared acquisition (still waiting for a Product Owner decision on the AWS poller), so
`c4d520261121` was re-parented onto `c7d820261122` in `rfone-wt/rf1-shared-acquisition` (uncommitted there,
like the rest of that work); with it the chain has one head (`c4d520261121`), up and down verified locally.
If RF1 ever had to ship first, the inverse re-parenting (c7d8 onto c4d5) is needed instead.

**Exact `c4d520261121` used for the combined graph.** It is not committed on any branch (in
`feature/rf1-shared-acquisition` the file is only marked intent-to-add, empty blob). The exact bytes used are
stored, unchanged, in this branch as
`07 Tasks/Reports/REGISTRY_MULTISITE_001_evidence/c4d520261121_shared_acquisition_requests_and_tips_period.py.txt`:
Git blob `cc1ae8cea619f9ea746eba60220de3b2b5a8469e`, SHA-256
`0b9d567c562a0677cf4e2a9680f1be8182bed66fb60d478875a039866fe118be`, `down_revision = 'c7d820261122'`.
Difference from the original: only `down_revision` (`b2c320261121` → `c7d820261122`) and a "Release order"
note in the docstring. When RF1 is committed, its `c4d520261121` must have this blob (or be re-verified).

## 2. Doubtful cases to verify before the switch-over (from the AWS data)

| # | Case | People | What happens after the switch |
|---|---|---|---|
| 1 | Active cards with no assignment (no site) | 37 Diego, 38 Jen kitchen, 39 Leonel Espinoza, 45 Anthony Watler, 91 Arthur ruvinsky, 92 Carlos Rosas, 96 Austin Blount | listed under «People without a site», at no site, until a site is assigned on the card |
| 2 | Dismissed cards with an open WP assignment | 35 Giovanna Toaldo, 55 Giulia Pagliaro, 56 Emily Garcia | still counted at WP by the site list; Registry shows them under Dismissed |
| 3 | Trainee without a card | person 343 Terry Muller (STUDENT, Training account 14) | at no site; a new Training invitation with the site creates the card |
| 4 | Former pending Clover identity | link 73, POS `DETG07X2M2804`, «Anna Friend» (WP) | no longer proposed; her work waits as unattributed until a POS ID is typed on a card |
| 5 | Company membership in MD without people | account 4 only | no effect on the lists |
| 6 | Assignments written by the former automatic Clover sync | 21 open at WP | kept as Registry history (they are the WP list) |

The report is reproducible: `python registry_multisite_migration_check.py --url <url> report`.

## 3. Components and what is deactivated

| Component (AWS) | New code | Old-flow part deactivated by the switch |
|---|---|---|
| App Runner `rfone-web` | Registry and Anagrafica site lists, manual entry with site, card sites + POS ID, Tips validation link text | «Clover identities to confirm» and its `clover_confirm` action; «Links to reconcile»; «Sync now» on Anagrafica; routes `/administration/employees/links/<id>/confirm` and `/administration/employees/sync-now` |
| ECS service `rfone-clover-correction-sync` (now `:12`) | jobs image of this branch, **same command** (`--location-id 1`) | staff-list read and Registry import at the start of every cycle (`_refresh_employees`), legacy-link seeding, Registry role sync (`sync_site`); the roster-only Mount Dora refresh and its `--roster-restaurant-id` flag (not used on AWS today — confirm the task definition does not pass it) |
| ECS task `rfone-clover-acquisition-job` (now `:12`) | same jobs image | staff-list read + Registry import and historical identity reader (`_resolve_historical_employee`) in Sync Now / Historical Backfill; the Historical Backfill read of `/employees?expand=role` that wrote the cards' Clover roles (`EmployeeSourceRole`); the staff list as a pre-flight source (`source_guard.CORE_SOURCES`) |
| ECS task `rfone-clover-live-sync` (`:1`) | same jobs image if it is still run | same as the acquisition job |
| App Runner `rfone-tips` | Data Store of this branch (unattributed-work rule, message text) | — (reads only) |
| App Runner `rfone-trainer-test` (the Server Course) | `Server Course/` of this branch: no site needed for an invitation; the course indicates the role Server; same email → same code (automatic resend) | the hand-off fallback to Winter Park |
| App Runner `rfone-training` (the Training service, image `rfone-web:training-*`, serves `training_cloud`) | invitation without a site (optional catalog role trained for); Confirm hire writes on the card; Server Course invitation with the catalog Server role, automatic resend | — |

Kept: Clover acquisition of shifts, orders, payments and refunds for Tips; existing Clover links (POS IDs)
and the work they attribute.

## 4. Steps (one at a time; verify before the next)

0. **Backup** — manual RDS snapshot `rfone-dev-pre-registry-multisite-<UTC>`; record its ARN.
1. **Preconditions** — Codex review closed; CLOVER_MULTISITE_001 release state decided (b2c3 applied
   before or together); `c4d520261121` re-parented if it ships; Training service identified; How Works
   check `python "03 Software/Shared UI/check_how_works.py" --app "RF-One Web" --rev <commit> --since <live>`
   with no new error (local result: same 24 inherited errors as the base, +2 pages with help).
2. **Read-only pre-check** — `registry_multisite_migration_check.py report` and `snapshot --json before.json`
   on RDS (read-only task as in §0). Record `employee_status_to_record` (expected today: `[]`). The snapshot
   also holds the **permissions**: the grants (`permission_grants`: accounts' status/administrator/owner,
   Domain accesses, selected items and companies, memberships, role profiles, role permissions) and the
   **effective permissions** (`effective_permissions`: for every account and Domain, may enter / administers /
   restaurants reached, computed by RF-One's central rules). At `a1c220261121` the missing `company_scope` is
   read as `ALL` (the default `b2c320261121` gives every existing access), so before and after compare on the
   same terms.
2a. *(Removed, Product Owner 2026-11-22.)* No catalog step is a prerequisite for Training: the invitation
   belongs to the person and needs no site, and Registry reads its role catalog as common to every site, so
   the existing «Server» role (id 3, stored with restaurant 1) is the catalog's Server for everybody without any
   data change. Read-only finding kept for reference (task `15ad0c6e3e5a4d7d8e907a705cfe0303`): role 3 is the
   only Server role, area 1. Aligning the stored `restaurant_id` of the five WP roles is not part of this release
   (Tips still reads it; spec §Correction).
3. **Migration** — one-off migration task (image built from the full development tree, as for
   `a1c220261121`): `alembic upgrade c7d820261122`.
4. **Post-check** — `snapshot --json after.json`; `compare before.json after.json` must be `identical: true`
   with `employee_status_exact: true` (added = the list of step 2) **and `permission_changes: []`** — any grant
   or effective permission added, changed or revoked fails the check (exit 1) and is listed; `alembic current` =
   `c7d820261122`. Proved locally on a database built by the real chain to `a1c220261121`: upgrade → identical,
   permissions included; a simulated revocation, a simulated grant and an administrator flag each make `compare`
   fail and name the account and Domain (`test_registry_multisite_permissions.py`, §6).
5. **Workers** — new revisions of `rfone-clover-correction-sync` and `rfone-clover-acquisition-job` with
   the jobs image, same command. Never ship a migration file whose parent is missing in the worker image.
6. **rfone-web**, then **rfone-tips**, then **`rfone-trainer-test` → `rfone-training`** (in this order: the new
   course works with the current Training, which reads only the email; the new Training reads the role the new
   course indicates — with an older course it still invites, without a role). English release interface (UI_DEVELOPMENT_LANGUAGE_001);
   the local copy stays Italian.
6a. **«Crea in Clover» stays off** — on every service after its update, read-only:
   `aws apprunner describe-service` for `rfone-web`, `rfone-training`, `rfone-tips`, `rfone-trainer-test` and
   `aws ecs describe-task-definition` for the new worker revisions: `RFONE_CLOVER_EMPLOYEE_CREATE` absent from
   environment and secrets, and no `CLOVER_SANDBOX_API_TOKEN__*`. On a Registry card without POS ID the site
   shows «Creation in Clover is not enabled on this installation» and no «Create in Clover» button; the POS ID
   is typed by hand.
7. **Verification** — Server Course: a test person without a site, one assigned to WP and one assigned to MD ask for the Training account → one invitation and one email each, the card keeps exactly its sites (none added), role Server noted, no other permission (then dismissed). Registry: WP lists the 21 WP-assigned people, MD an empty list, an unknown site a
   notice; no Clover queue anywhere; one correction cycle runs without calling `/employees`
   (CloudWatch); a manual test card at MD appears only at MD (then dismissed).

## 5. Rollback (rehearsed locally, §6)

Principle: **the Clover → Registry flow is never reactivated by a rollback.** The previous workers
(`rfone-clover-correction-sync:12`, `rfone-clover-acquisition-job:12`, `rfone-clover-live-sync:1`) read the staff
list and create Registry links/proposals at every cycle (proved in the rehearsal, phase 6), so they are never
restored.

| Component | Rollback | Time |
|---|---|---|
| Workers already started (correction sync, acquisition job) | Keep the new jobs image. On a worker defect: `aws ecs update-service --cluster rfone-jobs --service rfone-clover-correction-sync --desired-count 0` (stop), fix forward, start again. Never `:12`. Do **not** deregister the new acquisition revision: the previous RF-One Web «Sync now» launches the latest ACTIVE revision, which then stays the new one (no staff-list import). While stopped, Tips waits (readiness gate) and nothing is lost: the next cycle re-reads the window. | minutes |
| Live Sync | Stays off (`rfone-clover-live-sync` not launched; `RFONE_CLOVER_LIVE_SYNC_ENABLED` unchanged). If it must run, only with the new jobs image (rehearsal phase 7: no Registry change). | — |
| Data step **before** restoring any previous app image | `registry_multisite_rollback.py plan`, then `detach --record links.json --apply`: sets aside (file + removal) the card links the new Training entry wrote for Trainees who are not Employees; otherwise the previous code would show them as Employees (rehearsal phase 4). Cards, site assignments, POS IDs, Tips rows unchanged. The record file is written atomically before any removal and is never emptied: a repeated `detach` on the same path keeps the saved links and adds only new ones (rehearsed: two consecutive detaches). Copy `links.json` to the step-0 backup folder right after the first detach. | minutes |
| Migration | `alembic downgrade b2c320261121` (no-op). Restore the step-0 snapshot only if a data defect is proven. | minutes |
| rfone-tips, Training service | App Runner back to the digests recorded at step 0. | ~5 min each |
| rfone-web | Prefer fix forward. Restoring the previous image brings back its «Clover identities to confirm» queue, which lists every Clover link without a person: the former pending identity (Anna Friend) and every POS ID detached by a correction (`plan` → `previous_registry_queue_would_show`); confirming one there would attach it from Clover data. Its «Sync now» stays harmless (new acquisition revision). Restore the previous web image only with Pino's explicit decision. | ~5 min |
| Roll-forward | Deploy the new images again, `reattach --record links.json --apply`, `alembic upgrade head`, `compare` (expected and added: `[]`; the Trainees stay Trainees). `reattach` exits with code 2 and writes nothing when the record is missing, empty or unreadable, or when a recorded link cannot be back exactly (card meanwhile linked to another person): stop and review those cards before continuing. On success every recorded link is read back (`verified: true`). | minutes |

Data written by the new code meanwhile: cards, site assignments and POS IDs are ordinary rows the previous code
reads; POS IDs keep attributing work (rehearsal phase 5); attributions already resolved are never moved.

## 6. Local evidence (2026-11-22)

- AWS Registry data copy (disposable PostgreSQL 55497, database `registry_mig`, schema from the models at
  `b2c320261121`, AWS rows loaded): `upgrade → c7d820261122` → fingerprints identical; `downgrade` →
  identical; probe with one card link → EMPLOYEE added only for that person.
- Full local copy (3,574 shifts, 13,732 orders, 14,748 payments, 80 tip entitlements): data step applied
  → identities, links, assignments, shift/order/payment/refund attributions and tip entitlements identical.
- **Duplicate-column error (diagnosed and fixed).** On any database built from an empty schema the chain
  stopped at `k9g120261112` with `duplicate column name: elapsed_preparation_minutes`. Cause: its parent
  `k9a020261110` creates the Kitchen tables from the *current* Python models (`create(checkfirst=True)`), which
  already carry the columns and indexes that `k9g120261112` then added unconditionally. AWS is not affected
  (k9a ran there with the older models, and AWS is already past k9g). Fix: every step of `k9g120261112` is
  skipped when its object already exists; on a database without them it runs exactly as before. No schema
  change. Result: the full chain now reaches `c7d820261122` on empty SQLite and on empty PostgreSQL.
- PostgreSQL migration test 2026-11-22 (disposable cluster, port 55498, deleted afterwards): schema built by
  the real chain from empty to `a1c220261121` (the Selection app's own tables created at `r9a120261113`, as
  the Selection service does on AWS, because `t9e120261113` references them); every AWS Registry row of the
  read-only export loaded with **no missing column**; report = WP 21, MD 0, the same doubtful cases as §2;
  `upgrade head` (runs **`b2c320261121`** and `c7d820261122`) → `compare identical: true`; `downgrade
  b2c320261121` → identical; upgrade again → head.
- The canonical local database (`rfone_aws_copy`) is on the local development line (`k9f120261112`,
  `t9d120261113`), whose revision files are not in the AWS release line this branch follows: `alembic upgrade`
  cannot run on it from this branch. Not needed for AWS; its read-only report shows WP 15, MD 0.

### Codex review fixes (2026-11-22, after 8efaba0)

- Tips: a re-read or corrected Clover record keeps an attribution already resolved (`ingest.keep_resolved_attribution`,
  used by both upsert helpers); records without a person stay attributable. Case reproduced: order of A → POS ID
  correction → reimport → old ID given to B → reimport: the order stays A's (also payments and shifts); fails
  without the fix.
- Training: the Registry identity is resolved before anything is written (`employee_directory.resolve_training_card`);
  uncertain matches (same phone only, several cards, different phone) ask for confirmation; Selection path records
  the arrival only after that.
- Confirm Hire: requires the linked card; legacy Trainees get card and site via «Resolve card and site».
- Rehearsal `registry_multisite_rollback_rehearsal.py --old-tree <acd44b2 checkout> --extra-versions <dir with
  c4d520261121>`: ALL EXPECTATIONS MET (phases 1–9 above).
- AWS data copy (SQLite, chain-built to `a1c220261121`, 924 exported rows, no missing column): report WP 21, MD 0;
  upgrade → `c7d820261122`; `compare` identical, EMPLOYEE expected `[]`, added `[]`.

### Codex review 3 fixes (2026-11-22, after 2c643b7)

- Training: the operator's card choice carries the evidence shown (`card:<id>@<digest>` / `card:new@<digest>`,
  digest of matching cards, what matched, contact and sites). At submission it is re-checked: if the matching
  cards changed in the meantime, `CardConfirmationRequired(changed=True)` shows the updated options and no
  person, card, Trainee mark, arrival or invitation is written. Same rule on the direct invitation, Send to
  Training and «Resolve card and site».
- A US number with or without `+1` gives the same phone evidence (`employee_directory.phone_evidence`, also used by
  `training.enrollment.phone_key`, as Selection's `normalize_phone`); a phone-only match still asks the operator.
- Rollback: record file protected (atomic write, kept on a repeated detach); `reattach` fails explicitly and
  verifies every link. Rehearsal (now also on PostgreSQL with `--url`): two consecutive detaches keep the
  Trainee link in the record; reattach refused on a copy where the card was taken and with a missing record;
  reattach then restores and verifies it; the Trainee is still a Trainee on the same card. SQLite and
  PostgreSQL (disposable cluster, port 55499, deleted afterwards): ALL EXPECTATIONS MET. Outputs:
  `07 Tasks/Reports/REGISTRY_MULTISITE_001_evidence/rollback_rehearsal_round3_{sqlite,postgresql}.json`.

### Codex review 4 fixes (2026-11-22, after 409ce8f)

- Server Course resend: the new link is emailed first; the link already received stays valid until the email
  service accepts the new email, then the same invitation takes the new link. A refused send changes nothing;
  an invitation activated meanwhile is never reopened. Tests on WP and MD: success, failure, activation during
  the resend (`RF-One Web/tests/test_server_course_invite_http.py`).
- Permissions in the before/after check (§4 steps 2, 2a, 4): `test_registry_multisite_permissions.py` builds a
  database by the real chain to `a1c220261121` (no `company_scope`), seeds accounts, Domain accesses,
  companies, a membership and a role profile; snapshot → upgrade head → snapshot: identical, effective
  permissions included; a revocation (one access disabled), a new access and an administrator flag each make
  `compare` exit 1 with the account/Domain in `permission_changes`.

