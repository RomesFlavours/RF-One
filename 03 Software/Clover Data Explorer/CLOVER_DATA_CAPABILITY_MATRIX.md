# Clover Data Capability Matrix

TASK_CLOVER_003 — comprehensive empirical audit of what the current Clover production account (merchant `PYQYB7SKB6V31`) can provide for RF-One, based on:

- the full raw export `data/raw/2026-08-24T231114Z/` (TASK_CLOVER_001): 3,521 Orders, 3,751 Payments, 4,368 Shifts, 24 Employees, 7 Roles, 101,597 Customers, 532 Items, 21 Categories, 19 Modifier Groups (214 Modifiers), 511 Item Stocks, 5 Discounts, 4 Tax Rates, 20 Tags, 10 Order Types, 1 Merchant;
- the dedicated per-order `line_items?expand=modifications` cache from TASK_CLOVER_002 (271 orders / 1,838 line items, the 2026-08-17→2026-08-23 reconciliation window);
- new bounded, read-only supplementary GET calls made by this task (§ below) to close specific unresolved questions.

Classification legend (per TASK_CLOVER_003 § 2):

| Code | Meaning |
|---|---|
| **A** | DIRECT SOURCE FACT — a field Clover returns as-is |
| **B** | DERIVABLE FROM SOURCE FACTS — computable from one or more direct facts |
| **C** | RF-ONE INTERPRETATION / CLASSIFICATION — meaning assigned by RF-One, not by Clover |
| **D** | SOURCE ARTIFACT / WORKAROUND — a vendor-specific mechanism carrying business meaning it wasn't designed for |
| **E** | UNAVAILABLE — not exposed by the current API surface for this merchant/token |
| **F** | INCONCLUSIVE — insufficient evidence to classify with confidence |

No PII values (customer/employee names, emails, phone numbers, card digits, payment identifiers) appear anywhere in this document. Item, category, tag, discount, role, order-type and tender **names** are business/catalog labels, not personal data, and are included where they materially inform the audit (consistent with `CLOVER_EXPORT_MAPPING.md`/`CLOVER_EXPORT_RECONCILIATION.md`, which already do this).

---

## New supplementary GET calls made by this task

| # | Call | Reason | Result | Cached at |
|---|---|---|---|---|
| 1 | `GET /v3/merchants/{id}/items?expand=categories,tags,modifierGroups&limit=1000` | Bulk `items.json` (TASK_CLOVER_001) carries no `categories`/`tags`/`modifierGroups` field at all — needed to close Item↔Category, Item↔Tag, Item↔ModifierGroup cardinality (audit areas I/J/K/T) | 200 OK, 532/532 items, 1 page | `data/generated_exports/_api_cache/task3_audit/items_expand_categories_tags_modifierGroups.json` |
| 2 | `GET` merchant.opening_hours href | Merchant object only exposes `opening_hours` as an unfollowed `{href}` stub; business hours are potentially operationally useful (area A) | **Failed** (status 0 / network-level error on this specific href) | not cached — no data obtained |
| 3 | `GET /v3/merchants/{id}/refunds?limit=100` | Orders/Payments/LineItems show **zero** refund/void/exchange evidence anywhere in the full raw export (area R); Clover v3 exposes Refunds as its own top-level resource, not yet queried by any prior task | 200 OK, **2 elements**, 1 page (no further pages) | `data/generated_exports/_api_cache/task3_audit/refunds_page1.json` |

All three calls were `GET` only, used the existing `.env` token (never displayed), and are cached under the already-Git-ignored `data/generated_exports/_api_cache/` tree. No new endpoint was added to the permanent exporter (`orchestrator.py`) — see § Recommended Canonical Ingestion Set for whether each belongs there.

---

## A. Merchant / Location

| Business concept | Clover source | Fields | Class | Coverage | Historical availability | Confidence | RF-One relevance | Known issue |
|---|---|---|---|---|---|---|---|---|
| Merchant identity | `merchant.json` | `id`, `name` (PII-like, withheld) | A | 1/1 | n/a (single snapshot) | Confirmed | High | — |
| Location/address | `merchant.address` | object, PII-like, withheld | A | 1/1 | n/a | Confirmed | Low–Medium | Single location only observed; no multi-location structure evidenced |
| Timezone | *(not found)* | — | **E** | 0/1 | — | Confirmed absent | High (needed for all timestamp display) | No `timezone` field exists anywhere on the Merchant object. TASK_CLOVER_002's `America/New_York` conversion is an **assumption supplied out-of-band**, not sourced from the API — this remains open (see `CLOVER_EXPORT_MAPPING.md` and TASK_CLOVER_001 report §N) |
| Currency | `order.currency` | string | A | 3,521/3,521 (100%), always `"USD"` | full order history | Confirmed | Medium | No currency field was found directly on Merchant itself; sourced indirectly via Order |
| Business settings / opening hours | `merchant.opening_hours` | `{href}` stub only | **F** | — | — | Inconclusive | Low–Medium | This task's supplementary GET on the href failed (network-level, status 0); not resolved this session |
| Devices | separate `/devices` endpoint (TASK_CLOVER_002 supplementary call) | `id`, `model`, `serial`, `terminalPrefix`, `deviceTypeName`, `productName`, `pinDisabled`, `offlinePayments*` | A | 3/3 devices | n/a (config snapshot) | Confirmed | Medium (device-level segmentation, e.g. front counter vs. kitchen display) | Only referenced by `id` on Orders/Payments; never expanded inline |
| Printers | `merchant.printers` | `{href}` stub only | **E** (not dereferenced) | — | — | — | Low | Not fetched — hardware configuration, not business data; classified as vendor noise without spending a GET on it |
| Gateway | `merchant.gateway` | `{}` (empty object, no `href`) | **E** | 0/1 | — | Confirmed empty | Low | Payment gateway configuration is not exposed at all for this token/merchant |
| Tenders / TaxRates / OrderTypes (merchant-nested) | `merchant.tenders`/`.taxRates`/`.orderTypes` | `{href}` stubs | — | — | — | — | — | Redundant with the already-fetched top-level `tax_rates.json`/`order_types.json` collections and `payment.tender`; not separately dereferenced |

**Classification: Merchant identity/currency/devices = operationally useful. Address/gateway/printers/opening_hours = vendor configuration noise or currently unresolved, low priority for a Restaurant Sales/Service pipeline.**

---

## B. Employees

| Field | Class | Coverage | Notes |
|---|---|---|---|
| `id`, `href` | A | 24/24 (100%) | — |
| `name` | A (PII) | 24/24 (100%) | withheld from this document |
| `nickname` | A (PII) | 21/24 (88%) | withheld |
| `email` | A (PII) | 4/24 (17%) | withheld |
| `phoneNumber` | A (PII) | ~2/24 (8%) | withheld |
| `customId` | A | 16/24 (67%) | POS-assigned short code, not a name |
| `pin` | A | 24/24 (100%) | POS login PIN/code — treated as sensitive, not reproduced |
| `isOwner` | A | 24/24 (100%) | boolean |
| `inviteSent` | A | 24/24 (100%) | boolean |
| `claimedTime` | A | 4/24 (17%) | epoch ms; meaning not confirmed (likely account-claim time) — **F** |
| `role` | A | 24/24 (100%) | **string value of the `systemRole` TIER only** (`EMPLOYEE`/`MANAGER`/`ADMIN`) — see § C, not a reference to a specific named Role |
| active/inactive state | — | 0/24 | **E** — no boolean field of this kind was found on Employee at all |

**Employee relationships (source semantics, exact — do not over-interpret):**

