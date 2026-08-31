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

## 4. ADP `Payroll Detail` result parsing and persistence

`rfone_data_store/payroll/adp_importer.py`. Reads the real ADP export layout (header rows, a labeled column-header row, per-Employee rows, `Company Total`/`Pay Frequency Total` summary rows excluded, `*`/`**` footnote convention parsed off earning labels) using `openpyxl` only — no network access of any kind lives in this module. Two parsing entry points share one implementation: `parse_payroll_detail_workbook(path)` (local file) and `parse_payroll_detail_workbook_bytes(data)` (in-memory bytes, TASK_PAYROLL_003 — used by non-file acquisition adapters).

**Employee mapping** (`resolve_employee_mappings`): the real sample workbook has no stable ADP employee id, only `Last, First Middle` names and a masked partial SSN. Matching is a deterministic structural name-key comparison (first token = first name; the rest, joined, = last name — applied symmetrically to both the ADP `Last, First` format and RF-One's `First Last` `Employee.display_name`), never a similarity/fuzzy match. A key matching **exactly one** current Employee in the Restaurant's scope auto-resolves; zero or multiple matches are `UNRESOLVED`/`AMBIGUOUS` and block persistence for that row. Confirmed/rejected mappings are cached in `payroll_provider_employee_identities`, scoped by `(source_system_id, restaurant_id, external_employee_key)`.

**Idempotency and provenance** (`persist_parsed_import`, `payroll_import_runs`): keyed by `(source_system_id, restaurant_id, sha256(content))` — content hash, never filename or acquisition method, so the same result acquired twice through different paths (e.g. once manually, once via SFTP) is still recognized as one import. `payroll_import_runs.acquisition_method` (TASK_PAYROLL_003, free string — `ADP_XLSX_FILE`/`ADP_SFTP_AES`/future `ADP_API`) records how each import's bytes actually arrived, alongside the pre-existing `source_file_name`/`source_file_hash`. A different result is always a new import; it only supersedes a specific prior `PayrollRun` when the caller explicitly passes `supersedes_import_run_id` (`--supersedes-run` on the file-based CLI), which marks the prior run `SUPERSEDED` (never deleted) and links `superseded_by_payroll_run_id`.

`persist_import(session, *, file_path, ...)` is the thin, file-based entry point (`import_payroll_results.py`): it parses the local file, then delegates everything else to `persist_parsed_import(session, *, parsed, source_file_name, source_file_hash, acquisition_method, ...)` — the acquisition-method-independent core every adapter in `rfone_data_store/payroll/acquisition.py` (§5) calls identically. `dry_run_import`/`dry_run_parsed_import` mirror this split for the read-only path (no Employee name, SSN, or bank reference is ever printed by either).

---

## 5. Payroll Result Acquisition adapters (TASK_PAYROLL_003)

`rfone_data_store/payroll/acquisition.py`, entry point `acquire_payroll_results.py`. Implements `01 Domains/Administration/Payroll/Payroll Result Acquisition.md`'s adapter contract (`PayrollAcquisitionAdapter.fetch() -> list[AcquiredPayrollFile]`), every implementation normalizing into `ParsedPayrollDetail` and persisting via `adp_importer.persist_parsed_import` — no adapter has its own persistence or idempotency logic.

- **`LocalFileAcquisitionAdapter`** — wraps a single local `.xlsx` path; `acquisition_method="ADP_XLSX_FILE"`. The pre-existing manual fallback, unchanged in behavior, now expressed through the same adapter interface.
- **`AdpSftpAcquisitionAdapter`** — genuinely automatic. Connects (via `paramiko`, imported lazily so it is only required when SFTP acquisition actually runs) to a customer-controlled SFTP endpoint ADP's Automatic Export Service delivers a scheduled report to, and downloads every not-yet-processed `.xlsx` file in the configured remote directory; `acquisition_method="ADP_SFTP_AES"`. Connection details load only from environment variables (`ADP_SFTP_HOST`, `ADP_SFTP_USERNAME`, `ADP_SFTP_REMOTE_DIRECTORY`, `ADP_SFTP_PORT`, `ADP_SFTP_PASSWORD` or `ADP_SFTP_PRIVATE_KEY_PATH`) — `from_environment()` raises `AcquisitionNotConfiguredError` naming exactly what is missing when they are absent. The transport itself is expressed as a small `SftpTransport` Protocol (`listdir`/`open`), injectable via `transport_factory=`, so the adapter's logic is fully unit-testable without a real SFTP server or network access.
- **`AdpApiAcquisitionAdapter`** — scaffold for ADP's official Payroll Output API for RUN Powered by ADP. `from_environment()` validates OAuth/mTLS credential configuration (`ADP_API_BASE_URL`, `ADP_API_CLIENT_ID`, `ADP_API_CLIENT_SECRET`, `ADP_API_CLIENT_CERT_PATH`, `ADP_API_CLIENT_KEY_PATH`); `fetch()` always raises `AdpApiNotImplementedError` today — the exact endpoint/response schema requires ADP's protected developer documentation, not guessed here (see `07 Tasks/Reports/TASK_PAYROLL_003_REPORT.md`).

`acquire_and_import(session, adapter, ...)` is the shared orchestrator: calls `adapter.fetch()`, then `persist_parsed_import` for each result, returning one `PersistResult` per acquired file.

---

## 6. Payment Execution Provider and PayrollExecutionConfiguration (TASK_PAYROLL_002; corrected by TASK_PAYROLL_003)

`rfone_data_store/payroll/payment_execution.py`. `PayrollRun.payment_execution_provider` (nullable, `CheckConstraint`-enforced to `ADP_DIRECT_DEPOSIT`/`MERCURY_ACH`) is the explicit, auditable record of who moves money to Employees for that Run — independent from `source_system_id` (who calculated the Run) and from whether payment evidence actually exists.

**Correction:** `persist_parsed_import` no longer defaults every newly created Run's provider to `ADP_DIRECT_DEPOSIT` merely because the source is ADP (TASK_PAYROLL_002's original behavior — retracted). `payment_execution_provider` now defaults to `None` everywhere (`persist_import`, `persist_parsed_import`, `acquire_and_import`, both CLIs) and is resolved as: (1) an explicit argument/flag, if given; else (2) `payment_execution.approved_provider_at(session, restaurant_id=..., at=pay_date)` — the Restaurant's approved `PayrollExecutionConfiguration` valid at the Run's `pay_date`, if one exists; else (3) left unassigned (`NULL`).

