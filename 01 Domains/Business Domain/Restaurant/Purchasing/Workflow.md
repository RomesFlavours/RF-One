# Purchasing Workflow

## Purpose

This document defines the canonical end-to-end Purchasing workflow, from acquisition of a Purchase Document to the point where derived economic knowledge becomes available to the rest of the Restaurant Domain and to Administration.

It replaces a previous version of this document that contained only a single, disconnected "Ingredient Mapping" step with no preceding steps — see `07 Tasks/Reports/PURCHASING_CURRENT_STATE_AUDIT.md`, Section N.5.

---

# Step 1 – Acquire Purchase Document

The Purchase Document is acquired from any supported source (see `DataAcquisition.md`): PDF upload, OCR of a paper document, a Supplier API, XML/EDI, or manual entry.

The original source document is preserved and never modified (`BusinessRules.md`, Rule 2).

---

# Step 2 – Extract Header and Purchase Lines

Header facts (Supplier, document number, issue date, delivery date, destination, customer/account reference, currency, total, payment terms, and other facts genuinely disclosed by the source) are extracted onto the Purchase Document.

Every real line on the source document is extracted as one Purchase Line, with its `line_type` (`PRODUCT`, `SURCHARGE`, or `DISCOUNT`) determined from the source (`EntityDefinitions.md`, "Purchase Line").

Missing or uncertain header/line facts generate a Validation Log entry rather than being invented (`ErrorHandling.md`).

---

# Step 3 – Resolve Supplier / Supplier Products

The Supplier is identified or created.

For each `PRODUCT` Purchase Line, the (Supplier, Supplier Item Code) pair is resolved against Supplier Product memory:

- a known pair reuses the existing Supplier Product and its confirmed classification/mapping;
- a new pair creates/recognizes a candidate Supplier Product.

`SURCHARGE` and `DISCOUNT` lines never resolve to a Supplier Product (`BusinessRules.md`, Rule 3).

---

# Step 4 – Classify PRODUCT Lines

Each `PRODUCT` Purchase Line's Supplier Product is assigned a merchandise/economic classification (`FOOD`, `DRINK`, `SUPPLIES`, `OTHER`) when known, reusing a confirmed classification if the Supplier Product is already known.

When the classification places the Supplier Product in the Food/Ingredient context, Ingredient mapping is additionally pursued (`EntityDefinitions.md`, "Ingredient"; `BusinessRules.md`, Rule 4). Classification and Ingredient mapping are independent decisions — a `SUPPLIES` or `DRINK` classification does not require an Ingredient mapping.

---

# Step 5 – Validate Unknown/Ambiguous Items

Any `PRODUCT` line whose Supplier Product, classification, or Ingredient mapping cannot yet be resolved with confidence is recorded in the Validation Log rather than guessed.

AI may propose a classification or mapping; a human confirms it. Approved knowledge becomes reusable Supplier Product memory (`EntityDefinitions.md`, "Supplier Product"; `AIResponsibilities.md`).

This step addresses identity/interpretation uncertainty. It is distinct from Step 6, which addresses a known Supplier Product whose observed commercial configuration deviates from expectation (`ValidationRules.md`, "Alert vs Validation").

---

# Step 6 – Detect Purchase Configuration Variation and Raise Alerts

For each `PRODUCT` line whose Supplier Product identity is resolved (Step 3), compare its observed commercial configuration (packaging, pack count, pack size, unit, brand, variant, grade — `DataDictionary.md`) against the applicable reference, in priority order:

1. the Supplier Product's Configured Expectation, if one exists;
2. otherwise, the previous purchase of the same Supplier + Supplier Product, as an empirical fallback.

(`BusinessRules.md`, Rule 20; `EntityDefinitions.md`, "Configured Expectation," "Previous Purchase (Fallback Reference)".)

