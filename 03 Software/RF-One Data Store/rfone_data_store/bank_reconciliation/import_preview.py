"""Import Set Review — inspect an uploaded file set BEFORE it is imported
(BANK_SOURCE_AND_IMPORT_REVIEW_001).

The operator selects the files of a period; RF-One answers one question
before anything authoritative is written: *is this the correct, complete
set to import?* The answer is shown in one modal, and only the human's
Confirm imports the set. Cancel leaves the Bank data exactly as it was.

HOW THE ANSWER IS PRODUCED — REUSE, NOT A SECOND IMPORTER
---------------------------------------------------------
The set is run through the real import (`service.import_csv`) inside the
caller's session and then ROLLED BACK. So every fact the review shows is
the fact the real import would produce, from the same code:

* format recognition and unrecognized files — `parsers.parse_csv_bytes`;
* already-imported files — the content hash `import_csv` already uses
  (a renamed identical file is the same file; a same-named different file
  is not);
* file -> Source identity, multi-card files and rows naming an account no
  Source has — `import_csv`'s own instrument resolution;
* overlapping periods for one Source — `BankImportBatch.overlap_warning`;
* transactions already in the ledger — the candidate-duplicate search;
* which Sources a period expects — `monthly_source`'s expectation rule,
  restricted to ACTIVE Sources (an inactive Source is not expected);
* which Sources earlier imports already cover —
  `monthly_source.batches_covering` / `multi_instrument_batches_evidencing`.

Nothing here commits. `preview_import` ends with `session.rollback()`
whatever happens, so the caller must hand it a session with no pending
work of its own. Nothing is written outside the session either: the
import path does no file or network I/O.

Coverage is reported per calendar month the files actually cover, from
each file's own date range — never from its name or the upload date. A
file covering three months is shown covering three months; nothing is
forced into a single "monthly" shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import monthly_source, parsers
from . import service as bank_service

# File outcomes, in the words the review uses.
FILE_NEW = "NEW"
FILE_ALREADY_IMPORTED = "ALREADY_IMPORTED"
FILE_DUPLICATE_IN_SET = "DUPLICATE_IN_SET"
FILE_UNRECOGNIZED = "UNRECOGNIZED"

# Per period, what each expected Source looks like.
SOURCE_IN_UPLOAD = "IN_UPLOAD"
SOURCE_ALREADY_IMPORTED = "ALREADY_IMPORTED"
SOURCE_RESOLVED = "RESOLVED"
SOURCE_MISSING = "MISSING"


@dataclass(frozen=True)
class StagedFile:
    file_name: str
    content: bytes


def source_label(instrument: "m.PaymentInstrument") -> str:
    """A Source as the operator reads it: its name and, never more than,
    the last four digits of its account or card."""
    last_four = instrument.last_four or (
        instrument.external_account_identifier[-4:]
        if instrument.external_account_identifier else None
    )
    return instrument.display_name + (f" ··{last_four}" if last_four else "")


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _instruments_with_rows(session: Session, batch_id: int) -> dict[int, set[tuple[int, int]]]:
    """For one batch: which Sources its rows were normalized onto, and the
    months those rows were posted in. Read through the raw-row lineage, so a
    multi-card file credits each card with exactly its own rows."""
    found: dict[int, set[tuple[int, int]]] = {}
    rows = session.execute(
        select(m.FinancialTransaction.payment_instrument_id, m.FinancialTransaction.posting_date)
        .join(m.RawBankTransaction,
              m.RawBankTransaction.normalized_transaction_id == m.FinancialTransaction.id)
        .where(m.RawBankTransaction.import_batch_id == batch_id)
    ).all()
    for instrument_id, posting_date in rows:
        if instrument_id is None:
            continue
        months = found.setdefault(instrument_id, set())
        if posting_date is not None:
            months.add((posting_date.year, posting_date.month))
    return found


def preview_import(
    session: Session, *, files: list[StagedFile], uploaded_by_account_id: int | None,
    payment_instrument_id: int | None = None,
) -> dict:
    """Inspect `files` exactly as the import would see them; write nothing.

    Returns a JSON-serialisable dict (it is stored with the staged set and
    rendered by the review modal):

      files            one entry per uploaded file, with its outcome;
      expected_sources the ACTIVE Sources (the operator's expectation list);
      periods          per covered month: each expected Source in this
                       upload / already imported / resolved / missing, plus
                       uploaded Sources that are not expected;
      warnings         facts the operator should see before deciding;
      blocking         reasons Confirm would import nothing;
      importable_count files that would create a new import batch.
    """
    try:
        return _preview(
            session, files=files, uploaded_by_account_id=uploaded_by_account_id,
            payment_instrument_id=payment_instrument_id,
        )
    finally:
        session.rollback()


def _preview(
    session: Session, *, files: list[StagedFile], uploaded_by_account_id: int | None,
    payment_instrument_id: int | None,
) -> dict:
    instruments = list(session.scalars(
        select(m.PaymentInstrument).order_by(m.PaymentInstrument.display_name)
    ).all())
    by_id = {i.id: i for i in instruments}
    active = [i for i in instruments if i.status == "ACTIVE"]

    file_entries: list[dict] = []
    warnings: list[str] = []
    new_batch_ids: set[int] = set()
    # (year, month) -> Source ids this upload brings rows for.
    upload_presence: dict[tuple[int, int], set[int]] = {}
    seen_hashes: dict[str, str] = {}

    for staged in files:
        entry = {
            "file_name": staged.file_name, "status": FILE_NEW, "detected_format": None,
            "row_count": 0, "date_start": None, "date_end": None, "sources": [],
            "notes": [],
        }
        file_entries.append(entry)
        sha256 = parsers.sha256_bytes(staged.content)

        if sha256 in seen_hashes:
            entry["status"] = FILE_DUPLICATE_IN_SET
            entry["notes"].append(
                f"Same content as {seen_hashes[sha256]} in this upload — it would be imported once."
            )
            continue
        seen_hashes[sha256] = staged.file_name

        existing = session.scalars(
            select(m.BankImportBatch).where(m.BankImportBatch.sha256 == sha256)
        ).first()
        if existing is not None:
            entry["status"] = FILE_ALREADY_IMPORTED
            entry["detected_format"] = existing.detected_format
            entry["row_count"] = existing.row_count
            entry["date_start"] = _iso(existing.date_range_start)
            entry["date_end"] = _iso(existing.date_range_end)
            if existing.payment_instrument is not None:
                entry["sources"].append(source_label(existing.payment_instrument))
            entry["notes"].append(
                f"Already imported as batch #{existing.id} ({existing.original_file_name}, "
                f"{existing.uploaded_at:%Y-%m-%d}). Nothing would be imported again."
            )
            continue

        try:
            parsers.parse_csv_bytes(staged.content)
        except parsers.UnrecognizedFormatError as exc:
            entry["status"] = FILE_UNRECOGNIZED
            entry["notes"].append(str(exc))
            continue

        result = bank_service.import_csv(
            session, file_bytes=staged.content, original_file_name=staged.file_name,
            uploaded_by_account_id=uploaded_by_account_id,
            payment_instrument_id=payment_instrument_id,
        )
        batch = result.batch
        new_batch_ids.add(batch.id)
        entry["detected_format"] = batch.detected_format
        entry["row_count"] = result.parsed_row_count
        entry["date_start"] = _iso(batch.date_range_start)
        entry["date_end"] = _iso(batch.date_range_end)

        rows_by_source = _instruments_with_rows(session, batch.id)
        if batch.payment_instrument_id is not None:
            rows_by_source.setdefault(batch.payment_instrument_id, set()).update(
                monthly_source.months_spanned(batch.date_range_start, batch.date_range_end)
            )
        for instrument_id, months in rows_by_source.items():
            instrument = by_id.get(instrument_id)
            if instrument is None:
                continue
            entry["sources"].append(source_label(instrument))
            for month_key in months:
                upload_presence.setdefault(month_key, set()).add(instrument_id)
        entry["sources"].sort()

        name = staged.file_name
        if batch.payment_instrument_id is None and not rows_by_source:
            entry["notes"].append("Not matched to any Source — it would need a manual assignment after import.")
            if not result.unresolved_row_count:
                warnings.append(f"{name}: not matched to any Source.")
        if result.unresolved_row_count:
            note = (f"{result.unresolved_row_count} row(s) name an account/card with no Source "
                    f"({result.resolution_detail}).")
            entry["notes"].append(note)
            warnings.append(f"{name}: {note}")
        if result.unreadable_row_count:
            note = f"{result.unreadable_row_count} unreadable row(s)."
            entry["notes"].append(note)
            warnings.append(f"{name}: {note}")
        if result.candidate_duplicate_count:
            note = (f"{result.candidate_duplicate_count} transaction(s) look like ones already "
                    "recorded (candidate duplicates, reviewed after import).")
            entry["notes"].append(note)
            warnings.append(f"{name}: {note}")
        if batch.overlap_warning:
            entry["notes"].append(batch.overlap_warning)
            warnings.append(f"{name}: {batch.overlap_warning}")
        if batch.date_range_start is None:
            entry["notes"].append("No readable date: it covers no period.")
            warnings.append(f"{name}: no readable date, so it covers no period.")
        for instrument_id in rows_by_source:
            instrument = by_id.get(instrument_id)
            if instrument is not None and instrument.status != "ACTIVE":
                note = f"{source_label(instrument)} is an INACTIVE Source."
                entry["notes"].append(note)
                warnings.append(f"{name}: {note}")

    periods = [
        _period_view(session, month_key, active, by_id, upload_presence.get(month_key, set()),
                     new_batch_ids)
        for month_key in sorted(set(upload_presence) | _months_of(file_entries))
    ]
    for period in periods:
        if period["missing"]:
            scope = "" if period["controlled"] else " (historical month, not under completeness control)"
            warnings.append(
                f"{period['month']}: expected Source(s) missing{scope} — "
                + ", ".join(period["missing"]) + "."
            )

    importable = sum(1 for f in file_entries if f["status"] == FILE_NEW)
    blocking = []
    if not importable:
        blocking.append("No file in this set would import anything new.")

    dated = [f for f in file_entries if f["status"] == FILE_NEW and f["date_start"]]
    return {
        "files": file_entries,
        "file_count": len(file_entries),
        "recognized_count": sum(1 for f in file_entries if f["status"] != FILE_UNRECOGNIZED),
        "importable_count": importable,
        "unrecognized": [f["file_name"] for f in file_entries if f["status"] == FILE_UNRECOGNIZED],
        "duplicates": [
            f["file_name"] for f in file_entries
            if f["status"] in (FILE_ALREADY_IMPORTED, FILE_DUPLICATE_IN_SET)
        ],
        "expected_sources": [source_label(i) for i in active],
        "date_start": min((f["date_start"] for f in dated), default=None),
        "date_end": max((f["date_end"] for f in dated), default=None),
        "periods": periods,
        "warnings": warnings,
        "blocking": blocking,
    }


def _months_of(file_entries: list[dict]) -> set[tuple[int, int]]:
    """The months the NEW files' own date ranges touch — so a period is
    reviewed even when every row of it failed to resolve to a Source."""
    months: set[tuple[int, int]] = set()
    for entry in file_entries:
        if entry["status"] == FILE_NEW and entry["date_start"] and entry["date_end"]:
            months |= monthly_source.months_spanned(
                date.fromisoformat(entry["date_start"]), date.fromisoformat(entry["date_end"]),
            )
    return months


def _period_view(
    session: Session, month_key: tuple[int, int], active: list["m.PaymentInstrument"],
    by_id: dict[int, "m.PaymentInstrument"], present: set[int], new_batch_ids: set[int],
) -> dict:
    """One covered month: every ACTIVE Source the expectation rule expects,
    and where its data comes from."""
    year, month = month_key
    start, end = monthly_source.period_bounds(year, month)
    existing_period = monthly_source.get_period(session, year, month)
    # The expectation rule reads only the period's bounds; an unopened month
    # is evaluated without opening it.
    period = existing_period or SimpleNamespace(
        period_start=start, period_end=end, period_month=monthly_source.period_key(year, month),
    )
    resolutions = {}
    if existing_period is not None:
        resolutions = {
            c.payment_instrument_id: c for c in monthly_source.coverages(session, existing_period)
            if c.is_resolved
        }

    lines, missing = [], []
    expected_ids = set()
    for instrument in active:
        verdict = monthly_source.expectation_with_lifecycle_boundary(session, instrument, period)
        if verdict.verdict == m.COVERAGE_NOT_EXPECTED:
            continue
        expected_ids.add(instrument.id)
        label = source_label(instrument)
        if instrument.id in present:
            state, detail = SOURCE_IN_UPLOAD, "in this upload"
        else:
            earlier = [
                b for b in monthly_source.batches_covering(
                    session, period=period, instrument_id=instrument.id)
                if b.id not in new_batch_ids
            ] or [
                b for b in monthly_source.multi_instrument_batches_evidencing(
                    session, period=period, instrument_id=instrument.id)
                if b.id not in new_batch_ids
            ]
            if earlier:
                state = SOURCE_ALREADY_IMPORTED
                detail = f"already imported ({earlier[0].original_file_name})"
            elif instrument.id in resolutions:
                state = SOURCE_RESOLVED
                detail = f"no file — resolved as {resolutions[instrument.id].resolution}"
            else:
                state, detail = SOURCE_MISSING, "missing"
                missing.append(label)
        lines.append({"source": label, "institution": instrument.institution,
                      "state": state, "detail": detail})

    unexpected = sorted(
        source_label(by_id[i]) for i in present if i not in expected_ids and i in by_id
    )
    return {
        "month": monthly_source.period_key(year, month),
        "label": start.strftime("%B %Y"),
        "controlled": monthly_source.is_controlled_month(session, year, month),
        "lines": lines,
        "expected_count": len(lines),
        "in_upload_count": sum(1 for line in lines if line["state"] == SOURCE_IN_UPLOAD),
        "earlier_count": sum(1 for line in lines if line["state"] == SOURCE_ALREADY_IMPORTED),
        "resolved_count": sum(1 for line in lines if line["state"] == SOURCE_RESOLVED),
        "missing": missing,
        "unexpected": unexpected,
    }
