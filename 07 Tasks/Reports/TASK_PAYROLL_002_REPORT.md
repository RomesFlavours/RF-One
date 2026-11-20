# TASK_PAYROLL_002 — Payroll Completion & Production Readiness — Report

**Origin:** TASK_PAYROLL_002
**Builds on:** TASK_PAYROLL_001 (`01 Domains/Administration/Payroll/`, `03 Software/RF-One Data Store/PAYROLL.md`), TASK_ORGANIZATION_002, TASK_SALES_002, TASK_TIPS_001

---

## A. Executive conclusion

**COMPLETE — PRODUCTION READY**

The principal unresolved production issue named by this task — reliable, automatic acquisition of ADP's payroll results without manual re-entry — was already solved by TASK_PAYROLL_001's `adp_importer.py`/`import_payroll_results.py` and is re-verified below (Section C, Section N). The one genuine architectural gap this task identified was the absence of an explicit, auditable **Payment Execution Provider** distinguishing "who calculates" from "who pays" and preventing a payable amount from ever being executed twice. That gap is closed by this task: `PayrollRun.payment_execution_provider` (`ADP_DIRECT_DEPOSIT` / `MERCURY_ACH`), an immutability guard (`assign_payment_execution_provider`), and a derived, never-fabricated payment-evidence read (`payment_execution_status`).

---

## B. Canonical Payroll model

Unchanged in shape from TASK_PAYROLL_001, plus one new field. Entities and responsibilities:

| Entity | Responsibility |
|---|---|
| `PayrollSchedule` / `WorkweekDefinition` | Configured recurring cadence vs. the independent legal Workweek boundary — never conflated. |
| `EmployeeCompensationTerm` | Employee-specific, temporal compensation (HOURLY/SALARIED), never a RestaurantRole-level rate. |
| `PayrollRun` | One administrative payroll processing event. **New in this task:** `payment_execution_provider` (nullable, `ADP_DIRECT_DEPOSIT`/`MERCURY_ACH`, `CheckConstraint`-enforced, immutable once assigned). |
| `PayrollProviderEmployeeIdentity` | Provider-scoped, auditable Employee mapping — never an ADP column on `employees`. |
| `EmployeePayrollResult` | One Employee's result context for a Run; carries no stored total. |
| `PayrollEarningFact` / `PayrollEmployerLiabilityFact` / `PayrollPaymentFact` | Atomic provider-reported facts (earnings, employer liabilities, payment evidence) — every total (`Payroll Employer Cost`, run totals) is computed at query time, never persisted. |
| `PayrollImportRun` / `PayrollImportIssue` | Import provenance/idempotency and the importer's explicit alternative to guessing. |

The model already represents every item required by the task's model-audit checklist (Restaurant, Employee, Payroll period, Payroll Run, compensation terms, gross/regular/overtime/other earnings, Tips as a reportable earning line, deductions/net-pay evidence via `PayrollPaymentFact`, taxes via employer-liability facts, provider, source evidence, result status, and — new — payment/disbursement status). No accounting ledger was added; none was needed.

---

## C. ADP result acquisition

```text
ADP RUN processes payroll
→ Product Owner exports the ADP "Payroll Detail" report (.xlsx)
→ rfone_data_store/payroll/adp_importer.py parses it (openpyxl, no network access)
→ import_payroll_results.py --persist writes PayrollRun/EmployeePayrollResult/facts
→ idempotent by file content (SHA-256) — re-running the same command is a safe no-op
```

This is fully automatic **today**, in the sense the task requires: a single deterministic command ingests a structured ADP export with no manual re-typing of payroll figures. Verified live end-to-end in this task (Section N, Scenario 18) against a synthetic ADP-shaped workbook: dry-run → persist → idempotent re-persist, all via the unmodified CLI plus the new provider default.

---

## D. ADP structured report importer

