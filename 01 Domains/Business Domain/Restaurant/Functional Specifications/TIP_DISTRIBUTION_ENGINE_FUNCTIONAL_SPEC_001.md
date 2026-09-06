# RF-One — Tip Distribution Engine
## Functional Specification 001

### Status
Functional specification approved at analysis level before implementation.

---

## 1. Purpose

The Tip Distribution Engine transforms tip/gratuity amounts recorded by the POS into final employee-payable amounts by applying configurable rules at Company/Location level.

The engine must not be built around Rome’s Flavours-specific policy. Rome’s Flavours is one configuration of the generic engine.

---

## 2. Fundamental Separation

RF-One separates three layers:

### A. Source Facts
Facts received from the POS/time-clock system, including:
- Orders
- Payments
- voluntary tips
- automatic gratuity / service charge
- employee
- clock-in / clock-out
- sales
- order type / category
- refunds

### B. Distribution Rules
Rules defining how the business distributes those values.

### C. Distribution Results
Calculated results showing how much each employee:
- generated;
- gave out;
- received;
- must finally be paid.

Original POS facts are never modified by the calculation engine.

---

## 3. Primary Calculation Unit

The primary business calculation unit is the **Order**, not the individual Payment.

For each Order:

**Gross Earned Tips = sum of all Payment.tipAmount values + automatic gratuity/service charge on the Order**

The Order gratuity is counted **once only**, regardless of the number of Payments.

Split payment with 2, 5, or 10 cards does not change the economic meaning of the Order.

---

## 4. Original Tip Owner

The employee who originally owns the tip is:

**Order.employee**

`Payment.employee` is preserved for audit and anomaly detection, but does not determine tip ownership.

---

## 5. Settlement Time

Each Order has a:

**Settlement Time**

defined as:

**timestamp of the last successful Payment that completes payment of the Order**

Settlement Time determines:
- which rule version applies;
- which employees were clocked-in;
- which operational/distribution period the Order belongs to.

The later moment when someone enters or adjusts a tip in the POS is not used for eligibility.

---

## 6. Money Included

RF-One distributes only amounts observable in the system.

Included:
- electronic voluntary tip;
- automatic gratuity / service charge;
- future POS-recorded tip forms.

Excluded:
- unrecorded cash tips.

Therefore:

> What RF-One can see, RF-One can distribute.

A gratuity recorded on the Order is included even if the customer pays the check in cash.

---

## 7. Tip Distribution Rule

Each rule contains at least:

### Source Role
Example:
- `SERVER`

### Recipient Role
Examples:
- `HOST`
- `BARTENDER`
- `BUSSER`
- `RUNNER`

Host, bartender, busser, runner, etc. use the same rule engine. They are not separate calculation engines.

---

## 8. Calculation Base

Configurable for each rule.

Initial supported bases:

- `VOLUNTARY_TIP`
- `GRATUITY`
- `TIP_PLUS_GRATUITY`
- `TOTAL_SALES`
- `FOOD_SALES`
- `BEVERAGE_SALES`

The engine must remain extensible so additional calculation bases can be added without redesigning the core rule structure.

---

## 9. Rate

Each rule has a configurable rate.

Examples:

- Host → 10% of Tip + Gratuity
- Bartender → 1% of Sales
- Bartender → 5% of Beverage Sales
- Busser → 2% of Food Sales

The Rome’s Flavours 10% rate is configuration, never hardcoded engine behavior.

---

## 10. Independent Rules

Rules are always calculated on their own original base.

Rules are **not sequential** and never calculated on the remainder left after another tip-out.

Example:

Gross Earned Tips = $100

Host rule:
10% of Tips = $10

Bartender rule:
5% of Tips = $5

Result:

**Outbound Tip-Out = $15**

**Net Server Tips = $85**

---

## 11. Transaction Scope

Each rule can define which transactions it applies to.

Configurable scope may include:
- Dine In
- Takeout
- Delivery
- Catering
- Events
- specific Order Types
- specific Channels
- future inclusions/exclusions

A location may configure a rule as applying to all transactions.

---

## 12. Recipient Eligibility

A rule defines how eligible recipients are identified.

Initial eligibility modes:

### ACTIVE_AT_SETTLEMENT
Employees with the configured recipient role who are clocked-in at the Order Settlement Time.

### PERIOD_HOURS
Employees with the configured recipient role who worked during the Distribution Period.

Additional modes may be added later without changing the core engine.

