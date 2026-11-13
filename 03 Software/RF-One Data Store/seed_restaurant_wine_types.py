#!/usr/bin/env python
"""Load the initial Restaurant Wines type registry (RESTAURANT_WINES_FIRST_RELEASE_001).

The types come from the Product Owner's `Wine.xlsb`, sheet "Base", column A
(`rfone_data_store.restaurant_wines.wine_types.REFERENCE_WINE_TYPES`, where
the few corrected misspellings are listed).

Repeatable: a type already present under any of its names is never created
again; running it twice changes nothing the second time. Safe dry-run by
default; `--persist` is required to write.

Usage:
    python seed_restaurant_wine_types.py            # dry-run, writes nothing
    python seed_restaurant_wine_types.py --persist
"""

from __future__ import annotations

import argparse
import sys

from rfone_data_store.database import create_configured_engine, create_session_factory, redact_database_url, get_database_url
from rfone_data_store.restaurant_wines.wine_types import seed_reference_wine_types


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--persist", action="store_true", help="Write to the database. Default is dry-run.")
    args = parser.parse_args()

    print(f"Database: {redact_database_url(get_database_url())}")
    print(f"Mode: {'PERSIST' if args.persist else 'DRY_RUN'}")
    session_factory = create_session_factory(create_configured_engine())
    with session_factory() as session:
        report = seed_reference_wine_types(session)
        print(f"Types created:       {len(report.created)}")
        print(f"Names added:         {len(report.names_added)}")
        print(f"Already present:     {len(report.unchanged)}")
        for line in report.names_added:
            print(f"  + {line}")
        for line in report.conflicts:
            print(f"  ! {line}")
        if args.persist:
            session.commit()
            print("Committed.")
        else:
            session.rollback()
            print("Dry-run: nothing written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
