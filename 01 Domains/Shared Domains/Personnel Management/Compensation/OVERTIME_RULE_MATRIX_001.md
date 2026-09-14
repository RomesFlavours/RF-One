# Overtime Rule Matrix — Foundation

**Version:** 0.1
**Status:** Draft — schema/metadata foundation only, no evaluator yet
**Module:** Domain / Personnel Management (Shared Domains) / Compensation
**Origin:** Overtime Rule Matrix foundation task (Product Owner decision, 2026-09-08)

---

## What this document is

This document gives the existing functional specification's reference to a **"Rule Matrix"** (`COMPENSATION_AND_INCOME_COMPOSITION_001.md` §8, §21) a concrete target: the canonical `OvertimeRule` model.

It is **not** an overtime calculation specification. No overtime is calculated, detected, or evaluated by anything described here — this document and the underlying `overtime_rules` table describe **what a statutory overtime rule is**, so that RF-One can preserve the correct regulatory context and hand accurate, complete source facts to the Payroll Provider — see [PAYROLL_HANDOFF_CONNECTOR.md](PAYROLL_HANDOFF_CONNECTOR.md) — which performs the statutory Overtime calculation. RF-One does not calculate statutory Overtime compensation.

---

## Core principle

Overtime rules are **not hardcoded** into compensation formulas. RF-One represents rules that vary by jurisdiction, effective date, time scope, threshold, statutory multiplier, regular-rate calculation method, and overlap/non-stacking behavior — as data, not as branching logic. **RF-One does not calculate statutory Overtime compensation.** Storing this metadata preserves regulatory knowledge, required context, and explainability — it is not the same as executing the statutory calculation it describes.

```text
Rule Matrix (OvertimeRule)        →  WHAT the statutory rule concept is (metadata only)
RF-One Compensation                →  prepares/preserves the required source facts and
                                       rule context (non-monetary); produces Approved
                                       Compensation Data — no statutory Overtime premium
Payroll Handoff Connector          →  transports Approved Compensation Data (automated
                                       or human — see PAYROLL_HANDOFF_CONNECTOR.md)
Payroll Provider                   →  determines which rules apply, which hours trigger
                                       them, the applicable regular rate, the premium
                                       owed, and how overlapping rules interact
```

No statutory Regular Rate, overtime premium, or overlap resolution is **implemented by this task or anywhere in this repository** — that calculation belongs to the Payroll Provider, applied downstream of RF-One's Approved Compensation Data.

---

## Ownership boundary

```text
Rule Matrix (OvertimeRule)        owns legal/regulatory rule metadata
Worked Time (future)              owns worked-time facts
Compensation (EmployeeCompensationTerm)  owns compensation terms/rates
Payroll Provider                  owns the statutory Regular Rate / overtime
                                   premium / overlap determination
```

None of these owns another's data. The Rule Matrix does not know an Employee's actual hours or rate; Compensation does not know legal thresholds; Income Composition (`COMPENSATION_AND_INCOME_COMPOSITION_001.md` §18) never consumes a statutory Overtime monetary result, because RF-One never calculates one — that determination belongs to the Payroll Provider, applied to the Approved Compensation Data Compensation produces.

---

## Legal Entity boundary

`OvertimeRule` is **not** attached to `LegalEntity`. The applicable overtime law depends on the **jurisdiction where work is performed**, not on employer identity — a single Legal Entity may operate in, and therefore be subject to, more than one jurisdiction's rules. `LegalEntity` and `OvertimeRule` jurisdiction remain separate dimensions. A future Worked Time fact may supply the jurisdiction/location needed to select applicable rules for a given hour worked; that linkage is not implemented by this task.

---

## Fields

