"""Local acquisition-layer state for the Aruba mailbox.

This is Invoice Intake's OWN bookkeeping — mailbox cursor, source
provenance, and technical dedup/retry state — never the canonical Purchased
schema. Purchased owns the Purchase Fact (`PurchaseDocument`/`PurchaseLine`,
`03 Software/RF-One Data Store/`); this store only owns "did I already see
this exact attachment, and what happened when I tried to deliver it" — the
same acquisition-vs-domain-meaning split already established for Invoice
Intake generally (`01 Domains/Shared Domains/Administration/Invoice Intake/README.md`).

A plain `sqlite3` file (its own, separate from `rfone_data_store`'s
SQLAlchemy/Alembic-managed database) — proportionate to this prototype's
existing simplicity conventions (`excel_store.py`'s own `openpyxl`
workbook), and keeps acquisition state fully decoupled from the canonical
schema (no migration required for this task).
"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

STATUS_PENDING = "PENDING"
STATUS_DELIVERED = "DELIVERED"
STATUS_DUPLICATE_TECHNICAL = "DUPLICATE_TECHNICAL"
STATUS_FAILED = "FAILED"

# A record in one of these statuses is fully resolved -- never reprocessed,
# never retried (Task requirement 4, "Idempotency").
TERMINAL_SUCCESS_STATUSES = {STATUS_DELIVERED, STATUS_DUPLICATE_TECHNICAL}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS mailbox_cursor (
    mailbox TEXT PRIMARY KEY,
    last_uid INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS acquisitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mailbox TEXT NOT NULL,
    message_uid TEXT NOT NULL,
    attachment_index INTEGER NOT NULL,
    attachment_filename TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    sender TEXT,
    subject TEXT,
    received_at TEXT,
    ingested_at TEXT NOT NULL,
    status TEXT NOT NULL,
    stored_path TEXT,
    purchase_document_id INTEGER,
    functional_status TEXT,
    failure_reason TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    UNIQUE (mailbox, message_uid, attachment_index)
);

CREATE INDEX IF NOT EXISTS ix_acquisitions_content_hash ON acquisitions (content_hash);
CREATE INDEX IF NOT EXISTS ix_acquisitions_status ON acquisitions (status);
"""


@dataclass(frozen=True)
class AcquisitionRecord:
    id: int
    mailbox: str
    message_uid: str
    attachment_index: int
    attachment_filename: str
    content_hash: str
    sender: Optional[str]
    subject: Optional[str]
    received_at: Optional[str]
    ingested_at: str
    status: str
    stored_path: Optional[str]
    purchase_document_id: Optional[int]
    functional_status: Optional[str]
    failure_reason: Optional[str]
    retry_count: int


class AcquisitionStore:
    """One SQLite connection per instance. The poller runs single-threaded
    (one poll cycle at a time), so a simple lock around writes — the same
    pattern `excel_store.py` already uses — is sufficient; no connection
    pooling is needed."""

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        with self._conn:
            self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    # -- Cursor -----------------------------------------------------------

    def get_cursor(self, mailbox: str) -> Optional[int]:
        row = self._conn.execute("SELECT last_uid FROM mailbox_cursor WHERE mailbox = ?", (mailbox,)).fetchone()
        return int(row["last_uid"]) if row else None

    def set_cursor(self, mailbox: str, last_uid: int) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO mailbox_cursor (mailbox, last_uid) VALUES (?, ?) "
                "ON CONFLICT(mailbox) DO UPDATE SET last_uid = excluded.last_uid "
                "WHERE excluded.last_uid > mailbox_cursor.last_uid",
                (mailbox, last_uid),
            )

    # -- Identity / dedup lookups ------------------------------------------

    def find_by_identity(self, mailbox: str, message_uid: str, attachment_index: int) -> Optional[AcquisitionRecord]:
        row = self._conn.execute(
            "SELECT * FROM acquisitions WHERE mailbox = ? AND message_uid = ? AND attachment_index = ?",
            (mailbox, message_uid, attachment_index),
        ).fetchone()
        return self._to_record(row) if row else None

    def find_delivered_by_content_hash(self, content_hash: str) -> Optional[AcquisitionRecord]:
        row = self._conn.execute(
            "SELECT * FROM acquisitions WHERE content_hash = ? AND status = ? ORDER BY id ASC LIMIT 1",
            (content_hash, STATUS_DELIVERED),
        ).fetchone()
        return self._to_record(row) if row else None

    def get_retry_message_uids(self, mailbox: str) -> list[str]:
        """Messages with at least one attachment still in FAILED status —
        re-checked every poll cycle regardless of the mailbox cursor, so a
        retryable failure is never silently skipped once the cursor moves
        past it (Task requirement 9, "Failure behavior")."""

        rows = self._conn.execute(
            "SELECT DISTINCT message_uid FROM acquisitions WHERE mailbox = ? AND status = ?",
            (mailbox, STATUS_FAILED),
        ).fetchall()
        return [row["message_uid"] for row in rows]

    # -- Writes -------------------------------------------------------------

    def record_pending(
        self,
        *,
        mailbox: str,
        message_uid: str,
        attachment_index: int,
        attachment_filename: str,
        content_hash: str,
        sender: Optional[str],
        subject: Optional[str],
        received_at: Optional[datetime],
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._conn:
            cursor = self._conn.execute(
                "INSERT INTO acquisitions "
                "(mailbox, message_uid, attachment_index, attachment_filename, content_hash, "
                " sender, subject, received_at, ingested_at, status, retry_count) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
                (
                    mailbox,
                    message_uid,
                    attachment_index,
                    attachment_filename,
                    content_hash,
                    sender,
                    subject,
                    received_at.isoformat() if received_at else None,
                    now,
                    STATUS_PENDING,
                ),
            )
            return int(cursor.lastrowid)

    def mark_delivered(
        self, record_id: int, *, purchase_document_id: int, stored_path: str, functional_status: Optional[str] = None
    ) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE acquisitions SET status = ?, purchase_document_id = ?, stored_path = ?, "
                "functional_status = ?, failure_reason = NULL WHERE id = ?",
                (STATUS_DELIVERED, purchase_document_id, stored_path, functional_status, record_id),
            )

    def mark_duplicate_technical(self, record_id: int, *, purchase_document_id: Optional[int]) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE acquisitions SET status = ?, purchase_document_id = ?, failure_reason = NULL WHERE id = ?",
                (STATUS_DUPLICATE_TECHNICAL, purchase_document_id, record_id),
            )

    def mark_failed(self, record_id: int, *, reason: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE acquisitions SET status = ?, failure_reason = ?, retry_count = retry_count + 1 WHERE id = ?",
                (STATUS_FAILED, reason, record_id),
            )

    # -- Read (admin view) --------------------------------------------------

    def list_recent(self, limit: int = 200) -> list[AcquisitionRecord]:
        rows = self._conn.execute("SELECT * FROM acquisitions ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [self._to_record(row) for row in rows]

    @staticmethod
    def _to_record(row: sqlite3.Row) -> AcquisitionRecord:
        return AcquisitionRecord(**{key: row[key] for key in row.keys()})
