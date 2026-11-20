"""Runtime/Product persistence for Resume Screening — maps a
`CandidateCVProfile` (core/profile.py) onto `RawResume`/`Candidate`/
`CandidateEducation`/`CandidateWorkHistory` rows (`.. models`) and back.
Only Facts are persisted; see `.. models`'s own module comment on the
Selection tables for why Derived Information/Flags/Indicators have no
schema here.

This module is Runtime orchestration, not Selection Core — it is the one
place allowed to import both `core` and SQLAlchemy models together.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from .core.profile import (
    CandidateCVProfile, CertificationRecord, EducationRecord, LanguageRecord, WorkHistoryRecord,
)
from .core.resume_source import RawResumeRef


def save_raw_resume(
    session: Session, *, restaurant_id: int | None, source_type: str,
    original_filename: str | None, storage_path: str | None, raw_text: str | None,
    content_hash: str | None = None,
) -> m.RawResume:
    raw = m.RawResume(
        restaurant_id=restaurant_id, source_type=source_type,
        original_filename=original_filename, storage_path=storage_path, raw_text=raw_text,
        content_hash=content_hash,
    )
    session.add(raw)
    session.flush()
    return raw


def find_raw_resume_by_hash(
    session: Session, *, restaurant_id: int | None, content_hash: str,
) -> m.RawResume | None:
    """Duplicate-detection lookup (TASK_SELECTION_002 §2) — scoped to one
    restaurant/client, since two different clients uploading the same
    résumé is not a duplicate in any meaningful sense."""

    stmt = select(m.RawResume).where(m.RawResume.content_hash == content_hash)
    if restaurant_id is not None:
        stmt = stmt.where(m.RawResume.restaurant_id == restaurant_id)
    return session.scalars(stmt).first()


def find_candidate_by_raw_resume_id(session: Session, raw_resume_id: int) -> m.Candidate | None:
    stmt = select(m.Candidate).where(m.Candidate.raw_resume_id == raw_resume_id)
    return session.scalars(stmt).first()


def raw_resume_ref(raw_resume: m.RawResume) -> RawResumeRef:
    return RawResumeRef(
        source_type=raw_resume.source_type, raw_text=raw_resume.raw_text,
        original_filename=raw_resume.original_filename,
    )


def save_candidate_profile(
    session: Session, profile: CandidateCVProfile, *, restaurant_id: int | None, raw_resume_id: int | None,
) -> m.Candidate:
    candidate = m.Candidate(
        restaurant_id=restaurant_id, raw_resume_id=raw_resume_id,
        full_name=profile.full_name, email=profile.email, phone=profile.phone,
        location=profile.location, languages=profile.languages, target_role=profile.target_role,
        declared_availability=profile.declared_availability,
        source=profile.source, source_file=profile.source_file, source_provider=profile.source_provider,
        parsing_mode=profile.parsing_mode, parser_provider=profile.parser_provider,
        declared_age_context=profile.declared_age_context,
        derived_age_context_range=profile.derived_age_context_range,
        derived_age_context_rationale=profile.derived_age_context_rationale,
        derived_age_context_confidence=profile.derived_age_context_confidence,
        summary=profile.summary, linkedin_url=profile.linkedin_url,
        other_profile_url=profile.other_profile_url, other_sections_text=profile.other_sections_text,
        status="NEW",
    )
    session.add(candidate)
    session.flush()

    for skill in profile.skills:
        if skill and skill.strip():
            session.add(m.CandidateSkill(candidate_id=candidate.id, skill=skill.strip()))
    for c in profile.certifications:
        if c.name and c.name.strip():
            session.add(
                m.CandidateCertification(
                    candidate_id=candidate.id, name=c.name.strip(), issuer=c.issuer, date_text=c.date_text,
                )
            )
    for lang in profile.languages_detail:
        if lang.language and lang.language.strip():
            session.add(
                m.CandidateLanguage(
                    candidate_id=candidate.id, language=lang.language.strip(), proficiency=lang.proficiency,
                )
            )

    for e in profile.education:
        session.add(
            m.CandidateEducation(
                candidate_id=candidate.id, institution=e.institution, program=e.program,
                qualification=e.qualification, field=e.field, start_date=e.start_date, end_date=e.end_date,
                completion_status=e.completion_status, certifications=e.certifications, notes=e.notes,
                start_date_text=e.start_date_text, end_date_text=e.end_date_text,
                start_date_precision=e.start_date_precision, end_date_precision=e.end_date_precision,
                date_normalization_confidence=e.date_normalization_confidence,
            )
        )
    for w in profile.work_history:
        session.add(
            m.CandidateWorkHistory(
                candidate_id=candidate.id, employer=w.employer, location=w.location,
                original_job_title=w.original_job_title, normalized_role=w.normalized_role,
                start_date=w.start_date, end_date=w.end_date, is_current=w.is_current,
                responsibilities=w.responsibilities, achievements=w.achievements,
                reason_for_leaving=w.reason_for_leaving, evidence_snippet=w.evidence_snippet,
                start_date_text=w.start_date_text, end_date_text=w.end_date_text,
                start_date_precision=w.start_date_precision, end_date_precision=w.end_date_precision,
                date_normalization_confidence=w.date_normalization_confidence,
                normalized_title=w.normalized_title, role_family=w.role_family,
                seniority_level=w.seniority_level, multi_role=w.multi_role,
                title_normalization_confidence=w.title_normalization_confidence,
            )
        )
    session.flush()
    return candidate


def list_candidates(session: Session, *, restaurant_id: int | None = None) -> list[m.Candidate]:
    stmt = select(m.Candidate).order_by(m.Candidate.created_at.desc())
    if restaurant_id is not None:
        stmt = stmt.where(m.Candidate.restaurant_id == restaurant_id)
    return list(session.scalars(stmt).all())


def get_candidate(session: Session, candidate_id: int) -> m.Candidate | None:
    return session.get(m.Candidate, candidate_id)


def to_profile(candidate: m.Candidate) -> CandidateCVProfile:
    """Reconstruct a CandidateCVProfile from persisted rows — used so the
    analysis engine (core/*) always works against the same shape regardless
    of whether it is reasoning about a just-parsed or a previously-saved
    candidate."""

    return CandidateCVProfile(
        full_name=candidate.full_name, email=candidate.email, phone=candidate.phone,
        location=candidate.location, languages=candidate.languages, target_role=candidate.target_role,
        declared_availability=candidate.declared_availability,
        source=candidate.source, source_file=candidate.source_file, source_provider=candidate.source_provider,
        declared_age_context=candidate.declared_age_context,
        derived_age_context_range=candidate.derived_age_context_range,
        derived_age_context_rationale=candidate.derived_age_context_rationale,
        derived_age_context_confidence=candidate.derived_age_context_confidence,
        parsing_mode=candidate.parsing_mode, parser_provider=candidate.parser_provider,
        summary=candidate.summary, linkedin_url=candidate.linkedin_url,
        other_profile_url=candidate.other_profile_url, other_sections_text=candidate.other_sections_text,
        skills=[s.skill for s in candidate.skills],
        certifications=[
            CertificationRecord(name=c.name, issuer=c.issuer, date_text=c.date_text)
            for c in candidate.certifications
        ],
        languages_detail=[
            LanguageRecord(language=lang.language, proficiency=lang.proficiency)
            for lang in candidate.language_records
        ],
        education=[
            EducationRecord(
                institution=e.institution, program=e.program, qualification=e.qualification,
                field=e.field, start_date=e.start_date, end_date=e.end_date,
                completion_status=e.completion_status, certifications=e.certifications, notes=e.notes,
                start_date_text=e.start_date_text, end_date_text=e.end_date_text,
                start_date_precision=e.start_date_precision, end_date_precision=e.end_date_precision,
                date_normalization_confidence=e.date_normalization_confidence,
            )
            for e in candidate.education
        ],
        work_history=[
            WorkHistoryRecord(
                employer=w.employer, location=w.location, original_job_title=w.original_job_title,
                normalized_role=w.normalized_role, start_date=w.start_date, end_date=w.end_date,
                is_current=w.is_current, responsibilities=w.responsibilities, achievements=w.achievements,
                reason_for_leaving=w.reason_for_leaving, evidence_snippet=w.evidence_snippet,
                start_date_text=w.start_date_text, end_date_text=w.end_date_text,
                start_date_precision=w.start_date_precision, end_date_precision=w.end_date_precision,
                date_normalization_confidence=w.date_normalization_confidence,
                normalized_title=w.normalized_title, role_family=w.role_family,
                seniority_level=w.seniority_level, multi_role=w.multi_role,
                title_normalization_confidence=w.title_normalization_confidence,
            )
            for w in candidate.work_history
        ],
    )
