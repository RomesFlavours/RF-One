#!/usr/bin/env python
"""ADP `Payroll Detail` Excel import entry point (TASK_PAYROLL_001 §27).

RF-One does not automate ADP input. This automates the opposite, more
valuable direction: ADP processed payroll -> Payroll Details Excel -> RF-One
import, so employee-level payroll detail survives past ADP's own UI even
though the bank only ever shows one aggregate direct-deposit debit.

Usage:
    python import_payroll_results.py --file "C:\\path\\PayrollDetail.xlsx" \\
        --restaurant-id 1 \\
        --period-start 2026-08-03 --period-end 2026-08-17 \\
        --run-type REGULAR \\
        [--persist] [--pay-date-override 2026-08-19] \\
        [--supersedes-run <prior_import_run_id>]

Defaults to safe, read-only dry-run behavior (task §35): the workbook is
parsed and Employee mapping is resolved against already-confirmed mappings
plus exact-unique name-key matching, and an aggregate-only summary is
printed — no Employee name, SSN, or bank reference is ever printed by this
script. Nothing is written to the database unless `--persist` is passed.

No ADP API credential, OAuth token, or network access of any kind is used
or required (task §39/§42) — this only reads a local file.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from rfone_data_store.database import create_configured_engine, create_session_factory
from rfone_data_store import models as m
from rfone_data_store.payroll import adp_importer as adp

UTC = timezone.utc


def _parse_date(value: str) -> datetime:
    dt = datetime.strptime(value, "%Y-%m-%d")
    return dt.replace(tzinfo=UTC)


def _get_or_create_source_system(session, code: str) -> m.SourceSystem:
    existing = session.query(m.SourceSystem).filter(m.SourceSystem.code == code).one_or_none()
    if existing is not None:
        return existing
    created = m.SourceSystem(code=code, name=f"{code} (Payroll Provider)", active=True)
    session.add(created)
    session.flush()
    return created


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--file", required=True, type=Path, help="Path to the local ADP Payroll Detail .xlsx")
    parser.add_argument("--restaurant-id", type=int, required=True)
    parser.add_argument("--source-system-code", default="ADP")
    parser.add_argument(
        "--period-start", type=_parse_date, default=None,
        help="Payroll Period start (YYYY-MM-DD). Required for REGULAR runs — never inferred "
        "from the Pay Date (Payroll Schedule and Period.md).",
    )
    parser.add_argument("--period-end", type=_parse_date, default=None, help="Payroll Period end, exclusive (YYYY-MM-DD).")
    parser.add_argument("--run-type", choices=["REGULAR", "SPECIAL"], default="REGULAR")
    parser.add_argument("--payroll-schedule-id", type=int, default=None)
    parser.add_argument(
        "--pay-date-override", type=_parse_date, default=None,
        help="Only if the source's own Check Date cannot be trusted for this import.",
    )
    parser.add_argument("--supersedes-run", type=int, default=None, dest="supersedes_run",
                         help="PayrollImportRun id this corrected import explicitly supersedes.")
    parser.add_argument("--persist", action="store_true", help="Write to the database. Default is dry-run.")
    args = parser.parse_args()

    if args.run_type == "REGULAR" and (args.period_start is None or args.period_end is None):
        parser.error("--period-start/--period-end are required for REGULAR runs (never inferred from Pay Date).")

    if not args.file.exists():
        parser.error(f"File not found: {args.file}")

    engine = create_configured_engine()
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        if not args.persist:
            source_system = session.query(m.SourceSystem).filter(
                m.SourceSystem.code == args.source_system_code
            ).one_or_none()
            source_system_id = source_system.id if source_system is not None else -1

            summary = adp.dry_run_import(
                session,
                source_system_id=source_system_id,
                restaurant_id=args.restaurant_id,
                file_path=args.file,
            )
            print("Dry run — nothing was persisted (pass --persist to commit).")
            print(f"  employees represented:        {summary.employees_represented}")
            print(f"  pay date(s):                  {summary.pay_dates}")
            print(f"  earning-line count:           {summary.earning_line_count}")
            print(f"  reportable-tip line count:    {summary.reportable_tip_line_count}")
            print(f"  employer-liability lines:     {summary.employer_liability_line_count}")
            print(f"  payment facts:                {summary.payment_fact_count}")
            print(f"  total employer-paid earnings: {summary.total_employer_paid_earnings_minor} (minor units)")
            print(f"  total employer liabilities:   {summary.total_employer_liabilities_minor} (minor units)")
            print(f"  derived Payroll Employer Cost:{summary.total_payroll_employer_cost_minor} (minor units)")
            print(f"  total employee payment:       {summary.total_employee_payment_amount_minor} (minor units)")
            print(f"  unresolved Employee mappings: {summary.unresolved_employee_mapping_count}")
            print(f"  ambiguous Employee mappings:  {summary.ambiguous_employee_mapping_count}")
            print(f"  unparsed source labels:       {summary.unparsed_source_labels}")
            session.rollback()
            return 0

        source_system = _get_or_create_source_system(session, args.source_system_code)
        result = adp.persist_import(
            session,
            source_system_id=source_system.id,
            restaurant_id=args.restaurant_id,
            file_path=args.file,
            period_start=args.period_start,
            period_end=args.period_end,
            run_type=args.run_type,
            payroll_schedule_id=args.payroll_schedule_id,
            pay_date_override=args.pay_date_override,
            supersedes_import_run_id=args.supersedes_run,
        )
        session.commit()
        print(f"Import run id: {result.import_run_id} (created={result.created})")
        print(f"  PayrollRun id:              {result.payroll_run_id}")
        print(f"  Employees persisted:        {result.employees_persisted}")
        print(f"  Unresolved Employee count:  {result.unresolved_employee_count}")
        print(f"  Ambiguous Employee count:   {result.ambiguous_employee_count}")
        print(f"  Issues raised:              {result.issue_count}")
        print("Persisted." if result.created else "Idempotent — this exact file was already imported.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
