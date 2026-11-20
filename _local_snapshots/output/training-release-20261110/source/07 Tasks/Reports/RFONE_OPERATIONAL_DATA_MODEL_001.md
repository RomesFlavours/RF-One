# RFONE_OPERATIONAL_DATA_MODEL_001 — Clover Connector / RF-One Operational Data Model

## 1. Existing operational models found

Inspection of `rfone_data_store/models.py` found the following operational entities already persisted:

- `Merchant`, `Location` (organizational/tenant scope)
- `Employee`, `Shift`, `EmployeeAssignment` (workforce)
- `Order`, `OrderItem`, `OrderItemModifier`, `OrderFee` (sales)
- `Payment`, `PaymentTip`, `Refund` (settlement)
- `Item`, `Category`, `ModifierGroup`, `Modifier`, `Tender`, `Device`, `OrderType`, `DiscountDefinition`, `OrderDiscount`, `OrderItemDiscount`, `TaxRate`, `OrderItemTax` (catalog/reference)
- `SourceSystem`, `IngestionRun`, `SourceRecord` (provenance/acquisition infrastructure)
- `TipPolicy`, `TipPolicyComponent` (retired legacy Tips history, read-only, per TIPS_LEGACY_ENGINE_RETIREMENT_001)
- `TipDistributionRule`, `TipDistributionRuleVersion` (current canonical Tips configuration, out of scope here)

No `Customer` model exists anywhere in the schema (confirmed by search) — nothing in the repository currently ingests or consumes customer-level data, so none was created (task explicitly warns against creating entities blindly).

## 2. Which models were already canonical

`Merchant`, `Location`, `Employee`, and `Shift` were already fully canonical: each carries its own RF-One primary key as its real identity, with `source_system_id`/`source_*_id` already **nullable** and paired with a `UniqueConstraint`. Their own docstrings already state this explicitly as "modeling principle F" (`DATABASE_SCHEMA.md`). No change was needed to any of these four.

`PaymentTip` was already fully generic: it carries no external id field of its own at all (it is keyed 1:1 by `payment_id`), so it could never have had this problem.

## 3. Which Clover-specific coupling was found

The one concrete, structural gap: `Order`, `OrderItem`, `OrderFee`, `Payment`, and `Refund` had `source_system_id` (and, except for `OrderFee`, `source_*_id`) declared `NOT NULL`. This silently violated the schema's own documented principle F and meant a canonical record in any of these five tables **could not be created at all** without inventing a source system and a fake external id — structurally forcing every future record, including one a native RF-One POS would originate itself, to pretend to come from an external provider.

No other Clover-specific coupling was found in the canonical model itself: entity names are already generic (`Order`, not `CloverOrder`; `Employee`, not `CloverEmployee`), and the acquisition/normalization logic already lives entirely inside `technical/connectors/clover/` (relocated there by TECHNICAL_CONNECTORS_STRUCTURE_001), never inside a Domain.

One acceptable, deliberately-left, non-structural coupling: `Tips/app.py`'s `_resolve_clover_location_id()` filters `SourceSystem.code == "CLOVER"` when resolving which connector to invoke for a manually-triggered Historical Backfill. This is UI-action wiring ("which connector do I ask to backfill"), not tip-calculation logic — `tips/distribution_engine.py` has zero functional Clover references (confirmed by search) and consumes only canonical `Order`/`Payment`/`PaymentTip`/`OrderFee`/`Shift`/`EmployeeAssignment` rows.

## 4. Files/models/migrations changed

