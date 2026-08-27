# RF-One — Clover Restaurant Data Mapping

## Status

Runtime/Software mapping between the current Clover production data and the RF-One Restaurant sales model.

This document is vendor-specific.

Canonical restaurant semantics belong in:

```text
01 Domains/Restaurant/Sales/Restaurant Sales Model.md
```

This mapping records what Clover actually exposes, how RF-One can reconstruct canonical facts, and where Clover's representation is incomplete or semantically inconsistent.

---

# 1. Evidence basis

This mapping is grounded in empirical inspection of the current production merchant data.

Primary sources inspected:

```text
data/raw/2026-08-24T231114Z/orders.json
```

containing:

```text
3,521 Orders
```

and the dedicated line-item responses cached during TASK_CLOVER_002:

```text
data/generated_exports/_api_cache/supplementary/lineitems_*.json
```

covering:

```text
271 Orders
1,838 dedicated Line Items
```

The earlier reconciliation also validated the reconstructed Clover dashboard exports against the Product Owner's real Payments, Orders, Line Items, and Clock CSV exports.

This document must distinguish:
- confirmed source facts;
- derived mappings;
- unresolved semantics.

---

# 2. Mapping principle

Clover is a source system, not the RF-One ontology.

```text
Clover raw data
→ preserve
→ interpret/reconcile
→ RF-One canonical fact
```

Do not move a concept into the canonical model merely because Clover places a field in a particular object.

Known example:

```text
Clover may surface Tip through Order-oriented output
```

while RF-One conceptually treats Tip as Payment-level.

---

# 3. Order

Canonical:

```text
RF-One ORDER
```

Primary Clover source:

```text
Clover Order
```

Observed top-level Order fields in the real export include:

```text
clientCreatedTime
createdTime
currency
customers
device
discounts
employee
groupLineItems
href
id
isVat
lineItems
manualTransaction
modifiedTime
note
orderType
payType
paymentState
payments
state
taxRemoved
testMode
title
total
```

Clover Order remains the primary source grouping for:
- Order identity;
- Order timestamps;
- Order employee reference;
- Order type;
- Order state/payment state;
- nested/related Line Items;
- nested/related Payments;
- discounts;
- total.

---

# 4. Guest Count — no native Order field found

## Finding

**No dedicated native guest-count field was found in the current Clover Order API payloads.**

All observed top-level fields across 3,521 Orders were inspected.

No field represented:
- guest count;
- party size;
- covers;
- equivalent explicit headcount.

The `customers` field is not guest count. It references Clover Customer/loyalty records.

---

# 5. Declared Guest Count — current Clover workaround

The current merchant uses a synthetic/technical Item:

```text
# Guest
```

Structural form observed:

```json
{
  "id": "<redacted>",
  "item": {"id": "<redacted>"},
  "name": "# Guest",
  "price": 0,
  "unitQty": 2000,
  "unitName": "Nbr",
  "isRevenue": false,
  "isOrderFee": false,
  "printed": true
}
```

Mapping:

```text
RF-One declared_guest_count
← Clover "# Guest".unitQty / 1000
```

Example:

```text
unitQty = 2000
→ declared_guest_count = 2
```

Coverage in the 3,521-Order raw export:

```text
3,107 / 3,521 Orders contain at least one "# Guest" Line Item
= 88.2%
```

**Correction (TASK_CLOVER_003):** an earlier figure recorded here, "3,153 / 3,521 = 89.5%", counted the total number of `"# Guest"` **Line Items** summed across all Orders, not the number of **Orders** containing one. 42 Orders (1.2%) contain more than one `"# Guest"` Line Item (e.g. a re-entered/corrected declaration), which is why the item-count numerator (3,153) exceeds the order-count numerator (3,107) against the same 3,521-Order denominator. Both numbers are individually correct for what they measure; they were not previously distinguished. The order-count figure (88.2%) is the correct "coverage" measure for declared guest count. See `CLOVER_DATA_CAPABILITY_MATRIX.md` § G for the full re-measurement, including a first-time declared-vs-derived reconciliation over the complete 3,521-Order history.

