"""Tip Payment Cycle — aggregation, Approve & Pay, and Attention Management
integration (TASK_TIPS_COMPLETE_001 §4/§10/§12/§14; STEP 12B integration).

A Payment Cycle aggregates every currently-UNPAID `TipEntitlement` for a
Restaurant — spanning as many daily calculation runs/Business Dates as have
accrued since the previous cycle — into one `TipPaymentInstruction` per
Employee, then (once an authorized Acting Identity approves it) submits
each instruction through this Restaurant's configured payment connector
(`tips/payment_connector.py`), exactly one payee at a time, isolating one
payee's failure from every other.

Reuses, never reimplements: `payment_instruction.py`'s submit/refresh/
funding-check logic (this module only decides WHEN a batch runs and WHICH
entitlements it covers), `authority_service.authorize()` for the Approve &
Pay gate (never `is_admin`), and `attention_service.create_attention`/
`route_attention` + `organizational_responsibility_service.ScopeContext` for
routing a failed/reopened instruction to a human, through the SAME
Process Ownership -> Position -> Occupant -> Temporary Coverage -> Backup
Position -> Organizational Fallback chain every other Domain already uses
— no Tips-specific escalation model.

Approve & Pay is scoped per-Restaurant (TASK_TIPS_RESTAURANT_AUTHORITY_SCOPE_001):
the gate below checks a grant for `domain=TIPS, action=APPROVE_AND_PAY,
scope_type=RESTAURANT, scope_id=<this cycle's restaurant_id>` — an Acting
Identity authorized for Restaurant A is never thereby authorized for
Restaurant B, and the same Acting Identity may hold one such grant per
Restaurant with no duplication/workaround (`authority_service.grant_authority`
called once per Restaurant). A GLOBAL-scoped grant continues to authorize
Approve & Pay for every Restaurant unconditionally — `authorize()`'s own
GLOBAL match is unconditional regardless of the requested `scope_type`/
`scope_id` (see that function's docstring) — so a real cross-Restaurant
authorization is expressed with a GLOBAL grant, never by omitting scope.
`models.AUTHORITY_SCOPE_KINDS` includes `RESTAURANT`, mirroring
`POSITION_SCOPE_KINDS`'s existing `POSITION_SCOPE_RESTAURANT` value (a
separate enum on a separate table — the two scope vocabularies are not
merged).

Approve & Pay is ALSO gated on `payment_readiness.describe_payment_readiness`
(TASK_TIPS_RECONCILIATION_AND_PAYMENT_CONTROL_001,
CLOVER_CONTINUOUS_SYNCHRONIZATION_ARCHITECTURE.md §3/§7) — Clover live
healthy, reconciliation recent and successful, no blocking CRITICAL
Attention — in addition to, never instead of, the Authority gate above.
This is the SAME gate function the Web Payment Control and `tips/
scheduler.py`'s AUTO WITHOUT APPROVAL path both call (Channel Independence:
no business rule lives only in a route/template). A NOT READY outcome
raises `PaymentNotReadyError` — never treated as a financial error, never a
connector call — and is a normal, expected, silent-by-default condition;
only a PERSISTENTLY failing reconciliation is escalated to a human, via
`maybe_raise_attention_for_payment_readiness` below, reusing Attention
Management exactly as `_raise_attention_for_instruction` already does for a
failed payment instruction — never a Tips-specific escalation mechanism.

Connector-neutral by construction (STEP 12B Product Owner decision): every
function below that executes a payment takes a `connector:
payment_connector.PaymentConnector`, resolved by the CALLER (`tips/app.py`,
`tips/scheduler.py`) from this Restaurant's own configured `connector_code`
(`tips/payment_connector.resolve_connector`) — this module never imports
`technical.connectors.mercury` directly and never defaults to one on its
own. `resolve_source_account_id` below is the one Mercury-specific
exception: source-account resolution genuinely IS connector-specific
configuration (`TipsPaymentScheduleConfig.mercury_source_account_id`), so
it branches explicitly on `connector.connector_code` rather than pretend
every connector shares Mercury's own account model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..attention_service import create_attention, route_attention
from ..authority_service import AuthorizationContext, authorize
from ..organizational_responsibility_service import ScopeContext
from . import payment_connector as connector_svc
from . import payment_instruction as pi_svc
from . import payment_readiness as readiness_svc
from . import schedule_service as sched_svc

UTC = timezone.utc

AUTHORITY_DOMAIN_TIPS = "TIPS"
AUTHORITY_ACTION_APPROVE_AND_PAY = "APPROVE_AND_PAY"

ATTENTION_SOURCE_DOMAIN = "TIPS"
ATTENTION_SOURCE_MODULE = "PAYMENT_EXECUTION"
ATTENTION_SOURCE_PROCESS_NAME = "TIP_PAYOUT"


def _aware_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


# ---------------------------------------------------------------------------
# Source account resolution (Channel Independence: moved here from
# `Tips/app.py`, which had it as a route-local helper — the automatic
# scheduler's AUTO WITHOUT APPROVAL path (`tips/scheduler.py`) needs the
# EXACT same resolution outside any Flask request, so it can no longer live
# only in a route/template).
# ---------------------------------------------------------------------------


def resolve_source_account_id(
    session: Session, restaurant_id: int, connector: "connector_svc.PaymentConnector",
) -> str | None:
    """Connector-neutral entry point. `TipsPaymentScheduleConfig.
    mercury_source_account_id` is genuinely Mercury-specific configuration
    data (see that field's own docstring), so it is only ever consulted
    when the resolved connector IS Mercury. Beyond that one Mercury-named
    field, this stays fully generic: any connector may optionally implement
    its OWN `resolve_fallback_source_account_id()` (duck-typed, not part of
    the minimal `PaymentConnector` Protocol, since not every connector
    needs one), and this function calls it uniformly — never a second
    per-connector branch added here as connectors are added."""
    if connector.connector_code == connector_svc.CONNECTOR_CODE_MERCURY:
        payment_config = sched_svc.get_payment_schedule_effective_at(session, restaurant_id=restaurant_id)
        if payment_config is not None and payment_config.mercury_source_account_id:
            return payment_config.mercury_source_account_id
    fallback = getattr(connector, "resolve_fallback_source_account_id", None)
    if fallback is not None:
        return fallback()
    return None


# ---------------------------------------------------------------------------
# Unpaid entitlements / readiness
# ---------------------------------------------------------------------------


def get_unpaid_entitlements(session: Session, restaurant_id: int) -> list[m.TipEntitlement]:
    """Every `TipEntitlement` for this Restaurant not yet assigned to a
    Payment Instruction, regardless of which calculation run/Business Date
    produced it ("aggregate all unpaid eligible Tip Entitlements"). A
    non-positive `payable_amount_minor` is excluded here too — nothing to
    pay out for it (same rule `payment_instruction.
    get_or_create_payment_instructions_for_run` used to apply per-run)."""
    return list(
        session.scalars(
            select(m.TipEntitlement).where(
                m.TipEntitlement.restaurant_id == restaurant_id,
                m.TipEntitlement.tip_payment_instruction_id.is_(None),
                m.TipEntitlement.payable_amount_minor > 0,
            )
        )
    )


@dataclass
class PaymentCycleReadiness:
    has_unpaid: bool
    unpaid_entitlement_count: int
    unpaid_total_minor: int
    payee_count: int
    open_cycle: "m.TipPaymentCycle | None"
    ready_to_start_cycle: bool


def describe_payment_cycle_readiness(session: Session, restaurant_id: int) -> PaymentCycleReadiness:
    """Pure data condition (mirrors `readiness.describe_readiness`'s own
    philosophy, applied to the Payment side): is there an unpaid balance to
    aggregate, and is there already an OPEN cycle in progress (never start a
    second one concurrently — "one open cycle at a time")."""
    open_cycle = get_open_cycle(session, restaurant_id)
    unpaid = get_unpaid_entitlements(session, restaurant_id)
    payee_count = len({e.employee_id for e in unpaid})
    return PaymentCycleReadiness(
        has_unpaid=bool(unpaid), unpaid_entitlement_count=len(unpaid),
        unpaid_total_minor=sum(e.payable_amount_minor for e in unpaid), payee_count=payee_count,
        open_cycle=open_cycle, ready_to_start_cycle=bool(unpaid) and open_cycle is None,
    )


def get_open_cycle(session: Session, restaurant_id: int) -> "m.TipPaymentCycle | None":
    return session.scalars(
        select(m.TipPaymentCycle)
        .where(
            m.TipPaymentCycle.restaurant_id == restaurant_id,
            m.TipPaymentCycle.status == m.TIP_PAYMENT_CYCLE_STATUS_OPEN,
        )
        .order_by(m.TipPaymentCycle.id.desc())
    ).first()


# ---------------------------------------------------------------------------
# Starting a cycle (aggregation)
# ---------------------------------------------------------------------------


def start_payment_cycle(
    session: Session, *, restaurant_id: int, now: datetime | None = None, triggered_by: str = m.TIP_PAYMENT_CYCLE_TRIGGER_MANUAL,
) -> "m.TipPaymentCycle | None":
    """Aggregates every currently-unpaid `TipEntitlement` into one new
    `TipPaymentCycle`, creating exactly one `TipPaymentInstruction` per
    Employee for the SUM of their unpaid entitlements. Idempotent by
    construction: if an OPEN cycle already exists for this Restaurant, it
    is returned UNCHANGED — never a second concurrent cycle, never a
    double-aggregation of the same entitlements. Returns `None` (no cycle
    created) if there is nothing unpaid to aggregate."""
    now = now or datetime.now(UTC)

    existing_open = get_open_cycle(session, restaurant_id)
    if existing_open is not None:
        return existing_open

    unpaid = get_unpaid_entitlements(session, restaurant_id)
    if not unpaid:
        return None

    business_dates = [e.business_date for e in unpaid if e.business_date is not None]
    period_start = (
        datetime(min(business_dates).year, min(business_dates).month, min(business_dates).day, tzinfo=UTC)
        if business_dates else now
    )

    cycle = m.TipPaymentCycle(
        restaurant_id=restaurant_id, period_start=period_start, period_end=now,
        status=m.TIP_PAYMENT_CYCLE_STATUS_OPEN, triggered_by=triggered_by,
        notes=f"Aggregated {len(unpaid)} unpaid Tip Entitlement(s).",
    )
    session.add(cycle)
    session.flush()

    by_employee: dict[int, int] = {}
    for entitlement in unpaid:
        by_employee[entitlement.employee_id] = by_employee.get(entitlement.employee_id, 0) + entitlement.payable_amount_minor

    instructions_by_employee: dict[int, m.TipPaymentInstruction] = {}
    for employee_id, amount_minor in by_employee.items():
        instruction = m.TipPaymentInstruction(
            payment_cycle_id=cycle.id, employee_id=employee_id, amount_minor=amount_minor,
            idempotency_key=None, status=pi_svc.STATUS_READY,
        )
        session.add(instruction)
        instructions_by_employee[employee_id] = instruction
    session.flush()

    for entitlement in unpaid:
        entitlement.tip_payment_instruction_id = instructions_by_employee[entitlement.employee_id].id
    session.flush()

    return cycle


# ---------------------------------------------------------------------------
# Attention Management integration — no Tips-specific escalation
# ---------------------------------------------------------------------------


def _raise_attention_for_instruction(
    session: Session, instruction: "m.TipPaymentInstruction", *, restaurant_id: int,
) -> None:
    """Raises exactly ONE AttentionItem per instruction the first time it
    needs one (`attention_item_id` guards against a duplicate on a later
    retry/refresh pass that finds the SAME instruction still in NEEDS_
    ATTENTION) — routed through the shared runtime's own Process Ownership
    chain, scoped to this Restaurant (`POSITION_SCOPE_RESTAURANT`), never a
    Tips-specific notification path."""
    if instruction.attention_item_id is not None:
        return
    priority = instruction.priority or m.ATTENTION_PRIORITY_MEDIUM
    item = create_attention(
        session, source_domain=ATTENTION_SOURCE_DOMAIN, source_module=ATTENTION_SOURCE_MODULE,
        source_process_name=ATTENTION_SOURCE_PROCESS_NAME, source_phase=instruction.failure_class,
        source_reference=f"TipPaymentInstruction:{instruction.id}",
        reason=instruction.reason_for_failure or "Tip payment instruction requires attention.",
        priority=priority,
        scope=ScopeContext(scope_type=m.POSITION_SCOPE_RESTAURANT, scope_id=restaurant_id),
    )
    route_attention(session, item=item)
    instruction.attention_item_id = item.id


def _maybe_raise_attention(session: Session, instruction: "m.TipPaymentInstruction", *, restaurant_id: int) -> None:
    if instruction.status == pi_svc.STATUS_NEEDS_ATTENTION:
        _raise_attention_for_instruction(session, instruction, restaurant_id=restaurant_id)


ATTENTION_SOURCE_PHASE_RECONCILIATION = "PAYMENT_READINESS_PERSISTENT_FAILURE"


def maybe_raise_attention_for_payment_readiness(
    session: Session, *, restaurant_id: int, readiness: "readiness_svc.PaymentReadiness",
) -> "m.AttentionItem | None":
    """"se reconciliation fallisce persistentemente... usa Attention
    Management esistente. NON creare escalation specifica Tips." Called
    explicitly by the Web Payment Control route and by `tips/scheduler.py`'s
    automatic tick — NEVER from inside `approve_and_pay_cycle` itself, so a
    routine, expected NOT-READY denial never raises Attention on its own
    ("NON creare allarme inutile" for a normal wait). Idempotent: reuses the
    SAME `source_reference` dedup convention `_raise_attention_for_
    instruction` already uses — a second call while the SAME
    persistent-failure condition is still open returns the existing OPEN/
    ACKNOWLEDGED item instead of raising a duplicate. Returns `None` when
    readiness is not persistently failing — nothing to raise."""
    if not readiness.is_persistently_failing:
        return None

    source_reference = f"Restaurant:{restaurant_id}:PaymentReadiness"
    existing = session.scalars(
        select(m.AttentionItem).where(
            m.AttentionItem.source_domain == ATTENTION_SOURCE_DOMAIN,
            m.AttentionItem.source_reference == source_reference,
            m.AttentionItem.status.in_((m.ATTENTION_STATUS_OPEN, m.ATTENTION_STATUS_ACKNOWLEDGED)),
        )
    ).first()
    if existing is not None:
        return existing

    item = create_attention(
        session, source_domain=ATTENTION_SOURCE_DOMAIN, source_module=ATTENTION_SOURCE_MODULE,
        source_process_name=ATTENTION_SOURCE_PROCESS_NAME, source_phase=ATTENTION_SOURCE_PHASE_RECONCILIATION,
        source_reference=source_reference,
        reason=f"Tips payment readiness for this Restaurant has been persistently NOT READY: {readiness.reason}",
        priority=m.ATTENTION_PRIORITY_HIGH,
        scope=ScopeContext(scope_type=m.POSITION_SCOPE_RESTAURANT, scope_id=restaurant_id),
    )
    route_attention(session, item=item)
    return item


# ---------------------------------------------------------------------------
# Approve & Pay
# ---------------------------------------------------------------------------


class ApproveAndPayError(ValueError):
    """A malformed or unauthorized Approve & Pay attempt — no connector
    call is ever made and no cycle/instruction state changes when this is
    raised."""


class PaymentNotReadyError(ApproveAndPayError):
    """Raised instead of proceeding when `payment_readiness.
    describe_payment_readiness` reports NOT READY (stale/failed/incomplete
    reconciliation or a blocking CRITICAL Attention) — never a financial
    error: a normal, expected "not yet" outcome, exactly like
    `ApproveAndPayError` more generally, no connector call is ever made and
    no state changes."""

    def __init__(self, readiness: "readiness_svc.PaymentReadiness"):
        self.readiness = readiness
        super().__init__(f"Payment Cycle for Restaurant {readiness.restaurant_id} is NOT READY: {readiness.reason}")


def can_approve_and_pay(session: Session, *, acting_identity: "m.ActingIdentity", restaurant_id: int) -> bool:
    """Read-only convenience wrapper around the SAME gate `approve_and_pay_
    cycle` enforces server-side (never a second, divergent check) — for a
    UI (or any other caller) that wants to show/filter options before a
    submit attempt. Never itself a substitute for the server-side gate:
    `approve_and_pay_cycle` re-checks Authority unconditionally regardless
    of what this returned."""
    decision = authorize(
        session, actor=acting_identity, action=AUTHORITY_ACTION_APPROVE_AND_PAY,
        context=AuthorizationContext(domain=AUTHORITY_DOMAIN_TIPS, scope_type=m.SCOPE_RESTAURANT, scope_id=restaurant_id),
    )
    return decision.allowed


@dataclass
class ApproveAndPayResult:
    cycle: "m.TipPaymentCycle"
    submitted_count: int
    needs_attention_count: int
    funding: "pi_svc.FundingCheckResult"


def approve_and_pay_cycle(
    session: Session, *, cycle: "m.TipPaymentCycle", acting_identity: "m.ActingIdentity",
    connector: "connector_svc.PaymentConnector", source_account_id: str, now: datetime | None = None,
) -> ApproveAndPayResult:
    """REVIEW is simply reading `cycle`/its instructions (no mutation); this
    function IS "APPROVE & PAY," gated on Authority (never `is_admin`),
    scoped to `cycle.restaurant_id` specifically (module docstring above)
    so an Acting Identity authorized for one Restaurant can never
    Approve & Pay another's cycle — a GLOBAL grant remains the only way to
    authorize every Restaurant at once. Raises `ApproveAndPayError` and
    changes NOTHING (no connector call is made either) if the Acting
    Identity is not authorized for this Restaurant, the cycle is not OPEN,
    funding is insufficient for the whole batch (the existing funding-check
    principle, preserved unchanged — the connector's own available balance
    must cover the full batch before ANY instruction submits), or
    `payment_readiness.describe_payment_readiness` reports NOT READY
    (raises `PaymentNotReadyError` — module docstring above; checked AFTER
    Authority so an unauthorized caller never learns this Restaurant's
    reconciliation state, and BEFORE the funding check/any connector call).
    `now` is passed straight through to `describe_payment_readiness` —
    production callers omit it (real wall-clock time); tests pin it for a
    deterministic fresh/stale boundary. `connector` is resolved by the
    CALLER from this Restaurant's own configured `connector_code` — this
    function never resolves or defaults one itself."""
    if cycle.status != m.TIP_PAYMENT_CYCLE_STATUS_OPEN:
        raise ApproveAndPayError(f"Payment Cycle {cycle.id} is not OPEN (status={cycle.status!r}).")

    decision = authorize(
        session, actor=acting_identity, action=AUTHORITY_ACTION_APPROVE_AND_PAY,
        context=AuthorizationContext(
            domain=AUTHORITY_DOMAIN_TIPS, scope_type=m.SCOPE_RESTAURANT, scope_id=cycle.restaurant_id,
        ),
    )
    if not decision.allowed:
        raise ApproveAndPayError(
            f"Acting Identity {acting_identity.id} is not authorized to Approve & Pay Tips for Restaurant "
            f"{cycle.restaurant_id}: {decision.reason}"
        )

    readiness = readiness_svc.describe_payment_readiness(session, cycle.restaurant_id, now=now)
    if not readiness.ready:
        raise PaymentNotReadyError(readiness)

    instructions = list(
        session.scalars(select(m.TipPaymentInstruction).where(m.TipPaymentInstruction.payment_cycle_id == cycle.id))
    )
    ready = [i for i in instructions if i.status == pi_svc.STATUS_READY]
    funding = pi_svc.check_funding(connector, account_id=source_account_id, instructions=ready)
    if not funding.sufficient:
        raise ApproveAndPayError(f"Insufficient funding for Payment Cycle {cycle.id}: {funding.reason}")

    cycle.status = m.TIP_PAYMENT_CYCLE_STATUS_APPROVED
    cycle.approved_at = datetime.now(UTC)
    cycle.approved_by_identity_id = acting_identity.id

    submitted = 0
    for instruction in ready:
        pi_svc.submit_payment_instruction(session, instruction, connector, account_id=source_account_id)
        _maybe_raise_attention(session, instruction, restaurant_id=cycle.restaurant_id)
        if instruction.status in (pi_svc.STATUS_SENT, pi_svc.STATUS_SUBMITTED):
            submitted += 1
    session.flush()

    needs_attention = sum(1 for i in instructions if i.status == pi_svc.STATUS_NEEDS_ATTENTION)
    return ApproveAndPayResult(cycle=cycle, submitted_count=submitted, needs_attention_count=needs_attention, funding=funding)


def retry_instruction(
    session: Session, instruction: "m.TipPaymentInstruction", connector: "connector_svc.PaymentConnector", *,
    source_account_id: str,
) -> None:
    """Resumes exactly ONE failed/unresolved Payment Instruction; never
    touches any sibling instruction in the same cycle, and never resubmits
    an already-terminal (SENT/OUTCOME_VERIFIED) one (`payment_instruction.
    submit_payment_instruction`'s own guard)."""
    cycle = session.get(m.TipPaymentCycle, instruction.payment_cycle_id)
    pi_svc.submit_payment_instruction(session, instruction, connector, account_id=source_account_id)
    if cycle is not None:
        _maybe_raise_attention(session, instruction, restaurant_id=cycle.restaurant_id)
    session.flush()


def refresh_outcomes_for_cycle(
    session: Session, cycle: "m.TipPaymentCycle", connector: "connector_svc.PaymentConnector",
) -> None:
    """Polls the connector for every non-terminal instruction in `cycle`
    (Outcome Verification) — including re-checking an already
    OUTCOME_VERIFIED instruction, since a later `reversed` observation must
    still be able to reopen it ("Reversed payment -> riapre Attention")."""
    instructions = list(
        session.scalars(select(m.TipPaymentInstruction).where(m.TipPaymentInstruction.payment_cycle_id == cycle.id))
    )
    for instruction in instructions:
        if instruction.status in (pi_svc.STATUS_READY, pi_svc.STATUS_CANCELLED):
            continue
        was_verified = instruction.status == pi_svc.STATUS_OUTCOME_VERIFIED
        pi_svc.refresh_outcome(session, instruction, connector)
        if was_verified and instruction.status == pi_svc.STATUS_NEEDS_ATTENTION:
            # Outcome Reopened — a fresh Attention Item every time (never
            # reuses the old one, which was already resolved/irrelevant to
            # this NEW reopening) — clear the guard so `_maybe_raise_
            # attention` raises again for this new occurrence.
            instruction.attention_item_id = None
        _maybe_raise_attention(session, instruction, restaurant_id=cycle.restaurant_id)
    session.flush()
