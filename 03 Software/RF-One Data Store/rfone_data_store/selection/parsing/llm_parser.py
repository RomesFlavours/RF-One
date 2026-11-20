"""Real AI parsing provider (task §18). Only active when a provider is
actually configured (see `ai_client.py`) — this repository currently has no
`ANTHROPIC_API_KEY` configured anywhere (verified before implementation), so
this path is implemented but has not been exercised against a live API in
this environment; `resolve.py` falls back to `DeterministicResumeParser`
(Task 2A) when `AIProviderUnavailable` is raised, so an unset credential
never breaks the upload flow.

Task 2B: this parser asks the model for each date VERBATIM, exactly as
written on the résumé (not reformatted) — `start_date_text`/`end_date_text`
only. `selection/normalization.py` is the one place that turns that text
into a normalized date (with precision/confidence), the same as it does for
`DeterministicResumeParser`'s output, so both parsers go through identical
normalization logic rather than the AI silently doing its own.
"""

from __future__ import annotations

from ..core.parser_base import ProviderUnavailable, ResumeParser
from ..core.profile import (
    CandidateCVProfile, CertificationRecord, EducationRecord, LanguageRecord, WorkHistoryRecord,
)
from ..core.resume_source import RawResumeRef
from .ai_client import AIProviderUnavailable, generate_json

_PROMPT_TEMPLATE = """You are extracting structured information from a résumé for a human recruiter to review.

Rules:
- Extract ONLY what is explicitly stated. Do not invent, guess, or fill in missing information.
- "reason_for_leaving" must be null unless explicitly stated in the résumé text.
- "start_date_text"/"end_date_text" must be copied VERBATIM from the résumé text, exactly as written
  (e.g. "Jan 2021", "2019", "Present") — do NOT reformat, reinterpret, or normalize them yourself;
  use null only when no date is stated at all for that entry.
- For each work history entry, include a short verbatim "evidence_snippet" from the résumé text.
- "skills" is the list of skills exactly as stated — do not normalize, rate, or invent skills.
- "certifications" and "languages" are separate lists — only include an entry the résumé actually states.
- "other_sections_text" preserves useful sections not covered above (e.g. Awards, Volunteer work,
  Projects, hospitality-specific qualifications) as raw text grouped under their own heading; null if none.

Return ONLY valid JSON matching exactly this shape (no prose, no markdown fences):
{{
  "full_name": string|null, "email": string|null, "phone": string|null, "location": string|null,
  "languages": string|null, "declared_availability": string|null,
  "declared_age_context": string|null,
  "summary": string|null, "linkedin_url": string|null, "other_profile_url": string|null,
  "other_sections_text": string|null,
  "skills": [string, ...],
  "certifications": [{{"name": string|null, "issuer": string|null, "date_text": string|null}}],
  "language_details": [{{"language": string|null, "proficiency": string|null}}],
  "education": [{{"institution": string|null, "program": string|null, "qualification": string|null,
     "field": string|null, "start_date_text": string|null, "end_date_text": string|null,
     "completion_status": string|null, "certifications": string|null}}],
  "work_history": [{{"employer": string|null, "location": string|null, "original_job_title": string|null,
     "start_date_text": string|null, "end_date_text": string|null,
     "responsibilities": string|null, "achievements": string|null,
     "reason_for_leaving": string|null, "evidence_snippet": string|null}}]
}}

Résumé text:
---
{resume_text}
---
"""


class LLMResumeParser(ResumeParser):
    def parse(self, raw_resume: RawResumeRef) -> CandidateCVProfile:
        if not raw_resume.raw_text or not raw_resume.raw_text.strip():
            raise ProviderUnavailable("No extractable résumé text to send to the AI provider.")

        try:
            data = generate_json(_PROMPT_TEMPLATE.format(resume_text=raw_resume.raw_text))
        except AIProviderUnavailable as exc:
            raise ProviderUnavailable(str(exc)) from exc

        education = [
            EducationRecord(
                institution=e.get("institution"), program=e.get("program"),
                qualification=e.get("qualification"), field=e.get("field"),
                start_date_text=e.get("start_date_text"), end_date_text=e.get("end_date_text"),
                completion_status=e.get("completion_status"), certifications=e.get("certifications"),
            )
            for e in data.get("education", [])
        ]
        work_history = [
            WorkHistoryRecord(
                employer=w.get("employer"), location=w.get("location"),
                original_job_title=w.get("original_job_title"),
                start_date_text=w.get("start_date_text"), end_date_text=w.get("end_date_text"),
                responsibilities=w.get("responsibilities"), achievements=w.get("achievements"),
                reason_for_leaving=w.get("reason_for_leaving"), evidence_snippet=w.get("evidence_snippet"),
            )
            for w in data.get("work_history", [])
        ]

        certifications = [
            CertificationRecord(name=c.get("name"), issuer=c.get("issuer"), date_text=c.get("date_text"))
            for c in data.get("certifications", []) or []
            if c.get("name")
        ]
        languages_detail = [
            LanguageRecord(language=l.get("language"), proficiency=l.get("proficiency"))
            for l in data.get("language_details", []) or []
            if l.get("language")
        ]
        skills = [s for s in data.get("skills", []) or [] if s]

        return CandidateCVProfile(
            full_name=data.get("full_name"), email=data.get("email"), phone=data.get("phone"),
            location=data.get("location"), languages=data.get("languages"),
            declared_availability=data.get("declared_availability"),
            declared_age_context=data.get("declared_age_context"),
            source="LOCAL_UPLOAD", source_file=raw_resume.original_filename,
            summary=data.get("summary"), linkedin_url=data.get("linkedin_url"),
            other_profile_url=data.get("other_profile_url"),
            other_sections_text=data.get("other_sections_text"),
            education=education, work_history=work_history,
            skills=skills, certifications=certifications, languages_detail=languages_detail,
            parsing_mode="REAL_AI", parser_provider="anthropic",
        )
