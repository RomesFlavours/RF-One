# Data Acquisition

## Purpose

This document defines how Purchase Documents are acquired — the Invoice Intake capability of the Purchasing Module — regardless of source technology or supplier.

The objective of every acquisition channel is identical:

Generate the same logical Purchase Document and Purchase Lines, and the same purchasing knowledge.

The source technology is irrelevant once the Purchase Document has been created. Invoice Intake is a capability of this module, not a separate Domain module — see `README.md`.

---

# Supported Sources

Today:

- PDF upload (manually reviewed)
- Paper Invoices (OCR)
- Manual Data Entry

Future:

- IMAP mailbox (supplier sends invoices by email)
- Supplier API / token-based integration
- XML
- EDI
- Structured portal exports

Future acquisition methods may be added without changing the domain model. A source is provenance, not structure — two Purchase Documents from the same Supplier carrying the same commercial facts must produce the same canonical representation regardless of which channel produced them.

---

# Integration Principle

Every external source must produce exactly the same logical Purchase Document.

No acquisition method introduces new business entities.

External systems enrich information but never modify the Purchasing Module.

---

# Minimum Required Output

Every integration must provide enough information to create:

- Purchase Document
- Purchase Lines
- Supplier
- Supplier Products

If information is missing, RF-One records the missing data in the Validation Log.

---

# Optional Information

When available, integrations may also provide:

- Purchase Order references
- Taxes (preserved as source facts — see `OpenQuestions.md`, "Invoice Tax Treatment — OPEN")
- Delivery date / destination
- Customer/account reference, payment terms
- Discounts and Surcharges (extracted as `DISCOUNT`/`SURCHARGE` Purchase Lines — see `EntityDefinitions.md`)
- Credit Notes
- Attachments

Optional information enriches the Purchase Document but never changes its structure. Extract what the source knows; do not invent what the source does not know.

---

# Relationship to Physical Receiving

Physical Receiving (`EntityDefinitions.md`, "Receiving Record," "Receiving Line") is a distinct capture, not a Purchase Document acquisition channel: it does not itself produce a Purchase Document, and a Receiving Record may exist with no Purchase Document yet acquired, or vice versa. Receiving capture (mobile, label-based or Order-based) is documented in `BusinessRules.md`, "Receiving Is Mobile-First and Fallback-Capable," and `Workflow.md`, Step 10.

---

# Error Handling

Integration failures never invalidate the original supplier document.

Missing or uncertain information generates Validation Log entries for human review.

---

# Artificial Intelligence

AI may assist integrations by:

- Reading unstructured documents
- Extracting structured data
- Detecting inconsistencies
- Suggesting missing mappings

AI never changes supplier information.

---

# Design Principles

- One domain model.
- One logical Purchase Document.
- Source-independent architecture.
- Preserve supplier information.
- Validation before correction.
- Human authority over business decisions.