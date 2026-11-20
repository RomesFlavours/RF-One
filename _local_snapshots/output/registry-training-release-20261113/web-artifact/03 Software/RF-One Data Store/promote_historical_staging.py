#!/usr/bin/env python
"""Promote the certified CLEAN historical staging dataset into a database
(BANK_HISTORICAL_CLEAN_CONSOLIDATE_AND_IMPORT_001 §21-§24).

Promotion reads the CERTIFIED STAGING DATASET, not the original files
again. Re-parsing the corpus through a second path would mean the thing
that was certified and the thing that was imported are only *probably* the
same; here they are the same by construction.

Three layers are written, and they answer three different questions:

    BankImportBatch      which original file this came from
    RawBankTransaction   which source ROW said it — every row, including
                         the ones that turned out to be duplicate evidence
    FinancialTransaction which ECONOMIC EVENT occurred — one per certified
                         clean event, never one per source row

Several raw rows pointing at one financial transaction is the normal,
correct shape: it is how provenance survives without money being counted
twice.

Idempotent by construction. Every layer is keyed on content — a file by
its SHA-256, a raw row by its position in that file, a financial
transaction by its clean event key and occurrence index — so running this
twice creates nothing the second time. That is checked, not assumed.

Never touches AWS. Writes only to the database it is pointed at.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import date, datetime, timezone

from sqlalchemy import func, select

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import historical_staging as staging
from rfone_data_store.database import (
    create_configured_engine,
    create_session_factory,
    get_database_url,
    redact_database_url,
)

REPO_BANK_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "Bank")
)
STAGING_DIR = os.path.join(REPO_BANK_DIR, "Historic Staging")

# Marks a transaction whose canonicality was established by certified
# staging consolidation rather than by the per-settlement-account dedup
# pass. Recorded so nobody has to guess later which mechanism decided.
STAGING_DEDUP_REASON = (
    "Canonical by certified historical staging consolidation "
    "(BANK_HISTORICAL_CLEAN_CONSOLIDATE_AND_IMPORT_001): overlapping downloads were "
    "consolidated by multiset transaction identity before promotion."
)


def _iso_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def load_run(run_dir: str) -> dict:
    """Load one certified staging run from disk."""
    with open(os.path.join(run_dir, "manifests", "clean_manifest.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    with open(os.path.join(run_dir, "manifests", "clean_manifest.sha256"), encoding="utf-8") as fh:
        manifest_sha = fh.read().strip()
    with open(os.path.join(run_dir, "clean_events", "events.json"), encoding="utf-8") as fh:
        events = json.load(fh)
    with open(os.path.join(run_dir, "source_manifest", "sources.json"), encoding="utf-8") as fh:
        sources = json.load(fh)
    with open(os.path.join(run_dir, "review", "rows.json"), encoding="utf-8") as fh:
        rows = json.load(fh)
    recomputed = staging.manifest_sha256(manifest)
    if recomputed != manifest_sha:
        raise SystemExit(
            f"Staging manifest does not match its own SHA-256 ({recomputed} vs {manifest_sha}). "
            "The certified dataset has been altered; nothing is promoted."
        )
    return {
        "manifest": manifest, "manifest_sha256": manifest_sha,
        "events": events, "sources": sources, "rows": rows,
    }


def promote(session, run: dict, *, base_dir: str) -> dict:
    """Write the certified dataset. Returns what was created versus reused."""
    created = Counter()
    reused = Counter()

    # --- 1. One import batch per parsed source file -----------------------
    batch_by_path: dict[str, m.BankImportBatch] = {}
    for source in run["sources"]:
        if not source["detected_format"]:
            continue  # inventory-only or unsupported: no rows, no batch
        existing = session.scalar(
            select(m.BankImportBatch).where(m.BankImportBatch.sha256 == source["sha256"])
        )
        if existing is not None:
            batch_by_path[source["relative_path"]] = existing
            reused["batches"] += 1
            continue
        with open(os.path.join(base_dir, source["relative_path"]), "rb") as fh:
            file_bytes = fh.read()
        batch = m.BankImportBatch(
            detected_format=source["detected_format"],
            payment_instrument_id=source["payment_instrument_id"],
            original_file_name=source["relative_path"],
            raw_file_bytes=file_bytes,
            sha256=source["sha256"],
            uploaded_at=datetime.now(timezone.utc),
            row_count=source["source_row_count"],
            date_range_start=_iso_date(source.get("earliest")),
            date_range_end=_iso_date(source.get("latest")),
            # The existing canonical vocabulary, reused rather than
            # extended: these batches were parsed and normalized into
            # canonical transactions, which is exactly what NORMALIZED
            # means here. No new status word is invented for this import.
            status="NORMALIZED",
            overlap_warning=source["notes"] or None,
        )
        session.add(batch)
        session.flush()
        batch_by_path[source["relative_path"]] = batch
        created["batches"] += 1

    # --- 2. One financial transaction per certified clean event ------------
    transaction_by_event: dict[tuple[str, int], m.FinancialTransaction] = {}
    for event in run["events"]:
        fingerprint = f"{event['clean_event_key']}:{event['occurrence_index']}"
        existing = session.scalar(
            select(m.FinancialTransaction).where(
                m.FinancialTransaction.payment_instrument_id == event["payment_instrument_id"],
                m.FinancialTransaction.fingerprint == fingerprint,
            )
        )
        if existing is not None:
            transaction_by_event[(event["clean_event_key"], event["occurrence_index"])] = existing
            reused["transactions"] += 1
            continue

        establishing_path = (
            event["source_provenance"][0].rsplit("#", 1)[0]
            if event["source_provenance"] else None
        )
        establishing_row = (
            int(event["source_provenance"][0].rsplit("#", 1)[1])
            if event["source_provenance"] else None
        )
        batch = batch_by_path.get(establishing_path)

        transaction = m.FinancialTransaction(
            payment_instrument_id=event["payment_instrument_id"],
            bank_source=event["identity_basis"],
            posting_date=_iso_date(event["posting_date"]),
            transaction_date=_iso_date(event["transaction_date"]),
            description_original=event["description"],
            source_memo=event["memo"],
            source_memo_field="memo" if event["memo"] else None,
            amount_minor=event["amount_minor"],
            native_transaction_type=event["bank_transaction_type"],
            reference=event["reference"],
            balance_minor=event["balance_minor"],
            # These are settled historical downloads, not a live pending
            # feed: the bank published them as completed activity.
            status="COMPLETED",
            import_batch_id=batch.id if batch else None,
            source_row_number=establishing_row,
            fingerprint=fingerprint,
            occurrence_index_in_batch=event["occurrence_index"],
            occurrence_count_in_batch=event["occurrence_multiplicity"],
            # Canonical because staging already consolidated the overlapping
            # downloads. Recorded with its reason so the mechanism that
            # decided is never in doubt.
            accounting_status="CANONICAL",
            accounting_dedup_key=fingerprint,
            accounting_dedup_reason=STAGING_DEDUP_REASON,
            classification="UNKNOWN",
        )
        session.add(transaction)
        session.flush()
        transaction_by_event[(event["clean_event_key"], event["occurrence_index"])] = transaction
        created["transactions"] += 1

    # --- 3. Every source row, linked to the event it supports --------------
    # A row that was duplicate evidence points at the SAME transaction as
    # the row that established it. That is provenance without double money.
    event_by_provenance: dict[str, tuple[str, int]] = {}
    for event in run["events"]:
        key = (event["clean_event_key"], event["occurrence_index"])
        for provenance in event["source_provenance"]:
            event_by_provenance.setdefault(provenance, key)

    rows = run["rows"]

    for row in rows:
        batch = batch_by_path.get(row["source_path"])
        if batch is None:
            continue
        existing = session.scalar(
            select(m.RawBankTransaction).where(
                m.RawBankTransaction.import_batch_id == batch.id,
                m.RawBankTransaction.row_number == row["row_number"],
            )
        )
        if existing is not None:
            reused["raw_rows"] += 1
            continue
        provenance = f"{row['source_path']}#{row['row_number']}"
        event_key = event_by_provenance.get(provenance)
        transaction = transaction_by_event.get(event_key) if event_key else None
        session.add(
            m.RawBankTransaction(
                import_batch_id=batch.id,
                row_number=row["row_number"],
                raw_fields={
                    "source_path": row["source_path"],
                    "detected_format": row["detected_format"],
                    "posting_date": row["posting_date"],
                    "transaction_date": row["transaction_date"],
                    "amount_minor": row["amount_minor"],
                    "description": row["description"],
                    "memo": row["memo"],
                    "bank_transaction_type": row["bank_transaction_type"],
                    "reference": row["reference"],
                    "balance_minor": row["balance_minor"],
                    "account_hint": row["account_hint"],
                    "payment_instrument_id": row["payment_instrument_id"],
                },
                row_fingerprint=provenance,
                parse_status=row["parse_status"],
                anomalies="; ".join(row["anomalies"]) or row["row_class"],
                normalized_transaction_id=transaction.id if transaction else None,
            )
        )
        created["raw_rows"] += 1
    session.flush()

    return {"created": dict(created), "reused": dict(reused)}


def canonical_db_manifest(session) -> dict:
    """The business manifest of what the DATABASE now holds.

    Built from business facts only — no integer id appears anywhere — so it
    can be compared against the staging manifest, and against a completely
    independent database, by content alone."""
    rows = session.execute(
        select(
            m.FinancialTransaction.payment_instrument_id,
            m.FinancialTransaction.fingerprint,
            m.FinancialTransaction.posting_date,
            m.FinancialTransaction.transaction_date,
            m.FinancialTransaction.amount_minor,
        ).order_by(
            m.FinancialTransaction.payment_instrument_id, m.FinancialTransaction.fingerprint,
        )
    ).all()
    events = [
        {
            "payment_instrument_id": instrument_id,
            "clean_event_key": fingerprint.rsplit(":", 1)[0],
            "occurrence_index": int(fingerprint.rsplit(":", 1)[1]),
            "posting_date": posting.isoformat() if posting else None,
            "transaction_date": transaction.isoformat() if transaction else None,
            "amount_minor": amount,
        }
        for instrument_id, fingerprint, posting, transaction, amount in rows
    ]
    controls: dict[str, dict] = {}
    for event in events:
        entry = controls.setdefault(
            str(event["payment_instrument_id"]),
            {"clean_events": 0, "debit_minor": 0, "credit_minor": 0},
        )
        entry["clean_events"] += 1
        if event["amount_minor"] < 0:
            entry["debit_minor"] += event["amount_minor"]
        else:
            entry["credit_minor"] += event["amount_minor"]
    return {
        "clean_events": sorted(
            events,
            key=lambda e: (
                e["payment_instrument_id"], e["clean_event_key"], e["occurrence_index"],
            ),
        ),
        "per_instrument_controls": dict(sorted(controls.items())),
    }


def compare_to_staging(db_manifest: dict, staging_manifest: dict) -> tuple[bool, list[str]]:
    """The database must hold exactly the certified dataset (§40)."""
    problems: list[str] = []

    def signature(events):
        return Counter(
            (
                e["payment_instrument_id"], e["clean_event_key"], e["occurrence_index"],
                e["posting_date"], e["transaction_date"], e["amount_minor"],
            )
            for e in events
        )

    db_signature = signature(db_manifest["clean_events"])
    staging_signature = signature(staging_manifest["clean_events"])
    if db_signature != staging_signature:
        missing = staging_signature - db_signature
        extra = db_signature - staging_signature
        problems.append(
            f"Economic event multiset differs: {sum(missing.values())} missing from the "
            f"database, {sum(extra.values())} present that staging never certified."
        )

    for instrument_id, expected in staging_manifest["per_instrument_controls"].items():
        actual = db_manifest["per_instrument_controls"].get(instrument_id)
        if actual is None:
            problems.append(f"Instrument {instrument_id} has no transactions in the database.")
            continue
        for field in ("clean_events", "debit_minor", "credit_minor"):
            if actual[field] != expected[field]:
                problems.append(
                    f"Instrument {instrument_id} {field}: database {actual[field]} vs staging "
                    f"{expected[field]}."
                )
    return not problems, problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", default="runs/A", help="Certified staging run to promote.")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--apply", action="store_true", help="Commit. Without it, rolls back.")
    args = parser.parse_args()

    run_dir = os.path.join(STAGING_DIR, args.run)
    run = load_run(run_dir)

    url = args.database_url or get_database_url()
    print(f"Database URL     : {redact_database_url(url)}")
    print(f"Staging run      : {args.run}")
    print(f"Manifest SHA-256 : {run['manifest_sha256']}")
    print(f"Certified events : {len(run['events'])}")
    print(f"Mode             : {'APPLY' if args.apply else 'DRY RUN'}")

    engine = create_configured_engine(url)
    try:
        session_factory = create_session_factory(engine)
        with session_factory() as session:
            outcome = promote(session, run, base_dir=REPO_BANK_DIR)
            db_manifest = canonical_db_manifest(session)
            matches, problems = compare_to_staging(db_manifest, run["manifest"])
            print(f"Created          : {outcome['created']}")
            print(f"Reused           : {outcome['reused']}")
            print(f"DB manifest SHA  : {staging.manifest_sha256(db_manifest)}")
            print(f"MATCHES STAGING  : {'YES' if matches else 'NO'}")
            for problem in problems:
                print(f"   PROBLEM {problem}")
            if args.apply and matches:
                session.commit()
                print("COMMITTED")
            else:
                session.rollback()
                print("ROLLED BACK" if not matches else "DRY RUN — rolled back")
            return 0 if matches else 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
