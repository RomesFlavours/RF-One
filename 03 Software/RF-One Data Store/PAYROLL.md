# RF-One Data Store — Payroll

TASK_PAYROLL_001 — the first runtime/database implementation of the Administration/Payroll Domain documented conceptually at `01 Domains/Administration/Payroll/`. This document is the Software-layer counterpart: it explains how the schema in `DATABASE_SCHEMA.md` §4d is populated and used, and documents the ADP `Payroll Detail` Excel import workflow. It does not repeat the Domain-level definitions — see `01 Domains/Administration/Payroll/README.md` and its sibling files for those.

---

## 1. Domain boundaries (implementation view)

```text
Payroll ≠ Restaurant
Payroll ≠ Personnel Management
Payroll ≠ Taxation
Payroll ≠ ADP
Payroll ≠ jurisdiction/labor-rule law
```

Concretely: no table in this schema has an `ADP`-specific column; `SourceSystem(code="ADP")` is the only ADP-specific row anywhere. No table encodes a jurisdiction's overtime rule. `EmployeeCompensationTerm.restaurant_role_id` is the only optional link to Restaurant, and it is nullable — nothing in the Payroll package queries Restaurant semantics to compute a result.

---

## 2. PayrollSchedule / PayrollPeriod / Workweek / PayDate

`rfone_data_store/payroll/schedule.py` holds the only code governing these concepts, and it deliberately does **not** define any overtime computation. `PayrollSchedule.schedule_type` supports `WEEKLY`/`BIWEEKLY`/`MONTHLY` (`validate_schedule_type`). `WorkweekDefinition` is a separate table (`restaurant_id`, `start_weekday`, `valid_from`/`valid_to`) — never derived from `PayrollSchedule`. `workweeks_within_period(period_start, period_end, start_weekday)` is a pure calendar function used to demonstrate/exercise that a BIWEEKLY `PayrollRun`'s 14-day period contains exactly two 7-day Workweeks under Rome's Flavours' Monday-anchored configuration — nothing calls this function to compute overtime; it exists so a future jurisdiction/labor-rule layer has a Workweek boundary to consume. `PayrollRun.period_start`/`period_end`/`pay_date` are three independent columns; nothing derives one from another.

---

## 3. Compensation Terms

`rfone_data_store/payroll/compensation.py` + the `employee_compensation_terms` table. `terms_valid_during` resolves which terms apply to an interval; `detect_mid_period_conflict`/`review_status_for_period` implement the `MANUAL_REVIEW_REQUIRED` rule for an incompatible same-`function_label` rate change inside one Payroll Period (`01 Domains/Administration/Payroll/Compensation Terms.md`). A `CheckConstraint` on the table enforces that `HOURLY` rows carry `hourly_rate_minor` (and no `salaried_period_amount_minor`) and vice versa for `SALARIED`.

---

## 4. ADP `Payroll Detail` Excel import

`rfone_data_store/payroll/adp_importer.py`, entry point `import_payroll_results.py`. Reads the real ADP export layout (header rows, a labeled column-header row, per-Employee rows, `Company Total`/`Pay Frequency Total` summary rows excluded, `*`/`**` footnote convention parsed off earning labels) using `openpyxl` only — no network access of any kind.

**Employee mapping** (`resolve_employee_mappings`): the real sample workbook has no stable ADP employee id, only `Last, First Middle` names and a masked partial SSN. Matching is a deterministic structural name-key comparison (first token = first name; the rest, joined, = last name — applied symmetrically to both the ADP `Last, First` format and RF-One's `First Last` `Employee.display_name`), never a similarity/fuzzy match. A key matching **exactly one** current Employee in the Restaurant's scope auto-resolves; zero or multiple matches are `UNRESOLVED`/`AMBIGUOUS` and block persistence for that row. Confirmed/rejected mappings are cached in `payroll_provider_employee_identities`, scoped by `(source_system_id, restaurant_id, external_employee_key)`.

**Idempotency and provenance** (`persist_import`, `payroll_import_runs`): keyed by `(source_system_id, restaurant_id, sha256(file))`. Re-importing the identical file is a safe no-op (the existing `PayrollImportRun`/`PayrollRun` is returned unchanged). A different file is always a new import; it only supersedes a specific prior `PayrollRun` when the caller explicitly passes `--supersedes-run <id>`, which marks the prior run `SUPERSEDED` (never deleted) and links `superseded_by_payroll_run_id`.

**Dry-run first** (`dry_run_import`): read-only — parses and resolves mapping against the database without writing anything, returning an aggregate-only `DryRunSummary` (no Employee name, SSN, or bank reference). This is what `import_payroll_results.py` runs by default; `--persist` is required to write.

---

## 5. Payroll Employer Cost / Labor Cost query

`rfone_data_store/payroll/labor_cost.py`. `compute_employee_labor_cost`/`compute_payroll_run_labor_cost` derive every figure from `payroll_earning_facts` (`paid_to_employee = true` only) and `payroll_employer_liability_facts` at query time — no total is persisted. `EmployeeLaborCost.payroll_employer_cost_minor` is a computed `@property`, not a column.

---

## 6. Usage

```text
python import_payroll_results.py --file "<path to PayrollDetail.xlsx>" \
    --restaurant-id 1 --period-start 2026-08-03 --period-end 2026-08-17 \
    --run-type REGULAR
    # dry-run (default): prints an aggregate-only summary, writes nothing

python import_payroll_results.py --file "<path>" --restaurant-id 1 \
    --period-start 2026-08-03 --period-end 2026-08-17 --run-type REGULAR --persist
    # writes PayrollRun/EmployeePayrollResult/facts; idempotent by file hash

python test_payroll_engine.py
    # synthetic-fixture test suite (TASK_PAYROLL_001 §34) — run against a
    # fresh/staging database, same convention as test_tips_engine.py
```

---

## 7. Explicit non-goals (this task)

ADP Pay Data Input API / OAuth, payroll tax calculation, a full worldwide labor-law/jurisdiction rule engine, direct deposit execution, contractor/1099 payables, a bank reconciliation engine, KPI/bonus rule design, Tip calculation redesign or Tip payout execution, Personnel selection/Performance logic, benefit-provider integrations, Core changes. See `07 Tasks/Reports/TASK_PAYROLL_001_REPORT.md` for the full non-goal list and known limitations.
