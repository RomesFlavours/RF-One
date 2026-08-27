# Clover Source Relationship Map

TASK_CLOVER_003 — the confirmed source-system relationship graph for merchant `PYQYB7SKB6V31`, based only on empirically observed Clover API relationships. This document is about **Clover as a source system**, not RF-One ontology — no canonical RF-One entity name is used below (see `CLOVER_RESTAURANT_DATA_MAPPING.md` for the Clover → RF-One mapping).

Every relationship is marked:

- **CONFIRMED** — directly observed in the raw data or via a supplementary GET, with a measured cardinality.
- **INFERRED** — structurally present (an id-shaped field) but not independently cross-checked against the referenced collection in this pass.
- **UNRESOLVED** — plausible but not evidenced, or evidenced only as free text rather than a structured relationship.

No relationship is included merely because it would be useful.

---

## 1. Merchant-level graph

```text
Merchant (1)
├── Employees (24)                              CONFIRMED — top-level collection, merchant-scoped by token
├── Roles (7)                                    CONFIRMED
├── Customers (101,597)                          CONFIRMED
├── Items (532)                                  CONFIRMED
├── Categories (21)                               CONFIRMED
├── Tags (20)                                     CONFIRMED
├── ModifierGroups (19) → Modifiers (214)         CONFIRMED — modifiers only reachable nested under a group in this export
├── Discounts (5, catalog)                        CONFIRMED
├── TaxRates (4)                                  CONFIRMED
├── OrderTypes (10)                               CONFIRMED
├── Devices (3)                                   CONFIRMED — separate endpoint, not on Order/Payment/Merchant inline
├── ItemStocks (511)                              CONFIRMED
├── Shifts (4,368)                                CONFIRMED
├── Orders (3,521)                                CONFIRMED
├── Payments (3,751)                              CONFIRMED
└── Refunds (2, confirmed via this task's supplementary GET)   CONFIRMED
```

