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
_REFERENCE_PATTERNS = (
    re.compile(r"\b(?:card|account|acct)\s+ending\s+in\s+(\d{4})\b", re.I),
    re.compile(r"\bending\s+in\s+(\d{4})\b", re.I),
    re.compile(r"\b(?:to|from)\s+(?:card|account|acct)\s*#?\s*[xX*]{2,}(\d{4})\b", re.I),
    re.compile(r"\b(?:card|account|acct)\s*#?\s*[xX*]{4,}(\d{4})\b", re.I),
)


def extract_instrument_references(text: str | None) -> set[str]:
    """Last-four values this description credibly refers to.

    Only explicit account/card phrasing counts. RF-One would rather miss a
    hint than invent an account out of a trace number.
    """
    found: set[str] = set()
    if not text:
        return found
    for pattern in _REFERENCE_PATTERNS:
        for match in pattern.finditer(text):
            found.add(match.group(1))
    return found


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


def record_candidate(
    session: Session, *, last_four: str, institution: str | None, discovery: str,
    evidence: str, first_seen: date | None = None, last_seen: date | None = None,
    occurrences: int = 0,
) -> "m.BankHistoricalInstrumentCandidate":
    """Remember an account the evidence names and the registry lacks.

    Creates NO `PaymentInstrument`. Re-recording the same identity updates
    the evidence span rather than duplicating the candidate, so a second
    file mentioning ··9191 strengthens the record instead of cluttering it.
    """
    if discovery not in m.CANDIDATE_DISCOVERIES:
        raise ValueError(
            f"{discovery!r} is not a discovery RF-One recognises: "
            f"{', '.join(m.CANDIDATE_DISCOVERIES)}."
        )
    if not last_four or len(last_four) != 4:
        raise ValueError("A candidate is identified by exactly four digits.")

    existing = session.scalars(
        select(m.BankHistoricalInstrumentCandidate).where(
            m.BankHistoricalInstrumentCandidate.last_four == last_four,
            m.BankHistoricalInstrumentCandidate.institution.is_(institution)
            if institution is None
            else m.BankHistoricalInstrumentCandidate.institution == institution,
        )
    ).first()
    if existing is None:
        existing = m.BankHistoricalInstrumentCandidate(
            last_four=last_four, institution=institution, discovery=discovery,
            evidence=evidence, first_seen_date=first_seen, last_seen_date=last_seen,
            occurrence_count=occurrences,
        )
        session.add(existing)
        session.flush()
        return existing

    # A direct source is stronger evidence than a passing mention, so a
    # candidate is promoted to DIRECT_SOURCE but never demoted.
    if discovery == m.CANDIDATE_DIRECT_SOURCE:
        existing.discovery = discovery
    if evidence not in (existing.evidence or ""):
        existing.evidence = f"{existing.evidence} | {evidence}"
    if first_seen and (existing.first_seen_date is None or first_seen < existing.first_seen_date):
        existing.first_seen_date = first_seen
    if last_seen and (existing.last_seen_date is None or last_seen > existing.last_seen_date):
        existing.last_seen_date = last_seen
    existing.occurrence_count += occurrences
    session.flush()
    return existing


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
