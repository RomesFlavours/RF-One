"""Explanations of the Selection Indicators (SELECTION_INDICATOR_EXPLANATIONS_001).

For Direct Role Experience, Relevant / Propedeutic Experience, Stability and
Career Progression, says WHAT the shown value is made of: the experiences
used (original title, employer, dates as written, duration), why each one
counts for the application's target role, the rule and thresholds the
system actually applies — restated from the code, never changed here — and
what is excluded, missing or uncertain and limits the result.

When a value is "to be clarified", the explanation says which information
is missing; known durations are then given as detail only, never as a
complete total. "Reading uncertain" is about how the CV was read, never
about the candidate's reliability. Months by role come from the job TITLES
as read; coordination duties declared in the CV are a separate thing and are
never counted here.

No score, ranking, weight or new criterion: this module only explains.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .core.experience_analysis import TenureStats, months_between
from .core.profile import WorkHistoryRecord
from .core.role_model import ADJACENT, EQUIVALENT, PROPEDEUTIC, TARGET, RoleConfiguration, classify_role
from .core.trajectory import TrajectoryEvent

DIRECT = "Direct Role Experience"
PROPEDEUTIC_NAME = "Relevant / Propedeutic Experience"
STABILITY = "Stability"
PROGRESSION = "Career Progression"
TO_CLARIFY = "to be clarified"

TITLES_NOT_DUTIES = ("Counted from the job titles as read. Coordination duties declared in the CV are shown "
                     "separately and are not counted here.")


@dataclass
class ExplanationLine:
    title: str | None
    employer: str | None
    start: str | None
    end: str | None
    months: int | None
    reason: str


@dataclass
class IndicatorExplanation:
    name: str
    value: str
    state: str | None
    criteria: list[str]
    used: list[ExplanationLine] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)  # excluded, missing or uncertain information
    to_clarify: str | None = None  # why the value is "to be clarified"
    known_months_detail: int | None = None  # known part of an incomplete total — detail only
    total_months: int | None = None  # the total, when it is complete


def _months(record: WorkHistoryRecord) -> int | None:
    return months_between(record.start_date, record.end_date if not record.is_current else None)


def _where(record: WorkHistoryRecord) -> str:
    title = f'"{record.original_job_title}"' if record.original_job_title else "an experience with no title"
    return f"{title}{' at ' + record.employer if record.employer else ''}"


def _months_label(months: int) -> str:
    return f"{months} month{'s' if months != 1 else ''}"


def explain_role_months(
    name: str, work_history: list[WorkHistoryRecord], role_config: RoleConfiguration | None, *,
    display_name_fn: Callable[[str | None], str | None],
) -> IndicatorExplanation:
    """Direct (target + equivalent roles) or propedeutic (propedeutic +
    adjacent roles) months for the target role, from the existing
    Role Configuration and classification."""

    direct = name == DIRECT
    if role_config is None:
        return IndicatorExplanation(
            name=name, value=TO_CLARIFY, state=None,
            criteria=["Depends on the application's target role."],
            to_clarify="The application has no supported target role (Server or FOH Team Leader), so no "
                       "experience can be classified against it.",
        )

    label = role_config.label

    def names(codes) -> str:
        return ", ".join(sorted({display_name_fn(c) or c for c in codes})) or "none"

    if direct:
        categories = {TARGET, EQUIVALENT}
        criteria = [f"Months of experiences whose role is the target role ({label}) or an equivalent of it "
                    f"(equivalents: {names(role_config.equivalent_roles)}).", TITLES_NOT_DUTIES]
    else:
        categories = {PROPEDEUTIC, ADJACENT}
        criteria = [f"Months of experiences in roles that prepare for {label}: propedeutic "
                    f"({names(role_config.propedeutic_roles)}) or adjacent ({names(role_config.adjacent_roles)}).",
                    TITLES_NOT_DUTIES]

    used, limitations, missing_dates, uncertain = [], [], [], []
    total = 0
    for index, record in enumerate(work_history, start=1):
        if record.structure_confidence == "LOW":
            uncertain.append(f"Experience {index}: the CV could not be read with certainty (its role is not "
                             "determined), so it may or may not be of this kind.")
            continue
        category = classify_role(record.normalized_role, role_config)
        if category not in categories:
            if not record.normalized_role and record.original_job_title:
                limitations.append(f"{_where(record)}: title not recognized, not counted (to be clarified).")
            continue
        role_name = display_name_fn(record.normalized_role) or record.normalized_role
        reason = {
            TARGET: f"read as {role_name}: the target role {label}",
            EQUIVALENT: f"read as {role_name}: an equivalent of {label}",
            PROPEDEUTIC: f"read as {role_name}: propedeutic for {label}",
            ADJACENT: f"read as {role_name}: adjacent to {label}",
        }[category]
        months = _months(record)
        used.append(ExplanationLine(record.original_job_title, record.employer, record.start_date_text,
                                    record.end_date_text, months, reason))
        if months is None:
            missing_dates.append(f"{_where(record)}: no usable dates "
                                 f"(start {record.start_date_text or 'not stated'}, end "
                                 f"{record.end_date_text or 'not stated'}), so its duration is unknown.")
        else:
            total += months

    limitations = uncertain + missing_dates + limitations
    if uncertain or missing_dates:
        known = sum(line.months for line in used if line.months is not None)
        return IndicatorExplanation(
            name=name, value=TO_CLARIFY, state=None, criteria=criteria, used=used, limitations=limitations,
            to_clarify=" ".join(uncertain + missing_dates),
            known_months_detail=known if any(line.months is not None for line in used) else None,
        )
    return IndicatorExplanation(
        name=name, value=_months_label(total), state=None, criteria=criteria, used=used,
        limitations=limitations, total_months=total,
    )


def explain_stability(work_history: list[WorkHistoryRecord], tenure: TenureStats, state: str | None,
                      value: str) -> IndicatorExplanation:
    """Restates `core.indicators._stability_state` and
    `core.experience_analysis.compute_tenure_stats` exactly."""

    criteria = [
        "Durations come from the jobs with a start date; a job is short when it lasted under 6 months.",
        f"Distinct employers counted: {tenure.employer_count}. Jobs with a usable duration: "
        f"{tenure.dated_job_count}. Short jobs: {tenure.jobs_under_6_months}.",
        "Unknown: no employer, or no job with a usable duration.",
        "Weak: short jobs divided by distinct employers is 50% or more.",
        "Moderate: otherwise, at least one short job or an average tenure under 12 months.",
        "Strong: otherwise.",
    ]
    used, limitations = [], []
    for index, record in enumerate(work_history, start=1):
        months = _months(record) if record.start_date is not None else None
        if months is None:
            limitations.append(f"{_where(record)}: no usable dates, not part of the durations.")
            continue
        used.append(ExplanationLine(record.original_job_title, record.employer, record.start_date_text,
                                    record.end_date_text, months,
                                    "short (under 6 months)" if months < 6 else "not short"))
        if record.structure_confidence == "LOW":
            limitations.append(f"Experience {index}: read with uncertainty — counted by its dates, its employer "
                               "was not determined.")
    explanation = IndicatorExplanation(name=STABILITY, value=value, state=state, criteria=criteria, used=used,
                                       limitations=limitations)
    if state == "Unknown":
        explanation.to_clarify = ("No employer was identified." if tenure.employer_count == 0
                                  else "No job has a usable duration (dates missing).")
    return explanation


def explain_progression(work_history: list[WorkHistoryRecord], events: list[TrajectoryEvent], state: str | None,
                        value: str, *, seniority_rank_fn: Callable[[str | None], int | None]) -> IndicatorExplanation:
    """Restates `core.trajectory.detect_trajectory` exactly."""

    criteria = [
        "Each job is compared with the one just before it, in order of start date.",
        "The comparison uses the seniority rank of the roles as read (Restaurant extension, 1 to 5); "
        "a pair with a role of unknown rank is not compared.",
        "Higher rank at the same employer: promotion. Higher rank at another employer: increase in "
        "responsibility. Both count as an upward move; equal or lower rank does not.",
    ]
    dated = sorted((r for r in work_history if r.start_date is not None), key=lambda r: r.start_date)
    used, limitations = [], []
    for record in work_history:
        if record.start_date is None:
            limitations.append(f"{_where(record)}: no start date, not part of the comparison.")
    for previous, current in zip(dated, dated[1:]):
        prev_rank, curr_rank = seniority_rank_fn(previous.normalized_role), seniority_rank_fn(current.normalized_role)
        if prev_rank is None or curr_rank is None:
            limitations.append(f"{_where(previous)} → {_where(current)}: not compared, the rank of "
                               f"{_where(previous) if prev_rank is None else _where(current)} is unknown.")
            continue
        if curr_rank > prev_rank:
            kind = "promotion (same employer)" if previous.employer and previous.employer == current.employer \
                else "increase in responsibility (another employer)"
        elif curr_rank < prev_rank:
            kind = "lower rank (not an upward move)"
        else:
            kind = "same rank (not an upward move)"
        used.append(ExplanationLine(current.original_job_title, current.employer, current.start_date_text,
                                    current.end_date_text, _months(current),
                                    f"after {_where(previous)}: rank {prev_rank} → {curr_rank}, {kind}"))
    for record in work_history:
        if record.structure_confidence == "LOW":
            limitations.append("An experience was read with uncertainty: its role and rank are not determined.")
            break
    explanation = IndicatorExplanation(name=PROGRESSION, value=value, state=state, criteria=criteria, used=used,
                                       limitations=limitations)
    if len(dated) < 2:
        explanation.limitations.append("Fewer than two jobs with a start date: there is nothing to compare.")
    return explanation
