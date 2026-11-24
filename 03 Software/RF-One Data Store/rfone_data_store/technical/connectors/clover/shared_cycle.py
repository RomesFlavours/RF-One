"""The Clover side of the shared RF-One acquisition engine
(CLOVER_ACQUISITION_ENGINE_001, Product Owner 2026-11-22).

One download for ONE site (Location), with that site's own merchant identity
and credentials (`acquisition.get_location_client`), its own lock, its own
checkpoints and its own outcome. It composes the acquisition steps that
already exist — nothing here fetches, maps or writes Clover data itself:

* **Ordinary (SCHEDULED)** — 1. new records: `acquisition.import_clover_period`
  over `start -> now` (full scope, `MODE_SYNC_NOW`), where `start` is given by
  the caller: the end of the site's last COMPLETE ordinary download (minus an
  overlap) or of its last COMPLETE acquisition — never a PARTIAL one; 2. updates:
  `correction_sync.run_correction_cycle` over every resource. The download is
  COMPLETE only when both steps ended COMPLETE; an acquisition that ended
  PARTIAL (with record errors) makes the download FAILED.
* **Live (LIVE)** — only `correction_sync.run_correction_cycle`, limited to the
  resources the request asked for (Orders and Payments new or changed since
  their own checkpoints, recent Refunds). Nothing else is read.

Only a COMPLETE download carries a covered period (`CycleOutcome.coverage_*`);
a failed or busy attempt never does. Every write is an upsert by Clover
identity, so repeating a download never duplicates data.

Callers outside the connector use `rfone_data_store.operational_acquisition`,
never this module directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session, sessionmaker

from ....ingestion.common import utc_now
from .acquisition import (
    MODE_SYNC_NOW,
    CloverReadClient,
    ImportAlreadyRunningError,
    _acquire_import_lock,
    _aware_utc,
    _resolve_clover_merchant,
    _safe_error_summary,
    get_location_client,
    import_clover_period,
    location_is_active,
)
from .acquisition_jobs import _Heartbeat
from .correction_sync import ALL_RESOURCES, run_correction_cycle

UTC = timezone.utc

TRIGGER_SCHEDULED = "SCHEDULED"
TRIGGER_LIVE = "LIVE"

OUTCOME_COMPLETE = "COMPLETE"
OUTCOME_FAILED = "FAILED"
# The site's lock is held by another acquisition: nothing was done, the
# caller tries again later.
OUTCOME_BUSY = "BUSY"

NO_STARTING_POINT = (
    "RF-One has no completed download or Historical Backfill for this site yet, so there is no point to "
    "download from. Run a Historical Backfill for the site first (Clover Acquisition page).")


@dataclass
class CycleOutcome:
    location_id: int
    status: str
    ingestion_run_id: int | None = None
    coverage_start: datetime | None = None
    coverage_end: datetime | None = None
    messages: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        return "; ".join(self.messages)[:4000]

    def fail(self, message: str) -> "CycleOutcome":
        self.status = OUTCOME_FAILED
        self.coverage_start = self.coverage_end = None
        self.messages.append(message)
        return self

    def busy(self, message: str) -> "CycleOutcome":
        self.status = OUTCOME_BUSY
        self.coverage_start = self.coverage_end = None
        self.messages.append(message)
        return self


def _import_new_records(
    session: Session, *, location_id: int, source_system_id: int, start: datetime, now: datetime,
    client: CloverReadClient, session_factory: sessionmaker[Session] | None, outcome: CycleOutcome,
) -> bool:
    """Step 1 of the ordinary download. Returns False when it must stop here."""
    try:
        run = _acquire_import_lock(
            session, location_id=location_id, source_system_id=source_system_id,
            period_start=start, period_end=now, mode=MODE_SYNC_NOW,
        )
    except ImportAlreadyRunningError:
        outcome.busy("Another acquisition is running for this site.")
        return False
    outcome.ingestion_run_id = run.id
    try:
        if session_factory is not None:
            with _Heartbeat(session_factory, run.id):
                import_clover_period(session, location_id=location_id, period_start=start, period_end=now,
                                     client=client, mode=MODE_SYNC_NOW, ingestion_run=run)
        else:
            import_clover_period(session, location_id=location_id, period_start=start, period_end=now,
                                 client=client, mode=MODE_SYNC_NOW, ingestion_run=run)
        session.commit()
    except Exception as exc:  # noqa: BLE001 — the engine already recorded FAILED and released the lock
        session.rollback()
        outcome.fail(f"New records: {_safe_error_summary(exc)}")
        return False
    session.refresh(run)
    if run.status != "COMPLETE":
        outcome.fail(f"New records: acquisition ended {run.status}. {run.error_summary or ''}".strip())
        return False
    outcome.messages.append(f"New records: COMPLETE ({start.isoformat()} -> {now.isoformat()}).")
    return True


def run_location_cycle(
    session: Session, *, location_id: int, trigger: str, start: datetime | None = None,
    resources: tuple[str, ...] = ALL_RESOURCES, client: CloverReadClient | None = None,
    now: datetime | None = None, session_factory: sessionmaker[Session] | None = None,
) -> CycleOutcome:
    """One download for one site (see the module docstring). Never touches
    another site. `client` replaces the site's own Clover client (tests)."""
    now = _aware_utc(now or utc_now())
    outcome = CycleOutcome(location_id=location_id, status=OUTCOME_COMPLETE)
    merchant = _resolve_clover_merchant(session, location_id)
    if merchant is None:
        return outcome.fail(f"location_id={location_id} is not a Clover site with a merchant identifier.")
    if not location_is_active(session, location_id):
        return outcome.fail(f"location_id={location_id} is not active: nothing is downloaded until it is activated.")
    source_system_id, merchant_id = merchant
    try:
        resolved = client or get_location_client(merchant_id)
    except Exception as exc:  # noqa: BLE001 — a missing connection is this site's outcome only
        return outcome.fail(_safe_error_summary(exc))

    if trigger == TRIGGER_SCHEDULED:
        resources = ALL_RESOURCES
        if start is None:  # the caller gives only a COMPLETE starting point (never a PARTIAL one)
            return outcome.fail(NO_STARTING_POINT)
        start = _aware_utc(start)
        if not _import_new_records(
            session, location_id=location_id, source_system_id=source_system_id, start=start, now=now,
            client=resolved, session_factory=session_factory, outcome=outcome,
        ):
            return outcome
    elif trigger != TRIGGER_LIVE:
        raise ValueError(f"unknown trigger {trigger!r}")

    try:
        correction = run_correction_cycle(session, location_id=location_id, client=resolved, now=now,
                                          resources=tuple(resources))
    except Exception as exc:  # noqa: BLE001 — recorded as this download's outcome
        session.rollback()
        return outcome.fail(f"Updates: {_safe_error_summary(exc)}")
    if correction is None:
        return outcome.busy("Updates: another acquisition is running for this site.")
    failed = [r for r in correction.results if r.status != "COMPLETE"]
    if correction.employee_errors or failed:
        outcome.messages.extend(correction.employee_errors)
        for r in failed:
            outcome.messages.append(f"Updates ({r.resource_type}): {r.status} {'; '.join(r.errors[:3])}".strip())
        return outcome.fail("The download did not complete.")
    outcome.messages.append(f"Updates ({', '.join(r.resource_type for r in correction.results)}): COMPLETE.")
    if trigger == TRIGGER_SCHEDULED:
        outcome.coverage_start, outcome.coverage_end = start, now
    return outcome
