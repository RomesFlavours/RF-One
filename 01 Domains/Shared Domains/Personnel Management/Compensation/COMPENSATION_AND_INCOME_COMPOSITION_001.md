# Compensation & Income Composition — V1 Functional Specification

**Version:** 1.0
**Status:** Draft — authoritative V1 functional specification, incorporating Product Owner decisions verbatim; pending formal architectural sign-off.
**Module:** Domain / Personnel Management (Shared Domains) / Compensation
**Origin:** Employee Income Composition & Payroll functional specification task (Product Owner decisions, 2026-09-08); document and module renamed from Payroll to Compensation by later Product Owner decision — see `README.md`, "Why this module is not called Payroll."
**Formerly titled:** Employee Income Composition & Payroll — V1 Functional Specification (`EMPLOYEE_INCOME_COMPOSITION_AND_PAYROLL_001.md`)

---

## What this document is

This is the **functional specification** for the first RF-One Compensation & Income Composition model. It describes **what** the system must do and the functional rules that govern it.

It is **not**:

- a database specification;
- an API specification;
- a UI specification;
- a Payroll Provider integration specification;
- a payroll-tax engine specification.

Each of those will follow separately, once this functional model is settled. Nothing in this document should be read as fixing a table name, column name, or persistence detail — the "IMPORTANT" note in §8 applies as a general caution throughout: functional meaning is decided here, physical representation is decided later.

---

## 1. Core product definition

**RF-One does not process Payroll. RF-One determines, validates and approves the compensation data required by the Payroll Provider.** RF-One owns the composition and approval of compensation; the external Payroll Provider owns statutory payroll processing, tax calculation, withholding, filing, remittance and money movement. RF-One does **not** calculate payroll taxes and does **not** replace the Payroll Provider (no provider is canonical to RF-One).

RF-One determines:

- how much compensation an Employee has **economically earned** during a defined Pay Period;
- **why** that amount was earned;
- **which Legal Entity owes it**;
- and **which components** form that amount.

Conceptually:

```text
Base Compensation
+ Overtime Premium
+ Tips
+ Recognized Incentives
+/- Authorized Adjustments
= Gross Income
```

The external Payroll Provider receives the Approved Pay Data and handles taxes, withholding, statutory deductions, employer contributions and net payment.

**Explainability of the composition is a core product requirement** — not an optional convenience. See §18.

---

## 2. Employee identity

- RF-One uses **one canonical Employee identity**.
- A separate Compensation Employee master is **not** created.
- The existing Employee identity from the RF-One Data Store / Clover integration is reused, unchanged.
- Employee identity is separate from **Employment**, **Compensation**, and **Legal Entity** relationships — these describe how a person relates to the business over time; they are not the person's identity.
- The same person may work for multiple Legal Entities.

---

## 3. Legal Entity separation

- Compensation is always calculated and approved **per Legal Entity**.
- Rome's Flavours Winter Park LLC and Rome's Flavours Mount Dora LLC are separate paying entities.
- If one Employee works for both, RF-One must create **separate** Income Compositions/Compensation results for each entity.
- Income belonging to different Legal Entities must never be unintentionally merged.

**Legal Entity is a distinct canonical concept — never Restaurant, Brand, or Corporate.** Product Owner decision (correcting an earlier implementation mapping, confirmed unsafe by read-only verification): `Restaurant` is formally an **Operational Unit** (`01 Domains/Business Domain/Restaurant/Model/OU-Restaurant.md`, "Extends: Operational Unit"), never the Legal Entity itself. **One Legal Entity may own several Restaurants**, and an Employee may work across multiple Restaurants belonging to the same Legal Entity — that Employee's hours may ultimately combine into one Legal Entity Compensation Calculation (cross-Restaurant aggregation is not implemented yet; only the Legal Entity design must allow it later). Brand remains a separate commercial/identity concept and is never repurposed as Legal Entity; Corporate remains the highest organizational container and is not persisted by this MVP. Conceptually: `Corporate → Legal Entity → Restaurant (Operational Unit) → Location`.

