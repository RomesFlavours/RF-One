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
- Suggest Ingredient mappings.
- Normalize quantities.
- Calculate normalized costs.
- Detect anomalies.
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
- Perform irreversible business decisions.

---

# Human Responsibilities

Authorized users are responsible for:

- Creating new Ingredients.
- Approving Ingredient mappings.
- Resolving Validation Log entries.
- Confirming uncertain OCR results.
- Approving business exceptions.

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
- Business exceptions
- Data conflicts
- Ambiguous interpretations

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