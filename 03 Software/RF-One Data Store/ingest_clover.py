#!/usr/bin/env python
"""Ingest Clover source evidence into the RF-One canonical database.

Usage:
    python ingest_clover.py              # full run: enrich, stage, ingest, reconcile, promote
    python ingest_clover.py --dry-run    # everything except promotion
    python ingest_clover.py --skip-enrichment       # reuse whatever is already cached, don't fetch more
    python ingest_clover.py --max-enrichment 200     # bound this run's NEW enrichment fetches

Never prints the API token, payloads, customer data, card data, or
unnecessary employee names — only aggregate progress and counts.

Exit status reflects the ingestion status: 0 for COMPLETE, 1 for PARTIAL,
2 for FAILED (also printed as the last line, per task §8/§45).
"""

from __future__ import annotations

import argparse
import shutil
import sys
import traceback
from pathlib import Path

from rfone_data_store.database import (
    create_configured_engine,
    create_session_factory,
    get_database_url,
    redact_database_url,
    run_migrations_to_head,
)
from rfone_data_store.ingestion.clover import enrichment, ingest, reader, reconciliation
from rfone_data_store.ingestion.common import utc_now
from rfone_data_store.models import IngestionRun, SourceSystem

DATA_DIR = Path(__file__).resolve().parent / "data"
STAGING_DB_PATH = DATA_DIR / "rfone.staging.db"
STAGING_URL = f"sqlite:///{STAGING_DB_PATH.as_posix()}"


def _progress(msg: str) -> None:
    print(msg, flush=True)


