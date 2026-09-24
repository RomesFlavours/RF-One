#!/usr/bin/env python
"""Set the Reconciliation Control Start and apply it to the Bank history
already imported (BANK_ACTIVATE_CONTROL_START_001).

Goes through `monthly_source.activate_control_start`, the same service the
Monthly Sources screen uses. Setting the start for the first time or moving
it earlier opens/reuses, refreshes and evaluates the controlled months the
existing batches cover; moving it later writes only the setting. Running it
again with the same start re-applies the boundary idempotently.

Nothing is re-imported, no blocker is resolved, no month is declared
COMPLETE and no instrument lifecycle is changed. Guards checked before
committing: batch / transaction / raw counts, the canonical financial
manifest, full `financial_transactions` and `payment_instruments` hashes,
and the WHO/WHY row counts. Any change rolls the run back.

    python activate_reconciliation_control_start.py --start 2026-01-01           # preview
    python activate_reconciliation_control_start.py --start 2026-01-01 --apply   # write

Never contacts AWS, RDS or any network service.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import date

from sqlalchemy import func, select, text

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import historical_staging as staging
from rfone_data_store.bank_reconciliation import monthly_source
from rfone_data_store.database import (
    create_configured_engine,
    create_session_factory,
    get_database_url,
    redact_database_url,
)

import promote_historical_staging as promoter


def _table_sha256(session, table: str) -> str:
    digest = hashlib.sha256()
    for row in session.execute(text(f"SELECT * FROM {table} ORDER BY id")):
        digest.update(repr(tuple(row)).encode())
    return digest.hexdigest()


def controls(session) -> dict:
    count = lambda model: session.scalar(select(func.count(model.id)))  # noqa: E731
    return {
        "batches": count(m.BankImportBatch),
        "raw_rows": count(m.RawBankTransaction),
        "transactions": count(m.FinancialTransaction),
        "manifest": staging.manifest_sha256(promoter.canonical_db_manifest(session)),
        "financial_transactions": _table_sha256(session, "financial_transactions"),
        "payment_instruments": _table_sha256(session, "payment_instruments"),
        "batches_table": _table_sha256(session, "bank_import_batches"),
        "who_recognitions": count(m.BankWhoRecognition),
        "explanations": count(m.BankTransactionExplanation),
        "allocations": count(m.BankTransactionAllocation),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, help="first day of the first controlled month")
    parser.add_argument("--note", default=None)
    parser.add_argument("--apply", action="store_true", help="write (default: preview)")
    args = parser.parse_args()

    url = get_database_url()
    print(f"Database: {redact_database_url(url)}")
    engine = create_configured_engine(url)
    try:
        with create_session_factory(engine)() as session:
            try:
                year, month = monthly_source.control_start_date_from(date.fromisoformat(args.start))
            except ValueError as exc:
                print(f"REFUSED: {exc}")
                return 1
            before = controls(session)
            periods_before = session.scalar(select(func.count(m.BankMonthlySourcePeriod.id)))
            coverage_before = session.scalar(select(func.count(m.BankMonthlyInstrumentCoverage.id)))

            config, previous, outcome = monthly_source.activate_control_start(
                session, year=year, month=month, note=args.note,
            )
            if outcome is None and previous == config.control_start_month:
                outcome = monthly_source.apply_control_to_existing_batches(session)
            session.flush()

            print(f"control start       {previous or '(not set)'} -> {config.control_start_month}")
            if outcome is None:
                print("moved later: only the setting was written; nothing existing was touched.")
            else:
                print(f"batches examined    {outcome.batches_examined}")
                print(f"historical months   {len(outcome.historical_months)}"
                      + (f" ({outcome.historical_months[0]} .. {outcome.historical_months[-1]})"
                         if outcome.historical_months else ""))
                print(f"controlled months   created {outcome.created} · reused {outcome.reused}")
                for control in outcome.months:
                    report = control.report
                    if report is None:
                        print(f"  {control.period.period_month}  COMPLETE — left as history")
                        continue
                    print(f"  {control.period.period_month}  status {control.period.status:<9} "
                          f"expected {report.expected:>2} · received {report.received:>2} · "
                          f"not expected {report.not_expected:>2} · needs confirmation "
                          f"{report.needs_confirmation:>2} · blockers {len(report.blockers):>2}")
                    for blocker in report.blockers:
                        print(f"      - {blocker}")
            periods_after = session.scalar(select(func.count(m.BankMonthlySourcePeriod.id)))
            coverage_after = session.scalar(select(func.count(m.BankMonthlyInstrumentCoverage.id)))
            print(f"periods             {periods_before} -> {periods_after}")
            print(f"coverage rows       {coverage_before} -> {coverage_after}")

            after = controls(session)
            if before != after:
                session.rollback()
                changed = [key for key in before if before[key] != after[key]]
                print(f"REFUSED — protected data moved: {changed}. Rolled back.")
                return 1
            print(f"protected data unchanged: batches {after['batches']}, raw {after['raw_rows']}, "
                  f"transactions {after['transactions']}, manifest {after['manifest']}")
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
