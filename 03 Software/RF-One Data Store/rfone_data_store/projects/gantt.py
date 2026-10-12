"""MyRF Project Management v1 — Gantt geometry (read only).

Every position is a percentage of the whole plan, from the earliest planned
start to the latest planned end (calendar days). The chart therefore always
fits the width it is given — the screen, or a landscape page when printed —
and a long period is compressed, never cut. The timeline scale adapts to the
plan's length: weeks, months, then quarters.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .service import Plan, PlanTask

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
WEEKS_UP_TO_DAYS = 62
MONTHS_UP_TO_DAYS = 550
# Past this point of the timeline the percentage label goes before the bar,
# so it never runs off the right edge; when there is no room before the bar
# either (a bar spanning almost the whole plan), it goes inside the bar.
LABEL_FLIP_PERCENT = 88.0
LABEL_ROOM_PERCENT = 8.0


@dataclass(frozen=True)
class Segment:
    label: str
    left: float   # percent of the timeline
    width: float  # percent of the timeline


@dataclass(frozen=True)
class Bar:
    left: float
    width: float
    label: str = "after"   # where the percentage label sits: "after", "before" or "inside"

    @property
    def end(self) -> float:
        return round(self.left + self.width, 4)


@dataclass(frozen=True)
class Timeline:
    start: date
    end: date
    days: int
    unit: str          # "week", "month" or "quarter"
    segments: tuple[Segment, ...]

    def _percent(self, day: date) -> float:
        return (day - self.start).days / self.days * 100

    def bar(self, start: date, end: date) -> Bar:
        left = self._percent(start)
        width = ((end - start).days + 1) / self.days * 100
        if left + width <= LABEL_FLIP_PERCENT:
            label = "after"
        elif left >= LABEL_ROOM_PERCENT:
            label = "before"
        else:
            label = "inside"
        return Bar(left=round(left, 4), width=round(width, 4), label=label)

    def task_bar(self, task: PlanTask) -> Bar:
        return self.bar(task.planned_start_date, task.planned_end_date)


def _month_start(day: date) -> date:
    return day.replace(day=1)


def _add_months(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def timeline_for(plan: Plan) -> Timeline | None:
    start, end = plan.start, plan.end
    if start is None or end is None:
        return None
    days = (end - start).days + 1

    if days <= WEEKS_UP_TO_DAYS:
        unit = "week"
        boundary = start - timedelta(days=start.weekday())  # the Monday of the first week
        step = lambda d: d + timedelta(days=7)  # noqa: E731
        label = lambda d: d.strftime("%d/%m")  # noqa: E731
    elif days <= MONTHS_UP_TO_DAYS:
        unit = "month"
        boundary = _month_start(start)
        step = lambda d: _add_months(d, 1)  # noqa: E731
        label = lambda d: f"{MONTHS[d.month - 1]} {d.strftime('%y')}"  # noqa: E731
    else:
        unit = "quarter"
        boundary = date(start.year, (start.month - 1) // 3 * 3 + 1, 1)
        step = lambda d: _add_months(d, 3)  # noqa: E731
        label = lambda d: f"Q{(d.month - 1) // 3 + 1} {d.year}"  # noqa: E731

    segments: list[Segment] = []
    while boundary <= end:
        following = step(boundary)
        seg_start, seg_end = max(boundary, start), min(following - timedelta(days=1), end)
        segments.append(Segment(
            # A first segment cut by the plan's start shows its real first day.
            label=label(seg_start) if unit == "week" else label(boundary),
            left=round((seg_start - start).days / days * 100, 4),
            width=round(((seg_end - seg_start).days + 1) / days * 100, 4),
        ))
        boundary = following
    return Timeline(start=start, end=end, days=days, unit=unit, segments=tuple(segments))
