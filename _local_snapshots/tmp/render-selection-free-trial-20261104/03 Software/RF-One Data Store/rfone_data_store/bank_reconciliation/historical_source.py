"""Historical Bank source control (BANK_HISTORICAL_SOURCE_CONTROL_FOUNDATION_001).

An operator downloads the same history more than once. That is normal, it
is not a mistake, and RF-One must never ask them to decide which original
file to throw away. Every download is evidence and is kept.

So overlap has to be solved on the DATA, not on the files, and this module
is the machinery for that. It adds no second duplicate-detection framework:
`service.import_csv` still owns file-level identity by SHA-256 and the
transaction-level duplicate flow still owns what happens at import. What
was missing is the layer BEFORE import — deciding what a pile of
overlapping original downloads actually contains, and which accounts the
evidence proves exist.

TWO LEVELS OF IDEMPOTENCY, NEVER CONFLATED
------------------------------------------
LEVEL 1, SOURCE FILE IDENTITY: the SHA-256 of the original bytes. It
answers "have I already processed these exact bytes", and nothing else. A
renamed copy is the same file; a re-download with one more day of activity
is not.

LEVEL 2, SOURCE TRANSACTION IDENTITY: it answers "does this financial
event already exist even though it arrived through a different export".
Two files can share every transaction and still differ in bytes — that is
the ordinary case, not the exception.

MULTISET, NOT SET
-----------------
Identical-looking financial events legitimately recur. Two £4.50 coffees on
the same day at the same shop are two coffees. So reconciliation counts
OCCURRENCES within an instrument, and the union of two exports takes the
MAXIMUM multiplicity seen in either, never the sum and never one.

  old = [A, B, C, D]   new = [B, C, D, E]   ->  A B C D E   (five, not eight)
  old = [X, X]         new = [X, X, X]      ->  X X X       (three, not one)

Taking the maximum rather than the sum is what makes re-importing the same
history harmless, and taking it rather than collapsing to one is what keeps
genuine repetition intact.

WHAT THIS MODULE NEVER DOES
---------------------------
It never deletes or modifies a source file. It never creates a
`PaymentInstrument` from evidence alone. It never reads a source boundary
as a lifecycle date: the earliest transaction in a file is not an
activation date and the latest is not a closure date, and those two facts
are kept apart everywhere below.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import parsers

UTC = timezone.utc


# ---------------------------------------------------------------------------
# §7 — the strongest transaction identity each source can support
# ---------------------------------------------------------------------------

IDENTITY_PROVIDER_ID = "PROVIDER_TRANSACTION_ID"
IDENTITY_CANONICAL_EVIDENCE = "CANONICAL_SOURCE_EVIDENCE"

# A Chase ACH description carries the bank's own trace/transaction number.
# It is the strongest identity those rows have, and it is genuinely stable
# across re-downloads of the same account.
_CHASE_TRN = re.compile(r"\bTRN:\s*([A-Z0-9]+)")
_CHASE_TRACE = re.compile(r"\bTRACE#:\s*(\d+)")


def _normalize_text(value) -> str:
    """Whitespace-insensitive, case-insensitive form of a source string.

    Only spacing and case are normalized. No word is dropped, nothing is
    truncated, and the RAW value is always preserved separately by the
    caller — this is for comparison, never for storage.
    """
    return re.sub(r"\s+", " ", str(value or "")).strip().upper()


@dataclass(frozen=True)
class RowIdentity:
    """One financial event, as strongly identified as its source allows."""

    basis: str
    key: tuple

    def __str__(self) -> str:  # pragma: no cover - diagnostics only
        return f"{self.basis}:{self.key}"


def provider_transaction_id(detected_format: str, row: "parsers.ParsedBankRow") -> str | None:
    """The bank's or provider's OWN identifier for this transaction, when
    the source genuinely carries a stable one.

    Chase bank-account rows embed `TRN:` (and often `TRACE#:`) in the
    description for ACH activity. Card purchase rows carry neither, so this
    returns None for them and the caller falls back to evidence — which is
    the point of having two strategies rather than pretending one fits all.
    """
    if detected_format == parsers.CHASE_BANK_ACCOUNT:
        text = row.description or ""
        trn = _CHASE_TRN.search(text)
        if trn:
            return f"TRN:{trn.group(1)}"
        trace = _CHASE_TRACE.search(text)
        if trace:
            return f"TRACE:{trace.group(1)}"
    # `reference` is populated by the parsers that have one (First
    # Citizens' check number, Chase's check-or-slip). A blank or a bare
    # zero is not an identifier.
    ref = (row.reference or "").strip()
    if ref and ref not in {"0", "00", "000"}:
        return f"REF:{ref}"
    return None


def row_identity(detected_format: str, row: "parsers.ParsedBankRow") -> RowIdentity:
    """This row's identity, strongest evidence first.

    A. the provider's own transaction identifier, when the source has one;
    B. otherwise canonical evidence built from every reliable field the
       source supplies.

    The FILE'S LAYOUT is deliberately absent from both. Chase exports the
    same card in two variants — one carrying a `Card` column, one not — and
    they describe the same purchases. Putting the detected format, or the
    in-file account hint that only one variant supplies, into the identity
    would make two exports of one card look like two disjoint accounts.
    Which instrument a row belongs to is settled OUTSIDE this function, by
    the existing source resolver; here we identify the EVENT.

    Deliberately NOT "date + amount", and not "date + amount +
    description": those collide on exactly the rows a business repeats, and
    a collision here silently deletes money. Everything the source offers
    that is intrinsic to the event participates — the dates, the signed
    amount, the raw description, the memo, the bank's transaction type, the
    reference, and the running balance where the source supplies one.

    The running balance deserves its mention: it is derived, but it is
    derived DETERMINISTICALLY by the bank, so for one account it is
    identical across re-downloads and it differs between two genuinely
    separate transactions that otherwise look the same. It is the field
    that makes repeated identical purchases distinguishable instead of
    merely countable.
    """
    provider = provider_transaction_id(detected_format, row)
    if provider is not None:
        return RowIdentity(IDENTITY_PROVIDER_ID, (provider,))
    return RowIdentity(
        IDENTITY_CANONICAL_EVIDENCE,
        (
            row.posting_date.isoformat() if row.posting_date else "",
            row.transaction_date.isoformat() if row.transaction_date else "",
            row.amount_minor,
            _normalize_text(row.description),
            _normalize_text(row.source_memo),
            _normalize_text(row.bank_transaction_type),
            _normalize_text(row.reference),
            row.balance_minor if row.balance_minor is not None else "",
        ),
    )


# ---------------------------------------------------------------------------
# A source file, fingerprinted
# ---------------------------------------------------------------------------


@dataclass
class SourceFingerprint:
    """Everything needed to compare one original download with another,
    without re-reading it and without ever modifying it."""

    path: str
    sha256: str
    detected_format: str
    byte_size: int
    row_count: int = 0
    unreadable_count: int = 0
    identities: Counter = field(default_factory=Counter)
    account_hints: set[str] = field(default_factory=set)
    earliest: date | None = None
    latest: date | None = None
    provider_id_rows: int = 0

    @property
    def name(self) -> str:
        return os.path.basename(self.path)

    @property
    def distinct_identities(self) -> int:
        return len(self.identities)

    @property
    def total_identified(self) -> int:
        return sum(self.identities.values())

    @property
    def identity_strength(self) -> str:
        """How much of this file is identified by the provider's own id."""
        if not self.total_identified:
            return "EMPTY"
        if self.provider_id_rows == self.total_identified:
            return IDENTITY_PROVIDER_ID
        if self.provider_id_rows == 0:
            return IDENTITY_CANONICAL_EVIDENCE
        return "MIXED"


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fingerprint_bytes(
    *, file_bytes: bytes, path: str,
) -> SourceFingerprint:
    """Fingerprint one original download.

    Opens nothing for writing and keeps nothing but counts: the file on
    disk is evidence and is left exactly as it was.
    """
    parsed = parsers.parse_csv_bytes(file_bytes)
    fp = SourceFingerprint(
        path=path,
        sha256=hashlib.sha256(file_bytes).hexdigest(),
        detected_format=parsed.detected_format,
        byte_size=len(file_bytes),
    )
    for row in parsed.rows:
        if row.parse_status == "UNREADABLE":
            fp.unreadable_count += 1
            continue
        fp.row_count += 1
        identity = row_identity(parsed.detected_format, row)
        fp.identities[identity] += 1
        if identity.basis == IDENTITY_PROVIDER_ID:
            fp.provider_id_rows += 1
        if row.account_hint:
            fp.account_hints.add(row.account_hint.strip())
        for value in (row.posting_date, row.transaction_date):
            if value is None:
                continue
            fp.earliest = value if fp.earliest is None else min(fp.earliest, value)
            fp.latest = value if fp.latest is None else max(fp.latest, value)
    return fp


