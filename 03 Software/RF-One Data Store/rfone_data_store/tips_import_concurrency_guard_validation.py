"""Automated synthetic tests for the Clover data acquisition concurrency
guard (originally TIPS_IMPORT_CONCURRENCY_GUARD_001; the guard itself now
lives in `technical.connectors.clover.acquisition`, shared by Historical Backfill and
Live Sync — CLOVER_DATA_ACQUISITION_ARCHITECTURE_001 — never Tips-owned).

Mirrors `clover_acquisition_validation.py`'s pattern (own synthetic fixture,
own disposable database via `run_validation(session_factory)`, reuses its
`FakeCloverClient`/`ValidationResult`). NEVER contacts Clover production.

"Two concurrent HTTP requests" is simulated deterministically rather than
with real threads/processes: this module drives the guard's own primitives
directly — it registers a RUNNING lock exactly the way `import_clover_period`
itself does at the top of a real call, then calls `import_clover_period`
again for the same restaurant/period and asserts it is rejected before any
Clover call happens. This is equivalent to (and more deterministic than) two
real concurrent submissions racing each other, since the actual race-safety
guarantee comes from `IngestionRun.lock_key`'s UNIQUE index at the database
level (see `acquisition._acquire_import_lock`), not from timing.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from . import models as m
from .technical.connectors.clover.acquisition import (
    ImportAlreadyRunningError,
    ImportSummary,
    MODE_BACKFILL,
    MODE_LIVE_SYNC,
    _finalize_import_run,
    get_latest_acquisition_status,
    import_clover_period,
    reap_stale_acquisition_run,
)
from .clover_acquisition_validation import FakeCloverClient, ValidationResult, _FakeResult, _ref

UTC = timezone.utc


class RaisingCloverClient(FakeCloverClient):
    """Same GET-only fake as `FakeCloverClient`, except `.get()` raises a
    synthetic exception the moment a requested path ends with
    `raise_on_path_suffix` — used to deterministically exercise the FAILED
    recovery path without depending on any real Clover failure mode."""

    def __init__(self, merchant_id: str, raise_on_path_suffix: str):
        super().__init__(merchant_id)
        self._raise_on_path_suffix = raise_on_path_suffix

    def get(self, path: str, params: dict[str, Any] | None = None) -> _FakeResult:
        if path.endswith(self._raise_on_path_suffix):
            raise RuntimeError("synthetic Clover failure injected by TIPS_IMPORT_CONCURRENCY_GUARD_001 test")
        return super().get(path, params)


def run_validation(session_factory: sessionmaker[Session]) -> ValidationResult:
    result = ValidationResult(success=True)
    _test_ui_button_disabled_on_submit(result)
    with session_factory() as session:
        try:
            _test_accept_reject_and_release_on_success(session, result)
            _test_failed_import_releases_guard(session, result)
            _test_stale_running_import_is_auto_recovered(session, result)
            _test_status_report_and_manual_reap(session, result)
        finally:
            session.rollback()
    return result


# `03 Software/Tips/templates/home.html`, three levels up from this file
# (`rfone_data_store/`, then `RF-One Data Store/`, then `03 Software/`).
_TIPS_HOME_TEMPLATE = Path(__file__).resolve().parents[2] / "Tips" / "templates" / "home.html"


def _test_ui_button_disabled_on_submit(result: ValidationResult) -> None:
    """Task §2 / §8's "button is disabled after first submit" check.

    No browser/JS test runner is available in this environment, so this is
    a static assertion on the shipped template rather than a real
    click-through: it confirms the submit handler that disables the button,
    relabels it "Importing...", and blocks a second submit from the same
    page is actually present and wired to the form — the same limitation
    documented in `07 Tasks/Reports/TIPS_IMPORT_CONCURRENCY_GUARD_001.md`."""
    if not _TIPS_HOME_TEMPLATE.is_file():
        result.check(f"UI guard: {_TIPS_HOME_TEMPLATE} exists", False)
        return
    html = _TIPS_HOME_TEMPLATE.read_text(encoding="utf-8")
    result.check(
        "UI guard: the import form's submit is wired to a guard handler",
        'onsubmit="return guardImportSubmit()"' in html and 'id="import-submit-btn"' in html,
    )
    result.check(
        "UI guard: first submit disables the button and relabels it 'Importing...'",
        "btn.disabled = true" in html and "Importing..." in html,
    )
    result.check(
        "UI guard: a second submit from the same page (before reload) is blocked",
        "btn.dataset.submitting === '1'" in html and "return false;" in html,
    )


def _build_base_fixture(session: Session, *, merchant_source_id: str) -> tuple[m.Restaurant, m.Location, m.SourceSystem]:
    """The minimal Restaurant/Location/SourceSystem fixture the guard needs
    — no Payments/Orders required, since these tests exercise the
    lock/guard lifecycle itself, not import content (that is
    `clover_acquisition_validation.py`'s job, deliberately not duplicated
    here)."""
    source_system = session.scalars(select(m.SourceSystem).filter_by(code="CLOVER")).first()
    if source_system is None:
        source_system = m.SourceSystem(code="CLOVER", name="Clover", active=True)
        session.add(source_system)
        session.flush()

    merchant = m.Merchant(
        source_system_id=source_system.id, source_merchant_id=merchant_source_id, name="Guard Test Merchant",
    )
    session.add(merchant)
    session.flush()

    location = m.Location(
        merchant_id=merchant.id, source_system_id=source_system.id, source_location_id=merchant_source_id,
        name="Guard Test Location", currency="USD",
    )
    session.add(location)
    session.flush()

    restaurant = m.Restaurant(name=f"Synthetic Concurrency Guard Test Restaurant {merchant_source_id}", default_currency="USD")
    session.add(restaurant)
    session.flush()
    session.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=location.id, is_primary=True))
    session.flush()

    return restaurant, location, source_system


def _test_accept_reject_and_release_on_success(session: Session, result: ValidationResult) -> None:
    restaurant, location, source_system = _build_base_fixture(session, merchant_source_id="GUARDMERCH1")
    period_start = datetime(2026, 7, 1, tzinfo=UTC)
    period_end = datetime(2026, 7, 8, tzinfo=UTC)

    # =========================================================================
    # First request: accepted.
    # =========================================================================
    client1 = FakeCloverClient(merchant_id="GUARDMERCH1")
    summary1 = import_clover_period(
        session, location_id=location.id, period_start=period_start, period_end=period_end, client=client1,
    )
    session.commit()
    result.check("first import request is accepted (no errors)", summary1.errors == [])

    run1 = session.scalars(
        select(m.IngestionRun)
        .where(m.IngestionRun.source_system_id == source_system.id, m.IngestionRun.location_id == location.id)
        .order_by(m.IngestionRun.id.desc())
    ).first()
    result.check(
        "SUCCESS releases the guard: IngestionRun reaches COMPLETE with lock_key cleared",
        run1 is not None and run1.status == "COMPLETE" and run1.lock_key is None,
    )

    # =========================================================================
    # Simulate a second, concurrent request for the SAME restaurant/period
    # while the first is still (synthetically) RUNNING.
    # =========================================================================
    running_run = m.IngestionRun(
        source_system_id=source_system.id, location_id=location.id, started_at=datetime.now(UTC),
        status="RUNNING", source_window_start=period_start, source_window_end=period_end,
        lock_key=f"CLOVER_ACQUISITION:{location.id}",
        notes="synthetic concurrent RUNNING import registered by test",
    )
    session.add(running_run)
    session.commit()

    client2 = FakeCloverClient(merchant_id="GUARDMERCH1")
    client2.orders_by_id["ORDER-REJECTED"] = {
        "id": "ORDER-REJECTED", "employee": _ref("EMP1"), "createdTime": 0, "modifiedTime": 0,
        "state": "locked", "paymentState": "PAID", "currency": "USD", "total": 1000,
        "lineItems": {"elements": []},
    }
    client2.payments = [
        {
            "id": "PAY-REJECTED", "order": _ref("ORDER-REJECTED"), "employee": _ref("EMP1"),
            "tender": {"id": "TND-CARD", "label": "Credit Card"}, "amount": 1000, "taxAmount": 0,
            "createdTime": 0, "modifiedTime": 0, "result": "SUCCESS", "tipAmount": 100,
        }
    ]

    rejected = False
    try:
        import_clover_period(
            session, location_id=location.id, period_start=period_start, period_end=period_end, client=client2,
        )
    except ImportAlreadyRunningError:
        rejected = True
    result.check("second concurrent request for the same restaurant is rejected", rejected)
    result.check("rejected request performs NO Clover fetch at all", client2.calls == [])

    leaked_order = session.scalars(
        select(m.Order).filter_by(source_system_id=source_system.id, source_order_id="ORDER-REJECTED")
    ).first()
    leaked_payment = session.scalars(
        select(m.Payment).filter_by(source_system_id=source_system.id, source_payment_id="PAY-REJECTED")
    ).first()
    result.check(
        "rejected request performs NO database write (no Order/Payment row created)",
        leaked_order is None and leaked_payment is None,
    )

    rejected_run_count = len(
        session.scalars(
            select(m.IngestionRun).where(
                m.IngestionRun.source_system_id == source_system.id, m.IngestionRun.location_id == location.id,
                m.IngestionRun.status == "RUNNING",
            )
        ).all()
    )
    result.check(
        "rejecting the concurrent request never creates a second RUNNING IngestionRun row",
        rejected_run_count == 1,  # exactly the one this test manually registered
    )

    # =========================================================================
    # The original (synthetic) RUNNING import now completes -> guard released
    # -> the SAME restaurant/period can be intentionally imported again.
    # =========================================================================
    _finalize_import_run(
        running_run, ImportSummary(location_id=location.id, period_start=period_start, period_end=period_end),
        location_id=location.id, mode=MODE_BACKFILL,
    )
    session.add(running_run)
    session.commit()

    client3 = FakeCloverClient(merchant_id="GUARDMERCH1")
    summary3 = import_clover_period(
        session, location_id=location.id, period_start=period_start, period_end=period_end, client=client3,
    )
    session.commit()
    result.check(
        "the same period can be intentionally imported again AFTER the previous run completes",
        summary3.errors == [],
    )


def _test_failed_import_releases_guard(session: Session, result: ValidationResult) -> None:
    restaurant, location, source_system = _build_base_fixture(session, merchant_source_id="GUARDMERCH2")
    period_start = datetime(2026, 8, 1, tzinfo=UTC)
    period_end = datetime(2026, 8, 8, tzinfo=UTC)

    failing_client = RaisingCloverClient(merchant_id="GUARDMERCH2", raise_on_path_suffix="/payments")

    raised = False
    try:
        import_clover_period(
            session, location_id=location.id, period_start=period_start, period_end=period_end,
            client=failing_client,
        )
    except RuntimeError:
        raised = True
    result.check("a Clover fetch failure is never silently swallowed", raised)

    failed_run = session.scalars(
        select(m.IngestionRun)
        .where(m.IngestionRun.source_system_id == source_system.id, m.IngestionRun.location_id == location.id)
        .order_by(m.IngestionRun.id.desc())
    ).first()
    result.check("FAILED import: IngestionRun is marked FAILED", failed_run is not None and failed_run.status == "FAILED")
    result.check("FAILED import: the execution guard (lock_key) is released", failed_run is not None and failed_run.lock_key is None)
    result.check(
        "FAILED import: a safe error summary is stored, never a raw traceback",
        failed_run is not None and failed_run.notes is not None
        and "RuntimeError" in failed_run.notes and "Traceback" not in failed_run.notes,
    )

    # Guard released -> a fresh, working import for the SAME restaurant/period
    # is accepted — a failed import must never leave the system permanently
    # locked (task §4).
    working_client = FakeCloverClient(merchant_id="GUARDMERCH2")
    summary_retry = import_clover_period(
        session, location_id=location.id, period_start=period_start, period_end=period_end,
        client=working_client,
    )
    session.commit()
    result.check(
        "after a FAILED import, a fresh import for the same restaurant/period is accepted (guard was released)",
        summary_retry.errors == [],
    )


def _test_stale_running_import_is_auto_recovered(session: Session, result: ValidationResult) -> None:
    """CLOVER_DATA_ACQUISITION_ARCHITECTURE_001 §9/§10 — reproduces the real
    incident this task fixes: a process is killed mid-acquisition, leaving a
    RUNNING `IngestionRun` with its `lock_key` still set, forever (nothing
    is left running to ever mark it FAILED). The very next acquisition
    attempt for that restaurant must self-heal: detect the orphaned RUNNING
    row is older than `_STALE_RUN_THRESHOLD`, mark it FAILED with a clear
    auto-recovery note, release its lock, and proceed — never surfacing
    `ImportAlreadyRunningError` to a caller for a run that is genuinely
    dead, and never disturbing one that is merely old-ish but still
    plausibly alive."""
    restaurant, location, source_system = _build_base_fixture(session, merchant_source_id="GUARDMERCH3")
    period_start = datetime(2026, 9, 1, tzinfo=UTC)
    period_end = datetime(2026, 9, 5, tzinfo=UTC)

    # A RUNNING row exactly like a real interrupted process would leave
    # behind: started well past the staleness threshold, never finished.
    orphaned_run = m.IngestionRun(
        source_system_id=source_system.id, location_id=location.id,
        started_at=datetime.now(UTC) - timedelta(minutes=45),
        status="RUNNING", source_window_start=period_start, source_window_end=period_end,
        lock_key=f"CLOVER_ACQUISITION:{location.id}",
        notes="CLOVER_ACQUISITION mode=LIVE_SYNC location_id=%d; RUNNING" % location.id,
    )
    session.add(orphaned_run)
    session.commit()
    orphaned_run_id = orphaned_run.id

    client = FakeCloverClient(merchant_id="GUARDMERCH3")
    summary = import_clover_period(
        session, location_id=location.id, period_start=period_start, period_end=period_end, client=client,
        mode=MODE_BACKFILL,
    )
    session.commit()
    result.check(
        "a stale (>30min) RUNNING import is auto-recovered on the next attempt — no "
        "ImportAlreadyRunningError, the new acquisition proceeds normally",
        summary.errors == [],
    )

    recovered = session.get(m.IngestionRun, orphaned_run_id)
    session.refresh(recovered)
    result.check(
        "the orphaned run itself is marked FAILED with an explicit auto-recovery note, lock released",
        recovered.status == "FAILED" and recovered.lock_key is None
        and recovered.notes is not None and "AUTO-RECOVERED" in recovered.notes,
    )

    new_run = session.scalars(
        select(m.IngestionRun)
        .where(m.IngestionRun.source_system_id == source_system.id, m.IngestionRun.location_id == location.id)
        .order_by(m.IngestionRun.id.desc())
    ).first()
    result.check(
        "the auto-recovery produces a genuinely NEW run (not a reuse of the orphaned row's id)",
        new_run is not None and new_run.id != orphaned_run_id and new_run.status == "COMPLETE",
    )

    # A RUNNING row that is NOT yet stale must be left completely alone —
    # only a genuinely orphaned run is ever touched.
    fresh_running = m.IngestionRun(
        source_system_id=source_system.id, location_id=location.id,
        started_at=datetime.now(UTC) - timedelta(minutes=2),
        status="RUNNING", source_window_start=period_start, source_window_end=period_end,
        lock_key=f"CLOVER_ACQUISITION:{location.id}",
        notes="CLOVER_ACQUISITION mode=BACKFILL location_id=%d; RUNNING" % location.id,
    )
    session.add(fresh_running)
    session.commit()
    fresh_running_id = fresh_running.id

    rejected = False
    try:
        import_clover_period(
            session, location_id=location.id, period_start=period_start, period_end=period_end,
            client=FakeCloverClient(merchant_id="GUARDMERCH3"),
        )
    except ImportAlreadyRunningError:
        rejected = True
    result.check(
        "a RUNNING import that is NOT yet stale is still rejected normally — staleness recovery never "
        "disturbs a genuinely in-progress run",
        rejected,
    )
    still_running = session.get(m.IngestionRun, fresh_running_id)
    session.refresh(still_running)
    result.check(
        "the not-yet-stale run is completely untouched by the failed acquisition attempt",
        still_running.status == "RUNNING" and still_running.lock_key == f"CLOVER_ACQUISITION:{location.id}",
    )

    # Clean up so later checks in this module see a released guard.
    _finalize_import_run(
        still_running, ImportSummary(location_id=location.id, period_start=period_start, period_end=period_end),
        location_id=location.id, mode=MODE_BACKFILL,
    )
    session.add(still_running)
    session.commit()


def _test_status_report_and_manual_reap(session: Session, result: ValidationResult) -> None:
    """Task §10's explicit "status mechanism" — `get_latest_acquisition_status`
    is read-only (never mutates), and `reap_stale_acquisition_run` is the
    operator-facing manual counterpart to the automatic self-heal above,
    for on-demand recovery without first needing to trigger a new
    acquisition attempt."""
    restaurant, location, source_system = _build_base_fixture(session, merchant_source_id="GUARDMERCH4")
    period_start = datetime(2026, 9, 10, tzinfo=UTC)
    period_end = datetime(2026, 9, 12, tzinfo=UTC)

    no_status = get_latest_acquisition_status(session, location_id=location.id)
    result.check("status report: no acquisition run yet -> None, never fabricated", no_status is None)

    stale_run = m.IngestionRun(
        source_system_id=source_system.id, location_id=location.id,
        started_at=datetime.now(UTC) - timedelta(minutes=40),
        status="RUNNING", source_window_start=period_start, source_window_end=period_end,
        lock_key=f"CLOVER_ACQUISITION:{location.id}",
        notes="CLOVER_ACQUISITION mode=LIVE_SYNC location_id=%d; RUNNING" % location.id,
    )
    session.add(stale_run)
    session.commit()
    stale_run_id = stale_run.id

    status = get_latest_acquisition_status(session, location_id=location.id)
    result.check(
        "status report: a stale RUNNING run is correctly flagged is_stale=True, mode_hint parsed, "
        "and nothing was modified merely by checking",
        status is not None and status.run_id == stale_run_id and status.status == "RUNNING"
        and status.is_stale is True and status.mode_hint == "LIVE_SYNC",
    )
    unchanged = session.get(m.IngestionRun, stale_run_id)
    session.refresh(unchanged)
    result.check(
        "status report never mutates: the run is still RUNNING with its lock intact after being checked",
        unchanged.status == "RUNNING" and unchanged.lock_key is not None,
    )

    reaped_id = reap_stale_acquisition_run(session, location_id=location.id)
    result.check("manual reap returns the id of the run it recovered", reaped_id == stale_run_id)

    reaped_row = session.get(m.IngestionRun, stale_run_id)
    session.refresh(reaped_row)
    result.check(
        "manual reap marks the run FAILED and releases its lock, same as the automatic path",
        reaped_row.status == "FAILED" and reaped_row.lock_key is None,
    )

    second_reap = reap_stale_acquisition_run(session, location_id=location.id)
    result.check("reaping again when nothing is stale/RUNNING returns None, changes nothing", second_reap is None)
