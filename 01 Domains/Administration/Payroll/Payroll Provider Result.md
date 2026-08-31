# Payroll Provider Result

**Version:** 1.0
**Status:** Approved
**Module:** Administration Domain / Payroll
**Origin:** TASK_PAYROLL_001

---

## Provider boundary

A payroll provider is an external Runtime service. Today: **ADP RUN Powered by ADP**. Tomorrow: another provider.

```text
Payroll Domain ≠ ADP
```

No ADP field is built into canonical Payroll semantics. RF-One reuses the existing `SourceSystem`/provider conventions (`03 Software/RF-One Data Store/DATABASE_SCHEMA.md` §1) — ADP is one row in `source_systems`, not a schema-level assumption.

**ADP input automation is explicitly not the priority.** The current workflow may remain: RF-One prepares/calculates inputs → the Product Owner enters hours/overtime/bonus/reportable Tips manually in ADP. The important automation is the opposite direction:

```text
ADP processed payroll → Payroll Details result → RF-One import
```

No ADP API credential, OAuth onboarding, or Pay Data **Input** API integration is required or implemented for this capability (RF-One never sends payroll input data to ADP). This is unrelated to, and does not contradict, `Payroll Result Acquisition.md`'s use of ADP's **output**-side mechanisms (Automatic Export Service / Payroll Output API) to automatically retrieve the *completed* result in the direction shown above — those are output/acquisition APIs, never input APIs, and RF-One never writes payroll data to ADP through either.

---

## Provider Result as a Reality fact

The ADP `Payroll Detail` report contains externally realized provider facts. Inspection of a real sample workbook (`PayrollDetail.xlsx`, single "Payroll Detail" sheet) confirmed the actual layout:

```text
rows 1-4   report header (Company, Report, Check Dates From/pay-run label, To)
row 7      column headers
rows 8-N   one row per Employee
row N+2/3  "Company Total" / "Pay Frequency Total" summary rows — not
           Employee facts, must be excluded from import
row N+5/6  footnotes: "* Items Not Paid To Employee",
           "** Items Not Paid To Employee and Excluded From Some Wages"
```

Per-Employee columns actually present: `Employee Name`, `SSN` (masked, last 4 digits only), `TIN`, `Pay Frequency`, `Department`, up to three repeated `Earning N` / `Hours` / `Rate` / `Amount` groups, `Total Hours`, `Total Earnings`, employee-side tax columns (`FED FIT`, `FED SOCSEC`, `FED MEDCARE`, `Total Taxes`), `Deduction Total`, `Net Pay`, employer-side liability columns (`FED SOCSEC-ER`, `FED MEDCARE-ER`, `Total Employer Liability`), and one or more `Payment N` / `Payment N Check Date` / `Payment N Transaction ID or Check #` / `Payment N Amount` groups.

Critically, the report does **not** contain the Payroll Period's `period_start`/`period_end` — only a Pay Date and a provider-internal "Payroll N" sequence label. Per `Payroll Schedule and Period.md`, the Period is never inferred from this; it must be supplied explicitly by the operator at import time.

The report also confirms the exact fact this Domain models structurally: a "Cash tips*" earning line is included in the SS/Medicare wage base (both employee and employer liability columns reflect it) while being excluded from `Total Earnings` and excluded from `Net Pay` — i.e. reported and taxed, but not paid to the Employee through payroll. This is direct evidence for the Tips boundary in `Payroll Processing.md`.

```text
Provider facts may be stored.
Derived totals should not be duplicated as canonical truth when they can
be recomputed safely from atomic imported facts.
```

RF-One does not copy the entire ADP report schema blindly — only the atomic facts the Labor Cost use case actually needs.

---

## Minimal provider-result model

### PayrollRun

```text
id, source_system_id, payroll_schedule_id (nullable for SPECIAL runs),
period_start (nullable), period_end (nullable), pay_date, run_type,
provider_reference, status, provenance
```

### EmployeePayrollResult

One Employee's externally processed result context for a Run. Prefers identifiers/references and atomic child facts over redundant totals — it carries no stored earnings/liability/payment total of its own.

### PayrollEarningFact

A provider-reported earning/reporting line:

```text
employee_payroll_result_id, earning_type (normalized), source_label
(raw, as printed), quantity (nullable), unit (nullable), rate (nullable),
amount, paid_to_employee (parsed from a trailing "*"), sequence
```

