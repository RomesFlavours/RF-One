# Restaurant Domain

## Purpose

The Restaurant Domain defines the business knowledge required to model, operate and continuously improve any restaurant.

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
