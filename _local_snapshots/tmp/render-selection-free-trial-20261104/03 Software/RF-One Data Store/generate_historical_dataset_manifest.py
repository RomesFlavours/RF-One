#!/usr/bin/env python
"""Regenerate the safe historical dataset audit manifest
(BANK_HISTORICAL_DATASET_AUDIT_REPAIR_001 §6-§7).

The first version of `07 Tasks/Reports/BANK_HISTORICAL_DATASET_MANIFEST.md`
was assembled by hand from the import's analysis output, and its
per-instrument "raw rows" column counted rows by the BATCH's instrument. A
multi-instrument export (Chase's combined business-card download) has no
single batch instrument, so its 217 rows were counted for nobody, and
instruments 7 and 12 were under-reported. Money and events were never
affected; the control table was.

This script rebuilds the whole manifest from the two authorities instead of
patching numbers:

    the GOLDEN DATABASE     what RF-One holds (read only, never committed)
    the CERTIFIED STAGING   what the corpus was certified to contain

Every per-instrument figure is computed from the database and then CHECKED
against the certified staging controls; any disagreement aborts without
writing. A raw row is attributed to the instrument of the canonical
transaction it evidences — the row's own instrument — never to the batch.

Only aggregate, safe metadata is written: no transaction description, no
counterparty, no full account number.

    python generate_historical_dataset_manifest.py            # verify + print
    python generate_historical_dataset_manifest.py --write    # also write the .md

Never touches AWS.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

from sqlalchemy import func, select, text

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import historical_source
from rfone_data_store.bank_reconciliation import historical_staging as staging
from rfone_data_store.database import (
    create_configured_engine,
    create_session_factory,
    get_database_url,
    redact_database_url,
)

import promote_historical_staging as promoter

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", ".."))
STAGING_DIR = os.path.join(REPO_DIR, "Bank", "Historic Staging")
REPORT_PATH = os.path.join(REPO_DIR, "07 Tasks", "Reports", "BANK_HISTORICAL_DATASET_MANIFEST.md")
CERTIFIED_RUN = "runs/A"
ORDER_RUNS = (("A", "forward"), ("B", "reverse"), ("C", "grouped"))


class ManifestMismatch(RuntimeError):
    """The database and the certified staging disagree. Nothing is written."""


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _money(minor: int) -> str:
    return f"{minor / 100:,.2f}"


def _git_head() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_DIR, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception:  # pragma: no cover - diagnostics only
        return "unknown"


def raw_rows_by_instrument(session) -> dict[int, int]:
    """Raw source rows per instrument, attributed through the canonical
    transaction each row evidences — so a row from a multi-instrument
    export counts for the card it actually belongs to."""
    rows = session.execute(
        select(m.FinancialTransaction.payment_instrument_id, func.count(m.RawBankTransaction.id))
        .join(m.FinancialTransaction,
              m.FinancialTransaction.id == m.RawBankTransaction.normalized_transaction_id)
        .group_by(m.FinancialTransaction.payment_instrument_id)
    ).all()
    return {int(instrument): int(count) for instrument, count in rows}


def source_files_by_instrument(session) -> dict[int, list[str]]:
    """Which original files carry evidence for each instrument, again
    through the rows themselves rather than the batch header."""
    out: dict[int, set[str]] = defaultdict(set)
    for instrument, name in session.execute(
        select(m.FinancialTransaction.payment_instrument_id, m.BankImportBatch.original_file_name)
        .join(m.RawBankTransaction,
              m.RawBankTransaction.normalized_transaction_id == m.FinancialTransaction.id)
        .join(m.BankImportBatch, m.BankImportBatch.id == m.RawBankTransaction.import_batch_id)
        .distinct()
    ).all():
        out[int(instrument)].add(name)
    return {k: sorted(v) for k, v in out.items()}


def batch_instrument_split(session) -> dict[str, dict[int, int]]:
    """For every source file: how many of its rows belong to which
    instrument. A single-instrument file has one entry."""
    out: dict[str, dict[int, int]] = defaultdict(dict)
    for name, instrument, count in session.execute(
        select(
            m.BankImportBatch.original_file_name,
            m.FinancialTransaction.payment_instrument_id,
            func.count(m.RawBankTransaction.id),
        )
        .join(m.RawBankTransaction, m.RawBankTransaction.import_batch_id == m.BankImportBatch.id)
        .join(m.FinancialTransaction,
              m.FinancialTransaction.id == m.RawBankTransaction.normalized_transaction_id)
        .group_by(m.BankImportBatch.original_file_name, m.FinancialTransaction.payment_instrument_id)
    ).all():
        out[name][int(instrument)] = int(count)
    return out


def instrument_rows(session, staging_controls: dict) -> list[dict]:
    """One row per REGISTERED instrument — including those with no source —
    computed from the database and verified against certified staging."""
    raw = raw_rows_by_instrument(session)
    files = source_files_by_instrument(session)
    problems: list[str] = []
    rows: list[dict] = []
    for instrument in session.scalars(select(m.PaymentInstrument).order_by(m.PaymentInstrument.id)):
        stats = session.execute(
            select(
                func.count(m.FinancialTransaction.id),
                func.min(m.FinancialTransaction.posting_date),
                func.max(m.FinancialTransaction.posting_date),
                func.coalesce(func.sum(m.FinancialTransaction.amount_minor)
                              .filter(m.FinancialTransaction.amount_minor < 0), 0),
                func.coalesce(func.sum(m.FinancialTransaction.amount_minor)
                              .filter(m.FinancialTransaction.amount_minor >= 0), 0),
            ).where(m.FinancialTransaction.payment_instrument_id == instrument.id)
        ).one()
        canonical, first, last, debit, credit = stats
        raw_rows = raw.get(instrument.id, 0)
        row = {
            "id": instrument.id,
            "display_name": instrument.display_name,
            "instrument_type": instrument.instrument_type,
            "last_four": historical_source.instrument_last_four(instrument),
            "legal_entity_id": instrument.legal_entity_id,
            "status": instrument.status,
            "source_files": files.get(instrument.id, []),
            "raw_rows": raw_rows,
            "canonical": int(canonical),
            "duplicate_evidence": raw_rows - int(canonical),
            "first": first.isoformat() if first else None,
            "last": last.isoformat() if last else None,
            "debit_minor": int(debit),
            "credit_minor": int(credit),
            "census_state": (
                historical_source.REGISTERED_AND_SOURCED if canonical
                else historical_source.REGISTERED_NO_SOURCE
            ),
        }
        control = staging_controls.get(str(instrument.id))
        if control is None:
            if canonical:
                problems.append(f"instrument {instrument.id}: in the database, absent from staging")
            row.update(month_count=0, month_gaps=[])
        else:
            for ours, theirs in (
                ("raw_rows", "raw_rows"), ("canonical", "clean_events"),
                ("duplicate_evidence", "duplicate_evidence_rows"),
                ("debit_minor", "debit_minor"), ("credit_minor", "credit_minor"),
            ):
                if row[ours] != control[theirs]:
                    problems.append(
                        f"instrument {instrument.id} {ours}: database {row[ours]} vs staging "
                        f"{control[theirs]}"
                    )
            row.update(month_count=control["month_count"], month_gaps=control["month_gaps"])
        rows.append(row)
    if problems:
        raise ManifestMismatch("; ".join(problems))
    return rows


def coarse_vs_multiset_overlap(review_rows: list[dict], instrument_id: int) -> dict | None:
    """§3 of the audit repair: the two ways the ··3376 overlap was counted.

    COARSE: distinct (posting date, amount, description) keys present in
    both files — what the earlier identity audit counted. It is a SET, so
    two genuine same-day, same-amount, same-text transactions collapse
    into one key.
    MULTISET: the certified identity (full canonical evidence, running
    balance included) counted with multiplicity — what staging uses.
    """
    by_file: dict[str, list[dict]] = defaultdict(list)
    for row in review_rows:
        if row["payment_instrument_id"] == instrument_id:
            by_file[row["source_path"]].append(row)
    if len(by_file) != 2:
        return None
    (a_name, a), (b_name, b) = sorted(by_file.items())
    coarse = lambda r: (r["posting_date"], r["amount_minor"], r["description"])
    full = lambda r: (r["identity_basis"], json.dumps(r["identity_key"]))
    ca, cb = Counter(map(coarse, a)), Counter(map(coarse, b))
    fa, fb = Counter(map(full, a)), Counter(map(full, b))
    collapsed = sorted(k for k in set(ca) & set(cb) if ca[k] > 1 or cb[k] > 1)
    return {
        "files": [a_name, b_name],
        "coarse_distinct_shared": len(set(ca) & set(cb)),
        "multiset_shared": sum((fa & fb).values()),
        "collapsed_keys": [
            {"posting_date": k[0], "amount_minor": k[1], "rows_in_each_file": min(ca[k], cb[k])}
            for k in collapsed
        ],
    }


def build(session, golden_path: str) -> dict:
    run_dir = os.path.join(STAGING_DIR, CERTIFIED_RUN)
    run = promoter.load_run(run_dir)  # verifies the staging manifest's own SHA
    manifest = run["manifest"]
    with open(os.path.join(run_dir, "review", "relationships.json"), encoding="utf-8") as fh:
        relationships = json.load(fh)
    with open(os.path.join(run_dir, "review", "rows.json"), encoding="utf-8") as fh:
        review_rows = json.load(fh)

    order_shas = {}
    for run_name, order in ORDER_RUNS:
        path = os.path.join(STAGING_DIR, "runs", run_name, "manifests", "clean_manifest.sha256")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                order_shas[order] = fh.read().strip()

    db_manifest = promoter.canonical_db_manifest(session)
    matches, problems = promoter.compare_to_staging(db_manifest, manifest)
    if not matches:
        raise ManifestMismatch("; ".join(problems))

    counts = {
        "batches": session.scalar(select(func.count(m.BankImportBatch.id))),
        "raw_rows": session.scalar(select(func.count(m.RawBankTransaction.id))),
        "transactions": session.scalar(select(func.count(m.FinancialTransaction.id))),
        "raw_rows_unlinked": session.scalar(
            select(func.count(m.RawBankTransaction.id))
            .where(m.RawBankTransaction.normalized_transaction_id.is_(None))
        ),
    }
    row_classes = manifest["row_class_counts"]
    if counts["raw_rows"] != sum(row_classes.values()):
        raise ManifestMismatch(
            f"database raw rows {counts['raw_rows']} vs staging rows {sum(row_classes.values())}"
        )
    if counts["transactions"] != row_classes.get(staging.ROW_PROMOTED, 0):
        raise ManifestMismatch("canonical transactions differ from promoted staging rows")

    instruments = instrument_rows(session, manifest["per_instrument_controls"])
    if sum(i["raw_rows"] for i in instruments) != counts["raw_rows"]:
        raise ManifestMismatch("per-instrument raw rows do not add up to the raw total")

    identity_basis = Counter(r["identity_basis"] for r in review_rows)
    coarse = coarse_vs_multiset_overlap(review_rows, 6)

    candidates = [
        {
            "last_four": c.last_four, "institution": c.institution, "discovery": c.discovery,
            "occurrence_count": c.occurrence_count,
            "raw_evidence_count": c.raw_evidence_count,
            "first_seen": c.first_seen_date.isoformat() if c.first_seen_date else None,
            "last_seen": c.last_seen_date.isoformat() if c.last_seen_date else None,
            "resolution": c.resolution, "state": historical_source.candidate_state(c),
            "evidence": c.evidence,
        }
        for c in historical_source.list_candidates(session)
    ]

    knowledge = {
        "who_resolved": session.scalar(
            select(func.count(m.FinancialTransaction.id))
            .where(m.FinancialTransaction.explanation_id.is_not(None))
        ),
        "classified": session.scalar(
            select(func.count(m.FinancialTransaction.id))
            .where(m.FinancialTransaction.classification != "UNKNOWN")
        ),
        "invoice_matches": session.scalar(select(func.count(m.BankInvoiceMatch.id))),
        "allocations": session.scalar(select(func.count(m.BankTransactionAllocation.id))),
        "control_configs": session.scalar(select(func.count(m.BankReconciliationControlConfig.id))),
        "source_periods": session.scalar(select(func.count(m.BankMonthlySourcePeriod.id))),
        "instrument_coverages": session.scalar(
            select(func.count(m.BankMonthlyInstrumentCoverage.id))
        ),
    }

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "git_head": _git_head(),
        "alembic": session.execute(text("SELECT version_num FROM alembic_version")).scalar(),
        "golden_sha256": _sha256_file(golden_path) if golden_path else None,
        "staging_sha256": run["manifest_sha256"],
        "canonical_db_sha256": staging.manifest_sha256(db_manifest),
        "order_shas": order_shas,
        "source_corpus": manifest["source_corpus"],
        "batch_split": batch_instrument_split(session),
        "row_classes": row_classes,
        "identity_basis": dict(identity_basis),
        "relationships": Counter(r["verdict"] for r in relationships),
        "counts": counts,
        "instruments": instruments,
        "coarse_3376": coarse,
        "candidates": candidates,
        "knowledge": knowledge,
    }


def render(data: dict) -> str:
    out: list[str] = []
    w = out.append
    counts = data["counts"]
    rows_total = counts["raw_rows"]
    events = counts["transactions"]
    dup = data["row_classes"].get(staging.ROW_DUPLICATE_EVIDENCE, 0)

    w("# Bank Historical Dataset Manifest\n")
    w("**Tasks:** BANK_HISTORICAL_CLEAN_CONSOLIDATE_AND_IMPORT_001 (import) · "
      "BANK_HISTORICAL_DATASET_AUDIT_REPAIR_001 · "
      "BANK_HISTORICAL_CHECKPOINT_AND_CANDIDATE_IDEMPOTENCY_001 (this regeneration)  ")
    w(f"**Generated (UTC):** {data['generated_at']} by `generate_historical_dataset_manifest.py`  ")
    w(f"**Git commit:** {data['git_head']}  ")
    w(f"**Alembic revision:** `{data['alembic']}`  ")
    w(f"**Golden DB SHA-256 at generation:** `{data['golden_sha256']}`  ")
    w(f"**Clean staging manifest SHA-256:** `{data['staging_sha256']}`  ")
    w(f"**Canonical DB manifest SHA-256:** `{data['canonical_db_sha256']}`\n")
    w("Safe, aggregate metadata only. No raw transaction description, no full account number "
      "and no counterparty detail appears in this file — the cleaned dataset itself stays in the "
      "git-ignored staging workspace.\n")
    w("Every figure below is computed from the golden database and verified against the "
      "certified staging run; the generator refuses to write if the two disagree. A raw row is "
      "attributed to the instrument of the canonical transaction it evidences, never to its "
      "file's batch header.\n")
    w("---\n")

    w("## 1. Source corpus fingerprints\n")
    w("| # | File | Bytes | SHA-256 (first 16) | Format | Status | Rows | Rows by instrument |")
    w("|---:|---|---:|---|---|---|---:|---|")
    for index, source in enumerate(data["source_corpus"], 1):
        split = data["batch_split"].get(source["path"], {})
        split_text = ", ".join(f"{k}: {v}" for k, v in sorted(split.items())) or "—"
        w(f"| {index} | `{source['path']}` | {source['byte_size']} | `{source['sha256'][:16]}` | "
          f"{source.get('detected_format') or '—'} | {source['status']} | "
          f"{source['source_row_count']} | {split_text} |")
    duplicates = len(data["source_corpus"]) - len({s["sha256"] for s in data["source_corpus"]})
    w(f"\nExact byte duplicates across paths: **{duplicates}**. Rows from the two "
      f"`MULTI_INSTRUMENT_SOURCE` files are split across the cards they actually belong to.\n")

    parsed = [s for s in data["source_corpus"] if s["status"] != staging.SOURCE_INVENTORY_ONLY]
    inventory_only = len(data["source_corpus"]) - len(parsed)
    w("## 2. Clean staging construction\n")
    w("| Measure | Value |\n|---|---:|")
    w(f"| Source files inventoried | {len(data['source_corpus'])} |")
    w(f"| Files parsed for financial content | {len(parsed)} |")
    w(f"| Files inventory-only (Zelle PDF, not OCR'd) | {inventory_only} |")
    w(f"| Parsed source rows | {rows_total} |")
    w(f"| Promoted to clean economic event | {data['row_classes'].get(staging.ROW_PROMOTED, 0)} |")
    w(f"| Duplicate evidence (overlapping downloads) | {dup} |")
    for cls in (staging.ROW_AMBIGUOUS_DUPLICATE, staging.ROW_UNRESOLVED_INSTRUMENT,
                staging.ROW_PARSE_ERROR, staging.ROW_UNSUPPORTED):
        w(f"| {cls} | {data['row_classes'].get(cls, 0)} |")
    w(f"| Raw rows not linked to a canonical transaction | {counts['raw_rows_unlinked']} |")
    w(f"| **Clean economic events** | **{events}** |\n")
    basis = data["identity_basis"]
    w(f"Identity basis: provider transaction id **{basis.get('PROVIDER_TRANSACTION_ID', 0):,}** "
      f"rows, canonical evidence **{basis.get('CANONICAL_SOURCE_EVIDENCE', 0):,}** rows.\n")

    w("## 3. Ingestion order invariance\n")
    w("| Run | Source order | Clean manifest SHA-256 |\n|---|---|---|")
    for run_name, order in ORDER_RUNS:
        w(f"| {run_name} | {order} | `{data['order_shas'].get(order, 'missing')}` |")
    identical = len(set(data["order_shas"].values())) == 1 and len(data["order_shas"]) == 3
    w(f"\n**{'Identical across all three orders.' if identical else 'NOT identical.'}**\n")

    w("## 4. File overlap relationships (diagnostic)\n")
    for verdict, count in sorted(data["relationships"].items()):
        w(f"- `{verdict}`: {count} pair(s)")
    w("")

    w("## 5. Per-instrument controls\n")
    w("| Inst | Name | Type | Last 4 | LE | Files | Raw rows | Clean events | Dup. evidence "
      "| First | Last | Months | Gaps | Debit | Credit |")
    w("|---:|---|---|---|---:|---:|---:|---:|---:|---|---|---:|---:|---:|---:|")
    for i in data["instruments"]:
        w(f"| {i['id']} | {i['display_name']} | {i['instrument_type']} | {i['last_four'] or '—'} | "
          f"{i['legal_entity_id'] or '—'} | {len(i['source_files'])} | {i['raw_rows']} | "
          f"{i['canonical']} | {i['duplicate_evidence']} | {i['first'] or '—'} | "
          f"{i['last'] or '—'} | {i['month_count']} | {len(i['month_gaps'])} | "
          f"{_money(i['debit_minor'])} | {_money(i['credit_minor'])} |")
    debit = sum(i["debit_minor"] for i in data["instruments"])
    credit = sum(i["credit_minor"] for i in data["instruments"])
    w(f"\nTotals: raw rows **{sum(i['raw_rows'] for i in data['instruments']):,}**, clean events "
      f"**{sum(i['canonical'] for i in data['instruments']):,}**, duplicate evidence "
      f"**{sum(i['duplicate_evidence'] for i in data['instruments']):,}**; debits "
      f"**{_money(debit)}**, credits **{_money(credit)}**, net **{_money(debit + credit)}**. "
      "First/Last are canonical posting dates. Every row above was checked against the "
      "certified staging controls (raw rows, clean events, duplicate evidence, debits, "
      "credits) and matches.\n")

    w("## 6. Historical instrument census\n")
    with_tx = [i for i in data["instruments"] if i["canonical"]]
    w(f"Registered instruments: **{len(data['instruments'])}**. With canonical transactions: "
      f"**{len(with_tx)}**.\n")
    w("| Inst | Name | Last 4 | Census state |\n|---:|---|---|---|")
    for i in data["instruments"]:
        w(f"| {i['id']} | {i['display_name']} | {i['last_four'] or 'not set'} | "
          f"{i['census_state']} |")
    w("")
    w(f"**Historical instrument candidates persisted:** {len(data['candidates'])} "
      "(`bank_historical_instrument_candidates`). Discovered generically from the raw evidence "
      "by `historical_source.discover_indirect_reference_candidates`; none has a Payment "
      "Instrument, none is resolved.\n")
    if data["candidates"]:
        w("| Last 4 | Discovery | Canonical transactions | Raw evidence rows | First seen | "
          "Last seen | Resolution | State |")
        w("|---|---|---:|---:|---|---|---|---|")
        for c in data["candidates"]:
            w(f"| ··{c['last_four']} | {c['discovery']} | {c['occurrence_count']} | "
              f"{c['raw_evidence_count']} | "
              f"{c['first_seen'] or '—'} | {c['last_seen'] or '—'} | "
              f"{c['resolution'] or 'unresolved'} | {c['state']} |")
        w("")
    w("First/last seen are source boundaries of the evidence, never lifecycle dates.\n")

    k = data["knowledge"]
    w("## 7. Knowledge coverage\n")
    w("| State | Value |\n|---|---|")
    w(f"| Financial ingestion | {events:,} clean events, {rows_total:,} raw rows, "
      f"{counts['batches']} batches |")
    w(f"| WHO resolution | {k['who_resolved']} / {events:,} |")
    w(f"| WHY classification | {k['classified']} / {events:,} |")
    w(f"| Invoice matches | {k['invoice_matches']} |")
    w(f"| Allocations | {k['allocations']} |\n")

    w("## 8. Reconciliation control\n")
    w(f"`bank_reconciliation_control_configs`: **{k['control_configs']}**. "
      f"`bank_monthly_source_periods`: **{k['source_periods']}**. "
      f"`bank_monthly_instrument_coverages`: **{k['instrument_coverages']}**.\n")

    coarse = data["coarse_3376"]
    if coarse:
        w("## 9. ··3376 overlap: 1,370 vs 1,376\n")
        w(f"The earlier identity audit counted **{coarse['coarse_distinct_shared']:,}** shared "
          "rows between the two ··3376 exports: DISTINCT (posting date, amount, description) keys, "
          f"a set. Certified staging counts **{coarse['multiset_shared']:,}**: the full canonical "
          "evidence identity (running balance included) with multiplicity. The difference is "
          f"{len(coarse['collapsed_keys'])} key(s) where two genuinely separate transactions share "
          "date, amount and text and differ in running balance:\n")
        w("| Posting date | Amount | Transactions per file |\n|---|---:|---:|")
        for key in coarse["collapsed_keys"]:
            w(f"| {key['posting_date']} | {_money(key['amount_minor'])} | "
              f"{key['rows_in_each_file']} |")
        w("\nStaging is correct; the earlier count under-stated the overlap and its conclusion "
          "(one account, balances in agreement) is unaffected. No money changed.\n")

    w("## 10. Migration note\n")
    w("`a9e6d3c71f24` widens `bank_import_batches.detected_format` to admit the three American "
      "Express source shapes. It was applied to the golden database before the historical rows "
      "were promoted. The file's last modification is later than the golden database's last "
      "write, and because it was never committed the applied text cannot be recovered. What "
      "can be proven is the outcome: replaying the CURRENT file from the pre-migration backup "
      "produces a `sqlite_master` byte-identical to the golden database's, and a full "
      "downgrade/upgrade cycle returns to it. The applied schema and the file agree, so no "
      "corrective migration is needed. `test_bank_historical_audit_repair.py` pins this.\n")

    w("## 11. Corrections to the previous version of this file\n")
    w("- §5 raw rows for instruments 7 (Ink Giovanna ··3144) and 12 (Business Anthony ··2270) "
      "were 52 and 157; the rows of the two multi-instrument files were counted for no instrument. "
      "Every raw count is now attributed through the canonical transaction, and they add up to the "
      "raw total.")
    w("- §5 Batches column replaced by Files: the number of original files carrying evidence for "
      "the instrument, again through the rows.")
    w("- §6 candidates were reported only as a list of mentions; they are now persisted records.")
    w("- §9 is new: the ··3376 1,370 vs 1,376 reconciliation.")
    w("- Clean-event, canonical, debit and credit figures were correct and are unchanged.")
    w("- BANK_HISTORICAL_CHECKPOINT_AND_CANDIDATE_IDEMPOTENCY_001: each candidate's evidence is "
      "now a keyed set (`bank_historical_instrument_candidate_evidence`, migration "
      "`b31e7c0d9a54`, one row per raw bank row). Candidate counts and dates are recomputed from "
      "that set, so re-running discovery cannot inflate them; the raw evidence column is new.\n")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--write", action="store_true", help="Write the Markdown manifest.")
    parser.add_argument("--out", default=REPORT_PATH)
    args = parser.parse_args()

    url = args.database_url or get_database_url()
    golden_path = url.split("sqlite:///", 1)[1] if url.startswith("sqlite:///") else None
    print(f"Database URL: {redact_database_url(url)}")
    engine = create_configured_engine(url)
    try:
        with create_session_factory(engine)() as session:
            data = build(session, golden_path)
            session.rollback()
    finally:
        engine.dispose()

    print(f"raw rows {data['counts']['raw_rows']} · clean events {data['counts']['transactions']} · "
          f"duplicate evidence {data['row_classes'].get(staging.ROW_DUPLICATE_EVIDENCE, 0)}")
    print(f"canonical DB manifest {data['canonical_db_sha256']}")
    print(f"per-instrument raw rows {[(i['id'], i['raw_rows']) for i in data['instruments']]}")
    print(f"candidates {len(data['candidates'])}")
    if args.write:
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(render(data))
        print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
