# Dining Intelligence

**Version:** 1.0
**Status:** Approved — conceptual boundary defined; no production schema required by this task
**Module:** Restaurant Domain / Dining Intelligence
**Origin:** TASK_SERVER_PERFORMANCE_001

---

## Purpose

**Dining Intelligence** transforms observed items, beverages, service context and guest/session evidence into structured understanding of how a table is consuming.

```text
observed items, beverages, service context, guest/session evidence
  → Dining Intelligence
    → structured understanding of how a table is consuming
```

This responsibility is broader than Server Performance and must not be buried inside it. **Server Performance consumes Dining Intelligence; it does not own it.**

---

## Naming

Working names considered were `Dining Intelligence` and `Consumption Intelligence`. `Dining Intelligence` is adopted as the canonical name — no existing repository terminology (Restaurant Sales Model, Commercial Catalog, Tips) already used either term, so no collision exists; `Dining Intelligence` reads more naturally alongside the concept it defines first, `Dining Session Profile`. `Consumption Intelligence` may be used informally as a synonym but is not the canonical folder/document name.

---

## Why a separate, shared module — not part of Server Performance

```text
Dining Intelligence   answers: "What kind of consumption situation is this, and what
                       opportunities appear to exist?"
Server Performance     answers: "How effectively is this Server working with the
                       opportunities available?"
Service Copilot        answers: "What should help this Server next, and when?"
```

These three responsibilities are kept distinct. Dining Intelligence's output — Dining Session Profile, Customer Consumption Profile, food/drink correlations — is useful to more than Server Performance:

```text
Server Performance          → Opportunity Capture's "Available Opportunity" input
Service Copilot              → Next Best Action / Next Best Moment context
Personnel Management/Training → what consumption patterns a Server should be trained to recognize
Menu                          → which combinations/items are underperforming or over-performing
Marketing                     → guest segmentation, campaign targeting
Sales analytics                → aggregate consumption trend reporting
Purchasing / Inventory forecasting → where relevant, demand signal
Brand analysis                → cross-Location consumption comparison
```

Placing this responsibility inside Server Performance would force every one of those future consumers to depend on a Personnel-Management-adjacent module for a purely Restaurant-operational capability. Dining Intelligence therefore sits as a sibling Restaurant Domain module, consistent with Restaurant's existing modular pattern (`01 Domains/Restaurant/README.md`, "Current Modules") and closely related to the already-planned, not-yet-built "Sales Intelligence" area recorded in `01 Domains/Restaurant/Roadmap.md` §1 — Dining Intelligence is the consumption-pattern-specific part of that broader future area, not a duplicate of it.

---

## Module map

```text
Restaurant / Dining Intelligence
├── Dining Session Profile.md          the evolving, per-service-occasion consumption understanding
├── Customer Consumption Profile.md    the longitudinal, per-guest consumption understanding
└── Food and Drink Correlations.md     the shared statistical/behavioral relationship-learning responsibility
```

---

## Relationship to Sales

Dining Intelligence creates no competing Sales model. It consumes `Order`, `Order Item`, `quantity`, `Modifier`, `Payment`, `Location`, `business_date` (TASK_SALES_002, approved) as its raw observed evidence and derives consumption structure from them — it never redefines these facts.

## Relationship to Commercial Catalog

Dining Intelligence uses the Commercial Catalog's existing Item/Item Category/Item Group/Brand/Modifier vocabulary (`Commercial Catalog/README.md`) to describe food/drink families — it does not invent a parallel product taxonomy.

## Relationship to Reservation / Guest platforms

Dining Intelligence may eventually consume guest/reservation evidence from systems such as OpenTable, Resy, future reservation/CRM systems, or walk-in identification. **Dining Intelligence is never made dependent on any particular reservation provider** — provider adapters are expected to map into canonical RF-One `Guest`, `Reservation`, and `Dining Session` identity/context concepts. No such integration is implemented by this task — see [Customer Consumption Profile.md](Customer%20Consumption%20Profile.md), "Reservation / Guest sources."

---

## Not implemented by this task

No production schema, database migration, calculation code, correlation/ML model, or ingestion pipeline is built by this task, except where existing documentation already required one (none does). This module is conceptual architecture only.

---

## Related documents

- [../Server Performance/README.md](../Server%20Performance/README.md), [../Server Performance/Opportunity Capture.md](../Server%20Performance/Opportunity%20Capture.md)
- [../Service Copilot/README.md](../Service%20Copilot/README.md)
- [../Sales/Restaurant Sales Model.md](../Sales/Restaurant%20Sales%20Model.md)
- [../Commercial Catalog/README.md](../Commercial%20Catalog/README.md)
- [../Roadmap.md](../Roadmap.md)
- `07 Tasks/Reports/TASK_SERVER_PERFORMANCE_001_REPORT.md` — task that created this module
