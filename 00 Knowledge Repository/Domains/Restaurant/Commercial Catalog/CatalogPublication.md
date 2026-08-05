# Catalog Publication

## Purpose

A Catalog Publication represents the publication of a specific Catalogue Version to a specific Sales Channel.

It controls when and where a Catalogue Version becomes available without modifying the Catalogue itself.

The same Catalogue Version may be published simultaneously to multiple Sales Channels.

---

# Responsibilities

A Catalog Publication is responsible for:

- publishing a Catalogue Version
- identifying the target Sales Channel
- defining the publication period
- defining the publication status

A Catalog Publication never defines:

- Items
- prices
- taxes
- inventory
- purchasing
- sales transactions

Those responsibilities belong to specialized entities and domains.

---

# Typical Attributes

- Publication Id
- Catalogue Version
- Sales Channel
- Status
- Effective From
- Effective To
- Created At
- Updated At

---

# Publication Status

Typical publication states include:

- Draft
- Scheduled
- Published
- Suspended
- Archived

---

# Relationships

Catalog Publication

↓

Catalogue Version

↓

Sales Channel

---

# Design Principles

A Catalog Publication connects a Catalogue Version to a Sales Channel.

It contains no commercial data.

Multiple publications may reference the same Catalogue Version.

Publication history is preserved to support auditing, rollback and analytics.

---

# Benefits

Catalog Publication provides:

- multi-channel publishing
- publication scheduling
- publication history
- independent channel management
- centralized catalogue deployment

---

# Multi Domain

Catalog Publication belongs to the Commercial Catalogue domain.

It is industry independent and may publish commercial catalogues to physical stores, websites, mobile applications, marketplaces, delivery platforms and future sales channels.