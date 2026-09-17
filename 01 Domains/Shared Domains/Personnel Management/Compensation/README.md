# Compensation (Personnel Management)

**Version:** 0.2
**Status:** Draft — first functional specification
**Module:** Domain / Personnel Management (Shared Domain) / Compensation
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

`01 Domains/Shared Domains/Administration/Payroll/` already exists and remains unchanged: it is the **administrative execution/recording** boundary — what the external Payroll Provider actually processed, imported after the fact from a provider result. This module is the opposite direction of the same overall flow: it **determines, validates and approves**, before external processing, what RF-One expects the compensation to be.

```text
This module (Compensation / Income Composition)  →  Approved Compensation Snapshot / Approved Pay Data
                                                    →  Payroll Handoff Connector (automated OR manual — see
                                                        PAYROLL_HANDOFF_CONNECTOR.md; V1 manual implementation
                                                        now built, see "Implementation status" below)
                                                    →  External Payroll Provider
                                                    →  Administration/Payroll (what the provider actually did,
                                                        recorded manually or by import into the SAME
                                                        PayrollRun/EmployeePayrollResult/PayrollEarningFact
                                                        model this module always deferred to)
                                                    →  Compensation Reconciliation (V1: semantically comparable
                                                        components only — never Provider net pay against a
                                                        Compensation total; see "Implementation status")
```

Neither module redefines or duplicates the other. `Administration/Payroll` never composes or approves an economic amount; this module never records or reconciles what a provider actually paid. The **Payroll Handoff Connector** — see [PAYROLL_HANDOFF_CONNECTOR.md](PAYROLL_HANDOFF_CONNECTOR.md) — is the canonical boundary in between: it transports/maps Approved Compensation Data to whatever the Payroll Provider requires, automated or a human operator alike, and never decides or changes the approved values.

---

## Current authoritative functional specification

- [COMPENSATION_AND_INCOME_COMPOSITION_001.md](COMPENSATION_AND_INCOME_COMPOSITION_001.md) — the authoritative V1 functional specification (formerly `EMPLOYEE_INCOME_COMPOSITION_AND_PAYROLL_001.md`): Employee identity and Legal Entity separation, Pay Period, Compensation Engine (Hourly/Salary, multi-rate), effective dating, Worked Time boundary, Overtime/Rule Matrix boundary, Tips Engine boundary, Incentive Engine (Metric/Event, Incentive Rule types, Event Log, uniqueness, attribution confidence, Incentive Contributions and the Recognized Incentive, zero floor, Pool creation and participation, §16.2 Pool Participation governance — Effective Dating/Set By/Reason/Status, §12.1 V1 implementation scope — FIXED/PER_UNIT/PERCENT_OF_VALUE/THRESHOLD implemented first; TIERED/POOL canonical but deferred), Authorized Adjustments, the Income Composition Engine, explainability, Compensation states, approval, the Approved Compensation Snapshot, post-approval corrections, and the Rule Matrix/Payroll Provider boundaries.
- [OVERTIME_RULE_MATRIX_001.md](OVERTIME_RULE_MATRIX_001.md) — the Overtime Rule Matrix foundation: the canonical `OvertimeRule` model (jurisdiction, scope, thresholds, multiplier, regular-rate method, overlap method, effective dating) that gives §8's "Rule Matrix" reference a concrete target. Schema/metadata only — no Overtime Evaluator is built yet.
- [PAYROLL_HANDOFF_CONNECTOR.md](PAYROLL_HANDOFF_CONNECTOR.md) — the canonical boundary between Approved Compensation Data and the external Payroll Provider, valid whether automated or a manual human handoff.

This is a **functional** specification only — not a database specification, not an API specification, not a UI specification, not a Payroll Provider integration specification, not a payroll-tax engine specification.

---

## Implementation status

**The Approval + Approved Compensation Snapshot foundation (§19-20) is implemented** (Compensation V1 Task 1) — `CompensationPreparationRun` can be approved by an authorized actor reference, producing an immutable `ApprovedCompensationSnapshot`/`ApprovedEmployeeCompensationResult`/`ApprovedEmployeeEarningLine` set of rows (`03 Software/RF-One Data Store/rfone_data_store/payroll_calculation/approval.py`).

**Operational V1 with manual, bidirectional Payroll Provider communication is now implemented** (Compensation V1 — manual Payroll Handoff task):

- **Incentive Contributions and the Recognized Incentive (§14)** are implemented as a manual-entry capability — no Event Log/Incentive Rule engine exists yet (§10-13 remain conceptual/documented only), but a human can enter positive/negative Incentive Contributions per Employee per run, and `incentive_recognized_amount = MAX(0, SUM(contributions))` flows into the calculation, the approved snapshot (with full positive/negative detail preserved, never only the total), and the export view (`rfone_data_store/payroll_calculation/incentives.py`).
- **`tip_credit_makeup_amount`** is now a preservable field (nullable — `NULL` means "to be completed by the Payroll Provider", never a false zero); its calculation still belongs entirely to the Payroll Provider (§22) and is never computed by RF-One.
- **Compensation states now include `EXPORTED`/`CLOSED`** in the `payroll_calculation_runs.status` constraint (`EXPORTED` is reached automatically on the first recorded communication; nothing transitions a run to `CLOSED` yet — that remains a future operational decision).
- **The manual Payroll Handoff Connector (`PAYROLL_HANDOFF_CONNECTOR.md`)** is implemented: `rfone_data_store/payroll_calculation/export.py` builds a per-Employee manual export view (flagging, never inventing, a missing Payroll Provider employee-ID mapping) and records a human operator's confirmation that communication to the Provider actually happened (`CompensationExportConfirmation`) — never itself evidence that payroll was processed or paid.
- **The manual return of the Payroll Provider's result, and reconciliation, are implemented** (`rfone_data_store/payroll_calculation/reconciliation.py`) — reusing the EXISTING Administration/Payroll return model (`PayrollRun`/`EmployeePayrollResult`/`PayrollEarningFact`) rather than a new one. Reconciliation compares only semantically comparable components (Regular Pay to Regular Pay, Tips to Tips, Recognized Incentive to a Provider-reported bonus/incentive line) and refuses to compare across Legal Entities; it never compares the Provider's net pay to a Compensation total. Differences, missing components and Provider-added components are all surfaced explicitly and can be annotated (note + OPEN/EXPLAINED/ACCEPTED resolution) without ever overwriting the originally approved values.
- **Authorized Adjustments remain out of scope** (conceptual/documented only) — not part of this task.
- The operational UI is `03 Software/RF-One Web/compensation_routes.py` (replacing the former "Work in progress" page), calling the service layer above directly with no duplicated business logic.
- **Deployed** to the existing AWS App Runner service (`rfone-web`) on 2026-09-11, migration `f7174fa37e93` applied to the real RDS PostgreSQL database (`03 Software/Infrastructure/README.md` has the exact deploy procedure and verification). SALARIED compensation terms and any Employee missing required data are shown explicitly and excluded from calculation — never a computed zero.
- **Approval re-validates completeness itself** (`approval.approve_compensation_preparation`, `CompensationPreparationIncompleteDataError`) — an included Employee with no earning lines, or with an earning line referencing a non-HOURLY (e.g. SALARIED) or missing Compensation Term, blocks approval of the whole run and names every affected Employee, even if the calculation rows were written directly rather than through `payroll_calculation.engine`.

This closes the previous "optional Connector return / manual recording" framing in `PAYROLL_HANDOFF_CONNECTOR.md` for V1 — the manual return path is no longer deferred.

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
