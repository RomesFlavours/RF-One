"""TECHNICAL_CONNECTORS_STRUCTURE_001 / CLOVER_DATA_ACQUISITION_ARCHITECTURE_001
— the Clover Technical Connector's data acquisition service.

`technical/connectors/clover` is a Technical cross-domain connector
(`00 Core` = universal logic; `01 Domains` = functional/business logic;
`Technical` = shared technical infrastructure; `Technical/Connectors` =
external system integrations usable by Core and/or any Domain). It owns
ONLY Clover integration concerns — authentication, the API client, sync/
polling, checkpoints, retries, idempotent upsert, external identifier/
location mapping — never Tip calculation logic, Restaurant business rules,
Sales/Server-Performance/Server-Copilot logic, or any other Domain-specific
decision logic. It has no concept of "Restaurant" at all: its unit of
ownership is the technical/organizational `Location` (and the `Merchant`/
`SourceSystem` it belongs to) already defined in `models.py` — the existing
RF-One organizational model, not a new framework invented for this. Domains
(Tips, and in the future Server Copilot, Server Performance, Sales) resolve
WHICH Location they care about (e.g. Restaurant -> RestaurantLocation ->
Location, a Restaurant-Domain join) and pass that `location_id` in; this
connector never performs that resolution itself.

Originally built inside `tips/clover_import_service.py`, then relocated to
`ingestion/clover/acquisition.py` (CLOVER_DATA_ACQUISITION_ARCHITECTURE_001 —
"outside Tips, Restaurant-level shared acquisition"). Relocated AGAIN here
(TECHNICAL_CONNECTORS_STRUCTURE_001): Clover acquisition is not a
Restaurant-level concern either — it is a Technical connector, no different
in kind from a future ADP/Mercury/OpenTable/Resy connector, each of which
will need the exact same shape (its own external account/location, its own
API client, its own sync/backfill/idempotency/concurrency mechanics) without
knowing anything about Restaurant, Tips, or any other Domain.

This module owns the one shared acquisition path every mode uses:

- **Historical Backfill** (`03 Software/Tips/app.py`'s "Historical Backfill"
  action, or any future module's own explicit re-import UI): an
  operator-chosen date range, run on demand.
- **Live Sync** (`technical/connectors/clover/live_sync.py`): a short,
  recent, automatically-advancing window, run on a tight interval for
  near-real-time operation (seconds, not minutes).

Both call the exact same `import_clover_period()` — there is no second
ingestion system, no duplicated fetch/mapping/upsert logic, and no
duplicated concurrency guard. The two modes differ in HOW the
`period_start`/`period_end` window is chosen and how often the call is
made, AND (CLOVER_LIVE_SYNC_SCOPE_REDUCTION_001) in which entities each one
refreshes: Live Sync keeps only what needs continuous refresh (Orders,
Order Items, Order Item Modifiers, Payments, Payment Tips, Refunds, Order
Fees, Shifts, Employees); Historical Backfill additionally refreshes
catalog/reference data (Items, Categories, Modifier Groups/Modifiers, Tax
Rates, Discount Definitions, Order Types, Tenders, Devices, Source Roles)
plus Order Item Tax and Order-level Discounts, which depend on that
catalog. `mode=` is recorded on the `IngestionRun` for observability and
is the one flag `import_clover_period()` itself branches on for this.

Reuses the exact canonical schema and the exact pure raw-dict ->
column-kwargs mapping functions (`mapping.py`) and the exact idempotent
upsert-by-source-identity helper (`ingest.upsert`) that `ingest_clover.py`'s
full historical bulk pipeline already uses and has already populated the
operational database with.

Menu/catalog detail (Item, Category, ModifierGroup/Modifier, TaxRate,
DiscountDefinition, OrderType, SourceRole), per-item tax, and Order-level
discounts are ingested via `historical_backfill_detail.py` — a separate
file, not a second architecture: it reuses this module's own `mapping.py`/
`ingest.upsert()` primitives. Historical Backfill ONLY
(CLOVER_HISTORICAL_BACKFILL_EXTRACTOR_V1) — none of that catalog/reference
data needs continuous refresh, per CLOVER_LIVE_SYNC_SCOPE_REDUCTION_001,
which reverted a brief period (CLOVER_LIVE_SYNC_EXTRACTOR_V1) where Live
Sync also called it. Live Sync still gets OrderItem/OrderItemModifier
(the two transactional entities in that set it actually keeps) via that
same file's separate, smaller `ingest_order_item_and_modifier_detail()`,
which resolves against whatever catalog is already canonical instead of
refreshing it. `ingest_clover.py`'s own older full pipeline still
independently covers the same ground from an on-disk bundle; none of these
three paths read each other's writes.

READ-ONLY against Clover: only `CloverClient.get()` (a GET-only client with
no write methods at all) is ever used. Never logs or exposes the API token,
customer names, cardholder names, card numbers, or any `cardTransaction`
field.

Provider Mirror (CLOVER_PROVIDER_MIRROR_WIRING): every raw record this
module fetches (Employee, Tender, Device, Shift, Order, Payment, Refund) is
also persisted, unmapped and provider-shaped, into the existing generic
`SourceRecord` table via `_mirror_source_record()` — the same call site that
performs the canonical upsert, immediately after it, using the one
`retrieved_at` timestamp captured for the whole run. `SourceRecord` remains
append-only (no unique constraint of its own) and is never read by this
module, `ingest.py`'s bulk pipeline, or any Domain — it exists purely for
reconciliation/audit/recovery/reprocessing. The one exception to "provider-
shaped, unmapped": a Payment's `cardTransaction` field is stripped before
mirroring (`_payment_mirror_payload()`), honoring the "never persist a
cardTransaction field" commitment above, which previously held trivially
(nothing raw was ever persisted at all) and must now be actively enforced
now that raw Payment payloads are.

Concurrency guard (originally TIPS_IMPORT_CONCURRENCY_GUARD_001, generalized
by CLOVER_DATA_ACQUISITION_ARCHITECTURE_001, now Location-scoped rather than
Restaurant-scoped): `IngestionRun.lock_key` is `CLOVER_ACQUISITION:
{location_id}` — ONE lock shared by every mode for a given Location, because
the failure it prevents (`sqlite3.OperationalError: database is locked`) is
a property of the one shared database file, not of which module or mode
triggered the write. A Live Sync cycle and a Historical Backfill for the
same Location can never write concurrently; whichever loses the race gets a
clean rejection, never a corrupt half-write.

Interruption recovery: a hard process kill (not a Python exception) leaves
the RUNNING row exactly as committed — the guard's own design already keeps
that commit in a separate, short transaction from the heavy fetch/upsert
work, so a killed process's partial work was never committed at all
(SQLite's own atomicity guarantees no partial rows survive). The RUNNING row
itself, however, never transitions to FAILED on its own (nothing is left to
run that code) and would otherwise block every future acquisition for that
Location forever. `_reap_if_stale`/`get_latest_acquisition_status`/
`reap_stale_acquisition_run` below are the self-healing mechanism: any
future acquisition attempt that finds a RUNNING lock older than
`_STALE_RUN_THRESHOLD` automatically marks it FAILED (clearly noted as
auto-recovered) and proceeds, and an operator can also check/force this
explicitly via `clover_acquisition_status.py`.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .... import models as m
from ....ingestion.common import payload_hash, utc_now
from . import historical_backfill_detail, mapping
from .ingest import upsert

# Same reuse boundary `enrichment.py` already established: make the
# existing, already-reviewed read-only Clover client/pagination primitives
# importable without pulling any Clover Data Explorer *business logic*
# (dashboard CSV reconstruction, discovery reports) into this path.
_CLOVER_EXPLORER_DIR = Path(__file__).resolve().parents[5] / "Clover Data Explorer"
if str(_CLOVER_EXPLORER_DIR) not in sys.path:
    sys.path.insert(0, str(_CLOVER_EXPLORER_DIR))

from clover_explorer.pagination import paginate  # noqa: E402

UTC = timezone.utc

# How long a RUNNING acquisition may run before a future attempt treats it
# as orphaned. Generous enough that a legitimately large Historical Backfill
# (a wide date range, paginated against the live Clover API) is never killed
# out from under itself; short enough that a real crash/kill self-heals well
# within a single operator's working session.
_STALE_RUN_THRESHOLD = timedelta(minutes=30)

MODE_BACKFILL = "BACKFILL"
MODE_LIVE_SYNC = "LIVE_SYNC"


class CloverReadClient(Protocol):
    """The minimal shape this module needs from a Clover client — satisfied
    by the real `clover_explorer.client.CloverClient` in production, and by
    a small fake in tests (never contact Clover production from automated
    tests)."""

    merchant_id: str

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any: ...


def get_default_client() -> CloverReadClient:
    """The real, read-only, production-configured Clover client — imported
    lazily so a test that always supplies its own fake `client=` never needs
    Clover credentials to exist at all."""
    from .enrichment import get_client

    return get_client()


@dataclass
class EmployeeMismatch:
    order_source_id: str
    order_employee_source_id: str | None
    payment_source_id: str
    payment_employee_source_id: str | None


@dataclass
class ImportSummary:
    location_id: int
    period_start: datetime
    period_end: datetime

    payments_imported: int = 0  # new Payment rows created
    payments_updated: int = 0  # existing Payment rows whose facts changed
    orders_imported: int = 0  # new Order rows created
    orders_updated: int = 0  # existing Order rows whose facts changed

    voluntary_tips_count: int = 0  # payments in this run with tipAmount present and > 0
    voluntary_tips_total_minor: int = 0
    zero_tip_payments_count: int = 0  # tipAmount present and == 0
    missing_tip_amount_payments_count: int = 0  # tipAmount key absent entirely

    automatic_gratuity_count: int = 0  # OrderFee rows touched this run
    automatic_gratuity_total_minor: int = 0

    split_payment_orders_count: int = 0

    refunds_found: int = 0

    employees_resolved: int = 0  # distinct Employees upserted/resolved this run
    shifts_imported: int = 0  # Shift (clock-in/clock-out) rows touched, within the period

    employee_mismatches: list[EmployeeMismatch] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    # CLOVER_CONTINUOUS_SYNCHRONIZATION_ARCHITECTURE §2 PRECHECK finding —
    # distinct from `errors` (which also collects per-RECORD issues, e.g. one
    # unresolved Order reference, that do not mean the period's own
    # createdTime-windowed scan was incomplete). True only when a scan this
    # run DEPENDS ON to claim "this window is fully covered" — the Payments
    # or Refunds createdTime-filtered fetch itself — did not succeed. Read by
    # `_finalize_import_run` to decide COMPLETE/PARTIAL vs FAILED: a run that
    # never actually completed its windowed scan must never be eligible to
    # advance `compute_next_sync_window`'s or `freshness._is_range_covered`'s
    # checkpoint, even though some other resource in the same cycle (e.g.
    # Employees, or Orders reached via a partial Payments page) may have
    # succeeded — see Task report "Live Cursor safety" for the verified gap
    # this closes.
    window_scan_failed: bool = False

    @property
    def employee_mismatches_count(self) -> int:
        return len(self.employee_mismatches)


@dataclass
class AcquisitionRunStatus:
    """Read-only status snapshot ("status mechanism")."""

    run_id: int
    status: str
    mode_hint: str | None  # parsed best-effort from `notes`; never authoritative
    started_at: datetime
    finished_at: datetime | None
    is_stale: bool
    notes: str | None


def _resolve_clover_merchant(session: Session, location_id: int) -> tuple[int, str] | None:
    """Returns `(source_system_id, source_location_id/merchant_id)` for
    `location_id`, or `None` if it is not a Clover-sourced Location with a
    resolved external identifier. Purely technical: this connector has no
    concept of Restaurant or any other Domain-level ownership — a caller
    (a Domain module) is responsible for deciding WHICH Location it wants
    acquired, e.g. via its own Restaurant -> RestaurantLocation -> Location
    join; this module never performs that resolution itself, and does not
    (re)create Merchant/Location either — that is `ingest_clover.py`'s own
    onboarding concern, out of scope here."""
    location = session.get(m.Location, location_id)
    if location is None or location.source_location_id is None:
        return None
    source_system = session.get(m.SourceSystem, location.source_system_id)
    if source_system is None or source_system.code != "CLOVER":
        return None
    return source_system.id, location.source_location_id


def get_order_settlement_time(session: Session, order_id: int) -> datetime | None:
    """TIP_DISTRIBUTION_ENGINE_FUNCTIONAL_SPEC_001 §5 — the Order Settlement
    Time: the timestamp of the LAST SUCCESSFUL Payment that completes the
    Order. Deliberately NOT the moment a tip was later entered/adjusted in
    Clover (`Payment.modified_at` is never used here), and deliberately not
    a persisted/cached column — this is a pure function of already-ingested
    `Payment` rows, always exactly reproducible from source facts. Kept here
    (rather than inside Tips) because it is a generic derived fact over
    already-acquired Payments any Domain may need (Sales reporting, Server
    Performance timing — not only Tips), not a Tips-specific calculation.
    Returns `None` only when the Order has no successful Payment at all."""
    return session.scalar(
        select(func.max(m.Payment.created_at)).where(
            m.Payment.order_id == order_id, m.Payment.result == "SUCCESS",
        )
    )


def _mirror_source_record(
    session: Session, *, ingestion_run_id: int, source_system_id: int,
    entity_type: str, source_id: str | None, retrieved_at: datetime, raw: dict[str, Any],
) -> None:
    """CLOVER_PROVIDER_MIRROR_WIRING — Provider Mirror write. Persists the
    raw, provider-shaped payload this connector just fetched into the
    existing `SourceRecord` table, alongside (never instead of) the
    canonical upsert this same call site already performs.

    Append-only by design: `SourceRecord` has no unique constraint of its
    own (only a non-unique lookup index — see `models.py`), so re-fetching
    the same Clover record on a later Backfill or Live Sync cycle ADDS a new
    `SourceRecord` row rather than overwriting the previous one. Two
    retrievals of the same `source_id` are therefore always both preserved;
    `payload_hash` lets a later reader tell without re-diffing the full JSON
    whether they actually differ (a real Clover-side edit) or are
    byte-for-byte identical (a routine re-poll/re-backfill of an unchanged
    record) — this function never itself skips a write based on the hash,
    it only stamps it for that later comparison.

    Uses `raw_json` (never `raw_path`): unlike `ingest.py`'s bulk pipeline —
    which reads from an on-disk `CloverSourceBundle` and can cheaply
    reference the file it already wrote to disk — this connector fetches
    directly from the live Clover API with no bundle/file of its own to
    point `raw_path` at, so `raw_json` is the only faithful way to mirror
    what was retrieved.

    This is a second, independent effect of an already-fetched record. It
    never influences, gates, or gets read back by the canonical upsert that
    the same call site separately performs on the same raw dict.

    Skipped (no row written) if `source_id` is falsy — a raw record with no
    external id of its own cannot be traced back to anything and would
    violate `SourceRecord.source_id`'s own NOT NULL constraint."""
    if not source_id:
        return
    session.add(
        m.SourceRecord(
            ingestion_run_id=ingestion_run_id,
            source_system_id=source_system_id,
            entity_type=entity_type,
            source_id=source_id,
            retrieved_at=retrieved_at,
            payload_hash=payload_hash(raw),
            raw_path=None,
            raw_json=raw,
        )
    )


