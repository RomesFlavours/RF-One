"""Bank Reconciliation persistence, idempotency, and duplicate detection
(spec §4, §8). Every acquisition path (today: manual CSV upload from
RF-One Web) goes through `import_csv` — no separate persistence logic per
caller, mirroring this repository's existing Payroll import convention
(`rfone_data_store/payroll/adp_importer.py`).

Canonical Financial Model Convergence — Phase 3/4/4B (FINANCIAL_MODEL_
CONVERGENCE_001): normalization writes canonical `PaymentInstrument`/
`FinancialTransaction` rows (was `FinancialAccount`/
`NormalizedFinancialTransaction` on the source branch). Every newly
normalized `FinancialTransaction` row enters the Expert System
(`recognition.deduce_for_transaction`), which is now the ONE canonical
reconciliation decision (Product Owner Decision 1) — the legacy V1
catalog-style `assign_explanation` workflow has been retired (Decision
1/10); it no longer exists as a second, independent classification
mechanism."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import matching
from . import parsers
from . import recognition

# First Citizens' free-text `Status` column values map into the canonical
# FinancialTransaction.status vocabulary (COMPLETED/PENDING/REVERSED/
# FAILED/UNKNOWN) without introducing a redundant POSTED status (Product
# Owner instruction) — a previously "POSTED" bank transaction is the
# canonical COMPLETED semantic. Chase source rows never populate `Status`
# (`pending_status` is always None for them — see `parsers.py`), so they
# always map to UNKNOWN here, exactly as before (no status concept existed
# for them either).
_CSV_STATUS_MAP = {"PENDING": "PENDING", "POSTED": "COMPLETED"}


def map_csv_status(pending_status: str | None) -> str:
    if pending_status is None:
        return "UNKNOWN"
    return _CSV_STATUS_MAP.get(pending_status.strip().upper(), "UNKNOWN")


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def normalize_description(raw: str) -> str:
    """Whitespace-collapsed, upper-cased description — used ONLY as a
    comparison/grouping key for duplicate detection (spec §7.5's "normalized
    Description"). `description_original` on the normalized row is never
    replaced by this (spec §5: the raw description must never be lost)."""
    return " ".join((raw or "").strip().upper().split())


def compute_row_fingerprint(raw_fields: dict) -> str:
    canonical = "\x1f".join(f"{k}={raw_fields[k]}" for k in sorted(raw_fields))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_identity_fingerprint(
    *, payment_instrument_id: int, posting_date: date, description_normalized: str,
    amount_minor: int, native_transaction_type: str | None, reference: str | None,
    balance_minor: int | None,
) -> str:
    """Spec §8: retained for duplicate search and human review — NEVER used
    as the sole/automatic identity key. Includes type/reference/balance
    (when available) precisely so a reviewer can see two rows with the same
    coarse (instrument, date, description, amount) differ on these — spec
    §7.4's "a different balance is evidence these may be distinct"."""
    parts = [
        str(payment_instrument_id), posting_date.isoformat(), description_normalized,
        str(amount_minor), native_transaction_type or "", reference or "",
        str(balance_minor) if balance_minor is not None else "",
    ]
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def extract_last_four(hint: str | None) -> str | None:
    if not hint:
        return None
    digits = "".join(ch for ch in hint if ch.isdigit())
    return digits[-4:] if digits else None


def auto_resolve_payment_instrument(
    session: Session, detected_format: str, account_hint: str | None,
) -> "m.PaymentInstrument | None":
    """Automatic resolution only for layouts whose source file itself
    carries a reliable identifier (spec §3.2, §5.2) — First Citizens'
    `Account Number`, Chase credit card Variant A's `Card`. Never for
    Chase bank accounts or Chase credit card Variant B: those always
    require an explicit human-confirmed `payment_instrument_id` at upload
    (spec §3.2: a file name is a hint only, never authoritative)."""
    if not account_hint:
        return None
    if detected_format == parsers.FIRST_CITIZENS:
        last_four = extract_last_four(account_hint)
        return session.scalars(
            select(m.PaymentInstrument).where(
                m.PaymentInstrument.institution == "FIRST_CITIZENS",
                (m.PaymentInstrument.external_account_identifier == account_hint)
                | (m.PaymentInstrument.last_four == last_four),
            )
        ).first()
    if detected_format == parsers.CHASE_CREDIT_CARD_WITH_CARD:
        last_four = extract_last_four(account_hint)
        if not last_four:
            return None
        return session.scalars(
            select(m.PaymentInstrument).where(
                m.PaymentInstrument.institution == "CHASE",
                m.PaymentInstrument.last_four == last_four,
            )
        ).first()
    return None


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


@dataclass
class ImportResult:
    batch: "m.BankImportBatch"
    created: bool  # False when an identical file (same sha256) already existed
    parsed_row_count: int
    unreadable_row_count: int
    normalized_row_count: int
    candidate_duplicate_count: int


def import_csv(
    session: Session, *, file_bytes: bytes, original_file_name: str,
    uploaded_by_account_id: int | None, payment_instrument_id: int | None = None,
) -> ImportResult:
    """Idempotent by content hash (spec §8, condition 1): re-uploading the
    exact same bytes reuses the existing `BankImportBatch` and creates
    nothing new. A genuinely different file with overlapping data (spec
    §8, condition 2) is a distinct batch — its overlap is caught at the
    transaction level by `_normalize_rows`'s duplicate-candidate search,
    never at the file level.

    Raises `parsers.UnrecognizedFormatError` for a header matching none of
    the four known layouts — nothing is persisted in that case."""
    sha256 = parsers.sha256_bytes(file_bytes)
    existing = session.scalars(
        select(m.BankImportBatch).where(m.BankImportBatch.sha256 == sha256)
    ).first()
    if existing is not None:
        unreadable = session.scalars(
            select(m.RawBankTransaction).where(
                m.RawBankTransaction.import_batch_id == existing.id,
                m.RawBankTransaction.parse_status == "UNREADABLE",
            )
        ).all()
        candidates = session.scalars(
            select(m.FinancialTransaction).where(
                m.FinancialTransaction.import_batch_id == existing.id,
                m.FinancialTransaction.duplicate_status == "CANDIDATE_DUPLICATE",
            )
        ).all()
        normalized = session.scalars(
            select(m.FinancialTransaction).where(
                m.FinancialTransaction.import_batch_id == existing.id,
            )
        ).all()
        return ImportResult(
            batch=existing, created=False, parsed_row_count=existing.row_count,
            unreadable_row_count=len(unreadable), normalized_row_count=len(normalized),
            candidate_duplicate_count=len(candidates),
        )

    parsed_file = parsers.parse_csv_bytes(file_bytes)  # UnrecognizedFormatError propagates — nothing persisted

    batch = m.BankImportBatch(
        detected_format=parsed_file.detected_format,
        original_file_name=original_file_name,
        raw_file_bytes=file_bytes,
        sha256=sha256,
        uploaded_by_account_id=uploaded_by_account_id,
        row_count=len(parsed_file.rows),
        status="RECEIVED",
    )
    session.add(batch)
    session.flush()

    dated = [r.posting_date for r in parsed_file.rows if r.posting_date is not None]
    if dated:
        batch.date_range_start = min(dated)
        batch.date_range_end = max(dated)

    raw_objs: list[m.RawBankTransaction] = []
    for parsed_row in parsed_file.rows:
        raw = m.RawBankTransaction(
            import_batch_id=batch.id,
            row_number=parsed_row.row_number,
            raw_fields=parsed_row.raw_fields,
            row_fingerprint=compute_row_fingerprint(parsed_row.raw_fields),
            parse_status=parsed_row.parse_status,
            anomalies="; ".join(parsed_row.anomalies) if parsed_row.anomalies else None,
        )
        session.add(raw)
        raw_objs.append(raw)
    session.flush()

    unreadable_count = sum(1 for r in parsed_file.rows if r.parse_status == "UNREADABLE")

    instrument: "m.PaymentInstrument | None" = None
    if payment_instrument_id is not None:
        instrument = session.get(m.PaymentInstrument, payment_instrument_id)
    if instrument is None:
        hints = {r.account_hint for r in parsed_file.rows if r.account_hint}
        if len(hints) == 1:
            instrument = auto_resolve_payment_instrument(session, parsed_file.detected_format, next(iter(hints)))

    normalized_count = 0
    candidate_count = 0
    if instrument is not None:
        batch.payment_instrument_id = instrument.id
        normalized_count, candidate_count = _normalize_rows(session, batch, instrument, parsed_file.rows, raw_objs)
        batch.overlap_warning = _compute_overlap_warning(session, batch, instrument)

    if unreadable_count:
        batch.error_summary = (
            f"{unreadable_count} row(s) could not be parsed — see individual "
            "RawBankTransaction.anomalies."
        )
    if instrument is None:
        batch.status = "REQUIRES_REVIEW"
    elif unreadable_count or candidate_count:
        batch.status = "REQUIRES_REVIEW"
    else:
        batch.status = "NORMALIZED"

    session.flush()
    return ImportResult(
        batch=batch, created=True, parsed_row_count=len(parsed_file.rows),
        unreadable_row_count=unreadable_count, normalized_row_count=normalized_count,
        candidate_duplicate_count=candidate_count,
    )


def resolve_batch_instrument(
    session: Session, *, batch_id: int, payment_instrument_id: int,
) -> ImportResult:
    """Human resolution of a batch whose format carried no reliable
    in-file account identifier (Chase bank accounts; Chase credit card
    Variant B — spec §3.2). Re-parses each row from its already-preserved
    `raw_fields` (spec §4.1) rather than requiring the original file
    again, then normalizes exactly as `import_csv` would have done had the
    instrument been known at upload time."""
    batch = session.get(m.BankImportBatch, batch_id)
    if batch is None:
        raise ValueError(f"BankImportBatch {batch_id} not found")
    if batch.payment_instrument_id is not None:
        raise ValueError(
            f"BankImportBatch {batch_id} already has a resolved instrument "
            f"({batch.payment_instrument_id}) — re-resolution is not supported by this vertical slice."
        )
    instrument = session.get(m.PaymentInstrument, payment_instrument_id)
    if instrument is None:
        raise ValueError(f"PaymentInstrument {payment_instrument_id} not found")

    raw_objs = list(session.scalars(
        select(m.RawBankTransaction)
        .where(m.RawBankTransaction.import_batch_id == batch.id)
        .order_by(m.RawBankTransaction.row_number)
    ).all())
    parsed_rows = [
        parsers.parse_row_fields(batch.detected_format, r.row_number, r.raw_fields)
        for r in raw_objs
    ]

    batch.payment_instrument_id = instrument.id
    normalized_count, candidate_count = _normalize_rows(session, batch, instrument, parsed_rows, raw_objs)
    batch.overlap_warning = _compute_overlap_warning(session, batch, instrument)

    unreadable_count = sum(1 for r in raw_objs if r.parse_status == "UNREADABLE")
    batch.status = "REQUIRES_REVIEW" if (unreadable_count or candidate_count) else "NORMALIZED"
    session.flush()

    return ImportResult(
        batch=batch, created=True, parsed_row_count=len(raw_objs),
        unreadable_row_count=unreadable_count, normalized_row_count=normalized_count,
        candidate_duplicate_count=candidate_count,
    )


def _normalize_rows(
    session: Session, batch: "m.BankImportBatch", instrument: "m.PaymentInstrument",
    parsed_rows: list["parsers.ParsedBankRow"], raw_objs: list["m.RawBankTransaction"],
) -> tuple[int, int]:
    """Spec §5 (mapping) + §7.3/§8 (occurrence preservation and candidate
    duplicates). Flushes after each row so that a later row's duplicate
    search sees earlier rows already inserted in THIS SAME batch — this is
    what makes within-file identical rows (§7.3) surface as
    CANDIDATE_DUPLICATE via the exact same mechanism as cross-file/history
    duplicates (§7.2, §7.5), with no separate code path."""
    signature_counts: dict[tuple, int] = {}
    for row in parsed_rows:
        if row.parse_status == "UNREADABLE":
            continue
        sig = (row.posting_date, normalize_description(row.description or ""), row.amount_minor)
        signature_counts[sig] = signature_counts.get(sig, 0) + 1
    signature_seen: dict[tuple, int] = {}

    raw_by_row_number = {r.row_number: r for r in raw_objs}
    normalized_count = 0
    candidate_count = 0

    for row in parsed_rows:
        if row.parse_status == "UNREADABLE":
            continue
        description_normalized = normalize_description(row.description or "")
        sig = (row.posting_date, description_normalized, row.amount_minor)
        signature_seen[sig] = signature_seen.get(sig, 0) + 1
        occurrence_index = signature_seen[sig]
        occurrence_count = signature_counts[sig]

        fingerprint = compute_identity_fingerprint(
            payment_instrument_id=instrument.id, posting_date=row.posting_date,
            description_normalized=description_normalized, amount_minor=row.amount_minor,
            native_transaction_type=row.bank_transaction_type, reference=row.reference,
            balance_minor=row.balance_minor,
        )

        existing_match = session.scalars(
            select(m.FinancialTransaction)
            .where(
                m.FinancialTransaction.payment_instrument_id == instrument.id,
                m.FinancialTransaction.posting_date == row.posting_date,
                m.FinancialTransaction.amount_minor == row.amount_minor,
                m.FinancialTransaction.description_normalized == description_normalized,
            )
            .order_by(m.FinancialTransaction.id.asc())
        ).first()

        duplicate_status = "NONE"
        duplicate_of_id = None
        if existing_match is not None:
            duplicate_status = "CANDIDATE_DUPLICATE"
            duplicate_of_id = existing_match.id
            candidate_count += 1

        normalized = m.FinancialTransaction(
            payment_instrument_id=instrument.id,
            bank_source=batch.detected_format,
            posting_date=row.posting_date,
            transaction_date=row.transaction_date,
            description_original=row.description or "",
            description_normalized=description_normalized,
            amount_minor=row.amount_minor,
            native_transaction_type=row.bank_transaction_type,
            reference=row.reference,
            balance_minor=row.balance_minor,
            status=map_csv_status(row.pending_status),
            import_batch_id=batch.id,
            source_row_number=row.row_number,
            fingerprint=fingerprint,
            occurrence_index_in_batch=occurrence_index,
            occurrence_count_in_batch=occurrence_count,
            duplicate_status=duplicate_status,
            duplicate_of_transaction_id=duplicate_of_id,
            review_status="REQUIRES_REVIEW",
        )
        session.add(normalized)
        session.flush()  # visible to the next row's existing_match query

        # Recognition (BANK_RECONCILIATION_EXPERT_SYSTEM_001): the only
        # point import logic changes to apply the expert system to new
        # transactions. Runs once, at creation time, before any human has
        # looked at the row — never re-run for a transaction that already
        # has a decision (that would risk overwriting a human's choice).
        recognition.deduce_for_transaction(session, normalized)

        # Canonical post-acquisition matching (Phase 6B, Product Owner
        # Decision D): attempted for every newly normalized row, in the
        # same per-row loop that already makes each row visible to the
        # next one's duplicate search — so a later row in this same batch
        # can auto-match against an earlier one regardless of which side
        # (Bank/Credit Card/PayPal) arrived first. The hook itself skips a
        # CANDIDATE_DUPLICATE row; it never duplicates matching.py's own
        # criteria.
        matching.on_financial_transaction_acquired(session, normalized)

        raw = raw_by_row_number.get(row.row_number)
        if raw is not None:
            raw.normalized_transaction_id = normalized.id

        normalized_count += 1

    return normalized_count, candidate_count


def _compute_overlap_warning(
    session: Session, batch: "m.BankImportBatch", instrument: "m.PaymentInstrument",
) -> str | None:
    """Spec §8, condition 3 — informational only, never blocking."""
    if batch.date_range_start is None or batch.date_range_end is None:
        return None
    others = session.scalars(
        select(m.BankImportBatch).where(
            m.BankImportBatch.payment_instrument_id == instrument.id,
            m.BankImportBatch.id != batch.id,
            m.BankImportBatch.date_range_start.is_not(None),
            m.BankImportBatch.date_range_end.is_not(None),
        )
    ).all()
    overlapping = [
        o for o in others
        if o.date_range_start <= batch.date_range_end and o.date_range_end >= batch.date_range_start
    ]
    if not overlapping:
        return None
    names = ", ".join(o.original_file_name for o in overlapping)
    return f"Date range overlaps {len(overlapping)} existing batch(es) for this instrument: {names}"


# ---------------------------------------------------------------------------
# Review actions
# ---------------------------------------------------------------------------


def resolve_duplicate_decision(
    session: Session, *, transaction_id: int, decision: str,
) -> "m.FinancialTransaction":
    """A human decision on a `CANDIDATE_DUPLICATE` row (spec §8: "richiedi
    una decisione umana"). Never deletes anything — only records the
    decision."""
    if decision not in ("CONFIRMED_DUPLICATE", "CONFIRMED_DISTINCT"):
        raise ValueError(f"Invalid duplicate decision: {decision!r}")
    txn = session.get(m.FinancialTransaction, transaction_id)
    if txn is None:
        raise ValueError(f"FinancialTransaction {transaction_id} not found")
    txn.duplicate_status = decision
    session.flush()
    return txn


def record_recognition_decision(
    session: Session, *, transaction_id: int, occurrence_id: int, transaction_reason_id: int,
    confirmed_by_account_id: int | None, reuse_for_future: bool = False,
) -> "m.BankTransactionExplanation":
    """Canonical Financial Model Convergence — Phase 4B (Product Owner
    Decisions 1, 6, 7, 10). The ONE human-facing entry point for
    confirming/correcting the canonical Bank Reconciliation decision —
    thin wrapper around `recognition.record_human_decision` used by the
    Bank Review workflow (`bank_routes.py`). Replaces the retired legacy
    `assign_explanation` (there is no longer a second, independent
    Supplier/Receiving assignment action).

    Learning is never automatic: a `BankRecognitionRule` is only created/
    reused when the human explicitly opts in via `reuse_for_future`
    (Decision 12/"Do NOT automatically enable future reuse")."""
    result = recognition.record_human_decision(
        session,
        recognition.HumanDecisionRequest(
            transaction_id=transaction_id, occurrence_id=occurrence_id,
            transaction_reason_id=transaction_reason_id,
            confirmed_by_account_id=confirmed_by_account_id, reuse_for_future=reuse_for_future,
        ),
    )
    txn = session.get(m.FinancialTransaction, transaction_id)
    txn.review_status = "REVIEWED"
    session.flush()
    return result
