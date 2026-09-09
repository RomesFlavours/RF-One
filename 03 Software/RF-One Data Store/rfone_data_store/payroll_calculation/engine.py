"""Payroll Calculation Engine — minimum services only (Product Owner
decision, corrected Option C; then corrected again for multi-rate earning
lines).

Computes RF-One's INTERNAL EXPECTED payroll. An Employee may work at more
than one hourly rate within the same calculation run (e.g. Server hours and
Manager hours) — each rate is its own `EmployeePayrollCalculationEarningLine`,
and the `EmployeePayrollCalculation` summary aggregates them:

    line.regular_pay      = line.regular_hours x line.hourly_rate_used
    summary.regular_hours = SUM(line.regular_hours)
    summary.regular_pay   = SUM(line.regular_pay)
    summary.gross_pay     = summary.regular_pay + tips_amount + bonus_amount

This is never the actual payroll processed by the external provider (ADP) —
that remains `rfone_data_store.payroll` / `payroll_runs` /
`employee_payroll_results`, unchanged. Naming note: this engine's internal
run concept is `CompensationPreparationRun` (formerly `PayrollCalculationRun`
— renamed by explicit Product Owner decision, since RF-One does not perform
Payroll), never to be confused with the Administration/Payroll domain's own
`PayrollRun`.

No overtime, deductions, taxes, employer taxes, bonus formula, or
payroll-provider submission is computed here. `tips_amount` and
`bonus_amount` are always caller-supplied employee-summary input facts —
never split into earning lines — and Tips calculation logic
(`rfone_data_store.tips`) and Bonus rules (future Performance Cross Domain
capability) are never invoked or reimplemented by this module.

Compensation is resolved exclusively from the existing
`EmployeeCompensationTerm` rows. This engine does not auto-pick "the" rate
for an Employee — the caller selects which `compensation_term_id` applies to
each earning line (Product Owner decision, rule 6: the existing
`EmployeeCompensationTerm`/`function_label` model already allows more than
one concurrently valid HOURLY term for the same Employee under different
functions — Compensation Terms.md, "Multiple functions / multiple rates" —
so no change to that model or to `rfone_data_store.payroll_calculation.compensation`
was needed). This engine only VALIDATES that the selected term actually belongs
to the Employee, to the Legal Entity of the `CompensationPreparationRun`
(`EmployeeCompensationTerm.legal_entity_id`), is HOURLY, and is effective
for the line's `work_date` (or, when `work_date` is absent, for the
calculation run's period) — reusing the existing `terms_valid_during`
helper rather than inventing a new effective-date rule. A term with a NULL
`legal_entity_id` is always rejected — it cannot prove which Legal Entity it
belongs to (a data-readiness/backfill condition for historical rows, not a
model contradiction).

Every `CompensationPreparationRun` belongs to exactly one Legal Entity
(`legal_entity_id` — Product Owner decision: the canonical `LegalEntity`
model, not `Restaurant`. An earlier version of this engine used
`restaurant_id`, reusing `Restaurant` as the Legal Entity; a follow-up
read-only verification confirmed `Restaurant` is formally an Operational
Unit, not the Legal Entity — a Legal Entity may own several Restaurants, so
scoping by `restaurant_id` would have incorrectly split one Legal Entity's
payroll across its Restaurants. `LegalEntity` is used instead). Results for
different Legal Entities are never combined into one run, and a
compensation term belonging to a different Legal Entity is rejected before
anything is persisted.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Sequence

from sqlalchemy.orm import Session

from .. import models as m
from . import compensation as compensation_helpers

_MINOR_UNIT = Decimal(100)
_CENTS = Decimal("0.01")


def _minor_to_decimal(amount_minor: int) -> Decimal:
    return Decimal(amount_minor) / _MINOR_UNIT


def _as_naive_utc(value: datetime) -> datetime:
    """Strips `tzinfo` if present, never converts it (this schema's own
    convention — models.py module docstring — is that persisted datetimes
    are already normalized to UTC by the application/ingestion layer before
    persisting, tz-aware or not). SQLite, unlike PostgreSQL, does not
    reliably round-trip `tzinfo` on a `DateTime(timezone=True)` column once
    an ORM object is reloaded from a real query rather than served from the
    Session identity map — comparing a reloaded (naive) term against a
    caller-supplied aware bound would otherwise raise `TypeError`
    nondeterministically. Normalizing both sides the same way keeps the
    effective-date check correct regardless of backend or object-identity
    timing."""
    return value.replace(tzinfo=None) if value.tzinfo is not None else value


@dataclass(frozen=True)
class _NormalizedTerm:
    """A `compensation.CompensationTermLike`-shaped, naive-UTC view of one
    `EmployeeCompensationTerm` row — passed into the existing
    `terms_valid_during` helper instead of the raw ORM row, so normalization
    never mutates real persisted state."""

    function_label: str
    valid_from: datetime
    valid_to: datetime | None


@dataclass(frozen=True)
class EarningLineInput:
    """One caller-supplied earning-line request: this many hours, at the
    rate carried by this specific `EmployeeCompensationTerm`. `work_date` is
    optional (Product Owner decision, rule 2) — when absent, effective-date
    validation falls back to the calculation run's whole period."""

    compensation_term_id: int
    hours: Decimal
    work_date: date | None = None