def _payment_mirror_payload(payment_raw: dict[str, Any]) -> dict[str, Any]:
    """The Provider Mirror must stay a faithful, provider-shaped copy, but
    this module's own existing commitment (see module docstring) is to
    never persist a `cardTransaction` field anywhere — Clover's card/tender
    metadata for the payment. Every other field of the raw Payment is
    mirrored unchanged; this is the one redaction applied before a raw
    payload is written to `SourceRecord`."""
    if "cardTransaction" not in payment_raw:
        return payment_raw
    redacted = dict(payment_raw)
    redacted.pop("cardTransaction", None)
    return redacted


def _get_or_create(session: Session, model: type, unique_filter: dict[str, Any], values: dict[str, Any]) -> tuple[Any, bool]:
    """Like `ingest.upsert`, but also reports whether the row was newly
    created — needed for the `*_imported` vs `*_updated` counts, which the
    shared `upsert()` helper itself does not track."""
    existing = session.scalars(select(model).filter_by(**unique_filter)).first()
    if existing is not None:
        for key, value in values.items():
            setattr(existing, key, value)
        return existing, False
    obj = model(**unique_filter, **values)
    session.add(obj)
    return obj, True


def _existing_ids_by_source(session: Session, model: type, *, source_system_id: int, source_id_column: str) -> dict[str, int]:
    """CLOVER_LIVE_SYNC_SCOPE_REDUCTION_001 — reads whatever this catalog's
    canonical rows already are in the database (typically populated by a
    prior Historical Backfill run), without any Clover network call. Used
    by Live Sync for catalogs it no longer refreshes continuously (Tender,
    Device — and, in `historical_backfill_detail.py`, Item/Modifier): the
    FK still resolves correctly against anything already known; a source_id
    Live Sync has never seen before (because it was never Backfilled) simply
    stays unresolved (`None`), the same graceful-degradation shape already
    used throughout this codebase for any other unresolved reference."""
    rows = session.execute(
        select(getattr(model, source_id_column), model.id).where(model.source_system_id == source_system_id)
    ).all()
    return {row[0]: row[1] for row in rows if row[0]}


