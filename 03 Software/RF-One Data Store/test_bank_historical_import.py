#!/usr/bin/env python
"""Historical clean-import verification —
BANK_HISTORICAL_CLEAN_CONSOLIDATE_AND_IMPORT_001 §14, §19, §24, §40-§42.

Proves, against the REAL certified staging dataset and a disposable
database:

* the clean staging build is independent of source file order;
* every parsed source row is accounted for in exactly one class;
* multiset consolidation keeps legitimately repeated transactions and
  removes only overlapping re-download evidence;
* promotion into a fresh database reproduces the certified dataset
  exactly, by business content and with no dependence on integer ids;
* a second promotion creates no additional canonical money.

Reads the original corpus only through the staging engine, and never
writes to the authoritative database.
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter

from sqlalchemy import func, select

import build_historical_staging as builder
import promote_historical_staging as promoter
from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import historical_staging as staging
from rfone_data_store.database import (
    create_configured_engine,
    create_session_factory,
    get_database_url,
    redact_database_url,
    resolve_test_database_url,
    run_migrations_to_head,
)

CONFIG_TABLES = (
    "legal_entities", "payment_instruments", "bank_card_settlement_accounts",
    "reporting_groups", "reporting_entities", "reporting_entity_destination_aliases",
)


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        if condition:
            passed.append(description)
        else:
            failed.append(description)
            print(f"FAILED: {description}" + (f" ({detail})" if detail else ""))

    run_dir = os.path.join(builder.STAGING_DIR, "runs", "A")
    if not os.path.isdir(run_dir):
        print("No certified staging run found; run build_historical_staging.py first.")
        return 1

    golden_url = get_database_url()
    print(f"Golden database (read-only): {redact_database_url(golden_url)}")

    # --- Instruments, read once from the authoritative configuration -------
    engine = create_configured_engine(golden_url)
    try:
        session_factory = create_session_factory(engine)
        with session_factory() as session:
            instruments = builder.registered_instruments(session)
            golden_manifest = promoter.canonical_db_manifest(session)
            golden_counts = {
                "transactions": session.scalar(select(func.count(m.FinancialTransaction.id))),
                "raw_rows": session.scalar(select(func.count(m.RawBankTransaction.id))),
                "batches": session.scalar(select(func.count(m.BankImportBatch.id))),
            }
            session.rollback()
    finally:
        engine.dispose()

    # =====================================================================
    # §14 — ingestion order invariance
    # =====================================================================
    results = {
        order: builder.build(order=order, instruments=instruments)
        for order in ("forward", "reverse", "grouped")
    }
    shas = {order: result["manifest_sha256"] for order, result in results.items()}
    check(
        "[§14] the clean manifest is byte-identical in forward, reverse and grouped order",
        len(set(shas.values())) == 1,
        detail=str(shas),
    )

    forward = results["forward"]
    for order in ("reverse", "grouped"):
        other = results[order]
        check(
            f"[§14] {order} order yields the same economic event multiset",
            Counter(e.business_tuple() for e in forward["events"])
            == Counter(e.business_tuple() for e in other["events"]),
        )
        check(
            f"[§14] {order} order yields the same per-instrument controls",
            forward["manifest"]["per_instrument_controls"]
            == other["manifest"]["per_instrument_controls"],
        )

    # =====================================================================
    # §19 — certification gate
    # =====================================================================
    certified, failures = builder.certify(forward)
    check("[§19] the certification gate passes", certified, detail="; ".join(failures))

    classes = Counter(row.row_class for row in forward["rows"])
    check(
        "[§19B] every parsed row ends in exactly one explainable class",
        sum(classes.values()) == len(forward["rows"]) and "" not in classes,
        detail=str(dict(classes)),
    )
    check(
        "[§19C] promoted rows and clean events are the same number",
        classes[staging.ROW_PROMOTED] == len(forward["events"]),
        detail=f"{classes[staging.ROW_PROMOTED]} vs {len(forward['events'])}",
    )
    check(
        "[§19G] no parser silently lost a row",
        all(
            source.source_row_count
            == sum(1 for r in forward["rows"] if r.source_path == source.relative_path)
            + source.unreadable_row_count
            for source in forward["sources"]
            if source.status in (staging.SOURCE_PARSED, staging.SOURCE_MULTI_INSTRUMENT)
        ),
    )
    check(
        "[§19H] every source keeps its SHA-256 fingerprint",
        all(len(s.sha256) == 64 for s in forward["sources"]),
    )
    check(
        "[§19E] no source was assigned an instrument without a stated basis",
        all(
            s.instrument_basis != staging.BASIS_NONE
            for s in forward["sources"] if s.payment_instrument_id is not None
        ),
    )

    # =====================================================================
    # §10 — multiset semantics, on the real corpus
    # =====================================================================
    repeated = [e for e in forward["events"] if e.occurrence_multiplicity > 1]
    check(
        "[§10] legitimately repeated transactions are preserved, not collapsed to one",
        bool(repeated),
        detail=f"{len(repeated)} event occurrences belong to a repeated identity",
    )
    over_counted = [
        e for e in forward["events"]
        if e.occurrence_index >= e.occurrence_multiplicity
    ]
    check("[§10] no event has more occurrences than its multiplicity", not over_counted)

    duplicate_rows = classes[staging.ROW_DUPLICATE_EVIDENCE]
    check(
        "[§10] overlapping downloads contributed duplicate evidence, not duplicate money",
        duplicate_rows > 0
        and len(forward["events"]) + duplicate_rows == len(forward["rows"]),
        detail=f"{len(forward['events'])} events + {duplicate_rows} duplicates "
               f"= {len(forward['rows'])} rows",
    )
    check(
        "[§11] every clean event keeps a reference to all its source rows",
        all(e.source_provenance for e in forward["events"])
        and all(
            e.supporting_row_count >= e.occurrence_multiplicity for e in forward["events"]
        ),
    )

    # =====================================================================
    # §41 — independent import into a disposable database
    # =====================================================================
    disposable_url = resolve_test_database_url("bank_historical_import")
    run_migrations_to_head(disposable_url)
    _copy_configuration(golden_url, disposable_url)

    run = promoter.load_run(run_dir)
    disposable_engine = create_configured_engine(disposable_url)
    try:
        disposable_sessions = create_session_factory(disposable_engine)
        with disposable_sessions() as session:
            first = promoter.promote(session, run, base_dir=builder.REPO_BANK_DIR)
            session.commit()
            disposable_manifest = promoter.canonical_db_manifest(session)
            matches, problems = promoter.compare_to_staging(disposable_manifest, run["manifest"])
            check(
                "[§40] the disposable database holds exactly the certified dataset",
                matches, detail="; ".join(problems),
            )
            check(
                "[§41] the disposable database matches the golden database by business content",
                disposable_manifest["clean_events"] == golden_manifest["clean_events"],
                detail=(
                    f"{len(disposable_manifest['clean_events'])} vs "
                    f"{len(golden_manifest['clean_events'])} events"
                ),
            )
            check(
                "[§41] per-instrument controls match independently of integer ids",
                disposable_manifest["per_instrument_controls"]
                == golden_manifest["per_instrument_controls"],
            )
            check(
                "[§41] the same number of transactions, raw rows and batches was written",
                first["created"]["transactions"] == golden_counts["transactions"]
                and first["created"]["raw_rows"] == golden_counts["raw_rows"]
                and first["created"]["batches"] == golden_counts["batches"],
                detail=f"{first['created']} vs {golden_counts}",
            )

            # §24 — a second promotion creates nothing
            second = promoter.promote(session, run, base_dir=builder.REPO_BANK_DIR)
            session.commit()
            check(
                "[§24] a second promotion creates no additional canonical money",
                not second["created"],
                detail=str(second["created"]),
            )
            check(
                "[§24] the second promotion recognized all existing evidence instead",
                second["reused"]["transactions"] == len(run["events"]),
                detail=str(second["reused"]),
            )
            after = promoter.canonical_db_manifest(session)
            check(
                "[§24] the canonical manifest is unchanged by the second promotion",
                after == disposable_manifest,
            )

            # Provenance without double money.
            multi_evidence = session.scalar(
                select(func.count(m.RawBankTransaction.id)).where(
                    m.RawBankTransaction.normalized_transaction_id.is_not(None)
                )
            )
            check(
                "[§22] every raw row is linked to the one event it supports",
                multi_evidence == len(run["rows"]),
                detail=f"{multi_evidence} of {len(run['rows'])}",
            )
            shared = session.execute(
                select(
                    m.RawBankTransaction.normalized_transaction_id,
                    func.count(m.RawBankTransaction.id),
                )
                .group_by(m.RawBankTransaction.normalized_transaction_id)
                .having(func.count(m.RawBankTransaction.id) > 1)
            ).all()
            check(
                "[§22] several source rows may support one transaction without duplicating it",
                bool(shared)
                and session.scalar(select(func.count(m.FinancialTransaction.id)))
                == len(run["events"]),
                detail=f"{len(shared)} transactions carry more than one supporting row",
            )
    finally:
        disposable_engine.dispose()

    print()
    print(f"Checks passed: {len(passed)}")
    print(f"Checks failed: {len(failed)}")
    if failed:
        print()
        for description in failed:
            print(f"  FAILED  {description}")
        return 1
    for description in passed:
        print(f"  ok  {description}")
    return 0


def _copy_configuration(source_url: str, target_url: str) -> None:
    """Give the disposable database the SAME configuration the golden one
    has — entities, instruments, settlements, reporting perimeter — so the
    comparison tests the import, not a difference in setup."""
    import sqlite3

    source_path = source_url.replace("sqlite:///", "")
    target_path = target_url.replace("sqlite:///", "")
    source = sqlite3.connect(source_path)
    target = sqlite3.connect(target_path)
    try:
        target.execute("PRAGMA foreign_keys = OFF")
        for table in CONFIG_TABLES:
            rows = source.execute(f"SELECT * FROM {table}").fetchall()
            if not rows:
                continue
            columns = [c[1] for c in source.execute(f"PRAGMA table_info({table})")]
            target.execute(f"DELETE FROM {table}")
            target.executemany(
                f"INSERT INTO {table} ({','.join(columns)}) "
                f"VALUES ({','.join('?' for _ in columns)})",
                rows,
            )
        target.commit()
    finally:
        source.close()
        target.close()


if __name__ == "__main__":
    sys.exit(main())
