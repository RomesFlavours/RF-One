# Payroll Processing

**Version:** 1.0
**Status:** Approved
**Module:** Administration Domain / Payroll
**Origin:** TASK_PAYROLL_001

---

## Payroll Run

One actual administrative payroll processing event.

Supported at least:

```text
REGULAR   — a normal cycle tied to a PayrollSchedule/PayrollPeriod
SPECIAL   — an off-cycle event: annual production bonus, one-off
            discretionary bonus, correction, other off-cycle earning
```

A SPECIAL run is never forced into a fake recurring schedule — its `payroll_schedule_id`/`period_start`/`period_end` may be null where genuinely not applicable, while `pay_date` remains required. Optional reference/effective-period semantics are kept where a SPECIAL run does relate to a specific prior period (e.g. a correction).

---

## Worked Time vs. paid non-work time

```text
Worked Time ≠ Paid Time / Paid Entitlement
```

Worked Time may come from POS Shifts, manual work records, or future time systems. Paid non-work concepts (PTO, holiday pay, sick pay, other paid entitlement) may generate payroll earnings without any corresponding worked-time fact. Not every payable item is measured in hours — the earning model is extensible to an optional `quantity` / `unit` / `rate` / `amount`, rather than requiring hours for every earning (see `Payroll Provider Result.md`).

---

## Bonus boundary

```text
Performance / Bonus Rule → computes Bonus Result → Payroll consumes
                            amount for the relevant Payroll Run/Period
```

Payroll does not own bonus logic and computes no bonus formula. Today Rome's Flavours uses a simple 1%-of-sales production bonus for some salaried Employees; this is explicitly temporary business practice, not Payroll ontology, and must never become Payroll logic. Future KPI-based bonus rules belong to Personnel Management's Performance module (`01 Domains/Personnel Management/Performance/README.md`) — Payroll only consumes the resulting amount as an externally supplied earning fact.

---

## Tips boundary

```text
Tip earning ≠ Tip payout ≠ Payroll reporting
```

Tips are calculated and paid independently of the Payroll Schedule (`01 Domains/Restaurant/Tips/README.md`). A Restaurant may pay Tips daily, weekly, biweekly, or monthly — Rome's Flavours currently intends weekly Tip payout, independent of its biweekly Payroll Schedule.

Payroll receives only the **reportable** Tip amount applicable to a Payroll Period, for tax/compliance processing. The Tip principal itself is not automatically employer-paid wage cost merely because it appears on a payroll provider report — the real ADP `Payroll Details` export confirms this directly: it reports Tips as an earning line used for Social Security/Medicare tax calculation while explicitly marking them "* Items Not Paid To Employee" (see `Payroll Provider Result.md`). Payroll never treats such a line as employer-paid earnings, never duplicates Tip calculation logic, and never becomes a second Tip source of truth.

### Tip payout facts — required follow-up, not implemented here

A Tip payout that actually occurred is an external/economic fact belonging to Reality:

```text
Tip calculation → Tip payout execution fact → Payroll reportable Tips
                                                for Payroll Period
```

The existing Tips schema (`03 Software/RF-One Data Store/DATABASE_SCHEMA.md` §4b) does not yet persist a dedicated payout fact — `TipAllocation` records what was *calculated* as owed to an Employee, not that it was actually *paid out* (in cash or otherwise). This task documents the gap and does not close it: a future task should introduce a minimal `TipPayout` fact only when a concrete integration need requires it, rather than inventing a broad payout engine now. Payroll Tip integration for this task is limited to consuming an operator-supplied reportable Tip amount per Employee/Period, as it already arrives from the ADP report.

---

## Jurisdiction / labor-rule boundary

Worldwide capability is required by architecture. US/Federal/Florida overtime logic is never hard-coded into the generic Payroll engine.

```text
Employee / employment context
+ work location / jurisdiction
+ effective date
+ Compensation Terms
+ worked-time facts
        ↓
applicable labor rule set
        ↓
payable regular / overtime / other earnings
```

The jurisdiction layer is conceptually separate from Payroll — Payroll consumes its conclusions, never derives them. A future task will implement the first real jurisdiction rule pack using verified authoritative legal sources (see `01 Domains/Taxation/README.md` for the transversal Domain such a rule pack would relate to). Until applicable rules are configured and verified, a production calculation requiring legal interpretation (e.g. "is this hour overtime?") surfaces an unresolved/compliance state rather than silently applying a default formula. No speculative worldwide rule tables are created by this task beyond the minimal generic boundary this document states.

---

## Business Rules

- A `PayrollRun.run_type` is `REGULAR` or `SPECIAL`; `SPECIAL` runs may have null `payroll_schedule_id`/`period_start`/`period_end`, `REGULAR` runs use them.
- No RF-One Payroll code computes a bonus amount from a formula — a bonus is always an externally supplied `PayrollEarningFact`.
- No RF-One Payroll code computes an overtime amount from worked-time hours — overtime, where it appears, is always an externally supplied/provider-reported earning fact, pending a future jurisdiction rule pack.
- A reportable Tip earning fact marked "not paid to Employee" by its source is never summed into employer-paid wage cost (see `Labor Cost.md`).