The remaining Orders contain no declared guest-count signal through this mechanism.

Interpretation:

```text
declared_guest_count_source = technical Clover Item
```

The physical implementation should preserve the exact source/provenance.

Important:

`# Guest` is a technical Clover Item used to carry business information.

It must not automatically count as a true sold product in:
- item counts;
- product mix;
- average item value;
- server menu breadth;
- revenue-item metrics.

---

# 6. Guest assignment at Order Item level

## Finding

Clover does expose the guest/seat assignment of an Order Item.

Field:

```text
binName
```

Location:

```text
Order Line Item top-level field
```

Observed in:
- bulk `orders?expand=lineItems` payloads;
- dedicated `orders/{id}/line_items?expand=modifications` payloads.

This information is **not exposed in the dashboard Line Items CSV export** used for comparison.

---

# 7. `binName` coverage

TASK_CLOVER_002 window:

```text
1,809 / 1,838 Line Items
= 98.4% contain the binName key
```

Full bulk export:

```text
22,915 / 23,342 Line Items
= 98.2% contain the binName key
```

Within the TASK_CLOVER_002 window, many present values are empty strings.

Observed values include:

```text
"Guest 1"
"Guest 2"
...
"Guest 8"
```

and compound labels such as:

```text
"Guest 7 (From Table #2)"
```

A blank value means no usable guest assignment is encoded in that field for that Line Item.

Missing/blank guest assignment must not be silently converted into a guest number.

---

# 8. Guest Number parsing

Canonical mapping:

```text
RF-One OrderItem.guest_number
← parsed ordinal guest number from Clover OrderItem.binName
```

Examples:

```text
"Guest 1"
→ guest_number = 1
```

```text
"Guest 7 (From Table #2)"
→ guest_number = 7
```

The original Clover value should also be retained in source/provenance data because `binName` is a free-text positional label, not a foreign key.

Clover does **not** expose a separate Guest entity or opaque Guest ID in the inspected payloads.

Therefore:

```text
guest_number
```

is the canonical parsed operational value,

while:

```text
binName
```

remains the source-system evidence.

---

# 9. Derived Guest Count

RF-One can derive a guest count from atomic Order Item guest assignments:

```text
derived_guest_count
= MAX(parsed OrderItem.guest_number)
```

within the relevant Order/Table Service grouping.

Example:

```text
Guest 1
Guest 1
Guest 2
Guest 4
```

produces:

```text
derived_guest_count = 4
```

This value is distinct from the declared count carried by `# Guest`.

---

# 10. Guest-count reconciliation

For the current Clover integration, RF-One can preserve both:

```text
declared_guest_count
← "# Guest".unitQty / 1000
```

and:

```text
derived_guest_count
← MAX(parsed binName guest number)
```

This enables consistency checks.

Examples:

```text
declared = 4
derived = 4
→ coherent
```

```text
declared = 2
derived = 5
→ mismatch
```

```text
declared = 5
derived = 3
→ possible incomplete Item-to-Guest assignment
```

```text
declared missing
derived = 4
→ missing declaration
```

These discrepancies should be preserved as operational/data-quality evidence rather than silently corrected.

The Product Owner has identified missing guest data primarily as an order-entry discipline/process issue in the current operational workflow, not merely a technical API limitation.

---

# 11. Other POS compatibility

The canonical RF-One model must not depend on the current `# Guest` workaround.

A future POS may provide:

```text
native guest_count
```

directly.

Therefore Clover maps into generic canonical concepts:

```text
declared_guest_count
declared_guest_count_source
derived_guest_count
OrderItem.guest_number
```

rather than defining the concepts themselves.

---

# 12. Order Item

Canonical:

```text
RF-One ORDER_ITEM
```

Primary source:

```text
Clover Line Item
```

