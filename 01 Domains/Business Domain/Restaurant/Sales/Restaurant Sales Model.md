# RF-One Restaurant — Sales Model

## Status

Canonical Restaurant-domain model for restaurant sales and service data.

This document defines **restaurant reality**, not Clover's implementation, not an Excel export, and not a physical database schema.

The model must remain valid if RF-One later integrates a different POS.

---

# 1. Modeling principle

RF-One should preserve operational facts as atomically as practical and derive metrics later.

```text
Restaurant reality
→ atomic operational facts
→ relationships
→ derived measures
→ KPIs / Performance Evidence / decisions
```

Do not structure the canonical model around:
- a POS export;
- an Excel workbook;
- a KPI dashboard;
- a vendor-specific database layout.

Vendor-specific mappings belong in the relevant Runtime/Software integration.

---

# 2. Fundamental service entity: Table Service

The fundamental restaurant-service entity is:

```text
TABLE_SERVICE
```

A Table Service represents:

> one real service occasion involving a group of guests.

It is not the physical table and it is not the POS Order.

Each Table Service requires a stable RF-One identifier:

```text
table_service_id
```

A Table Service provides the common operational context from which Orders, people, physical tables, and later analytics can be related.

---

# 3. Physical Table

A Physical Table is a persistent restaurant resource.

Typical attributes may include:

```text
PHYSICAL_TABLE
- physical_table_id
- table_number
- seat_capacity
- area
- indoor_outdoor
- section/location
- active_status
- other physical/preference attributes
```

`PHYSICAL_TABLE` and `TABLE_SERVICE` are distinct.

Relationship:

```text
TABLE_SERVICE ↔ PHYSICAL_TABLE
```

Cardinality:

```text
M:N
```

This permits:
- one Table Service at one physical table;
- one Table Service using several joined physical tables;
- reassignment/movement if operationally required;
- a service with no physical table, such as To Go.

No mandatory `primary_table` is assumed.

---

# 4. Table Service and Employees

A Table Service may involve one or many Employees.

Relationship:

```text
TABLE_SERVICE ↔ EMPLOYEE
```

Cardinality:

```text
M:N
```

A relationship table may later implement this physically:

```text
TABLE_SERVICE_EMPLOYEE
```

If one Employee participates, there is one relationship.
If several participate, there are several relationships.

Do not introduce a mandatory `primary_server` unless future operational reality requires it.

Source systems may separately identify:
- the Employee associated with an Order;
- the Employee associated with a Payment;
- the Employee associated with another atomic fact.

Those source observations should remain distinct from the broader participation relationship.

---

# 5. Table Service and Orders

A Table Service may contain one or more Orders.

```text
TABLE_SERVICE
└── 1:N ORDER
```

Do not assume:

```text
1 Table Service = 1 Order
```

Multiple Orders may represent the same real service because of:
- large parties;
- split-check behavior;
- POS constraints;
- fictitious tables;
- To Go workflows;
- operational workarounds.

The Order is therefore a commercial/POS grouping inside the broader Table Service.

---

# 6. Order

An Order represents a commercial grouping of sold units and settlements.

Canonical Order facts may include:

```text
ORDER
- order_id
- table_service_id
- location_id
- source_order_id
- source_employee_id
- order_type_id
- opened_at
- created_at
- modified_at
- payment_state
- business_date
- subtotal
- discount_total
- tax_total
- total
- note
- source metadata
```

Every Order is attributable to the Restaurant Location at which it occurred (`Organization/Restaurant Profile.md`, "Restaurant ↔ Location"). This is what allows the same canonical Sales model to support a Restaurant operating from one Location today and several over time, without embedding any single Location's assumptions into the Order.

Exact physical fields are deferred to database design.

Conceptual ownership:

```text
Order
├── sold units
├── order-level discounts
├── tax
├── mandatory order fees
└── payments that settle the order
```

A Payment settles value already created by the Order.

---

# 6a. Business Date

RF-One distinguishes between:

- an event's actual **timestamp** — when something literally happened, in real clock time;
- the restaurant's **Business Date** (operating day) — the operational day that event is attributed to.

