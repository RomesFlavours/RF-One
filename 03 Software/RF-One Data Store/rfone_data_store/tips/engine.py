"""Post-hoc Tip calculation engine (task §17-19).

Central principle: RF-One does not observe or control the POS at payment
time. It calculates later, from already-persisted source facts:

    Payment -> recorded PaymentTip -> Order context -> Payment timestamp
    -> Shifts intersecting that timestamp -> EmployeeAssignment / Restaurant
    Role valid at that timestamp -> Tip Policy -> atomic allocations

Nothing here introduces a new Tip timestamp: the temporal anchor for every
calculation is always `Payment.created_at` (the parent Payment's own
canonical timestamp), never a value stored on `PaymentTip` itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from .resolvers import AMBIGUOUS, RESOLVED, ServiceAttributionResolver, ServiceAttributionResult
from .rounding import equal_split, split_largest_remainder

MODE_DRY_RUN = "DRY_RUN"
MODE_PERSIST = "PERSIST"

STATUS_RUNNING = "RUNNING"
STATUS_COMPLETE = "COMPLETE"
STATUS_FAILED = "FAILED"

SEVERITY_BLOCKING = "BLOCKING"
SEVERITY_WARNING = "WARNING"

ISSUE_NO_VALID_POLICY = "NO_VALID_POLICY"
ISSUE_SERVICE_OWNER_UNRESOLVED = "SERVICE_OWNER_UNRESOLVED"
ISSUE_SERVICE_OWNER_AMBIGUOUS = "SERVICE_OWNER_AMBIGUOUS"
ISSUE_NO_ELIGIBLE_RECIPIENT = "NO_ELIGIBLE_RECIPIENT"
ISSUE_SHIFT_ASSIGNMENT_GAP = "SHIFT_ASSIGNMENT_GAP"
# Reserved (TASK_TIPS_002): no longer raised by _resolve_role_present. A
# concurrent EmployeeAssignment under a different RestaurantRole is not, by
# itself, a conflict (Manager + Server is legitimate — see Restaurant
# Semantic Model.md §9). Kept as a documented issue_type for a genuine
# future ambiguity (task §7 of TASK_TIPS_002), e.g. a policy that explicitly
# requires mutually exclusive role resolution and the data cannot satisfy
# it — no such case is implemented yet.
ISSUE_CONFLICTING_ASSIGNMENTS = "CONFLICTING_ASSIGNMENTS"
ISSUE_FAILED_PAYMENT_WITH_TIP = "FAILED_PAYMENT_WITH_TIP"
ISSUE_REFUND_REVIEW_REQUIRED = "REFUND_REVIEW_REQUIRED"
ISSUE_ALLOCATION_RECONCILIATION_FAILURE = "ALLOCATION_RECONCILIATION_FAILURE"

BASIS_SERVICE_OWNER = "SERVICE_OWNER"
BASIS_ROLE_PRESENT_AT_PAYMENT = "ROLE_PRESENT_AT_PAYMENT"

BEHAVIOR_RETURN_TO_SERVICE_OWNER = "RETURN_TO_SERVICE_OWNER"
BEHAVIOR_REDISTRIBUTE = "REDISTRIBUTE_TO_ELIGIBLE_COMPONENTS"
BEHAVIOR_LEAVE_UNALLOCATED = "LEAVE_UNALLOCATED"

_HUNDRED = Decimal("100")
_SHARE_TOLERANCE = Decimal("0.0001")


@dataclass
class CalculationSummary:
    source_tips_considered: int = 0
    source_tip_amount_minor: int = 0
    allocations_produced: int = 0
    allocated_amount_minor: int = 0
    unallocated_amount_minor: int = 0
    blocking_issue_count: int = 0
    warning_issue_count: int = 0


@dataclass
class _ComponentOutcome:
    component: "m.TipPolicyComponent"
    target_amount: int
    eligible_ids: list[int]
    gap_detected: bool = False
    resolved_via: str = ""  # human-readable, for the audit `reason` trail


def _restaurant_location_ids(session: Session, restaurant_id: int) -> set[int]:
    rows = session.scalars(
        select(m.RestaurantLocation.location_id).where(
            m.RestaurantLocation.restaurant_id == restaurant_id
        )
    ).all()
    return set(rows)


def _valid_policy_at(
    session: Session, restaurant_id: int, location_id: int, at: datetime
) -> "m.TipPolicy | None":
    candidates = session.scalars(
        select(m.TipPolicy).where(
            m.TipPolicy.restaurant_id == restaurant_id,
            m.TipPolicy.status == "ACTIVE",
            m.TipPolicy.valid_from <= at,
            (m.TipPolicy.valid_to.is_(None)) | (m.TipPolicy.valid_to > at),
            (m.TipPolicy.location_id.is_(None)) | (m.TipPolicy.location_id == location_id),
        )
    ).all()
    if not candidates:
        return None
    # Deterministic preference: a location-specific policy over a
    # restaurant-wide one, then the most recently started.
    candidates.sort(key=lambda p: (p.location_id is None, -p.valid_from.timestamp(), -p.id))
    return candidates[0]


def _shift_active_employee_ids(
    session: Session, location_ids: set[int], at: datetime
) -> set[int]:
    if not location_ids:
        return set()
    rows = session.scalars(
        select(m.Shift.employee_id)
        .join(m.Employee, m.Employee.id == m.Shift.employee_id)
        .where(
            m.Employee.location_id.in_(location_ids),
            m.Shift.clock_in.is_not(None),
            m.Shift.clock_in <= at,
            (m.Shift.clock_out.is_(None)) | (m.Shift.clock_out >= at),
        )
    ).all()
    return set(rows)


def _assignment_employee_ids(
    session: Session, restaurant_id: int, at: datetime, restaurant_role_id: int | None = None
) -> set[int]:
    conditions = [
        m.EmployeeAssignment.restaurant_id == restaurant_id,
        m.EmployeeAssignment.valid_from <= at,
        (m.EmployeeAssignment.valid_to.is_(None)) | (m.EmployeeAssignment.valid_to > at),
    ]
    if restaurant_role_id is not None:
        conditions.append(m.EmployeeAssignment.restaurant_role_id == restaurant_role_id)
    rows = session.scalars(select(m.EmployeeAssignment.employee_id).where(*conditions)).all()
    return set(rows)


def _resolve_role_present(
    session: Session,
    restaurant_id: int,
    restaurant_role_id: int,
    location_ids: set[int],
    at: datetime,
) -> tuple[list[int], bool]:
    """Employees with a Shift active at `at` AND at least one valid
    EmployeeAssignment at `at` matching `restaurant_role_id`/`restaurant_id`
    (task §7-8 of TASK_TIPS_001; corrected by TASK_TIPS_002 §3-5).

    Returns (eligible_employee_ids_sorted, gap_detected). `gap_detected`: at
    least one Shift-present employee has zero valid Assignment at `at` at
    all (an epistemic gap — SHIFT_ASSIGNMENT_GAP — not the same fact as
    "confirmed nobody in this role").

    Concurrent Employee Assignments are not automatically a conflict
    (Restaurant Semantic Model.md §9, Organization/Employee Assignment.md
    "Multi-role / multi-area capability"): an Employee holding another
    valid-at-`at` Assignment under a DIFFERENT Restaurant Role — in the same
    or a different Operational Area (e.g. Manager + Server) — does NOT
    disqualify them here. Eligibility for this component depends only on
    whether a matching Assignment exists; other concurrent Assignments are
    irrelevant to that determination (TASK_TIPS_002).
    """
    shift_ids = _shift_active_employee_ids(session, location_ids, at)
    if not shift_ids:
        return [], False

    role_assignment_employee_ids = session.scalars(
        select(m.EmployeeAssignment.employee_id).where(
            m.EmployeeAssignment.restaurant_id == restaurant_id,
            m.EmployeeAssignment.restaurant_role_id == restaurant_role_id,
            m.EmployeeAssignment.employee_id.in_(shift_ids),
            m.EmployeeAssignment.valid_from <= at,
            (m.EmployeeAssignment.valid_to.is_(None)) | (m.EmployeeAssignment.valid_to > at),
        )
    ).all()
    # A set naturally deduplicates an Employee who holds more than one
    # matching Assignment at `at` (e.g. the Role valid in two Operational
    # Areas at once) — one economic headcount share per Employee, never two
    # (TASK_TIPS_002 §5).
    eligible = sorted(set(role_assignment_employee_ids))

    any_assignment_ids = _assignment_employee_ids(session, restaurant_id, at)
    gap_detected = bool(shift_ids - any_assignment_ids)
    return eligible, gap_detected


def _add_issue(
    session: Session,
    run: "m.TipCalculationRun",
    *,
    issue_type: str,
    severity: str,
    details: str,
    payment_tip_id: int | None = None,
    payment_id: int | None = None,
    order_id: int | None = None,
) -> None:
    session.add(
        m.TipCalculationIssue(
            calculation_run_id=run.id,
            payment_tip_id=payment_tip_id,
            payment_id=payment_id,
            order_id=order_id,
            issue_type=issue_type,
            severity=severity,
            details=details,
        )
    )


def _candidate_payment_tips(
    session: Session, location_ids: set[int], period_start: datetime, period_end: datetime
):
    if not location_ids:
        return []
    return (
        session.scalars(
            select(m.PaymentTip)
            .join(m.Payment, m.Payment.id == m.PaymentTip.payment_id)
            .join(m.Order, m.Order.id == m.Payment.order_id)
            .where(
                m.Order.location_id.in_(location_ids),
                m.Payment.created_at >= period_start,
                m.Payment.created_at < period_end,
            )
            .order_by(m.PaymentTip.payment_id)
        )
        .all()
    )


def run_tip_calculation(
    session: Session,
    *,
    restaurant_id: int,
    period_start: datetime,
    period_end: datetime,
    resolver: ServiceAttributionResolver,
    mode: str = MODE_DRY_RUN,
    calculation_version: str = "1",
) -> tuple["m.TipCalculationRun", CalculationSummary]:
    """Run the post-hoc Tip calculation for `restaurant_id` over
    [`period_start`, `period_end`) using the Payment's own canonical
    timestamp as the period selector (task §20) — never a Tip-entry time,
    which does not exist as a separate field in this schema at all.

    Always builds a `TipCalculationRun` plus its `TipAllocation`/
    `TipCalculationIssue` rows in `session` (added, not yet committed). The
    caller decides whether to commit (`mode=PERSIST`) or roll back
    (`mode=DRY_RUN`, the safe default) — this function never commits.
    """
    run = m.TipCalculationRun(
        restaurant_id=restaurant_id,
        period_start=period_start,
        period_end=period_end,
        status=STATUS_RUNNING,
        mode=mode,
        calculation_version=calculation_version,
    )
    session.add(run)
    session.flush()

    summary = CalculationSummary()
    location_ids = _restaurant_location_ids(session, restaurant_id)

    if not location_ids:
        _add_issue(
            session,
            run,
            issue_type=ISSUE_NO_VALID_POLICY,
            severity=SEVERITY_BLOCKING,
            details=(
                f"Restaurant {restaurant_id} has no associated Location "
                "(no RestaurantLocation row) — no Payment can be scoped to it."
            ),
        )
        summary.blocking_issue_count += 1
        run.status = STATUS_FAILED
        run.completed_at = datetime.now(period_start.tzinfo)
        return run, summary

    service_result_cache: dict[int, "ServiceAttributionResult"] = {}
    bad_policy_ids: set[int] = set()

    tips = _candidate_payment_tips(session, location_ids, period_start, period_end)

    for tip in tips:
        summary.source_tips_considered += 1
        summary.source_tip_amount_minor += tip.amount or 0

        payment = session.get(m.Payment, tip.payment_id)
        order = session.get(m.Order, payment.order_id)
        t = payment.created_at

        if payment.result != "SUCCESS":
            _add_issue(
                session,
                run,
                issue_type=ISSUE_FAILED_PAYMENT_WITH_TIP,
                severity=SEVERITY_BLOCKING,
                details=(
                    f"Payment {payment.id} result={payment.result!r} is not economically "
                    "valid (SUCCESS); its recorded Tip was not allocated."
                ),
                payment_tip_id=tip.payment_id,
                payment_id=payment.id,
                order_id=order.id,
            )
            summary.blocking_issue_count += 1
            summary.unallocated_amount_minor += tip.amount or 0
            continue

        refunds = session.scalars(select(m.Refund).where(m.Refund.payment_id == payment.id)).all()
        if refunds:
            tip_refunds = [r for r in refunds if r.tip_amount not in (None, 0)]
            if tip_refunds:
                _add_issue(
                    session,
                    run,
                    issue_type=ISSUE_REFUND_REVIEW_REQUIRED,
                    severity=SEVERITY_BLOCKING,
                    details=(
                        f"Payment {payment.id} has {len(tip_refunds)} Refund(s) with an "
                        "explicit non-zero tip_amount — the recorded Tip was NOT allocated "
                        "pending human review, since RF-One does not infer how a Tip "
                        "refund should be netted against a prior/future allocation."
                    ),
                    payment_tip_id=tip.payment_id,
                    payment_id=payment.id,
                    order_id=order.id,
                )
                summary.blocking_issue_count += 1
                summary.unallocated_amount_minor += tip.amount or 0
                continue
            _add_issue(
                session,
                run,
                issue_type=ISSUE_REFUND_REVIEW_REQUIRED,
                severity=SEVERITY_WARNING,
                details=(
                    f"Payment {payment.id} has {len(refunds)} Refund(s) with no tip_amount "
                    "evidence — no source fact indicates the Tip itself was affected, so it "
                    "was allocated in full; flagged for human review."
                ),
                payment_tip_id=tip.payment_id,
                payment_id=payment.id,
                order_id=order.id,
            )
            summary.warning_issue_count += 1

        policy = _valid_policy_at(session, restaurant_id, order.location_id, t)
        if policy is None:
            _add_issue(
                session,
                run,
                issue_type=ISSUE_NO_VALID_POLICY,
                severity=SEVERITY_BLOCKING,
                details=f"No ACTIVE TipPolicy is valid for restaurant {restaurant_id} at {t.isoformat()}.",
                payment_tip_id=tip.payment_id,
                payment_id=payment.id,
                order_id=order.id,
            )
            summary.blocking_issue_count += 1
            summary.unallocated_amount_minor += tip.amount or 0
            continue

        if policy.id in bad_policy_ids:
            summary.unallocated_amount_minor += tip.amount or 0
            continue

        components = [c for c in policy.components if c.active is not False]
        if not components:
            _add_issue(
                session,
                run,
                issue_type=ISSUE_NO_VALID_POLICY,
                severity=SEVERITY_BLOCKING,
                details=f"TipPolicy {policy.id} has no active TipPolicyComponent.",
                payment_tip_id=tip.payment_id,
                payment_id=payment.id,
                order_id=order.id,
            )
            summary.blocking_issue_count += 1
            summary.unallocated_amount_minor += tip.amount or 0
            continue

        share_sum = sum((c.share_percentage for c in components), Decimal(0))
        if share_sum > _HUNDRED + _SHARE_TOLERANCE:
            _add_issue(
                session,
                run,
                issue_type=ISSUE_ALLOCATION_RECONCILIATION_FAILURE,
                severity=SEVERITY_BLOCKING,
                details=(
                    f"TipPolicy {policy.id} components sum to {share_sum}% (>100%) — cannot "
                    "reconcile exactly to the source Tip without silently renormalizing the "
                    "Restaurant's configured shares. Blocking every Tip under this policy "
                    "until corrected."
                ),
            )
            summary.blocking_issue_count += 1
            bad_policy_ids.add(policy.id)
            summary.unallocated_amount_minor += tip.amount or 0
            continue

        leftover_share = _HUNDRED - share_sum
        weights = [c.share_percentage for c in components] + [leftover_share]
        amounts = split_largest_remainder(tip.amount or 0, weights)
        component_amounts = dict(zip((c.id for c in components), amounts[:-1]))
        design_leftover_amount = amounts[-1]

        if order.id not in service_result_cache:
            service_result_cache[order.id] = resolver.resolve(session, order)
        service_result = service_result_cache[order.id]

        outcomes: dict[int, _ComponentOutcome] = {}
        for component in components:
            target = component_amounts[component.id]
            if component.recipient_basis == BASIS_SERVICE_OWNER:
                if service_result.status == RESOLVED:
                    outcomes[component.id] = _ComponentOutcome(
                        component, target, sorted(service_result.employee_ids), resolved_via="service_owner"
                    )
                else:
                    outcomes[component.id] = _ComponentOutcome(component, target, [])
            elif component.recipient_basis == BASIS_ROLE_PRESENT_AT_PAYMENT:
                eligible, gap = _resolve_role_present(
                    session, restaurant_id, component.restaurant_role_id, location_ids, t
                )
                outcomes[component.id] = _ComponentOutcome(
                    component, target, eligible, gap_detected=gap,
                    resolved_via="role_present_at_payment",
                )
            else:
                outcomes[component.id] = _ComponentOutcome(component, target, [])

        tip_allocated = 0
        tip_unallocated = design_leftover_amount

        # First pass: components with a nonempty eligible set allocate directly.
        pending: list[_ComponentOutcome] = []
        for component in components:
            outcome = outcomes[component.id]
            if outcome.eligible_ids:
                for emp_id, amt in equal_split(outcome.target_amount, outcome.eligible_ids).items():
                    session.add(
                        m.TipAllocation(
                            calculation_run_id=run.id,
                            payment_tip_id=tip.payment_id,
                            payment_id=payment.id,
                            order_id=order.id,
                            policy_component_id=component.id,
                            employee_id=emp_id,
                            allocated_amount_minor=amt,
                            reason=(
                                f"component #{component.sequence} {component.recipient_basis} "
                                f"share={component.share_percentage}% via {outcome.resolved_via}, "
                                f"{len(outcome.eligible_ids)} eligible employee(s), "
                                f"{component.split_method}"
                            ),
                        )
                    )
                    tip_allocated += amt
                    summary.allocations_produced += 1
            else:
                pending.append(outcome)

        # Second pass: apply each pending component's no_eligible_behavior.
        successful = [
            outcomes[c.id] for c in components if outcomes[c.id].eligible_ids
        ]
        for outcome in pending:
            component = outcome.component
            if component.recipient_basis == BASIS_SERVICE_OWNER and service_result.status != RESOLVED:
                issue_type = (
                    ISSUE_SERVICE_OWNER_AMBIGUOUS
                    if service_result.status == AMBIGUOUS
                    else ISSUE_SERVICE_OWNER_UNRESOLVED
                )
                _add_issue(
                    session,
                    run,
                    issue_type=issue_type,
                    severity=SEVERITY_BLOCKING,
                    details=(
                        f"Order {order.id}: service owner {service_result.status} "
                        f"({service_result.detail or 'no detail'}); component #{component.sequence} "
                        f"({component.share_percentage}%) not allocated."
                    ),
                    payment_tip_id=tip.payment_id,
                    payment_id=payment.id,
                    order_id=order.id,
                )
                summary.blocking_issue_count += 1
                tip_unallocated += outcome.target_amount
                continue

            if outcome.gap_detected:
                _add_issue(
                    session,
                    run,
                    issue_type=ISSUE_SHIFT_ASSIGNMENT_GAP,
                    severity=SEVERITY_WARNING,
                    details=(
                        f"Component #{component.sequence} (role {component.restaurant_role_id}): "
                        "at least one Employee present via Shift at the payment timestamp has no "
                        "EmployeeAssignment at all for this Restaurant at that time — role "
                        "eligibility could not be fully verified for them."
                    ),
                    payment_tip_id=tip.payment_id,
                    payment_id=payment.id,
                    order_id=order.id,
                )
                summary.warning_issue_count += 1

            if component.no_eligible_behavior == BEHAVIOR_RETURN_TO_SERVICE_OWNER:
                if service_result.status == RESOLVED:
                    for emp_id, amt in equal_split(
                        outcome.target_amount, sorted(service_result.employee_ids)
                    ).items():
                        session.add(
                            m.TipAllocation(
                                calculation_run_id=run.id,
                                payment_tip_id=tip.payment_id,
                                payment_id=payment.id,
                                order_id=order.id,
                                policy_component_id=component.id,
                                employee_id=emp_id,
                                allocated_amount_minor=amt,
                                reason=(
                                    f"component #{component.sequence} {component.recipient_basis} "
                                    f"had no eligible recipient; RETURN_TO_SERVICE_OWNER redirected "
                                    f"{component.share_percentage}% to the resolved service owner"
                                ),
                            )
                        )
                        tip_allocated += amt
                        summary.allocations_produced += 1
                else:
                    issue_type = (
                        ISSUE_SERVICE_OWNER_AMBIGUOUS
                        if service_result.status == AMBIGUOUS
                        else ISSUE_SERVICE_OWNER_UNRESOLVED
                    )
                    _add_issue(
                        session,
                        run,
                        issue_type=issue_type,
                        severity=SEVERITY_BLOCKING,
                        details=(
                            f"Component #{component.sequence}: no eligible recipient, and "
                            f"RETURN_TO_SERVICE_OWNER could not apply because the service owner "
                            f"is {service_result.status}."
                        ),
                        payment_tip_id=tip.payment_id,
                        payment_id=payment.id,
                        order_id=order.id,
                    )
                    summary.blocking_issue_count += 1
                    tip_unallocated += outcome.target_amount

            elif component.no_eligible_behavior == BEHAVIOR_REDISTRIBUTE:
                if successful:
                    redistribute_weights = [o.component.share_percentage for o in successful]
                    redistribute_amounts = split_largest_remainder(
                        outcome.target_amount, redistribute_weights
                    )
                    # Aggregate per employee first (an employee could be eligible
                    # under more than one target component) so at most one
                    # TipAllocation row is ever inserted per (component, employee)
                    # — required both for auditability and for the (run, tip,
                    # component, employee) uniqueness guard.
                    per_employee: dict[int, int] = {}
                    target_sequences: dict[int, list[int]] = {}
                    for target_outcome, extra in zip(successful, redistribute_amounts):
                        for emp_id, amt in equal_split(extra, target_outcome.eligible_ids).items():
                            if amt == 0:
                                continue
                            per_employee[emp_id] = per_employee.get(emp_id, 0) + amt
                            target_sequences.setdefault(emp_id, []).append(target_outcome.component.sequence)
                    for emp_id, amt in per_employee.items():
                        # Attributed to the ORIGINATING (empty) component, not the
                        # target's — this row accounts for component `component`'s
                        # own share (redirected), keeping (run, tip, component,
                        # employee) unique even when the target employee also
                        # separately earns a target component's own share.
                        session.add(
                            m.TipAllocation(
                                calculation_run_id=run.id,
                                payment_tip_id=tip.payment_id,
                                payment_id=payment.id,
                                order_id=order.id,
                                policy_component_id=component.id,
                                employee_id=emp_id,
                                allocated_amount_minor=amt,
                                reason=(
                                    f"component #{component.sequence} had no eligible recipient; "
                                    f"REDISTRIBUTE_TO_ELIGIBLE_COMPONENTS moved this share to the "
                                    f"eligible employee(s) of component(s) "
                                    f"{sorted(set(target_sequences[emp_id]))}"
                                ),
                            )
                        )
                        tip_allocated += amt
                        summary.allocations_produced += 1
                else:
                    _add_issue(
                        session,
                        run,
                        issue_type=ISSUE_NO_ELIGIBLE_RECIPIENT,
                        severity=SEVERITY_WARNING,
                        details=(
                            f"Component #{component.sequence}: no eligible recipient, and "
                            "REDISTRIBUTE_TO_ELIGIBLE_COMPONENTS could not apply because no "
                            "other component in this Tip had an eligible recipient either."
                        ),
                        payment_tip_id=tip.payment_id,
                        payment_id=payment.id,
                        order_id=order.id,
                    )
                    summary.warning_issue_count += 1
                    tip_unallocated += outcome.target_amount

            elif component.no_eligible_behavior == BEHAVIOR_LEAVE_UNALLOCATED:
                _add_issue(
                    session,
                    run,
                    issue_type=ISSUE_NO_ELIGIBLE_RECIPIENT,
                    severity=SEVERITY_WARNING,
                    details=(
                        f"Component #{component.sequence}: no eligible recipient; "
                        "LEAVE_UNALLOCATED applied as explicitly configured."
                    ),
                    payment_tip_id=tip.payment_id,
                    payment_id=payment.id,
                    order_id=order.id,
                )
                summary.warning_issue_count += 1
                tip_unallocated += outcome.target_amount

        if tip_allocated + tip_unallocated != (tip.amount or 0):
            _add_issue(
                session,
                run,
                issue_type=ISSUE_ALLOCATION_RECONCILIATION_FAILURE,
                severity=SEVERITY_BLOCKING,
                details=(
                    f"PaymentTip {tip.payment_id}: allocated ({tip_allocated}) + unallocated "
                    f"({tip_unallocated}) != source amount ({tip.amount}). This should never "
                    "happen by construction; surfaced defensively rather than silently accepted."
                ),
                payment_tip_id=tip.payment_id,
                payment_id=payment.id,
                order_id=order.id,
            )
            summary.blocking_issue_count += 1

        summary.allocated_amount_minor += tip_allocated
        summary.unallocated_amount_minor += tip_unallocated

    run.status = STATUS_COMPLETE
    run.completed_at = datetime.now(period_start.tzinfo)
    run.notes = (
        f"considered={summary.source_tips_considered} "
        f"allocated_minor={summary.allocated_amount_minor} "
        f"unallocated_minor={summary.unallocated_amount_minor} "
        f"blocking={summary.blocking_issue_count} warnings={summary.warning_issue_count}"
    )
    return run, summary
