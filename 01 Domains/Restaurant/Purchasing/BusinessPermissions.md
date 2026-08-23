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
- Modify Ingredient mapping
- Close Validation Log
- Delete business records (if allowed)
- Configure integrations

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