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

## 10. Purchased output (NORMALIZED/HUMAN, non-goods allocation, Effective Purchased View)

`rfone_data_store/purchasing/repository.py` exposes read-only functions implementing Purchased's own functional model over the unchanged `PurchaseDocument`/`PurchaseLine` schema — no new column, no migration:

- `get_document_functional_status(session, purchase_document_id)` / `get_line_functional_status(session, purchase_line_id)` — **NORMALIZED** unless an OPEN WARNING/ERROR `PurchasingValidationLogEntry` references the document/line, in which case **HUMAN** (Purchased/README.md, "NORMALIZED / HUMAN" — no other functional state is exposed). Derived on demand, same convention as Effective Product Cost/Reconciliation Outcome. **What decides NORMALIZED vs. HUMAN in the first place** (`purchased_bridge._validate_extracted_fields()`, "Improve Generic Parser and Prepare Supplier Format Training"): field completeness/coherence only — supplier recognized, date recognized, total recognized (a $0.00 read counts as unrecognized), no conflicting total-like amounts, line amounts (when any were extracted) arithmetically summing to the total. **The acquisition method (OCR vs. digital-text PDF) is never itself a factor** — an OCR-sourced document with complete, coherent fields is NORMALIZED exactly like a digital-text one; the earlier "OCR → HUMAN by default" rule is retired. Because this is derived solely from `PurchasingValidationLogEntry` (never from `PurchaseDocument`/`PurchaseLine` columns directly), a document a Human Review reviewer has resolved reads NORMALIZED identically to every consumer — there is no raw-column path that could show it as still HUMAN.
- `get_purchased_lines_with_allocation(session, purchase_document_id)` — Purchased/README.md's "Non-goods cost allocation": each PRODUCT line's **effective** amount (source amount, or its latest Human Review correction when one exists — see "Effective Purchased View" immediately below) plus a proportional share of the document's SURCHARGE/DISCOUNT lines' effective total (signed as disclosed), the last line absorbing any rounding remainder so shares reconcile exactly. The raw SURCHARGE/DISCOUNT `PurchaseLine` rows are never deleted or hidden — they remain queryable as source evidence; this function only adds the allocated view on top. The returned dict carries both `source_amount_minor` (raw, immutable) and `effective_amount_minor` (post-correction) per line. A document with no PRODUCT line leaves any non-goods amount unallocated (README's own open edge case).
- `find_purchase_documents_by_number(session, supplier_id, document_number)` — the identity lookup `purchased_bridge.py`'s duplicate/correction handling (§5) is built on.

### Effective Purchased View ("Make Effective Purchased View canonical for all consumers")

**Purchased source evidence (the immutable `PurchaseDocument`/`PurchaseLine` columns) is not the same thing as the Effective Purchased View (that evidence merged with every accepted Human Review correction).** A Business Domain consumer reading a *business* fact — what was the amount, quantity, supplier, date — must read the Effective Purchased View, never the raw columns directly, whenever `purchased_field_corrections` may hold a correction for that document. Reading raw columns directly remains correct only for genuine source-evidence/audit access (e.g. duplicate-identity lookups by `document_number`, provenance/FK reads, Configured-Expectation-deviation detection against fields Human Review does not correct).

The merge itself — "the latest `PurchasedFieldCorrection` per (line, field) overrides the original value; a bare `CORRECT` confirmation does not" — has exactly one implementation, in this module: `resolve_latest_field_corrections()` / `latest_field_corrections()` / `effective_field_value()` / `correction_overrides_value()` (§11's `human_review.py` orchestration layer calls these rather than keeping its own copy). Three canonical business reads are built on it:

- `get_purchased_lines_with_allocation()` above — effective line amounts as the non-goods allocation base;
- `reconcile_receiving_line()` / `raise_receiving_discrepancy_alert()` (Physical Receiving three-way reconciliation, §7) — effective invoice quantity, via the private `_effective_invoice_quantity()` helper, so a Human-Review-corrected quantity is what Restaurant/Purchasing's own reconciliation compares against, not a stale OCR read;
- `human_review.effective_document_view()` (§11) — the header/line display values and re-validation input reviewers and `app.py`'s `/review*` routes see.

`PurchaseDocument`/`PurchaseLine` are never mutated by any of this — the merge is always computed on read.

---

## 11. Supplier + Source Format training foundation

`03 Software/InvoiceIntake/supplier_format_training.py` is a foundation only, per Purchased/README.md's own "Source/format validation and training" (§10 there): a local, append-only record of how many documents have been observed for each (Supplier name, source format) pair and with what NORMALIZED/HUMAN outcome. Its own SQLite file, separate from the canonical database — no migration. It **never** auto-validates a Supplier: a brand new pair always starts `UNTRAINED`, no universal N or accuracy threshold is defined, and nothing in `purchased_bridge.py` reads this store back to influence a document's own NORMALIZED/HUMAN result. Automatic *promotion* remains a deliberate future decision (`set_trust_state()` exists for a human/Product-Owner-driven promotion once a real N/threshold is decided — nothing calls it automatically).

**"Purchased Supplier+Format Training — Phase 1"** began real training against actually-acquired documents (see `07 Tasks/` phase-1 report) and extended this foundation:

- `trust_state` now also has `TRAINING`/`VALIDATED`/`DEGRADED` values. The *only* transition this module makes on its own is a demotion: a `VALIDATED` pair observed again with a materially different `layout_signature` shape is moved to `DEGRADED` automatically (never the reverse — promotion stays human-driven).
- `source_format` is now `"<acquisition method>/<channel>"` (e.g. `"OCR/Direct"`, `"OCR/Instacart"`) — `supplier_format_rules.detect_channel()` distinguishes a direct/in-store document from one arriving through a marketplace/delivery channel (Purchased/README.md's own "Supplier + acquisition method / document format" unit), so e.g. Costco direct and Costco via Instacart are never merged just because the Supplier is the same. No real Instacart document has been acquired yet.
- A new `field_reviews` table/API (`record_field_review`/`list_field_reviews`/`summarize_field_reviews`) durably records the phase-1 Human Review Model's own field-by-field CORRECT/INCORRECT/UNREAD/AMBIGUOUS classifications against real documents — never a silent correction.
- `03 Software/InvoiceIntake/supplier_format_rules.py` (new) is the "generic parser → supplier-format specialization → validation" second stage `purchased_bridge.save_purchase_document()` now runs before resolving/validating a document's header: narrow, real-evidence-only corrections for Prime Line Distributors, Costco Wholesale (direct), and Ben E. Keith Foods (supplier name only) — see that module's own docstring for exactly what and why. Every other Supplier's header is unaffected.

**"Purchased Supplier Training — Phase 2"** closed three gaps Phase 1 found and left open:

- **Multi-invoice PDF splitting** (`03 Software/InvoiceIntake/invoice_splitter.py`, new): one physical source file can now yield more than one `PurchaseDocument` — real Prime Line/Ben E. Keith batches showed "one file = one document" was wrong (see that module's own docstring for the exact real evidence and the boundary/uncertainty algorithm). `purchased_bridge.save_purchase_documents_from_batch()` is the new entry point `mailbox_acquisition/acquisition_service.py`'s automated pipeline now calls instead of `save_purchase_document()` directly; every resulting document still goes through that same unchanged function (dedup, NORMALIZED/HUMAN, Supplier+Format training all included "for free," called once per real invoice). Page/range provenance is encoded in the existing `source_reference` field (e.g. `"batch.pdf#p2-3"`) — no schema change needed for this part. `app.py`'s manual single-document upload/review flow is unchanged (deliberately out of scope — "NON costruire una UI complessa"; splitting matters for the automated mailbox channel these real batches actually arrive through).
- **Canonical Supplier cleanup + alias model** (`models.SupplierAlias`, migration `baf1fe9ef53a`): a new `supplier_aliases` table (Supplier `id` + historical `alias_name` + free-text `source`) is the minimum needed to represent Purchased/README.md's own "canonical Supplier + preserved source provenance" rule. `purchasing.repository.rename_supplier_canonical()` renames `Supplier.name` IN PLACE (same `id` — every existing `PurchaseDocument.supplier_id` FK stays valid, no document moved, no amount changed) and records the old name as an alias before overwriting it; `get_or_create_supplier()` now also resolves a known alias to its Supplier's current canonical name instead of creating a duplicate row, and `purchased_bridge._resolve_supplier_name()` does the same alias-aware matching. `03 Software/RF-One Data Store/fix_supplier_canonical_names.py` is the small, idempotent, checked-in script that actually applied this to the one real dirty name found in Phase 1 ("PRIME LINE DISTRIBUTORS INVOICE" → "Prime Line Distributors") — safe to re-run, and the place to add a future dirty-name fix.
- **Configurable trust threshold** (`supplier_format_training.py`): `DEFAULT_TRUST_THRESHOLD = 5` ("5 documenti consecutivi verificati corretti," Task requirement 11) is a starting default, not a universal rule — `get_trust_threshold()`/`set_trust_threshold()` support a global override plus an optional per-(Supplier, Format) override, stored in a new `trust_thresholds` table in the same local file. `record_observation()` now also tracks `consecutive_correct_count` (reset by any HUMAN outcome) and demotes a `VALIDATED` pair to `DEGRADED` on a real error too, not only a layout change. `is_eligible_for_validation()`/`promote_if_eligible()` implement the actual `TRAINING` → `VALIDATED` path — `promote_if_eligible()` is the one function that promotes, and it is never called automatically anywhere in this codebase (an explicit call IS the "human confirmation / explicit approval" Task requirement 12 asks for); a `DEGRADED` pair must be moved back to `TRAINING` via `set_trust_state()` — a deliberate human step — before it can become eligible again.

**"Purchased Human Review + Supplier Format Training UI"** implements the flow Purchased/README.md's own NORMALIZED/HUMAN diagram always described but nothing built until now — `HUMAN -> review -> correction/confirmation -> NORMALIZED -> training observation`:

- `03 Software/InvoiceIntake/human_review.py` is the orchestration layer. It **never mutates `PurchaseDocument`/`PurchaseLine`** (both remain "Immutable by convention," models.py) — a human's correction/confirmation is its own additive row in a new `purchased_field_corrections` table (`models.PurchasedFieldCorrection`, migration `879dbf90de9b`; classification `CORRECT`/`INCORRECT`/`UNREAD`/`AMBIGUOUS` — the same Human Review Model Phase 1 introduced). `effective_document_view()` merges the latest correction per field on top of the original, untouched columns for display and for re-validation; the original extraction is never lost.
- Re-validation of the effective (corrected) values reuses `purchased_bridge._validate_extracted_fields()` — the exact function used at initial save, never a second parallel check. When it now passes, every OPEN `PurchasingValidationLogEntry` referencing the document (or a line) is closed via the new `close_validation_log_entry()` repository function (`status` OPEN -> CLOSED, `human_decision`/`resolved_at` set — columns that already existed, unused until now), so `get_document_functional_status()` naturally returns NORMALIZED again. No third functional state exists anywhere.
- Every completed review — whatever the outcome — writes one observation (and one field review per corrected field) to `supplier_format_training.py`, the same store/API Phase 1/2 already built. No second manual training step exists.
- A reviewed Supplier correction that differs from the document's original resolution is captured as a new `SupplierAlias` for future recognition (reusing Phase 2's alias-aware `get_or_create_supplier()` — never a needless duplicate Supplier), without rewriting the historical document's own `supplier_id`.
- New repository functions: `record_field_correction`/`list_field_corrections`, `list_human_review_queue` (every PurchaseDocument currently HUMAN, most recent first), `list_sibling_documents` (every other PurchaseDocument from the same source file — `invoice_splitter.py`'s `"<file>#p<range>"` convention — so a 4-invoice batch shows as 4 linked review records), `close_validation_log_entry`.
- **Authority**: `10 System/Identity & Access/README.md` is explicitly frozen ("Do not continue implementation against this area... No Domain currently consumes this foundation"). `03 Software/InvoiceIntake/review_authority.py` is a small, Purchased-local, non-parallel stand-in (VIEWER/REVIEWER/VALIDATOR, three actions) enforced server-side against a Flask session set by a non-authenticating `/review/login` — explicitly documented as a temporary fill-in for when Identity & Access unfreezes, not a security boundary against a malicious actor.
- New `/review`, `/review/<id>`, `/review/<id>/field`, `/review/<id>/complete`, `/review/source/<path>`, `/training`, `/training/validate` routes in `app.py` — `app.py`'s existing `/upload`→`/save` manual flow is unchanged.

---

## 12. Remaining gaps (intentional, out of this task's scope)

- **Ingredient/Recipe/Food Cost persistence** — no `ingredients`/`products`/`specifications` table exists yet; `SupplierProduct.ingredient_id` is an un-constrained placeholder. Explicitly out of scope ("Software boundary": "Do not build recipe costing").
- **Order/Purchase Support module** — `PurchaseOrder`/`PurchaseOrderLine` remain deliberately minimal; nothing creates/manages them beyond what reconciliation needs.
- **`PACKAGING_DEVIATION` reconciliation outcome** — Rule 33's illustrative list includes it, but no current repository code path distinguishes an observed packaging mismatch from `QUANTITY_DEVIATION`/`SUBSTITUTED` at the Receiving reconciliation level (as opposed to the separate, already-implemented `CONFIGURATION_DEVIATION` Alert path for Purchase Lines, Rule 20). A future task can add it without a schema change — `reconciliation.py`'s outcome list is not a rigid enum.
- **Module Capability Gap escalation** — Rule 24's principle is representable (`decide_configuration_alert(..., "MODULE_CAPABILITY_GAP")` records the decision without changing the Configured Expectation), but no routing/ticketing mechanism exists, matching TASK_PURCHASING_002's own explicit non-goal.
- **Credit-matching automation** — `link_supplier_credit()` requires an explicit caller decision about which Expected Supplier Credit a later document satisfies; no automatic/probabilistic matching was built, per this task's explicit instruction.
- **InvoiceIntake restaurant selection** — `purchased_bridge.py` reuses the single existing `Restaurant` row (or creates one placeholder) rather than offering a chooser; InvoiceIntake has no multi-restaurant UI. This is also Purchased/README.md's single-scope-per-invoice rule in practice (one Restaurant reused/created per document) — a genuinely multi-scope source is not detected or handled (README: routed to HUMAN, not designed here).
- **InvoiceIntake Supplier Item Code extraction** — the existing OCR/parser heuristics do not extract a structured supplier item code, so InvoiceIntake-sourced Purchase Lines do not yet exercise Supplier Product memory reuse (`supplier_product_id` stays `NULL`); Physical Receiving and the direct `repository.record_purchase_document()` API already support it fully when a caller supplies `supplier_item_code`.
- **No Purchasing UI, no automatic ordering, no supplier negotiation, no Inventory** — per the task's explicit "Software boundary."
- ~~Human Review corrections are not (yet) visible to other Purchased/Purchasing consumers~~ — **closed by "Make Effective Purchased View canonical for all consumers"**: the merge (`resolve_latest_field_corrections()`/`effective_field_value()`, §10 "Effective Purchased View") moved into `purchasing/repository.py` itself, so `get_purchased_lines_with_allocation()`'s non-goods allocation and `reconcile_receiving_line()`/`raise_receiving_discrepancy_alert()`'s three-way reconciliation quantity now read the same effective values `human_review.effective_document_view()` displays — not just that one InvoiceIntake-side function. Configured-Expectation-deviation detection (`detect_configuration_deviation()`) is unaffected by design: it compares fields (`pack_count`/`pack_size`/`purchase_unit`/`brand`/`product_variant`/`grade`) Human Review has no correction model for.
- **Human Review has no real authentication** — `review_authority.py`'s VIEWER/REVIEWER/VALIDATOR role is self-declared via a non-verifying `/review/login` form, because Identity & Access (the system that would provide a real one) is frozen. See that module's own docstring.
- **Human Review is not reachable via Attention** — Attention Management (`00 Core/ConceptualArchitecture/12_Attention_Management.md`) has no implementation anywhere in RF-One yet; this task deliberately did not build a parallel escalation model, per its own instructions. The review queue (`/review`) is reachable directly for now.
- **`raw_text` is not persisted on `PurchaseDocument`** — Human Review's re-validation therefore cannot re-check conflicting-totals against the original source text (only against the effective header/line values) — a pre-existing gap, not introduced by this task.
