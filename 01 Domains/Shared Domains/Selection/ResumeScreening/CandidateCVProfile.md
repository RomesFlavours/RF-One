# Candidate CV Profile

**Version:** 0.2
**Status:** Draft (initial canonical foundation)
**Domain:** Selection / Resume Screening
**Origin:** TASK_SELECTION_001; extended by TASK 2A (batch import + real résumé parser) with Summary,
Skills, Certifications, Languages and Other Sections.

---

## Purpose

This document defines the Resume Source pipeline and the shape of the `CandidateCVProfile` it produces — the structured, validated output every résumé parser (regardless of implementation or provider) must return. It does not define UI, persistence schema, or a specific parser's internals — see `03 Software/RF-One Data Store/rfone_data_store/selection/` for the current Runtime implementation.

---

## Resume Source architecture

Résumés are acquired manually today (local upload — PDF, DOCX or TXT) but must not be assumed to stay that way — a future integration (Indeed, another provider, an API/token-based feed) is a different `ResumeSource`, not a different pipeline:

```text
ResumeSource
  -> RawResume
    -> ResumeParser
      -> CandidateCVProfile
```

- **ResumeSource** — where a résumé came from (`LOCAL_UPLOAD` today; a future API source is a new value, not a new pipeline shape). Local upload (PDF, DOCX, TXT) supports importing multiple résumés in one batch; each résumé is still acquired, parsed and persisted as its own independent `RawResume` → `CandidateCVProfile`, so one résumé failing never affects any other in the same batch.
- **RawResume** — the acquired artifact plus, where available, its extracted raw text — before any structured interpretation. `CandidateCVProfile` is never tightly coupled to a local file: it references its originating `RawResume`, not a file path directly. A `RawResume` also carries a best-effort content hash used only for duplicate detection ("have we already imported this exact résumé for this restaurant?") — never for candidate identity resolution.
- **ResumeParser** — turns a `RawResume` into a `CandidateCVProfile`. Interchangeable and provider-independent (`18. PARSER / AI BOUNDARY` of the originating task; see the Runtime implementation's own parser-boundary docstring for the concrete abstraction).
- **CandidateCVProfile** — the structured, validated result this document defines below.

---

## CANDIDATE

| Field | Notes |
|---|---|
| `id` | Surrogate identity, assigned on persistence. |
| `full_name` | Fact. |
| `email` | Fact. |
| `phone` | Fact. |
| `location` | Fact. |
| `languages` | Fact, where stated. |
| `target_role` | The role the candidate is being screened for — Client/Role Configuration context, not necessarily a résumé Fact. |
| `source` | Which `ResumeSource` this candidate's résumé came from (e.g. `LOCAL_UPLOAD`) — always the true acquisition source, independent of which `ResumeParser` (real AI, or the real rule-based fallback when no AI provider is configured — Task 2A) ultimately produced the structured content. |
| `source_provider` | Who/what acquired the résumé within `source` — `manual` for today's local upload; a future API integration sets its own provider name here without changing this shape. |
| `source_file` | Reference to the originating `RawResume`/upload, where applicable — never the only way to identify the candidate. |
| `created_at` | When this profile was produced — also this candidate's import timestamp. |
| `declared_availability` | Fact, only if explicitly stated. |
| `summary` | Fact — the résumé's own summary/objective/profile text, only when the résumé carries an explicit such section; never generated on the candidate's behalf. |
| `linkedin_url` | Fact, where a LinkedIn profile URL is explicitly present. |
| `other_profile_url` | Fact, where another professional profile URL (portfolio, GitHub, etc.) is explicitly present. |
| `other_sections_text` | Fact — raw text of résumé sections that are useful but not individually modeled below (e.g. Awards, Volunteer work, Projects, hospitality-specific qualifications), preserved verbatim under their own heading rather than discarded. |

---

## EDUCATION

One record per education entry:

| Field | Notes |
|---|---|
| `institution` | Fact. |
| `program` | Fact. |
| `qualification` / `degree` | Fact. |
| `field` | Fact. |
| `start_date` / `end_date` | Fact, where stated — see [ExperienceAndTrajectory.md](ExperienceAndTrajectory.md), "Date precision," for how partial dates are handled. |
| `completion_status` | Fact where explicit (e.g. "in progress"); otherwise `UNKNOWN`, never assumed complete. |
| `certifications` | Fact. |
| `relevant professional education` | Fact — any non-degree professional education/training explicitly listed. |

---

## WORK HISTORY

One record per employment:

| Field | Notes |
|---|---|
| `employer` | Fact. Preserved only as a Fact — see `README.md`, "Organization Intelligence — OPEN / TBD." |
| `location` | Fact. |
| `original job title` | Fact — exactly as the résumé states it. |
| `normalized role` | Derived — mapped to a Role Model code (`RoleModel.md`) by the applicable Industry Extension; never overwrites `original job title`. |
| `start_date` / `end_date` | Fact, where stated. |
| `duration in months` | Derived — see [ExperienceAndTrajectory.md](ExperienceAndTrajectory.md). Never persisted as if it were a Fact; always recomputed from the two dates. |
| `current job (yes/no)` | Fact, where the résumé makes it explicit (e.g. "Present"); otherwise Unknown, never assumed. |
| `responsibilities` | Fact. |
| `achievements` | Fact. |
| `reason for leaving` | Fact, only if explicitly stated — never inferred (see [ExperienceAndTrajectory.md](ExperienceAndTrajectory.md), "Do not infer motive"). |
| `evidence snippets` | The résumé text this record was built from, preserved whenever practical so the UI can show provenance (`EvidenceModel.md`). |

---

## SKILLS

A list of skills, exactly as stated on the résumé — no inferred, normalized, or rated skills (rating/scoring skills is not part of Task 2A):

| Field | Notes |
|---|---|
| `skill` | Fact — one stated skill/competency. |

---

## CERTIFICATIONS / LICENSES

One record per certification or license explicitly stated, kept separate from `EDUCATION.certifications` (a free-text Fact on an education record) so a certification standing on its own — not tied to a specific institution/program — is not lost:

| Field | Notes |
|---|---|
| `name` | Fact — certification/license name. |
| `issuer` | Fact, where stated. |
| `date_text` | Fact, exactly as written (e.g. "2022", "March 2021") — no normalization in Task 2A. |

---

## LANGUAGES

One record per language explicitly stated (distinct from the coarser `CANDIDATE.languages` free-text Fact, which remains the single-string summary a parser may also populate):

| Field | Notes |
|---|---|
| `language` | Fact. |
| `proficiency` | Fact, only where explicitly stated (e.g. "Fluent", "Native", "B2"). |

---

## Contextual career/age information

Kept structurally separate from the Candidate/Education/Work-History Facts above — see [ExperienceAndTrajectory.md](ExperienceAndTrajectory.md), "Contextual career / age information," for the full rules. In short: only ever declared (Fact) or conservatively derived from a clearly dated record (Derived, labeled with confidence), always excluded from Indicators and rankings, always labeled context-only.

---

## Validation contract

A `ResumeParser` implementation must return a `CandidateCVProfile` matching the shape above — every field individually optional (a résumé may simply not state something), but the *shape* itself (which fields exist, which are lists of records vs. single values) fixed, so the rest of the Resume Engine (Experience Analysis, Trajectory, Flags, Indicators) never needs to know which parser or `ResumeSource` produced the profile it is reasoning about.
