"""Supplier + Source Format training foundation.

`01 Domains/Shared Domains/Purchased/README.md`, "Source/format validation
and training" already describes the target concept: Purchased must
validate the combination **Supplier + acquisition method/document format**,
not "the Supplier" in the abstract, and a training period (the first N
documents, an accuracy threshold) may eventually make a given
Supplier+Format combination "trusted" — but explicitly leaves N and the
threshold as a future, configurable concern, not fixed by this or any
prior task.

This module is that foundation, and *only* that foundation: a place to
durably record, per (Supplier name, source format), how many documents
have been observed and with what NORMALIZED/HUMAN outcome, plus a
`trust_state` column for a future promotion mechanism to use. It does
**not**:

- auto-validate any Supplier — `trust_state` is always written as
  `UNTRAINED` by `record_observation()`; nothing in this module ever
  promotes it, and no caller reads it back to influence a document's own
  NORMALIZED/HUMAN result (see `purchased_bridge.py`'s own validation,
  which never queries this store);
- define a universal N or accuracy threshold — those remain a future,
  per-format/per-Supplier configuration decision;
- implement automatic promotion — this is observation/bookkeeping only.

A plain local SQLite file, its own and separate from `rfone_data_store`'s
canonical database — the same "acquisition/quality-tracking metadata, not
a Purchased fact" boundary already drawn by `mailbox_acquisition/
acquisition_store.py`, so no Alembic migration is needed for this
foundation.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DEFAULT_DB_PATH = os.path.join(DATA_DIR, "supplier_format_training.db")

TRUST_STATE_UNTRAINED = "UNTRAINED"  # the only trust_state value this module itself ever writes

_SCHEMA = """
CREATE TABLE IF NOT EXISTS supplier_format_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_name TEXT NOT NULL,
    source_format TEXT NOT NULL,
    reviewed_count INTEGER NOT NULL DEFAULT 0,
    normalized_count INTEGER NOT NULL DEFAULT 0,
    human_count INTEGER NOT NULL DEFAULT 0,
    trust_state TEXT NOT NULL DEFAULT 'UNTRAINED',
    last_layout_signature TEXT,
    last_seen_at TEXT NOT NULL,
    UNIQUE (supplier_name, source_format)
);
"""


@dataclass(frozen=True)
class SupplierFormatObservation:
    id: int
    supplier_name: str
    source_format: str
    reviewed_count: int
    normalized_count: int
    human_count: int
    trust_state: str
    last_layout_signature: Optional[str]
    last_seen_at: str


def layout_signature(*, supplier_found: bool, date_found: bool, number_found: bool, total_found: bool, line_count: int) -> str:
    """A deliberately coarse "shape" fingerprint of what a document's
    extraction looked like — NOT real layout/version detection, just enough
    to notice "this looks like a different pattern than usual" in a future
    review UI. Illustrative only; a future task may replace this with
    something more meaningful once real training data exists."""

    return f"S{int(supplier_found)}D{int(date_found)}N{int(number_found)}T{int(total_found)}-L{line_count}"


class SupplierFormatTrainingStore:
    """One SQLite connection per instance — same simplicity convention as
    `mailbox_acquisition/acquisition_store.py`."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        with self._conn:
            self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def record_observation(
        self,
        *,
        supplier_name: str,
        source_format: str,
        was_normalized: bool,
        signature: str | None = None,
    ) -> SupplierFormatObservation:
        """Records one more observed document for this (Supplier, Source
        Format) pair. Always leaves `trust_state` at `UNTRAINED` — this
        function never promotes anything (see module docstring)."""

        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO supplier_format_observations "
                "(supplier_name, source_format, reviewed_count, normalized_count, human_count, "
                " trust_state, last_layout_signature, last_seen_at) "
                "VALUES (?, ?, 1, ?, ?, ?, ?, ?) "
                "ON CONFLICT(supplier_name, source_format) DO UPDATE SET "
                "reviewed_count = reviewed_count + 1, "
                "normalized_count = normalized_count + excluded.normalized_count, "
                "human_count = human_count + excluded.human_count, "
                "last_layout_signature = excluded.last_layout_signature, "
                "last_seen_at = excluded.last_seen_at",
                (
                    supplier_name,
                    source_format,
                    1 if was_normalized else 0,
                    0 if was_normalized else 1,
                    TRUST_STATE_UNTRAINED,
                    signature,
                    now,
                ),
            )
        return self.get(supplier_name, source_format)

    def get(self, supplier_name: str, source_format: str) -> SupplierFormatObservation | None:
        row = self._conn.execute(
            "SELECT * FROM supplier_format_observations WHERE supplier_name = ? AND source_format = ?",
            (supplier_name, source_format),
        ).fetchone()
        return SupplierFormatObservation(**dict(row)) if row else None

    def list_all(self) -> list[SupplierFormatObservation]:
        rows = self._conn.execute(
            "SELECT * FROM supplier_format_observations ORDER BY supplier_name, source_format"
        ).fetchall()
        return [SupplierFormatObservation(**dict(row)) for row in rows]