This supports `REGULAR`, `OVERTIME`, `SALARY`/base pay, `BONUS`, `CASH_TIPS`, and any future provider earning label — without a schema change, because `earning_type`/`source_label` are free strings, not an enum. An entirely new provider label the importer has never seen is stored with a normalized `earning_type` derived generically from its own text, not rejected.

### PayrollEmployerLiabilityFact

A provider-reported employer-side liability/cost line: `employee_payroll_result_id, liability_type, source_label, amount`. Employee tax withholding (`FED FIT`, employee-side `FED SOCSEC`/`FED MEDCARE`) is never modeled here — it is not employer labor cost (see `Labor Cost.md`).

### PayrollPaymentFact

A provider-reported employee payment fact: `employee_payroll_result_id, pay_date, payment_method, payment_amount, provider_payment_reference (nullable, already-masked by the provider), sequence`. This is what lets RF-One answer "how much did ADP actually pay Employee X for Payroll Run Y?" directly from the provider's own per-Employee detail, independent of an aggregate bank debit (see "Actual payment reconstruction" below).

---

## Employee tax and deduction detail — deliberately not modeled

RF-One does not replicate ADP's tax engine or an employee tax ledger. Federal/state withholding, employee-side Social Security/Medicare withholding, and every employee deduction are **not** given a canonical model. The real sample confirms this is safe: `Net Pay` equals the corresponding `Payment N Amount` directly, so `PayrollPaymentFact` already answers the "actual payment" question without RF-One ever needing to re-derive it from `Total Earnings − Total Taxes − Deductions`. ADP remains authoritative for its own detailed payroll tax/compliance processing.

---

## Employee mapping

The real sample workbook contains **no stable ADP employee/associate identifier column** — only `Employee Name` (formatted `Last, First [Middle]`) and a masked partial `SSN` (last 4 digits only; never the full SSN). This is provider-independent evidence, not an ADP quirk to special-case: the import boundary must work from name evidence alone.

```text
if a stable provider Employee identifier exists → map it explicitly
if only names exist → do not use fuzzy matching silently
```

RF-One resolves this with an explicit, provider-scoped external identity mapping (never an ADP-specific column on `employees`): a deterministic, structural name-key comparison (first token as first name, remaining tokens as last name, on both the `Last, First Middle` provider format and the `First Last` RF-One `display_name` format) is attempted; a match is accepted automatically **only when exactly one** current Employee in the import's Restaurant scope matches the key. Two Employees sharing a key, or zero matches, are surfaced as `AMBIGUOUS`/`UNRESOLVED` and excluded from persistence for that Employee — never guessed. A human can then explicitly confirm a mapping once, after which it is reused. This is exact structural matching, not similarity/fuzzy matching: a mismatch never silently produces a wrong assignment, only a safe non-match requiring review.

---

## Import provenance and idempotency

Every imported Payroll provider result is auditable: source system, source file name, file hash (SHA-256), `imported_at`, the `PayrollRun` it produced, the provider pay date, and mapping/reconciliation status are all preserved. The workbook binary itself is never stored in the database.

Import is idempotent by file hash: re-importing the exact same file for the same scope is detected and produces no duplicate `PayrollRun`/`EmployeePayrollResult`/fact rows. A **corrected** provider report (same period/pay date, different content, different hash) is never silently merged into or overwriting the prior import's history — it requires an explicit operator confirmation that it supersedes a specific prior import, and both the original and the corrected import remain traceable afterward.

---

## Actual payment reconstruction

```text
ADP Employee payment facts → employee-level detail
Bank                        → aggregate settlement/debit
RF-One                      → later reconciliation
```

The provider result lets RF-One answer "how much did ADP actually pay Employee X for Payroll Run Y?" directly — this is the current operational pain (direct deposit produces one aggregate bank debit that loses employee-level detail). The bank transaction is a settlement/reconciliation source, never the source of employee-level payroll detail. A deep bank reconciliation engine is not implemented by this task; this is documented as the next integration point.

---

## Spreadsheet handling

The ADP workbook is treated as a source document: never modified, never converted into a new canonical spreadsheet. RF-One's database stores normalized provider facts, not workbook formatting. Local source payroll spreadsheets/exports remain Git-ignored — never committed.
