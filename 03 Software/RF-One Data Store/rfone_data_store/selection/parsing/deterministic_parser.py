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


def _split_into_blocks_by_blank_lines(lines: list[str]) -> list[list[str]]:
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
    return blocks


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

    blocks = _split_into_blocks_by_blank_lines(lines)
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


# SELECTION_CV_STRUCTURE_READING_001 — how sure the reader is that an
# experience's title, employer, dates and duties were grouped correctly.
# It is about the READING, never about the candidate: HIGH = an explicit clue
# fixed the grouping; MEDIUM = read with the parser's long-standing layout
# convention ("Title, Employer"), or a fact is simply absent; LOW = the
# grouping could not be determined, so the uncertain fields are left empty
# and a person has to check the original text (see `structure_note`).
STRUCTURE_HIGH = "HIGH"
STRUCTURE_MEDIUM = "MEDIUM"
STRUCTURE_LOW = "LOW"

_STRIP_CHARS = " \t-–—,|()"
_ENTRY_BULLET_RE = re.compile(r"^[\-•\*·]\s*")
_LOCATION_ONLY_RE = re.compile(rf"^\s*{_LOCATION_RE.pattern}\s*$")
# A title/employer line is short and is neither a bullet, a sentence nor a
# date line. At most two such lines introduce an entry (title, employer).
_MAX_HEADER_WORDS = 10
_MAX_HEADER_LINES = 2


def _is_header_like(line: str) -> bool:
    stripped = line.strip()
    return bool(
        stripped and not _ENTRY_BULLET_RE.match(stripped) and not stripped.endswith((".", ";", ":"))
        and len(stripped.split()) <= _MAX_HEADER_WORDS and not _DATE_RANGE_RE.search(stripped)
    )


def _date_line_remainder(line: str) -> str:
    match = _DATE_RANGE_RE.search(line)
    return (line[: match.start()] + line[match.end():]).strip(_STRIP_CHARS) if match else ""


def _split_experience_blocks(lines: list[str]) -> list[tuple[list[str], bool]]:
    """EXPERIENCE only: blank-line paragraphs, then every paragraph holding
    more than one date range is split again so that each date range starts
    its own entry. The (up to two) title/employer lines written just above a
    date line move with it, instead of staying at the end of the previous
    entry. Returns (block, boundaries_inferred) pairs."""

    result: list[tuple[list[str], bool]] = []
    for block in _split_into_blocks_by_blank_lines(lines):
        rows = [l for l in block if l.strip()]
        anchors = [i for i, l in enumerate(rows) if _DATE_RANGE_RE.search(l)]
        if len(anchors) <= 1:
            result.append((block, False))
            continue
        starts = [0]
        for k in range(1, len(anchors)):
            floor = anchors[k - 1] + 1
            start = anchors[k]
            while start - 1 >= floor and anchors[k] - (start - 1) <= _MAX_HEADER_LINES \
                    and _is_header_like(rows[start - 1]):
                start -= 1
            starts.append(start)
        for k, start in enumerate(starts):
            end = starts[k + 1] if k + 1 < len(starts) else len(rows)
            result.append((rows[start:end], True))
    return result


def _resolve_header(parts: list[str], employer_cues: set[int]) -> tuple[str | None, str | None, str, str | None]:
    """(title, employer, structure_confidence, structure_note) from the
    lines that introduce an entry. Never guesses: when nothing shows which
    line is the employer, both stay None and the note quotes the lines."""

    if not parts:
        return None, None, STRUCTURE_LOW, (
            "No job title or employer was found before the dates. Check the original text."
        )
    if len(parts) == 1:
        text = parts[0]
        for sep in (" at ", " @ "):
            if sep in text:
                left, right = (s.strip(_STRIP_CHARS) for s in text.split(sep, 1))
                if left and right:
                    return left, right, STRUCTURE_HIGH, None
        for sep in (" – ", " — ", " - ", " | ", ","):
            if sep in text:
                left, right = (s.strip(_STRIP_CHARS) for s in text.split(sep, 1))
                if left and right:
                    return left, right, STRUCTURE_MEDIUM, (
                        f'Read as "job title, employer" from "{text}".'
                    )
        return text, None, STRUCTURE_MEDIUM, "Only one line introduces this entry: read as the job title."
    if len(parts) == 2 and len(employer_cues) == 1:
        employer_idx = next(iter(employer_cues))
        return parts[1 - employer_idx], parts[employer_idx], STRUCTURE_HIGH, None
    quoted = " / ".join(f'"{p}"' for p in parts)
    return None, None, STRUCTURE_LOW, (
        f"Lines before the dates: {quoted}. It could not be determined which is the job title and "
        "which the employer, so neither was recorded. Check the original text."
    )


