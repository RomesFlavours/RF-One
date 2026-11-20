"""Accounting deduplication of bank transactions
(BANK_CARDHOLDER_AND_ACCOUNTING_DEDUPLICATION_001).

The problem this solves: the same economic operation reaches the books
more than once. It appears on a mother card's file AND on the linked
card's file, in two overlapping Chase downloads, twice inside one file,
in files saved under different names, or in imports run weeks apart.
**A different `last_four` does not make a row a different accounting
fact.**

The Product Owner's key — four elements, and only these four:

    1. settlement bank account
    2. accounting/posting date
    3. signed amount, to the cent
    4. normalized payee/receiver description

When all four coincide the rows are the same accounting fact, and exactly
one occurrence may feed accounting, the monthly export, P&L and Balance
Sheet.

Three boundaries this module holds absolutely:

* **Raw is never touched.** `BankImportBatch.raw_file_bytes` and
  `RawBankTransaction.raw_fields` are neither read for mutation nor
  written. No `FinancialTransaction` is deleted either — a suppressed row
  stays, linked to its canonical, and remains visible in import/audit
  screens.
* **Nothing is invented.** A transaction whose settlement account is not
  configured is reported as `UNRESOLVED_NO_SETTLEMENT_ACCOUNT`, never
  merged with anything. Unresolved rows are never grouped with each other:
  two cards whose accounts are both unknown are not thereby the same
  account.
* **A human decision wins.** The pre-existing `duplicate_status` flow
  (per-instrument candidate duplicates, spec §7/§8) is a different
  mechanism with a different question, and a person's verdict recorded
  there is authoritative — see `_human_verdict_precedence` below.

This module is separate from `service.py`'s `compute_identity_fingerprint`
on purpose. That fingerprint is per-INSTRUMENT and deliberately includes
transaction type, reference and balance so a reviewer can see why two
similar rows might be distinct. This key is per-SETTLEMENT-ACCOUNT and
deliberately ignores all three, because the accountant's question is
narrower: did this money movement already hit the books?
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import models as m
from . import card_configuration

# Bumped whenever `normalize_payee` changes. Stored on every transaction it
# normalized, so a grouping decision stays reproducible and auditable after
# the algorithm evolves — and so a recompute can tell which rows were
# keyed by an older version.
PAYEE_NORMALIZATION_VERSION = "v1"

CANONICAL = "CANONICAL"
DUPLICATE_SUPPRESSED = "DUPLICATE_SUPPRESSED"
UNRESOLVED_NO_SETTLEMENT_ACCOUNT = "UNRESOLVED_NO_SETTLEMENT_ACCOUNT"

# Statuses that may feed accounting. Everything else must not.
ACCOUNTING_VISIBLE_STATUSES = (CANONICAL,)

# --- Payee normalization ----------------------------------------------------
#
# Conservative by design. It removes only technical noise that is already
# identifiable with certainty in the supported formats, and never strips a
# number or a word that could distinguish two genuinely different payees:
# an invoice number, a store number or an order id is exactly what tells
# two US Foods charges apart, so digits are preserved.

# Chase inserts a card-suffix marker into card-file descriptions that the
# same merchant does not carry on the settlement account's own line. It is
# pure technical noise about WHICH PLASTIC was used, which is precisely
# what accounting dedup must ignore.
_CARD_SUFFIX_NOISE_RE = re.compile(r"\bCARD\s*#?\s*\d{4}\b")
# A trailing "XXXX1234"/"************1234" masked card number, same reason.
# No leading `\b`: `*` is not a word character, so a word boundary never
# exists before it and the pattern would silently never match.
_MASKED_CARD_RE = re.compile(r"(?<![A-Z0-9])[X*]{2,}\s*\d{4}\b")
# Punctuation that varies between export formats of the SAME merchant
# (Chase inserts `*`, `#`, extra dots and commas inconsistently) is
# collapsed to a single space. Letters and digits are never touched.
_PUNCTUATION_RE = re.compile(r"[^A-Z0-9]+")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_payee(raw: str | None) -> str:
    """Deterministic, conservative, verifiable normalization of a payee /
    receiver description.

    Steps, in order: trim; upper-case; drop the two technical card
    markers above; collapse non-alphanumeric punctuation to spaces;
    collapse whitespace. Nothing else is removed — in particular no
    numeric token and no word is dropped on a guess, because either could
    be what distinguishes two different receivers.

    The ORIGINAL description is never replaced: callers store this
    alongside `description_original`, together with
    `PAYEE_NORMALIZATION_VERSION`."""
    text = (raw or "").strip().upper()
    text = _CARD_SUFFIX_NOISE_RE.sub(" ", text)
    text = _MASKED_CARD_RE.sub(" ", text)
    text = _PUNCTUATION_RE.sub(" ", text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def compute_accounting_dedup_key(
    *, settlement_account_id: int, posting_date: date, amount_minor: int, payee_normalized: str,
) -> str:
    """The fingerprint of the four-element key. Hashed rather than stored
    as a tuple so it can be indexed and compared cheaply; the four inputs
    remain individually readable on the transaction, so a group is always
    explainable without reversing the hash."""
    parts = [
        str(settlement_account_id),
        posting_date.isoformat(),
        str(amount_minor),
        payee_normalized,
    ]
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Per-transaction classification
# ---------------------------------------------------------------------------


def _human_verdict_precedence(txn: "m.FinancialTransaction") -> str | None:
    """Where the older per-instrument human flow has already produced a
    verdict, that verdict wins over automatic accounting dedup. Two rules,
    both documented as the deliberate precedence:

    * `CONFIRMED_DISTINCT` — a person looked at these two rows and said
      they are NOT the same operation. Automatic dedup must not overrule
      that, so the row stays CANONICAL even if the four-element key
      matches another. This is the conservative direction: keeping a real
      transaction in the books is recoverable, silently dropping one is
      not.
    * `CONFIRMED_DUPLICATE` — a person already said this row is a
      duplicate. It is suppressed regardless of what the key says, and
      the reason records that a human, not the engine, decided it.

    Any other value (NONE, CANDIDATE_DUPLICATE, NULL) leaves the decision
    to the engine."""
    if txn.duplicate_status == "CONFIRMED_DISTINCT":
        return CANONICAL
    if txn.duplicate_status == "CONFIRMED_DUPLICATE":
        return DUPLICATE_SUPPRESSED
    return None


def settlement_account_id_for(
    session: Session, txn: "m.FinancialTransaction",
    instrument_cache: dict[int, "m.PaymentInstrument"] | None = None,
) -> int | None:
    """The settlement account that scopes this transaction's accounting.

    A BANK_ACCOUNT stands for itself; a CREDIT_CARD resolves through the
    settlement account in force on its posting date. `None` means the
    configuration is missing — the caller must report it, never guess."""
    if txn.payment_instrument_id is None:
        return None
    if instrument_cache is not None and txn.payment_instrument_id in instrument_cache:
        instrument = instrument_cache[txn.payment_instrument_id]
    else:
        instrument = session.get(m.PaymentInstrument, txn.payment_instrument_id)
        if instrument_cache is not None and instrument is not None:
            instrument_cache[txn.payment_instrument_id] = instrument
    if instrument is None:
        return None
    account = card_configuration.accounting_account_for(
        session, instrument=instrument, on_date=txn.posting_date,
    )
    return account.id if account is not None else None


def classify_transaction(
    session: Session, txn: "m.FinancialTransaction",
    instrument_cache: dict[int, "m.PaymentInstrument"] | None = None,
) -> None:
    """Compute and store this transaction's payee normalization,
    settlement account and dedup key. Does NOT decide canonical vs
    suppressed — that is a decision about a GROUP and belongs to
    `recompute_accounting_dedup`, which is the only function that may set
    it. Keeping the two apart is what makes the group decision stable."""
    txn.payee_normalized = normalize_payee(txn.description_original)
    txn.payee_normalization_version = PAYEE_NORMALIZATION_VERSION

    settlement_account_id = settlement_account_id_for(session, txn, instrument_cache)
    txn.accounting_settlement_account_id = settlement_account_id

    if settlement_account_id is None or txn.posting_date is None:
        txn.accounting_dedup_key = None
        return
    txn.accounting_dedup_key = compute_accounting_dedup_key(
        settlement_account_id=settlement_account_id,
        posting_date=txn.posting_date,
        amount_minor=txn.amount_minor,
        payee_normalized=txn.payee_normalized,
    )


# ---------------------------------------------------------------------------
# Group resolution
# ---------------------------------------------------------------------------


def _canonical_sort_key(txn: "m.FinancialTransaction") -> tuple:
    """Deterministic, stable, idempotent choice of the canonical row.

    Ordered by: (1) a row a human already confirmed as a duplicate never
    wins; (2) then the lowest id — the occurrence RF-One acquired first.
    Id is unique and immutable, so re-running dedup over the same data,
    or re-importing that data, can never move the canonical row around:
    the earliest-acquired occurrence stays canonical, and a newly imported
    copy always loses to it."""
    return (1 if txn.duplicate_status == "CONFIRMED_DUPLICATE" else 0, txn.id)


@dataclass
class DedupOutcome:
    """What a recompute did, in the terms the Import & Instruments summary
    reports."""

    transactions_considered: int = 0
    duplicate_groups: int = 0
    canonical_transactions: int = 0
    suppressed_transactions: int = 0
    unresolved_transactions: int = 0
    raw_rows_preserved: int = 0
    unresolved_instrument_ids: set[int] = field(default_factory=set)

    @property
    def unresolved_cards(self) -> int:
        return len(self.unresolved_instrument_ids)


def recompute_accounting_dedup(
    session: Session, *, payment_instrument_ids: list[int] | None = None,
) -> DedupOutcome:
    """Recompute accounting deduplication, idempotently.

    Safe to run at any time and as often as wanted: it derives everything
    from the current transactions and the current card configuration, and
    writes only the accounting-dedup columns. It never touches
    `raw_file_bytes`, `raw_fields`, any amount, any date, any description,
    the per-instrument `duplicate_status` flow, or a reconciliation
    decision.

    Scope: the whole ledger by default. `payment_instrument_ids` narrows
    the rows to RE-KEY (after one card's settlement account changed, say),
    but the GROUPS those rows belong to are always resolved in full —
    otherwise a card's rows could be re-keyed into a group whose other
    members were never reconsidered, and the canonical choice would depend
    on what the caller happened to pass in.

    Called after an import, after a settlement account is assigned or
    corrected, and after a batch or transaction is reassigned to another
    instrument."""
    query = select(m.FinancialTransaction)
    if payment_instrument_ids:
        query = query.where(
            m.FinancialTransaction.payment_instrument_id.in_(payment_instrument_ids)
        )
    scoped = list(session.scalars(query).all())

    instrument_cache: dict[int, m.PaymentInstrument] = {}
    for txn in scoped:
        classify_transaction(session, txn, instrument_cache)
    session.flush()

    # Resolve every group any re-keyed row now belongs to, in full.
    touched_keys = {t.accounting_dedup_key for t in scoped if t.accounting_dedup_key}
    if payment_instrument_ids and touched_keys:
        group_members = list(session.scalars(
            select(m.FinancialTransaction).where(
                m.FinancialTransaction.accounting_dedup_key.in_(touched_keys)
            )
        ).all())
    else:
        group_members = scoped

    by_key: dict[str, list[m.FinancialTransaction]] = {}
    outcome = DedupOutcome()

    for txn in group_members:
        outcome.transactions_considered += 1
        if txn.accounting_dedup_key is None:
            txn.accounting_status = UNRESOLVED_NO_SETTLEMENT_ACCOUNT
            txn.accounting_canonical_transaction_id = None
            txn.accounting_dedup_reason = (
                "No settlement account is configured for this transaction's instrument on its "
                "posting date, so its accounting identity cannot be established. It is neither "
                "deduplicated nor merged with anything."
            )
            outcome.unresolved_transactions += 1
            if txn.payment_instrument_id is not None:
                outcome.unresolved_instrument_ids.add(txn.payment_instrument_id)
            continue
        by_key.setdefault(txn.accounting_dedup_key, []).append(txn)

    for key, members in by_key.items():
        members.sort(key=_canonical_sort_key)
        canonical = members[0]

        human_verdict = _human_verdict_precedence(canonical)
        if human_verdict == DUPLICATE_SUPPRESSED and len(members) == 1:
            # A lone row a human already called a duplicate stays suppressed,
            # with no canonical of its own to point at.
            canonical.accounting_status = DUPLICATE_SUPPRESSED
            canonical.accounting_canonical_transaction_id = None
            canonical.accounting_dedup_reason = (
                "Suppressed from accounting by an explicit human duplicate decision "
                "(duplicate_status = CONFIRMED_DUPLICATE), not by the accounting key."
            )
            outcome.suppressed_transactions += 1
            continue

        canonical.accounting_status = CANONICAL
        canonical.accounting_canonical_transaction_id = None
        canonical.accounting_dedup_reason = (
            f"Canonical accounting occurrence of {len(members)} row(s) sharing the accounting key "
            f"(settlement account {canonical.accounting_settlement_account_id}, "
            f"{canonical.posting_date.isoformat() if canonical.posting_date else '—'}, "
            f"{canonical.amount_minor} cents, payee {canonical.payee_normalized!r}). "
            f"Chosen as the earliest acquired occurrence (id {canonical.id})."
            if len(members) > 1 else
            "Only occurrence of this accounting key — nothing to deduplicate."
        )
        outcome.canonical_transactions += 1

        for duplicate in members[1:]:
            if _human_verdict_precedence(duplicate) == CANONICAL:
                # A human explicitly said this row is NOT the same operation.
                duplicate.accounting_status = CANONICAL
                duplicate.accounting_canonical_transaction_id = None
                duplicate.accounting_dedup_reason = (
                    "Shares the accounting key with transaction "
                    f"{canonical.id}, but a human explicitly recorded it as CONFIRMED_DISTINCT. "
                    "The human decision takes precedence and this row still feeds accounting."
                )
                outcome.canonical_transactions += 1
                continue
            duplicate.accounting_status = DUPLICATE_SUPPRESSED
            duplicate.accounting_canonical_transaction_id = canonical.id
            duplicate.accounting_dedup_reason = (
                f"Same accounting fact as transaction {canonical.id}: identical settlement account "
                f"({canonical.accounting_settlement_account_id}), posting date "
                f"({canonical.posting_date.isoformat() if canonical.posting_date else '—'}), signed "
                f"amount ({canonical.amount_minor} cents) and normalized payee "
                f"({canonical.payee_normalized!r}). Kept and linked, excluded from accounting."
            )
            outcome.suppressed_transactions += 1

        if len([t for t in members if t.accounting_status == DUPLICATE_SUPPRESSED]) > 0:
            outcome.duplicate_groups += 1

    session.flush()

    outcome.raw_rows_preserved = session.scalar(
        select(func.count(m.RawBankTransaction.id))
    ) or 0
    return outcome


def summarize(session: Session) -> DedupOutcome:
    """Read-only counters for the Import & Instruments page. Computes
    nothing and writes nothing — it reports what the last recompute
    stored, so the page can never quietly change the data it displays."""
    outcome = DedupOutcome()
    outcome.raw_rows_preserved = session.scalar(select(func.count(m.RawBankTransaction.id))) or 0
    outcome.transactions_considered = session.scalar(
        select(func.count(m.FinancialTransaction.id))
    ) or 0
    outcome.canonical_transactions = session.scalar(
        select(func.count(m.FinancialTransaction.id))
        .where(m.FinancialTransaction.accounting_status == CANONICAL)
    ) or 0
    outcome.suppressed_transactions = session.scalar(
        select(func.count(m.FinancialTransaction.id))
        .where(m.FinancialTransaction.accounting_status == DUPLICATE_SUPPRESSED)
    ) or 0
    outcome.unresolved_transactions = session.scalar(
        select(func.count(m.FinancialTransaction.id))
        .where(m.FinancialTransaction.accounting_status == UNRESOLVED_NO_SETTLEMENT_ACCOUNT)
    ) or 0
    outcome.duplicate_groups = session.scalar(
        select(func.count(func.distinct(m.FinancialTransaction.accounting_canonical_transaction_id)))
        .where(m.FinancialTransaction.accounting_canonical_transaction_id.is_not(None))
    ) or 0
    outcome.unresolved_instrument_ids = set(session.scalars(
        select(m.FinancialTransaction.payment_instrument_id)
        .where(m.FinancialTransaction.accounting_status == UNRESOLVED_NO_SETTLEMENT_ACCOUNT)
        .distinct()
    ).all()) - {None}
    return outcome


def duplicate_group(
    session: Session, transaction_id: int,
) -> list["m.FinancialTransaction"]:
    """Every row of the accounting group a transaction belongs to, canonical
    first — what the Review detail view shows. Returns the transaction
    alone when it has no group."""
    txn = session.get(m.FinancialTransaction, transaction_id)
    if txn is None:
        return []
    canonical_id = txn.accounting_canonical_transaction_id or txn.id
    canonical = session.get(m.FinancialTransaction, canonical_id) or txn
    others = list(session.scalars(
        select(m.FinancialTransaction)
        .where(m.FinancialTransaction.accounting_canonical_transaction_id == canonical.id)
        .order_by(m.FinancialTransaction.id)
    ).all())
    return [canonical] + others


def is_accounting_visible(txn: "m.FinancialTransaction") -> bool:
    """Whether this transaction feeds accounting.

    A row acquired before this task ran has `accounting_status = NULL`;
    it is treated as visible so an un-recomputed database keeps exporting
    exactly what it exported before, rather than silently emptying."""
    return txn.accounting_status is None or txn.accounting_status in ACCOUNTING_VISIBLE_STATUSES


def accounting_visible_filter():
    """The same rule as a SQL filter, so a query and an in-memory check can
    never diverge."""
    return or_(
        m.FinancialTransaction.accounting_status.is_(None),
        m.FinancialTransaction.accounting_status.in_(ACCOUNTING_VISIBLE_STATUSES),
    )


def not_suppressed_filter():
    """Everything EXCEPT a copy suppressed as an accounting duplicate.

    Deliberately weaker than `accounting_visible_filter`, and used for a
    different job: deciding what a month's export must still be CHECKED
    for. A row whose settlement account is unknown is not exportable, but
    it must stay in the blocker scope so every other reason it is not
    ready — an undecided candidate duplicate, a missing Who — is still
    reported. Dropping it from scope would silently narrow the reasons a
    human is shown to the single one this task introduced."""
    return or_(
        m.FinancialTransaction.accounting_status.is_(None),
        m.FinancialTransaction.accounting_status != DUPLICATE_SUPPRESSED,
    )
