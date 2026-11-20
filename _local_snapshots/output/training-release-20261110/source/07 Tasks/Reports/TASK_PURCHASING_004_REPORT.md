# TASK_PURCHASING_004 — REPORT

**Task:** Implement the first persistent RF-One Purchasing data layer, per `07 Tasks/TASK_PURCHASING_004_Implement_Persistent_Purchasing_Data_Store.md` (as given in the task prompt) and the canonical model established, documentation-only, by TASK_PURCHASING_001-003 (`01 Domains/Restaurant/Purchasing/`).
**Scope:** Implementation. No Domain/conceptual model was redesigned.
**Date:** 2026-08-30

---

## A. Summary

Before this task, `01 Domains/Restaurant/Purchasing/` was a complete, exceptionally detailed canonical specification with **no persistence at all** — the only running software, `03 Software/InvoiceIntake/`, wrote reviewed invoices to an Excel workbook using a reduced, ad hoc schema that did not implement `line_type`, Merchandise/Economic Classification, or any of the Alert/Receiving/Expected Supplier Credit model from TASK_PURCHASING_002/003.

Investigation of `03 Software/` (mandatory first step) found that RF-One already has a real, general-purpose persistence layer — `03 Software/RF-One Data Store/` (SQLAlchemy 2.x + Alembic, SQLite by default, already backing Restaurant Profile, Tips, and Payroll). Per the task's explicit instruction ("do not assume a new persistence technology before inspecting what RF-One already uses" / "if RF-One already has a database or migration framework, use it"), this task extends that existing store rather than inventing a second one. No new persistence technology, framework, or dependency was introduced.

Implemented:

- **13 new tables** in `rfone_data_store/models.py`, covering every canonical entity TASK_PURCHASING_001-003 approved (Supplier, Supplier Product, Purchase Order/Line, Purchase Document/Line, Configured Expectation, Receiving Record/Line, Alert, Expected Supplier Credit, its linked credit references, Validation Log), added by one pure-additive Alembic migration (`93df95757d5e`, revises the existing head `47b3d9bb8108`).
- **A repository module** (`rfone_data_store/purchasing/repository.py`) — the only supported way to write Purchasing data — implementing the historical-integrity invariants (immutable Purchase Document/Line and Receiving Line, prospective-only Configured Expectation changes, Supplier Product corrections that never rewrite historical classification), the Configuration-Deviation Alert workflow (Rules 19-24), the Receiving/three-way-reconciliation/Expected-Supplier-Credit workflow (Rules 25-42), and Supplier Product memory.
- **A deterministic reconciliation module** (`rfone_data_store/purchasing/reconciliation.py`) implementing Rule 26/33's atomic-difference comparison — no rule engine, no probabilistic matching.
- **InvoiceIntake integration** (`03 Software/InvoiceIntake/purchasing_bridge.py`): the existing OCR/parser/review flow now saves through this bridge into the canonical store; Excel becomes a secondary, best-effort export/debugging capability only.
- **Tests**: `purchasing_validation.py` (rolled-back structural/repository checks, mirroring the existing `schema_validation.py`/`payroll_validation.py` pattern) plus `test_purchasing_engine.py`, a dedicated entry point implementing all 7 canonical scenarios from the task, including the persistence-survives-restart check, against a disposable local database. All 24 checks pass.
- **Documentation**: `03 Software/RF-One Data Store/PURCHASING.md` (new), README updates across `03 Software/RF-One Data Store/README.md`, `03 Software/InvoiceIntake/README.md`, `03 Software/README.md`, `PROJECT_STATE.md`.
- **`.gitignore` fix**: found (mandatory validation step) that InvoiceIntake's Excel export and two real uploaded supplier documents were already Git-tracked, in violation of the task's "no supplier documents... under Git tracking" instruction. Added ignore rules and untracked those three files (content preserved on disk) — flagged prominently in Section L, since this changes what is currently staged.

