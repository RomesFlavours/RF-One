#!/usr/bin/env python
"""UI_OFFICIAL_ENTRY_AND_LOCAL_DAYS_001 — pure rules, no database.

Proves:
  A. a chosen day is the Location's LOCAL civil day: 20-26 Sept 2026 in
     Winter Park is 20 Sept 00:00 EDT (04:00Z) -> 26 Sept 23:59:59 EDT
     (27 Sept 03:59:59Z);
  B. the EDT/EST change is decided by the zone: 1-2 Nov 2026 runs from
     00:00 EDT (04:00Z) to 23:59:59 EST (3 Nov 04:59:59Z); a winter day is
     05:00Z -> 04:59:59Z;
  C. the Tips operating-day cutoff (04:00) plays no part;
  D. a Location without a timezone is refused, never guessed;
  E. the official-entry redirect: only when configured, only GET/HEAD,
     never for requests CloudFront forwarded, and keeps path and query
     (with the /tips prefix for Tips).

Usage:
    python test_local_days_and_official_entry.py
"""

from __future__ import annotations

import os
import sys
from datetime import date, datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from rfone_data_store import local_calendar, public_entry  # noqa: E402

UTC = timezone.utc
NY = "America/New_York"


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    start, end = local_calendar.local_days_to_utc(date(2026, 9, 20), date(2026, 9, 26), NY)
    check("A: From 20 Sept = 20 Sept 00:00 EDT = 04:00Z", start == datetime(2026, 9, 20, 4, 0, tzinfo=UTC), str(start))
    check("A: Through 26 Sept = 26 Sept 23:59:59 EDT = 27 Sept 03:59:59Z",
          end == datetime(2026, 9, 27, 3, 59, 59, tzinfo=UTC), str(end))

    start, end = local_calendar.local_days_to_utc(date(2026, 11, 1), date(2026, 11, 2), NY)
    check("B: a period across the EDT->EST change starts at 04:00Z (EDT)",
          start == datetime(2026, 11, 1, 4, 0, tzinfo=UTC), str(start))
    check("B: ... and ends at 04:59:59Z (EST)", end == datetime(2026, 11, 3, 4, 59, 59, tzinfo=UTC), str(end))
    start, end = local_calendar.local_days_to_utc(date(2026, 1, 15), date(2026, 1, 15), NY)
    check("B: a winter day is 05:00Z -> 04:59:59Z next day",
          start == datetime(2026, 1, 15, 5, 0, tzinfo=UTC) and end == datetime(2026, 1, 16, 4, 59, 59, tzinfo=UTC))

    check("C: the civil day starts at local midnight, not at the 04:00 Tips cutoff",
          local_calendar.local_days_to_utc(date(2026, 9, 20), date(2026, 9, 20), NY)[0].astimezone(
              __import__("zoneinfo").ZoneInfo(NY)).hour == 0)

    for tz in (None, "", "Not/AZone"):
        try:
            local_calendar.local_days_to_utc(date(2026, 9, 20), date(2026, 9, 20), tz)
            refused = False
        except local_calendar.LocationTimezoneMissingError:
            refused = True
        check(f"D: timezone {tz!r} is refused, never guessed", refused)
    check("D: form values parse as days; garbage does not",
          local_calendar.parse_day("2026-09-20") == date(2026, 9, 20) and local_calendar.parse_day("20/09") is None)

    os.environ.pop(public_entry.ENV_VAR, None)
    check("E: not configured -> never redirects", public_entry.official_redirect("GET", {}, "/login?") is None)
    os.environ[public_entry.ENV_VAR] = "https://rfone.romesflavours.com"
    check("E: a direct GET goes to the same page on the official address",
          public_entry.official_redirect("GET", {}, "/clover-acquisition?from=tips")
          == "https://rfone.romesflavours.com/clover-acquisition?from=tips")
    check("E: a bare path loses Flask's trailing '?'",
          public_entry.official_redirect("GET", {}, "/?") == "https://rfone.romesflavours.com/")
    check("E: Tips keeps its /tips prefix",
          public_entry.official_redirect("GET", {}, "/distribution-rules?", prefix="/tips")
          == "https://rfone.romesflavours.com/tips/distribution-rules")
    check("E: a request forwarded by CloudFront is served, not redirected",
          public_entry.official_redirect("GET", {"X-RFOne-Entry": "cloudfront"}, "/") is None)
    check("E: a POST is never redirected (its body would be lost)",
          public_entry.official_redirect("POST", {}, "/login?") is None)
    os.environ[public_entry.ENV_VAR] = "http://rfone.romesflavours.com"
    check("E: a non-HTTPS official address is refused as configuration",
          public_entry.official_redirect("GET", {}, "/?") is None)
    os.environ.pop(public_entry.ENV_VAR, None)

    print(f"Local days and official entry tests: {'SUCCESS' if not failed else 'FAILURE'} "
          f"({len(passed)} passed, {len(failed)} failed)")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
