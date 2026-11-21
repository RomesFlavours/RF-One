# Coordinated release plan — Registry + Clover multi-site + Tips (CLOVER_MULTISITE_001)

Status: **PLAN ONLY — not executed** (updated 2026-11-21 for the multi-site permissions and payment security fixes). Every step needs the Product Owner's explicit authorization.
Mount Dora (MD) stays **inactive** throughout; activation is a separate, later decision.

## 0. Pre-release verification (2026-11-21, read-only, nothing changed on AWS)

| Check | Result |
|---|---|
| Live services | unchanged since this plan: web `…-web2` (digest `sha256:90704712…`), tips `tip-role-history-20261118c-tips` (`sha256:fb453257…`), correction `:12`, acquisition `:12`, live sync `:1`, all ACTIVE |
| RDS | PostgreSQL 18.3, alembic `a1c220261121` |
| Migration `b2c320261121` against RDS | compatible: `rfone_account_domain_access` has no `company_scope` and no conflicting constraint; the new table and index do not exist; FK targets `rfone_accounts`, `rfone_company_contexts` exist; 72 access rows (TIPS 7, CLOVER_ACQUISITION 6, all scope ALL). Adding a column with a constant default is a catalogue-only change on PostgreSQL ≥ 11 (no table rewrite). `check_migration_chain.py`: head `b2c320261121` contains `a1c220261121`. |
| Company mapping | WP restaurant #1 → legal entity 1 → company WP; MD restaurant #4 → legal entity 2 → company MD; RFGroup = GROUP |
| Tips payments on AWS | 0 payment cycles, 0 payment instructions, 0 TIPS authority grants, 0 account identities: no payment can be duplicated or lost by release or rollback; nobody can approve today either |
| Compensation status constraint on RDS | already includes EXPORTED and CLOSED (= the corrected model) |
| Live code not in the branch | none: every live-only line (web, Tips, workers) is an older version replaced by the branch |
| Branch content not live | the branch is built on the integration tree `6633f05`, which also carries other sessions' work not published in `rfone-web`/`rfone-tips` (e.g. Training courses and activation links, Kitchen menu areas, Bank WHO picker styles, AI client timeouts, database pool options). See §3 precondition 7. |

## 1. What is released

| Component | Service | Source | Change for people |
|---|---|---|---|
| Clover workers (acquisition job, correction poller, live sync, verification) | ECS `rfone-jobs` task definitions | branch `feature/clover-multisite-registry` | none for WP. Per-merchant credentials; inactive sites never acquired; cross-site roster guard; Registry role sync (already live) kept |
| Tips | App Runner `rfone-tips` | same branch | Restaurant selector; inactive site refused; Shift Location certain or pending |
| RF-One Web | App Runner `rfone-web` | same branch | Clover Acquisition selector + Help; Tips period validation per restaurant + Help; Compensation summary Location text; account Access page: restaurants (companies) per site-scoped Domain + payment authorizations per restaurant + Help |
| Tips Payment Control | (in `rfone-tips`) | same branch | approver = signed-in account (no identity picker); Approve & Pay and retry need restaurant access + payment authorization; retry never pays twice; Help |
| Database | RDS | — | **one additive migration** `a1c220261121 -> b2c320261121`: column `rfone_account_domain_access.company_scope` (default `ALL`) + table `rfone_account_domain_company_access`. No data is changed; every existing access keeps reaching every restaurant. |

## 2. Live state at planning time (rollback targets)

| Item | Live now |
|---|---|
| rfone-tips | `rfone-tips:tip-role-history-20261118c-tips` |
| rfone-web | `rfone-web:registry-departments-20261121t030713z-web2` |
| rfone-clover-correction-sync | service on task definition `:12` (image `rfone-tips@sha256:8ba25ab6…`), command `--location-id 1` |
| rfone-clover-acquisition-job | task definition `:12` (image `rfone-tips@sha256:970c0fe6…`) |
| rfone-clover-live-sync | task definition `:1` (`--location-id 1 --once`) |
| RDS alembic | `a1c220261121` |
| Latest manual snapshot | `rfone-dev-pre-registry-departments-20261121t030713z` |

