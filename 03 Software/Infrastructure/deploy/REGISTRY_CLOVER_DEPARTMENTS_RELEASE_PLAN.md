# REGISTRY_CLOVER_DEPARTMENTS_001 — AWS release plan

Status: **prepared, not executed.** Executing any step requires the Product Owner's explicit
authorization. Account 418674484214, region us-east-1.

## Artifacts

| Artifact | Branch / commit | Base (what runs today) |
|---|---|---|
| Feature (integration tree, migration source) | `feature/registry-clover-departments` (d8b3eb1, 433b8b4) | `origin/integration/live-2026-11-20` |
| rfone-web overlay | local `release/registry-web-20261121` | `origin/live/2026-11-20-web` = image `rfone-web:web-forgot-password-email-20261118` |
| Clover worker image | local `release/registry-clover-jobs-20261121` (fe7e1a6, d344165) | image `rfone-tips@sha256:970c0fe6…` (release `tip-role-history-20261118d-jobs`), verified file by file |

The worker branch differs from the running image only in: `employee_directory.py`, `models.py`,
`correction_sync.py`, `ingest.py`, `historical_backfill_detail.py`, the connector manifest and its check,
plus the new `registry_departments.py`, `test_registry_departments.py` and migration `a1c220261121`.
Build every source ZIP with `git -c core.autocrlf=false archive` (manifest hashes are LF).

## Steps

1. **Backup.** `aws rds create-db-snapshot --db-instance-identifier rfone-dev
   --db-snapshot-identifier rfone-dev-pre-registry-departments-<UTC>`; wait until `available`;
   record `alembic_version` (expected `e9a120261117`) and the counts of `employee_assignments`,
   `restaurant_roles`, `restaurant_locations`, `locations`, `tip_distribution_calculation_runs`,
   `tip_entitlements`, `tip_payment_instructions`.
2. **Migration** `e9a120261117 -> a1c220261121` (additive: 4 new tables, departments FOH/BOH, roles
   Cook/Dishwasher/Server Help, the initial Role/Department table). One-off ECS task in `rfone-jobs`
   with an image built from the feature branch, command `alembic upgrade a1c220261121`, secret
   `RFONE_DATABASE_URL`, network of the rfone-tips VPC connector + `sg-0a4d4d094ea0d0fc3`. Then update
   `schema/aws_applied_revision.json` (S3) and commit the receipt. Re-running is a no-op; tested
   upgrade -> downgrade -> upgrade on a copy (roles never duplicated, assignments untouched).
3. **Clover worker.** Build `release/registry-clover-jobs-20261121` with `rfone-tips-build`; register
   `rfone-clover-correction-sync` revision 11 = revision 10 with the new image, plus secrets
   `CLOVER_MD_API_TOKEN` / `CLOVER_MD_MERCHANT_ID` (rfone-tips/clover-md-*), env
   `CLOVER_MD_TIMEZONE=America/New_York`, command adds `--roster-restaurant-id 4`.
   **Needs an IAM change:** the execution role `rfone-clover-acquisition-job-execution-role` may read only
   the WP secrets today; add the two MD secret ARNs to its `ReadJobSecrets` statement.
   `aws ecs update-service --cluster rfone-jobs --service rfone-clover-correction-sync --task-definition
   rfone-clover-correction-sync:11`. The acquisition job (Sync Now) stays on revision 12 unchanged.
4. **Mount Dora.** No manual step: the first poller cycle reuses or creates the MD Location from the
   Clover merchant and links it to restaurant 4 (`Rome's Flavours - MD`, today without any location).
   Its 4 Clover people appear as identities to confirm. No MD sales, shifts or tips are acquired.
5. **rfone-web.** Build `release/registry-web-20261121` with `rfone-web-build` (overlay on the live
   image's tree); App Runner `update-service` changing only `ImageIdentifier`, adding the non-secret
   env `CLOVER_MD_MERCHANT_ID` (so Anagrafica recognizes the MD site and shows no Sync Now button
   for it: MD has no acquisition credentials there).
6. **Excel history.** Run `load_registry_history.py` (rfone-web image, one-off task) with the 58 Note
   records reduced to `row, register_id, name, house, role`: first without `--persist` (expected: 56
   people, 56 reconciled, 48 to load, 0 not found, 9 incomplete, 1 duplicate), then with `--persist`,
   then once more (expected 0 loaded, 48 already loaded).
7. **Sync checks.** Poller logs: no `Employee synchronization failed`; on Winter Park the first cycle
   opens about 11 assignments, closes 3+4, changes nothing at the second cycle; `SELECT employee_id,
   restaurant_id, count(*) FROM employee_assignments WHERE valid_to IS NULL GROUP BY 1,2 HAVING
   count(*)>1` returns no row; MD location linked once.
8. **Non-regression.** Tips `calculate_tips_for_business_dates` for the last 14 closed business dates
   before and after (read-only, identical digests expected); unchanged counts/checksums of
   `tip_distribution_calculation_runs`, `tip_entitlements`, `tip_payment_*`, compensation tables;
   Anagrafica pages, Registry, Tips home and Compensation home answer 200.
9. **Rollback** (any failure):
   - worker: `update-service ... --task-definition rfone-clover-correction-sync:10`;
   - web: App Runner back to `rfone-web:web-forgot-password-email-20261118`;
   - data written by the sync after the release instant T:
     `DELETE FROM employee_assignments WHERE assignment_source='CLOVER_ROLE_SYNC' AND valid_from >= T;
      UPDATE employee_assignments SET valid_to=NULL WHERE assignment_source='CLOVER_ROLE_SYNC' AND valid_to >= T;`
     remove the MD `restaurant_locations` row and, if created, the MD `locations` / `merchants` rows;
   - schema: `alembic downgrade e9a120261117` (drops only the 4 new tables; the 3 new roles stay);
   - last resort: restore the step-1 snapshot.
