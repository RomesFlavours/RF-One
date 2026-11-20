# AI Responsibilities

## Purpose

This document defines the responsibilities, limits and decision authority of Artificial Intelligence within the Purchasing Module.

AI supports human operators but never replaces business ownership.

---

# AI Mission

Artificial Intelligence transforms raw purchasing information into structured business knowledge.

Its objective is to reduce manual work while preserving data integrity and human control.

---

# AI Responsibilities

AI may:

- Read purchasing documents.
- Extract structured data.
- Recognize Supplier Products.
- Suggest merchandise/economic classifications.
- Suggest Ingredient mappings.
- Normalize quantities.
- Calculate normalized costs.
- Detect anomalies.
- Detect commercial configuration deviations against a Configured Expectation or the previous purchase, and propose an Alert (`EntityDefinitions.md`, "Alert"; `BusinessRules.md`, Rules 19–20).
- Propose the contextual question a responsible User should be asked to resolve an Alert (`EntityDefinitions.md`, "Alert"; `BusinessRules.md`, Rule 24).
- Read package/case labels captured during Receiving and extract available facts (Supplier item, product identity, brand/variant, packaging, pack size, unit, quantity), and reconstruct the Receiving Record from them (`BusinessRules.md`, "Receiving Is Mobile-First and Fallback-Capable").
- Derive the three-way reconciliation (Order vs Invoice vs Receiving) and its atomic differences (`BusinessRules.md`, "Three-Way Reconciliation," "Reconciliation Produces Atomic Differences, Not a Boolean Result").
- Detect a Receiving discrepancy (shortage, Extra/Unexpected Item, damaged quantity, substitution, Invoice/Order mismatch) and propose an Alert with Trigger `RECEIVING_DISCREPANCY`, clearly marking any identification proposal as interpretation, not fact (`EntityDefinitions.md`, "Alert").
- Propose an Expected Supplier Credit amount from a rejected/returned quantity and its original invoiced price, and propose a match between a later Supplier document's credit evidence and an open Expected Supplier Credit (`BusinessRules.md`, "Expected Supplier Credit," "Credit Reconciliation Against Future Supplier Documents").
- Estimate confidence levels.
- Prioritize validations.
- Learn from approved human decisions.

---

# AI Limitations

AI must never:

- Modify the original supplier document.
- Create or approve a new Ingredient autonomously.
- Validate a new Supplier Product mapping.
- Rewrite purchasing history.
- Delete business information.
- Close Validation Log entries.
- Close an Alert.
- Create or change a Configured Expectation autonomously.
- Decide whether a deviation is Configuration Learning or a Module Capability Gap — this is a Human Decision (`BusinessRules.md`, Rule 24).
- Decide ACCEPT or REJECT/RETURN on a Receiving discrepancy, classify whether a substitution or an Extra/Unexpected Item is acceptable, or determine economic responsibility for damaged merchandise — these are Human Decisions (`BusinessRules.md`, "Purchasing Decision on a Receiving Discrepancy").
- Rewrite a Receiving observation as if merchandise had never been received (`BusinessRules.md`, "Rejection Preserves Historical Reality").
- Close an Expected Supplier Credit or decide it is resolved.
- Perform irreversible business decisions.

---

# Human Responsibilities

Authorized users are responsible for:

- Creating new Ingredients.
- Approving Ingredient mappings.
- Resolving Validation Log entries.
- Confirming uncertain OCR results.
- Approving business exceptions.
- Acknowledging and deciding Alerts (`EntityDefinitions.md`, "Alert"; `BusinessRules.md`, Rule 22).
- Deciding whether an Alert's resolution updates the Configured Expectation (Configuration Learning) or must be escalated as a Module Capability Gap (`BusinessRules.md`, Rule 24).
- Acknowledging and deciding Receiving Discrepancy Alerts — ACCEPT or REJECT/RETURN — at quantity level (`BusinessRules.md`, "Purchasing Decision on a Receiving Discrepancy," "Partial Quantity").
- Resolving an Expected Supplier Credit, including judging whether a later Supplier document's credit evidence genuinely satisfies it (`BusinessRules.md`, "Expected Supplier Credit," "Credit Reconciliation Against Future Supplier Documents").

Human decisions always override AI suggestions.

---

# Decision Authority

## AI Decisions

AI may decide automatically only when:

- The confidence level satisfies the configured threshold.
- No business knowledge is required.
- The decision is reversible.

Examples:

- OCR extraction
- Unit conversion
- Cost normalization

## Human Decisions

Human validation is always required for:

- New Ingredient creation
- New Supplier Product mapping
- New merchandise/economic classification
- Business exceptions
- Data conflicts
- Ambiguous interpretations
- Alert acknowledgement and decision (accept this purchase only, accept as alternative, change expectation, or escalate a capability gap)
- Configured Expectation creation or change
- Receiving Discrepancy Alert acknowledgement and decision (ACCEPT or REJECT/RETURN, at quantity level)
- Expected Supplier Credit resolution

---

# Continuous Learning

AI improves by observing validated human decisions.

Learning may include:

- OCR improvements
- Product recognition
- Ingredient mapping suggestions
- Packaging recognition

Learning never changes historical business data.

---

# Explainability

Every AI suggestion should be explainable.

Whenever possible, AI should provide:

- Confidence score
- Supporting evidence
- Reason for the suggestion
- Alternative candidates

---

# Design Principles

- AI assists people.
- Human knowledge is authoritative.
- Every AI action must be traceable.
- Every AI suggestion must be reversible.
- AI learns from validated business knowledge.
- Business ownership always remains with the restaurant.