Legal Entity separation is explicit throughout this document — see the diagram in §21.

---

## 4. Pay Period

Pay Period is **cadence-neutral**. It must conceptually support at least:

```text
DAILY
WEEKLY
BIWEEKLY
SEMIMONTHLY
MONTHLY
OFF_CYCLE
FINAL_PAY_PERIOD
```

A Pay Period conceptually contains:

```text
Legal Entity
period_start
period_end
pay_date
```

Legal final-paycheck deadlines (e.g. how quickly a `FINAL_PAY_PERIOD` must be paid after termination) are **not hardcoded** here. Applicable timing/deadline rules belong to the Rule Matrix (§21) and depend on jurisdiction/context.

---

## 5. Compensation Engine

The Compensation Engine is a **separate functional component** responsible for determining an Employee's base earned pay from worked time.

It must support, from the first conceptual version:

```text
HOURLY
SALARIED
```

(Aligned to the canonical `compensation_basis` value already used by the existing, approved `EmployeeCompensationTerm`/`Compensation Terms.md` — not a new label.)

Salaried is **not** treated as future-only — it is a first-class compensation basis in V1, alongside Hourly.

### 5.1 Multi-rate employees

The same Employee may have **multiple legitimate hourly rates** in the same period/workweek, based on the actual work performed. Example:

```text
Server    $12/hour
Manager   $22/hour
Training  $16/hour
```

Compensation therefore **cannot** be modeled conceptually as simply:

```text
Employee -> hourly_rate
```

It must instead resolve compensation from context including:

```text
Employee
Legal Entity
Work Role / Compensation Activity
Effective Date
```

Worked hours must preserve the **role/activity** to which the rate applies — a hard requirement that flows directly into §7 (Worked Time).

---

## 6. Effective dating

Economic rules are **effective-dated**. At minimum, this applies to:

```text
Compensation Rules
Salary Rules
Incentive Rules
Pool Participation
future economic rules
```

Rules are **not overwritten**. A change creates a new effective period; the prior rule's history is preserved.

**Historical approved Compensation results are never altered because a later rule changes.** This is the same principle §20 (Approved Compensation Snapshot) and §19 (Post-Approval Corrections) apply at the Compensation-result level.

**Pool Participation, made concrete (Product Owner decision):** this principle's application to "Pool Participation" above is no longer general-only — §16 now states the specific governed fields (Effective From/To, Set By, Reason, Status) a Participation Weight must carry so this effective-dating principle is actually enforceable for it, not merely asserted.

---

## 7. Worked Time

- Compensation consumes **validated/corrected** time.
- Compensation does **not** preserve the history of time-clock errors or corrections — that audit trail belongs to Time & Attendance, not to Compensation.
- Income Composition consumes the **current validated** work record only.

Conceptually, each work segment must preserve:

```text
Employee
Legal Entity
Location
Work Date
Work Role / Compensation Activity
Validated Hours
```

Preserving Work Role/Compensation Activity on the work segment is what lets the Compensation Engine (§5.1) resolve the correct rate for each block of hours.

---

## 8. Overtime and the Rule Matrix

**RF-One does not calculate statutory Overtime compensation.** Overtime treatment is governed by legal/statutory rules the RF-One Rule Matrix preserves as metadata, not hardcoded branching inside Compensation — but preserving that metadata is not the same as executing the statutory calculation it describes. The Payroll Provider applies the statutory treatment; RF-One prepares and preserves the correct source facts and rule context it requires.

The Rule Matrix may need to preserve at least, when applicable, which statutory method governs a jurisdiction's rule:

```text
WEIGHTED_REGULAR_RATE
RATE_IN_EFFECT
```

These name the **Payroll Provider's** statutory method, not an RF-One calculation. `RATE_IN_EFFECT` is **not** universally applicable — its applicability, like any Rule Matrix metadata, may depend on:

```text
jurisdiction
employee classification
legal entity
workweek
compensation arrangement
effective date
contractual conditions
other relevant context
```

This functional document does **not** attempt to encode federal/state law itself, and does not assign RF-One the job of applying it — see §21, "Rule Matrix boundary," for the canonical boundary this context supplies to.

