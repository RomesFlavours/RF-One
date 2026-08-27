# Labor Cost

**Version:** 1.0
**Status:** Approved
**Module:** Administration Domain / Payroll
**Origin:** TASK_PAYROLL_001

---

## Payroll Employer Cost

The employer-paid payroll cost attributable to an Employee for a processed Payroll Run.

```text
Payroll Employer Cost
=
employer-paid earnings
+
employer-side payroll liabilities
```

Where:

- **employer-paid earnings** = the sum of `PayrollEarningFact.amount` for that Employee/Run where `paid_to_employee = true`. A reportable Tip line the provider marks as *not* paid to the Employee (see `Payroll Provider Result.md`) is structurally excluded here — it is never added a second time as employer-paid wage cost merely because it appears on the payroll report. It was already paid to the Employee from customer Tip funds, not from the employer's payroll disbursement.
- **employer-side payroll liabilities** = the sum of `PayrollEmployerLiabilityFact.amount` for that Employee/Run (e.g. employer Social Security, employer Medicare).

Employee withholding taxes (federal/state income tax withholding, employee-side Social Security/Medicare) are never part of this sum — they are not modeled as employer labor cost at all, structurally: no employee-withholding table exists in this schema for `Payroll Employer Cost` to (mis)reference (see `Payroll Provider Result.md`, "Employee tax and deduction detail — deliberately not modeled").

`Payroll Employer Cost` is never stored as a redundant total column — it is always computed from the atomic `PayrollEarningFact`/`PayrollEmployerLiabilityFact` rows, so a correction to one atomic fact is immediately reflected without a separate reconciliation step.

---

## Fully Loaded Labor Cost — legacy synonym for Total Employee Cost

`Payroll Employer Cost` is one component/source of the canonical, Administration-level concept `Total Employee Cost`, defined in full — including the causal-attribution test, `Unallocated Personnel Cost`, `Total Personnel Cost`, calendar-day derivation for multi-period costs, and the rejection of artificial overhead allocation — in `../Personnel Cost.md`.

```text
Payroll Employer Cost
+ other Employee-attributable economic cost facts (asset-mediated or direct)
→ Total Employee Cost
```

`Fully Loaded Labor Cost` is retained only as a non-canonical/legacy/business synonym for the same Employee-attributable total. It is **never** `Direct Employee Labor Cost + Allocated Labor Overhead` — RF-One does not load arbitrary shared/generic personnel overhead onto an Employee (`../Personnel Cost.md` §2). Illustrative, non-exhaustive examples of the "other Employee-attributable cost facts" `Total Employee Cost` extends to: health insurance, retirement employer contribution, workers compensation, company vehicle, company-paid vehicle insurance, company-paid fuel, other employer-paid benefits/costs. This list is never a mandatory taxonomy. This task implements only the `Payroll Employer Cost` half (from ADP), because RF-One does not yet possess any of the other employer-attributable cost sources; the extension point is structural, so a future employer-attributable-cost fact can be summed alongside `Payroll Employer Cost` for the same Employee/period without altering the `Payroll Employer Cost` calculation itself.

`Total Employee Cost` is important to future Personnel Management Selection/Performance/Personnel Decisions reasoning, but Payroll does not make those decisions — see `01 Domains/Administration/Payroll/README.md`, "Relationship to Personnel Management," and `../Personnel Cost.md` §11.

---

## Labor Cost query/service

For a processed Payroll Run, the minimal query/service this task provides returns, per Employee:

```text
employer-paid earnings
employer liabilities
Payroll Employer Cost
provider-reported payment amount / net pay (where available)
```

and Run totals of the same four figures, summed across Employees. All totals are calculated from atomic persisted facts at query time — never persisted as a convenience aggregate — so the output is deterministic and auditable back to the imported provider rows that produced it.

---

## Business Rules

- `Payroll Employer Cost` for an Employee/Run is always `sum(paid PayrollEarningFact.amount) + sum(PayrollEmployerLiabilityFact.amount)`; no other input contributes to it.
- A `PayrollEarningFact` with `paid_to_employee = false` never contributes to `Payroll Employer Cost`'s earnings component.
- No employee-withholding amount is ever added to `Payroll Employer Cost`.
- No `payroll_employer_cost_total`-shaped column is persisted anywhere in the schema; the value is always computed.
- `Total Employee Cost` (`Fully Loaded Labor Cost`) is additive over `Payroll Employer Cost` and zero or more other Employee-attributable cost facts; it is never computed by discounting or estimating `Payroll Employer Cost` itself, and never includes an `Allocated Labor Overhead`-shaped component (`../Personnel Cost.md` §2).
