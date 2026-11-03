# Payroll

**Version:** 1.0
**Status:** Approved
**Module:** Administration Domain / Payroll
**Origin:** TASK_PAYROLL_001

---

## Purpose

**Payroll** is the administrative executor that processes Employee compensation and records what an external payroll provider actually did.

```text
RF-One operational facts/configuration
→ payroll inputs can be prepared manually today
→ ADP RUN processes payroll
→ RF-One acquires the provider-generated payroll facts — automatically where
  configured (Payroll Result Acquisition.md), or via manual Payroll Details
  Excel export as a fallback
→ RF-One reconstructs actual payroll cost by Employee and Payroll Run
```

Central principle:

```text
Payroll does not decide operational value, personnel performance, bonus
policy, tip policy, or labor law. It receives or resolves the inputs
required to process employee compensation, records externally realized
payroll results, and exposes those results for labor-cost analysis and
reconciliation.
```

---

## Canonical boundary

```text
Payroll ≠ Restaurant
Payroll ≠ Compensation
Payroll ≠ Management
Payroll ≠ Taxation
Payroll ≠ Accounting
Payroll ≠ ADP
Payroll ≠ legal/labor rules (jurisdiction)
```

Payroll may consume facts/configuration from all of them, and owns none of them:

```text
Restaurant / Work Time            → worked time
Tips                              → reportable tip amount
Performance / Bonus logic         → bonus amount
Compensation (Terms)              → employee-specific compensation (owned by Administration/Compensation)
Jurisdiction Rule Pack            → legally payable/reportable treatment
Payroll                           → administrative processing
Payroll Provider (ADP)            → tax/compliance/direct-deposit processing
```

---

## Files in this section

| File | Concept |
|---|---|
| [Payroll Schedule and Period.md](Payroll%20Schedule%20and%20Period.md) | PayrollSchedule, PayrollPeriod, PayDate, Workweek — four distinct concepts |
| [Payroll Processing.md](Payroll%20Processing.md) | PayrollRun (REGULAR/SPECIAL), Bonus boundary, Tips boundary, jurisdiction/labor-rule boundary |
| [Payroll Provider Result.md](Payroll%20Provider%20Result.md) | The provider (ADP) boundary and the atomic provider-result facts imported from Payroll Details Excel |
| [Payroll Result Acquisition.md](Payroll%20Result%20Acquisition.md) | Genuinely automatic vs. manual-fallback acquisition; the adapter abstraction (local file / ADP SFTP AES / ADP Payroll Output API); verified ADP mechanisms |
| [Payment Execution.md](Payment%20Execution.md) | Payroll calculation ≠ Payroll result acquisition ≠ Payment execution; the `payment_execution_provider` field (`ADP_DIRECT_DEPOSIT` today, `MERCURY_ACH` future), `PayrollExecutionConfiguration`, and double-payment prevention |
| [Labor Cost.md](Labor%20Cost.md) | `Payroll Employer Cost` — the Payroll-sourced component of the Administration-level `Total Employee Cost` (see [../Personnel Cost.md](../Personnel%20Cost.md)) |

---

## Employment relationship boundary

Payroll operates on Employees/employment relationships. Contractors/independent service providers are outside this Payroll model. A person is never classified as a contractor merely because they perform a second function or are paid outside Payroll — that classification, if ever needed, belongs to a future employment-relationship concept, not to Payroll.

---

## Relationship to Compensation

[Compensation](../Compensation/README.md) is the sibling Administration module that determines and approves what is owed and hands Approved Pay Data to the Payroll Provider through the Payroll Handoff Connector. Payroll records what the provider actually processed. Payroll consumes [Compensation Terms](../Compensation/Compensation%20Terms.md) — Employee-specific, temporal compensation (HOURLY/SALARIED, multiple concurrent functions/rates) — owned by Compensation since 2026-10-25 (previously listed in this folder; content unchanged).

## Relationship to Management

Payroll produces economic facts that Management / Organization may consume; it does not make Organization's decisions about the person in the role.

```text
Payroll      → actual labor cost
Performance  → actual output/performance evidence
Selection    → candidate alternatives
Organization (comparison of alternatives) → compares expected value using all of the above
```

`cheapest Employee = best Employee` is never a conclusion Payroll draws or implies. Payroll only supplies cost evidence; Management / Organization owns the comparison and the decisions reserved to authorized people — see `01 Domains/Shared Domains/Management/Organization/README.md`.

---

## Relationship to Taxation

Payroll does not replicate a payroll tax engine or a jurisdiction's legal rules. Where a calculation genuinely requires legal/tax interpretation (e.g. overtime determination, withholding computation) and no verified jurisdiction rule pack is configured, Payroll surfaces an unresolved/compliance state rather than silently applying a default formula. Taxation (`01 Domains/Shared Domains/Taxation/README.md`) is the Domain that would own the eventual jurisdiction rule content; Payroll only consumes its conclusions.

---

## Relationship to Restaurant

Payroll consumes Restaurant facts (worked time via Shift, Employee identity, optionally Employee Assignment for provenance) but does not depend on Restaurant semantics to be internally valid — a non-Restaurant business could use the same Payroll model. See `01 Domains/Business Domain/Restaurant/Organization/Employee Assignment.md` for the existing Tips/Compensation resolution contract this Domain reuses without redefining.

---

## Related documents

- [../README.md](../README.md) — Administration Domain
- [../Personnel Cost.md](../Personnel%20Cost.md) — `Total Employee Cost`/`Total Personnel Cost`, the canonical concept `Payroll Employer Cost` feeds into
- [../../Restaurant/Tips/README.md](../../../Business%20Domain/Restaurant/Tips/README.md) — Tips boundary Payroll consumes without duplicating
- [../Compensation/README.md](../Compensation/README.md) — Compensation, including the Bonus/Incentive boundary
- [../../Management/Organization/README.md](../../Management/Organization/README.md) — decision semantics about the person in the role
- [../../Taxation/README.md](../../Taxation/README.md) — jurisdiction/tax boundary
- `03 Software/RF-One Data Store/PAYROLL.md` — runtime/database implementation of this Domain
- `07 Tasks/Reports/TASK_PAYROLL_001_REPORT.md` — implementation history
- `07 Tasks/Reports/TASK_PAYROLL_002_REPORT.md` — Payment Execution Provider introduction and production-readiness review
- `07 Tasks/Reports/TASK_PAYROLL_003_REPORT.md` — genuine automatic ADP acquisition, explicit payment-executor configuration
