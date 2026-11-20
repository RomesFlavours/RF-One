"""Automated synthetic tests for the Business Date foundation (Product
Owner decision).

Mirrors the established `*_validation.py` pattern (see
`identity_authority_signature_validation.py`): synthetic fixture, disposable
database, always rolled back, never touches real data. Deliberately covers
only the minimum behaviors requested for this task — not an exhaustive
suite, and no Tips/Payroll behavior is exercised here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone

from sqlalchemy.orm import Session, sessionmaker

from . import models as m
from .business_date import derive_business_date, resolve_and_persist_order_business_date

UTC = timezone.utc


@dataclass
class ValidationResult:
    success: bool
    checks_passed: list[str] = field(default_factory=list)
    checks_failed: list[str] = field(default_factory=list)

    def check(self, description: str, condition: bool) -> None:
        if condition:
            self.checks_passed.append(description)
        else:
            self.checks_failed.append(description)
            self.success = False


def run_validation(session_factory: sessionmaker[Session]) -> ValidationResult:
    result = ValidationResult(success=True)
    with session_factory() as session:
        try:
            _test_pure_derivation_cutoff_boundary(result)
            _test_two_locations_different_timezones_and_cutoffs(result)
            _test_order_business_date_persists_via_settlement_time(session, result)
            _test_missing_inputs_never_invent_a_date(session, result)
        finally:
            session.rollback()
    return result


def _make_merchant_location(
    session: Session, name: str, *, timezone_name: str | None, cutoff: time | None,
) -> m.Location:
    merchant = m.Merchant(name=f"{name} Merchant")
    session.add(merchant)
    session.flush()
    location = m.Location(
        merchant_id=merchant.id, name=f"{name} Location", timezone=timezone_name,
        operating_day_cutoff_time=cutoff,
    )
    session.add(location)
    session.flush()
    return location


def _make_order_with_successful_payment(
    session: Session, *, location_id: int, payment_created_at: datetime,
) -> m.Order:
    order = m.Order(location_id=location_id, created_at=payment_created_at)
    session.add(order)
    session.flush()
    payment = m.Payment(order_id=order.id, created_at=payment_created_at, result="SUCCESS", amount=1000)
    session.add(payment)
    session.flush()
    return order


# ---------------------------------------------------------------------------
# C/D/E. Cutoff boundary + timezone conversion (pure function — no DB
# needed for the core rule itself).
# ---------------------------------------------------------------------------


def _test_pure_derivation_cutoff_boundary(result: ValidationResult) -> None:
    cutoff = time(4, 0)  # 04:00 local

    # Sales Model §6a's own worked example: Order opens Aug 30 23:45 local,
    # Payment (Settlement Time) occurs Aug 31 00:30 local -> Business Date
    # Aug 30 for both, under a 04:00 cutoff.
    settlement_before_cutoff = datetime(2026, 8, 31, 0, 30, tzinfo=UTC)  # 00:30 local (UTC test tz)
    business_date_before = derive_business_date(
        settlement_time=settlement_before_cutoff, location_timezone="UTC",
        operating_day_cutoff_time=cutoff,
    )
    result.check(
        "Settlement Time BEFORE the operating-day cutoff (00:30, cutoff 04:00) is attributed to the "
        "PREVIOUS calendar day (Aug 30) — matches Sales Model §6a's worked example",
        business_date_before == date(2026, 8, 30),
    )

    settlement_at_or_after_cutoff = datetime(2026, 8, 30, 23, 45, tzinfo=UTC)  # 23:45 local
    business_date_after = derive_business_date(
        settlement_time=settlement_at_or_after_cutoff, location_timezone="UTC",
        operating_day_cutoff_time=cutoff,
    )
    result.check(
        "Settlement Time AT/AFTER the operating-day cutoff (23:45, cutoff 04:00) is attributed to "
        "that SAME calendar day (Aug 30) — matches Sales Model §6a's worked example",
        business_date_after == date(2026, 8, 30),
    )

    exactly_at_cutoff = datetime(2026, 8, 31, 4, 0, tzinfo=UTC)
    business_date_exact = derive_business_date(
        settlement_time=exactly_at_cutoff, location_timezone="UTC", operating_day_cutoff_time=cutoff,
    )
    result.check(
        "Settlement Time exactly AT the cutoff (04:00) is attributed to that same calendar day "
        "(at-or-after, never before)",
        business_date_exact == date(2026, 8, 31),
    )


def _test_two_locations_different_timezones_and_cutoffs(result: ValidationResult) -> None:
    # F. The SAME UTC instant, at two Locations with different timezones and
    # different cutoffs, must be able to derive different Business Dates.
    same_utc_instant = datetime(2026, 3, 15, 8, 30, tzinfo=UTC)  # 08:30 UTC

    # Location A: America/New_York (UTC-4 in March, EDT starts 2nd Sunday of
    # March) -> local time ~04:30, cutoff 04:00 -> at/after cutoff -> same day.
    date_a = derive_business_date(
        settlement_time=same_utc_instant, location_timezone="America/New_York",
        operating_day_cutoff_time=time(4, 0),
    )
    # Location B: Pacific/Honolulu (UTC-10, no DST) -> local time 22:30 on
    # the PREVIOUS calendar day, cutoff 02:00 -> at/after cutoff -> that
    # (previous, relative to UTC date) same local day.
    date_b = derive_business_date(
        settlement_time=same_utc_instant, location_timezone="Pacific/Honolulu",
        operating_day_cutoff_time=time(2, 0),
    )
    result.check(
        "the same UTC instant produces different Business Dates at two Locations with different "
        "timezones/cutoffs (timezone conversion happens before cutoff evaluation)",
        date_a == date(2026, 3, 15) and date_b == date(2026, 3, 14) and date_a != date_b,
    )


# ---------------------------------------------------------------------------
# A/B. Migration applies (implicit — this suite runs against a disposable DB
# migrated from scratch) + Order.business_date persists via a real Order's
# Settlement Time.
# ---------------------------------------------------------------------------


def _test_order_business_date_persists_via_settlement_time(
    session: Session, result: ValidationResult
) -> None:
    location = _make_merchant_location(
        session, "Business Date Persistence", timezone_name="America/New_York",
        cutoff=time(4, 0),
    )
    # 2026-08-31 03:00 UTC = 2026-08-30 23:00 America/New_York (EDT, UTC-4)
    # -> local time 23:00, at/after cutoff 04:00 -> same calendar day (Aug 30).
    order = _make_order_with_successful_payment(
        session, location_id=location.id, payment_created_at=datetime(2026, 8, 31, 3, 0, tzinfo=UTC),
    )
    result.check(
        "Order.business_date is None before resolution (never invented eagerly)",
        order.business_date is None,
    )

    resolved = resolve_and_persist_order_business_date(session, order.id)
    session.flush()

    result.check(
        "resolve_and_persist_order_business_date computes and persists Order.business_date "
        "(2026-08-30, via Settlement Time converted to Location-local time before cutoff evaluation)",
        resolved == date(2026, 8, 30) and order.business_date == date(2026, 8, 30),
    )

    reloaded = session.get(m.Order, order.id)
    result.check(
        "the persisted business_date is actually re-readable from the database",
        reloaded is not None and reloaded.business_date == date(2026, 8, 30),
    )


# ---------------------------------------------------------------------------
# G. Missing required inputs never invent a Business Date.
# ---------------------------------------------------------------------------


def _test_missing_inputs_never_invent_a_date(session: Session, result: ValidationResult) -> None:
    # No Location timezone.
    location_no_tz = _make_merchant_location(
        session, "No Timezone", timezone_name=None, cutoff=time(4, 0),
    )
    order_no_tz = _make_order_with_successful_payment(
        session, location_id=location_no_tz.id, payment_created_at=datetime(2026, 8, 31, 3, 0, tzinfo=UTC),
    )
    resolved_no_tz = resolve_and_persist_order_business_date(session, order_no_tz.id)
    result.check(
        "a missing Location.timezone never invents a Business Date (returns None, business_date stays NULL)",
        resolved_no_tz is None and order_no_tz.business_date is None,
    )

    # No Location operating_day_cutoff_time.
    location_no_cutoff = _make_merchant_location(
        session, "No Cutoff", timezone_name="America/New_York", cutoff=None,
    )
    order_no_cutoff = _make_order_with_successful_payment(
        session, location_id=location_no_cutoff.id,
        payment_created_at=datetime(2026, 8, 31, 3, 0, tzinfo=UTC),
    )
    resolved_no_cutoff = resolve_and_persist_order_business_date(session, order_no_cutoff.id)
    result.check(
        "a missing Location.operating_day_cutoff_time never invents a Business Date",
        resolved_no_cutoff is None and order_no_cutoff.business_date is None,
    )

    # No successful Payment at all (no Settlement Time).
    location_ok = _make_merchant_location(
        session, "No Settlement Time", timezone_name="America/New_York", cutoff=time(4, 0),
    )
    order_no_payment = m.Order(location_id=location_ok.id, created_at=datetime(2026, 8, 31, tzinfo=UTC))
    session.add(order_no_payment)
    session.flush()
    resolved_no_payment = resolve_and_persist_order_business_date(session, order_no_payment.id)
    result.check(
        "an Order with no successful Payment (no Settlement Time) never invents a Business Date",
        resolved_no_payment is None and order_no_payment.business_date is None,
    )
