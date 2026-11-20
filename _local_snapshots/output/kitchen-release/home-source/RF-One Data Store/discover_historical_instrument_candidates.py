#!/usr/bin/env python
"""Persist the accounts the historical evidence names but the registry lacks
(BANK_HISTORICAL_DATASET_AUDIT_REPAIR_001 §4).

Runs `historical_source.discover_indirect_reference_candidates` over every
preserved raw bank row. A candidate is created only for explicit
account/card phrasing whose last four match no registered Payment
Instrument; it stays UNRESOLVED until a person decides. Nothing else is
written: no Payment Instrument, no lifecycle date, no change to any
FinancialTransaction or raw row.

Idempotent: a second run creates and changes nothing.

    python discover_historical_instrument_candidates.py            # dry run
    python discover_historical_instrument_candidates.py --apply    # commit

Never touches AWS.
"""

from __future__ import annotations

import argparse
import sys

from rfone_data_store.bank_reconciliation import historical_source
from rfone_data_store.database import (
    create_configured_engine,
    create_session_factory,
    get_database_url,
    redact_database_url,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--apply", action="store_true", help="Commit. Without it, rolls back.")
    args = parser.parse_args()

    url = args.database_url or get_database_url()
    print(f"Database URL : {redact_database_url(url)}")
    print(f"Mode         : {'APPLY' if args.apply else 'DRY RUN'}")
    engine = create_configured_engine(url)
    try:
        with create_session_factory(engine)() as session:
            result = historical_source.discover_indirect_reference_candidates(session)
            print(f"Raw rows scanned            : {result.raw_rows_scanned}")
            print(f"References to registered    : {sorted(result.registered_references)}")
            print(f"Created                     : {result.created}")
            print(f"Updated                     : {result.updated}")
            print(f"Unchanged                   : {result.unchanged}")
            print(f"Left alone (direct source)  : {result.skipped}")
            for candidate in historical_source.list_candidates(session):
                print(
                    f"  ··{candidate.last_four}  {candidate.discovery}  "
                    f"count={candidate.occurrence_count}  "
                    f"raw_evidence={candidate.raw_evidence_count}  "
                    f"{candidate.first_seen_date}..{candidate.last_seen_date}  "
                    f"resolution={candidate.resolution or 'UNRESOLVED'}"
                )
            if args.apply:
                session.commit()
                print("COMMITTED")
            else:
                session.rollback()
                print("DRY RUN — rolled back")
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
