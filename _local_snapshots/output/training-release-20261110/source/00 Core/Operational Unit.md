# Operational Unit

**Version:** 5.0
**Status:** Approved
**Module:** Core

---

# Definition

An **Operational Unit (OU)** is the fundamental operational Entity responsible for executing business operations.

It defines the operational boundary within which business activities, resources and responsibilities are managed.

Every operational resource belongs to exactly one Operational Unit.

An Operational Unit may generate revenue, incur costs, provide services or support other Operational Units.

---

# Purpose

Operational Units execute the strategy defined by the Corporate and the standards defined by the Brand.

They transform resources into operational outcomes.

Depending on its specialization, an Operational Unit may:

- Produce goods
- Deliver services
- Generate revenue
- Support other Operational Units
- Manage operational resources
- Operate one physical facility

---

# Position in the Core

```
Corporate
    ↓
Brand
    ↓
Operational Unit
    ↓
Operational Area
```

---

# Operational Boundary

The Operational Unit is the primary operational responsibility boundary.

Every operational activity and resource belongs to exactly one Operational Unit.

Typical resources include:

- Employees
- Equipment
- Inventory
- Processes
- Documents
- Services
- Operational Assets

Domain-specific entities belong to their corresponding Domain.

---

# Relationships

## Corporate

Every Operational Unit belongs to exactly one Corporate.

Corporate owns and governs the Operational Unit.

## Brand

Every Operational Unit belongs to exactly one Brand.

The Brand defines identity and standards.

The Operational Unit executes them.

## Operational Area

Every Operational Unit contains one or more Operational Areas.

Operational Areas partition responsibilities but never exist independently.

---

# Identity

Every Operational Unit has a unique immutable RF-ONE identifier.

Mutable attributes may include:

- Name
- Address
- Manager
- Operating Hours

---

# Physical Location

One Operational Unit represents one physical operational location.

Multiple locations require multiple Operational Units.

---

# Responsibility

Operational Units are responsible for operational execution.

They never define Corporate strategy or Brand identity.

---

# Business Rules

- Every Operational Unit belongs to one Corporate.
- Every Operational Unit belongs to one Brand.
- Every Operational Unit represents one physical location.
- Every operational resource belongs to one Operational Unit.
- Operational Areas cannot exist independently.
- Operational responsibility belongs to the Operational Unit.

---

# Scalability

The Operational Unit model is industry-independent.

Specializations such as Restaurant, Warehouse, Retail Store or Manufacturing Plant belong to their respective Domains without requiring changes to the Core.
