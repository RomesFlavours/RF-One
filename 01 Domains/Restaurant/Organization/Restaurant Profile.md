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

### Primary Location integrity (TASK_ORGANIZATION_002)

A Restaurant may have **zero** currently-active primary Locations (a valid transitional state — e.g. between closing an old primary and opening a new one) or **exactly one**, but **never more than one**. "Currently active" means the `RestaurantLocation` row is open (`valid_to IS NULL`).

This is enforced structurally — a partial unique index on `restaurant_locations(restaurant_id)`, scoped to rows where `is_primary = true AND valid_to IS NULL` (`03 Software/RF-One Data Store/DATABASE_SCHEMA.md` §4a). Historical (closed) primary-Location rows are never constrained by it, so changing a Restaurant's primary Location over time remains fully representable without rewriting history:

```text
Winter Park   is_primary=true   valid_to = 2026-08-31   (historical — closed)
Mount Dora    is_primary=true   valid_to = NULL         (current)
```

is valid; two simultaneously open `is_primary=true` rows for the same Restaurant is not.

---

## What Restaurant does not duplicate

Restaurant does not repeat every `Merchant`/`Location` field. It is canonical business identity/context — name, legal name, status, default currency, default timezone — not a second copy of source/runtime facts already owned by `Merchant`/`Location` (see `DATABASE_SCHEMA.md` §2).

---

## Location timezone authority (TASK_ORGANIZATION_002)

**Location**, not Restaurant, is authoritative for the timezone of the operational events (Orders, Shifts, Table Services) that occur at it — necessary once a Restaurant operates Locations in different timezones. `Restaurant.default_timezone` may still exist as a convenience/default (§ "What Restaurant does not duplicate" above), but it never overrides a Location's own `timezone` for that Location's events.

`Location.timezone` is a standard **IANA timezone identifier** (e.g. `America/New_York`), never a raw GMT offset — an offset alone cannot correctly account for Daylight Saving Time or historical timezone-rule changes, both of which an IANA identifier resolves unambiguously for any given instant.

A Location may exist before its timezone is known — `Location.timezone` is nullable, and no value is ever fabricated from geography or any other inference (`03 Software/RF-One Data Store/DATABASE_SCHEMA.md` §2/§4a). A Location with `timezone IS NULL` remains a structurally valid canonical Location; it is simply not yet ready for timezone-sensitive transaction processing (Business Date computation, in particular) until an operator supplies the real value.

---

## Location Business Day Rule (Business Date)

Each **Location** owns the configuration needed to determine its own Business Date (operating day) — not Restaurant globally, because different Locations may operate on different schedules and cutoff rules (`TASK_SALES_002`).

```text
LOCATION
- ...existing Location facts (name, timezone, currency, active) — DATABASE_SCHEMA.md §2...
- operating_day_cutoff_time
```

`operating_day_cutoff_time` is the smallest adequate Business Day Rule: a time-of-day, evaluated in the Location's own `timezone`, below which an event's calendar day is its own Business Date, and at or above which the event's Business Date is the previous calendar day. This is deliberately minimal — Restaurant Profile does not build a general restaurant-scheduling/calendar engine here. Implemented as `locations.operating_day_cutoff_time` (`03 Software/RF-One Data Store/DATABASE_SCHEMA.md` §4a, TASK_ORGANIZATION_002) — nullable, like `timezone`, and never populated from Rome's Flavours' real production data unless a Product-Owner-confirmed value exists; synthetic/test fixtures may use `America/New_York` / `04:00` as illustrative values.

The resulting `business_date` fact itself is defined and owned by the Restaurant Domain's Sales module, on `ORDER` — see `Sales/Restaurant Sales Model.md` § 6a. Restaurant Profile owns only the Location-level configuration input (`operating_day_cutoff_time`, `timezone`); it does not compute or store transactional Business Dates itself. As of TASK_ORGANIZATION_002, `Order.business_date` itself is not yet implemented in the RF-One Data Store schema (a Sales-side implementation gap, tracked by `TASK_SALES_002_REPORT.md` § L) — this section's configuration fields exist and are usable independently of that pending Sales-side column.

A Location's `operating_day_cutoff_time` may change over time. This must never retroactively change a `business_date` already persisted on a historical Order — see `Sales/Restaurant Sales Model.md` § 6a, "Historical immutability."

Once defined here and in Sales, `business_date` is the single canonical concept other transactional Domains (Tips, Payroll, Performance) should reuse rather than duplicating an independent business-date rule of their own — see `Sales/Restaurant Sales Model.md` § 6a, "Cross-domain use."

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
- A Restaurant may be associated with more than one Location, but only over non-overlapping or explicitly marked-primary periods. Primary-Location uniqueness (never more than one currently-open `is_primary=true` row per Restaurant) is enforced structurally — see "Primary Location integrity" above. General overlap validation beyond that specific rule remains an application-level concern, not a blanket database constraint (see `Employee Assignment.md` for the analogous reasoning applied to Employee Assignment's own exact-duplicate rule).
- Operational Areas, Physical Areas and Restaurant Roles belong to exactly one Restaurant's configuration; they are never shared/global across Restaurants (task §13-15).
- No Restaurant Role, Operational Area, or Physical Area is created automatically from Clover source data (see `README.md`, "Relationship to Clover source semantics").

---

## Current runtime state

Exactly one `Restaurant` row exists in the current RF-One Data Store, created because the repository's existing Clover-sourced `Merchant.name` and `Location.name` unambiguously agree (`Rome's Flavours - WP`) — the narrow condition task §19 allows for automatic creation of the Restaurant identity itself. No Operational Area, Physical Area, Restaurant Role, Operational Area ↔ Role combination, or Employee Assignment has been created — that configuration is Product Owner input, not inferred by this task. See `03 Software/RF-One Data Store/RESTAURANT_PROFILE.md`, "Current runtime configuration."
