#!/usr/bin/env python
"""Load historical roles from a document into Registry (REGISTRY_CLOVER_DEPARTMENTS_001).

    python load_registry_history.py records.json --restaurant-id 1 --merchant-id <Clover WP merchant> \
        --reference "2026 - WP Control Bank.xlsb / Note" [--persist]

records.json: a list of {row, register_id, name, house, role} extracted from the document (only these
fields: no bank, salary or contact data). Dry-run by default; prints the reconciliation report.
Never creates people, never changes names, status, assignments or the current Clover role.
"""
import argparse
import json
import sys

from rfone_data_store import registry_departments as registry
from rfone_data_store.database import create_configured_engine, create_session_factory


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("records")
    parser.add_argument("--restaurant-id", type=int, required=True)
    parser.add_argument("--merchant-id", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--source", default=registry.EXCEL_WP_NOTE)
    parser.add_argument("--persist", action="store_true")
    args = parser.parse_args(argv)
    records = json.load(open(args.records, encoding="utf-8"))
    allowed = {"row", "register_id", "name", "house", "role"}
    records = [{k: v for k, v in r.items() if k in allowed} for r in records]
    with create_session_factory(create_configured_engine())() as db:
        report = registry.load_source_roles(db, records, restaurant_id=args.restaurant_id, merchant_id=args.merchant_id,
                                            source=args.source, reference=args.reference, dry_run=not args.persist)
        if args.persist:
            db.commit()
    print(json.dumps({"mode": "PERSIST" if args.persist else "DRY_RUN", **report.as_dict()}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