A restaurant operating past midnight may record events whose calendar timestamp falls on the next calendar day but that still belong, operationally, to the previous business day.

```text
Location operating day: August 30
Order opens:             August 30, 23:45
Payment occurs:          August 31, 00:30
Business Date:           August 30
```

Timestamps are never replaced by Business Date; both remain preserved, independently.

## Location owns the Business Day Rule

The configuration needed to determine a Business Date belongs to `LOCATION`, not to Restaurant globally, because different Locations may operate on different schedules and cutoff rules:

```text
LOCATION
- ...existing Location facts (name, timezone, currency, active)...
- operating_day_cutoff_time
```

`operating_day_cutoff_time` — a time-of-day, evaluated in the Location's own `timezone` — is the smallest adequate Business Day Rule: an event timestamped before this cutoff on a given calendar day is attributed to that calendar day; an event timestamped at or after this cutoff is attributed to the previous calendar day, until the next occurrence of the cutoff. This is deliberately minimal — RF-One does not build a general restaurant-scheduling/calendar engine here.

`timezone` comes from Location; the cutoff is meaningless without it, since "midnight" is only defined relative to a timezone. See `Organization/Restaurant Profile.md`, "Location Business Day Rule (Business Date)," for where this configuration is owned at the Organization level.

## Order carries its own Business Date

`ORDER.business_date` (§ 6) is the canonical, minimum-required Business Date fact in this model. It is:

- computed once, from the Order's own timestamp and the Location's Business Day Rule in effect at that time;
- persisted on the Order itself, not recomputed on every read;
- independent of, and never a replacement for, the Order's actual timestamps.

## Historical immutability

A Location's `operating_day_cutoff_time` may change over time. This must never retroactively change the Business Date already attributed to a historical Order:

```text
Order from August, business_date = August 30
     │
     │  (Location cutoff changes in September)
     │
     └── Order.business_date remains August 30
```

RF-One achieves this by persisting `business_date` on the Order at the time it is first determined, rather than deriving it at read time from the Order's timestamp and the Location's *current* configuration. If the Location's own Business Day Rule needs to be versioned/audited over time, that is a Location-configuration concern, not a Sales concern — Sales only requires the Order's own persisted `business_date` to remain stable.

## Table Service

Table Service does not persist an independent Business Date. Where one is needed at the Table Service level, it may be derived from its Order(s)' `business_date` (ordinarily consistent within one continuous service); Order remains the canonical, persisted source.

## Cross-domain use

`business_date`, as defined here, is the single canonical concept `Tips`, `Payroll`, and `Performance` should reuse for "which operating day does this belong to," rather than each Domain independently inventing its own business-date rule. Those Domains are not modified by this task beyond this cross-reference; they may adopt `business_date` where operationally appropriate. Purchasing may use it later if operationally appropriate, but Purchasing is not expanded by this document.

## Provider independence

Business Date is a provider-independent RF-One concept. A source system may separately supply its own business-date-like value; where it does, RF-One preserves it as source evidence, but RF-One's own `business_date` (computed from the Location's Business Day Rule) remains canonical.

## Non-assumptions

Do not assume:

```text
business_date = the calendar date of Order.opened_at
timestamp = business_date
Location.operating_day_cutoff_time changing rewrites historical Order.business_date
every Domain computes its own independent business date
```

---

# 7. Order Item — atomic sales fact

`ORDER_ITEM` is the atomic sales event.

Principle:

```text
ORDER_ITEM = one recorded sold line / sold item occurrence,
             with its own observed quantity and historical economic attributes
```

Relationship:

```text
ORDER
└── 1:N ORDER_ITEM
```

Whether several identical Items sold together are recorded as several separate Order Item facts or as one Order Item fact with a `quantity` greater than one depends on how the source/business event actually occurred. RF-One preserves whichever shape reality presents and never collapses or expands one shape into the other.

Each Order Item preserves the historical reality of that sale, including values that may later differ from the current Item definition.

Typical facts may include:

