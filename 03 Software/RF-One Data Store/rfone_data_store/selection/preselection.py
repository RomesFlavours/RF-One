"""Preselection: filtering and side-by-side comparison of applications
(SELECTION_PRESELECTION_COMPARE_001).

Works on APPLICATIONS — each with its own target role, stage and outcome —
while keeping the candidate visible. Everything shown comes from what
already exists: the analysis for the application's target role, its
Indicators, Flags and declared coordination evidence, its current stage and
effective outcome. Nothing here scores, ranks, weighs or recommends.

"To be clarified" is never zero:

- direct / propedeutic months are UNKNOWN (None) when the application has no
  supported target role, when an experience of that kind has no usable
  dates (it would otherwise silently count as 0), or when a reading is
  uncertain (that experience might be of that kind);
- stability "Unknown" is to be clarified, not a category;
- no declared coordination evidence means "not documented in the CV".

Unknown values never satisfy a numeric or stability filter, unless the
operator explicitly asks to include data to be clarified.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from .. import models as m
from . import application_service as app_svc
from . import outcome_service as outcome_svc
from . import persistence
from .analysis import CandidateAnalysisView, analyze_candidate
from .core import flags as flags_mod
from .core.coordination_evidence import CATEGORY_LABELS, CoordinationEvidence
from .core.experience_analysis import months_between
from .core.role_model import ADJACENT, EQUIVALENT, PROPEDEUTIC, TARGET, classify_role
from .industry.restaurant import ROLE_CONFIGURATIONS

STABILITY_CATEGORIES = ("Strong", "Moderate", "Weak")  # the existing Indicator states
STABILITY_TO_CLARIFY = "Unknown"
NO_OUTCOME = "__none__"

COORDINATION_ANY = "any"
COORDINATION_NONE = "none"  # not documented in the CV

ISSUE_MISSING = "missing"
ISSUE_UNCERTAIN = "uncertain"
ISSUE_ANY = "any"

MIN_COMPARE = 2
MAX_COMPARE = 4


@dataclass
class ExperienceLine:
    title: str | None
    employer: str | None
    start: str | None
    end: str | None
    months: int | None
    category: str | None  # for the application's target role; None if unknown
    reading_uncertain: bool


@dataclass
class ApplicationSummary:
    application_id: int
    candidate_id: int
    person_id: int
    full_name: str
    target_role: str | None
    target_role_label: str | None
    direct_months: int | None  # None: to be clarified
    propedeutic_months: int | None  # None: to be clarified
    stability: str | None
    stability_detail: str
    coordination: list[CoordinationEvidence]
    missing_information: list[str]  # evidence texts of MISSING_INFORMATION / TITLE_INCONSISTENCY flags
    uncertain_readings: list[str]  # evidence texts of EXTRACTION_UNCERTAIN flags
    questions: list[str]
    stage: str | None
    outcome: str | None
    experiences: list[ExperienceLine] = field(default_factory=list)

    @property
    def coordination_categories(self) -> set[str]:
        return {e.category for e in self.coordination}


@dataclass
class PreselectionFilters:
    target_role: str | None = None
    stage: str | None = None
    outcome: str | None = None  # an outcome label, or NO_OUTCOME
    direct_min: int | None = None
    direct_max: int | None = None
    propedeutic_min: int | None = None
    propedeutic_max: int | None = None
    stability: tuple[str, ...] = ()
    coordination: str | None = None  # COORDINATION_ANY / COORDINATION_NONE / a category code
    issues: str | None = None  # ISSUE_MISSING / ISSUE_UNCERTAIN / ISSUE_ANY
    include_to_clarify: bool = False

    @property
    def active(self) -> bool:
        return any([
            self.target_role, self.stage, self.outcome, self.direct_min is not None, self.direct_max is not None,
            self.propedeutic_min is not None, self.propedeutic_max is not None, self.stability,
            self.coordination, self.issues, self.include_to_clarify,
        ])


def _role_months(view: CandidateAnalysisView, categories: set[str]) -> int | None:
    """Months of experience classified in `categories` for the target role,
    or None when that total cannot be known (see module docstring)."""

    if view.role_config is None:
        return None
    total = 0
    for record in view.profile.work_history:
        if record.structure_confidence == "LOW":
            return None
        if classify_role(record.normalized_role, view.role_config) not in categories:
            continue
        months = months_between(record.start_date, record.end_date if not record.is_current else None)
        if months is None:
            return None
        total += months
    return total


def summarize_application(session: Session, application: m.Application) -> ApplicationSummary:
    candidate = application.candidate
    profile = persistence.to_profile(candidate)
    view = analyze_candidate(profile, target_role=application.target_role)
    stability = next(i for i in view.indicators if i.name == "Stability")

    experiences = []
    for record in profile.work_history:
        months = months_between(record.start_date, record.end_date if not record.is_current else None)
        experiences.append(ExperienceLine(
            title=record.original_job_title, employer=record.employer,
            start=record.start_date_text, end=record.end_date_text, months=months,
            category=classify_role(record.normalized_role, view.role_config) if view.role_config else None,
            reading_uncertain=record.structure_confidence == "LOW",
        ))

    missing = [f.evidence for f in view.flags
               if f.type in (flags_mod.MISSING_INFORMATION, flags_mod.TITLE_INCONSISTENCY)]
    uncertain = [f.evidence for f in view.flags if f.type == flags_mod.EXTRACTION_UNCERTAIN]
    questions = [f.suggested_question for f in view.flags if f.suggested_question] + view.coordination_questions

    return ApplicationSummary(
        application_id=application.id, candidate_id=candidate.id, person_id=application.person_id,
        full_name=candidate.full_name or "(name not extracted)",
        target_role=application.target_role, target_role_label=view.target_role_label,
        direct_months=_role_months(view, {TARGET, EQUIVALENT}),
        propedeutic_months=_role_months(view, {PROPEDEUTIC, ADJACENT}),
        stability=stability.state, stability_detail=stability.raw_value,
        coordination=view.coordination_evidence, missing_information=missing, uncertain_readings=uncertain,
        questions=list(dict.fromkeys(q for q in questions if q)),
        stage=application.current_stage,
        outcome=outcome_svc.get_effective_application_outcome(session, application.id).label,
        experiences=experiences,
    )


def _within(value: int | None, low: int | None, high: int | None, include_to_clarify: bool) -> bool:
    if low is None and high is None:
        return True
    if value is None:
        return include_to_clarify
    return (low is None or value >= low) and (high is None or value <= high)


def matches(summary: ApplicationSummary, f: PreselectionFilters) -> bool:
    if f.target_role and summary.target_role != f.target_role:
        return False
    if f.stage and summary.stage != f.stage:
        return False
    if f.outcome:
        if f.outcome == NO_OUTCOME:
            if summary.outcome:
                return False
        elif summary.outcome != f.outcome:
            return False
    if not _within(summary.direct_months, f.direct_min, f.direct_max, f.include_to_clarify):
        return False
    if not _within(summary.propedeutic_months, f.propedeutic_min, f.propedeutic_max, f.include_to_clarify):
        return False
    if f.stability:
        if summary.stability in STABILITY_CATEGORIES:
            if summary.stability not in f.stability:
                return False
        elif not f.include_to_clarify:
            return False
    if f.coordination:
        categories = summary.coordination_categories
        if f.coordination == COORDINATION_ANY and not categories:
            return False
        if f.coordination == COORDINATION_NONE and categories:
            return False
        if f.coordination in CATEGORY_LABELS and f.coordination not in categories:
            return False
    if f.issues:
        has_missing, has_uncertain = bool(summary.missing_information), bool(summary.uncertain_readings)
        if f.issues == ISSUE_MISSING and not has_missing:
            return False
        if f.issues == ISSUE_UNCERTAIN and not has_uncertain:
            return False
        if f.issues == ISSUE_ANY and not (has_missing or has_uncertain):
            return False
    return True


def filter_applications(summaries: list[ApplicationSummary], f: PreselectionFilters) -> list[ApplicationSummary]:
    return [s for s in summaries if matches(s, f)]


class ComparisonNotAllowed(ValueError):
    """The selected applications cannot be compared side by side."""


def comparison(session: Session, application_ids: list[int]) -> list[ApplicationSummary]:
    """2 to 4 applications for the SAME supported target role, in the order
    given. Raises ComparisonNotAllowed with a plain explanation otherwise."""

    ids = list(dict.fromkeys(application_ids))
    if not MIN_COMPARE <= len(ids) <= MAX_COMPARE:
        raise ComparisonNotAllowed(
            f"Select from {MIN_COMPARE} to {MAX_COMPARE} applications to compare (selected: {len(ids)}).")
    applications = [app_svc.get_application(session, i) for i in ids]
    if any(a is None for a in applications):
        raise ComparisonNotAllowed("One of the selected applications no longer exists.")
    roles = {a.target_role for a in applications}
    if None in roles or "" in roles:
        raise ComparisonNotAllowed(
            "An application without a target role cannot be compared: set its target role first, then choose "
            "applications for the same target role.")
    if len(roles) > 1:
        raise ComparisonNotAllowed(
            "Only applications for the same target role can be compared: choose applications for one target "
            "role.")
    if next(iter(roles)) not in ROLE_CONFIGURATIONS:
        raise ComparisonNotAllowed(
            "This target role is not supported by the screening: choose applications for Server or FOH Team "
            "Leader.")
    return [summarize_application(session, a) for a in applications]
