# Purchasing Module

## Purpose

The Purchasing Module transforms heterogeneous purchasing information into a single standardized knowledge model for the Restaurant Domain.

Its purpose is to create a reliable and supplier-independent representation of every purchase performed by the restaurant.

The module is designed around the Purchase Document, regardless of how the information is acquired.

---

## Objectives

The Purchasing Module enables RF-One to:

- Acquire purchasing information from any supplier.
- Normalize heterogeneous purchasing data.
- Calculate the real cost of Ingredients.
- Maintain the purchasing history.
- Compare suppliers objectively.
- Provide reliable purchasing knowledge to the rest of the Restaurant Domain.

---

## Scope

The module manages:

- Suppliers
- Supplier Products
- Purchase Orders
- Purchase Documents
- Purchase Lines
- Ingredient Mapping
- Unit Normalization
- Cost Allocation
- Purchase History

---

## Out of Scope

The module does not manage:

- Inventory
- Production
- Recipes
- Accounting
- Payments
- Warehouse
- Menu Engineering

---

## Fundamental Principle

The Purchase Document is the central entity of the Purchasing Module.

Every purchasing event must be representable as a Purchase Document regardless of its origin.

Supported acquisition sources include:

- Paper invoices
- PDF invoices
- Electronic invoices
- APIs
- XML
- EDI
- Manual data entry

All acquisition sources generate the same logical Purchase Document.

---

## Domain Philosophy

The module is designed around the minimum information that every supplier can provide.

Additional information enriches the model but never changes its structure.

---

## Internal Standard

Every purchasable Ingredient is normalized into:

- grams
- cost per gram

All economic calculations are based on these values.

---

## Ingredient Mapping

Supplier Products are manually associated with Ingredients by an authorized user.

AI may propose mappings but never validates them autonomously.

---

## Validation

RF-One never modifies supplier documents.

Detected inconsistencies are recorded in a Validation Log.

The Purchase Document always remains the legal representation of the purchase.

---

## Artificial Intelligence

AI assists by:

- Reading documents
- Extracting information
- Suggesting mappings
- Detecting anomalies
- Proposing normalizations

AI never performs irreversible business decisions.

---

## Design Principles

- One logical purchasing model.
- Purchase Document is the central entity.
- Every purchase becomes historical knowledge.
- Every Ingredient is normalized into grams.
- Recipes never depend on suppliers.
- Reality is recorded, never rewritten.
- Human validation always prevails.
