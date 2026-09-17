"""Information Quality (01 Domains/Shared Domains/Selection/
ResumeScreening/FlagsAndIndicators.md, "Information Quality").

Absence of evidence is not automatically negative evidence — these
Indicators exist so a sparse profile reads as *sparse*, not as equivalent to
"nothing relevant found."
"""

from __future__ import annotations

from dataclasses import dataclass

from .profile import CandidateCVProfile


def _state(pct: float) -> str:
    if pct >= 80:
        return "High"
    if pct >= 50:
        return "Moderate"
    return "Low"


@dataclass
class InformationQuality:
    completeness_pct: float
    date_precision_pct: float
    evidence_density_pct: float
    overall_confidence_pct: float

    @property
    def completeness_state(self) -> str:
        return _state(self.completeness_pct)

    @property
    def overall_state(self) -> str:
        return _state(self.overall_confidence_pct)


def compute_information_quality(profile: CandidateCVProfile) -> InformationQuality:
    candidate_fields = [profile.full_name, profile.email, profile.phone, profile.location, profile.target_role]
    candidate_completeness = sum(1 for f in candidate_fields if f) / len(candidate_fields)

    work_history = profile.work_history
    if work_history:
        history_completeness = sum(
            1 for r in work_history
            if r.employer and r.original_job_title and r.start_date
        ) / len(work_history)
        date_precision = sum(
            1 for r in work_history if r.start_date and (r.end_date or r.is_current)
        ) / len(work_history)
        evidence_density = sum(
            1 for r in work_history
            if (r.evidence_snippet and r.evidence_snippet.strip())
            or (r.achievements and r.achievements.strip())
        ) / len(work_history)
    else:
        history_completeness = 0.0
        date_precision = 0.0
        evidence_density = 0.0

    completeness_pct = round((candidate_completeness * 0.4 + history_completeness * 0.6) * 100, 1)
    date_precision_pct = round(date_precision * 100, 1)
    evidence_density_pct = round(evidence_density * 100, 1)
    overall_confidence_pct = round(
        (completeness_pct + date_precision_pct + evidence_density_pct) / 3, 1
    )

    return InformationQuality(
        completeness_pct=completeness_pct,
        date_precision_pct=date_precision_pct,
        evidence_density_pct=evidence_density_pct,
        overall_confidence_pct=overall_confidence_pct,
    )
