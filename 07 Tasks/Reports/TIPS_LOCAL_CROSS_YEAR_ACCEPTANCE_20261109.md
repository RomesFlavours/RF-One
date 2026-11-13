# REPORT

## 1. Authorized local operation

The Product Owner explicitly requested including payments spanning 2025 to value the first week, retaining the original period, local only. Applied exclusively to the canonical database `127.0.0.1:55436 / rfone_aws_copy`. No AWS access, synchronization, deployment or Git push.

## 2. Result

Seven Completed, explicitly Tip-labelled observations totaling **$5,512.73** now count toward historical coverage. Their original period remains **December 30, 2025–January 4, 2026**. Their January 5 payment dates, original memo, status, identities, amounts and stored source categories remain unchanged. No amount was apportioned between calendar years and no January-only earnings value was invented.

The owner decision is recorded separately on each observation and in an audit event. The report derives the effective included category from that decision. The source PDF observations and document input hash remain immutable, and re-importing the original PDF payload is still idempotent.

Coverage is now **45 valued weekly intervals out of 45 elapsed intervals through November 8**. This means weekly representation in the selected historical payment evidence, not certification that every employee's payment is complete or every exception resolved. The earlier ambiguous payments and possible repetitions remain flagged.

The current full snapshot reports $284,640.64; with the non-overlapping October 26–November 1 supplement, the selected document-observed total is $289,450.20 across 376 included entries. That total now includes a cross-year period in full and the previously reported $2,612.73 possible-repeat excess. It is not a prorated total of earnings solely attributable to calendar 2026 or a certified deduplicated bank amount.

## 3. Checks

Eleven historical-payment tests pass, including explicit cross-year acceptance without source mutation, rejection of invalid/rejected/non-tip evidence, Delivered acceptance, integrity checks and same-document idempotency. The actual local change was verified before commit and re-read after commit. Authenticated English and Italian local HTTP checks show the updated amount, original dates and matching contextual Help. No employees, role assignments, distribution rules, entitlements or calculation-run counts changed. No money was sent.

## 4. Local changes and recovery

Local-only changes extend the historical report's existing explicit-decision handling, update its tests and the historical page/Help explanation in English and Italian. No schema migration was required.

Backup: `C:\Users\servi\AppData\Local\RF-One\Local-Backup\Tips\cross-year-acceptance-20261109T235151Z`, with `observations_before.json` and `result.json`. Working result: `tmp/cross_year_acceptance/result.json`. Audit entity: `tips_historical_period_acceptance`, under original import run `228146`. Reverting this decision would remove its acceptance annotations, not alter original bank facts or delete the import.