**`PayrollExecutionConfiguration`** (`payroll_execution_configurations` table) — Restaurant-scoped, temporal (`valid_from`/`valid_to`), mirroring the existing `EmployeeCompensationTerm`/`TipPolicy` pattern: a change closes the prior row and opens a new one, never overwritten in place. `approved_provider_at` selects the row valid at the queried instant (most-recently-started wins if more than one technically overlaps — never ambiguous). Because a Run's own `payment_execution_provider`, once assigned, is separately immutable (below), changing the configuration later never alters an already-created Run's assignment, even if that Run's `pay_date` now falls inside the new configuration's window.

`assign_payment_execution_provider(payroll_run, provider)` is the only sanctioned way to set `PayrollRun.payment_execution_provider`: it rejects an unsupported value, and — the production-critical invariant — raises rather than silently switching a Run already assigned to a *different* provider (re-asserting the same value is a no-op). No code path anywhere reassigns an already-assigned Run's provider; this is what makes it structurally impossible for one payable batch to ever be executed through both ADP and a future Mercury integration.

`payment_execution_status(payroll_run)` is a derived, never-stored read: `UNKNOWN` until at least one `PayrollPaymentFact` exists under the Run (i.e. the provider's own report evidences an actual payment), `PAYMENT_EVIDENCED` afterward. RF-One never infers "paid" merely because a Run was calculated or imported.

`MERCURY_ACH` is a structural placeholder only — no Mercury API call, ACH instruction, or credential/sandbox handling exists anywhere in this package.

---

## 7. Payroll Employer Cost / Labor Cost query

`rfone_data_store/payroll/labor_cost.py`. `compute_employee_labor_cost`/`compute_payroll_run_labor_cost` derive every figure from `payroll_earning_facts` (`paid_to_employee = true` only) and `payroll_employer_liability_facts` at query time — no total is persisted. `EmployeeLaborCost.payroll_employer_cost_minor` is a computed `@property`, not a column.

---

## 8. Usage

```text
python import_payroll_results.py --file "<path to PayrollDetail.xlsx>" \
    --restaurant-id 1 --period-start 2026-08-03 --period-end 2026-08-17 \
    --run-type REGULAR
    # dry-run (default): prints an aggregate-only summary, writes nothing

python import_payroll_results.py --file "<path>" --restaurant-id 1 \
    --period-start 2026-08-03 --period-end 2026-08-17 --run-type REGULAR --persist
    # manual/local-file path; writes PayrollRun/EmployeePayrollResult/facts;
    # idempotent by content hash

python acquire_payroll_results.py --source sftp --restaurant-id 1 \
    --period-start 2026-08-03 --period-end 2026-08-17 --run-type REGULAR --persist
    # automatic acquisition (TASK_PAYROLL_003) — no human downloads/uploads a
    # file for this run; requires ADP_SFTP_* environment variables (see
    # Payroll Result Acquisition.md)

python test_payroll_engine.py
    # synthetic-fixture test suite (TASK_PAYROLL_001 §34, extended by
    # TASK_PAYROLL_002/003) — run against a fresh/staging database, same
    # convention as test_tips_engine.py
```

---

## 9. Explicit non-goals

ADP Pay Data Input API / OAuth (RF-One never sends payroll input data to ADP), the actual ADP Payroll Output API request/response implementation (scaffolded only — pending ADP's protected documentation, TASK_PAYROLL_003), payroll tax calculation, a full worldwide labor-law/jurisdiction rule engine, RF-One-initiated payment execution of any kind (ADP or Mercury — RF-One only records who executes and what evidence exists, never sends money itself), a live Mercury ACH integration (structural placeholder only — no API call, credential, or sandbox), contractor/1099 payables, a bank reconciliation engine, KPI/bonus rule design, Tip calculation redesign or Tip payout execution, Personnel selection/Performance logic, benefit-provider integrations, Core changes. See `07 Tasks/Reports/TASK_PAYROLL_001_REPORT.md`, `07 Tasks/Reports/TASK_PAYROLL_002_REPORT.md` and `07 Tasks/Reports/TASK_PAYROLL_003_REPORT.md` for the full non-goal list and known limitations.
