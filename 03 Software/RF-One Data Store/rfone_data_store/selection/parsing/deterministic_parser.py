"""Rule-based résumé parser (Task 2A; date handling changed by Task 2B).
Real, evidence-based, deterministic structured extraction from a résumé's
actual extracted text — no AI call, no fixture, nothing invented. This is
the production fallback used whenever the real AI provider is unavailable
(`resolve.py`); it replaces the earlier fabricated-fixture `DemoResumeParser`
fallback, which Task 2A §2/§4/§7 forbids from the actual import flow
("never invent candidate information").

Approach: detect section headers (EXPERIENCE, EDUCATION, SKILLS,
CERTIFICATIONS, LANGUAGES, SUMMARY, and a few "preserve as-is" sections),
then apply targeted regex/heuristics within each section. Every extracted
field is a substring of, or a direct read from, the résumé's own text; a
field is left None whenever it cannot be confidently identified — this
parser never guesses a company name, a role title, or a date it did not
actually see (task §4/§7). Employment/education entries keep their raw
block text on `evidence_snippet`/kept implicitly via the section split, so
even an imperfect split is always traceable back to real résumé text.

Task 2B changed how dates leave this module: this parser only ever captures
the date text AS WRITTEN into `start_date_text`/`end_date_text` — it no
longer converts it into a `datetime` itself. `selection/normalization.py`
does that conversion (with precision/confidence) uniformly for every parser,
right after parsing, so there is one normalization implementation, not one
per parser.

Deliberately NOT attempted here (Task 2A §11 — later tasks):
- canonical role-title normalization (that's the Industry Extension, applied
  uniformly by `selection/normalization.py`, Task 2B);
- tenure/duration calculation;
- distinguishing responsibilities from achievements beyond an explicit
  "Achievement:"/"Award:" label in the text.
"""

from __future__ import annotations

import re

from ..core.parser_base import ResumeParser
from ..core.profile import (
    CandidateCVProfile, CertificationRecord, EducationRecord, LanguageRecord, WorkHistoryRecord,
)
from ..core.resume_source import RawResumeRef
from .flexible_dates import is_current_marker

# ---------------------------------------------------------------------------
# Section detection
# ---------------------------------------------------------------------------

_SECTION_SYNONYMS: dict[str, set[str]] = {
    "SUMMARY": {"summary", "professional summary", "objective", "career objective", "profile",
                "about me", "professional profile", "personal statement"},
    "EXPERIENCE": {"experience", "work experience", "employment history", "professional experience",
                   "work history", "relevant experience", "career history"},
    "EDUCATION": {"education", "academic background", "education and training", "educational background"},
    "SKILLS": {"skills", "technical skills", "core competencies", "key skills", "skills and abilities",
               "areas of expertise"},
    "CERTIFICATIONS": {"certifications", "certificates", "licenses", "licences",
                        "certifications and licenses", "certifications & licenses"},
    "LANGUAGES": {"languages", "language skills"},
    "AWARDS": {"awards", "honors", "honours", "awards and honors"},
    "VOLUNTEER": {"volunteer", "volunteering", "volunteer experience", "community service"},
    "PROJECTS": {"projects", "key projects"},
}
_HEADER_LOOKUP: dict[str, str] = {
    syn: section for section, synonyms in _SECTION_SYNONYMS.items() for syn in synonyms
}
_MODELED_SECTIONS = {"SUMMARY", "EXPERIENCE", "EDUCATION", "SKILLS", "CERTIFICATIONS", "LANGUAGES"}


def _normalize_header(line: str) -> str:
    return re.sub(r"[^a-z ]", "", line.lower()).strip()


def _find_sections(lines: list[str]) -> list[tuple[str, int, int]]:
    """Returns (section_name, content_start_idx, content_end_idx_exclusive)
    for every recognized header line — a header must be short (<=6 words)
    and match a known synonym exactly (never a substring match), so an
    ordinary sentence is never misread as a section header."""

    headers: list[tuple[str, int]] = []
    for i, line in enumerate(lines):
        stripped = line.strip().rstrip(":")
        if not stripped or len(stripped) > 45 or len(stripped.split()) > 6:
            continue
        section = _HEADER_LOOKUP.get(_normalize_header(stripped))
        if section:
            headers.append((section, i))

    spans = []
    for idx, (section, header_line_idx) in enumerate(headers):
        end = headers[idx + 1][1] if idx + 1 < len(headers) else len(lines)
        spans.append((section, header_line_idx + 1, end))
    return spans


# ---------------------------------------------------------------------------
# Contact / identity extraction (searched across the whole document)
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"(\+?\d[\d\-.\s()]{7,}\d)")
_LINKEDIN_RE = re.compile(r"(https?://)?(www\.)?linkedin\.com/\S+", re.IGNORECASE)
_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_LOCATION_RE = re.compile(r"\b[A-Z][A-Za-z.'\- ]{1,30},\s*[A-Z]{2}\b")


