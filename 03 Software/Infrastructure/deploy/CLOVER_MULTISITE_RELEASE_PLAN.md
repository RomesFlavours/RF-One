# Coordinated release plan — Registry + Clover multi-site + Tips (CLOVER_MULTISITE_001)

Status: **PLAN ONLY — not executed** (updated 2026-11-21: payment audit, combined Tips release with
TIPS_REGISTRY_ROLES_001/002, one release branch per AWS component built from its live code).
Every step needs the Product Owner's explicit authorization.
Mount Dora (MD) stays **inactive** throughout; activation is a separate, later decision.
No payment is made by this release; Payment Control is still the Mercury Sandbox pilot.

## 0. Live state and rollback targets (read-only, re-read 2026-11-21 ~13:00 UTC)

| Component | Live now (rollback target) | Image digest |
|---|---|---|
| App Runner `rfone-web` | `rfone-web:registry-departments-20261121t030713z-web2` | `sha256:907047129357db0ecac8e85dbac64dbb888197dc09a1f0cc8dc0de00add3aee2` |
| App Runner `rfone-tips` | `rfone-tips:tip-role-history-20261118c-tips` | `sha256:fb453257f1e3b2db907759ba524c8a893f985fba4df88db3559872b6ac03a6ac` |
| ECS service `rfone-clover-correction-sync` | task definition `:12`, command `--location-id 1` | `rfone-tips@sha256:8ba25ab6dfb14adf6bf33200f7746ba858dcd7b9b1cc324ea64b2e8e3ea3f51d` |
| ECS task `rfone-clover-acquisition-job` | task definition `:12` | `rfone-tips@sha256:970c0fe624e8f691692726ec998e4632d811c1e040ef929a9c7c9b5747a9114f` |
| ECS task `rfone-clover-live-sync` | task definition `:1` (`--location-id 1 --once`) | `rfone-tips@sha256:62b68db53ec3e50f3148254396516e96f358501f761eef9293868b408b8dd2d8` |
| RDS alembic | `a1c220261121` | — |
| Latest manual snapshot | `rfone-dev-pre-registry-departments-20261121t030713z` | — |

Earlier read-only checks (2026-11-21, unchanged since): migration `b2c320261121` compatible with RDS
(no `company_scope`, no new table present, FK targets exist; 72 access rows, all scope ALL); WP
restaurant #1 → legal entity 1 → company WP, MD restaurant #4 → legal entity 2 → company MD; Tips
payments on AWS: 0 cycles, 0 instructions, 0 TIPS grants; Compensation status constraint already
includes EXPORTED and CLOSED. Re-read all of §0 immediately before step 0; if anything changed, stop.

## 1. Release branches (local Git, not pushed)

Each branch starts from that service's **live code**, and carries only the authorized changes:
Registry departments (already live in web/workers), Clover multi-site, Tips (multi-site, payment
authorization and audit, Registry roles), permissions. Nothing of Training, Kitchen, Bank, Selection
or other Domains is added: their files are the live ones.

| Component | Branch | Base (live code) | Release commit |
|---|---|---|---|
| rfone-tips | `release/clover-multisite-tips-20261121` | `2274373` = live snapshot `76b32c8` (image `tip-role-history-20261118c-tips`), line endings only | `9e45626` |
| rfone-web | `release/clover-multisite-web-20261121` | `7580fa2` = `release/registry-web-20261121` (image `…-web2`) | `c08b2b5` |
| Clover workers | `release/clover-multisite-jobs-20261121` | `7b5d35c` = `release/registry-clover-jobs-20261121` (correction `:12`) | `c968fb5` |
| Development line | `feature/clover-multisite-registry` | integration tree `6633f05` | commit of this plan |

### 1.1 Exact content

**rfone-tips** (only `RF-One Data Store/`, `Tips/`, `Shared UI/` change; RF-One Web, Training,
Infrastructure stay at the live snapshot):
- `89417b8`, `57a8f22`, `1dc32c1` = `7633da7`, `d71808d`, `36f3ef5` of `feature/tips-registry-roles`
  (TIPS_REGISTRY_ROLES_001/002 + defect note). **PO decision 2026-11-21 (relayed by the
  tips-registry-roles session): only these three.** The uncommitted TIPS_RULE_END_OF_VALIDITY_001
  work and its table are **not** included.
- `8f7c97a`, `bdfd6d3` = Registry departments `d8b3eb1`, `433b8b4` (already live in web/workers;
  needed by the Registry role reading and the import).
