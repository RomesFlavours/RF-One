"""Contextual career/age information (01 Domains/Shared Domains/Personnel Management/
Selection/ResumeScreening/ExperienceAndTrajectory.md, "Contextual career /
age information"). Deliberately conservative: only ever declared, or derived
from a CLEARLY dated high-school-completion record. Never forced from weak
evidence such as an ambiguous university date. The result of this module
must never be read by `core/indicators.py` — it is context-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .profile import CandidateCVProfile

TYPICAL_HIGH_SCHOOL_GRADUATION_AGE_LOW = 17
TYPICAL_HIGH_SCHOOL_GRADUATION_AGE_HIGH = 19


@dataclass
class DerivedAgeContext:
    range: str
    rationale: str
    confidence: str  # always "LOW" — this is an estimate, never treated as fact


def derive_age_context_from_education(profile: CandidateCVProfile) -> DerivedAgeContext | None:
    """Only fires on an explicit, clearly dated high-school completion
    record — never on an ambiguous university date (task §12)."""

    if profile.declared_age_context:
        return None  # a declared value already covers this; do not also derive one

    hs_records = [
        e for e in profile.education
        if e.qualification and "high school" in e.qualification.lower() and e.end_date is not None
    ]
    if not hs_records:
        return None

    graduation = min(hs_records, key=lambda e: e.end_date).end_date
    current_year = datetime.now().year
    years_since = current_year - graduation.year
    low = years_since + TYPICAL_HIGH_SCHOOL_GRADUATION_AGE_LOW
    high = years_since + TYPICAL_HIGH_SCHOOL_GRADUATION_AGE_HIGH

    return DerivedAgeContext(
        range=f"{low}-{high}",
        rationale=(
            f"Derived from a dated high school completion record ({graduation.year}), assuming a "
            f"typical graduation age of {TYPICAL_HIGH_SCHOOL_GRADUATION_AGE_LOW}-"
            f"{TYPICAL_HIGH_SCHOOL_GRADUATION_AGE_HIGH}. An estimate, not a fact."
        ),
        confidence="LOW",
    )