def _fetch_reference_catalogs(
    client: CloverReadClient, session: Session, *, location_id: int, source_system_id: int,
    ingestion_run_id: int, retrieved_at: datetime, mode: str,
) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
    """Employees — refreshed live every call, both modes (task's own
    "Employees" retained-entity list). Tenders and Devices — refreshed live
    only for Historical Backfill (CLOVER_LIVE_SYNC_SCOPE_REDUCTION_001: both
    are explicitly removed from Live Sync's continuous refresh); for Live
    Sync, their id maps are instead read from whatever is already canonical
    (`_existing_ids_by_source`), so `Payment.tender_id`/`device_id` still
    resolve for anything Historical Backfill has already discovered, without
    Live Sync ever calling `/tenders`/`/devices` itself. Returns
    `(employee_by_source_id, tender_by_source_id, device_by_source_id)`."""
    employee_by_source_id: dict[str, int] = {}
    result = paginate(client, f"/v3/merchants/{client.merchant_id}/employees")
    for raw in result.elements if result.ok else []:
        values = mapping.map_employee(raw)
        source_id = values.pop("source_employee_id")
        if not source_id:
            continue
        obj, _ = _get_or_create(
            session, m.Employee, {"source_system_id": source_system_id, "source_employee_id": source_id},
            {**values, "location_id": location_id},
        )
        session.flush()
        employee_by_source_id[source_id] = obj.id
        _mirror_source_record(
            session, ingestion_run_id=ingestion_run_id, source_system_id=source_system_id,
            entity_type="employee", source_id=source_id, retrieved_at=retrieved_at, raw=raw,
        )

    if mode == MODE_BACKFILL:
        tender_by_source_id: dict[str, int] = {}
        result = paginate(client, f"/v3/merchants/{client.merchant_id}/tenders")
        for raw in result.elements if result.ok else []:
            values = mapping.map_tender(raw)
            source_id = values.pop("source_tender_id")
            if not source_id:
                continue
            obj, _ = _get_or_create(
                session, m.Tender, {"source_system_id": source_system_id, "source_tender_id": source_id},
                {**values, "location_id": location_id},
            )
            session.flush()
            tender_by_source_id[source_id] = obj.id
            _mirror_source_record(
                session, ingestion_run_id=ingestion_run_id, source_system_id=source_system_id,
                entity_type="tender", source_id=source_id, retrieved_at=retrieved_at, raw=raw,
            )

        device_by_source_id: dict[str, int] = {}
        result = paginate(client, f"/v3/merchants/{client.merchant_id}/devices")
        for raw in result.elements if result.ok else []:
            values = mapping.map_device(raw)
            source_id = values.pop("source_device_id")
            if not source_id:
                continue
            obj, _ = _get_or_create(
                session, m.Device, {"source_system_id": source_system_id, "source_device_id": source_id},
                {**values, "location_id": location_id},
            )
            session.flush()
            device_by_source_id[source_id] = obj.id
            _mirror_source_record(
                session, ingestion_run_id=ingestion_run_id, source_system_id=source_system_id,
                entity_type="device", source_id=source_id, retrieved_at=retrieved_at, raw=raw,
            )
    else:
        tender_by_source_id = _existing_ids_by_source(
            session, m.Tender, source_system_id=source_system_id, source_id_column="source_tender_id",
        )
        device_by_source_id = _existing_ids_by_source(
            session, m.Device, source_system_id=source_system_id, source_id_column="source_device_id",
        )

    return employee_by_source_id, tender_by_source_id, device_by_source_id


