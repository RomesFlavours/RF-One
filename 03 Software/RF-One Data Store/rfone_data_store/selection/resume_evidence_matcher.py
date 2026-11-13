"""Résumé-stage automatic evidence generation (Task 3B). Turns one
RequirementSnapshotItem + one CandidateCVProfile into zero or more
`EvidenceDraft`s — conservative, keyword-based, and deliberately unable to
conclude a behavioral/personality trait from résumé text alone (task §10:
"Do NOT automatically assess behavioral/personality characteristics from
weak proxies" — humility, teamwork, conflictual nature, counter-dependence,
accountability, coachability, customer empathy, emotional stability,
honesty, motivation, work ethic).

This is NOT restaurant-specific: every category/keyword rule here applies
regardless of which restaurant or template a Requirement came from. Rome's
Flavours' non-negotiable attitude traits are reached by the exact same
conservative `_match_behavioral` path as any other restaurant's behavioral
requirement — never a special case keyed on restaurant identity (task §25).

Stage permission (is `RESUME` even in the Requirement's assessment_stages?)
is deliberately NOT checked here — `fit_assessment_service.py` is the only
place that decision is made, so the stage boundary is enforced in exactly
one place (task §6).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .core import fit_assessment_model as fam
from .core.experience_analysis import current_roles, work_entry_duration_months
from .core.profile import CandidateCVProfile

_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "have", "from", "able", "work", "working", "role",
    "strong", "good", "well", "team", "some", "when", "what", "were", "been", "being", "into", "onto",
    "over", "years", "year", "months", "month", "experience", "required", "preferred", "must", "should",
    "will", "than", "your", "such", "each", "very", "also", "more", "most", "other",
}

# Behavioral/personality categories (task's own generic examples, §10) —
# conservative path only: self-description text, never job titles, tenure,
# responsibilities, or wording style.
_BEHAVIORAL_CATEGORIES = {
    "Attitude / Behavioral Traits", "Teamwork", "Trainability / Learning", "Accountability / Work Ethic",
}


@dataclass
class EvidenceDraft:
    source_type: str
    evidence_text: str
    evidence_classification: str
    evidence_relationship: str
    confidence: str
    source_reference: str
    explanation: str | None = None
    is_system_generated: bool = True


def _keywords(*texts: str | None) -> set[str]:
    words: set[str] = set()
    for text in texts:
        if not text:
            continue
        words.update(w for w in re.findall(r"[a-zA-Z]+", text.lower()) if len(w) >= 4 and w not in _STOPWORDS)
    return words


def _overlap(keywords: set[str], *candidate_texts: str | None) -> set[str]:
    if not keywords:
        return set()
    found: set[str] = set()
    for text in candidate_texts:
        if not text:
            continue
        low = text.lower()
        found.update(k for k in keywords if k in low)
    return found


def _match_behavioral(item, profile: CandidateCVProfile) -> list[EvidenceDraft]:
    """Only the résumé's own self-descriptive text (summary / other
    explicit sections) is even considered — never work-history
    responsibilities (those describe duties performed, not a self-attested
    trait), never titles, never tenure. A match here is capped at
    PARTIALLY_EVIDENCED (confidence is never HIGH — see
    `core.fit_assessment_model.compute_status_from_evidence`), because a
    résumé's self-description is inherently weak evidence for a behavioral
    trait even when literally present ("unusually explicit" is still just
    a self-report, not observed behavior)."""

    keywords = _keywords(item.name, item.description)
    matched = _overlap(keywords, profile.summary, profile.other_sections_text)
    if not matched:
        return []
    text = (profile.summary or profile.other_sections_text or "")[:400]
    return [
        EvidenceDraft(
            source_type=fam.RESUME_FACT, evidence_text=text,
            evidence_classification=fam.FACT, evidence_relationship=fam.SUPPORTS,
            confidence=fam.CONFIDENCE_LOW, source_reference="profile.summary",
            explanation=(
                f"Résumé self-description mentions: {', '.join(sorted(matched))}. A self-reported claim "
                "is weak evidence for a behavioral trait — kept at low confidence, never treated as "
                "confirmed."
            ),
        )
    ]


def _match_certifications(item, profile: CandidateCVProfile) -> list[EvidenceDraft]:
    keywords = _keywords(item.name, item.description)
    drafts = []
    for c in profile.certifications:
        if _overlap(keywords, c.name, c.issuer):
            drafts.append(EvidenceDraft(
                source_type=fam.RESUME_FACT, evidence_text=c.name + (f" ({c.issuer})" if c.issuer else ""),
                evidence_classification=fam.FACT, evidence_relationship=fam.SUPPORTS,
                confidence=fam.CONFIDENCE_HIGH, source_reference="certifications",
            ))
    for e in profile.education:
        if e.certifications and _overlap(keywords, e.certifications):
            drafts.append(EvidenceDraft(
                source_type=fam.RESUME_FACT, evidence_text=e.certifications,
                evidence_classification=fam.FACT, evidence_relationship=fam.SUPPORTS,
                confidence=fam.CONFIDENCE_HIGH, source_reference="education.certifications",
            ))
    return drafts


def _match_languages(item, profile: CandidateCVProfile) -> list[EvidenceDraft]:
    keywords = _keywords(item.name, item.description)
    drafts = []
    for lang in profile.languages_detail:
        if _overlap(keywords, lang.language):
            text = lang.language + (f" ({lang.proficiency})" if lang.proficiency else "")
            drafts.append(EvidenceDraft(
                source_type=fam.RESUME_FACT, evidence_text=text,
                evidence_classification=fam.FACT, evidence_relationship=fam.SUPPORTS,
                confidence=fam.CONFIDENCE_HIGH, source_reference="languages_detail",
            ))
    return drafts


def _match_skills(item, profile: CandidateCVProfile) -> list[EvidenceDraft]:
    keywords = _keywords(item.name, item.description)
    drafts = []
    for skill in profile.skills:
        if _overlap(keywords, skill):
            drafts.append(EvidenceDraft(
                source_type=fam.RESUME_FACT, evidence_text=skill,
                evidence_classification=fam.FACT, evidence_relationship=fam.SUPPORTS,
                confidence=fam.CONFIDENCE_HIGH, source_reference="skills",
            ))
    return drafts


def _match_education(item, profile: CandidateCVProfile) -> list[EvidenceDraft]:
    keywords = _keywords(item.name, item.description)
    drafts = []
    for e in profile.education:
        matched = _overlap(keywords, e.qualification, e.field, e.institution)
        if matched:
            text = " - ".join(v for v in (e.qualification, e.field, e.institution) if v)
            drafts.append(EvidenceDraft(
                source_type=fam.RESUME_FACT, evidence_text=text,
                evidence_classification=fam.FACT, evidence_relationship=fam.SUPPORTS,
                confidence=fam.CONFIDENCE_MEDIUM, source_reference="education",
            ))
    return drafts


def _match_availability(item, profile: CandidateCVProfile) -> list[EvidenceDraft]:
    if not profile.declared_availability:
        return []
    keywords = _keywords(item.name, item.description)
    if not _overlap(keywords, profile.declared_availability) and "availab" not in (item.name or "").lower():
        return []
    return [EvidenceDraft(
        source_type=fam.RESUME_FACT, evidence_text=profile.declared_availability,
        evidence_classification=fam.FACT, evidence_relationship=fam.SUPPORTS,
        confidence=fam.CONFIDENCE_HIGH, source_reference="declared_availability",
    )]


_DURATION_RE = re.compile(r"(\d+)\s*\+?\s*(year|month)")


def _match_work_history(item, profile: CandidateCVProfile) -> list[EvidenceDraft]:
    keywords = _keywords(item.name, item.description)
    if not keywords:
        return []

    drafts: list[EvidenceDraft] = []
    matched_indices: list[int] = []
    for idx, w in enumerate(profile.work_history):
        structured_matched = _overlap(
            keywords, w.original_job_title, w.normalized_title, w.role_family, w.seniority_level, w.employer,
        )
        free_text_matched = _overlap(keywords, w.responsibilities, w.achievements)
        if structured_matched:
            matched_indices.append(idx)
            drafts.append(EvidenceDraft(
                source_type=fam.RESUME_FACT,
                evidence_text=f"{w.original_job_title or '?'} at {w.employer or '?'}"
                              + (" (current)" if w.is_current else ""),
                evidence_classification=fam.FACT, evidence_relationship=fam.SUPPORTS,
                confidence=fam.CONFIDENCE_HIGH, source_reference=f"work_history[{idx}]",
                explanation=f"Matched on: {', '.join(sorted(structured_matched))}",
            ))
        elif free_text_matched:
            matched_indices.append(idx)
            drafts.append(EvidenceDraft(
                source_type=fam.RESUME_DERIVED_INFORMATION,
                evidence_text=(w.responsibilities or w.achievements or "")[:300],
                evidence_classification=fam.INFERENCE, evidence_relationship=fam.SUPPORTS,
                confidence=fam.CONFIDENCE_MEDIUM, source_reference=f"work_history[{idx}].responsibilities",
                explanation=f"Matched only in free-text description, not in the stated title/role: "
                            f"{', '.join(sorted(free_text_matched))}",
            ))

    # Duration/tenure — reuses Task 2B's existing duration calculation
    # (`work_entry_duration_months`) rather than reimplementing date math.
    name_and_desc = f"{item.name or ''} {item.description or ''}".lower()
    duration_match = _DURATION_RE.search(name_and_desc)
    if duration_match and matched_indices:
        matched_entries = [profile.work_history[i] for i in matched_indices]
        total_months = sum((work_entry_duration_months(w) or 0) for w in matched_entries)
        required_months = int(duration_match.group(1)) * (12 if duration_match.group(2) == "year" else 1)
        drafts.append(EvidenceDraft(
            source_type=fam.RESUME_DERIVED_INFORMATION,
            evidence_text=f"~{total_months} month(s) across matching role(s)",
            evidence_classification=fam.DERIVED_INFORMATION,
            evidence_relationship=fam.SUPPORTS if total_months >= required_months else fam.NEUTRAL,
            confidence=fam.CONFIDENCE_MEDIUM, source_reference="work_history (derived duration)",
            explanation=f"Calculated from start/end dates of the matching entries above; the "
                        f"Requirement's wording implies at least {required_months} month(s).",
        ))

    if "current" in name_and_desc:
        current_matches = [
            w for w in current_roles(profile.work_history)
            if _overlap(keywords, w.original_job_title, w.normalized_title, w.role_family)
        ]
        if current_matches:
            drafts.append(EvidenceDraft(
                source_type=fam.RESUME_FACT,
                evidence_text=f"Currently: {current_matches[0].original_job_title} at "
                              f"{current_matches[0].employer or '?'}",
                evidence_classification=fam.FACT, evidence_relationship=fam.SUPPORTS,
                confidence=fam.CONFIDENCE_HIGH, source_reference="work_history (is_current)",
            ))

    return drafts


_CATEGORY_MATCHERS: dict[str, list] = {
    "Attitude / Behavioral Traits": [_match_behavioral],
    "Teamwork": [_match_behavioral],
    "Trainability / Learning": [_match_behavioral],
    "Accountability / Work Ethic": [_match_behavioral],
    "Customer Orientation": [_match_behavioral, _match_work_history],
    "Experience": [_match_work_history],
    "Role Skills": [_match_work_history, _match_skills],
    "Technical Knowledge": [_match_skills, _match_work_history],
    "Sales": [_match_skills, _match_work_history],
    "Leadership / Management": [_match_work_history],
    "Communication": [_match_skills],
    "Availability / Practical Constraints": [_match_availability],
    "Certifications / Legal Requirements": [_match_certifications],
}
_DEFAULT_MATCHERS = [_match_skills, _match_work_history, _match_certifications, _match_education, _match_languages]


def generate_resume_evidence(item, profile: CandidateCVProfile) -> list[EvidenceDraft]:
    """Returns evidence drafts for one RequirementSnapshotItem. Callers
    must check `RESUME in item.assessment_stages` themselves before calling
    this — see the module docstring; this function does not re-check stage
    permission, keeping that boundary enforced in exactly one place."""

    matchers = _CATEGORY_MATCHERS.get(item.category, _DEFAULT_MATCHERS)
    drafts: list[EvidenceDraft] = []
    for matcher in matchers:
        drafts.extend(matcher(item, profile))

    # Different matchers can legitimately produce the same (source,text)
    # pair for one category (e.g. Role Skills runs both work-history and
    # skills matchers) — de-duplicate rather than double-count.
    seen: set[tuple[str, str]] = set()
    deduped: list[EvidenceDraft] = []
    for draft in drafts:
        key = (draft.source_reference, draft.evidence_text)
        if key not in seen:
            seen.add(key)
            deduped.append(draft)
    return deduped
