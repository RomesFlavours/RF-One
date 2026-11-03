"""Company information for drafting requirements — read-only, isolated.

Today RF-One has no Organization service the prototype can call, and the
central AI service does not exist yet. This adapter reads, strictly
read-only, an RF-One Data Store SQLite file named by
`RFONE_SELECTION_PROTOTYPE_ORG_DB` (if any) and returns only facts actually
found there, each with its source. Anything not found is reported as
missing — never filled in. Replacing this module with a call to the future
Organization service changes nothing else in the prototype.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

ENV_VAR = "RFONE_SELECTION_PROTOTYPE_ORG_DB"
EXPECTED = ("ristorante", "sede e indirizzo", "fuso orario della sede", "ruoli e aree operative configurati")


def _rows(conn, sql: str) -> list[sqlite3.Row]:
    try:
        return list(conn.execute(sql))
    except sqlite3.Error:
        return []


def get_context(location_hint: str | None) -> dict:
    """{"available": bool, "source": str, "facts": [str], "missing": [str], "timezone": str|None}"""
    path = (os.environ.get(ENV_VAR) or "").strip()
    if not path:
        return {"available": False, "source": "Organization non collegata al prototipo", "facts": [],
                "missing": list(EXPECTED), "timezone": None}
    if not Path(path).is_file():
        return {"available": False, "source": f"Archivio Organization non trovato ({path})", "facts": [],
                "missing": list(EXPECTED), "timezone": None}

    conn = sqlite3.connect(Path(path).as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        facts, missing, timezone = [], [], None
        restaurants = _rows(conn, "select * from restaurants")
        if restaurants:
            facts += [f"Ristorante: {r['name']}" for r in restaurants if r["name"]]
        else:
            missing.append("ristorante")

        locations = _rows(conn, "select * from locations")
        hint = (location_hint or "").strip().lower()
        matching = [l for l in locations if hint and hint in " ".join(str(v) for v in dict(l).values() if v).lower()]
        for loc in matching or locations:
            values = {k: v for k, v in dict(loc).items() if v not in (None, "") and not k.endswith("_id")
                      and k not in ("id", "created_at", "updated_at")}
            facts.append("Sede: " + ", ".join(f"{k}={v}" for k, v in values.items()))
            timezone = timezone or values.get("timezone")
        if not locations:
            missing += ["sede e indirizzo", "fuso orario della sede"]

        roles = _rows(conn, "select * from restaurant_roles")
        if roles:
            names = sorted({str(r["name"]) for r in roles if "name" in r.keys() and r["name"]})
            if names:
                facts.append("Ruoli configurati: " + ", ".join(names))
        else:
            missing.append("ruoli e aree operative configurati")
    finally:
        conn.close()
    return {"available": bool(facts), "source": f"RF-One Data Store in sola lettura ({Path(path).name})",
            "facts": facts, "missing": missing, "timezone": timezone}
