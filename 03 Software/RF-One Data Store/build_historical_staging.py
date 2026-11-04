#!/usr/bin/env python
"""Build the certified CLEAN historical staging dataset
(BANK_HISTORICAL_CLEAN_CONSOLIDATE_AND_IMPORT_001 §4-§20).

Reads the original download corpus, consolidates it into economic events
OUTSIDE the authoritative database, and writes a deterministic manifest.

**The originals are evidence.** This script opens them for reading only.
Nothing is renamed, rewritten, normalized in place, or removed — including
files that turn out to be exact byte duplicates of each other.

Run it at least twice, in different source orders, and compare the manifest
SHA-256. If the two disagree, the cleaning depends on traversal order and
nothing may be promoted.

    python build_historical_staging.py --order forward --out runs/A
    python build_historical_staging.py --order reverse --out runs/B

Never touches AWS and never writes to the golden database.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter

from sqlalchemy import select

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import historical_source, parsers
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
SOURCE_ROOTS = ["Historic Data", "Download"]


def registered_instruments(session) -> list[dict]:
    """The registered instruments, as plain data. Read-only: this script
    never creates, renames or modifies a Payment Instrument."""
    return [
        {
            "id": instrument.id,
            "display_name": instrument.display_name,
            "instrument_type": instrument.instrument_type,
            "last_four": historical_source.instrument_last_four(instrument),
            "legal_entity_id": instrument.legal_entity_id,
            "status": instrument.status,
        }
        for instrument in session.scalars(
            select(m.PaymentInstrument).order_by(m.PaymentInstrument.id)
        )
    ]


def build(*, order: str, instruments: list[dict]) -> dict:
    """Inventory, parse, resolve, consolidate. Returns everything the
    caller needs to certify and promote."""
    sources = staging.inventory(SOURCE_ROOTS, REPO_BANK_DIR)
    staging.mark_exact_file_duplicates(sources)

    # The ORDER the corpus is traversed in. Reversing it must change
    # nothing about the result — that is the whole point of running this
    # twice.
    ordered = list(sources)
    if order == "reverse":
        ordered = list(reversed(ordered))
    elif order == "grouped":
        ordered = sorted(ordered, key=lambda s: (s.family, s.relative_path))

    rows: list[staging.StagedRow] = []
    unresolved_rows = 0
    unsupported_rows = 0

    for source in ordered:
        if source.status == staging.SOURCE_EXACT_FILE_DUPLICATE:
            continue
        if source.family in (
            staging.FAMILY_ZELLE_EVIDENCE_PENDING, staging.FAMILY_UNSUPPORTED,
        ):
            # Inventoried and fingerprinted, deliberately not read for
            # financial content. The Zelle PDF is provenance in this task,
            # never a source of rows.
            source.status = (
                staging.SOURCE_INVENTORY_ONLY
                if source.family == staging.FAMILY_ZELLE_EVIDENCE_PENDING
                else staging.SOURCE_UNSUPPORTED
            )
            source.notes = (
                "Zelle PDF: inventory and provenance only. Not OCR'd, and no financial row is "
                "derived from it in this task."
                if source.family == staging.FAMILY_ZELLE_EVIDENCE_PENDING
                else "No parser supports this file type; it is recorded, never silently skipped."
            )
            continue

        try:
            parsed = staging.parse_source(source, REPO_BANK_DIR)
        except Exception as exc:  # noqa: BLE001 — a parse failure is recorded, not raised
            source.status = staging.SOURCE_PARSE_ERROR
            source.notes = f"{type(exc).__name__}: {exc}"
            continue
        if parsed is None:
            source.status = staging.SOURCE_UNSUPPORTED
            source.notes = "No parser selected for this extension."
            continue

        source.detected_format = parsed.detected_format
        source.family = staging._FORMAT_FAMILY.get(parsed.detected_format, source.family)
        source.source_row_count = len(parsed.rows)
        source.parsed_row_count = sum(1 for r in parsed.rows if r.parse_status != "UNREADABLE")
        source.unreadable_row_count = sum(1 for r in parsed.rows if r.parse_status == "UNREADABLE")
        for row in parsed.rows:
            for value in (row.posting_date, row.transaction_date):
                if value is None:
                    continue
                iso = value.isoformat()
                source.earliest = iso if source.earliest is None else min(source.earliest, iso)
                source.latest = iso if source.latest is None else max(source.latest, iso)

        staging.resolve_instrument(source, parsed, instruments)

        for row in parsed.rows:
            if row.parse_status == "UNREADABLE":
                unsupported_rows += 1
                continue
            # A layout that names the account on every row is resolved row
            # by row: one export may legitimately cover several cards, and
            # each row says which. Everything else inherits the file's own
            # single resolved instrument.
            if parsed.detected_format in staging.PER_ROW_ACCOUNT_FORMATS:
                row_instrument = staging.resolve_row_instrument(
                    row.account_hint, parsed.detected_format, instruments,
                )
            else:
                row_instrument = source.payment_instrument_id
            staged = staging.StagedRow(
                source_path=source.relative_path,
                row_number=row.row_number,
                detected_format=parsed.detected_format,
                payment_instrument_id=row_instrument,
                posting_date=row.posting_date,
                transaction_date=row.transaction_date,
                amount_minor=row.amount_minor,
                description=row.description,
                memo=row.source_memo,
                bank_transaction_type=row.bank_transaction_type,
                reference=row.reference,
                balance_minor=row.balance_minor,
                account_hint=row.account_hint,
                parse_status=row.parse_status,
                anomalies=tuple(row.anomalies),
            )
            if row_instrument is None:
                staged.row_class = staging.ROW_UNRESOLVED_INSTRUMENT
                unresolved_rows += 1
            rows.append(staged)

    promotable = [r for r in rows if r.payment_instrument_id is not None]
    identity_stats = staging.assign_identities(promotable)
    events, consolidation_stats = staging.consolidate(promotable)

    manifest = staging.build_manifest(sources=sources, events=events, rows=rows)
    return {
        "order": order,
        "sources": sources,
        "rows": rows,
        "events": events,
        "manifest": manifest,
        "manifest_sha256": staging.manifest_sha256(manifest),
        "identity_stats": identity_stats,
        "consolidation_stats": consolidation_stats,
        "unresolved_rows": unresolved_rows,
        "unreadable_rows": unsupported_rows,
    }


def relationships(result: dict) -> list[dict]:
    """How each pair of files for the same instrument relates (§12).

    Diagnostic provenance only: the dedup decision is made per transaction
    identity, never from a file-level verdict."""
    # Group by the instruments a file's ROWS actually touch, not by a
    # single file-level answer: a multi-card export belongs to every
    # instrument it covers, and leaving it out would hide exactly the
    # overlap this report exists to show.
    instruments_touched: dict[str, set[int]] = {}
    for row in result["rows"]:
        if row.payment_instrument_id is None:
            continue
        instruments_touched.setdefault(row.source_path, set()).add(row.payment_instrument_id)

    by_instrument: dict[int, list] = {}
    for source in result["sources"]:
        for instrument_id in sorted(instruments_touched.get(source.relative_path, ())):
            by_instrument.setdefault(instrument_id, []).append(source)

    # Identities are compared PER INSTRUMENT, so a file covering two cards
    # is compared against another file once per shared card rather than as
    # one undifferentiated bag.
    identities_by_source: dict[tuple[str, int], Counter] = {}
    for row in result["rows"]:
        if row.payment_instrument_id is None or not row.identity_basis:
            continue
        identities_by_source.setdefault(
            (row.source_path, row.payment_instrument_id), Counter()
        )[(row.identity_basis, row.identity_key)] += 1

    findings: list[dict] = []
    for instrument_id, group in sorted(by_instrument.items()):
        ordered = sorted(group, key=lambda s: s.relative_path)
        for index, left in enumerate(ordered):
            for right in ordered[index + 1:]:
                a = identities_by_source.get((left.relative_path, instrument_id), Counter())
                b = identities_by_source.get((right.relative_path, instrument_id), Counter())
                shared = sum((a & b).values())
                only_a = sum((a - b).values())
                only_b = sum((b - a).values())
                if left.sha256 == right.sha256:
                    verdict = historical_source.EXACT_FILE_DUPLICATE
                elif not a and not b:
                    verdict = historical_source.AMBIGUOUS
                elif not shared:
                    verdict = historical_source.DISJOINT
                elif not only_a and not only_b:
                    verdict = historical_source.TRANSACTION_EQUIVALENT
                elif not only_b:
                    verdict = historical_source.TRANSACTION_SUPERSET
                elif not only_a:
                    verdict = historical_source.TRANSACTION_SUBSET
                else:
                    verdict = historical_source.PARTIAL_OVERLAP
                findings.append(
                    {
                        "payment_instrument_id": instrument_id,
                        "a": left.relative_path,
                        "b": right.relative_path,
                        "verdict": verdict,
                        "shared": shared,
                        "only_a": only_a,
                        "only_b": only_b,
                    }
                )
    return findings


def certify(result: dict) -> tuple[bool, list[str]]:
    """The gate (§19). Every check must pass before anything is promoted."""
    failures: list[str] = []
    rows = result["rows"]
    events = result["events"]

    unclassified = [r for r in rows if not r.row_class]
    if unclassified:
        failures.append(
            f"B: {len(unclassified)} parsed row(s) ended in no class — a silent discard."
        )

    for source in result["sources"]:
        if source.status == staging.SOURCE_PARSED and source.detected_format:
            accounted = sum(1 for r in rows if r.source_path == source.relative_path)
            if accounted + source.unreadable_row_count != source.source_row_count:
                failures.append(
                    f"G: {source.relative_path} parsed {source.source_row_count} row(s) but "
                    f"{accounted + source.unreadable_row_count} were accounted for."
                )

    promoted = sum(1 for r in rows if r.row_class == staging.ROW_PROMOTED)
    if promoted != len(events):
        failures.append(
            f"C: {promoted} promoted row(s) but {len(events)} clean event(s) — these must match."
        )

    guessed = [
        s for s in result["sources"]
        if s.payment_instrument_id is not None
        and s.instrument_basis == staging.BASIS_NONE
    ]
    if guessed:
        failures.append(
            f"E: {len(guessed)} source(s) were assigned an instrument with no stated basis."
        )

    seen = set()
    for event in events:
        key = (event.payment_instrument_id, event.clean_event_key, event.occurrence_index)
        if key in seen:
            failures.append(f"C: duplicate clean event occurrence {key}.")
        seen.add(key)

    for event in events:
        if event.amount_minor is None:
            failures.append(f"F: clean event {event.clean_event_key} has no amount.")

    missing_fingerprint = [s for s in result["sources"] if not s.sha256]
    if missing_fingerprint:
        failures.append("H: a source is missing its SHA-256 fingerprint.")

    return not failures, failures


def write_outputs(result: dict, out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    for name in ("source_manifest", "clean_events", "review", "manifests", "logs"):
        os.makedirs(os.path.join(out_dir, name), exist_ok=True)

    with open(os.path.join(out_dir, "manifests", "clean_manifest.json"), "w",
              encoding="utf-8") as fh:
        fh.write(staging.canonical_json(result["manifest"]))
    with open(os.path.join(out_dir, "manifests", "clean_manifest.sha256"), "w",
              encoding="utf-8") as fh:
        fh.write(result["manifest_sha256"] + "\n")

    with open(os.path.join(out_dir, "source_manifest", "sources.json"), "w",
              encoding="utf-8") as fh:
        fh.write(staging.canonical_json([vars(s) for s in result["sources"]]))

    with open(os.path.join(out_dir, "clean_events", "events.json"), "w",
              encoding="utf-8") as fh:
        fh.write(staging.canonical_json([vars(e) for e in result["events"]]))

    with open(os.path.join(out_dir, "review", "row_classes.json"), "w",
              encoding="utf-8") as fh:
        fh.write(
            staging.canonical_json(
                dict(sorted(Counter(r.row_class for r in result["rows"]).items()))
            )
        )
    with open(os.path.join(out_dir, "review", "relationships.json"), "w",
              encoding="utf-8") as fh:
        fh.write(staging.canonical_json(relationships(result)))
    # Every parsed row, with the class it ended in. Promotion reads this so
    # raw provenance is written from the SAME certified artifact the clean
    # events came from, never from a second pass over the originals.
    with open(os.path.join(out_dir, "review", "rows.json"), "w", encoding="utf-8") as fh:
        fh.write(staging.canonical_json([vars(r) for r in result["rows"]]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--order", choices=("forward", "reverse", "grouped"), default="forward")
    parser.add_argument("--out", default="runs/A", help="Output folder under Historic Staging.")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    url = get_database_url()
    engine = create_configured_engine(url)
    try:
        session_factory = create_session_factory(engine)
        with session_factory() as session:
            instruments = registered_instruments(session)
            # Read-only: nothing was written, so nothing is committed.
            session.rollback()
    finally:
        engine.dispose()

    result = build(order=args.order, instruments=instruments)
    certified, failures = certify(result)

    out_dir = os.path.join(STAGING_DIR, args.out)
    write_outputs(result, out_dir)

    if not args.quiet:
        print(f"Database URL (read-only): {redact_database_url(url)}")
        print(f"Source order            : {args.order}")
        print(f"Source files inventoried: {len(result['sources'])}")
        print(f"Parsed rows             : {len(result['rows'])}")
        print(f"Clean economic events   : {len(result['events'])}")
        print(f"Row classes             : "
              f"{dict(sorted(Counter(r.row_class for r in result['rows']).items()))}")
        print(f"Identity stats          : {result['identity_stats']}")
        print(f"Manifest SHA-256        : {result['manifest_sha256']}")
        print(f"CLEAN STAGING CERTIFIED : {'YES' if certified else 'NO'}")
        for failure in failures:
            print(f"   FAILURE {failure}")
        print(f"Written to              : {out_dir}")
    return 0 if certified else 1


if __name__ == "__main__":
    sys.exit(main())