def _parse_work_entry(block: list[str], *, boundaries_inferred: bool = False) -> WorkHistoryRecord:
    non_blank = [l.strip() for l in block if l.strip()]
    evidence_snippet = " ".join(non_blank)[:600] or None

    date_lines = [i for i, line in enumerate(non_blank) if _DATE_RANGE_RE.search(line)]
    date_line_idx = date_lines[0] if date_lines else None
    date_match = _DATE_RANGE_RE.search(non_blank[date_line_idx]) if date_line_idx is not None else None

    start_date_text = end_date_text = None
    if date_match:
        start_date_text = date_match.group("start")
        end_date_text = date_match.group("end")

    # The lines that introduce the entry: everything above the date line
    # that is not a bullet, plus whatever shares the date line. With no date
    # line, only the first line (unchanged behaviour).
    if date_line_idx is not None:
        header_idx = [i for i in range(date_line_idx) if not _ENTRY_BULLET_RE.match(non_blank[i])]
        remainder = _date_line_remainder(non_blank[date_line_idx])
    else:
        header_idx = [0] if non_blank else []
        remainder = ""
    raw_parts = [non_blank[i] for i in header_idx] + ([remainder] if remainder else [])

    # Location: a "City, ST" line of its own belongs to the line above it; a
    # location written on a line marks that line as the employer's.
    location = None
    parts: list[str] = []
    employer_cues: set[int] = set()
    for text in raw_parts:
        if _LOCATION_ONLY_RE.match(text):
            location = location or text.strip()
            if parts:
                employer_cues.add(len(parts) - 1)
            continue
        loc_match = _LOCATION_RE.search(text)
        if loc_match:
            location = location or loc_match.group(0)
            text = text.replace(loc_match.group(0), "").strip(_STRIP_CHARS)
            if text:
                employer_cues.add(len(parts))
        if text:
            parts.append(text)
    if location is None and date_line_idx is not None:
        loc_match = _LOCATION_RE.search(non_blank[date_line_idx])
        location = loc_match.group(0) if loc_match else None

    original_job_title, employer, structure_confidence, structure_note = _resolve_header(parts, employer_cues)
    if date_line_idx is None:
        structure_confidence = STRUCTURE_MEDIUM if structure_confidence == STRUCTURE_HIGH else structure_confidence
        structure_note = " ".join(filter(None, [structure_note, "No dates were found for this entry."]))
    if len(date_lines) > 1:
        structure_confidence, original_job_title, employer = STRUCTURE_LOW, None, None
        structure_note = ("This entry contains more than one date range, so several experiences may have "
                          "been read as one. Check the original text.")
    elif boundaries_inferred and structure_confidence != STRUCTURE_LOW:
        structure_confidence = STRUCTURE_MEDIUM
        structure_note = " ".join(filter(None, [
            structure_note, "Entries are not separated by blank lines: this one was delimited by its dates."]))

    used = set(header_idx) | ({date_line_idx} if date_line_idx is not None else set())
    body_lines = [l for i, l in enumerate(non_blank) if i not in used]
    body_lines = [_ENTRY_BULLET_RE.sub("", l) for l in body_lines]

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
        structure_confidence=structure_confidence, structure_note=structure_note or None,
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
                for block, boundaries_inferred in _split_experience_blocks(content_lines):
                    entry = _parse_work_entry(block, boundaries_inferred=boundaries_inferred)
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