When a meaningful deviation is detected, an Alert is raised (`EntityDefinitions.md`, "Alert"). Because Product identity is already certain at this step, the `PRODUCT` line continues to be recorded normally; the Alert remains **OPEN** in parallel and does not block recording (`BusinessRules.md`, Rule 21).

A responsible User acknowledges the Alert and, when a decision is required, makes a Human Decision: accept this purchase only, accept as an additional alternative, or change the expectation (`BusinessRules.md`, Rule 23). RF-One asks the minimum useful contextual question needed to distinguish these cases rather than inferring intent silently (`EntityDefinitions.md`, "Alert").

The Human Decision is then tested against the Configuration Learning vs Module Capability Gap distinction (`BusinessRules.md`, Rule 24): a representable answer updates the Configured Expectation prospectively; a non-representable but valid operational rule is escalated as a capability gap rather than forced into an incorrect configuration.

Known, coherent `PRODUCT` lines (no applicable deviation) pass through this step automatically, with no Alert and no human involvement — the User's attention is reserved for genuine exceptions (`BusinessRules.md`, Design Principles).

---

# Step 7 – Derive Surcharge/Discount-Adjusted Costs

`SURCHARGE` and `DISCOUNT` lines are allocated proportionally across eligible `PRODUCT` lines to derive each `PRODUCT` line's Effective Product Cost (`BusinessRules.md`, Rules 9, 10, 12).

Effective Product Cost, allocation shares and normalized/per-gram costs are derived on demand; none of them is persisted as canonical stored truth (`DataDictionary.md`, "Persist Facts — Derive Calculations").

---

# Step 8 – Produce Downstream Restaurant Economic Knowledge

For `PRODUCT` lines in the Food/Ingredient context, normalized quantity and cost-per-gram support Recipe costing and Food Cost (`EntityDefinitions.md`, "Ingredient").

For every classified `PRODUCT` line, derived category totals (e.g. Food, Drink, Supplies) become available to the rest of the Restaurant Domain (`BusinessRules.md`, Rule 16).

---

# Step 9 – Expose Derived Category Allocation to Administration

Administration consumes the derived category allocation and other derived economic facts (document totals, payment/reconciliation status) produced by this workflow. Administration does not reinterpret item-level semantics and does not own Purchase Document, Purchase Line, Supplier Product, or Ingredient mapping (`BusinessRules.md`, Rule 17).

---

# Step 10 – Record Physical Receiving

Physical Receiving is a distinct, independent source of Purchase Reality and is not strictly sequential with Steps 1–9: goods may physically arrive before, together with, or after the corresponding Purchase Document is acquired (`BusinessRules.md`, "Three Sources of Purchase Reality"). Whenever it occurs, Receiving is captured through the mobile-first, fallback-capable interaction described in `BusinessRules.md`, "Receiving Is Mobile-First and Fallback-Capable": label-based (scan Invoice, then scan each package/case label) or Order-based (confirm actual quantity against each expected Order item), falling back to manual factual capture when the preferred mode fails.

The Employee records only facts — observed items, quantities, observed configuration, Extra/Unexpected Items (mandatory photo), and damaged quantities (mandatory photo) — and never interprets or classifies a deviation (`BusinessRules.md`, "Receiving Is Observation, Not Decision"). A Receiving Record reaches Completed status once the Employee finishes the session, independently of whether every Receiving Line reconciles cleanly (`BusinessRules.md`, "Receiving Completion Is Independent of Alert Resolution").

---

# Step 11 – Reconcile Order vs Invoice vs Receiving

Whenever more than one of Purchase Order Line, `PRODUCT` Purchase Line, and Receiving Line exists for the same item, RF-One performs the three-way reconciliation (`BusinessRules.md`, "Three-Way Reconciliation"): Order vs Invoice, Invoice vs Receiving, and Order vs Receiving. The result is a set of atomic differences (e.g. `MATCH`, `SHORT`, `EXTRA`, `SUBSTITUTED`, `DAMAGED`, `INVOICE MISMATCH`, `ORDER MISMATCH`, `PACKAGING DEVIATION`, `QUANTITY DEVIATION`), never a single boolean result (`BusinessRules.md`, "Reconciliation Produces Atomic Differences, Not a Boolean Result"). Reconciliation Outcome is derived on demand; it is not persisted as canonical truth.