def _enrichment_progress(done: int, total: int) -> None:
    print(f"Enriching dedicated line items: {done}/{total} complete", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-enrichment", action="store_true")
    parser.add_argument("--max-enrichment", type=int, default=None)
    args = parser.parse_args()

    print("Reading cached source...")
    bundle = reader.load_source_bundle()
    print(f"  Run: {bundle.run_dir.name} — {len(bundle.orders)} orders, {len(bundle.payments)} payments in source.")

    dedicated_complete = True
    if not args.skip_enrichment:
        order_ids = [o["id"] for o in bundle.orders]
        already = len(order_ids) - len(enrichment.missing_line_item_order_ids(order_ids))
        print(f"Enriching dedicated line items: {already}/{len(order_ids)} already cached.")
        client = enrichment.get_client()
        li_summary = enrichment.enrich_dedicated_line_items(
            client, order_ids, max_to_fetch=args.max_enrichment, progress=_enrichment_progress
        )
        dedicated_complete = li_summary.complete
        print(
            f"Enriching dedicated line items: "
            f"{li_summary.already_cached + li_summary.fetched_ok}/{li_summary.total} complete "
            f"({'COMPLETE' if dedicated_complete else 'INCOMPLETE'})."
        )

        non_default_tax_item_ids = [i["id"] for i in bundle.items_raw if i.get("defaultTaxRates") is False]
        tax_summary = enrichment.enrich_item_tax_rates(client, non_default_tax_item_ids)
        if not tax_summary.complete:
            print(f"  Item tax-rate overrides incomplete: {tax_summary.fetched_failed} failed.")
    else:
        order_ids = [o["id"] for o in bundle.orders]
        dedicated_complete = len(enrichment.missing_line_item_order_ids(order_ids)) == 0
        print(f"Skipping enrichment (--skip-enrichment). Dedicated coverage complete: {dedicated_complete}")

    print("Creating staging DB...")
    if STAGING_DB_PATH.exists():
        STAGING_DB_PATH.unlink()
    run_migrations_to_head(STAGING_URL)
    staging_engine = create_configured_engine(STAGING_URL)
    session_factory = create_session_factory(staging_engine)

    status = "FAILED"
    stats = None
    report = None

    with session_factory() as session:
        source_system = ingest.upsert(
            session, SourceSystem, {"code": "CLOVER"}, {"name": "Clover", "active": True}
        )
        session.flush()

        ingestion_run = IngestionRun(
            source_system_id=source_system.id,
            started_at=utc_now(),
            status="RUNNING",
            source_window_start=None,
            source_window_end=None,
            notes=f"raw run={bundle.run_dir.name}; dedicated_line_items_complete={dedicated_complete}",
        )
        session.add(ingestion_run)
        session.flush()

        try:
            stats = ingest.run_full_ingestion(
                session, bundle, source_system.id, ingestion_run.id, progress=_progress
            )

            print("Reconciling...")
            report = reconciliation.run_full_reconciliation(session, bundle, stats)

            status = _determine_status(dedicated_complete, stats, report)
            ingestion_run.status = status
            ingestion_run.finished_at = utc_now()
            session.commit()
        except Exception:  # noqa: BLE001 — a failed run must not be marked successful (task §39)
            session.rollback()
            traceback.print_exc()
            try:
                ingestion_run.status = "FAILED"
                ingestion_run.finished_at = utc_now()
                session.add(ingestion_run)
                session.commit()
            except Exception:  # noqa: BLE001
                session.rollback()
            status = "FAILED"

    # Release every pooled SQLite connection before any file operation on the
    # staging DB below (Windows locks an open file; SQLite's connection pool
    # otherwise keeps a handle open past the `with` block's session.close()).
    staging_engine.dispose()

    _write_documentation_artifacts(bundle, dedicated_complete, stats, report, status)

    if status == "FAILED":
        print("Status: FAILED")
        print(f"Staging database preserved for inspection at: {STAGING_DB_PATH}")
        return 2

    if args.dry_run:
        print("Dry run: staging DB NOT promoted; expected canonical counts reported above/in reconciliation docs.")
        STAGING_DB_PATH.unlink(missing_ok=True)
        print(f"Status: {status} (dry-run)")
        return 0 if status == "COMPLETE" else 1

    target_url = get_database_url()
    _promote_staging(STAGING_DB_PATH, target_url)
    print(f"Promoted staging DB to: {redact_database_url(target_url)}")

    print(f"Status: {status}")
    return 0 if status == "COMPLETE" else 1


def _determine_status(dedicated_complete: bool, stats, report) -> str:
    if stats is None or report is None:
        return "FAILED"
    critical_checks_ok = all(
        c.passed
        for c in report.empirical_checks
        if "Refund" in c.description or "Orders source total" in c.description or "Payments source total" in c.description
    )
    if not critical_checks_ok:
        return "FAILED"

    core_counts_ok = all(
        cmp.matches
        for cmp in report.count_comparisons
        if cmp.entity in ("Order", "Payment", "Refund", "Merchant", "Location") and cmp.source_count >= 0
    )
    if not core_counts_ok:
        return "FAILED"

    if not dedicated_complete or not report.all_empirical_checks_passed or not report.all_counts_match:
        return "PARTIAL"

    return "COMPLETE"


def _promote_staging(staging_path: Path, target_url: str) -> None:
    if not target_url.startswith("sqlite:///"):
        raise RuntimeError(
            "Promotion by file copy only supports the local SQLite target. "
            "For PostgreSQL, promotion should instead run migrations directly against "
            "the target and re-run ingestion there — not implemented by this task."
        )
    target_path = Path(target_url[len("sqlite:///") :])
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if target_path.exists():
        backup_path = target_path.with_suffix(target_path.suffix + ".bak")
        shutil.copy2(target_path, backup_path)
    shutil.copy2(staging_path, target_path)


def _write_documentation_artifacts(bundle, dedicated_complete, stats, report, status) -> None:
    """Writes the machine-computed figures this run produced to a small,
    Git-ignored JSON file the documentation-writing step reads — keeps
    CLOVER_INGESTION_RECONCILIATION.md's numbers traceable to an actual run
    without re-deriving them by hand."""
    import json

    from rfone_data_store.ingestion.clover import reader as _reader

    out = {
        "status": status,
        "run_dir": bundle.run_dir.name,
        "dedicated_line_items_complete": dedicated_complete,
        "stats_counts": stats.counts if stats else None,
        "unresolved": (stats.__dict__ if stats else None),
        "reconciliation": {
            "count_comparisons": [c.__dict__ for c in report.count_comparisons] if report else None,
            "empirical_checks": [c.__dict__ for c in report.empirical_checks] if report else None,
            "monetary": report.monetary if report else None,
            "weekly_confidence": report.weekly_confidence if report else None,
            "data_quality": report.data_quality if report else None,
        }
        if report
        else None,
    }
    out_path = DATA_DIR / "last_ingestion_result.json"
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
