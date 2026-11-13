"""Automated synthetic tests for `technical.connectors.clover.freshness`
(the central on-demand Clover data freshness service).

Mirrors `clover_live_sync_validation.py`'s pattern: synthetic fixture,
disposable database, `FakeCloverClient`, always rolled back, never contacts
Clover production. Deliberately minimal — only the two behaviors the
service exists to guarantee:

1. an already-covered range returns ALREADY_FRESH and calls Clover for
   nothing (no new `IngestionRun`, no client call);
2. a range with no covering run invokes the existing importer and returns
   REFRESHED with the import's own summary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from . import models as m
from .clover_acquisition_validation import FakeCloverClient
from .technical.connectors.clover.freshness import (
    STATUS_ALREADY_FRESH,
    STATUS_REFRESHED,
    ensure_clover_data_fresh,
)

UTC = timezone.utc


@dataclass
class ValidationResult:
    success: bool
    checks_passed: list[str] = field(default_factory=list)
    checks_failed: list[str] = field(default_factory=list)

    def check(self, description: str, condition: bool) -> None:
        if condition:
            self.checks_passed.append(description)
        else:
            self.checks_failed.append(description)
            self.success = False


def run_validation(session_factory: sessionmaker[Session]) -> ValidationResult:
    result = ValidationResult(success=True)
    with session_factory() as session:
        try:
            _test_already_fresh_range_skips_import(session, result)
            _test_missing_range_invokes_importer(session, result)
        finally:
            session.rollback()
    return result


def _build_fixture(session: Session, *, merchant_source_id: str) -> tuple[m.Location, m.SourceSystem]:
    source_system = session.scalars(select(m.SourceSystem).filter_by(code="CLOVER")).first()
    if source_system is None:
        source_system = m.SourceSystem(code="CLOVER", name="Clover", active=True)
        session.add(source_system)
        session.flush()

    merchant = m.Merchant(
        source_system_id=source_system.id, source_merchant_id=merchant_source_id, name="Freshness Test Merchant",
    )
    session.add(merchant)
    session.flush()

    location = m.Location(
        merchant_id=merchant.id, source_system_id=source_system.id, source_location_id=merchant_source_id,
        name="Freshness Test Location", currency="USD",
    )
    session.add(location)
    session.flush()
    return location, source_system


def _test_already_fresh_range_skips_import(session: Session, result: ValidationResult) -> None:
    location, source_system = _build_fixture(session, merchant_source_id="FRESH1")
    period_start = datetime(2026, 9, 4, tzinfo=UTC)
    period_end = datetime(2026, 9, 5, tzinfo=UTC)

    # A prior COMPLETE run already covers the requested range end-to-end.
    session.add(
        m.IngestionRun(
            source_system_id=source_system.id, location_id=location.id, started_at=period_end,
            finished_at=period_end, status="COMPLETE",
            source_window_start=period_start, source_window_end=period_end,
            notes="CLOVER_ACQUISITION mode=BACKFILL location_id=%d; payments=0 orders=0 shifts=0 refunds=0" % location.id,
        )
    )
    session.commit()

    runs_before = len(session.scalars(select(m.IngestionRun).filter_by(location_id=location.id)).all())
    client = FakeCloverClient(merchant_id="FRESH1")
    outcome = ensure_clover_data_fresh(
        session, location_id=location.id, from_date=period_start, through_date=period_end, client=client,
    )
    runs_after = len(session.scalars(select(m.IngestionRun).filter_by(location_id=location.id)).all())

    result.check(
        "an already-covered range returns ALREADY_FRESH with no summary",
        outcome.status == STATUS_ALREADY_FRESH and outcome.summary is None,
    )
    result.check(
        "an already-covered range calls Clover for nothing and creates no new IngestionRun",
        client.calls == [] and runs_after == runs_before,
    )


def _test_missing_range_invokes_importer(session: Session, result: ValidationResult) -> None:
    location, source_system = _build_fixture(session, merchant_source_id="FRESH2")
    period_start = datetime(2026, 9, 4, tzinfo=UTC)
    period_end = datetime(2026, 9, 5, tzinfo=UTC)

    # No prior IngestionRun at all for this Location — nothing is covered.
    client = FakeCloverClient(merchant_id="FRESH2")
    order_time = period_start + timedelta(hours=2)
    client.orders_by_id["FRESH2-ORDER-1"] = {
        "id": "FRESH2-ORDER-1", "employee": {"id": "FRESH2-EMP1"},
        "createdTime": int(order_time.timestamp() * 1000), "modifiedTime": int(order_time.timestamp() * 1000),
        "state": "locked", "paymentState": "PAID", "currency": "USD", "total": 1000,
        "lineItems": {"elements": []},
    }
    client.payments.append({
        "id": "FRESH2-PAY-1", "order": {"id": "FRESH2-ORDER-1"}, "employee": {"id": "FRESH2-EMP1"},
        "tender": {"id": "FRESH2-TND1", "label": "Cash"}, "amount": 1000, "taxAmount": 0,
        "createdTime": int(order_time.timestamp() * 1000), "modifiedTime": int(order_time.timestamp() * 1000),
        "result": "SUCCESS",
    })

    outcome = ensure_clover_data_fresh(
        session, location_id=location.id, from_date=period_start, through_date=period_end, client=client,
    )

    result.check(
        "a missing range calls the existing importer (Clover client was actually invoked) and returns "
        "REFRESHED with its summary",
        outcome.status == STATUS_REFRESHED and outcome.summary is not None and client.calls != [],
    )
    order = session.scalars(
        select(m.Order).filter_by(source_system_id=source_system.id, source_order_id="FRESH2-ORDER-1")
    ).first()
    result.check(
        "the invoked import actually wrote the fetched Order via the existing canonical upsert path",
        order is not None and outcome.summary.orders_imported == 1,
    )
    ingestion_run = session.scalars(
        select(m.IngestionRun).filter_by(location_id=location.id, source_system_id=source_system.id)
    ).first()
    result.check(
        "the resulting IngestionRun is COMPLETE and committed",
        ingestion_run is not None and ingestion_run.status == "COMPLETE",
    )

    # A second call for the SAME range must now be ALREADY_FRESH — the run
    # just committed above satisfies its own coverage check.
    client_calls_before = len(client.calls)
    outcome2 = ensure_clover_data_fresh(
        session, location_id=location.id, from_date=period_start, through_date=period_end, client=client,
    )
    result.check(
        "immediately re-requesting the same now-imported range returns ALREADY_FRESH and makes no "
        "further Clover calls",
        outcome2.status == STATUS_ALREADY_FRESH and len(client.calls) == client_calls_before,
    )