def _fetch_and_ingest_shifts(
    client: CloverReadClient, session: Session, *, period_start: datetime, period_end: datetime,
    source_system_id: int, employee_by_source_id: dict[str, int],
    ingestion_run_id: int, retrieved_at: datetime,
) -> int:
    """Clock-in/clock-out source facts, using Clover's `/shifts` endpoint
    and `mapping.map_shift()`. Confirmed empirically (read-only GET, no
    write) that this endpoint does NOT support a server-side time-range
    filter or `orderBy` on `inTime` (both return HTTP 400) — unlike
    Payments/Refunds. The full collection is therefore paginated in full and
    filtered client-side to Shifts whose clock-in falls within the requested
    period before upserting, so a run does not repeatedly rewrite a growing
    history of unrelated older Shifts."""
    result = paginate(client, f"/v3/merchants/{client.merchant_id}/shifts")
    if not result.ok:
        return 0

    touched = 0
    for raw in result.elements:
        clock_in = raw.get("inTime")
        if clock_in is None or not (
            int(period_start.astimezone(UTC).timestamp() * 1000)
            <= clock_in
            <= int(period_end.astimezone(UTC).timestamp() * 1000)
        ):
            continue

        values = mapping.map_shift(raw)
        source_id = values.pop("source_shift_id")
        employee_source_id = values.pop("employee_source_id")
        override_in_source_id = values.pop("override_in_employee_source_id")
        override_out_source_id = values.pop("override_out_employee_source_id")

        _mirror_source_record(
            session, ingestion_run_id=ingestion_run_id, source_system_id=source_system_id,
            entity_type="shift", source_id=source_id, retrieved_at=retrieved_at, raw=raw,
        )

        employee_id = employee_by_source_id.get(employee_source_id) if employee_source_id else None
        if employee_id is None:
            continue  # Shift.employee_id is NOT NULL — cannot ingest an orphaned shift

        upsert(
            session, m.Shift, {"source_system_id": source_system_id, "source_shift_id": source_id},
            {
                **values, "employee_id": employee_id,
                "override_in_employee_id": (
                    employee_by_source_id.get(override_in_source_id) if override_in_source_id else None
                ),
                "override_out_employee_id": (
                    employee_by_source_id.get(override_out_source_id) if override_out_source_id else None
                ),
            },
        )
        touched += 1

    session.flush()
    return touched


def _ingest_order(
    session: Session, order_raw: dict[str, Any], *, location_id: int, source_system_id: int,
    employee_by_source_id: dict[str, int], ingestion_run_id: int, retrieved_at: datetime,
) -> tuple[m.Order, bool]:
    values = mapping.map_order(order_raw)
    order_source_id = values.pop("source_order_id")
    employee_source_id = values.pop("source_employee_id")
    employee_source_id_fk = values.pop("employee_source_id")
    values.pop("order_type_source_id")  # not resolved here — out of scope for this module
    values.pop("device_source_id")  # not resolved here — device attribution is a Sales/Payment concern

    employee_id = employee_by_source_id.get(employee_source_id_fk) if employee_source_id_fk else None

    order, is_new = _get_or_create(
        session, m.Order, {"source_system_id": source_system_id, "source_order_id": order_source_id},
        {
            **values,
            "location_id": location_id,
            "source_employee_id": employee_source_id,
            "employee_id": employee_id,
        },
    )
    session.flush()
    _mirror_source_record(
        session, ingestion_run_id=ingestion_run_id, source_system_id=source_system_id,
        entity_type="order", source_id=order_source_id, retrieved_at=retrieved_at, raw=order_raw,
    )
    return order, is_new


def _ingest_fee_line_items(
    session: Session, order_raw: dict[str, Any], order: m.Order, *, source_system_id: int, summary: ImportSummary,
) -> None:
    """The synthetic Order-level Gratuity/Service-Charge line item only,
    identified by `isOrderFee: true`. The charged amount is always read from
    `lineItem.price` — never derived from `percentage`. Never merged into
    `PaymentTip`.

    Called exactly ONCE per Order (from the Order-ingestion loop, never from
    the per-Payment loop), so a gratuity line item is counted exactly once
    regardless of how many Payments settle that Order."""
    line_items = (order_raw.get("lineItems") or {}).get("elements", [])
    for li_raw in line_items:
        if not li_raw.get("isOrderFee"):
            continue
        fee_values = mapping.map_order_fee(li_raw)
        source_line_item_id = fee_values.get("source_line_item_id")
        existing = session.scalars(
            select(m.OrderFee).filter_by(order_id=order.id, source_line_item_id=source_line_item_id)
        ).first()
        if existing is not None:
            for key, value in fee_values.items():
                if key != "source_line_item_id":
                    setattr(existing, key, value)
        else:
            session.add(m.OrderFee(order_id=order.id, source_system_id=source_system_id, **fee_values))
            session.flush()
        summary.automatic_gratuity_count += 1
        summary.automatic_gratuity_total_minor += fee_values.get("amount") or 0