def _extract_contact(full_text: str, lines: list[str]) -> dict:
    email_match = _EMAIL_RE.search(full_text)
    phone_match = _PHONE_RE.search(full_text)
    linkedin_match = _LINKEDIN_RE.search(full_text)

    other_url = None
    for m in _URL_RE.finditer(full_text):
        if not linkedin_match or m.group(0) != linkedin_match.group(0):
            other_url = m.group(0).rstrip(").,")
            break

    full_name = None
    for line in lines[:3]:
        candidate = line.strip()
        if not candidate:
            continue
        words = candidate.split()
        if (
            "@" not in candidate and not _PHONE_RE.search(candidate)
            and 1 <= len(words) <= 5 and not _normalize_header(candidate) in _HEADER_LOOKUP
            and not any(ch.isdigit() for ch in candidate)
        ):
            full_name = candidate
        break  # only the very first non-blank line is ever considered the name

    location = None
    for line in lines[:6]:
        loc_match = _LOCATION_RE.search(line)
        if loc_match:
            location = loc_match.group(0)
            break

    return {
        "email": email_match.group(0) if email_match else None,
        "phone": phone_match.group(0).strip() if phone_match else None,
        "linkedin_url": linkedin_match.group(0) if linkedin_match else None,
        "other_profile_url": other_url,
        "full_name": full_name,
        "location": location,
    }


# ---------------------------------------------------------------------------
# EXPERIENCE / EDUCATION entry splitting
# ---------------------------------------------------------------------------

_MONTH_ALT = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?"
_DATE_TOKEN = rf"(?:{_MONTH_ALT}\s+\d{{4}}|\d{{1,2}}/\d{{4}}|\d{{4}})"
_DATE_RANGE_RE = re.compile(
    rf"(?P<start>{_DATE_TOKEN})\s*(?:-|–|—|to)\s*(?P<end>{_DATE_TOKEN}|Present|Current|Now|Ongoing)",
    re.IGNORECASE,
)


def _split_into_blocks(lines: list[str]) -> list[list[str]]:
    """Splits a section's lines into per-entry blocks. Prefers blank-line
    paragraph breaks (the common case for well-formatted résumés); falls
    back to splitting right before each date-range match when the whole
    section is one unbroken block with multiple date ranges in it. The
    fallback is a known, documented simplification — a title-only line
    immediately before a date range may end up attached to the previous
    entry instead of the one it introduces; `evidence_snippet` always keeps
    the real text either way, so nothing is fabricated, only imperfectly
    grouped."""

    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if line.strip() == "":
            if current:
                blocks.append(current)
                current = []
        else:
            current.append(line)
    if current:
        blocks.append(current)

    if len(blocks) > 1:
        return blocks

    flat = blocks[0] if blocks else []
    anchors = [i for i, l in enumerate(flat) if _DATE_RANGE_RE.search(l)]
    if len(anchors) <= 1:
        return blocks

    result = []
    for k, idx in enumerate(anchors):
        start = idx if k == 0 else max(idx, anchors[k - 1] + 1)
        end = anchors[k + 1] if k + 1 < len(anchors) else len(flat)
        segment = flat[start:end]
        if segment:
            result.append(segment)
    return result or blocks


def _parse_work_entry(block: list[str]) -> WorkHistoryRecord:
    non_blank = [l.strip() for l in block if l.strip()]
    evidence_snippet = " ".join(non_blank)[:600] or None

    date_line_idx = None
    date_match = None
    for i, line in enumerate(non_blank):
        m = _DATE_RANGE_RE.search(line)
        if m:
            date_line_idx, date_match = i, m
            break

    start_date_text = end_date_text = None
    if date_match:
        start_date_text = date_match.group("start")
        end_date_text = date_match.group("end")

    header_text = ""
    if date_line_idx is not None:
        remainder = (
            non_blank[date_line_idx][: date_match.start()] + non_blank[date_line_idx][date_match.end():]
        ).strip(" \t-–—,|()")
        if remainder:
            header_text = remainder
        elif date_line_idx > 0:
            header_text = non_blank[date_line_idx - 1]
    elif non_blank:
        header_text = non_blank[0]

    location = None
    loc_match = _LOCATION_RE.search(header_text) or (
        _LOCATION_RE.search(non_blank[date_line_idx]) if date_line_idx is not None else None
    )
    if loc_match:
        location = loc_match.group(0)
        header_text = header_text.replace(location, "").strip(" \t-–—,|()")

    original_job_title = employer = None
    for sep in (" at ", " – ", " — ", " - ", " | ", ","):
        if sep in header_text:
            left, right = header_text.split(sep, 1)
            left, right = left.strip(" \t-–—,|()"), right.strip(" \t-–—,|()")
            if left and right:
                original_job_title, employer = left, right
                break
    if original_job_title is None and header_text:
        original_job_title = header_text

    body_lines = [
        l for i, l in enumerate(non_blank)
        if i != date_line_idx and l != header_text and l not in (original_job_title, employer)
    ]
    body_lines = [re.sub(r"^[\-•\*·]\s*", "", l) for l in body_lines]

    achievements = None
    responsibilities_lines = []
    achievement_lines = []
    for line in body_lines:
        if re.match(r"^(achievement|award)s?\s*:", line, re.IGNORECASE):
            achievement_lines.append(re.sub(r"^(achievement|award)s?\s*:\s*", "", line, flags=re.IGNORECASE))
        else:
            responsibilities_lines.append(line)
    if achievement_lines:
        achievements = "\n".join(achievement_lines)
    responsibilities = "\n".join(responsibilities_lines) or None

    return WorkHistoryRecord(
        employer=employer, location=location, original_job_title=original_job_title,
        start_date_text=start_date_text, end_date_text=end_date_text,
        responsibilities=responsibilities, achievements=achievements,
        reason_for_leaving=None, evidence_snippet=evidence_snippet,
    )


