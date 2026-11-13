# Clover Data Discovery Report

Generated: 2026-08-24T23:13:10.539471+00:00
Environment: production  
Base URL: `https://api.clover.com`  
Merchant ID: `PYQYB7SKB6V31`  
Export run: `2026-08-24T23:11:14.876406+00:00` → `2026-08-24T23:13:09.433571+00:00`

This report is schema/discovery oriented. It never includes customer names, emails, phone numbers, payment identifiers or other PII values — only field names, types, presence counts and aggregate timestamps.

Tip calculation, KPI derivation and Restaurant-domain normalization are explicitly out of scope for this report (TASK_CLOVER_001).

## Merchant

- **Merchant ID:** `PYQYB7SKB6V31`
- **Merchant name field present:** yes (value withheld from this report)
- **Top-level fields observed:**
  - `address` (object) — PII-like field name, value withheld from this report
  - `createdTime` (int)
  - `gateway` (object)
  - `href` (string)
  - `id` (string)
  - `merchantPlan` (reference(id))
  - `modifierGroups` (object)
  - `name` (string) — PII-like field name, value withheld from this report
  - `opening_hours` (object)
  - `orderTypes` (object)
  - `orders` (object)
  - `owner` (object)
  - `payments` (object)
  - `printers` (object)
  - `reseller` (reference(id))
  - `shifts` (object)
  - `taxRates` (object)
  - `tenders` (object)

## Collections

### Employees — `employees`

- **Endpoint:** `/v3/merchants/PYQYB7SKB6V31/employees`
- **Record count:** 24
- **Pages fetched:** 1 (pagination required: no)
- **Earliest timestamp observed:** 2014-09-28T17:04:51+00:00
- **Latest timestamp observed:** 2026-03-06T20:24:47+00:00
- **Top-level fields observed:**
  - `claimedTime` (int), present in 17% of records
  - `customId` (string), present in 67% of records
  - `email` (string), present in 17% of records — PII-like field name, value withheld from this report
  - `href` (string), present in 100% of records
  - `id` (string), present in 100% of records
  - `inviteSent` (bool), present in 100% of records
  - `isOwner` (bool), present in 100% of records
  - `name` (string), present in 100% of records — PII-like field name, value withheld from this report
  - `nickname` (string), present in 88% of records — PII-like field name, value withheld from this report
  - `orders` (object), present in 100% of records
  - `phoneNumber` (string), present in 8% of records — PII-like field name, value withheld from this report
  - `pin` (string), present in 100% of records
  - `role` (string), present in 100% of records

### Employees — `shifts`

- **Endpoint:** `/v3/merchants/PYQYB7SKB6V31/shifts`
- **Record count:** 4368
- **Pages fetched:** 5 (pagination required: yes)
- **Earliest timestamp observed:** 2025-07-29T16:21:01+00:00
- **Latest timestamp observed:** 2026-08-24T02:40:19+00:00
- **Top-level fields observed:**
  - `employee` (object), present in 100% of records
  - `href` (string), present in 100% of records
  - `id` (string), present in 100% of records
  - `inTime` (int), present in 99% of records
  - `outTime` (int), present in 99% of records
  - `overrideInEmployee` (object), present in 5% of records
  - `overrideInTime` (int), present in 5% of records
  - `overrideOutEmployee` (object), present in 4% of records
  - `overrideOutTime` (int), present in 4% of records
  - `serverBanking` (bool), present in 1% of records
- **Fields potentially relevant to tips/payments analysis:** `employee`, `overrideInEmployee`, `overrideOutEmployee`
- **Notes:** Investigated for hours and cash-tip-related fields.

### Employees — `roles`

- **Endpoint:** `/v3/merchants/PYQYB7SKB6V31/roles`
- **Record count:** 7
- **Pages fetched:** 1 (pagination required: no)
- **Timestamps:** none of the common `*time*` epoch-millis fields were found
- **Top-level fields observed:**
  - `href` (string), present in 100% of records
  - `id` (string), present in 100% of records
  - `merchant` (object), present in 100% of records
  - `name` (string), present in 100% of records — PII-like field name, value withheld from this report
  - `systemRole` (string), present in 100% of records

