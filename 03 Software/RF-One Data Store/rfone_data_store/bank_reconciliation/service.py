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
mechanism.

BANK_RECONCILIATION_INSTRUMENT_ASSIGNMENT_001 (web collaudo findings)
adds three things to this same module, without a second ledger and
without ever touching the raw preservation layer:

  * **Per-row source resolution.** A batch is no longer resolved only as
    a whole. A Chase credit-card export carrying several distinct `Card`
    values resolves each ROW to its own instrument; only rows whose
    identifier is unknown are left unnormalized for a human.
  * **Correction.** `assign_batch_instrument` /
    `reassign_transaction_instrument` correct an assignment already made,
    updating the existing `FinancialTransaction` rows in place
    (idempotently, never deleting and never re-inserting), re-running
    duplicate detection, Recognition and matching, and writing one
    `BankInstrumentAssignmentAudit` row per correction.
  * **Reuse.** A human's one-off resolution of a source that cannot
    identify itself (First Citizens' `AccountHistory.csv`) can be saved as
    a `BankSourceInstrumentProfile` and reused by later imports.

A file name is still never authoritative on its own (spec §3.2). It is
used only as the WEAKEST evidence, after the file's own content and after
a rule a human explicitly confirmed — see `resolve_instrument_for_source`.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import accounting_dedup
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


def normalize_institution(value: str | None) -> str | None:
    """Institution names are entered by humans and have been observed in
    the same database as both `CHASE` and `Chase`, `FIRST_CITIZENS` and
    `First Citizens`. Automatic source resolution must not depend on which
    spelling someone happened to type, so every institution comparison in
    this module goes through this one normalization: upper-cased, with any
    run of non-alphanumeric characters collapsed to a single underscore."""
    if value is None:
        return None
    collapsed = re.sub(r"[^A-Z0-9]+", "_", value.strip().upper()).strip("_")
    return collapsed or None


CHASE = "CHASE"
FIRST_CITIZENS = "FIRST_CITIZENS"

# Windows appends ` (1)`, ` (2)`, ... when the same file is downloaded
# twice into the same folder. That suffix is a download artifact, never
# part of the source's identity.
_WINDOWS_COPY_SUFFIX_RE = re.compile(r"\s*\(\d+\)\s*$")
# A trailing run of 6-8 digits, optionally separated, is the export date
# (`Chase2915_Activity_20260920`) — variable by definition, so it is
# removed before the file name is used as a stable key.
_TRAILING_DATE_RE = re.compile(r"[_\-\s]*\d{6,8}$")
_CHASE_FILE_LAST_FOUR_RE = re.compile(r"^chase(\d{4})(?:[_\-].*)?$")


def file_name_key(original_file_name: str | None) -> str | None:
    """The stable part of a source file's name: lower-cased, without its
    extension, without a Windows `(1)`/`(2)` duplication suffix, and
    without a trailing export date.

        'Chase2915_Activity_20260920 (1).csv' -> 'chase2915_activity'
        'AccountHistory.csv'                  -> 'accounthistory'

    Used as the key of a `BankSourceInstrumentProfile` and as the weakest
    resolution hint — never as authoritative identity on its own."""
    if not original_file_name:
        return None
    name = original_file_name.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if "." in name:
        name = name.rsplit(".", 1)[0]
    name = _WINDOWS_COPY_SUFFIX_RE.sub("", name)
    name = _TRAILING_DATE_RE.sub("", name)
    name = name.strip().strip("_-").lower()
    return name or None


def chase_last_four_from_file_name(original_file_name: str | None) -> str | None:
    """`Chase2915_Activity_20260920 (1).csv` -> `'2915'`.

    The date and the Windows duplication suffix are ignored (they are
    stripped by `file_name_key` before this pattern is applied). Returns
    None for any name that does not literally start with `Chase` followed
    by exactly four digits — nothing is guessed."""
    key = file_name_key(original_file_name)
    if not key:
        return None
    match = _CHASE_FILE_LAST_FOUR_RE.match(key)
    return match.group(1) if match else None


def _instrument_last_four(instrument: "m.PaymentInstrument") -> str | None:
    return instrument.last_four or extract_last_four(instrument.external_account_identifier)


def _active_instruments(session: Session) -> list["m.PaymentInstrument"]:
    return list(session.scalars(
        select(m.PaymentInstrument).where(m.PaymentInstrument.status == "ACTIVE")
        .order_by(m.PaymentInstrument.id)
    ).all())


# ---------------------------------------------------------------------------
# Source resolution — which Payment Instrument did this file/row come from
# ---------------------------------------------------------------------------

BASIS_IN_FILE_IDENTIFIER = "IN_FILE_IDENTIFIER"
BASIS_SAVED_PROFILE = "SAVED_SOURCE_PROFILE"
BASIS_FILE_NAME_HINT = "FILE_NAME_HINT"
BASIS_ONLY_COMPATIBLE_INSTRUMENT = "ONLY_COMPATIBLE_INSTRUMENT"


@dataclass
class InstrumentResolution:
    """The outcome of trying to decide which `PaymentInstrument` a source
    file (or one of its rows) belongs to. `instrument is None` with a
    non-empty `candidates` list is genuine ambiguity — a human must
    choose; it is never resolved by picking the first match."""

    instrument: "m.PaymentInstrument | None" = None
    basis: str | None = None
    candidates: list["m.PaymentInstrument"] = field(default_factory=list)
    detail: str = ""

    @property
    def ambiguous(self) -> bool:
        return self.instrument is None and len(self.candidates) > 1


def _institution_for_format(detected_format: str) -> str | None:
    if detected_format == parsers.FIRST_CITIZENS:
        return FIRST_CITIZENS
    if detected_format in (
        parsers.CHASE_BANK_ACCOUNT, parsers.CHASE_CREDIT_CARD_WITH_CARD,
        parsers.CHASE_CREDIT_CARD_NO_CARD,
    ):
        return CHASE
    return None


def _instrument_type_for_format(detected_format: str) -> str | None:
    if detected_format in (parsers.CHASE_CREDIT_CARD_WITH_CARD, parsers.CHASE_CREDIT_CARD_NO_CARD):
        return "CREDIT_CARD"
    if detected_format in (parsers.CHASE_BANK_ACCOUNT, parsers.FIRST_CITIZENS):
        return "BANK_ACCOUNT"
    return None


def _compatible_instruments(
    session: Session, detected_format: str,
) -> list["m.PaymentInstrument"]:
    """Every ACTIVE instrument that could plausibly be the source of a file
    in `detected_format` — same institution and same instrument type. Type
    is part of compatibility because a Chase credit-card export can never
    be a Chase bank account, however similar the names look."""
    institution = _institution_for_format(detected_format)
    instrument_type = _instrument_type_for_format(detected_format)
    result = []
    for instrument in _active_instruments(session):
        if institution and normalize_institution(instrument.institution) != institution:
            continue
        if instrument_type and instrument.instrument_type != instrument_type:
            continue
        result.append(instrument)
    return result


def _match_by_account_hint(
    session: Session, detected_format: str, account_hint: str,
) -> list["m.PaymentInstrument"]:
    """Instruments whose own configured identifier matches the identifier
    the FILE ITSELF carries — the strongest available evidence (spec §5.2).
    An exact `external_account_identifier` match wins outright; otherwise
    the last four digits are compared."""
    compatible = _compatible_instruments(session, detected_format)
    exact = [i for i in compatible if i.external_account_identifier
             and i.external_account_identifier.strip() == account_hint.strip()]
    if exact:
        return exact
    last_four = extract_last_four(account_hint)
    if not last_four:
        return []
    return [i for i in compatible if _instrument_last_four(i) == last_four]


def find_source_profile(
    session: Session, *, detected_format: str, account_hint: str | None,
    original_file_name: str | None,
) -> "m.BankSourceInstrumentProfile | None":
    """The ACTIVE rule a human previously taught for this source, if any.
    An `account_hint` rule is more specific than a file-name rule and is
    tried first."""
    if account_hint:
        profile = session.scalars(
            select(m.BankSourceInstrumentProfile).where(
                m.BankSourceInstrumentProfile.status == "ACTIVE",
                m.BankSourceInstrumentProfile.detected_format == detected_format,
                m.BankSourceInstrumentProfile.account_hint == account_hint,
            )
        ).first()
        if profile is not None:
            return profile
    key = file_name_key(original_file_name)
    if key:
        return session.scalars(
            select(m.BankSourceInstrumentProfile).where(
                m.BankSourceInstrumentProfile.status == "ACTIVE",
                m.BankSourceInstrumentProfile.detected_format == detected_format,
                m.BankSourceInstrumentProfile.file_name_key == key,
                m.BankSourceInstrumentProfile.account_hint.is_(None),
            )
        ).first()
    return None


def resolve_instrument_for_source(
    session: Session, *, detected_format: str, account_hint: str | None = None,
    original_file_name: str | None = None,
) -> InstrumentResolution:
    """Decide which instrument a source belongs to, using the strongest
    available evidence first:

      1. the identifier the FILE ITSELF carries (`account_hint`) — First
         Citizens' `Account Number`, Chase Variant A's `Card`;
      2. a `BankSourceInstrumentProfile` a human explicitly saved for this
         source;
      3. the file name's own `Chase####` prefix, matched against an
         instrument's configured last four digits — a hint only, used
         solely when the content offered nothing;
      4. exactly ONE compatible instrument existing at all (First Citizens
         with a single account: nothing is ambiguous, so nothing needs a
         human).

    Ambiguity is never resolved by guessing: when more than one instrument
    matches, `instrument` stays None and `candidates` lists them all."""
    if account_hint:
        matches = _match_by_account_hint(session, detected_format, account_hint)
        if len(matches) == 1:
            return InstrumentResolution(
                instrument=matches[0], basis=BASIS_IN_FILE_IDENTIFIER,
                detail=f"in-file identifier {account_hint!r}",
            )
        if len(matches) > 1:
            return InstrumentResolution(
                candidates=matches, basis=BASIS_IN_FILE_IDENTIFIER,
                detail=(
                    f"in-file identifier {account_hint!r} matches {len(matches)} instruments — "
                    "a human must choose"
                ),
            )

    profile = find_source_profile(
        session, detected_format=detected_format, account_hint=account_hint,
        original_file_name=original_file_name,
    )
    if profile is not None and profile.payment_instrument is not None:
        if profile.payment_instrument.status == "ACTIVE":
            return InstrumentResolution(
                instrument=profile.payment_instrument, basis=BASIS_SAVED_PROFILE,
                detail=f"saved source rule #{profile.id}",
            )

    file_last_four = chase_last_four_from_file_name(original_file_name)
    if file_last_four and _institution_for_format(detected_format) == CHASE:
        matches = [
            i for i in _compatible_instruments(session, detected_format)
            if _instrument_last_four(i) == file_last_four
        ]
        if len(matches) == 1:
            return InstrumentResolution(
                instrument=matches[0], basis=BASIS_FILE_NAME_HINT,
                detail=f"file name last four {file_last_four!r}",
            )
        if len(matches) > 1:
            return InstrumentResolution(
                candidates=matches, basis=BASIS_FILE_NAME_HINT,
                detail=(
                    f"file name last four {file_last_four!r} matches {len(matches)} instruments — "
                    "a human must choose"
                ),
            )

    compatible = _compatible_instruments(session, detected_format)
    if not compatible:
        return InstrumentResolution(detail="no compatible Payment Instrument is configured")

    # "Exactly one compatible instrument exists, so nothing is ambiguous"
    # applies to FIRST CITIZENS only. `AccountHistory.csv` never changes
    # name and its account number is often masked beyond recognition, so
    # with a single First Citizens account there is genuinely nothing for a
    # human to decide.
    #
    # It deliberately does NOT apply to Chase: spec §3.2 requires an
    # explicit human-confirmed instrument for a Chase source that carries
    # no reliable identifier, and that approved rule is not relaxed here.
    # The one Chase automation added by this task is the `Chase####`
    # file-name prefix matched against a configured last four (above) —
    # evidence about THIS file, not an inference from how few instruments
    # happen to be configured.
    if detected_format == parsers.FIRST_CITIZENS and len(compatible) == 1:
        return InstrumentResolution(
            instrument=compatible[0], basis=BASIS_ONLY_COMPATIBLE_INSTRUMENT,
            detail="the only compatible First Citizens instrument",
        )

    return InstrumentResolution(
        candidates=compatible,
        detail=(
            f"no reliable identifier in the file; {len(compatible)} compatible instrument(s) "
            "configured — a human must confirm which one"
        ),
    )


def auto_resolve_payment_instrument(
    session: Session, detected_format: str, account_hint: str | None,
) -> "m.PaymentInstrument | None":
    """Backwards-compatible thin wrapper over `resolve_instrument_for_source`
    for callers that only want "the instrument, if it is unambiguous".
    Kept because it is the published entry point of this module's original
    source-resolution behavior; it returns None for ambiguity exactly as
    before, never a first-of-many guess."""
    return resolve_instrument_for_source(
        session, detected_format=detected_format, account_hint=account_hint,
    ).instrument


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
    # Rows whose own identifier could not be resolved to an instrument —
    # normalization is deferred for exactly those rows, never guessed.
    unresolved_row_count: int = 0
    resolution_detail: str = ""


def _resolutions_for_rows(
    session: Session, *, detected_format: str, original_file_name: str,
    parsed_rows: list["parsers.ParsedBankRow"], forced_instrument: "m.PaymentInstrument | None",
) -> tuple[dict[int, "m.PaymentInstrument"], "m.PaymentInstrument | None", str]:
    """Map each row number to the instrument it belongs to.

    A file carrying a SINGLE identifier (or none at all) resolves once, as
    a whole, and the resolved instrument also becomes the batch's own.
    A file carrying SEVERAL distinct identifiers (a Chase credit-card
    export with more than one `Card`) resolves ROW BY ROW and the batch
    itself stays unresolved — attributing all of its rows to one
    instrument would be wrong, not merely imprecise."""
    if forced_instrument is not None:
        return ({r.row_number: forced_instrument for r in parsed_rows}, forced_instrument,
                "instrument confirmed by the operator at upload time")

    hints = {r.account_hint for r in parsed_rows if r.account_hint}

    if len(hints) <= 1:
        hint = next(iter(hints)) if hints else None
        resolution = resolve_instrument_for_source(
            session, detected_format=detected_format, account_hint=hint,
            original_file_name=original_file_name,
        )
        if resolution.instrument is None:
            return ({}, None, resolution.detail)
        return (
            {r.row_number: resolution.instrument for r in parsed_rows},
            resolution.instrument,
            f"resolved by {resolution.basis} ({resolution.detail})",
        )

    per_row: dict[int, "m.PaymentInstrument"] = {}
    unresolved_hints: set[str] = set()
    for row in parsed_rows:
        if not row.account_hint:
            continue
        resolution = resolve_instrument_for_source(
            session, detected_format=detected_format, account_hint=row.account_hint,
            original_file_name=None,  # per-row: the file name says nothing about a single row
        )
        if resolution.instrument is not None:
            per_row[row.row_number] = resolution.instrument
        else:
            unresolved_hints.add(row.account_hint)

    detail = (
        f"file carries {len(hints)} distinct in-file identifiers — resolved per row "
        f"({len(per_row)} row(s) resolved"
    )
    if unresolved_hints:
        detail += f", unknown identifier(s): {', '.join(sorted(unresolved_hints))}"
    detail += ")"
    return per_row, None, detail


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

    forced: "m.PaymentInstrument | None" = None
    if payment_instrument_id is not None:
        forced = session.get(m.PaymentInstrument, payment_instrument_id)

    instrument_by_row, batch_instrument, resolution_detail = _resolutions_for_rows(
        session, detected_format=parsed_file.detected_format, original_file_name=original_file_name,
        parsed_rows=parsed_file.rows, forced_instrument=forced,
    )

    if batch_instrument is not None:
        batch.payment_instrument_id = batch_instrument.id

    normalized_count, candidate_count = _normalize_rows(
        session, batch, parsed_file.rows, raw_objs, instrument_by_row,
    )
    if batch_instrument is not None:
        batch.overlap_warning = _compute_overlap_warning(session, batch, batch_instrument)

    unresolved_count = sum(
        1 for r in parsed_file.rows
        if r.parse_status != "UNREADABLE" and r.row_number not in instrument_by_row
    )

    if unreadable_count:
        batch.error_summary = (
            f"{unreadable_count} row(s) could not be parsed — see individual "
            "RawBankTransaction.anomalies."
        )

    _refresh_batch_status(session, batch)
    session.flush()
    return ImportResult(
        batch=batch, created=True, parsed_row_count=len(parsed_file.rows),
        unreadable_row_count=unreadable_count, normalized_row_count=normalized_count,
        candidate_duplicate_count=candidate_count, unresolved_row_count=unresolved_count,
        resolution_detail=resolution_detail,
    )


# ---------------------------------------------------------------------------
# Instrument assignment — first resolution and later correction
# ---------------------------------------------------------------------------


def _record_assignment_audit(
    session: Session, *, scope: str, batch: "m.BankImportBatch | None",
    transaction: "m.FinancialTransaction | None", previous_instrument_id: int | None,
    new_instrument_id: int, reason: str, affected_transaction_count: int,
    changed_by_account_id: int | None,
) -> "m.BankInstrumentAssignmentAudit":
    audit = m.BankInstrumentAssignmentAudit(
        scope=scope,
        import_batch_id=batch.id if batch is not None else None,
        financial_transaction_id=transaction.id if transaction is not None else None,
        previous_payment_instrument_id=previous_instrument_id,
        new_payment_instrument_id=new_instrument_id,
        reason=reason.strip(),
        affected_transaction_count=affected_transaction_count,
        changed_by_account_id=changed_by_account_id,
    )
    session.add(audit)
    session.flush()
    return audit


def _recompute_duplicate_state(session: Session, txn: "m.FinancialTransaction") -> bool:
    """Re-run spec §7/§8 duplicate detection for ONE transaction against
    its CURRENT instrument. Returns True when it is now a candidate
    duplicate.

    An explicit human decision (`CONFIRMED_DUPLICATE`/`CONFIRMED_DISTINCT`)
    is preserved as long as the transaction it was decided against is
    still on the same instrument — that decision is still about the same
    pair. Once the counterpart no longer shares the instrument the decision
    no longer means anything, so the automatic state is recomputed; nothing
    is ever deleted either way."""
    if txn.duplicate_status in ("CONFIRMED_DUPLICATE", "CONFIRMED_DISTINCT"):
        counterpart = (
            session.get(m.FinancialTransaction, txn.duplicate_of_transaction_id)
            if txn.duplicate_of_transaction_id else None
        )
        if counterpart is not None and counterpart.payment_instrument_id == txn.payment_instrument_id:
            return False

    earlier = session.scalars(
        select(m.FinancialTransaction)
        .where(
            m.FinancialTransaction.payment_instrument_id == txn.payment_instrument_id,
            m.FinancialTransaction.posting_date == txn.posting_date,
            m.FinancialTransaction.amount_minor == txn.amount_minor,
            m.FinancialTransaction.description_normalized == txn.description_normalized,
            m.FinancialTransaction.id != txn.id,
            m.FinancialTransaction.id < txn.id,
        )
        .order_by(m.FinancialTransaction.id.asc())
    ).first()

    if earlier is not None:
        txn.duplicate_status = "CANDIDATE_DUPLICATE"
        txn.duplicate_of_transaction_id = earlier.id
        return True
    txn.duplicate_status = "NONE"
    txn.duplicate_of_transaction_id = None
    return False


def _reprocess_transaction(session: Session, txn: "m.FinancialTransaction") -> bool:
    """Everything that must be re-derived after a transaction's instrument
    changed: identity fingerprint, duplicate state, Recognition, and
    cross-ledger matching. Idempotent — running it twice on an unchanged
    transaction produces the same state and creates nothing new.

    Recognition is re-run ONLY when the current decision was not made by a
    human: `BankRecognitionRule`s can be scoped to a payment instrument, so
    the correct rule may genuinely differ after a correction — but a human's
    own confirmed decision is never overwritten by a rule."""
    if txn.posting_date is not None and txn.amount_minor is not None:
        txn.fingerprint = compute_identity_fingerprint(
            payment_instrument_id=txn.payment_instrument_id,
            posting_date=txn.posting_date,
            description_normalized=txn.description_normalized or "",
            amount_minor=txn.amount_minor,
            native_transaction_type=txn.native_transaction_type,
            reference=txn.reference,
            balance_minor=txn.balance_minor,
        )
    is_candidate = _recompute_duplicate_state(session, txn)
    session.flush()

    current = recognition.get_current_explanation(session, financial_transaction_id=txn.id)
    if current is None or current.decision_source != "HUMAN":
        recognition.deduce_for_transaction(session, txn)

    matching.on_financial_transaction_acquired(session, txn)
    session.flush()
    return is_candidate


def _refresh_batch_status(session: Session, batch: "m.BankImportBatch") -> str:
    """Recompute `BankImportBatch.status` from what is actually true right
    now — used after import and after every correction, so the status a
    human reads is never stale."""
    state = compute_batch_review_state(session, batch)
    batch.status = state.status
    return batch.status


def _raw_rows_for_batch(session: Session, batch: "m.BankImportBatch") -> list["m.RawBankTransaction"]:
    return list(session.scalars(
        select(m.RawBankTransaction)
        .where(m.RawBankTransaction.import_batch_id == batch.id)
        .order_by(m.RawBankTransaction.row_number)
    ).all())


def batch_distinct_account_hints(
    session: Session, batch: "m.BankImportBatch", raw_rows: list["m.RawBankTransaction"] | None = None,
) -> set[str]:
    """The distinct in-file identifiers this batch's rows carry, read back
    from the preserved raw fields (never from the original file, which is
    never re-read). More than one means the file is NOT a single
    account/card and must never be assigned as a whole."""
    rows = raw_rows if raw_rows is not None else _raw_rows_for_batch(session, batch)
    hints: set[str] = set()
    for raw in rows:
        parsed = parsers.parse_row_fields(batch.detected_format, raw.row_number, raw.raw_fields)
        if parsed.account_hint:
            hints.add(parsed.account_hint)
    return hints


def normalize_pending_rows(
    session: Session, *, batch_id: int,
) -> tuple[int, int]:
    """Normalize the rows of an already-imported batch that are still
    waiting for an instrument, re-running source resolution against the
    CURRENT instrument configuration.

    This is the action for a file that mixes several cards: once the
    missing instrument is configured (or its last four filled in), its
    rows resolve by their own `Card` value — the batch is never collapsed
    onto one instrument to make the pending rows go away. Returns
    `(normalized, candidate_duplicates)` and is safe to re-run: rows
    already normalized are skipped."""
    batch = session.get(m.BankImportBatch, batch_id)
    if batch is None:
        raise ValueError(f"BankImportBatch {batch_id} not found")

    raw_rows = _raw_rows_for_batch(session, batch)
    pending = [
        r for r in raw_rows
        if r.normalized_transaction_id is None and r.parse_status != "UNREADABLE"
    ]
    if not pending:
        return 0, 0

    parsed_rows = [
        parsers.parse_row_fields(batch.detected_format, r.row_number, r.raw_fields)
        for r in pending
    ]
    forced = batch.payment_instrument if batch.payment_instrument_id is not None else None
    instrument_by_row, _batch_instrument, _detail = _resolutions_for_rows(
        session, detected_format=batch.detected_format,
        original_file_name=batch.original_file_name, parsed_rows=parsed_rows,
        forced_instrument=forced,
    )
    normalized, candidates = _normalize_rows(
        session, batch, parsed_rows, pending, instrument_by_row,
    )
    if batch.payment_instrument is not None:
        batch.overlap_warning = _compute_overlap_warning(session, batch, batch.payment_instrument)
    _refresh_batch_status(session, batch)
    session.flush()
    return normalized, candidates


def assign_batch_instrument(
    session: Session, *, batch_id: int, payment_instrument_id: int,
    reason: str | None = None, changed_by_account_id: int | None = None,
    save_as_source_profile: bool = False,
) -> "ImportResult":
    """Assign — or CORRECT — the Payment Instrument of a whole batch.

    First resolution (the batch had none) normalizes its rows from their
    already-preserved `raw_fields` (spec §4.1), exactly as `import_csv`
    would have done had the instrument been known at upload time.

    A correction (the batch already had an instrument) never deletes and
    never re-inserts anything: the existing `FinancialTransaction` rows are
    updated in place, then reprocessed (fingerprint, duplicates,
    Recognition, matching). Re-running the same correction is a no-op.

    A reason is REQUIRED for a correction — a change of an assignment a
    human already made must say why."""
    batch = session.get(m.BankImportBatch, batch_id)
    if batch is None:
        raise ValueError(f"BankImportBatch {batch_id} not found")
    instrument = session.get(m.PaymentInstrument, payment_instrument_id)
    if instrument is None:
        raise ValueError(f"PaymentInstrument {payment_instrument_id} not found")

    previous_instrument_id = batch.payment_instrument_id
    is_correction = previous_instrument_id is not None
    if is_correction and not (reason or "").strip():
        raise ValueError("A reason is required to change an assignment that was already made.")
    if is_correction and previous_instrument_id == instrument.id:
        raise ValueError(
            f"Batch {batch_id} is already assigned to {instrument.display_name!r} — nothing to change."
        )

    raw_objs = _raw_rows_for_batch(session, batch)

    # A file that genuinely carries several different cards has no single
    # correct batch-level answer: assigning it as a whole would silently
    # attribute other cards' rows to this instrument. Refuse, and point at
    # the two actions that ARE correct.
    distinct_hints = batch_distinct_account_hints(session, batch, raw_objs)
    if len(distinct_hints) > 1:
        raise ValueError(
            f"This file carries {len(distinct_hints)} different in-file identifiers "
            f"({', '.join(sorted(distinct_hints))}) — it is not a single account or card, so it "
            "cannot be assigned as a whole. Configure the missing instrument (its last four "
            "digits) and use 'Normalize pending rows', or reassign an individual transaction "
            "from Review Transactions."
        )

    existing_transactions = list(session.scalars(
        select(m.FinancialTransaction)
        .where(m.FinancialTransaction.import_batch_id == batch.id)
        .order_by(m.FinancialTransaction.id)
    ).all())

    batch.payment_instrument_id = instrument.id

    candidate_count = 0
    normalized_count = 0

    # Rows already normalized: move them, never recreate them.
    for txn in existing_transactions:
        txn.payment_instrument_id = instrument.id
    session.flush()
    for txn in existing_transactions:
        if _reprocess_transaction(session, txn):
            candidate_count += 1
        normalized_count += 1

    # Rows never normalized (the batch had no instrument, or a row's own
    # identifier was unknown): normalize them now, from preserved raw
    # fields only — the original file is never re-read.
    already_normalized_row_numbers = {
        r.row_number for r in raw_objs if r.normalized_transaction_id is not None
    }
    pending_raw = [r for r in raw_objs if r.row_number not in already_normalized_row_numbers]
    if pending_raw:
        parsed_rows = [
            parsers.parse_row_fields(batch.detected_format, r.row_number, r.raw_fields)
            for r in pending_raw
        ]
        instrument_by_row = {r.row_number: instrument for r in parsed_rows}
        added, added_candidates = _normalize_rows(
            session, batch, parsed_rows, pending_raw, instrument_by_row,
        )
        normalized_count += added
        candidate_count += added_candidates

    batch.overlap_warning = _compute_overlap_warning(session, batch, instrument)

    _record_assignment_audit(
        session, scope="BATCH", batch=batch, transaction=None,
        previous_instrument_id=previous_instrument_id, new_instrument_id=instrument.id,
        reason=(reason or "First resolution of a batch whose file carried no reliable identifier."),
        affected_transaction_count=normalized_count,
        changed_by_account_id=changed_by_account_id,
    )

    if save_as_source_profile:
        save_source_profile(
            session,
            detected_format=batch.detected_format,
            account_hint=next(iter(distinct_hints)) if len(distinct_hints) == 1 else None,
            original_file_name=batch.original_file_name,
            payment_instrument_id=instrument.id,
            created_from_batch_id=batch.id,
            created_by_account_id=changed_by_account_id,
        )

    unreadable_count = sum(1 for r in raw_objs if r.parse_status == "UNREADABLE")
    _refresh_batch_status(session, batch)
    session.flush()

    return ImportResult(
        batch=batch, created=True, parsed_row_count=len(raw_objs),
        unreadable_row_count=unreadable_count, normalized_row_count=normalized_count,
        candidate_duplicate_count=candidate_count, unresolved_row_count=0,
        resolution_detail="corrected by a human" if is_correction else "resolved by a human",
    )


def resolve_batch_instrument(
    session: Session, *, batch_id: int, payment_instrument_id: int,
    reason: str | None = None, changed_by_account_id: int | None = None,
    save_as_source_profile: bool = False,
) -> "ImportResult":
    """Human resolution of a batch (spec §3.2). Kept as the published name
    of this operation; correction of an already-assigned batch is the same
    operation and is delegated to `assign_batch_instrument`, which records
    the audit row either way."""
    return assign_batch_instrument(
        session, batch_id=batch_id, payment_instrument_id=payment_instrument_id,
        reason=reason, changed_by_account_id=changed_by_account_id,
        save_as_source_profile=save_as_source_profile,
    )


def reassign_transaction_instrument(
    session: Session, *, transaction_id: int, payment_instrument_id: int,
    reason: str, changed_by_account_id: int | None = None,
) -> "m.FinancialTransaction":
    """Correct ONE transaction's instrument — the case of a single source
    file carrying several cards, where the batch as a whole has no single
    correct answer. The row is updated in place and reprocessed; its raw
    row and the batch's raw file are untouched, and no row is created or
    deleted."""
    if not (reason or "").strip():
        raise ValueError("A reason is required to reassign a transaction.")
    txn = session.get(m.FinancialTransaction, transaction_id)
    if txn is None:
        raise ValueError(f"FinancialTransaction {transaction_id} not found")
    instrument = session.get(m.PaymentInstrument, payment_instrument_id)
    if instrument is None:
        raise ValueError(f"PaymentInstrument {payment_instrument_id} not found")
    previous_instrument_id = txn.payment_instrument_id
    if previous_instrument_id == instrument.id:
        raise ValueError(
            f"Transaction {transaction_id} is already assigned to {instrument.display_name!r} — "
            "nothing to change."
        )

    txn.payment_instrument_id = instrument.id
    session.flush()
    _reprocess_transaction(session, txn)

    _record_assignment_audit(
        session, scope="TRANSACTION", batch=txn.import_batch, transaction=txn,
        previous_instrument_id=previous_instrument_id, new_instrument_id=instrument.id,
        reason=reason, affected_transaction_count=1,
        changed_by_account_id=changed_by_account_id,
    )

    if txn.import_batch is not None:
        _refresh_batch_status(session, txn.import_batch)

    # The transaction now belongs to a different instrument, so its
    # settlement account — and therefore its accounting identity — may
    # have changed. Both the group it left and the group it joins are
    # re-resolved.
    accounting_dedup.recompute_accounting_dedup(
        session,
        payment_instrument_ids=sorted({previous_instrument_id, instrument.id} - {None}),
    )
    session.flush()
    return txn


def recompute_accounting_deduplication(
    session: Session, *, payment_instrument_ids: list[int] | None = None,
) -> "accounting_dedup.DedupOutcome":
    """The one public entry point for re-running accounting deduplication
    (BANK_CARDHOLDER_AND_ACCOUNTING_DEDUPLICATION_001). Idempotent and
    safe to call at any time: it re-derives everything from the current
    transactions and the current card configuration, writes only the
    accounting-dedup columns, and never touches the raw layer, an amount,
    a date, a description, the per-instrument `duplicate_status` flow, or
    a reconciliation decision.

    Called by the web layer after a settlement account is assigned or
    corrected — the configuration change that most often turns an
    un-deduplicable row into a resolvable one."""
    return accounting_dedup.recompute_accounting_dedup(
        session, payment_instrument_ids=payment_instrument_ids,
    )


# ---------------------------------------------------------------------------
# Reusable source rules
# ---------------------------------------------------------------------------


def save_source_profile(
    session: Session, *, detected_format: str, payment_instrument_id: int,
    account_hint: str | None = None, original_file_name: str | None = None,
    created_from_batch_id: int | None = None, created_by_account_id: int | None = None,
    notes: str | None = None,
) -> "m.BankSourceInstrumentProfile":
    """Save (or re-point, or re-activate) the rule that resolves this kind
    of source to this instrument. Idempotent on its key: teaching the same
    source twice updates the one rule instead of accumulating rules."""
    key = None if account_hint else file_name_key(original_file_name)
    if not key and not account_hint:
        raise ValueError(
            "A source rule needs either an in-file identifier or a usable file name to key on."
        )
    if session.get(m.PaymentInstrument, payment_instrument_id) is None:
        raise ValueError(f"PaymentInstrument {payment_instrument_id} not found")

    name_condition = (
        m.BankSourceInstrumentProfile.file_name_key.is_(None) if key is None
        else m.BankSourceInstrumentProfile.file_name_key == key
    )
    hint_condition = (
        m.BankSourceInstrumentProfile.account_hint.is_(None) if account_hint is None
        else m.BankSourceInstrumentProfile.account_hint == account_hint
    )
    existing = session.scalars(
        select(m.BankSourceInstrumentProfile).where(
            m.BankSourceInstrumentProfile.detected_format == detected_format,
            name_condition,
            hint_condition,
        )
    ).first()
    if existing is not None:
        existing.payment_instrument_id = payment_instrument_id
        existing.status = "ACTIVE"
        if notes:
            existing.notes = notes
        session.flush()
        return existing

    profile = m.BankSourceInstrumentProfile(
        detected_format=detected_format, file_name_key=key, account_hint=account_hint,
        payment_instrument_id=payment_instrument_id, status="ACTIVE",
        created_from_batch_id=created_from_batch_id, created_by_account_id=created_by_account_id,
        notes=notes,
    )
    session.add(profile)
    session.flush()
    return profile


def set_source_profile_status(
    session: Session, *, profile_id: int, status: str,
) -> "m.BankSourceInstrumentProfile":
    """Enable or disable a saved rule. Disabling never deletes it — the
    evidence that a human once taught this mapping is kept."""
    if status not in ("ACTIVE", "INACTIVE"):
        raise ValueError(f"Invalid source rule status: {status!r}")
    profile = session.get(m.BankSourceInstrumentProfile, profile_id)
    if profile is None:
        raise ValueError(f"BankSourceInstrumentProfile {profile_id} not found")
    profile.status = status
    session.flush()
    return profile


def update_source_profile_instrument(
    session: Session, *, profile_id: int, payment_instrument_id: int,
) -> "m.BankSourceInstrumentProfile":
    profile = session.get(m.BankSourceInstrumentProfile, profile_id)
    if profile is None:
        raise ValueError(f"BankSourceInstrumentProfile {profile_id} not found")
    if session.get(m.PaymentInstrument, payment_instrument_id) is None:
        raise ValueError(f"PaymentInstrument {payment_instrument_id} not found")
    profile.payment_instrument_id = payment_instrument_id
    session.flush()
    return profile


# ---------------------------------------------------------------------------
# Payment Instrument configuration
# ---------------------------------------------------------------------------

VALID_INSTRUMENT_TYPES = ("BANK_ACCOUNT", "CREDIT_CARD", "PAYPAL")
VALID_INSTRUMENT_STATUSES = ("ACTIVE", "INACTIVE")

_UNSET = object()


def _assert_no_resolution_conflict(
    session: Session, *, instrument_id: int | None, institution: str | None,
    instrument_type: str, last_four: str | None, external_account_identifier: str | None,
    status: str,
) -> None:
    """Two ACTIVE instruments of the same institution and type that carry
    the SAME identifier would make automatic source resolution ambiguous
    forever — every import of that account would need a human. Refuse the
    configuration instead of silently degrading recognition.

    Only ACTIVE instruments are compared: closing an old card and opening a
    new one with the same last four is a legitimate, non-ambiguous state as
    long as only one of them is active."""
    if status != "ACTIVE":
        return
    normalized_institution = normalize_institution(institution)
    effective_last_four = last_four or extract_last_four(external_account_identifier)
    if not normalized_institution or not (effective_last_four or external_account_identifier):
        return

    for other in _active_instruments(session):
        if instrument_id is not None and other.id == instrument_id:
            continue
        if normalize_institution(other.institution) != normalized_institution:
            continue
        if other.instrument_type != instrument_type:
            continue
        if (external_account_identifier and other.external_account_identifier
                and other.external_account_identifier.strip() == external_account_identifier.strip()):
            raise ValueError(
                f"{other.display_name!r} (id={other.id}) already uses account identifier "
                f"{external_account_identifier!r} for the same institution and instrument type — "
                "automatic source recognition could not tell the two apart."
            )
        if effective_last_four and _instrument_last_four(other) == effective_last_four:
            raise ValueError(
                f"{other.display_name!r} (id={other.id}) already uses last four "
                f"{effective_last_four!r} for the same institution and instrument type — "
                "automatic source recognition could not tell the two apart. Close (set INACTIVE) "
                "the instrument that is no longer in use, or give them distinct identifiers."
            )


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def create_payment_instrument(
    session: Session, *, institution: str | None, display_name: str, instrument_type: str,
    last_four: str | None = None, external_account_identifier: str | None = None,
    legal_entity_id: int | None = None, currency: str | None = None,
    linked_instrument_id: int | None = None, status: str = "ACTIVE",
) -> "m.PaymentInstrument":
    """Create an instrument with the same server-side validation an edit
    applies — so a conflicting instrument can never be created either."""
    return _write_payment_instrument(
        session, instrument=None, institution=institution, display_name=display_name,
        instrument_type=instrument_type, last_four=last_four,
        external_account_identifier=external_account_identifier, legal_entity_id=legal_entity_id,
        currency=currency, linked_instrument_id=linked_instrument_id, status=status,
    )


def update_payment_instrument(
    session: Session, *, instrument_id: int, institution: str | None = _UNSET,
    display_name: str | None = _UNSET, instrument_type: str | None = _UNSET,
    last_four: str | None = _UNSET, external_account_identifier: str | None = _UNSET,
    legal_entity_id: int | None = _UNSET, currency: str | None = _UNSET,
    linked_instrument_id: int | None = _UNSET, status: str | None = _UNSET,
) -> "m.PaymentInstrument":
    """Edit an existing instrument. Only the fields actually passed are
    changed. The canonical `PaymentInstrument` is edited in place — no
    parallel instrument model, and no new row that would orphan the
    transactions already pointing at this one."""
    instrument = session.get(m.PaymentInstrument, instrument_id)
    if instrument is None:
        raise ValueError(f"PaymentInstrument {instrument_id} not found")

    def pick(passed, current):
        return current if passed is _UNSET else passed

    return _write_payment_instrument(
        session, instrument=instrument,
        institution=pick(institution, instrument.institution),
        display_name=pick(display_name, instrument.display_name),
        instrument_type=pick(instrument_type, instrument.instrument_type),
        last_four=pick(last_four, instrument.last_four),
        external_account_identifier=pick(
            external_account_identifier, instrument.external_account_identifier
        ),
        legal_entity_id=pick(legal_entity_id, instrument.legal_entity_id),
        currency=pick(currency, instrument.currency),
        linked_instrument_id=pick(linked_instrument_id, instrument.linked_instrument_id),
        status=pick(status, instrument.status),
    )


def _write_payment_instrument(
    session: Session, *, instrument: "m.PaymentInstrument | None", institution: str | None,
    display_name: str | None, instrument_type: str | None, last_four: str | None,
    external_account_identifier: str | None, legal_entity_id: int | None, currency: str | None,
    linked_instrument_id: int | None, status: str | None,
) -> "m.PaymentInstrument":
    display_name = _clean(display_name)
    if not display_name:
        raise ValueError("Display name is required.")
    if instrument_type not in VALID_INSTRUMENT_TYPES:
        raise ValueError(
            f"Invalid instrument type {instrument_type!r} — must be one of {VALID_INSTRUMENT_TYPES}."
        )
    status = status or "ACTIVE"
    if status not in VALID_INSTRUMENT_STATUSES:
        raise ValueError(
            f"Invalid status {status!r} — must be one of {VALID_INSTRUMENT_STATUSES}."
        )

    institution = _clean(institution)
    last_four = _clean(last_four)
    if last_four is not None:
        if not (last_four.isdigit() and len(last_four) == 4):
            raise ValueError("Last four must be exactly four digits, or left empty.")
    external_account_identifier = _clean(external_account_identifier)
    currency = _clean(currency)
    if currency is not None:
        currency = currency.upper()

    if legal_entity_id is not None and session.get(m.LegalEntity, legal_entity_id) is None:
        raise ValueError(f"LegalEntity {legal_entity_id} not found")
    if linked_instrument_id is not None:
        if instrument is not None and linked_instrument_id == instrument.id:
            raise ValueError("An instrument cannot be linked to itself.")
        if session.get(m.PaymentInstrument, linked_instrument_id) is None:
            raise ValueError(f"Linked PaymentInstrument {linked_instrument_id} not found")

    _assert_no_resolution_conflict(
        session, instrument_id=instrument.id if instrument is not None else None,
        institution=institution, instrument_type=instrument_type, last_four=last_four,
        external_account_identifier=external_account_identifier, status=status,
    )

    if instrument is None:
        instrument = m.PaymentInstrument()
        session.add(instrument)

    instrument.institution = institution
    instrument.display_name = display_name
    instrument.instrument_type = instrument_type
    instrument.last_four = last_four
    instrument.external_account_identifier = external_account_identifier
    instrument.legal_entity_id = legal_entity_id
    instrument.currency = currency
    instrument.linked_instrument_id = linked_instrument_id
    instrument.status = status
    session.flush()
    return instrument


def instrument_export_warning(instrument: "m.PaymentInstrument") -> str | None:
    """The one configuration gap that does not prevent saving an instrument
    but DOES block the Monthly Export for every transaction on it
    (`export.compute_export_blockers`) — stated here once so the edit form
    and the instrument list say exactly the same thing."""
    if instrument.legal_entity_id is None:
        return (
            "No Company / Legal Entity: the instrument is saved, but the Monthly Export "
            "stays blocked for every month containing its transactions."
        )
    return None


# ---------------------------------------------------------------------------
# What a batch actually needs from a human
# ---------------------------------------------------------------------------

ACTION_RESOLVE_INSTRUMENT = "RESOLVE_INSTRUMENT"
ACTION_REVIEW_ISSUES = "REVIEW_ISSUES"
ACTION_NORMALIZE = "NORMALIZE"
ACTION_REPROCESS = "REPROCESS"


@dataclass
class BatchReviewState:
    """Why a batch is in the status it is in, and what the ONE thing a
    human can usefully do about it is. Computed from the live data, never
    stored — a status without a reason was the whole defect this replaces."""

    status: str
    reasons: list[str] = field(default_factory=list)
    action: str | None = None
    action_label: str = ""
    # Number of items the action concerns (candidate duplicates, unreadable
    # rows, rows still to normalize) — shown next to the status.
    item_count: int = 0
    candidate_duplicate_count: int = 0
    unreadable_row_count: int = 0
    unnormalized_row_count: int = 0
    normalized_row_count: int = 0
    needs_review_transaction_count: int = 0
    invalid_match_count: int = 0

    @property
    def has_work(self) -> bool:
        return self.action is not None


def compute_batch_review_state(
    session: Session, batch: "m.BankImportBatch",
) -> BatchReviewState:
    """The concrete reason a batch requires review, and the action that
    addresses it.

    This is what makes `REQUIRES_REVIEW` actionable: a batch that is fully
    normalized but holds a single candidate duplicate gets `Review issues`
    with "1 candidate duplicate" and a direct link to that row — it must
    NOT get a `Normalize` button, because there is nothing left to
    normalize."""
    raw_rows = list(session.scalars(
        select(m.RawBankTransaction).where(m.RawBankTransaction.import_batch_id == batch.id)
    ).all())
    transactions = list(session.scalars(
        select(m.FinancialTransaction).where(m.FinancialTransaction.import_batch_id == batch.id)
    ).all())

    unreadable = [r for r in raw_rows if r.parse_status == "UNREADABLE"]
    unnormalized = [
        r for r in raw_rows
        if r.parse_status != "UNREADABLE" and r.normalized_transaction_id is None
    ]
    candidates = [t for t in transactions if t.duplicate_status == "CANDIDATE_DUPLICATE"]
    needs_review = [t for t in transactions if t.review_status == "REQUIRES_REVIEW"]

    invalid_matches = 0
    for txn in transactions:
        for match in session.scalars(
            select(m.FinancialTransactionMatch).where(
                (m.FinancialTransactionMatch.transaction_a_id == txn.id)
                | (m.FinancialTransactionMatch.transaction_b_id == txn.id)
            )
        ).all():
            other_id = (
                match.transaction_b_id if match.transaction_a_id == txn.id else match.transaction_a_id
            )
            other = session.get(m.FinancialTransaction, other_id)
            if other is not None and other.payment_instrument_id == txn.payment_instrument_id:
                invalid_matches += 1

    state = BatchReviewState(
        status="NORMALIZED",
        candidate_duplicate_count=len(candidates),
        unreadable_row_count=len(unreadable),
        unnormalized_row_count=len(unnormalized),
        normalized_row_count=len(transactions),
        needs_review_transaction_count=len(needs_review),
        invalid_match_count=invalid_matches,
    )

    if batch.status == "REJECTED":
        state.status = "REJECTED"
        state.reasons.append("This batch was rejected.")
        return state

    if batch.payment_instrument_id is None and not transactions:
        state.status = "REQUIRES_REVIEW"
        state.reasons.append(
            "No Payment Instrument resolved — the file carries no identifier this configuration "
            "can match, so its rows have not been normalized."
        )
        state.action = ACTION_RESOLVE_INSTRUMENT
        state.action_label = "Resolve instrument"
        state.item_count = len(raw_rows)
        return state

    if unnormalized:
        state.status = "REQUIRES_REVIEW"
        distinct_hints = batch_distinct_account_hints(session, batch, raw_rows)
        if len(distinct_hints) > 1:
            state.reasons.append(
                f"{len(unnormalized)} row(s) carry an in-file identifier that matches no "
                f"configured instrument. This file mixes {len(distinct_hints)} cards, so it is "
                "resolved row by row — configure the missing instrument (with its last four "
                "digits) and normalize the pending rows."
            )
            state.action = ACTION_NORMALIZE
            state.action_label = "Normalize pending rows"
        elif batch.payment_instrument_id is None:
            state.reasons.append(
                f"{len(unnormalized)} row(s) are not normalized — no Payment Instrument is "
                "resolved for this file."
            )
            state.action = ACTION_RESOLVE_INSTRUMENT
            state.action_label = "Resolve instrument"
        else:
            state.reasons.append(f"{len(unnormalized)} row(s) still to normalize.")
            state.action = ACTION_NORMALIZE
            state.action_label = "Normalize"
        state.item_count = len(unnormalized)
        return state

    if unreadable:
        state.status = "REQUIRES_REVIEW"
        state.reasons.append(
            f"{len(unreadable)} row(s) could not be parsed and were preserved unmodified "
            "(see the row's own anomalies)."
        )
        state.action = ACTION_REVIEW_ISSUES
        state.action_label = "Review issues"
        state.item_count = len(unreadable)
        return state

    if candidates:
        state.status = "REQUIRES_REVIEW"
        state.reasons.append(
            f"{len(candidates)} candidate duplicate(s) awaiting a human Distinct/Duplicate decision."
        )
        state.action = ACTION_REVIEW_ISSUES
        state.action_label = "Review issues"
        state.item_count = len(candidates)
        return state

    if invalid_matches:
        state.status = "REQUIRES_REVIEW"
        state.reasons.append(
            f"{invalid_matches} confirmed internal-transfer match(es) now have both sides on the "
            "same instrument after a reassignment — nothing was deleted; re-check them."
        )
        state.action = ACTION_REPROCESS
        state.action_label = "Reprocess"
        state.item_count = invalid_matches
        return state

    state.status = "NORMALIZED"
    if needs_review:
        state.reasons.append(
            f"{len(needs_review)} transaction(s) still need a reconciliation decision (Who / Why) "
            "before the Monthly Export can run."
        )
        state.item_count = len(needs_review)
    return state


def reprocess_batch(
    session: Session, *, batch_id: int,
) -> "BatchReviewState":
    """Re-derive everything derivable for an already-normalized batch,
    without creating or deleting a single transaction: fingerprints,
    duplicate state, Recognition (never over a human decision) and
    matching. Idempotent — running it twice changes nothing the second
    time."""
    batch = session.get(m.BankImportBatch, batch_id)
    if batch is None:
        raise ValueError(f"BankImportBatch {batch_id} not found")
    transactions = list(session.scalars(
        select(m.FinancialTransaction)
        .where(m.FinancialTransaction.import_batch_id == batch.id)
        .order_by(m.FinancialTransaction.id)
    ).all())
    for txn in transactions:
        _reprocess_transaction(session, txn)
    if batch.payment_instrument is not None:
        batch.overlap_warning = _compute_overlap_warning(session, batch, batch.payment_instrument)
    _refresh_batch_status(session, batch)
    session.flush()
    return compute_batch_review_state(session, batch)


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


def _normalize_rows(
    session: Session, batch: "m.BankImportBatch",
    parsed_rows: list["parsers.ParsedBankRow"], raw_objs: list["m.RawBankTransaction"],
    instrument_by_row: dict[int, "m.PaymentInstrument"],
) -> tuple[int, int]:
    """Spec §5 (mapping) + §7.3/§8 (occurrence preservation and candidate
    duplicates). Flushes after each row so that a later row's duplicate
    search sees earlier rows already inserted in THIS SAME batch — this is
    what makes within-file identical rows (§7.3) surface as
    CANDIDATE_DUPLICATE via the exact same mechanism as cross-file/history
    duplicates (§7.2, §7.5), with no separate code path.

    `instrument_by_row` carries the instrument for each row: normally the
    same one for the whole file, but genuinely per-row when the source
    file mixes several cards. A row with no entry is NOT normalized — its
    raw row is preserved and waits for a human, which is always better
    than attributing it to the wrong instrument."""
    signature_counts: dict[tuple, int] = {}
    for row in parsed_rows:
        if row.parse_status == "UNREADABLE" or row.row_number not in instrument_by_row:
            continue
        instrument = instrument_by_row[row.row_number]
        sig = (instrument.id, row.posting_date, normalize_description(row.description or ""), row.amount_minor)
        signature_counts[sig] = signature_counts.get(sig, 0) + 1
    signature_seen: dict[tuple, int] = {}

    raw_by_row_number = {r.row_number: r for r in raw_objs}
    instrument_cache: dict[int, "m.PaymentInstrument"] = {}
    normalized_count = 0
    candidate_count = 0

    for row in parsed_rows:
        if row.parse_status == "UNREADABLE":
            continue
        instrument = instrument_by_row.get(row.row_number)
        if instrument is None:
            continue
        description_normalized = normalize_description(row.description or "")
        sig = (instrument.id, row.posting_date, description_normalized, row.amount_minor)
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

        # Accounting deduplication keying
        # (BANK_CARDHOLDER_AND_ACCOUNTING_DEDUPLICATION_001): the payee
        # normalization, the settlement account in force on this row's
        # posting date, and the four-element accounting key are computed
        # here, per row. The canonical-vs-suppressed decision is NOT made
        # here — it is a decision about a GROUP, and the group is only
        # complete once the whole batch is in, so `_resolve_accounting_
        # dedup_for_batch` below makes it once at the end.
        accounting_dedup.classify_transaction(session, normalized, instrument_cache)

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

    # Accounting deduplication, resolved ONCE for the whole pass rather
    # than per row: which occurrence is canonical is a property of the
    # GROUP, and the group is only complete now. Scoped to the instruments
    # this pass touched, but `recompute_accounting_dedup` always resolves
    # the FULL group each of those rows belongs to — that is what makes a
    # row in this batch deduplicate against an identical row imported
    # weeks ago, from another file, on the linked card.
    if instrument_cache:
        accounting_dedup.recompute_accounting_dedup(
            session, payment_instrument_ids=sorted(instrument_cache),
        )

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
    if txn.import_batch is not None:
        _refresh_batch_status(session, txn.import_batch)
        session.flush()
    return txn


def record_recognition_decision(
    session: Session, *, transaction_id: int, occurrence_id: int,
    confirmed_by_account_id: int | None, learn_description: bool = True,
) -> "m.BankTransactionExplanation":
    """Canonical Financial Model Convergence — Phase 4B (Product Owner
    Decisions 1, 6, 7, 10). The ONE human-facing entry point for
    confirming/correcting the canonical Bank Reconciliation decision —
    thin wrapper around `recognition.record_human_decision` used by the
    Bank Review workflow (`bank_routes.py`). Replaces the retired legacy
    `assign_explanation` (there is no longer a second, independent
    Supplier/Receiving assignment action).

    BANK_RECONCILIATION_WHO_WHY_WHAT_001: the caller supplies the WHO and
    nothing else — the WHY and the WHAT come from the Who's stored chain
    (`classification.resolve_chain`), which is why no
    `transaction_reason_id` parameter exists any more. An incomplete Who
    raises `ValueError` carrying the concrete reason to show the human.

    `learn_description` controls ONLY whether this confirmation also
    teaches RF-One that this exact normalized description means this Who
    (an `EXACT_NORMALIZED_DESCRIPTION` `BankRecognitionRule`). It does
    not, and can no longer, affect whether the Who -> Why -> What
    associations persist: those live on the vocabulary itself. Broader
    `CONTAINS_TEXT`/`PREFIX` rules still require an explicit, separate
    human choice — a single description never creates one."""
    result = recognition.record_human_decision(
        session,
        recognition.HumanDecisionRequest(
            transaction_id=transaction_id, occurrence_id=occurrence_id,
            confirmed_by_account_id=confirmed_by_account_id,
            learn_description=learn_description,
        ),
    )
    txn = session.get(m.FinancialTransaction, transaction_id)
    txn.review_status = "REVIEWED"
    session.flush()
    return result


def reclassify_transaction(
    session: Session, *, transaction_id: int, confirmed_by_account_id: int | None,
) -> "m.BankTransactionExplanation":
    """BANK_RECONCILIATION_WHO_WHY_WHAT_001 — apply the CURRENT
    Who -> Why -> What chain to a transaction that was decided under an
    earlier one. Appends a new auditable `HUMAN_RECLASSIFIED` decision;
    the superseded decision row is never edited or deleted."""
    result = recognition.reclassify_transaction(
        session, transaction_id=transaction_id, confirmed_by_account_id=confirmed_by_account_id,
    )
    txn = session.get(m.FinancialTransaction, transaction_id)
    txn.review_status = "REVIEWED"
    session.flush()
    return result
