# Item Group

## Purpose

An Item Group represents a logical collection of Items created for a specific commercial purpose.

Unlike Item Categories, Item Groups do not classify Items.

They organize Items dynamically for merchandising, marketing, promotions and commercial presentation.

An Item may belong to multiple Item Groups simultaneously.

---

# Responsibilities

An Item Group is responsible for:

- grouping related Items
- supporting commercial organization
- simplifying merchandising
- supporting promotions
- improving customer navigation

An Item Group never defines:

- Item identity
- prices
- taxes
- inventory
- recipes
- purchasing
- sales transactions

Those responsibilities belong to specialized entities and domains.

---

# Typical Attributes

- Group Id
- Name
- Description
- Display Order
- Status
- Created At
- Updated At

---

# Relationships

Item Group

↓

Items

↓

Catalogue Entries

↓

Catalogue Versions

---

# Examples

Seasonal

- Summer Specials
- Winter Menu

Marketing

- Best Sellers
- New Arrivals
- Chef's Recommendations

Promotions

- Happy Hour
- Family Bundle
- Lunch Specials

Business

- Signature Dishes
- Premium Selection
- Limited Edition

---

# Design Principles

Item Groups are flexible.

They do not classify Items.

They simply organize Items for specific commercial objectives.

The same Item may belong to any number of Item Groups.

---

# Benefits

Item Groups provide:

- reusable commercial collections
- flexible merchandising
- simplified promotions
- AI-friendly grouping
- no duplication of Items

---

# Multi Domain

Item Group belongs to the Commercial Catalogue domain.

It is industry independent and may be used by restaurants, retail, hospitality, healthcare and future business domains.