### Customers — `customers`

- **Endpoint:** `/v3/merchants/PYQYB7SKB6V31/customers`
- **Record count:** 101597
- **Pages fetched:** 102 (pagination required: yes)
- **Timestamps:** none of the common `*time*` epoch-millis fields were found
- **Top-level fields observed:**
  - `customerSince` (int), present in 100% of records
  - `firstName` (string), present in 100% of records — PII-like field name, value withheld from this report
  - `href` (string), present in 100% of records
  - `id` (string), present in 100% of records
  - `lastName` (string), present in 100% of records — PII-like field name, value withheld from this report
  - `marketingAllowed` (bool), present in 100% of records
  - `metadata` (object), present in 100% of records
- **Notes:** No additional sensitive expansions requested beyond the endpoint default.

### Inventory — `items`

- **Endpoint:** `/v3/merchants/PYQYB7SKB6V31/items`
- **Record count:** 532
- **Pages fetched:** 1 (pagination required: no)
- **Earliest timestamp observed:** 2025-07-22T07:02:48+00:00
- **Latest timestamp observed:** 2026-08-15T19:33:32+00:00
- **Top-level fields observed:**
  - `alternateName` (string), present in 87% of records — PII-like field name, value withheld from this report
  - `autoManage` (bool), present in 100% of records
  - `available` (bool), present in 100% of records
  - `code` (string), present in 100% of records
  - `cost` (int), present in 96% of records
  - `defaultTaxRates` (bool), present in 100% of records
  - `deleted` (bool), present in 100% of records
  - `description` (string), present in 29% of records
  - `enabledOnline` (bool), present in 100% of records
  - `hidden` (bool), present in 100% of records
  - `id` (string), present in 100% of records
  - `isAgeRestricted` (bool), present in 100% of records
  - `isRevenue` (bool), present in 100% of records
  - `modifiedTime` (int), present in 100% of records
  - `name` (string), present in 100% of records — PII-like field name, value withheld from this report
  - `onlineName` (string), present in 100% of records — PII-like field name, value withheld from this report
  - `price` (int), present in 100% of records
  - `priceType` (string), present in 100% of records
  - `priceWithoutVat` (int), present in 29% of records
  - `sku` (string), present in 98% of records
  - `stockCount` (int), present in 96% of records
  - `type` (string), present in 100% of records
  - `unitName` (string), present in 100% of records — PII-like field name, value withheld from this report
- **Fields potentially relevant to tips/payments analysis:** `defaultTaxRates`, `modifiedTime`

### Inventory — `categories`

- **Endpoint:** `/v3/merchants/PYQYB7SKB6V31/categories`
- **Record count:** 21
- **Pages fetched:** 1 (pagination required: no)
- **Timestamps:** none of the common `*time*` epoch-millis fields were found
- **Top-level fields observed:**
  - `deleted` (bool), present in 100% of records
  - `id` (string), present in 100% of records
  - `name` (string), present in 100% of records — PII-like field name, value withheld from this report
  - `sortOrder` (int), present in 100% of records

### Inventory — `modifier_groups`

- **Endpoint:** `/v3/merchants/PYQYB7SKB6V31/modifier_groups`
- **Record count:** 19
- **Pages fetched:** 1 (pagination required: no)
- **Timestamps:** none of the common `*time*` epoch-millis fields were found
- **Top-level fields observed:**
  - `deleted` (bool), present in 100% of records
  - `id` (string), present in 100% of records
  - `modifierIds` (string), present in 90% of records
  - `modifiers` (object), present in 100% of records
  - `name` (string), present in 100% of records — PII-like field name, value withheld from this report
  - `showByDefault` (bool), present in 100% of records
- **Notes:** Modifiers retrieved nested via expand; nested array may be truncated independently of the parent page.

### Inventory — `item_stocks`