def fingerprint_path(path: str) -> SourceFingerprint:
    with open(path, "rb") as fh:
        return fingerprint_bytes(file_bytes=fh.read(), path=path)


# ---------------------------------------------------------------------------
# §9 — how two sources for the same instrument relate
# ---------------------------------------------------------------------------

EXACT_FILE_DUPLICATE = "EXACT_FILE_DUPLICATE"
TRANSACTION_EQUIVALENT = "TRANSACTION_EQUIVALENT"
TRANSACTION_SUPERSET = "TRANSACTION_SUPERSET"
TRANSACTION_SUBSET = "TRANSACTION_SUBSET"
PARTIAL_OVERLAP = "PARTIAL_OVERLAP"
DISJOINT = "DISJOINT"
AMBIGUOUS = "AMBIGUOUS"

RELATIONSHIPS = (
    EXACT_FILE_DUPLICATE, TRANSACTION_EQUIVALENT, TRANSACTION_SUPERSET,
    TRANSACTION_SUBSET, PARTIAL_OVERLAP, DISJOINT, AMBIGUOUS,
)


@dataclass
class SourceRelationship:
    verdict: str
    shared: int
    only_a: int
    only_b: int
    basis: str

    @property
    def both_needed(self) -> bool:
        """Whether discarding either file would lose evidence. Nothing is
        ever deleted regardless; this only says what the data shows."""
        return self.verdict in (PARTIAL_OVERLAP, DISJOINT, AMBIGUOUS)


