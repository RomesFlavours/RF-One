# Restaurant Domain

For current canonical coverage, placeholders/scaffolding, and planned knowledge areas, see [Roadmap.md](Roadmap.md). For the full business-capability classification (including areas that belong to Strategy, Shared Domain candidates, or Software rather than this Domain), see [../../09 Strategy/04_Business_Capability_Coverage.md](../../09%20Strategy/04_Business_Capability_Coverage.md). For how Restaurant relates to the transversal Domain Personnel Management (Workforce, Selection, Training, Performance, Personnel Decisions) and the remaining transversal Domain candidates (Customer Feedback, Review), see [../Domain Architecture.md](../Domain%20Architecture.md).

## Purpose

The Restaurant Domain defines the business knowledge required to model, operate and continuously improve any restaurant. Restaurant is primarily the **technical/operational Domain**: it owns restaurant-specific operations and technical knowledge, and it must not own a capability merely because that capability happens to be first used in a restaurant. Cross-industry (transversal) Domains consume Restaurant's technical knowledge as an input rather than duplicating it — see [../Domain Architecture.md](../Domain%20Architecture.md).

Its objective is not to reproduce a traditional ERP.

Its objective is to create a knowledge-driven system capable of helping restaurants make better operational, financial and strategic decisions.

The Restaurant Domain provides the business foundation upon which all Restaurant modules are built.

---

# Scope

The Restaurant Domain models every business concept required to manage a restaurant independently from technology, suppliers or external systems.

It includes:

- Ingredients
- Products
- Specifications
- Recipes
- Purchasing
- Inventory
- Production
- Sales
- Food Cost
- Forecasting
- Marketing
- Customer Knowledge

Each capability is implemented as an independent module sharing the same Domain Model.

**Marketing** is listed here as planned business coverage, not as a settled architectural placement. The generic parts of Marketing (campaigns, channels, advertising, social media, promotions, loyalty mechanics, audience targeting) are a future Shared Domain candidate; restaurant-specific marketing execution (menu/product promotion, seasonal offers, local-store execution, guest communication tied to Restaurant Menu/Commercial Catalog) may remain a Restaurant specialization. Which parts move where is not decided by this listing — see `Roadmap.md`, "Cross-Domain candidates and extraction triggers."

The **Commercial Catalog** module (see `Commercial Catalog/`) is canonical Restaurant content today and is not moved by this document. It is recorded as the highest-confidence future Shared Domain extraction candidate — see `Roadmap.md` for the approved extraction trigger.

---

# Domain Philosophy

The Restaurant Domain represents knowledge rather than software functions.

Every entity exists because it represents a business concept.

Implementation details, databases and user interfaces are independent from the Domain.

---

# Architectural Principles

## Canonical Knowledge

Business concepts are represented only once.

Every module references the same canonical entities.

## Modular Architecture

Every business capability is implemented as an independent module.

Modules collaborate through the shared Domain Model rather than through duplicated information.

## Supplier Independence

Business knowledge never depends on suppliers.

Supplier information is translated into canonical restaurant knowledge before becoming available to the rest of the system.

## Human Knowledge

Artificial Intelligence assists users.

Business knowledge always belongs to the restaurant.

Human validation has priority over AI assumptions.

---

# Current Modules

- Purchasing
- Recipes (planned)
- Inventory (planned)
- Production (planned)
- Sales Intelligence (planned)
- Forecasting (planned)
- Marketing (planned)

---

# Relationship with RF-One

The Restaurant Domain is one of the business domains implemented by RF-One.

RF-One provides the architectural framework.

The Restaurant Domain provides restaurant-specific business knowledge.

---

# Design Principles

- Business before technology.
- Knowledge before data.
- One canonical business model.
- Modular evolution.
- AI supports human expertise.
- Preserve business history.
- Preserve business knowledge.