| Field | Meaning |
|---|---|
| `rule_code` | Unique canonical identifier for this rule row (e.g. `US_FLSA_WEEKLY_OT`). A conceptual rule's later legal revision is a **new row with a new `rule_code`** (e.g. a year/version suffix), never an overwrite of the old row — see "Effective dating" below. |
| `name` | Human-readable rule name. |
| `jurisdiction_level` | `FEDERAL`, `STATE`, or `LOCAL`. |
| `jurisdiction_code` | Compact canonical string (e.g. `US`, `CA`, `FL`) — not a full Jurisdiction table; this task does not populate every jurisdiction. |
| `rule_scope` | See "Rule scopes" below. |
| `threshold_hours` | Nullable — the hour threshold that triggers the rule, where applicable. |
| `threshold_day_number` | Nullable — the day-sequence number that triggers the rule (e.g. `7` for a seventh-consecutive-day rule). |
| `total_rate_multiplier` | See "Multiplier semantics" below. |
| `regular_rate_method` | See "Regular-rate method" below. |
| `overlap_method` | See "Overlap method" below. |
| `employee_classification`, `industry_code` | Nullable, future filtering metadata only — no exemption engine, classification taxonomy, or industry taxonomy is built by this task. |
| `effective_from` / `effective_to` | See "Effective dating" below. |
| `status` | `ACTIVE` / `INACTIVE` — independent of effective dating; a historically-stored rule can be `INACTIVE` for new configuration/use while remaining fully persisted. |

---

## Rule scopes

```text
WORKWEEK            threshold evaluated across the legally defined workweek
WORKDAY              threshold evaluated within the legally defined workday
CONSECUTIVE_HOURS    threshold evaluated against a continuous-hours rule
CONSECUTIVE_DAY      triggered by sequence/day-number conditions (e.g. a
                     seventh-consecutive-day rule)
```

None of these is evaluated by this task.

**Worked Time dependency:** `WORKDAY`, `CONSECUTIVE_HOURS` and `CONSECUTIVE_DAY` cannot be evaluated reliably from aggregate pay-period hours alone. The Payroll Provider will require sufficiently granular Worked Time facts to apply these scopes statutorily; RF-One's role is to preserve and supply those facts, not to evaluate the scope itself. `CONSECUTIVE_HOURS` in particular may require actual time boundaries (clock-in/clock-out instants), not merely a `work_date`. `EmployeePayrollCalculationEarningLine` is not modified to solve this — Worked Time ownership remains entirely outside Compensation Calculation; Compensation only ever consumes already-validated Worked Time facts.

---

## Multiplier semantics

`total_rate_multiplier` is the **total** statutory pay-rate multiplier (e.g. `1.5`, `2.0`) — **not** the incremental amount still owed once straight-time wages have already been paid. Conceptually, if straight time is already included in regular earnings and the statutory total multiplier is `1.5`, the Payroll Provider may determine the additional premium owed is `0.5 × regular_rate` — that derivation is not performed or stored here, and RF-One does not perform it. The stored legal-rule fact is the total multiplier only.

---

## Regular-rate method

```text
WEIGHTED_REGULAR_RATE   names the statutory method the Payroll Provider will
                         use to derive the regular rate from includable
                         workweek remuneration and hours — RF-One does not
                         derive this rate
RATE_IN_EFFECT          names the statutory method under which a rule may
                         use the rate applicable to the work triggering
                         overtime, where legally permitted/configured —
                         applied by the Payroll Provider, not RF-One
NOT_APPLICABLE          this distinction is not required for this rule shape
```

**Federal multi-rate foundation:** the data model must not contradict the future requirement that the Payroll Provider, applying the `WEIGHTED_REGULAR_RATE` method, be able to use an Employee's multiple straight-time rates within one workweek (e.g. 20h × $12 + 25h × $22) to derive a weighted regular rate. RF-One's role is to preserve and supply those multiple rates/hours accurately (already supported — see `EmployeeCompensationTerm`/multi-rate earning lines); `OvertimeRule` stores only the legal *method* (`WEIGHTED_REGULAR_RATE`) — never a calculated Employee rate. No calculation is implemented by this task, and none is implemented by RF-One at all — this is Payroll Provider statutory treatment.

No regular rate is calculated here, and `EmployeeCompensationTerm` is not modified by this task.

---

## Overlap method

```text
NON_STACKING_MAXIMUM   overlapping triggers are not blindly added; the
                       Payroll Provider must select the legally required
                       result (e.g. the greater applicable benefit) where
                       appropriate
STACKING               premiums/rules may be cumulative where explicitly
                       allowed or required
INDEPENDENT            evaluated independently; no overlap behavior is
                       encoded by this row
```

No overlap resolution is implemented by this task, or by RF-One at all — this field only names which statutory overlap method the Payroll Provider must apply. The purpose of this field is only to avoid a data model that assumes every triggered rule simply stacks.

---

## Effective dating

