# Payroll Schedule, Payroll Period, Pay Date, Workweek

**Version:** 1.0
**Status:** Approved
**Module:** Administration Domain / Payroll
**Origin:** TASK_PAYROLL_001

---

## Four distinct concepts

```text
PayrollSchedule  ≠  PayrollPeriod  ≠  PayDate  ≠  Workweek
```

Conflating any two of these has historically produced incorrect overtime logic (see "Workweek" below). Each is defined independently.

---

## Payroll Schedule

The configured recurring cadence under which normal Payroll Periods are generated for a Restaurant/company.

Must support at least:

```text
WEEKLY
BIWEEKLY
MONTHLY
```

This is runtime configuration, not Domain ontology — a Restaurant/company chooses the schedule its payroll provider and operating policy support. Rome's Flavours currently uses `BIWEEKLY`; this is a fact about Rome's Flavours' current configuration, never a universal default.

---

## Payroll Period

The official interval whose compensation facts are processed together in one normal payroll cycle.

```text
Schedule: BIWEEKLY
Period:   Monday 1 Sep → Sunday 14 Sep
Pay Date: Thursday 18 Sep
```

The Period is a first-class temporal context for payroll processing — it is never inferred from Pay Date. If a provider result source does not reliably contain period start/end (the real ADP `Payroll Details` export does not — see `Payroll Provider Result.md`), the Period must be supplied explicitly at import time, never guessed backward from the Pay Date or the provider's own "Payroll N" sequence label.

---

## Pay Date

The date an Employee is actually paid for a processed Payroll Period. Distinct from both the Schedule (which merely says how often pay dates recur) and the Period (which says which compensation facts were processed). A Pay Date is typically a fixed number of days after its Period ends, but that lag is administrative/provider behavior, never assumed by Payroll as a formula for deriving one date from the other.

---

## Workweek

A recurring legal/compensation evaluation interval — **not** determined by payroll frequency.

Rome's Flavours' current operational configuration:

```text
Monday → Sunday
```

and one normal biweekly Payroll Period contains **two** Workweeks.

### The canonical invariant this corrects

```text
Biweekly payroll ≠ 80-hour overtime evaluation period
```

The historically incorrect logic — `total biweekly hours > 80 → overtime` — is explicitly **not** implemented anywhere in the generic Payroll engine. Overtime determination must be delegated to the applicable jurisdiction/labor-rule layer (see `Payroll Processing.md`, "Jurisdiction / labor-rule boundary") and evaluated on the legally applicable interval(s), which are Workweeks, not Payroll Periods. A Restaurant working two Workweeks of 45 hours each inside one BIWEEKLY Period has 90 total hours and zero hours over 40 in either individual Workweek — under a standard single-Workweek overtime rule, that is zero overtime, the opposite conclusion a biweekly-total threshold would reach.

This task does not implement a complete legal rule engine. It makes the architecture capable of using one later — see `Payroll Processing.md` for the jurisdiction interface boundary.

---

## Business Rules

- A `PayrollSchedule` is Restaurant/company-scoped configuration, never a hard-coded universal default.
- A `PayrollPeriod`'s `period_start`/`period_end` are independent fields from `pay_date` — never derived from it.
- A `Workweek` boundary (its recurring start weekday) is independent configuration from `PayrollSchedule` — changing payroll frequency never changes the legal Workweek boundary, and vice versa.
- No generic Payroll code computes overtime from a Payroll-Period-total hour threshold. Any overtime determination is delegated to a future jurisdiction/labor-rule layer operating on Workweek-scoped worked time.