def classify_relationship(a: SourceFingerprint, b: SourceFingerprint) -> SourceRelationship:
    """Classify two original downloads. Neither is ever deleted: this is
    PROVENANCE, recorded so a human can see what they have.

    Comparison is by MULTISET, so a file containing a transaction twice is
    not a superset of one containing it once by accident of set algebra.
    """
    if a.sha256 == b.sha256:
        return SourceRelationship(
            EXACT_FILE_DUPLICATE, a.total_identified, 0, 0,
            "identical bytes — the same download, however it was named",
        )
    # A layout difference is not a content difference: Chase's two card
    # variants describe the same card, and comparing them is the whole
    # point. What makes two files genuinely incomparable is describing
    # something that cannot be the same account — a different issuer, or a
    # bank account against a credit card. Both tests reuse the mapping the
    # source resolver already owns rather than restating it.
    from .service import _institution_for_format, _instrument_type_for_format
    a_kind = (_institution_for_format(a.detected_format),
              _instrument_type_for_format(a.detected_format))
    b_kind = (_institution_for_format(b.detected_format),
              _instrument_type_for_format(b.detected_format))
    if a_kind != b_kind:
        return SourceRelationship(
            AMBIGUOUS, 0, a.total_identified, b.total_identified,
            f"these describe different kinds of account ({a_kind[0]} {a_kind[1]} vs "
            f"{b_kind[0]} {b_kind[1]}); they cannot be the same one, so their overlap "
            "would mean nothing",
        )
    if not a.total_identified or not b.total_identified:
        return SourceRelationship(
            AMBIGUOUS, 0, a.total_identified, b.total_identified,
            "one of the two files yielded no readable transaction, so nothing can "
            "be concluded about their relationship",
        )

    shared = sum((a.identities & b.identities).values())
    only_a = sum((a.identities - b.identities).values())
    only_b = sum((b.identities - a.identities).values())

    if shared == 0:
        return SourceRelationship(
            DISJOINT, 0, only_a, only_b,
            "no transaction appears in both — they describe different activity",
        )
    if only_a == 0 and only_b == 0:
        return SourceRelationship(
            TRANSACTION_EQUIVALENT, shared, 0, 0,
            "different bytes, identical transaction content — one is redundant as "
            "DATA, though both are kept as evidence",
        )
    if only_b == 0:
        return SourceRelationship(
            TRANSACTION_SUPERSET, shared, only_a, 0,
            f"the first contains everything the second does, plus {only_a} more",
        )
    if only_a == 0:
        return SourceRelationship(
            TRANSACTION_SUBSET, shared, 0, only_b,
            f"the second contains everything the first does, plus {only_b} more",
        )
    return SourceRelationship(
        PARTIAL_OVERLAP, shared, only_a, only_b,
        f"{shared} transaction(s) in both, {only_a} only in the first, {only_b} only "
        "in the second — BOTH are needed",
    )


# ---------------------------------------------------------------------------
# §8 — the multiset union
# ---------------------------------------------------------------------------


@dataclass
class ReconciledSources:
    """What a set of overlapping downloads actually contains, once."""

    identities: Counter = field(default_factory=Counter)
    provenance: dict = field(default_factory=dict)
    files: list = field(default_factory=list)

    @property
    def economic_row_count(self) -> int:
        return sum(self.identities.values())

    @property
    def distinct_identities(self) -> int:
        return len(self.identities)

    @property
    def raw_row_total(self) -> int:
        """What a naive concatenation would have produced."""
        return sum(f.total_identified for f in self.files)

    @property
    def rows_avoided(self) -> int:
        return self.raw_row_total - self.economic_row_count


def reconcile(fingerprints) -> ReconciledSources:
    """Combine overlapping downloads of ONE instrument into the economic
    truth, and remember which file supplied what.

    The multiplicity of each identity is the MAXIMUM seen in any single
    file, never the sum. Summing double-counts every re-download; taking
    one collapses genuine repetition. The maximum is the only choice that
    is right in both directions:

      [X, X] and [X, X, X]  ->  three X, because one export saw three.

    Provenance is kept per identity, so an economic row can always be
    traced back to every original download that evidenced it — which is
    what makes it safe never to delete a file.
    """
    result = ReconciledSources()
    for fp in fingerprints:
        result.files.append(fp)
        for identity, count in fp.identities.items():
            if count > result.identities.get(identity, 0):
                result.identities[identity] = count
            result.provenance.setdefault(identity, []).append(fp.name)
    return result