```text
ORDER_ITEM
- order_item_id
- order_id
- item_id
- quantity
- guest_number
- historical unit price
- source timestamps
- source metadata
```

Discounts and Modifiers are related facts and should not be destructively flattened into the Item definition.

## Quantity

`ORDER_ITEM.quantity` is an explicit, provider-independent fact. It:

- supports decimal values (e.g. `0.5`, `1.5`), not only whole units — real restaurant reality includes fractional/portion-based sales, not only whole-unit lines;
- preserves the quantity actually observed/reported by the source when available;
- is never a provider-specific (e.g. Clover-specific) encoding;
- is never inferred from the number of Order Item rows;
- is never silently defaulted to a provider convention — if the source does not state a quantity, RF-One preserves that as missing/unknown, not as an assumed `1`;
- remains independent from historical unit price — `quantity` and unit price are two separate atomic facts, never combined into one figure.

The Sales module does not require duplicating Order Item rows merely to represent quantity. One Order Item fact may carry `quantity = 1`, `quantity = 3`, `quantity = 0.5`, or any other valid observed decimal quantity, depending on actual restaurant reality.

## Quantity is not aggregation

Amending the quantity rule does not change what Order Item's atomicity means. The atomic fact remains a single recorded sold-line **event** — atomicity concerns historical event identity, not forcing `quantity = 1`.

Do not aggregate unrelated Order Item facts merely because they share the same Item. Two separately recorded sold-line events remain two Order Item facts even when they share the same Item, price, Order, and quantity:

```text
OrderItem A → Water, quantity = 1
OrderItem B → Water, quantity = 1
```

remains two Order Item facts, never automatically merged into one `quantity = 2` fact. Merging identical-looking facts is a downstream aggregation/derivation choice, never a rewrite of the atomic Sales facts themselves.

## Derived line amounts

Where an Order Item's total economic amount can be deterministically derived from `quantity × historical unit price`, adjusted by Modifier price impact (§ 19) and Order Item Discounts (§ 18), RF-One derives it rather than persisting a redundant stored total — consistent with § 22, "Observed facts vs derived metrics." If reconciliation/evidence requires preserving a source-reported line total separately (e.g. the source's own total disagrees with the deterministic derivation), that source total is preserved as its own atomic fact, never silently discarded or forced to match the derivation.

---

# 8. Item

`ITEM` is the stable definition of something sellable.

It does **not** mean "current menu item."

```text
ITEM = anything the restaurant can sell
```

Examples:
- food;
- cocktail;
- wine;
- beverage;
- branded glass;
- oil bottle;
- merchandise;
- a fee represented by a POS as a sellable Item;
- a technical/instrumental Item created because of POS limitations.

An Item may:
- be displayed on the current menu;
- be a special;
- be temporarily unavailable;
- not be customer-facing at all.

Menu exposure is a separate concept.

Recipe is also a separate concept and is outside the scope of this sales-data model.

Relationship:

```text
ORDER_ITEM → ITEM
```

`ITEM` defines what the sellable thing is.

`ORDER_ITEM` records one historical sale of it.

`ITEM` as used here is the same canonical entity defined by `Commercial Catalog/Item.md`, not a parallel Sales-owned definition. Sales consumes the Commercial Catalog's Item identity; it does not redefine it. The same applies to `MODIFIER` and `MODIFIER_GROUP` (§ 19–20 below), which are the Commercial Catalog's canonical `Modifier.md`/`ModifierGroup.md` entities as observed in a specific sale.

---

# 9. Historical sale values

Historical Order Item facts must not be overwritten by later changes to the Item definition.

Example:

```text
Item X standard price today = 24.00
```

does not change:

```text
OrderItem sold three months ago = 20.00
```

The historical sale remains the historical truth.

---

# 10. Guest Number — atomic item assignment

Guest assignment belongs to the atomic Order Item when the source system provides it.

```text
ORDER_ITEM.guest_number
```

This represents the guest/seat position to which that sold unit was assigned.

Example:

```text
OrderItem A → Guest 1
OrderItem B → Guest 1
OrderItem C → Guest 2
OrderItem D → Guest 4
```

The Guest Number is a more atomic observation than an aggregate guest count.

RF-One should preserve missing guest assignment as missing rather than silently inventing a guest number.

---

# 11. Declared and Derived Guest Count

RF-One should preserve both:

```text
declared_guest_count
derived_guest_count
```

because they represent different evidence.

## Declared Guest Count

```text
declared_guest_count
```

means:

> the number of guests explicitly declared by the source/POS/operator for the service.

A future POS may expose this as a native field.

A current POS may represent it through another mechanism.

The canonical model must not depend on the vendor-specific mechanism.

Recommended provenance:

```text
declared_guest_count_source
```

Possible source meanings may later include:

```text
NATIVE_POS_FIELD
TECHNICAL_ITEM
MANUAL
OTHER
UNKNOWN
```

These are illustrative, not yet final database enums.

## Derived Guest Count

```text
derived_guest_count
```

means:

> the guest count reconstructed from atomic guest assignment evidence.

Where guest numbering is ordinal:

```text
derived_guest_count = MAX(OrderItem.guest_number)
```

within the appropriate service/order grouping.

This is a derived value, but retaining it materially improves validation, querying, and process-quality analysis.

---

# 12. Guest-count reconciliation

Keeping both values allows RF-One to detect data-quality/process issues.

Examples:

```text
declared = 4
derived  = 4
→ coherent
```

```text
declared = 2
derived  = 5
→ mismatch
```

```text
declared = 5
derived  = 3
→ guest assignment may be incomplete
```

```text
declared = missing
derived  = 4
→ missing declaration
```

RF-One should retain the original evidence and the discrepancy rather than silently correcting one value from the other.

This intentional redundancy is useful for reducing malpractice and improving order-entry discipline.

---

# 13. Payment

An Order may have multiple Payments.

```text
ORDER
└── 1:N PAYMENT
```

This is essential restaurant reality.

Examples include:
- cash;
- one card;
- multiple cards;
- mixed cash/card;
- arbitrary split checks;
- one guest paying specific portions;
- several people dividing the remaining balance.

Payment is therefore an independent atomic settlement entity.

Typical facts may include:

```text
PAYMENT
- payment_id
- order_id
- source_payment_id
- source_employee_id
- paid_at
- amount
- tender_id
- result
- source metadata
```

Do not collapse multiple Payments into one canonical payment row.

---

# 14. Tip

Tip belongs conceptually to Payment.

```text
PAYMENT
└── TIP
```

A Tip represents an amount voluntarily controlled by the customer as part of a Payment.

A Table Service may therefore contain multiple Tips.

Higher-level Tip values are derived:

```text
Order Tip
= SUM(Payment Tips for the Order)
```

```text
Table Service Tip
= SUM(Payment Tips across all Orders in the Table Service)
```

Do not treat a higher-level summed Tip as though it were one atomic observed fact.

---

# 14a. Refund

A completed Order or Payment may later be economically reversed, in whole or in part. This is restaurant reality independent of any POS: a guest disputes a charge the next day, a kitchen error is corrected after the check has closed, a manager comps a completed sale after the fact.

```text
REFUND
- refund_id
- order_id (nullable)
- payment_id (nullable)
- source_refund_id
- source_employee_id
- refunded_at
- amount
- tax_amount
- tip_amount
- status
- source metadata
```

A Refund is an **independent atomic fact**, not a correction applied retroactively to the Order or Payment it reverses:

```text
Order / Payment
     │
     │  (unchanged — the original sale remains historical truth)
     │
     └── 0:N REFUND
```

Principles:

- The original Order and Payment are never rewritten, deleted, or silently zeroed to make a refunded sale "look like it never happened." The Order/Payment facts and the Refund fact both remain true and both remain visible.
- A Refund may reference its originating Order and/or Payment, but the reference may be only partially resolvable (e.g. a Refund known by amount and timestamp without a confidently resolved Payment). RF-One preserves the Refund fact even when it cannot be fully linked, rather than discarding it.
- A Refund may occur on a later business date than the Order/Payment it reverses. Nothing in this model assumes a Refund shares the Order's business date.
- A Payment may have more than one Refund (e.g. successive partial refunds); a Refund is never assumed to be full unless the evidence states so.
- A Refund's existence must not be inferred from an Order's or Payment's own status fields — a source system's `payment_state`/`result` may remain unchanged even when a genuine Refund exists elsewhere. Where a source separates Refund from Order/Payment status this way, RF-One preserves the Refund as the authoritative fact, not the unchanged status field.
- Whether a Refund also reverses the associated Tip is a fact to be evidenced, never assumed either way — see `Tips/Tip.md`, "Refunds and corrections."
- A `voided` or similarly named flag on a Refund is source evidence about that Refund's own lifecycle (e.g. a Refund itself later reversed), not a general-purpose Order/Item void mechanism. Order/Item void and cancellation *before* settlement (as distinct from a Refund *after* settlement) is a separate concept — see § 14b, Void / Cancellation.

---

# 14b. Void / Cancellation

A commercial Sales event, or part of it, may be abandoned or cancelled **before** final economic settlement. This is restaurant reality independent of any POS: an item entered then removed before the check closes, an Order abandoned before payment, a payment attempt voided before it settles.

```text
VOID / CANCELLATION   (before settlement)
        ≠
REFUND                 (after settlement, § 14a)
```

Void/Cancellation and Refund are never merged into one concept. The distinguishing fact is whether a completed economic settlement had already occurred:

- **before** settlement → Void / Cancellation;
- **after** a completed settlement → Refund.

## Order Item Void

```text
ORDER_ITEM_VOID
- order_item_void_id
- order_item_id
- voided_at
- source_employee_id
- reason
- source metadata
```

Records that a specific Order Item was voided/cancelled before settlement. The original `ORDER_ITEM` fact is never deleted or silently removed merely because it was voided. Where both the original recorded sale-line and later Void evidence are observable, RF-One preserves both:

```text
ORDER_ITEM (original recorded event)
     │
     └── 0:N ORDER_ITEM_VOID   (later/same-lifecycle Void evidence)
```

## Order Cancellation

```text
ORDER_CANCELLATION
- order_cancellation_id
- order_id
- cancelled_at
- source_employee_id
- reason
- source metadata
```

Records that an entire Order was cancelled/abandoned before completion. As with Order Item Void, the original `ORDER` and its `ORDER_ITEM` facts are preserved, never deleted:

```text
ORDER (original recorded event)
     │
     └── 0:1 ORDER_CANCELLATION
```

## Order versus Order Item

Order cancellation and Order Item void are kept as two distinct facts because they represent different operational reality — an entire Order abandoned is not the same event as one line removed from an otherwise-completed Order. RF-One does not force them into a shared generic state.

## Payment Void boundary

This model does not introduce a separate Payment Void entity at this stage. A payment authorization/attempt voided before it settles is, for canonical Sales purposes, evidence relevant to the *Order's* or *Order Item's* Void/Cancellation state (or, where a source models Payment lifecycle status independently, a `Payment.result` value — § 13) rather than a fourth parallel void concept. A failed payment, a cancelled Order, an Order Item void, a payment void, and a Refund are not treated as equivalent to one another. If a genuinely distinct Payment Void economic concept is later evidenced as necessary, it should be added as its own smallest addition at that time, not invented speculatively now.

## Source evidence limitation

A POS may fail to expose Void/Cancellation evidence at all, or may expose it incompletely — this is a Provider/Data Acquisition Gap (see `07 Tasks/Reports/TASK_SALES_001_REPORT.md` § I), not a reason to remove the Void/Cancellation concept from this Domain. Missing Void evidence must remain Unknown/unavailable — RF-One never infers that an Order Item was voided merely because it is absent from a final POS export; absence-from-export and confirmed-void are different facts (see § 23, "Data quality as operational evidence").

---

# 15. Tax

Tax belongs conceptually to the Order.

```text
ORDER
└── TAX
```

