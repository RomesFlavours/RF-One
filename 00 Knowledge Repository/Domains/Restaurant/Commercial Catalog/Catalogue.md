# Catalogue

## Purpose

The Catalogue represents the commercial structure through which an organization defines, organizes and publishes its sellable offerings.

It is the central component of the Commercial Catalog domain.

The Catalogue does not store commercial data itself. Instead, it organizes and exposes Items through versioned publications that can be distributed across different sales channels, locations and business contexts.

---

# Responsibilities

A Catalogue is responsible for:

- organizing commercial offerings
- grouping Items into a coherent commercial structure
- managing Catalogue Versions
- supporting multiple business contexts
- providing the source for commercial publications

A Catalogue never defines:

- item prices
- taxes
- recipes
- inventory
- purchasing
- sales
- analytics

Those responsibilities belong to specialized domains.

---

# Design Principles

The Catalogue represents a logical commercial container.

All commercial information is exposed through Catalogue Versions.

Every business context should reference a Catalogue Version rather than modifying the Catalogue itself.

The Catalogue remains stable while its published versions evolve over time.

---

# Relationships

Catalogue

↓

Catalogue Version

↓

Catalogue Entry

↓

Item

---

# Examples

Restaurant Commercial Catalogue

Retail Commercial Catalogue

Hospitality Commercial Catalogue

Franchise Commercial Catalogue

---

# Versioning

A Catalogue may contain multiple versions simultaneously.

Examples include:

- Winter Park
- Mount Dora
- Uber Eats
- DoorDash
- Website
- Catering
- Christmas Menu
- Happy Hour

Each version may expose different Items, prices, visibility rules and commercial configurations while sharing the same underlying Item repository.

---

# Publication

A Catalogue is not directly published.

Only Catalogue Versions may be published to one or more Sales Channels.

This guarantees:

- historical consistency
- version traceability
- multi-location support
- multi-channel support
- staged deployments
- rollback capability

---

# Design Goals

The Catalogue should:

- eliminate data duplication
- support unlimited commercial versions
- remain independent from business domains
- provide a single source of truth for commercial publishing

---

# Multi Domain

The Catalogue belongs to the Commercial Catalog domain.

Restaurant, Retail, Hospitality and future domains reuse the same Catalogue model while defining their own domain-specific behaviors independently.