# ---------------------------------------------------------------------------
# §11C — accounts the evidence mentions but the registry does not contain
# ---------------------------------------------------------------------------

# Phrases a bank actually uses when one account refers to another. Kept
# deliberately narrow: a bare four-digit run inside a trace number or an
# order reference is NOT an account reference, and treating it as one would
# bury the real findings under noise.
#
# Each pattern carries the KIND of evidence it is, most specific first, so a
# candidate can say how it was found. The word immediately before
# "card/account" is captured as an institution HINT only; whether it is an
# institution is decided against the registry's own vocabulary, never here.
REF_CARD_OR_ACCOUNT_ENDING_IN = "CARD_OR_ACCOUNT_ENDING_IN"
REF_ENDING_IN = "ENDING_IN"
REF_TRANSFER_MASKED_NUMBER = "TRANSFER_MASKED_NUMBER"
REF_MASKED_ACCOUNT_NUMBER = "MASKED_ACCOUNT_NUMBER"

_REFERENCE_PATTERNS = (
    (REF_CARD_OR_ACCOUNT_ENDING_IN, re.compile(
        r"(?:\b(?P<institution>[A-Za-z][A-Za-z&.-]*)\s+)?"
        r"\b(?:card|account|acct)\s+ending\s+in\s+(?P<last_four>\d{4})\b", re.I)),
    (REF_ENDING_IN, re.compile(r"\bending\s+in\s+(?P<last_four>\d{4})\b", re.I)),
    (REF_TRANSFER_MASKED_NUMBER, re.compile(
        r"\b(?:to|from)\s+(?:card|account|acct)\s*#?\s*[xX*]{2,}(?P<last_four>\d{4})\b", re.I)),
    (REF_MASKED_ACCOUNT_NUMBER, re.compile(
        r"\b(?:card|account|acct)\s*#?\s*[xX*]{4,}(?P<last_four>\d{4})\b", re.I)),
)


@dataclass(frozen=True)
class InstrumentReference:
    """One credible mention of another account inside a transaction text."""

    last_four: str
    kind: str
    institution: str | None = None


def instrument_reference_evidence(
    text: str | None, *, known_institutions: set[str] | frozenset[str] = frozenset(),
) -> list[InstrumentReference]:
    """The account references a text credibly makes, one per last four,
    labelled with the most specific pattern that found it.

    `institution` is filled only when the word before "card/account" is an
    institution RF-One's registry already uses (compared case-insensitively),
    so "Chase card ending in 4321" yields CHASE while "credit card ending in
    4321" yields nothing rather than an institution called CREDIT.
    """
    if not text:
        return []
    known = {value.upper() for value in known_institutions if value}
    found: dict[str, InstrumentReference] = {}
    for kind, pattern in _REFERENCE_PATTERNS:
        for match in pattern.finditer(text):
            last_four = match.group("last_four")
            if last_four in found:
                continue
            hint = match.groupdict().get("institution")
            institution = hint.upper() if hint and hint.upper() in known else None
            found[last_four] = InstrumentReference(last_four, kind, institution)
    return [found[key] for key in sorted(found)]


def extract_instrument_references(text: str | None) -> set[str]:
    """Last-four values this description credibly refers to.

    Only explicit account/card phrasing counts. RF-One would rather miss a
    hint than invent an account out of a trace number.
    """
    return {reference.last_four for reference in instrument_reference_evidence(text)}


# Raw-row keys that describe the row's OWN account or its provenance, never a
# reference to another account, and are therefore not scanned.
_NON_REFERENCE_RAW_KEYS = frozenset(
    {"account_hint", "source_path", "detected_format", "payment_instrument_id"}
)
DISCOVERY_SCAN_VERSION = "indirect-reference-scan v1"


@dataclass
class CandidateDiscoveryResult:
    raw_rows_scanned: int = 0
    registered_references: set = field(default_factory=set)
    created: list = field(default_factory=list)
    updated: list = field(default_factory=list)
    unchanged: list = field(default_factory=list)
    skipped: list = field(default_factory=list)


