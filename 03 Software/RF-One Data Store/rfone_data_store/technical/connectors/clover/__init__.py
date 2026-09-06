"""The Clover Technical Connector (TECHNICAL_CONNECTORS_STRUCTURE_001).

Reads Clover's raw/cached evidence (produced by `03 Software/Clover Data
Explorer/`) and maps it into the RF-One canonical schema; also owns Live
Sync (near-real-time polling) and Historical Backfill (`acquisition.py`,
`live_sync.py`). Owns only Clover integration concerns (authentication, API
client, sync/polling, checkpoints, retries, idempotent upsert, external
identifier/location mapping) — never Tip calculation logic, Restaurant
business rules, or any other Domain-specific decision logic. Nothing here is
imported by `rfone_data_store.models` — the dependency runs one way.
"""
