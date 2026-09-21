#!/usr/bin/env python
"""Seed the canonical RF-One restaurant accounting catalog
(BANK_CANONICAL_ACCOUNTING_CATALOG_001).

The ordinary deployment already installs the catalog: migration
`b8d3f1a72c64` seeds it, so a fresh or production database has it after
`alembic upgrade head` with no manual step. This command exists for the
cases a migration does not cover — checking what a database currently
holds, and re-seeding one that was migrated before the catalog existed.

Idempotent and non-destructive: a code already present with the same name
is left untouched, and a code present with a DIFFERENT name aborts the
whole run rather than redefining an account that historical decisions may
reference.

    python seed_canonical_accounting_catalog.py            # report only
    python seed_canonical_accounting_catalog.py --apply    # seed

Never contacts AWS, RDS or any network service: it operates on whatever
`RFONE_DATABASE_URL` resolves to.
"""

from __future__ import annotations

import argparse
import sys

from rfone_data_store.bank_reconciliation import canonical_catalog
from rfone_data_store.bank_reconciliation import deterministic_rules
from rfone_data_store.database import (
    create_configured_engine,
    create_session_factory,
    get_database_url,
    redact_database_url,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true",
        help="write the catalog (default is a read-only report)",
    )
    args = parser.parse_args()

    url = get_database_url()
    print(f"Database: {redact_database_url(url)}")
    print(f"Catalog : {canonical_catalog.CATALOG_VERSION}")
    print()

    engine = create_configured_engine(url)
    session_factory = create_session_factory(engine)
    try:
        with session_factory() as session:
            rows = canonical_catalog.catalog_rows()
            print(f"Canonical definition: {len(rows)} account(s)")
            print(f"  Profit & Loss : {len([r for r in rows if r['Statement Type'] == 'PROFIT_LOSS'])}")
            print(f"  Balance Sheet : {len([r for r in rows if r['Statement Type'] == 'BALANCE_SHEET'])}")
            for node_type in canonical_catalog.NODE_TYPES:
                print(f"  {node_type:<16}: {len([r for r in rows if r['Node Type'] == node_type])}")
            print(f"  Contra          : {len([r for r in rows if r['Is Contra'] == 'TRUE'])}")
            print(f"  Review-sensitive: {len([r for r in rows if r['Review Sensitive'] == 'TRUE'])}")

            if not args.apply:
                present = 0
                missing = 0
                for row in rows:
                    if canonical_catalog.by_code(session, row["Code"]) is None:
                        missing += 1
                    else:
                        present += 1
                print()
                print(f"In this database: {present} present, {missing} missing.")
                print("Report only. Re-run with --apply to seed.")
                return 0

            outcome = canonical_catalog.seed(session)
            session.commit()
            print()
            print(f"Created   : {len(outcome.created)}")
            print(f"Unchanged : {len(outcome.unchanged)}")

            problems = canonical_catalog.validate_hierarchy(session)
            if problems:
                print()
                print("HIERARCHY PROBLEMS:")
                for problem in problems:
                    print("  -", problem)
                return 1
            print("Hierarchy validated: statement sides consistent, no cycle, no duplicate code.")

            semantic = canonical_catalog.semantic_problems(session)
            if semantic:
                print()
                print("SEMANTIC PROBLEMS:")
                for problem in semantic:
                    print("  -", problem)
                return 1
            print(
                "Semantics validated: node type, normal balance, contra and review sensitivity "
                "match the canonical definition."
            )

            # BANK_RESTORE_STRUCTURAL_WHY_BASELINE_001 — the canonical
            # PURPOSES RF-One recognises, seeded alongside the accounts they
            # point at. Vocabulary only: no Who, no rule, no transaction.
            why_outcome = deterministic_rules.seed_structural_reasons(session)
            session.commit()
            print()
            print(f"Structural Why vocabulary: {len(why_outcome.created)} created, "
                  f"{len(why_outcome.unchanged)} unchanged")
            for rule in deterministic_rules.structural_why_baseline():
                print(f"  {rule.why_code:<26} -> {rule.account_code}")
            return 0
    except ValueError as exc:
        print()
        print(f"REFUSED: {exc}")
        return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