def discover_indirect_reference_candidates(session: Session) -> CandidateDiscoveryResult:
    """Persist every account the RAW evidence names but the registry lacks.

    Scans every preserved `RawBankTransaction` — duplicate evidence
    included, because a mention is evidence wherever it was downloaded —
    with the narrow patterns above. A last four matching ANY registered
    Payment Instrument, whatever its status, is not a candidate.

    Persistence goes through `record_candidate`, one `CandidateEvidence`
    per raw row keyed by that row's id, so idempotency is a property of the
    generic function and not of this scan: re-running it offers the same
    keys and changes nothing. `occurrence_count` is the number of distinct
    canonical transactions that mention the account; first/last seen are
    their posting dates — source boundaries, never lifecycle dates.

    Never creates a Payment Instrument, never sets or clears a resolution,
    never writes to a transaction or raw row. A candidate found by its own
    source file (DIRECT_SOURCE) is left as its discoverer recorded it.
    """
    result = CandidateDiscoveryResult()
    instruments = list(session.scalars(select(m.PaymentInstrument)))
    registered = {lf for lf in (instrument_last_four(i) for i in instruments) if lf}
    known_institutions = {i.institution for i in instruments if i.institution}
    posting = dict(session.execute(
        select(m.FinancialTransaction.id, m.FinancialTransaction.posting_date)
    ).all())

    items: dict[str, dict[str, CandidateEvidence]] = {}
    kinds: dict[str, set[str]] = {}
    institutions: dict[str, set[str]] = {}
    for raw in session.scalars(select(m.RawBankTransaction).order_by(m.RawBankTransaction.id)):
        result.raw_rows_scanned += 1
        fields = raw.raw_fields or {}
        for key in sorted(fields):
            value = fields[key]
            if key in _NON_REFERENCE_RAW_KEYS or not isinstance(value, str):
                continue
            for reference in instrument_reference_evidence(
                value, known_institutions=known_institutions,
            ):
                if reference.last_four in registered:
                    result.registered_references.add(reference.last_four)
                    continue
                kinds.setdefault(reference.last_four, set()).add(reference.kind)
                if reference.institution:
                    institutions.setdefault(reference.last_four, set()).add(reference.institution)
                # One item per raw row: the first field that referred wins,
                # so a row mentioning the account twice is still one row.
                items.setdefault(reference.last_four, {}).setdefault(
                    f"raw:{raw.id}",
                    CandidateEvidence.from_raw_row(
                        raw_bank_transaction_id=raw.id, kind=reference.kind,
                        financial_transaction_id=raw.normalized_transaction_id,
                        observed=posting.get(raw.normalized_transaction_id),
                    ),
                )

    for last_four in sorted(items):
        existing = list(session.scalars(
            select(m.BankHistoricalInstrumentCandidate).where(
                m.BankHistoricalInstrumentCandidate.last_four == last_four
            )
        ))
        if len(existing) > 1 or (
            existing and existing[0].discovery != m.CANDIDATE_INDIRECT_REFERENCE
        ):
            result.skipped.append(last_four)
            continue
        named = sorted(institutions.get(last_four, set()))
        if existing:
            institution = existing[0].institution
            before = (
                existing[0].occurrence_count, existing[0].first_seen_date,
                existing[0].last_seen_date, existing[0].evidence,
                len(existing[0].evidence_items),
            )
        else:
            # One institution only when the evidence is unanimous about it.
            institution = named[0] if len(named) == 1 else None
            before = None
        summary = (
            f"{m.CANDIDATE_INDIRECT_REFERENCE} found by {DISCOVERY_SCAN_VERSION}: explicit "
            f"account/card phrasing in another account's raw bank rows; "
            f"reference_kinds={','.join(sorted(kinds[last_four]))}; "
            f"institution_named_in_text={','.join(named) or 'none'}. Each distinct raw row is "
            "one evidence item. Dates are source boundaries, not lifecycle dates. No Payment "
            "Instrument was created."
        )
        candidate = record_candidate(
            session, last_four=last_four, institution=institution,
            discovery=m.CANDIDATE_INDIRECT_REFERENCE, evidence=summary,
            evidence_items=[items[last_four][k] for k in sorted(items[last_four])],
        )
        after = (
            candidate.occurrence_count, candidate.first_seen_date, candidate.last_seen_date,
            candidate.evidence, len(candidate.evidence_items),
        )
        if before is None:
            result.created.append(last_four)
        else:
            (result.updated if after != before else result.unchanged).append(last_four)
    session.flush()
    return result


# ---------------------------------------------------------------------------
# §12 — the states, reusing RF-One's existing meanings
# ---------------------------------------------------------------------------

REGISTERED_AND_SOURCED = "REGISTERED_AND_SOURCED"
REGISTERED_SOURCE_PARTIAL = "REGISTERED_SOURCE_PARTIAL"
REGISTERED_NO_SOURCE = "REGISTERED_NO_SOURCE"
SOURCE_WITHOUT_REGISTERED_INSTRUMENT = "SOURCE_WITHOUT_REGISTERED_INSTRUMENT"
REFERENCED_WITHOUT_REGISTERED_INSTRUMENT = "REFERENCED_WITHOUT_REGISTERED_INSTRUMENT"
HISTORICALLY_RESOLVED = "HISTORICALLY_RESOLVED"
NEEDS_HUMAN_CONFIRMATION = m.COVERAGE_NEEDS_CONFIRMATION

CENSUS_STATES = (
    REGISTERED_AND_SOURCED, REGISTERED_SOURCE_PARTIAL, REGISTERED_NO_SOURCE,
    SOURCE_WITHOUT_REGISTERED_INSTRUMENT, REFERENCED_WITHOUT_REGISTERED_INSTRUMENT,
    HISTORICALLY_RESOLVED, NEEDS_HUMAN_CONFIRMATION,
)


