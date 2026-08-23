# Data Dictionary

## Purpose

This document defines the business attributes of every Entity belonging to the Purchasing Module.

It specifies the meaning of each attribute independently from database implementation.

Entity behavior is documented elsewhere.

---

# Supplier

| Attribute | Description |
|------------|-------------|
| SupplierId | Unique internal identifier |
| Name | Supplier business name |
| Status | Active / Inactive |
| AcquisitionMethods | Supported acquisition methods |
| Notes | Optional business notes |

---

# Purchase Order

| Attribute | Description |
|------------|-------------|
| PurchaseOrderId | Unique internal identifier |
| SupplierId | Referenced Supplier |
| OrderDate | Purchase order date |
| Status | Current business status |
| Notes | Optional notes |

---

# Purchase Document

| Attribute | Description |
|------------|-------------|
| PurchaseDocumentId | Unique internal identifier |
| SupplierId | Referenced Supplier |
| PurchaseOrderId | Related Purchase Order (optional) |
| DocumentNumber | Supplier document number |
| DocumentType | Invoice, Receipt, Credit Note, etc. |
| IssueDate | Supplier issue date |
| AcquisitionMethod | OCR, PDF, API, XML, EDI, Manual |
| Currency | Original document currency |
| TotalAmount | Total document amount |
| Status | Business processing status |

---

# Purchase Line

| Attribute | Description |
|------------|-------------|
| PurchaseLineId | Unique internal identifier |
| PurchaseDocumentId | Parent Purchase Document |
| SupplierProductId | Purchased Supplier Product |
| SupplierDescription | Original supplier description |
| Quantity | Original purchased quantity |
| PurchaseUnit | Original purchasing unit |
| UnitPrice | Supplier unit price |
| LineAmount | Original line amount |
| NormalizedQuantity | Quantity expressed in grams |
| CostPerGram | Standardized cost per gram |
| RealIngredientCost | Cost after allocation of document-level charges |
| EffectiveCost | Cost after temporary discounts |

---

# Supplier Product

| Attribute | Description |
|------------|-------------|
| SupplierProductId | Unique internal identifier |
| SupplierId | Referenced Supplier |
| SupplierCode | Supplier product code |
| SupplierName | Original supplier description |
| Packaging | Commercial packaging |
| IngredientId | Referenced Ingredient (optional until validated) |

---

# Product

| Attribute | Description |
|------------|-------------|
| ProductId | Unique internal identifier |
| Name | Canonical product name |
| Category | Business category |

---

# Specification

| Attribute | Description |
|------------|-------------|
| SpecificationId | Unique internal identifier |
| Name | Specification name |
| Type | Specification type |
| Value | Specification value |

---

# Ingredient

| Attribute | Description |
|------------|-------------|
| IngredientId | Unique internal identifier |
| ProductId | Referenced Product |
| Specifications | Set of associated Specifications |
| Density | Used for liquid normalization |
| EdibleYield | Percentage of usable product |
| CookingYield | Percentage after cooking |

---

# Validation Log

| Attribute | Description |
|------------|-------------|
| ValidationId | Unique internal identifier |
| PurchaseDocumentId | Related Purchase Document |
| PurchaseLineId | Related Purchase Line (optional) |
| Severity | Information, Warning or Error |
| Message | Validation message |
| SuggestedAction | AI proposed action |
| HumanDecision | Approved business decision |
| Status | Open, Approved, Rejected, Closed |
| Timestamp | Date and time of creation |

---

# Attribute Principles

- Every Entity has one unique internal identifier.
- Original supplier information is always preserved.
- Internal business identifiers never depend on supplier identifiers.
- Quantities are normalized into grams.
- Historical values are never overwritten.
- Temporary commercial events never modify historical purchasing data.