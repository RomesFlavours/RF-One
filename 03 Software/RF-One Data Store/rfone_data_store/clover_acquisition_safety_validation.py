"""Synthetic tests for CLOVER_ACQUISITION_SAFETY_001 — a Clover read that
fails is never taken for an empty answer.

One Location is first acquired successfully (Orders, Payments with their
Employee and Tender links, Shifts), which also sets its last successful
synchronization. Then, for each failure below, a Sync Now job is run and
the test checks that it ends FAILED, that EVERY table except the job
history is byte-for-byte what it was before, that no Employee/Tender link
was cleared, that the sync point did not move, and that the message says
what really happened:

- invalid token (every call 401)
- wrong merchant (configured merchant is not the Location's)
- Clover answering for a different merchant
- Employees denied (403) / Tenders denied (403) / Shifts denied (403)
- a Clover error in the middle of the job, after writes had begun
- a pagination answer cut short (incomplete)

A really empty but valid answer, by contrast, lets the job complete.
Never contacts Clover.
"""

from __future__ import annotations

from datetime import datetime, time as dtime, timedelta, timezone
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from . import models as m
from .clover_acquisition_validation import ValidationResult, _FakeResult
from .historical_backfill_extractor_validation import _FullCoverageFakeCloverClient
from .technical.connectors.clover import acquisition_jobs as jobs
from .technical.connectors.clover.source_guard import CloverSourceUnavailableError, require_complete

UTC = timezone.utc
MERCHANT = "SAFE-MERCH-1"
T0 = datetime(2026, 9, 20, 23, 0, tzinfo=UTC)


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


class _Clover(_FullCoverageFakeCloverClient):
    """A healthy fake Clover whose answers can be broken one way at a time."""

    def __init__(self, merchant_id: str = MERCHANT) -> None:
        super().__init__(merchant_id=merchant_id)
        self.all_unauthorized = False
        self.deny: set[str] = set()  # collection names answered 403
        self.merchant_answers_as: str | None = None
        self.fail_order_fetch = False
        self.empty_everything = False

    def get(self, path: str, params: dict[str, Any] | None = None) -> _FakeResult:
        if self.all_unauthorized:
            self.calls.append((path, params))
            return _FakeResult(ok=False, error="authentication/authorization failed: HTTP 401", status_code=401)
        if path == f"/v3/merchants/{self.merchant_id}" and self.merchant_answers_as:
            return _FakeResult(ok=True, data={"id": self.merchant_answers_as})
        last = path.rstrip("/").rsplit("/", 1)[-1]
        if last in self.deny:
            self.calls.append((path, params))
            return _FakeResult(ok=False, error="authentication/authorization failed: HTTP 403", status_code=403)
        if self.fail_order_fetch and "/orders/" in path and "/line_items" not in path:
            return _FakeResult(ok=False, error="server error after retries: HTTP 502", status_code=502)
        if self.empty_everything and path.endswith("/payments"):
            return _FakeResult(ok=True, data={"elements": []})
        return super().get(path, params)


def _seed_clover(client: _Clover) -> None:
    client.employees = [{"id": "S-EMP1", "name": "Alice", "role": "EMPLOYEE"}]
    client.tenders = [{"id": "S-TND1", "label": "Credit Card", "labelKey": "com.clover.tender.credit_card", "enabled": True}]
    client.shifts = [{"id": "S-SHIFT1", "employee": {"id": "S-EMP1"}, "inTime": _ms(T0 - timedelta(hours=4)),
                      "outTime": _ms(T0 + timedelta(hours=2))}]
    client.orders_by_id["S-ORD1"] = {
        "id": "S-ORD1", "employee": {"id": "S-EMP1"}, "createdTime": _ms(T0), "modifiedTime": _ms(T0),
        "state": "locked", "paymentState": "PAID", "currency": "USD", "total": 5000, "lineItems": {"elements": []},
    }
    client.payments = [{
        "id": "S-PAY1", "order": {"id": "S-ORD1"}, "employee": {"id": "S-EMP1"},
        "tender": {"id": "S-TND1", "label": "Credit Card"}, "amount": 5000, "taxAmount": 0, "tipAmount": 800,
        "createdTime": _ms(T0), "modifiedTime": _ms(T0), "result": "SUCCESS",
    }]


