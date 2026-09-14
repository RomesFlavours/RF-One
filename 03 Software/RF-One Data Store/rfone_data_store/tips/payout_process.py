"""Tip Calculation trigger orchestration — the Clover-readiness-gated "Run
Calculation Now" action (TASK_TIPS_CORE2_PILOT; TASK_TIPS_COMPLETE_001 §5/
§15/§16), channel-independent (`00 Core/ImplementationGuidelines.md`, Core
2.0 Channel Independence): a UI button, `tips/scheduler.py`'s automatic
calculation loop, a CLI script, and a future Trigger Intelligence capability
can all call `run_calculation_now` identically.

This is intentionally thin: every actual decision is delegated to an
existing, already-approved piece —

    readiness.describe_readiness        -> what is ready to CALCULATE
    distribution_engine                 -> the untouched Tip Business Rules
                                            + entitlement persistence

Everything from Payment Cycle onward (aggregating unpaid `TipEntitlement`
rows, Approve & Pay, Mercury submission, Attention) is a SEPARATE concern
owned by `tips/payment_cycle_service.py` — never triggered from here (task
§2's "Calculation Schedule != Payment Schedule" applies to the orchestration
layer too, not only to the configuration)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from .. import models as m
from . import distribution_engine as engine_svc
from . import readiness as readiness_svc


@dataclass
class CalculationRunResult:
    business_date: str | None
    ran: bool = False
    blocked_reason: str | None = None
    calculation_summary: "engine_svc.CalculationSummary | None" = None
    calculation_run: "m.TipDistributionCalculationRun | None" = None
    entitlements_created: int = 0


def run_calculation_now(session: Session, *, restaurant_id: int) -> CalculationRunResult:
    """Task §5's mandatory sequence: Schedule/Manual Trigger -> Clover/
    Business Date Readiness Check -> calculate ONLY if READY. Never
    calculates twice for the same Business Date (`already_calculated`), and
    never calculates incomplete data (`clover_ready`) — either condition
    simply returns with `blocked_reason` set, no exception, no false
    financial error (task §5's explicit requirement); the caller (a human,
    or `tips/scheduler.py`'s own retry-next-tick loop) is expected to try
    again later."""
    state = readiness_svc.describe_readiness(session, restaurant_id)
    result = CalculationRunResult(business_date=state.business_date.isoformat() if state.business_date else None)

    if state.business_date is None:
        result.blocked_reason = "No Business Date with Order data on file yet — nothing to calculate."
        return result

    if state.already_calculated:
        result.blocked_reason = f"Business Date {state.business_date.isoformat()} is already calculated."
        result.calculation_run = state.calculation_run
        return result

    if not state.clover_ready:
        result.blocked_reason = f"Not ready to calculate: {state.clover_reason}"
        return result

    period_start, period_end = readiness_svc.business_date_period(state.business_date)
    run, summary = engine_svc.run_tip_distribution_calculation(
        session, restaurant_id=restaurant_id, period_start=period_start, period_end=period_end,
    )
    session.flush()
    result.calculation_run = run
    result.calculation_summary = summary

    if run.status == engine_svc.STATUS_FAILED:
        result.blocked_reason = run.notes
        return result

    entitlements = engine_svc.populate_entitlements_for_run(session, run, business_date=state.business_date)
    result.entitlements_created = len(entitlements)
    result.ran = True
    return result
