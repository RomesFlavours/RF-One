#!/usr/bin/env python
"""Recognise the WHO of every canonical bank transaction from its own text
(BANK_HISTORICAL_WHO_RECOGNITION_001).

Writes only `bank_occurrence_types` (the existing COUNTERPARTY type, if
missing), `bank_occurrences`, `bank_occurrence_aliases`,
`bank_who_recognitions` and — through the existing exact-name resolver —
`bank_occurrence_suppliers`. Never a WHY, a decision, an allocation, an
invoice match or a financial transaction.

The canonical financial manifest is computed before and after; if it
differs, or the raw/canonical counts move, the run is rolled back.

    python apply_who_recognition.py           # preview (rolled back)
    python apply_who_recognition.py --apply   # write

Never contacts AWS, RDS or any network service.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import func, select

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import historical_staging as staging
from rfone_data_store.bank_reconciliation import who_recognition as wr
from rfone_data_store.database import (
    create_configured_engine,
    create_session_factory,
    get_database_url,
    redact_database_url,
)

import promote_historical_staging as promoter


def financial_controls(session) -> dict:
    return {
        "raw_rows": session.scalar(select(func.count(m.RawBankTransaction.id))),
        "transactions": session.scalar(select(func.count(m.FinancialTransaction.id))),
        "manifest": staging.manifest_sha256(promoter.canonical_db_manifest(session)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write (default: preview)")
    args = parser.parse_args()

    url = get_database_url()
    print(f"Database: {redact_database_url(url)}")
    engine = create_configured_engine(url)
    try:
        with create_session_factory(engine)() as session:
            before = financial_controls(session)
            summary, _results = wr.recognize_transactions(session)
            after = financial_controls(session)

            print(f"transactions        {summary.transactions}")
            for tier in (wr.DETERMINISTIC, wr.STRUCTURAL, wr.PROPOSED, wr.UNRESOLVED):
                count = summary.by_tier.get(tier, 0)
                print(f"  {tier:<14} {count:>6}  {count / max(summary.transactions, 1):6.1%}")
            print(f"occurrences created {summary.occurrences_created} (used {summary.occurrences_used})")
            print(f"aliases created     {summary.aliases_created}")
            print(f"recognitions        created {summary.recognitions_created} · updated "
                  f"{summary.recognitions_updated} · unchanged {summary.recognitions_unchanged}")
            print(f"supplier links      {dict(summary.supplier_outcomes)}")
            print("by family / tier:")
            for (family, tier), count in sorted(summary.by_family_tier.items(), key=lambda kv: -kv[1]):
                print(f"  {family:<26} {tier:<14} {count:>6}")

            if before != after:
                session.rollback()
                print(f"REFUSED — financial controls moved: {before} -> {after}. Rolled back.")
                return 1
            print(f"financial controls unchanged: {after}")

            if not args.apply:
                session.rollback()
                print("Preview only. Re-run with --apply to write.")
                return 0
            session.commit()
            print("APPLIED.")
            return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
