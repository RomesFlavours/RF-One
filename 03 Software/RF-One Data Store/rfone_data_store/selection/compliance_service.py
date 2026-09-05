"""Compliance / Rule Review service (Task 5F Part A). Reviews restaurant/
company-authored Selection configuration for potential compliance/quality
concerns — NEVER a legal determination (see `core/compliance_model.
DISCLAIMER`, which every surface using this module must show), and NEVER a
silent rewrite: a `ComplianceReview`/`ComplianceWarning` is purely
informational until a human records a `ComplianceDisposition` (task §5).

Deliberately generic across object types (task §1's "do NOT hard-code the
service only to one existing model"): `_OBJECT_TYPE_REGISTRY` maps a stable
type string to the live ORM class; `_extract_reviewable_text` reads only
COMMON, optionally-present attribute names, so adding a new reviewable type
is one registry entry, never a bespoke extractor.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from .core import compliance_model as cpm
from .core import primary_screening_model as psm

_OBJECT_TYPE_REGISTRY: dict[str, type] = {
    cpm.REQUIREMENT: m.Requirement,
    cpm.PRIMARY_SCREENING_CRITERION: m.PrimaryScreeningCriterion,
    cpm.SIGNAL_DEFINITION: m.SignalDefinition,
    cpm.REVIEW_PRIORITY_POLICY_RULE: m.ReviewPriorityPolicyRule,
    cpm.APPLICATION_QUESTION_DEFINITION: m.ApplicationQuestionDefinition,
    cpm.PHONE_INTERVIEW_QUESTION_DEFINITION: m.PhoneInterviewQuestionDefinition,
    cpm.ASSESSMENT_ITEM_DEFINITION: m.AssessmentItemDefinition,
    cpm.SELECTION_OUTCOME_DEFINITION: m.SelectionOutcomeDefinition,
    cpm.JOB_POSTING_VERSION: m.JobPostingVersion,
}

_COMMON_TEXT_ATTRS = (
    "name", "question_text", "title_or_question", "description", "category", "evaluation_guidance",
    "evidence_positive", "evidence_contrary", "evidence_insufficient", "notes", "title",
    "company_description", "branch_description", "role_summary", "responsibilities", "minimum_requirements",
    "preferred_experience", "candidate_flag_name", "candidate_flag_default_reason", "authority_label",
)

# Task §20/Part D — Criteria naming a deep behavioral/personality trait
# genuinely require later-stage evidence (Phone/In-Person) to assess
# reliably; flagging these when `evidence_sources_allowed` is restricted to
# only CV/Application-era sources is a SELECTION QUALITY warning, never a
# legal one.
_BEHAVIORAL_TRAIT_KEYWORDS = (
    "trainability", "coaching", "guest sensitivity", "social adaptability", "composure",
    "under pressure", "initiative", "not my table", "listening", "team mentality", "adaptability",
    "personality", "attitude under stress", "emotional intelligence",
)
_EARLY_STAGE_ONLY_SOURCES = {psm.RESUME_FACT, psm.RESUME_DERIVED_INFORMATION, psm.APPLICATION, psm.APPLICATION_HISTORY}

# Task §11 — phrases that treat an absence of information as an outcome,
# rather than as INSUFFICIENT_EVIDENCE.
_ABSENCE_INDICATORS = ("not mentioned", "not on the cv", "not on cv", "no mention", "absence of", "if not stated", "not listed")
_NEGATIVE_OUTCOME_INDICATORS = ("level 0", "= 0", "score 0", "counts as negative", "count as negative", "treat as fail", "treat as failing", "assume no", "assume none", "automatically reject", "automatic disqualif")

# Task §2 — keyword lists are illustrative, non-exhaustive triggers for a
# human-readable warning; matching is deliberately simple/transparent
# (never an AI judgment) and a match is never itself proof of a legal
# problem — see `cpm.DISCLAIMER`.
_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    cpm.AGE: ("must be young", "youthful", "young and energetic", "no older than", "under the age of", "recent graduate only"),
    cpm.APPEARANCE_BODY: ("attractive", "good looking", "good-looking", "handsome", "beautiful", "slim build", "must be thin", "physically attractive"),
    cpm.NATIONALITY_ETHNICITY_RACE: ("must be italian", "must be american", "must be mexican", "native english speaker only", "must be white", "must be of", "ethnicity", "must be a native"),
    cpm.SEX_GENDER: ("must be male", "must be female", "males only", "females only", "waitress only", "must be a woman", "must be a man"),
    cpm.RELIGION: ("must be christian", "must be catholic", "must be muslim", "must be jewish", "religious background", "must practice"),
    cpm.DISABILITY: ("no disabilities", "must not have a disability", "able-bodied only", "cannot have a medical condition"),
    cpm.FAMILY_MARITAL_PREGNANCY: ("must be single", "not pregnant", "no children", "must be married", "marital status", "family status", "cannot be pregnant", "are you married", "do you have children", "have children", "pregnant", "maternity leave", "paternity leave"),
    cpm.VAGUE_SUBJECTIVE: ("good vibe", "nice person", "fits our culture", "just a feeling", "the right type of person", "good energy"),
}


@dataclass
class _WarningDraft:
    category: str
    severity: str
    explanation: str
    suggested_rewrite: str | None


def get_object(session: Session, object_type: str, object_id: int):
    cpm.validate_object_type(object_type)
    model_cls = _OBJECT_TYPE_REGISTRY[object_type]
    return session.get(model_cls, object_id)


def _extract_reviewable_text(obj) -> str:
    parts: list[str] = []
    for attr in _COMMON_TEXT_ATTRS:
        value = getattr(obj, attr, None)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    level_descriptions = getattr(obj, "level_descriptions", None)
    if isinstance(level_descriptions, dict):
        parts.extend(str(v) for v in level_descriptions.values() if isinstance(v, str) and v.strip())
    reason_choices = getattr(obj, "reason_choices", None)
    if isinstance(reason_choices, list):
        parts.extend(str(v) for v in reason_choices if isinstance(v, str) and v.strip())
    return "\n".join(parts)


def _run_keyword_rules(text: str) -> list[_WarningDraft]:
    lowered = text.lower()
    drafts: list[_WarningDraft] = []
    for category, keywords in _CATEGORY_KEYWORDS.items():
        matched = [kw for kw in keywords if kw in lowered]
        if not matched:
            continue
        drafts.append(_WarningDraft(
            category=category, severity=cpm.HIGH_CONCERN,
            explanation=(
                f"Potential protected-characteristic issue: the text appears to reference "
                f"{category.replace('_', ' ').lower()} (matched: \"{matched[0]}\"). Consider whether this can "
                "instead be expressed as an objective, job-related requirement. Potential compliance concern — "
                "consider review before activation."
            ),
            suggested_rewrite=(
                f"Consider rephrasing around the specific, observable job duty or skill genuinely required for "
                "this role, rather than the personal characteristic referenced above."
            ),
        ))
    for keyword in _CATEGORY_KEYWORDS[cpm.VAGUE_SUBJECTIVE]:
        if keyword in lowered:
            drafts.append(_WarningDraft(
                category=cpm.VAGUE_SUBJECTIVE, severity=cpm.WARNING,
                explanation=(
                    f"Weak job relevance: \"{keyword}\" is a vague, subjective phrase that is difficult to "
                    "evaluate consistently or defend as job-related. Better framed as a job-related observable "
                    "behavior."
                ),
                suggested_rewrite="Consider rephrasing as a specific, observable behavior tied to a job duty.",
            ))
            break
    return drafts


def _run_stage_reliability_rule(text: str, obj) -> list[_WarningDraft]:
    evidence_sources_allowed = getattr(obj, "evidence_sources_allowed", None)
    if not isinstance(evidence_sources_allowed, list) or not evidence_sources_allowed:
        return []
    if not set(evidence_sources_allowed) <= _EARLY_STAGE_ONLY_SOURCES:
        return []
    lowered = text.lower()
    matched = [kw for kw in _BEHAVIORAL_TRAIT_KEYWORDS if kw in lowered]
    if not matched:
        return []
    return [_WarningDraft(
        category=cpm.STAGE_RELIABILITY, severity=cpm.WARNING,
        explanation=(
            f"Stage assessment reliability: this characteristic (\"{matched[0]}\") may be important, but the "
            "evidence sources currently allowed for it are limited to CV/Application-era facts, which are usually "
            "insufficient to assess it reliably. This is a Selection quality observation, not a legal warning."
        ),
        suggested_rewrite=(
            "Consider marking this NOT ASSESSABLE AT THIS STAGE (INSUFFICIENT EVIDENCE) here, and allowing a "
            "later-stage evidence source (Phone Interview, In-Person/Practical, or Consistency) once available."
        ),
    )]


def _run_missing_evidence_negative_rule(text: str) -> list[_WarningDraft]:
    lowered = text.lower()
    if not any(a in lowered for a in _ABSENCE_INDICATORS):
        return []
    if not any(n in lowered for n in _NEGATIVE_OUTCOME_INDICATORS):
        return []
    return [_WarningDraft(
        category=cpm.MISSING_EVIDENCE_AS_NEGATIVE, severity=cpm.HIGH_CONCERN,
        explanation=(
            "This configuration appears to treat the ABSENCE of information as a negative result. Missing "
            "evidence must never become negative evidence — absence of a statement is not evidence of absence."
        ),
        suggested_rewrite=(
            "Consider: \"No evidence available at this stage -> INSUFFICIENT EVIDENCE; assess later or request "
            "the missing information (e.g. via a Missing-Evidence Questionnaire).\""
        ),
    )]


def _run_rules(text: str, obj) -> list[_WarningDraft]:
    if not text.strip():
        return []
    return _run_keyword_rules(text) + _run_stage_reliability_rule(text, obj) + _run_missing_evidence_negative_rule(text)


# ---------------------------------------------------------------------------
# Review (task §6) — always a NEW, immutable row; never edits a prior one.
# ---------------------------------------------------------------------------

def review_object(session: Session, object_type: str, object_id: int) -> m.ComplianceReview:
    obj = get_object(session, object_type, object_id)
    if obj is None:
        raise ValueError(f"No {object_type} with id {object_id}")

    text = _extract_reviewable_text(obj)
    object_version = getattr(obj, "version", 1) or 1
    review = m.ComplianceReview(
        object_type=object_type, object_id=object_id, object_version=object_version, reviewed_text=text,
        engine_version=cpm.ENGINE_VERSION,
    )
    session.add(review)
    session.flush()

    for draft in _run_rules(text, obj):
        session.add(m.ComplianceWarning(
            review_id=review.id, category=draft.category, severity=draft.severity, explanation=draft.explanation,
            suggested_rewrite=draft.suggested_rewrite,
        ))
    session.flush()
    return review


def get_latest_review(session: Session, object_type: str, object_id: int) -> m.ComplianceReview | None:
    stmt = (
        select(m.ComplianceReview)
        .where(m.ComplianceReview.object_type == object_type, m.ComplianceReview.object_id == object_id)
        .order_by(m.ComplianceReview.id.desc())
    )
    return session.scalars(stmt).first()


def list_review_history(session: Session, object_type: str, object_id: int) -> list[m.ComplianceReview]:
    stmt = (
        select(m.ComplianceReview)
        .where(m.ComplianceReview.object_type == object_type, m.ComplianceReview.object_id == object_id)
        .order_by(m.ComplianceReview.id)
    )
    return list(session.scalars(stmt).all())


def list_all_reviews(session: Session) -> list[m.ComplianceReview]:
    return list(session.scalars(select(m.ComplianceReview).order_by(m.ComplianceReview.id.desc())).all())


# ---------------------------------------------------------------------------
# Human disposition (task §5/§6) — the only way a review is "acted on."
# ---------------------------------------------------------------------------

def _latest_disposition(session: Session, review_id: int) -> m.ComplianceDisposition | None:
    stmt = (
        select(m.ComplianceDisposition)
        .where(m.ComplianceDisposition.review_id == review_id)
        .order_by(m.ComplianceDisposition.id.desc())
    )
    return session.scalars(stmt).first()


def _has_high_concern(review: m.ComplianceReview) -> bool:
    return any(w.severity == cpm.HIGH_CONCERN for w in review.warnings)


def record_disposition(
    session: Session, review_id: int, *, action: str, performed_by: str | None, final_text: str | None = None,
    reason: str | None = None,
) -> m.ComplianceDisposition:
    """Task §5 — the human's own choice: ACCEPT_REWRITE/EDIT_MANUALLY/
    KEEP_ORIGINAL/DEACTIVATE/ACKNOWLEDGE_HIGH_CONCERN. A `reason` is
    mandatory for `ACKNOWLEDGE_HIGH_CONCERN` always, and for `KEEP_ORIGINAL`
    when the review carries a HIGH_CONCERN warning (task §8's "preserve...
    reason" applied to the one case where silence would be most risky)."""

    cpm.validate_disposition_action(action)
    review = session.get(m.ComplianceReview, review_id)
    if review is None:
        raise ValueError(f"No ComplianceReview with id {review_id}")

    if action == cpm.ACKNOWLEDGE_HIGH_CONCERN and not (reason and reason.strip()):
        raise ValueError("Acknowledging a HIGH CONCERN warning requires a reason.")
    if action == cpm.KEEP_ORIGINAL and _has_high_concern(review) and not (reason and reason.strip()):
        raise ValueError("Keeping the original text despite a HIGH CONCERN warning requires a reason.")

    disposition = m.ComplianceDisposition(
        review_id=review_id, action=action, final_text=final_text, performed_by=performed_by, reason=reason,
    )
    session.add(disposition)
    session.flush()
    return disposition


def list_dispositions(session: Session, review_id: int) -> list[m.ComplianceDisposition]:
    stmt = (
        select(m.ComplianceDisposition)
        .where(m.ComplianceDisposition.review_id == review_id)
        .order_by(m.ComplianceDisposition.id)
    )
    return list(session.scalars(stmt).all())


# ---------------------------------------------------------------------------
# Activation guard (task §8) — reused, minimal wiring; never a redesign of
# the global authority system. `assert_activation_allowed` is called by the
# small set of app.py routes that (re)activate a reviewed object; an object
# never reviewed at all is "NOT YET REVIEWED" (task §9) and is never blocked
# — no retroactive destructive behavior.
# ---------------------------------------------------------------------------

def assert_activation_allowed(session: Session, object_type: str, object_id: int) -> None:
    review = get_latest_review(session, object_type, object_id)
    if review is None or not _has_high_concern(review):
        return
    latest = _latest_disposition(session, review.id)
    if latest is not None and latest.action in cpm.ACTIVATION_RESOLVING_ACTIONS:
        return
    raise ValueError(
        "This rule has an unresolved HIGH CONCERN compliance warning and cannot be activated without an "
        "authorized human explicitly acknowledging it (with a reason)."
    )


def review_status_summary(session: Session, object_type: str, object_id: int) -> dict:
    """A small convenience for UI/audit surfaces: latest review, its
    warnings, its latest disposition, and whether activation is currently
    blocked — never a numeric score, always the same conversational
    severities the review itself carries."""

    review = get_latest_review(session, object_type, object_id)
    if review is None:
        return {"status": "NOT_YET_REVIEWED", "review": None, "warnings": [], "latest_disposition": None, "blocks_activation": False}
    latest_disposition = _latest_disposition(session, review.id)
    blocks = _has_high_concern(review) and not (latest_disposition and latest_disposition.action in cpm.ACTIVATION_RESOLVING_ACTIONS)
    return {
        "status": "REVIEWED", "review": review, "warnings": review.warnings, "latest_disposition": latest_disposition,
        "blocks_activation": blocks,
    }
