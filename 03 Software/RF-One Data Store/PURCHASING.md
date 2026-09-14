# RF-One Data Store — Purchasing

The first persistent implementation of `01 Domains/Business Domain/Restaurant/Purchasing/` (TASK_PURCHASING_001-003, documentation only) — TASK_PURCHASING_004. Software must adapt to that Domain model; nothing here redefines it. Section references below (e.g. "Rule 26") are to `01 Domains/Business Domain/Restaurant/Purchasing/BusinessRules.md` unless stated otherwise.

**Ownership realignment (Align legacy Invoice Intake with Purchased):** `PurchaseDocument`/`PurchaseLine` — §2 below, unchanged — are the Purchase Fact that `01 Domains/Shared Domains/Purchased/README.md` (a Shared Domain) canonically owns: capture + normalize + publish. Restaurant/Purchasing is a **consumer** of this Purchase Fact for its own remaining scope (Purchase Order, Configured Expectation, Physical Receiving, Reconciliation, Alert, Expected Supplier Credit — all unchanged, §3-§8 below) — it is never a prerequisite for creating one. No table was renamed and no migration was added for this realignment: the existing schema already models the Purchase Fact correctly: only *ownership* and a few *behaviors* changed — see the new §5 and §11 below.

---

## 1. Domain boundaries (implementation view)

This implements **Purchase Recording** only — observing Reality (Supplier, Supplier Product, Purchase Document/Line, Configured Expectation/Alert, Physical Receiving, three-way reconciliation, Expected Supplier Credit). **Purchase Support** (deciding what/how much/from whom to buy) is not designed or implemented. Consistent with that, `PurchaseOrder`/`PurchaseOrderLine` are deliberately minimal — Supplier, item, quantity — existing only to give reconciliation an "Order" side (`Purchasing/EntityDefinitions.md`, "Purchase Order Line").

No `Ingredient`/`Product`/`Specification` table exists anywhere in this schema yet — Recipe/Food Cost/Inventory persistence is out of this task's scope (TASK_PURCHASING_004, "Software boundary"). `SupplierProduct.ingredient_id` is an un-constrained placeholder integer for this reason; see "Remaining gaps" below.

---

## 2. Schema (`rfone_data_store/models.py`)

13 tables, added by migration `93df95757d5e` (revises `47b3d9bb8108`):

| Table | Canonical entity | Notes |
|---|---|---|
| `suppliers` | Supplier | Restaurant-scoped (`restaurant_id`), like every other Restaurant-configured entity in this schema. |
| `purchase_orders` / `purchase_order_lines` | Purchase Order / Purchase Order Line | Minimal — see §1. |
| `supplier_products` | Supplier Product | `(supplier_id, supplier_code)` unique — the "Supplier Product memory" key. |
| `purchase_documents` | Purchase Document | Immutable by convention (Rule 2) — only `status` is ever updated in place. |
| `purchase_lines` | Purchase Line | `line_type` structurally constrained to `PRODUCT`/`SURCHARGE`/`DISCOUNT`; two further CheckConstraints make Rule 3 (only `PRODUCT` may carry a Supplier Product or classification) a database guarantee, not just an application convention. |
| `configured_expectations` | Configured Expectation | A change inserts a new `ACTIVE` row and marks the prior one `SUPERSEDED` — never edited in place (Rule 23). |
| `receiving_records` / `receiving_lines` | Receiving Record / Receiving Line | `receiving_lines` has two CheckConstraints making Rules 29-30's mandatory-photo requirement (Extra/Unexpected Item; damaged quantity) structural. |
| `purchasing_alerts` | Alert | Named `PurchasingAlert` (not the bare `Alert`) since Alert is a cross-cutting Interaction Architecture concept this task implements only for Purchasing. |
| `expected_supplier_credits` / `supplier_credit_references` | Expected Supplier Credit / its linked credit evidence | `RecognizedAmount`/`OutstandingAmount` are not columns — always queried on demand from `supplier_credit_references` (Rule 38). |
| `purchasing_validation_log_entries` | Validation Log | Named with a `Purchasing` prefix for the same cross-cutting-naming reason as `PurchasingAlert`. |

