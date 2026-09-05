"""Career Trajectory detection (01 Domains/Cross Domain/Selection/
ResumeScreening/ExperienceAndTrajectory.md, "Career trajectory").

Detects THAT a transition happened; never infers WHY (see that document,
"Do not infer motive"). Seniority ranking and role-category classification
are always supplied by the caller (an Industry Extension) — Selection Core
has no notion of what makes one role more senior than another.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from .profile import WorkHistoryRecord
from .role_model import RoleConfiguration

PROMOTION = "PROMOTION"
INCREASE_IN_RESPONSIBILITY = "INCREASE_IN_RESPONSIBILITY"
LATERAL_MOVE = "LATERAL_MOVE"
APPARENT_DECREASE = "APPARENT_DECREASE"
RETURN_TO_EMPLOYER = "RETURN_TO_EMPLOYER"


@dataclass
class TrajectoryEvent:
    type: str
    from_title: str | None
    to_title: str | None
    from_employer: str | None
    to_employer: str | None
    at_date: datetime | None
    detail: str


def _ordered(work_history: list[WorkHistoryRecord]) -> list[WorkHistoryRecord]:
    return sorted((r for r in work_history if r.start_date is not None), key=lambda r: r.start_date)


def detect_trajectory(
    work_history: list[WorkHistoryRecord],
    *,
    seniority_rank_fn: Callable[[str | None], int | None],
) -> list[TrajectoryEvent]:
    """Compare each role to the one immediately before it, chronologically.
    Only roles with a known seniority rank participate — an unranked role
    (e.g. outside the configured industry catalog) is skipped rather than
    guessed at."""

    ordered = _ordered(work_history)
    events: list[TrajectoryEvent] = []

    seen_employers: set[str] = set()
    for previous, current in zip(ordered, ordered[1:]):
        if current.employer and current.employer in seen_employers and current.employer != previous.employer:
            events.append(
                TrajectoryEvent(
                    type=RETURN_TO_EMPLOYER, from_title=previous.original_job_title,
                    to_title=current.original_job_title, from_employer=previous.employer,
                    to_employer=current.employer, at_date=current.start_date,
                    detail=f"Candidate returned to a previous employer: {current.employer}.",
                )
            )
        if previous.employer:
            seen_employers.add(previous.employer)

        prev_rank = seniority_rank_fn(previous.normalized_role)
        curr_rank = seniority_rank_fn(current.normalized_role)
        if prev_rank is None or curr_rank is None:
            continue

        same_employer = bool(previous.employer) and previous.employer == current.employer
        if curr_rank > prev_rank:
            event_type = PROMOTION if same_employer else INCREASE_IN_RESPONSIBILITY
            detail = (
                f"{'Promoted' if same_employer else 'Moved to a higher-responsibility role'} "
                f"from {previous.original_job_title or previous.normalized_role} to "
                f"{current.original_job_title or current.normalized_role}."
            )
        elif curr_rank < prev_rank:
            event_type = APPARENT_DECREASE
            detail = (
                f"Apparent decrease in responsibility from "
                f"{previous.original_job_title or previous.normalized_role} to "
                f"{current.original_job_title or current.normalized_role} — motive unknown."
            )
        else:
            event_type = LATERAL_MOVE
            detail = (
                f"Lateral move from {previous.original_job_title or previous.normalized_role} to "
                f"{current.original_job_title or current.normalized_role}."
            )

        events.append(
            TrajectoryEvent(
                type=event_type, from_title=previous.original_job_title, to_title=current.original_job_title,
                from_employer=previous.employer, to_employer=current.employer,
                at_date=current.start_date, detail=detail,
            )
        )

    return events


def _display_category(category: str) -> str:
    """Short all-caps category codes (e.g. "BOH") read as acronyms and stay
    upper-case; longer codes (e.g. "NON_HOSPITALITY") are title-cased. A
    generic heuristic — Core has no list of real industry acronyms."""
    if category.isupper() and len(category) <= 4:
        return category
    return category.replace("_", " ").title()


@dataclass
class TransitionToInvestigate:
    from_category: str
    to_role: str
    from_title: str | None
    from_employer: str | None
    suggested_question: str


def detect_transitions_to_investigate(
    work_history: list[WorkHistoryRecord],
    role_config: RoleConfiguration,
    *,
    role_category_fn: Callable[[str | None], str | None],
) -> list[TransitionToInvestigate]:
    """Look at the candidate's single most recent role. If its category
    (BOH, Management, ... — Industry Extension-defined) is one of
    `role_config.transition_flags`, this is worth an interview question —
    never automatic rejection (task §9's own example: Cook applying for
    Server). A role that could not be classified into the industry's own
    catalog at all (`role_category_fn` returns None while a
    `normalized_role` was still attempted) is treated as "NON_HOSPITALITY"
    when that category is configured — Selection Core does not otherwise
    know what "outside the industry" means for a given industry."""

    ordered = _ordered(work_history)
    if not ordered:
        return []
    most_recent = ordered[-1]
    category = role_category_fn(most_recent.normalized_role)
    if category is None and most_recent.normalized_role is None and "NON_HOSPITALITY" in role_config.transition_flags:
        category = "NON_HOSPITALITY"
    if category is None or category not in role_config.transition_flags:
        return []

    question = (
        f"Your recent experience has primarily been in {_display_category(category)}. "
        f"What is making you want to move into {role_config.target_role.replace('_', ' ').title()}?"
    )
    return [
        TransitionToInvestigate(
            from_category=category, to_role=role_config.target_role,
            from_title=most_recent.original_job_title, from_employer=most_recent.employer,
            suggested_question=question,
        )
    ]
