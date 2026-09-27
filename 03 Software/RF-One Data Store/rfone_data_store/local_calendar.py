"""A calendar day chosen by a person, as the Location's LOCAL civil day.

Product Owner decision (UI_OFFICIAL_ENTRY_AND_LOCAL_DAYS_001, 2026-09-27):
a date a person picks for a Clover Historical Backfill, or to filter the
imported Clover data, means the Location's own civil day — Winter Park:
"20 Sept" is 20 Sept 00:00:00 through 23:59:59 America/New_York — never a
UTC day. RF-One converts that to UTC instants internally; UTC stays a
storage detail.

This is NOT the Tips Business Date (`business_date.py`): that is the
Location's configured operating day (currently 04:00 -> 04:00). The
operating-day cutoff is deliberately not used here.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UTC = timezone.utc
END_OF_DAY = time(23, 59, 59)


class LocationTimezoneMissingError(ValueError):
    """The Location has no usable timezone. RF-One never guesses one."""


def _zone(tz_name: str | None) -> ZoneInfo:
    try:
        if tz_name:
            return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        pass
    raise LocationTimezoneMissingError(
        "This Location has no timezone configured, so its local days cannot be determined. "
        "Ask an RF-One administrator to set the Location's timezone."
    )


def local_days_to_utc(first_day: date, last_day: date, tz_name: str | None) -> tuple[datetime, datetime]:
    """[first_day 00:00:00, last_day 23:59:59] local, as UTC instants.
    The zone's own rules decide the UTC offset of each end, so a period
    crossing an EDT/EST change is converted correctly at both ends."""
    zone = _zone(tz_name)
    start = datetime.combine(first_day, time.min, tzinfo=zone)
    end = datetime.combine(last_day, END_OF_DAY, tzinfo=zone)
    return start.astimezone(UTC), end.astimezone(UTC)


def parse_day(value: str | None) -> date | None:
    """A `YYYY-MM-DD` form value, or `None`."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None
