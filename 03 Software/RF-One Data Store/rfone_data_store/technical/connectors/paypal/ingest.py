"""Orchestrates loading PayPal transactions into the canonical
`FinancialTransaction` ledger, using upsert-by-(`payment_instrument_id`,
`external_transaction_id`) idempotency (`uq_ft_instrument_external_id`,
`models.py`) — mirrors `technical/connectors/clover/ingest.py`'s own
`upsert()` convention — and creating `IngestionRun`/`SourceRecord`
provenance, exactly like the Clover connector.

Ported from `feature/purchased-invoice-intake-alignment`
(FINANCIAL_MODEL_CONVERGENCE_001 Phase 5) and retargeted from that
branch's `PaymentInstrumentTransaction` (not present on this branch, and
not reintroduced — see Phase 3's `FinancialTransaction` module docstring)
to the canonical `FinancialTransaction` already shared with CSV-sourced
Bank Reconciliation. Field adaptation from the source connector:

- `PaymentInstrumentTransaction` -> `FinancialTransaction`.
- `description` -> `description_original` (canonical's own field name;
  `description_normalized` is left NULL — PayPal ingestion has no CSV-style
  normalization step and none is invented here).
- `currency` is dropped: `FinancialTransaction` carries no per-row currency
  column (only `PaymentInstrument.currency` does) — this is an existing
  canonical schema fact, not a Phase 5 omission, and no schema change is
  made to reintroduce it (task §16).
- `posting_date`/`transaction_date` are left NULL: the source connector
  never populated an accounting/posting date distinct from
  `transaction_datetime`, and PayPal's Transaction Search response carries
  no separate posting/settlement date field to justify populating one
  (task §9) — only `transaction_datetime` carries PayPal's precise
  timestamp, with no precision loss.
- `bank_source`/`reference`/`balance_minor`/`import_batch_id`/
  `source_row_number` are CSV-specific fields with no PayPal source fact to
  populate them; left NULL/unset, never invented.

This module never talks to PayPal directly for parsing/mapping — only
`client.py` does network I/O. `ingest_transaction_details()` accepts
already-fetched raw `transaction_details` dicts, so it can be exercised in
tests with fixture payloads and never requires real PayPal credentials —
`run_sync()` is the thin live entrypoint that fetches via a real
`PayPalClient` and then calls the exact same tested path.

Recognition (`bank_reconciliation.recognition.deduce_for_transaction`) is
deliberately NOT invoked here: it is currently wired specifically into the
CSV normalization path (`bank_reconciliation/service.py`'s
`normalize_batch`), not generically triggered by `FinancialTransaction`
creation regardless of source. Extending Recognition to PayPal rows is
deferred to a later phase rather than broadened here (task §12) — see the
Phase 5 final report.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .... import models as m
from ....bank_reconciliation import matching
from ....ingestion.common import payload_hash, utc_now
from . import mapping, parser
from .client import PayPalClient

PAYPAL_SOURCE_SYSTEM_CODE = "PAYPAL"


def get_or_create_paypal_source_system(session: Session) -> m.SourceSystem:
    existing = session.scalars(select(m.SourceSystem).filter_by(code=PAYPAL_SOURCE_SYSTEM_CODE)).first()
    if existing is not None:
        return existing
    source_system = m.SourceSystem(code=PAYPAL_SOURCE_SYSTEM_CODE, name="PayPal", active=True)
    session.add(source_system)
    session.flush()
    return source_system


def _upsert_transaction(
    session: Session, *, payment_instrument_id: int, source_system_id: int, txn: parser.PayPalTransaction,
) -> m.FinancialTransaction:
    """Idempotent insert-or-update keyed by
    (`payment_instrument_id`, `external_transaction_id`) — matches
    `uq_ft_instrument_external_id` (`models.py`), the same
    unique-filter-matches-a-real-UniqueConstraint convention
    `technical/connectors/clover/ingest.py:upsert()` documents."""
    unique_filter = {
        "payment_instrument_id": payment_instrument_id,
        "external_transaction_id": txn.transaction_id,
    }
    values = {
        "source_system_id": source_system_id,
        "transaction_datetime": txn.transaction_datetime,
        "amount_minor": txn.net_amount_minor if txn.net_amount_minor is not None else txn.gross_amount_minor,
        "gross_amount_minor": txn.gross_amount_minor,
        "fee_amount_minor": txn.fee_amount_minor,
        "net_amount_minor": txn.net_amount_minor,
        "native_transaction_type": txn.event_code,
        "status": mapping.to_canonical_status(txn.status),
        "description_original": txn.description,
        "counterparty_name": txn.counterparty_name,
        "counterparty_identifier": txn.counterparty_identifier,
        "related_external_transaction_id": txn.related_transaction_id,
    }
    stmt = select(m.FinancialTransaction).filter_by(**unique_filter)
    existing = session.scalars(stmt).first()
    if existing is not None:
        for key, value in values.items():
            setattr(existing, key, value)
        return existing
    obj = m.FinancialTransaction(**unique_filter, **values, classification="UNKNOWN")
    session.add(obj)
    return obj


def ingest_transaction_details(
    session: Session,
    *,
    payment_instrument_id: int,
    raw_transaction_details: list[dict[str, Any]],
    started_at: datetime | None = None,
) -> m.IngestionRun:
    """Loads already-fetched raw PayPal `transaction_details` entries for
    one `PaymentInstrument` (expected `instrument_type == 'PAYPAL'`) into
    the canonical `FinancialTransaction` ledger. Idempotent: re-running with
    the same entries updates the existing rows in place rather than
    duplicating them — the DB-level guard is `uq_ft_instrument_external_id`.
    Never creates a `BankImportBatch`/`RawBankTransaction` (those remain
    CSV-specific provenance) — provenance here is `IngestionRun`/
    `SourceRecord` only."""
    source_system = get_or_create_paypal_source_system(session)
    session.flush()

    lock_key = f"paypal:{payment_instrument_id}"
    run = m.IngestionRun(
        source_system_id=source_system.id,
        started_at=started_at or utc_now(),
        status="RUNNING",
        lock_key=lock_key,
    )
    session.add(run)
    session.flush()

    for raw in raw_transaction_details:
        txn = parser.parse_transaction_detail(raw)
        financial_transaction = _upsert_transaction(
            session, payment_instrument_id=payment_instrument_id, source_system_id=source_system.id, txn=txn,
        )
        session.add(
            m.SourceRecord(
                ingestion_run_id=run.id,
                source_system_id=source_system.id,
                entity_type="paypal_transaction",
                source_id=txn.transaction_id,
                retrieved_at=utc_now(),
                payload_hash=payload_hash(raw),
                raw_path=None,
                raw_json=raw,
            )
        )
        # `financial_transaction.id` must exist before the canonical
        # matching hook can compare it against candidates (Phase 6B) — the
        # same per-row flush convention `bank_reconciliation/service.py`
        # already uses for its own normalized rows.
        session.flush()
        matching.on_financial_transaction_acquired(session, financial_transaction)

    run.finished_at = utc_now()
    run.status = "COMPLETE"
    run.lock_key = None  # release the concurrency guard (models.py IngestionRun.lock_key docstring)
    return run


def run_sync(
    session: Session,
    *,
    payment_instrument_id: int,
    client: PayPalClient,
    start_date: datetime,
    end_date: datetime,
) -> m.IngestionRun:
    """Live entrypoint: fetches raw transactions from PayPal via `client`
    and ingests them through the exact same tested path as
    `ingest_transaction_details`. Not exercised by the test suite — no real
    PayPal credentials are available in this environment."""
    raw_transaction_details = client.fetch_all_transactions(start_date, end_date)
    return ingest_transaction_details(
        session,
        payment_instrument_id=payment_instrument_id,
        raw_transaction_details=raw_transaction_details,
        started_at=utc_now(),
    )