Clover Line Items are the principal source for atomic sold-unit analysis.

TASK_CLOVER_002 confirmed that dedicated per-Order line-item endpoints were required to obtain the full modifier detail needed for faithful reconstruction.

Relevant source concepts include:
- Line Item ID;
- referenced Item;
- name;
- historical price;
- `binName`;
- `isRevenue`;
- `isOrderFee`;
- refunded/exchanged flags;
- modifications;
- other line-level attributes.

RF-One must preserve one atomic sold unit per canonical Order Item.

---

# 13. Item

Canonical:

```text
RF-One ITEM
```

Primary Clover source:

```text
Clover Inventory Item
```

Clover Item must not be interpreted as "currently displayed menu item."

The current merchant may contain:
- normal food/beverage products;
- merchandise;
- fee-like Items;
- technical Items such as `# Guest`.

RF-One classification of the Item's business nature is separate from Clover's raw catalog representation.

---

# 14. Item ↔ Modifier

Clover provides Item/Modifier associations and Modifier Groups.

Canonical relationships:

```text
ITEM ↔ MODIFIER
```

for Modifier availability/association,

and:

```text
ORDER_ITEM ↔ MODIFIER
```

for Modifiers actually selected in a specific sale.

Clover's Modifier Group is preserved as source/catalog structure:

```text
MODIFIER_GROUP → MODIFIER
```

Do not infer semantic Modifier nature from Clover alone.

Observed operational examples may include both true product variants and service/production instructions.

---

# 15. Payment

Canonical:

```text
RF-One PAYMENT
```

Primary source:

```text
Clover Payment
```

Relationship:

```text
Clover Payment → Clover Order
```

An Order can have multiple Payments.

TASK_CLOVER_002 validated 287 Payments against the official Clover Payments CSV with 100% match on the compared fields.

Payment is the canonical settlement entity, not the sale itself.

---

# 16. Tip

Canonical ownership:

```text
PAYMENT → TIP
```

Primary Clover atomic source:

```text
payment.tipAmount
```

TASK_CLOVER_002 finding:

```text
Payments.Tip Amount
← payment.tipAmount
```

Missing `tipAmount` is not automatically equivalent to zero.

In the validated reference window:

```text
253 / 287 Payments had Tip Amount populated
34 / 287 were blank
```

Clover's Orders export also displays a Tip value, but TASK_CLOVER_002 reconstructed that value by summing nested Payment `tipAmount` values.

Therefore:

```text
Clover Orders.Tip
= derived Order-level presentation
```

while:

```text
Clover payment.tipAmount
= Payment-level source fact
```

RF-One should preserve the Payment-level atomic facts and derive higher-level totals.

---

# 17. Service Charge

Canonical concept:

```text
ORDER_FEE
```

with Service Charge as one fee type.

Current Clover representation:

```text
synthetic Order Line Item
isOrderFee = true
note = "Service Charge"
```

TASK_CLOVER_002 found that Service Charge was reconstructable from Orders/Line Items.

The official Payments reference contained no populated Service Charge Amount values:

```text
0 / 287
```

Therefore the current Clover integration must not rely on Payment data for Service Charge.

Mapping:

```text
RF-One Order Fee: Service Charge
← Clover synthetic order-fee Line Item
```

The source Line Item identity/provenance should remain available even though the canonical semantic representation is an Order Fee.

---

# 18. Other fees

Other business fees may be represented as ordinary Clover Items.

Example discussed operationally:

```text
Cork Fee
```

If Clover does not explicitly expose semantic fee nature, the integration should preserve the original Item/Order Item and apply RF-One classification only when supported by independent business knowledge.

Do not infer a relationship to a specific bottle/item unless the source actually provides it.

---

# 19. Tax

Clover exposes tax-related information in multiple source objects.

Canonical ownership remains:

```text
RF-One Order → Tax
```

even when Clover also carries tax amounts in Payment representations.

