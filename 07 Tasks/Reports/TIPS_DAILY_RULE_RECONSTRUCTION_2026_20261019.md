# REPORT

## 1. Outcome and scope

Completed a separate, reviewable reconstruction for January 1–October 4, 2026: 40 weekly periods, 339 person/week rows, 22 people and 12,244 orders. The first period, December 29–January 4, includes only January 1–4; no December 2025 amounts were reconstructed. The final September 28–October 4 week is complete.

| Observed result | USD |
| --- | ---: |
| Recorded tips | 228,322.48 |
| Recorded gratuity | 31,505.42 |
| Total source gross | 259,827.90 |
| January–September gross | 254,560.00 |
| October 1–4 extension | 5,267.90 |
| Exact host allocation, displayed to cents | 25,439.47 |
| Sum after individual weekly rounding | 259,827.95 |

The five-cent difference comes from rounding each person's weekly result. Exact fractions conserve the source gross; no artificial balancing adjustments were introduced. There are zero pending amounts and zero calculation issues.

## 2. Approved rule and decisions

Tip plus gratuity belongs to the order owner, including owners classified Manager, Team Leader or Admin. Where a business day has host hours, 10% of that day's gross is shared among hosts in proportion to their hours across the whole day. With no host hours, the owner retains 100%. User-confirmed host roles, including the final six-person confirmation and Giorgia's confirmation, apply throughout this reconstruction period. These decisions are retained in the private rules file.

Two explicitly identified trials are excluded, accounting for 30 shifts and zero order gross. Their source records remain preserved. The exclusion is not generalized to other employees outside the historical roster.

The calculation uses the canonical order business date and New York 04:00 cutoff. Shifts are split at business-day boundaries using elapsed time across daylight-saving changes. Overlapping hours for the same host are counted once. Clock corrections affect the worker's hours, not the identity of the supervisor who corrected them; see [Clover shift reference](https://docs.clover.com/dev/reference/employeeupdateshift).

## 3. Changes and protection

Added a deterministic calculation engine, ten regression tests, readonly snapshot/audit and independent verification helpers, and a private JSON/interactive HTML result. Private reconstruction outputs are gitignored. No reconstruction was written to the database, no new consolidated run was created, and no connector deployment was needed.

Independent verification confirmed all 11 protected tip-table fingerprints unchanged and the local Bank file bytes unchanged. The workflow performed no Bank writes. AWS remained the source master; no local database copy was performed.

## 4. Success criteria and evidence

| Criterion | Outcome |
| --- | --- |
| Exact conservation, including host transfers per week | Passed |
| No trial recipients | Passed |
| No pending allocations | Passed |
| Protected tip-table fingerprints unchanged | Passed |
| Bank file hash unchanged | Passed |
| Ten calculation regression tests | Passed |
| Generated HTML JavaScript syntax | Passed |

An initial unittest module-style invocation failed because the helper module was outside that invocation's import path. Running the test file directly resolved the invocation issue; all ten tests passed. The independent financial/integrity verifier also passed.

Snapshot SHA256: `16465c57ad9042800346c0bc4a71b442efa28ad93b2b944c2e7117ffff40ea82`.

Reconstruction SHA256: `cec2ae24cec12be8a6be1fd33a4bcec49a9b105dd07538da2036af5b7fe4f94a`.

## 5. Limits and interpretation

This is a reconstruction of amounts recorded by Clover under the user-approved allocation rule, ready for review and subsequent Zelle comparison. It does not establish whether an amount has already been paid. No Zelle reconciliation or Bank enrichment was performed in this step.

1,468 successful source payments have no reported tip field; unreported cash tips cannot be inferred. Historical roles are user-confirmed assumptions for this period, not a complete role history supplied by Clover. Four refunds report zero tips and require no tip deduction. Taxes, unimplemented line discounts and compensation rates were not reconstructed.

Historical source rows remain retained. Future line-based reconstruction must respect `order_items.source_present IS NOT FALSE`; this calculation uses verified payment tips and order service-charge facts rather than deriving amounts from historical lines.

## 6. Traceability and recovery

- Private review: `output/tips_reconstruction_2026/index.html`.
- Private calculation and trace: `output/tips_reconstruction_2026/reconstruction.json`.
- Private readonly evidence: `input_snapshot.json`, `input_audit_private.json`, `confirmed_rules.json`, `verification.json` in the same folder.
- Calculation: `tmp/tips_daily_rule_engine.py`; regression tests: `tmp/test_tips_daily_rule_engine.py`.
- Preparation and verification: `tmp/audit_tip_reconstruction_inputs.py`, `tmp/build_tips_reconstruction_2026.py`, `tmp/verify_tip_reconstruction_2026.py`.
- Previous source audit: `CLOVER_AWS_MASTER_RECOVERY_20261019.md`; trial decision: `CLOVER_EMPLOYEE_TRIAL_DECISION_20261019.md`.

No database restore is necessary because this reconstruction made no database writes. Preserve the private snapshot, rules and result together to reproduce the calculation.
