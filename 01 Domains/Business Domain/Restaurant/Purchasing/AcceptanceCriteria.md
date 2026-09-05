# Acceptance Criteria

## Purpose

This document defines the business acceptance criteria for the Purchasing Module.

A feature is considered complete only when it satisfies these criteria.

---

# General Acceptance Criteria

The module shall:

- Produce the same logical Purchase Document regardless of the acquisition source.
- Preserve every original supplier value.
- Never modify the original supplier document.
- Normalize every purchasable Ingredient into grams.
- Calculate normalized cost per gram.
- Maintain complete purchasing history.
- Record every anomaly in the Validation Log.

---

# Purchase Document

Acceptance Criteria:

- Every purchase generates exactly one Purchase Document.
- Every Purchase Document contains one or more Purchase Lines.
- Original supplier information is preserved.

---

# Purchase Line

Acceptance Criteria:

- Every real line on the source document is preserved as a Purchase Line with a `line_type` of `PRODUCT`, `SURCHARGE`, or `DISCOUNT`.
- Only `PRODUCT` lines may reference a Supplier Product or carry a merchandise/economic classification; `SURCHARGE` and `DISCOUNT` lines never do.

---

# Supplier Product

Acceptance Criteria:

- Unknown Supplier Products are created automatically.
- Existing Supplier Products are reused, together with their confirmed classification and mapping.
- A merchandise/economic classification is required before Ingredient mapping is attempted.
- Manual Ingredient mapping is required before Food/Ingredient-context business use; it is not required for Supplies/Drink/Other classifications.

---

# Merchandise / Economic Classification and Ingredient Mapping

Acceptance Criteria:

- AI may suggest classifications and mappings.
- Human approval is mandatory for both.
- Approved classifications and mappings become permanent until explicitly changed, and never rewrite historical Purchase Lines already recorded under a prior classification.

---

# Cost Calculation

Acceptance Criteria:

- Quantities are normalized into grams as a derived measure.
- SURCHARGE and DISCOUNT lines are proportionally allocated across eligible PRODUCT lines.
- Supplier Price and Effective Product Cost are derived correctly; neither is stored as canonical truth (see `DataDictionary.md`, "Persist Facts — Derive Calculations").

---

# Validation

Acceptance Criteria:

- Original supplier documents are never discarded.
- Validation Log entries are created whenever required.
- Every validation decision is auditable.

---

# Configured Expectation and Alert

Acceptance Criteria:

- A commercial configuration change (e.g. packaging) on a `PRODUCT` Purchase Line never creates a new Ingredient/Product by itself.
- Variation is detected against the Supplier Product's Configured Expectation when one exists, otherwise against the previous purchase of the same Supplier + Supplier Product.
- A deviation from the previous-purchase fallback never becomes an approved Configured Expectation by itself.
- When Product identity is certain, a detected deviation raises an Alert and Purchase Recording continues; the Purchase Line is not blocked.
- An Alert remains Open until acknowledged and, when a decision is required, until a Human Decision is recorded.
- Choosing "accept this purchase only" leaves the Configured Expectation unchanged; the next purchase matching the prior baseline does not raise a new deviation Alert.
- Choosing "accept as alternative" adds an approved configuration without removing the existing one.
- Choosing "change expectation" updates the Configured Expectation prospectively and never rewrites the historical Purchase Line that triggered the Alert.
- A representable Human Decision updates the Configured Expectation (Configuration Learning); a non-representable but valid operational rule is escalated as a Module Capability Gap rather than forced into an incorrect configuration.
- Alert is never recorded as a Validation Log entry, and a Validation Log entry is never treated as an Alert.

---

# Physical Receiving and Reconciliation

Acceptance Criteria:

- Order, Invoice and Physical Receiving are preserved as three distinct representations and are never collapsed into one.
- Receiving supports both label-based and Order-based capture, and label-based capture falls back to Order-based/manual capture when the label cannot be read.
- A Receiving session can be completed by the Employee even when a shortage, Extra/Unexpected Item, damaged quantity, packaging deviation, or Invoice mismatch remains unresolved.
- An Extra/Unexpected Item requires a mandatory photograph and always raises a Purchasing Alert; the Employee is never asked to classify or accept it.
- A damaged quantity requires a mandatory photograph and always raises a Purchasing Alert; the Employee is never asked to determine economic responsibility.
- Reconciliation (Order vs Invoice vs Receiving) produces atomic differences (e.g. MATCH, SHORT, EXTRA, SUBSTITUTED, DAMAGED, INVOICE MISMATCH, ORDER MISMATCH, PACKAGING DEVIATION, QUANTITY DEVIATION), never a single boolean result.
- Acceptance/rejection decisions operate at quantity level; a Purchase Line or Receiving Line is never forced into an all-or-nothing outcome.
- A responsible Purchasing User's decision on a Receiving Discrepancy Alert is exactly ACCEPT or REJECT/RETURN.
- A REJECT/RETURN decision never erases or rewrites the original Receiving observation; the merchandise remains recorded as received, then rejected/returned — never as "never received."

---

# Expected Supplier Credit

Acceptance Criteria:

- An Expected Supplier Credit is created only when already-invoiced merchandise is rejected/returned.
- An Expected Supplier Credit may remain Open indefinitely; no automatic expiration is applied.
- A partial Supplier credit reduces the outstanding amount without closing the expectation; the outstanding amount is derived, not persisted as canonical truth.
- A later Supplier Purchase Document's credit evidence is reconciled against open Expected Supplier Credits; an omitted, incorrect, misapplied, or partial correction keeps the expectation Open and generates/maintains a Purchasing Alert.
- Credit Note remains the single canonical credit-document type; no second credit-document ontology is introduced.

---

# Artificial Intelligence

Acceptance Criteria:

AI shall:

- Read documents.
- Extract purchasing data.
- Detect anomalies.
- Suggest merchandise/economic classifications.
- Suggest Ingredient mappings.
- Detect commercial configuration deviations and propose an Alert with a contextual question.
- Read Receiving labels and reconstruct the Receiving Record.
- Derive three-way reconciliation results and propose a Receiving Discrepancy Alert.
- Propose an Expected Supplier Credit amount and propose a match with a later Supplier document's credit evidence.

AI shall not:

- Modify the original supplier document.
- Approve Ingredient mappings.
- Rewrite purchasing history.
- Close an Alert.
- Create or change a Configured Expectation.
- Decide ACCEPT or REJECT/RETURN on a Receiving discrepancy, or determine economic responsibility for damage.
- Rewrite a Receiving observation as if merchandise had never been received.
- Close or resolve an Expected Supplier Credit.
- Perform irreversible business decisions.

---

# Completion Criteria

The Purchasing Module is considered complete when:

- All reference examples produce the expected results.
- All business rules are satisfied.
- All validation rules are enforced.
- Human approval workflow functions correctly.
- Purchasing knowledge is available to the remaining Restaurant Domain modules.

---

# Success Principle

The success of the Purchasing Module is measured by the quality of the purchasing knowledge it produces, not by the technology used to acquire the data.