TASK_CLOVER_002 showed that the official Orders Tax Amount was reconstructed from nested Payment information for that dashboard export.

That export derivation does not redefine the canonical Restaurant meaning.

The integration should preserve source tax representations sufficiently to reconcile:

```text
Order-level tax
Line-item tax detail
Payment-reported tax
```

where available.

---

# 20. Discounts

Clover exposes:
- Order-level discounts;
- Line Item-level discount information;
- dashboard-derived order-discount proportions.

Canonical RF-One model keeps original Order and Order Item discount facts distinct.

Any Clover dashboard allocation across Line Items is an export/report derivation and should not overwrite the source-level distinction.

---

# 21. Employee references

Clover source data may associate Employees with:
- Orders;
- Payments;
- possibly other source records.

These references should be preserved as source facts.

Do not automatically interpret:

```text
Order.employee
```

as:

```text
the person who personally sold every Order Item
```

and do not automatically interpret:

```text
Payment.employee
```

as:

```text
the only Employee who served the Table Service
```

Broader Table Service participation is an RF-One relationship.

---

# 22. Current guest-data mapping summary

```text
CLOVER SOURCE                         RF-ONE CANONICAL

"# Guest".unitQty / 1000
        ───────────────────────────→  declared_guest_count

source mechanism
        ───────────────────────────→  declared_guest_count_source

OrderItem.binName
        ───────────────────────────→  source guest label

parse Guest N from binName
        ───────────────────────────→  OrderItem.guest_number

MAX(OrderItem.guest_number)
        ───────────────────────────→  derived_guest_count
```

This is intentionally redundant because the difference between declared and derived values carries operational information.

---

# 23. Data-quality opportunity

The API reveals information that the normal dashboard CSV does not.

Most importantly:

```text
OrderItem.binName
```

provides Item-to-Guest positional assignment even though the dashboard Line Items export has no equivalent column.

This means RF-One can detect:
- missing guest assignment;
- declared-vs-derived guest-count mismatch;
- incomplete order-entry discipline;
- Item distribution by guest;
- shared/unassigned Item patterns.

These are potential process-quality observations.

They must not automatically become negative employee judgments without context.

---

# 24. Raw vs canonical preservation

The integration should preserve:

```text
RAW Clover evidence
```

and separately populate:

```text
RF-One canonical values
```

Example:

```text
raw binName = "Guest 7 (From Table #2)"
canonical guest_number = 7
```

Do not destroy the raw string when extracting the normalized value.

Similarly:

```text
raw "# Guest" Line Item
```

should remain auditable even when RF-One derives:

```text
declared_guest_count
```

from it.

---

# 25. Confirmed mapping confidence

## Confirmed

```text
Clover "# Guest".unitQty / 1000
→ current merchant declared guest count
```

```text
Clover OrderItem.binName
→ guest positional label
```

```text
parsed Guest N from binName
→ OrderItem.guest_number
```

```text
MAX guest_number
→ derived guest count
```

```text
Clover Payment
→ Order relationship
```

```text
payment.tipAmount
→ atomic Payment Tip source
```

```text
synthetic isOrderFee Service Charge Line Item
→ Service Charge Order Fee source
```

## Vendor-specific but semantically unresolved

```text
Modifier semantic nature
```

```text
Employee attribution beyond source-record ownership
```

```text
classification of ordinary Items that operationally represent fees
```

---

# 26. Table / Seating Zone — `Order.title` (TASK_CLOVER_003 finding)

## Finding

Clover exposes no dedicated Table entity, seat capacity, floor/layout, or dining/seating-session resource for this merchant (confirmed empirically by TASK_CLOVER_003 — see `CLOVER_DATA_CAPABILITY_MATRIX.md` § F).

However, `order.title` (present on 92.8% of Orders) was found, through structural analysis, to follow the pattern:

```text
"#<table number> - <zone>"
```