**The Rule Matrix has a concrete foundation:** the canonical `OvertimeRule` model — see [OVERTIME_RULE_MATRIX_001.md](OVERTIME_RULE_MATRIX_001.md). It stores WHAT an overtime rule is (jurisdiction, scope, thresholds, total rate multiplier, regular-rate method, overlap method, effective dating) — regulatory/rule metadata only. RF-One does not execute this metadata into a statutory Regular Rate, overtime premium, or any other monetary Overtime result; identifying which rule context applies to a Person/Pay Period and validating that the required source facts are present remain non-monetary preparation activities. The **Payroll Provider** determines which rules apply to the Approved Compensation Data it receives and what is statutorily owed — see [OVERTIME_RULE_MATRIX_001.md](OVERTIME_RULE_MATRIX_001.md) and [PAYROLL_HANDOFF_CONNECTOR.md](PAYROLL_HANDOFF_CONNECTOR.md).

---

## 9. Tips Engine

Tips is an **independent, stateless calculation engine**.

```text
Compensation  →  asks Tips for: Employee / Legal Entity or Location / Pay Period
Tips          →  returns the calculated amount
```

Compensation does not know, and never duplicates, the Tips formula.

Tips **intermediate** calculations are **not** versioned/persisted merely because Compensation is recalculated — recalculation is cheap and stateless.

The Tips amount actually included in an **APPROVED** Compensation result becomes part of the Approved Compensation Snapshot (§20).

**Principle:**

```text
Tips Engine calculates.
Compensation snapshots what was actually approved/paid.
```

---

## 10. Incentive Engine

The Incentive Engine is a **transversal RF-One engine** — not merely a traditional Bonus Engine.

Any validated RF-One event or metric may potentially become input to an Incentive Rule. Possible source Domains include, without limiting the architecture:

```text
Sales
Dining Intelligence / Reviews
Training
Operational Knowledge
Performance
Workforce
Customer Experience
Cost Control
future RF-One Domains
```

The Incentive Engine must **not** need to know how the source Domain produced the event/metric — it consumes validated facts, not source-Domain implementation detail.

---

## 11. Metric/Event vs. Formula

This separation is fundamental to the Incentive Engine:

```text
Metric/Event    = describes what happened or what was measured.
Incentive Rule  = determines what economic effect that fact has.
```

Examples:

```text
NET_SALES = 150000
FIVE_STAR_REVIEW_EMPLOYEE_MENTION = 7
TRAINING_PASSED = 1 event
```

These facts can feed economic rules **independently** of each other — a Metric/Event's existence does not imply any particular economic treatment until an Incentive Rule is applied to it.

---

## 12. Incentive Rule types

The initial formula families:

| Type | Meaning | Example |
|---|---|---|
| `FIXED` | A fixed amount for qualifying occurrence(s). | $50 for completing a certification. |
| `PER_UNIT` | An amount per qualifying unit of a metric/event. | $10 per confirmed five-star review mention. |
| `PERCENT_OF_VALUE` | A percentage of a measured value. | 1% of an Employee's personal net sales. |
| `POOL` | A shared pool computed from a business metric, then allocated among participants (§15-§16). | 2% of Location net sales, split by participation. |
| `THRESHOLD` | An amount unlocked once a metric crosses a defined threshold. | $100 once quarterly reviews reach 20. |
| `TIERED` | Different rates/amounts apply at different bands of a metric. | $5/unit for the first 10 units, $8/unit above 10. |

The design must permit **additional future calculation types** without redesigning Income Composition — these six are the initial set, not an exhaustive closed list.

These are calculation methods, not separate economic concepts. Each formula ultimately produces one or more **Incentive Contributions**, positive or negative according to the Incentive Rule (§14) — never a separately-named Bonus or Disincentive result.

### 12.1 Implementation scope (V1) — Product Owner decision

**Implementation scope is not Domain scope.** All six formula families above remain part of the canonical RF-One Incentive model, unreduced. This subsection records only which of them the **first Incentive Engine software release** implements — a progressive-delivery decision, not a change to the model documented in §12 or §14.

