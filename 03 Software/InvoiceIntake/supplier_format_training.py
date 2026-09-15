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

- auto-validate any Supplier — a brand new (Supplier, Format) pair is
  always first written as `UNTRAINED` by `record_observation()`; nothing
  in this module ever *promotes* a pair to `TRAINING`/`VALIDATED` on its
  own (see "Phase 1" below for the one narrow exception), and no caller
  reads `trust_state` back to influence a document's own NORMALIZED/HUMAN
  result (see `purchased_bridge.py`'s own validation, which never queries
  this store);
- define a universal N or accuracy threshold — those remain a future,
  per-format/per-Supplier configuration decision;
- implement automatic promotion — this is observation/bookkeeping only.
  `set_trust_state()` exists for a human/Product-Owner-driven decision to
  record a promotion once a real N/threshold is defined (see
  `03 Software/RF-One Data Store/PURCHASING.md`, §11) — nothing in this
  module calls it itself.

**Phase 1 ("Purchased Supplier+Format Training — Phase 1") extension:**
`trust_state` now has four values — `UNTRAINED`, `TRAINING`, `VALIDATED`,
`DEGRADED` — matching the Purchased/README.md "Source/format validation and
training" concept of an internal, purely technical/operational routing
marker, explicitly **not** one of Purchased Line's own two functional
states (NORMALIZED/HUMAN — see `purchased_bridge.py`, never confused with
this module's `trust_state`). The one automatic transition this module
performs is a **demotion**, never a promotion: if a (Supplier, Format)
pair already sitting at `VALIDATED` is observed again with a materially
different layout shape (Task requirement 12 — a coarser comparison than a
real layout-version detector, see `layout_signature()`), `record_observation()`
moves it to `DEGRADED` on the spot, so a silently changed supplier format
is never left looking trusted. Nothing here ever moves a pair the other
direction automatically.

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

# Lets a test suite point every `SupplierFormatTrainingStore()` call made
# through `purchased_bridge.py` (which always constructs one with no
# explicit path) at a disposable file instead of the real one — the same
# isolation `RFONE_DATABASE_URL` already gives the canonical Purchasing
# database in tests. Without this, running `test_purchased_bridge.py`
# silently pollutes the real, persistent training data with synthetic test
# suppliers (found during "Purchased Supplier+Format Training — Phase 1",
# see its report) — this store is meant to reflect real observed documents.
_ENV_DB_PATH_OVERRIDE = "SUPPLIER_FORMAT_TRAINING_DB_PATH"

TRUST_STATE_UNTRAINED = "UNTRAINED"  # written for a brand new (Supplier, Format) pair
TRUST_STATE_TRAINING = "TRAINING"  # human-set once real review of this pair has begun
TRUST_STATE_VALIDATED = "VALIDATED"  # human/Product-Owner-set once accuracy is judged sufficient (no N/threshold fixed here)
TRUST_STATE_DEGRADED = "DEGRADED"  # auto-set by record_observation() when a VALIDATED pair's layout shape changes

TRUST_STATES = (TRUST_STATE_UNTRAINED, TRUST_STATE_TRAINING, TRUST_STATE_VALIDATED, TRUST_STATE_DEGRADED)

# Field-level human review classifications (Task requirement 5 — "Human
# Review Model"). Illustrative labels, not a confidence score: every
# reviewed field is put in exactly one bucket, and a mismatch is always
# recorded as INCORRECT/UNREAD/AMBIGUOUS rather than silently corrected
# ("NON correggere in silenzio").
FIELD_REVIEW_CORRECT = "CORRECT"
FIELD_REVIEW_INCORRECT = "INCORRECT"
FIELD_REVIEW_UNREAD = "UNREAD"
FIELD_REVIEW_AMBIGUOUS = "AMBIGUOUS"

FIELD_REVIEW_CLASSIFICATIONS = (
    FIELD_REVIEW_CORRECT,
    FIELD_REVIEW_INCORRECT,
    FIELD_REVIEW_UNREAD,
    FIELD_REVIEW_AMBIGUOUS,
)

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

CREATE TABLE IF NOT EXISTS field_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_name TEXT NOT NULL,
    source_format TEXT NOT NULL,
    document_reference TEXT NOT NULL,
    field_name TEXT NOT NULL,
    classification TEXT NOT NULL,
    extracted_value TEXT,
    expected_value TEXT,
    note TEXT,
    reviewed_at TEXT NOT NULL
);
"""


def _shape_prefix(signature: str | None) -> str | None:
    """The field-presence part of a `layout_signature()` string (everything
    before the "-L<count>" suffix) — used to decide whether two signatures
    are "materially different" (Task requirement 12). A document simply
    having a few more or fewer lines than usual is normal variation, not a
    layout change; which fields could be found/not found at all is."""

    if not signature:
        return None
    return signature.split("-", 1)[0]


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


@dataclass(frozen=True)
class FieldReview:
    id: int
    supplier_name: str
    source_format: str
    document_reference: str
    field_name: str
    classification: str
    extracted_value: Optional[str]
    expected_value: Optional[str]
    note: Optional[str]
    reviewed_at: str


@dataclass(frozen=True)
class FieldReviewSummary:
    supplier_name: str
    source_format: str
    field_name: str
    counts: dict  # classification -> count, always containing all of FIELD_REVIEW_CLASSIFICATIONS


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

    def __init__(self, db_path: str | None = None):
        db_path = db_path or os.environ.get(_ENV_DB_PATH_OVERRIDE) or DEFAULT_DB_PATH
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
        Format) pair. A brand new pair is written as `UNTRAINED`; an
        existing pair keeps whatever `trust_state` it already had —
        *except* a `VALIDATED` pair whose layout shape just changed
        materially, which this function demotes to `DEGRADED` on the spot
        (Task requirement 12). This is the only trust_state transition this
        function ever makes — it never promotes anything (see module
        docstring)."""

        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._conn:
            existing = self._conn.execute(
                "SELECT trust_state, last_layout_signature FROM supplier_format_observations "
                "WHERE supplier_name = ? AND source_format = ?",
                (supplier_name, source_format),
            ).fetchone()

            next_trust_state = TRUST_STATE_UNTRAINED
            if existing is not None:
                next_trust_state = existing["trust_state"]
                if (
                    existing["trust_state"] == TRUST_STATE_VALIDATED
                    and signature is not None
                    and existing["last_layout_signature"] is not None
                    and _shape_prefix(signature) != _shape_prefix(existing["last_layout_signature"])
                ):
                    next_trust_state = TRUST_STATE_DEGRADED

            self._conn.execute(
                "INSERT INTO supplier_format_observations "
                "(supplier_name, source_format, reviewed_count, normalized_count, human_count, "
                " trust_state, last_layout_signature, last_seen_at) "
                "VALUES (?, ?, 1, ?, ?, ?, ?, ?) "
                "ON CONFLICT(supplier_name, source_format) DO UPDATE SET "
                "reviewed_count = reviewed_count + 1, "
                "normalized_count = normalized_count + excluded.normalized_count, "
                "human_count = human_count + excluded.human_count, "
                "trust_state = excluded.trust_state, "
                "last_layout_signature = excluded.last_layout_signature, "
                "last_seen_at = excluded.last_seen_at",
                (
                    supplier_name,
                    source_format,
                    1 if was_normalized else 0,
                    0 if was_normalized else 1,
                    next_trust_state,
                    signature,
                    now,
                ),
            )
        return self.get(supplier_name, source_format)

    def set_trust_state(self, supplier_name: str, source_format: str, trust_state: str) -> SupplierFormatObservation:
        """Explicit, human/Product-Owner-driven trust_state change — e.g.
        promoting a (Supplier, Format) pair to `VALIDATED` once a real
        N/accuracy-threshold decision has been made (Purchased/README.md,
        "Source/format validation and training"; PURCHASING.md §11).
        Never called automatically by this module — see module docstring
        for why (no universal N/threshold is fixed here)."""

        if trust_state not in TRUST_STATES:
            raise ValueError(f"Unknown trust_state {trust_state!r}; must be one of {TRUST_STATES}")
        existing = self.get(supplier_name, source_format)
        if existing is None:
            raise ValueError(f"No observation recorded yet for ({supplier_name!r}, {source_format!r})")
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE supplier_format_observations SET trust_state = ? "
                "WHERE supplier_name = ? AND source_format = ?",
                (trust_state, supplier_name, source_format),
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

    # -- Human Review Model (Task requirement 5) ----------------------------

    def record_field_review(
        self,
        *,
        supplier_name: str,
        source_format: str,
        document_reference: str,
        field_name: str,
        classification: str,
        extracted_value: str | None = None,
        expected_value: str | None = None,
        note: str | None = None,
    ) -> FieldReview:
        """Durably records one field-level human review classification for
        one real document (Task requirement 5: comparing supplier, invoice
        date, invoice number, total, and line-item fields against the real
        document, and classifying each as CORRECT/INCORRECT/UNREAD/
        AMBIGUOUS — "NON correggere in silenzio"). `document_reference` is
        any stable identifier for the reviewed source document (e.g. its
        original filename); this store never resolves it to a
        PurchaseDocumentId — that would couple this observational store to
        the canonical database, which it must stay independent of (see
        module docstring)."""

        if classification not in FIELD_REVIEW_CLASSIFICATIONS:
            raise ValueError(f"Unknown classification {classification!r}; must be one of {FIELD_REVIEW_CLASSIFICATIONS}")
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._conn:
            cursor = self._conn.execute(
                "INSERT INTO field_reviews "
                "(supplier_name, source_format, document_reference, field_name, classification, "
                " extracted_value, expected_value, note, reviewed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    supplier_name,
                    source_format,
                    document_reference,
                    field_name,
                    classification,
                    extracted_value,
                    expected_value,
                    note,
                    now,
                ),
            )
            review_id = cursor.lastrowid
        row = self._conn.execute("SELECT * FROM field_reviews WHERE id = ?", (review_id,)).fetchone()
        return FieldReview(**dict(row))

    def list_field_reviews(
        self, supplier_name: str | None = None, source_format: str | None = None
    ) -> list[FieldReview]:
        query = "SELECT * FROM field_reviews"
        params: tuple = ()
        clauses = []
        if supplier_name is not None:
            clauses.append("supplier_name = ?")
            params += (supplier_name,)
        if source_format is not None:
            clauses.append("source_format = ?")
            params += (source_format,)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY id"
        rows = self._conn.execute(query, params).fetchall()
        return [FieldReview(**dict(row)) for row in rows]

    def summarize_field_reviews(self) -> list[FieldReviewSummary]:
        """One row per (Supplier, Format, field_name), with a count per
        classification — the shape the phase-1 report's "K.
        NORMALIZED/HUMAN by format" / field-reliability sections are built
        from."""

        rows = self._conn.execute(
            "SELECT supplier_name, source_format, field_name, classification, COUNT(*) AS n "
            "FROM field_reviews GROUP BY supplier_name, source_format, field_name, classification"
        ).fetchall()
        summaries: dict[tuple[str, str, str], dict[str, int]] = {}
        for row in rows:
            key = (row["supplier_name"], row["source_format"], row["field_name"])
            summaries.setdefault(key, {c: 0 for c in FIELD_REVIEW_CLASSIFICATIONS})[row["classification"]] = row["n"]
        return [
            FieldReviewSummary(supplier_name=k[0], source_format=k[1], field_name=k[2], counts=counts)
            for k, counts in sorted(summaries.items())
        ]