---

# Step 12 – Raise Purchasing Alerts for Receiving Discrepancies

Every meaningful reconciliation difference from Step 11 — shortage, Extra/Unexpected Item, damaged quantity, substitution, or Invoice/Order mismatch — raises an Alert with Trigger `RECEIVING_DISCREPANCY` (`EntityDefinitions.md`, "Alert," "Alert Trigger"), routed to the responsible Purchasing authority (`BusinessRules.md`, "Receiving Discrepancies Are Routed to the Responsible Purchasing Authority"). Raising this Alert never blocks Receiving completion (Step 10) and never blocks Purchase Recording when the underlying facts are certain.

---

# Step 13 – Responsible Purchasing Decision: Accept or Reject/Return

A responsible Purchasing User acknowledges the Alert and, for each affected quantity (partial acceptance/rejection is supported at quantity level, `BusinessRules.md`, "Partial Quantity"), makes exactly one Human Decision: **ACCEPT** or **REJECT/RETURN** (`BusinessRules.md`, "Purchasing Decision on a Receiving Discrepancy"). An exceptional configuration accepted this way may additionally be routed through the Configured Expectation semantics of Step 6 (one-time acceptance, added alternative, or changed expectation) without duplicating those rules.

---

# Step 14 – Expected Supplier Credit and Reconciliation

If the decision is REJECT/RETURN and the rejected quantity was already invoiced, RF-One creates an Expected Supplier Credit (`BusinessRules.md`, "Expected Supplier Credit"), while preserving the original Receiving observation unchanged — the merchandise is recorded as `Received → Rejected/Returned`, never as `Never received` (`BusinessRules.md`, "Rejection Preserves Historical Reality"). When a later Supplier Purchase Document (typically a Credit Note, or a credit/adjustment on a later Invoice) arrives, RF-One reconciles it against open Expected Supplier Credits, resolving them fully or partially (`BusinessRules.md`, "Partial Supplier Credit," "Credit Reconciliation Against Future Supplier Documents").

---

# Step 15 – Resolve or Keep Open

An Expected Supplier Credit, and the Alert(s) associated with it, close only once the recognized applicable Supplier Credits satisfy the expected amount, or a responsible User explicitly resolves the expectation by another valid decision. Purchase Recording is therefore not necessarily complete when Receiving ends — a supplier issue may remain OPEN for months or years, with no arbitrary expiration (`BusinessRules.md`, "No Arbitrary Expiration for Long-Lived Open Supplier Issues").

---

# Design Principles

- Preserve business reality at every step.
- Reuse confirmed knowledge; never re-interpret a known Supplier Product from zero.
- Persist facts, derive calculations.
- Human validation always prevails over AI proposals.
- Downstream modules and Domains consume derived knowledge; they never redefine item-level semantics.
- Known and coherent `PRODUCT` lines process automatically; a configuration deviation raises an Alert without blocking recording, and the User's attention goes to the exception, not to re-reviewing every line.
- A Human Decision on an Alert changes future operational knowledge — it never rewrites the historical Purchase Line it was raised on.
- Physical Receiving is an independent observation of Reality, reconciled against Order and Invoice rather than assumed equivalent to either.
- Receiving completion and Purchasing Alert resolution are independent; the Employee unloading merchandise is never blocked waiting for a Purchasing decision.
- A rejection/return is recorded alongside the original Receiving observation, never as a rewrite of it.

---

# Purchase Recording vs Purchase Support

This workflow describes **Purchase Recording**: observing Reality and comparing it with what the Restaurant already knows or expects. It does not describe the future **Purchase Support** capability — deciding what, how much and from whom to purchase — which is out of scope for this workflow and is not designed here.
