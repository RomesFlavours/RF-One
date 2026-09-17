"""Initial Indicators (01 Domains/Shared Domains/Selection/
ResumeScreening/FlagsAndIndicators.md, "Indicators"). Separate, named
dimensions — never combined into one CV score. Each carries a raw value plus
a descriptive state where useful; no weighting between them is defined here.
"""

from __future__ import annotations

from dataclasses import dataclass

from .experience_analysis import ExperienceBreakdown, TenureStats
from .information_quality import InformationQuality
from .trajectory import INCREASE_IN_RESPONSIBILITY, PROMOTION, TrajectoryEvent


@dataclass
class Indicator:
    name: str
    raw_value: str
    state: str | None = None


def _months_label(months: int) -> str:
    return f"{months} month{'s' if months != 1 else ''}"


def _stability_state(tenure: TenureStats) -> str:
    if tenure.employer_count == 0:
        return "Unknown"
    short_ratio = (tenure.jobs_under_6_months / tenure.employer_count) if tenure.employer_count else 0
    if short_ratio >= 0.5:
        return "Weak"
    if short_ratio > 0 or tenure.average_tenure_months < 12:
        return "Moderate"
    return "Strong"


def compute_indicators(
    breakdown: ExperienceBreakdown,
    tenure: TenureStats,
    trajectory_events: list[TrajectoryEvent],
    information_quality: InformationQuality,
) -> list[Indicator]:
    progression_observed = any(e.type in (PROMOTION, INCREASE_IN_RESPONSIBILITY) for e in trajectory_events)

    return [
        Indicator("Direct Role Experience", _months_label(breakdown.direct_role_months)),
        Indicator("Relevant / Propedeutic Experience", _months_label(breakdown.relevant_propedeutic_months)),
        Indicator("Industry Experience", _months_label(breakdown.industry_months)),
        Indicator(
            "Stability",
            f"avg tenure {tenure.average_tenure_months} mo, {tenure.jobs_under_6_months} job(s) < 6mo",
            _stability_state(tenure),
        ),
        Indicator(
            "Career Progression",
            f"{sum(1 for e in trajectory_events if e.type in (PROMOTION, INCREASE_IN_RESPONSIBILITY))} "
            "upward move(s) detected",
            "Observed" if progression_observed else "Not observed",
        ),
        Indicator("Customer-Facing Exposure", _months_label(breakdown.customer_facing_months)),
        Indicator("Commercial Exposure", _months_label(breakdown.commercial_months)),
        Indicator("Supervisory Responsibility", _months_label(breakdown.supervisory_months)),
        Indicator(
            "Evidence Density", f"{information_quality.evidence_density_pct}%",
            None,
        ),
        Indicator(
            "Information Confidence", f"{information_quality.overall_confidence_pct}%",
            information_quality.overall_state,
        ),
    ]