No Domain document under `01 Domains/Restaurant/Purchasing/` was modified — the canonical model was implemented faithfully, not redesigned.

---

## B. Persistence technology

**SQLAlchemy 2.x (typed declarative `Mapped`/`mapped_column`) + Alembic migrations, targeting SQLite by default** (`03 Software/RF-One Data Store/rfone_data_store/database.py`) — the exact technology already used for every other canonical RF-One entity (Restaurant Profile, Tips, Payroll). Chosen because:

1. The task explicitly requires inspecting and reusing existing persistence before introducing a new one, and a real one already existed and is under active use (it currently holds ~74 tables and real ingested Clover/Payroll data).
2. It already satisfies every hard requirement the task lists: reproducible schema initialization from the repository (Alembic), a migration path that never deletes populated data, SQLite for local development with a schema designed to also target PostgreSQL later, and an established `.gitignore` discipline for local database files.
3. Introducing a second, parallel persistence mechanism (e.g. a standalone SQLite file under `InvoiceIntake/`) would have violated "do not introduce a large framework merely for this task" in spirit — it would have meant maintaining two schema/migration mechanisms in one repository for no reason.

No new Python dependency was added to `03 Software/RF-One Data Store/requirements.txt` (SQLAlchemy and Alembic were already there). `03 Software/InvoiceIntake/requirements.txt` was left unchanged; its README now documents installing the Data Store's own `requirements.txt` alongside it, since `purchasing_bridge.py` imports `rfone_data_store` directly (via a `sys.path` insert to the sibling `03 Software/RF-One Data Store/` directory — the smallest reversible way to share the package across the two independent prototype folders without turning either into an installable package).

---

## C. Schema / persistent entities

13 tables, added by `migrations/versions/93df95757d5e_add_purchasing_schema.py` (revises `47b3d9bb8108`, the previous head):

| Table | Canonical entity (`Purchasing/EntityDefinitions.md`) |
|---|---|
| `suppliers` | Supplier |
| `purchase_orders` | Purchase Order |
| `purchase_order_lines` | Purchase Order Line |
| `supplier_products` | Supplier Product |
| `purchase_documents` | Purchase Document |
| `purchase_lines` | Purchase Line |
| `configured_expectations` | Configured Expectation |
| `receiving_records` | Receiving Record |
| `receiving_lines` | Receiving Line |
| `purchasing_alerts` | Alert |
| `expected_supplier_credits` | Expected Supplier Credit |
| `supplier_credit_references` | (join/detail) Expected Supplier Credit's `LinkedCreditReferences` |
| `purchasing_validation_log_entries` | Validation Log |