_DEGREE_KEYWORDS = (
    # Deliberately excludes bare "school"/"high school" — those overlap with
    # institution names (e.g. "Orlando High School"); "diploma" is the
    # reliable signal for a high-school-diploma qualification line instead.
    "bachelor", "master", "associate", "diploma", "certificate", "phd", "doctorate", "mba",
    "b.a", "b.s",
)
_INSTITUTION_KEYWORDS = ("university", "college", "school", "institute", "academy", "polytechnic")
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def _classify_edu_line(line: str) -> tuple[bool, bool]:
    low = line.lower()
    return any(k in low for k in _DEGREE_KEYWORDS), any(k in low for k in _INSTITUTION_KEYWORDS)


def _parse_education_entry(block: list[str]) -> EducationRecord:
    non_blank = [l.strip() for l in block if l.strip()]

    date_match = None
    date_line_idx = None
    for i, line in enumerate(non_blank):
        m = _DATE_RANGE_RE.search(line)
        if m:
            date_match, date_line_idx = m, i
            break

    start_date_text = end_date_text = None
    completion_status = None
    if date_match:
        start_date_text = date_match.group("start")
        end_raw = date_match.group("end")
        if is_current_marker(end_raw):
            completion_status = "IN_PROGRESS"
        else:
            end_date_text = end_raw
    else:
        year_match = _YEAR_RE.search(" ".join(non_blank))
        if year_match:
            end_date_text = year_match.group(0)

    if completion_status is None:
        joined_lower = " ".join(non_blank).lower()
        if "in progress" in joined_lower or "expected" in joined_lower or "anticipated" in joined_lower:
            completion_status = "IN_PROGRESS"
        elif "completed" in joined_lower or "graduated" in joined_lower:
            completion_status = "COMPLETED"

    candidate_lines = [
        l for i, l in enumerate(non_blank) if i != date_line_idx
    ][:2]
    if date_line_idx is not None:
        remainder = (
            non_blank[date_line_idx][: date_match.start()] + non_blank[date_line_idx][date_match.end():]
        ).strip(" \t-–—,|()")
        if remainder:
            candidate_lines = ([remainder] + candidate_lines)[:2]

    qualification = institution = field = None
    for line in candidate_lines:
        is_degree, is_institution = _classify_edu_line(line)
        if is_degree and qualification is None:
            m = re.search(r"^(.*?)\s+in\s+(.+)$", line, re.IGNORECASE)
            if m:
                qualification, field = m.group(1).strip(" ,-–"), m.group(2).strip(" ,-–")
            else:
                qualification = line.strip(" ,-–")
        elif is_institution and institution is None:
            institution = line.strip(" ,-–")

    if qualification is None and institution is None and candidate_lines:
        institution = candidate_lines[0].strip(" ,-–")
        if len(candidate_lines) > 1:
            qualification = candidate_lines[1].strip(" ,-–")

    return EducationRecord(
        institution=institution, program=None, qualification=qualification, field=field,
        start_date_text=start_date_text, end_date_text=end_date_text, completion_status=completion_status,
        certifications=None, notes=None,
    )


# ---------------------------------------------------------------------------
# SKILLS / CERTIFICATIONS / LANGUAGES
# ---------------------------------------------------------------------------

_BULLET_RE = re.compile(r"^[\-•\*·]\s*")


