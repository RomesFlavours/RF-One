"""Incentive Contributions and the Recognized Incentive (functional spec
§14, `01 Domains/Cross Domain/Personnel Management/Compensation/
COMPENSATION_AND_INCOME_COMPOSITION_001.md`).

Compensation V1 has no Event Log / Incentive Rule engine (spec §10-13
remain conceptual/documented only) — a human enters each positive or
negative Incentive Contribution directly for an Employee within one
`CompensationPreparationRun`, exactly as the manual Payroll Provider
communication this task completes requires.

RF-One has one economic concept, the Incentive — there is no separate
"Disincentive" concept (spec §14). A negative Contribution only ever
reduces the Incentive being evaluated:

    Raw Incentive        = SUM(contribution.amount)
    Recognized Incentive = MAX(0, Raw Incentive)

No negative economic value is ever sent to Compensation's `gross_pay` or to
the Payroll Provider — only the Recognized (already-floored) Incentive
leaves this module (spec §14/§18/§22)."""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m

_CENTS = Decimal("0.01")

_EDITABLE_STATUSES = ("OPEN", "CALCULATED")


class IncentiveContributionRunNotEditableError(ValueError):
    """Raised when an Incentive Contribution is added to or removed from a
    `CompensationPreparationRun` that is no longer OPEN/CALCULATED (already
    APPROVED/EXPORTED/CLOSED) — approved Incentive detail is immutable (see
    `ApprovedIncentiveContributionLine`, copied once at approval time)."""


def add_incentive_contribution(
    session: Session,
    *,
    calculation_run_id: int,
    employee_id: int,
    label: str,
    amount: Decimal,
    created_by: str,
    source_note: str | None = None,
) -> m.IncentiveContribution:
    """Persists one Incentive Contribution. `amount` may be negative — it is
    never rejected or clamped here; the zero-floor rule (spec §14.1) is
    applied only when computing the Recognized Incentive
    (`calculate_recognized_incentive`), never on an individual Contribution.
    Does not commit."""

    run = session.get(m.CompensationPreparationRun, calculation_run_id)
    if run is None:
        raise ValueError(f"CompensationPreparationRun {calculation_run_id} does not exist")
    if run.status not in _EDITABLE_STATUSES:
        raise IncentiveContributionRunNotEditableError(
            f"CompensationPreparationRun {calculation_run_id} is not editable "
            f"(status={run.status!r})"
        )
    if not label or not label.strip():
        raise ValueError("add_incentive_contribution requires a non-empty label")
    if not created_by or not created_by.strip():
        raise ValueError(
            "add_incentive_contribution requires a non-empty created_by actor reference"
        )

    contribution = m.IncentiveContribution(
        calculation_run_id=calculation_run_id,
        employee_id=employee_id,
        label=label.strip(),
        amount=amount.quantize(_CENTS),
        source_note=source_note,
        created_by=created_by,
    )
    session.add(contribution)
    session.flush()
    return contribution


def delete_incentive_contribution(session: Session, *, contribution_id: int) -> None:
    """Removes one not-yet-approved Incentive Contribution. A no-op if the
    contribution no longer exists (idempotent delete, matching this
    schema's existing convention elsewhere)."""

    contribution = session.get(m.IncentiveContribution, contribution_id)
    if contribution is None:
        return
    run = session.get(m.CompensationPreparationRun, contribution.calculation_run_id)
    if run is not None and run.status not in _EDITABLE_STATUSES:
        raise IncentiveContributionRunNotEditableError(
            f"CompensationPreparationRun {contribution.calculation_run_id} is not editable "
            f"(status={run.status!r})"
        )
    session.delete(contribution)
    session.flush()


def list_incentive_contributions(
    session: Session, *, calculation_run_id: int, employee_id: int,
) -> list[m.IncentiveContribution]:
    return list(
        session.scalars(
            select(m.IncentiveContribution)
            .where(
                m.IncentiveContribution.calculation_run_id == calculation_run_id,
                m.IncentiveContribution.employee_id == employee_id,
            )
            .order_by(m.IncentiveContribution.created_at)
        ).all()
    )


def calculate_recognized_incentive(
    contributions: Iterable[m.IncentiveContribution] | Iterable[Decimal],
) -> Decimal:
    """Raw = algebraic sum of contribution amounts; Recognized = MAX(0, Raw)
    (functional spec §14, §14.1). Accepts either persisted
    `IncentiveContribution` rows or bare `Decimal` amounts, so a caller
    building an in-memory preview (not yet persisted) can use the identical
    function."""

    raw = Decimal("0")
    for contribution in contributions:
        amount = contribution.amount if hasattr(contribution, "amount") else contribution
        raw += amount
    return max(Decimal("0"), raw).quantize(_CENTS)
