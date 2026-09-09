# Compensation (Personnel Management)

**Version:** 0.2
**Status:** Draft — first functional specification
**Module:** Domain / Personnel Management (Cross Domain) / Compensation
**Formerly named:** Payroll — renamed by explicit Product Owner decision (see "Why this module is not called Payroll" below). All content below is otherwise unchanged in substance.

---

## Purpose

This module answers: **how much compensation has an Employee economically earned for a Pay Period, why, and which Legal Entity owes it — and what Approved Pay Data must RF-One send to the Payroll Provider?**

RF-One determines the composition of an Employee's compensation — Base Compensation, Overtime Compensation, Tips, Recognized Incentives and Authorized Adjustments — and produces an explainable, auditable Income Composition per Employee, per Legal Entity, per Pay Period.

---

## Why this module is not called Payroll

**RF-One does not process Payroll. RF-One determines, validates and approves the compensation data required by the Payroll Provider.**

RF-One owns the composition and approval of compensation. The external Payroll Provider owns statutory payroll processing, tax calculation, withholding, filing, remittance and money movement.

This module does **not** calculate payroll taxes and does **not replace a Payroll Provider** (e.g. ADP, Check, Gusto Embedded, or another provider — no provider is canonical to RF-One). The external Payroll Provider receives the RF-One-approved Approved Pay Data and handles tax withholding, statutory deductions, employer contributions, filings and net payment.

---

## Legal Entity is a distinct canonical concept

**Legal Entity** is the actual juridical/employing entity — never `Restaurant` (an Operational Unit), `Brand` (a commercial/identity concept), or `Corporate` (the highest organizational container, not persisted by this MVP). One Legal Entity may own several Restaurants; an Employee may work across multiple Restaurants belonging to the same Legal Entity, and that Employee's hours may ultimately combine into one Legal Entity Compensation Calculation. Compensation / Income Composition is always calculated and approved per Legal Entity — see the main specification, §3.

---

## Compensation vs. external Payroll processing

```text
RF-One (this module)                         External Payroll Provider
─────────────────────                         ───────────────────────────────
determines compensation:                      receives Approved Pay Data
  Base Compensation                           applies:
  + Overtime Compensation                       tax withholding
  + Tips                                        statutory deductions
  + Recognized Incentives                       employer contributions
  +/- Authorized Adjustments                    filings / remittance
  = Approved Compensation / Approved Pay Data    net payment
```

RF-One is the source of the **economic composition and its approval**, never of the **statutory tax/payment execution**. The Payroll Provider may change without changing this module.

---

## Relationship to `Administration/Payroll`

`01 Domains/Cross Domain/Administration/Payroll/` already exists and remains unchanged: it is the **administrative execution/recording** boundary — what the external Payroll Provider actually processed, imported after the fact from a provider result. This module is the opposite direction of the same overall flow: it **determines, validates and approves**, before external processing, what RF-One expects the compensation to be.

```text
This module (Compensation / Income Composition)  →  Approved Compensation Snapshot / Approved Pay Data
                                                    →  Payroll Handoff Connector (automated OR manual — see
                                                        PAYROLL_HANDOFF_CONNECTOR.md)
                                                    →  External Payroll Provider
                                                    →  Administration/Payroll (what the provider actually did)
                                                    →  Provider Reconciliation (not defined here)
```

Neither module redefines or duplicates the other. `Administration/Payroll` never composes or approves an economic amount; this module never records or reconciles what a provider actually paid. The **Payroll Handoff Connector** — see [PAYROLL_HANDOFF_CONNECTOR.md](PAYROLL_HANDOFF_CONNECTOR.md) — is the canonical boundary in between: it transports/maps Approved Compensation Data to whatever the Payroll Provider requires, automated or a human operator alike, and never decides or changes the approved values.

---

## Current authoritative functional specification

- [COMPENSATION_AND_INCOME_COMPOSITION_001.md](COMPENSATION_AND_INCOME_COMPOSITION_001.md) — the authoritative V1 functional specification (formerly `EMPLOYEE_INCOME_COMPOSITION_AND_PAYROLL_001.md`): Employee identity and Legal Entity separation, Pay Period, Compensation Engine (Hourly/Salary, multi-rate), effective dating, Worked Time boundary, Overtime/Rule Matrix boundary, Tips Engine boundary, Incentive Engine (Metric/Event, Incentive Rule types, Event Log, uniqueness, attribution confidence, Incentive Contributions and the Recognized Incentive, zero floor, Pool creation and participation, §16.2 Pool Participation governance — Effective Dating/Set By/Reason/Status, §12.1 V1 implementation scope — FIXED/PER_UNIT/PERCENT_OF_VALUE/THRESHOLD implemented first; TIERED/POOL canonical but deferred), Authorized Adjustments, the Income Composition Engine, explainability, Compensation states, approval, the Approved Compensation Snapshot, post-approval corrections, and the Rule Matrix/Payroll Provider boundaries.
- [OVERTIME_RULE_MATRIX_001.md](OVERTIME_RULE_MATRIX_001.md) — the Overtime Rule Matrix foundation: the canonical `OvertimeRule` model (jurisdiction, scope, thresholds, multiplier, regular-rate method, overlap method, effective dating) that gives §8's "Rule Matrix" reference a concrete target. Schema/metadata only — no Overtime Evaluator is built yet.
- [PAYROLL_HANDOFF_CONNECTOR.md](PAYROLL_HANDOFF_CONNECTOR.md) — the canonical boundary between Approved Compensation Data and the external Payroll Provider, valid whether automated or a manual human handoff.

This is a **functional** specification only — not a database specification, not an API specification, not a UI specification, not a Payroll Provider integration specification, not a payroll-tax engine specification.

---

## Pending

The **RF-One → Payroll Provider Data Contract** — the exact field-level data handed to the external provider — is intentionally **not defined yet**. It will follow as a separate document once a specific provider has been selected and its available fields/screens have been reviewed. Do not assume or invent any provider's fields from this module in the meantime.

---

## Related documents

- [../README.md](../README.md) — Personnel Management Domain
- [PAYROLL_HANDOFF_CONNECTOR.md](PAYROLL_HANDOFF_CONNECTOR.md) — the canonical Compensation → Payroll Provider handoff boundary
- [../../Administration/Payroll/README.md](../../Administration/Payroll/README.md) — the administrative execution/recording boundary this module hands its approved result to
- [../../Administration/Personnel Cost.md](../../Administration/Personnel%20Cost.md) — `Total Employee Cost`, the Administration-level canonical cost concept this module's Approved Compensation eventually feeds
- [../../../Business Domain/Restaurant/Tips/README.md](../../../Business%20Domain/Restaurant/Tips/README.md) — the Tips Engine this module consumes without duplicating
- [../../Taxation/README.md](../../Taxation/README.md) — jurisdiction/tax boundary this module's Rule Matrix dependency relates to
