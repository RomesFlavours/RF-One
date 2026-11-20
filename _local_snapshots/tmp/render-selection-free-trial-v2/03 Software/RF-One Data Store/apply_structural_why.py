#!/usr/bin/env python
"""Apply deterministic structural WHY to the canonical bank history
(BANK_HISTORICAL_DETERMINISTIC_WHY_EXPERTIZATION_001).

Only transactions whose own text (plus RF-One's instrument registry)
proves or strongly structurally determines the purpose receive a RULE
decision. WHO never decides WHY; no allocation is written; a human
decision is never overwritten.

Guards, checked after the run and before committing:

* the canonical financial manifest and the raw/canonical counts;
* a hash of every `financial_transactions` column EXCEPT the current-
  decision pointer (`explanation_id`, and `updated_at` which moves with
  it) — the one column the approved decision model is meant to update.

    python apply_structural_why.py           # preview (rolled back)
    python apply_structural_why.py --apply   # write

Never contacts AWS, RDS or any network service.
"""

from __future__ import annotations

import argparse
import hashlib
import sys

from sqlalchemy import func, select, text

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import historical_staging as staging
from rfone_data_store.bank_reconciliation import structural_why as sw
from rfone_data_store.database import (
    create_configured_engine,
    create_session_factory,
    get_database_url,
    redact_database_url,
)

import promote_historical_staging as promoter

DECISION_POINTER_COLUMNS = frozenset({"explanation_id", "updated_at"})


def financial_facts_sha256(session) -> str:
    columns = [c.name for c in m.FinancialTransaction.__table__.columns
               if c.name not in DECISION_POINTER_COLUMNS]
    digest = hashlib.sha256()
    for row in session.execute(text(
            f"SELECT {', '.join(columns)} FROM financial_transactions ORDER BY id")):
        digest.update(repr(tuple(row)).encode())
    return digest.hexdigest()


def financial_controls(session) -> dict:
    return {
        "raw_rows": session.scalar(select(func.count(m.RawBankTransaction.id))),
        "transactions": session.scalar(select(func.count(m.FinancialTransaction.id))),
        "manifest": staging.manifest_sha256(promoter.canonical_db_manifest(session)),
        "financial_facts": financial_facts_sha256(session),
        "allocations": session.scalar(select(func.count(m.BankTransactionAllocation.id))),
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
            summary, _results = sw.apply_structural_why(session)
            session.flush()
            after = financial_controls(session)

            total = max(summary.transactions, 1)
            print(f"transactions        {summary.transactions}")
            for tier in (sw.DETERMINISTIC, sw.STRONG_STRUCTURAL, sw.UNRESOLVED):
                count = summary.by_tier.get(tier, 0)
                print(f"  {tier:<18} {count:>6}  {count / total:6.1%}")
            print("by rule:")
            for rule, count in summary.by_rule.most_common():
                print(f"  {rule:<32} {count:>6}")
            print("by WHY:")
            for why, count in summary.by_why.most_common():
                print(f"  {why:<32} {count:>6}")
            print("unresolved families:")
            for family, count in summary.unresolved_families.most_common():
                print(f"  {family:<32} {count:>6}")
            print(f"decisions created {summary.decisions_created} · unchanged "
                  f"{summary.decisions_unchanged} · human skipped {summary.skipped_human} · "
                  f"conflicts {len(summary.conflicts)} · refused destinations "
                  f"{len(summary.refused_destination)}")

            if before != after or summary.conflicts or summary.refused_destination:
                session.rollback()
                print(f"REFUSED — controls {before} -> {after}; conflicts {summary.conflicts[:5]}; "
                      f"refused {summary.refused_destination[:5]}. Rolled back.")
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
