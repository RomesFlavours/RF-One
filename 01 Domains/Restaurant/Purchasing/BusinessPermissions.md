# Security & Permissions

## Purpose

This document defines the authorization model of the Purchasing Module.

The objective is to protect business knowledge while allowing every user to perform only the operations required by their role.

---

# Security Principles

- Authentication identifies the user.
- Authorization defines what the user may do.
- Every business action must be auditable.
- Permissions are granted, never assumed.

---

# Business Roles

## Administrator

May configure the Purchasing Module and manage permissions.

---

## Purchasing Manager

May:

- Create Purchase Orders
- Review Purchase Documents
- Approve validations
- Manage Suppliers

---

## Chef

May:

- Create Ingredients
- Approve Ingredient mappings
- Review Supplier Products

---

## Operator

May:

- Upload documents
- Correct OCR results
- Process assigned validation tasks

---

## Receiving User

A mobile-scoped role, narrower than general Purchasing access, limited to an assigned organizational scope/Location (`03 Software/User Interaction Architecture.md`, Section 4, "Authorization Model," Section 6, "Authorization Scope").

May:

- Perform Mobile Receiving for the assigned scope
- Capture Receiving evidence (label scans, photos)
- Record actual quantities against an Order
- Record Extra/Unexpected Items and damaged quantities, with mandatory photo
- Complete a Receiving session

May not, by default:

- Access full Purchasing Web pages
- Configure Suppliers or Supplier Products
- Perform cost analysis
- Approve deviations or resolve Alerts
- Change Configured Expectations

This is an illustrative role shape, not a concrete customer-specific permission set (`BusinessRules.md`, "Receiving Authorization May Be Narrower Than Purchasing Access").

---

## AI

May:

- Read documents
- Extract data
- Suggest mappings
- Detect anomalies

AI never owns business permissions.

---

# Protected Operations

The following operations require explicit authorization:

- Create Ingredient
- Approve or modify merchandise/economic classification
- Modify Ingredient mapping
- Close Validation Log
- Delete business records (if allowed)
- Configure integrations
- Decide ACCEPT or REJECT/RETURN on a Receiving Discrepancy Alert
- Resolve an Expected Supplier Credit

---

# Audit Requirements

The system shall record:

- User
- Date and Time
- Operation
- Previous Value
- New Value
- Reason (when applicable)

Audit records are immutable.

---

# Design Principles

- Least privilege.
- Human ownership of business knowledge.
- Full traceability.
- AI never replaces authorization.