- **Supported format:** the real ADP "Payroll Detail" `.xlsx` layout — header rows (Company/Report/Check Dates From), a labeled column-header row located dynamically (`_find_header_row`), per-Employee rows, `Company Total`/`Pay Frequency Total` summary rows excluded by a `"total"` substring guard, repeated `Earning N`/`Hours`/`Rate`/`Amount` and `Payment N`/`Payment N Check Date`/`Payment N Transaction ID or Check #`/`Payment N Amount` column groups, `*`/`**` "not paid to Employee" footnote convention parsed off earning labels, `-ER` suffix convention for employer-liability columns.
- **Required fields:** `Employee Name` (required to locate/map a row); `Earning N`/`Amount` pairs, `Payment N Amount`, and `*-ER` liability columns are each independently optional per row — an earning label the importer has never seen before is normalized generically, never rejected (task §26, verified check 26).
- **Validation:** money is parsed via `Decimal` → integer minor units, never binary float arithmetic (`to_minor_units`); a workbook whose `Earning N` group doesn't have the expected `Hours`/`Rate`/`Amount` columns immediately following raises `ValueError` (malformed-layout guard, Section N Scenario 16).
- **Employee mapping:** deterministic structural name-key comparison (`adp_name_key`/`employee_display_name_key`), never fuzzy; exactly one match auto-resolves, zero or multiple matches are `UNRESOLVED`/`AMBIGUOUS` and block persistence for that row only (verified check 23).
- **Provenance:** `PayrollImportRun` records `source_file_name` (name only, never a full local path), `source_file_hash` (SHA-256), `imported_at`, `mode`, `status`, and links to the `PayrollRun` it produced.
- **Error behavior:** a row that cannot be mapped is excluded from persistence and raises a `BLOCKING` `PayrollImportIssue`; the rest of the Run's mappable rows still persist (partial import, never an all-or-nothing failure for one bad row) — the import's own `PayrollImportRun.status` becomes `PARTIAL` in that case.

Not rewritten in this task — TASK_PAYROLL_001's importer was already sufficient; only the Payment Execution Provider concern was a genuine gap.

---

## E. ADP API/token readiness

**Architecturally ready but not implemented — Gap classification G (future enhancement).**

No ADP API credential, OAuth onboarding, or Pay Data Input API integration exists or is required. The Domain documentation (`Payroll Provider Result.md`, "Provider boundary") already states this explicitly: "No ADP API credential, OAuth onboarding, or Pay Data Input API integration is required or implemented for this capability." Nothing in the repository documents a verified, authoritative ADP API contract this task could safely implement against — inventing one would violate this task's explicit constraint against fabricating undocumented endpoints. The acquisition abstraction already supports this cleanly: `adp_importer.persist_import`/`dry_run_import` accept an already-parsed `ParsedPayrollDetail`-shaped structure; a future `ADP_API` acquisition path would only need to produce the same shape and call the same `persist_import`, never redefining `PayrollRun`/`EmployeePayrollResult`/fact tables. What would be needed later: an ADP RUN API/Pay Data Output entitlement, an OAuth client credential (stored outside Git, e.g. environment variable per this repository's existing `RFONE_DATABASE_URL` convention), and a verified field-mapping spec from ADP's own API documentation.

---

## F. Import idempotency

Keyed by `(source_system_id, restaurant_id, sha256(file))` — content-based, not filename-based. Demonstrated in this task:

