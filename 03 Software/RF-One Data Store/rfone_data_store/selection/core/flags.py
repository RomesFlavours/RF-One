"""Structured Flag model (01 Domains/Shared Domains/Selection/
ResumeScreening/FlagsAndIndicators.md, "Flags"). A Flag is never
automatically negative — it marks something worth the evaluator's
attention, positive, negative, or simply unresolved.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .experience_analysis import EmploymentGap, EmploymentOverlap, TenureStats, months_between
from .profile import WorkHistoryRecord
from .trajectory import TransitionToInvestigate, _display_category

SHORT_TENURE_PATTERN = "SHORT_TENURE_PATTERN"
EMPLOYMENT_GAP = "EMPLOYMENT_GAP"
DATE_OVERLAP = "DATE_OVERLAP"
ROLE_TRANSITION = "ROLE_TRANSITION"
TITLE_INCONSISTENCY = "TITLE_INCONSISTENCY"
MISSING_INFORMATION = "MISSING_INFORMATION"
CHRONOLOGY_QUESTION = "CHRONOLOGY_QUESTION"

INFO = "INFO"
REVIEW = "REVIEW"
VERIFY = "VERIFY"


@dataclass
class Flag:
    type: str
    attention_level: str
    evidence: str
    explanation: str
    confidence: str  # LOW | MEDIUM | HIGH
    suggested_question: str | None = None


def flag_short_tenure_pattern(work_history: list[WorkHistoryRecord], *, threshold_months: int = 6) -> Flag | None:
    """Three or more CONSECUTIVE jobs shorter than `threshold_months`
    (FlagsAndIndicators.md's own worked example)."""

    ordered = sorted((r for r in work_history if r.start_date is not None), key=lambda r: r.start_date)
    run = 0
    run_records: list[WorkHistoryRecord] = []
    for record in ordered:
        months = months_between(record.start_date, record.end_date if not record.is_current else None)
        if months is not None and months < threshold_months:
            run += 1
            run_records.append(record)
        else:
            run = 0
            run_records = []
        if run >= 3:
            employers = ", ".join(r.employer or "unknown employer" for r in run_records[-3:])
            return Flag(
                type=SHORT_TENURE_PATTERN, attention_level=REVIEW,
                evidence=f"{run} consecutive roles under {threshold_months} months: {employers}.",
                explanation="Multiple consecutive short tenures may indicate instability, a difficult "
                "job market, or unrelated personal circumstances — worth asking about directly.",
                confidence="HIGH",
                suggested_question="I noticed a few recent roles were fairly short. Can you walk me "
                "through what happened in each of those?",
            )
    return None


def flag_employment_gaps(gaps: list[EmploymentGap]) -> list[Flag]:
    flags = []
    for gap in gaps:
        flags.append(
            Flag(
                type=EMPLOYMENT_GAP, attention_level=REVIEW,
                evidence=f"{gap.gap_months}-month gap between {gap.after_employer or 'a previous role'} "
                f"and {gap.before_employer or 'the next role'}.",
                explanation="An unexplained gap is not evidence of anything by itself — it may be "
                "education, caregiving, travel, illness, or simply not documented on the résumé.",
                confidence="MEDIUM",
                suggested_question="Could you tell me what you were doing between these two roles?",
            )
        )
    return flags


def flag_date_overlaps(overlaps: list[EmploymentOverlap]) -> list[Flag]:
    flags = []
    for overlap in overlaps:
        flags.append(
            Flag(
                type=DATE_OVERLAP, attention_level=VERIFY,
                evidence=f"Overlapping dates between {overlap.employer_a or 'one role'} and "
                f"{overlap.employer_b or 'another role'}.",
                explanation="Could be legitimate concurrent employment (e.g. two part-time roles) or a "
                "date recorded imprecisely on the résumé — worth confirming which.",
                confidence="MEDIUM",
                suggested_question="I see two roles with overlapping dates — were you working both at "
                "the same time, or is one of the dates approximate?",
            )
        )
    return flags


def flag_role_transitions(
    transitions: list[TransitionToInvestigate],
    *,
    detail_type_fn: Callable[[str], str] | None = None,
) -> list[Flag]:
    """`detail_type_fn` lets an Industry Extension name a more specific Flag
    type (e.g. Restaurant's `BOH_TO_FOH`) without Selection Core needing to
    know it exists — see FlagsAndIndicators.md, "Initial types"."""

    flags = []
    for transition in transitions:
        flag_type = detail_type_fn(transition.from_category) if detail_type_fn else ROLE_TRANSITION
        flags.append(
            Flag(
                type=flag_type or ROLE_TRANSITION, attention_level=REVIEW,
                evidence=f"Most recent role: {transition.from_title or transition.from_category} "
                f"at {transition.from_employer or 'unknown employer'}.",
                explanation=f"Transition from {_display_category(transition.from_category)} into "
                f"{transition.to_role.replace('_', ' ').title()} — worth understanding the motivation. "
                "Motivation: Unknown.",
                confidence="HIGH",
                suggested_question=transition.suggested_question,
            )
        )
    return flags


def flag_title_inconsistencies(work_history: list[WorkHistoryRecord]) -> list[Flag]:
    flags = []
    for record in work_history:
        if record.original_job_title and not record.normalized_role:
            flags.append(
                Flag(
                    type=TITLE_INCONSISTENCY, attention_level=VERIFY,
                    evidence=f'Job title "{record.original_job_title}" at {record.employer or "unknown employer"} '
                    "did not match any known role.",
                    explanation="The title may use non-standard wording, belong to a different industry, or "
                    "the résumé may need clarification on actual responsibilities.",
                    confidence="LOW",
                    suggested_question=f'Can you tell me more about what your role as "{record.original_job_title}" '
                    "actually involved day to day?",
                )
            )
    return flags


def flag_missing_information(
    *, has_email: bool, has_phone: bool, work_history: list[WorkHistoryRecord],
) -> list[Flag]:
    flags = []
    if not has_email and not has_phone:
        flags.append(
            Flag(
                type=MISSING_INFORMATION, attention_level=VERIFY,
                evidence="No email or phone number found on the résumé.",
                explanation="Absence of evidence is not automatically negative evidence — but the "
                "evaluator cannot contact the candidate without it.",
                confidence="HIGH",
            )
        )
    for record in work_history:
        if record.start_date is None:
            flags.append(
                Flag(
                    type=MISSING_INFORMATION, attention_level=REVIEW,
                    evidence=f"No start date recorded for {record.employer or 'a listed role'}.",
                    explanation="A missing date limits how confidently this role can be placed in the "
                    "candidate's timeline — see Information Quality.",
                    confidence="MEDIUM",
                )
            )
    return flags


def flag_chronology_questions(work_history: list[WorkHistoryRecord]) -> list[Flag]:
    flags = []
    for record in work_history:
        if record.start_date and record.end_date and record.end_date < record.start_date:
            flags.append(
                Flag(
                    type=CHRONOLOGY_QUESTION, attention_level=VERIFY,
                    evidence=f"{record.employer or 'A role'}: end date precedes start date as parsed.",
                    explanation="Likely a parsing or résumé formatting issue rather than a real fact — "
                    "needs confirmation before the timeline can be trusted.",
                    confidence="LOW",
                    suggested_question=f"Could you confirm the dates you worked at {record.employer or 'this role'}?",
                )
            )
    return flags
