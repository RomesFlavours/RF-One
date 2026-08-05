# Sales Channel

## Purpose

A Sales Channel represents a commercial channel through which Catalogue Versions are published and made available to customers.

It defines where commercial offerings are exposed without determining pricing, inventory, or sales behavior.

A Sales Channel may publish one or more Catalogue Versions.

---

# Responsibilities

A Sales Channel is responsible for:

- identifying a commercial sales channel
- supporting catalogue publication
- providing commercial visibility
- defining channel identity

A Sales Channel never defines:

- prices
- taxes
- inventory
- purchasing
- sales transactions
- business rules

Those responsibilities belong to specialized entities and domains.

---

# Typical Attributes

- Sales Channel Id
- Name
- Description
- Status
- Created At
- Updated At

---

# Examples

Physical Store

- Winter Park
- Mount Dora

Online

- Website
- Mobile App

Delivery

- Uber Eats
- DoorDash
- Deliveroo

Marketplace

- Amazon
- Walmart Marketplace

Other

- Self-Service Kiosk
- Call Center

---

# Relationships

Sales Channel

↓

Catalog Publication

↓

Catalogue Version

---

# Design Principles

A Sales Channel identifies where commercial offerings are published.

It does not determine commercial behavior.

Business rules remain independent from the Sales Channel itself.

---

# Benefits

Sales Channels provide:

- multi-channel publishing
- centralized catalogue management
- consistent commercial visibility
- simplified integrations
- AI-friendly channel analytics

---

# Multi Domain

Sales Channel belongs to the Commercial Catalogue domain.

It is industry independent and may represent physical, online or third-party commercial channels across restaurants, retail, hospitality, healthcare and future business domains.