**V1 implementation:**

| Type | V1 status | Example |
|---|---|---|
| `FIXED` | Implemented | Management target achieved → +$300 Incentive Contribution. |
| `PER_UNIT` | Implemented | 5 qualifying reviews × $10 → +$50 Incentive Contribution; unit source is validated RF-One Events/Metrics. |
| `PERCENT_OF_VALUE` | Implemented | Wine Sales = $5,000, Rule = 1% → +$50 Incentive Contribution. |
| `THRESHOLD` | Implemented | Customer Rating ≥ 4.7 → +$250 Incentive Contribution. Threshold operators and persistence are not redesigned by this task. |
| `TIERED` | **Deferred** — canonical, not yet implemented | Units 1–10 → $2/unit, 11–20 → $3/unit, >20 → $5/unit. Concept remains valid and documented; no V1 implementation required. |
| `POOL` | **Deferred** — canonical, not yet implemented | See §15–§16 (unchanged). Deferred because it introduces additional allocation/participation logic beyond the first Incentive Engine release — not because Pool is unsupported. |

**Deferred does not mean unsupported.** `TIERED` and `POOL` are **supported by the canonical model** but **not part of the first software release**. Neither is deprecated, rejected, removed, or out of scope for the Domain — they are sequencing decisions only.

Illustrative V1 usage (examples only — never hardcoded as business rules):

```text
FIXED:              Management target achieved → $300
PER_UNIT:            3 qualifying 5-star reviews × $10 → $30
PERCENT_OF_VALUE:    1% of $8,000 wine sales → $80
THRESHOLD:           Training completion rate >= 95% → $150
```

This subsection defines **what** the first release implements, not **how** — no database schema, ORM model, API contract, formula interpreter, persistence strategy, calculation execution architecture, UI, Rule editor, or Pool execution architecture is decided here. Those belong to a later implementation task. The unified Incentive model (§14) — Incentive Contributions, algebraic sum, `Recognized Incentive = MAX(0, Raw Incentive)`, no separate Disincentive concept — applies identically to every implemented formula family and is unchanged by this scoping decision.

---

## 13. Incentive Event Log

RF-One maintains a **pre-Compensation-Approval Incentive Event Log**. This is **not** Compensation calculation history — it records validated source facts/events that **may** be used by Incentive Rules, independent of whether or how they are ever consumed economically.

An event should conceptually contain enough information to identify:

```text
event type
employee/subject where applicable
legal entity/location where applicable
event date
source domain
unique source reference
status
```

Example:

```text
FIVE_STAR_REVIEW_EMPLOYEE_MENTION
Employee = Giovanna
Location = Winter Park
Source Domain = Dining Intelligence
Source Reference = unique review
Status = CONFIRMED
```

### 13.1 Event uniqueness

Source events must be **idempotent/non-duplicable**. Running the source engine multiple times, or recalculating Compensation, must **never** create duplicate economic events. This applies to every event source, including:

```text
review mention
training completion
certification
performance event
future event sources
```

### 13.2 Uncertain event attribution

```text
Certain attribution:
  "Giovanna was fantastic"       -> may become CONFIRMED automatically.

Uncertain attribution:
  "Giovana was fantastic"        -> may become PENDING_CONFIRMATION.
```

Only **valid/confirmed** events may contribute economically. Human confirmation may resolve uncertain attribution.

This document does **not** encode specific fuzzy-matching algorithms — attribution-confidence mechanics belong to whichever source Domain/capability produces the event, not to this specification.

### 13.3 One event, multiple rules

One event **can** contribute to multiple Incentive Rules simultaneously. Example: one qualifying five-star review can:

- generate $10 through a `PER_UNIT` rule; **and simultaneously**
- contribute toward a quarterly `THRESHOLD` rule.

**Event existence and Rule Application are separate concepts** — an event is a fact; how many rules apply it, and how, is a separate, independent question per rule.

### 13.4 Training as an event source example

Training is documented here only as an **example** of a source Domain — it has no special Compensation-specific logic:

