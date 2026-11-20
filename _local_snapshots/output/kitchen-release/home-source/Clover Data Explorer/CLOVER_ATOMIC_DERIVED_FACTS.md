# Clover Atomic and Derived Facts

TASK_CLOVER_003 — every finding from `CLOVER_DATA_CAPABILITY_MATRIX.md` and `CLOVER_SOURCE_RELATIONSHIP_MAP.md`, organized by the six categories the task requires: **Atomic source facts**, **Derived values**, **Vendor artifacts/workarounds**, **RF-One classifications required later**, **Unavailable facts**, **Inconclusive facts**. Categories are not collapsed — an item appears in exactly the category it belongs to.

---

## 1. Atomic source facts

Direct fields Clover returns as-is, with no computation or interpretation.

**Guest Count / Guest Number (required example):**
- `LineItem.binName` (raw string, e.g. `"Guest 3"`) — the atomic source fact. **The parsed `guest_number` is NOT atomic — it is derived (§ 2).**
- `"# Guest".unitQty` (raw integer, e.g. `2000`) — the atomic source fact. **`declared_guest_count` (= unitQty / 1000) is NOT atomic — it is derived (§ 2).**

**Orders:** `id`, `clientCreatedTime`, `createdTime`, `modifiedTime`, `currency`, `employee` (ref), `device` (ref), `orderType` (ref), `state`, `paymentState`, `payType`, `total`, `taxRemoved`, `isVat`, `manualTransaction`, `groupLineItems`, `testMode`, `title`, `note`, `customers` (ref, 0..1).

**Line Items (both bulk and dedicated sources):** `id`, `orderRef`, `item` (ref), `name`, `price`, `unitQty`, `unitName`, `unitQtyDecimalDigits`, `binName`, `itemCode`, `isRevenue`, `isOrderFee`, `printed`, `refunded`, `exchanged`, `note`, `orderFee`/`percentage` (fee lines only), `alternateName`, `createdTime` (the line's **own** timestamp — genuinely distinct from the order's in 95.4% of cases), `orderClientCreatedTime`, `excludeCashDiscount`, `isAgeRestricted`, `lineItemInfo` (`{"allergens": {"elements": [...]}}`, observed empty for this merchant).

**Modifications (dedicated endpoint only):** `id`, `lineItemRef`, `name`, `amount`, `modifier` (ref).