def _ingest_payment(
    session: Session, payment_raw: dict[str, Any], *, order_id: int, source_system_id: int,
    employee_by_source_id: dict[str, int], tender_by_source_id: dict[str, int],
    device_by_source_id: dict[str, int], summary: ImportSummary,
    ingestion_run_id: int, retrieved_at: datetime,
) -> m.Payment:
    values = mapping.map_payment(payment_raw)
    source_payment_id = values.pop("source_payment_id")
    values.pop("order_source_id")
    employee_source_id_fk = values.pop("employee_source_id")
    tender_source_id = values.pop("tender_source_id")
    device_source_id = values.pop("device_source_id")

    employee_id = employee_by_source_id.get(employee_source_id_fk) if employee_source_id_fk else None
    tender_id = tender_by_source_id.get(tender_source_id) if tender_source_id else None
    device_id = device_by_source_id.get(device_source_id) if device_source_id else None

    payment, is_new = _get_or_create(
        session, m.Payment, {"source_system_id": source_system_id, "source_payment_id": source_payment_id},
        {
            **values, "order_id": order_id, "employee_id": employee_id, "tender_id": tender_id,
            "device_id": device_id, "device_source_id": device_source_id,
        },
    )
    session.flush()
    if is_new:
        summary.payments_imported += 1
    else:
        summary.payments_updated += 1

    _mirror_source_record(
        session, ingestion_run_id=ingestion_run_id, source_system_id=source_system_id,
        entity_type="payment", source_id=source_payment_id, retrieved_at=retrieved_at,
        raw=_payment_mirror_payload(payment_raw),
    )

    # Card tips can finalize after Payment.createdTime, so a re-import MUST
    # refresh the tip from Clover's current value, never treat the first
    # observation as final — `_get_or_create` above already does this for
    # every Payment column via plain attribute overwrite; the same applies
    # to PaymentTip below.
    tip_values = mapping.map_payment_tip(payment_raw)
    if tip_values["source_present"]:
        existing_tip = session.get(m.PaymentTip, payment.id)
        if existing_tip is not None:
            existing_tip.amount = tip_values["amount"]
            existing_tip.source_present = True
        else:
            session.add(m.PaymentTip(payment_id=payment.id, amount=tip_values["amount"], source_present=True))
        amount = tip_values["amount"] or 0
        if amount > 0:
            summary.voluntary_tips_count += 1
            summary.voluntary_tips_total_minor += amount
        else:
            summary.zero_tip_payments_count += 1
    else:
        # No PaymentTip row at all — "tip field absent from source", never
        # coerced to zero. If a PREVIOUS import already recorded a present
        # tip for this exact payment, a now-absent key is treated as an
        # anomaly to surface for review rather than silently deleted.
        existing_tip = session.get(m.PaymentTip, payment.id)
        if existing_tip is not None:
            summary.errors.append(
                f"Payment {source_payment_id[:4]}...: previously recorded tipAmount is now absent on "
                "re-fetch — left unchanged, not deleted; review manually."
            )
        summary.missing_tip_amount_payments_count += 1

    return payment


def _ingest_refund(
    session: Session, refund_raw: dict[str, Any], *, source_system_id: int,
    order_by_source_id: dict[str, int], payment_by_source_id: dict[str, int],
    employee_by_source_id: dict[str, int], device_by_source_id: dict[str, int],
    ingestion_run_id: int, retrieved_at: datetime,
) -> None:
    """The Refund resource is the ONLY authoritative refund source;
    `Payment.result == SUCCESS` is never assumed to mean "never refunded"."""
    values = mapping.map_refund(refund_raw)
    source_refund_id = values.pop("source_refund_id")
    order_source_id = values.pop("order_source_id")
    payment_source_id = values.pop("payment_source_id")
    employee_source_id = values.pop("employee_source_id")
    device_source_id = values.pop("device_source_id")

    upsert(
        session, m.Refund, {"source_system_id": source_system_id, "source_refund_id": source_refund_id},
        {
            **values,
            "order_id": order_by_source_id.get(order_source_id) if order_source_id else None,
            "payment_id": payment_by_source_id.get(payment_source_id) if payment_source_id else None,
            "employee_id": (employee_by_source_id.get(employee_source_id) if employee_source_id else None),
            "device_id": device_by_source_id.get(device_source_id) if device_source_id else None,
            "device_source_id": device_source_id,
        },
    )
    session.flush()
    _mirror_source_record(
        session, ingestion_run_id=ingestion_run_id, source_system_id=source_system_id,
        entity_type="refund", source_id=source_refund_id, retrieved_at=retrieved_at, raw=refund_raw,
    )


class ImportAlreadyRunningError(RuntimeError):
    """Raised by `import_clover_period` when another Clover acquisition
    (Historical Backfill OR Live Sync, any mode) is already RUNNING for the
    same Location. No Clover fetch and no import write-transaction ever
    starts when this is raised — the caller is expected to catch it: a
    Backfill route shows a clean "an import is already in progress" message;
    a Live Sync cycle simply logs and waits for the next tick."""


def _acquisition_lock_key(location_id: int) -> str:
    """The guard's scope: same Location + Clover acquisition, regardless of
    mode (Backfill or Live Sync) or requested period. Deliberately Location-
    scoped, not Restaurant-scoped (TECHNICAL_CONNECTORS_STRUCTURE_001 — this
    connector has no concept of Restaurant): the actual failure this guards
    against (`sqlite3.OperationalError: database is locked`) is a property
    of the one shared SQLite *file*, not of which module/mode/period
    triggered the write — a Live Sync cycle and a Historical Backfill for
    the same Location must never be allowed to write concurrently either."""
    return f"CLOVER_ACQUISITION:{location_id}"


def _safe_error_summary(exc: Exception) -> str:
    """A FAILED run's "safe error summary" for `notes`: the exception's type
    and message only — never a full traceback (which could incidentally
    echo request parameters) — truncated so a very long or unexpected
    message can't bloat `notes`."""
    return f"{type(exc).__name__}: {exc}"[:500]


