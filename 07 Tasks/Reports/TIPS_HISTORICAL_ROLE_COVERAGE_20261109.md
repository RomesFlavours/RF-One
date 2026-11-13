# REPORT

## 1. Scope and method

Read-only audit of the current AWS database, snapshot **2026-11-09 22:38:01 UTC / 17:38:01 America/New_York**. Coverage: business dates January 1 through November 8, 2026, using the location's 04:00 cutoff. November 9 is excluded as the current, incomplete business day.

Observed source facts: 13,659 settled orders, 3,554 shift records selected for the period, 64 employee identities and 15 RF1 role assignments. SQL ran in a read-only, repeatable-read transaction. No roles, identities, shifts, rules, entitlements, payments or schema were changed. No database alignment or deployment was performed.

## 2. Historical coverage is missing

All 15 assignments have the same effective start, **2026-09-04 00:00 UTC**, which is **September 3 at 20:00 New York**. All have an open end and source `CLOVER_ROLE_SYNC`; there are no closed assignment rows reconstructing role changes.

January–August contains **11,040 settled orders and $234,843.23 in voluntary tips plus gratuity**, but none of those order owners has an RF1 role valid at settlement. Shifts exist in every month. Every business day with an order has at least one recorded, closed shift somewhere in the location. Therefore missing role eligibility must not be described as proof that no Host actually worked.

Under the stored assignments, 173 business days with orders have no eligible Host; the last is September 2. This is a diagnostic consequence of the role coverage gap, not evidence of 173 days of actual Host absence.

The original role-sync script anchors first assignments to the earliest shift available when synchronization runs. Its code does not establish an employee's historical role from the beginning of the year. The uniform September date is consistent with an earlier initialization followed by a later historical backfill; that sequence is an inference, not a proven execution history.

## 3. Current source observations disagree with RF1 assignments

Clover's latest linked snapshots show:

| Employee | RF1 assignment | Latest Clover snapshot | Consequence |
|---|---|---|---|
| Gaby Steinborn | Host | Server | Treated as a Host recipient; excluded as a named-Server source |
| Alice Martini | Team Leader | Server | Excluded as a named-Server source |
| Lonnie Dunston | Team Leader | Server | Excluded as a named-Server source |
| Sevilla Antuna | No assignment | Host | Recorded work is excluded from Host eligibility |
| Terry Muller | No assignment | Host | Recorded work is excluded from Host eligibility |
| Emily Garcia | No assignment | Host | Recorded work is excluded from Host eligibility |
| Bailey Roman | No assignment | Host | Recorded work is excluded from Host eligibility |
| Giulia Pagliaro | No assignment | Server | Has worked shifts, but no RF1 source-role coverage |

The latest snapshot proves the role observed at that snapshot, not the effective date of a past change. Expanded raw employee snapshots already show Gaby, Alice and Lonnie as Server on October 29. Older membership observations include Host for Gaby (last observed October 12) and Team Leader for Alice/Lonnie (September 7). `observed_at` is not an employment effective date; it cannot establish the exact change date.

The ingestion functions add/refresh `EmployeeSourceRole` observations without removing older role memberships. Those rows can therefore retain old and new roles together. They must not be read as a simultaneous role assignment or a complete historical change log. The employee directory refreshes provider observations, while the calculation uses the distinct, effective-dated `EmployeeAssignment` facts. This explains how a correct current Clover snapshot can coexist with obsolete or missing RF1 assignments.

## 4. Recorded work excluded by missing assignments

The following current Clover Host/Server employees have no RF1 assignment at any date. These are recorded closed-shift hours, not a conclusion that the same role applied throughout their history:

| Employee | Latest Clover role | First recorded shift, New York | Last recorded shift date | Recorded hours in audit period |
|---|---|---|---|---:|
| Sevilla Antuna | Host | 2026-09-17 | 2026-10-30 | 84.03 |
| Terry Muller | Host | 2026-09-12 | 2026-11-07 | 55.44 |
| Giulia Pagliaro | Server | 2026-09-25 | 2026-10-17 | 34.66 |
| Emily Garcia | Host | 2026-10-08 | 2026-10-15 | 2.11 |
| Bailey Roman | Host | 2026-10-14 | 2026-11-08 | 21.47 |

Some old assignments start after all recorded work for that employee: Michael Nelms, Gabriela Morales, Alyssa Monacelli and Fernanda Mardones are examples. Those assignments cannot qualify their earlier shifts.

Twenty people with closed shifts have no RF1 assignment. This count includes legitimate BOH/Admin/Employee classifications and must not be interpreted as twenty missing Host assignments. Five have current Host/Server observations above. Eight have no role in their latest linked snapshot (or no linked snapshot) and need historical identification before they can be classified:

| Employee / internal identity for unnamed records | First recorded shift | Last recorded shift | Recorded hours | Earlier role observation, when available |
|---|---|---|---:|---|
| Alex Steven | 2026-09-16 | 2026-09-16 | 0.04 | Server observed 2026-10-20 |
| Gabrielle Milotte | 2026-01-02 | 2026-05-31 | 406.18 | None |
| Giorgia Tommasi | 2026-01-02 | 2026-03-08 | 332.85 | None |
| Sienna Silverstin | 2026-03-14 | 2026-05-30 | 273.87 | None |
| Unnamed employee #61 | 2026-04-22 | 2026-07-18 | 109.70 | None |
| Unnamed employee #62 | 2026-05-03 | 2026-05-09 | 1.33 | None |
| Penelope Scotto | 2026-06-25 | 2026-07-26 | 75.79 | None |
| Carlie Ray | 2026-07-03 | 2026-07-26 | 36.17 | None |

