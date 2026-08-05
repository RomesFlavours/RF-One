# Availability

## Purpose

Availability defines when, where and under which conditions an Item may be offered for sale.

It separates commercial availability from inventory and operational constraints, allowing Items to be selectively published across different business contexts.

Availability does not indicate whether an Item is physically in stock.

---

# Responsibilities

Availability is responsible for:

- defining commercial availability
- defining validity periods
- defining scheduling rules
- defining publication constraints
- supporting business-specific availability policies

Availability never defines:

- inventory levels
- stock movements
- purchasing
- recipes
- sales transactions

Those responsibilities belong to specialized domains.

---

# Typical Attributes

- Availability Id
- Name
- Description
- Status
- Effective From
- Effective To
- Created At
- Updated At

---

# Examples

Typical availability definitions include:

- Always Available
- Breakfast
- Lunch
- Dinner
- Weekends Only
- Holidays
- Seasonal
- Limited Time Offer

---

# Relationships

Availability

↓

Catalogue Entry

↓

Catalogue Version

↓

Sales Channels

---

# Design Principles

Availability defines commercial eligibility, not operational capability.

Inventory determines whether an Item can actually be fulfilled.

Business domains determine whether additional operational constraints apply.

---

# Benefits

Availability provides:

- scheduled commercial offerings
- seasonal availability
- time-based menus
- channel-specific publication
- simplified commercial management

---

# Multi Domain

Availability belongs to the Commercial Catalogue domain.

It is independent of any specific industry and may be used by restaurants, retail, hospitality, healthcare and future business domains.