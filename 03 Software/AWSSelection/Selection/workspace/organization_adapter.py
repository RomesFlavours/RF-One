"""Company information for drafting requirements — read-only.

Reads, from the same RF-One database Selection uses, only facts actually
recorded there (restaurant, locations, configured restaurant roles) and
returns each with its source. Anything not found is reported as missing —
never filled in. Replacing this module with a call to a future Organization
service changes nothing else in Selection.
"""

from __future__ import annotations

from sqlalchemy import select

from rfone_data_store import models as m

EXPECTED = ("restaurant", "location and address", "location time zone", "configured roles and operating areas")


def get_context(session, location_hint: str | None) -> dict:
    """{"available": bool, "source": str, "facts": [str], "missing": [str], "timezone": str|None}"""
    facts, missing, timezone = [], [], None
    restaurants = session.scalars(select(m.Restaurant).order_by(m.Restaurant.id)).all()
    if restaurants:
        facts += [f"Restaurant: {r.name}" for r in restaurants if r.name]
        timezone = next((r.default_timezone for r in restaurants if r.default_timezone), None)
    else:
        missing.append("restaurant")

    locations = session.scalars(select(m.Location).where(m.Location.active.is_(True)).order_by(m.Location.id)).all()
    hint = (location_hint or "").strip().lower()
    matching = [loc for loc in locations if hint and hint in (loc.name or "").lower()]
    for loc in matching or locations:
        facts.append("Location: " + ", ".join(f"{k}={v}" for k, v in (("name", loc.name), ("timezone", loc.timezone),
                                                                  ("currency", loc.currency)) if v))
        timezone = timezone or loc.timezone
    if not locations:
        missing += ["location and address", "location time zone"]

    roles = sorted({r.name for r in session.scalars(select(m.RestaurantRole)).all()
                    if r.name and r.active is not False})
    if roles:
        facts.append("Configured roles: " + ", ".join(roles))
    else:
        missing.append("configured roles and operating areas")
    return {"available": bool(facts), "source": "RF-One Data Store (read only)", "facts": facts,
            "missing": missing, "timezone": timezone}
