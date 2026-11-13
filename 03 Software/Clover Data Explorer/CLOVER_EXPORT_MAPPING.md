# Clover Export Mapping

TASK_CLOVER_002 — per-column mapping from the Clover dashboard reference CSVs to the raw Clover API data (`03 Software/Clover Data Explorer/data/raw/`) and, where a value is not a direct field, the derivation used by `clover_explorer/export_payments.py`, `export_orders.py`, and `export_line_items.py`.

Confidence labels:

- **Confirmed** — verified byte-for-byte against reference rows across the full 2026-08-17→2026-08-23 window comparison (see `CLOVER_EXPORT_RECONCILIATION.md`), 100% or effectively 100% field match.
- **Strongly supported** — verified against multiple real examples but not covered by an automatable field-match check (e.g. because the reference is always blank for this merchant).
- **Inferred** — a plausible, partially-tested derivation; not contradicted by available evidence but not exhaustively validated.
- **Unresolved** — no source field/formula identified; RF-One's output is deliberately left blank rather than fabricated.

No mapping below was upgraded to Confirmed without an actual passing field-match measurement.

---

## 1. Payments

| Dashboard column | API source | Transformation | Join required | Confidence |
|---|---|---|---|---|
| Payment Date | `payment.createdTime` | epoch ms → `23-Aug-2026 09:34 PM EDT` (Eastern) | — | Confirmed |
| Payment ID | `payment.id` | — | — | Confirmed |
| External Payment ID | *(none found)* | — | — | Unresolved |
| Invoice Number | *(none found)* | — | — | Unresolved |
| Card Auth Code | `payment.cardTransaction.authCode` | — | `GET /payments/{id}?expand=cardTransaction` (supplementary, not in TASK_CLOVER_001's export) | Confirmed |
| Transaction # | `payment.cardTransaction.transactionNo` | — | same as above | Confirmed |
| Note | *(none found)* | — | — | Unresolved |
| Tender | `payment.tender.label` | — | present via `expand=tender`, already fetched by TASK_CLOVER_001 | Confirmed |
| Card Brand | `payment.cardTransaction.cardType` | — | same cardTransaction join | Confirmed |
| Card Number | `payment.cardTransaction.last4` | — | same cardTransaction join | Confirmed |
| Card Entry Type | `payment.cardTransaction.entryType` | — | same cardTransaction join | Confirmed |
| Currency | `order.currency` | uppercased | `payment.order.id` → order | Strongly supported (no direct `currency` field exists on the Payment object itself) |
| Amount | `payment.amount` | minor units ÷ 100 | — | Confirmed |
| Tax Amount | `payment.taxAmount` | minor units ÷ 100 | — | Confirmed |
| Tip Amount | `payment.tipAmount` | minor units ÷ 100, **missing key → blank, NOT 0.00** | — | Confirmed (see §5 below — this is the opposite default from Orders.Tip) |
| Service Charge Amount | *(field does not exist on Payment)* | always blank | — | Confirmed absent — 0/287 reference rows populated; see §5 |
| Customer Name | `payment.cardTransaction.cardholderName` | — | same cardTransaction join | Strongly supported (sourced from the card processor's cardholder name, not a Clover Customer record) |
| Payment Employee ID/Name/Custom ID | `payment.employee.id` → `employees.json` | — | employee id join | Confirmed |
| Order ID | `payment.order.id` | — | — | Confirmed |
| Order Date | `order.createdTime` | epoch ms → dashboard datetime | order id join | Confirmed |
| Order Employee ID/Name/Custom ID | `order.employee.id` → `employees.json` | — | order id join, then employee id join | Confirmed |
| Result | `payment.result` | — | — | Confirmed |
| Device | `payment.device.id` → `devices[].serial` | — | `GET /devices` (supplementary, tiny collection, 1 call) | Confirmed |
| # Refunds | *(none found)* | — | — | Unresolved — no refunded payment in the validated window to confirm a source; Clover v3 likely exposes this via a `refunds` sub-resource not queried in this task |
| Refund Amount | *(none found)* | — | — | Unresolved — same as above |
| Custom Fields | *(none found)* | — | — | Unresolved |

---

## 2. Orders

| Dashboard column | API source | Transformation | Join required | Confidence |
|---|---|---|---|---|
| Order Date | `order.createdTime` | epoch ms → dashboard datetime | — | Confirmed |
| Order ID | `order.id` | — | — | Confirmed |
| Invoice Number | *(none found)* | — | — | Unresolved |
| Order Number | *(none found)* | — | — | Unresolved |
| Order Type | `order.orderType.id` → `order_types.json[].label` | — | order type id join | Confirmed |
| Order Employee ID/Name/Custom ID | `order.employee.id` → `employees.json` | — | employee id join | Confirmed |
| Note | `order.note` | — | — | Strongly supported (rare field, present on ~1% of orders) |
| Currency | `order.currency` | uppercased | — | Confirmed |
| Tax Amount | **not a field on Order** — `sum(order.payments[].taxAmount)` | minor units ÷ 100 | order's own nested payments | Confirmed |
| Tip | **not a field on Order** — `sum(order.payments[].tipAmount or 0)` | minor units ÷ 100, **missing key defaults to 0** | order's own nested payments | Confirmed — this default-to-zero IS the dashboard's actual behavior for Orders (contrast with Payments.Tip Amount, which stays blank; see §5) |
| Service Charge | **not a field anywhere** — `sum(price of order.lineItems[] where isOrderFee==true)` | minor units ÷ 100, **blank (not 0.00) when no such line item exists** | order's own nested lineItems | Confirmed — see §5 for the full Service Charge finding |
| Discount | `sum` of each revenue line item's price × `order.discounts[].percentage` ⁄ 100, negated | rounded half-up to the cent | order's own nested discounts + lineItems | Confirmed for percentage-type discounts (100% of this merchant's window). Non-percentage discount types are Unresolved — not present in the validated data, not guessed |
| Order Total | `order.total` | minor units ÷ 100 | — | Confirmed |
| Payments Total | `sum(order.payments[].amount)` | minor units ÷ 100 | order's own nested payments | Confirmed |
| Payment Note | *(none found)* | — | — | Unresolved |
| Refunds Total | *(none found)* | — | — | Unresolved — no refunded order in this window |
| Manual Refunds Total | *(none found)* | — | — | Unresolved — same as above |
| Tender | one `tender.label` **per payment, not deduplicated**, comma-joined in payment order | — | top-level `payments.json` (has `expand=tender`), joined per payment id | Confirmed |
| Credit Card Auth Code | first available `payment.cardTransaction.authCode` among the order's payments | — | cardTransaction join (shared cache with Payments export) | Confirmed for single-payment orders; Inferred (first-found) for the rare multi-payment order |
| Credit Card Transaction ID | first available `payment.cardTransaction.referenceId` | — | same cardTransaction join | Confirmed for single-payment orders; Inferred for multi-payment |
| Order Payment State | `order.paymentState` | `"PAID"` → `"Paid"` (only mapping observed) | — | Confirmed for `PAID`; other raw states pass through unmapped (Unresolved — not observed in this window) |

---

## 3. Line Items

The most involved reconstruction. `orders?expand=lineItems` (TASK_CLOVER_001's bulk export) never includes `modifications` — confirmed absent on every sampled line item, even ones the reference shows a modifier on. Full modifier data requires `GET /orders/{orderId}/line_items?expand=modifications` per order (one supplementary call per in-window order).

| Dashboard column | API source | Transformation | Confidence |
|---|---|---|---|
| Line Item Date | `order.createdTime` (not the individual line item's own `createdTime`) | epoch ms → dashboard datetime | Confirmed — every line item in an order shares the order's timestamp in the reference, not its own |
| Order Employee ID/Name/Custom ID | `order.employee.id` → employees | — | Confirmed |
| Item ID | `lineItem.item.id` | blank for fee/order-level items (Gratuity) | Confirmed |
| Item Product Code | `items.json[itemId].code` | — | Strongly supported (join confirmed structurally; always blank for this merchant's catalog, so never exercised against a non-blank reference value) |
| Item SKU | `items.json[itemId].sku` | — | Strongly supported (same caveat as Product Code) |
| Order ID | `order.id` | — | Confirmed |
| Item Name | `lineItem.name` | — | Confirmed (not `alternateName`, which the dashboard does not use here) |
| Currency | `order.currency` | uppercased | Confirmed |
| Per Unit Quantity | `lineItem.unitQty` | ÷ 1000, 3 decimals; **blank if key absent** (not every item carries a quantity) | Confirmed |
| Item Unit | `lineItem.unitName` | blank if absent | Confirmed |
| Item Revenue | `lineItem.price` | minor units ÷ 100 | Confirmed for the overwhelming majority of rows — **except an unresolved minority; see §5** |
| Modifiers | `lineItem.modifications[].{name, modifier.id, amount}` | `"{name} ({modifierId}) ${amount/100:.2f}"`, multiple modifiers joined `", "` | Confirmed for single-modifier lines; Inferred separator for multi-modifier lines (limited test coverage) |
| Modifiers Revenue | `sum(modifications[].amount)` | minor units ÷ 100, **blank if no modifications** (not 0.00) | Confirmed |
| Total Revenue | Item Revenue + Modifiers Revenue | — | Confirmed |
| Discounts | *(no line-item-level discount mechanism identified, distinct from order-level)* | always blank | Confirmed absent for this merchant (0 non-blank reference rows) |
| Total Discount | *(same — always `"0.00"`, never blank)* | fixed `"0.00"` | Confirmed (0/1838 reference rows non-zero) |
| Order Discounts | text description of this item's share of an order-level percentage discount | `"{discountName} ({pct}%) -${share:.2f}"`, multiple joined `"; "` | Confirmed |
| Order Discount Proportion | **a dollar amount, despite the column name** — the negated per-item discount share | — | Confirmed |
| Item Total | Total Revenue + Order Discount Proportion (i.e. minus the discount share) | — | Confirmed for the same majority as Item Revenue |
| Item Tax Rate | `tax_rates.json` entry with `isDefault=true` if `item.defaultTaxRates=true`; otherwise the item's own `taxRates` (via `GET /items/{id}?expand=taxRates`, supplementary) — **an empty per-item `taxRates` list means 0%, not "fall back to default"** | rate ÷ 10,000,000, formatted as Python's default float string (e.g. `0.065`, `0.0`) | Confirmed (100% field match after this exact empty-list-means-zero rule was identified — see `CLOVER_EXPORT_RECONCILIATION.md` §3) |
| Item Fee | *(no source field identified)* | fixed `"0.00"` | Inferred — always 0.00 across all 1838 validated rows, but no field was found that would produce a non-zero value if this merchant used one |
| Tax Amount | Item Total × Item Tax Rate | rounded half-up to the cent | Confirmed |
| Item Total with Tax/Fee Amount | Item Total + Item Fee + Tax Amount | — | Confirmed |
| Refunded | `lineItem.refunded` | lowercase `"true"`/`"false"` | Confirmed (all `false` in this window — no refunds to validate `true` against) |
| Exchanged | `lineItem.exchanged` | lowercase `"true"`/`"false"` | Confirmed (same caveat) |
| Order Payment State | `order.paymentState` | same mapping as Orders.Order Payment State | Confirmed |
| Service Charge | `lineItem.isOrderFee` | `"True"` (capitalized, unlike Refunded/Exchanged) if true, else blank | Confirmed |

---

## 4. Clock

Three sections; see `CLOVER_EXPORT_RECONCILIATION.md` §4 for full validation (100% match on all three sections against the reference for this window).

| Dashboard column | API source | Confidence |
|---|---|---|
| SHIFTS: Clock In/Out | `shift.overrideInTime` if present else `shift.inTime`; `shift.overrideOutTime` if present else `shift.outTime` | Confirmed |
| SHIFTS: Elapsed Hours | (effective clock-out − effective clock-in) ÷ 3600s, 2 decimals | Confirmed |
| EMPLOYEE TOTALS: Total Hours | sum of each employee's SHIFTS-section elapsed hours in the window | Confirmed |
| OVERRIDDEN SHIFTS: Override Clock In/Out | `shift.overrideInTime` / `shift.overrideOutTime` (blank if that side wasn't overridden) | Confirmed |
| OVERRIDDEN SHIFTS: Overridden by | `shift.overrideInEmployee` / `shift.overrideOutEmployee` → employee name | Confirmed |
| OVERRIDDEN SHIFTS: Actual Clock In/Out | `shift.inTime` / `shift.outTime` (the raw, un-overridden clock event) | Confirmed |
| OVERRIDDEN SHIFTS: Overridden/Actual Elapsed Hours, Difference | derived from the above pairs | Confirmed, with one caveat: Clover's own reference export shows a ~0.01h rounding discrepancy between its SHIFTS-section "Elapsed Hours" and OVERRIDDEN-SHIFTS-section "Overridden Elapsed Hours" for the *same* in/out pair — a property of the source export itself, not of this reconstruction (see reconciliation report) |

Employee ID/Name/Custom ID throughout: `employees.json` join by id. Confirmed.

---

## 5. Key semantic findings (Tip / Service Charge) — no business rule decided here

1. **Payments.Tip Amount vs Orders.Tip use opposite missing-value defaults.** A payment with no tip has `tipAmount` **absent** from the API payment object; the Payments dashboard export leaves the cell **blank**. The Orders dashboard export, for the very same underlying payment, shows **`0.00`** — confirmed on real examples where the order-nested payment object carries `tipAmount: 0` explicitly while the top-level payment for the identical payment ID has no `tipAmount` key at all. **RF-One's reconstruction preserves this distinction deliberately**: Payments_RFOne.csv leaves a missing tip blank; Orders_RFOne.csv defaults a missing tip to 0.00 — because that is what the reference dashboard itself does, not an assumption.
2. **Service Charge is essentially absent from the Payments API/export, and only reconstructable from Orders/Line Items.** No `serviceCharge`-like field exists on the Payment object; 0 of 287 reference Payments rows populate `Service Charge Amount`. The value only exists as a synthetic line item on the **Order**: `name: "Gratuity"`, `note: "Service Charge"`, `isOrderFee: true`, `isRevenue: false`, with a `percentage` (e.g. `180000` = 18.0000%) and an `orderFee` reference. 29 of 271 reference Orders rows (≈10.7%) have a non-zero Service Charge, and every one of them is reconstructed from this synthetic line item, not from any Payment field.
3. This directly matches the Product Owner's own observation that the current manual Excel process sometimes has to fall back to the Order export for Service Charge, because the Payment export cannot carry it at all.
4. **No decision is made here about which field RF-One should use for tip/service-charge payroll calculation.** That is explicitly deferred to TASK_CLOVER_003 (see the task report, §O).