def _parse_skills(lines: list[str]) -> list[str]:
    items: list[str] = []
    for line in lines:
        line = _BULLET_RE.sub("", line.strip())
        if not line:
            continue
        parts = re.split(r"[,;|·]+", line) if re.search(r"[,;|·]", line) else [line]
        items.extend(p.strip() for p in parts if p.strip())

    seen = set()
    deduped = []
    for item in items:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped


_CERT_DATE_RE = re.compile(rf"(?:^|[\s,\-|])({_MONTH_ALT}\s+)?((?:19|20)\d{{2}})", re.IGNORECASE)


def _parse_certifications(lines: list[str]) -> list[CertificationRecord]:
    records = []
    for raw_line in lines:
        line = _BULLET_RE.sub("", raw_line.strip())
        if not line:
            continue
        date_text = None
        m = _CERT_DATE_RE.search(line)
        if m:
            date_text = line[m.start():m.end()].strip(" ,-|")
            line = (line[: m.start()] + line[m.end():]).strip(" ,-|()")

        name, issuer = line, None
        for sep in (" - ", " – ", " | ", ","):
            if sep in line:
                left, right = line.split(sep, 1)
                left, right = left.strip(), right.strip()
                if left and right:
                    name, issuer = left, right
                break
        if name:
            records.append(CertificationRecord(name=name, issuer=issuer, date_text=date_text))
    return records


_LANG_ITEM_RE = re.compile(r"^(.*?)\s*[\(:\-]\s*([A-Za-z0-9/. ]+?)\)?$")


def _parse_languages(lines: list[str]) -> list[LanguageRecord]:
    joined = ", ".join(_BULLET_RE.sub("", l.strip()) for l in lines if l.strip())
    items = [p.strip() for p in re.split(r"[,;\n]+", joined) if p.strip()]

    records = []
    for item in items:
        m = _LANG_ITEM_RE.match(item)
        if m and m.group(1).strip():
            records.append(LanguageRecord(language=m.group(1).strip(), proficiency=m.group(2).strip()))
        else:
            records.append(LanguageRecord(language=item, proficiency=None))
    return records


# ---------------------------------------------------------------------------
# Parser entry point
# ---------------------------------------------------------------------------

class DeterministicResumeParser(ResumeParser):
    """The no-AI-provider-configured path. Always succeeds (never raises,
    never falls back further) — worst case, every field is None except
    `evidence_snippet`/`RawResume.raw_text`, which is never fabricated
    away."""

    def parse(self, raw_resume: RawResumeRef) -> CandidateCVProfile:
        raw_text = raw_resume.raw_text or ""
        lines = raw_text.splitlines()

        contact = _extract_contact(raw_text, lines)
        sections = _find_sections(lines)

        summary = None
        skills: list[str] = []
        certifications: list[CertificationRecord] = []
        languages_detail: list[LanguageRecord] = []
        work_history: list[WorkHistoryRecord] = []
        education: list[EducationRecord] = []
        other_blocks: list[str] = []

        for section, start, end in sections:
            content_lines = lines[start:end]
            if section == "SUMMARY" and summary is None:
                text = "\n".join(l.strip() for l in content_lines if l.strip())
                summary = text or None
            elif section == "EXPERIENCE":
                for block in _split_into_blocks(content_lines):
                    entry = _parse_work_entry(block)
                    if entry.original_job_title or entry.employer or entry.start_date_text or entry.evidence_snippet:
                        work_history.append(entry)
            elif section == "EDUCATION":
                for block in _split_into_blocks(content_lines):
                    entry = _parse_education_entry(block)
                    if entry.institution or entry.qualification or entry.start_date_text or entry.end_date_text:
                        education.append(entry)
            elif section == "SKILLS":
                skills.extend(_parse_skills(content_lines))
            elif section == "CERTIFICATIONS":
                certifications.extend(_parse_certifications(content_lines))
            elif section == "LANGUAGES":
                languages_detail.extend(_parse_languages(content_lines))
            elif section not in _MODELED_SECTIONS:
                text = "\n".join(l.strip() for l in content_lines if l.strip())
                if text:
                    other_blocks.append(f"{section.title()}:\n{text}")

        languages_flat = ", ".join(
            f"{r.language} ({r.proficiency})" if r.proficiency else r.language
            for r in languages_detail if r.language
        ) or None

        return CandidateCVProfile(
            full_name=contact["full_name"], email=contact["email"], phone=contact["phone"],
            location=contact["location"], languages=languages_flat,
            source_file=raw_resume.original_filename,
            summary=summary, linkedin_url=contact["linkedin_url"],
            other_profile_url=contact["other_profile_url"],
            other_sections_text="\n\n".join(other_blocks) or None,
            education=education, work_history=work_history,
            skills=skills, certifications=certifications, languages_detail=languages_detail,
            parsing_mode="RULE_BASED", parser_provider="deterministic",
        )