def _fingerprint(session_factory: sessionmaker[Session]) -> dict[str, list[str]]:
    """Every row of every table except the job history itself."""
    out: dict[str, list[str]] = {}
    with session_factory() as s:
        for table in m.Base.metadata.sorted_tables:
            if table.name == "ingestion_runs":
                continue
            rows = s.execute(text(f'SELECT * FROM "{table.name}"')).fetchall()
            out[table.name] = sorted(repr(tuple(r)) for r in rows)
    return out


def _links(session_factory: sessionmaker[Session]) -> tuple[int, int, int]:
    with session_factory() as s:
        orders = s.scalar(select(m.Order.employee_id).filter_by(source_order_id="S-ORD1"))
        pay = s.execute(select(m.Payment.employee_id, m.Payment.tender_id).filter_by(source_payment_id="S-PAY1")).one()
        return orders, pay[0], pay[1]


def run_validation(session_factory: sessionmaker[Session]) -> ValidationResult:
    result = ValidationResult(success=True)

    with session_factory() as s:
        source_system = s.scalars(select(m.SourceSystem).filter_by(code="CLOVER")).first()
        if source_system is None:
            source_system = m.SourceSystem(code="CLOVER", name="Clover", active=True)
            s.add(source_system)
            s.flush()
        merchant = m.Merchant(source_system_id=source_system.id, source_merchant_id=MERCHANT, name="Safety Merchant")
        s.add(merchant)
        s.flush()
        location = m.Location(
            merchant_id=merchant.id, source_system_id=source_system.id, source_location_id=MERCHANT,
            name="Safety Test Location", currency="USD", timezone="America/New_York",
            operating_day_cutoff_time=dtime(4, 0),
        )
        s.add(location)
        s.commit()
        location_id = location.id

    # --- Baseline: a successful Backfill, then a successful Sync Now ---------
    healthy = _Clover()
    _seed_clover(healthy)
    with s_(session_factory) as s:
        run = jobs.request_historical_backfill(
            s, location_id=location_id, period_start=T0 - timedelta(days=1), period_end=T0 + timedelta(hours=3),
            launcher=lambda _id: None,
        )
    jobs.execute_job(session_factory, run.id, client=healthy)
    with s_(session_factory) as s:
        sync = jobs.request_sync_now(s, location_id=location_id, launcher=lambda _id: None,
                                     now=T0 + timedelta(hours=6))
    jobs.execute_job(session_factory, sync.id, client=healthy)
    with s_(session_factory) as s:
        baseline_status = s.get(m.IngestionRun, sync.id).status
        point_before = jobs.get_last_successful_sync_point(s, location_id=location_id).at
    order_emp, pay_emp, pay_tender = _links(session_factory)
    result.check("baseline: healthy Backfill + Sync Now COMPLETE, Order/Payment linked to Employee and Tender",
                 baseline_status == "COMPLETE" and None not in (order_emp, pay_emp, pay_tender))

    def scenario(name: str, client: _Clover, expected: tuple[str, ...]) -> None:
        before = _fingerprint(session_factory)
        with s_(session_factory) as s:
            job = jobs.request_sync_now(s, location_id=location_id, launcher=lambda _id: None,
                                        now=T0 + timedelta(hours=12))
        jobs.execute_job(session_factory, job.id, client=client)
        with s_(session_factory) as s:
            run = s.get(m.IngestionRun, job.id)
            point_after = jobs.get_last_successful_sync_point(s, location_id=location_id).at
        after = _fingerprint(session_factory)
        changed = [t for t in before if before[t] != after[t]]
        message = run.error_summary or ""
        result.check(f"{name}: the job ends FAILED and releases the location", run.status == "FAILED" and run.lock_key is None)
        result.check(f"{name}: every pre-existing row is identical (no table changed)", not changed)
        result.check(f"{name}: no Employee/Tender link was cleared", _links(session_factory) == (order_emp, pay_emp, pay_tender))
        result.check(f"{name}: the last successful sync did not move", point_after == point_before)
        result.check(f"{name}: the message states the real problem ({message[:110]!r})",
                     all(fragment in message for fragment in expected) and "no RF-One data was changed" in message)

    def broken(**flags: Any) -> _Clover:
        client = _Clover(merchant_id=flags.pop("merchant_id", MERCHANT))
        _seed_clover(client)
        client.tips_changed = True
        client.payments[0]["tipAmount"] = 1500  # would be written if the job ever got that far
        for key, value in flags.items():
            setattr(client, key, value)
        return client

    scenario("invalid token", broken(all_unauthorized=True),
             ("could not read the merchant account", "refused the credentials", "HTTP 401"))
    scenario("wrong merchant configured", broken(merchant_id="OTHER-MERCH"),
             ("Wrong Clover merchant", "Safety Test Location", MERCHANT, "OTHER-MERCH"))
    scenario("Clover answers for another merchant", broken(merchant_answers_as="STRANGER"),
             ("Wrong Clover merchant", "different merchant", "STRANGER"))
    scenario("Employees denied", broken(deny={"employees"}), ("could not read Employees", "HTTP 403"))
    scenario("Tenders denied", broken(deny={"tenders"}), ("could not read Tenders (payment methods)", "HTTP 403"))
    scenario("Shifts denied", broken(deny={"shifts"}), ("could not read Shifts", "HTTP 403"))
    scenario("Clover error in the middle of the job (after writes began)", broken(fail_order_fetch=True),
             ("could not read Order", "server error", "HTTP 502"))

    # --- Incomplete pagination is never a complete answer --------------------
    class _Truncated:
        ok = True
        elements = [{"id": "x"}]
        truncated_by_safety_guard = True

    try:
        require_complete(_Truncated(), "Payments")
        refused = False
    except CloverSourceUnavailableError as exc:
        refused = "incomplete" in str(exc)
    result.check("an answer cut short by the pagination limit is refused as incomplete", refused)

    # --- A really empty, valid answer is a real "nothing" -------------------
    empty = _Clover()
    _seed_clover(empty)
    empty.empty_everything = True
    before = _fingerprint(session_factory)
    with s_(session_factory) as s:
        job = jobs.request_sync_now(s, location_id=location_id, launcher=lambda _id: None,
                                    now=T0 + timedelta(hours=13))
    jobs.execute_job(session_factory, job.id, client=empty)
    with s_(session_factory) as s:
        run = s.get(m.IngestionRun, job.id)
        point_after = jobs.get_last_successful_sync_point(s, location_id=location_id).at
    after = _fingerprint(session_factory)
    only_expected = all(before[t] == after[t] for t in before if t not in ("employees", "tenders", "devices", "source_records", "shifts", "employee_source_roles"))
    result.check("a valid empty answer (no Payments in the window) completes: COMPLETE, 0 orders/payments",
                 run.status == "COMPLETE" and run.orders_processed == 0 and run.payments_processed == 0)
    result.check("a valid empty answer moves the sync point to the end of its window",
                 point_after == T0 + timedelta(hours=13))
    result.check("a valid empty answer changes no Order/Payment/Tip and clears no link",
                 only_expected and _links(session_factory) == (order_emp, pay_emp, pay_tender))
    return result


class s_:  # noqa: N801 — tiny session context helper
    def __init__(self, factory: sessionmaker[Session]):
        self._session = factory()

    def __enter__(self) -> Session:
        return self._session

    def __exit__(self, *exc: Any) -> None:
        self._session.close()