- **Endpoint:** `/v3/merchants/PYQYB7SKB6V31/item_stocks`
- **Record count:** 511
- **Pages fetched:** 1 (pagination required: no)
- **Earliest timestamp observed:** 2025-07-22T07:02:48+00:00
- **Latest timestamp observed:** 2026-02-14T19:22:10+00:00
- **Top-level fields observed:**
  - `item` (reference(id)), present in 100% of records
  - `modifiedTime` (int), present in 100% of records
  - `quantity` (float), present in 100% of records
  - `stockCount` (int), present in 100% of records
- **Relationship-shaped fields (nested `{id}` references):** `item`
- **Fields potentially relevant to tips/payments analysis:** `modifiedTime`

### Inventory — `discounts`

- **Endpoint:** `/v3/merchants/PYQYB7SKB6V31/discounts`
- **Record count:** 5
- **Pages fetched:** 1 (pagination required: no)
- **Timestamps:** none of the common `*time*` epoch-millis fields were found
- **Top-level fields observed:**
  - `id` (string), present in 100% of records
  - `name` (string), present in 100% of records — PII-like field name, value withheld from this report
  - `percentage` (int), present in 100% of records
  - `type` (string), present in 100% of records

### Inventory — `tax_rates`

- **Endpoint:** `/v3/merchants/PYQYB7SKB6V31/tax_rates`
- **Record count:** 4
- **Pages fetched:** 1 (pagination required: no)
- **Earliest timestamp observed:** 2025-07-11T21:43:06+00:00
- **Latest timestamp observed:** 2025-07-22T07:02:47+00:00
- **Top-level fields observed:**
  - `id` (string), present in 100% of records
  - `isDefault` (bool), present in 100% of records
  - `modifiedTime` (int), present in 100% of records
  - `name` (string), present in 100% of records — PII-like field name, value withheld from this report
  - `rate` (int), present in 100% of records
- **Fields potentially relevant to tips/payments analysis:** `modifiedTime`

### Inventory — `tags`

- **Endpoint:** `/v3/merchants/PYQYB7SKB6V31/tags`
- **Record count:** 20
- **Pages fetched:** 1 (pagination required: no)
- **Timestamps:** none of the common `*time*` epoch-millis fields were found
- **Top-level fields observed:**
  - `id` (string), present in 100% of records
  - `name` (string), present in 100% of records — PII-like field name, value withheld from this report
  - `showInReporting` (bool), present in 100% of records

### Inventory — `order_types`

- **Endpoint:** `/v3/merchants/PYQYB7SKB6V31/order_types`
- **Record count:** 10
- **Pages fetched:** 1 (pagination required: no)
- **Timestamps:** none of the common `*time*` epoch-millis fields were found
- **Top-level fields observed:**
  - `avgOrderTime` (int), present in 60% of records
  - `fee` (int), present in 60% of records
  - `filterCategories` (bool), present in 100% of records
  - `hoursAvailable` (string), present in 100% of records
  - `id` (string), present in 100% of records
  - `isDefault` (bool), present in 100% of records
  - `isDeleted` (bool), present in 100% of records
  - `isHidden` (bool), present in 100% of records
  - `label` (string), present in 100% of records
  - `labelKey` (string), present in 60% of records
  - `maxOrderAmount` (int), present in 60% of records
  - `maxRadius` (int), present in 60% of records
  - `minOrderAmount` (int), present in 60% of records
  - `systemOrderTypeId` (string), present in 60% of records
  - `taxable` (bool), present in 100% of records
- **Fields potentially relevant to tips/payments analysis:** `maxOrderAmount`, `minOrderAmount`, `taxable`

### Orders — `orders`

