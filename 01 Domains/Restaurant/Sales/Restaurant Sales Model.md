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
- source_order_id
- source_employee_id
- order_type_id
- opened_at
- created_at
- modified_at
- payment_state
- subtotal
- discount_total
- tax_total
- total
- note
- source metadata
```

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

# 7. Order Item — atomic sales fact

`ORDER_ITEM` is the atomic sales event.

Principle:

```text
ORDER_ITEM = one individual sold unit
```

Relationship:

```text
ORDER
└── 1:N ORDER_ITEM
```

If three identical Items are sold, RF-One preserves three atomic sold-unit records rather than collapsing them into one canonical row.

Example:

```text
OrderItem A → Item X
OrderItem B → Item X
OrderItem C → Item X
```

Each Order Item preserves the historical reality of that sale, including values that may later differ from the current Item definition.

Typical facts may include:

```text
ORDER_ITEM
- order_item_id
- order_id
- item_id
- guest_number
- historical unit price
- source timestamps
- source metadata
```

Discounts and Modifiers are related facts and should not be destructively flattened into the Item definition.

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
              │
              ├── 1:N ORDER_ITEM
              │       │
              │       ├── N:1 ITEM
              │       ├── guest_number
              │       ├── 0:N ORDER_ITEM_MODIFIER → MODIFIER
              │       └── 0:N ORDER_ITEM_DISCOUNT
              │
              ├── 1:N PAYMENT
              │       └── TIP
              │
              ├── 0:N ORDER_DISCOUNT
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
Order Items
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
Order Item = aggregated quantity
Item = menu item
Modifier = always a product customization
Order employee = person who sold every Order Item
Payment employee = person who served the Table Service
missing source value = zero
declared guest count = derived guest count
Service Charge = Tip
Payment owns Tax
POS structure = Restaurant ontology
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
