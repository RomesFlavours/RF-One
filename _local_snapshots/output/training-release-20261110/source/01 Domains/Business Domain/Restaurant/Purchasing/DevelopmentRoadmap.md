# Development Roadmap

## Purpose

This document defines the planned evolution of the Purchasing Module.

The roadmap is organized by business capabilities rather than technical implementation.

---

# Version 1.0 - Purchasing Foundation

Objectives:

- Purchase Document acquisition
- OCR document reading
- Supplier management
- Supplier Product management
- Ingredient mapping
- Quantity normalization
- Cost normalization
- Validation Log
- Purchase history
- Physical Receiving (mobile, label-based and Order-based, fallback-capable)
- Order vs Invoice vs Receiving reconciliation and Purchasing Alerts
- Expected Supplier Credit tracking and credit reconciliation

Result:

A complete Purchasing Module capable of transforming supplier documents into standardized purchasing knowledge.

---

# Version 1.1 - API Integration

Objectives:

- Supplier API connectors
- XML import
- EDI import
- Electronic invoice import

Result:

Multiple acquisition channels producing the same logical Purchase Document and the same purchasing knowledge.

---

# First Operational Priority Suppliers

The first real mixed-product suppliers selected for implementation/testing are:

- Ben E. Keith
- Cheney Brothers
- Gordon Food

Reason: their invoices can contain multiple economic product classifications (Food, Drink, Supplies) on the same document, so Supplier/FinancialTransaction recognition alone is insufficient to determine the correct expense allocation — Purchase Line-level classification and Effective Product Cost derivation (`BusinessRules.md`) are required.

BBC Wine is not Priority 1.

This is implementation/roadmap context, not ontology — it does not change any canonical entity or rule defined elsewhere in this module.

---

# Version 1.2 - Purchasing Intelligence

Objectives:

- Automatic order suggestions
- Price trend analysis
- Supplier comparison
- Missing product analysis
- Repeated stock-out analysis
- Cost variation alerts

Result:

Support purchasing decisions using historical knowledge.

---

# Version 1.3 - AI Learning

Objectives:

- Improved OCR
- Improved Ingredient mapping suggestions
- Packaging recognition
- Confidence optimization
- Continuous learning from validated decisions

Result:

Reduction of manual work while preserving human control.

---

# Version 2.0 - Multi-Restaurant

Objectives:

- Centralized purchasing
- Localized deliveries
- Shared Ingredient knowledge
- Restaurant-specific Purchase Documents
- Cross-restaurant purchasing analysis

Result:

Support restaurant groups using a common purchasing knowledge base.

---

# Future Evolution

Possible future capabilities include:

- Predictive purchasing
- Supplier performance scoring
- Seasonal purchasing optimization
- Automatic negotiation support
- Sustainability indicators
- Carbon footprint estimation

---

# Development Principles

- Every version must provide usable business value.
- New capabilities must preserve the existing domain model.
- AI augments human decisions.
- Business knowledge has priority over automation.
- The Purchase Document remains the foundation of the module.