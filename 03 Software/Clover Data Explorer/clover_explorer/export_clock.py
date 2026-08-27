"""Reconstruct the three-section clock_RFOne.csv comparable to Clover's
dashboard "Clock" export (SHIFTS / EMPLOYEE TOTALS / OVERRIDDEN SHIFTS).

Empirically confirmed semantics (validated against 8 real overridden-shift
reference rows by employee ID + timestamp, see CLOVER_EXPORT_MAPPING.md):

- `shift.inTime` / `shift.outTime` are the RAW/actual clock-in/out events.
- `shift.overrideInTime` / `shift.overrideOutTime`, when present, are a
  manager-entered correction that becomes the OFFICIAL clock-in/out used
  for the main SHIFTS section and for payroll hour totals.
- `shift.overrideInEmployee` / `shift.overrideOutEmployee` identify who
  performed the override (dashboard "Overridden by").
- The OVERRIDDEN SHIFTS section additionally shows the raw/actual time
  ("Actual Clock In/Out") next to the override, and both an "Overridden"
  and an "Actual" elapsed-hours figure.

A small (~0.01h) rounding inconsistency was observed between how Clover's
own SHIFTS-section "Elapsed Hours" and OVERRIDDEN-SHIFTS-section
"Overridden Elapsed Hours" round the *same* in/out pair — this is a
property of the reference export itself, not reproduced deliberately here;
see CLOVER_EXPORT_RECONCILIATION.md §4.
"""

from __future__ import annotations

from typing import Any

from .export_models import RawData, ref_id
from .time_money import elapsed_hours_str, format_clock_date, format_clock_time

SHIFTS_COLUMNS = [
    "Employee ID",
    "Employee Name",
    "Employee Custom ID",
    "Clock In Date",
    "Clock In Time",
    "Clock Out Date",
    "Clock Out Time",
    "Elapsed Hours",
]

EMPLOYEE_TOTALS_COLUMNS = [
    "Employee ID",
    "Employee Name",
    "Employee Custom ID",
    "Total Hours",
]

OVERRIDDEN_SHIFTS_COLUMNS = [
    "Employee ID",
    "Employee Name",
    "Employee Custom ID",
    "Override Clock In Date",
    "Override Clock In Time",
    "Overridden by",
    "Actual Clock In Date",
    "Actual Clock In Time",
    "Override Clock Out Date",
    "Override Clock Out Time",
    "Overridden by",
    "Actual Clock Out Date",
    "Actual Clock Out Time",
    "Overridden Elapsed Hours",
    "Actual Elapsed Hours",
    "Difference",
]


def _effective_in(shift: dict[str, Any]) -> int | None:
    return shift.get("overrideInTime", shift.get("inTime"))


def _effective_out(shift: dict[str, Any]) -> int | None:
    return shift.get("overrideOutTime", shift.get("outTime"))


def build_shifts_rows(shifts_in_window: list[dict[str, Any]], raw: RawData) -> list[dict[str, str]]:
    rows = []
    for s in shifts_in_window:
        in_ms, out_ms = _effective_in(s), _effective_out(s)
        if in_ms is None or out_ms is None:
            continue  # incomplete shift (no clock-out yet): not in the SHIFTS section
        emp_id, emp_name, emp_custom = raw.employee_fields(ref_id(s.get("employee")))
        rows.append(
            {
                "Employee ID": emp_id,
                "Employee Name": emp_name,
                "Employee Custom ID": emp_custom,
                "Clock In Date": format_clock_date(in_ms),
                "Clock In Time": format_clock_time(in_ms),
                "Clock Out Date": format_clock_date(out_ms),
                "Clock Out Time": format_clock_time(out_ms),
                "Elapsed Hours": elapsed_hours_str(in_ms, out_ms),
            }
        )
    return rows


