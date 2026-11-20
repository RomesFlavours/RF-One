#!/usr/bin/env python
"""Automatic ADP Payroll Result acquisition entry point (TASK_PAYROLL_003).

Unlike `import_payroll_results.py` (which requires a human to supply
`--file` for every run), this script is meant to run unattended — on a
schedule (cron/Task Scheduler) — and requires no per-run human action once
its adapter is configured:

    python acquire_payroll_results.py --source sftp --restaurant-id 1 \\
        --period-start 2026-08-03 --period-end 2026-08-17 --run-type REGULAR
        # dry-run (default): prints an aggregate-only summary per acquired
        # file, writes nothing

    python acquire_payroll_results.py --source sftp --restaurant-id 1 \\
        --period-start 2026-08-03 --period-end 2026-08-17 --run-type REGULAR \\
        --persist
        # acquires every not-yet-imported file from the configured SFTP
        # endpoint and persists each through the same idempotent core
        # import_payroll_results.py uses

--source sftp uses `AdpSftpAcquisitionAdapter` (ADP's Automatic Export
Service delivering a report to a customer-controlled SFTP endpoint —
configured on the ADP account side; see 07 Tasks/Reports/
TASK_PAYROLL_003_REPORT.md for exactly what to request from ADP).
Connection details come only from environment variables (ADP_SFTP_HOST,
ADP_SFTP_USERNAME, ADP_SFTP_REMOTE_DIRECTORY, ADP_SFTP_PORT,
ADP_SFTP_PASSWORD or ADP_SFTP_PRIVATE_KEY_PATH) — never hard-coded, never
committed to Git. Without them configured, this exits with a clear error
naming exactly what is missing.

--source api uses `AdpApiAcquisitionAdapter` (ADP's official Payroll Output
API for RUN Powered by ADP). Its credentials load the same way from the
environment (ADP_API_BASE_URL, ADP_API_CLIENT_ID, ADP_API_CLIENT_SECRET,
ADP_API_CLIENT_CERT_PATH, ADP_API_CLIENT_KEY_PATH), but calling it always
raises today — the exact endpoint/schema requires ADP's protected API
documentation, not guessed by this task (see the report).

--source file behaves identically to import_payroll_results.py (the
manual/local-file fallback), included here only so every acquisition path
can be exercised through one entry point.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from rfone_data_store.database import create_configured_engine, create_session_factory
from rfone_data_store import models as m
from rfone_data_store.payroll import acquisition as acq
from rfone_data_store.payroll import adp_importer as adp
from rfone_data_store.payroll import payment_execution as pe

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


def _build_adapter(source: str, file_path: Path | None) -> acq.PayrollAcquisitionAdapter:
    if source == "file":
        if file_path is None:
            raise SystemExit("--file is required when --source file")
        return acq.LocalFileAcquisitionAdapter(file_path=file_path)
    if source == "sftp":
        return acq.AdpSftpAcquisitionAdapter.from_environment(dict(os.environ))
    if source == "api":
        return acq.AdpApiAcquisitionAdapter.from_environment(dict(os.environ))
    raise SystemExit(f"Unknown --source {source!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", choices=["file", "sftp", "api"], required=True)
    parser.add_argument("--file", type=Path, default=None, help="Required when --source file.")
    parser.add_argument("--restaurant-id", type=int, required=True)
    parser.add_argument("--source-system-code", default="ADP")
    parser.add_argument(
        "--period-start", type=_parse_date, default=None,
        help="Payroll Period start (YYYY-MM-DD). Required for REGULAR runs.",
    )
    parser.add_argument("--period-end", type=_parse_date, default=None, help="Payroll Period end, exclusive.")
    parser.add_argument("--run-type", choices=["REGULAR", "SPECIAL"], default="REGULAR")
    parser.add_argument("--payroll-schedule-id", type=int, default=None)
    parser.add_argument("--pay-date-override", type=_parse_date, default=None)
    parser.add_argument(
        "--payment-execution-provider", choices=list(pe.PAYMENT_EXECUTION_PROVIDERS),
        default=None, dest="payment_execution_provider",
        help="Defaults to unset — derived from the Restaurant's approved "
        "PayrollExecutionConfiguration if one exists, otherwise left unassigned. Never inferred "
        "merely because the source is ADP.",
    )
    parser.add_argument("--persist", action="store_true", help="Write to the database. Default is dry-run.")
    args = parser.parse_args()

    if args.run_type == "REGULAR" and (args.period_start is None or args.period_end is None):
        parser.error("--period-start/--period-end are required for REGULAR runs.")

    adapter = _build_adapter(args.source, args.file)

    engine = create_configured_engine()
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        if not args.persist:
            source_system = session.query(m.SourceSystem).filter(
                m.SourceSystem.code == args.source_system_code
            ).one_or_none()
            source_system_id = source_system.id if source_system is not None else -1

            acquired_files = adapter.fetch()
            print(f"Dry run — {len(acquired_files)} file(s) acquired, nothing persisted.")
            for acquired in acquired_files:
                parsed = adp.parse_payroll_detail_workbook_bytes(acquired.file_bytes)
                summary = adp.dry_run_parsed_import(
                    session, source_system_id=source_system_id, restaurant_id=args.restaurant_id, parsed=parsed,
                )
                print(f"  --- {acquired.source_file_name} ({acquired.acquisition_method}) ---")
                print(f"    employees represented:        {summary.employees_represented}")
                print(f"    pay date(s):                  {summary.pay_dates}")
                print(f"    unresolved Employee mappings: {summary.unresolved_employee_mapping_count}")
                print(f"    ambiguous Employee mappings:  {summary.ambiguous_employee_mapping_count}")
            session.rollback()
            return 0

        source_system = _get_or_create_source_system(session, args.source_system_code)
        results = acq.acquire_and_import(
            session,
            adapter,
            source_system_id=source_system.id,
            restaurant_id=args.restaurant_id,
            period_start=args.period_start,
            period_end=args.period_end,
            run_type=args.run_type,
            payroll_schedule_id=args.payroll_schedule_id,
            pay_date_override=args.pay_date_override,
            payment_execution_provider=args.payment_execution_provider,
        )
        session.commit()
        print(f"Acquired and processed {len(results)} file(s):")
        for result in results:
            print(f"  Import run id: {result.import_run_id} (created={result.created})")
            print(f"    PayrollRun id:              {result.payroll_run_id}")
            print(f"    Employees persisted:        {result.employees_persisted}")
            print(f"    Unresolved Employee count:  {result.unresolved_employee_count}")
            print(f"    Ambiguous Employee count:   {result.ambiguous_employee_count}")
            print(f"    Issues raised:              {result.issue_count}")
            if result.payroll_run_id is not None:
                run = session.get(m.PayrollRun, result.payroll_run_id)
                print(f"    Payment execution provider: {run.payment_execution_provider}")
            print("    Persisted." if result.created else "    Idempotent — already imported.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