def instrument_last_four(instrument: "m.PaymentInstrument") -> str | None:
    """The instrument's effective last four — the same fallback the source
    resolver already applies, reused rather than restated."""
    from .service import extract_last_four
    return instrument.last_four or extract_last_four(instrument.external_account_identifier)


@dataclass
class InstrumentCoverage:
    """§16 — what the SOURCES say about one registered instrument.

    Every field here is a fact about the FILES. None of it is a fact about
    the account's life: `earliest`/`latest` are source boundaries, and the
    class refuses to offer them under any name that could be mistaken for
    an activation or a closure date.
    """

    instrument_id: int
    display_name: str
    institution: str | None
    last_four: str | None
    state: str
    files: list = field(default_factory=list)
    relationships: list = field(default_factory=list)
    earliest_source_date: date | None = None
    latest_source_date: date | None = None
    months_represented: list = field(default_factory=list)
    internal_missing_months: list = field(default_factory=list)
    economic_row_count: int = 0
    unresolved_reasons: list = field(default_factory=list)

    @property
    def source_count(self) -> int:
        return len(self.files)

    @property
    def is_resolved(self) -> bool:
        return not self.unresolved_reasons


def _months_between(lo: date, hi: date) -> list[str]:
    out, year, month = [], lo.year, lo.month
    while (year, month) <= (hi.year, hi.month):
        out.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return out


def coverage_for_fingerprints(
    instrument: "m.PaymentInstrument", fingerprints: list[SourceFingerprint],
) -> InstrumentCoverage:
    """Source coverage for one registered instrument.

    A gap is INTERNAL only: a month with no evidence that sits BETWEEN two
    months that have some. RF-One does not report the months before the
    first file or after the last one as missing, because it has no idea how
    far back this account goes — and guessing would turn a source boundary
    into a lifecycle claim, which is exactly the confusion §16 forbids.
    """
    coverage = InstrumentCoverage(
        instrument_id=instrument.id,
        display_name=instrument.display_name,
        institution=instrument.institution,
        last_four=instrument_last_four(instrument),
        state=REGISTERED_NO_SOURCE,
    )
    if not fingerprints:
        coverage.unresolved_reasons.append(
            "no source file has been supplied for this registered instrument"
        )
        return coverage

    coverage.files = sorted(fingerprints, key=lambda f: f.name)
    combined = reconcile(coverage.files)
    coverage.economic_row_count = combined.economic_row_count

    dated = [f for f in coverage.files if f.earliest and f.latest]
    if dated:
        coverage.earliest_source_date = min(f.earliest for f in dated)
        coverage.latest_source_date = max(f.latest for f in dated)

    present: set[str] = set()
    for fp in coverage.files:
        if fp.earliest and fp.latest:
            present.update(_months_between(fp.earliest, fp.latest))
    coverage.months_represented = sorted(present)
    if coverage.earliest_source_date and coverage.latest_source_date:
        whole = _months_between(coverage.earliest_source_date, coverage.latest_source_date)
        coverage.internal_missing_months = [mth for mth in whole if mth not in present]

    for i in range(len(coverage.files)):
        for j in range(i + 1, len(coverage.files)):
            rel = classify_relationship(coverage.files[i], coverage.files[j])
            coverage.relationships.append((coverage.files[i].name, coverage.files[j].name, rel))
            if rel.verdict == AMBIGUOUS:
                coverage.unresolved_reasons.append(
                    f"{coverage.files[i].name} vs {coverage.files[j].name}: {rel.basis}"
                )

    if coverage.internal_missing_months:
        coverage.unresolved_reasons.append(
            f"{len(coverage.internal_missing_months)} month(s) inside the covered span have "
            f"no source: {', '.join(coverage.internal_missing_months)}"
        )

    coverage.state = (
        REGISTERED_SOURCE_PARTIAL if coverage.unresolved_reasons else REGISTERED_AND_SOURCED
    )
    return coverage


# ---------------------------------------------------------------------------
# §14 — a human resolving a candidate
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CandidateEvidence:
    """One distinct piece of evidence for a candidate, with a STABLE key.

    Use `from_raw_row` for a preserved raw bank row: its key is the row's
    own id, so the same row can never be counted twice however often it is
    processed. `occurrences` matters only for evidence that is not tied to
    a canonical transaction (a whole source file summarised as N rows).
    """

    key: str
    kind: str
    raw_bank_transaction_id: int | None = None
    financial_transaction_id: int | None = None
    first_observed: date | None = None
    last_observed: date | None = None
    occurrences: int = 1

    @classmethod
    def from_raw_row(
        cls, *, raw_bank_transaction_id: int, kind: str,
        financial_transaction_id: int | None, observed: date | None,
    ) -> "CandidateEvidence":
        return cls(
            key=f"raw:{raw_bank_transaction_id}", kind=kind,
            raw_bank_transaction_id=raw_bank_transaction_id,
            financial_transaction_id=financial_transaction_id,
            first_observed=observed, last_observed=observed,
        )