- **Endpoint:** `/v3/merchants/PYQYB7SKB6V31/orders`
- **Record count:** 3521
- **Pages fetched:** 4 (pagination required: yes)
- **Earliest timestamp observed:** 2026-05-27T15:35:40+00:00
- **Latest timestamp observed:** 2026-08-24T05:46:02+00:00
- **Top-level fields observed:**
  - `clientCreatedTime` (int), present in 100% of records
  - `createdTime` (int), present in 100% of records
  - `currency` (string), present in 100% of records
  - `customers` (object), present in 82% of records
  - `device` (reference(id)), present in 100% of records
  - `discounts` (object), present in 2% of records
  - `employee` (reference(id)), present in 100% of records
  - `groupLineItems` (bool), present in 100% of records
  - `href` (string), present in 100% of records
  - `id` (string), present in 100% of records
  - `isVat` (bool), present in 100% of records
  - `lineItems` (object), present in 100% of records
  - `manualTransaction` (bool), present in 100% of records
  - `modifiedTime` (int), present in 100% of records
  - `note` (string), present in 1% of records
  - `orderType` (reference(id)), present in 100% of records
  - `payType` (string), present in 100% of records
  - `paymentState` (string), present in 100% of records
  - `payments` (object), present in 100% of records
  - `state` (string), present in 100% of records
  - `taxRemoved` (bool), present in 100% of records
  - `testMode` (bool), present in 100% of records
  - `title` (string), present in 93% of records
  - `total` (int), present in 100% of records
- **Relationship-shaped fields (nested `{id}` references):** `device`, `employee`, `orderType`
- **Fields potentially relevant to tips/payments analysis:** `clientCreatedTime`, `createdTime`, `employee`, `modifiedTime`, `taxRemoved`
- **Notes:** Expanded nested collections (lineItems/payments/discounts) may be truncated; see orders_line_item_completeness_sample.json for a bounded completeness check.

### Payments — `payments`

- **Endpoint:** `/v3/merchants/PYQYB7SKB6V31/payments`
- **Record count:** 3751
- **Pages fetched:** 4 (pagination required: yes)
- **Earliest timestamp observed:** 2026-05-27T16:13:50+00:00
- **Latest timestamp observed:** 2026-08-24T05:46:02+00:00
- **Top-level fields observed:**
  - `amount` (int), present in 100% of records
  - `cashTendered` (int), present in 9% of records
  - `cashbackAmount` (int), present in 100% of records
  - `clientCreatedTime` (int), present in 100% of records
  - `createdTime` (int), present in 100% of records
  - `device` (reference(id)), present in 100% of records
  - `employee` (reference(id)), present in 100% of records
  - `id` (string), present in 100% of records
  - `modifiedTime` (int), present in 100% of records
  - `offline` (bool), present in 91% of records
  - `order` (reference(id)), present in 100% of records
  - `result` (string), present in 100% of records
  - `taxAmount` (int), present in 100% of records
  - `tender` (object), present in 100% of records
  - `tipAmount` (int), present in 89% of records
- **Relationship-shaped fields (nested `{id}` references):** `device`, `employee`, `order`
- **Fields potentially relevant to tips/payments analysis:** `amount`, `cashTendered`, `cashbackAmount`, `clientCreatedTime`, `createdTime`, `employee`, `modifiedTime`, `result`, `taxAmount`, `tender`, `tipAmount`
- **Notes:** First-class payments export; primary source investigated for tip-related fields.

## Orders line-item completeness sample

A bounded sample of 20 order(s) was checked by comparing the `expand=lineItems` array returned on the `orders` collection against a direct call to that order's own `line_items` endpoint. See `orders_line_item_completeness_sample.json` in the raw export directory for the per-order comparison. Do not assume the full order history's expanded line items are complete based on this sample alone.

## Known limitations

- Pagination uses `limit`/`offset`; a page shorter than the requested page size is treated as the last page (Clover does not reliably return a total count).
- Nested `expand`-ed collections (e.g. order `lineItems`, `modifier_groups` → `modifiers`) can be truncated independently of the parent collection's own pagination; only a bounded sample of orders was cross-checked against their dedicated `line_items` endpoint in this pass.
- No date-range filter was applied; the exporter attempted the complete accessible history for every collection. Any endpoint-imposed history limit is recorded per collection above via HTTP status/error where encountered.