- Modified `rfone_data_store/models.py`: `Order.source_system_id`/`source_order_id`, `OrderItem.source_system_id`/`source_line_item_id`, `OrderFee.source_system_id`, `Payment.source_system_id`/`source_payment_id`, `Refund.source_system_id`/`source_refund_id` changed from required (`nullable=False`) to optional (`nullable=True`), with an explanatory comment on `Order` (the primary rationale) and short cross-references from the other four.
- New migration `migrations/versions/b6d3f8a1c4e7_relax_source_identity_nullability.py` (down_revision `e2c7b4a9f1d6`, now the sole head): relaxes the same ten columns to nullable via `batch_alter_table`. No column added, removed, renamed, or retyped; no `UniqueConstraint` changed; no existing row's data touched (every already-ingested row already has real, non-null values, so it already satisfies the relaxed constraint). Downgrade re-tightens to `NOT NULL`.
- New `rfone_data_store/rfone_operational_data_model_validation.py` and `test_rfone_operational_data_model.py`: synthetic-fixture regression suite (7 checks) proving native (sourceless) rows can be created, two native rows never collide, and genuine external-id duplicates are still rejected.
- Modified `DATABASE_SCHEMA.md`: corrected the now-stale "Required source fields"/"Required" wording for the `orders`, `order_items`, `payments`, and `refunds` sections, and added a nullability note to the unique-constraint summary table. Unrelated sections (`items`, `categories`, `modifier_groups`, `tenders`, `devices`, etc. — genuinely out of this task's scope) were left untouched.
- Modified `PROJECT_STATE.md`: added a status bullet for this task.

## 5. Provider Mirror structure

The existing `SourceRecord` table (`id`, `ingestion_run_id`, `source_system_id`, `entity_type`, `source_id`, `retrieved_at`, `payload_hash`, `raw_path`, `raw_json`) already satisfies the Provider Mirror concept structurally: a generic, append-only, Clover-shaped raw-payload log, owned exclusively by the connector layer, never read by a Domain. It is not currently written to by the live-sync/backfill acquisition path (`technical/connectors/clover/acquisition.py`, `live_sync.py`) — that path fetches, maps, and upserts directly into the canonical model without a separate raw-mirror write step. Wiring `SourceRecord` writes into that path was considered and deliberately **not done**: it would mean adding a new write step into the live-sync/backfill code path, which crosses into "redesigning Clover Live Sync" — explicitly out of scope for this task. This is flagged here as an honest open finding, not silently built or silently ignored (see §11).

## 6. RF-One canonical operational structure

`Order`, `OrderItem`, `OrderFee`, `Payment`, and `Refund` now follow exactly the same pattern already used by `Merchant`/`Location`/`Employee`/`Shift`: each row's real identity is its own RF-One-assigned primary key (`id`); `source_system_id`/`source_*_id` are optional provenance, present when (and only when) the row came from an external system. No entity name, column, or required field in the canonical model refers to Clover or requires Clover-specific knowledge to populate or consume.

## 7. Source/external identity mechanism

Unchanged in mechanism, now consistently applied: `SourceSystem.code` (e.g. `"CLOVER"`) identifies the provider; each canonical entity's own `source_system_id` (FK) + `source_*_id` (raw external id string) pair is optionally present and enforced unique together via `UniqueConstraint(source_system_id, source_*_id)`. SQL/SQLite treats `NULL` as distinct from any other value (including another `NULL`) in a unique constraint, so relaxing these columns to nullable cannot create new collisions among natively-created rows, while a genuine duplicate external-id pair is still rejected exactly as before (regression-tested, §10). Location/Merchant scoping for multi-location isolation is unaffected — `location_id`/`merchant_id` remain required, ordinary foreign keys throughout.

## 8. How Clover now populates canonical RF-One data

Unchanged: `technical/connectors/clover/acquisition.py` (Historical Backfill and Live Sync, both idempotent, both funneling through the same mapping/upsert code) fetches Clover data and upserts directly into the canonical tables above, always supplying real `source_system_id`/`source_*_id` values for every row it creates. This task did not touch that path — it only removed the previously-forced `NOT NULL` constraint on the destination columns those upserts already fill in.

## 9. How Domains consume it

Unchanged and confirmed unaffected: Tips (`tips/distribution_engine.py`, `tips/distribution_rule_service.py`) reads canonical `Order`/`Payment`/`PaymentTip`/`OrderFee`/`Shift`/`EmployeeAssignment`/`Employee` rows directly, with no Clover API or Clover-shaped field anywhere in its query or calculation logic (confirmed by search — zero functional Clover references). This task did not redesign the Tip Calculator, as instructed.

## 10. Validation results

All nine checklist items from the task's §10 were verified:

1. Clover provider-specific responsibilities remain inside `technical/connectors/clover/` — confirmed, unchanged by this task.
2. RF-One canonical operational records have RF-One internal identities — confirmed: every table's own `id` is its real identity; new synthetic test proves `Order`/`OrderItem`/`Payment`/`OrderFee`/`Refund` rows can be created with `source_system_id is None`.
3. Existing Clover ids remain traceable as external/source identities — confirmed: no existing row's data was touched by the migration; the same `source_system_id`/`source_*_id` columns and unique constraints remain in place, only their `NOT NULL` requirement was relaxed.
4. Domains can consume canonical entities without Clover API knowledge — confirmed, unchanged (§9).
5. Repeated Clover ingestion remains idempotent — confirmed: `test_clover_acquisition.py` (38/38) and `test_clover_live_sync.py` (8/8) pass unchanged after the migration.
6. Historical Backfill still populates the same canonical model — confirmed, same suites.
7. Live Sync still updates that model — confirmed, same suites.
8. Multiple Locations remain isolated correctly — confirmed: `test_organization_validation.py` (14/14) unaffected.
9. Nothing in the canonical model prevents RF-One from becoming the originating POS later — confirmed by the new `rfone_operational_data_model_validation.py` suite (7/7): native Merchant/Location/Order/OrderItem/Payment/OrderFee/Refund rows can each be created with no source system at all; two natively-created Orders coexist without a unique-constraint collision; a genuine duplicate external-id pair is still correctly rejected.

Full regression run (all suites green, no suite touched by this task regressed):
`test_clover_acquisition.py` 38/38, `test_clover_live_sync.py` 8/8, `test_tips_import_concurrency_guard.py` 26/26, `test_tips_distribution_rules.py` 24/24, `test_tips_distribution_engine.py` 29/29, `test_organization_validation.py` 14/14, `test_restaurant_profile_bootstrap.py` 14/14, `test_purchasing_engine.py` 24/24, `test_sales_validation.py` 27/27, `test_rfone_operational_data_model.py` 7/7 (new).

Migration verified in both directions on a disposable database: upgrade from `e2c7b4a9f1d6` clean; downgrade back and re-upgrade clean. `alembic heads` confirms a single linear head (`b6d3f8a1c4e7`).

## 11. Architectural blocker / open finding

Not a blocker, but an honest gap worth flagging: the Provider Mirror concept (`SourceRecord`) exists structurally but is not currently populated by the live-sync/backfill acquisition path — only by the older bulk `ingest.py` pipeline. Wiring raw-payload preservation into the live/backfill path would require touching that code path's write sequence, which was judged to cross into "redesigning Clover Live Sync," explicitly forbidden by this task. No other architectural blocker was found: the canonical schema already needed only this one, narrow, additive relaxation to satisfy every item in the task's validation checklist.
