# Catalogue Version

## Purpose

A Catalogue Version represents a specific commercial publication of a Catalogue.

It defines which Items are available, how they are presented, and under which commercial conditions they are offered for a particular business context.

A Catalogue may contain multiple active or inactive versions simultaneously.

---

# Responsibilities

A Catalogue Version is responsible for:

- defining a commercial offering
- selecting the Items included
- organizing Catalogue Entries
- defining the validity period
- supporting commercial versioning
- serving as the source for publication

A Catalogue Version never defines:

- Item identity
- recipes
- inventory
- purchasing
- sales transactions
- analytics

Those responsibilities belong to other domains.

---

# Lifecycle

A Catalogue Version typically progresses through the following states:

- Draft
- Under Review
- Approved
- Published
- Archived

This lifecycle allows commercial changes to be prepared without affecting the currently published version.

---

# Relationships

Catalogue

↓

Catalogue Version

↓

Catalogue Entry

↓

Item

↓

Catalog Publication

---

# Typical Attributes

- Version Id
- Name
- Description
- Status
- Effective From
- Effective To
- Parent Version (optional)
- Created At
- Updated At

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
- Lunch Menu
- Dinner Menu
- Happy Hour

Each version represents an independent commercial publication while sharing the same Item repository.

---

# Design Principles

Catalogue Versions are immutable once published.

Commercial changes should generate a new version rather than modifying an existing published version.

This guarantees:

- complete history
- traceability
- reproducibility
- rollback capability
- auditability

---

# Publication

A Catalogue Version is the only entity that can be published.

The same version may be published simultaneously to multiple Sales Channels.

Likewise, different channels may publish different versions of the same Catalogue.

---

# Design Goals

A Catalogue Version should:

- isolate commercial changes
- support multiple locations
- support multiple sales channels
- support seasonal offerings
- support temporary promotions
- preserve historical consistency

---

# Multi Domain

Catalogue Version belongs to the Commercial Catalogue domain.

It is independent of any specific industry and can be reused by restaurants, retail, hospitality, healthcare, franchises, and future business domains.