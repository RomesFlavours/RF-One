# REPORT

## 1. Conclusion

The N+1 problem is confirmed in the **currently running local Tips application**. A single business day requires 28,375 SQL executions for calculation plus employee review. A 289-order week requires 29,462. A same-database comparison with the local bulk implementation already present in the main repository needs **16 queries** for either period and reproduces the tested aggregate results.

This was reconnaissance only: no application code, launcher, database contents, authentication or AWS resources were changed.

## 2. Exact running environment

Observed Python process 17648 runs `C:/Users/servi/AppData/Local/RF-One/Employee Directory/AWS-20261110T120743Z/launch_local.py`. Its verification state selects:

- Source: `C:\Users\servi\.codex\worktrees\edee\RF One\tmp\git-anagrafica-release\03 Software`.
- Entry: `http://127.0.0.1:5094/tips/`.
- Database: `127.0.0.1:55571 / rfone_employee_directory`.
- Dataset: 13,685 orders, 14,698 payments, 3,574 shifts, 573,720 source records and 15 assignments.

This is a different source tree and database from the Tips working checkout and the local payment imports performed in this chat (`tips-engine`, loopback 55436 / rfone_aws_copy). The running source lacks both the bulk eligibility cache and the flexible daily-aggregation implementation. Its historical-payment view sees only one old 700-row source document, rather than the current full snapshot and missing-week supplement. Version/database drift is therefore an independently observed issue, not just a performance hypothesis.

## 3. Measured query counts and times

All profiled implementations used the **same running application's database**. Measurements were sequential, on real persisted facts, with PostgreSQL `default_transaction_read_only=on`. SQLAlchemy cursor events counted executions and captured query shapes/call sites without parameters. Setup row-count probes are excluded. These are function-path measurements, not an assertion that a whole HTTP request contains no additional navigation/authentication queries. Times include Python/ORM work and profiling overhead and are specific to this PC/cache state.

| Period | Orders | Active: calculation + review queries | Active seconds | Bulk comparison queries | Bulk seconds |
|---|---:|---:|---:|---:|---:|
| Nov 8 business day | 90 | 28,375 | 30.195 | 16 | 0.885 |
| Oct 21–25 | 289 | 29,462 | 34.745 | 16 | 1.115 |
| Jan 1–Nov 8 | 13,659 | 145,288 | 146.429 | 124 | 3.951 |

The week comparison reduces database round trips by about 1,841 times, with about a 31-times observed elapsed-time improvement. The tested equivalence covers order count, gross voluntary tips plus gratuity, total distributed amount, employee-entitlement total and blocked state. It is not a complete certification of every allocation or all other rule shapes.

The already-present bulk comparison is the **uncommitted working-tree implementation** in `C:/Users/servi/OneDrive/AI-RF-ONE/RF One/03 Software/RF-One Data Store/rfone_data_store/tips/distribution_engine.py`. It was not copied, committed, applied or deployed by this audit. It does not contain the newer daily aggregation capability; integrating optimizations must preserve the newer functionality, rather than replacing the module blindly.

The newer `tips-engine` checkout is better than the active copy but is not fully optimized: the same week needs **876 calculation queries + 2 review queries = 878**, about 2.448 seconds. Remaining per-order role/presence lookups still need batching/caching.

## 4. Causes, with measured call sites

### 4.1 Scanning the full historical order set to select one period

Active `distribution_engine.py`, lines 671–672, loops over all candidate orders created before the period end and calls `acquisition.get_order_settlement_time` for each. A single `SELECT max(payments.created_at) WHERE order_id=...` is issued per order before testing whether its settlement is inside the requested window.

For the 289-order week, the candidate set is 13,126 orders. The calculation scans it once; `_orders_in_scope` (lines 599–622), called by `build_employee_review` (line 885), scans it again. Opening the Host audit calls that review yet again. Across the profiled calculation/review/audit flow this one query shape executes **39,378 times**.

A grouped settlement query filtered to the period avoids these per-order round trips. The main working tree already has `_settlements_in_scope` at line 604.

### 4.2 More database lookups inside each selected-order loop

The active calculation reads successful payments, each PaymentTip and OrderFee rows repeatedly, then queries owner roles (line 695), the effective rule version (line 701), recipient roles and shifts. Even a rule sourced from the order owner still executes the owner-role lookup. Review independently re-reads the same monetary facts.

