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
has a card too). AWS has 0 such links → writes nothing there. No identity, assignment, Clover link or Tips
row changes. Former pending Clover identities stay in `employee_clover_links` as history; no screen or job
shows or proposes them.

Chain on AWS: `a1c220261121` (live) → `b2c320261121` (CLOVER_MULTISITE_001, not yet applied) →
`c7d820261122`. **Conflict to resolve before release:** `feature/rf1-shared-acquisition` carries
`c4d520261121`, also with down revision `b2c320261121`; whichever ships second must be re-parented.

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
| ECS task `rfone-clover-acquisition-job` (now `:12`) | same jobs image | staff-list read + Registry import and historical identity reader (`_resolve_historical_employee`) in Sync Now / Historical Backfill |
| ECS task `rfone-clover-live-sync` (`:1`) | same jobs image if it is still run | same as the acquisition job |
| App Runner `rfone-tips` | Data Store of this branch (unattributed-work rule, message text) | — (reads only) |
| Training service (the one serving `training_cloud`) | invite form with training site and role; Confirm hire writes on the card | — |

Kept: Clover acquisition of shifts, orders, payments and refunds for Tips; existing Clover links (POS IDs)
and the work they attribute.

## 4. Steps (one at a time; verify before the next)

0. **Backup** — manual RDS snapshot `rfone-dev-pre-registry-multisite-<UTC>`; record its ARN.
1. **Preconditions** — Codex review closed; CLOVER_MULTISITE_001 release state decided (b2c3 applied
   before or together); `c4d520261121` re-parented if it ships; Training service identified; How Works
   check `python "03 Software/Shared UI/check_how_works.py" --app "RF-One Web" --rev <commit> --since <live>`
   with no new error (local result: same 24 inherited errors as the base, +2 pages with help).
2. **Read-only pre-check** — `registry_multisite_migration_check.py report` and `snapshot --json before.json`
   on RDS (read-only task as in §0).
3. **Migration** — one-off migration task (image built from the full development tree, as for
   `a1c220261121`): `alembic upgrade c7d820261122`.
4. **Post-check** — `snapshot --json after.json`; `compare before.json after.json` must be `identical: true`.
5. **Workers** — new revisions of `rfone-clover-correction-sync` and `rfone-clover-acquisition-job` with
   the jobs image, same command. Never ship a migration file whose parent is missing in the worker image.
6. **rfone-web**, then **rfone-tips**, then the **Training service**. English release interface
   (UI_DEVELOPMENT_LANGUAGE_001); the local copy stays Italian.
7. **Verification** — Registry: WP lists the 21 WP-assigned people, MD an empty list, an unknown site a
   notice; no Clover queue anywhere; one correction cycle runs without calling `/employees`
   (CloudWatch); a manual test card at MD appears only at MD (then dismissed).

## 5. Rollback

| Step | Rollback | Time |
|---|---|---|
| 5 workers | `aws ecs update-service --cluster rfone-jobs --service rfone-clover-correction-sync --task-definition rfone-clover-correction-sync:12`; deregister the new acquisition revision (launcher uses the latest ACTIVE → `:12`) | minutes |
| 6 web / tips / training | App Runner back to the digests recorded in `CLOVER_MULTISITE_RELEASE_PLAN.md` §0 (or the ones live at step 0) | ~5 min each |
| 3 migration | `alembic downgrade b2c320261121` (no-op: the explicit EMPLOYEE rows equal what the old code derives); restore the step-0 snapshot only if a data defect is proven | minutes |
| Data written meanwhile | cards, site assignments and POS IDs written by the new code are ordinary Registry rows that the old code reads; unattributed work typed via POS ID stays attributed (the old code would have done the same after a confirmation) | — |

## 6. Local evidence (2026-11-22)

- AWS Registry data copy (disposable PostgreSQL 55497, database `registry_mig`, schema from the models at
  `b2c320261121`, AWS rows loaded): `upgrade → c7d820261122` → fingerprints identical; `downgrade` →
  identical; probe with one card link → EMPLOYEE added only for that person.
- Full local copy (3,574 shifts, 13,732 orders, 14,748 payments, 80 tip entitlements): data step applied
  → identities, links, assignments, shift/order/payment/refund attributions and tip entitlements identical.
- Not exercised on PostgreSQL: `b2c320261121` itself (validated by CLOVER_MULTISITE_001; it needs the Tips
  payment tables that the registry-only copy does not contain).