`effective_from` is required; `effective_to` is nullable (open-ended/current when null). `effective_to >= effective_from` is enforced when both are present. A change in law is represented by **closing the prior row's `effective_to` and adding a new row under a new `rule_code`** — never an in-place overwrite — mirroring this schema's existing temporal-configuration pattern (`EmployeeCompensationTerm`, `TipDistributionRuleVersion`).

---

## Regular-rate numerator boundary (documented, not implemented)

The **Payroll Provider** must distinguish which compensation components belong in the statutory regular-rate numerator. Examples requiring that statutory classification include: hourly straight-time earnings, shift differentials, nondiscretionary incentives/bonuses, discretionary bonuses, commissions, customer tips, service charges, and other statutory inclusions/exclusions. **No such classification is implemented by this task, or anywhere in RF-One** — RF-One's role is limited to preserving the correct economic identity and amount of each component (e.g. the Recognized Incentive, the Tips amount) and supplying it accurately as part of Approved Compensation Data; neither Tips nor Incentive structures are changed, and no Regular Rate logic is added to the Incentive Engine or to Tips.

---

## Source of legal rules

`overtime_rules` is a canonical RF-One representation of legal/configuration rules — it is **not** a complete or production-certified legal database. This task's representative rows (Federal weekly, California daily 8h/1.5x, California daily 12h/2.0x, a seventh-consecutive-day example) exist only in the test suite (`rfone_data_store/overtime_rule_matrix_validation.py`), proving the model can represent materially different rule shapes. No exhaustive US rule set is seeded into any production table by this task.

---

## Explicitly not implemented

- Overtime hour detection, workweek/workday/consecutive-hours/consecutive-day aggregation.
- Weighted regular-rate calculation, `RATE_IN_EFFECT` calculation, overtime premium calculation.
- Stacking/non-stacking resolution.
- Minimum wage checks, exemptions, tipped-employee overtime rules.
- A general-purpose Rule Matrix engine — this document defines only the Overtime Rule Matrix foundation.
- Any change to `LegalEntity`, `Restaurant`, `EmployeeCompensationTerm`, `EmployeePayrollCalculationEarningLine`, `WorkweekDefinition`, Tips, or Incentive structures — including no field/behavior change to `WorkweekDefinition` itself (ownership note below is documentation-only).
- Any change to the existing Administration Payroll domain (`PayrollRun`, `PayrollSchedule`, `PayrollExecutionConfiguration`).

None of the calculations listed above is deferred RF-One work-in-progress — under the canonical Product Owner boundary, RF-One does not perform statutory Overtime calculations at all. Each belongs to the **Payroll Provider**, applied to the Approved Compensation Data and rule context RF-One supplies (see [PAYROLL_HANDOFF_CONNECTOR.md](PAYROLL_HANDOFF_CONNECTOR.md)).

**`WorkweekDefinition` ownership (Product Owner decision):** `WorkweekDefinition` does not belong to Administration/Payroll merely because Payroll eventually consumes or reports results. It defines the evaluation window this Rule Matrix's `WORKWEEK` scope (below) requires, so its conceptual ownership belongs to Compensation / Compensation Rules / Rule Matrix, not to Administration/Payroll. This is a documentation/ownership correction only — `WorkweekDefinition`'s table, fields and behavior are unchanged; its helper (`workweeks_within_period`) has moved to `rfone_data_store/payroll_calculation/workweek.py`.

---

## Related documents

- [COMPENSATION_AND_INCOME_COMPOSITION_001.md](COMPENSATION_AND_INCOME_COMPOSITION_001.md) §8, §21 — the functional specification sections this document gives a concrete target
- [PAYROLL_HANDOFF_CONNECTOR.md](PAYROLL_HANDOFF_CONNECTOR.md) — the canonical boundary through which RF-One's source facts and rule context reach the Payroll Provider that performs the statutory calculation described in this document
- [README.md](README.md) — Compensation (Personnel Management) module
- `03 Software/RF-One Data Store/rfone_data_store/models.py` — `OvertimeRule` (canonical schema)
- `03 Software/RF-One Data Store/rfone_data_store/overtime_rule_matrix_validation.py` — representative-shape test fixtures (not a production legal database)
- `03 Software/RF-One Data Store/rfone_data_store/payroll_calculation/workweek.py` — the `WorkweekDefinition` evaluation-window helper (`workweeks_within_period`), relocated here from the Administration/Payroll package per the ownership decision above
