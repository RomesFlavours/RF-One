"""Acquisition of one invoice file, from arrival to Purchase Documents
(INVOICE_SCAN_ACQUISITION_001).

One record per distinct file content (SHA-256 of the bytes), whatever the
channel (manual upload, mailbox):

    RECEIVED  -> file preserved in uploads/, not read yet
    FAILED    -> the file could not be read (service error, unreadable
                 file, a page not processed). NO invoice was created. The
                 original stays preserved and the acquisition can be retried.
    ACQUIRED  -> every invoice found in the file was saved as a Purchase
                 Document (Purchased decides NORMALIZED / HUMAN).

Uploading the exact same file again, or retrying, never creates another
invoice: an ACQUIRED file returns the documents it already produced; a
FAILED file is retried in place (same record, same preserved original);
and each invoice of a file is saved at most once (`acquisition_invoices`
is unique per file and invoice index), so a retry after a partial failure
only saves the invoices still missing.

Everything read is kept with the acquisition (`acquisition_invoices.
extraction_json`): header, lines, the document-level amounts (total,
subtotal, tax, discount, shipping, other charges, amount paid, balance due)
kept distinct, conflicts, unreadable values and — for AWS Textract — the
page, position and confidence of each value. The raw provider response is
preserved next to the original (`uploads/_provider_mirror/`).

This is acquisition state only; the canonical Purchase Fact stays in the
RF-One Data Store (Purchased).
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import document_reader
import purchased_bridge

UTC = timezone.utc
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
MIRROR_DIR = os.path.join(UPLOAD_DIR, "_provider_mirror")
DEFAULT_DB_PATH = os.path.join(BASE_DIR, "data", "document_acquisitions.db")

STATUS_RECEIVED = "RECEIVED"
STATUS_FAILED = "FAILED"
STATUS_ACQUIRED = "ACQUIRED"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS acquisitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_hash TEXT NOT NULL UNIQUE,
    original_filename TEXT NOT NULL,
    stored_name TEXT NOT NULL,
    channel TEXT NOT NULL,
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    method TEXT,
    pages_total INTEGER,
    pages_read TEXT,
    mirror_dir TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS acquisition_invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    acquisition_id INTEGER NOT NULL REFERENCES acquisitions(id),
    invoice_index INTEGER NOT NULL,
    purchase_document_id INTEGER NOT NULL,
    source_reference TEXT NOT NULL,
    extraction_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (acquisition_id, invoice_index)
);
CREATE INDEX IF NOT EXISTS ix_acq_invoices_document ON acquisition_invoices (purchase_document_id);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class AcquisitionOutcome:
    acquisition_id: int
    status: str
    purchase_document_ids: list[int]
    already_acquired: bool = False
    error: Optional[str] = None


class AcquisitionFailed(RuntimeError):
    """Raised by `acquire_saved_file(..., raise_on_failure=True)` (mailbox
    channel): the file is recorded FAILED and can be retried."""


class AcquisitionStore:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def by_hash(self, digest: str) -> Optional[sqlite3.Row]:
        return self._conn.execute("SELECT * FROM acquisitions WHERE content_hash = ?", (digest,)).fetchone()

    def get(self, acquisition_id: int) -> Optional[sqlite3.Row]:
        return self._conn.execute("SELECT * FROM acquisitions WHERE id = ?", (acquisition_id,)).fetchone()

    def create(self, digest: str, original_filename: str, stored_name: str, channel: str) -> int:
        cur = self._conn.execute(
            "INSERT INTO acquisitions (content_hash, original_filename, stored_name, channel, status, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (digest, original_filename, stored_name, channel, STATUS_RECEIVED, _now(), _now()),
        )
        self._conn.commit()
        return cur.lastrowid

    def update(self, acquisition_id: int, **fields: Any) -> None:
        fields["updated_at"] = _now()
        cols = ", ".join(f"{k} = ?" for k in fields)
        self._conn.execute(f"UPDATE acquisitions SET {cols} WHERE id = ?", (*fields.values(), acquisition_id))
        self._conn.commit()

    def invoices(self, acquisition_id: int) -> list[sqlite3.Row]:
        return list(self._conn.execute(
            "SELECT * FROM acquisition_invoices WHERE acquisition_id = ? ORDER BY invoice_index", (acquisition_id,)
        ))

    def add_invoice(self, acquisition_id: int, index: int, document_id: int, source_reference: str, extraction: dict) -> None:
        self._conn.execute(
            "INSERT INTO acquisition_invoices (acquisition_id, invoice_index, purchase_document_id, source_reference,"
            " extraction_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (acquisition_id, index, document_id, source_reference, json.dumps(extraction, default=str), _now()),
        )
        self._conn.commit()

    def invoice_for_document(self, purchase_document_id: int) -> Optional[sqlite3.Row]:
        return self._conn.execute(
            "SELECT i.*, a.original_filename, a.stored_name, a.method, a.pages_total, a.pages_read, a.channel,"
            " a.status AS acquisition_status FROM acquisition_invoices i JOIN acquisitions a ON a.id = i.acquisition_id"
            " WHERE i.purchase_document_id = ? ORDER BY i.id DESC LIMIT 1",
            (purchase_document_id,),
        ).fetchone()

    def list_all(self, limit: int = 200) -> list[sqlite3.Row]:
        return list(self._conn.execute("SELECT * FROM acquisitions ORDER BY id DESC LIMIT ?", (limit,)))


def _document_ids(store: AcquisitionStore, acquisition_id: int) -> list[int]:
    return [row["purchase_document_id"] for row in store.invoices(acquisition_id)]


def _preserve_raw(stored_name: str, read: document_reader.ReadResult) -> Optional[str]:
    if read.method != document_reader.METHOD_TEXTRACT:
        return None
    directory = os.path.join(MIRROR_DIR, f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}_{uuid.uuid4().hex[:8]}")
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, "raw_provider_response.json"), "w", encoding="utf-8") as fh:
        json.dump({"source_file": stored_name, "provider": read.method, **read.raw}, fh, indent=1, default=str)
    return os.path.relpath(directory, UPLOAD_DIR)


def _attempt(store: AcquisitionStore, row: sqlite3.Row, reader: Optional[Callable[[str], document_reader.ReadResult]]) -> AcquisitionOutcome:
    reader = reader or document_reader.read_document
    acquisition_id = row["id"]
    stored_path = os.path.join(UPLOAD_DIR, row["stored_name"])
    store.update(acquisition_id, attempts=row["attempts"] + 1)
    try:
        read = reader(stored_path)
    except Exception as exc:  # noqa: BLE001 — DocumentReadError or anything unexpected: recoverable, no invoice
        message = str(exc) if isinstance(exc, document_reader.DocumentReadError) else \
            f"Unexpected error while reading — {type(exc).__name__}: {exc}"
        store.update(acquisition_id, status=STATUS_FAILED, last_error=message[:1000])
        return AcquisitionOutcome(acquisition_id, STATUS_FAILED, _document_ids(store, acquisition_id), error=message)

    mirror = _preserve_raw(row["stored_name"], read)
    store.update(acquisition_id, method=read.method, pages_total=read.pages_total,
                 pages_read=json.dumps(read.pages_read), mirror_dir=mirror)
    saved = {r["invoice_index"] for r in store.invoices(acquisition_id)}
    several = len(read.invoices) > 1
    try:
        for index, invoice in enumerate(read.invoices, start=1):
            if index in saved:
                continue  # already saved by an earlier attempt: never saved twice
            reference = row["stored_name"] + (f"#{invoice.page_range_label}" if invoice.page_range_label else "")
            note = (f"multi-invoice file: invoice {index} of {len(read.invoices)}, pages {invoice.page_range_label}"
                    if several else None)
            document_id = purchased_bridge.save_read_invoice(invoice, reference, read.method, batch_note=note)
            store.add_invoice(acquisition_id, index, document_id, reference,
                              {**invoice.to_dict(), "method": read.method, "pages_total": read.pages_total})
    except Exception as exc:  # noqa: BLE001 — e.g. database unavailable: retryable, nothing duplicated
        message = f"Saving the read invoice(s) failed — {type(exc).__name__}: {exc}"[:1000]
        store.update(acquisition_id, status=STATUS_FAILED, last_error=message)
        return AcquisitionOutcome(acquisition_id, STATUS_FAILED, _document_ids(store, acquisition_id), error=message)
    store.update(acquisition_id, status=STATUS_ACQUIRED, last_error=None)
    return AcquisitionOutcome(acquisition_id, STATUS_ACQUIRED, _document_ids(store, acquisition_id))


def acquire_bytes(data: bytes, original_filename: str, *, channel: str = "MANUAL_UPLOAD",
                  store: Optional[AcquisitionStore] = None, reader=None) -> AcquisitionOutcome:
    """Manual upload: preserves the file (only if its content is new) and acquires it."""
    own = store is None
    store = store or AcquisitionStore()
    try:
        digest = content_hash(data)
        row = store.by_hash(digest)
        if row is not None and row["status"] == STATUS_ACQUIRED:
            return AcquisitionOutcome(row["id"], STATUS_ACQUIRED, _document_ids(store, row["id"]), already_acquired=True)
        if row is None:
            os.makedirs(UPLOAD_DIR, exist_ok=True)
            safe_name = os.path.basename(original_filename.replace("\\", "/")) or "document"
            stored_name = f"{uuid.uuid4().hex[:8]}_{safe_name}"
            with open(os.path.join(UPLOAD_DIR, stored_name), "wb") as fh:
                fh.write(data)
            store.create(digest, original_filename, stored_name, channel)
            row = store.by_hash(digest)
        return _attempt(store, row, reader)
    finally:
        if own:
            store.close()


def acquire_saved_file(saved_path: str, original_filename: str, *, channel: str = "MAILBOX",
                       store: Optional[AcquisitionStore] = None, reader=None,
                       raise_on_failure: bool = True) -> AcquisitionOutcome:
    """Mailbox channel: the attachment is already saved in uploads/."""
    own = store is None
    store = store or AcquisitionStore()
    try:
        with open(saved_path, "rb") as fh:
            digest = content_hash(fh.read())
        row = store.by_hash(digest)
        if row is not None and row["status"] == STATUS_ACQUIRED:
            return AcquisitionOutcome(row["id"], STATUS_ACQUIRED, _document_ids(store, row["id"]), already_acquired=True)
        if row is None:
            store.create(digest, original_filename, os.path.basename(saved_path), channel)
            row = store.by_hash(digest)
        outcome = _attempt(store, row, reader)
        if outcome.status == STATUS_FAILED and raise_on_failure:
            raise AcquisitionFailed(outcome.error or "acquisition failed")
        return outcome
    finally:
        if own:
            store.close()


def retry(acquisition_id: int, *, store: Optional[AcquisitionStore] = None,
          reader=None) -> AcquisitionOutcome:
    own = store is None
    store = store or AcquisitionStore()
    try:
        row = store.get(acquisition_id)
        if row is None:
            raise ValueError(f"No acquisition {acquisition_id}")
        if row["status"] == STATUS_ACQUIRED:
            return AcquisitionOutcome(row["id"], STATUS_ACQUIRED, _document_ids(store, row["id"]), already_acquired=True)
        return _attempt(store, row, reader)
    finally:
        if own:
            store.close()


def extraction_for_document(purchase_document_id: int, store: Optional[AcquisitionStore] = None) -> Optional[dict]:
    """What was read for this document (amounts, provenance, conflicts...),
    or None for a document acquired before this capability existed."""
    own = store is None
    store = store or AcquisitionStore()
    try:
        row = store.invoice_for_document(purchase_document_id)
        if row is None:
            return None
        data = json.loads(row["extraction_json"])
        data["acquisition"] = {k: row[k] for k in ("acquisition_id", "original_filename", "stored_name", "method",
                                                   "pages_total", "pages_read", "channel", "acquisition_status",
                                                   "source_reference")}
        return data
    finally:
        if own:
            store.close()
