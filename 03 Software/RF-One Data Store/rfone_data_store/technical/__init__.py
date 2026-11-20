"""RF-One Technical layer — shared technical infrastructure usable by Core,
Domains, or any other RF-One component (TECHNICAL_CONNECTORS_STRUCTURE_001).

Distinct from both:
- Core (universal RF-One logic/intelligence — concept definitions, not
  implementation), and
- Domains (functional/business logic — Restaurant, Personnel Management,
  Selection, Taxation, Administration, etc.).

`technical.connectors` holds integrations with external systems (Clover,
ADP, Mercury, OpenTable, Resy, ...). A connector under `technical.connectors`
owns ONLY technical integration concerns for its external system
(authentication, API client, sync/polling/webhooks, checkpoints, retries,
idempotent upsert, external identifier/account/location mapping) — never
Domain-specific business rules or decision logic. Domains consume the data a
connector provides; they do not reach into how it was acquired.
"""