The Order determines the amount due before settlement.

Payment pays that amount; Payment does not create the tax.

If a source also exposes tax detail at sold-unit level, RF-One may preserve that evidence for reconciliation and analysis.

---

# 16. Fees

A mandatory fee applies conceptually to the Order.

General model:

```text
ORDER
└── 0:N ORDER_FEE
```

Examples may include:
- Service Charge;
- Cork Fee;
- other mandatory charges.

Not all POS systems represent fees consistently.

A source may expose a native fee mechanism or may model a fee as a sellable Item.

RF-One should preserve source reality while mapping the business meaning only when supported.

---

# 17. Service Charge and Tip are distinct

```text
SERVICE CHARGE ≠ TIP
```

Service Charge:
- is an Order-level mandatory fee;
- is not under the same customer discretion as Tip.

Tip:
- belongs to Payment;
- is customer-controlled.

They may later be combined for a particular payroll/business calculation, but they remain distinct operational facts.

---

# 18. Discounts

Discounts may occur at two distinct levels.

```text
ORDER
└── 0:N ORDER_DISCOUNT
```

and:

```text
ORDER_ITEM
└── 0:N ORDER_ITEM_DISCOUNT
```

Do not collapse the two.

If a reporting system later apportions an Order-level discount across Order Items, that allocation is a derived transformation, not the original discount fact.

A discount is observed in at least two independent shapes, and RF-One preserves whichever shape the source actually reports rather than converting one into the other:

```text
percentage  — e.g. 20% off
fixed amount — e.g. $20 off
```

Where a source reports a percentage, RF-One preserves that percentage as evidence and separately preserves (or computes and stores) the resulting monetary amount, so the discount's true economic impact is always determinable without re-deriving it from the percentage at read time. Where a source reports only a fixed amount, RF-One never back-infers a percentage that was not actually stated. Neither shape is treated as the canonical one; both `percentage` and `amount` are independently optional facts on `ORDER_DISCOUNT`/`ORDER_ITEM_DISCOUNT`, and a discount fact may carry either or both depending on what the source actually provided.

---

# 19. Modifier

An Order Item may have zero or arbitrarily many Modifiers.

```text
ORDER_ITEM
└── 0:N ORDER_ITEM_MODIFIER
          └── MODIFIER
```

Modifier represents a POS-defined variant/option associated with an Item.

Some Modifiers may affect price.

Examples:

```text
Extra mozzarella
No onion
Premium gin
```

However a POS may also use the same mechanism for operational instructions such as:

```text
First
Second
Third
Wait for server
```

Therefore the source Modifier mechanism does not necessarily reveal the true semantic nature of the value.

RF-One must preserve the source fact without automatically assuming the Modifier is a product customization.

