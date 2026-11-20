"""Clean historical staging — turning a messy download corpus into a
certified set of economic events
(BANK_HISTORICAL_CLEAN_CONSOLIDATE_AND_IMPORT_001).

The corpus is what a real business accumulates: the same card downloaded
twice on different days, the same month exported in three formats, two
variants of one Chase card layout, and files for accounts nobody has
registered yet. Importing it naively would either double-count money or
silently delete it.

This module answers exactly one question:

    WHICH FINANCIAL EVENTS OCCURRED?

It does NOT answer what they meant. No WHO, no WHY, no WHAT, no
beneficiary enters a cleaning identity — that would make the same purchase
look like two different events the day somebody reclassified it.

Cleaning is multiset consolidation
----------------------------------
Two exports of one card are not two sets of money. Nor are they one set:

    File A: A B C D          File B: B C D E     ->  CLEAN: A B C D E
    File A: X X              File B: X X X       ->  CLEAN: X X X

Three, not five and not one. A business really does buy the same coffee
twice in a day, and an overlapping re-download really does repeat it. The
multiplicity of an event is therefore the STRONGEST supported occurrence
count — the maximum any single source attests — never the sum across
overlapping downloads.

Nothing is ever discarded
-------------------------
A duplicate source row is not deleted evidence; it simply does not create a
second economic event. Every clean event keeps a reference to every source
row that supports it, and every parsed row ends in exactly one explainable
class. There is no silent discard anywhere in this module.

Order invariance
----------------
Every decision here is a function of the corpus as a whole, never of the
order files happened to be read in. Multiplicity is a maximum, the
representative row is chosen by content, and collisions are detected
corpus-wide. Reversing the file order must produce a byte-identical
manifest, and the caller is expected to prove it before promoting anything.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone

from . import historical_source, parsers

# --- Source families -------------------------------------------------------
FAMILY_CHASE_BANK = "CHASE_BANK"
FAMILY_CHASE_CARD = "CHASE_CARD"
FAMILY_FIRST_CITIZENS = "FIRST_CITIZENS"
FAMILY_AMEX_QBO = "AMEX_QBO"
FAMILY_AMEX_CSV = "AMEX_CSV"
FAMILY_AMEX_XLSX = "AMEX_XLSX"
FAMILY_ZELLE_EVIDENCE_PENDING = "ZELLE_EVIDENCE_PENDING"
FAMILY_UNSUPPORTED = "UNSUPPORTED"

# --- How a source file ended up ---------------------------------------------
SOURCE_PARSED = "PARSED"
SOURCE_EXACT_FILE_DUPLICATE = "EXACT_FILE_DUPLICATE"
SOURCE_WITHOUT_REGISTERED_INSTRUMENT = "SOURCE_WITHOUT_REGISTERED_INSTRUMENT"
SOURCE_AMBIGUOUS_INSTRUMENT = "AMBIGUOUS_SOURCE_INSTRUMENT"
SOURCE_UNSUPPORTED = "UNSUPPORTED"
SOURCE_PARSE_ERROR = "PARSE_ERROR"
SOURCE_INVENTORY_ONLY = "INVENTORY_ONLY"
# A single export legitimately carrying several cards, each row naming its
# own. Not ambiguity: the source is perfectly clear, just not about ONE
# instrument. RF-One already anticipates this — `BankInstrumentAssignment
# Audit` has a TRANSACTION scope precisely for "a file carrying several
# cards/identifiers".
SOURCE_MULTI_INSTRUMENT = "MULTI_INSTRUMENT_SOURCE"

# --- Where every parsed row ended up (§16). No silent discard ---------------
ROW_PROMOTED = "PROMOTED_TO_CLEAN_EVENT"
ROW_DUPLICATE_EVIDENCE = "DUPLICATE_EVIDENCE"
ROW_AMBIGUOUS_DUPLICATE = "AMBIGUOUS_DUPLICATE"
ROW_UNRESOLVED_INSTRUMENT = "UNRESOLVED_INSTRUMENT"
ROW_NON_FINANCIAL = "NON_FINANCIAL_SOURCE_ROW"
ROW_UNSUPPORTED = "UNSUPPORTED"
ROW_PARSE_ERROR = "PARSE_ERROR"
ROW_CLASSES = (
    ROW_PROMOTED, ROW_DUPLICATE_EVIDENCE, ROW_AMBIGUOUS_DUPLICATE,
    ROW_UNRESOLVED_INSTRUMENT, ROW_NON_FINANCIAL, ROW_UNSUPPORTED, ROW_PARSE_ERROR,
)

# How a source file was tied to a Payment Instrument, strongest first.
BASIS_STRUCTURED_ACCOUNT = "STRUCTURED_ACCOUNT_FIELD"
BASIS_PROVIDER_FILENAME = "PROVIDER_FILENAME"
BASIS_ROW_ACCOUNT = "ROW_ACCOUNT_FIELD"
BASIS_NONE = "NONE"

# Layouts that identify the account on EVERY ROW rather than once per
# file. For these, the instrument is resolved per row: one export may
# legitimately cover several cards, and collapsing it to a single
# file-level answer would either mis-assign rows or throw them away.
PER_ROW_ACCOUNT_FORMATS = frozenset(
    {
        parsers.CHASE_CREDIT_CARD_WITH_CARD,
        parsers.FIRST_CITIZENS,
        parsers.AMEX_QBO,
        parsers.AMEX_CSV,
        parsers.AMEX_XLSX,
    }
)

_CHASE_FILENAME = re.compile(r"^Chase(\d{4})_Activity_", re.I)
_ACCOUNT_HISTORY = re.compile(r"^AccountHistory", re.I)


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------


@dataclass
class SourceFile:
    """One original download, described without being altered."""

    relative_path: str
    filename: str
    extension: str
    family: str
    sha256: str
    byte_size: int
    modified_utc: str
    parser: str | None = None
    detected_format: str | None = None
    account_hint: str | None = None
    instrument_last_four: str | None = None
    payment_instrument_id: int | None = None
    instrument_basis: str = BASIS_NONE
    instrument_candidates: tuple[int, ...] = ()
    source_row_count: int = 0
    parsed_row_count: int = 0
    unreadable_row_count: int = 0
    earliest: str | None = None
    latest: str | None = None
    status: str = SOURCE_PARSED
    duplicate_of: str | None = None
    notes: str = ""

    @property
    def is_promotable(self) -> bool:
        return self.status == SOURCE_PARSED and self.payment_instrument_id is not None


def _family_for(filename: str, extension: str) -> str:
    ext = extension.lower()
    if ext == ".pdf":
        return FAMILY_ZELLE_EVIDENCE_PENDING if "zelle" in filename.lower() else FAMILY_UNSUPPORTED
    if ext == ".qbo":
        return FAMILY_AMEX_QBO
    if ext == ".xlsx":
        return FAMILY_AMEX_XLSX
    if ext != ".csv":
        return FAMILY_UNSUPPORTED
    if _ACCOUNT_HISTORY.match(filename):
        return FAMILY_FIRST_CITIZENS
    if _CHASE_FILENAME.match(filename):
        # Bank versus card is decided by the HEADER, never by the name. The
        # family is refined once the file is actually parsed.
        return FAMILY_CHASE_CARD
    return FAMILY_AMEX_CSV


_FORMAT_FAMILY = {
    parsers.CHASE_BANK_ACCOUNT: FAMILY_CHASE_BANK,
    parsers.CHASE_CREDIT_CARD_WITH_CARD: FAMILY_CHASE_CARD,
    parsers.CHASE_CREDIT_CARD_NO_CARD: FAMILY_CHASE_CARD,
    parsers.FIRST_CITIZENS: FAMILY_FIRST_CITIZENS,
    parsers.AMEX_QBO: FAMILY_AMEX_QBO,
    parsers.AMEX_CSV: FAMILY_AMEX_CSV,
    parsers.AMEX_XLSX: FAMILY_AMEX_XLSX,
}

# Which instrument types a layout may legitimately belong to. A bank-account
# export can never be a credit card, whatever a filename suggests.
_FORMAT_INSTRUMENT_TYPES = {
    parsers.CHASE_BANK_ACCOUNT: ("BANK_ACCOUNT",),
    parsers.FIRST_CITIZENS: ("BANK_ACCOUNT",),
    parsers.CHASE_CREDIT_CARD_WITH_CARD: ("CREDIT_CARD",),
    parsers.CHASE_CREDIT_CARD_NO_CARD: ("CREDIT_CARD",),
    parsers.AMEX_QBO: ("CREDIT_CARD",),
    parsers.AMEX_CSV: ("CREDIT_CARD",),
    parsers.AMEX_XLSX: ("CREDIT_CARD",),
}


def inventory(roots: list[str], base_dir: str) -> list[SourceFile]:
    """Every file under the given roots, described and hashed.

    Nothing is skipped: an unsupported file is recorded as unsupported, not
    passed over. Sorted by relative path so two runs see the same corpus in
    the same order regardless of how the filesystem enumerates it."""
    found: list[SourceFile] = []
    for root in roots:
        absolute_root = os.path.join(base_dir, root)
        if not os.path.isdir(absolute_root):
            continue
        for directory, _, filenames in os.walk(absolute_root):
            for filename in filenames:
                full = os.path.join(directory, filename)
                relative = os.path.relpath(full, base_dir).replace("\\", "/")
                with open(full, "rb") as handle:
                    data = handle.read()
                extension = os.path.splitext(filename)[1]
                found.append(
                    SourceFile(
                        relative_path=relative,
                        filename=filename,
                        extension=extension.lower(),
                        family=_family_for(filename, extension),
                        sha256=hashlib.sha256(data).hexdigest(),
                        byte_size=len(data),
                        modified_utc=datetime.fromtimestamp(
                            os.path.getmtime(full), tz=timezone.utc
                        ).isoformat(),
                    )
                )
    return sorted(found, key=lambda s: s.relative_path)


def mark_exact_file_duplicates(sources: list[SourceFile]) -> None:
    """Identical bytes in two paths are one piece of evidence in two
    places. Both paths stay in provenance; only the first by sorted path is
    parsed, so copied bytes never become a second economic dataset."""
    first_by_hash: dict[str, str] = {}
    for source in sorted(sources, key=lambda s: s.relative_path):
        if source.sha256 in first_by_hash:
            source.status = SOURCE_EXACT_FILE_DUPLICATE
            source.duplicate_of = first_by_hash[source.sha256]
            source.notes = (
                f"Byte-identical to {first_by_hash[source.sha256]}; preserved as provenance and "
                "parsed once."
            )
        else:
            first_by_hash[source.sha256] = source.relative_path


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


@dataclass
class StagedRow:
    """One parsed source row, before consolidation decides its fate."""

    source_path: str
    row_number: int
    detected_format: str
    payment_instrument_id: int | None
    posting_date: date | None
    transaction_date: date | None
    amount_minor: int | None
    description: str | None
    memo: str | None
    bank_transaction_type: str | None
    reference: str | None
    balance_minor: int | None
    account_hint: str | None
    parse_status: str
    anomalies: tuple[str, ...]
    identity_basis: str = ""
    identity_key: tuple = ()
    row_class: str = ""

    @property
    def provenance(self) -> str:
        return f"{self.source_path}#{self.row_number}"


def parse_source(source: SourceFile, base_dir: str) -> parsers.ParsedFile | None:
    """Parse one source with the parser its CONTENT calls for.

    Format is decided by the header or the document structure, never by the
    filename — a file called `Chase2915_Activity` is a credit-card export
    because its header says so, not because of its name."""
    full = os.path.join(base_dir, source.relative_path)
    if source.extension == ".xlsx":
        source.parser = "parse_amex_xlsx"
        return parsers.parse_amex_xlsx(full)
    with open(full, "rb") as handle:
        data = handle.read()
    if source.extension == ".qbo":
        source.parser = "parse_qbo_bytes"
        return parsers.parse_qbo_bytes(data)
    if source.extension != ".csv":
        return None
    try:
        source.parser = "parse_csv_bytes"
        return parsers.parse_csv_bytes(data)
    except parsers.UnrecognizedFormatError:
        source.parser = "parse_amex_csv_bytes"
        return parsers.parse_amex_csv_bytes(data)


# ---------------------------------------------------------------------------
# Instrument resolution
# ---------------------------------------------------------------------------


def _last_four(value: str | None) -> str | None:
    if not value:
        return None
    digits = re.sub(r"\D", "", str(value))
    return digits[-4:] if len(digits) >= 4 else None


def resolve_instrument(
    source: SourceFile, parsed: parsers.ParsedFile, instruments: list[dict],
) -> None:
    """Tie one source to exactly one registered Payment Instrument, or say
    plainly that it cannot.

    Evidence, strongest first:

    1. a structured account/card field inside the file;
    2. the provider's own filename convention (`Chase1057_Activity_...`).

    When both exist they must AGREE. A file named for one card whose rows
    carry another is not resolved by preferring one — it is reported.

    The instrument TYPE must also fit the layout: a bank-account export can
    never resolve to a credit card. That check is what keeps a card export
    named `Chase2915` away from a same-numbered bank account, and vice
    versa, without anybody hardcoding either.

    Zero or several matches leave the source preserved but unpromotable.
    No instrument is ever created here."""
    hints = {
        _last_four(row.account_hint)
        for row in parsed.rows
        if row.account_hint and _last_four(row.account_hint)
    }
    structured = sorted(h for h in hints if h)
    filename_match = _CHASE_FILENAME.match(source.filename)
    from_filename = filename_match.group(1) if filename_match else None

    if len(structured) > 1:
        if parsed.detected_format in PER_ROW_ACCOUNT_FORMATS:
            # Every row names its own card, so the file is not ambiguous —
            # it simply covers more than one instrument. Each row is
            # resolved individually by `resolve_row_instrument` below.
            source.status = SOURCE_MULTI_INSTRUMENT
            source.instrument_basis = BASIS_ROW_ACCOUNT
            source.notes = (
                f"One export covering {len(structured)} cards ({', '.join(structured)}). Each row "
                "carries its own account identifier and is assigned from that, never from the "
                "file as a whole."
            )
            return
        source.status = SOURCE_AMBIGUOUS_INSTRUMENT
        source.notes = (
            f"Rows carry {len(structured)} different account identifiers ({', '.join(structured)}) "
            "and this layout has no per-row account field to settle it. The source is preserved, "
            "not assigned."
        )
        return

    from_structured = structured[0] if structured else None
    if from_structured and from_filename and from_structured != from_filename:
        source.status = SOURCE_AMBIGUOUS_INSTRUMENT
        source.notes = (
            f"The filename says {from_filename} but the rows say {from_structured}. RF-One does "
            "not choose between a name and the data; the source is preserved unassigned."
        )
        return

    last_four = from_structured or from_filename
    source.instrument_last_four = last_four
    source.account_hint = from_structured
    source.instrument_basis = (
        BASIS_STRUCTURED_ACCOUNT if from_structured
        else BASIS_PROVIDER_FILENAME if from_filename
        else BASIS_NONE
    )
    if not last_four:
        source.status = SOURCE_WITHOUT_REGISTERED_INSTRUMENT
        source.notes = (
            "The source carries no account identifier and its filename follows no known provider "
            "convention, so no instrument can be established from it."
        )
        return

    allowed_types = _FORMAT_INSTRUMENT_TYPES.get(parsed.detected_format, ())
    matches = [
        instrument for instrument in instruments
        if instrument["last_four"] == last_four
        and (not allowed_types or instrument["instrument_type"] in allowed_types)
    ]
    source.instrument_candidates = tuple(sorted(i["id"] for i in matches))

    if len(matches) == 1:
        source.payment_instrument_id = matches[0]["id"]
        return
    if not matches:
        same_number = [i for i in instruments if i["last_four"] == last_four]
        source.status = SOURCE_WITHOUT_REGISTERED_INSTRUMENT
        source.notes = (
            f"No registered {'/'.join(allowed_types) or 'instrument'} carries last four "
            f"{last_four}."
            + (
                f" An instrument with that number exists but is a "
                f"{same_number[0]['instrument_type']}, which this layout cannot be."
                if same_number else ""
            )
        )
        return
    source.status = SOURCE_AMBIGUOUS_INSTRUMENT
    source.notes = (
        f"{len(matches)} registered instruments carry last four {last_four} "
        f"({', '.join(str(i['id']) for i in matches)}); the source is preserved unassigned."
    )


def resolve_row_instrument(
    row_account_hint: str | None,
    detected_format: str,
    instruments: list[dict],
) -> int | None:
    """The instrument ONE row belongs to, from the account identifier that
    row itself carries.

    Used for layouts that name the account on every row. Returns None when
    the hint matches no registered instrument of a type the layout allows,
    or matches several — in both cases the row is preserved and reported,
    never assigned by preference."""
    last_four = _last_four(row_account_hint)
    if not last_four:
        return None
    allowed_types = _FORMAT_INSTRUMENT_TYPES.get(detected_format, ())
    matches = [
        instrument for instrument in instruments
        if instrument["last_four"] == last_four
        and (not allowed_types or instrument["instrument_type"] in allowed_types)
    ]
    return matches[0]["id"] if len(matches) == 1 else None


# ---------------------------------------------------------------------------
# Identity, with collision protection
# ---------------------------------------------------------------------------


def _row_to_parsed(row: StagedRow) -> parsers.ParsedBankRow:
    """Rebuild the shape `historical_source.row_identity` expects, so the
    certified identity implementation is REUSED rather than duplicated."""
    return parsers.ParsedBankRow(
        row_number=row.row_number,
        raw_fields={},
        parse_status=row.parse_status,
        posting_date=row.posting_date,
        transaction_date=row.transaction_date,
        description=row.description,
        amount_minor=row.amount_minor,
        bank_transaction_type=row.bank_transaction_type,
        reference=row.reference,
        balance_minor=row.balance_minor,
        source_memo=row.memo,
    )


def _evidence_core(row: StagedRow) -> tuple:
    """The facts a provider id must stay consistent with to be trusted."""
    return (
        row.posting_date.isoformat() if row.posting_date else "",
        row.amount_minor,
    )


def _evidence_identity_key(row: StagedRow) -> tuple:
    """Full canonical evidence for a row, field for field the same tuple
    `historical_source.row_identity` builds for its evidence branch.

    Written out here rather than delegated because the caller needs the
    evidence form EVEN WHEN a provider id exists — and `row_identity`
    would return the provider id instead, which is precisely the value
    that has just been rejected as ambiguous."""
    return (
        row.posting_date.isoformat() if row.posting_date else "",
        row.transaction_date.isoformat() if row.transaction_date else "",
        row.amount_minor,
        historical_source._normalize_text(row.description),
        historical_source._normalize_text(row.memo),
        historical_source._normalize_text(row.bank_transaction_type),
        historical_source._normalize_text(row.reference),
        row.balance_minor if row.balance_minor is not None else "",
    )


def assign_identities(rows: list[StagedRow]) -> dict[str, int]:
    """Give every row its identity, distrusting any provider id that the
    corpus proves is not unique.

    Chase reuses check numbers across years. A check numbered 1234 in 2019
    and another in 2024 would share `REF:1234` and silently collapse into
    one event, deleting money. So provider ids are validated against the
    whole corpus first: one that appears on two genuinely different
    (date, amount) pairs for the same instrument is DEMOTED, and every row
    carrying it falls back to full canonical evidence instead.

    This is a property of the corpus, not of the reading order, so the
    outcome is identical however the files are traversed."""
    by_provider: dict[tuple[int | None, str], set[tuple]] = defaultdict(set)
    for row in rows:
        parsed = _row_to_parsed(row)
        provider = historical_source.provider_transaction_id(row.detected_format, parsed)
        if provider is not None:
            by_provider[(row.payment_instrument_id, provider)].add(_evidence_core(row))

    demoted = {key for key, cores in by_provider.items() if len(cores) > 1}

    counts: dict[str, int] = Counter()
    for row in rows:
        parsed = _row_to_parsed(row)
        provider = historical_source.provider_transaction_id(row.detected_format, parsed)
        if provider is not None and (row.payment_instrument_id, provider) not in demoted:
            row.identity_basis = historical_source.IDENTITY_PROVIDER_ID
            row.identity_key = (provider,)
        else:
            # Either the source never had a provider id, or the corpus
            # showed that one is not unique. Both land on full canonical
            # evidence — built explicitly rather than by re-calling
            # `row_identity`, which would hand back the very provider id
            # just rejected.
            row.identity_basis = historical_source.IDENTITY_CANONICAL_EVIDENCE
            row.identity_key = _evidence_identity_key(row)
        counts[row.identity_basis] += 1

    return {
        "provider_id_rows": counts.get(historical_source.IDENTITY_PROVIDER_ID, 0),
        "evidence_rows": counts.get(historical_source.IDENTITY_CANONICAL_EVIDENCE, 0),
        "demoted_provider_ids": len(demoted),
    }


# ---------------------------------------------------------------------------
# Multiset consolidation
# ---------------------------------------------------------------------------


@dataclass
class CleanEvent:
    """One occurrence of one economic event, with all its evidence."""

    clean_event_key: str
    occurrence_index: int
    occurrence_multiplicity: int
    payment_instrument_id: int
    identity_basis: str
    posting_date: str | None
    transaction_date: str | None
    amount_minor: int
    description: str | None
    memo: str | None
    bank_transaction_type: str | None
    reference: str | None
    balance_minor: int | None
    provider_transaction_id: str | None
    source_provenance: tuple[str, ...]
    supporting_source_count: int
    supporting_row_count: int

    def business_tuple(self) -> tuple:
        """The business identity of this event — no surrogate id anywhere,
        so two databases can be compared by content alone."""
        return (
            self.payment_instrument_id,
            self.clean_event_key,
            self.occurrence_index,
            self.posting_date or "",
            self.transaction_date or "",
            self.amount_minor,
        )


def _clean_event_key(instrument_id: int, basis: str, key: tuple) -> str:
    """A deterministic key for an economic event.

    Hashed so it is a stable fixed-width token regardless of how long a
    bank description is, and salted with the instrument because the same
    identity on two cards is two different events."""
    payload = json.dumps(
        [instrument_id, basis, [str(part) for part in key]], separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def consolidate(rows: list[StagedRow]) -> tuple[list[CleanEvent], dict]:
    """Collapse overlapping downloads into economic events.

    Multiplicity is the MAXIMUM any single source attests, never the sum.
    Two exports that both contain the same purchase twice describe two
    purchases, not four.

    Every contributing row is classified: the ones that establish the
    event's occurrences are PROMOTED, the rest are DUPLICATE_EVIDENCE —
    kept, linked, and counted, never deleted."""
    grouped: dict[tuple[int, str, tuple], list[StagedRow]] = defaultdict(list)
    for row in rows:
        grouped[(row.payment_instrument_id, row.identity_basis, row.identity_key)].append(row)

    events: list[CleanEvent] = []
    promoted = 0
    duplicate_evidence = 0

    for (instrument_id, basis, key), group in grouped.items():
        per_source = Counter(row.source_path for row in group)
        multiplicity = max(per_source.values())
        clean_key = _clean_event_key(instrument_id, basis, key)

        # Deterministic ordering by CONTENT, so the representative row and
        # the provenance list never depend on traversal order.
        ordered = sorted(group, key=lambda r: (r.source_path, r.row_number))
        provenance = tuple(row.provenance for row in ordered)

        # The sources that attest the full multiplicity establish the
        # occurrences; their rows are the promoted ones.
        establishing = sorted(
            path for path, count in per_source.items() if count == multiplicity
        )[0]
        establishing_rows = [row for row in ordered if row.source_path == establishing]

        for occurrence_index in range(multiplicity):
            representative = establishing_rows[occurrence_index]
            representative.row_class = ROW_PROMOTED
            promoted += 1
            parsed = _row_to_parsed(representative)
            events.append(
                CleanEvent(
                    clean_event_key=clean_key,
                    occurrence_index=occurrence_index,
                    occurrence_multiplicity=multiplicity,
                    payment_instrument_id=instrument_id,
                    identity_basis=basis,
                    posting_date=(
                        representative.posting_date.isoformat()
                        if representative.posting_date else None
                    ),
                    transaction_date=(
                        representative.transaction_date.isoformat()
                        if representative.transaction_date else None
                    ),
                    amount_minor=representative.amount_minor,
                    description=representative.description,
                    memo=representative.memo,
                    bank_transaction_type=representative.bank_transaction_type,
                    reference=representative.reference,
                    balance_minor=representative.balance_minor,
                    provider_transaction_id=historical_source.provider_transaction_id(
                        representative.detected_format, parsed,
                    ),
                    source_provenance=provenance,
                    supporting_source_count=len(per_source),
                    supporting_row_count=len(group),
                )
            )

        for row in ordered:
            if row.row_class != ROW_PROMOTED:
                row.row_class = ROW_DUPLICATE_EVIDENCE
                duplicate_evidence += 1

    events.sort(key=lambda e: (e.payment_instrument_id, e.clean_event_key, e.occurrence_index))
    return events, {
        "distinct_identities": len(grouped),
        "clean_events": len(events),
        "promoted_rows": promoted,
        "duplicate_evidence_rows": duplicate_evidence,
    }


# ---------------------------------------------------------------------------
# Controls and manifest
# ---------------------------------------------------------------------------


def per_instrument_controls(events: list[CleanEvent], rows: list[StagedRow]) -> dict[int, dict]:
    """Reproducible per-instrument totals, computed from the clean events
    themselves so the numbers can be recomputed from the manifest alone."""
    controls: dict[int, dict] = {}
    for event in events:
        entry = controls.setdefault(
            event.payment_instrument_id,
            {
                "clean_events": 0, "debit_minor": 0, "credit_minor": 0,
                "earliest": None, "latest": None, "months": set(),
                "provider_id_events": 0, "evidence_events": 0,
            },
        )
        entry["clean_events"] += 1
        if event.amount_minor < 0:
            entry["debit_minor"] += event.amount_minor
        else:
            entry["credit_minor"] += event.amount_minor
        if event.identity_basis == historical_source.IDENTITY_PROVIDER_ID:
            entry["provider_id_events"] += 1
        else:
            entry["evidence_events"] += 1
        for value in (event.posting_date, event.transaction_date):
            if not value:
                continue
            entry["earliest"] = value if entry["earliest"] is None else min(entry["earliest"], value)
            entry["latest"] = value if entry["latest"] is None else max(entry["latest"], value)
            entry["months"].add(value[:7])

    for instrument_id, entry in controls.items():
        months = sorted(entry.pop("months"))
        entry["month_count"] = len(months)
        entry["first_month"] = months[0] if months else None
        entry["last_month"] = months[-1] if months else None
        entry["month_gaps"] = _month_gaps(months)
        entry["raw_rows"] = sum(
            1 for row in rows if row.payment_instrument_id == instrument_id
        )
        entry["duplicate_evidence_rows"] = sum(
            1 for row in rows
            if row.payment_instrument_id == instrument_id
            and row.row_class == ROW_DUPLICATE_EVIDENCE
        )
    return controls


def _month_gaps(months: list[str]) -> list[str]:
    """Calendar months with no activity between the first and last month
    that do. A gap is reported, never filled."""
    if len(months) < 2:
        return []
    first_year, first_month = int(months[0][:4]), int(months[0][5:7])
    last_year, last_month = int(months[-1][:4]), int(months[-1][5:7])
    present = set(months)
    gaps: list[str] = []
    year, month = first_year, first_month
    while (year, month) <= (last_year, last_month):
        key = f"{year:04d}-{month:02d}"
        if key not in present:
            gaps.append(key)
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return gaps


def build_manifest(
    *, sources: list[SourceFile], events: list[CleanEvent], rows: list[StagedRow],
) -> dict:
    """The deterministic business manifest of the cleaned dataset.

    Contains no surrogate id and no traversal artefact: two independent
    runs over the same corpus, in any order, must produce byte-identical
    JSON and therefore the same SHA-256."""
    controls = per_instrument_controls(events, rows)
    return {
        "manifest_version": "1",
        "source_corpus": [
            {
                "path": source.relative_path,
                "sha256": source.sha256,
                "byte_size": source.byte_size,
                "family": source.family,
                "detected_format": source.detected_format,
                "status": source.status,
                "payment_instrument_id": source.payment_instrument_id,
                "instrument_last_four": source.instrument_last_four,
                "instrument_basis": source.instrument_basis,
                "source_row_count": source.source_row_count,
                "parsed_row_count": source.parsed_row_count,
            }
            for source in sorted(sources, key=lambda s: s.relative_path)
        ],
        "clean_events": [
            {
                "clean_event_key": event.clean_event_key,
                "occurrence_index": event.occurrence_index,
                "payment_instrument_id": event.payment_instrument_id,
                "posting_date": event.posting_date,
                "transaction_date": event.transaction_date,
                "amount_minor": event.amount_minor,
                "identity_basis": event.identity_basis,
                "provider_transaction_id": event.provider_transaction_id,
                "provenance_fingerprint": hashlib.sha256(
                    "|".join(event.source_provenance).encode("utf-8")
                ).hexdigest()[:16],
            }
            for event in sorted(
                events,
                key=lambda e: (e.payment_instrument_id, e.clean_event_key, e.occurrence_index),
            )
        ],
        "per_instrument_controls": {
            str(instrument_id): {
                key: value for key, value in sorted(entry.items())
            }
            for instrument_id, entry in sorted(controls.items())
        },
        "row_class_counts": dict(sorted(Counter(row.row_class for row in rows).items())),
    }


def manifest_sha256(manifest: dict) -> str:
    return hashlib.sha256(canonical_json(manifest).encode("utf-8")).hexdigest()


def canonical_json(payload) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