```text
TRAINING_PASSED  ->  generates an event
Incentive Rule    ->  may assign economic value to that event
```

The same pattern applies uniformly to every other source Domain listed in §10.

---

## 14. Incentive Contributions and the Recognized Incentive

RF-One has **one** economic concept: the **Incentive**. There is no separate economic concept called Disincentive. A negative economic effect is a **negative Incentive Contribution** — it exists only to reduce the Incentive being evaluated, never as an independent downstream amount.

**Canonical definition:** an Incentive is variable compensation produced by one or more measurable positive or negative contributions evaluated according to an Incentive Rule. The final Recognized Incentive cannot be less than zero.

```text
Events / Metrics / Conditions
        ↓
Incentive Rule
        ↓
Positive and Negative Incentive Contributions
        ↓
Algebraic Sum
        ↓
MAX(0, Result)
        ↓
Recognized Incentive
```

**Canonical formula:**

```text
Raw Incentive        = Σ Positive Contributions + Σ Negative Contributions
Recognized Incentive = MAX(0, Raw Incentive)
```

A **negative Incentive Contribution** reduces the Incentive being evaluated only. It must **not** reduce:

```text
agreed hourly compensation
salary
legally owed overtime
Tips
Tip Credit / minimum-wage make-up
previously owed compensation
Authorized Adjustments unrelated to Incentives
any other legally or contractually owed amount
```

The management purpose of a negative Incentive Contribution is **motivational**, not punitive — it can only ever act on the Incentive being evaluated, never on compensation the Employee is otherwise legally or contractually owed.

### 14.1 Zero floor (the Incentive Floor)

**A Recognized Incentive cannot be negative.** If the algebraic sum of contributions is zero or negative, no Incentive is recognized — there is no separate negative economic result.

```text
EXAMPLE A
Wine Sales Contribution       +200
Review Contribution            +80
Training Contribution          +50
Performance Contribution       -75
                              -----
Raw Incentive                  255
Recognized Incentive           255
```

```text
EXAMPLE B
Positive Contributions        +200
Negative Contributions       -300
                              -----
Raw Incentive                 -100
Recognized Incentive             0
```

In Example B there is **no Disincentive of -100** — there is simply no recognized Incentive. No negative economic value is ever sent to Compensation or to the Payroll Provider.

### 14.2 Bonus is not a separate engine

A "bonus" is not a separate RF-One economic engine. Where the word is useful as ordinary business terminology, common-sense description, or a Payroll Provider earning-code label (e.g. Rome's Flavours' production bonus, `Payroll Processing.md` "Bonus boundary"), it may remain in use — but the canonical RF-One economic concept behind it is always the **Incentive**: a `FIXED` Incentive Rule that produces one positive Incentive Contribution is functionally what "a bonus" means here, not a distinct Bonus Engine, Incentive Engine, and Disincentive Engine as three separate things.

---

## 15. Pool creation

A `POOL` Incentive Rule (§12) has two stages.

**Stage 1 — calculate the total economic pool:**

```text
Winter Park Net Sales = $150,000
Pool Rate             = 2%
Total Pool            = $3,000
```

**Stage 2 — allocate the Pool among eligible participants** (§16).

---

## 16. Pool participation model

The current conceptual allocation model may depend on **two** factors:

```text
A. participation weight/value assigned per hour;
B. eligible hours actually worked during the relevant pool period.
```

Conceptually:

```text
Weighted Units = Eligible Hours × Participation Weight
```

Example:

```text
Anthony    80h × 1.5 = 120
Giovanna  100h × 1.2 = 120
Tatiana    60h × 1.0 =  60

Total Weighted Units = 300
```

```text
Employee Pool Share = Employee Weighted Units / Total Weighted Units
```

Therefore:

```text
Anthony    40%
Giovanna   40%
Tatiana    20%
```

For a $3,000 pool:

```text
Anthony   $1,200
Giovanna  $1,200
Tatiana     $600
```

For each participant, the allocated amount becomes a **positive Incentive Contribution** feeding that participant's Recognized Incentive (§14) — the same unified model every other Incentive Rule type uses, unchanged by this Pool-specific allocation logic.

