"""Compensation Terms helpers (TASK_PAYROLL_001).

No formula computes a Bonus amount anywhere in this module — Bonus is
always an externally supplied earning fact (`Payroll Processing.md`,
"Bonus boundary"). No formula computes overtime here either (see
`schedule.py`'s module docstring).
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, Sequence

HOURLY = "HOURLY"
SALARIED = "SALARIED"
COMPENSATION_BASES: tuple[str, ...] = (HOURLY, SALARIED)

OK = "OK"
MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"


class CompensationTermLike(Protocol):
    """Structural (duck-typed) shape the helpers below require — satisfied
    by the `EmployeeCompensationTerm` ORM model or any plain fixture."""

    function_label: str
    valid_from: datetime
    valid_to: datetime | None


def terms_valid_during(
    terms: Sequence[CompensationTermLike], interval_start: datetime, interval_end: datetime
) -> list[CompensationTermLike]:
    """Every term whose [valid_from, valid_to) interval overlaps
    [interval_start, interval_end). `valid_to is None` means open-ended."""
    result: list[CompensationTermLike] = []
    for term in terms:
        term_end = term.valid_to if term.valid_to is not None else interval_end
        if term.valid_from < interval_end and term_end > interval_start:
            result.append(term)
    return result


def detect_mid_period_conflict(
    terms: Sequence[CompensationTermLike], period_start: datetime, period_end: datetime
) -> bool:
    """True when more than one Compensation Term under the SAME
    `function_label` applies inside one Payroll Period (Compensation
    Terms.md, "Mid-period compensation changes") — a rate CHANGE mid-period
    for one function, never simply two different concurrent functions
    (which is not a conflict at all, "Multiple functions / multiple
    rates")."""
    active = terms_valid_during(terms, period_start, period_end)
    by_function: dict[str, int] = {}
    for term in active:
        by_function[term.function_label] = by_function.get(term.function_label, 0) + 1
    return any(count > 1 for count in by_function.values())


def review_status_for_period(
    terms: Sequence[CompensationTermLike], period_start: datetime, period_end: datetime
) -> str:
    return MANUAL_REVIEW_REQUIRED if detect_mid_period_conflict(terms, period_start, period_end) else OK