`ORDER_ITEM_MODIFIER` — the record of one Modifier selected on one Order Item — preserves the historical price impact of that selection (e.g. "+$3") as its own atomic fact, distinct from the Modifier's current catalog definition, for the same reason `ORDER_ITEM` preserves its own historical unit price (§ 9): a later catalog price change for that Modifier must not rewrite what a past sale actually charged. Reconstructing an Order Item's true total economic amount (base price plus every selected Modifier's historical price impact) is therefore always possible from atomic facts, without re-deriving it from the current catalog.

---

# 20. Modifier Group

Modifier Group is a source/catalog grouping that may need to be preserved.

```text
MODIFIER_GROUP
└── 1:N MODIFIER
```

Important relationships remain:

```text
ITEM ↔ MODIFIER
```

for Modifiers associated/available to an Item,

and:

```text
ORDER_ITEM ↔ MODIFIER
```

for Modifiers actually selected in a specific sale.

Modifier Group should not be given more semantic authority than the source provides.

---

# 21. Current relationship model

```text
PHYSICAL_TABLE
      ↕ M:N
TABLE_SERVICE
      ↕ M:N
   EMPLOYEE

TABLE_SERVICE
      │
      └── 1:N ORDER
              │       business_date
              ├── 1:N ORDER_ITEM
              │       │       quantity
              │       ├── N:1 ITEM
              │       ├── guest_number
              │       ├── 0:N ORDER_ITEM_MODIFIER → MODIFIER
              │       ├── 0:N ORDER_ITEM_DISCOUNT
              │       └── 0:N ORDER_ITEM_VOID
              │
              ├── 1:N PAYMENT
              │       └── TIP
              │
              ├── 0:N ORDER_DISCOUNT
              ├── 0:N REFUND
              ├── 0:1 ORDER_CANCELLATION
              ├── TAX
              └── 0:N ORDER_FEE
```

Supporting relationships:

```text
ITEM ↔ MODIFIER
MODIFIER_GROUP → MODIFIER
```

Guest-count evidence:

```text
TABLE_SERVICE / relevant grouping
├── declared_guest_count
├── declared_guest_count_source
└── derived_guest_count

ORDER_ITEM
└── guest_number
```

The exact placement of aggregate guest-count fields in the physical schema will be decided during implementation, while preserving the semantic distinction above.

---

# 22. Observed facts vs derived metrics

The canonical fact model should not be polluted with KPI columns.

Examples of source/atomic facts:

```text
Order timestamps
Order business_date
Order Items
Order Item quantity
Item identity
Guest Number
Payments
Tips
Employees
Physical Tables
Discounts
Taxes
Fees
Modifiers
Refunds
Order/Order Item Void and Cancellation
```

Examples of derived measures:

```text
service duration
declared/derived guest mismatch
gross / guest
items / guest
guests / hour
orders / hour
items / hour
gross / hour
tip / gross
tip / order
tip / hour
table turnover
product mix
item concentration
demand by time band
```

These belong to analytics and Performance layers.

Any derived measure that counts sold units (e.g. "items / guest," "items / hour," unit-count product mix) must be understood as `SUM(quantity)` across the relevant Order Items where economically appropriate, not `COUNT(Order Item rows)` — a row no longer necessarily represents exactly one unit (§ 7, "Quantity"). This corrects how a unit-count-based derivation must be computed; it does not change which measures are derived versus persisted.

---

# 23. Data quality as operational evidence

Missing or inconsistent data may represent:
- source limitations;
- workflow design;
- employee/process discipline;
- malformed input;
- incomplete execution.

RF-One should not silently treat all missing values as technical limitations.

Where appropriate it should preserve enough evidence to distinguish:

```text
source cannot provide the value
```

from:

```text
the workflow should have produced the value but did not
```

This can support process-compliance and data-quality indicators without automatically converting them into employee judgments.

---

# 24. Provenance

Canonical records should preserve sufficient provenance to answer:

```text
Where did this fact come from?
When was it observed?
Was it directly observed or derived?
Did another representation agree with it?
```

Exact physical provenance columns remain a database-design decision.

---

# 25. Important non-assumptions

Do not assume:

```text
1 Table Service = 1 Physical Table
1 Table Service = 1 Employee
1 Table Service = 1 Order
1 Order = 1 Payment
Order Item quantity = number of Order Item rows
Order Item quantity = always 1
Order Item quantity default = 1 when source is silent
identical Order Item facts = automatically the same event (merge on match)
Item = menu item
Modifier = always a product customization
Order employee = person who sold every Order Item
Payment employee = person who served the Table Service
missing source value = zero
declared guest count = derived guest count
Service Charge = Tip
Payment owns Tax
POS structure = Restaurant ontology
Refund status = visible in Order/Payment status fields
Refund = full reversal unless evidenced
Refund business date = Order business date
Void = Refund
Order Item absent from a POS export = automatically voided
business_date = the calendar date of Order.opened_at
timestamp = business_date
Location.operating_day_cutoff_time changing rewrites historical Order.business_date
```

---

# 26. Scope boundary

This document defines the Restaurant sales/service conceptual model.

It does not define:
- Clover field names;
- Clover API paths;
- Clover workarounds;
- physical SQL schema;
- database indexes;
- KPI formulas;
- payroll logic;
- Training logic;
- Performance scoring.

Those belong to other layers/documents.
