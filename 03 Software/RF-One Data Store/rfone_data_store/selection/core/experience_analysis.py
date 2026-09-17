"""Experience Analysis (01 Domains/Shared Domains/Selection/
ResumeScreening/ExperienceAndTrajectory.md).

Every function here returns Derived Information computed from Work History
Facts — never persisted, always recomputed. Industry-specific role
classification (which normalized roles count as "the industry," customer-
facing, commercial, supervisory) is always supplied by the caller.

Documented year-only-date convention (Task 2B: "use a consistent documented
rule for year-only dates"): `selection/normalization.py` always normalizes a
bare year (e.g. "2021") to January 1st of that year. Every duration
calculated here from such a date (`months_between`, `work_entry_duration_months`,
`total_span_months`) therefore treats "2021 – 2022" as exactly 12 months —
not a claim that the underlying dates are actually known to month
precision (see `WorkHistoryRecord.start_date_precision`/`end_date_precision`
for that), just a single, consistent way to make year-only and month-precise
records comparable rather than incomparable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .profile import WorkHistoryRecord
from .role_model import ADJACENT, EQUIVALENT, OTHER, PROPEDEUTIC, TARGET, RoleConfiguration, classify_role

# Résumé dates carry no time-of-day/timezone meaning (month/year precision
# at best) and SQLite round-trips DateTime columns as naive regardless of
# `timezone=True` on the model — so every datetime in this package is kept
# naive by convention, never mixed with a tz-aware value.


def _now() -> datetime:
    return datetime.now()


def months_between(start: datetime | None, end: datetime | None) -> int | None:
    """Whole calendar months between two dates. `end=None` (an ongoing role)
    is treated as "through today." Returns None only when `start` itself is
    missing — an unknown start date is not the same as zero experience."""

    if start is None:
        return None
    effective_end = end or _now()
    if effective_end < start:
        return 0
    months = (effective_end.year - start.year) * 12 + (effective_end.month - start.month)
    if effective_end.day < start.day:
        months -= 1
    return max(months, 0)


def work_entry_duration_months(record: WorkHistoryRecord) -> int | None:
    """Task 2B's `duration_months` — one employment record's own duration,
    respecting whatever date precision it actually has. Reuses
    `months_between()` unchanged: every normalized date already carries
    day=1 by construction regardless of stated precision (module note
    above), so "2021 – 2022" (YEAR precision) and "Jan 2021 – Dec 2022"
    (MONTH precision) are NOT pretended to be equally precise — the caller
    can check `record.start_date_precision`/`end_date_precision` for that —
    but both compute a duration the same consistent, documented way: as if
    each date were the 1st of its (stated or year-assumed) month. Returns
    None exactly when `months_between()` would (no start date at all), i.e.
    "cannot be calculated reliably" per task's own rule."""

    return months_between(record.start_date, record.end_date if not record.is_current else None)


def chronological_timeline(work_history: list[WorkHistoryRecord]) -> list[WorkHistoryRecord]:
    """Task 2B's "career timeline" — work history sorted by `start_date`
    ascending (earliest first), never by résumé listing order (task:
    "Do NOT assume the order in the resume is always correct"). Records with
    no usable `start_date` are appended at the end, in their original
    relative order, rather than dropped — an unknown date is not the same
    as "does not belong on the timeline"."""

    dated = sorted((r for r in work_history if r.start_date is not None), key=lambda r: r.start_date)
    undated = [r for r in work_history if r.start_date is None]
    return dated + undated


def current_roles(work_history: list[WorkHistoryRecord]) -> list[WorkHistoryRecord]:
    """Every record flagged `is_current` — a candidate can genuinely hold
    more than one current role (part-time/consulting/seasonal, task
    "OVERLAPPING ROLES"), so this is a list, never assumed to be exactly
    one."""

    return [r for r in work_history if r.is_current]


def record_span(record: WorkHistoryRecord) -> tuple[datetime, datetime] | None:
    if record.start_date is None:
        return None
    end = record.end_date if (record.end_date and not record.is_current) else _now()
    if end < record.start_date:
        end = record.start_date
    return record.start_date, end