**IMPORTANT:** this document does not decide whether the persisted configuration value is literally called `percentage`, `weight`, or `hourly economic equivalent` — that belongs to the later data-model specification. Only the **functional meaning** (a per-participant weight applied to eligible hours to produce a share of the pool) is decided here.

### 16.1 Pool validity

A Pool configuration that requires complete participation allocation **cannot be considered valid** while its required allocation configuration is incomplete/inconsistent. The user must **not** be able to finish/activate an invalid Pool configuration. RF-One does **not** automatically rebalance allocations to make an incomplete configuration valid.

### 16.2 Pool Participation governance (Product Owner decision)

**A Pool Participation Weight is an effective-dated governed fact, never an anonymous timeless value.** This makes §6's general effective-dating principle concrete for "Pool Participation" specifically. At minimum, a Pool Participation record must conceptually carry:

```text
Person
Pool / Incentive Rule
Participation Weight
Effective From
Effective To
Set By
Reason
Status
```

These are conceptual fields only — this document does not decide database types, an ORM shape, or a persistence/versioning mechanism for them (same caution as the "IMPORTANT" note above).

**Weight vs. Share remain distinct, as already defined above — unchanged by this governance addition:**

```text
Participation Weight  = INPUT — a multiplier applied to Eligible Hours
                         (Weighted Units = Eligible Hours × Participation Weight)
Pool Share             = DERIVED — Participant Weighted Units / Total Weighted Units
```

Participation Weight is never redefined as a percentage, and is never renamed to Pool Share.

**Pool / Incentive Rule relationship:** every Participation Weight belongs to exactly one specific `POOL` Incentive Rule / Pool configuration (§12, §15). A Participation Weight must never exist without an identifiable Pool/Incentive Rule it belongs to.

**Effective dating and no-overwrite:** a Participation Weight has an `Effective From` and an `Effective To`. A change in weight does **not** overwrite the prior value — it creates a new effective period, and the prior value's history is preserved. Example:

```text
Person: Anthony
Pool Rule: MANAGEMENT_POOL

Jan 1 – Mar 31   Weight = 1.20
From Apr 1       Weight = 1.50
```

The historical `1.20` record remains preserved, never rewritten. RF-One must conceptually be able to answer both "What Participation Weight was valid for Anthony on March 15?" (`1.20`) and "...on April 15?" (`1.50`). **Pool Participation history is preserved; changes create new effective periods rather than overwriting prior Participation Weights.**

**Set By:** the identity of the authorized RF-One actor who established the Participation Weight. `Set By` alone is sufficient governance metadata for this decision — a separate, mandatory `Approved By` is **not** required now; a future approval workflow may add one if required, but dual approval is not introduced by this document.

**Reason:** a concise explanation of why the value was assigned or changed (e.g. management responsibility level, role responsibility change, temporary operational assignment, revised incentive structure — illustrative only, never a hardcoded closed category list).

**Status:** a Pool Participation record requires a status sufficient to distinguish whether it is currently usable. Minimum conceptual statuses: `DRAFT`, `ACTIVE`, `RETIRED` — reusing the same status vocabulary an existing RF-One effective-dated configuration record already uses for the identical purpose (`TipPolicy.status`, `03 Software/RF-One Data Store/rfone_data_store/models.py`: "Conceptual values: DRAFT, ACTIVE, RETIRED") rather than inventing a duplicate vocabulary. No additional status is introduced without need.

**Historical reconstruction (conceptual requirement for future implementation):** RF-One must eventually be able to answer, for any Person and any historical date: which Participation Weight applied, which Pool Rule it belonged to, who set it, why, and when it became and stopped being effective. This governance model does not itself implement that reconstruction — Pool remains deferred from Incentive Engine V1 (§12.1) — it only states the conceptual fields future implementation must carry so the answer is possible.

---

## 17. Authorized Adjustments

Authorized Adjustments are **separate** from Incentives and from Compensation.

An adjustment may address corrections or exceptional authorized amounts. Conceptually it captures:

