"""Move the Conoscenza register from the first-release local SQLite file to
PostgreSQL (AWS RDS, schema `conoscenza`), preserving every row and id.

- `export_v1_sqlite(path)` reads the first-release file (read-only) and
  returns all tables in the current model, adding the attributions the
  first release did not store separately:
  * the only person is the owner, Pino (every first-release credential was
    his);
  * `contributed_by_person_id` = Pino for entries recorded through his
    Claude/Codex sessions, UNKNOWN (NULL) for historical imports;
  * `decided_by_person_id` = Pino only where the decision is documented as
    his (`decided_by = 'Pino'`) and the entry is a decision/correction.
- `load(engine, data)` inserts everything with the original ids into an
  EMPTY register and realigns the PostgreSQL sequences.
- `manifest(data)` / `read_all(engine)` give per-table row counts and a
  SHA-256 over the normalized rows, computed the same way on both sides.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import Engine, func, insert, select, text

from .models import ALL_TABLES

TABLE_ORDER = [t.name for t in ALL_TABLES]
_TABLES = {t.name: t for t in ALL_TABLES}


def _iso_dt(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace(" ", "T"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _norm(column, value):
    if value is None:
        return None
    type_name = type(column.type).__name__
    if type_name == "DateTime":
        return _iso_dt(value)
    if type_name == "Date":
        return value.isoformat() if isinstance(value, date) else str(value)
    if type_name == "Boolean":
        return bool(value)
    if type_name == "Integer":
        return int(value)
    return value


def normalize_rows(table_name: str, rows: list[dict]) -> list[dict]:
    table = _TABLES[table_name]
    out = [{c.name: _norm(c, row.get(c.name)) for c in table.columns} for row in rows]
    return sorted(out, key=lambda r: r["id"])


def manifest(data: dict[str, list[dict]]) -> dict:
    result = {}
    for name in TABLE_ORDER:
        rows = normalize_rows(name, data.get(name, []))
        digest = hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        result[name] = {"righe": len(rows), "sha256": digest}
    return result


def export_v1_sqlite(path: Path, owner_name: str = "Pino") -> dict[str, list[dict]]:
    con = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row

    def rows(table):
        return [dict(r) for r in con.execute(f"SELECT * FROM {table} ORDER BY id")]

    clients = rows("conoscenza_clients")
    created = min((c["created_at"] for c in clients), default=datetime.now(UTC).isoformat())
    data: dict[str, list[dict]] = {
        "conoscenza_people": [{"id": 1, "name": owner_name, "is_owner": True, "status": "ACTIVE",
                               "created_at": created}],
        "conoscenza_access_rules": [],
        "conoscenza_clients": [{**c, "person_id": 1} for c in clients],
        "conoscenza_approvals": [], "conoscenza_oauth_clients": [], "conoscenza_oauth_grants": [],
    }
    items = []
    for item in rows("conoscenza_items"):
        item = dict(item)
        item.setdefault("contributed_by_person_id", 1 if item["recorded_by"] in ("CLAUDE", "CODEX") else None)
        documented = (item["kind"] != "WORK_UPDATE" and item["authority"] == "PO_EXPLICIT"
                      and (item.get("decided_by") or "").strip().lower() == owner_name.lower())
        item.setdefault("decided_by_person_id", 1 if documented else None)
        items.append(item)
    data["conoscenza_items"] = items
    data["conoscenza_evidence"] = rows("conoscenza_evidence")
    data["conoscenza_links"] = rows("conoscenza_links")
    data["conoscenza_access_log"] = [{**a, "person_id": a.get("person_id") or 1} for a in rows("conoscenza_access_log")]
    con.close()
    return {name: normalize_rows(name, data[name]) for name in TABLE_ORDER}


def read_all(engine: Engine) -> dict[str, list[dict]]:
    with engine.connect() as conn:
        return {name: normalize_rows(name, [dict(r._mapping) for r in conn.execute(select(_TABLES[name]))])
                for name in TABLE_ORDER}


def _db_value(column, value):
    if value is None:
        return None
    type_name = type(column.type).__name__
    if type_name == "DateTime":
        return datetime.fromisoformat(value)
    if type_name == "Date":
        return date.fromisoformat(value)
    return value


def load(engine: Engine, data: dict[str, list[dict]]) -> None:
    """Insert all rows with their ids into an EMPTY register."""
    with engine.begin() as conn:
        for name in TABLE_ORDER:
            count = conn.execute(select(func.count()).select_from(_TABLES[name])).scalar_one()
            if count:
                raise RuntimeError(f"Destination table {name} is not empty ({count} rows): refusing to import.")
        for name in TABLE_ORDER:
            table = _TABLES[name]
            rows = [{c.name: _db_value(c, r.get(c.name)) for c in table.columns} for r in data.get(name, [])]
            if rows:
                conn.execute(insert(table), rows)
        if engine.dialect.name == "postgresql":
            for name in TABLE_ORDER:
                conn.execute(text(
                    f"SELECT setval(pg_get_serial_sequence('{name}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {name}), 0) + 1, false)"))
