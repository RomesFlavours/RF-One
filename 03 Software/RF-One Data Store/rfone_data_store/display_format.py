"""How RF-One shows times and people to a person — display rules only.

RF-One UI Rules (`03 Software/Shared UI/UI Rules.md`) §1 and §2, in ONE place
so every RF-One app (RF-One Web, Tips) formats the same way instead of each
keeping its own copy:

  * a time is shown in the LOCAL time of the Location the fact belongs to
    (its IANA `Location.timezone`, e.g. Winter Park -> America/New_York),
    never in UTC. UTC stays the storage and computation format; nothing
    here changes a stored value;
  * an employee is shown, in operational displays, as SURNAME + first-name
    INITIAL ("Tatiana Ceban" -> "Ceban T."), never as a technical id. The
    full name and every identifier stay in the database untouched.

Deliberately free of any web-framework import: the apps register these as
template filters.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UTC = timezone.utc
DEFAULT_FORMAT = "%Y-%m-%d %H:%M"


def _zone(tz_name: str | None) -> ZoneInfo | None:
    if not tz_name:
        return None
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def to_local(value: datetime | None, tz_name: str | None) -> datetime | None:
    """`value` as a wall-clock time at the Location.

    A naive datetime is a stored RF-One timestamp, which is always UTC
    (SQLite hands them back without tzinfo). A Location with no usable
    timezone yields the UTC instant unchanged — RF-One never guesses a
    timezone; `zone_label` then says "UTC" so the reader is not misled."""
    if value is None:
        return None
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    zone = _zone(tz_name)
    return aware.astimezone(zone if zone is not None else UTC)


def local_datetime(value: datetime | None, tz_name: str | None, fmt: str = DEFAULT_FORMAT,
                   *, with_zone: bool = False, empty: str = "-") -> str:
    """Format `value` in the Location's local time. `with_zone` appends the
    zone abbreviation (EDT/EST); use it where a single time stands alone,
    not on every table row."""
    local = to_local(value, tz_name)
    if local is None:
        return empty
    text = local.strftime(fmt)
    return f"{text} {local.tzname()}" if with_zone else text


def zone_label(tz_name: str | None) -> str:
    """The zone a page's times are in, for one short note per page
    ("America/New_York"), or "UTC" when the Location has none configured."""
    return tz_name if _zone(tz_name) is not None else "UTC"


def employee_short_name(full_name: str | None, *, empty: str = "-") -> str:
    """SURNAME + first-name initial: "Tatiana Ceban" -> "Ceban T.".

    Clover stores one free-text name, first name first. The surname is
    everything after the first word, so a compound surname stays whole
    ("Maria De Luca" -> "De Luca M."). A single word is shown as it is."""
    parts = (full_name or "").split()
    if not parts:
        return empty
    if len(parts) == 1:
        return parts[0]
    return f"{' '.join(parts[1:])} {parts[0][0].upper()}."


def employee_first_name_initial(full_name: str | None, *, empty: str = "-") -> str:
    """FIRST NAME + surname initial: "Tatiana Ceban" -> "Tatiana C.".

    Used only where the Product Owner asked for it explicitly (Compensation
    Period Summary, COMPENSATION_PERIOD_SUMMARY_001); everywhere else the
    standing rule is `employee_short_name`. Same parsing: the first word is
    the first name, the rest is the surname ("Maria De Luca" -> "Maria D.").
    A single word is shown as it is."""
    parts = (full_name or "").split()
    if not parts:
        return empty
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} {parts[1][0].upper()}."