with `<zone>` observed as `Inside` or `Outside` (one real example directly confirmed: `"#4 - Inside"`, obtained via a supplementary refund lookup — see `CLOVER_DATA_CAPABILITY_MATRIX.md` § R). 97.4% of non-empty titles contain `"inside"` or `"outside"` as a substring; only 31 distinct title values exist across 3,268 non-empty Orders, each repeated hundreds of times — consistent with a small fixed set of table/zone labels, not a free-form or personal-name field.

## Mapping

```text
RF-One table_number  (candidate)
        ← parsed leading "#N" from Clover Order.title

RF-One seating_zone   (candidate)
        ← parsed "Inside"/"Outside" (and possibly a third, unconfirmed zone) from Clover Order.title
```

This is a **source artifact**, exactly like `binName` (§ 6–9 above): free text carrying business meaning Clover has no structured field for. It must not become a Clover-shaped field name in the canonical Restaurant model — only the parsed `table_number`/`seating_zone` concepts, if and when a future task confirms the parsing rule is reliable enough to promote to a canonical fact (not done by TASK_CLOVER_003, which only established the pattern).

## Merged tables

The only other evidence of merged-table behavior is the `binName` suffix `"(From Table #X)"` (116/23,342 line items, 0.5% — see § 7 above), also free text, also not a structured relationship.

---

# 27. Refunds (TASK_CLOVER_003 finding)

## Finding

TASK_CLOVER_002 could not validate Refund behavior — its reconciliation window contained no examples. TASK_CLOVER_003 found **2 real, confirmed refund records** via a bounded supplementary `GET /v3/merchants/{id}/refunds` call (not part of the standard export). Full field structure and both examples are documented in `CLOVER_DATA_CAPABILITY_MATRIX.md` § R.

## Critical mapping implication

**Neither confirmed refund is reflected in `Order.paymentState`, `Payment.result`, or any `LineItem.refunded` flag.** Both remain `"PAID"`/`"SUCCESS"`/`false` respectively, even though a full-amount refund is confirmed to exist for each, cross-checked by exact Order/Payment ID.

```text
RF-One REFUND
        ← Clover dedicated /refunds resource ONLY

NOT reliably reconstructable from:
        Order.paymentState
        Payment.result
        LineItem.refunded
```

Any future ingestion pipeline that only walks Orders → Payments → LineItems will silently miss refunds. `/refunds` must be queried and joined back explicitly (by `orderRef.id`/`payment.id`) if Refund is to be represented at all.

---

# 28. Discount — ad hoc / non-catalog shapes (TASK_CLOVER_003 finding)

## Finding

TASK_CLOVER_002's Discount derivation (`CLOVER_EXPORT_MAPPING.md` § 2) sums `order.discounts[].percentage`, validated only against catalog-referenced, percentage-type discounts (100% of its one-week window). TASK_CLOVER_003 inspected the full 3,521-Order history and found **two additional applied-discount shapes** Clover actually produces:

```text
Ad hoc / manual, percentage
        {id, orderRef, name, percentage}       — no catalog "discount" reference, no discType

Ad hoc / manual, fixed amount
        {id, orderRef, name, amount}           — amount in cents, negative sign
        (1 confirmed real example: "$50.00 Off" → amount: -5000)
```

## Implication

The existing `amount`-only derivation does not read the `amount` field at all — a real, confirmed `amount`-shaped Order-level discount would currently be silently treated as if no discount existed. This is recorded here as a mapping gap for whoever next implements Order Discount ingestion; it is not fixed by TASK_CLOVER_003 (no database/KPI code is implemented by this task).

---

# 29. Do not encode Clover quirks into the Restaurant domain

Do not make the canonical model depend on:
- `binName` as a field name;
- `# Guest` as an ontology;
- Clover synthetic fee Line Items;
- Clover dashboard Tip placement;
- Clover Modifier Group semantics;
- Clover export column layouts.

Those belong here, in the Clover mapping.

The Restaurant-domain model should remain usable with a different POS adapter.
