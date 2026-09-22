"""Tip Distribution Engine — core calculation/allocation logic
(TIP_DISTRIBUTION_ENGINE_001).

STATELESS (TIPS_STATELESS_CALCULATION_001): `calculate_tips` derives the
complete result for any requested period IN MEMORY and persists nothing —
no calculation run, no allocation rows, no aggregate. Any period may
therefore be recalculated freely and repeatedly, including periods that
overlap, contain, or are contained by any other. Overlap detection,
overlap refusal and run supersession no longer exist, because no stored
result can be contradicted. Reproducibility comes from the inputs
(Orders, Payments, Shifts, EmployeeAssignments, effective-dated
RuleVersions), all of which are persisted facts.

Implements ONLY what the task authorizes: Order-level Gross Earned Tips,
Settlement-Time-based rule-version selection, ACTIVE_AT_SETTLEMENT
eligibility from persisted Shift facts, EQUAL distribution, and atomic
allocation results. Reuses
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
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..ingestion.common import utc_now
from ..technical.connectors.clover.acquisition import get_order_settlement_time
from . import distribution_rule_service as rule_svc

UTC_TZ = timezone.utc
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


# TIPS_OPERATIONAL_RESULTS_AND_CALCULATION_FIX_001 §3/§5 — which side of
# the distribution an employee is on in THIS run. Derived per run, never
# a property of the person: the same employee may own orders one week and
# only receive tip-out the next.
RESULT_TYPE_SERVICE_OWNER = "SERVICE_OWNER"
RESULT_TYPE_HOST = "HOST"
RESULT_TYPE_BOTH = "BOTH"


@dataclass
class AllocationLine:
    """One calculated allocation, held IN MEMORY only
    (TIPS_STATELESS_CALCULATION_001).

    Carries exactly the fields the retired `TipDistributionAllocation` table
    used to persist, so Review, Order drill-down, Host Audit and CSV export
    keep the same line-level detail — the difference is purely that this is
    derived on demand from source facts each time, never stored. Two
    calculations over the same period produce equal lines because the
    inputs (Orders, Payments, Shifts, EmployeeAssignments, effective-dated
    RuleVersions) are themselves persisted facts."""

    order_id: int
    clover_order_id: str | None
    settlement_time: datetime
    source_employee_id: int | None
    rule_id: int
    rule_version_id: int
    calculation_base: str
    rate: Decimal
    base_amount_minor: int
    # The pool ACTUALLY generated for distribution, always equal to the sum
    # of `allocated_amount_minor` across this Order's lines for this Rule
    # Version. It is 0 whenever nothing was distributed — no eligible Host,
    # or an unimplemented rule shape — because in that case no pool was
    # generated. It is NEVER "what the rate would have produced if someone
    # had been eligible": that number is not computed anywhere in RF-One.
    pool_amount_minor: int
    recipient_employee_id: int | None
    recipient_eligibility_basis: str
    no_eligible_recipient: bool
    allocated_amount_minor: int
    eligible_recipient_count: int
    # TIPS_OPERATIONAL_RESULTS_AND_CALCULATION_FIX_001 §1/§6 — the two
    # components of the Gross Tip Base, kept APART all the way down to the
    # line so a run can be reconciled directly against Clover, which
    # reports voluntary tips and automatic gratuity separately. Their sum
    # is `gross_tip_base_minor`; `base_amount_minor` is what the RULE
    # actually charged its rate against, which is the same thing only when
    # the rule's Calculation Base is TIP_PLUS_GRATUITY.
    voluntary_minor: int = 0
    gratuity_minor: int = 0
    # §6 — why no Host was eligible, retained rather than repaired. Empty
    # when a recipient was found.
    candidate_recipient_employee_ids: list[int] = field(default_factory=list)
    exclusion_reason: str | None = None

    @property
    def gross_tip_base_minor(self) -> int:
        """Voluntary + Gratuity for this Order, whatever base the rule used."""
        return self.voluntary_minor + self.gratuity_minor


@dataclass
class TipCalculationResult:
    """The complete in-memory result of one on-demand calculation
    (TIPS_STATELESS_CALCULATION_001). Nothing here is persisted: any
    period, of any length, overlapping any other, may be calculated freely
    and repeatedly.

    `unresolved_*` covers lines the engine genuinely could not compute (an
    unimplemented Calculation Base or Distribution Method). A
    NO_ELIGIBLE_RECIPIENT line is NOT unresolved — it is a fully resolved
    SOURCE_RETAINS outcome that moved $0."""

    restaurant_id: int
    period_start: datetime
    period_end: datetime
    lines: list[AllocationLine] = field(default_factory=list)
    summary: CalculationSummary = field(default_factory=CalculationSummary)
    rule_version_ids: list[int] = field(default_factory=list)
    voluntary_total_minor: int = 0
    gratuity_total_minor: int = 0
    blocked_reason: str | None = None
    # §5 — the period as the OPERATOR stated it. The UTC period_start/end
    # above are the retrieval window derived from these, not the truth.
    first_business_date: date | None = None
    last_business_date: date | None = None

    @property
    def recipient_lines(self) -> list[AllocationLine]:
        return [line for line in self.lines if line.recipient_employee_id is not None]

    @property
    def unresolved_lines(self) -> list[AllocationLine]:
        return [
            line for line in self.lines
            if line.recipient_employee_id is None
            and line.recipient_eligibility_basis.startswith("NOT_IMPLEMENTED")
        ]

    @property
    def no_eligible_recipient_lines(self) -> list[AllocationLine]:
        return [
            line for line in self.lines
            if line.recipient_employee_id is None
            and line.recipient_eligibility_basis.startswith("NO_ELIGIBLE_RECIPIENT")
        ]

    @property
    def distributed_total_minor(self) -> int:
        """What actually moved to recipients."""
        return sum(line.allocated_amount_minor for line in self.recipient_lines)

    # There is deliberately NO "retained" / "unresolved" / "would have been
    # distributed" monetary aggregate on this result.
    #
    # They were the remains of a retired reconciliation control (voluntary
    # == retained + distributed + unresolved) that has not gated anything
    # since the ONE authoritative control became
    #
    #     Total Tips + Gratuity  ==  Total Employee Entitlements
    #
    # (`OperationalTotals`). Their only surviving effect was to put a price
    # on an Order that distributed nothing — money that was never destined
    # anywhere. What the Service Owner keeps is already stated, in full and
    # per person, by `build_employee_review`'s `final_entitlement_minor`;
    # restating a slice of it as "retained" adds no fact and invites the
    # reading that something is outstanding.
    #
    # `no_eligible_recipient_lines` and `unresolved_lines` remain: they are
    # qualitative — WHICH Orders and WHY — and carry no amount of their own.


@dataclass
class EmployeeReviewRow:
    """Review table row — every figure derived fresh from source facts and
    the in-memory calculation result, never stored as its own atomic data
    (TIPS_STATELESS_CALCULATION_001)."""

    employee_id: int
    display_name: str | None
    gross_earned_tips_minor: int
    outbound_tip_out_minor: int
    inbound_tip_out_minor: int
    net_before_adjustments_minor: int
    has_warning: bool
    # TIPS_OPERATIONAL_RESULTS_AND_CALCULATION_FIX_001 §3 — the operational
    # page answers one question: how much must this employee be PAID?
    #
    # Voluntary and Gratuity stay separate because Clover reports them
    # separately and the run has to reconcile against it. `result_type`
    # says which side of the distribution this person is on, so one column
    # can show "Tip Out" for a Service Owner and "Tip Received" for a Host
    # rather than the page carrying both.
    voluntary_tips_minor: int = 0
    gratuity_minor: int = 0
    result_type: str = RESULT_TYPE_SERVICE_OWNER
    # There is deliberately NO "retained / would have been distributed"
    # figure on this row.
    #
    # When no eligible recipient was on shift at Order Open Time, no
    # distribution obligation arose, so nothing was withheld and nothing is
    # outstanding: the Service Owner earned 100% of that Order. An amount
    # describing what a rule WOULD have moved under circumstances that did
    # not occur has no functional use, and carrying it "for audit" invited
    # exactly the reading it was meant to prevent — that some amount is
    # still owed to somebody. It is not computed, not stored and not shown.
    warning_notes: list[str] = field(default_factory=list)
    # Task §18 — every Order this Employee is traceable through (as Gross-Tip
    # owner, outbound source, or inbound recipient) in this run, sorted, so
    # the Review UI can link straight to each Order's drill-down.
    order_ids: list[int] = field(default_factory=list)

    @property
    def final_entitlement_minor(self) -> int:
        """§10 — what this employee is entitled to receive for the period.

        Service Owner: Tips + Gratuity generated, minus what was ACTUALLY
        distributed to eligible recipients. An Order with no eligible Host
        deducts nothing, because no distribution obligation arose.
        Recipient: the total actually received across the period."""
        return self.net_before_adjustments_minor

    @property
    def distributed_away_minor(self) -> int:
        """§12 — shown for a Service Owner ONLY when distribution actually
        occurred."""
        return self.outbound_tip_out_minor

    @property
    def received_minor(self) -> int:
        """§12 — aggregate distribution received, for a recipient."""
        return self.inbound_tip_out_minor

    @property
    def needs_attention(self) -> bool:
        """Whether this row must not be presented as ready to pay.

        §6/§12 — a SOURCE_RETAINS outcome is NOT an attention condition. A
        Service Owner keeping 100% of an Order because no Host was on shift
        when it opened is a valid, final result, and flagging it trained
        the operator to distrust correct numbers. Only a genuine data
        warning (e.g. a Refund on record) raises attention now."""
        return self.has_warning

    @property
    def net_payable_minor(self) -> int:
        """What this employee must actually be paid for this run.

        Service Owner: Gross Tips - Tip Out. Host: Tip Received. Someone
        who is both in the same period: both, netted. Identical arithmetic
        to `net_before_adjustments_minor`, named for what the operator does
        with it — and the figure a future Mercury payment is expected to
        match (§8)."""
        return self.net_before_adjustments_minor

    @property
    def tip_out_or_received_minor(self) -> int:
        """The single movement column the operational page shows: money
        taken from a Service Owner, or money given to a Host."""
        if self.result_type == RESULT_TYPE_HOST:
            return self.inbound_tip_out_minor
        return self.outbound_tip_out_minor


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
    session: Session, *, order: m.Order, restaurant_id: int,
    source_employee_id: int, settlement_time: datetime, order_open_time: datetime,
    rule_version: m.TipDistributionRuleVersion,
    voluntary_minor: int, gratuity_minor: int, summary: CalculationSummary,
) -> list[AllocationLine]:
    """Returns the `AllocationLine`s this Rule Version produces for this
    Order. Pure with respect to the database: it only READS facts and
    appends to the returned list — it never writes an allocation row
    (TIPS_STATELESS_CALCULATION_001). The allocation semantics themselves
    are unchanged from the original engine."""

    def line(**kwargs) -> AllocationLine:
        base = dict(
            order_id=order.id, clover_order_id=order.source_order_id, settlement_time=settlement_time,
            source_employee_id=source_employee_id, rule_id=rule_version.rule_id,
            rule_version_id=rule_version.id, calculation_base=rule_version.calculation_base,
            rate=rule_version.rate,
            # §1/§6 — kept on every line regardless of which base the rule
            # charged, so Clover's two figures stay reconcilable and a
            # diagnostic can show what the base COULD have been.
            voluntary_minor=voluntary_minor, gratuity_minor=gratuity_minor,
        )
        base.update(kwargs)
        return AllocationLine(**base)

    base_amount = _base_amount_for(rule_version.calculation_base, voluntary_minor, gratuity_minor)
    if base_amount is None:
        summary.rules_not_implemented += 1
        return [
            line(
                base_amount_minor=0, pool_amount_minor=0, recipient_employee_id=None,
                recipient_eligibility_basis=(
                    f"NOT_IMPLEMENTED: calculation_base={rule_version.calculation_base!r} is not yet computable "
                    "by this engine (sales-based bases are configuration-only for now); no pool was generated."
                ),
                no_eligible_recipient=True, allocated_amount_minor=0, eligible_recipient_count=0,
            )
        ]

    summary.rules_applied += 1

    recipient_role = session.get(m.RestaurantRole, rule_version.recipient_role_id)
    role_name = recipient_role.name if recipient_role is not None else str(rule_version.recipient_role_id)

    if rule_version.distribution_method != m.DISTRIBUTION_METHOD_EQUAL:
        return [
            line(
                # No pool is computed on a line that distributes nothing —
                # see the SOURCE_RETAINS branch below for the full reasoning.
                base_amount_minor=base_amount, pool_amount_minor=0, recipient_employee_id=None,
                recipient_eligibility_basis=(
                    f"NOT_IMPLEMENTED: distribution_method={rule_version.distribution_method!r} is not yet "
                    "computable by this engine; no outbound allocation was made."
                ),
                no_eligible_recipient=True, allocated_amount_minor=0, eligible_recipient_count=0,
            )
        ]

    # TIPS_BRANCH_CONFIG_BUSINESS_DATE_AND_ELIGIBILITY_002 §5/§7 — WHICH
    # INSTANT decides eligibility is the rule's own choice, and both modes
    # compare ACTUAL INSTANTS. Business Date never enters here: it groups
    # and reports, it does not establish who was working.
    #
    # ACTIVE_AT_ORDER_OPEN is the authoritative rule: the Host who was
    # clocked in when the table was opened keeps the tip-out even if they
    # go home before the guest pays. A Host arriving later does not gain it.
    if rule_version.eligibility_mode == m.ELIGIBILITY_MODE_ACTIVE_AT_ORDER_OPEN:
        eligibility_at = order_open_time
        eligibility_label = "ACTIVE_AT_ORDER_OPEN"
        eligibility_instant_label = "Order Open Time"
    else:
        eligibility_at = settlement_time
        eligibility_label = "ACTIVE_AT_SETTLEMENT"
        eligibility_instant_label = "Settlement Time"

    role_holders = _employees_with_role_at(
        session, restaurant_id=restaurant_id, restaurant_role_id=rule_version.recipient_role_id,
        location_id=order.location_id, at=eligibility_at,
    )
    shift_active = _employees_shift_active_at(session, location_id=order.location_id, at=eligibility_at)
    eligible_ids = sorted(role_holders & shift_active)

    if eligible_ids:
        # The pool is computed HERE and nowhere else: a pool only exists
        # when there is somebody to distribute it to. Computing it before
        # eligibility is known would produce, on an Order with no eligible
        # Host, a figure for money that was never destined anywhere.
        pool_amount = _round_pool(base_amount, rule_version.rate)
        shares = equal_split(pool_amount, eligible_ids)
        lines = []
        for emp_id in eligible_ids:
            lines.append(
                line(
                    base_amount_minor=base_amount, pool_amount_minor=pool_amount, recipient_employee_id=emp_id,
                    recipient_eligibility_basis=(
                        f"{eligibility_label}: held Recipient Role {role_name!r} with an active Shift at "
                        f"{eligibility_instant_label} {eligibility_at.isoformat()}; EQUAL split across "
                        f"{len(eligible_ids)} eligible recipient(s)."
                    ),
                    no_eligible_recipient=False, allocated_amount_minor=shares[emp_id],
                    eligible_recipient_count=len(eligible_ids),
                )
            )
            summary.allocations_produced += 1
        return lines

    # Task §11 — SOURCE_RETAINS: no pool is generated at all, and the fact
    # that nobody was eligible is preserved explicitly, never silently
    # omitted.
    #
    # NO HYPOTHETICAL AMOUNT IS PRODUCED HERE. When no Host was eligible at
    # Order Open Time, 100% of the Order's voluntary Tips and Gratuity
    # belong to the Service Owner. That is a complete, resolved, final
    # outcome — not a distribution that failed. There is therefore no
    # "amount that would have gone to a Host", no "10% withheld because
    # nobody was present", and no "potentially distributable" figure: such
    # a number describes money that was never destined anywhere, and
    # carrying it (even only "for audit") invites exactly the reading it
    # would be wrong to invite — that something is still owed to somebody.
    # `pool_amount_minor` is 0 because no pool was generated, matching
    # `allocated_amount_minor=0`, and the invariant sum(allocated) ==
    # pool_amount_minor still holds.
    #
    # What IS preserved is qualitative only, and that is deliberate: which
    # Employees held the Recipient Role, whether any of them was on shift,
    # and the reason no recipient qualified.
    #
    # TIPS_OPERATIONAL_RESULTS_AND_CALCULATION_FIX_001 §6 — and WHY nobody
    # was eligible is preserved too, in the two halves that actually
    # distinguish the causes: who held the Role at settlement, and who was
    # on shift. "Nobody holds the Host role" and "three Hosts hold it but
    # none was clocked in" are different problems with different fixes, and
    # the engine must not flatten them into one sentence. Nothing here is
    # repaired automatically.
    role_holder_ids = sorted(role_holders)
    if not role_holder_ids:
        exclusion = (
            f"NO_ROLE_HOLDER: no Employee held Recipient Role {role_name!r} at this Location at "
            f"{eligibility_instant_label} {eligibility_at.isoformat()} — check EmployeeAssignment coverage."
        )
    else:
        exclusion = (
            f"NO_ACTIVE_SHIFT: {len(role_holder_ids)} Employee(s) held Recipient Role {role_name!r} "
            f"({', '.join(str(i) for i in role_holder_ids)}) but none had an active Shift at "
            f"{eligibility_instant_label} {eligibility_at.isoformat()} — check Shift records."
        )
    return [
        line(
            base_amount_minor=base_amount, pool_amount_minor=0, recipient_employee_id=None,
            recipient_eligibility_basis=(
                f"NO_ELIGIBLE_RECIPIENT: no Employee held Recipient Role {role_name!r} with an active Shift "
                f"at {eligibility_instant_label} {eligibility_at.isoformat()}; SOURCE_RETAINS applied — no pool "
                "was generated and the Order Service Owner keeps 100%."
            ),
            no_eligible_recipient=True, allocated_amount_minor=0, eligible_recipient_count=0,
            candidate_recipient_employee_ids=role_holder_ids, exclusion_reason=exclusion,
        )
    ]


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


def calculate_tips(
    session: Session, *, restaurant_id: int, period_start: datetime, period_end: datetime,
) -> TipCalculationResult:
    """THE canonical Tips calculation (TIPS_STATELESS_CALCULATION_001).

    Computes the complete result for ANY `[period_start, period_end)` and
    returns it in memory. It writes nothing: no calculation run, no
    allocation rows, no aggregate. Consequently ANY period may be
    calculated at any time, as often as wanted — the same period twice, a
    subset, a superset, or a partially overlapping window. There is no
    overlap detection, no refusal, and no supersession, because there is no
    stored result for a later calculation to conflict with.

    Reproducibility comes from the inputs, not from storage: Orders,
    Payments, Shifts, EmployeeAssignments and effective-dated
    RuleVersions are all themselves persisted facts, so re-running a past
    period reproduces the past answer.

    This is the single engine — `run_tip_distribution_calculation` below is
    a thin wrapper that merely records a payout anchor around this same
    function; it does not implement a second set of semantics."""

    period_start = _aware_utc(period_start)
    period_end = _aware_utc(period_end)
    result = TipCalculationResult(
        restaurant_id=restaurant_id, period_start=period_start, period_end=period_end,
    )

    location_ids = _restaurant_location_ids(session, restaurant_id)
    if not location_ids:
        result.blocked_reason = (
            f"Restaurant {restaurant_id} has no associated Location — nothing to calculate."
        )
        return result

    active_rules = rule_svc.list_rules(session, restaurant_id, active_only=True)
    summary = result.summary
    rule_version_ids: set[int] = set()

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

        # §6 — the authoritative Order Open Time is `Order.created_at`,
        # which `clover.mapping.map_order` fills from `order.createdTime`.
        # Never `client_created_at` (a device clock), never a payment time.
        order_open_time = _aware_utc(order.created_at)

        voluntary_minor, gratuity_minor = _order_gross_tip_components(session, order)
        result.voluntary_total_minor += voluntary_minor
        result.gratuity_total_minor += gratuity_minor

        if order.employee_id is None:
            summary.orders_skipped_no_employee += 1
            continue

        owner_role_ids = _roles_held_by_employee_at(
            session, restaurant_id=restaurant_id, employee_id=order.employee_id, location_id=order.location_id,
            at=settlement_time,
        )

        for rule in active_rules:
            version = rule_svc.get_version_effective_at(session, rule.id, settlement_time)
            if version is None:
                continue
            # ORDER_SERVICE_OWNER_SOURCE_SEMANTICS_001 — a ROLE-semantics
            # Version still requires the Order-owning Employee to hold
            # `source_role_id` (unchanged); an ORDER_SERVICE_OWNER Version
            # is unconditionally sourced from `order.employee_id` — that
            # Employee's RestaurantRole, if any, is irrelevant to source
            # qualification.
            if version.source_semantics == m.TIP_SOURCE_SEMANTICS_ROLE and version.source_role_id not in owner_role_ids:
                continue
            rule_version_ids.add(version.id)
            result.lines.extend(
                _apply_rule_to_order(
                    session, order=order, restaurant_id=restaurant_id, source_employee_id=order.employee_id,
                    settlement_time=settlement_time, rule_version=version, voluntary_minor=voluntary_minor,
                    order_open_time=order_open_time,
                    gratuity_minor=gratuity_minor, summary=summary,
                )
            )

    result.rule_version_ids = sorted(rule_version_ids)
    return result


def summarize_notes(result: TipCalculationResult) -> str:
    s = result.summary
    return (
        f"orders_considered={s.orders_considered} "
        f"orders_with_no_settlement_time={s.orders_with_no_settlement_time} "
        f"orders_skipped_no_employee={s.orders_skipped_no_employee} "
        f"rules_applied={s.rules_applied} allocations_produced={s.allocations_produced} "
        f"rules_not_implemented={s.rules_not_implemented}"
    )


def run_tip_distribution_calculation(
    session: Session, *, restaurant_id: int, period_start: datetime, period_end: datetime,
) -> tuple[m.TipDistributionCalculationRun, TipCalculationResult]:
    """Payout-anchor wrapper (TIPS_STATELESS_CALCULATION_001).

    Tips itself never calls this: the Calculate Tips screen, Host Audit and
    CSV export all use `calculate_tips` directly and persist nothing. This
    exists solely because the DOWNSTREAM payment pipeline crystallizes an
    approved amount: `TipEntitlement.calculation_run_id` is a NOT NULL FK
    to `TipDistributionCalculationRun`, and entitlements feed Payment
    Cycles and Payment Instructions. The run row is therefore a payment
    anchor/receipt, NOT an authoritative Tips calculation — it stores no
    allocations, and nothing reads a result back out of it.

    Overlap detection, refusal and supersession are gone: two payout runs
    covering overlapping periods are no longer a conflict, because neither
    one owns the answer. Duplicate crystallization is prevented where it
    actually matters — `readiness`'s own already-calculated gate and
    `uq_tip_entitlement_run_employee`."""

    result = calculate_tips(
        session, restaurant_id=restaurant_id, period_start=period_start, period_end=period_end,
    )
    run = m.TipDistributionCalculationRun(
        restaurant_id=restaurant_id, period_start=_aware_utc(period_start), period_end=_aware_utc(period_end),
        status=STATUS_RUNNING,
    )
    session.add(run)
    session.flush()

    if result.blocked_reason is not None:
        run.status = STATUS_FAILED
        run.completed_at = utc_now()
        run.notes = result.blocked_reason
        return run, result

    run.status = STATUS_COMPLETE
    run.completed_at = utc_now()
    run.notes = summarize_notes(result)
    return run, result


def get_latest_payout_run(
    session: Session, *, restaurant_id: int, period_start: datetime, period_end: datetime,
):
    """The most recent COMPLETE payout-anchor run for this EXACT period, if
    any (TIPS_STATELESS_CALCULATION_001).

    This answers only "has this period already been crystallized into
    entitlements for payment?" — it is NOT a cached Tips result and is
    never used to display or reuse a calculation. Tips always recalculates.
    Supersession is gone, so this simply returns the latest matching row."""
    return session.scalars(
        select(m.TipDistributionCalculationRun)
        .where(
            m.TipDistributionCalculationRun.restaurant_id == restaurant_id,
            m.TipDistributionCalculationRun.period_start == _aware_utc(period_start),
            m.TipDistributionCalculationRun.period_end == _aware_utc(period_end),
            m.TipDistributionCalculationRun.status == STATUS_COMPLETE,
        )
        .order_by(m.TipDistributionCalculationRun.id.desc())
    ).first()


def require_location_business_day_config(
    session: Session, restaurant_id: int,
) -> tuple[m.Location, str]:
    """The Location's Business Day configuration, or a clear refusal.

    TIPS_BRANCH_CONFIG_BUSINESS_DATE_AND_ELIGIBILITY_002 §2 — there is NO
    fallback. RF-One does not invent a timezone and does not invent an
    operating-day cutoff: a calculation that guessed either would attribute
    a whole night's takings to the wrong day and nobody would see it happen.
    Returns `(location, "")` when configured, or `(location_or_None,
    reason)` naming the Location and the missing field(s)."""
    location_id = session.scalars(
        select(m.RestaurantLocation.location_id)
        .where(m.RestaurantLocation.restaurant_id == restaurant_id)
    ).first()
    location = session.get(m.Location, location_id) if location_id else None
    if location is None:
        return None, (
            f"Restaurant {restaurant_id} has no associated Location, so no Business Day "
            "configuration can be resolved."
        )
    missing = []
    if not location.timezone:
        missing.append("timezone")
    if location.operating_day_cutoff_time is None:
        missing.append("operating_day_cutoff_time")
    if missing:
        return location, (
            f"Location {location.id} ({location.name!r}) is missing its Business Day "
            f"configuration: {', '.join(missing)}. Tips cannot calculate a Business Date "
            "without it, and RF-One never substitutes a default timezone or cutoff. "
            "Configure the Location first."
        )
    return location, ""


def business_date_window_utc(
    location: m.Location, first_business_date: date, last_business_date: date,
) -> tuple[datetime, datetime]:
    """The UTC half-open instant window covering the INCLUSIVE Business Date
    range for this Location.

    §3/§5 — business day D is [D at cutoff local, D+1 at cutoff local), so
    the range [first .. last] inclusive is [first at cutoff, last+1 at
    cutoff). UTC is an implementation detail for retrieval; the period the
    operator states and the UI shows is the Business Date range."""
    tz = ZoneInfo(location.timezone)
    cutoff = location.operating_day_cutoff_time
    start_local = datetime.combine(first_business_date, cutoff, tzinfo=tz)
    end_local = datetime.combine(last_business_date + timedelta(days=1), cutoff, tzinfo=tz)
    return start_local.astimezone(UTC_TZ), end_local.astimezone(UTC_TZ)


def calculate_tips_for_business_dates(
    session: Session, *, restaurant_id: int,
    first_business_date: date, last_business_date: date,
) -> TipCalculationResult:
    """THE Tips calculation for an INCLUSIVE Business Date range (§3/§4/§5).

    Business Date comes from the canonical Sales implementation
    (`rfone_data_store.business_date`) via the Location's own timezone and
    cutoff — Tips has no business-date algorithm of its own and must not
    grow one. Refuses outright when the Location is unconfigured."""
    location, reason = require_location_business_day_config(session, restaurant_id)
    if reason:
        result = TipCalculationResult(
            restaurant_id=restaurant_id,
            period_start=_aware_utc(datetime.combine(first_business_date, time(0, 0))),
            period_end=_aware_utc(datetime.combine(last_business_date, time(0, 0))),
        )
        result.blocked_reason = reason
        return result
    period_start, period_end = business_date_window_utc(
        location, first_business_date, last_business_date,
    )
    result = calculate_tips(
        session, restaurant_id=restaurant_id,
        period_start=period_start, period_end=period_end,
    )
    result.first_business_date = first_business_date
    result.last_business_date = last_business_date
    return result


def build_employee_review(session: Session, result: TipCalculationResult) -> list[EmployeeReviewRow]:
    """One row per Employee touched by this calculation, either as a
    Gross-Tip-earning Order owner, an outbound source, or an inbound
    recipient. Derived entirely from the in-memory
    `TipCalculationResult` plus source facts — it reads no persisted
    allocation rows and no stored aggregate
    (TIPS_STATELESS_CALCULATION_001)."""
    orders_in_scope = _orders_in_scope(
        session, restaurant_id=result.restaurant_id,
        period_start=result.period_start, period_end=result.period_end,
    )
    orders_by_id = {order.id: order for order in orders_in_scope}

    # §1/§3 — accumulated SEPARATELY. `Order.employee_id` is the Order
    # Service Owner, which is what attributes a tip to a person; no Role is
    # consulted here and none ever was.
    gross_by_employee: dict[int, int] = {}
    voluntary_by_employee: dict[int, int] = {}
    gratuity_by_employee: dict[int, int] = {}
    for order in orders_in_scope:
        if order.employee_id is None:
            continue
        voluntary_minor, gratuity_minor = _order_gross_tip_components(session, order)
        voluntary_by_employee[order.employee_id] = (
            voluntary_by_employee.get(order.employee_id, 0) + voluntary_minor
        )
        gratuity_by_employee[order.employee_id] = (
            gratuity_by_employee.get(order.employee_id, 0) + gratuity_minor
        )
        gross_by_employee[order.employee_id] = (
            gross_by_employee.get(order.employee_id, 0) + voluntary_minor + gratuity_minor
        )

    allocations = result.lines

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
            # NOT a warning. No eligible Host at Order Open Time means no
            # distribution obligation arose, so the Service Owner simply
            # keeps 100% of that Order: a normal, resolved, payable
            # outcome. The per-order REASON (which Host was expected, why
            # they were excluded) stays in the Order drill-down, where a
            # question about one order belongs — but no amount is carried
            # forward, because no amount is owed.
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
        # §3/§5 — which side of the distribution this employee is on in
        # THIS run. A Host who generated nothing and only received tip-out
        # is a HOST row and still appears, because they still have to be
        # paid; that is the whole point of the operational page.
        # Judged on MONEY, not on order ownership: a Host who happens to
        # have a zero-tip order attributed to them is a Host on a payment
        # sheet, not a Service Owner with nothing to show.
        owns_orders = gross > 0 or outbound > 0
        receives = inbound > 0
        if owns_orders and receives:
            result_type = RESULT_TYPE_BOTH
        elif receives:
            result_type = RESULT_TYPE_HOST
        else:
            result_type = RESULT_TYPE_SERVICE_OWNER
        rows.append(
            EmployeeReviewRow(
                employee_id=emp_id,
                display_name=employees_by_id[emp_id].display_name if emp_id in employees_by_id else None,
                gross_earned_tips_minor=gross, outbound_tip_out_minor=outbound, inbound_tip_out_minor=inbound,
                net_before_adjustments_minor=gross - outbound + inbound,
                has_warning=bool(warnings_by_employee.get(emp_id)),
                voluntary_tips_minor=voluntary_by_employee.get(emp_id, 0),
                gratuity_minor=gratuity_by_employee.get(emp_id, 0),
                result_type=result_type,
                warning_notes=warnings_by_employee.get(emp_id, []),
                order_ids=sorted(orders_by_employee.get(emp_id, set())),
            )
        )
    return rows


@dataclass
class OperationalTotals:
    """The run's payment-and-reconciliation header
    (TIPS_OPERATIONAL_RESULTS_AND_CALCULATION_FIX_001 §4).

    Derived from the same employee rows the page pays from, so the header
    can never disagree with the table under it. `distribution_balanced`
    is the control that matters before anyone is paid: every dollar taken
    from a Service Owner must be a dollar a Host is owed."""

    voluntary_minor: int = 0
    gratuity_minor: int = 0
    # TIPS_FINALIZED_PERIOD_CALCULATION_AND_REPORT_001 §11 — THE ONE
    # authoritative monetary control:
    #
    #     Total Tips + Gratuity  ==  Total Employee Entitlements
    #
    # Nothing else is a control. "Tip Out Required", "Unresolved Tip Out"
    # and "Financial Difference" are gone as controls: they treated a
    # SOURCE_RETAINS outcome as money in limbo when in fact the Service
    # Owner simply keeps it, so they reported a problem where none existed.
    #
    # Every cent collected in the period must land on exactly one
    # employee's entitlement. If it does not, the run is not valid for
    # finalization — and the discrepancy is REPORTED, never repaired.
    service_owner_entitlements_minor: int = 0
    other_recipient_entitlements_minor: int = 0
    distributed_minor: int = 0

    @property
    def gross_minor(self) -> int:
        """Total Tips + Gratuity for the period — the left side of the
        control."""
        return self.voluntary_minor + self.gratuity_minor

    @property
    def total_employee_entitlements_minor(self) -> int:
        """The right side of the control."""
        return (
            self.service_owner_entitlements_minor
            + self.other_recipient_entitlements_minor
        )

    @property
    def control_difference_minor(self) -> int:
        """Total Tips + Gratuity minus Total Employee Entitlements. PASS
        requires exactly zero at currency precision."""
        return self.gross_minor - self.total_employee_entitlements_minor

    @property
    def control_passes(self) -> bool:
        return self.control_difference_minor == 0

    @property
    def valid_for_finalization(self) -> bool:
        """§11/§17/§18 — a run whose control does not balance is NOT valid
        for finalization, by any path, manual or automatic."""
        return self.control_passes


def build_operational_totals(
    result: TipCalculationResult, rows: list[EmployeeReviewRow],
) -> OperationalTotals:
    """The §4 header for one run. Voluntary and Gratuity are reported
    separately because Clover reports them separately and the run has to
    reconcile against it — Gross is their sum, never a substitute."""
    return OperationalTotals(
        voluntary_minor=result.voluntary_total_minor,
        gratuity_minor=result.gratuity_total_minor,
        service_owner_entitlements_minor=sum(
            row.final_entitlement_minor for row in rows
            if row.result_type != RESULT_TYPE_HOST
        ),
        other_recipient_entitlements_minor=sum(
            row.final_entitlement_minor for row in rows
            if row.result_type == RESULT_TYPE_HOST
        ),
        distributed_minor=sum(row.received_minor for row in rows),
    )


def populate_entitlements_for_run(
    session: Session, run: m.TipDistributionCalculationRun, result: TipCalculationResult,
    *, business_date: date | None = None,
) -> list[m.TipEntitlement]:
    """STEP 12B integration (TASK_TIPS_COMPLETE_001 §9) — persists
    `build_employee_review`'s own per-Employee aggregate (gross/outbound/
    inbound/final entitlement, plus the voluntary/gratuity/result-type
    split) as one `TipEntitlement` row per Employee for this run, so
    it can later be aggregated across MANY runs/Business Dates into a
    Payment Cycle without re-deriving it. Idempotent: calling this twice for the same COMPLETE run never
    creates duplicate rows (`uq_tip_entitlement_run_employee`) — existing
    rows are left exactly as they were (an entitlement, once persisted, is
    never silently recomputed; a genuine correction goes through the same
    correction is a fresh calculation plus a fresh entitlement).

    `business_date` is the caller's own business-date attribution for this
    run's period (`readiness.business_date_period`'s inverse) — left `None`
    for a manually-chosen, non-single-day period, per `TipEntitlement`'s own
    docstring. Only ever called for a COMPLETE run; a FAILED run has no
    employee results to persist."""
    if run.status != STATUS_COMPLETE:
        return []

    existing = list(
        session.scalars(select(m.TipEntitlement).where(m.TipEntitlement.calculation_run_id == run.id))
    )
    if existing:
        return existing

    review_rows = build_employee_review(session, result)
    entitlements: list[m.TipEntitlement] = []
    for row in review_rows:
        entitlement = m.TipEntitlement(
            calculation_run_id=run.id, restaurant_id=run.restaurant_id, business_date=business_date,
            employee_id=row.employee_id, gross_amount_minor=row.gross_earned_tips_minor,
            outbound_amount_minor=row.outbound_tip_out_minor, inbound_amount_minor=row.inbound_tip_out_minor,
            payable_amount_minor=row.final_entitlement_minor, tip_payment_instruction_id=None,
            # TIPS_FINALIZED_PERIOD_CALCULATION_AND_REPORT_001 §13 — the
            # per-person figures the run report and Payroll need, persisted
            # from the SAME `build_employee_review` row that produced the
            # aggregate above, so a reopened report can never disagree with
            # the totals it was finalized on.
            voluntary_amount_minor=row.voluntary_tips_minor,
            gratuity_amount_minor=row.gratuity_minor,
            result_type=row.result_type,
        )
        session.add(entitlement)
        entitlements.append(entitlement)
    session.flush()
    return entitlements


def get_order_drilldown(session: Session, result: TipCalculationResult, order_id: int) -> dict | None:
    """"Why did this employee receive/pay this amount" for one Order in
    this calculation. Returns `None` only if `order_id` is not actually
    part of the calculated period/Location scope at all. Reads its
    allocation detail from the in-memory result, never from storage."""
    order = session.get(m.Order, order_id)
    if order is None:
        return None
    location_ids = _restaurant_location_ids(session, result.restaurant_id)
    if order.location_id not in location_ids:
        return None
    settlement_time = get_order_settlement_time(session, order.id)
    if settlement_time is None:
        return None
    settlement_time = _aware_utc(settlement_time)
    if not (_aware_utc(result.period_start) <= settlement_time < _aware_utc(result.period_end)):
        return None

    voluntary_minor, gratuity_minor = _order_gross_tip_components(session, order)
    allocations = [line for line in result.lines if line.order_id == order_id]
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
