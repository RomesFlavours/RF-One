# Clover → RF-One Canonical Ingestion

TASK_DATABASE_002 — the first real ingestion of Clover source evidence into the RF-One canonical Restaurant operational database created by TASK_DATABASE_001. This document describes the ingestion **architecture and design decisions**; for the actual run's results, see `CLOVER_INGESTION_RECONCILIATION.md` and `07 Tasks/Reports/TASK_DATABASE_002_REPORT.md`.

```text
Clover raw/API evidence
        ↓
Clover source adapter          ← this document
        ↓
normalization + provenance
        ↓
RF-One canonical operational database
        ↓
future analytics / KPI / Performance / Training / Decisions
```

---

## 1. Architecture

```text
03 Software/RF-One Data Store/
├── ingest_clover.py                    CLI entry point (task §45)
├── enrich_clover_cache.py              standalone resumable enrichment entry point
├── validate_ingestion.py               post-promotion validation (task §48)
└── rfone_data_store/
    ├── ingestion/
    │   ├── common.py                   source-independent helpers (epoch→UTC, payload hashing)
    │   └── clover/
    │       ├── reader.py               disk-only reads of Clover's raw/cache evidence
    │       ├── enrichment.py           resumable dedicated-endpoint GET calls
    │       ├── parser.py               pure parsing rules (guest_number, discount shape, tax rate)
    │       ├── mapping.py              Clover raw dict → canonical column-kwargs dict
    │       ├── ingest.py               orchestration: upserts into a (staging) session
    │       └── reconciliation.py       post-ingestion counts/checks/monetary/weekly confidence
    └── models.py                       the canonical schema (TASK_DATABASE_001, corrected §3 below)
```

This mirrors the task's suggested structure exactly. Nothing in `rfone_data_store.models` imports from `ingestion/` — the dependency runs one way (ingestion → canonical schema), so the schema stays usable by a future non-Clover source without carrying any Clover-specific code.

**Reuse boundary:** the adapter reuses the Clover Data Explorer's already-reviewed, read-only HTTP primitives — `clover_explorer.client.CloverClient`, `.config.load_config`, `.pagination.paginate`, `.api_cache.ApiCache` — for the enrichment GET calls only (`enrichment.py`). It does **not** import any of that module's dashboard-CSV reconstruction logic (`export_orders.py`, `export_payments.py`, etc.) — canonical mapping is written fresh in `mapping.py`, shaped for the canonical schema, not a CSV column layout.

---

## 2. Pre-ingestion schema review (task §3)

One correction was made before any real data was loaded, exactly as the task anticipated:

**`device_id` FK added to `Order`, `Payment`, `Refund`** (alongside the existing `device_source_id` raw string). TASK_DATABASE_001 had left Device linkage as a raw string only, reasoning it mirrored `source_employee_id`'s pattern. Since `Device` is already a canonical catalog entity resolvable from Clover's small, stable `/devices` collection (3 records), a resolved FK materially improves queryability at negligible cost. Both columns are retained: `device_id` is populated only when the source device is actually resolved to a canonical `Device` row; `device_source_id` always preserves the raw source reference regardless of resolution. See `DATABASE_SCHEMA.md` §5/§10 for the updated field documentation, and `rfone_data_store/schema_validation.py` for the extended synthetic-fixture check.