Money: integer minor units (cents), matching this schema's existing convention. Quantity: `Numeric(12, 4)`, matching `OrderItem.quantity`. Timestamps: `DateTime(timezone=True)`. Full column-level detail is in `models.py`'s docstrings and `01 Domains/Business Domain/Restaurant/Purchasing/DataDictionary.md`.

**Derived, never a column anywhere in this schema:** Effective Product Cost, surcharge/discount allocation shares, category totals, Reconciliation Outcome, Expected Supplier Credit's Recognized/Outstanding Amount (`Purchasing/DataDictionary.md`, "Persist Facts — Derive Calculations"). `PurchasingAlert.reconciliation_context` is a descriptive text snapshot only, explicitly never read back as authoritative — see its docstring in `models.py`.

---

## 3. Repository (`rfone_data_store/purchasing/repository.py`)

The only supported way to write Purchasing data. No function updates a `PurchaseDocument`/`PurchaseLine`'s source-fact columns, or a `ReceivingLine`, once inserted. A Supplier Product classification correction (`update_supplier_product_classification`) updates only that row — never a `PurchaseLine.economic_classification` already recorded under the prior value, because each Purchase Line snapshots its own classification at insert time rather than reading `SupplierProduct` live. `set_configured_expectation` never edits a row — see §2.

Key functions: `get_or_create_supplier`, `get_or_create_supplier_product` (Supplier Product memory), `update_supplier_product_classification`, `create_purchase_order`, `record_purchase_document`, `set_configured_expectation` / `get_active_configured_expectation`, `get_previous_purchase_line` (Rule 20 fallback), `detect_configuration_deviation` / `decide_configuration_alert` (Rules 20-24), `start_receiving` / `add_receiving_line` / `complete_receiving` (Rule 32 — completion never waits on Alert resolution), `reconcile_receiving_line` (Rule 26/33, delegates to `reconciliation.py`), `raise_receiving_discrepancy_alert` / `decide_receiving_alert` (Rules 29-36), `create_expected_supplier_credit` / `link_supplier_credit` / `get_expected_supplier_credit_amounts` (Rules 37-40), `acknowledge_alert`, `add_validation_log_entry`.

## 4. Reconciliation (`rfone_data_store/purchasing/reconciliation.py`)