class InvalidCompensationTermError(ValueError):
    """Raised when a caller-selected `compensation_term_id` cannot be used
    for an earning line — wrong Employee, wrong Legal Entity, not HOURLY, or
    not effective for the line's `work_date`/the run's period. RF-One never
    silently substitutes a different term."""


def _validate_hourly_term_effective(
    session: Session,
    *,
    compensation_term_id: int,
    employee_id: int,
    legal_entity_id: int,
    work_date: date | None,
    period_start: datetime,
    period_end: datetime,
) -> m.EmployeeCompensationTerm:
    term = session.get(m.EmployeeCompensationTerm, compensation_term_id)
    if term is None:
        raise InvalidCompensationTermError(
            f"EmployeeCompensationTerm {compensation_term_id} does not exist"
        )
    if term.employee_id != employee_id:
        raise InvalidCompensationTermError(
            f"EmployeeCompensationTerm {compensation_term_id} does not belong to "
            f"employee_id={employee_id}"
        )
    if term.legal_entity_id != legal_entity_id:
        raise InvalidCompensationTermError(
            f"EmployeeCompensationTerm {compensation_term_id} belongs to a different "
            f"Legal Entity (legal_entity_id={term.legal_entity_id!r}) than the "
            f"CompensationPreparationRun's Legal Entity (legal_entity_id={legal_entity_id})"
        )
    if term.compensation_basis != compensation_helpers.HOURLY:
        raise InvalidCompensationTermError(
            f"EmployeeCompensationTerm {compensation_term_id} is not HOURLY"
        )

    normalized = _NormalizedTerm(
        function_label=term.function_label,
        valid_from=_as_naive_utc(term.valid_from),
        valid_to=_as_naive_utc(term.valid_to) if term.valid_to is not None else None,
    )
    if work_date is not None:
        # A single calendar day, as a half-open [day, day+1) window — the
        # same interval-overlap semantics `terms_valid_during` already uses
        # for a period, applied to one day instead of inventing a separate
        # point-in-time rule.
        day_start = datetime(work_date.year, work_date.month, work_date.day)
        window_start, window_end = day_start, day_start + timedelta(days=1)
    else:
        window_start, window_end = _as_naive_utc(period_start), _as_naive_utc(period_end)

    active = compensation_helpers.terms_valid_during([normalized], window_start, window_end)
    if not active:
        when = (
            f"work_date={work_date}"
            if work_date is not None
            else f"period {period_start}..{period_end}"
        )
        raise InvalidCompensationTermError(
            f"EmployeeCompensationTerm {compensation_term_id} is not effective for {when}"
        )
    return term


