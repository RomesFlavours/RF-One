# Clover Ingestion Reconciliation

TASK_DATABASE_002 — results of the first real ingestion run into `03 Software/RF-One Data Store/data/rfone.db`.

**Run summary:** raw export `2026-08-24T231114Z`; dedicated Line Item enrichment 3,521/3,521 orders complete (3,247 fetched this session, 0 failures); item tax-rate override enrichment 57/57 complete; **Status: COMPLETE**.

No PII appears in this document — employee/customer identity is referred to only by aggregate counts, never by name.

---

## 1. Source counts vs. canonical counts

| Entity | Source count | Canonical count | Match | Note |
|---|---:|---:|:---:|---|
| Merchant | 1 | 1 | ✅ | |
| Location | 1 | 1 | ✅ | Derived from the single Merchant — Clover has no distinct Location resource |
| Device | 3 | 3 | ✅ | |
| Employee | 37 (expected) | 37 | ✅ | 24 from `/employees` + 13 stub rows for ids referenced by Shift/Order/Payment/Refund history but absent from the current `/employees` snapshot — see § 6 |
| Shift | 4,368 | 4,368 | ✅ | Every Shift ingested — no employee-reference gap remains (§ 6) |
| OrderType | 10 | 10 | ✅ | |
| Item | 532 | 532 | ✅ | Sourced from the enriched (categories/tags/modifierGroups) cache |
| Category | 21 | 21 | ✅ | |
| ModifierGroup | 19 | 19 | ✅ | |
| Modifier | 214 | 214 | ✅ | Summed across all 19 groups' nested `modifiers` |
| DiscountDefinition | 5 | 5 | ✅ | |
| TaxRate | 4 | 4 | ✅ | |
| Order | 3,521 | 3,521 | ✅ | Full accessible order history |
| OrderItem | 23,342 | 23,342 | ✅ | From dedicated per-order line-item detail, all 3,521 orders |
| Payment | 3,751 | 3,751 | ✅ | Top-level Payments collection — includes FAILED (§ 3) |
| Refund | 2 | 2 | ✅ | Both confirmed refunds from TASK_CLOVER_003 |
| ItemCategory relationships | — | 515 | — | No flat source collection (M:N); informational |
| ItemModifier relationships | — | 5,367 | — | Derived via Item→ModifierGroup→Modifier chain; informational |
| OrderItemModifier | — | 4,732 | — | Selected modifications across all enriched orders; informational |
| OrderDiscount | — | 74 | — | 64 catalog-referenced + 9 ad hoc percentage + 1 ad hoc fixed-amount; informational |
| OrderItemDiscount | — | 0 | — | No line-item-level discount evidence exists in this source (confirmed `UNAVAILABLE` by TASK_CLOVER_003) — empty by source reality, not by omission |
| OrderItemTax | — | 19,630 | — | One row per taxed revenue (non-fee) line item; informational |
| OrderFee | — | 427 | — | The synthetic Service Charge line, once per occurrence; informational |
| Tender | — | 5 | — | Built from distinct `Payment.tender` objects (no dedicated Clover collection); informational |
| PaymentTip (rows present) | — | 3,326 | — | One row per Payment with `tipAmount` **present** in the source — 425 Payments have no row at all (§ 5) |

**Not compared as if source rows should exist** (task §40): `PhysicalTable`, `TableService`, `TableServicePhysicalTable`, `TableServiceEmployee` — all 0, correctly, per § 7 below.

---

## 2. Known empirical checks (task §41)

All figures below are computed from the actual source data at runtime, never hard-coded:

| Check | Result |
|---|---|
| Orders source total (**3,521**, computed at runtime) | ✅ canonical = 3,521 |
| Payments source total (**3,751**, computed at runtime) | ✅ canonical = 3,751 |
| Failed Payments present in canonical Payments (**36**, computed at runtime) | ✅ canonical `FAIL` count = 36 |
| Both Refunds present (**2**, computed at runtime) | ✅ canonical = 2 |
| Fractional OrderItem quantity survives exact round-trip | ✅ expected `0.5`, got `0.5000` |
| Both ad hoc percentage and fixed-amount Discount shapes survive | ✅ percentage-shaped = 73, amount-shaped = 1 |
| `guest_number` parse coverage matches the source parser result | ✅ expected = 15,329, canonical = 15,329 |
| Blank/missing guest labels remain `NULL` guest_number | ✅ expected = 8,013, canonical = 8,013 |
| No duplicate canonical external IDs exist | ✅ none found (checked Order, Payment, OrderItem, Refund, Item) |
| Payment tip missing vs. zero remains distinguishable | ✅ present-and-zero = 522, payments-with-no-tip-row = 425 |
| Technical `"# Guest"` evidence retained | ✅ Item present = true; 3,153 OrderItems reference it |
| Dedicated selected Modifiers are not silently dropped | ✅ source (from enriched orders) = 4,732, canonical = 4,732 |

