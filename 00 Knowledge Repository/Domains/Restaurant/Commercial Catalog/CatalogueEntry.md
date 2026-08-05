# Catalogue Entry

## Purpose

A Catalogue Entry represents the publication of an Item within a specific Catalogue Version.

It defines how an Item is presented in a particular commercial context without modifying the Item itself.

The same Item may appear in multiple Catalogue Versions through different Catalogue Entries.

---

# Responsibilities

A Catalogue Entry is responsible for:

- referencing an Item
- defining its visibility
- defining its presentation
- defining its commercial configuration
- defining its position within the Catalogue Version

A Catalogue Entry never defines:

- Item identity
- recipes
- inventory
- purchasing
- sales transactions
- analytics

Those responsibilities belong to other domains.

---

# Typical Attributes

- Entry Id
- Catalogue Version
- Item
- Display Order
- Visibility
- Status
- Featured
- Created At
- Updated At

---

# Relationships

Catalogue

↓

Catalogue Version

↓

Catalogue Entry

↓

Item

Catalogue Entry may also reference:

- Price
- Price List
- Tax Category
- Availability
- Modifier Groups
- Sales Channels

without owning those entities.

---

# Design Principles

The Catalogue Entry acts as the publication layer between the Catalogue Version and the Item.

It allows the same Item to be presented differently across multiple commercial contexts while preserving a single Item definition.

Business rules remain delegated to specialized entities.

---

# Examples

The same "Margherita Pizza" Item may appear as:

- Lunch Menu
- Dinner Menu
- Happy Hour
- Uber Eats
- DoorDash
- Winter Park
- Mount Dora

Each occurrence is represented by a different Catalogue Entry.

---

# Benefits

Catalogue Entry enables:

- multiple commercial presentations
- reusable Items
- independent commercial configurations
- simplified version management
- elimination of duplicated data

---

# Multi Domain

Catalogue Entry belongs to the Commercial Catalogue domain.

It is independent of any specific industry and can be reused by restaurants, retail, hospitality, healthcare, franchises, and future business domains.