Three selected shifts have no clock-out (Pino Miraglia, Alice Martini and Meagan Messick). They are not currently Host assignments and do not explain the Host mismatch. No reversed-duration closed shifts were found in the selected data. This observation does not certify that every recorded duration agrees with payroll or Excel.

## 5. The source of the contribution also needs the intended meaning

The Excel week includes tips attributed to Tatiana Ceban, whose RF1 and current Clover role is Manager. Its source totals also include Alice and Lonnie, stored as Team Leader, and Gaby, stored as Host. Thus a rule explicitly limited to the named `Server` role does not reproduce that spreadsheet. This should be resolved by the correct rule source semantics, not by inventing Server assignments to make the totals match.

With current assignments, October 21–25 distributes only **$112.47** from the named Server role. Using every order owner as the source distributes **$576.00**. Those are diagnostic simulations, not saved entitlements. The intended treatment of order-owning Managers/Team Leaders must be explicit before applying the historical rule.

## 6. October 21–25: the recipient discrepancy is concrete

With unchanged RF1 assignments and all order owners contributing, the $576.00 goes to Andrew Muller ($203.58), Foster King ($135.68) and Gaby Steinborn ($236.74). Sevilla and Terry receive zero because they have no Host assignment. This explains why matching the combined Host total alone does not validate the recipients.

A separate **in-memory sensitivity scenario**, confined to this week, uses exactly the four Hosts shown in Excel, their recorded daily shifts and the new per-source/day rounding. It does not assert or save historical role dates. Its results are:

| Host | Excel screenshot | Recorded daily hours scenario | Difference |
|---|---:|---:|---:|
| Foster King | $153.34 | $152.12 | $-1.22 |
| Andrew Muller | $180.67 | $201.22 | $20.55 |
| Sevilla Antuna | $133.41 | $152.42 | $19.01 |
| Terry Muller | $108.58 | $70.24 | $-38.34 |

Both columns total $576.00. Therefore correcting the recipient identities alone does not fully reconcile the per-person spreadsheet amounts. Recorded hours / the spreadsheet's hours and calculation basis require a separate reconciliation. The screenshot contains no hours, so the precise remaining cause cannot be established from that screenshot alone.

## 7. Monthly evidence

| Business month | Settled orders | Tips + gratuity | Orders whose owner has no valid RF1 role | Days with orders and no eligible Host under recorded roles |
|---|---:|---:|---:|---:|
| 2026-01 | 1,539 | $34,028.21 | 1,539 | 22 |
| 2026-02 | 1,508 | $31,406.54 | 1,508 | 19 |
| 2026-03 | 1,523 | $31,943.02 | 1,523 | 21 |
| 2026-04 | 1,548 | $33,495.12 | 1,548 | 22 |
| 2026-05 | 1,461 | $32,212.94 | 1,461 | 23 |
| 2026-06 | 1,111 | $22,926.92 | 1,111 | 20 |
| 2026-07 | 1,205 | $24,493.15 | 1,205 | 23 |
| 2026-08 | 1,145 | $24,337.33 | 1,145 | 22 |
| 2026-09 | 963 | $19,716.77 | 58 | 1 |
| 2026-10 | 1,290 | $26,234.02 | 25 | 0 |
| 2026-11 | 366 | $7,549.65 | 8 | 0 |

The January–August zeros in recipient eligibility are caused by missing historical role facts; they are not a valid reason to conclude that servers should retain all tips for those months.

## 8. What must be established before applying from January

1. Reconstruct each relevant employee's real role periods, including former staff and actual changes. Do not automatically backdate today's role to January or treat the first recorded shift as proof of the role.
2. Add the missing Host/Server assignment periods and resolve the Gaby/Alice/Lonnie discrepancies using dated evidence or the owner's explicit historical confirmation.
3. State whether the contributing source is every order owner, including Managers/Team Leaders who receive tips, or only employees actually holding the Server role.
4. Reconcile the October per-person amounts against the spreadsheet's daily hours before using it as an expected result for the year.

**Recommendation:** do not apply the January rule to the current role history. No corrective action or rule application has been performed by this audit.

## 9. Traceability

- AWS read-only snapshot: `2026-11-09 22:38:01.160721+00:00`.
- Successful ECS reader: `arn:aws:ecs:us-east-1:418674484214:task/rfone-jobs/b941b4b9e63c4e5288c21e658af149f3` (exit 0).
- Private AWS evidence: `s3://rfone-tips-deploy-418674484214/audits/roles-20261109T223735Z/facts.json`.
- Local evidence: `tmp/roles_audit/aws_facts.json`, `analysis.json`, `october_sensitivity.json`; these operational-data files are not committed.
- Period and arithmetic reproducible with `tmp/roles_audit/analyze.py` and `october_sensitivity.py`; neither connects for writes.
- Source review: `rfone_data_store/models.py` (`EmployeeSourceRole`, `EmployeeAssignment`), `employee_directory.py`, `technical/connectors/clover/ingest.py`, `historical_backfill_detail.py`, `sync_winter_park_employee_roles.py` in `03 Software/RF-One Data Store`.
- No UI/code changes: How Works update not applicable. No push or deployment was performed.
