"""CandidateCVProfile — the structured, validated output every ResumeParser
must return (01 Domains/Shared Domains/Selection/ResumeScreening/
CandidateCVProfile.md).

Plain dataclasses, deliberately independent of the SQLAlchemy models in
`rfone_data_store.models` — a parser (real or demo) builds one of these
without knowing anything about persistence; `..persistence` maps it onto
`Candidate`/`CandidateEducation`/`CandidateWorkHistory` rows afterward. This
is what keeps a `ResumeParser` swappable and keeps `CandidateCVProfile`
never "tightly coupled to local files" (task §6).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class EducationRecord:
    institution: str | None = None
    program: str | None = None
    qualification: str | None = None
    field: str | None = None
    start_date: datetime | None = None  # Normalized (Task 2B) — see start_date_text for the original
    end_date: datetime | None = None
    completion_status: str | None = None  # "COMPLETED" | "IN_PROGRESS" | None (unknown)
    certifications: str | None = None
    notes: str | None = None

    # Task 2B — date normalization. `start_date_text`/`end_date_text` are the
    # résumé's own text, exactly as extracted (e.g. "2017", "Present");
    # `start_date`/`end_date` above are ALWAYS re-derived from these two
    # fields by `selection/normalization.py`, never hand-set elsewhere, so
    # normalization stays idempotent (same text in -> same date out, every
    # time). A record with no captured raw text (e.g. a pre-Task-2B legacy
    # candidate) is left with `start_date_precision`/`end_date_precision`
    # unset rather than guessed.
    start_date_text: str | None = None
    end_date_text: str | None = None
    start_date_precision: str | None = None  # "DAY" | "MONTH" | "YEAR" | "APPROXIMATE" | "UNKNOWN" | None
    end_date_precision: str | None = None
    date_normalization_confidence: str | None = None  # "HIGH" | "MEDIUM" | "LOW" | None


@dataclass
class CertificationRecord:
    name: str | None = None
    issuer: str | None = None
    date_text: str | None = None  # Exactly as written — no date normalization in Task 2A


@dataclass
class LanguageRecord:
    language: str | None = None
    proficiency: str | None = None  # Fact only if explicitly stated


@dataclass
class WorkHistoryRecord:
    employer: str | None = None
    location: str | None = None
    original_job_title: str | None = None  # Never overwritten by normalization — the authoritative Fact
    normalized_role: str | None = None  # Derived — catalog code, set by the Industry Extension (unchanged, Task 2A)
    start_date: datetime | None = None  # Normalized (Task 2B) — see start_date_text for the original
    end_date: datetime | None = None
    is_current: bool = False  # Normalized (Task 2B) — derived from end_date_text, see selection/normalization.py
    responsibilities: str | None = None
    achievements: str | None = None
    reason_for_leaving: str | None = None  # Fact only if explicitly stated — never inferred
    evidence_snippet: str | None = None

    # Task 2B — date normalization (see EducationRecord's matching fields for
    # the full rationale: `start_date`/`end_date`/`is_current` above are
    # always re-derived from these two raw-text fields, never hand-set).
    start_date_text: str | None = None
    end_date_text: str | None = None
    start_date_precision: str | None = None  # "DAY" | "MONTH" | "YEAR" | "APPROXIMATE" | "UNKNOWN" | None
    end_date_precision: str | None = None
    date_normalization_confidence: str | None = None  # "HIGH" | "MEDIUM" | "LOW" | None

    # Task 2B — role/title normalization. `original_job_title` above stays
    # untouched; these are always re-derived from it by
    # `selection/normalization.py`, never from each other or from
    # `normalized_role` — keeps re-normalization idempotent.
    normalized_title: str | None = None  # Human-readable canonical title(s), e.g. "Server / Bartender"
    role_family: str | None = None  # e.g. "FOH Service"; multiple joined with " / " for a multi-role title
    seniority_level: str | None = None  # Only when the TITLE TEXT itself evidences it — never from tenure
    multi_role: bool = False  # True when >1 catalog role was identified in one title
    title_normalization_confidence: str | None = None  # "HIGH" | "MEDIUM" | "LOW" | None


@dataclass
class CandidateCVProfile:
    """A parser's structured output for one résumé. `source`/`source_file`
    identify the originating ResumeSource/RawResume by reference — never a
    local filesystem path baked into the profile itself."""

    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    languages: str | None = None
    target_role: str | None = None
    declared_availability: str | None = None

    source: str | None = None  # e.g. "LOCAL_UPLOAD", "DEMO_FIXTURE"
    source_file: str | None = None
    source_provider: str | None = None  # e.g. "manual"; a future API source's provider name

    # Task 2A additions — Facts only, extracted as stated, never invented.
    summary: str | None = None  # Résumé's own summary/objective/profile text
    linkedin_url: str | None = None
    other_profile_url: str | None = None
    other_sections_text: str | None = None  # Raw text of useful-but-unmodeled sections (Awards, Projects, ...)

    education: list[EducationRecord] = field(default_factory=list)
    work_history: list[WorkHistoryRecord] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    certifications: list[CertificationRecord] = field(default_factory=list)
    languages_detail: list[LanguageRecord] = field(default_factory=list)

    # Contextual career/age information (ExperienceAndTrajectory.md) — kept
    # structurally separate from every field above that analysis.py turns
    # into an Indicator. `declared_age_context` is a Fact (candidate stated
    # it); `derived_age_context_*` is Derived, conservative, and optional.
    declared_age_context: str | None = None
    derived_age_context_range: str | None = None
    derived_age_context_rationale: str | None = None
    derived_age_context_confidence: str | None = None

    # Parser/AI boundary (task §18; Task 2A §11 removed the fabricated-fixture
    # DEMO fallback from the production import path — DEMO now only appears
    # on synthetic test fixtures constructed directly, never through
    # `parsing/resolve.py`) — never disguised.
    parsing_mode: str = "DEMO"  # "REAL_AI" | "RULE_BASED" | "DEMO"
    parser_provider: str | None = None