The source of truth for clock-in / clock-out is the POS/time-clock system. For Rome’s Flavours this is Clover.

---

## 13. Distribution Method

Configurable independently from the rule rate.

### EQUAL
The pool is divided equally among all eligible recipients.

### HOURS_PROPORTIONAL
The pool is divided in proportion to hours worked.

### WEIGHTED_HOURS
The pool is divided according to:

**hours × configured weight**

Example:

Host A = 5 hours × 1.0  
Host B = 5 hours × 1.25

---

## 14. No Eligible Recipient

Behavior is configurable.

Initial supported policy:

### SOURCE_RETAINS

If no eligible recipient exists, the original source employee keeps the amount.

Rome’s Flavours uses this behavior for Hosts.

---

## 15. Distribution Period

The Distribution Period is separate from transaction-level eligibility.

Configurable modes may include:
- Shift / End of Night
- Daily
- Weekly
- Biweekly
- Custom period

Eligibility can still depend on the specific Settlement Time of each Order even when totals are aggregated weekly or biweekly.

---

## 16. Rule Versioning

Rules are versioned and effective-dated.

Each rule version contains at least:
- `effective_from`
- optional `effective_to`
- complete rule configuration
- created by
- created timestamp

The applicable rule version is determined by the **Order Settlement Time**.

Future rule changes must never silently alter historical calculations.

---

## 17. Rounding

All monetary calculations use **integer cents**.

Floating-point arithmetic must not be used for monetary distribution.

Example:

$10.00 divided among 3 recipients:

- $3.33
- $3.33
- $3.34

Any residual cent is assigned using a deterministic and repeatable rule.

The sum of distributed shares must always reconcile exactly to the original pool.

---

## 18. Refunds

A Refund is a separate POS fact.

**A refund does not automatically cancel or reverse an already assigned tip.**

RF-One records the refund, but it does not change the Tip Distribution Result unless:
- a future explicit business rule requires it; or
- an authorized human adjustment is created.

---

## 19. Manual Adjustments

A manual correction never modifies original POS Source Facts.

Each adjustment contains:
- Employee
- positive or negative Amount
- mandatory Reason
- Created by
- Timestamp
- optional Order / Payment reference
- optional Note

Examples:
- missing tip correction
- allocation correction
- authorized compensation adjustment

---

## 20. Approval and Lock

A Distribution Period follows at least:

**OPEN → CALCULATED → REVIEWED → APPROVED / LOCKED**

Once `LOCKED`:
- no silent recalculation is allowed;
- historical results are not changed automatically.

A later correction requires either:
- an adjustment in a later period; or
- an explicit reopening with reason and audit trail.

---

## 21. Explainability

Every distributed dollar must be reconstructable.

For each employee RF-One must show:

**Gross Earned Tips**  
− **Outbound Tip-Outs**  
+ **Inbound Tip-Outs**  
± **Adjustments**  
= **Final Payable**

Every Tip-Out must be traceable through:

**Order → Rule → Calculation Base → Rate → Recipient(s) → Allocation**

---

# Rome’s Flavours — Initial Configuration

### Source Role
`SERVER`

### Recipient Role
`HOST`

### Calculation Base
`TIP_PLUS_GRATUITY`

### Rate
`10%`

### Original Tip Owner
`Order.employee`

### Settlement Time
Timestamp of the last successful Payment that completes the Order.

### Eligibility
Host clocked-in at Settlement Time.

### Distribution Method
`EQUAL`

### No Eligible Host
`SOURCE_RETAINS`

### Cash Tips
Unrecorded cash tips are excluded.

### Automatic Gratuity
Included.

### Tip on Top of Gratuity
Included. Both voluntary tip and automatic gratuity form the Gross Tip Base.

### Split Payments
Economically irrelevant to distribution logic. All payment tips are consolidated at Order level and the Order gratuity is counted once.

### Distribution Period
Configurable.

### Refund
No automatic tip reversal.

### Manual Adjustments
Allowed with mandatory reason and audit history.

### Rule Versioning
Effective-dated and determined by Order Settlement Time.

---

## Implementation Boundary

This document defines the functional behavior of the Tip Distribution Engine.

It does not define:
- Clover ingestion internals beyond the Source Facts consumed by the engine;
- payroll payment execution;
- Zelle or ACH payment integration;
- ADP integration;
- broader RF-One employee/personnel architecture.

Those remain separate implementation/integration concerns.