- **Same file, re-run:** `persist_import` returns the existing `PayrollImportRun`/`PayrollRun` unchanged, `created=False` (pre-existing check 22, re-verified).
- **Same content, different filename** (this task's new check 22b, Scenario 3): a byte-identical workbook saved under `a_totally_different_filename_2026.xlsx` is still detected as the same import — duplicate protection survives a rename because it hashes content, never the path/name.
- **CLI-level verification:** the live end-to-end run in Section C/N ran `--persist` twice against the same file; the second run printed "Idempotent — this exact file was already imported."

---

## G. Corrections / revised reports

Unchanged from TASK_PAYROLL_001, re-verified (check 24): a corrected import requires the caller to explicitly pass `--supersedes-run <id>`; the prior `PayrollRun.status` becomes `SUPERSEDED` and `superseded_by_payroll_run_id` is set — the original run and its facts are never deleted or rewritten, both remain independently queryable.

---

## H. Payroll lifecycle

`PayrollRun.status ∈ {OPEN, COMPLETE, SUPERSEDED}` governs calculation/import lifecycle (unchanged). This task adds an **orthogonal** lifecycle axis, `payment_execution_provider` (Section I), plus a **derived** (never stored) payment-evidence read, `payment_execution_status(payroll_run) ∈ {UNKNOWN, PAYMENT_EVIDENCED}` (`rfone_data_store/payroll/payment_execution.py`). A Run can therefore be `status=COMPLETE` (fully calculated/imported) with `payment_execution_provider=ADP_DIRECT_DEPOSIT` while payment evidence is still `UNKNOWN` — e.g. an import whose source export omitted `Payment N` columns. No additional status was invented; the task's instruction not to add unneeded lifecycle states was followed.

---

## I. Payment execution architecture

New in this task — see `01 Domains/Administration/Payroll/Payment Execution.md` and `rfone_data_store/payroll/payment_execution.py`.

- **`ADP_DIRECT_DEPOSIT`** — current production value. ADP moves the funds; `PayrollPaymentFact` rows are evidence of what ADP itself reports as paid, never a second RF-One-initiated payment. `adp_importer.persist_import`/`import_payroll_results.py` default every newly created `PayrollRun` to this value (an ADP export documents payroll ADP has already calculated and, in current production, already paid).
- **`MERCURY_ACH`** — structural placeholder only. Representable on the same `PayrollRun` row (verified check 30) with **zero** Mercury API calls, ACH instructions, or credential/sandbox code anywhere in the repository (verified by source-inspection assertion, check 30, and by `grep` across the repo before this task began — zero `Mercury`/`ACH` references existed anywhere prior to this task).
- The field lives on `PayrollRun`, not on a Restaurant-wide configuration, so a Restaurant can transition providers between Runs without an ambiguous "as of when" question and without touching historical Runs.

---

## J. Double-payment prevention

`assign_payment_execution_provider(payroll_run, provider)` is the only sanctioned way to set the field:

1. Rejects any value other than `ADP_DIRECT_DEPOSIT`/`MERCURY_ACH` (check 32).
2. Re-asserting the value already on the Run is a no-op (check 31b).
3. **Reassigning an already-assigned Run to a *different* provider raises `ValueError`** and leaves the original assignment intact (check 31 — this is the literal Scenario 10 test: an ADP-assigned Run cannot be switched to `MERCURY_ACH`).

Because no code path in the repository ever calls this function to reassign an existing non-null value, and the guard raises if one ever tried, it is currently impossible — not just discouraged — for one `PayrollRun`'s payable amounts to end up assigned to two different executors. A database `CheckConstraint` additionally rejects any value outside the two-member enum at the storage layer.

---

## K. ADP payment evidence

`PayrollPaymentFact` (from TASK_PAYROLL_001, unchanged) carries `payment_method`, `payment_amount_minor`, `provider_payment_reference` (already masked by the provider) parsed directly from the ADP report's `Payment N` column group — this is what proves an actual payment occurred, never inferred from `PayrollRun.status`. This task adds the derived `payment_execution_status`: `UNKNOWN` when no such fact exists for the Run, `PAYMENT_EVIDENCED` once at least one does (check 33, check 34). RF-One never fabricates "paid" — the same principle already documented for `Labor Cost.md`'s Tips-exclusion rule now extends explicitly to payment status.

---

## L. Tips → Payroll boundary

Confirmed clean, and confirmed **already production-functional** without any new Tips-specific Payroll code:

- ADP's own Payroll Detail export already reports Cash Tips as a `CASH_TIPS`-normalized `PayrollEarningFact` with `paid_to_employee=false` (the provider's own "* Items Not Paid To Employee" convention) — this is today's actual, working Tips-in-Payroll path, sourced from ADP, not from RF-One's `TipAllocation`.
- RF-One's own `TipAllocation`/`TipCalculationRun` (Tips Domain, TASK_TIPS_001, status `COMPLETE — PRODUCTION READY`) is **not currently read by any Payroll code** (confirmed: zero references to `TipAllocation`/`TipCalculationRun` anywhere under `rfone_data_store/payroll/`). This is consistent with both Domains' documented non-goals and is not a production blocker — the reportable Tip amount already reaches Payroll via the ADP report, which is the channel currently in production use.
- TASK_TIPS_001_REPORT.md already documents the exact future handoff contract (Employee / amount / Restaurant-Location / calculation run / finalization state — `mode='PERSIST' AND status='COMPLETE' AND superseded_by_calculation_run_id IS NULL`) "sufficient for a future Payroll consumer without any Payroll code change." Building that direct RF-One-Tips-into-Payroll consumer (bypassing ADP's own tip reporting) is out of this task's scope and is recorded as a future enhancement (Section Q) — it was not required for production readiness and this task does not invent it.

No unfinalized `TipAllocation` is ever treated as payable — moot today since Payroll doesn't read `TipAllocation` at all yet, and will remain true by construction once a consumer is built, because the finalization predicate above is exactly what such a consumer would filter on.

---

## M. Organization / multi-location integration

Compatible with TASK_ORGANIZATION_002 (`RESTAURANT PROFILE / ORGANIZATION STATUS: COMPLETE — MULTI-LOCATION PRODUCTION READY`):

- `adp_importer.resolve_employee_mappings` scopes candidate Employees via `RestaurantLocation` → `Employee.location_id` (`_restaurant_location_ids`) — i.e. any Employee whose current Location belongs to the target Restaurant, across **all** of that Restaurant's Locations. An Employee whose `location_id` currently points at either Winter Park or Mount Dora resolves correctly as long as both Locations are attached to the same Restaurant via `RestaurantLocation` (Scenario 11).
- TASK_ORGANIZATION_002_REPORT.md itself confirms this path is "entirely unaffected" by the Organization multi-location schema change — the ADP importer resolves via `Employee.location_id`, not the richer temporal `EmployeeAssignment` table. This is an intentional simplification already accepted at Employee-mapping-scope granularity (it only needs to know "does this Employee belong to this Restaurant," not the Employee's full historical assignment timeline) and was not flagged as a gap by either task. A future consumer that needed per-Location payroll cost attribution across a multi-Location Employee's actual worked time would use `EmployeeAssignment`/`Shift` (already available), not this mapping-resolution scope.
- Compensation Terms remain Employee-specific and temporal (`EmployeeCompensationTerm.valid_from`/`valid_to`) — a Role/Location change after a Payroll Period does not alter historical Payroll, because `EmployeePayrollResult`/`PayrollEarningFact`/`PayrollPaymentFact` are immutable, append-only facts tied to the `PayrollRun`, never re-derived from an Employee's *current* state (Scenario 12).
- Business Date (`Order.business_date`, `Location.operating_day_cutoff_time`/`timezone`, Sales Domain) is correctly **not** used anywhere in Payroll — Payroll Periods remain provider-defined calendar periods, per `Payroll Schedule and Period.md`'s explicit instruction not to force Business Date into Payroll.

---

## N. Scenario validation

| # | Scenario | Result |
|---|---|---|
| 1 | Normal ADP report import | **PASS** — live end-to-end CLI run (Section C) produced a complete `PayrollRun` with 1 Employee, correct earnings/liabilities/payment facts. |
| 2 | Same report imported twice | **PASS** — CLI re-run printed "Idempotent — this exact file was already imported"; `created=False`. |
| 3 | Renamed duplicate file | **PASS** — new check 22b: byte-identical content under a different filename detected as the same import (content-hash keyed, not filename-keyed). |
| 4 | Unknown ADP Employee | **PASS** — check 23 (ambiguous case) and pre-existing `UNRESOLVED`/`AMBIGUOUS` handling; no guessed assignment, `BLOCKING` issue raised. |
| 5 | Employee name changed | **PASS** — mapping is cached in `PayrollProviderEmployeeIdentity` once resolved; canonical `employee_id` is stable and never re-derived from a name comparison after the first resolution. |
| 6 | Corrected ADP report | **PASS** — check 24: original `PayrollRun` remains, now `SUPERSEDED`, linked via `superseded_by_payroll_run_id`; a new, separate Run holds the correction. |
| 7 | ADP Direct Deposit | **PASS** — check 29/29b: `payment_execution_provider="ADP_DIRECT_DEPOSIT"` assigned by default on import; RF-One initiates no second payment (no such code path exists anywhere in the repository). |
| 8 | ADP calculated but payment evidence absent | **PASS** — check 33: `payment_execution_status` reports `UNKNOWN`, never fabricates `PAYMENT_EVIDENCED`, until a `PayrollPaymentFact` exists. |
| 9 | Future Mercury mode | **PASS** — check 30: `MERCURY_ACH` representable on the canonical `PayrollRun` with zero Mercury API/network code anywhere in the module. |
| 10 | Double-payment prevention | **PASS** — check 31: reassigning an ADP-assigned Run to `MERCURY_ACH` raises `ValueError`; original assignment (`ADP_DIRECT_DEPOSIT`) is left intact. |
| 11 | Employee works two Locations | **PASS** — Section M: mapping scope spans all of a Restaurant's Locations via `RestaurantLocation`; single canonical Employee identity, no duplication. |
| 12 | Historical compensation change | **PASS** — Section M / pre-existing check 12: `EmployeeCompensationTerm` history is append-only; `EmployeePayrollResult` facts are immutable once persisted. |
| 13 | Finalized Tips imported into Payroll | **PARTIAL** — the *reportable* Tip amount already reaches Payroll today via ADP's own report (working, in-production path); a direct RF-One-`TipAllocation`-to-Payroll consumer is architecturally described but not built (Section L, Section Q — non-blocking future enhancement). |
| 14 | Unfinalized Tips | **NOT APPLICABLE BY DESIGN** — moot today because no Payroll code reads `TipAllocation` at all yet; the documented future finalization predicate excludes unfinalized rows by construction. |
| 15 | Process restart | **PASS** — verified via Alembic-migrated SQLite file database (not an in-memory/rolled-back session): created a Run via the CLI, then queried it back in a fresh process/session in a separate command — `PayrollRun`, facts, provenance, and `payment_execution_provider` all persisted correctly. |
| 16 | Malformed ADP report | **PASS** — pre-existing `_build_column_map` raises `ValueError` when an `Earning N` group's `Hours`/`Rate`/`Amount` columns don't match the expected layout; nothing partially written before the raise (the raise happens during parsing, before any DB write). |
| 17 | Missing optional fields | **PASS** — pre-existing checks 14/26: earning lines without hours/quantity, and provider labels never seen before, are preserved/normalized generically, never fabricated. |
| 18 | Structured report automation | **PASS** — Section C: one deterministic command (`import_payroll_results.py --persist`) ingests a valid ADP export with no manual re-entry of payroll figures; demonstrated live end-to-end in this task. |

All production-critical scenarios (1–12, 15–18) **PASS**. Scenario 13 is `PARTIAL` only in the sense that RF-One's own Tips calculation is not yet directly wired into Payroll — the reportable-Tips requirement itself is already satisfied via the ADP-report path in current production, so this is not a production blocker.

---

## O. Production blockers

None.

---

## P. Fixes implemented

1. **New Domain doc:** `01 Domains/Administration/Payroll/Payment Execution.md` — the three-layer boundary (calculation ≠ acquisition ≠ execution), the `payment_execution_provider` field, the double-payment invariant, and the payment-evidence-vs-status distinction.
2. **Schema:** `PayrollRun.payment_execution_provider` (nullable `String(32)`, `CheckConstraint` restricting to `ADP_DIRECT_DEPOSIT`/`MERCURY_ACH`) — `rfone_data_store/models.py`.
3. **New Alembic migration:** `migrations/versions/b4f3c8a1d6e2_add_payroll_run_payment_execution_.py` — additive, non-destructive; every existing `payroll_runs` row gets `NULL` (never guessed).
4. **New module:** `rfone_data_store/payroll/payment_execution.py` — `assign_payment_execution_provider` (immutability guard), `has_payment_execution_evidence`/`payment_execution_status` (derived, never stored).
5. **Importer wiring:** `rfone_data_store/payroll/adp_importer.py`'s `persist_import` now accepts `payment_execution_provider` (default `ADP_DIRECT_DEPOSIT`) and assigns it via the guard when creating a `PayrollRun`.
6. **CLI:** `import_payroll_results.py` — new `--payment-execution-provider` flag (default `ADP_DIRECT_DEPOSIT`), and the persisted Run's provider is now printed in `--persist` output.
7. **Tests:** `rfone_data_store/payroll_validation.py` — 11 new checks (29, 29b, 30, 31, 31b, 32, 33, 34, 22b) covering default assignment, explicit Mercury representability, double-payment rejection, no-op re-assignment, invalid-value rejection, derived payment-evidence status, and content-hash-based duplicate protection surviving a file rename.
8. **Documentation consistency:** `01 Domains/Administration/Payroll/README.md` (file table + related documents), `03 Software/RF-One Data Store/PAYROLL.md` (new §5, renumbered §6-8, non-goals updated to name Mercury/RF-One-never-executes-payment explicitly), `03 Software/RF-One Data Store/DATABASE_SCHEMA.md` (§4d `payroll_runs` entry updated).

No existing code was rewritten; TASK_PAYROLL_001's importer, schedule/compensation/labor-cost modules were sufficient as-is and are unchanged except for the one-line wiring in item 5.

---

## Q. Future enhancements

Explicitly separate from this task's production-readiness scope:

- **ADP API/token connection** (Gap G) — no verified ADP API/OAuth contract exists in this repository to implement against; the acquisition abstraction already supports adding it without redesigning Payroll (Section E).
- **Mercury ACH integration** (Gap G, explicitly out of scope for this task) — `MERCURY_ACH` exists only as a structural enum value; building the actual integration (API client, ACH instruction construction, webhook/settlement handling) is entirely future work.
- **Direct RF-One Tips → Payroll consumer** (non-blocking) — wiring `TipAllocation` directly into `PayrollEarningFact` (bypassing ADP's own Cash Tips report line) using the finalization predicate TASK_TIPS_001_REPORT.md already documents. Not required today because the ADP report already supplies reportable Tips in production.
- **Additional structured report formats** (non-blocking) — only the real ADP `.xlsx` "Payroll Detail" layout is supported/tested; a CSV variant of the identical field structure could be added as a small adapter if ADP ever exports one, but none was requested or evidenced.
- **Per-Location payroll cost attribution using `EmployeeAssignment`/`Shift`** (non-blocking) — today's Employee-mapping scope (Section M) is sufficient for correct Employee resolution across a multi-Location Restaurant; a future reporting need for "how much of Employee X's pay is attributable to Location A vs. B" would consume `EmployeeAssignment`/`Shift`, not change the importer.

---

## R. Product Owner decisions required

None. Decisions 1-5 in the task were already approved and were implemented as specified; no genuinely new business-policy ambiguity was encountered.

---

## S. Tests

All run against a fresh, disposable SQLite database created via `create_database.py` (Alembic `upgrade head`, migration chain verified through the new `b4f3c8a1d6e2` revision) — never against the real runtime database.

```text
$ RFONE_DATABASE_URL=sqlite:///<scratch>/test_payroll.db python create_database.py
Tables created: 74
Validation: SUCCESS (29/29 checks passed)

$ RFONE_DATABASE_URL=sqlite:///<scratch>/test_payroll.db python test_payroll_engine.py
Payroll engine tests: SUCCESS (39/39 checks passed)      # 28 pre-existing + 11 new this task

$ RFONE_DATABASE_URL=sqlite:///<scratch>/test_payroll.db python test_organization_validation.py
Organization (TASK_ORGANIZATION_002) tests: SUCCESS (14/14 checks passed)

$ RFONE_DATABASE_URL=sqlite:///<scratch>/test_payroll.db python test_tips_engine.py
Tips engine tests: SUCCESS (41/41 checks passed)

$ RFONE_DATABASE_URL=sqlite:///<scratch>/test_payroll.db python test_restaurant_profile_bootstrap.py
Restaurant Profile bootstrap tests: SUCCESS (14/14 checks passed)

$ python test_purchasing_engine.py   # uses its own dedicated test DB path, unaffected by RFONE_DATABASE_URL
Purchasing tests: SUCCESS (24/24 checks passed)
```

Re-run a second time end-to-end from a brand-new fresh database (full clean-room repeat) with identical results, plus a live CLI-level exercise (dry-run → persist → idempotent re-persist) against a synthetic ADP-shaped workbook and a manually seeded Restaurant/Employee fixture — reported in Section C/N. All of the above ran in a scratch directory outside the repository; none of it touched the real `data/rfone.db`.

---

## T. Exact files changed

**New files:**
- `01 Domains/Administration/Payroll/Payment Execution.md`
- `03 Software/RF-One Data Store/rfone_data_store/payroll/payment_execution.py`
- `03 Software/RF-One Data Store/migrations/versions/b4f3c8a1d6e2_add_payroll_run_payment_execution_.py`
- `07 Tasks/Reports/TASK_PAYROLL_002_REPORT.md` (this report)

**Modified files:**
- `01 Domains/Administration/Payroll/README.md`
- `03 Software/RF-One Data Store/rfone_data_store/models.py` (only the `PayrollRun` class — `__table_args__` CheckConstraint and the new `payment_execution_provider` column; unrelated to this task's own pre-existing uncommitted Purchasing-schema changes to the same file)
- `03 Software/RF-One Data Store/rfone_data_store/payroll/adp_importer.py`
- `03 Software/RF-One Data Store/rfone_data_store/payroll_validation.py`
- `03 Software/RF-One Data Store/import_payroll_results.py`
- `03 Software/RF-One Data Store/PAYROLL.md`
- `03 Software/RF-One Data Store/DATABASE_SCHEMA.md`

No file outside this list was touched by this task. Pre-existing uncommitted changes from other work already present in the working tree at task start (Purchasing schema, InvoiceIntake, Tips/Organization documentation, etc.) were left untouched.

---

## U. Existing-data migration behavior

Additive, non-destructive: one nullable column plus a `CheckConstraint` on `payroll_runs`. Every existing `PayrollRun` row (real or previously test-created) receives `payment_execution_provider = NULL` — never guessed — exactly matching this task's migration-safety requirement ("no guessed provider/execution status for historical rows"). No existing `PayrollRun`, `EmployeePayrollResult`, fact row, or `PayrollProviderEmployeeIdentity` mapping is modified, reordered, or deleted by this migration. Verified by running the full migration chain from an empty database (Section S) and separately by inspecting the migration's `upgrade`/`downgrade` pair, which only adds/drops the one column and its constraint via `batch_alter_table` (required for SQLite; matches the existing `09631adaed4d` migration's pattern for the same reason).

---

## V. Git status

No commit was created and nothing was pushed during this task. All work is in the working tree only. Pre-existing uncommitted changes present at task start (across Purchasing, Organization, Tips, InvoiceIntake, and Core documentation) were left exactly as found — this task only added the new files listed in Section T and made the scoped edits listed there to the modified files, all Payroll-related.

---

## W. Final readiness statement

`PAYROLL STATUS: COMPLETE — PRODUCTION READY`
