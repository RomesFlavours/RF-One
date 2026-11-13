#!/usr/bin/env python
"""Run the Clover Live Sync loop (TECHNICAL_CONNECTORS_STRUCTURE_001 /
CLOVER_DATA_ACQUISITION_ARCHITECTURE_001).

Near-real-time acquisition of Clover data (Payments, Orders, Shifts,
Refunds, Employees/Tenders/Devices) for Tips, and in the future Server
Copilot, Server Performance, Sales, and other Domains — see
`rfone_data_store/technical/connectors/clover/live_sync.py` for the full
design (checkpoint-based window, idempotent upsert, shared concurrency
guard with Historical Backfill).

Location-scoped, not Restaurant-scoped: the Clover connector has no concept
of Restaurant. Find the `location_id` for a Restaurant's Clover Location via
its `RestaurantLocation` row (a Restaurant-Domain join) if you only know the
Restaurant.

Usage:
    python clover_live_sync.py --location-id 1
        # runs forever, polling every 15s (default)
    python clover_live_sync.py --location-id 1 --interval-seconds 10
    python clover_live_sync.py --location-id 1 --once
        # a single cycle then exit — for cron/Task Scheduler invocation
"""

from __future__ import annotations

import sys

from rfone_data_store.technical.connectors.clover.live_sync import main

if __name__ == "__main__":
    sys.exit(main())