def merge_intervals(intervals: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    """Merge overlapping/adjacent intervals so a total span never double-
    counts concurrent employment (ExperienceAndTrajectory.md, "Overlap-safe
    total span")."""

    if not intervals:
        return []
    ordered = sorted(intervals, key=lambda iv: iv[0])
    merged = [ordered[0]]
    for start, end in ordered[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def total_span_months(work_history: list[WorkHistoryRecord]) -> int:
    spans = [s for s in (record_span(r) for r in work_history) if s is not None]
    merged = merge_intervals(spans)
    return sum(months_between(s, e) or 0 for s, e in merged)


@dataclass
class ExperienceBreakdown:
    target_months: int = 0
    equivalent_months: int = 0
    propedeutic_months: int = 0
    adjacent_months: int = 0
    other_months: int = 0
    industry_months: int = 0
    customer_facing_months: int = 0
    commercial_months: int = 0
    supervisory_months: int = 0
    total_span_months: int = 0

    @property
    def direct_role_months(self) -> int:
        """Target + Equivalent — what ExperienceAndTrajectory.md's "target-
        role experience" plus "equivalent-role experience" jointly mean by
        "direct" (RoleModel.md draws the Target/Equivalent line as
        interchangeable satisfaction of the same requirement)."""
        return self.target_months + self.equivalent_months

    @property
    def relevant_propedeutic_months(self) -> int:
        return self.propedeutic_months + self.adjacent_months


def compute_experience_breakdown(
    work_history: list[WorkHistoryRecord],
    role_config: RoleConfiguration,
    *,
    industry_roles: set[str] = frozenset(),
    customer_facing_roles: set[str] = frozenset(),
    commercial_roles: set[str] = frozenset(),
    supervisory_roles: set[str] = frozenset(),
) -> ExperienceBreakdown:
    breakdown = ExperienceBreakdown(total_span_months=total_span_months(work_history))
    for record in work_history:
        months = months_between(record.start_date, record.end_date if not record.is_current else None)
        if months is None:
            continue
        category = classify_role(record.normalized_role, role_config)
        if category == TARGET:
            breakdown.target_months += months
        elif category == EQUIVALENT:
            breakdown.equivalent_months += months
        elif category == PROPEDEUTIC:
            breakdown.propedeutic_months += months
        elif category == ADJACENT:
            breakdown.adjacent_months += months
        else:
            breakdown.other_months += months

        role = record.normalized_role or ""
        if role in industry_roles:
            breakdown.industry_months += months
        if role in customer_facing_roles:
            breakdown.customer_facing_months += months
        if role in commercial_roles:
            breakdown.commercial_months += months
        if role in supervisory_roles:
            breakdown.supervisory_months += months

    return breakdown


@dataclass
class TenureStats:
    employer_count: int = 0
    average_tenure_months: float = 0.0
    median_tenure_months: float = 0.0
    longest_tenure_months: int = 0
    most_recent_tenure_months: int | None = None
    jobs_under_3_months: int = 0
    jobs_under_6_months: int = 0
    jobs_over_12_months: int = 0
    jobs_over_24_months: int = 0


def compute_tenure_stats(work_history: list[WorkHistoryRecord]) -> TenureStats:
    durations = []
    dated = [r for r in work_history if r.start_date is not None]
    for record in dated:
        months = months_between(record.start_date, record.end_date if not record.is_current else None)
        if months is not None:
            durations.append(months)

    stats = TenureStats(employer_count=len({r.employer for r in work_history if r.employer}))
    if durations:
        stats.average_tenure_months = round(sum(durations) / len(durations), 1)
        sorted_durations = sorted(durations)
        mid = len(sorted_durations) // 2
        stats.median_tenure_months = (
            float(sorted_durations[mid]) if len(sorted_durations) % 2
            else (sorted_durations[mid - 1] + sorted_durations[mid]) / 2
        )
        stats.longest_tenure_months = max(durations)
        stats.jobs_under_3_months = sum(1 for d in durations if d < 3)
        stats.jobs_under_6_months = sum(1 for d in durations if d < 6)
        stats.jobs_over_12_months = sum(1 for d in durations if d >= 12)
        stats.jobs_over_24_months = sum(1 for d in durations if d >= 24)

    ordered_by_recency = sorted(
        (r for r in dated if r.start_date is not None), key=lambda r: r.start_date, reverse=True
    )
    if ordered_by_recency:
        most_recent = ordered_by_recency[0]
        stats.most_recent_tenure_months = months_between(
            most_recent.start_date, most_recent.end_date if not most_recent.is_current else None
        )
    return stats


@dataclass
class EmploymentGap:
    after_employer: str | None
    before_employer: str | None
    start: datetime
    end: datetime
    gap_months: int


@dataclass
class EmploymentOverlap:
    employer_a: str | None
    employer_b: str | None
    overlap_start: datetime
    overlap_end: datetime


def detect_gaps(work_history: list[WorkHistoryRecord], *, threshold_months: int = 2) -> list[EmploymentGap]:
    dated = [r for r in work_history if r.start_date is not None]
    ordered = sorted(dated, key=lambda r: r.start_date)
    gaps: list[EmploymentGap] = []
    for previous, current in zip(ordered, ordered[1:]):
        prev_end = previous.end_date if not previous.is_current else _now()
        if prev_end is None or current.start_date is None:
            continue
        gap_months = months_between(prev_end, current.start_date)
        if gap_months and gap_months >= threshold_months:
            gaps.append(
                EmploymentGap(
                    after_employer=previous.employer, before_employer=current.employer,
                    start=prev_end, end=current.start_date, gap_months=gap_months,
                )
            )
    return gaps


def detect_overlaps(work_history: list[WorkHistoryRecord]) -> list[EmploymentOverlap]:
    dated = [r for r in work_history if r.start_date is not None]
    ordered = sorted(dated, key=lambda r: r.start_date)
    overlaps: list[EmploymentOverlap] = []
    for i, a in enumerate(ordered):
        a_end = a.end_date if not a.is_current else _now()
        if a_end is None:
            continue
        for b in ordered[i + 1:]:
            if b.start_date is None or b.start_date >= a_end:
                break
            b_end = b.end_date if not b.is_current else _now()
            overlap_end = min(a_end, b_end) if b_end else a_end
            overlaps.append(
                EmploymentOverlap(
                    employer_a=a.employer, employer_b=b.employer,
                    overlap_start=b.start_date, overlap_end=overlap_end,
                )
            )
    return overlaps