The main working tree's `_gross_by_order` (line 621) and `_PeriodEligibility` (line 382) demonstrate bulk loading of those facts. The annual comparison uses bounded 500-ID batches, which is why it needs 124 queries rather than the 16 seen on the smaller periods.

### 4.3 Host audit repeats work and retains its own N+1 pattern

For the same weekly Host, receiving an already computed result:

| Implementation | Additional audit queries | Seconds |
|---|---:|---:|
| Active copy | 14,447 | 14.435 |
| Main bulk comparison | 444 | 0.722 |
| Newer Tips checkout | 340 | 0.362 |

The active audit calls `build_employee_review` at line 311, causing another full historical settlement scan. Its per-allocation loop (line 238) also loads Order, successful Payments and employee names one at a time. The main comparison still shows 234 employee-name reads and 100 Order + 100 Payment reads for this audit. Thus an additional N+1 remains after the calculation optimization.

The sibling-allocation lookup scans `result.lines` for every audited allocation (line 257). That is another repeated full-list traversal; its large-period CPU effect was identified from code, not separately benchmarked here.

## 5. Other pages and another type of bottleneck

Measured actual HTTP responses from the existing loopback server, using its existing automatic local operator access:

| Page | HTTP | Seconds | Body bytes | Table rows |
|---|---:|---:|---:|---:|
| `/tips/` | 200 | 0.585 | 6,658 | 0 |
| `/tips/configuration` | 200 | 0.295 | 14,058 | 3 |
| `/tips/tips-runs` | 200 | 0.151 | 7,914 | 5 |
| `/tips/historical-tip-payments` | 200 | 0.345 | 98,610 | 532 |
| `/tips/?from_date=2026-01-01&through_date=2026-11-08` | 200 | 4.778 | 10,441,818 | 31,960 |
| `/tips/calculate-tips` | 200 | 32.546 | 25,442 | 8 |

The actual default Calculate Tips response takes **32.546 seconds** despite returning only about 25 KB and eight table rows. This corroborates the backend calculation diagnosis.

Historical payment reporting is not the principal slow path in this running copy: 23 profiled database executions for listing the document and rendering its 700-observation report, and roughly 0.345 seconds over HTTP. It still performs some small per-person identity lookups, but nothing comparable to the calculation's tens of thousands of round trips.

The annual imported-Clover view uses 89 batched database queries (about 3.005 seconds in its read function), but returns **10,441,818 bytes and 31,960 HTML table rows** without pagination. Its real HTTP response takes 4.778 seconds before any additional browser layout work. Browser rendering time was not measured; the large DOM/payload is a separate observed cause for concern, not another 26,000-query claim.

## 6. Recommended priorities — not executed

1. Establish the intended local source tree and canonical database, preserving the full historical imports, explicit status/cross-year decisions and flexible daily rules. Correct launcher/version drift after those dependencies are verified.
2. Integrate the already-present grouped settlement, bulk money and cached eligibility reads into the complete Tips implementation. Reuse the result's facts for review instead of rescanning history.
3. Batch audit Order/Payment/Employee reads and index sibling allocation lines once; reuse review facts instead of re-reading them.
4. Paginate the imported Orders/Payments/Shifts tables while retaining period-wide totals.

Changing indexes or adding a result cache alone would not remove the unnecessary per-order round trips. No fixes, data consolidation, restarts, new databases, AWS access or deployment were authorized or carried out by this reconnaissance.

## 7. Evidence and traceability

Profiler: `tmp/tips_performance_audit/profile_readonly.py` in the chat workspace. Raw stage/query-shape evidence: `active_day.json`, `active_week.json`, `active_year.json`, `main_day.json`, `main_week.json`, `main_year.json`, `updated_week.json`, `active_history.json`, `active_imported.json`, `active_http.json` and `active_calculate_http.json` in the same directory. `runtime.json` is private local configuration evidence and is not a deliverable.

Active source call sites refer to the running source folder from section 2. Main bulk call sites refer to the repository path in section 3. No query parameter values or signing secrets are included in this report.

This is a read-only technical audit. No How Works update applies because no application behavior or page was modified.