def _summary_evidence(
    discovery: str, evidence: str, first_seen: date | None, last_seen: date | None,
    occurrences: int,
) -> CandidateEvidence:
    """The single evidence item a caller that has no row-level evidence
    describes: its identity is the description itself, so repeating the
    same description is recognised as the same evidence."""
    digest = hashlib.sha256(
        "|".join([discovery, evidence, str(first_seen), str(last_seen), str(occurrences)])
        .encode("utf-8")
    ).hexdigest()[:40]
    return CandidateEvidence(
        key=f"summary:{digest}", kind=discovery, first_observed=first_seen,
        last_observed=last_seen, occurrences=max(occurrences, 1),
    )


def _recompute_candidate(candidate: "m.BankHistoricalInstrumentCandidate") -> None:
    """Candidate figures as a pure function of its evidence set.

    Evidence tied to a canonical transaction counts once per DISTINCT
    transaction, however many raw copies evidence it; other evidence
    counts its declared `occurrences`. The span is the minimum first and
    maximum last observed date. Only changed values are written, so an
    unchanged evidence set leaves the row — and its `updated_at` — alone.
    """
    items = candidate.evidence_items
    transactions = {e.financial_transaction_id for e in items if e.financial_transaction_id}
    count = len(transactions) + sum(e.occurrences for e in items if not e.financial_transaction_id)
    firsts = [e.first_observed_date for e in items if e.first_observed_date]
    lasts = [e.last_observed_date for e in items if e.last_observed_date]
    values = {
        "occurrence_count": count,
        "first_seen_date": min(firsts) if firsts else None,
        "last_seen_date": max(lasts) if lasts else None,
    }
    for name, value in values.items():
        if getattr(candidate, name) != value:
            setattr(candidate, name, value)


def record_candidate(
    session: Session, *, last_four: str, institution: str | None, discovery: str,
    evidence: str, first_seen: date | None = None, last_seen: date | None = None,
    occurrences: int = 0, evidence_items: list[CandidateEvidence] | None = None,
) -> "m.BankHistoricalInstrumentCandidate":
    """Remember an account the evidence names and the registry lacks.

    Candidate identity + evidence set -> deterministic persisted state.
    Each piece of evidence carries a stable key and is stored once per
    candidate; `occurrence_count` and the first/last observed dates are
    RECOMPUTED from the whole set on every call, never accumulated. So
    processing the same evidence again changes nothing, and genuinely new
    evidence moves the figures by exactly what it adds.

    `evidence` is the human-readable description; it is appended only when
    the candidate does not already carry that exact text. A caller with no
    row-level evidence (`evidence_items` omitted) is recorded as a single
    summary item identified by its own description, dates and count — a
    repeated identical call is therefore also a no-op.

    Creates NO `PaymentInstrument` and never touches a resolution: what a
    human decided survives any number of re-discoveries.
    """
    if discovery not in m.CANDIDATE_DISCOVERIES:
        raise ValueError(
            f"{discovery!r} is not a discovery RF-One recognises: "
            f"{', '.join(m.CANDIDATE_DISCOVERIES)}."
        )
    if not last_four or len(last_four) != 4:
        raise ValueError("A candidate is identified by exactly four digits.")
    items = list(evidence_items) if evidence_items else [
        _summary_evidence(discovery, evidence, first_seen, last_seen, occurrences)
    ]

    candidate = session.scalars(
        select(m.BankHistoricalInstrumentCandidate).where(
            m.BankHistoricalInstrumentCandidate.last_four == last_four,
            m.BankHistoricalInstrumentCandidate.institution.is_(institution)
            if institution is None
            else m.BankHistoricalInstrumentCandidate.institution == institution,
        )
    ).first()
    if candidate is None:
        candidate = m.BankHistoricalInstrumentCandidate(
            last_four=last_four, institution=institution, discovery=discovery,
            evidence=evidence, occurrence_count=0,
        )
        session.add(candidate)
        session.flush()
    else:
        # A direct source is stronger evidence than a passing mention, so a
        # candidate is promoted to DIRECT_SOURCE but never demoted.
        if discovery == m.CANDIDATE_DIRECT_SOURCE and candidate.discovery != discovery:
            candidate.discovery = discovery
        if evidence not in (candidate.evidence or ""):
            candidate.evidence = f"{candidate.evidence} | {evidence}"

    known = {e.evidence_key for e in candidate.evidence_items}
    for item in items:
        if item.key in known:
            continue
        known.add(item.key)
        candidate.evidence_items.append(m.BankHistoricalInstrumentCandidateEvidence(
            evidence_key=item.key, evidence_kind=item.kind,
            raw_bank_transaction_id=item.raw_bank_transaction_id,
            financial_transaction_id=item.financial_transaction_id,
            first_observed_date=item.first_observed, last_observed_date=item.last_observed,
            occurrences=max(item.occurrences, 1),
        ))
    session.flush()
    _recompute_candidate(candidate)
    session.flush()
    return candidate