`merchant.opening_hours`, `.gateway`, `.printers`, `.tenders`, `.taxRates`, `.orderTypes`, `.modifierGroups` are exposed only as `{href}` stubs on the base Merchant object — **UNRESOLVED / not dereferenced** for `opening_hours` (this task's supplementary GET failed) and `printers`/`gateway` (classified as configuration noise, not attempted — see Capability Matrix § A); `.tenders`/`.taxRates`/`.orderTypes` are redundant with already-fetched top-level collections and were not separately followed.

---

## 2. Order graph

```text
Order (3,521)
├── Employee                       CONFIRMED, 1:1 (order-level reference only — see § 6 warning)
├── Device                         CONFIRMED, 1:1
├── OrderType                      CONFIRMED, 1:1 — real usage: "Table" 93.6%, "To Go on Site (Asap)" 5.7%, "Employee" 0.6%, "Sample" 0.1%
├── Customer                       CONFIRMED, 0..1 (never observed >1) — present on 82.3% of orders
├── LineItems                      CONFIRMED, 1..n (23,342 total across 3,521 orders; every order has ≥1)
├── Payments (nested)              CONFIRMED, 1..4 — EXCLUDES failed payment attempts (see § 6)
├── Discounts (nested)             CONFIRMED, 0..n — present on 2.1% of orders; two distinct element shapes (catalog-referenced vs. ad hoc, see Capability Matrix § L)
└── Refund                         CONFIRMED (indirect only) — reachable via Refund.orderRef, not from the Order side; Order carries no field referencing its own Refund(s)
```

**Order.title as table/zone reference — UNRESOLVED as a structural relationship.** Strong structural and one directly-confirmed real example (`"#4 - Inside"`, obtained via the refunds supplementary GET) indicate `order.title` encodes a table number + seating zone as free text (see Capability Matrix § F). This is recorded as a **source artifact**, not a relationship, because there is no foreign key — only a text string with no dedicated Table entity to resolve against.

---

## 3. Order Item (Line Item) graph

```text
LineItem (23,342 bulk / 1,838 dedicated-endpoint-confirmed subset)
├── Order (orderRef)                             CONFIRMED, n:1
├── Item                                          CONFIRMED, n:1 — present on 98.1–98.4% (absent on fee/technical lines with no catalog Item)
├── Modifications → Modifier                      CONFIRMED, 1:n — dedicated endpoint only (17.1% of dedicated-window items carry ≥1); STRUCTURALLY ABSENT from the bulk export (0%, not merely incomplete)
├── binName (guest positional label)              CONFIRMED as a field; UNRESOLVED as a relationship — free text, no Guest entity exists to resolve against (see § 4)
├── orderFee (fee catalog reference)               CONFIRMED, present only on the 1.8% of lines with isOrderFee=true
└── Employee                                       UNRESOLVED — confirmed ABSENT (0% coverage, both bulk and dedicated); no employee attribution exists at line-item granularity in Clover for this merchant
```

---

## 4. Guest — not a Clover entity

There is **no Guest entity, endpoint, or opaque Guest ID anywhere in the inspected Clover API surface.** Everything guest-related is reconstructed from two independent free-text/quantity artifacts, neither of which is a relationship in the structural sense:

```text
"# Guest" technical Item (isRevenue=false, unitQty encodes count×1000)
        UNRESOLVED as a relationship — a workaround Item, not a Guest entity

LineItem.binName ("Guest N" / "Guest N (From Table #X)")
        UNRESOLVED as a relationship — free text, not a foreign key to any Guest record
```

See `CLOVER_ATOMIC_DERIVED_FACTS.md` for how RF-One may derive `guest_number`/`declared_guest_count`/`derived_guest_count` from these two artifacts without treating either as a genuine Clover relationship.

---

## 5. Employee / Role / Shift graph

```text
Employee (24)
├── Role (tier)              CONFIRMED — `employee.role` (plain, un-expanded) is the systemRole TIER string (EMPLOYEE/MANAGER/ADMIN) only.
├── Role (specific, CORRECTED by TASK_CLOVER_004)   CONFIRMED, 1:1 (all 24/24 current employees) — via `employees/{id}?expand=role` (or `roles`), which returns `roles.elements[]` carrying the specific named Role (id/name/systemRole). Independently confirmed from the Role side via `roles/{id}?expand=employees` → `employeesRef.elements[]`. Current-snapshot only (404 for a historical/absent employee id, same as Employee itself). See `07 Tasks/Reports/TASK_CLOVER_004_REPORT.md`.
├── Orders (as order.employee)          CONFIRMED, 1:n (order-side reference)
├── Payments (as payment.employee)       CONFIRMED, 1:n (payment-side reference)
├── Shifts (as shift.employee)           CONFIRMED, 1:n (shift-side reference)
└── Refunds (as refund.employee)         CONFIRMED, 1:n (refund-side reference; confirmed distinct from the order/payment employee in both known examples)

Shift (4,368)
├── Employee                              CONFIRMED, n:1
├── overrideInEmployee / overrideOutEmployee   CONFIRMED, n:1 each — present on 4.7%/4.0% of shifts; may differ from Shift.employee (manager correction)
```

---

## 6. Payment graph

```text
Payment (3,751)
├── Order                                  CONFIRMED, n:1
├── Employee                               CONFIRMED, n:1
├── Device                                 CONFIRMED, n:1
├── Tender                                 CONFIRMED, n:1 (nested object, not a separate top-level Tender collection actually queried — the tender object arrives inline via expand)
├── CardTransaction                        CONFIRMED, 1:1 where present — supplementary `expand=cardTransaction` per payment (TASK_CLOVER_002); not part of the bulk export
└── Customer                               UNRESOLVED — confirmed ABSENT; no field on Payment references a Customer at all (only reachable transitively via Payment → Order → Customer)
```

**Order.payments (nested) vs. top-level Payments — exact, confirmed relationship gap:** nested `order.payments` sums to 3,715 across all orders; the top-level `payments.json` collection has 3,751. The difference (36) equals exactly the count of `result: "FAIL"` payments. **CONFIRMED: `Order.payments` excludes failed payment attempts; the top-level Payments collection is the only complete view.**

---

## 7. Refund graph (new this task)

```text
Refund (2 confirmed records, via dedicated /refunds endpoint)
├── orderRef        CONFIRMED, n:1 — fully-expanded nested Order object inline (not just an id)
├── payment          CONFIRMED, n:1 — fully-expanded nested Payment object inline
├── device            CONFIRMED, n:1
└── employee           CONFIRMED, n:1 — the employee who processed the refund; confirmed DIFFERENT from orderRef.employee / payment.employee in both known examples

Order  ⇢  Refund     UNRESOLVED (indirect only) — no field on Order or Payment references a Refund; the relationship is only discoverable by separately querying /refunds and matching orderRef.id / payment.id back to the already-known Order/Payment collections
```

**This is the single most important relationship-completeness finding of this task:** a Refund's existence is invisible from the Order, Payment, or LineItem side. Any future ingestion that only walks Orders → Payments → LineItems will silently miss refunds entirely unless `/refunds` is queried and joined back explicitly.

---

## 8. Item / Category / Tag / ModifierGroup graph

```text
Item (532)
├── Category            CONFIRMED, 0..n — 0 categories: 32 items (6.0%); 1: 498 (93.6%); 2: 1; 15: 1 (verified genuinely distinct, not a duplication artifact)
├── Tag                 CONFIRMED, 0..n — 0 tags: 41 items (7.7%); 1: 490 (92.1%); 2: 1
├── ModifierGroup        CONFIRMED, 0..n — 0: 318 (59.8%); 1: 99; 2: 41; 3: 58; 4: 16
└── TaxRate override      CONFIRMED, 0..1 (via defaultTaxRates=false + supplementary expand=taxRates; an empty override list means 0%, not "fall back to default" — confirmed rule, not inferred)

ModifierGroup (19)
└── Modifier              CONFIRMED, 1:n (214 total; also cross-referenced back via Modifier.modifierGroup)
```

---

## 9. Summary table

| Relationship | Cardinality | Status |
|---|---|---|
| Merchant → Employees/Roles/Customers/Items/Categories/Tags/ModifierGroups/Discounts/TaxRates/OrderTypes/Devices/ItemStocks/Shifts/Orders/Payments | 1:n each | CONFIRMED |
| Merchant → Refunds | 1:n | CONFIRMED (via dedicated endpoint, not merchant-nested) |
| Order → Employee/Device/OrderType | n:1 each | CONFIRMED |
| Order → Customer | 0..1 | CONFIRMED |
| Order → LineItems | 1..n | CONFIRMED |
| Order → Payments (nested) | 1..4, excludes FAILED | CONFIRMED |
| Order → Discounts (nested) | 0..n, two element shapes | CONFIRMED |
| Order ↔ Refund | — | UNRESOLVED (indirect only, via Refund.orderRef) |
| Order.title → Table/Zone | — | UNRESOLVED (free-text artifact, no entity) |
| LineItem → Order/Item | n:1 each | CONFIRMED |
| LineItem → Modifications → Modifier | 1:n | CONFIRMED (dedicated endpoint only) |
| LineItem → Employee | — | UNRESOLVED (confirmed absent) |
| LineItem.binName → Guest | — | UNRESOLVED (free-text artifact, no Guest entity) |
| Employee → Role (tier) | 1:1 | CONFIRMED |
| Employee → Role (specific named Role) | 1:1 (24/24 current employees), current-snapshot only | CONFIRMED — CORRECTED by TASK_CLOVER_004 via `?expand=role`/`?expand=employees` (was UNRESOLVED) |
| Employee → Orders/Payments/Shifts/Refunds | 1:n each | CONFIRMED |
| Shift → Employee / override Employees | n:1 each | CONFIRMED |
| Payment → Order/Employee/Device/Tender/CardTransaction | n:1 each | CONFIRMED |
| Payment → Customer | — | UNRESOLVED (confirmed absent) |
| Refund → Order/Payment/Device/Employee | n:1 each | CONFIRMED |
| Item → Category/Tag/ModifierGroup | 0..n each | CONFIRMED |
| Item → TaxRate override | 0..1 | CONFIRMED |
| ModifierGroup → Modifier | 1:n | CONFIRMED |

---

**End of Relationship Map.**
