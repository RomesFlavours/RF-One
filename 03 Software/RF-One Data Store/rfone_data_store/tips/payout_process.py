"""Tip Calculation trigger orchestration — the Clover-readiness-gated "Run
Calculation Now" action (TASK_TIPS_CORE2_PILOT; TASK_TIPS_COMPLETE_001 §5/
§15/§16; STEP 12B integration), channel-independent (`00 Core/
ImplementationGuidelines.md`, Core 2.0 Channel Independence): a UI button,
`tips/scheduler.py`'s automatic calculation loop, a CLI script, and a
future Trigger Intelligence capability can all call `run_calculation_now`
identically.

This is intentionally thin: every actual decision is delegated to an
existing, already-approved piece —

    readiness.describe_readiness        -> what is ready to CALCULATE,
                                            already gated on STEP 12A's
                                            canonical Clover Correction/
                                            Reconciliation Sync readiness
                                            (`readiness.ready_to_calculate`/
                                            `reconciliation_reason`) — never
                                            re-derived here
    distribution_engine                 -> the untouched Tip Business Rules
                                            + entitlement persistence

Everything from Payment Cycle onward (aggregating unpaid `TipEntitlement`
rows, Approve & Pay, connector submission, Attention) is a SEPARATE concern
owned by `tips/payment_cycle_service.py` — never triggered from here
("Calculation Schedule != Payment Schedule" applies to the orchestration
layer too, not only to the configuration)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from sqlalchemy import func, select

from .. import models as m
from . import calculation_run_service as run_svc
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
    """The mandatory sequence: Schedule/Manual Trigger -> Clover/Business
    Date Readiness Check -> calculate ONLY if READY. Never calculates
    twice for the same Business Date (`already_calculated`), and never
    calculates incomplete/not-yet-reconciled data (`ready_to_calculate`) —
    either condition simply returns with `blocked_reason` set, no
    exception, no false financial error; the caller (a human, or
    `tips/scheduler.py`'s own retry-next-tick loop) is expected to try
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

    if not state.ready_to_calculate:
        result.blocked_reason = f"Not ready to calculate: {state.reconciliation_reason}"
        return result

    # BANK_FINAL_RELEASE_BLOCKERS_001 T1 — the ONE persisted calculation:
    # the same service "Calculate and save this period" uses, over the
    # Location's Business Day window (timezone + operating-day cutoff, Order
    # Open Time), producing a validatable run. Never a UTC-midnight window,
    # never a second entitlement population.
    run, reason = run_svc.save_calculation_run(
        session, restaurant_id=restaurant_id,
        first_business_date=state.business_date, last_business_date=state.business_date,
    )
    if run is None:
        result.blocked_reason = reason
        return result
    result.calculation_run = run
    result.entitlements_created = session.scalar(
        select(func.count(m.TipEntitlement.id)).where(m.TipEntitlement.calculation_run_id == run.id)
    ) or 0
    result.ran = True
    return result
