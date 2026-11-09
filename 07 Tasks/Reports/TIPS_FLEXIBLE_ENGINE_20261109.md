# REPORT

## 1. Approved outcome

Copy the deployed Tips application and full AWS database to local first; then extend and test one configurable calculation engine locally and deploy it to AWS. Do not synchronize local data back to AWS or create a separate engine for each rule.

## 2. Verified starting point

The AWS source archive SHA256 is `614dd45aa9010d9b05a25ac7bd72364631f3db61b7c3cb83f5434415de84076e` (665 files verified). The read-only database snapshot at 2026-11-09 15:33:39 UTC contains 297 tables, 1,068,172 rows and 287 sequences. Every table's count and content hash and every sequence were verified after restore. Revision: `e1b220261102`. Local database: `rfone_aws_copy`, loopback port 55436. Previous local contents remain in a full backup file; staging databases were removed. AWS database writes: none.

Private backup and restore evidence: `%LOCALAPPDATA%/RF-One/AWS-Backup/tips-engine/20261109T153258Z/`, including `aws-tips-source.zip`, `aws-service.json`, `rfone_full.dump`, `manifest.json`, `local_before_full.dump` and `full_copy_verification.json`. These files contain private operational data and are not committed.

## 3. Executable rule specification

The operator describes a rule, reviews its complete meaning, and confirms it. Interpretation alone saves nothing. The same engine composes:

| Axis | Supported choices |
|---|---|
| Source | Named assigned role, or order service owner |
| Base | Voluntary tips, gratuity, or their sum |
| Rate | Percentage |
| Aggregation | Individual order, or source employee / location / business day / rule version |
| Eligibility | Active at order opening, active at settlement, or worked during the business day |
| Distribution | Equal shares; or proportional to eligible worked time during the business day |
| No recipient | Source retains the entire amount |

Daily aggregation requires daily eligibility. Hours weighting requires daily eligibility. Order aggregation may also use daily eligibility and equal or hours-weighted distribution. Existing rule versions retain order aggregation by default and their original behavior.

The requested historical rule uses source-business-day aggregation, 10%, daily eligibility and hours-proportional distribution. Each server's daily base is summed and its contribution rounded once to cents. Its recipients receive deterministic largest-remainder shares. Order-level lines remain traceable and reconcile exactly to each server's contribution. Each location uses its configured timezone and business-day cutoff. Shift time is clipped to the day and effective role coverage, overlapping intervals are merged, and only actual positive worked time counts. Incomplete relevant shifts block calculation rather than inventing hours. No eligible worked time means no deduction. Full-day context is calculated before filtering the requested window, so subperiods remain consistent.

## 4. Validation and deployment

Implementation, local validation, release identifiers and observed outcomes will be recorded here as they complete.

## 5. Local observed results

- Migration `e2c320261109` applied locally after verified full restore; it adds only `aggregation_scope`, default `ORDER` for every existing rule version.
- 16 new financial scenarios pass: daily per-source rounding, hours weighting, no recipient, presence at another time of day, merged overlaps, effective role coverage, incomplete shifts, partial windows, daylight saving, invalid combinations, independent axes, interpreter confirmation, zero/signed corrections, cutoff boundary, location isolation and 100% cent conservation.
- Existing suites passed: engine 40 checks, configuration 27, interpreter 45, stateless calculation 31, Host audit 33; finalized-period suite exited 0. English and Italian authenticated HTTP checks passed for Configuration, Rule History and Calculate Tips.
- A real local Bedrock call proposed `SOURCE_BUSINESS_DAY / WORKED_DURING_BUSINESS_DAY / HOURS_PROPORTIONAL`, 10%, with no rule saved.
- Real-data local simulation (transaction always rolled back): 13,659 orders from January 1 to November 9, total tips plus gratuity $288,343.67; employee entitlements reconcile exactly. Runtime about 1.5 seconds on this PC.
- For October 21–25: 289 orders, gross $5,759.95. With every order owner as source, daily distribution is $576.00, matching the Excel screenshot's combined Host total; zero source orders lack an eligible Host during their business day. This is a total reconciliation, **not** a per-person Excel reconciliation: current persisted role coverage yields different recipients. A rule limited to the named Server role distributes only $112.47 for these days. No assignments were repaired or inferred.
- Existing account identity was used only for local HTTP inspection; no accounts, historical rules, entitlements or payments were created. Local preview scaffolding and private configuration are excluded from the release.
- Windows browser automation stopped because its policy check could not establish Edge's current URL. No alternative automation bypass was attempted. Visual verification in Edge remains uncompleted; authenticated HTTP rendering was verified instead.