| Relationship | Field | Coverage | Status | Exact meaning |
|---|---|---|---|---|
| Employee → Orders | `order.employee` (id ref) | 3,521/3,521 (100%) | CONFIRMED | The employee associated with the Order record — **not** "who sold every Order Item" |
| Employee → Payments | `payment.employee` (id ref) | 3,751/3,751 (100%) | CONFIRMED | The employee associated with the Payment/settlement — **not** "who served the table" |
| Employee → Shifts | `shift.employee` (id ref) | 4,368/4,368 (100%) | CONFIRMED | The employee whose clock event this is |
| Employee → Line Items | *(no field)* | 0/23,342 bulk; 0/1,838 dedicated | **UNAVAILABLE** | Confirmed absent in both the bulk `expand=lineItems` export and the dedicated `line_items` endpoint — no per-item employee attribution exists in Clover for this merchant |
| Employee → Refunds | `refund.employee` (id ref) | 2/2 confirmed refund records | CONFIRMED | The employee who processed the refund — can differ from the order/payment employee (confirmed on both real examples) |

Per the task's explicit warning, this audit found **no field anywhere** that would justify inferring "Order employee = who sold every item" or "Payment employee = who served the table" — these remain single, order/payment-level references only.

---

## C. Roles

| Field | Class | Coverage | Notes |
|---|---|---|---|
| `id`, `href`, `merchant` | A | 7/7 | — |
| `name` | A (business label, not PII) | 7/7 | Real values: `Team Leader`, `Server`, `Host`, `BOH`, `Employee`, `Manager`, `Admin` |
| `systemRole` | A | 7/7 | `MANAGER` (2 roles: Team Leader, Manager), `EMPLOYEE` (4 roles: Server, Host, BOH, Employee), `ADMIN` (1 role: Admin) |
| permissions/capabilities | — | 0/7 | **UNAVAILABLE** — no such field is exposed on Role |

