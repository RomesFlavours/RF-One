"""Tip Distribution Engine — core calculation/allocation logic
(TIP_DISTRIBUTION_ENGINE_001).

Implements ONLY what the task authorizes: Order-level Gross Earned Tips,
Settlement-Time-based rule-version selection, ACTIVE_AT_SETTLEMENT
eligibility from persisted Shift facts, EQUAL distribution, atomic
allocation results, and a minimal calculation-run/period structure. Reuses
(never duplicates) `tips.distribution_rule_service` for rule configuration/
versioning, `technical.connectors.clover.acquisition.get_order_settlement_time`
(the Clover Technical Connector — TECHNICAL_CONNECTORS_STRUCTURE_001 — owns
this as a generic derived fact over already-acquired Payments, not a
Tips-owned concern) for the canonical Settlement Time, and
`tips.rounding.equal_split` for deterministic residual-cent apportionment.

Deliberately separate from the legacy, since-retired per-Payment `TipPolicy`
engine (TIPS_LEGACY_ENGINE_RETIREMENT_001) — see `models.py`'s own docstring
above `TipDistributionCalculationRun` for why these were never merged. This
module never imports Clover/network code at all: every input is an already-
persisted RF-One database fact, fetched by the Clover Technical Connector
(`technical/connectors/clover/acquisition.py`,
`technical/connectors/clover/live_sync.py`), never by this module directly.

Manual adjustments, Review/Approve/Lock, Payment Batch, and automatic batch
scheduling are explicitly NOT implemented here — see
`07 Tasks/Reports/TIP_DISTRIBUTION_ENGINE_001.md`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..ingestion.common import utc_now
from ..technical.connectors.clover.acquisition import get_order_settlement_time
from . import distribution_rule_service as rule_svc
from .rounding import equal_split

UTC = timezone.utc

STATUS_RUNNING = "RUNNING"
STATUS_COMPLETE = "COMPLETE"
STATUS_FAILED = "FAILED"

_HUNDRED = Decimal("100")
_CENT = Decimal("1")


@dataclass
class CalculationSummary:
    orders_considered: int = 0
    orders_with_no_settlement_time: int = 0
    orders_skipped_no_employee: int = 0
    rules_applied: int = 0
    rules_not_implemented: int = 0
    allocations_produced: int = 0


@dataclass
class EmployeeReviewRow:
    """Task §17's Review table row — every figure derived fresh from
    persisted `TipDistributionAllocation`/source-fact rows, never stored as
    its own atomic data (task §19: "do not replace atomic data with these
    summaries")."""

    employee_id: int
    display_name: str | None
    gross_earned_tips_minor: int
    outbound_tip_out_minor: int
    inbound_tip_out_minor: int
    net_before_adjustments_minor: int
    has_warning: bool
    warning_notes: list[str] = field(default_factory=list)
    # Task §18 — every Order this Employee is traceable through (as Gross-Tip
    # owner, outbound source, or inbound recipient) in this run, sorted, so
    # the Review UI can link straight to each Order's drill-down.
    order_ids: list[int] = field(default_factory=list)


def _aware_utc(dt: datetime) -> datetime:
    """SQLite round-trips `DateTime(timezone=True)` as offset-naive (same
    caveat `tips_distribution_rule_validation.py` documents), while
    `period_start`/`period_end` here are always constructed timezone-aware
    by the caller. `get_order_settlement_time` is a DB-computed value, so it
    comes back naive after any commit/expire — normalize it to aware UTC
    once, immediately, so every comparison and every value handed to
    `distribution_rule_service` (whose own tests pass timezone-aware
    instants) stays internally consistent."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _restaurant_location_ids(session: Session, restaurant_id: int) -> set[int]:
    return set(
        session.scalars(
            select(m.RestaurantLocation.location_id).where(m.RestaurantLocation.restaurant_id == restaurant_id)
        ).all()
    )


def _round_pool(base_amount_minor: int, rate: Decimal) -> int:
    """Task §17 — integer cents, never floating point. The pool itself is a
    single derived value (not split across multiple parties, unlike the
    outbound recipient split below), so ordinary deterministic round-half-up
    to the nearest cent is used: reproducible, and the same inputs always
    produce the same pool."""
    exact = (Decimal(base_amount_minor) * rate) / _HUNDRED
    return int(exact.quantize(_CENT, rounding=ROUND_HALF_UP))


def _order_gross_tip_components(session: Session, order: m.Order) -> tuple[int, int]:
    """Returns `(voluntary_tip_minor, gratuity_minor)` for one Order (spec
    §3/§6).

    Voluntary tips: summed across the Order's Payments whose `result ==
    SUCCESS` only — a FAILED Payment never actually settled, so any
    `tipAmount` it carried was never real collected money (spec §6's "what
    RF-One can see, RF-One can distribute" is read here as observed AND
    settled). A Payment with no `PaymentTip` row (source-absent) contributes
    0, never coerced (spec §6 "unrecorded cash tips excluded").

    Automatic gratuity: summed from this Order's `OrderFee` rows — already
    counted exactly once per Order by the ingestion layer's own
    upsert-by-source-line-item (spec §3's "counted once only" is a direct
    structural consequence of that ingestion behavior, not re-implemented
    here).
    """
    payments = session.scalars(select(m.Payment).where(m.Payment.order_id == order.id)).all()
    voluntary = 0
    for payment in payments:
        if payment.result != "SUCCESS":
            continue
        tip = session.get(m.PaymentTip, payment.id)
        if tip is not None and tip.amount:
            voluntary += tip.amount

    fees = session.scalars(select(m.OrderFee).where(m.OrderFee.order_id == order.id)).all()
    gratuity = sum((fee.amount or 0) for fee in fees)
    return voluntary, gratuity


def _base_amount_for(calculation_base: str, voluntary_minor: int, gratuity_minor: int) -> int | None:
    """Task §13 — each rule computes from its OWN original base, never a
    remainder left after another rule. Returns `None` for a Calculation Base
    this engine does not yet compute (TOTAL_SALES/FOOD_SALES/BEVERAGE_SALES
    — task §6 "do not implement those... unless already trivially
    available"; they are not)."""
    if calculation_base == m.CALC_BASE_VOLUNTARY_TIP:
        return voluntary_minor
    if calculation_base == m.CALC_BASE_GRATUITY:
        return gratuity_minor
    if calculation_base == m.CALC_BASE_TIP_PLUS_GRATUITY:
        return voluntary_minor + gratuity_minor
    return None


def _roles_held_by_employee_at(
    session: Session, *, restaurant_id: int, employee_id: int, location_id: int, at: datetime,
) -> set[int]:
    """Which `RestaurantRole.id`(s) `employee_id` held at `at` (task §4/§10
    — reuses the existing `EmployeeAssignment` structure, the canonical
    RF-One "who holds which Role, when" fact, rather than inventing a new
    role-membership concept)."""
    rows = session.scalars(
        select(m.EmployeeAssignment.restaurant_role_id).where(
            m.EmployeeAssignment.restaurant_id == restaurant_id,
            m.EmployeeAssignment.employee_id == employee_id,
            m.EmployeeAssignment.valid_from <= at,
            (m.EmployeeAssignment.valid_to.is_(None)) | (m.EmployeeAssignment.valid_to > at),
            (m.EmployeeAssignment.location_id.is_(None)) | (m.EmployeeAssignment.location_id == location_id),
        )
    ).all()
    return set(rows)


def _employees_with_role_at(
    session: Session, *, restaurant_id: int, restaurant_role_id: int, location_id: int, at: datetime,
) -> set[int]:
    """The reverse of `_roles_held_by_employee_at` — every Employee holding
    `restaurant_role_id` at `at` (task §9.2's "identify employees with
    Recipient Role")."""
    rows = session.scalars(
        select(m.EmployeeAssignment.employee_id).where(
            m.EmployeeAssignment.restaurant_id == restaurant_id,
            m.EmployeeAssignment.restaurant_role_id == restaurant_role_id,
            m.EmployeeAssignment.valid_from <= at,
            (m.EmployeeAssignment.valid_to.is_(None)) | (m.EmployeeAssignment.valid_to > at),
            (m.EmployeeAssignment.location_id.is_(None)) | (m.EmployeeAssignment.location_id == location_id),
        )
    ).all()
    return set(rows)


def _employees_shift_active_at(session: Session, *, location_id: int, at: datetime) -> set[int]:
    """Task §9's literal presence formula:

        clock_in <= at AND (clock_out IS NULL OR at < clock_out)

    Scoped to `location_id` when a Shift carries its own Location evidence
    (`Shift.location_id`); a Shift with no Location evidence is treated as
    matching. Rome's Flavours is single-Location today, and this task
    explicitly scopes to its first configuration and forbids "broad
    architecture/integrity reviews" — the legacy engine's fuller
    multi-Location epistemic-gap handling (TASK_TIPS_004) is deliberately
    not reproduced here; see the implementation report."""
    rows = session.scalars(
        select(m.Shift.employee_id).where(
            (m.Shift.location_id.is_(None)) | (m.Shift.location_id == location_id),
            m.Shift.clock_in.is_not(None),
            m.Shift.clock_in <= at,
            (m.Shift.clock_out.is_(None)) | (at < m.Shift.clock_out),
        )
    ).all()
    return set(rows)


def _apply_rule_to_order(
    session: Session, *, run: m.TipDistributionCalculationRun, order: m.Order, restaurant_id: int,
    source_employee_id: int, settlement_time: datetime, rule_version: m.TipDistributionRuleVersion,
    voluntary_minor: int, gratuity_minor: int, summary: CalculationSummary,
) -> None:
    base_amount = _base_amount_for(rule_version.calculation_base, voluntary_minor, gratuity_minor)
    if base_amount is None:
        summary.rules_not_implemented += 1
        session.add(
            m.TipDistributionAllocation(
                calculation_run_id=run.id, order_id=order.id, source_employee_id=source_employee_id,
                rule_version_id=rule_version.id, calculation_base=rule_version.calculation_base,
                rate=rule_version.rate, base_amount_minor=0, pool_amount_minor=0, recipient_employee_id=None,
                recipient_eligibility_basis=(
                    f"NOT_IMPLEMENTED: calculation_base={rule_version.calculation_base!r} is not yet computable "
                    "by this engine (sales-based bases are configuration-only for now); no pool was generated."
                ),
                no_eligible_recipient=True, allocated_amount_minor=0, settlement_time=settlement_time,
            )
        )
        return

    summary.rules_applied += 1
    pool_amount = _round_pool(base_amount, rule_version.rate)

    recipient_role = session.get(m.RestaurantRole, rule_version.recipient_role_id)
    role_name = recipient_role.name if recipient_role is not None else str(rule_version.recipient_role_id)

    if rule_version.distribution_method != m.DISTRIBUTION_METHOD_EQUAL:
        session.add(
            m.TipDistributionAllocation(
                calculation_run_id=run.id, order_id=order.id, source_employee_id=source_employee_id,
                rule_version_id=rule_version.id, calculation_base=rule_version.calculation_base,
                rate=rule_version.rate, base_amount_minor=base_amount, pool_amount_minor=pool_amount,
                recipient_employee_id=None,
                recipient_eligibility_basis=(
                    f"NOT_IMPLEMENTED: distribution_method={rule_version.distribution_method!r} is not yet "
                    "computable by this engine; no outbound allocation was made."
                ),
                no_eligible_recipient=True, allocated_amount_minor=0, settlement_time=settlement_time,
            )
        )
        return

    role_holders = _employees_with_role_at(
        session, restaurant_id=restaurant_id, restaurant_role_id=rule_version.recipient_role_id,
        location_id=order.location_id, at=settlement_time,
    )
    shift_active = _employees_shift_active_at(session, location_id=order.location_id, at=settlement_time)
    eligible_ids = sorted(role_holders & shift_active)

    if eligible_ids:
        shares = equal_split(pool_amount, eligible_ids)
        for emp_id in eligible_ids:
            session.add(
                m.TipDistributionAllocation(
                    calculation_run_id=run.id, order_id=order.id, source_employee_id=source_employee_id,
                    rule_version_id=rule_version.id, calculation_base=rule_version.calculation_base,
                    rate=rule_version.rate, base_amount_minor=base_amount, pool_amount_minor=pool_amount,
                    recipient_employee_id=emp_id,
                    recipient_eligibility_basis=(
                        f"ACTIVE_AT_SETTLEMENT: held Recipient Role {role_name!r} with an active Shift at "
                        f"Settlement Time {settlement_time.isoformat()}; EQUAL split across "
                        f"{len(eligible_ids)} eligible recipient(s)."
                    ),
                    no_eligible_recipient=False, allocated_amount_minor=shares[emp_id],
                    settlement_time=settlement_time,
                )
            )
            summary.allocations_produced += 1
    else:
        # Task §11 — SOURCE_RETAINS: generated outbound allocation = 0, and
        # the fact that nobody was eligible is preserved explicitly, never
        # silently omitted.
        session.add(
            m.TipDistributionAllocation(
                calculation_run_id=run.id, order_id=order.id, source_employee_id=source_employee_id,
                rule_version_id=rule_version.id, calculation_base=rule_version.calculation_base,
                rate=rule_version.rate, base_amount_minor=base_amount, pool_amount_minor=pool_amount,
                recipient_employee_id=None,
                recipient_eligibility_basis=(
                    f"NO_ELIGIBLE_RECIPIENT: no Employee held Recipient Role {role_name!r} with an active Shift "
                    f"at Settlement Time {settlement_time.isoformat()}; SOURCE_RETAINS applied — the source "
                    "employee retains the full pool."
                ),
                no_eligible_recipient=True, allocated_amount_minor=0, settlement_time=settlement_time,
            )
        )


def _orders_in_scope(
    session: Session, *, restaurant_id: int, period_start: datetime, period_end: datetime,
) -> list[m.Order]:
    """Every Order at this Restaurant's Location(s) whose Settlement Time
    (task §5's canonical helper) falls within `[period_start, period_end)`.
    `Order.created_at <= period_end` is a safe, non-excluding prefilter (an
    Order cannot settle before it is created); the authoritative filter is
    always the actual computed Settlement Time, never `created_at` itself.

    `period_start`/`period_end` are normalized to timezone-aware UTC here
    (never assumed) since a caller may pass a `TipDistributionCalculationRun`
    attribute that came back offset-naive after a SQLite round-trip
    (`_aware_utc`'s own docstring)."""
    period_start = _aware_utc(period_start)
    period_end = _aware_utc(period_end)
    location_ids = _restaurant_location_ids(session, restaurant_id)
    if not location_ids:
        return []
    candidates = session.scalars(
        select(m.Order).where(m.Order.location_id.in_(location_ids), m.Order.created_at <= period_end)
    ).all()
    in_scope = []
    for order in candidates:
        settlement_time = get_order_settlement_time(session, order.id)
        if settlement_time is not None and period_start <= _aware_utc(settlement_time) < period_end:
            in_scope.append(order)
    return in_scope


def _unsuperseded_conflict(
    session: Session, restaurant_id: int, period_start: datetime, period_end: datetime, exclude_run_id: int,
) -> m.TipDistributionCalculationRun | None:
    return session.scalars(
        select(m.TipDistributionCalculationRun)
        .where(
            m.TipDistributionCalculationRun.restaurant_id == restaurant_id,
            m.TipDistributionCalculationRun.id != exclude_run_id,
            m.TipDistributionCalculationRun.status == STATUS_COMPLETE,
            m.TipDistributionCalculationRun.superseded_by_calculation_run_id.is_(None),
            m.TipDistributionCalculationRun.period_start < period_end,
            m.TipDistributionCalculationRun.period_end > period_start,
        )
        .limit(1)
    ).first()


def run_tip_distribution_calculation(
    session: Session, *, restaurant_id: int, period_start: datetime, period_end: datetime,
) -> tuple[m.TipDistributionCalculationRun, CalculationSummary]:
    """Task §17's "Calculate Tips" action. Always persists (added to
    `session`, not committed — the caller decides when to commit, matching
    this codebase's existing convention); there is no separate dry-run mode
    for this first version (task §15 stops at a clean CALCULATED/REVIEWABLE
    state, with no approval/lock workflow to preview against yet).

    Task §16 "recalculation safety": recalculating the EXACT same
    `period_start`/`period_end` as an existing COMPLETE, unsuperseded run
    for this Restaurant is treated as an explicit, auditable intentional
    recalculation — the prior run is marked superseded by this one (its
    `TipDistributionAllocation` rows are never deleted or rewritten) and a
    fresh set of allocations is produced under this run's own id. A
    DIFFERENT, only partially-overlapping period is refused rather than
    guessed at, since this task's UI has no explicit "supersede run #N"
    control (task §17's "keep it simple").
    """
    run = m.TipDistributionCalculationRun(
        restaurant_id=restaurant_id, period_start=period_start, period_end=period_end, status=STATUS_RUNNING,
    )
    session.add(run)
    session.flush()

    summary = CalculationSummary()

    conflict = _unsuperseded_conflict(session, restaurant_id, period_start, period_end, exclude_run_id=run.id)
    if conflict is not None:
        if _aware_utc(conflict.period_start) == period_start and _aware_utc(conflict.period_end) == period_end:
            conflict.superseded_by_calculation_run_id = run.id
        else:
            run.status = STATUS_FAILED
            run.completed_at = utc_now()
            run.notes = (
                f"Refusing to calculate: TipDistributionCalculationRun {conflict.id} "
                f"(period {conflict.period_start.isoformat()}..{conflict.period_end.isoformat()}) already "
                "covers part of the requested period and has not been superseded. Recalculate using the "
                "EXACT same From/Through to intentionally supersede it, or choose a non-overlapping period."
            )
            return run, summary

    location_ids = _restaurant_location_ids(session, restaurant_id)
    if not location_ids:
        run.status = STATUS_FAILED
        run.completed_at = utc_now()
        run.notes = f"Restaurant {restaurant_id} has no associated Location — nothing to calculate."
        return run, summary

    active_rules = rule_svc.list_rules(session, restaurant_id, active_only=True)

    candidates = session.scalars(
        select(m.Order).where(m.Order.location_id.in_(location_ids), m.Order.created_at <= period_end)
    ).all()

    for order in candidates:
        settlement_time = get_order_settlement_time(session, order.id)
        if settlement_time is None:
            summary.orders_with_no_settlement_time += 1
            continue
        settlement_time = _aware_utc(settlement_time)
        if not (period_start <= settlement_time < period_end):
            continue

        summary.orders_considered += 1

        if order.employee_id is None:
            summary.orders_skipped_no_employee += 1
            continue

        voluntary_minor, gratuity_minor = _order_gross_tip_components(session, order)
        owner_role_ids = _roles_held_by_employee_at(
            session, restaurant_id=restaurant_id, employee_id=order.employee_id, location_id=order.location_id,
            at=settlement_time,
        )

        for rule in active_rules:
            version = rule_svc.get_version_effective_at(session, rule.id, settlement_time)
            if version is None or version.source_role_id not in owner_role_ids:
                continue
            _apply_rule_to_order(
                session, run=run, order=order, restaurant_id=restaurant_id, source_employee_id=order.employee_id,
                settlement_time=settlement_time, rule_version=version, voluntary_minor=voluntary_minor,
                gratuity_minor=gratuity_minor, summary=summary,
            )

    session.flush()
    run.status = STATUS_COMPLETE
    run.completed_at = utc_now()
    run.notes = (
        f"orders_considered={summary.orders_considered} "
        f"orders_with_no_settlement_time={summary.orders_with_no_settlement_time} "
        f"orders_skipped_no_employee={summary.orders_skipped_no_employee} "
        f"rules_applied={summary.rules_applied} allocations_produced={summary.allocations_produced} "
        f"rules_not_implemented={summary.rules_not_implemented}"
    )
    return run, summary


def get_latest_unsuperseded_run(
    session: Session, *, restaurant_id: int, period_start: datetime, period_end: datetime,
) -> m.TipDistributionCalculationRun | None:
    """The current, unsuperseded COMPLETE run for the EXACT requested
    period, if one exists — what the Review UI should show for this
    From/Through without re-running the calculation."""
    stmt = (
        select(m.TipDistributionCalculationRun)
        .where(
            m.TipDistributionCalculationRun.restaurant_id == restaurant_id,
            m.TipDistributionCalculationRun.period_start == period_start,
            m.TipDistributionCalculationRun.period_end == period_end,
            m.TipDistributionCalculationRun.status == STATUS_COMPLETE,
            m.TipDistributionCalculationRun.superseded_by_calculation_run_id.is_(None),
        )
        .order_by(m.TipDistributionCalculationRun.id.desc())
    )
    return session.scalars(stmt).first()


def build_employee_review(session: Session, run: m.TipDistributionCalculationRun) -> list[EmployeeReviewRow]:
    """Task §17/§19 — one row per Employee touched by this run, either as a
    Gross-Tip-earning Order owner, an outbound source, or an inbound
    recipient. Every figure is recomputed from persisted facts each call —
    never read from a stored aggregate."""
    orders_in_scope = _orders_in_scope(
        session, restaurant_id=run.restaurant_id, period_start=run.period_start, period_end=run.period_end,
    )
    orders_by_id = {order.id: order for order in orders_in_scope}

    gross_by_employee: dict[int, int] = {}
    for order in orders_in_scope:
        if order.employee_id is None:
            continue
        voluntary_minor, gratuity_minor = _order_gross_tip_components(session, order)
        gross_by_employee[order.employee_id] = (
            gross_by_employee.get(order.employee_id, 0) + voluntary_minor + gratuity_minor
        )

    allocations = session.scalars(
        select(m.TipDistributionAllocation).where(m.TipDistributionAllocation.calculation_run_id == run.id)
    ).all()

    outbound_by_employee: dict[int, int] = {}
    inbound_by_employee: dict[int, int] = {}
    warnings_by_employee: dict[int, list[str]] = {}
    orders_by_employee: dict[int, set[int]] = {}
    for order in orders_in_scope:
        if order.employee_id is not None:
            orders_by_employee.setdefault(order.employee_id, set()).add(order.id)
    for allocation in allocations:
        if allocation.source_employee_id is not None:
            outbound_by_employee[allocation.source_employee_id] = (
                outbound_by_employee.get(allocation.source_employee_id, 0) + allocation.allocated_amount_minor
            )
            orders_by_employee.setdefault(allocation.source_employee_id, set()).add(allocation.order_id)
            if allocation.no_eligible_recipient:
                warnings_by_employee.setdefault(allocation.source_employee_id, []).append(
                    f"Order {allocation.order_id}: no eligible recipient for this rule — pool retained."
                )
        if allocation.recipient_employee_id is not None:
            inbound_by_employee[allocation.recipient_employee_id] = (
                inbound_by_employee.get(allocation.recipient_employee_id, 0) + allocation.allocated_amount_minor
            )
            orders_by_employee.setdefault(allocation.recipient_employee_id, set()).add(allocation.order_id)

    order_ids = list(orders_by_id.keys())
    refund_order_ids: set[int] = (
        set(session.scalars(select(m.Refund.order_id).where(m.Refund.order_id.in_(order_ids))).all())
        if order_ids else set()
    )
    for order_id in refund_order_ids:
        order = orders_by_id.get(order_id)
        if order is not None and order.employee_id is not None:
            warnings_by_employee.setdefault(order.employee_id, []).append(
                # Task §20 — displayed as a warning only; never changes the calculation.
                f"Order {order_id} has a Refund on record — not automatically reflected in this calculation."
            )

    employee_ids = sorted(set(gross_by_employee) | set(outbound_by_employee) | set(inbound_by_employee))
    employees_by_id = (
        {e.id: e for e in session.scalars(select(m.Employee).where(m.Employee.id.in_(employee_ids))).all()}
        if employee_ids else {}
    )

    rows: list[EmployeeReviewRow] = []
    for emp_id in employee_ids:
        gross = gross_by_employee.get(emp_id, 0)
        outbound = outbound_by_employee.get(emp_id, 0)
        inbound = inbound_by_employee.get(emp_id, 0)
        rows.append(
            EmployeeReviewRow(
                employee_id=emp_id,
                display_name=employees_by_id[emp_id].display_name if emp_id in employees_by_id else None,
                gross_earned_tips_minor=gross, outbound_tip_out_minor=outbound, inbound_tip_out_minor=inbound,
                net_before_adjustments_minor=gross - outbound + inbound,
                has_warning=bool(warnings_by_employee.get(emp_id)),
                warning_notes=warnings_by_employee.get(emp_id, []),
                order_ids=sorted(orders_by_employee.get(emp_id, set())),
            )
        )
    return rows


def get_order_drilldown(session: Session, run: m.TipDistributionCalculationRun, order_id: int) -> dict | None:
    """Task §18 — "why did this employee receive/pay this amount" for one
    Order under this run. Returns `None` only if `order_id` is not actually
    part of this run's period/Location scope at all."""
    order = session.get(m.Order, order_id)
    if order is None:
        return None
    location_ids = _restaurant_location_ids(session, run.restaurant_id)
    if order.location_id not in location_ids:
        return None
    settlement_time = get_order_settlement_time(session, order.id)
    if settlement_time is None:
        return None
    settlement_time = _aware_utc(settlement_time)
    if not (_aware_utc(run.period_start) <= settlement_time < _aware_utc(run.period_end)):
        return None

    voluntary_minor, gratuity_minor = _order_gross_tip_components(session, order)
    allocations = session.scalars(
        select(m.TipDistributionAllocation).where(
            m.TipDistributionAllocation.calculation_run_id == run.id, m.TipDistributionAllocation.order_id == order_id,
        )
    ).all()
    refunds = session.scalars(select(m.Refund).where(m.Refund.order_id == order_id)).all()

    return {
        "order": order,
        "settlement_time": settlement_time,
        "voluntary_tip_minor": voluntary_minor,
        "gratuity_minor": gratuity_minor,
        "gross_earned_tips_minor": voluntary_minor + gratuity_minor,
        "allocations": allocations,
        "refunds": refunds,
    }