- `1214012`, `9cf7d33`, `d367b05`, `941c63a`, `e87fe8a`, `b8dfba8`, `72db10f` = multi-site
  `6ab48e5`(-m 1), `cec9619`, `1b1ee48`, `d459f66`, `0947cc9`, `8c26bce`, payment audit `f2c3c55`.
- `f2cc550` packaging: no migration file in this image (its chain ends at `t9a120261110`); RF-One Web
  and worker deploy files reset to the snapshot.
- `9e45626` obsolete tests updated (shared-schema head, record holds, historical payments stub).

**rfone-web**: multi-site `6ab48e5`(-m 1), `cec9619`, `1b1ee48`, `d459f66`, `f2c3c55` ported as
`95c924c`, `923f009`, `2c193d1`, `71c0d73`, `386e417`; `6eb9701` registers the four Helps
(Clover Acquisition, saved periods list and run, account Access) and records RDS `a1c220261121`;
`c08b2b5` passes the Registry translator to the live How Works component on those pages (without it
they answered 500 on the live web code) and updates obsolete tests.
Kept at the live web version: the Tips calculation engine and its validations (the web image does not
calculate tips), `Tips/`, `Infrastructure/`. Carries migration `b2c320261121`.

**Clover workers**: `4235a35` = the worker part of `6ab48e5` (Clover connector, employee directory,
shift location, `test_clover_multisite`); `a3cc502` start check also runs `test_clover_multisite`,
manifest `clover-multisite-20261121-jobs`; `c968fb5` obsolete tests updated and manifest digests
recomputed. No migration file.

### 1.2 Images to build (record the pushed digest of each before deploying)

| Image | Built from | Replaces |
|---|---|---|
| `rfone-web:clover-multisite-<UTC>-migration` (one-off, never served) | development line `feature/clover-multisite-registry` (full Data Store: alembic loads every revision file, including `t9e120261113`, which imports Training code absent from the web image) | — (same recipe as `…-migration2` of 2026-11-21) |
| `rfone-web:clover-multisite-<UTC>-web` | `c08b2b5` | `sha256:90704712…aee2` |
| `rfone-tips:clover-multisite-<UTC>-tips` | `9e45626` | `sha256:fb453257…a6ac` |
| `rfone-tips:clover-multisite-<UTC>-jobs` | `c968fb5` | `sha256:8ba25ab6…f51d` (correction), `sha256:970c0fe6…114f` (acquisition) |

ECR tags are mutable: task definitions and App Runner use the **digest**.
Build source = `git -c core.autocrlf=false archive <commit>` (LF): the worker manifest holds git-blob
digests; a CRLF checkout fails the start check ("Runtime artifact mismatch"). Verified 2026-11-21 on an
LF archive of `c968fb5`: `CLOVER_RELEASE_VERIFIED`, 36 tests, artifact verified.

## 2. What changes for people

| Component | Change |
|---|---|
| Clover workers | none for WP. Per-merchant credentials; inactive sites never acquired; cross-site roster guard; Shift Location certain or pending |
| Tips | Restaurant selector (WP selected, MD inactive); inactive site refused; role of a person read only from Registry (Anagrafica > Reparti e ruoli) |
| Tips Payment Control | approver = signed-in account; Approve & Pay and retry need restaurant access + payment authorization; retry never pays twice; **every step audited** (account or system, date and time) |
| RF-One Web | Clover Acquisition selector + Help; Tips saved periods per restaurant + Help; Compensation summary Location text; account Access page: restaurants per Domain + payment authorizations + Help |
| Database | one additive migration `a1c220261121 -> b2c320261121`: column `rfone_account_domain_access.company_scope` (default `ALL`), tables `rfone_account_domain_company_access` and `tip_payment_audit_events` (empty). No data changed |

## 3. Preconditions (all required)

1. PO authorization of this plan and of each step.
2. Release commits fixed (§1); push of the three release branches only on the PO's instruction.
3. Local regression green on each release commit (§7).
4. No other session deploying Clover workers, Tips or RF-One Web. The `feature/tips-registry-roles`
   session confirmed it will not deploy `rfone-tips`: this is the **one** Tips release.