Re-read all of these immediately before step 1; if anything changed, stop and re-plan.

## 3. Preconditions

1. PO authorization of this plan.
2. Branch pushed to GitHub; release commit fixed (no further commits during the release).
3. Local regression green on the release commit (suites listed in §7).
4. No other session deploying Clover workers, Tips or RF-One Web (coordinate with the Registry session).
5. Read-only inventory done on 2026-11-21 (§0): no TIPS grant exists; WP restaurant has legal entity 1. Repeat it immediately before step 1.
7. **Release builds contain only what is authorized.** Either (a) each image is built from that service's live code (`release/registry-web-20261121` for rfone-web, the live snapshot `76b32c8` for rfone-tips, `release/registry-clover-jobs-20261121` for the workers) with only the CLOVER_MULTISITE_001 changes ported onto it and the suites of §7 re-run there, as done for the Registry release; or (b) the PO explicitly authorizes publishing the whole integrated tree. Recommended: (a).
8. **One Tips release at a time.** The session on `feature/tips-registry-roles` is preparing an `rfone-tips` release from the same live image: the two are combined into one release (or released one after the other, the second rebased on the first), never deployed independently.
9. Image references are recorded by digest (the ECR repositories have mutable tags): rollback uses the digests of §0.
10. Local UI in English for the release build (UI_DEVELOPMENT_LANGUAGE_001): the new strings are English by default and Italian only with `RFONE_UI_LANGUAGE=it`.

## 4. Steps (one component at a time, verify before the next)

**Step 0 — Safety snapshot.** Manual RDS snapshot `rfone-dev-pre-clover-multisite-<UTC>`; record the identifiers of §2.

**Step 1 — Migration `b2c320261121` (additive).** One-off ECS task with an image built from the release commit, command `alembic upgrade b2c320261121`, as done for `a1c220261121`. Verify: RDS alembic = `b2c320261121`; every `rfone_account_domain_access` row has `company_scope = 'ALL'`; the new table is empty; the live services (old code) keep working — the column has a server default, the old code neither reads nor writes it.

**Step 1b — Clover worker image.**
- Build the `rfone-tips` worker image from the release commit.
- Update the Clover connector manifest hashes (`clover_connector_release.json`).
- The image contains migrations up to `b2c320261121`, which step 1 has applied: the start check sees no orphan chain (lesson of 2026-11-21). Never build the workers before step 1.
- Register new revisions of `rfone-clover-acquisition-job` and `rfone-clover-correction-sync` with the **same command as today** (`--location-id 1`) and the **same secrets** (WP pair only).

**Step 2 — Correction poller (WP only).** Update the service to the new revision. Verify:
- the start check logs `CLOVER_RELEASE_VERIFIED`;
- 3 consecutive cycles for location 1 are COMPLETE;
- no cycle runs for location 2;
- WP link counts are unchanged (`directory_links`, employees available/unavailable as before).

**Step 3 — Acquisition job (WP).** One Sync Now for WP from RF-One Web after step 5, or a one-off run of the new revision. The IngestionRun is COMPLETE; orders, payments and shifts get location 1; nothing is written for location 2.

**Step 4 — Tips (App Runner).** Deploy the new image. Verify on WP:
- the selector shows WP selected and MD "inactive";
- a **known saved period** (Saved Periods) shows the same totals as before;
- Calculate on a past WP period gives the same result as before the release;
- the Tips run notes show `shifts_without_certain_location=0` (all 3,409 legacy shifts resolve to WP);
- Payment Control shows "Approving as <signed-in name>" and no identity list; without a payment authorization the button is disabled with the reason.