def build_employee_totals_rows(shifts_in_window: list[dict[str, Any]], raw: RawData) -> list[dict[str, str]]:
    totals: dict[str, float] = {}
    order: list[str] = []
    for s in shifts_in_window:
        in_ms, out_ms = _effective_in(s), _effective_out(s)
        if in_ms is None or out_ms is None:
            continue
        emp_id = ref_id(s.get("employee"))
        if emp_id is None:
            continue
        hours = (out_ms - in_ms) / 1000 / 3600
        if emp_id not in totals:
            totals[emp_id] = 0.0
            order.append(emp_id)
        totals[emp_id] += hours

    rows = []
    for emp_id in order:
        _, emp_name, emp_custom = raw.employee_fields(emp_id)
        rows.append(
            {
                "Employee ID": emp_id,
                "Employee Name": emp_name,
                "Employee Custom ID": emp_custom,
                "Total Hours": f"{totals[emp_id]:.2f}",
            }
        )
    return rows


def overridden_shift_row_values(row: dict[str, str]) -> list[str]:
    """Serializes one build_overridden_shifts_rows() row dict into the exact
    16 positional values matching OVERRIDDEN_SHIFTS_COLUMNS — needed because
    the reference CSV's header legitimately repeats "Overridden by" twice
    (once for the in-side, once for the out-side), which a dict cannot hold
    as two distinct keys."""
    return [
        row["Employee ID"],
        row["Employee Name"],
        row["Employee Custom ID"],
        row["Override Clock In Date"],
        row["Override Clock In Time"],
        row["Overridden by (in)"],
        row["Actual Clock In Date"],
        row["Actual Clock In Time"],
        row["Override Clock Out Date"],
        row["Override Clock Out Time"],
        row["Overridden by (out)"],
        row["Actual Clock Out Date"],
        row["Actual Clock Out Time"],
        row["Overridden Elapsed Hours"],
        row["Actual Elapsed Hours"],
        row["Difference"],
    ]


def build_overridden_shifts_rows(shifts_in_window: list[dict[str, Any]], raw: RawData) -> list[dict[str, str]]:
    rows = []
    for s in shifts_in_window:
        has_in_override = "overrideInTime" in s
        has_out_override = "overrideOutTime" in s
        if not has_in_override and not has_out_override:
            continue

        emp_id, emp_name, emp_custom = raw.employee_fields(ref_id(s.get("employee")))
        in_employee_id, in_employee_name, _ = raw.employee_fields(ref_id(s.get("overrideInEmployee")))
        out_employee_id, out_employee_name, _ = raw.employee_fields(ref_id(s.get("overrideOutEmployee")))

        override_in_ms = s.get("overrideInTime")
        override_out_ms = s.get("overrideOutTime")
        actual_in_ms = s.get("inTime")
        actual_out_ms = s.get("outTime")

        overridden_in_ms = override_in_ms if has_in_override else actual_in_ms
        overridden_out_ms = override_out_ms if has_out_override else actual_out_ms

        overridden_elapsed = elapsed_hours_str(overridden_in_ms, overridden_out_ms)
        actual_elapsed = elapsed_hours_str(actual_in_ms, actual_out_ms)
        difference = ""
        if overridden_elapsed and actual_elapsed:
            difference = f"{float(overridden_elapsed) - float(actual_elapsed):.2f}"

        rows.append(
            {
                "Employee ID": emp_id,
                "Employee Name": emp_name,
                "Employee Custom ID": emp_custom,
                "Override Clock In Date": format_clock_date(override_in_ms) if has_in_override else "",
                "Override Clock In Time": format_clock_time(override_in_ms) if has_in_override else "",
                "Overridden by (in)": in_employee_name if has_in_override else "",
                "Actual Clock In Date": format_clock_date(actual_in_ms),
                "Actual Clock In Time": format_clock_time(actual_in_ms),
                "Override Clock Out Date": format_clock_date(override_out_ms) if has_out_override else "",
                "Override Clock Out Time": format_clock_time(override_out_ms) if has_out_override else "",
                "Overridden by (out)": out_employee_name if has_out_override else "",
                "Actual Clock Out Date": format_clock_date(actual_out_ms),
                "Actual Clock Out Time": format_clock_time(actual_out_ms),
                "Overridden Elapsed Hours": overridden_elapsed,
                "Actual Elapsed Hours": actual_elapsed,
                "Difference": difference,
            }
        )
    return rows