Deterministic quantity/identity comparison only — `MATCH`, `SHORT`, `EXTRA`, `SUBSTITUTED`, `DAMAGED`, `INVOICE_MISMATCH`, `ORDER_MISMATCH`, `QUANTITY_DEVIATION` (Rule 33's illustrative list; `PACKAGING_DEVIATION` is not currently produced — see "Remaining gaps"). No probabilistic or fuzzy matching, per the task's explicit "do not build a sophisticated reconciliation engine" instruction. Verified against Rule 26's four worked examples and the canonical Examples 6-8 (`01 Domains/Business Domain/Restaurant/Purchasing/Examples.md`) in `test_purchasing_engine.py`.

---

## 5. InvoiceIntake integration (`03 Software/InvoiceIntake/purchased_bridge.py`)

`InvoiceIntake` (OCR/text extraction → human review → save) saves through this bridge into the RF-One Data Store — the Purchased Purchase Fact, per the ownership realignment above (renamed from `purchasing_bridge.py`; same persistence target, same tables). The source document reaches this bridge either via manual upload (`app.py`) or, as of "Purchased Invoice Intake — Aruba Mailbox Acquisition," via `mailbox_acquisition/` polling Rome's Flavours' operational mailbox (`invoices@romesflavours.com`) — both converge on the exact same pipeline:

```text
Supplier document (PDF/photo — manual upload, or an email attachment
acquired by mailbox_acquisition/)
        ↓
ocr_engine.py / parser.py     (unchanged — still heuristic, still human-reviewed)
        ↓
review.html                    (line_type + document_type, incl. correction types)
        ↓
purchased_bridge.save_purchase_document()   ← duplicate/correction check, then insert
        ↓
rfone_data_store.purchasing.repository.record_purchase_document()
        ↓
RF-One Data Store (this module) — the canonical Purchase Fact Purchased owns
```

`excel_store.py` (and `data/PurchaseDocuments.xlsx`) remain available only as a secondary, best-effort export/debugging capability — `app.py` still calls it after the canonical save, but a failure there (e.g. the workbook open in Excel on Windows) never blocks or loses the canonical save. No OCR/parsing logic changed.

The bridge never invents a fact the OCR/parser did not extract (an unparsed date/amount is passed through as `None`/Unknown, never defaulted). It has no restaurant-selection UI yet — see "Remaining gaps."

`purchased_bridge.py` additionally (Align legacy Invoice Intake with Purchased):

- **Duplicate handling** (Purchased/README.md): before inserting, looks up existing `PurchaseDocument` rows by `(supplier_id, document_number)`. An equivalent re-submission (same total/issue date) returns the existing `PurchaseDocumentId` rather than inserting a second row. A same-identity submission with *different* content is still inserted (nothing is ever silently overwritten) but flagged via a WARNING `PurchasingValidationLogEntry` cross-referencing the earlier document.
- **Supplier-side corrections** (Purchased/README.md): a `document_type` of Credit Memo / Corrected Invoice / Return Credit / Adjustment against an existing `document_number` is treated as a deliberate correction — inserted as its own new row, linked to the original via an INFORMATION (non-blocking) validation log entry, never a rewrite of the original.
- **Functional state**: computes a WARNING validation log entry when the document (OCR-sourced and/or missing a key header field) or a PRODUCT line (no description) looks unreliable — see §11.

---

## 6. Historical integrity

- **Purchase Document / Purchase Line:** `repository.py` exposes no update function for their source-fact columns (only `PurchaseDocument.status`). Enforced at the application layer, same as every other immutable-by-convention entity already in this schema.
- **Purchase Line `line_type`/Supplier Product relationship:** structurally enforced by two CheckConstraints on `purchase_lines` (Rule 3) — a `SURCHARGE`/`DISCOUNT` line with a Supplier Product or classification is rejected by the database itself, not just by convention.
- **Supplier Product correction:** updates `supplier_products` only; every `PurchaseLine.economic_classification` already recorded keeps its original snapshot.
- **Configured Expectation:** a change supersedes the prior row rather than editing it (Rule 23) — full approval history preserved.
- **Receiving Line:** never updated once inserted. A REJECT/RETURN decision never rewrites it (Rule 36) — it creates an `ExpectedSupplierCredit` instead. Mandatory photo evidence (Extra/Unexpected Item, damaged quantity) is structurally enforced by two CheckConstraints on `receiving_lines` (Rules 29-30).
- **Credit evidence:** a later Credit Note/adjustment is inserted as its own `SupplierCreditReference`, never merged into or overwriting the original rejection/Purchase Document.

---

## 7. Receiving and reconciliation

Persisted: `ReceivingRecord`/`ReceivingLine` facts (observed quantity, configuration, damaged quantity, photo evidence, capture method, status). Derived on demand: Reconciliation Outcome (`reconciliation.py`), Effective Product Cost, category totals. `ReceivingRecord.status = COMPLETED` may coexist with an `OPEN` `PurchasingAlert` — `complete_receiving()` only ever flips that one column, regardless of any linked Alert's state (Rule 32) — verified directly in `test_purchasing_engine.py`, Scenario 3.

---

## 8. Expected Supplier Credit

Created only by `decide_receiving_alert(..., "REJECT_RETURN", ...)` when the rejected quantity was already invoiced (the Alert carries a `purchase_line_id`). `status` (`OPEN` / `PARTIALLY_RESOLVED` / `RESOLVED`) is recomputed by `link_supplier_credit()` from a live query over `supplier_credit_references`, never from a cached/stored Recognized or Outstanding Amount. No code path ever auto-closes or expires one (Rule 40) — verified in `test_purchasing_engine.py`, Scenarios 5-6 (partial credit → full resolution, and the same state confirmed again after a process restart).

---

## 9. Usage

```text
python create_database.py       # includes the Purchasing tables (migration 93df95757d5e)
python test_purchasing_engine.py       # structural/repository validation + the 7 canonical
                                 # business scenarios + persistence-survives-restart check
```

`test_purchasing_engine.py` always targets its own disposable `data/purchasing_test.db` (deleted and recreated at the start of every run) — never `RFONE_DATABASE_URL`/the shared local `data/rfone.db`.

---

## 10. Purchased output (NORMALIZED/HUMAN, non-goods allocation)

`rfone_data_store/purchasing/repository.py` exposes three read-only functions implementing Purchased's own functional model over the unchanged `PurchaseDocument`/`PurchaseLine` schema — no new column, no migration:

- `get_document_functional_status(session, purchase_document_id)` / `get_line_functional_status(session, purchase_line_id)` — **NORMALIZED** unless an OPEN WARNING/ERROR `PurchasingValidationLogEntry` references the document/line, in which case **HUMAN** (Purchased/README.md, "NORMALIZED / HUMAN" — no other functional state is exposed). Derived on demand, same convention as Effective Product Cost/Reconciliation Outcome.
- `get_purchased_lines_with_allocation(session, purchase_document_id)` — Purchased/README.md's "Non-goods cost allocation": each PRODUCT line's `source_amount_minor` plus a proportional share of the document's SURCHARGE/DISCOUNT lines' total (signed as disclosed), the last line absorbing any rounding remainder so shares reconcile exactly. The raw SURCHARGE/DISCOUNT `PurchaseLine` rows are never deleted or hidden — they remain queryable as source evidence; this function only adds the allocated view on top. A document with no PRODUCT line leaves any non-goods amount unallocated (README's own open edge case).
- `find_purchase_documents_by_number(session, supplier_id, document_number)` — the identity lookup `purchased_bridge.py`'s duplicate/correction handling (§5) is built on.

---

## 11. Remaining gaps (intentional, out of this task's scope)

- **Ingredient/Recipe/Food Cost persistence** — no `ingredients`/`products`/`specifications` table exists yet; `SupplierProduct.ingredient_id` is an un-constrained placeholder. Explicitly out of scope ("Software boundary": "Do not build recipe costing").
- **Order/Purchase Support module** — `PurchaseOrder`/`PurchaseOrderLine` remain deliberately minimal; nothing creates/manages them beyond what reconciliation needs.
- **`PACKAGING_DEVIATION` reconciliation outcome** — Rule 33's illustrative list includes it, but no current repository code path distinguishes an observed packaging mismatch from `QUANTITY_DEVIATION`/`SUBSTITUTED` at the Receiving reconciliation level (as opposed to the separate, already-implemented `CONFIGURATION_DEVIATION` Alert path for Purchase Lines, Rule 20). A future task can add it without a schema change — `reconciliation.py`'s outcome list is not a rigid enum.
- **Module Capability Gap escalation** — Rule 24's principle is representable (`decide_configuration_alert(..., "MODULE_CAPABILITY_GAP")` records the decision without changing the Configured Expectation), but no routing/ticketing mechanism exists, matching TASK_PURCHASING_002's own explicit non-goal.
- **Credit-matching automation** — `link_supplier_credit()` requires an explicit caller decision about which Expected Supplier Credit a later document satisfies; no automatic/probabilistic matching was built, per this task's explicit instruction.
- **InvoiceIntake restaurant selection** — `purchased_bridge.py` reuses the single existing `Restaurant` row (or creates one placeholder) rather than offering a chooser; InvoiceIntake has no multi-restaurant UI. This is also Purchased/README.md's single-scope-per-invoice rule in practice (one Restaurant reused/created per document) — a genuinely multi-scope source is not detected or handled (README: routed to HUMAN, not designed here).
- **InvoiceIntake Supplier Item Code extraction** — the existing OCR/parser heuristics do not extract a structured supplier item code, so InvoiceIntake-sourced Purchase Lines do not yet exercise Supplier Product memory reuse (`supplier_product_id` stays `NULL`); Physical Receiving and the direct `repository.record_purchase_document()` API already support it fully when a caller supplies `supplier_item_code`.
- **No Purchasing UI, no automatic ordering, no supplier negotiation, no Inventory** — per the task's explicit "Software boundary."
