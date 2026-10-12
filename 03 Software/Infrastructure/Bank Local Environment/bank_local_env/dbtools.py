"""SQLite tools of the local Bank environment: consistent snapshots,
integrity, fingerprints and content comparison.

Never writes to a source database: sources are opened read-only, and a
snapshot is taken with SQLite's online backup API (consistent even while a
server holds the database open), never by copying the file.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

# The tables that carry the Bank work a person does — compared first and
# shown by name. Every other table is still compared, as "other tables".
KEY_TABLES = (
    ("financial_transactions", "movements"),
    ("bank_transaction_explanations", "WHO/WHY decisions"),
    ("bank_transaction_allocations", "For Whom allocations"),
    ("bank_occurrences", "WHO catalog"),
    ("bank_transaction_reasons", "WHY catalog"),
    ("bank_occurrence_reason_associations", "WHO → possible WHY"),
    ("bank_recognition_rules", "WHO Rules"),
    ("bank_general_rules", "General Rules"),
    ("bank_reconciliation_standards", "Reconciliation Standards"),
    ("payment_instruments", "Sources"),
    ("bank_ai_rules", "AI rules (operative)"),
    ("bank_ai_rule_versions", "AI rule versions"),
    ("bank_ai_rule_interpretations", "AI rule interpretations"),
    ("bank_ai_rule_drafts", "AI rule drafts"),
    ("bank_ai_rule_previews", "AI rule previews"),
    ("bank_ai_rule_applications", "AI rule applications"),
    ("bank_ai_instructions", "AI general instructions"),
    ("financial_transaction_matches", "internal transfer matches"),
)


def open_readonly(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)


def snapshot(source: Path, target: Path) -> None:
    """A consistent copy of `source` at `target` through the SQLite backup
    API. `target` must not exist."""
    target = Path(target)
    if target.exists():
        raise FileExistsError(f"{target} already exists")
    target.parent.mkdir(parents=True, exist_ok=True)
    src = open_readonly(source)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def integrity(path: Path) -> str:
    con = open_readonly(path)
    try:
        return con.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        con.close()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def revision(path: Path) -> str | None:
    con = open_readonly(path)
    try:
        row = con.execute("SELECT version_num FROM alembic_version").fetchone()
        return row[0] if row else None
    except sqlite3.Error:
        return None
    finally:
        con.close()


@dataclass
class TableContent:
    rows: dict = field(default_factory=dict)      # primary key -> row hash
    count: int = 0
    keyed: bool = True


def _tables(con: sqlite3.Connection) -> list[str]:
    return [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]


def _columns(con: sqlite3.Connection, table: str) -> tuple[list[str], list[str]]:
    info = con.execute(f'PRAGMA table_info("{table}")').fetchall()
    columns = [r[1] for r in info]
    pk = [r[1] for r in sorted(info, key=lambda r: r[5]) if r[5]]
    return columns, pk


def content(path: Path) -> dict[str, TableContent]:
    """Per table: primary key -> hash of the row (all columns, by name)."""
    con = open_readonly(path)
    try:
        result = {}
        for table in _tables(con):
            columns, pk = _columns(con, table)
            entry = TableContent(keyed=bool(pk))
            cols = ", ".join(f'"{c}"' for c in columns)
            for row in con.execute(f'SELECT {cols} FROM "{table}"'):
                record = dict(zip(columns, row))
                key = tuple(record[c] for c in pk) if pk else json.dumps(record, sort_keys=True, default=str)
                body = json.dumps(record, sort_keys=True, default=lambda v: v.hex() if isinstance(v, bytes) else str(v))
                entry.rows[key] = hashlib.sha1(body.encode("utf-8")).hexdigest()
            entry.count = len(entry.rows)
            result[table] = entry
        return result
    finally:
        con.close()


@dataclass
class TableDiff:
    table: str
    only_a: int
    only_b: int
    changed: int
    count_a: int
    count_b: int

    @property
    def equal(self) -> bool:
        return not (self.only_a or self.only_b or self.changed)


def diff(a: dict[str, TableContent], b: dict[str, TableContent]) -> list[TableDiff]:
    """Row-level differences per table, by primary key and row content."""
    out = []
    for table in sorted(set(a) | set(b)):
        ta, tb = a.get(table, TableContent()), b.get(table, TableContent())
        keys_a, keys_b = set(ta.rows), set(tb.rows)
        changed = sum(1 for k in keys_a & keys_b if ta.rows[k] != tb.rows[k])
        out.append(TableDiff(table, len(keys_a - keys_b), len(keys_b - keys_a), changed, ta.count, tb.count))
    return out


def changed_keys(a: TableContent, b: TableContent) -> tuple[list, list, list]:
    keys_a, keys_b = set(a.rows), set(b.rows)
    return (sorted(keys_a - keys_b, key=str), sorted(keys_b - keys_a, key=str),
            sorted((k for k in keys_a & keys_b if a.rows[k] != b.rows[k]), key=str))