def _aware_utc(dt: datetime) -> datetime:
    """SQLite round-trips `DateTime(timezone=True)` as offset-naive —
    normalize a DB-loaded timestamp back to aware UTC before comparing it
    against a freshly-constructed `utc_now()` value."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _reap_if_stale(session: Session, *, location_id: int) -> int | None:
    """If the run currently holding this Location's acquisition lock has
    been RUNNING longer than `_STALE_RUN_THRESHOLD`, treat it as orphaned (a
    process interruption that never reached its own FAILED-handling code):
    mark it FAILED with an explicit auto-recovery note, clear its
    `lock_key`, commit, and return its id so the caller can retry acquiring
    the lock. Returns `None` (and changes nothing) if no RUNNING run holds
    this lock, or if it holds it but is not yet stale — in the latter case a
    genuinely in-progress acquisition must not be disturbed."""
    lock_key = _acquisition_lock_key(location_id)
    stale_cutoff = utc_now() - _STALE_RUN_THRESHOLD
    stale_run = session.scalars(
        select(m.IngestionRun).where(m.IngestionRun.lock_key == lock_key, m.IngestionRun.status == "RUNNING")
    ).first()
    if stale_run is None or _aware_utc(stale_run.started_at) >= stale_cutoff:
        return None

    stale_run.status = "FAILED"
    stale_run.finished_at = utc_now()
    stale_run.lock_key = None
    stale_run.notes = (
        f"{stale_run.notes or ''} | AUTO-RECOVERED: exceeded max run time ({_STALE_RUN_THRESHOLD}) — "
        "presumed orphaned by an interrupted process (killed/crashed before reaching COMPLETE/FAILED). "
        "Recovered automatically by the next acquisition attempt; no data was reverted (an interrupted "
        "run's own write transaction, if any, was never committed and needed no recovery of its own)."
    )
    session.add(stale_run)
    session.commit()
    return stale_run.id


def _acquire_import_lock(
    session: Session, *, location_id: int, source_system_id: int,
    period_start: datetime, period_end: datetime, mode: str,
) -> m.IngestionRun:
    """Persists the RUNNING execution token *before* any Clover fetch or
    long-running write transaction begins, and commits immediately in its
    own short transaction so the guard is visible to any other request the
    instant it is acquired. Race-safety comes from `IngestionRun.
    lock_key`'s UNIQUE index, not from a check-then-act SELECT: two
    concurrent submissions attempting this same INSERT can never both
    succeed, even against SQLite's single-writer file lock — the loser gets
    an `IntegrityError`. Before surfacing that as a rejection, one staleness
    check/reap is attempted so an orphaned RUNNING row from a past
    interruption self-heals on the very next acquisition attempt."""
    lock_key = _acquisition_lock_key(location_id)
    for attempt in range(2):
        run = m.IngestionRun(
            source_system_id=source_system_id, location_id=location_id, started_at=utc_now(),
            status="RUNNING", source_window_start=period_start, source_window_end=period_end,
            lock_key=lock_key,
            notes=f"CLOVER_ACQUISITION mode={mode} location_id={location_id}; RUNNING",
        )
        session.add(run)
        try:
            session.commit()
            return run
        except IntegrityError:
            session.rollback()
            if attempt == 0 and _reap_if_stale(session, location_id=location_id) is not None:
                continue  # a stale lock was just cleared — retry the insert
            raise ImportAlreadyRunningError(
                f"An import is already in progress for location_id={location_id}."
            ) from None
    raise ImportAlreadyRunningError(  # pragma: no cover — unreachable, keeps the return type honest
        f"An import is already in progress for location_id={location_id}."
    )


def _finalize_import_run(ingestion_run: m.IngestionRun, summary: ImportSummary, *, location_id: int, mode: str) -> None:
    """The RUNNING -> COMPLETE/PARTIAL/FAILED transition, and "release the
    execution guard" (clearing `lock_key` back to NULL).

    `window_scan_failed` (CLOVER_CONTINUOUS_SYNCHRONIZATION_ARCHITECTURE §2
    PRECHECK) takes priority over the ordinary PARTIAL-on-errors rule: a run
    whose Payments or Refunds createdTime-windowed scan itself did not
    succeed is marked FAILED, never PARTIAL/COMPLETE — `compute_next_sync_
    window` and `freshness._is_range_covered` both only ever treat COMPLETE/
    PARTIAL runs as having advanced the checkpoint, so a FAILED run here
    correctly leaves the checkpoint exactly where it was, and the next cycle
    (via its own overlap buffer) retries the same ground rather than silently
    skipping past a window that was never actually verified."""
    if summary.window_scan_failed:
        ingestion_run.status = "FAILED"
    else:
        ingestion_run.status = "COMPLETE" if not summary.errors else "PARTIAL"
    ingestion_run.finished_at = utc_now()
    ingestion_run.lock_key = None
    ingestion_run.notes = (
        f"CLOVER_ACQUISITION mode={mode} location_id={location_id}; "
        f"payments={summary.payments_imported + summary.payments_updated}; "
        f"orders={summary.orders_imported + summary.orders_updated}; "
        f"shifts={summary.shifts_imported}; "
        f"refunds={summary.refunds_found}"
        + ("; WINDOW SCAN FAILED — checkpoint not advanced, will retry" if summary.window_scan_failed else "")
    )


def get_latest_acquisition_status(session: Session, *, location_id: int) -> AcquisitionRunStatus | None:
    """Read-only ("status mechanism") — the most recent acquisition run
    (Backfill or Live Sync, whichever ran last) for `location_id`. Never
    modifies anything; see `reap_stale_acquisition_run` for the mutating
    counterpart."""
    run = session.scalars(
        select(m.IngestionRun)
        .where(m.IngestionRun.location_id == location_id)
        .order_by(m.IngestionRun.id.desc())
        .limit(1)
    ).first()
    if run is None:
        return None
    is_stale = run.status == "RUNNING" and _aware_utc(run.started_at) < utc_now() - _STALE_RUN_THRESHOLD
    mode_hint = None
    if run.notes and "mode=" in run.notes:
        try:
            mode_hint = run.notes.split("mode=", 1)[1].split(" ", 1)[0]
        except IndexError:  # pragma: no cover — defensive only, notes is free text
            mode_hint = None
    return AcquisitionRunStatus(
        run_id=run.id, status=run.status, mode_hint=mode_hint, started_at=run.started_at,
        finished_at=run.finished_at, is_stale=is_stale, notes=run.notes,
    )


def reap_stale_acquisition_run(session: Session, *, location_id: int) -> int | None:
    """Explicit/manual recovery entry point — an operator-facing counterpart
    to the automatic self-heal `_acquire_import_lock` already performs on
    its own next attempt. Returns the reaped run's id, or `None` if nothing
    was stale (either no RUNNING run exists, or one exists but has not yet
    exceeded `_STALE_RUN_THRESHOLD` — never disturbed)."""
    return _reap_if_stale(session, location_id=location_id)


def import_clover_period(
    session: Session, *, location_id: int, period_start: datetime, period_end: datetime,
    client: CloverReadClient | None = None, mode: str = MODE_BACKFILL,
) -> ImportSummary:
    """The central Clover data acquisition entry point. Fetches Payments for
    the period, their Orders, qualifying fee line items, resolves Employees/
    Tenders/Devices, fetches/reconciles Refunds for the same period, upserts
    every source fact, and returns an operational summary. Idempotent:
    re-running for a period that was already imported UPDATES existing rows
    from Clover's current values rather than duplicating them — this is
    what makes it safe for both Historical Backfill (an operator-chosen,
    possibly-overlapping date range) and Live Sync (a short, deliberately-
    overlapping rolling window) to call unchanged.

    `location_id` is the ONLY ownership concept this connector needs
    (TECHNICAL_CONNECTORS_STRUCTURE_001) — it never resolves or reasons
    about Restaurant, Tips, or any other Domain; a Domain-layer caller
    resolves which Location it wants acquired (e.g. Tips resolves its
    Restaurant's own Location via `RestaurantLocation`) before calling in.

    `mode` (`MODE_BACKFILL` default, or `MODE_LIVE_SYNC`) is recorded on the
    `IngestionRun` and, since CLOVER_LIVE_SYNC_SCOPE_REDUCTION_001, is also
    what this function branches on to decide which entities to refresh (see
    the module docstring) — it does not change the concurrency guard's scope
    (also the sole entry point enforcing that guard) — raises
    `ImportAlreadyRunningError` immediately
    (before any Clover fetch) if another acquisition of ANY mode is already
    RUNNING for this Location, and otherwise guarantees the RUNNING
    execution token it registers is always resolved to COMPLETE, PARTIAL, or
    FAILED before this function returns or raises, so a failed (or
    interrupted-and-later-reaped) run never leaves the system permanently
    locked."""
    summary = ImportSummary(location_id=location_id, period_start=period_start, period_end=period_end)

    merchant = _resolve_clover_merchant(session, location_id)
    if merchant is None:
        summary.errors.append(
            f"location_id={location_id} is not a Clover-sourced Location with a resolved external "
            "identifier. This module does not create Merchant/Location — run the full Clover onboarding "
            "ingestion first (see ingest_clover.py)."
        )
        return summary
    source_system_id, merchant_id = merchant

    ingestion_run = _acquire_import_lock(
        session, location_id=location_id, source_system_id=source_system_id,
        period_start=period_start, period_end=period_end, mode=mode,
    )
    # One retrieved_at timestamp for every Provider Mirror row this run
    # writes — the same "single timestamp per run/bundle" convention
    # `ingest.py`'s bulk pipeline already uses, not a per-record fetch time.
    retrieved_at = utc_now()

    try:
        resolved_client = client or get_default_client()

        start_ms = int(period_start.astimezone(UTC).timestamp() * 1000)
        end_ms = int(period_end.astimezone(UTC).timestamp() * 1000)

        payments_result = paginate(
            resolved_client, f"/v3/merchants/{merchant_id}/payments",
            extra_params={
                "expand": "order,tender,employee",
                "filter": [f"createdTime>={start_ms}", f"createdTime<={end_ms}"],
                "orderBy": "createdTime ASC",
            },
        )
        if not payments_result.ok:
            summary.errors.append(f"Fetching Payments failed: {payments_result.error or 'unknown error'}")
            # The Payments createdTime scan is what THIS window's checkpoint
            # certifies as "covered" — if it never succeeded, the window was
            # never actually scanned and must not be treated as done.
            summary.window_scan_failed = True
            _finalize_import_run(ingestion_run, summary, location_id=location_id, mode=mode)
            session.flush()
            return summary
        payments_raw = payments_result.elements

        employee_by_source_id, tender_by_source_id, device_by_source_id = _fetch_reference_catalogs(
            resolved_client, session, location_id=location_id, source_system_id=source_system_id,
            ingestion_run_id=ingestion_run.id, retrieved_at=retrieved_at, mode=mode,
        )
        summary.employees_resolved = len(employee_by_source_id)

        summary.shifts_imported = _fetch_and_ingest_shifts(
            resolved_client, session, period_start=period_start, period_end=period_end,
            source_system_id=source_system_id, employee_by_source_id=employee_by_source_id,
            ingestion_run_id=ingestion_run.id, retrieved_at=retrieved_at,
        )

        # CLOVER_HISTORICAL_BACKFILL_EXTRACTOR_V1 — full menu/catalog +
        # source-role coverage, Historical Backfill only.
        # CLOVER_LIVE_SYNC_SCOPE_REDUCTION_001 reverted this to Backfill-only
        # after a brief period (CLOVER_LIVE_SYNC_EXTRACTOR_V1) where Live
        # Sync also refreshed it: Items/Categories/ModifierGroups/Modifiers/
        # TaxRates/DiscountDefinitions/OrderTypes/SourceRoles are catalog/
        # reference data that does not need continuous refresh — Historical
        # Backfill remains the sole path that keeps them current, and Live
        # Sync's Order Item/Modifier detail below resolves against whatever
        # is already canonical instead (see `historical_backfill_detail.
        # ingest_order_item_and_modifier_detail`).
        catalog: historical_backfill_detail.CatalogMaps | None = None
        tax_override_cache: dict[str, float] = {}
        if mode == MODE_BACKFILL:
            catalog = historical_backfill_detail.fetch_full_catalog(
                resolved_client, session, location_id=location_id, source_system_id=source_system_id,
                ingestion_run_id=ingestion_run.id, retrieved_at=retrieved_at,
                mirror_source_record=_mirror_source_record,
            )
            catalog.employee_by_source_id = employee_by_source_id
            catalog.tender_by_source_id = tender_by_source_id
            catalog.device_by_source_id = device_by_source_id
            historical_backfill_detail.ingest_employee_source_roles(
                session, resolved_client, source_system_id=source_system_id,
                employee_by_source_id=employee_by_source_id, catalog=catalog, retrieved_at=retrieved_at,
            )

        order_ids_needed: set[str] = set()
        for p in payments_raw:
            ref = p.get("order")
            oid = ref.get("id") if isinstance(ref, dict) else None
            if oid:
                order_ids_needed.add(oid)

        order_by_source_id: dict[str, int] = {}
        orders_raw_by_source_id: dict[str, dict[str, Any]] = {}
        # `discounts` is only requested for Historical Backfill again
        # (CLOVER_LIVE_SYNC_SCOPE_REDUCTION_001) — Order Discounts are not
        # in Live Sync's retained-entity list, so there is no reason for
        # Live Sync's per-order GET to request them.
        order_expand = "employee,lineItems,discounts" if mode == MODE_BACKFILL else "employee,lineItems"
        for order_source_id in order_ids_needed:
            order_result = resolved_client.get(
                f"/v3/merchants/{merchant_id}/orders/{order_source_id}", params={"expand": order_expand},
            )
            if not order_result.ok:
                summary.errors.append(f"Fetching Order {order_source_id[:4]}... failed: {order_result.error}")
                continue
            order_raw = order_result.data
            orders_raw_by_source_id[order_source_id] = order_raw
            order, is_new = _ingest_order(
                session, order_raw, location_id=location_id, source_system_id=source_system_id,
                employee_by_source_id=employee_by_source_id,
                ingestion_run_id=ingestion_run.id, retrieved_at=retrieved_at,
            )
            order_by_source_id[order_source_id] = order.id
            if is_new:
                summary.orders_imported += 1
            else:
                summary.orders_updated += 1
            _ingest_fee_line_items(session, order_raw, order, source_system_id=source_system_id, summary=summary)

            if mode == MODE_BACKFILL and catalog is not None:
                # Full detail: OrderItem, OrderItemModifier, OrderItemTax,
                # OrderDiscount — needs the live-fetched catalog above.
                historical_backfill_detail.ingest_order_detail(
                    session, resolved_client, order_raw, order, source_system_id=source_system_id,
                    catalog=catalog, ingestion_run_id=ingestion_run.id, retrieved_at=retrieved_at,
                    mirror_source_record=_mirror_source_record, tax_override_cache=tax_override_cache,
                )
            elif mode == MODE_LIVE_SYNC:
                # CLOVER_LIVE_SYNC_SCOPE_REDUCTION_001 — Order Items and
                # Order Item Modifiers remain in Live Sync's retained-entity
                # list (they are transactional facts, not catalog), but
                # without a live-refreshed catalog to resolve against;
                # `item_id`/`modifier_id` resolve against whatever is
                # already canonical instead. No Order Item Tax, no Order
                # Discount here — both depend on catalogs Live Sync no
                # longer refreshes (TaxRate/Item, DiscountDefinition).
                historical_backfill_detail.ingest_order_item_and_modifier_detail(
                    session, resolved_client, order_raw, order, source_system_id=source_system_id,
                    ingestion_run_id=ingestion_run.id, retrieved_at=retrieved_at,
                    mirror_source_record=_mirror_source_record,
                )

        payment_by_source_id: dict[str, int] = {}
        for payment_raw in payments_raw:
            order_ref = payment_raw.get("order")
            order_source_id = order_ref.get("id") if isinstance(order_ref, dict) else None
            order_id = order_by_source_id.get(order_source_id) if order_source_id else None
            if order_id is None:
                summary.errors.append(
                    f"Payment {(payment_raw.get('id') or '')[:4]}... references an unresolved Order; skipped."
                )
                continue
            payment = _ingest_payment(
                session, payment_raw, order_id=order_id, source_system_id=source_system_id,
                employee_by_source_id=employee_by_source_id, tender_by_source_id=tender_by_source_id,
                device_by_source_id=device_by_source_id, summary=summary,
                ingestion_run_id=ingestion_run.id, retrieved_at=retrieved_at,
            )
            payment_by_source_id[payment_raw.get("id")] = payment.id

        # Order.employee vs Payment.employee: Order.employee is the Tip
        # Distribution Engine's authoritative tip owner; Payment.employee is
        # preserved independently for audit/anomaly detection only and
        # never overwrites or changes Order.employee. Both values are
        # preserved, and any discrepancy is flagged for review rather than
        # silently resolved.
        for order_source_id, order_raw in orders_raw_by_source_id.items():
            order_employee_source_id = (order_raw.get("employee") or {}).get("id")
            order_id = order_by_source_id[order_source_id]
            order_payments = session.scalars(select(m.Payment).where(m.Payment.order_id == order_id)).all()
            if len(order_payments) > 1:
                summary.split_payment_orders_count += 1
            for payment in order_payments:
                if (
                    payment.source_employee_id
                    and order_employee_source_id
                    and payment.source_employee_id != order_employee_source_id
                ):
                    summary.employee_mismatches.append(
                        EmployeeMismatch(
                            order_source_id=order_source_id,
                            order_employee_source_id=order_employee_source_id,
                            payment_source_id=payment.source_payment_id,
                            payment_employee_source_id=payment.source_employee_id,
                        )
                    )

        refunds_result = paginate(
            resolved_client, f"/v3/merchants/{merchant_id}/refunds",
            extra_params={"filter": [f"createdTime>={start_ms}", f"createdTime<={end_ms}"]},
        )
        if refunds_result.ok:
            for refund_raw in refunds_result.elements:
                _ingest_refund(
                    session, refund_raw, source_system_id=source_system_id,
                    order_by_source_id=order_by_source_id, payment_by_source_id=payment_by_source_id,
                    employee_by_source_id=employee_by_source_id, device_by_source_id=device_by_source_id,
                    ingestion_run_id=ingestion_run.id, retrieved_at=retrieved_at,
                )
                summary.refunds_found += 1
        else:
            summary.errors.append(f"Fetching Refunds failed: {refunds_result.error or 'unknown error'}")
            # Same reasoning as the Payments case above: Refunds is the other
            # createdTime-windowed scan this run's checkpoint certifies —
            # Orders/Payments having already succeeded earlier in this same
            # cycle must not mask a Refunds-scan failure into a checkpoint
            # advance that silently skips this window's refunds forever.
            summary.window_scan_failed = True
    except Exception as exc:  # noqa: BLE001 — a failed run must release the guard, never stay RUNNING forever
        session.rollback()
        ingestion_run.status = "FAILED"
        ingestion_run.finished_at = utc_now()
        ingestion_run.lock_key = None
        ingestion_run.notes = (
            f"CLOVER_ACQUISITION mode={mode} location_id={location_id}; FAILED: {_safe_error_summary(exc)}"
        )
        session.add(ingestion_run)
        session.commit()
        raise

    _finalize_import_run(ingestion_run, summary, location_id=location_id, mode=mode)
    session.flush()

    return summary