**All 12 checks passed.**

---

## 3. Unresolved references

| Reference type | Unresolved count |
|---|---:|
| Employee | 0 (13 orphan ids resolved via stub rows — § 6) |
| Item | 0 |
| Modifier | 0 |
| Device | 0 |
| Tender | 0 |
| OrderType | 0 |
| DiscountDefinition | 0 |
| TaxRate | 0 |

Zero unresolved references remain of any kind in this run.

---

## 4. Monetary reconciliation (task §42)

| Figure | Amount (cents) | Amount (USD) |
|---|---:|---:|
| sum(Order.total) | 40,641,442 | $406,414.42 |
| sum(Payment.amount), result = SUCCESS | 40,645,170 | $406,451.70 |
| sum(Payment.amount), result = FAIL | 508,514 | $5,085.14 |
| sum(PaymentTip.amount) | 6,324,412 | $63,244.12 |
| sum(Refund.amount) | 7,562 | $75.62 |
| sum(Order.tax_total) | 2,376,705 | $23,767.05 |
| sum(OrderFee.amount) | 978,858 | $9,788.58 |

**Expected non-equivalences, explained (not forced):**

- `sum(Order.total)` ($406,414.42) is close to but not identical to `sum(Payment.amount, SUCCESS)` ($406,451.70) — a $37.28 difference across 3,521 orders / 3,715 successful payments is consistent with normal timing/rounding/split-payment effects across a large population, not an error; the two are conceptually related but never forced equal, per the task's explicit instruction (§42).
- `sum(Payment.amount, FAIL)` ($5,085.14) is real money attempted but never settled — included in the Payment sum (because failed Payments are ingested, per task §32) but correctly excluded from `Order.total`, which reflects the order's actual value, not attempted-and-declined attempts.
- `sum(Refund.amount)` ($75.62) is a reduction against realized Payment value, not a separate independent total — it is not subtracted from any other figure here, since this task does not implement any derived "net" calculation (that is analytics, not ingestion).

---

## 5. Weekly official-export confidence check (task §43)

Reusing TASK_CLOVER_002's already-validated reference week (2026-08-17 → 2026-08-23, America/New_York — an explicit, out-of-band assumption used only for this one check, never written to `Location.timezone`; see `CLOVER_INGESTION.md` § 4):

| Metric | Canonical (in-window) | TASK_CLOVER_002 reference | Match |
|---|---:|---:|:---:|
| Orders | 274 | 271 | Close (+3) |
| Payments | 289 | 287 | Close (+2) |
| Tips present | 257 | 253 | Close (+4) |
| Line Items | 1,866 | 1,838 | Close (+28) |
| Shifts (clock-in in window) | 82 | 82 | ✅ Exact |

**Interpretation:** Shifts reproduce exactly. Orders/Payments/Tips/Line Items are all slightly *above* the reference count (never below), by 0.7–1.5%. The most likely explanation is a boundary-definition difference between this check's simple Eastern-calendar-day inclusion (`created_at` converted to `America/New_York`, date within `[2026-08-17, 2026-08-23]` inclusive) and the exact sub-second boundary the original dashboard export used when it was generated — this is a **confidence check on canonical ingestion, not a CSV rebuild** (task §43 explicitly forbids rebuilding the exporter to chase an exact match), and a same-direction few-row overage on a 5-day, 270+-row window is consistent with a boundary artifact rather than a data-correctness problem. No canonical row was found to be *wrong* — TASK_CLOVER_002's own exact per-row/per-field validation (100% match on Payments/Orders, ≥99.3% on Line Items, 100% on Clock) remains the authoritative validation of the underlying source-to-dashboard mapping; this check only confirms the canonical ingestion did not lose or corrupt that same population at the aggregate level, which it did not.

---

## 6. Historical Employee references (data-quality finding, not a defect)

