# Operational Area (Restaurant)

**Document Version:** 4.0
**Status:** Approved
**Module:** Core Domain
**Extends:** Operational Area (Core)

---

# Purpose

This document defines how the Core concept of **Operational Area** is specialized within the Restaurant Domain.

Identity, operational boundary and base Business Rules are defined once in `Core/OperationalArea.md` and are fully inherited here without redefinition.

This document adds only the behavior, attributes and examples that are specific to restaurants.

---

# Position in the Domain

```
Corporate
    ↓
Brand
    ↓
Operational Unit
    ↓
Restaurant
    ↓
Operational Area
```

---

# Inherited from Core

A Restaurant Operational Area inherits, without change, from `Core/OperationalArea.md`:

- Unique immutable identity.
- Membership in exactly one Operational Unit (here, one Restaurant).
- The rule that Operational Areas never exist independently.
- Overall operational responsibility remaining with the Operational Unit.

---

# Area Types

Restaurant Operational Areas may be:

## Physical

- Kitchen
- Bar
- Dining Room
- Patio
- Warehouse
- Office
- Receiving Area

## Logical

- Online Orders
- Reservations
- Delivery Dispatch
- Catering Coordination
- Quality Control

## Hybrid

- Drive-Thru
- Take-Out
- Packaging Area
- Production Line

---

# Restaurant-Specific Responsibilities

Typical responsibilities include:

- Food Preparation
- Beverage Production
- Customer Service
- Receiving Goods
- Inventory Management
- Cleaning
- Equipment Maintenance

Responsibilities may evolve without changing identity.

---

# Employees

Employees are assigned to Operational Areas.

Assignments may change over time.

---

# Equipment

Equipment belongs to one Operational Area.

Examples:

- Ovens
- Refrigerators
- POS Stations
- Coffee Machines
- Dishwashers

---

# Capacity

Operational Areas own capacities such as:

- Seating Capacity
- Storage Capacity
- Production Capacity
- Workstation Capacity

Operational Unit (Restaurant) capacity is derived from its Operational Areas.

---

# Availability

Operational Areas determine their own availability based on:

- Staff
- Equipment
- Operating Hours
- Business Rules

Restaurant availability is derived from these values.

---

# Processes

Operational Areas execute business Processes such as:

- Food Preparation
- Order Assembly
- Receiving Inventory
- Cleaning
- Opening Procedures
- Closing Procedures

Processes belong to the business.

---

# Services

Operational Areas support one or more Services without owning them.

Examples:

Kitchen → Dine-In, Delivery, Catering

Bar → Dine-In, Events

---

# Restaurant-Specific Relationships

In addition to the Operational Unit relationship inherited from Core, a Restaurant Operational Area may relate to:

- Employees
- Equipment
- Inventory
- Products
- Recipes
- Documents
- Processes
- Services

Relationships never define identity.

---

# Restaurant-Specific Business Rules

These rules add to, and never override, the Core Business Rules:

- Operational Areas may be physical, logical or hybrid.
- Every operational resource (staff, equipment, inventory) belongs to one Operational Area.
- Capacity belongs to the Operational Area.
- Availability belongs to the Operational Area.
- Processes are executed by Operational Areas.
