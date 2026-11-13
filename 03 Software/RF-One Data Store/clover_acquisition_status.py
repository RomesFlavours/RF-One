#!/usr/bin/env python
"""Read-only status report + explicit recovery for Clover data acquisition
runs (TECHNICAL_CONNECTORS_STRUCTURE_001 / CLOVER_DATA_ACQUISITION_
ARCHITECTURE_001 — "clean recovery/status mechanism").

Historical Backfill and Live Sync both go through the same
`IngestionRun`/`lock_key` guard (`rfone_data_store/technical/connectors/
clover/acquisition.py`). This script reports the latest acquisition run for
a Location — including whether a RUNNING run has exceeded the staleness
threshold and would therefore be auto-recovered on the very next
acquisition attempt anyway — and, with `--reap`, performs that same
recovery immediately rather than waiting for the next attempt.

Location-scoped, not Restaurant-scoped: the Clover connector has no concept
of Restaurant. Find the `location_id` for a Restaurant's Clover Location via
its `RestaurantLocation` row (a Restaurant-Domain join) if you only know the
Restaurant.

Never touches Clover; never touches any table other than `ingestion_runs`.

Usage:
    python clover_acquisition_status.py --location-id 1
    python clover_acquisition_status.py --location-id 1 --reap
"""

from __future__ import annotations

import argparse
import sys

from rfone_data_store.database import create_configured_engine, create_session_factory, get_database_url, redact_database_url
from rfone_data_store.technical.connectors.clover.acquisition import get_latest_acquisition_status, reap_stale_acquisition_run


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--location-id", type=int, required=True)
    parser.add_argument(
        "--reap", action="store_true",
        help="If the latest run is RUNNING and stale, mark it FAILED and release its lock now, "
        "instead of only reporting it.",
    )
    args = parser.parse_args()

    url = get_database_url()
    engine = create_configured_engine(url)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        status = get_latest_acquisition_status(session, location_id=args.location_id)
        if status is None:
            print(f"No acquisition run exists yet for location_id={args.location_id}.")
            return 0

        print(f"Database: {redact_database_url(url)}")
        print(f"Latest acquisition run: id={status.run_id} status={status.status} mode={status.mode_hint or '(unknown)'}")
        print(f"  started_at={status.started_at}  finished_at={status.finished_at}")
        print(f"  notes: {status.notes}")

        if status.status != "RUNNING":
            print("Not currently RUNNING — nothing to recover.")
            return 0

        if not status.is_stale:
            print("RUNNING and within the normal run-time threshold — not stale, left untouched.")
            return 0

        print("RUNNING but STALE (exceeded the max expected run time) — likely an orphaned/interrupted run.")
        if not args.reap:
            print("Run again with --reap to mark it FAILED and release the lock now "
                  "(this also happens automatically the next time any acquisition is attempted).")
            return 1

        # `reap_stale_acquisition_run` commits internally the moment it
        # reaps a row (mirroring the same short-transaction convention the
        # acquisition guard itself uses) — no separate commit needed here.
        reaped_id = reap_stale_acquisition_run(session, location_id=args.location_id)
        if reaped_id is None:
            print("Nothing was reaped (it may have just completed on its own) — re-run to check current status.")
            return 0
        print(f"Recovered: run id={reaped_id} marked FAILED, lock released.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