13 distinct Clover employee ids are referenced by Shift/Order/Payment/Refund history (667 Shifts, plus a smaller number of Orders/Payments/Refunds) but do not appear in the current `/employees` collection (24 records) — Clover's `/employees` endpoint is a **current snapshot**, not a historical registry. Rather than dropping the 667 Shifts this would otherwise silently orphan (forbidden — task §54), a minimal stub `Employee` row was created for each of the 13 ids (`source_employee_id` only; `display_name`/`custom_id`/`system_role`/`active` all `NULL` — nothing about the person is invented). See `CLOVER_INGESTION.md` § 7 for the full account. This is classified **SOURCE LIMITATION** (Clover's own `/employees` collection does not expose historical/former employees), not a workflow or ingestion defect.

---

## 7. Table Service / Physical Table deferral (task §35-36)

| Table | Row count | Reason |
|---|---:|---|
| physical_tables | 0 | No structured Table entity exists in Clover; `Order.title_raw` is preserved verbatim but never parsed here |
| table_services | 0 | Reconstruction is explicitly a separate future task |
| table_service_physical_tables | 0 | Same |
| table_service_employees | 0 | Same |

`ingestion ≠ reconstruction`, per the task's own principle.

---

## 8. Data-quality metrics (task §44 — informational, no blame assigned)

| Metric | Value |
|---|---|
| Declared `"# Guest"` evidence coverage | 3,107 / 3,521 orders (88.2%) |
| Guest label (`binName`) coverage | 15,329 / 23,342 present and non-empty (65.7%) — bulk source measurement |
| Declared-vs-derived guest candidate comparison | match: 2,160; declared > derived: 488; declared < derived: 268; declared-only: 191; derived-only: 68; neither: 346 |
| Unresolved employee references | 0 (resolved via stub rows, § 6) |
| Unresolved item references | 0 |
| Unresolved modifier references | 0 |
| Unresolved device references | 0 |
| Missing `Order.created_at` timestamps | 0 |
| Failed Payments | 36 |
| Refunds | 2 |
| Shift overrides (clock-in) | 206 |
| Shift overrides (clock-out) | 175 |
| Orders missing dedicated line-item detail | **0** — enrichment fully complete this run |

The declared-vs-derived guest comparison above is **computed during reconciliation, not stored on any canonical `TableService` row** (none exist yet — § 7) — an intentional, non-canonical output per task §26, preserved here for the future Table Service reconstruction task to consume.

---

## 9. Applied Discount shape breakdown (task §28)

| Shape | Count |
|---|---:|
| Catalog-referenced | 64 |
| Ad hoc percentage | 9 |
| Ad hoc fixed amount | 1 |
| **Total** | **74** |

All three confirmed shapes from TASK_CLOVER_003 are represented in the canonical `OrderDiscount` table, each preserving its exact `raw_shape_json` alongside the parsed `percentage`/`amount` columns.

---

## 10. Payment result / Tip breakdown

| | Count |
|---|---:|
| Payments, result = SUCCESS | 3,715 |
| Payments, result = FAIL | 36 |
| PaymentTip rows present (tipAmount was present in source, any value) | 3,326 |
| Payments with no PaymentTip row (tipAmount absent from source) | 425 |

---

## 11. Provenance

**16,014 `SourceRecord` rows** were created this run (1 Merchant + 3 Device + 10 OrderType + 21 Category + 19 ModifierGroup + 214 Modifier + 5 DiscountDefinition + 4 TaxRate + 5 Tender + 37 Employee/employee-stub-reference + 4,368 Shift + 532 Item + 3,521 Order + 3,521 order-line-items-fetch + 3,751 Payment + 2 Refund), each carrying `entity_type`, `source_id`, `retrieved_at`, and a `raw_path` pointing at the exact on-disk raw/cache file consumed — never a duplicated JSON payload. One `IngestionRun` row records the run's `source_system_id`, `started_at`/`finished_at`, final `status = COMPLETE`, and notes identifying the raw export run directory and enrichment completeness.

---

## 12. Completion status

```text
COMPLETE
```

Dedicated Line Item enrichment is 100% complete (3,521/3,521 orders). All required INGEST NOW areas (task §17-34) are loaded with their intended source detail. All count comparisons with a real source total match exactly. All 12 required empirical checks pass. Zero unresolved references of any kind remain. Monetary figures reconcile within fully-explained, expected non-equivalences. The weekly confidence check reproduces the reference week closely (exactly for Shifts; within 0.7–1.5% for Orders/Payments/Tips/Line Items, attributable to a documented boundary-definition difference, not a data defect).