def calculate_earning_line(*, hours: Decimal, hourly_rate: Decimal) -> Decimal:
    """`regular_pay` for one earning line — the entire per-line MVP formula
    (Product Owner decision, rule 4). No overtime, no deductions, no taxes."""

    return (hours * hourly_rate).quantize(_CENTS)


def create_calculation_run(
    session: Session,
    *,
    legal_entity_id: int,
    period_start: datetime,
    period_end: datetime,
    status: str = "OPEN",
) -> m.CompensationPreparationRun:
    """Creates one `CompensationPreparationRun` — RF-One's own expected-payroll
    calculation cycle, never the Administration/Payroll domain's
    provider-facing `PayrollRun`. `legal_entity_id` is the required Legal
    Entity this run belongs to; results for different Legal Entities are
    never combined into one run."""

    run = m.CompensationPreparationRun(
        legal_entity_id=legal_entity_id, period_start=period_start, period_end=period_end,
        status=status,
    )
    session.add(run)
    session.flush()
    return run


def get_calculation_run(session: Session, calculation_run_id: int) -> m.CompensationPreparationRun | None:
    return session.get(m.CompensationPreparationRun, calculation_run_id)


def calculate_employee_payroll(
    session: Session,
    calculation_run: m.CompensationPreparationRun,
    *,
    employee_id: int,
    earning_lines: Sequence[EarningLineInput],
    tips_amount: Decimal = Decimal("0"),
    bonus_amount: Decimal = Decimal("0"),
) -> m.EmployeePayrollCalculation:
    """Validates each requested earning line's selected compensation term,
    persists one `EmployeePayrollCalculationEarningLine` per line, and
    persists the aggregated `EmployeePayrollCalculation` summary.
    `tips_amount`/`bonus_amount` are caller-supplied employee-summary input
    facts (default zero) — never computed here, never split into lines.

    Raises `InvalidCompensationTermError` (a `ValueError`) if any requested
    line's `compensation_term_id` does not belong to this Employee, belongs
    to a different Legal Entity than `calculation_run.legal_entity_id` (or
    has a NULL `legal_entity_id` — never assumed to match), is not HOURLY,
    or is not effective for its `work_date`/the run's period — no earning
    line or summary is persisted for a rejected request."""

    if not earning_lines:
        raise ValueError("calculate_employee_payroll requires at least one earning line")

    resolved_lines: list[tuple[EarningLineInput, m.EmployeeCompensationTerm, Decimal, Decimal]] = []
    for line_input in earning_lines:
        term = _validate_hourly_term_effective(
            session,
            compensation_term_id=line_input.compensation_term_id,
            employee_id=employee_id,
            legal_entity_id=calculation_run.legal_entity_id,
            work_date=line_input.work_date,
            period_start=calculation_run.period_start,
            period_end=calculation_run.period_end,
        )
        hourly_rate = _minor_to_decimal(term.hourly_rate_minor)
        line_pay = calculate_earning_line(hours=line_input.hours, hourly_rate=hourly_rate)
        resolved_lines.append((line_input, term, hourly_rate, line_pay))

    total_regular_hours = sum((li.hours for li, _t, _r, _p in resolved_lines), Decimal("0"))
    total_regular_pay = sum((line_pay for _li, _t, _r, line_pay in resolved_lines), Decimal("0"))
    gross_pay = total_regular_pay + tips_amount + bonus_amount

    summary = m.EmployeePayrollCalculation(
        calculation_run_id=calculation_run.id,
        employee_id=employee_id,
        regular_hours=total_regular_hours,
        regular_pay=total_regular_pay,
        tips_amount=tips_amount,
        bonus_amount=bonus_amount,
        gross_pay=gross_pay,
    )
    session.add(summary)
    session.flush()

    for line_input, term, hourly_rate, line_pay in resolved_lines:
        session.add(
            m.EmployeePayrollCalculationEarningLine(
                employee_payroll_calculation_id=summary.id,
                work_date=line_input.work_date,
                compensation_term_id=term.id,
                regular_hours=line_input.hours,
                hourly_rate_used=hourly_rate,
                regular_pay=line_pay,
            )
        )
    session.flush()
    return summary
