"""Cross-ledger reconciliation — matches two `FinancialTransaction` rows on
DIFFERENT Payment Instruments that represent the two sides of the same
internal movement of funds (e.g. a PayPal "transfer to bank" row and the
corresponding bank "PayPal transfer" deposit row; a Bank Account "credit
card payment" row and the corresponding Credit Card "payment received"
row).

Ported from `feature/purchased-invoice-intake-alignment`'s proven
`bank_reconciliation/matching.py` (FINANCIAL_MODEL_CONVERGENCE_001 Phase 6)
and retargeted from that branch's `PaymentInstrumentTransaction`/
`PaymentInstrumentTransactionMatch` (neither present on this branch) to
canonical `FinancialTransaction`/`FinancialTransactionMatch`. This remains
RF-One's ONE reconciliation/matching engine — "deterministic, never fuzzy/
probabilistic": a match is only ever created when every required criterion
holds exactly, never from amount coincidence alone. When evidence is
insufficient, no match is created and the transaction is left unresolved
for `confirm_match()`/HUMAN review — never guessed.

Two field-level adaptations from the source engine, both because the
canonical model's own field shape differs from the retired ledger's:

- Currency comparison reads `PaymentInstrument.currency` on both sides
  (canonical `FinancialTransaction` carries no per-row `currency` column of
  its own — only `PaymentInstrument.currency` does; this is an existing
  Phase 1 schema fact, not invented here). A NULL currency on either side
  is treated as insufficient evidence — never guessed compatible.
- Date/time comparison uses `_effective_match_moment()`: canonical
  `FinancialTransaction` carries three optional date/time facts
  (`transaction_datetime`, `transaction_date`, `posting_date` — the source
  ledger had only one, non-nullable, `transaction_datetime`). The
  precedence is `transaction_datetime` (most precise) ->
  `transaction_date` -> `posting_date`, each used exactly as stored;
  nothing is ever written back to these fields, and a transaction with
  none of the three set cannot be matched (insufficient evidence, not
  guessed as "same day"). The proven 3-day tolerance window
  (`DEFAULT_DATE_TOLERANCE_DAYS`) is unchanged.

Recognition (WHO/WHY/HOW) is NOT touched by this module: a match decides
only the WHAT dimension (`classification = 'INTERNAL_TRANSFER'`) — it never
creates a `BankOccurrence`/`BankTransactionReason`/`BankTransactionExplanation`
row. Phase 6 left the resulting interaction with the Kermali export blocker
("Missing reconciliation decision" firing on a confirmed transfer that
legitimately has no WHO/WHY decision) unresolved; Phase 6B closes it in
`bank_reconciliation/export.py` (`_confirmed_internal_transfer_ids`), not
in this module — WHAT (a confirmed `FinancialTransactionMatch` created
here) is sufficient on its own, and export must never fabricate a WHO/WHY
merely to get past its own blocker.

Phase 6B also adds the ONE canonical, source-neutral post-acquisition
hook every acquisition path calls after creating/upserting a
`FinancialTransaction` — `on_financial_transaction_acquired`, at the
bottom of this module — so AUTO matching (this module's own existing
criteria, unchanged) is attempted automatically rather than only on
explicit demand.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import models as m

DEFAULT_DATE_TOLERANCE_DAYS = 3


def _effective_match_moment(transaction: m.FinancialTransaction) -> datetime | None:
    """The most precise legitimate date/time fact already stored on
    `transaction`, used ONLY for comparing two transactions during
    matching — never persisted back to any canonical field. Precedence:
    `transaction_datetime` (already a precise, tz-aware moment) ->
    `transaction_date` -> `posting_date` (each promoted to a UTC midnight
    `datetime` purely so it is comparable to a `transaction_datetime` on
    the other side of a match; this promotion is never written anywhere).

    Phase 6B fix: SQLite has no native timezone-aware storage — a
    `transaction_datetime` value re-read after the owning object's
    attributes expire (the default after any `session.commit()`) comes
    back tz-naive even though every writer of this field in this
    codebase stores it as UTC (PayPal's parser is the only writer, and it
    always parses a UTC `Z`-suffixed timestamp — `technical/connectors/
    paypal/parser.py`). Phase 6B's own post-acquisition hook is the first
    code path that routinely compares a freshly computed, always-aware
    `posting_date` fallback (below) against a real, possibly-reloaded
    `transaction_datetime` from an earlier commit, so a naive value read
    back here is normalized to UTC — never guessed, since UTC is the only
    value any writer has ever put there."""
    if transaction.transaction_datetime is not None:
        moment = transaction.transaction_datetime
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return moment
    fallback_date: date | None = transaction.transaction_date or transaction.posting_date
    if fallback_date is None:
        return None
    return datetime.combine(fallback_date, time.min, tzinfo=timezone.utc)


def is_matched(session: Session, transaction_id: int) -> bool:
    stmt = select(m.FinancialTransactionMatch).where(
        or_(
            m.FinancialTransactionMatch.transaction_a_id == transaction_id,
            m.FinancialTransactionMatch.transaction_b_id == transaction_id,
        )
    )
    return session.scalars(stmt).first() is not None


def _instruments_linked(a: m.PaymentInstrument, b: m.PaymentInstrument) -> bool:
    """True only when a `PaymentInstrument.linked_instrument_id`
    relationship explicitly connects the two, in either direction — this
    is the PRIMARY signal that separates a genuine internal-transfer
    candidate from two unrelated transactions that merely share an
    amount."""
    return a.linked_instrument_id == b.id or b.linked_instrument_id == a.id


def _currencies_compatible(a: m.PaymentInstrument, b: m.PaymentInstrument) -> bool:
    """Currency lives on `PaymentInstrument`, not `FinancialTransaction`.
    Both sides must carry the SAME, known currency — a NULL currency on
    either instrument is insufficient evidence, never assumed compatible.
    No FX conversion is ever performed."""
    return a.currency is not None and a.currency == b.currency


def find_cross_ledger_candidates(
    session: Session,
    transaction: m.FinancialTransaction,
    *,
    date_tolerance_days: int = DEFAULT_DATE_TOLERANCE_DAYS,
    require_linked_instrument: bool = True,
) -> list[m.FinancialTransaction]:
    """Unmatched transactions on a DIFFERENT Payment Instrument, with the
    exact opposite amount, within `date_tolerance_days` of `transaction`'s
    effective match moment. Returns every candidate found — callers decide
    what to do with zero/one/many; ambiguity (more than one candidate) is
    never resolved by guessing the "closest" one.

    `require_linked_instrument=True` (the default, used by
    `auto_match_transaction`) additionally requires an explicit
    `PaymentInstrument.linked_instrument_id` relationship — the automatic-
    match criterion. `require_linked_instrument=False` (used to surface
    HUMAN-review candidates in Bank Review) drops that one requirement
    while still requiring every other proven criterion (different
    transaction, different instrument, opposite amount, compatible
    currency, date proximity) — it never creates a match by itself, it only
    lists candidates for a human to explicitly `confirm_match()`."""
    own_moment = _effective_match_moment(transaction)
    if own_moment is None:
        return []
    window_start = own_moment - timedelta(days=date_tolerance_days)
    window_end = own_moment + timedelta(days=date_tolerance_days)

    stmt = select(m.FinancialTransaction).where(
        m.FinancialTransaction.id != transaction.id,
        m.FinancialTransaction.payment_instrument_id != transaction.payment_instrument_id,
        m.FinancialTransaction.amount_minor == -transaction.amount_minor,
    )
    candidates = session.scalars(stmt).all()

    results = []
    for candidate in candidates:
        candidate_moment = _effective_match_moment(candidate)
        if candidate_moment is None or not (window_start <= candidate_moment <= window_end):
            continue
        if not _currencies_compatible(transaction.payment_instrument, candidate.payment_instrument):
            continue
        if require_linked_instrument and not _instruments_linked(
            transaction.payment_instrument, candidate.payment_instrument
        ):
            continue
        if is_matched(session, candidate.id):
            continue
        results.append(candidate)

    return results


def create_match(
    session: Session,
    transaction_a: m.FinancialTransaction,
    transaction_b: m.FinancialTransaction,
    *,
    match_method: str,
    match_basis: str,
    confirmed_by: str | None = None,
) -> m.FinancialTransactionMatch:
    """Idempotent: re-matching the same pair returns the existing match
    (`uq_ftm_pair`, ordered by id per `ck_ftm_ordered_pair`) rather than
    duplicating it. Sets both transactions' `classification` to
    `'INTERNAL_TRANSFER'` — never `'REVENUE'`/`'EXPENSE'` — and never
    deletes or merges the two source rows; both remain independently
    auditable."""
    lower, higher = sorted([transaction_a, transaction_b], key=lambda t: t.id)

    existing = session.scalars(
        select(m.FinancialTransactionMatch).filter_by(
            transaction_a_id=lower.id, transaction_b_id=higher.id,
        )
    ).first()
    if existing is not None:
        return existing

    match = m.FinancialTransactionMatch(
        transaction_a_id=lower.id,
        transaction_b_id=higher.id,
        match_type="INTERNAL_TRANSFER",
        match_method=match_method,
        match_basis=match_basis,
        matched_amount_minor=abs(lower.amount_minor),
        confirmed_by=confirmed_by,
    )
    session.add(match)

    # Internal Transfer, never Revenue/Expense - a fee (if any) on a
    # DIFFERENT transaction row (e.g. the original PayPal customer payment)
    # is untouched by this.
    lower.classification = "INTERNAL_TRANSFER"
    higher.classification = "INTERNAL_TRANSFER"

    return match


def auto_match_transaction(
    session: Session,
    transaction: m.FinancialTransaction,
    *,
    date_tolerance_days: int = DEFAULT_DATE_TOLERANCE_DAYS,
) -> m.FinancialTransactionMatch | None:
    """Attempts a fully-automatic cross-ledger match for `transaction`.
    Only creates a match when exactly ONE candidate satisfies every
    criterion — zero candidates (nothing to match) or multiple candidates
    (genuinely ambiguous) both leave the transaction unresolved for
    `confirm_match()`/HUMAN review instead of guessing."""
    if is_matched(session, transaction.id):
        return None

    candidates = find_cross_ledger_candidates(session, transaction, date_tolerance_days=date_tolerance_days)
    if len(candidates) != 1:
        return None

    candidate = candidates[0]
    basis = (
        f"amount={abs(transaction.amount_minor)} {transaction.payment_instrument.currency}, "
        f"opposite direction, linked instruments "
        f"({transaction.payment_instrument_id}<->{candidate.payment_instrument_id}), "
        f"date within {date_tolerance_days}d"
    )
    return create_match(session, transaction, candidate, match_method="AUTO", match_basis=basis)


def confirm_match(
    session: Session,
    transaction_a_id: int,
    transaction_b_id: int,
    *,
    confirmed_by: str,
    note: str | None = None,
) -> m.FinancialTransactionMatch:
    """Human-confirmed match — the fallback for when `auto_match_
    transaction` found insufficient evidence (e.g. no `linked_instrument_id`
    configured yet). Does not require the instrument-link criterion
    `auto_match_transaction` enforces (a human reviewer may have evidence
    RF-One's own automatic criteria cannot see), but still requires
    opposite amounts, compatible currency, and two DIFFERENT instruments,
    so an operator typo cannot silently link an unrelated pair of rows as
    an internal transfer."""
    transaction_a = session.get(m.FinancialTransaction, transaction_a_id)
    transaction_b = session.get(m.FinancialTransaction, transaction_b_id)
    if transaction_a is None or transaction_b is None:
        raise ValueError("Both transactions must exist to confirm a match.")
    if transaction_a.payment_instrument_id == transaction_b.payment_instrument_id:
        raise ValueError("A cross-ledger match requires two different Payment Instruments.")
    if transaction_a.amount_minor != -transaction_b.amount_minor:
        raise ValueError("A cross-ledger match requires exactly opposite amounts.")
    if not _currencies_compatible(transaction_a.payment_instrument, transaction_b.payment_instrument):
        raise ValueError("A cross-ledger match requires the same known currency on both sides.")

    basis = f"human-confirmed by {confirmed_by}" + (f": {note}" if note else "")
    return create_match(
        session, transaction_a, transaction_b, match_method="HUMAN", match_basis=basis, confirmed_by=confirmed_by,
    )


def on_financial_transaction_acquired(
    session: Session, transaction: m.FinancialTransaction,
) -> m.FinancialTransactionMatch | None:
    """Canonical, source-neutral post-acquisition hook (Financial Model
    Convergence Phase 6B, Product Owner Decision D): matching belongs to
    the canonical transaction layer, not to a particular connector, so
    every acquisition path that creates/updates a `FinancialTransaction` —
    Bank CSV (`service.py`), PayPal (`technical/connectors/paypal/
    ingest.py`), and any future canonical financial connector — calls this
    ONE function immediately afterward instead of invoking matching itself
    or implementing its own matching logic.

    This hook owns none of the matching evidence (amount, instrument,
    currency, date, linked-instrument) — it only decides whether
    `transaction` is eligible to be considered for matching AT ALL right
    now, then delegates entirely to `auto_match_transaction`, the existing
    canonical Phase 6 engine, for the actual decision. A transaction still
    carrying a CSV-specific `CANDIDATE_DUPLICATE` status (spec §8) is not
    yet a settled fact and is excluded here — PayPal's own upsert
    idempotency never produces this status, so this exclusion is a no-op
    for PayPal-sourced transactions.

    Safe to call unconditionally and repeatedly (idempotent, mirrors
    `auto_match_transaction`/`create_match`'s own idempotency): a
    transaction already matched, or with zero/multiple candidates, simply
    returns `None` without side effects — so repeated PayPal
    synchronization or CSV re-import never creates a duplicate match."""
    if transaction.duplicate_status == "CANDIDATE_DUPLICATE":
        return None
    return auto_match_transaction(session, transaction)