**Employee ↔ Role — CORRECTED by TASK_CLOVER_004 (was: F, INCONCLUSIVE for specific role; now: A, CONFIRMED for both tier and specific named Role).** The plain, un-expanded `employee.role` field (used by every prior task's bulk `employees.json` export) is indeed only the literal `systemRole` string (`EMPLOYEE`/`MANAGER`/`ADMIN`), not a foreign key — this part of the original finding stands. **However, TASK_CLOVER_004 found that the bulk export/plain detail call was never the right request to test:** `GET /v3/merchants/{id}/employees/{employeeId}?expand=role` (or `expand=roles`, both accepted) returns an additional `roles.elements[]` array containing the **specific named Role** the employee is assigned (`id`, `name`, `systemRole`) — e.g. `{id: ..., name: "Server", systemRole: "EMPLOYEE"}`. The same relationship is independently confirmed from the Role side: `GET /v3/merchants/{id}/roles/{roleId}?expand=employees` returns an `employeesRef.elements[]` array of the Role's member Employees, and the membership is symmetric (an employee found via `roles?expand=employees` also has that same Role in their own `employees?expand=role` response). **Cardinality confirmed empirically: exactly 1 named Role per current Employee, for all 24/24 employees** (Server ×8, Host ×5, Admin ×4, BOH ×4, Employee ×1, Manager ×1, Team Leader ×1) — the resolved Role's own `systemRole` matches `employee.role` (the tier) in all 24/24 cases, a strong internal consistency check. **This is a current-snapshot-only relationship** — the same `?expand=role` call against a historical Employee id no longer in the current `/employees` collection returns 404, matching Employee's own current-snapshot-only behavior (TASK_CLOVER_003's stub-employee finding). Do not infer Restaurant-domain role semantics (e.g. "Server → FOH Area") from this field alone — that remains a separate RF-One classification decision, not inherited from the Clover Role name. Full investigation: `07 Tasks/Reports/TASK_CLOVER_004_REPORT.md`.

---

## D. Shifts / Clock

| Field | Class | Coverage (missing key / present-null / present-value, not conflated) | Notes |
|---|---|---|---|
| `id`, `employee`, `href` | A | 4,368/4,368 (100%) | — |
| `inTime` | A | 4,325/4,368 (~99%) | epoch ms |
| `outTime` | A | 4,325/4,368 (~99%) | epoch ms; the ~1% gap is an open (not currently open) shift, not investigated further here |
| `overrideInEmployee` / `overrideInTime` | A | 206/4,368 (4.7%) | manager-entered correction |
| `overrideOutEmployee` / `overrideOutTime` | A | 175/4,368 (4.0%) | manager-entered correction |
| `serverBanking` | A | key **missing** on 4,310/4,368 (98.7%); key **present** with `true` on 45 (1.0%); key **present** with `false` on 13 (0.3%); **never present-and-null** | meaning unresolved — **F** |

- **Elapsed Hours** (B, DERIVABLE) — `(effective clock-out − effective clock-in) / 3600`, using override time when present else raw time; confirmed by TASK_CLOVER_002 at 100% match against the reference Clock export.
- **Employee Totals** (B, DERIVABLE) — sum of an employee's Elapsed Hours in a window; confirmed 100% match.
- **Override frequency** (B, DERIVABLE aggregate) — 4.7% in / 4.0% out is a computed rate, not itself a source field; do not store as if it were atomic.
- **`serverBanking`** meaning remains genuinely unresolved (F) — too rare (1.3% of records carry the key at all) to infer from data alone, and no Clover documentation was consulted in this pass.

---

## E. Orders

Full field census (bulk `orders?expand=lineItems,payments,discounts,customer`, 3,521 records):

| Field | Class | Coverage | Type | Notes |
|---|---|---|---|---|
| `id`, `href` | A | 100% | string | — |
| `clientCreatedTime`, `createdTime`, `modifiedTime` | A | 100% each | int (epoch ms) | see Timestamp Inventory |
| `currency` | A | 100% | string | always `"USD"` |
| `employee` | A | 100% | ref | see § B |
| `device` | A | 100% | ref | — |
| `orderType` | A | 100% | ref | see § S |
| `state` | A | 100% | string | always `"locked"` in this export (no open/in-progress orders captured) |
| `paymentState` | A | 100% | string | always `"PAID"` — **no other value observed anywhere in the full 3,521-order history** (no `OPEN`, no `REFUNDED`; see § M/R — refunds exist but do not change `paymentState`) |
| `payType` | A | 99.97% (1 order has `null`) | string | `FULL` 3,345 (95.0%), `SPLIT_CUSTOM` 172 (4.9%), `SPLIT_GUEST` 3 (0.1%), missing/`null` 1 |
| `total` | A | 100% | int (cents) | — |
| `taxRemoved` | A | 100% | bool | always `False` observed |
| `isVat` | A | 100% | bool | always `False` observed — VAT machinery configured but unused for this (US) merchant |
| `manualTransaction`, `groupLineItems`, `testMode` | A | 100% each | bool | always `False` observed for all three |
| `title` | A | 92.8% (3,268/3,521) | string | **see § F — strong evidence this encodes a table number + seating zone as free text, not a structured field** |
| `note` | A | 0.9% (33/3,521) | string | free-text order note; distinct from `lineItem.note` (§ H) |
| `customers` | A | 82.3% (2,897/3,521) | nested, **0 or 1 element, never more** | id-only reference (`{href, id}`), no inline PII |
| `payments` (nested) | A | 100% present as key; element count 1 (3,338 orders), 2 (174), 3 (7), 4 (2) | nested | **excludes FAILED payment attempts** — see reconciliation below |
| `discounts` (nested) | A | 2.1% (74/3,521) non-empty | nested | see § L — catalog-referenced AND ad hoc/manual shapes both observed |
| `lineItems` (nested) | A | 100% present; 23,342 total elements across all orders | nested | see § H |

**Order.payments vs top-level Payments — exact reconciliation (CONFIRMED):** nested `order.payments` sums to 3,715 across all orders (3,338×1 + 174×2 + 7×3 + 2×4); the top-level `payments.json` collection has 3,751 records. The difference (36) is **exactly** the number of `result: "FAIL"` payments (§ O) — **Order.payments (nested) only includes non-failed payment attempts; failed attempts exist only in the top-level Payments collection.** This is a precise, previously undocumented completeness fact.

**Order usage by type (observed behavior, not just configuration):** `Table` 3,295 (93.6%), `To Go on Site (Asap)` 202 (5.7%), `Employee` 21 (0.6%), `Sample` 3 (0.1%). None of the other 6 configured order types (`Online - Doordash`, `Online - On Site`, `Delivery`, `Curbside Pickup`, `In-store Pickup`, `Dine In`) appear in any of the 3,521 orders' actual `orderType` reference — configured but currently unused (or arriving through a channel not captured by this token).

---

## F. Table / Dining information

Empirical determination, per the task's required YES/NO/INCONCLUSIVE format, with exact source evidence:

| Concept | Answer | Evidence |
|---|---|---|
| Physical table identity (structured field/entity) | **NO** | No dedicated `Table` resource/endpoint exists in this Clover integration; nothing in `orchestrator.py`'s investigated collection set or this task's supplementary calls surfaced one |
| Table number/name | **YES — but only as free text, not a structured field** | `order.title` (92.8% coverage) — see structural finding below |
| Table grouping | **NO** | No evidence found |
| Section / area (inside/outside) | **YES — free text within `order.title`** | See structural finding below |
| Seat capacity | **NO** | No evidence found |
| Inside / outside | **YES — confirmed** | See structural finding below |
| Floor / layout | **NO** | No evidence found |
| Table assignment on Order | **YES — only as free text, not a relationship** | `order.title`, not a foreign key |
| Dining session / seating session | **NO** | No dedicated entity found; an Order is the closest available unit |
| Merged tables | **YES — free-text evidence only** | `binName` values matching `"Guest N (From Table #X)"` — 116/23,342 line items (0.5%) — see § G |
| Fictitious / To Go table behavior | **YES — at the Order Type level, not per-table** | `order_types.json`'s default order type is literally named `"Table"` (`isDefault: true`, `systemOrderTypeId: "DINE-IN-TYPE"`); dine-in vs. `"To Go on Site (Asap)"`/`"Curbside Pickup"`/`"Delivery"`/`"In-store Pickup"` is distinguished at Order Type granularity, not per physical table |

### `order.title` structural finding (this task's primary new discovery for this section)

`order.title` is present on 92.8% of orders (3,268/3,521). Structural analysis (character-class, vocabulary-substring, and cardinality checks — **no raw title values were printed to any tool output or document to avoid any PII risk**, only structural counts) found:

- only **31 distinct values**, each repeated hundreds of times (no value occurs only once) — inconsistent with a customer name field, consistent with a small fixed set of physical labels;
- 97.4% of non-empty titles (3,183/3,268) contain the substring `"inside"` or `"outside"` (2,309 "inside" + 874 "outside", which sum exactly to 3,183 — every "side"-containing title is one or the other, no third variant);
- length is uniformly 11–17 characters; alpha-character count clusters at exactly 6 (matching "Inside") or 7 (matching "Outside"), meaning the rest of the title's characters are digits/punctuation only;
- **one real example was directly confirmed** via the refund records obtained in this task's supplementary `/refunds` call (§ R): `order.title = "#4 - Inside"` on one of the two refunded orders — this is a business/operational label (a table number + seating zone), not personal data, and is reproduced here because it directly resolves this section's question.

**Conclusion:** `order.title` follows the pattern **`"#<table number> - <zone>"`** where zone ∈ {`Inside`, `Outside`, at least one other unconfirmed 8-alpha-character variant, structurally consistent with `"Curbside"`}. This is a **source artifact / workaround** (D) exactly like `binName` — free text carrying table/zone information Clover has no structured field for — not a proper Clover relationship. Per the task's instruction, this is documented as a source artifact, not promoted to a relationship.

---

## G. Guest information

### Declared guest count — re-measured over the full dataset

Current merchant workaround: `"# Guest".unitQty / 1000`.

**Corrected coverage measurement (this task):** **3,107 / 3,521 orders (88.2%)** contain at least one `"# Guest"`-named line item.

**Correction to `CLOVER_RESTAURANT_DATA_MAPPING.md`:** that document's existing figure, "3,153 / 3,521 = 89.5%", is the **count of `"# Guest"` line items summed across all orders**, not the count of orders containing one — 42 orders (1.2%) contain **more than one** `"# Guest"` line item (e.g. the guest count was corrected/re-entered), which inflates the item-count numerator (3,153) above the order-count numerator (3,107) against the same 3,521-order denominator. Both counts are confirmed correct for what they each measure; the earlier document mixed the two. **`CLOVER_RESTAURANT_DATA_MAPPING.md` is corrected accordingly by this task** (see its updated § 5).

### Item → Guest assignment (`binName`) — full-dataset audit

| Metric | Value |
|---|---|
| `binName` key present | 22,915 / 23,342 line items (98.2%) |
| `binName` = empty string | 7,586 / 23,342 (32.5%) |
| `binName` non-empty | 15,329 / 23,342 (65.7%) |
| Non-empty value matches `"Guest N"` exactly | 15,213 / 15,329 (99.2% of non-empty) |
| Non-empty value matches `"Guest N (From Table #X)"` (merged-table label) | 116 / 15,329 (0.76% of non-empty) |
| Non-empty value NOT matching either pattern (malformed/unexpected) | **0** |
| Guest numbers observed | 1 through 12; heavily skewed to 1–4 (guest 1: 6,743; guest 2: 5,519; guest 3: 1,760; guest 4: 837; 5 and above: 471 combined) |

**Every single non-empty `binName` value for this merchant follows the expected pattern — zero malformed or unexpected labels were found.** This is a clean, well-disciplined source field for this merchant, once present.

### Declared vs. derived guest-count reconciliation (re-computed over the full dataset, not previously quantified)

| Category | Orders | % of 3,521 |
|---|---|---|
| Both declared and derived present | 2,916 | 82.8% |
| — of which: match exactly | 2,160 | 61.3% |
| — declared > derived (possible incomplete item-to-guest assignment) | 488 | 13.9% |
| — declared < derived (derived exceeds declared) | 268 | 7.6% |
| Declared present, no `binName` "Guest N" found at all | 191 | 5.4% |
| Derived present, declared missing (no `"# Guest"` item) | 68 | 1.9% |
| Neither present | 346 | 9.8% |

These discrepancies are preserved as operational/data-quality evidence, not silently corrected — consistent with `CLOVER_RESTAURANT_DATA_MAPPING.md` § 10's existing principle, now with a real distribution behind it. Per the same document, missing guest data is understood by the Product Owner primarily as order-entry discipline, not an API limitation — see § Q (data-quality signals) below, which does not assign blame to any individual.

---

## H. Order Items

Two evidence sources: the **bulk** export (`orders?expand=lineItems`, all 23,342 line items across 3,521 orders) and the **dedicated** endpoint (`orders/{id}/line_items?expand=modifications`, 1,838 line items across the 271-order TASK_CLOVER_002 window). Both are censused below; where they differ, the dedicated endpoint is authoritative for fields the bulk export cannot carry.

| Field | Class | Bulk coverage (23,342) | Dedicated coverage (1,838) | Notes |
|---|---|---|---|---|
| `id` | A | 100% | 100% | line item ID |
| `orderRef` | A | 100% | 100% | order relationship |
| `item` | A | 98.1% | 98.4% | item relationship — **absent** on fee/technical lines (e.g. the Gratuity fee line) |
| `name` | A | 100% | 100% | — |
| `price` | A | 100% | 100% | cents; **see § L for the ~half-priced residual TASK_CLOVER_002 could not explain** |
| `unitQty` | A | 14.8% (3,463) | 13.7% (251) | ÷1000; **not just the Guest item** — 308 bulk revenue line items also carry it (see below) |
| `unitName` | A | 13.5% | 12.7% | e.g. `"Nbr"` for the Guest item |
| `unitQtyDecimalDigits` | A | 13.5% | 12.7% | new field, not previously documented |
| `binName` | A | 98.2% | 98.4% | see § G |
| `itemCode` | A | 98.1% | 98.4% | new field, not previously documented — catalog item code echoed onto the line |
| `isRevenue` | A | 100% | 100% | `false` on 3,706/23,342 (15.9%) — see below |
| `isOrderFee` | A | 100% | 100% | `true` on 427/23,342 (1.8%) — see § N |
| `printed` | A | 100% | 100% | `false` on 235/23,342 (1.0%) |
| `refunded` | A | 100% | 100% | **`true` on 0/23,342 — zero, across the entire history** — see § R |
| `exchanged` | A | 100% | 100% | **`true` on 0/23,342 — zero** — see § R |
| `modifications` | A | **0% (never present in the bulk export)** | 17.1% (315/1,838) | Confirms TASK_CLOVER_002: the bulk export structurally cannot carry modifier data at all |
| `note` | A | 4.1% (966) | 4.2% (77) | line-item-level free text, distinct from `order.note` |
| `orderFee` / `percentage` | A | 1.8% each (427) | 1.6% each (29) | present only together, only on fee lines — see § N |
| `alternateName` | A | 88.2% | 88.0% | catalog alternate name echoed onto the line |
| `createdTime` | A | 100% | 100% | **the line item's own timestamp — see finding below** |
| `orderClientCreatedTime` | A | 100% | 100% | copy of the parent order's `clientCreatedTime`, for convenience joins |
| `excludeCashDiscount`, `isAgeRestricted` | A | 98.1% each | 98.4% each | catalog attributes echoed onto the line |
| `lineItemInfo` | A | 3.5% (809) | 2.0% (36) | new field — structure is `{"allergens": {"elements": [...]}}`; **observed empty (`elements: []`) in every sampled case** — an allergen-tracking mechanism exists but is unpopulated for this merchant |
| employee on line item | — | 0% | 0% | **UNAVAILABLE**, confirmed absent in both sources — see § B |
| tax detail on line item | — | 0% | 0% | **UNAVAILABLE as a direct field** — must be derived via `item.defaultTaxRates` / per-item `taxRates` (§ M) |
| discount on line item | — | 0% | 0% | **UNAVAILABLE as a direct field** — confirmed no `discounts` key exists on any line item, bulk or dedicated |

**Atomicity — Clover does NOT always produce one record per atomic sold unit (B, corrects an assumption):** `unitQty` appears on 308 **revenue** line items in the bulk export (not only the technical `"# Guest"` item), with values including 500 (half, 218 occurrences), 333/334 (third, 54), 250 (quarter, 24), 167/166 (sixth, 12) of 1000. Real item names carrying these fractional quantities include (business/menu names, not PII) `S- Focaccia`, `Tiramisu`, `Bruschetta Caprese`, `Prosciutto & Cantaloupe`, `Caprese Buffalo Mozzarella`, `Still Water 500ml - Glass Bottle`, and others. **A single line item can therefore represent a fractional or non-1.0 quantity of a sold unit; the raw `price` field on that line already reflects that quantity's total revenue, not a fixed per-unit price.** Any future ingestion must treat quantity as a real dimension, not assume every line item = exactly one physical unit.

**Line item's own `createdTime` is genuinely distinct from the order's (B/A, new finding):** 22,272 / 23,342 (95.4%) of line items have a `createdTime` that differs from their parent order's `createdTime` (diff range: −1,000 ms to +11,573,000 ms, i.e. up to ~3.2 hours later). **The Clover dashboard Line Items export uses the order's timestamp for display (confirmed by TASK_CLOVER_002), not the item's own — meaning the item's true "when this was rung in" timestamp is currently discarded in the dashboard-equivalent reconstruction.** This is a genuine, currently-unused atomic fact with real service-timing value (e.g. detecting when a table ordered a second round).

**Non-revenue, non-fee ("technical") line items observed (business/technical names, not PII):** `"# Guest"` (3,153 occurrences — the guest-count workaround, § G), `"Side-Broccoli and Mushroom"` (101), and four `"E-"`-prefixed items (`E-Pizza Via Napoli`, `E-Chicken Breast 4oz with Side Salad`, `E-Dry Pasta Napoli Based Sauce`, `E-Dry Pasta Oil or Butter Based`, `E-Tomato Bruschetta` — 10, 10, 2, 2, 1 occurrences). The `"E-"` prefix and the presence of an `"Employees Meals"` Category/Tag (§ I/J) strongly suggest these are **staff-meal technical items** — a plausible, evidence-grounded interpretation (C), not confirmed as a Clover-documented fact.

---

## I. Items / Inventory

| Field | Class | Coverage | Notes |
|---|---|---|---|
| `id`, `name` | A | 100% | name is a menu/business label, not PII |
| `alternateName`, `onlineName` | A | 86.7% / 100% | — |
| `price` | A | 100% | cents |
| `priceWithoutVat` | A | 28.8% | VAT-style field, largely unused (see § M) |
| `cost` | A | 96.1% | cents |
| `sku`, `code` | A | 98.1% / 99.8% | for this merchant's catalog, every reference value happened to be blank when validated against dashboard exports (TASK_CLOVER_002) — the field exists and is populated structurally, but its actual content was never exercised against a non-blank reference |
| `priceType` | A | 100% | `FIXED` 521 (97.9%), `VARIABLE` 6 (1.1%), `PER_UNIT` 5 (0.9%) — **new finding**: a small number of items have open/variable or per-unit pricing, not a fixed catalog price |
| `type` | A | 100% | always `REGULAR` — no other Item "type" variant observed |
| `defaultTaxRates` | A | 100% | bool — see § M |
| `stockCount` | A | 96.1% | see § U |
| `available`, `hidden`, `enabledOnline`, `deleted`, `autoManage`, `isAgeRestricted`, `isRevenue` | A | 100% each | booleans |
| `description` | A | 28.8% | — |
| `modifiedTime` | A | 100% | see Timestamp Inventory |
| `categories` (via this task's supplementary `expand`) | A | see § J | — |
| `tags` (via this task's supplementary `expand`) | A | see § J | — |
| `modifierGroups` (via this task's supplementary `expand`) | A | see § K | — |

**`Clover Item ≠ current menu item` — confirmed with real examples:** the catalog contains ordinary food/beverage items, plus technical items (`# Guest`), plus what appear to be staff-meal items (`E-*`, `Side-Broccoli and Mushroom`), plus the synthetic fee item (`Gratuity`, § N). RF-One classification of an Item's business nature is a separate concern from Clover's raw catalog representation, per `CLOVER_RESTAURANT_DATA_MAPPING.md` § 13 (unchanged, reconfirmed).

---

## J. Categories

| Field | Class | Coverage |
|---|---|---|
| `id`, `name`, `sortOrder`, `deleted` | A | 21/21 (100%) |

**Item ↔ Category cardinality (confirmed via this task's supplementary `expand` call, real merchant data):**

| Categories per item | Item count |
|---|---|
| 0 | 32 (6.0%) |
| 1 | 498 (93.6%) |
| 2 | 1 (0.2%) |
| 15 | 1 (0.2%) |

An item may belong to **zero, one, or multiple** categories — confirmed, not assumed. The 15-category item was verified to have 15 genuinely **distinct** category IDs (not a duplication artifact) — spanning nearly the entire 21-category catalog. This is recorded as a data-quality observation (§ Q), not corrected or explained away.

---

## K. Modifiers

**Modifier Group** (19 records): `id`, `name`, `showByDefault` (100%), `modifierIds` (comma-separated **string**, not an array, 90%), `modifiers` (nested expand, 100%), `deleted` (100%).

**Modifier** (214 total, nested under groups): `id`, `name`, `available`, `price` (cents), `modifiedTime`, `modifierGroup` (back-reference), `deleted` — all 100% of 214; `alternateName` only 2/214 (0.9%).

**Item ↔ Modifier Group cardinality (confirmed via this task's supplementary `expand` call):**

| Modifier groups per item | Item count |
|---|---|
| 0 | 318 (59.8%) |
| 1 | 99 (18.6%) |
| 2 | 41 (7.7%) |
| 3 | 58 (10.9%) |
| 4 | 16 (3.0%) |

**Order Item ↔ selected Modifier** — the `modifications` array (dedicated endpoint only, § H): each element carries `id`, `lineItemRef` (back-reference), `name`, `amount` (cents), `modifier` (catalog reference). Confirmed structure (real, non-PII example): `{name: "First", amount: 0, modifier: {id: ...}}` — matching the previously-known "When Serve" instruction-style modifier group.

**Modifier semantic nature remains unresolved (F), as previously known** — no field distinguishes a true product variant (e.g. an "Extra mozzarella" topping, which carries a non-zero `price`) from a service/production instruction (e.g. "First"/"Wait for server", which carries `price`/`amount` = 0 in every observed case). A **derivable (B)** heuristic — non-zero catalog `price` suggests a true add-on; zero suggests an instruction — was **not** confirmed exhaustively across all 214 modifiers in this pass and is offered only as a candidate, not a conclusion.

---

## L. Discounts

**Catalog** (`discounts.json`, 5 records): `id`, `name`, `percentage`, `type` — all `type: "DEFAULT"` (i.e. the catalog only defines percentage-type discounts). Real names (business labels): `Customer Issues` (30%), `Neighborhood Employee` (10%), `Friends & Family` (25%), `Employee On Clock` (50%), `Wine Bottle To Go` (40%).

**Order-level applied discounts** (`order.discounts`, 74/3,521 orders, 2.1%) — **two distinct shapes found, confirmed by direct inspection of the full history (a genuinely new finding beyond TASK_CLOVER_002's validated window):**

| Shape | Count | Fields | Example (business label, not PII) |
|---|---|---|---|
| Catalog-referenced | 64 (86.5% of applied discounts) | `id`, `orderRef`, `discount` (catalog id ref), `name`, `percentage`, `discType: "DEFAULT"` | `Employee On Clock` ×36, `Friends & Family` ×15, `Neighborhood Employee` ×10, `Wine Bottle To Go` ×3 |
| **Ad hoc / manual, percentage** | 9 (12.2%) | `id`, `orderRef`, `name`, `percentage` — **no `discount` catalog reference, no `discType` key at all** | `100% Off` ×6, `20% Off` ×2, `30% Off` ×1 |
| **Ad hoc / manual, fixed amount** | **1 (1.4%) — NEW FINDING** | `id`, `orderRef`, `name`, `amount` (cents, **negative**) | `$50.00 Off` → `amount: -5000` |

**This is a material correction to the current reconstruction logic:** TASK_CLOVER_002's `export_orders.py` Discount derivation (`CLOVER_EXPORT_MAPPING.md` § 2) sums `order.discounts[].percentage` only — it has no handling for an `amount`-shaped discount element at all, because the validated 2026-08-17→2026-08-23 window happened to contain only percentage-type discounts. **This audit found one confirmed real `amount`-type discount in the fuller history that the current derivation would silently under-count (treat as if `percentage` were absent/zero).** This is flagged as a required fix before any Discount figure is treated as canonical — not fixed in this task (out of scope; this task does not implement KPI/database logic), but it must not be missed by whoever picks up ingestion next.

**Line-item-level discount:** confirmed **UNAVAILABLE** — no `discounts` key exists on any line item across the full 23,342-item bulk census or the 1,838-item dedicated census. The dashboard's "Order Discount Proportion" per line item (`CLOVER_EXPORT_MAPPING.md` § 3) is a **derived (B)** apportionment, not a source field — reconfirmed.

---

## M. Taxes

| Source | Field | Class | Coverage | Notes |
|---|---|---|---|---|
| `tax_rates.json` (catalog) | `id`, `name`, `rate`, `isDefault`, `modifiedTime` | A | 4/4 | Real names: `Tax` (6.5%, default), `Liquor Tax` (6.97%), `Gratuity` (0%), `NO_TAX_APPLIED` (0%) — **note the `Gratuity` and `NO_TAX_APPLIED` rate names are themselves 0%-rate "tax" catalog entries, used to bucket non-taxed or fee-adjacent lines, not to apply real tax** |
| `item.defaultTaxRates` | bool | A | 100% | whether the item uses the merchant default rate |
| per-item `taxRates` override | via supplementary `GET /items/{id}?expand=taxRates` (13 cached calls, TASK_CLOVER_002) | A | 13/13 fetched, bounded sample | **Confirmed non-obvious rule: an empty per-item `taxRates` list means 0% (untaxed), it does NOT fall back to the merchant default** — this was the root cause of a real reconciliation bug fixed in TASK_CLOVER_002, reconfirmed here |
| `order.isVat` | bool | A | 100% | always `False` observed |
| `order.taxRemoved` | bool | A | 100% | always `False` observed |
| `item.priceWithoutVat` | int (cents) | A | 28.8% | VAT-style field present on a minority of the catalog |
| `payment.taxAmount` | int (cents) | A | 100% | **the atomic settlement-level tax fact** |
| Order-level tax | — | — | **not a direct Order field** | `sum(order.payments[].taxAmount)` — DERIVED (B), confirmed 100% match by TASK_CLOVER_002 |
| Line-item tax detail | — | — | **not a direct field** | DERIVED (B) as `Item Total × applicable rate`, where the applicable rate itself requires the `defaultTaxRates`/per-item-override join above |

**Ownership is not decided by Clover's placement:** tax values appear on Payment (settlement total), are derivable at Order level (sum of payments), and are derivable at line-item level (via the Item/rate join) — consistent with `CLOVER_RESTAURANT_DATA_MAPPING.md` § 19's existing principle that canonical ownership (`Order → Tax`) is an RF-One decision, not inherited from where Clover happens to expose a number.

---

## N. Fees / Service Charge

Two **distinct, unrelated** fee mechanisms were confirmed — do not conflate them:

1. **Order-instance Service Charge/Gratuity** — a synthetic line item (`name: "Gratuity"`, `note: "Service Charge"`, `isOrderFee: true`, carrying its own `percentage` and an `orderFee` catalog reference). **Full-history count: 427/23,342 line items (1.8%)**, appearing on an estimated ~12% of orders (consistent with, and now supersedes with a full-history figure, TASK_CLOVER_002's 29/271-order-window ≈10.7% sample). Reconfirmed: **absent from the Payments API/export entirely** — 0 fields on the Payment object could carry it.
2. **Order-Type-level `fee`** — a **separate, configuration-level** numeric field on `order_types.json` (60% of the 10 order types carry a non-null `fee`, along with `minOrderAmount`/`maxOrderAmount`/`avgOrderTime`). This is order-type business-rule configuration (e.g. a delivery/online-order fee), not the per-order Gratuity line item, and was never observed to actually populate a real Order in this merchant's history (no order was found where this configured fee produced a distinct charge line — not investigated further, out of scope for this pass).

Do not infer fee semantics from an Item's name alone unless independently supported — the technical items in § H (`E-*`, `Side-Broccoli...`) are **not** fees; they are `isRevenue: false` non-fee items.

---

## O. Payments

Full census (3,751 records) — largely reconfirms TASK_CLOVER_001/002, with new findings marked:

| Field | Class | Coverage | Notes |
|---|---|---|---|
| `id`, `href` | A | 100% | — |
| `amount` | A | 100% | cents |
| `taxAmount` | A | 100% | cents |
| `tipAmount` | A | 88.7% (3,326/3,751) | **missing key, not zero, on the remaining 11.3%** — reconfirmed |
| `cashTendered` | A | 8.6% (321) | cents, cash payments only |
| `cashbackAmount` | A | 99.6% | cents |
| `employee`, `order`, `device` | A | 100% each | refs |
| `tender` | A | 100% | nested object — see § Q |
| `clientCreatedTime`, `createdTime`, `modifiedTime` | A | 100% each | epoch ms |
| `offline` | A | 91.1% | bool |
| `result` | A | 100% | **`SUCCESS` 3,715 (99.04%), `FAIL` 36 (0.96%) — NEW: the first confirmed non-success example found in this audit; no `REFUNDED`/`VOIDED` result value was ever observed** (refunds live entirely outside this field — § R) |
| refund-shaped field on Payment | — | 0/3,751 | **UNAVAILABLE** — confirmed no key containing "refund" exists anywhere on the Payment object |
| `customer`-shaped field on Payment | — | 0/3,751 | **UNAVAILABLE** — Payment never references a Customer directly; only reachable transitively via Payment → Order → Customer |

---

## P. Tips

`payment.tipAmount` reconfirmed as the atomic source fact (88.7% present, cents, minor units). Distinguishing missing-key from present-zero was preserved throughout (no conflation). Order-level `Tip` remains a **derived (B)** sum with the opposite missing-value default (0.00) from Payments — both behaviors are Clover's own dashboard behavior, reconfirmed by TASK_CLOVER_002, not re-litigated here. **No payroll/tip-allocation rule is implemented or proposed by this task**, per its restrictions.

---

## Q. Tenders

| Field | Class | Coverage | Notes |
|---|---|---|---|
| `id`, `href`, `label` | A | 100% | 5 distinct labels observed: `Credit Card` (2,503), `Debit Card` (913), `Cash` (321), `External Gift Card` (13), `Online Payment` (1) |
| `labelKey` | A | 100% | i18n key |
| `editable`, `enabled`, `visible` | A | 100% | booleans |
| `opensCashDrawer` | A | 100% | **NEW finding, corrects an initial hypothesis: `opensCashDrawer` is `False` for every observed tender, including `Cash`** — it does **not** function as a structural cash/card indicator for this merchant's configuration |
| `supportsCashDiscount` | A | 100% | present, not cross-validated against real cash-discount behavior in this pass |

**Payment method must currently be inferred from `tender.label` text** — no reliable structural boolean was found to substitute for it, correcting this task's own initial hypothesis after checking real data (`opensCashDrawer` looked promising but is uniformly `False`). This is recorded as **F, INCONCLUSIVE** for "does Clover supply a non-text structural type" — the label itself remains the only practical signal.

---

## R. Refunds / voids / exchanges

TASK_CLOVER_002 could not validate this area (its window had zero examples). **This task found real evidence** via a bounded supplementary `GET /v3/merchants/{id}/refunds?limit=100` (§ New supplementary GET calls): **2 confirmed refund records**, full structure:

`id`, `orderRef` (fully-expanded nested Order object), `device`, `amount`, `taxAmount`, `tipAmount`, `createdTime`, `clientCreatedTime`, `payment` (fully-expanded nested Payment object), `employee` (id ref — the employee who **processed the refund**, confirmed different from the order/payment employee in both records), `voided` (bool), `status` (string).

Both confirmed examples:

| | Refund 1 | Refund 2 |
|---|---|---|
| `amount` | 3,728 (= payment.amount exactly — full refund) | 3,834 (= payment.amount exactly — full refund) |
| `taxAmount` | 228 (= payment.taxAmount exactly) | 234 (= payment.taxAmount exactly) |
| `tipAmount` | 0 | 0 |
| `voided` | `false` | `false` |
| `status` | `SUCCESS` | `SUCCESS` |

**Critical, non-obvious finding: neither refund is reflected anywhere else in the data.** Both referenced orders were cross-checked directly against `orders.json`/`payments.json`: `order.paymentState` remains `"PAID"`, `payment.result` remains `"SUCCESS"`, and **every line item on both orders has `refunded: false`.** Confirmed by exact ID cross-reference, not inferred. **Refund evidence exists exclusively in the dedicated `/refunds` resource — it does not propagate to Order, Payment, or Line Item representations for this merchant/API version.** This is classified as a **SOURCE LIMITATION** (§ Q data-quality signals), not a workflow issue.

| Concept | Answer |
|---|---|
| Refund | **YES — CONFIRMED**, 2 real examples, full field structure documented above |
| Manual refund | Both confirmed examples are full-amount refunds; no partial-refund example was found to confirm that shape separately — **INCONCLUSIVE** for partial refunds |
| Void | **INCONCLUSIVE** — `voided: false` on both known refunds; no `voided: true` example exists anywhere in the currently accessible data |
| Refunded line item | **NO evidence** — `lineItem.refunded` is `false` on all 23,342 line items in the full history, including the line items belonging to the 2 refunded orders |
| Exchanged line item | **NO evidence** — `lineItem.exchanged` is `false` on all 23,342 line items |
| Payment refund | **YES — CONFIRMED** via the `refund.payment` nested reference (same 2 examples) |
| Order state effects | **NO effect observed** — `order.paymentState`/`order.state` are unchanged by a refund for these 2 examples |

Only 100 records were requested (`limit=100`) and exactly 2 were returned with no further pages — this appears to be the complete refund history currently visible to this token, not a truncated sample. No refund/void was fabricated or guessed; both examples are drawn from a real API response.

---

## S. Order Types

Full census (10 records) — configuration vs. observed usage, kept distinct:

| `label` | `isDefault` | `isHidden` | `taxable` | `fee`/`minOrderAmount`/`maxOrderAmount`/`avgOrderTime` | Actually used? |
|---|---|---|---|---|---|
| `Table` | **true** | false | true | 0/0/0/0 | **YES — 3,295/3,521 orders (93.6%)** |
| `To Go on Site (Asap)` | false | false | true | 0/0/0/0 | **YES — 202/3,521 (5.7%)** |
| `Employee` | false | false | true | 0/0/0/0 | **YES — 21/3,521 (0.6%)** |
| `Sample` | false | false | true | 0/0/0/0 | **YES — 3/3,521 (0.1%)** |
| `Online - Doordash (=40')` | false | false | true | 0/0/0/0 | NO — configured, not used in this history |
| `Online - On Site (<40')` | false | false | true | 0/0/0/0 | NO |
| `Delivery` | false | **true (hidden)** | true | `null`/`null`/`null`/`null` | NO |
| `Curbside Pickup` | false | **true (hidden)** | true | `null`/`null`/`null`/`null` | NO |
| `In-store Pickup` | false | **true (hidden)** | true | `null`/`null`/`null`/`null` | NO |
| `Dine In` | false | **true (hidden)** | true | `null`/`null`/`null`/`null` | NO |

The default/most-used order type is literally named `"Table"` — the strongest available signal that this merchant primarily operates dine-in service through a single generic "Table" order type rather than per-table order types (consistent with § F's finding that individual table identity lives in free-text `order.title`, not in Order Type).

---

## T. Tags

| Field | Class | Coverage |
|---|---|---|
| `id`, `name`, `showInReporting` | A | 20/20 (100%), `showInReporting` always `false` observed |

**Item ↔ Tag cardinality (confirmed via supplementary `expand`):** 0 tags (41/532, 7.7%), 1 tag (490/532, 92.1%), 2 tags (1/532, 0.2%).

**Data-quality observation:** the 20 Tag names substantially **duplicate** the 21 Category names (e.g. both have `Sides`/`Sides & Add`, `Beer`, `Pasta`, `Wine Red - Bottle`, `Employees Meals`, etc.). For this merchant, Tags do not appear to encode information genuinely orthogonal to Categories — classified as a **BUSINESS CONFIGURATION** observation (§ Q), not a Clover limitation.

---

## U. Item Stock

| Field | Class | Coverage |
|---|---|---|
| `item` (ref), `stockCount`, `quantity`, `modifiedTime` | A | 511/532 items (96.1%) have a stock record |

**Critical finding: `quantity` and `stockCount` are `0` on 511/511 (100%) of records — every single Item Stock record currently shows zero stock.** This is a snapshot-only source (one current value per item, `modifiedTime` spans 2025-07-22→2026-02-14 per the original discovery report — no movement/transaction history is exposed), and for this merchant it currently carries **no usable inventory signal at all** (not "low value," literally always zero). **Not sufficient for historical inventory analysis; not currently useful even for current-state analysis, given the universal zero.** No inventory movement is inferred, per the task's restriction.

---

## V. Customers

Audited minimally, per the task's instruction (deferred, not currently needed for Restaurant Sales Analytics):

| Field | Class | Coverage |
|---|---|---|
| `id`, `href` | A | 101,597/101,597 (100%) |
| `firstName`, `lastName` | A (PII) | 100% each | withheld |
| `customerSince` | A | 100% | int; sampled 4,998/5,000 distinct values — functions as a per-record variable timestamp (creation-time proxy), **not confirmed to be a meaningful business "customer since" date** — F |
| `marketingAllowed` | A | 100% | bool |
| `metadata` | A (key present) | 100% present as key, but **confirmed empty (`{}`) on every one of a 5,000-record sample** | no loyalty/linkage data populated |

**Relationships:**

| Relationship | Evidence | Status |
|---|---|---|
| Customer → Order | `order.customers`, 0 or 1 element (never more), 82.3% of orders reference one | CONFIRMED |
| Customer → Payment | none — confirmed 0/3,751 payments carry any customer-shaped field | UNAVAILABLE (only reachable transitively via Order) |
| Loyalty/customer linkage | `metadata` object exists but is empty | UNAVAILABLE for this merchant currently |

**Classification: AVAILABLE BUT DEFERRED**, per the task's own instruction — no current RF-One use is needed, and no PII value was ever displayed to reach this conclusion.

---

## Timestamp Inventory

All epoch-millisecond fields, UTC-based (confirmed by TASK_CLOVER_002's `zoneinfo`-based conversion to `America/New_York` for display — the underlying value itself carries no timezone marker).

| Entity | Field | Meaning (if known) | Earliest observed | Latest observed | Coverage | Confidence | Supports |
|---|---|---|---|---|---|---|---|
| Employee | `claimedTime` | account-claim time (unconfirmed) | — | 2026-03-06 | 17% | F, unresolved | — |
| Shift | `inTime`/`outTime` | clock in/out | 2025-07-29 | 2026-08-24 | ~99% | Confirmed | shift timing |
| Shift | `overrideInTime`/`overrideOutTime` | manager correction | — | — | 4.7% / 4.0% | Confirmed | shift timing (corrected) |
| Item | `modifiedTime` | catalog last-modified | 2025-07-22 | 2026-08-15 | 100% | Confirmed | historical catalog changes |
| ItemStock | `modifiedTime` | stock snapshot last-modified | 2025-07-22 | 2026-02-14 | 100% | Confirmed | snapshot only, not a movement log |
| TaxRate | `modifiedTime` | rate last-modified | 2025-07-11 | 2025-07-22 | 100% | Confirmed | historical catalog changes |
| Modifier | `modifiedTime` | modifier last-modified | not separately computed in this pass | — | 100% (214/214) | Confirmed present | historical catalog changes |
| Order | `clientCreatedTime` | client-side creation time | 2026-05-27 | 2026-08-24 | 100% | Confirmed | order timing |
| Order | `createdTime` | server-side creation time | 2026-05-27 | 2026-08-24 | 100% | Confirmed | order timing, sync |
| Order | `modifiedTime` | last modification | — | — | 100% | Confirmed | data synchronization |
| LineItem | `createdTime` | **the item's own timestamp** | — | — | 100% | Confirmed, genuinely distinct from Order in 95.4% of cases | **service timing (currently unused by the dashboard reconstruction — new opportunity)** |
| LineItem | `orderClientCreatedTime` | copy of parent order's `clientCreatedTime` | — | — | 100% | Confirmed | join convenience only |
| Payment | `clientCreatedTime`/`createdTime`/`modifiedTime` | payment timing | 2026-05-27 | 2026-08-24 | 100% each | Confirmed | payment timing, sync |
| Refund | `createdTime`/`clientCreatedTime` | refund timing | 2026-06-03 (1 of 2 examples) | 2026-06-13 (1 of 2 examples) | 2/2 confirmed examples | Confirmed | refund timing (thin evidence base) |
| Customer | `customerSince` | unclear — behaves like a creation-time proxy | — | — | 100% | F, unresolved | — |

**Notable gap, reconfirmed:** Orders/Payments/Shifts history starts **2026-05-27/07-29**, well after menu setup (Items/TaxRates: 2025-07-11/22). Not newly resolved by this task — remains an open question for the Product Owner (see TASK_CLOVER_001 report § N, carried forward, not re-litigated here).

---

## Monetary Field Inventory

All Clover monetary amounts are **integer minor units (cents)** unless otherwise noted. Non-monetary integer/float fields that could be mistaken for currency are explicitly called out and excluded.

| Entity.Field | Minor-unit / decimal | Business meaning | Coverage | Direct / Derived | Reconciliation target |
|---|---|---|---|---|---|
| `Order.total` | minor units | order grand total | 100% | Direct | matches `sum(payments.amount)` (confirmed 100%, TASK_CLOVER_002) |
| `Payment.amount` | minor units | payment settlement amount | 100% | Direct | sums to `Order.total` |
| `Payment.taxAmount` | minor units | tax portion of the payment | 100% | Direct | sums into derived Order Tax Amount |
| `Payment.tipAmount` | minor units | tip portion | 88.7% | Direct | sums into derived Order Tip (with an opposite missing-value default — § P) |
| `Payment.cashTendered` | minor units | cash handed over | 8.6% | Direct | cash payments only |
| `Payment.cashbackAmount` | minor units | cash given back | 99.6% | Direct | — |
| `LineItem.price` | minor units | this line's total revenue at its `unitQty` | 100% | Direct | see § H atomicity finding — not always a "per single unit" price |
| `Modifier.price` (catalog) | minor units | modifier's catalog price | 100% (214/214) | Direct | — |
| `Modification.amount` (applied instance) | minor units | this application's price impact | dedicated-endpoint only (17.1% of line items carry any) | Direct | sums into "Modifiers Revenue" (confirmed, TASK_CLOVER_002) |
| `Discount.percentage` (catalog and ad hoc) | **raw integer percent (e.g. `50` = 50%)** | discount rate | see § L | Direct | **different scaling convention from `TaxRate.rate` below — do not assume a uniform scale across "rate"-like fields** |
| **`Discount.amount` (ad hoc only, NEW)** | minor units, **negative sign** | fixed-amount discount | 1 confirmed example (`-5000` = −$50.00) | Direct | **not currently summed by the existing Order Discount derivation — see § L** |
| `Item.price` / `Item.cost` / `Item.priceWithoutVat` | minor units | catalog price / cost / VAT-exclusive price | 100% / 96.1% / 28.8% | Direct | — |
| `OrderType.fee` / `.minOrderAmount` / `.maxOrderAmount` | minor units (assumed; not independently verified against a real non-zero charge) | order-type-level configured fee | 60% (6/10 order types) | Direct (config) | never observed to produce an actual charge in this history — see § N |
| `Refund.amount` / `.taxAmount` / `.tipAmount` | minor units | refunded amounts | 2/2 confirmed examples | Direct | both examples reconcile exactly to the original `Payment.amount`/`.taxAmount` |
| `TaxRate.rate` | **NOT minor-unit currency — a rate, scaled ÷10,000,000** (e.g. `650000` = 6.5%) | tax rate | 100% (4/4) | Direct | **flagged explicitly: an integer field that is not money — do not classify by type alone** |
| `LineItem.unitQty` | **NOT currency — a quantity, scaled ÷1000** | quantity/fraction of a unit | 14.8% bulk | Direct | **flagged explicitly: another integer field that is not money** |
| `ItemStock.quantity` / `.stockCount` | **NOT currency — inventory counts** | stock level | 96.1% | Direct | **always 0 for this merchant — see § U** |

---

## Data-quality / workflow signals

| Signal | Frequency | Classification | Basis |
|---|---|---|---|
| Missing declared Guest Item (`# Guest`) | 414/3,521 orders (11.8%) | WORKFLOW / ENTRY DISCIPLINE | Consistent with the Product Owner's own prior characterization (`CLOVER_RESTAURANT_DATA_MAPPING.md` § 10), reused, not newly asserted |
| Blank `binName` | 7,586/23,342 line items (32.5%) | WORKFLOW / ENTRY DISCIPLINE | Same basis |
| Declared-vs-derived guest-count mismatch | 756/2,916 orders with both present (25.9%) — see § G table | WORKFLOW / ENTRY DISCIPLINE | Newly quantified this task; preserved as evidence, not corrected |
| Shift override usage | 206/4,368 in (4.7%), 175/4,368 out (4.0%) | UNKNOWN | Cannot determine from data alone whether this reflects clock-in mistakes or deliberate manager scheduling adjustments — no blame assigned |
| Missing `tipAmount` | 425/3,751 payments (11.3%) | **Not a data-quality defect** — expected business variation (no tip given, or a payment type that doesn't carry one) | Reconfirmed from TASK_CLOVER_001/002 |
| Unexpected/technical Items (`# Guest`, `E-*`, `Side-Broccoli...`) | see § H | BUSINESS CONFIGURATION | Deliberate technical/staff-meal items, evidenced by the matching `Employees Meals` Category/Tag |
| Ad hoc (non-catalog) order-level discounts | 10/74 applied discounts (13.5%) | BUSINESS CONFIGURATION | Clover explicitly supports free-entry discount amounts/percentages by design, not an error path |
| Category over-tagging (1 item in 15/21 categories) | 1/532 items | UNKNOWN | Single anomalous item; low impact, not investigated further |
| `FAIL`-result payments | 36/3,751 (0.96%) | BUSINESS CONFIGURATION / expected | Declined transactions are a normal payment-processing outcome, not a source defect |
| **Refund invisible in Order/Payment/LineItem representations** | 2/2 known refunds | **SOURCE LIMITATION** | Clover's own data model separates Refunds into an independent resource without back-propagating status to the related Order/Payment/LineItem — architectural, not workflow-driven |

No signal above assigns fault to a specific employee, consistent with the task's restriction.

---

## Recommended Canonical Clover Ingestion Set

Answers: **which Clover facts should a future RF-One database ingestion pipeline actually persist?** No database schema is designed here — this is a classification only.

### INGEST NOW

Direct source facts with confirmed high coverage and clear RF-One relevance:

- Merchant identity (`id`, currency via Order)
- Employees (`id`, `customId`, `role` [tier], relationships to Order/Payment/Shift — **not** name/email/phone unless a PII-handling design is separately approved)
- Roles catalog (`id`, `name`, `systemRole`) **and** the Employee↔Role membership (`employees?expand=role`, current-snapshot only) — confirmed available, TASK_CLOVER_004, ingested as of that task
- Shifts (`inTime`/`outTime`/override fields/`employee`) — atomic clock facts, not the derived Elapsed Hours
- Orders (full field set in § E, including the `title` free-text field preserved raw for future zone/table parsing)
- Order Items — **from the dedicated `line_items?expand=modifications` endpoint, not the bulk `expand=lineItems` export** (the bulk export cannot carry `modifications` at all — confirmed structurally, not just a completeness gap) — including `binName`, `unitQty`, the line item's own `createdTime`, and `lineItemInfo`
- Items/catalog (`id`, `name`, `price`, `priceType`, `defaultTaxRates`, `sku`/`code`, category/tag/modifierGroup relationships)
- Categories, Tags, Modifier Groups, Modifiers (catalog + relationships)
- Discounts catalog **and** the raw applied-discount element on each order, preserved in its actual shape (percentage-catalog / percentage-ad-hoc / amount-ad-hoc) — **do not persist only a derived percentage-based total**, given the confirmed amount-type gap (§ L)
- Tax Rates catalog + per-item tax-rate overrides (via the `expand=taxRates` join, confirmed necessary — the empty-list-means-zero rule must be preserved)
- Payments (full field set in § O), including `result` and the confirmed FAILED-payment-excluded-from-Order.payments relationship
- Tenders (`id`, `label`, and the boolean flags, despite `opensCashDrawer` not being a reliable cash/card discriminator — still worth persisting as-is)
- Refunds — **from the dedicated `/refunds` endpoint**, given the confirmed finding that no other source reflects this data at all
- Item Stock — persist as-is (current snapshot), but do not build any inventory feature on it while it remains universally zero for this merchant

### INGEST LATER

Real, confirmed, but lower immediate priority or thinner evidence:

- Devices (3 records) — useful for POS-terminal-level segmentation, not currently needed
- Order Types catalog + usage (needed once cross-order-type reporting matters; currently 93.6% of volume is a single type)
- Customers — confirmed AVAILABLE BUT DEFERRED (§ V); revisit once a loyalty/CRM use case exists
- `lineItemInfo`/allergens — structurally present but empty for this merchant; revisit if the merchant starts populating it

### DO NOT INGEST / CONFIGURATION NOISE

- Merchant `printers`, `gateway` (empty/hardware config, no business value observed)
- Merchant `opening_hours` — unresolved by this task (GET failed); low priority given it wasn't previously identified as needed
- `merchant.tenders`/`.taxRates`/`.orderTypes` nested href stubs — fully redundant with already-ingested top-level collections

### UNRESOLVED

- `Employee.claimedTime` meaning
- `Shift.serverBanking` meaning
- `Customer.customerSince` meaning (functions as a creation-time proxy in this data, not confirmed as a genuine business date)
- Whether `Order.title`'s ~2.4% non-Inside/Outside/digit residual (77/3,268 titles) carries different information (not inspected further, to avoid any PII risk from printing raw values)
- The unresolved ~half-priced `LineItem.price` residual on a handful of items in 10 orders (TASK_CLOVER_002, not re-investigated by this task — no new evidence found)
- Whether a partial refund (as opposed to the 2 confirmed full refunds) behaves the same way structurally

---

**End of Capability Matrix.**