**No other schema change was made.** In particular, `Shift.employee_id` (`NOT NULL`) was deliberately left unchanged — see § 6 below for how a real gap this created during ingestion (historical Shifts referencing employees no longer in Clover's current `/employees` snapshot) was resolved without weakening the schema or dropping data.

---

## 3. Migration baseline (task §4)

Alembic was introduced for the first time this task, before any real data was loaded:

- `alembic.ini` + `migrations/` (standard Alembic layout, `script_location = migrations`).
- `migrations/env.py` targets `rfone_data_store.models.Base.metadata` and resolves its database URL the same way `rfone_data_store.database.get_database_url()` does (`RFONE_DATABASE_URL` / `.env` / local SQLite default), or via `ALEMBIC_DATABASE_URL_OVERRIDE` — used internally by `rfone_data_store.database.run_migrations_to_head(url)` so the same migration path also creates/upgrades the ingestion staging database (§ 5 below).
- **Baseline revision** `9516f3bd1495_baseline_canonical_restaurant_schema.py`, generated via `alembic revision --autogenerate` against an empty SQLite database, represents the exact 32-table schema (including the `device_id` correction above) used for this ingestion.
- `create_database.py` now runs `alembic upgrade head` internally rather than a direct `Base.metadata.create_all()` — the same code path works whether the target is brand new or already on an older revision, so **no future schema change requires deleting a populated database.**
- Verified this task: `alembic upgrade head` against a freshly-deleted, non-existent SQLite file creates all 32 tables correctly (confirmed via `inspect_database.py` immediately after).

See `README.md`, "Schema migrations (Alembic)", for day-to-day usage.

---

## 4. Source priority (task §6)

```text
1. dedicated cached endpoint response when it contains richer structure
2. full raw Clover export
3. bounded additional GET only when required for an INGEST NOW field
```

Concretely, `reader.py`'s `CloverSourceBundle.items` property prefers the TASK_CLOVER_003 supplementary cache (`items_expand_categories_tags_modifierGroups.json` — carries `categories`/`tags`/`modifierGroups`, which the bulk `items.json` cannot) over the plain bulk export, falling back automatically if the enriched cache is ever absent. `OrderItem`/`OrderItemModifier` ingestion always prefers the dedicated per-order `lineitems_<orderId>.json` cache (which alone carries `modifications`) over the bulk `orders?expand=lineItems` nested array. Devices and Refunds come from their dedicated cached responses (`devices.json`, `refunds_page1.json`) since no bulk equivalent exists for either. No data was re-downloaded that was already usable on disk.

---

## 5. Dedicated Line Item enrichment (task §7, §9, §47)

TASK_CLOVER_002/003 had enriched only 271 of the merchant's 3,521 orders (the one validated reconciliation week). This task's `enrichment.py` closed the remaining gap:

- `missing_line_item_order_ids(order_ids)` checks, per order, whether `data/generated_exports/_api_cache/supplementary/lineitems_<orderId>.json` already exists on disk — the exact same cache file `ApiCache.get_or_fetch` (Clover Data Explorer, TASK_CLOVER_002) already uses. **This file-existence check is the entire resumability mechanism** — no separate checkpoint/progress file is needed. Interrupting the process and re-running `enrich_clover_cache.py` (or `ingest_clover.py` without `--skip-enrichment`) simply finds the already-written files and only fetches what's still missing.
- Fetches are `GET`-only (`.../orders/{id}/line_items?expand=modifications`, fully paginated via the existing `paginate()` helper), paced at 0.12s between requests (a deliberate politeness margin on top of `CloverClient`'s own 429/5xx retry+backoff — no documented Clover rate limit required this, but the task asked for conservative pacing), and every response is cached before the next request begins.
- The analogous, much smaller **item tax-rate override enrichment** (`itemtaxrate_<itemId>.json`, for the 57 items with `defaultTaxRates: false`) uses the identical pattern.
- Progress is printed as `Enriching dedicated line items: X/Y complete` (task §45's example), updated every 25 orders — never the payload, never the token.

**Result this run: 3,521/3,521 orders fully enriched (3,247 newly fetched this session, 0 failures); 57/57 item tax-rate overrides cached (44 newly fetched, 0 failures).** Dedicated line-item enrichment is therefore **complete** for the full currently-accessible order history — this ingestion did not need to fall back to the bulk-nested `lineItems` for any order, and no `OrderItem` in the canonical database is missing its selected-Modifier detail because of an unenriched source.

---

## 6. Entity mapping — direct vs. derived transformations

Full field-by-field documentation lives in `mapping.py`'s docstrings/comments (one function per entity) and `DATABASE_SCHEMA.md`. The mapping decisions worth calling out explicitly here, because they are not 1:1 field copies:

| Canonical field | Source | Nature | Rationale |
|---|---|---|---|
| `Location` (the entity itself) | `merchant.json` | **Derived** — Clover has no distinct Location resource; the single Merchant IS the single Location | `source_location_id` reuses the merchant's own id, documented, not a separate Clover field |
| `Location.currency` | Majority value of `Order.currency` across the full order history (100% `"USD"`) | **Derived** | Clover exposes no currency field on Merchant/Location directly; left `NULL` if no Order evidence exists |
| `Location.timezone` | — | **Never populated** | No timezone field exists anywhere on Clover's Merchant object (TASK_CLOVER_003) — always `NULL`, never `"America/New_York"` |
| `Device.name` | `device.productName` (e.g. "Flex 4") | **Direct**, but a naming choice | Clover has no plain "name" field on Device; `productName` is the closest human-readable label, kept distinct from `model` |
| `Tender.source_type` | `tender.labelKey` (e.g. an i18n key) | **Direct** | `opensCashDrawer` is explicitly NOT used — TASK_CLOVER_003 disproved it as a cash/card signal for this merchant |
| `Item.active` | `not item.deleted` (when `deleted` is present) | **Derived, single-signal by design** | Clover exposes `deleted`/`hidden`/`available` as three distinct, non-equivalent signals; only `deleted` (the least speculative) feeds the single `active` column the schema provides — `hidden`/`available` are not otherwise persisted |
| `TaxRate.rate` / `OrderItemTax.rate_applied` | `clover_rate / 10_000_000` | **Derived (re-expressed)** | Canonical decimal fraction (e.g. `0.065000`), not Clover's own scaling — see `parser.canonical_tax_rate()` |
| `DiscountDefinition.percentage` / `OrderDiscount.percentage` | Clover's own `percentage` field, already a plain percent integer | **Direct** (different scale from `TaxRate.rate` — documented explicitly so no future maintainer assumes a uniform "rate" encoding) |
| `OrderItemTax` (per line item) | `Item.defaultTaxRates` + per-item `taxRates` override (empty override list ⇒ 0%, confirmed rule, not "fall back to default") | **Derived** | Only computed for revenue, non-fee line items; never fabricated where the enrichment cache lacks the override (task §30) |
| `Order.tax_total` | `sum(order.payments[].taxAmount)` | **Derived, non-allocative** | A simple sum of the Order's own nested Payments — conceptually owned by Order (Restaurant Sales Model §15), not an allocation across Items |
| `Order.subtotal` / `Order.discount_total` | — | **Never populated (`NULL`)** | Clover exposes neither directly; computing them accurately requires the same percentage-to-cents allocation the task calls "derived analytics, not source truth" at the Item level (§29) — left for a future analytics pass, not fabricated here |
| `ItemModifier` (Item↔Modifier availability) | Item→ModifierGroup (enriched cache) → Modifier (ModifierGroup's own nested expand) | **Derived** — not a direct Clover field | Clover only gives Item→ModifierGroup directly; the Group→Modifier membership is applied to flatten it into the schema's Item↔Modifier table, following Clover's own defined structure, not inventing one |
| `OrderFee.fee_type` | `"SERVICE_CHARGE"` iff `line_item.note == "Service Charge"`, else `NULL` | **Derived, narrowly scoped** | The only confirmed real combination (427/427 fee lines) — no other fee type is guessed (task §31) |
| `Employee` stub rows | Employee ids referenced by Shift/Order/Payment/Refund but absent from the current `/employees` snapshot | **New this task — see § 7 below** | |

Everything else (Order/OrderItem/Payment/Refund/catalog fields not listed above) is a **direct** 1:1 copy of the corresponding Clover field, per `mapping.py`.

---

## 7. A genuine gap found during ingestion: historical Employee references

Clover's `/employees` collection is a **current snapshot** — it does not include employees who have since been removed from the account. This task found, empirically, that **13 distinct employee ids are referenced by 667 of the merchant's 4,368 Shifts (and by a smaller number of Orders/Payments/Refunds) but do not appear in the fetched `employees.json`.**

`Shift.employee_id` is `NOT NULL` (unchanged from TASK_DATABASE_001 — no evidence required weakening it). The first implementation of employee-reference resolution therefore **silently skipped** 667 Shifts whose main employee could not be resolved — caught by this task's own reconciliation (a Shift count mismatch, 3,701 canonical vs. 4,368 source) before promotion, and corrected: `ingest.py`'s `ingest_employee_stub_references()` now creates a minimal stub `Employee` row for every such id (only `source_employee_id` is set; every other field — `display_name`, `custom_id`, `system_role`, `active` — stays `NULL`, nothing about the person is fabricated) before Shifts/Orders/Payments/Refunds are ingested. **Result: all 4,368 Shifts are ingested; zero unresolved employee references remain.** The reconciliation's Employee count comparison accounts for this explicitly (`24 from /employees + 13 stub rows`), rather than treating it as a false mismatch.

This is recorded here because it is exactly the kind of "known source relationship that would otherwise be stored incorrectly or lose evidence" the task's pre-ingestion review (§3) anticipated — it just wasn't visible until real historical data was actually loaded, which is precisely why this task (not the schema-only TASK_DATABASE_001) is where it surfaced.

---

## 8. Idempotency (task §9)

Every canonical entity is upserted (`ingest.upsert()`) keyed by its schema `UniqueConstraint` — `(source_system_id, source_*_id)` — never blindly inserted. Running the same source data twice updates existing rows in place rather than duplicating them, for every entity type the task lists (Orders, Order Items, Items, Payments, Refunds, Employees, Shifts, catalog entities, applied Modifiers, Discounts, Taxes, Fees, SourceRecords).

**Source elements without a guaranteed independent id** (e.g. an ad hoc Order Discount element, which always carries its own `id` in this merchant's data, or an `OrderItemModifier` whose `source_modification_id` may be absent) are upserted against `(order_item_id, source_modification_id)` when a modification id exists; when it does not, the row is inserted without an update-in-place guarantee — documented as a known limitation, not silently pretended to be fully idempotent (no real example lacking `source_modification_id` was found in this merchant's data, so this path was not exercised).

**In practice**, this run's staging→promotion design (§ 9 below) makes idempotency observable at the whole-database level too: re-running `ingest_clover.py` against the same cached source always produces staging DB with the same row counts (the upsert logic is exercised against an *empty* staging DB every run, so it always takes the "insert" branch — but the same code, if ever pointed at an already-populated target, would take the "update" branch instead without duplicating rows, since the upsert check is unconditional).

---

## 9. Transaction safety: staging → reconciliation → promotion (task §10)

```text
1. Delete (if present) and freshly migrate an isolated, Git-ignored staging SQLite DB
   (data/rfone.staging.db) to the current schema head.
2. Run the full ingestion into the staging DB.
3. Run full reconciliation against the staging DB.
4. Only if the run's status is COMPLETE or PARTIAL (never FAILED — see § "Ingestion status"
   below) AND not --dry-run: copy the staging DB file over the target database
   (data/rfone.db), after first backing up any pre-existing target to `rfone.db.bak`.
```

The last known-good `rfone.db` is **never touched** until a full, successfully-reconciled staging run exists on disk. A failed run leaves `rfone.db` exactly as it was before the attempt, and preserves the staging DB for inspection (printed explicitly by the CLI) rather than deleting evidence of what went wrong. `--dry-run` performs every step through reconciliation, reports the same counts, and then deletes the staging DB without ever touching `rfone.db` — "must not leave committed source output" (task §46) is satisfied by this explicit cleanup.

---

## 10. Provenance (task §38-39)

- **`IngestionRun`** — one row per full run, in the staging DB (and therefore promoted alongside the data it describes). Records `source_system_id`, `started_at`/`finished_at`, `status` (`RUNNING` → `COMPLETE`/`PARTIAL`/`FAILED`), and a `notes` field recording which raw export run directory was used and whether dedicated line-item enrichment was complete. **A failed run is never marked successful** — the `except` path in `ingest_clover.py` explicitly sets `status="FAILED"` before its own best-effort commit.
- **`SourceRecord`** — one row per top-level ingested source entity instance (Merchant, Device, OrderType, Category, ModifierGroup, Modifier, DiscountDefinition, TaxRate, Tender, Employee, employee-stub-reference, Shift, Item, Order, order-line-items-fetch, Payment, Refund), each carrying `entity_type`, `source_id`, `retrieved_at`, and `raw_path` pointing at the actual on-disk raw/cache file it came from — **not** a duplicated `raw_json` payload (task §38 explicitly discourages this; the large raw exports already live, Git-ignored, under `03 Software/Clover Data Explorer/data/`). Sub-elements embedded within an already-recorded parent's own JSON (`OrderItem`, `OrderItemModifier`, `OrderDiscount`, `OrderItemDiscount`, `OrderItemTax`, `OrderFee`, `PaymentTip`) do not get their own separate `SourceRecord` row — their provenance is the parent Order/Payment's `raw_path` plus their own `source_system_id`+`source_*_id` columns, which are sufficient to trace them back to the exact source element without a 40,000-row `SourceRecord` table that would add cost without adding traceability. This granularity choice is deliberate — see `ingest.py`'s `_add_source_record` call sites for exactly which entity types get one.
- **This run produced 16,014 `SourceRecord` rows** (one IngestionRun; see `CLOVER_INGESTION_RECONCILIATION.md` for the full breakdown).

---

## 11. Reconciliation (task §40-44)

Implemented in `reconciliation.py`, covering exactly the required areas: source-vs-canonical counts for every listed entity (informational-only for pure relationship tables with no flat source collection — `ItemCategory`, `ItemModifier`, `OrderItemModifier`, `OrderDiscount`, `OrderItemDiscount`, `OrderItemTax`, `OrderFee`, `Tender`, `PaymentTip`, none of which have a single natural "source total" to force-equate against); the specific empirical checks the task names (failed Payments present, both Refunds present, fractional quantity round-trip, both discount shapes, guest_number parse coverage, blank labels stay `NULL`, no duplicate external ids, tip missing-vs-zero distinguishable, `# Guest` evidence retained, selected Modifiers not dropped); monetary reconciliation with explicit non-equivalence explanations; and the weekly confidence check against TASK_CLOVER_002's already-validated reference week. **Full results are in `CLOVER_INGESTION_RECONCILIATION.md` — this document describes only how each check works, not this run's numbers.**

---

## 12. Known deferred concepts

Deliberately **not** implemented by this task, per its own restrictions:

- **Table Service reconstruction** — `table_services`, `table_service_physical_tables`, `table_service_employees` are left empty. `Order.table_service_id` is `NULL` for every ingested Order. A separate future task reconstructs service events from Orders, timestamps, `title_raw`/zone evidence, guest assignment, and business rules — `ingestion ≠ reconstruction` (task §36).
- **Physical Table fabrication** — `physical_tables` is left empty. `Order.title_raw` is preserved verbatim (e.g. `"#4 - Inside"`) but never parsed into a Table relationship here (task §23, §35).
- **Customers** — not ingested at all, per TASK_CLOVER_003's `AVAILABLE BUT DEFERRED` classification and this task's explicit restriction (§37, §54).
- **`TableService.declared_guest_count`/`derived_guest_count`** — not populated, since no `TableService` rows exist to populate them on. The candidate declared/derived guest counts ARE computed (per-Order, from the `"# Guest"` OrderItem and `guest_number`-parsed `binName` evidence, exactly as the Restaurant Sales Model and TASK_CLOVER_003 define them) and reported in `CLOVER_INGESTION_RECONCILIATION.md`'s data-quality section — a **non-canonical** ingestion/reconciliation output, per the task's explicit instruction (§26), pending the Table Service reconstruction task that will decide how to aggregate them onto real `TableService` rows.
- **`Order.subtotal`/`Order.discount_total`** — left `NULL`; see § 6 above.
- **`OrderItemDiscount`** — the table exists and the ingestion path for it exists (`mapping.py` has no dedicated function only because no line-item-level discount was ever observed in the source — see `CLOVER_DATA_CAPABILITY_MATRIX.md` § L, "UNAVAILABLE, confirmed"); it is empty in this run because the source contains no such evidence, not because it was skipped.
- **KPI/Performance/Training/payroll/tip-allocation logic, a web UI, a REST API** — none implemented, per task §54.
