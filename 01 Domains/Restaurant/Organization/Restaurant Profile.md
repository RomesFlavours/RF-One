# Restaurant Profile

**Version:** 1.0
**Status:** Approved
**Module:** Restaurant Domain / Organization
**Origin:** TASK_RESTAURANT_001

---

## Definition

The **Restaurant** is the canonical business/operational restaurant being modeled by RF-One.

It is **not** merely a Clover Merchant object, and it is **not** merely a canonical `Location` row. Both of those are runtime/source concepts; Restaurant is the business identity they serve.

Example: `Rome's Flavours - WP`.

---

## Position relative to Core and to the existing Restaurant model

`Model/OU-Restaurant.md` already establishes Restaurant as a specialization of Core `Operational Unit` within `Corporate → Brand → Operational Unit`. This document does not replace that conceptual placement. It defines the narrower, concrete profile a Restaurant carries once it exists: which Location(s) it operates from, and the Areas/Roles/Assignments documented alongside it in this `Organization/` section.

---

## Restaurant ↔ Location

A Restaurant may be associated with one or more operational Locations over time. This is deliberately **not** a single foreign key on Restaurant, because:

- a Restaurant's association with a given Location may change (relocation, multi-site consolidation, temporary closure and reopening);
- the current RF-One data has exactly one canonical `Location`, but the model must not assume that remains true.

The relationship is represented by a temporally-bounded association fact — see `03 Software/RF-One Data Store/DATABASE_SCHEMA.md` §4a (`restaurant_locations`) — carrying `valid_from`/`valid_to` and an `is_primary` marker for the currently-operative Location when more than one is valid.

---

## What Restaurant does not duplicate

Restaurant does not repeat every `Merchant`/`Location` field. It is canonical business identity/context — name, legal name, status, default currency, default timezone — not a second copy of source/runtime facts already owned by `Merchant`/`Location` (see `DATABASE_SCHEMA.md` §2).

---

## Relationships

```text
Restaurant
├── (1:N over time) Location            [Restaurant ↔ Location, temporal]
├── (1:N) Operational Area               [Restaurant-configured]
├── (1:N) Physical Area                  [Restaurant-configured]
├── (1:N) Restaurant Role                [Restaurant-configured]
└── (1:N) Employee Assignment            [temporal, per Employee]
```

---

## Business Rules

- A Restaurant is canonical business identity, distinct from any Clover Merchant object.
- A Restaurant may be associated with more than one Location, but only over non-overlapping or explicitly marked-primary periods — overlap/primary-uniqueness enforcement is an application-level concern, not a blanket database constraint (see `Employee Assignment.md` for the analogous reasoning applied to Employee Assignment).
- Operational Areas, Physical Areas and Restaurant Roles belong to exactly one Restaurant's configuration; they are never shared/global across Restaurants (task §13-15).
- No Restaurant Role, Operational Area, or Physical Area is created automatically from Clover source data (see `README.md`, "Relationship to Clover source semantics").

---

## Current runtime state

Exactly one `Restaurant` row exists in the current RF-One Data Store, created because the repository's existing Clover-sourced `Merchant.name` and `Location.name` unambiguously agree (`Rome's Flavours - WP`) — the narrow condition task §19 allows for automatic creation of the Restaurant identity itself. No Operational Area, Physical Area, Restaurant Role, Operational Area ↔ Role combination, or Employee Assignment has been created — that configuration is Product Owner input, not inferred by this task. See `03 Software/RF-One Data Store/RESTAURANT_PROFILE.md`, "Current runtime configuration."
