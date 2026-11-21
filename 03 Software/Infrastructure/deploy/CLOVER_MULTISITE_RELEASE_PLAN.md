# Coordinated release plan — Registry + Clover multi-site + Tips (CLOVER_MULTISITE_001)

Status: **PLAN ONLY — not executed.** Every step needs the Product Owner's explicit authorization.
Mount Dora (MD) stays **inactive** throughout; activation is a separate, later decision.

## 1. What is released

| Component | Service | Source | Change for people |
|---|---|---|---|
| Clover workers (acquisition job, correction poller, live sync, verification) | ECS `rfone-jobs` task definitions | branch `feature/clover-multisite-registry` | none for WP. Per-merchant credentials; inactive sites never acquired; cross-site roster guard; Registry role sync (already live) kept |
| Tips | App Runner `rfone-tips` | same branch | Restaurant selector; inactive site refused; Shift Location certain or pending |
| RF-One Web | App Runner `rfone-web` | same branch | Clover Acquisition selector + Help; Tips period validation per restaurant + Help; Compensation summary Location text |
| Database | RDS | — | **no migration** in this release (Registry migration `a1c220261121` is already applied) |

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
5. Local UI in English for the release build (UI_DEVELOPMENT_LANGUAGE_001): the new strings are English by default and Italian only with `RFONE_UI_LANGUAGE=it`.

## 4. Steps (one component at a time, verify before the next)

**Step 0 — Safety snapshot.** Manual RDS snapshot `rfone-dev-pre-clover-multisite-<UTC>`; record the identifiers of §2.

**Step 1 — Clover worker image.**
- Build the `rfone-tips` worker image from the release commit.
- Update the Clover connector manifest hashes (`clover_connector_release.json`).
- **Exclude migration files whose chain is not on RDS** from the worker image (lesson of 2026-11-21: an orphan migration file breaks the start check).
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
- the Tips run notes show `shifts_without_certain_location=0` (all 3,409 legacy shifts resolve to WP).

**Step 5 — RF-One Web.** Deploy the new image. Verify:
- Clover Acquisition opens on WP with Help;
- Tips › saved periods lists WP only;
- the Compensation Period Summary for a past WP period shows the same hours as before, with the "from Clover record" note and no "no certain Location" warning.

**Step 6 — Switch the poller to multi-site (optional, behaviour-neutral while MD is inactive).**
- New correction-sync revision with `--all-active-locations`.
- Verify cycles still run for location 1 only.

## 5. Rollback

| Failure in | Action | Time |
|---|---|---|
| Step 2/3/6 | `aws ecs update-service --service rfone-clover-correction-sync --task-definition rfone-clover-correction-sync:12`; acquisition job back to `:12` (web launcher uses the family's latest ACTIVE revision: deregister the new one) | minutes |
| Step 4 | App Runner rfone-tips back to `tip-role-history-20261118c-tips` | ~5 min |
| Step 5 | App Runner rfone-web back to `registry-departments-20261121t030713z-web2` | ~5 min |
| Data anomaly | No schema change and no data migration in this release, so code rollback is sufficient. Data written by the new code (IngestionRuns, links) is the same shape as before. Restore the snapshot only if a data defect is proven. | — |

## 6. Conditions to activate Mount Dora (separate authorization)

1. Steps 1–5 verified on WP and stable for at least one business day.
2. Execution role `rfone-clover-acquisition-job-execution-role` may read `rfone-tips/clover-md-api-token`; **then** add `CLOVER_API_TOKEN__WP3NHX517C0M1` to the worker task definitions (in this order, or the WP workers would fail to start).
3. Per-site permissions decided (see the authorization proposal), so that who sees MD is intentional.
4. Optional, if the PO authorizes it: MD employee roster refresh (roster only) and identity confirmation in Registry.
5. PO authorization to set merchant 2 and location 2 `active = true`, then the first MD Historical Backfill and verification of MD-only data.

## 7. Local verification of the release commit

Clover: acquisition, jobs, safety, correction, live sync, freshness. Tips: distribution engine, order owner, host audit, stateless, rules, payment execution, payment connector, flexible engine, finalized period. Compensation: period, summary, approval, payroll calculation, overtime. Multi-site: `test_clover_multisite`, `Tips/test_multisite_selection_http`, `RF-One Web/tests/test_clover_acquisition_multisite_http`, `RF-One Web/tests/test_tips_validation_multisite_http`. Registry: `test_registry_departments`. How Works check (no new errors). WP acquisition differential, old against new code, identical.
