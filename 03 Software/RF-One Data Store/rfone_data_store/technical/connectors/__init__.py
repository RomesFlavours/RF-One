"""RF-One Technical Connectors — integrations with external systems, usable
by Core and/or Domains (TECHNICAL_CONNECTORS_STRUCTURE_001).

Current connectors:
- `clover` — Clover POS (authentication, API client, live sync/polling,
  historical backfill, idempotent upsert, external identifier/location
  mapping).

Future connectors (ADP, Mercury, OpenTable, Resy, ...) are added as sibling
packages here, each owning only its own external system's technical
integration concerns — never Domain-specific business logic.
"""
