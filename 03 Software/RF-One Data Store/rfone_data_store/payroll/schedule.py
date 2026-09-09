"""Payroll Schedule / Payroll Period helpers (TASK_PAYROLL_001).

`PayrollSchedule` and `PayrollPeriod` are structurally independent concepts
— see `01 Domains/Cross Domain/Administration/Payroll/Payroll Schedule and
Period.md`. This module holds only the pure helper that demonstrates/
exercises that independence for the Administration/Payroll domain's own
cadence configuration.

`Workweek` (`workweeks_within_period`) moved to
`rfone_data_store/payroll_calculation/workweek.py` by explicit Product Owner
decision: the Workweek boundary is the evaluation window RF-One Compensation
/ Rule Matrix needs for a future Overtime Evaluator, so it is conceptually
owned by Compensation, not by this Administration/Payroll package, even
though `WorkweekDefinition`'s physical table is unchanged. Import it from
there where needed.

Deliberately absent from this module, by design (task §7-8, "Jurisdiction /
labor-rule boundary"): any function that computes overtime, or that treats a
BIWEEKLY Payroll Period's total hours as an 80-hour threshold. Overtime
determination is delegated to a future jurisdiction/labor-rule layer
operating on Workweek-scoped worked time, never on Payroll-Period-scoped
totals. `test_payroll_engine.py` asserts this module exposes no such
function at all, rather than merely asserting a formula is "correct."
"""

from __future__ import annotations

SCHEDULE_TYPES: tuple[str, ...] = ("WEEKLY", "BIWEEKLY", "MONTHLY")


def validate_schedule_type(schedule_type: str) -> None:
    if schedule_type not in SCHEDULE_TYPES:
        raise ValueError(
            f"Unsupported PayrollSchedule schedule_type: {schedule_type!r}. "
            f"Supported: {SCHEDULE_TYPES}"
        )
