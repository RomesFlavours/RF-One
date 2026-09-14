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

**Correction (Product Owner decision — supersedes the original text below):** ownership is Source Domain / source fact vs. Compensation / economic rule, not Payroll vs. "Performance Shared Domains":

```text
Source Domain (Performance, Training, Selection, Operations, or any
  other RF-One Domain) → owns the source fact/event/metric
Compensation / Income Composition → owns the economic Incentive Rule
  that converts a qualifying source fact/event/metric into an amount
```

The Source Domain owns the fact/event/metric; it does not decide its economic effect. Compensation / Income Composition (`01 Domains/Shared Domains/Personnel Management/Compensation/COMPENSATION_AND_INCOME_COMPOSITION_001.md`; the Personnel Management module formerly named Payroll) — not this Administration/Payroll module, which continues to consume only the resulting amount as an externally supplied earning fact once actually processed by the external provider — queries/consumes the source fact and owns the economic rule that converts it into an amount. A processing/event log prevents the same source event from being unintentionally processed twice by the *same* economic rule (uniqueness is source event × economic rule, not source event alone), while the same source event may legitimately trigger multiple different rules. Today Rome's Flavours uses a simple 1%-of-sales production bonus for some salaried Employees; this remains explicitly temporary business practice, not Payroll ontology.

<details><summary>Original text (superseded by the correction above)</summary>

```text
Performance / Bonus Rule → computes Bonus Result → Payroll consumes
                            amount for the relevant Payroll Run/Period
```

Payroll does not own bonus logic and computes no bonus formula. Today Rome's Flavours uses a simple 1%-of-sales production bonus for some salaried Employees; this is explicitly temporary business practice, not Payroll ontology, and must never become Payroll logic. Future KPI-based bonus rules belong to the Performance Shared Domains (`01 Domains/Shared Domains/Performance/README.md`) — Payroll only consumes the resulting amount as an externally supplied earning fact.

</details>

---

## Tips boundary

```text
Tip earning ≠ Tip payout ≠ Payroll reporting
```

Tips are calculated and paid independently of the Payroll Schedule (`01 Domains/Business Domain/Restaurant/Tips/README.md`). A Restaurant may pay Tips daily, weekly, biweekly, or monthly — Rome's Flavours currently intends weekly Tip payout, independent of its biweekly Payroll Schedule.

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

Worldwide capability is required by architecture. US/Federal/Florida overtime logic is never hard-coded into the generic Payroll engine. **Correction (Product Owner decision — RF-One does not perform statutory Payroll):** the diagram below previously implied RF-One itself derives "payable regular / overtime / other earnings" from jurisdiction rules. That is not RF-One's role. The corrected flow is:

```text
Employee / employment context
+ work location / jurisdiction
+ effective date
+ Compensation Terms
+ worked-time facts
+ Rule Matrix / regulatory context (where preserved)
        ↓
Approved Compensation Data
        ↓
Payroll Handoff Connector  (automated or human)
        ↓
Payroll Provider applies statutory labor/payroll treatment
  (including any applicable jurisdiction's regular rate,
   overtime, and other statutory earnings determination)
        ↓
Payroll result returned / recorded here for reconciliation
```

The jurisdiction layer is conceptually separate from Payroll (Administration) — Payroll consumes and records its conclusions once the Payroll Provider has applied them; it never derives them, and neither does any other RF-One component. RF-One's own role is limited to preserving accurate employment context, jurisdiction, effective dates, Compensation Terms, and worked-time facts, and to supplying them — together with any Rule Matrix metadata already preserved (`01 Domains/Shared Domains/Personnel Management/Compensation/OVERTIME_RULE_MATRIX_001.md`) — as part of Approved Compensation Data. No RF-One jurisdiction rule pack that calculates statutory earnings is implemented, planned, or implied by this document; that calculation belongs to the Payroll Provider. Until the Payroll Provider (or an authorized human Connector acting on its behalf) has applied the correct statutory treatment, a production calculation requiring legal interpretation (e.g. "is this hour overtime?") surfaces an unresolved/compliance state within RF-One rather than RF-One silently applying a default formula. No speculative worldwide rule tables are created by this task beyond the minimal generic boundary this document states.

---

## Business Rules

- A `PayrollRun.run_type` is `REGULAR` or `SPECIAL`; `SPECIAL` runs may have null `payroll_schedule_id`/`period_start`/`period_end`, `REGULAR` runs use them.
- No RF-One Payroll code computes a bonus amount from a formula — a bonus is always an externally supplied `PayrollEarningFact`.
- No RF-One Payroll code computes an overtime amount from worked-time hours — overtime, where it appears, is always an externally supplied/provider-reported earning fact; the Payroll Provider, not a future RF-One jurisdiction rule pack, performs that statutory calculation.
- A reportable Tip earning fact marked "not paid to Employee" by its source is never summed into employer-paid wage cost (see `Labor Cost.md`).
