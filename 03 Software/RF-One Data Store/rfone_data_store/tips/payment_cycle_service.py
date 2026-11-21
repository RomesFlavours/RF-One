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

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as m
from .. import acting_identity_service
from .. import financial_authorization
from ..site_selection import require_operational
from . import payment_audit
from .money_lock import lock_restaurant
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
    # BANK_FINAL_RELEASE_BLOCKERS_001 T2 — only entitlements of a FINAL run
    # (validated by a person, or finalized automatically in AUTOMATIC mode
    # when the §11 control balances) may be paid. A CALCULATED run is not
    # approved truth, and two FINAL runs can never share a Business Date
    # (`calculation_run_service._blocking_final_run`), so no day is paid twice.
    return list(
        session.scalars(
            select(m.TipEntitlement)
            .join(m.TipDistributionCalculationRun,
                  m.TipDistributionCalculationRun.id == m.TipEntitlement.calculation_run_id)
            .where(
                m.TipEntitlement.restaurant_id == restaurant_id,
                m.TipEntitlement.tip_payment_instruction_id.is_(None),
                m.TipEntitlement.payable_amount_minor > 0,
                m.TipDistributionCalculationRun.state == m.TIPS_RUN_STATE_FINAL,
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
    prepared_by: "m.ActingIdentity | None" = None,
) -> "m.TipPaymentCycle | None":
    """Aggregates every currently-unpaid `TipEntitlement` into one new
    `TipPaymentCycle`, creating exactly one `TipPaymentInstruction` per
    Employee for the SUM of their unpaid entitlements. Idempotent by
    construction: if an OPEN cycle already exists for this Restaurant, it
    is returned UNCHANGED — never a second concurrent cycle, never a
    double-aggregation of the same entitlements. Returns `None` (no cycle
    created) if there is nothing unpaid to aggregate.

    `prepared_by`: the signed-in account's Acting Identity when a person
    prepares the cycle (Payment Control); omitted by automatic/system callers,
    which are recorded as the RF-One SYSTEM identity. A PREPARED audit event
    is written for every newly created cycle (CLOVER_MULTISITE_001)."""
    now = now or datetime.now(UTC)
    require_operational(session, restaurant_id)  # CLOVER_MULTISITE_001: no payment cycle for an inactive site
    # Serialized per restaurant: a manual and an automatic preparation never aggregate the same
    # entitlements; the second one waits, then finds the first one's open cycle.
    lock_restaurant(session, restaurant_id)

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

    # Second, independent guard: an entitlement is linked only while still unlinked; anything else means
    # a concurrent aggregation got there first, and nothing of this cycle is kept.
    for entitlement in unpaid:
        linked = session.execute(
            m.TipEntitlement.__table__.update()
            .where(m.TipEntitlement.id == entitlement.id, m.TipEntitlement.tip_payment_instruction_id.is_(None))
            .values(tip_payment_instruction_id=instructions_by_employee[entitlement.employee_id].id)
        ).rowcount
        if linked != 1:
            raise ApproveAndPayError(
                f"Tip Entitlement {entitlement.id} was aggregated by another Payment Cycle meanwhile; "
                "nothing was prepared.")
        session.expire(entitlement, ["tip_payment_instruction_id"])

    payment_audit.record(
        session, event=m.TIP_PAYMENT_AUDIT_PREPARED, cycle=cycle,
        acting_identity=prepared_by or acting_identity_service.get_or_create_system_identity(session),
        outcome=cycle.status, detail=f"{triggered_by}: {len(by_employee)} instruction(s), {len(unpaid)} entitlement(s).",
        now=now,
    )
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


def _payment_authority(session: Session, *, acting_identity: "m.ActingIdentity", restaurant_id: int):
    """The ONE Authority gate of every Tips payment action (Approve & Pay and
    retry of a failed instruction alike)."""
    return authorize(
        session, actor=acting_identity, action=AUTHORITY_ACTION_APPROVE_AND_PAY,
        context=AuthorizationContext(domain=AUTHORITY_DOMAIN_TIPS, scope_type=m.SCOPE_RESTAURANT, scope_id=restaurant_id),
    )


def can_approve_and_pay(session: Session, *, acting_identity: "m.ActingIdentity", restaurant_id: int) -> bool:
    """Read-only convenience wrapper around the SAME gate `approve_and_pay_
    cycle` enforces server-side (never a second, divergent check) — for a
    UI (or any other caller) that wants to show/filter options before a
    submit attempt. Never itself a substitute for the server-side gate:
    `approve_and_pay_cycle` re-checks Authority unconditionally regardless
    of what this returned."""
    return _payment_authority(session, acting_identity=acting_identity, restaurant_id=restaurant_id).allowed


def account_payment_identity(session: Session, *, account, restaurant_id: int) -> "m.ActingIdentity":
    """CLOVER_MULTISITE_001 (Product Owner 2026-11-21): a person approves or
    retries a Tips payment only as the account they are signed in with — the
    central `financial_authorization.require` (restaurant access in TIPS, an
    operational site, and the account's own Approve & Pay authority). Returns
    that account's Acting Identity; raises `ApproveAndPayError` otherwise."""
    try:
        return financial_authorization.require(
            session, account=account, permission=financial_authorization.TIPS_APPROVE_AND_PAY,
            restaurant_id=restaurant_id,
        )
    except financial_authorization.FinancialAuthorizationError as exc:
        raise ApproveAndPayError(str(exc)) from exc


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
    require_operational(session, cycle.restaurant_id)  # CLOVER_MULTISITE_001
    # Serialized per restaurant, then the cycle row is locked and re-read: two approvals (a person and
    # the scheduler, or two people) can never both see it OPEN.
    lock_restaurant(session, cycle.restaurant_id)
    session.execute(select(m.TipPaymentCycle.id).where(m.TipPaymentCycle.id == cycle.id).with_for_update())
    session.refresh(cycle)
    if cycle.status != m.TIP_PAYMENT_CYCLE_STATUS_OPEN:
        raise ApproveAndPayError(f"Payment Cycle {cycle.id} is not OPEN (status={cycle.status!r}).")

    decision = _payment_authority(session, acting_identity=acting_identity, restaurant_id=cycle.restaurant_id)
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

    # Phase 1 (one transaction): approval, and one durable attempt per instruction recorded BEFORE any
    # call to the provider (CLOVER_MULTISITE_001). Committed here.
    cycle.status = m.TIP_PAYMENT_CYCLE_STATUS_APPROVED
    cycle.approved_at = datetime.now(UTC)
    cycle.approved_by_identity_id = acting_identity.id
    payment_audit.record(
        session, event=m.TIP_PAYMENT_AUDIT_APPROVED, cycle=cycle, acting_identity=acting_identity,
        outcome=cycle.status, detail=f"{len(ready)} instruction(s) to submit.", now=cycle.approved_at,
    )
    actor = _submission_actor(session, acting_identity)
    prepared = []
    for instruction in ready:
        submission = pi_svc.prepare_submission(
            session, instruction, restaurant_id=cycle.restaurant_id, connector_code=connector.connector_code,
            account_id=source_account_id, actor=actor, now=cycle.approved_at)
        if submission is None:            # no recipient: nothing is sent, attention is raised
            _maybe_raise_attention(session, instruction, restaurant_id=cycle.restaurant_id)
        else:
            prepared.append((submission, instruction))
    session.commit()

    # Phase 2: one provider call per recorded attempt, each outcome committed on its own. A crash or a
    # lost answer leaves the attempt PENDING and the instruction SUBMITTING: awaiting reconciliation,
    # never sent again as a new payment.
    submitted = 0
    for submission, instruction in prepared:
        pi_svc.send_submission(session, submission, instruction, connector)
        _maybe_raise_attention(session, instruction, restaurant_id=cycle.restaurant_id)
        payment_audit.record(
            session, event=m.TIP_PAYMENT_AUDIT_EXECUTED, cycle=cycle, instruction=instruction,
            acting_identity=acting_identity, outcome=instruction.status,
            detail=f"submission {submission.id} {submission.state}; " + _execution_detail(instruction),
        )
        session.commit()
        if instruction.status in (pi_svc.STATUS_SENT, pi_svc.STATUS_SUBMITTED):
            submitted += 1

    needs_attention = sum(1 for i in instructions if i.status == pi_svc.STATUS_NEEDS_ATTENTION)
    return ApproveAndPayResult(cycle=cycle, submitted_count=submitted, needs_attention_count=needs_attention, funding=funding)


def _submission_actor(session: Session, acting_identity: "m.ActingIdentity") -> tuple[str, int | None, int | None]:
    """(actor_kind, account_id, acting_identity_id) recorded on every provider attempt."""
    kind, account_id, _label = payment_audit._actor(session, acting_identity)
    return kind, account_id, acting_identity.id


class PaymentRetryError(ApproveAndPayError):
    """A retry was refused: nothing was submitted and no state changed, or
    (for "already paid") only the read-back outcome was recorded."""


RETRY_SUBMITTED = "SUBMITTED"


def retry_instruction(
    session: Session, instruction: "m.TipPaymentInstruction", connector: "connector_svc.PaymentConnector", *,
    source_account_id: str, acting_identity: "m.ActingIdentity", now: datetime | None = None,
) -> str:
    """Resends exactly ONE failed Payment Instruction of an APPROVED cycle (CLOVER_MULTISITE_001,
    Product Owner 2026-11-21). Only when ALL hold:

    - the person (or system) has the Approve & Pay authority for the cycle's restaurant (the
      person-facing caller resolves `acting_identity` with `account_payment_identity`) and the site is
      operational;
    - no attempt of this instruction has an unknown outcome (PENDING/UNCERTAIN = awaiting
      reconciliation: never sent again);
    - the previous outcome is VERIFIED and is a failure: the provider refused the request (REJECTED),
      or its transaction is read back failed/blocked/cancelled (VERIFIED_FAILED); a transaction pending,
      sent or posted is already paid; a reversed one needs a person's review; an unreadable one is not
      guessed; an instruction never sent (no recipient) may be sent;
    - the amount is the authorized one (the instruction amount, equal to its aggregated entitlements and
      to the previous attempt) and the recipient is the authorized one (the same as the previous
      attempt, or a change recorded by an authorized recipient change after it).

    The new attempt is recorded and committed before the provider is called, with a new idempotency
    key (the failed key must not replay the failed transaction). Returns `RETRY_SUBMITTED`; raises
    `PaymentRetryError` when refused (an authorized refusal is audited)."""
    now = now or datetime.now(UTC)
    cycle = session.get(m.TipPaymentCycle, instruction.payment_cycle_id)
    if cycle is None:
        raise PaymentRetryError(f"Payment Instruction {instruction.id} has no Payment Cycle.")
    require_operational(session, cycle.restaurant_id)
    lock_restaurant(session, cycle.restaurant_id)
    session.execute(select(m.TipPaymentInstruction.id).where(
        m.TipPaymentInstruction.id == instruction.id).with_for_update())
    session.refresh(instruction)
    session.refresh(cycle)
    decision = _payment_authority(session, acting_identity=acting_identity, restaurant_id=cycle.restaurant_id)
    if not decision.allowed:
        raise PaymentRetryError(
            f"Acting Identity {acting_identity.id} is not authorized to pay Tips for Restaurant "
            f"{cycle.restaurant_id}: {decision.reason}")

    def refuse(message: str) -> PaymentRetryError:
        # An authorized attempt that resubmitted nothing is still audited.
        payment_audit.record(
            session, event=m.TIP_PAYMENT_AUDIT_RETRIED, cycle=cycle, instruction=instruction,
            acting_identity=acting_identity, outcome="REFUSED", detail=message, now=now,
        )
        session.flush()
        return PaymentRetryError(message)

    if cycle.status != m.TIP_PAYMENT_CYCLE_STATUS_APPROVED:
        raise refuse(f"Payment Cycle {cycle.id} is not approved (status={cycle.status!r}): use Approve & Pay.")
    if pi_svc.open_submission(session, instruction.id) is not None or instruction.status == pi_svc.STATUS_SUBMITTING:
        raise refuse(
            f"Payment Instruction {instruction.id} has an attempt whose outcome is not known yet: it is awaiting "
            "reconciliation with the provider and is never sent again as a new payment.")
    if instruction.status != pi_svc.STATUS_NEEDS_ATTENTION:
        raise refuse(
            f"Payment Instruction {instruction.id} is {instruction.status}: there is no failed payment to retry.")

    last = pi_svc.latest_submission(session, instruction.id)
    if last is None:
        if instruction.failure_class != pi_svc.FAILURE_RECIPIENT_NOT_CONFIGURED:
            raise refuse(f"Payment Instruction {instruction.id} has no recorded attempt to verify.")
    elif last.state == m.TIP_SUBMISSION_ACCEPTED:
        try:
            transaction = connector.get_transaction(last.provider_transaction_id)
        except connector_svc.PaymentConnectorError as exc:
            raise refuse(f"The outcome of the earlier payment of instruction {instruction.id} cannot be read "
                         f"from the provider ({exc}): nothing was resubmitted.")
        last.provider_status = transaction.status
        status = (transaction.status or "").lower()
        if status in ("pending", "sent"):
            instruction.provider_status = transaction.status
            instruction.status = pi_svc.STATUS_SENT
            instruction.failure_class = instruction.reason_for_failure = instruction.priority = None
            raise refuse(f"Payment Instruction {instruction.id} is already paid or in progress at the provider "
                         f"(status {transaction.status!r}): nothing was resubmitted.")
        if status == "reversed":
            raise refuse(f"Payment Instruction {instruction.id} was reversed by the provider: it needs a person's "
                         "review, not an automatic resubmission.")
        if status not in pi_svc.TERMINAL_FAILURE_STATUSES:
            raise refuse(f"The outcome of the earlier payment of instruction {instruction.id} is "
                         f"{transaction.status!r}, not a verified failure: nothing was resubmitted.")
        last.state = m.TIP_SUBMISSION_VERIFIED_FAILED
        last.resolved_at = now
    elif last.state not in (m.TIP_SUBMISSION_REJECTED, m.TIP_SUBMISSION_VERIFIED_FAILED):
        raise refuse(f"The previous attempt of instruction {instruction.id} is {last.state}: not a verified failure.")

    entitled = session.scalar(select(func.coalesce(func.sum(m.TipEntitlement.payable_amount_minor), 0)).where(
        m.TipEntitlement.tip_payment_instruction_id == instruction.id))
    if entitled != instruction.amount_minor or (last is not None and last.amount_minor != instruction.amount_minor):
        raise refuse(f"The amount of instruction {instruction.id} is not the authorized one: nothing was resubmitted.")
    reference = pi_svc.active_recipient_reference(session, instruction.employee_id,
                                                  connector_code=connector.connector_code)
    if last is not None and reference is not None and reference.id != last.recipient_reference_id:
        authorized_change = session.scalar(select(m.TipPaymentRecipientChange.id).where(
            m.TipPaymentRecipientChange.employee_id == instruction.employee_id,
            m.TipPaymentRecipientChange.new_reference_id == reference.id,
            m.TipPaymentRecipientChange.changed_at >= last.requested_at))
        if authorized_change is None:
            raise refuse(f"The recipient of instruction {instruction.id} changed without an authorized, recorded "
                         "recipient change: nothing was resubmitted.")

    submission = pi_svc.prepare_submission(
        session, instruction, restaurant_id=cycle.restaurant_id, connector_code=connector.connector_code,
        account_id=source_account_id, actor=_submission_actor(session, acting_identity), now=now, retry=True)
    if submission is None:
        session.flush()
        raise refuse(f"Employee {instruction.employee_id} has no active recipient: nothing was resubmitted.")
    session.commit()                      # the attempt is durable before the provider is called
    pi_svc.send_submission(session, submission, instruction, connector)
    _maybe_raise_attention(session, instruction, restaurant_id=cycle.restaurant_id)
    payment_audit.record(
        session, event=m.TIP_PAYMENT_AUDIT_RETRIED, cycle=cycle, instruction=instruction,
        acting_identity=acting_identity, outcome=instruction.status,
        detail=f"submission {submission.id} {submission.state}; " + _execution_detail(instruction), now=now,
    )
    session.commit()
    return RETRY_SUBMITTED


def _execution_detail(instruction: "m.TipPaymentInstruction") -> str:
    """Provider evidence of one submit attempt, for the audit row."""
    parts = [f"amount_minor={instruction.amount_minor}"]
    if instruction.provider_transaction_id:
        parts.append(f"provider_transaction_id={instruction.provider_transaction_id}")
    if instruction.idempotency_key:
        parts.append(f"idempotency_key={instruction.idempotency_key}")
    if instruction.failure_class:
        parts.append(f"failure_class={instruction.failure_class}")
    return "; ".join(parts)


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
