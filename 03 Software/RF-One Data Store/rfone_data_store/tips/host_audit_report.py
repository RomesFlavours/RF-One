"""Host Tip Audit / Explain report (HOST_TIP_AUDIT_001).

Explains, for one Host Employee and one requested period, exactly which
allocation lines produced their Host Tip total, grouped by the Host's
actual `Shift` records, cross-checked against Clover source facts
(Order/Payment ids and timestamps already stored by the existing Clover
connector), and reconciled against the engine's own independently-computed
per-Employee aggregate (`distribution_engine.build_employee_review`).

ON DEMAND (TIPS_STATELESS_CALCULATION_001): the lines come from a fresh
`distribution_engine.calculate_tips` over the requested period, held in
memory. No persisted allocation row is read, and nothing is written — so
any period, overlapping or not, can be audited at any time. Callers that
already hold a `TipCalculationResult` pass it in, so the audit and the
screen that triggered it are guaranteed to describe the very same numbers.

This is NOT a second calculation engine: every figure shown here comes
from that single engine result or from simple grouping/summation of it —
nothing here re-implements eligibility, pooling, splitting, or rounding. If the underlying calculation is ever wrong, this report will
faithfully reproduce that wrongness rather than silently correct it — its
entire purpose is to make the ALREADY-COMPUTED result inspectable, not to
compute a second opinion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..business_date import derive_business_date
from . import distribution_engine as engine_svc

UTC = timezone.utc

STATUS_ALLOCATED = "ALLOCATED"
STATUS_NOT_IMPLEMENTED = "NOT_IMPLEMENTED"


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


@dataclass
class HostAllocationLine:
    """One calculated allocation line where the audited Host was the
    recipient — every field here is read directly off the engine's own
    in-memory result, never recomputed here."""

    order_id: int
    clover_order_id: str | None
    business_date: date | None
    settlement_time: datetime
    payment_timestamps: list[datetime]
    clover_payment_ids: list[str]
    server_employee_id: int | None
    server_employee_name: str
    original_tip_amount_minor: int  # base_amount_minor
    host_pool_amount_minor: int  # pool_amount_minor
    eligible_host_count: int
    eligible_hosts: list[tuple[str, int]]  # [(employee display name, their allocated_amount_minor), ...]
    host_allocated_amount_minor: int  # THIS Host's own allocated_amount_minor
    rule_version_id: int
    status: str


@dataclass
class HostShiftAuditGroup:
    shift_id: int | None  # None only for the defensive "no matching Shift record" bucket
    business_date: date | None
    role_name: str
    shift_start: datetime | None
    shift_end: datetime | None
    rule_version_ids: list[int]
    lines: list[HostAllocationLine] = field(default_factory=list)

    @property
    def total_host_tips_minor(self) -> int:
        return sum(line.host_allocated_amount_minor for line in self.lines)


@dataclass
class UnresolvedPeriodItem:
    """A calculated line the engine could not automatically
    resolve at all (`NOT_IMPLEMENTED` — an unsupported Calculation Base or
    Distribution Method configuration) — restaurant/period-scoped, NOT
    attributable to any specific Host, since no recipient was ever
    determined for it (task §13 — shown separately, never as a Host
    allocation, never invented as belonging to this Host)."""

    order_id: int
    clover_order_id: str | None
    business_date: date | None
    settlement_time: datetime
    rule_version_id: int
    detail: str


@dataclass
class PeriodReconciliation:
    """Cross-check of this report's own line sum for the requested period
    against `build_employee_review`'s independently computed inbound figure
    for the same Host, over the same in-memory result."""

    period_start: datetime
    period_end: datetime
    line_sum_minor: int
    engine_reported_inbound_minor: int  # distribution_engine.build_employee_review's own independent figure
    ok: bool


@dataclass
class HostAuditReport:
    restaurant_id: int
    host_employee_id: int
    host_employee_name: str
    period_start: datetime
    period_end: datetime
    shift_groups: list[HostShiftAuditGroup]
    unresolved_items: list[UnresolvedPeriodItem]
    reconciliations: list[PeriodReconciliation]

    @property
    def period_total_host_tips_minor(self) -> int:
        return sum(group.total_host_tips_minor for group in self.shift_groups)

    @property
    def period_reconciliation_ok(self) -> bool:
        return all(r.ok for r in self.reconciliations)


def _employee_name(session: Session, employee_id: int | None) -> str:
    if employee_id is None:
        return "(unknown)"
    employee = session.get(m.Employee, employee_id)
    if employee is None:
        return f"Employee #{employee_id}"
    return employee.display_name or f"Employee #{employee_id}"


def _restaurant_location_ids(session: Session, restaurant_id: int) -> set[int]:
    return set(
        session.scalars(
            select(m.RestaurantLocation.location_id).where(m.RestaurantLocation.restaurant_id == restaurant_id)
        ).all()
    )


def _find_covering_shift(shifts: list[m.Shift], at: datetime) -> m.Shift | None:
    """The Host's own Shift whose `[clock_in, clock_out)` window contains
    `at` — the SAME literal presence formula `distribution_engine.
    _employees_shift_active_at` already used at calculation time, so a Host
    allocation line always falls inside exactly one of their Shifts by
    construction; the tie-break (latest `clock_in`) only matters for the
    defensive case of overlapping source Shift records."""
    at = _aware(at)
    candidates = [
        s for s in shifts
        if s.clock_in is not None and _aware(s.clock_in) <= at
        and (s.clock_out is None or at < _aware(s.clock_out))
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda s: _aware(s.clock_in))


def build_host_audit_report(
    session: Session, *, restaurant_id: int, host_employee_id: int, period_start: datetime, period_end: datetime,
    result: engine_svc.TipCalculationResult | None = None,
) -> HostAuditReport:
    """Build the audit for one Host over `[period_start, period_end)`.

    `result` lets a caller that has ALREADY calculated the period pass that
    exact result in, guaranteeing the audit explains the same numbers the
    caller just displayed. When omitted, the period is calculated fresh
    here. Either way nothing is read from, or written to, persisted
    allocation storage."""
    period_start = _aware(period_start)
    period_end = _aware(period_end)
    host_name = _employee_name(session, host_employee_id)

    location_ids = _restaurant_location_ids(session, restaurant_id)

    if result is None:
        result = engine_svc.calculate_tips(
            session, restaurant_id=restaurant_id, period_start=period_start, period_end=period_end,
        )

    allocations = sorted(
        (line for line in result.lines if line.recipient_employee_id == host_employee_id),
        key=lambda line: line.settlement_time,
    )

    # This Host's own Shifts overlapping the requested period — every real
    # allocation line above must fall inside exactly one of these, since
    # the engine only ever allocated to this Host because a Shift like this
    # was active at that Order's Settlement Time.
    shifts = list(
        session.scalars(
            select(m.Shift).where(
                m.Shift.employee_id == host_employee_id,
                m.Shift.clock_in.is_not(None),
                m.Shift.clock_in < period_end,
                (m.Shift.clock_out.is_(None)) | (m.Shift.clock_out > period_start),
            )
        )
    )

    groups_by_shift_key: dict[int | None, HostShiftAuditGroup] = {}

    def _group_for(shift: m.Shift | None) -> HostShiftAuditGroup:
        key = shift.id if shift is not None else None
        if key not in groups_by_shift_key:
            role_name = "(unknown)"
            business_dt = None
            location = None
            if shift is not None and shift.location_id is not None:
                location = session.get(m.Location, shift.location_id)
            if shift is not None and location is not None and location.timezone and location.operating_day_cutoff_time:
                business_dt = derive_business_date(
                    settlement_time=shift.clock_in, location_timezone=location.timezone,
                    operating_day_cutoff_time=location.operating_day_cutoff_time,
                )
            groups_by_shift_key[key] = HostShiftAuditGroup(
                shift_id=key, business_date=business_dt, role_name=role_name,
                shift_start=shift.clock_in if shift is not None else None,
                shift_end=shift.clock_out if shift is not None else None,
                rule_version_ids=[],
            )
        return groups_by_shift_key[key]

    for allocation in allocations:
        shift = _find_covering_shift(shifts, allocation.settlement_time)
        group = _group_for(shift)
        if allocation.rule_version_id not in group.rule_version_ids:
            group.rule_version_ids.append(allocation.rule_version_id)
        if group.role_name == "(unknown)":
            rule_version = session.get(m.TipDistributionRuleVersion, allocation.rule_version_id)
            if rule_version is not None:
                role = session.get(m.RestaurantRole, rule_version.recipient_role_id)
                if role is not None:
                    group.role_name = role.name

        order = session.get(m.Order, allocation.order_id)
        payments = list(
            session.scalars(
                select(m.Payment).where(m.Payment.order_id == allocation.order_id, m.Payment.result == "SUCCESS")
            )
        )
        siblings = [
            line for line in result.lines
            if line.order_id == allocation.order_id
            and line.rule_version_id == allocation.rule_version_id
            and line.recipient_employee_id is not None
        ]
        eligible_hosts = [
            (_employee_name(session, s.recipient_employee_id), s.allocated_amount_minor) for s in siblings
        ]

        group.lines.append(
            HostAllocationLine(
                order_id=allocation.order_id,
                clover_order_id=order.source_order_id if order is not None else None,
                business_date=order.business_date if order is not None else None,
                settlement_time=allocation.settlement_time,
                payment_timestamps=[p.created_at for p in payments],
                clover_payment_ids=[p.source_payment_id for p in payments if p.source_payment_id],
                server_employee_id=allocation.source_employee_id,
                server_employee_name=_employee_name(session, allocation.source_employee_id),
                original_tip_amount_minor=allocation.base_amount_minor,
                host_pool_amount_minor=allocation.pool_amount_minor,
                eligible_host_count=len(siblings),
                eligible_hosts=eligible_hosts,
                host_allocated_amount_minor=allocation.allocated_amount_minor,
                rule_version_id=allocation.rule_version_id,
                status=STATUS_ALLOCATED,
            )
        )

    shift_groups = sorted(
        groups_by_shift_key.values(),
        key=lambda g: (g.shift_start or datetime.min.replace(tzinfo=UTC)),
    )

    # Period-level unresolved items (task §13) — never attributed to this
    # Host specifically, since no recipient was ever determined for them.
    unresolved_rows = result.unresolved_lines
    unresolved_items = []
    for row in unresolved_rows:
        order = session.get(m.Order, row.order_id)
        unresolved_items.append(
            UnresolvedPeriodItem(
                order_id=row.order_id, clover_order_id=order.source_order_id if order is not None else None,
                business_date=order.business_date if order is not None else None,
                settlement_time=row.settlement_time, rule_version_id=row.rule_version_id,
                detail=row.recipient_eligibility_basis,
            )
        )

    # Reconciliation — cross-check this report's own line sum, per
    # calculation run, against `build_employee_review`'s independently
    # computed inbound figure for this Host (the SAME engine's own
    # aggregate, never a second implementation).
    line_sum = sum(a.allocated_amount_minor for a in allocations)
    review_rows = engine_svc.build_employee_review(session, result)
    reported = next((r.inbound_tip_out_minor for r in review_rows if r.employee_id == host_employee_id), 0)
    reconciliations = [
        PeriodReconciliation(
            period_start=period_start, period_end=period_end,
            line_sum_minor=line_sum, engine_reported_inbound_minor=reported, ok=(line_sum == reported),
        )
    ]

    return HostAuditReport(
        restaurant_id=restaurant_id, host_employee_id=host_employee_id, host_employee_name=host_name,
        period_start=period_start, period_end=period_end, shift_groups=shift_groups,
        unresolved_items=unresolved_items, reconciliations=reconciliations,
    )


# ---------------------------------------------------------------------------
# CSV export (task §14) — one row per displayed audit line, plus unresolved
# items appended with status NOT_IMPLEMENTED so the export is a complete,
# faithful mirror of what the UI shows.
# ---------------------------------------------------------------------------

CSV_FIELDNAMES = [
    "business_date", "host_employee", "shift_start", "shift_end", "payment_timestamp", "server_employee",
    "clover_order_id", "clover_payment_id", "original_tip_amount", "host_share_amount", "eligible_host_count",
    "host_allocated_amount", "rule_version", "status",
]


def _minor_to_str(minor: int) -> str:
    return f"{minor / 100:.2f}"


def report_to_csv_rows(report: HostAuditReport) -> list[dict]:
    rows: list[dict] = []
    for group in report.shift_groups:
        for line in group.lines:
            rows.append({
                "business_date": line.business_date.isoformat() if line.business_date else "",
                "host_employee": report.host_employee_name,
                "shift_start": group.shift_start.isoformat() if group.shift_start else "",
                "shift_end": group.shift_end.isoformat() if group.shift_end else "",
                "payment_timestamp": "; ".join(t.isoformat() for t in line.payment_timestamps),
                "server_employee": line.server_employee_name,
                "clover_order_id": line.clover_order_id or "",
                "clover_payment_id": "; ".join(line.clover_payment_ids),
                "original_tip_amount": _minor_to_str(line.original_tip_amount_minor),
                "host_share_amount": _minor_to_str(line.host_pool_amount_minor),
                "eligible_host_count": line.eligible_host_count,
                "host_allocated_amount": _minor_to_str(line.host_allocated_amount_minor),
                "rule_version": line.rule_version_id,
                "status": line.status,
            })
    for item in report.unresolved_items:
        rows.append({
            "business_date": item.business_date.isoformat() if item.business_date else "",
            "host_employee": report.host_employee_name,
            "shift_start": "", "shift_end": "",
            "payment_timestamp": item.settlement_time.isoformat(),
            "server_employee": "",
            "clover_order_id": item.clover_order_id or "", "clover_payment_id": "",
            "original_tip_amount": "", "host_share_amount": "", "eligible_host_count": "",
            "host_allocated_amount": "", "rule_version": item.rule_version_id,
            "status": STATUS_NOT_IMPLEMENTED,
        })
    return rows