```text
Employee
Legal Entity
Amount
Reason
Reference Period (when applicable)
Authorized By
```

Adjustments must **not** become a shortcut for arbitrarily changing agreed compensation — they exist for corrections and genuinely exceptional, explicitly authorized amounts, not as a routine compensation-setting mechanism.

---

## 18. Income Composition Engine

The Income Composition Engine is the **central composition layer**. It consumes results from:

```text
Compensation Engine
Overtime / Rule Matrix
Tips Engine
Incentive Engine
Authorized Adjustments
```

From the Incentive Engine, the Income Composition Engine consumes the **Recognized Incentive** only (§14) — never a raw positive/negative composition, and never a negative amount.

and produces **one explainable Income Composition** for:

```text
Employee
Legal Entity
Pay Period
```

### 18.1 Explainability

Explainability is **mandatory**. The system must allow the gross total to be decomposed into its contributing components.

For an Incentive component specifically, the system must be able to identify conceptually:

```text
Incentive Rule
source Metric/Event
source (Domain)
measured value
positive/negative Contribution
resulting Recognized Incentive
```

The system must be able to answer:

> **"Why is this employee's Gross Income this amount?"**

---

## 19. Compensation states

The first functional state model:

```text
OPEN
CALCULATED
APPROVED
EXPORTED
CLOSED
```

| State | Meaning |
|---|---|
| `OPEN` | The period exists and inputs may still change. |
| `CALCULATED` | Income Composition has been generated but can still be recalculated. |
| `APPROVED` | An authorized user approves the result; the Approved Compensation Snapshot is created (§20). |
| `EXPORTED` | The Approved Pay Data has been handed to the Payroll Provider. |
| `CLOSED` | The operational cycle is complete. |

### 19.1 Approval

For V1: **single authorized approval**. No mandatory dual approval yet.

Compensation Approval must conceptually retain:

```text
approved_by
approved_at
```

---

## 20. Approved Compensation Snapshot

`CALCULATED` values remain **recalculable**. Once `APPROVED`, the approved Compensation becomes an **immutable fiscal/business snapshot** — the Approved Compensation Snapshot.

The snapshot must preserve enough detail to reconstruct what the company approved, including:

```text
Employee
Legal Entity
Pay Period
Hours used
Compensation rates used
Salary component (where applicable)
Base Compensation
Overtime
Tips
Incentive detail (positive/negative Contributions and the Recognized Incentive)
Adjustments
Gross Income
Approved By
Approved At
```

**Later rule changes must never alter the snapshot** — this is the Compensation-result-level expression of the effective-dating principle in §6.

### 20.1 Post-approval corrections

Approved/closed Compensation is **not rewritten**. If a difference is discovered later, RF-One creates a **Prior Period Adjustment**, applied in:

```text
a subsequent appropriate Pay Period,
  or
an Off-Cycle Compensation process, if required.
```

Historical Compensation remains intact in every case.

---

## 21. Rule Matrix boundary

The Rule Matrix is the **regulatory/rule-governance layer**. Income Composition avoids hardcoded jurisdiction-specific branches throughout — instead, it supplies context such as:

```text
Employee
Employee Classification
Legal Entity
Jurisdiction
Location
Work Date
Pay Period
Workweek
Compensation Type
Role
Employment Status
Relevant Event
```

The Rule Matrix identifies which legal/rule metadata is contextually relevant, given that context — never a statutory monetary result. Income Composition consumes RF-One Compensation values (§18); it never consumes an RF-One-calculated statutory Overtime premium or Regular Rate, because RF-One does not calculate one. That statutory determination belongs to the Payroll Provider, applied downstream to the Approved Compensation Data Compensation produces (§20, §22).

---

## 22. Payroll Provider boundary

Between an Approved Compensation Snapshot (§20) and the Payroll Provider sits the **Payroll Handoff Connector** — see [PAYROLL_HANDOFF_CONNECTOR.md](PAYROLL_HANDOFF_CONNECTOR.md) for the canonical definition. The Connector may be an automated API/file/SFTP integration or a manual human handoff (a human operator entering approved values into ADP or another provider is a valid Connector) — the functional boundary is identical either way. The Connector transports/maps Approved Compensation Data into whatever form the Payroll Provider requires; it never decides or changes an approved value.