**Items (catalog):** `id`, `name`, `alternateName`, `onlineName`, `price`, `priceWithoutVat`, `cost`, `sku`, `code`, `priceType`, `type`, `defaultTaxRates`, `stockCount`, `available`, `hidden`, `enabledOnline`, `deleted`, `autoManage`, `isAgeRestricted`, `isRevenue`, `description`, `modifiedTime`, plus (via this task's supplementary `expand`) `categories`, `tags`, `modifierGroups`.

**Categories:** `id`, `name`, `sortOrder`, `deleted`.

**Tags:** `id`, `name`, `showInReporting`.

**Modifier Groups:** `id`, `name`, `showByDefault`, `modifierIds` (comma-separated string), `modifiers` (nested), `deleted`.

**Modifiers:** `id`, `name`, `available`, `price`, `modifiedTime`, `modifierGroup` (ref), `deleted`, `alternateName` (rare).

**Discounts (catalog):** `id`, `name`, `percentage`, `type`.

**Discounts (order-level, applied):** `id`, `orderRef`, and then one of two atomic shapes — `discount` (catalog ref) + `name` + `percentage` + `discType` (catalog-referenced), or `name` + `percentage` (ad hoc percentage), or `name` + `amount` (ad hoc fixed amount, negative cents) — all three shapes are atomic source facts, not derivations; **which shape applies to a given element is itself a fact to preserve, not a detail to normalize away.**

**Tax Rates:** `id`, `name`, `rate`, `isDefault`, `modifiedTime`.

**Payments:** `id`, `amount`, `taxAmount`, `tipAmount`, `cashTendered`, `cashbackAmount`, `employee` (ref), `order` (ref), `device` (ref), `tender` (nested), `clientCreatedTime`, `createdTime`, `modifiedTime`, `offline`, `result`.

**Tenders:** `id`, `label`, `labelKey`, `editable`, `enabled`, `visible`, `opensCashDrawer`, `supportsCashDiscount`.

**Refunds:** `id`, `orderRef` (expanded), `payment` (expanded), `device`, `amount`, `taxAmount`, `tipAmount`, `createdTime`, `clientCreatedTime`, `employee` (ref, the refund-processing employee), `voided`, `status`.

**Employees:** `id`, `customId`, `pin`, `isOwner`, `inviteSent`, `claimedTime`, `role` (systemRole tier string only), plus PII fields (`name`, `nickname`, `email`, `phoneNumber` — withheld from all tracked audit documents).

**Roles:** `id`, `name`, `systemRole`.

**Employee ↔ Role membership (TASK_CLOVER_004, corrects prior "unavailable" classification):** the `roles.elements[]` array returned by `employees/{id}?expand=role` (equivalently `roles/{id}?expand=employees` → `employeesRef.elements[]` from the Role side) — each element is a full Role reference (`id`, `name`, `systemRole`). Confirmed 1:1 for all 24/24 current employees; current-snapshot only (404 for an employee id no longer in `/employees`).

**Shifts:** `id`, `employee` (ref), `inTime`, `outTime`, `overrideInEmployee`/`overrideInTime`, `overrideOutEmployee`/`overrideOutTime`, `serverBanking` (present-with-value on only 1.3% of records — missing-key is the norm, not `null` and not `false`).

**Order Types:** `id`, `label`, `isDefault`, `isHidden`, `isDeleted`, `taxable`, `fee`, `minOrderAmount`, `maxOrderAmount`, `avgOrderTime`, `systemOrderTypeId`, `labelKey`.

**Item Stock:** `item` (ref), `stockCount`, `quantity`, `modifiedTime` — atomic, but universally `0` for this merchant (§ 5, Unavailable, in practice).

**Customers:** `id`, `customerSince`, `firstName`, `lastName` (PII, withheld), `marketingAllowed`, `metadata` (present, confirmed always empty).

**Devices:** `id`, `model`, `serial`, `terminalPrefix`, `deviceTypeName`, `productName`, `pinDisabled`, `offlinePayments`, `offlinePaymentsAll`.

**Merchant:** `id`, `name` (PII, withheld), `address` (PII-like, withheld), `createdTime`, `merchantPlan` (ref), `reseller` (ref); `gateway`/`printers`/`opening_hours`/`orderTypes`/`orders`/`payments`/`shifts`/`taxRates`/`tenders`/`modifierGroups` as `{href}` stubs only.

---

## 2. Derived values

Computable from one or more atomic source facts; never a Clover field itself.

**Guest Count / Guest Number (required example):**
- `guest_number = parse("Guest (\d+)", binName)` — e.g. `"Guest 7 (From Table #2)"` → `7`. Parsing rule confirmed reliable: **0 malformed/unexpected non-empty `binName` values** were found across 15,329 non-empty observations (100% matched `"Guest N"` or `"Guest N (From Table #X)"`).
- `declared_guest_count = "# Guest".unitQty / 1000` — e.g. `2000` → `2`.
- `derived_guest_count = MAX(guest_number)` within an order — e.g. guest labels 1,1,2,4 → `4`.
- The **declared-vs-derived reconciliation** itself (match / declared>derived / declared<derived / one-sided / neither) — a derived comparison, computed this task over the full 3,521-order history (see Capability Matrix § G) — not a source fact.

**Shift/Clock:**
- `Elapsed Hours = (effective clock-out − effective clock-in) / 3600` (using override time when present, else raw time) — confirmed 100% match against the Clover dashboard reference (TASK_CLOVER_002).
- `Employee Totals` = sum of an employee's Elapsed Hours within a window.
- `Override frequency` (4.7% in / 4.0% out) — an aggregate rate, not a per-record fact.

**Orders:**
- `Order.Tax Amount = sum(order.payments[].taxAmount)` — not a direct Order field.
- `Order.Tip = sum(order.payments[].tipAmount or 0)` — missing-value defaults to 0 (opposite of Payments' own blank default — both are Clover's own dashboard behavior, not an RF-One assumption).
- `Order.Service Charge = sum(price of order.lineItems[] where isOrderFee==true)` — blank (not `0.00`) when no such line item exists.
- `Order.Discount` = for **catalog-referenced/ad-hoc-percentage** shapes: `sum(revenue line item price × discount.percentage / 100)`, rounded half-up; for the **ad hoc amount** shape (confirmed to exist, § 3): not currently computed by any existing derivation — a gap, not a resolved formula.
- `Payments Total = sum(order.payments[].amount)`.

**Order Items:**
- `Total Revenue = Item Revenue + Modifiers Revenue`.
- `Order Discount Proportion` = this item's negated share of an order-level percentage discount, apportioned across revenue line items.
- `Item Total = Total Revenue + Order Discount Proportion`.
- `Item Tax Rate` = the item's own per-item `taxRates` override if `defaultTaxRates=false` (empty override list ⇒ `0`, confirmed rule, not "fall back to default"), else the merchant's `isDefault=true` catalog rate.
- `Tax Amount = Item Total × Item Tax Rate`, rounded half-up.
- `Item Total with Tax/Fee Amount = Item Total + Item Fee + Tax Amount`.

**Fees:**
- Order-type-level `fee` field is configuration, not itself a derived per-order value — no order in this history was observed to actually carry a charge produced by it (not investigated further).

**Item/Category cardinality summaries** (e.g. "318 items have 0 modifier groups") are derived aggregates over the atomic per-item `categories`/`tags`/`modifierGroups` relationship — the aggregate counts are not themselves Clover fields.

---

## 3. Vendor artifacts / workarounds

Clover mechanisms carrying business meaning they were not designed to carry — must not be encoded into the Restaurant Domain as if they were proper relationships (`CLOVER_RESTAURANT_DATA_MAPPING.md` § 26 already establishes this principle; the items below are the confirmed instances).

- **`"# Guest"` technical Item** — a sellable-Item-shaped record (`price: 0`, `isRevenue: false`) used to carry a declared headcount via `unitQty`. Must never be counted as a real sold product.
- **`LineItem.binName`** — free text used to carry guest-seat positional assignment; not a foreign key, not a Guest entity.
- **`binName` "(From Table #X)" suffix** — the only evidence of merged-table behavior; free text, not a structured merge relationship.
- **`Order.title` = `"#<table number> - <zone>"`** (e.g. the confirmed real example `"#4 - Inside"`) — free text used to carry table number + Inside/Outside zone; no structured Table entity exists to resolve it against. See Capability Matrix § F for the full structural derivation of this finding (no other raw title value is reproduced anywhere in tracked documents).
- **Synthetic `"Gratuity"` / `"Service Charge"` fee line item** (`isOrderFee: true`, `note: "Service Charge"`, catalog `orderFee` + `percentage`) — the only way Service Charge is representable at all; structurally an ordinary revenue-adjacent line item, not a first-class Fee/Charge concept in Clover's own model.
- **`"E-"`-prefixed technical Items** (`E-Pizza Via Napoli`, `E-Chicken Breast 4oz with Side Salad`, `E-Dry Pasta Napoli Based Sauce`, `E-Dry Pasta Oil or Butter Based`, `E-Tomato Bruschetta`) and **`"Side-Broccoli and Mushroom"`** — ordinary catalog Items repurposed, plausibly for staff-meal tracking (an `"Employees Meals"` Category/Tag exists) — a plausible interpretation grounded in evidence, not a confirmed Clover-documented fact (see § 4).
- **Ad hoc order-level discount elements with no catalog reference** (`"100% Off"`, `"20% Off"`, `"30% Off"`, `"$50.00 Off"`) — free-entry discount amounts typed directly at the register rather than selected from the `discounts.json` catalog; a real, confirmed Clover capability, not a data-quality defect, but structurally different from the catalog-referenced shape.
- **`Discount.percentage` vs. `TaxRate.rate` use different integer scaling conventions** (raw percent vs. ÷10,000,000) — not itself a business workaround, but a vendor inconsistency that must be documented so no future ingestion assumes a single uniform "rate" encoding across Clover objects.

---

## 4. RF-One classifications required later

Meaning Clover does not supply and RF-One (or a human reviewer) must assign — not decided in this task.

- **Modifier semantic nature** — true product/topping variant vs. service/production instruction (e.g. "Extra mozzarella" vs. "First"/"Wait for server"). A candidate heuristic (non-zero catalog `price` ⇒ likely a true add-on) was noted but **not exhaustively validated** across all 214 modifiers — offered as a hypothesis, not a rule.
- **Whether `"E-"`-prefixed Items and `"Side-Broccoli and Mushroom"` are genuinely staff-meal items** — plausible given the matching `"Employees Meals"` Category/Tag, but not independently confirmed (e.g. by asking the Product Owner).
- **Employee attribution beyond source-record ownership** — `Order.employee` and `Payment.employee` must not be interpreted as "who sold every item" / "who served the table"; any broader Table-Service participation model is an RF-One relationship to be designed, not read from Clover.
- **Classification of ordinary Items that operationally represent fees** (the discussion-only "Cork Fee" example from `CLOVER_RESTAURANT_DATA_MAPPING.md` § 18) — requires independent business knowledge, not inferable from the Item name alone.
- **Whether `Order.title`'s zone vocabulary includes a third value** (the 8-alpha-character cluster, structurally consistent with `"Curbside"` but not directly confirmed with a real example in this task) — would need one more directly-observed example to close.
- **Whether the 1 item with 15/21 categories, and the near-total overlap between Tag names and Category names, reflect a deliberate business pattern or legacy data entry** — recorded as observations (§ Capability Matrix J/T), not resolved.

---

## 5. Unavailable facts

Confirmed absent from the current API surface for this merchant/token — not merely unobserved.

- **Employee attribution at the Order Item (line-item) level** — confirmed 0% across both the bulk (23,342 items) and dedicated (1,838 items) sources.
- **Discount at the Order Item (line-item) level** — confirmed 0% across both sources; only Order-level discounts exist.
- **Tax detail as a direct field on Order or Line Item** — must be derived via the Item/rate join; no such field exists directly.
- **Merchant timezone** — no field of this kind exists anywhere on the Merchant object.
- **Employee active/inactive state** — no boolean field of this kind exists on Employee.
- **Role permissions/capabilities** — no such field exists on Role.
- ~~Specific named Role per Employee~~ — **CORRECTED by TASK_CLOVER_004, no longer unavailable.** The plain `employee.role` field is still only the tier, but `employees/{id}?expand=role` (or `roles`) returns the specific named Role (`Server`/`Host`/`BOH`/`Employee`/`Team Leader`/`Manager`/`Admin`), confirmed for all 24/24 current employees and cross-verified from the Role side (`roles/{id}?expand=employees`). See § 1 (moved) and `07 Tasks/Reports/TASK_CLOVER_004_REPORT.md`.
- **Physical Table entity, seat capacity, floor/layout, dining/seating-session entity** — no such resource exists in this Clover integration (confirmed absent from the investigated collection set and this task's supplementary calls).
- **Payment → Customer** direct reference — confirmed 0/3,751; only reachable transitively via Payment → Order → Customer.
- **Refund → Order/Payment back-reference** — Order and Payment carry no field pointing to their own Refund; the relationship is only discoverable from the Refund side.
- **`payment.result` / `order.paymentState` / `lineItem.refunded` reflecting a real, confirmed refund** — confirmed they do **not**, for both known refund examples (cross-checked by exact ID).
- **Historical inventory movement** — Item Stock is a current snapshot only (and, for this merchant, a universally-zero one); no movement/transaction log is exposed.
- **Customer loyalty/linkage data** — the `metadata` object is present as a key on every Customer record but confirmed empty on a 5,000-record sample.
- **A non-text structural cash/card indicator on Tender** — `opensCashDrawer` is `False` for every tender including `Cash`; no reliable substitute for the free-text `label` was found.

---

## 6. Inconclusive facts

Insufficient evidence to classify with confidence — not guessed, not fabricated.

- **`Employee.claimedTime` meaning** (17% coverage) — plausibly an account-claim timestamp; not confirmed.
- **`Shift.serverBanking` meaning** (present-with-value on only 1.3% of shifts) — no definition found; too rare to infer from data alone.
- **`Customer.customerSince` meaning** — behaves like a per-record creation-time proxy (4,998/5,000 sampled values distinct) rather than a meaningful "customer since" business date; not confirmed either way.
- **Merchant `opening_hours` content** — this task's supplementary GET on the href failed (network-level error, status 0); genuinely not resolved, not merely deprioritized.
- **Partial refund behavior** — both of the 2 confirmed refund examples are full-amount refunds; whether a partial refund uses the same structure is not evidenced.
- **`voided: true` behavior** — no example exists anywhere in the currently accessible data; `voided` is confirmed present as a field, but only ever observed `false`.
- **The ~half-priced `LineItem.price` residual on a handful of items in 10 orders** (TASK_CLOVER_002) — carried forward unresolved; no new evidence was found or sought in this task.
- **Whether `Order.title`'s ~2.4% non-Inside/Outside/digit-pattern residual (77/3,268) carries different information** — not investigated further, to avoid printing raw title values that might not be safe business labels for the remaining minority.
- **Whether the configured Order-Type-level `fee` (60% of order types) has ever actually produced a charge** — not found to have done so in this history, but a full search was not performed (out of scope for this pass).

---

**End of Atomic and Derived Facts.**
