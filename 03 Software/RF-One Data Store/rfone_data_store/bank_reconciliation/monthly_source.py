"""Monthly Bank SOURCE COMPLETENESS (BANK_MONTHLY_SOURCE_COMPLETENESS_001).

One question, and only one: for a given month, did RF-One receive an
original source download from every bank and card it should have?

That is deliberately NOT the accounting close, NOT reconciliation
completion, NOT P&L approval and NOT classification completion. A month can
be source-complete while every transaction in it is still unclassified.
Keeping them apart is the point: merged, a missing file would hide behind a
finished-looking close.

WHAT IS AND IS NOT A SOURCE
---------------------------
The source of truth is the ORIGINAL MONTHLY DOWNLOAD from each issuer,
already represented by `BankImportBatch` (original bytes, SHA-256 of those
bytes, detected format, resolved instrument, covered date range).

No spreadsheet is ever consulted here — not `2026 WP Control.xlsb`, not
`RfBank.xlsx`, not any hand-maintained control sheet. They may be historical
design evidence; they never determine which instruments were expected, what
was received, or whether a month may be declared complete. Nothing in this
module opens a file at all.

WHAT THIS MODULE REUSES RATHER THAN REINVENTS
---------------------------------------------
* file fingerprinting and exact-duplicate rejection — `service.import_csv`
  already hashes the original bytes and returns the existing batch instead
  of creating a second one;
* source file -> instrument identity — `service.resolve_instrument_for_source`
  already auto-assigns on exactly one match and refuses to guess otherwise;
* date-range overlap between files — `BankImportBatch.overlap_warning`;
* transaction-level deduplication — unchanged, and still the only thing
  that prevents counting money twice.

This module adds the month, the per-instrument coverage, the expectation
verdict and the completeness gate. Nothing else.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from .. import models as m
from . import accounting_dedup

UTC = timezone.utc


# ---------------------------------------------------------------------------
# The month itself
# ---------------------------------------------------------------------------


def period_bounds(year: int, month: int) -> tuple[date, date]:
    """The calendar month's first and last day.

    Generic by construction: no month is special-cased anywhere in this
    module, so August, September and every month after behave identically.
    """
    if not 1 <= month <= 12:
        raise ValueError(f"month must be 1..12, got {month}")
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def period_key(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def get_period(session: Session, year: int, month: int) -> "m.BankMonthlySourcePeriod | None":
    return session.scalars(
        select(m.BankMonthlySourcePeriod).where(
            m.BankMonthlySourcePeriod.period_month == period_key(year, month)
        )
    ).first()


def get_or_create_period(session: Session, year: int, month: int) -> "m.BankMonthlySourcePeriod":
    existing = get_period(session, year, month)
    if existing is not None:
        return existing
    start, end = period_bounds(year, month)
    period = m.BankMonthlySourcePeriod(
        period_month=period_key(year, month), period_start=start, period_end=end, status="OPEN",
    )
    session.add(period)
    session.flush()
    return period


def list_periods(session: Session) -> list["m.BankMonthlySourcePeriod"]:
    return list(session.scalars(
        select(m.BankMonthlySourcePeriod).order_by(m.BankMonthlySourcePeriod.period_month.desc())
    ).all())


# ---------------------------------------------------------------------------
# §7 — expectation, from EVIDENCE only
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Expectation:
    verdict: str
    basis: str


def evaluate_expectation(
    *, status: str, effective_start_date: date | None, effective_end_date: date | None,
    period_start: date, period_end: date,
) -> Expectation:
    """Was this instrument expected to produce a source file this month?

    A pure function of the evidence recorded about the instrument's life —
    no session, no I/O — so the rule can be read, tested and reasoned about
    on its own.

    The three answers mean exactly what they say:

      EXPECTED                  evidence PROVES it was active during some
                                part of the period;
      NOT_EXPECTED              evidence PROVES it was not;
      NEEDS_HUMAN_CONFIRMATION  the evidence does not settle it.

    The last one is the important one. An instrument that is ACTIVE today
    does not prove when it first became active; an instrument INACTIVE today
    does not prove when it stopped. Where the record is silent, RF-One says
    so instead of guessing, and asks a human.
    """
    # Proven over before the month began.
    if effective_end_date is not None and effective_end_date < period_start:
        return Expectation(
            m.COVERAGE_NOT_EXPECTED,
            f"ceased on {effective_end_date.isoformat()}, before this period began "
            f"({period_start.isoformat()}).",
        )
    # Proven not yet in existence when the month ended.
    if effective_start_date is not None and effective_start_date > period_end:
        return Expectation(
            m.COVERAGE_NOT_EXPECTED,
            f"became effective on {effective_start_date.isoformat()}, after this period ended "
            f"({period_end.isoformat()}).",
        )
    # Known to have started on or before the period's end.
    if effective_start_date is not None:
        if effective_end_date is not None:
            # The first branch already excluded an end before the period.
            return Expectation(
                m.COVERAGE_EXPECTED,
                f"active {effective_start_date.isoformat()} to {effective_end_date.isoformat()}, "
                "which overlaps this period.",
            )
        if status == "ACTIVE":
            return Expectation(
                m.COVERAGE_EXPECTED,
                f"active since {effective_start_date.isoformat()} and still open today.",
            )
        # INACTIVE, and the record never says when it stopped.
        return Expectation(
            m.COVERAGE_NEEDS_CONFIRMATION,
            f"became effective {effective_start_date.isoformat()} but is INACTIVE today with no "
            "recorded end date, so whether it was still active during this period is unknown.",
        )
    # No start date, but a known end at or after the period's start: it was
    # therefore still running when the period began.
    if effective_end_date is not None:
        return Expectation(
            m.COVERAGE_EXPECTED,
            f"ceased on {effective_end_date.isoformat()}, on or after this period began, so it "
            "was active during it.",
        )
    # Nothing is known about when this instrument's life began or ended.
    return Expectation(
        m.COVERAGE_NEEDS_CONFIRMATION,
        "no effective start date is recorded. `created_at` is when this row was written in "
        "RF-One, not when the real account or card opened, and is deliberately not used as a "
        "substitute.",
    )


def expectation_for(
    instrument: "m.PaymentInstrument", period: "m.BankMonthlySourcePeriod",
) -> Expectation:
    return evaluate_expectation(
        status=instrument.status,
        effective_start_date=instrument.effective_start_date,
        effective_end_date=instrument.effective_end_date,
        period_start=period.period_start,
        period_end=period.period_end,
    )


# ---------------------------------------------------------------------------
# §8/§5 — which source file covers which instrument this month
# ---------------------------------------------------------------------------


def batches_covering(
    session: Session, *, period: "m.BankMonthlySourcePeriod", instrument_id: int,
) -> list["m.BankImportBatch"]:
    """Accepted source files assigned to this instrument whose own covered
    date range intersects the month.

    A batch with no parsed date range is not counted: an unreadable file is
    not evidence that the month was covered.
    """
    return list(session.scalars(
        select(m.BankImportBatch)
        .where(
            m.BankImportBatch.payment_instrument_id == instrument_id,
            m.BankImportBatch.date_range_start.is_not(None),
            m.BankImportBatch.date_range_end.is_not(None),
            m.BankImportBatch.date_range_start <= period.period_end,
            m.BankImportBatch.date_range_end >= period.period_start,
        )
        .order_by(m.BankImportBatch.id)
    ).all())


def relevant_instruments(session: Session) -> list["m.PaymentInstrument"]:
    """Every Payment Instrument RF-One knows about.

    Inactive ones are included on purpose: a card closed last year is still
    relevant to a month it was alive for, and the expectation rule — not a
    pre-filter — decides whether it was. Nothing is ever excluded merely
    for being inactive today.
    """
    return list(session.scalars(
        select(m.PaymentInstrument).order_by(
            m.PaymentInstrument.institution, m.PaymentInstrument.display_name,
        )
    ).all())


def refresh_coverage(
    session: Session, period: "m.BankMonthlySourcePeriod",
) -> list["m.BankMonthlyInstrumentCoverage"]:
    """Bring the month's coverage rows in line with the instruments and the
    source files that exist right now.

    Re-runnable at any time while the month is open. It never overwrites a
    human resolution — only the machine-derived half (the expectation
    verdict, its basis, and the batch that covers the month) is recomputed.

    A COMPLETED month is left exactly as it is (§18): its rows are history.
    """
    if period.status == "COMPLETE":
        return list(period.coverages)

    existing = {c.payment_instrument_id: c for c in session.scalars(
        select(m.BankMonthlyInstrumentCoverage).where(
            m.BankMonthlyInstrumentCoverage.period_id == period.id
        )
    ).all()}

    rows: list[m.BankMonthlyInstrumentCoverage] = []
    for instrument in relevant_instruments(session):
        verdict = expectation_for(instrument, period)
        batches = batches_covering(session, period=period, instrument_id=instrument.id)
        coverage = existing.get(instrument.id)
        if coverage is None:
            coverage = m.BankMonthlyInstrumentCoverage(
                period_id=period.id, payment_instrument_id=instrument.id,
                expectation=verdict.verdict, expectation_basis=verdict.basis,
            )
            session.add(coverage)
        else:
            coverage.expectation = verdict.verdict
            coverage.expectation_basis = verdict.basis
        # The earliest covering batch is the one credited with the month;
        # later ones are corrections/reissues and are surfaced separately.
        coverage.import_batch_id = batches[0].id if batches else None
        rows.append(coverage)

    session.flush()
    return rows


def coverages(session: Session, period: "m.BankMonthlySourcePeriod") -> list["m.BankMonthlyInstrumentCoverage"]:
    return list(session.scalars(
        select(m.BankMonthlyInstrumentCoverage)
        .where(m.BankMonthlyInstrumentCoverage.period_id == period.id)
        .order_by(m.BankMonthlyInstrumentCoverage.id)
    ).all())


# ---------------------------------------------------------------------------
# The closure date, DERIVED — never typed
# ---------------------------------------------------------------------------

CONFIRMED_DUPLICATE = "CONFIRMED_DUPLICATE"


def lifecycle_eligible_transaction_filter():
    """Which of an instrument's transactions may date its closure.

    Everything except a KNOWN DUPLICATE COPY: the two states that mean
    "this row is a second copy of another row", and nothing else.

    NULL is eligible on both columns, and is written out explicitly rather
    than left to SQL's three-valued logic. `column != 'X'` evaluates to
    NULL, not TRUE, for a NULL column, so the shorter spelling would
    silently drop every row that was never marked at all.

    Deliberately NOT `accounting_dedup.accounting_visible_filter()`. That
    one answers whether a row feeds the BOOKS, and it excludes
    UNRESOLVED_NO_SETTLEMENT_ACCOUNT — real bank activity whose settlement
    account merely has not been configured yet. Incomplete configuration
    must never make an account look as though it stopped earlier than it
    did, so those rows stay eligible here.

    `FinancialTransaction.status` (COMPLETED / PENDING / REVERSED / FAILED
    / UNKNOWN) is deliberately NOT consulted. RF-One has no authoritative
    rule about which of those count, and a closure date is not the place
    to invent one: a REVERSED row still proves the account was alive that
    day.
    """
    return and_(
        or_(
            m.FinancialTransaction.duplicate_status.is_(None),
            m.FinancialTransaction.duplicate_status != CONFIRMED_DUPLICATE,
        ),
        or_(
            m.FinancialTransaction.accounting_status.is_(None),
            m.FinancialTransaction.accounting_status != accounting_dedup.DUPLICATE_SUPPRESSED,
        ),
    )


def last_posting_date(session: Session, instrument_id: int) -> date | None:
    """MAX(posting_date) over that instrument's eligible transactions.

    `None` MEANS UNKNOWN, and it is a real answer rather than a failure.
    An instrument with no transactions has no posting date; so does one
    whose transactions all carry `posting_date = NULL`, which is the
    normal case for a PayPal instrument, because that connector records
    only `transaction_datetime` and deliberately populates no separate
    posting date. Nothing is substituted in either case — not
    `transaction_date`, not `transaction_datetime`, not `created_at`, not
    today.
    """
    return session.scalars(
        select(func.max(m.FinancialTransaction.posting_date)).where(
            m.FinancialTransaction.payment_instrument_id == instrument_id,
            lifecycle_eligible_transaction_filter(),
        )
    ).first()


# ---------------------------------------------------------------------------
# §13 — human resolution of a month with no source file
# ---------------------------------------------------------------------------


def resolve_coverage(
    session: Session, *, coverage: "m.BankMonthlyInstrumentCoverage", resolution: str,
    note: str | None = None, effective_date: date | None = None,
    replaced_by_instrument_id: int | None = None, account_id: int | None = None,
) -> "m.BankMonthlyInstrumentCoverage":
    """Record what a human decided about an instrument with no source file.

    §14, the invariant this function exists to protect: absence of a source
    file NEVER closes, deactivates, or dates an instrument. Only the
    explicit lifecycle resolutions below touch `PaymentInstrument`, and only
    because a human chose them by name.

    NOT_EXPECTED_CONFIRMED requires a reason, because "this does not belong
    to this month" is a claim, not a default. Nothing infers it silently.

    An unknown effective date stays UNKNOWN (NULL). It is never replaced
    with today, with the period end, or with anything else convenient.

    THE CLOSURE DATE IS DERIVED, NOT SUPPLIED. For a lifecycle-ending
    resolution the operator names the reason and nothing else: the date
    comes from `last_posting_date`, the instrument's last eligible posting
    date. Passing `effective_date` alongside such a resolution is refused
    rather than ignored, so a second, manual way to date a closure cannot
    quietly reappear. `effective_date` remains available for the
    resolutions that end no life, where it is an annotation on the month
    and touches no instrument.
    """
    if resolution not in m.COVERAGE_RESOLUTIONS:
        raise ValueError(
            f"{resolution!r} is not a resolution RF-One recognises: {', '.join(m.COVERAGE_RESOLUTIONS)}."
        )
    if coverage.period.status == "COMPLETE":
        raise ValueError(
            f"Period {coverage.period.period_month} is COMPLETE. Reopen it before changing a "
            "resolution, so the change is a visible act rather than a silent edit of history."
        )
    note = (note or "").strip() or None
    if resolution == m.RESOLUTION_NOT_EXPECTED and not note:
        raise ValueError(
            "Confirming that an instrument is NOT EXPECTED for this month requires a short "
            "reason — RF-One never infers that state on its own."
        )
    if resolution == m.RESOLUTION_OTHER and not note:
        raise ValueError("A lifecycle end reason of OTHER requires a short explanation.")

    if resolution in m.LIFECYCLE_ENDING_RESOLUTIONS and effective_date is not None:
        raise ValueError(
            "A closure date is never supplied: RF-One derives it from the instrument's last "
            "eligible posting date. Record the reason alone."
        )

    instrument = coverage.payment_instrument
    if resolution in m.LIFECYCLE_ENDING_RESOLUTIONS:
        # DERIVED here, before anything is written, so the coverage row and
        # the instrument can never disagree about which date was used.
        effective_date = last_posting_date(session, instrument.id)

    coverage.resolution = resolution
    coverage.resolution_note = note
    coverage.resolution_effective_date = effective_date  # None MEANS UNKNOWN
    coverage.resolved_at = datetime.now(UTC)
    coverage.resolved_by_account_id = account_id

    if resolution in m.LIFECYCLE_ENDING_RESOLUTIONS:
        # The one path that may end a life, taken only because a human named
        # it. Identity — last four, external identifier, display name — is
        # never rewritten: the historical instrument stays queryable and
        # matchable exactly as it was.
        instrument.status = "INACTIVE"
        instrument.lifecycle_end_reason = resolution
        instrument.effective_end_date = effective_date  # None MEANS UNKNOWN
        if resolution == m.RESOLUTION_REPLACED:
            # The replacement is a DIFFERENT instrument. This records the
            # succession; it does not merge the two or move anything.
            instrument.replaced_by_instrument_id = replaced_by_instrument_id
    elif resolution == m.RESOLUTION_NO_ACTIVITY:
        # "It existed, it stayed active, nothing happened." Explicitly NOT a
        # lifecycle event: the instrument is left exactly as it was.
        pass

    session.flush()
    return coverage


def clear_resolution(
    session: Session, *, coverage: "m.BankMonthlyInstrumentCoverage",
) -> "m.BankMonthlyInstrumentCoverage":
    """Undo a resolution while the month is still open (§17 — resolutions
    are correctable before COMPLETE).

    Deliberately does NOT reverse a lifecycle change on the instrument:
    reviving a closed card is its own decision, made on the instrument, not
    a side effect of editing a month.
    """
    if coverage.period.status == "COMPLETE":
        raise ValueError(
            f"Period {coverage.period.period_month} is COMPLETE — reopen it first."
        )
    coverage.resolution = None
    coverage.resolution_note = None
    coverage.resolution_effective_date = None
    coverage.resolved_at = None
    coverage.resolved_by_account_id = None
    session.flush()
    return coverage


# ---------------------------------------------------------------------------
# §12 — the completeness gate
# ---------------------------------------------------------------------------


@dataclass
class CompletenessReport:
    period: "m.BankMonthlySourcePeriod"
    expected: int = 0
    received: int = 0
    resolved_without_file: int = 0
    not_expected: int = 0
    needs_confirmation: int = 0
    blockers: list[str] = field(default_factory=list)

    @property
    def missing_unresolved(self) -> int:
        return len(self.blockers)

    @property
    def can_complete(self) -> bool:
        return not self.blockers


def evaluate(session: Session, period: "m.BankMonthlySourcePeriod") -> CompletenessReport:
    """What stands between this month and COMPLETE.

    Every instrument must be either covered by an accepted source file or
    explicitly resolved by a human. Anything else is named as a blocker, in
    the operator's words rather than a row id, so the month never has to be
    diagnosed from a log.
    """
    report = CompletenessReport(period=period)
    for coverage in coverages(session, period):
        instrument = coverage.payment_instrument
        label = f"{instrument.institution or '—'} · {instrument.display_name}"
        if coverage.expectation == m.COVERAGE_EXPECTED:
            report.expected += 1
        elif coverage.expectation == m.COVERAGE_NOT_EXPECTED:
            report.not_expected += 1
        else:
            report.needs_confirmation += 1

        if coverage.source_received:
            report.received += 1
            continue
        if coverage.is_resolved:
            if coverage.resolution is not None:
                report.resolved_without_file += 1
            continue

        if coverage.resolution == m.RESOLUTION_SOURCE_FILE_MISSING:
            report.blockers.append(
                f"{label}: marked SOURCE FILE MISSING — the file is still owed."
            )
        elif coverage.expectation == m.COVERAGE_NEEDS_CONFIRMATION:
            report.blockers.append(
                f"{label}: RF-One cannot tell whether this was active during the month, and no "
                "human has said. Confirm it or resolve it."
            )
        else:
            report.blockers.append(
                f"{label}: expected this month, no source file received and no resolution recorded."
            )
    return report


def complete_period(
    session: Session, *, period: "m.BankMonthlySourcePeriod", account_id: int | None = None,
) -> CompletenessReport:
    """Declare the month source-complete, or refuse and say why.

    RF-One cannot mark a monthly Bank source period COMPLETE while an
    expected or unresolved account/card remains unexplained. That is the
    whole purpose of this gate, and it has no override.

    On success each coverage row is snapshotted (§18) so the decision stays
    reconstructable no matter what happens to the instruments afterwards.
    """
    refresh_coverage(session, period)
    report = evaluate(session, period)
    if not report.can_complete:
        period.status = "INCOMPLETE"
        session.flush()
        return report

    now = datetime.now(UTC)
    for coverage in coverages(session, period):
        instrument = coverage.payment_instrument
        coverage.instrument_display_name_snapshot = instrument.display_name
        coverage.institution_snapshot = instrument.institution
        coverage.last_four_snapshot = instrument.last_four
        coverage.instrument_status_snapshot = instrument.status
        coverage.lifecycle_label_snapshot = instrument.lifecycle_label

    period.status = "COMPLETE"
    period.completed_at = now
    period.completed_by_account_id = account_id
    _append_audit(
        period,
        f"{now.isoformat()} COMPLETE by account {account_id}: "
        f"{report.received} received, {report.resolved_without_file} resolved without a file, "
        f"{report.not_expected} not expected.",
    )
    session.flush()
    return report


def reopen_period(
    session: Session, *, period: "m.BankMonthlySourcePeriod", reason: str,
    account_id: int | None = None,
) -> "m.BankMonthlySourcePeriod":
    """Reopen a completed month without erasing what it had concluded.

    `completed_at`/`completed_by_account_id` and every snapshot stay exactly
    as they were; the reopening is appended to the audit log. §17 — a
    reopened month must still be able to say what it once decided and who
    decided it.
    """
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("Reopening a completed month requires a reason.")
    if period.status != "COMPLETE":
        raise ValueError(f"Period {period.period_month} is {period.status}, not COMPLETE.")
    _append_audit(
        period,
        f"{datetime.now(UTC).isoformat()} REOPENED by account {account_id}: {reason}",
    )
    period.status = "INCOMPLETE"
    session.flush()
    return period


def _append_audit(period: "m.BankMonthlySourcePeriod", line: str) -> None:
    period.audit_log = f"{period.audit_log}\n{line}" if period.audit_log else line