5. §0 re-read immediately before step 0.
6. **Registry role correspondences for Winter Park complete (blocking for Tips):** Tips now reads the
   Clover role → RF-One role only from `registry_role_mappings`. Before step 4, read-only on RDS:
   every Clover role observed in WP in the periods to be calculated has a current mapping with an
   RF-One role:
   ```sql
   SELECT DISTINCT sr.id, sr.name
   FROM employee_source_roles esr JOIN source_roles sr ON sr.id = esr.source_role_id
   JOIN restaurant_locations rl ON rl.location_id = sr.location_id AND rl.restaurant_id = 1
   WHERE NOT EXISTS (SELECT 1 FROM registry_role_mappings rm WHERE rm.restaurant_id = 1
     AND rm.source = 'CLOVER' AND rm.original_key = sr.source_role_id AND rm.valid_to IS NULL
     AND rm.restaurant_role_id IS NOT NULL);
   ```
   Expected: no rows. Rows = define them in Anagrafica > Reparti e ruoli first (otherwise every WP
   calculation is blocked and names the role). Not yet run (no database access in this preparation).
7. How Works check: `rfone-tips` 0 errors. `rfone-web`: 3 errors **already present in the live web
   code** (`email_control.html`, `email_detail.html`, `forgot_username.html`, pages of other
   releases, not changed here) — PO decision required (author their Help in their own release, or
   accept them as inherited) before `release_selection.py` can pass.

## 4. Steps (one component at a time; verify before the next)

**Step 0 — Safety snapshot.** Manual RDS snapshot `rfone-dev-pre-clover-multisite-<UTC>`.

**Step 1 — Migration `b2c320261121`.** One-off ECS task with the migration image (§1.2), command
`alembic upgrade b2c320261121`. Verify: alembic = `b2c320261121`; every `rfone_account_domain_access`
row has `company_scope = 'ALL'`; `rfone_account_domain_company_access` and
`tip_payment_audit_events` exist and are empty; the live services (old code) still answer — they
neither read nor write the new objects. Publish `aws_applied_revision.json` = `b2c320261121`.

**Step 2 — Clover workers.** Register new revisions of `rfone-clover-correction-sync` and
`rfone-clover-acquisition-job` with the jobs image digest, the **same command** as today
(`--location-id 1`) and the **same secrets** (WP pair only). Update the correction service.
Verify: start check prints `CLOVER_RELEASE_VERIFIED` with release `clover-multisite-20261121-jobs`;
3 consecutive cycles for location 1 COMPLETE; no cycle for location 2; WP `directory_links` and
employee counts unchanged.

**Step 3 — RF-One Web.** Deploy the web image. Verify: Clover Acquisition opens on WP with Help;
Tips saved periods list WP only; a past WP Compensation Period Summary shows the same hours as
before, with no "no certain Location" warning; Settings › Accounts › Access shows "All companies"
for every existing account and the Payment authorizations section; Helps open.

**Step 4 — Tips** (only after precondition 6). Deploy the Tips image. Verify on WP:
- selector shows WP selected and MD "inactive";
- a known saved period shows the same totals as before;
- Calculate on a past WP period: no "Clover role" block, run notes `shifts_without_certain_location=0`;
  recalculate in memory one past WP FINAL period and compare with its stored entitlements (identical;
  stored FINAL runs, entitlements and payments are never recalculated automatically);
- Payment Control shows "Approving as <signed-in name>"; without a payment authorization the button
  is disabled with the reason. No payment is executed for the verification.

**Step 5 — Acquisition (WP).** One Sync Now for WP from RF-One Web. IngestionRun COMPLETE; orders,
payments and shifts get location 1; nothing written for location 2.

**Step 6 — Poller multi-site (optional, behaviour-neutral while MD is inactive).** New
correction-sync revision with `--all-active-locations`; cycles still run for location 1 only.

**Step 7 — Payment authorizations (data, separate PO authorization).** An administrator ticks
"Tips — Approve & Pay" for WP on the Access page of each approver named by the PO; nothing is granted
automatically. Every later preparation, approval, execution and retry is recorded in
`tip_payment_audit_events`.

## 5. Rollback

