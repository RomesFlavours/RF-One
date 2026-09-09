"""Business Date — canonical Order/Sales-owned fact (Business Date
Foundation task, Product Owner decision).

Business Date (operating day) is owned by Sales/Order — never by Tips,
Compensation, or any other Domain (`01 Domains/Business Domain/Restaurant/Sales/
Restaurant Sales Model.md` §6a, "Cross-domain use"). This module is the
single canonical place that computes it; every consuming Domain reuses
`Order.business_date` (once persisted) or, where a fresh derivation is
genuinely needed, the pure `derive_business_date` function below — no
Domain may independently invent a competing business-date rule.

The rule (Sales Model §6a, and `Location.operating_day_cutoff_time`'s own
docstring in `models.py`): `operating_day_cutoff_time` is a time-of-day,
evaluated in the Location's own `timezone`. An event at or after that
time-of-day is attributed to that same calendar day; an event before that
time-of-day is attributed to the PREVIOUS calendar day (the still-open
"night before"). This module's derivation was cross-checked against Sales
Model §6a's own worked example (Order opens Aug 30 23:45, Payment occurs
Aug 31 00:30, Business Date = Aug 30 for both) and against ordinary
late-night "operating day" semantics; see the corrected note on
`Location.operating_day_cutoff_time` for why an earlier wording of this
rule (now fixed) had the cutoff direction inverted.

Settlement Time itself is NOT redefined here — it is reused exactly as
already defined by `technical.connectors.clover.acquisition.
get_order_settlement_time` (the timestamp of the Order's last successful
Payment), which already documents itself as a generic derived fact usable
by any Domain, not a Tips-owned concern.

Business Date is computed ONCE and persisted on `Order.business_date`
(never recomputed at read time, never versioned/history-tracked) — a
recalculation, where legitimately needed before any future fiscal locking,
simply replaces the current value; see `resolve_and_persist_order_business_date`.
No Business Date is ever invented when a required input cannot be resolved
— see "Missing inputs" below.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from . import models as m
from .technical.connectors.clover.acquisition import get_order_settlement_time

UTC = timezone.utc


def _as_aware_utc(value: datetime) -> datetime:
    """SQLite does not reliably round-trip `tzinfo` on a
    `DateTime(timezone=True)` column once an ORM object is reloaded from a
    real query (see `payroll_calculation/engine.py`'s `_as_naive_utc` for
    the same, already-documented caveat in this codebase). This schema's
    own convention (models.py module docstring) is that persisted datetimes
    are already normalized to UTC by the application/ingestion layer before
    persisting, whether or not `tzinfo` survives the round trip — so a
    naive value here is treated as already-UTC, never converted."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def derive_business_date(
    *, settlement_time: datetime, location_timezone: str, operating_day_cutoff_time: time,
) -> date:
    """The pure Business Date derivation rule (Sales Model §6a) — no
    database access, no Order/Location lookup, so it can be reused
    identically by real-time persistence, a future dedicated backfill, and
    tests alike (never a second, competing implementation).

    `settlement_time` must already be timezone-aware (or naive-and-known-UTC
    per this schema's convention) — callers resolving it from
    `get_order_settlement_time` should pass it through `_as_aware_utc`
    first, as `resolve_and_persist_order_business_date` does.
    """
    aware = _as_aware_utc(settlement_time)
    local_dt = aware.astimezone(ZoneInfo(location_timezone))
    if local_dt.time() < operating_day_cutoff_time:
        return local_dt.date() - timedelta(days=1)
    return local_dt.date()


def resolve_and_persist_order_business_date(session: Session, order_id: int) -> date | None:
    """Resolves the canonical facts for one Order (Settlement Time via the
    existing, reused `get_order_settlement_time`; Location via
    `Order.location_id`; the Location's `timezone`/`operating_day_cutoff_time`),
    computes Business Date, and persists it on `Order.business_date` —
    replacing any previously-computed value, never creating history (Sales
    Model §6a: persisted at determination time, not versioned).

    Missing inputs (Sales Model §6a; task-level "Missing inputs" rule):
    if the Order has no Settlement Time (no successful Payment yet), no
    resolvable Location, no Location `timezone`, or no Location
    `operating_day_cutoff_time`, this function does NOT invent a Business
    Date — it leaves `Order.business_date` as it already is (`None` for an
    Order that has never had one resolved) and returns `None`. It never
    falls back to a calendar date, a UTC date, a midnight cutoff, or any
    other guess.

    Does not commit — matches this codebase's existing convention
    (`payroll_calculation/engine.py`, `tips/distribution_engine.py`): the
    caller decides when to commit."""

    order = session.get(m.Order, order_id)
    if order is None:
        return None

    settlement_time = get_order_settlement_time(session, order_id)
    if settlement_time is None:
        return None

    location = session.get(m.Location, order.location_id)
    if location is None or not location.timezone or location.operating_day_cutoff_time is None:
        return None

    business_date = derive_business_date(
        settlement_time=settlement_time,
        location_timezone=location.timezone,
        operating_day_cutoff_time=location.operating_day_cutoff_time,
    )
    order.business_date = business_date
    return business_date