The exact RF-One → Payroll Provider data contract is **intentionally not finalized** in this document. A subsequent document — **RF-One → Payroll Provider Data Contract** — will define it, once a specific provider (e.g. ADP) has been selected and its available fields/screens have been reviewed.

No provider-specific field is invented or assumed here.

RF-One sends only **recognized** economic values downstream — a Recognized Incentive of $200 (from +$300/-$100 internal Contributions) is handed off as one recognized amount, never as a separate `BONUS = +300` and `PENALTY = -100`. The Payroll Provider does not need RF-One's internal positive/negative Incentive composition unless a future provider mapping/reporting need requires it.

---

## 23. Functional architecture (concise flow)

Legal Entity separation applies throughout — every branch below is evaluated **per Legal Entity**, never merged across entities (§3).

```text
RF-One Domains (Sales, Dining Intelligence/Reviews, Training,
Operational Knowledge, Performance, Workforce, Customer
Experience, Cost Control, future Domains)
    |
    v
Event / Metric Log  (per Legal Entity/Location where applicable — §13)
    |
    v
Incentive Engine  (Metric/Event -> Incentive Rule -> positive/negative
                   Contribution -> Recognized Incentive — §10-§16)
    |
    v
Recognized Incentives  (zero floor applied — §14.1)
    |
    |         Time (validated, per Legal Entity — §7) --> Compensation Engine (§5)
    |                                                            |
    |                                                            v
    |                                                       Rule Matrix (§8, §21)
    |
    |         Tips (per Legal Entity/Location/Period) --> Tips Engine (§9)
    |
    |         Authorized Adjustments (per Legal Entity — §17)
    |                    |
    v                    v
    +----------> Income Composition Engine (per Employee, per Legal
                  Entity, per Pay Period — §18)
                       |
                       v
                 Gross Employee Income
                       |
                       v
                    Compensation  (per Legal Entity — §19)
                       |
                       v
                    Approve  (§19.1)
                       |
                       v
             Approved Compensation Snapshot  (§20)
                       |
                       v
             Payroll Handoff Connector  (automated OR manual — §22)
                       |
                       v
             Payroll Provider (e.g. ADP)  (§22)
```

---

## 24. Explicit non-goals for V1

Restating the scope boundaries stated throughout this document, in one place:

- No payroll-tax calculation is introduced into RF-One.
- No specific jurisdiction/labor-law rule is hardcoded here — that belongs to the Rule Matrix.
- No Payroll Provider field/data contract is defined here.
- No fuzzy-matching/attribution algorithm is defined here.
- No automatic Pool-allocation rebalancing is performed.
- No dual-approval workflow is required for V1.
- No database, API, or UI design is decided by this document.

---

## Related documents

- [README.md](README.md) — this module's purpose and its relationship to `Administration/Payroll`
- [PAYROLL_HANDOFF_CONNECTOR.md](PAYROLL_HANDOFF_CONNECTOR.md) — the canonical Connector boundary referenced in §22
- [../README.md](../README.md) — Personnel Management Domain
- [../../Administration/Payroll/README.md](../../Administration/Payroll/README.md) — the administrative execution/recording boundary (the external Payroll Provider) this specification's Approved Pay Data is handed to
- [../../Administration/Personnel Cost.md](../../Administration/Personnel%20Cost.md) — `Total Employee Cost`, the Administration-level canonical cost concept this specification's approved Gross Income eventually feeds
- [../../../Business Domain/Restaurant/Tips/README.md](../../../Business%20Domain/Restaurant/Tips/README.md) — the Tips Engine (§9)
- [../../Taxation/README.md](../../Taxation/README.md) — jurisdiction/tax boundary the Rule Matrix (§8, §21) relates to
- [../../Performance/README.md](../../Performance/README.md) — one possible Incentive Event source Domain (§10)