## 6. Release scope and recovery

One engine composes aggregation, eligibility and weighting. The new schema column is additive and old images can still read existing data. Rollback consists of restoring the prior App Runner image/configuration; leave the additive column in place. Data rollback is not part of an application rollback. Full AWS snapshot and previous local backup references are in section 2.

How Works is updated on Configuration, Rule History, Calculate Tips and Host Audit. The shared modal component has a visible close button and native keyboard/focus support. The release defaults to English; the loopback local launcher selects Italian. Eight unrelated legacy pages remain listed as missing contextual Help; this release does not certify those pages.

Final pre-release regression rerun: all 16 new scenarios, engine 40, audit 33, interpreter 45, existing Role/Rule HTTP suite, Configuration HTTP 27 and Calculate/Consolidate HTTP 31 passed. The generic settlement fact is exposed once by the Clover connector for scalar and bulk consumers. No browser visual pass is claimed.


## 7. Completed AWS release

| Evidence | Observed value |
|---|---|
| Runtime commit | `83d583caf1a2cf1d5c29f44d59367311317ececa` (pushed to `origin/codex/tips-flexible-rules`) |
| Build | `rfone-tips-build:8c107bd3-4ee3-489c-ba27-54ab7e200ab1` — SUCCEEDED |
| Image | `418674484214.dkr.ecr.us-east-1.amazonaws.com/rfone-tips:tips-flexible-20261109t160202z` |
| Immutable image digest | `sha256:f23db11f364553de6236176691305d21b29d8ebcc1f8f98687c4f6fdd4976d8d` |
| Source archive SHA256 | `a42ef170d6d19953733aa57cc818264a5fbd901222a380feb4c3749478781ed6` |
| Source archive | `s3://rfone-tips-deploy-418674484214/releases/tips-flexible-20261109t160202z/source.zip` |
| Migration task | `arn:aws:ecs:us-east-1:418674484214:task/rfone-jobs/d834ad9d50264ae3ae7b659d0ed8429d` — STOPPED, exit 0 |
| Shared schema | `e2c320261109`; registry published in the deployment bucket |
| App Runner operation | `19756129f1d24f79a55c0931df4deb7e` — SUCCEEDED |
| Service | RUNNING; live image matches the release image |
| Public authenticated checks | GET configuration 200; POST interpretation 200 |
| Real AWS proposal | 10.0000%, TIP_PLUS_GRATUITY, SOURCE_BUSINESS_DAY, WORKED_DURING_BUSINESS_DAY, HOURS_PROPORTIONAL |
| Confirmation / payment | No rule confirmation, no paid-tip records created |
| AWS data alignment | None; the only schema change is the additive rule configuration column |
| Network / AI provider | Unchanged; existing OpenAI GPT-OSS via Bedrock, no NAT |

The AWS migration verified unchanged counts for orders, shifts, employee assignments, rule identities and rule versions. Every pre-existing rule version retained `ORDER`. The official shared page served English contextual Help. Local authenticated HTTP checks retained Italian. Browser visual verification remains the specific limitation described in section 5.

## 8. Success criteria and restore

| Criterion | Outcome |
|---|---|
| Complete AWS code and DB copied before engine edits | PASS — section 2; verified hashes and sequences |
| One configurable engine, existing rules preserved | PASS — configuration axes and regression suites |
| Requested daily/hour rule executable and explainable | PASS — financial scenarios, local real-data simulation and real local/AWS interpretation |
| Local tests before AWS deployment | PASS — section 5 |
| AWS deployed from pushed commit | PASS — section 7 |
| No local-to-AWS database synchronization | PASS |
| Edge visual check | NOT COMPLETED — browser policy could not verify current URL |

Restore application code by updating App Runner back to `418674484214.dkr.ecr.us-east-1.amazonaws.com/rfone-tips:tips-openai-bedrock-20261109t140457z`, using the saved prior service configuration in `tmp/flexible_previous_service.json` (private working evidence). The additive column can remain: the previous image does not name it. Do not restore the full shared database merely to roll back application code. A full data restore, if separately needed and authorized, uses the custom-format dump and manifest in section 2; its SHA256 is `cf8e528b19378dad1e56d2b933cb7ea6459a3790814f52291cea2a11dbcee9fc`.

No Product Owner decision remains for this engine release. Applying a historical rule and resolving differences in historical role coverage are separate operator decisions; they were not silently performed by this release.