Conventions matched exactly to the existing schema (`03 Software/RF-One Data Store/DATABASE_SCHEMA.md` §0; see `README.md`, "Numeric conventions"): money as integer minor units (cents), quantity as `Numeric(12, 4)`, timestamps `DateTime(timezone=True)`, surrogate integer `id` primary keys, snake_case plural table names / singular PascalCase class names. `PurchasingAlert`/`PurchasingValidationLogEntry` are deliberately prefixed (not the bare `Alert`/`ValidationLog`) because both are cross-cutting concepts (`03 Software/User Interaction Architecture.md` §7.1; the Domain's Validation Log pattern) this task implements only for Purchasing — the bare names are left free for a future cross-module implementation.

Two classes of Domain-mandated closed vocabularies became **structural `CheckConstraint`s** rather than free strings (matching the precedent TASK_PAYROLL_001 set for `employee_compensation_terms`): `PurchaseLine.line_type` (`PRODUCT`/`SURCHARGE`/`DISCOUNT`) and its Rule-3 relationship constraints; `ReceivingLine`'s two mandatory-photo constraints (Rules 29-30); `ReceivingRecord.capture_method`/`status`; `PurchasingAlert.trigger`/`comparison_basis`/`status`; `ExpectedSupplierCredit.status`; `PurchasingValidationLogEntry.severity`/`status`. Fields the Domain leaves open-ended (`Supplier.status`, `PurchaseDocument.status`, `PurchasingAlert.human_decision`) stay free strings, matching the schema's existing convention for evolving classification fields (e.g. `EmployeeAssignment.assignment_source`).

**Derived values with no column anywhere in this schema** (`Purchasing/DataDictionary.md`, "Persist Facts — Derive Calculations"): Effective Product Cost, surcharge/discount allocation shares, category totals, Reconciliation Outcome, Expected Supplier Credit's Recognized/Outstanding Amount. `PurchasingAlert.reconciliation_context` is a descriptive text snapshot only (e.g. `"SHORT: order=10, invoiced=10, received=8"`), explicitly documented in its docstring as never re-read as authoritative.

**One intentional non-FK placeholder**: `SupplierProduct.ingredient_id` is a plain nullable `Integer`, not a real foreign key — no `ingredients`/`products`/`specifications` table exists anywhere in this schema yet (Recipe/Food Cost/Inventory persistence is explicitly out of this task's "Software boundary"). See Section K.

---

## D. Relationships

All relationships the task's "Identity and relationships" section requires are implemented, exactly as the Domain scopes them (required vs. optional):

- Purchase Document → Purchase Lines (`purchase_document_id` FK, required).
- Supplier → Supplier Products (`supplier_id` FK, required) and → Purchase Orders/Documents/Receiving Records.
- Purchase Lines → Supplier Products **when identified** (`supplier_product_id`, nullable; structurally forbidden on `SURCHARGE`/`DISCOUNT` lines).
- Purchase Lines → Ingredient mapping **when validated**: via `SupplierProduct.ingredient_id` (placeholder — Section C) once a real Ingredient entity exists.
- Receiving Record → Receiving Lines (`receiving_record_id` FK, required).
- Receiving Lines → Purchase Lines **when known** (`purchase_line_id`, nullable) and → Purchase Order Lines **when known** (`purchase_order_line_id`, nullable — its absence is, by definition, an Extra/Unexpected Item).
- Alerts → the relevant Purchase/Receiving entities: `purchasing_alerts` carries nullable FKs to `purchase_documents`, `purchase_lines`, `supplier_products`, `purchase_order_lines`, `receiving_records`, `receiving_lines` — populated according to which of the two Triggers raised the Alert (`Purchasing/EntityDefinitions.md`, "Alert Trigger").
- Expected Supplier Credit → its originating Alert (`alert_id`, required) and → the original invoiced Purchase Document/Line (required, since an Expected Supplier Credit only exists once merchandise was already invoiced) → later `SupplierCreditReference` rows (one-to-many, each independently nullable to a crediting Purchase Document/Line since credit evidence is not always line-itemized, Rule 39).

Stable internal identity: every table has its own surrogate integer `id`; `(supplier_id, supplier_code)` is the unique "Supplier Product memory" key (`Purchasing/EntityDefinitions.md`: "the pair (Supplier, Supplier Item Code) identifies a Supplier Product across purchases over time") — enforced as a database `UniqueConstraint`, not merely an application convention, so the repository's get-or-create lookup is race-safe. No Supplier name, invoice number, or free text is ever used as a primary key.

---

## E. InvoiceIntake integration

```text
Supplier document (PDF/photo)
        ↓
ocr_engine.py / parser.py         (unchanged — still heuristic, still human-reviewed)
        ↓
review.html                        (now also lets the reviewer set/correct line_type)
        ↓
purchasing_bridge.save_purchase_document()      ← new
        ↓
rfone_data_store.purchasing.repository.record_purchase_document()
        ↓
RF-One Data Store (SQLite, migrated to head automatically on first save)
```

`app.py`'s `/save` route now calls `purchasing_bridge.save_purchase_document(header, lines, source_file)` as the canonical save, and only then calls the existing `excel_store.save_purchase_document(...)` as a best-effort secondary export wrapped in `try/except` — a locked/open Excel file on Windows can never lose or block the canonical save (the success page shows a note instead of failing). The success page now shows the real `PurchaseDocumentId` assigned by the store.

`review.html` gained one new column, a `line_type` `<select>` (Prodotto/Supplemento/Sconto) per line, pre-selected from a new `purchasing_bridge.guess_line_type()` heuristic (keyword match on "surcharge"/"fee"/"delivery" → `SURCHARGE`, "discount"/"credit"/"rebate"/"bonus" → `DISCOUNT`, else `PRODUCT`) — always human-correctable before saving, consistent with "human validation always prevails." No OCR/parsing logic was changed; `ocr_engine.py` and `parser.py` are untouched.

`purchasing_bridge.py` never invents a fact the OCR/parser did not extract: an unparsed date (`_parse_date`) or amount (`_parse_money_minor`) becomes `None` (Unknown), never a guessed default — the raw string, when present but unparsed, is preserved in `PurchaseDocument.source_provenance` for traceability rather than silently dropped.

**Known limitation, by design, not a defect**: the existing OCR/parser does not extract a structured Supplier Item Code, so InvoiceIntake-sourced `PRODUCT` lines currently save with `supplier_product_id = NULL` (a fully valid, Domain-permitted state — "may/reference a Supplier Product, when supplier product identity is available from the source"). Supplier Product memory reuse is already fully implemented in the repository and is exercised by `record_purchase_document` whenever a caller supplies `supplier_item_code` — it is simply not yet wired from InvoiceIntake's own extraction, since that extraction target does not exist today. See Section K.

---

## F. Historical integrity

Enforced at two layers, per the task's "where practical, enforce this structurally" instruction:

**Structural (database `CheckConstraint`, cannot be bypassed by any future caller):**
- Rule 3 (Supplier Product Relationship Depends on Line Type): a `SURCHARGE`/`DISCOUNT` `PurchaseLine` row with a non-NULL `supplier_product_id` or `economic_classification` is rejected by SQLite itself.
- Rules 29-30 (mandatory photo evidence): a `ReceivingLine` with no `purchase_order_line_id` (Extra/Unexpected Item) and no `photo_evidence`, or with a non-zero `damaged_quantity` and no `photo_evidence`, is rejected by SQLite itself.

Both were verified directly in `purchasing_validation.py` by attempting the invalid insert inside a `SAVEPOINT` and asserting `IntegrityError`.

**Application layer (`rfone_data_store/purchasing/repository.py` — the only supported write path):**
- No function updates a `PurchaseDocument`'s or `PurchaseLine`'s source-fact columns once inserted (only `PurchaseDocument.status`, a business-processing flag, is ever updated).
- No function updates a `ReceivingLine` once inserted. `decide_receiving_alert(..., "REJECT_RETURN", ...)` never touches the Receiving Line — it creates a new `ExpectedSupplierCredit` row instead (Rule 36, verified in Scenario 5: the line still shows `ObservedQuantity = 10`, `DamagedQuantity = 2` after the REJECT/RETURN decision, never rewritten to 8).
- `update_supplier_product_classification` updates only the `SupplierProduct` row. Every `PurchaseLine.economic_classification` already recorded keeps its own value, because each Purchase Line snapshots the Supplier Product's *current* classification at insert time (`record_purchase_document`) rather than reading it live at query time — verified directly in `purchasing_validation.py` ("a later Supplier Product correction never rewrites a historical Purchase Line's own classification").
- `set_configured_expectation` never edits an existing row: it inserts a new `ACTIVE` row and marks the prior one `SUPERSEDED` (mirrors `EmployeeAssignment`'s existing close-and-open temporal pattern elsewhere in this schema) — full approval history preserved, verified in both `purchasing_validation.py` and Scenario 1's Configured Expectation exercise.
- A later Supplier credit document (Credit Note) is always inserted as its own new `PurchaseDocument`/`PurchaseLine` and a new `SupplierCreditReference` row — never merged into, or used to edit, the original rejected Purchase Document/Line (Scenario 6).

---

## G. Receiving and reconciliation

**Persisted**: `ReceivingRecord`/`ReceivingLine` facts — Supplier, related Order/Purchase Document when known, Location, timestamp, Receiving User, capture method, source evidence, completion status; observed item/quantity/configuration, damaged quantity, mandatory photo evidence.

**Derived on demand, never persisted** (`rfone_data_store/purchasing/reconciliation.py`): Reconciliation Outcome. `compute_reconciliation_outcome()` implements Rule 26 (three-way comparison: Order vs Invoice, Invoice vs Receiving, Order vs Receiving) and Rule 33 (atomic differences, not a boolean) deterministically — `MATCH`, `SHORT`, `EXTRA`, `SUBSTITUTED`, `DAMAGED`, `INVOICE_MISMATCH`, `ORDER_MISMATCH`, `QUANTITY_DEVIATION` — verified against Rule 26's four worked examples (short delivery, pre-invoice shorting, unauthorized substitution, invoice/delivery mismatch) and Examples 6-8 in `test_purchasing_engine.py`. No probabilistic or fuzzy identity matching was built, per the task's explicit "do not build a sophisticated reconciliation engine" instruction — item-identity substitution is a simple, caller-supplied boolean (a direct `SupplierProductId` comparison), never guessed.

`ReceivingRecord.status = COMPLETED` may coexist with an `OPEN` `PurchasingAlert` (Rule 32): `complete_receiving()` only ever flips that one `status` column and never inspects, blocks on, or touches any linked Alert — verified in Scenario 3 (Order 10 → Invoice 10 → Receiving 8: `SHORT` is derived, the Receiving Record reaches `COMPLETED`, the Alert stays `OPEN`) and reconfirmed after a full process restart.

---

## H. Expected Supplier Credit

Created only by `decide_receiving_alert(session, alert_id, "REJECT_RETURN", ...)` when the Alert already carries a `purchase_line_id` (i.e. the rejected/returned quantity was already invoiced) — never for an un-invoiced discrepancy. `status` (`OPEN` / `PARTIALLY_RESOLVED` / `RESOLVED`) is recomputed by `link_supplier_credit()` from a live `SUM(applied_amount_minor)` query over `supplier_credit_references`, **never** from a stored Recognized/Outstanding Amount column (neither exists) — `get_expected_supplier_credit_amounts()` is the single function that computes both, on demand, every time.

No code path anywhere imposes an expiration, write-off, or automatic closure (Rule 40) — a credit with `status = OPEN` or `PARTIALLY_RESOLVED` simply stays that way indefinitely until a caller records enough `SupplierCreditReference` rows to satisfy it, or explicitly resolves it another way.

Verified end-to-end in Scenarios 5-6 (`test_purchasing_engine.py`): damaged delivery → 8 ACCEPT / 2 REJECT-RETURN → Expected Supplier Credit opens at €24.00 (Status `OPEN`) → a first Credit Note recognizes €14.00 (Status → `PARTIALLY_RESOLVED`, derived outstanding = €10.00) → a second Credit Note recognizes the remaining €10.00 (Status → `RESOLVED`, derived outstanding = €0.00) — and all of the above is re-confirmed identically after closing the Engine/Session and reopening a fresh one against the same database file ("process restart").

---

## I. Tests

**`rfone_data_store/purchasing_validation.py`** — mirrors the existing `schema_validation.py`/`payroll_validation.py` pattern (synthetic fixture built inside one transaction, always rolled back). Covers: Supplier/Supplier-Product get-or-create idempotency, the classification-snapshot-never-rewritten guarantee, both structural `CheckConstraint`s (SAVEPOINT + expected `IntegrityError`), Configured Expectation supersede-on-change, a Configuration-Deviation Alert raised against a since-superseded expectation, `ACCEPT_THIS_PURCHASE_ONLY` leaving the active expectation untouched, an Extra-Item-without-photo rejection, partial→full Expected Supplier Credit resolution, and a foreign-key-integrity smoke test.

**`test_purchasing_engine.py`** — a dedicated entry point (no `pytest` — this repository has never used it; every existing "test" here is a custom assertion-collecting script run directly, e.g. `test_payroll_engine.py`, and this task follows that established convention rather than introducing a new one) that:

1. Deletes and recreates its own disposable `data/purchasing_test.db` and runs Alembic migrations to head on it — **never** touches `RFONE_DATABASE_URL`/the shared local `data/rfone.db`.
2. Runs `purchasing_validation.run_validation` (rolled back).
3. Persists (commits, for real) all **7 canonical scenarios from the task**:
   - **Scenario 1** (normal Purchase Document, matching lines): a `PRODUCT` line and a `SURCHARGE` line, both preserved verbatim, the `PRODUCT` line correctly classified.
   - **Scenario 2** (unknown Supplier Product): a new Supplier Product is created and exactly one `PurchasingValidationLogEntry` is generated — never guessed.
   - **Scenario 3** (Order 10 → Invoice 10 → Receiving 8): `SHORT` is derived; Receiving reaches `COMPLETED`; the Alert stays `OPEN`.
   - **Scenario 4** (Order 10 → Invoice 8 → Receiving 8): `ORDER_MISMATCH` is derived; Invoice and Receiving match cleanly.
   - **Scenario 5** (10 observed / 8 accepted / 2 rejected): `DAMAGED` is derived; the Receiving observation still shows `10` received / `2` damaged after the REJECT/RETURN decision (never rewritten to 8); an Expected Supplier Credit opens for the invoiced value of the rejected quantity.
   - **Scenario 6** (later Supplier credit document): the original Purchase Document/Line is unchanged; two separate Credit Notes are linked as independent evidence; the expectation moves `OPEN → PARTIALLY_RESOLVED → RESOLVED` exactly as the task's worked example specifies.
   - **Scenario 7** (extra/unexpected item): a Receiving Line with no Purchase Order Line, mandatory photo evidence present, and an `EXTRA` discrepancy Alert raised.
4. Disposes the Engine, opens a **fresh** Engine/Session over the same database file, and re-asserts every scenario's key state (Scenario 1's document/lines, Scenario 3's completed-Receiving-with-open-Alert, Scenario 5/6's Receiving observation and now-`RESOLVED` credit, Scenario 7's open Alert) — the explicit "persisted records survive process restart" requirement.

**Result: 24/24 checks passed** (verified twice during this task, and re-verified after the migration was also applied to a disposable copy of the real populated `data/rfone.db` — see below).

**Additional verification performed:**
- The autogenerated migration was applied, and re-applied, cleanly to a throwaway staging SQLite file built by running all five pre-existing migrations first (baseline through `47b3d9bb8108`), confirming a correct `down_revision` chain.
- The migration was applied to a **disposable copy** of the real, populated `data/rfone.db` (14 MB, real Clover/Payroll data) — succeeded with zero data loss; `inspect_database.py` confirmed all 74 tables (61 pre-existing + 13 new) present, pre-existing row counts unchanged, new Purchasing tables empty. The copy was deleted immediately after; the real `data/rfone.db` was never touched.
- `create_database.py`'s own original TASK_DATABASE_001 fixture (`schema_validation.py`, unrelated to Purchasing) was re-run end-to-end against a fresh disposable file after the model changes: **29/29 checks still pass** — confirms the Purchasing addition did not regress the existing schema.
- `purchasing_bridge.save_purchase_document()` was smoke-tested directly (Gordon Food invoice, one `PRODUCT` line, one `SURCHARGE` line, one blank row) against a disposable database: correct Supplier resolution, correct minor-unit total (`14250` from `"142.50"`), correct parsed `issue_date`, correct line typing, blank row silently skipped.
- All edited/created Python files pass `python -m py_compile`.

Every temporary/disposable database file used for verification above was deleted after use; only `data/purchasing_test.db` (the dedicated, Git-ignored artifact `test_purchasing_engine.py` itself manages) remains on disk.

---

## J. Exact files changed

**Created:**

- `03 Software/RF-One Data Store/migrations/versions/93df95757d5e_add_purchasing_schema.py`
- `03 Software/RF-One Data Store/rfone_data_store/purchasing/__init__.py`
- `03 Software/RF-One Data Store/rfone_data_store/purchasing/repository.py`
- `03 Software/RF-One Data Store/rfone_data_store/purchasing/reconciliation.py`
- `03 Software/RF-One Data Store/rfone_data_store/purchasing_validation.py`
- `03 Software/RF-One Data Store/test_purchasing_engine.py`
- `03 Software/RF-One Data Store/PURCHASING.md`
- `03 Software/InvoiceIntake/purchasing_bridge.py`
- `07 Tasks/Reports/TASK_PURCHASING_004_REPORT.md` (this file)

**Modified:**

- `03 Software/RF-One Data Store/rfone_data_store/models.py` — 13 new ORM classes + `ALL_MODELS` update (Section C).
- `03 Software/RF-One Data Store/README.md` — intro paragraph, Usage, migration history, module-structure table, explicit non-goals.
- `03 Software/InvoiceIntake/app.py` — `/save` route now calls `purchasing_bridge` as the canonical save, `excel_store` as a secondary best-effort export; `line_type` threaded through from the review form.
- `03 Software/InvoiceIntake/templates/review.html` — new `line_type` column/select per line (table header, existing rows, and the JS `addRow()` template for manually added rows).
- `03 Software/InvoiceIntake/templates/success.html` — shows the canonical `PurchaseDocumentId`; notes the Excel copy as secondary, including when it failed.
- `03 Software/InvoiceIntake/excel_store.py` — module docstring only (now documents itself as the secondary export, not the canonical store); no logic changed.
- `03 Software/InvoiceIntake/README.md` — rewritten to describe the RF-One Data Store as the canonical target, Excel as secondary, and the new known limitations.
- `03 Software/README.md` — `InvoiceIntake` row updated; `RF-One Data Store` row added to the module table.
- `PROJECT_STATE.md` — `InvoiceIntake` bullet updated; new `RF-One Data Store` bullet added.
- `.gitignore` — new rules for `InvoiceIntake/uploads/*` (except `.gitkeep`) and `InvoiceIntake/data/*.xlsx` (Section L).

**Untracked from Git (content preserved on disk — Section L):**

- `03 Software/InvoiceIntake/data/PurchaseDocuments.xlsx`
- `03 Software/InvoiceIntake/uploads/1ab27ba6_Invoice 6855.pdf`
- `03 Software/InvoiceIntake/uploads/e0b72c85_20260712_143017.jpg`

**Not touched:** any file under `01 Domains/Restaurant/Purchasing/` (the canonical Domain model was implemented faithfully, not modified); `03 Software/InvoiceIntake/ocr_engine.py`, `parser.py`, `requirements.txt`, `templates/upload.html`, `templates/base.html` (no OCR/parsing/upload-flow change was needed); any file outside `03 Software/`, `.gitignore`, `PROJECT_STATE.md`, and this report.

All pre-existing uncommitted work from TASK_PURCHASING_001-003 and TASK_INTERACTION_001 (visible in `git status` at task start) was left exactly as found.

---

## K. Remaining gaps

Intentional, all explicitly within the task's stated boundaries:

1. **No `Ingredient`/`Product`/`Specification` table.** `SupplierProduct.ingredient_id` is an un-constrained placeholder integer, not a real foreign key, since Recipe/Food Cost/Inventory persistence is explicitly out of this task's "Software boundary" ("Do not build recipe costing... Do not build Inventory").
2. **Order/Purchase Support module not built.** `PurchaseOrder`/`PurchaseOrderLine` are deliberately minimal (Supplier, item, quantity) — nothing creates or manages them beyond what `create_purchase_order()` needs to give reconciliation an "Order" side, per the task's explicit "do not invent a full Order/Purchase Support module."
3. **`PACKAGING_DEVIATION` reconciliation outcome not produced.** Rule 33's illustrative list includes it; the current `reconciliation.py` does not yet distinguish an observed-packaging mismatch from `QUANTITY_DEVIATION`/`SUBSTITUTED` at the Receiving-reconciliation level (the separate, already-fully-implemented `CONFIGURATION_DEVIATION` Alert path for Purchase Lines, Rule 20, does cover packaging deviation at intake time). The outcome list is explicitly not a rigid enum, so this can be added later without a schema change.
4. **No credit-matching automation.** `link_supplier_credit()` requires an explicit caller decision about which Expected Supplier Credit a later document satisfies — no automatic/probabilistic matching was built, per the task's explicit "do not invent probabilistic supplier-credit matching algorithms."
5. **InvoiceIntake has no restaurant-selection UI.** `purchasing_bridge.py` reuses the single existing `Restaurant` row (or creates one clearly-labeled placeholder) rather than offering a chooser — InvoiceIntake was, and remains, a single-flow prototype.
6. **InvoiceIntake does not yet extract a structured Supplier Item Code**, so its Purchase Lines do not yet exercise Supplier Product memory reuse (Section E) — the repository already fully supports it.
7. **No Purchasing UI, automatic ordering, supplier negotiation, or generalized accounting system** — per the task's explicit "Software boundary" list.

None of these represent an unimplemented piece of the *approved* canonical model — each is either explicitly out of this task's scope, or a documented "smallest reversible" implementation choice.

---

## L. Architectural questions

1. **Two previously Git-tracked private files, now untracked (not yet committed).** `03 Software/InvoiceIntake/data/PurchaseDocuments.xlsx` and two real uploaded supplier documents (`uploads/1ab27ba6_Invoice 6855.pdf`, `uploads/e0b72c85_20260712_143017.jpg`) were already committed to this repository before this task, in direct tension with this task's own instruction ("Do not place operational database files, credentials, supplier documents or generated private data under Git tracking"). This task added `.gitignore` rules and ran `git rm --cached` on all three (per "Do not commit," these are staged deletions only — the files themselves are untouched on disk, and no commit was made). **This does not remove them from prior Git history** — a Product Owner decision is needed on whether repository history itself should be rewritten/scrubbed (a materially more invasive operation this task did not perform) or whether "stop tracking going forward" is sufficient.
2. **`SupplierProduct.ingredient_id` as a non-FK placeholder** (Section K.1) is the smallest reversible choice available given no Ingredient table exists yet — flagged for whichever future task implements Ingredient/Recipe persistence to either add the real FK via a new Alembic migration, or confirm this column's shape is still adequate.
3. **Single-Restaurant assumption in `purchasing_bridge.py`** (Section K.5) is a genuine simplification, not a Domain decision — a future multi-restaurant InvoiceIntake UI will need an explicit restaurant-selection mechanism this task did not design.

No contradiction was found between the approved Purchasing model and this implementation — every open item above is a scoping boundary the task itself drew, not a conflict discovered during implementation.

---

## M. Git status

`git rm --cached` was run on the three files listed in Section L.1 (staged removal from tracking only — files remain on disk, nothing was deleted). No other `git add`, `git commit`, or `git push` was run. `git status` at the end of this task shows: the modifications and new files listed in Section J, the three staged deletions from Section L.1, and all pre-existing uncommitted work from TASK_PURCHASING_001-003/TASK_INTERACTION_001 exactly as it was found at the start of this task. Nothing has been committed.