def resolve_candidate(
    session: Session, *, candidate: "m.BankHistoricalInstrumentCandidate", resolution: str,
    note: str | None = None, effective_date: date | None = None,
    payment_instrument_id: int | None = None, account_id: int | None = None,
) -> "m.BankHistoricalInstrumentCandidate":
    """Record what a human decided about a candidate.

    The invariant that governs the whole Bank domain applies here too:
    ABSENCE ALONE NEVER SELECTS ANY OF THESE. A candidate with no source
    file stays unresolved until a person names a reason, and nothing about
    it is concluded from silence.

    A lifecycle-ending resolution takes an effective date ONLY if the human
    genuinely knows one. None stays None, meaning UNKNOWN; it is never
    filled from the evidence span, because the last transaction RF-One
    happens to hold is not the day the account stopped.
    """
    if resolution not in m.CANDIDATE_RESOLUTIONS:
        raise ValueError(
            f"{resolution!r} is not a resolution RF-One recognises: "
            f"{', '.join(m.CANDIDATE_RESOLUTIONS)}."
        )
    note = (note or "").strip() or None
    if resolution == m.CANDIDATE_NOT_OURS and not note:
        raise ValueError(
            "Confirming that an identity is NOT OUR INSTRUMENT requires a reason — "
            "RF-One never infers that on its own."
        )
    if resolution == m.RESOLUTION_OTHER and not note:
        raise ValueError("A lifecycle end reason of OTHER requires a short explanation.")
    if resolution == m.CANDIDATE_CONFIRMED and payment_instrument_id is None:
        raise ValueError(
            "Confirming a candidate means naming the Payment Instrument it became."
        )
    if resolution != m.CANDIDATE_CONFIRMED and payment_instrument_id is not None:
        raise ValueError(
            "Only CONFIRMED_INSTRUMENT links a candidate to a Payment Instrument."
        )

    candidate.resolution = resolution
    candidate.resolution_note = note
    candidate.resolution_effective_date = effective_date  # None MEANS UNKNOWN
    candidate.resolved_payment_instrument_id = payment_instrument_id
    candidate.resolved_at = datetime.now(UTC)
    candidate.resolved_by_account_id = account_id
    session.flush()
    return candidate


def list_candidates(session: Session) -> list["m.BankHistoricalInstrumentCandidate"]:
    return list(session.scalars(
        select(m.BankHistoricalInstrumentCandidate).order_by(
            m.BankHistoricalInstrumentCandidate.last_four
        )
    ).all())


def candidate_state(candidate: "m.BankHistoricalInstrumentCandidate") -> str:
    """§12 — the state this candidate is in, in RF-One's own vocabulary."""
    if candidate.is_resolved:
        return HISTORICALLY_RESOLVED
    if candidate.resolution == m.CANDIDATE_SOURCE_MISSING:
        return REGISTERED_NO_SOURCE if candidate.resolved_payment_instrument_id \
            else REFERENCED_WITHOUT_REGISTERED_INSTRUMENT
    if candidate.discovery == m.CANDIDATE_DIRECT_SOURCE:
        return SOURCE_WITHOUT_REGISTERED_INSTRUMENT
    return REFERENCED_WITHOUT_REGISTERED_INSTRUMENT


# ---------------------------------------------------------------------------
# §17 — is the historical corpus complete?
# ---------------------------------------------------------------------------


@dataclass
class CorpusStatus:
    coverages: list = field(default_factory=list)
    candidates: list = field(default_factory=list)
    blockers: list = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        return not self.blockers


def corpus_status(
    session: Session, coverages: list[InstrumentCoverage],
) -> CorpusStatus:
    """Whether the historical corpus can be called complete.

    It cannot, while anything at all is unresolved — a registered
    instrument with no source, an internal gap, a source whose instrument
    is unknown, a reference nobody has judged, or two files whose overlap
    could not be determined. There is no override, silent or otherwise.
    """
    status = CorpusStatus(coverages=coverages)
    for coverage in coverages:
        label = f"{coverage.institution or '—'} · {coverage.display_name}"
        for reason in coverage.unresolved_reasons:
            status.blockers.append(f"{label}: {reason}")

    status.candidates = list_candidates(session)
    for candidate in status.candidates:
        if candidate.is_resolved:
            continue
        label = f"··{candidate.last_four}"
        if candidate.resolution == m.CANDIDATE_SOURCE_MISSING:
            status.blockers.append(
                f"{label}: marked SOURCE FILE MISSING — the file is still owed."
            )
        else:
            status.blockers.append(
                f"{label}: {candidate_state(candidate)} — no human has judged it yet."
            )
    return status