| Failure in | Action | Time |
|---|---|---|
| Step 1 | Not expected (additive, empty). The old code ignores the new objects, so leave them. `alembic downgrade a1c220261121` only after every new image is rolled back and only if the new tables are still empty (it drops them). | minutes |
| Step 2/6 | `aws ecs update-service --cluster rfone-jobs --service rfone-clover-correction-sync --task-definition rfone-clover-correction-sync:12`; deregister the new acquisition revision (the web launcher uses the family's latest ACTIVE revision → `:12`). | minutes |
| Step 3 | App Runner `rfone-web` back to digest `sha256:90704712…aee2` (`…-web2`). | ~5 min |
| Step 4 | App Runner `rfone-tips` back to digest `sha256:fb453257…a6ac` (`tip-role-history-20261118c-tips`). The old Tips code reads `source_role_mappings` again (empty on AWS: calculations blocked as before the release). | ~5 min |
| Step 7 | Untick the authorization on the Access page (revoked, kept in history). | seconds |
| Payments | None exist on AWS; a rollback never re-executes anything. Audit rows written by the new code stay (append-only history); the old code does not write them. |
| Data anomaly | Code rollback is sufficient (one additive schema change, no data migration). Restore the step-0 snapshot only if a data defect is proven. | — |

## 6. Conditions to activate Mount Dora (separate authorization)

1. Steps 1–5 verified on WP and stable for at least one business day.
2. Execution role `rfone-clover-acquisition-job-execution-role` may read `rfone-tips/clover-md-api-token`;
   **then** add `CLOVER_API_TOKEN__WP3NHX517C0M1` to the worker task definitions (this order).
3. Authorizations reviewed with the PO: narrow on the Access page those who must not see MD; grant MD
   payment authorization only to the intended approvers.
4. MD Registry role correspondences complete (same query as precondition 6 with `restaurant_id = 4`).
5. Optional, if authorized: MD roster refresh and identity confirmation in Registry.
6. PO authorization to set merchant 2 and location 2 `active = true`, then the first MD Historical
   Backfill and verification of MD-only data.

## 7. Local verification of the release commits (2026-11-21)

Each suite is run as its own script on the release commit (`python <test>.py`), disposable SQLite only.

**Test databases.** The rfone-tips and worker chains deliberately stop before `a1c220261121` (no
orphan migration file in those images), and the live web checkout cannot load its chain
(`t9e120261113` imports Training code absent from the web image); on every tree a from-scratch chain
also fails at the Kitchen revision `k9g120261112` (duplicate column — pre-existing, not touched).
So the local runner completes the test schema with the models: rfone-tips/workers = their own
migrations + the missing tables/columns of the models (= RDS after `b2c320261121`); rfone-web =
`create_all` + stamp. Test-only, never in a release. The migration itself was verified separately on
PostgreSQL 18.3 (disposable cluster, deleted): schema at `a1c220261121` from the live web models →
`upgrade b2c320261121` (existing access row → `company_scope = 'ALL'`; both new tables; FK and actor
constraints enforced) → `downgrade a1c220261121` (column and tables gone) → `upgrade` again: OK.

| Tree (commit) | Files | Failed files | vs live code |
|---|---|---|---|
| rfone-tips `9e45626` | 56 (193 unittest cases + validation scripts) | **0** | live snapshot: 5 failing files (all fixed or obsolete-updated) |
| Clover workers `c968fb5` | 20 (98 cases) | 1: `test_clover_acquisition_safety` (no `registry_departments` on the worker chain) | same failure on live `7b5d35c`; passes with the completed schema |
| rfone-web `c08b2b5` | 71 (165 cases) | 10, **all also failing on live `7580fa2`** (14 there) | no new failure |

Pre-existing web failures (live code too, not changed here): Training/Dev-Journal tables absent from
the models (home, accounts, admin permissions, item access), `templates/help` directory scan, the
alembic-based `SharedDatabaseRuleTests`, the Tips app copy inside the web tree (not in the image).

Covered: Clover (acquisition, jobs, safety, correction, live sync, freshness, employee history,
identity holds, monthly recovery, line presence, multi-site); Tips (distribution engine, rules,
flexible engine, Registry roles 11/11, order owner, host audit, stateless, finalized period, payment
execution, connector, readiness, scheduler, final-release blockers, historical payments, all Tips HTTP
suites); Compensation (period, summary, approval, v1, payroll engines, overtime matrix); Registry
(`test_registry_departments`); permissions and payments (`test_multisite_permissions` 39 incl.
WP/MD reach, double approval, retry never paying twice, audit rows; `test_payment_control_authorization_http`
5; `test_account_access_multisite_http` 5; `test_clover_acquisition_multisite_http` 7;
`test_tips_validation_multisite_http` 5; `Tips/test_multisite_selection_http` 11). How Works:
rfone-tips 0 errors; rfone-web 3 inherited errors (precondition 7).

**Obsolete tests updated (behaviour unchanged):** shared-schema single head ×2 and private-SQLite
head (hard-coded old revision); person foundation (record holds since
EMPLOYEE_DIRECTORY_RECORD_HOLD_001); historical tip payments HTTP (account stub, merchants table);
three web multi-site HTTP tests (live How Works markup); `test_clover_multisite` consumer assertions
per image; plus the five already updated in `1b1ee48` (TIPS grant, selector GET, help directory,
Compensation summary text, employee-directory selector).
