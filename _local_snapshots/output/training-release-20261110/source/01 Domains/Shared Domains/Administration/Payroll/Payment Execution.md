# Payment Execution

**Version:** 1.1
**Status:** Approved
**Module:** Administration Domain / Payroll
**Origin:** TASK_PAYROLL_002; corrected by TASK_PAYROLL_003

---

## Three independent layers

```text
Payroll calculation  ≠  Payroll result acquisition  ≠  Payment execution
```

- **Payroll calculation** — who determines gross wages, taxes, deductions, employer contributions, net pay. Today: ADP (`Payroll Provider Result.md`, "Provider boundary"). RF-One does not replace this.
- **Payroll result acquisition** — how RF-One learns the authoritative Payroll results (an ADP structured report today; a future ADP API is additive, never required — `Payroll Provider Result.md`). This is data acquisition, never payment execution.
- **Payment execution** — who actually moves money to the Employee. This document defines that boundary.

Conflating any of these has direct financial risk. It is why a Payment Execution Provider must be an explicit, recorded fact on the `PayrollRun` it applies to, never inferred from the mere fact that a Run was calculated or imported.

---

## Payment Execution Provider

An explicit, auditable field on `PayrollRun`:

```text
payment_execution_provider ∈ { NULL, ADP_DIRECT_DEPOSIT, MERCURY_ACH }
```

- **`ADP_DIRECT_DEPOSIT`** — ADP is responsible for moving funds. The corresponding `PayrollPaymentFact` rows (`Payroll Provider Result.md`) are evidence of what ADP itself reports as paid, never a second, RF-One-initiated payment. This is the only value used in current production (`Payroll Processing.md` boundary is preserved: RF-One never initiates a payment when this value is set).
- **`MERCURY_ACH`** — reserved for a future provider where RF-One determines final employee payable amounts and Mercury executes ACH. **Not implemented.** No RF-One code calls a Mercury API, sends an ACH instruction, or fabricates Mercury credentials/sandbox behavior. This value exists only so the canonical model can represent the future selection without a later Payroll redesign (TASK_PAYROLL_002).
- **`NULL`** — not yet assigned. Historical `PayrollRun` rows created before this concept existed are never guessed into one value or the other (see Migration Safety, `07 Tasks/Reports/TASK_PAYROLL_002_REPORT.md`).

**Correction (TASK_PAYROLL_003):** who calculated/supplied a Payroll result does not determine who executes payment. The ADP importer/acquisition adapters (`Payroll Result Acquisition.md`) do **not** default a newly created Run's `payment_execution_provider` to `ADP_DIRECT_DEPOSIT` merely because the source is ADP — TASK_PAYROLL_002's original importer default is retracted. A Run's provider is now resolved as, in order:

```text
1. an explicit selection passed at import/acquisition time (e.g. --payment-execution-provider), else
2. the Restaurant's approved PayrollExecutionConfiguration (below) valid at the Run's pay_date, else
3. left unassigned (NULL) — never guessed
```

### PayrollExecutionConfiguration — the approved-executor configuration

A Restaurant-scoped, temporally valid statement of which provider is currently approved for new PayrollRuns, mirroring the existing `EmployeeCompensationTerm`/`TipPolicy` temporal-configuration pattern (a change closes the prior row's `valid_to` and opens a new row — history is never overwritten in place):

```text
PayrollExecutionConfiguration: restaurant_id, provider, valid_from, valid_to
```

This is what lets Option 2 above work without a human re-specifying the provider on every single import, while keeping the eventual `ADP_DIRECT_DEPOSIT` → `MERCURY_ACH` transition temporally safe: changing the configuration only affects Runs created *after* the change (evaluated against each Run's own `pay_date`), and — because `payment_execution_provider` is separately immutable once assigned (below) — can never retroactively alter a Run created under the prior configuration, even if that Run's `pay_date` would now fall inside the new configuration's window.

`payment_execution_provider` itself is deliberately scoped to `PayrollRun` — the same granularity as the payable batch itself — not only to the Restaurant-wide configuration, because an explicit per-Run selection (Option 1) must remain possible even when it disagrees with the standing configuration (e.g. a one-off correction).

---

## Double-payment prevention (critical invariant)

```text
At most one Payment Execution Provider ever executes a given PayrollRun's payable amounts.
```

Once a `PayrollRun.payment_execution_provider` is assigned a non-null value, it is immutable — no RF-One code path changes it to a different provider afterward. This is enforced procedurally (`rfone_data_store/payroll/payment_execution.py`, `assign_payment_execution_provider`), not only documented: an attempt to reassign a Run already carrying a *different* provider value raises, rather than silently switching. Re-asserting the same value already on the Run is a safe no-op, matching this Domain's existing idempotency conventions (`Payroll Provider Result.md`).

This is the smallest correction of the double-payment risk possible today: because Mercury execution is not implemented, no code path can actually attempt a second execution yet — the guard exists so that when Mercury execution is eventually built, it is architecturally impossible for it to run against a Run ADP has already been assigned to execute, and vice versa.

---

## Payment evidence vs. payment execution status

RF-One never fabricates a "paid" conclusion. Whether a `PayrollRun` has actual payment evidence is always derived, never stored, from the presence of `PayrollPaymentFact` rows (`Payroll Provider Result.md`) under its Employee results:

```text
no PayrollPaymentFact rows present   → payment execution evidence UNKNOWN
one or more PayrollPaymentFact rows  → payment evidenced (by the provider's own report)
```

A `PayrollRun` may therefore be fully calculated/imported (`status = COMPLETE`) with `payment_execution_provider = ADP_DIRECT_DEPOSIT` while payment evidence remains `UNKNOWN` — e.g. an ADP export that, for some reason, does not include `Payment N` columns for an Employee. RF-One never infers "paid" merely because Payroll was calculated or imported.

---

## Business Rules

- `PayrollRun.payment_execution_provider` is `NULL` (not yet assigned) or exactly one of `ADP_DIRECT_DEPOSIT` / `MERCURY_ACH` — enforced by a database `CheckConstraint`.
- Once assigned a non-null value, `payment_execution_provider` is never reassigned to a *different* value by any RF-One code path; reassigning the same value is a no-op.
- No RF-One code computes or stores a "paid"/executed status independent of `PayrollPaymentFact` evidence — payment execution status is always derived at query time, never persisted as a redundant column.
- `MERCURY_ACH` exists structurally only; no RF-One code sends an ACH instruction, calls a Mercury API, or fabricates Mercury credentials/sandbox behavior.

---

## Related documents

- [README.md](README.md) — Payroll module
- [Payroll Result Acquisition.md](Payroll%20Result%20Acquisition.md) — the acquisition layer this document's boundary distinguishes payment execution from
- [Payroll Provider Result.md](Payroll%20Provider%20Result.md) — `PayrollPaymentFact` evidence this document builds on
- [Payroll Processing.md](Payroll%20Processing.md) — `PayrollRun` lifecycle
- `03 Software/RF-One Data Store/rfone_data_store/payroll/payment_execution.py` — runtime implementation
- `07 Tasks/Reports/TASK_PAYROLL_002_REPORT.md` — task that introduced this document
- `07 Tasks/Reports/TASK_PAYROLL_003_REPORT.md` — task that corrected the implicit ADP default and added `PayrollExecutionConfiguration`
