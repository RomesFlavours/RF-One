"""Tip Payout Process — the orchestration layer tying Process Activation
readiness, the existing deterministic Tip Distribution Engine, Payment
Instruction identity, funding check, and per-Payee isolation into ONE
channel-independent call (TASK_TIPS_CORE2_PILOT).

This is intentionally thin: every actual decision is delegated to an
existing, already-approved piece —

    readiness.describe_readiness        -> what is ready
    distribution_engine                 -> the untouched Tip Business Rules
    payment_instruction                 -> RF-One's own idempotency/outcome
    technical.connectors.mercury        -> the payment executor

— so this module has no Business Logic of its own to hide, satisfying task
§19's "no magic" requirement and Core 2.0's Channel Independence
(`00 Core/ImplementationGuidelines.md`): a UI button, a CLI script, and a
future Trigger Intelligence capability can all call `run_business_date_
payout` identically.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from .. import models as m
from ..technical.connectors.mercury.client import MercuryClient
from . import distribution_engine as engine_svc
from . import payment_instruction as pi_svc
from . import readiness as readiness_svc


@dataclass
class PayoutRunResult:
    business_date: str | None
    calculation_summary: engine_svc.CalculationSummary | None = None
    funding_check: pi_svc.FundingCheckResult | None = None
    submitted_count: int = 0
    verified_count: int = 0
    needs_attention_count: int = 0
    blocked_reason: str | None = None
    instructions: list["m.TipPaymentInstruction"] = field(default_factory=list)


def run_business_date_payout(
    session: Session, *, restaurant_id: int, client: MercuryClient, source_account_id: str,
) -> PayoutRunResult:
    """The full Process, from readiness to Outcome observation, for the
    single latest candidate Business Date (task §16's end-to-end pilot
    flow). Never processes more than one Business Date per call — a caller
    wanting the next one simply calls again once this one is
    `fully_settled` (`readiness.describe_readiness`).

    Funding is checked ONCE for the whole batch before ANY instruction is
    submitted (task §8): if insufficient, NO instruction is submitted —
    this function returns with `blocked_reason` set and every instruction
    left in READY, never a partial arbitrary payout. Once funding is
    confirmed sufficient, each instruction is submitted and its outcome
    refreshed independently (task §9): one instruction's failure is
    recorded on that instruction alone and never stops, rolls back, or
    re-runs any other instruction in the same batch."""
    state = readiness_svc.describe_readiness(session, restaurant_id)
    result = PayoutRunResult(business_date=state.business_date.isoformat() if state.business_date else None)

    if state.business_date is None:
        result.blocked_reason = "No Business Date with Order data on file yet — nothing to process."
        return result

    period_start, period_end = readiness_svc.business_date_period(state.business_date)

    if state.ready_to_calculate:
        run, summary = engine_svc.run_tip_distribution_calculation(
            session, restaurant_id=restaurant_id, period_start=period_start, period_end=period_end,
        )
        session.flush()
        result.calculation_summary = summary
        if run.status == engine_svc.STATUS_FAILED:
            result.blocked_reason = run.notes
            return result
    else:
        run = state.calculation_run

    instructions = pi_svc.get_or_create_payment_instructions_for_run(session, run)
    result.instructions = instructions

    ready_instructions = [i for i in instructions if i.status == pi_svc.STATUS_READY]
    if ready_instructions:
        funding = pi_svc.check_funding(client, account_id=source_account_id, instructions=ready_instructions)
        result.funding_check = funding
        if not funding.sufficient:
            # Task §8 — no arbitrary partial payout without a Business Rule
            # authorizing one. Every READY instruction stays READY; this is
            # a batch-level Attention condition, not per-instruction.
            result.blocked_reason = funding.reason
            return result

        for instruction in ready_instructions:
            # Each instruction is its own unit of work — an exception here
            # would already be unusual (submit_payment_instruction itself
            # catches every classified Mercury failure), but isolation is
            # structural: a raised exception from one instruction must never
            # prevent the loop from reaching the rest (task §9).
            try:
                pi_svc.submit_payment_instruction(session, instruction, client, account_id=source_account_id)
            except Exception as exc:  # noqa: BLE001 - isolation boundary, see docstring.
                pi_svc.mark_needs_attention(
                    instruction, failure_class=pi_svc.FAILURE_PROVIDER_UNAVAILABLE,
                    reason=f"Unexpected error submitting this Payment Instruction: {exc}",
                    priority=pi_svc.PRIORITY_HIGH,
                )
            session.flush()

    for instruction in instructions:
        if instruction.status in (pi_svc.STATUS_SENT, pi_svc.STATUS_SUBMITTED, pi_svc.STATUS_OUTCOME_VERIFIED):
            try:
                pi_svc.refresh_outcome(session, instruction, client)
            except Exception as exc:  # noqa: BLE001 - isolation boundary, see docstring.
                pi_svc.mark_needs_attention(
                    instruction, failure_class=pi_svc.FAILURE_PROVIDER_UNAVAILABLE,
                    reason=f"Unexpected error reading back this Payment Instruction's outcome: {exc}",
                    priority=pi_svc.PRIORITY_MEDIUM,
                )
            session.flush()

    result.submitted_count = sum(1 for i in instructions if i.submitted_at is not None)
    result.verified_count = sum(1 for i in instructions if i.status == pi_svc.STATUS_OUTCOME_VERIFIED)
    result.needs_attention_count = sum(1 for i in instructions if i.status == pi_svc.STATUS_NEEDS_ATTENTION)
    return result


def retry_instruction(session: Session, instruction: "m.TipPaymentInstruction", client: MercuryClient, *, source_account_id: str) -> None:
    """Task §16 item 12 — resume ONLY the one failed Payment Instruction
    after correction (e.g. a recipient reference was added/fixed). Never
    re-runs the calculation or touches any sibling instruction."""
    pi_svc.submit_payment_instruction(session, instruction, client, account_id=source_account_id)
    session.flush()
    if instruction.provider_transaction_id is not None:
        pi_svc.refresh_outcome(session, instruction, client)
        session.flush()
