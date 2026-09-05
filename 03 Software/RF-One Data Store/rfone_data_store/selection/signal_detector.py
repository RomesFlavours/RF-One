"""Selection Signal detection engine (Task 3C). Turns one `SignalDefinition`
+ a `DetectionContext` (an Application's `CandidateCVProfile`, its person's
prior Applications, and — for FIT_EXPERIENCE signals — an existing Fit
Assessment summary) into zero or more `SignalEvidenceDraft`s. Dispatches by
`signal_definition.signal_subtype` to a small, representative set of
genuinely evidence-based detectors — not an exhaustive catalog (mirrors
Task 3B's `resume_evidence_matcher.py`: prove the model works with real
detection logic, not a placeholder).

Every detector here reasons about PROFESSIONAL FACTS ONLY — dates, role
families, certifications, explicit résumé text. None of them infer a
personal/protected explanation for an employment gap or a life event
(concept note §3B: "RF-One must NOT infer or use protected/personal
explanations for employment gaps."). None of them characterize the
candidate ("ambitious," "highly motivated") — only the underlying facts are
ever stated (concept note §4).

Stage permission (is `RESUME` even in the Signal's permitted stages?) is
checked in exactly one place — `signal_service.generate_resume_stage_signals()`
— never here, mirroring `resume_evidence_matcher.py`'s own boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .core import fit_assessment_model as fam
from .core.experience_analysis import months_between
from .core.profile import CandidateCVProfile


@dataclass
class SignalEvidenceDraft:
    source_type: str
    evidence_text: str
    evidence_classification: str
    evidence_relationship: str
    confidence: str
    source_reference: str
    explanation: str | None = None
    detected_pattern: str | None = None
    is_system_generated: bool = True


@dataclass
class DetectionContext:
    profile: CandidateCVProfile
    target_role_family: str | None = None
    target_normalized_role: str | None = None
    # This person's earlier Applications' (target_role, profile) pairs,
    # oldest first — empty for a first-time applicant.
    prior_target_roles_and_profiles: list[tuple[str | None, CandidateCVProfile]] = field(default_factory=list)
    # From `fit_assessment_service.get_summary()` for this Application's
    # candidate, or None if no Fit Assessment exists yet.
    fit_assessment_summary: dict | None = None
    restaurant_name: str | None = None


def _relevant_entries(work_history, target_role_family, target_normalized_role):
    if not (target_role_family or target_normalized_role):
        return []
    return [
        w for w in work_history
        if (target_role_family and w.role_family == target_role_family)
        or (target_normalized_role and w.normalized_role == target_normalized_role)
    ]


# ---------------------------------------------------------------------------
# READINESS / RECENCY (concept note §3B)
# ---------------------------------------------------------------------------

def _detect_recent_relevant_experience(context: DetectionContext) -> list[SignalEvidenceDraft]:
    relevant = _relevant_entries(context.profile.work_history, context.target_role_family, context.target_normalized_role)
    if not relevant:
        return []

    current = [w for w in relevant if w.is_current]
    if current:
        w = current[0]
        return [SignalEvidenceDraft(
            source_type=fam.RESUME_FACT,
            evidence_text=f"Currently working as {w.original_job_title or '(untitled role)'} at {w.employer or '(employer not stated)'}.",
            evidence_classification=fam.FACT, evidence_relationship=fam.SUPPORTS,
            confidence=fam.CONFIDENCE_HIGH, source_reference="work_history (is_current)",
        )]

    dated = [w for w in relevant if w.end_date is not None]
    if not dated:
        return []
    most_recent = max(dated, key=lambda w: w.end_date)
    months_since = months_between(most_recent.end_date, None)
    if months_since is not None and months_since <= 6:
        return [SignalEvidenceDraft(
            source_type=fam.RESUME_DERIVED_INFORMATION,
            evidence_text=f"Most recent relevant role ended {months_since} month(s) ago.",
            evidence_classification=fam.DERIVED_INFORMATION, evidence_relationship=fam.SUPPORTS,
            confidence=fam.CONFIDENCE_MEDIUM, source_reference="work_history (derived recency)",
        )]
    return []


def _detect_long_relevant_gap(context: DetectionContext, *, threshold_months: int = 24) -> list[SignalEvidenceDraft]:
    relevant = _relevant_entries(context.profile.work_history, context.target_role_family, context.target_normalized_role)
    if not relevant or any(w.is_current for w in relevant):
        return []
    dated = [w for w in relevant if w.end_date is not None]
    if not dated:
        return []
    most_recent = max(dated, key=lambda w: w.end_date)
    months_since = months_between(most_recent.end_date, None)
    if months_since is not None and months_since >= threshold_months:
        return [SignalEvidenceDraft(
            source_type=fam.RESUME_DERIVED_INFORMATION,
            evidence_text=f"No relevant operational experience in the previous {months_since} month(s).",
            evidence_classification=fam.DERIVED_INFORMATION, evidence_relationship=fam.SUPPORTS,
            confidence=fam.CONFIDENCE_MEDIUM, source_reference="work_history (derived gap)",
            explanation="A professional-fact observation only — no personal cause is inferred or stated.",
        )]
    return []


# ---------------------------------------------------------------------------
# MOTIVATION / PROFESSIONAL (concept note §3C.2, §4's own worked example)
# ---------------------------------------------------------------------------

def _entries_matching_role(work_history, target_normalized_role):
    """Strict match on the SPECIFIC target role code — deliberately NOT
    role-family (`_relevant_entries`'s broader match is right for
    "any relevant recent experience," but wrong here: Dishwasher and Line
    Cook share the same "Kitchen / BOH" family, yet moving from one to the
    other is exactly the progression this detector needs to recognize)."""

    if not target_normalized_role:
        return []
    return [w for w in work_history if w.normalized_role == target_normalized_role]


def _detect_progression_since_previous_application(context: DetectionContext) -> list[SignalEvidenceDraft]:
    if not context.prior_target_roles_and_profiles:
        return []

    earliest_target_role, earliest_profile = context.prior_target_roles_and_profiles[0]
    if earliest_target_role and context.target_normalized_role and earliest_target_role == context.target_normalized_role:
        return []  # applying for the same role again is not "progression"

    earliest_relevant = _entries_matching_role(earliest_profile.work_history, context.target_normalized_role)
    current_relevant = _entries_matching_role(context.profile.work_history, context.target_normalized_role)
    if current_relevant and not earliest_relevant:
        gained = current_relevant[0]
        return [SignalEvidenceDraft(
            source_type=fam.RESUME_DERIVED_INFORMATION,
            evidence_text=(
                f"Previous application target role: {earliest_target_role or '(unspecified)'}. Since then, "
                f"gained experience as {gained.original_job_title or '(untitled role)'} at "
                f"{gained.employer or '(employer not stated)'}. Current application target role: "
                f"{context.target_normalized_role or context.target_role_family or '(unspecified)'}."
            ),
            evidence_classification=fam.DERIVED_INFORMATION, evidence_relationship=fam.SUPPORTS,
            confidence=fam.CONFIDENCE_MEDIUM, source_reference="application history (derived progression)",
            detected_pattern=(
                f"Applied for {earliest_target_role or '(unspecified)'} previously; subsequently gained "
                f"{gained.original_job_title or 'new'} experience; now applies for a role aligned with that "
                "newly gained experience."
            ),
            explanation="Preserves only the underlying facts (prior target role, newly gained role, current "
                        "target role) — does not characterize the candidate.",
        )]
    return []


# ---------------------------------------------------------------------------
# MOTIVATION / PERSONAL (concept note §3C.1) — conservative: only the
# résumé's own self-descriptive text is ever considered, mirroring Task 3B's
# behavioral-Requirement conservatism exactly. Confidence is never HIGH.
# ---------------------------------------------------------------------------

_INTEREST_KEYWORDS = ("excited", "passion", "admire", "dream", "love working", "return to", "long time")


def _detect_explicit_interest_statement(context: DetectionContext) -> list[SignalEvidenceDraft]:
    text = " ".join(t for t in (context.profile.summary, context.profile.other_sections_text) if t)
    if not text:
        return []
    low = text.lower()
    matched_restaurant = bool(context.restaurant_name and context.restaurant_name.lower() in low)
    matched_keyword = next((k for k in _INTEREST_KEYWORDS if k in low), None)
    if not (matched_restaurant or matched_keyword):
        return []
    return [SignalEvidenceDraft(
        source_type=fam.RESUME_FACT, evidence_text=text[:400],
        evidence_classification=fam.FACT, evidence_relationship=fam.SUPPORTS,
        confidence=fam.CONFIDENCE_LOW, source_reference="profile.summary",
        explanation="A self-reported statement — kept at low confidence, never treated as proof of motivation.",
    )]


# ---------------------------------------------------------------------------
# FIT / EXPERIENCE (concept note §3A) — reuses Task 3B's Fit Assessment
# output directly, per the concept note's own suggestion.
# ---------------------------------------------------------------------------

def _detect_fit_assessment_strength(context: DetectionContext) -> list[SignalEvidenceDraft]:
    summary = context.fit_assessment_summary
    if not summary:
        return []
    counts = summary.get("counts", {})
    evidenced = counts.get("EVIDENCED", 0)
    assessed_total = sum(v for status, v in counts.items() if status != "NOT_ASSESSED_AT_THIS_STAGE")
    if assessed_total == 0:
        return []
    if evidenced >= 2 and evidenced / assessed_total >= 0.5:
        return [SignalEvidenceDraft(
            source_type=fam.RESUME_DERIVED_INFORMATION,
            evidence_text=f"{evidenced} of {assessed_total} assessed Requirements are EVIDENCED.",
            evidence_classification=fam.DERIVED_INFORMATION, evidence_relationship=fam.SUPPORTS,
            confidence=fam.CONFIDENCE_MEDIUM, source_reference="fit_assessment.summary",
        )]
    return []


SUBTYPE_DETECTORS = {
    "recent_relevant_experience": _detect_recent_relevant_experience,
    "long_relevant_gap": _detect_long_relevant_gap,
    "progression_since_previous_application": _detect_progression_since_previous_application,
    "explicit_interest_statement": _detect_explicit_interest_statement,
    "fit_assessment_strength": _detect_fit_assessment_strength,
}


def generate_signal_evidence(signal_definition, context: DetectionContext) -> list[SignalEvidenceDraft]:
    """Returns evidence drafts for one `SignalDefinition`, IF `RESUME` is
    among its `assessment_stages` and a detector exists for its
    `signal_subtype` — callers (`signal_service.py`) must check the stage
    permission themselves and set NOT_ASSESSED directly otherwise, exactly
    like `resume_evidence_matcher.generate_resume_evidence()`."""

    detector = SUBTYPE_DETECTORS.get(signal_definition.signal_subtype)
    if detector is None:
        return []
    return detector(context)