**Step 5 — RF-One Web.** Deploy the new image. Verify:
- Clover Acquisition opens on WP with Help;
- Tips › saved periods lists WP only;
- the Compensation Period Summary for a past WP period shows the same hours as before, with the "from Clover record" note and no "no certain Location" warning;
- Settings › Accounts › Access shows, for Tips and Clover Acquisition, "Restaurants: All companies" selected for every existing account (nothing narrowed), and the Payment authorizations section; the Help opens.

**Step 6 — Switch the poller to multi-site (optional, behaviour-neutral while MD is inactive).**
- New correction-sync revision with `--all-active-locations`.
- Verify cycles still run for location 1 only.

**Step 7 — Payment authorizations (data, separate PO authorization).** Approve & Pay and retry now act only as the signed-in account, so the existing grants held by identities not bound to an account (inventory of precondition 5) no longer let a person pay from the page. The RF-One System grant used by the automatic mode (`WITHOUT_APPROVAL`) is unchanged. On the PO's instruction, an administrator ticks "Tips — Approve & Pay" for WP on the Access page of each approver named by the PO; nothing is granted automatically. Payment Control is still the Mercury Sandbox pilot, so no real payment depends on this step.

## 5. Rollback

| Failure in | Action | Time |
|---|---|---|
| Step 1 | Not expected (additive, no data). If needed: `alembic downgrade a1c220261121` — only after the new code is rolled back, since the new code reads the column. Otherwise leaving the column in place is harmless to the old code. | minutes |
| Step 2/3/6 | `aws ecs update-service --service rfone-clover-correction-sync --task-definition rfone-clover-correction-sync:12`; acquisition job back to `:12` (web launcher uses the family's latest ACTIVE revision: deregister the new one) | minutes |
| Step 4 | App Runner rfone-tips back to `tip-role-history-20261118c-tips` | ~5 min |
| Step 5 | App Runner rfone-web back to `registry-departments-20261121t030713z-web2` | ~5 min |
| Step 7 | Untick the authorization on the Access page (the grant is revoked, kept in history). | seconds |
| Payments | None exist on AWS (§0); a rollback never re-executes anything. If payments existed, the old code would lose only the retry guards, not the instructions' idempotency keys. |
| Data anomaly | One additive schema change and no data migration, so code rollback is sufficient. Never downgrade the migration after release: it would delete the company selections made on the Access page. Data written by the new code (IngestionRuns, links) is the same shape as before. Restore the snapshot only if a data defect is proven. | — |

## 6. Conditions to activate Mount Dora (separate authorization)

1. Steps 1–5 verified on WP and stable for at least one business day.
2. Execution role `rfone-clover-acquisition-job-execution-role` may read `rfone-tips/clover-md-api-token`; **then** add `CLOVER_API_TOKEN__WP3NHX517C0M1` to the worker task definitions (in this order, or the WP workers would fail to start).
3. Authorizations reviewed with the PO before activation (PO rule 2): existing accounts still reach every restaurant (`All companies`); narrow on the Access page those who must not see MD, and grant MD payment authorization only to the intended approvers.
4. Optional, if the PO authorizes it: MD employee roster refresh (roster only) and identity confirmation in Registry.
5. PO authorization to set merchant 2 and location 2 `active = true`, then the first MD Historical Backfill and verification of MD-only data.

## 7. Local verification of the release commit

Clover: acquisition, jobs, safety, correction, live sync, freshness. Tips: distribution engine, order owner, host audit, stateless, rules, payment execution, payment connector, flexible engine, finalized period. Compensation: period, summary, approval, payroll calculation, overtime. Multi-site: `test_clover_multisite`, `Tips/test_multisite_selection_http`, `RF-One Web/tests/test_clover_acquisition_multisite_http`, `RF-One Web/tests/test_tips_validation_multisite_http`. Registry: `test_registry_departments`. Permissions and payments: `test_multisite_permissions` (22), `Tips/test_payment_control_authorization_http` (5), `RF-One Web/tests/test_account_access_multisite_http` (5). Migration `b2c320261121` upgrade/downgrade on a copy of the previous schema. How Works check (no new errors). WP acquisition differential, old against new code, identical.
