# Selection Domain — Current Status Review

Read-only inspection of the actual current files (not task documents) as of this review.

## 1. Executive summary

Selection currently implements exactly one capability end-to-end: **Resume Screening** — batch résumé import (PDF/DOCX/TXT), real text extraction, real structured parsing (AI with a real rule-based fallback, never a fabricated fixture), date and role normalization, and evidence/indicator/flag presentation to a human evaluator. This is fully working and tested (46/46 + 19/19 targeted checks passing as of this review).

Everything **beyond** structuring and presenting résumé evidence — role/job-fit matching against a Requirement, scoring, phone interview, interview evaluation, shortlist, and a final Selection Decision — exists only as conceptual domain documentation (`01 Domains/Cross Domain/Selection/*.md`, all "Draft, initial canonical foundation"). None of it has corresponding code. The implementation stops cleanly at "structured, normalized candidate evidence, ready for a human to review" and does not cross into judging or deciding on the candidate.

## 2. Current end-to-end Selection flow

```
résumé file (PDF/DOCX/TXT)
  → text extraction              (text_extraction.py)
  → structured parsing           (LLMResumeParser or DeterministicResumeParser, resolve.py)
  → date + role normalization    (normalization.py)
  → candidate profile persisted  (persistence.py / models.py)
  → evidence + Derived/Flags/Indicators view (analysis.py, on every read)
  → [screening / matching / decision — NOT PRESENT]
```

Only the first five stages exist. There is no stage that consumes this profile to make or support a hiring decision.

## 3. Feature/status table

| Stage / Feature | Status | Principal files |
|---|---|---|
| Batch multi-file import (one action, per-file isolation) | **IMPLEMENTED** | `app.py` (`/upload`, `/api/upload`), `import_pipeline.py` |
| PDF text extraction | **IMPLEMENTED** | `parsing/text_extraction.py` (pdfplumber) |
| DOCX text extraction | **IMPLEMENTED** | `parsing/text_extraction.py` (python-docx) |
| TXT extraction | **IMPLEMENTED** | `parsing/text_extraction.py` |
| Unsupported/corrupt/empty file handling | **IMPLEMENTED** | `import_pipeline.py` ("no extractable text" → FAILED, never a fabricated result) |
| Real AI structured parsing | **IMPLEMENTED, but unexercised in this environment** — no `ANTHROPIC_API_KEY` and the `anthropic` package is not installed here, so this path is coded and prompt-complete but never actually runs; every real import currently falls through to the rule-based parser | `parsing/llm_parser.py`, `parsing/ai_client.py` |
| Real deterministic (rule-based) parsing fallback | **IMPLEMENTED** — this is the path actually exercised today | `parsing/deterministic_parser.py` |
| Old fixture-based "demo" parser | **PRESENT BUT UNUSED IN PRODUCTION** — kept only for direct synthetic-fixture testing of the analysis engine; not reachable from the import pipeline | `parsing/demo_parser.py`, `parsing/fixtures.py` |
| Candidate persistence (Candidate/Education/WorkHistory/Skill/Certification/Language) | **IMPLEMENTED** | `models.py`, `persistence.py` |
| Raw résumé text preservation (evidence) | **IMPLEMENTED** | `models.RawResume.raw_text`, shown on the candidate detail page |
| Duplicate detection (content-hash, per-restaurant) | **IMPLEMENTED** — exact/renamed-file duplicates only, not identity resolution | `parsing/dedup.py`, `import_pipeline.py` |
| COMPLETED / PARTIAL / FAILED / DUPLICATE batch statuses | **IMPLEMENTED** | `import_pipeline.py` |
| Employment history (multi-entry, employer/title/dates/responsibilities/achievements/evidence) | **IMPLEMENTED** | `core/profile.py` (`WorkHistoryRecord`), parsers |
| Education (multi-entry) | **IMPLEMENTED** | `core/profile.py` (`EducationRecord`), parsers |
| Skills | **IMPLEMENTED** (flat list, no rating) | `core/profile.py`, `models.CandidateSkill` |
| Certifications (standalone list) | **IMPLEMENTED** | `models.CandidateCertification` |
| Languages (list with proficiency) | **IMPLEMENTED** | `models.CandidateLanguage` |
| Summary / LinkedIn / other profile URL / other sections | **IMPLEMENTED** | `Candidate.summary/linkedin_url/other_profile_url/other_sections_text` |
| Date normalization (precision + confidence, current-role handling) | **IMPLEMENTED** | `normalization.py`, `parsing/flexible_dates.py` |
| Role/title normalization (canonical title, role family, multi-role, seniority) | **IMPLEMENTED** | `normalization.py`, `industry/restaurant.py` |
| Duration / chronological timeline / current-role(s) / overlap | **IMPLEMENTED** (computed on read, not stored) | `core/experience_analysis.py` |
| Candidate profile construction (CandidateCVProfile shape) | **IMPLEMENTED** | `core/profile.py` |
| Evidence-based screening surfacing (Flags, Indicators, Information Quality — no score) | **IMPLEMENTED** | `core/flags.py`, `core/indicators.py`, `core/information_quality.py`, `analysis.py` |
| Organization Intelligence (employer-quality reasoning) | **PLACEHOLDER — explicit, documented stub** (`NOT_IMPLEMENTED = True`) | `core/organization_intelligence.py` |
| Role/job-fit matching against a Requirement | **NOT IMPLEMENTED** — only a conceptual doc exists | `SelectionRequirement.md`, `FitAssessment.md` (docs only) |
| Trainable Gap assessment | **NOT IMPLEMENTED** — doc only | `TrainableGap.md` |
| Candidate scoring / ranking | **NOT IMPLEMENTED** — explicitly and repeatedly excluded by design ("no universal CV score"), tested against | — |
| Phone interview | **NOT IMPLEMENTED** | — |
| Interview evaluation | **NOT IMPLEMENTED** | — |
| Shortlist / Selection Decision | **NOT IMPLEMENTED** — doc only | `SelectionDecision.md` (doc only) |
| UI: candidate list + batch upload | **IMPLEMENTED** | `templates/home.html` |
| UI: candidate detail (facts, derived info, flags, indicators) | **IMPLEMENTED** | `templates/detail.html` |
| UI: screening/interview/decision screens | **NOT IMPLEMENTED** | — |

## 4. Most recent completed work (Task 2B — date + role normalization)

The most recent development pass added a normalization layer between parsing and persistence:

- Both parsers (AI and rule-based) now capture dates as **raw text only**; a new module (`normalization.py`) converts that text into normalized dates with an explicit **precision** (DAY/MONTH/YEAR/APPROXIMATE/UNKNOWN) and **confidence** (HIGH/MEDIUM/LOW), applied uniformly to whichever parser produced the profile.
- Current-role markers (Present/Current/Ongoing/Now) are handled consistently; unparseable dates stay null rather than guessed.
- Duration is exposed (not stored) via `work_entry_duration_months()`, with a documented convention for year-only dates.
- Role/title normalization was extended: new `normalized_title`, `role_family` (12 hospitality families), `seniority_level` (from title text only, never tenure), and `multi_role` support (e.g. "Server/Bartender" → two roles). The Restaurant catalog gained Assistant General Manager/GM/generic Manager codes.
- A `reprocess_candidate()` function lets an already-persisted candidate be re-normalized without re-uploading its résumé.
- One new Alembic migration (`f4d8e2a1c6b3`) added the supporting columns; all pre-existing data/behavior verified unaffected.

Immediately prior to that (Task 2A), the batch import pipeline itself was built: multi-file upload, real PDF/DOCX/TXT extraction, the deterministic parser replacing an earlier fixture-based fallback, COMPLETED/PARTIAL/FAILED/DUPLICATE statuses, and the fuller structured schema (skills/certifications/languages/summary/URLs/other sections).

## 5. Existing partial / placeholder components

- **Real AI parsing path** — fully coded (prompt, JSON mapping, provider abstraction) but not exercised in this environment: no API key configured, `anthropic` package not installed. Every current import goes through the rule-based fallback. Not "fake" — genuinely implemented, just currently unreachable here.
- **`demo_parser.py` / `fixtures.py`** — real code, but deliberately not wired into the production import path since Task 2A; used only by the direct synthetic-fixture tests of the analysis engine (`selection_validation.py`). Present in the codebase but not part of the active flow — worth knowing about so it isn't mistaken for live behavior.
- **`organization_intelligence.py`** — an explicit, documented empty extension point (`NOT_IMPLEMENTED = True`), not wired to anything.
- **Deterministic parser's structural heuristics** — block-splitting/employer-vs-title splitting are heuristic (documented limitations in the code itself); they degrade to `None`/lower confidence rather than fabricating, but are not 100% reliable on unusual résumé layouts.
- **Duplicate handling** — content-hash exact/renamed-file matching only; explicitly not candidate identity resolution (two résumés for the same person under different content are not detected as duplicates).

## 6. Current data model relevant to Selection

Tables (in the shared `rfone_data_store` schema, via `RawResume`/`Candidate` and children):

- `raw_resumes` — source_type, filename, storage_path, raw_text, content_hash, uploaded_at
- `candidates` — identity/contact facts, summary, linkedin_url, other_profile_url, other_sections_text, source/source_provider, parsing_mode/parser_provider, status, declared/derived age-context, timestamps
- `candidate_education` — institution/program/qualification/field, start/end date + `*_text`/`*_precision`, completion_status, certifications (free text), notes
- `candidate_work_history` — employer/location/original_job_title/normalized_role, start/end date + `*_text`/`*_precision`, is_current, responsibilities/achievements/reason_for_leaving/evidence_snippet, `date_normalization_confidence`, `normalized_title`/`role_family`/`seniority_level`/`multi_role`/`title_normalization_confidence`
- `candidate_skills`, `candidate_certifications`, `candidate_languages` — one-row-per-item child tables

No table exists for Requirement, Fit Assessment, Trainable Gap, Interview, or Selection Decision — those concepts have no schema.

## 7. Current UI/API entry points

Single Flask app, `03 Software/Selection/app.py`:

- `GET /` — candidate list, batch upload form (drag/drop, multi-file)
- `POST /upload` — classic multipart batch upload (no-JS fallback)
- `POST /api/upload` — one-file-per-call JSON endpoint used by the batch-upload JavaScript (live per-file progress)
- `GET /candidate/<id>` — candidate detail: Facts, Derived Information (experience breakdown, tenure, trajectory), Flags, Indicators

No route exists for anything past this (no requirement configuration, matching, interview, or decision screens).

## 8. Tests currently present and what they cover

- `03 Software/RF-One Data Store/test_selection_engine.py` → `rfone_data_store/selection_validation.py`: 46 checks — batch import/duplicate/isolation, experience/tenure/trajectory calculations, Restaurant title normalization, three synthetic-fixture candidate scenarios (flags/indicators), persistence round-trips, and 18 Task 2B checks (date formats, current-role synonyms, duration, overlap, role normalization incl. AGM/GM/multi-role/seniority, idempotency, live-pipeline normalization, reprocessing an existing candidate). **All 46 passing** as verified in this review.
- `03 Software/Selection/test_batch_upload.py`: 19 checks, end-to-end through the real Flask app with real TXT/DOCX fixtures — batch upload, unsupported/corrupt-file handling, PARTIAL/FAILED/DUPLICATE outcomes, and (new) confirmation that a live import receives normalized dates/roles. **All 19 passing**.
- No tests exist for anything beyond structured/normalized candidate data, since nothing beyond it is implemented.

## 9. Concrete unfinished frontier

The implementation is complete and consistent up through: **a normalized, evidence-preserving `CandidateCVProfile`, persisted and displayed with Facts / Derived Information / Flags / Indicators.**

The first point where implementation stops is immediately after that: nothing consumes a candidate's normalized profile against a **Role/Client Requirement** to produce a Fit Assessment. `SelectionRequirement.md` and `FitAssessment.md` define the concept (what must be evaluated, how evidence maps to a requirement, the "Selection looks for the right raw material" philosophy) but there is no code representing a Requirement, no matching logic, and no UI to configure or view one. This is the first genuine gap between what is documented and what runs.

---

**Recommended restart point:** Role/Client Requirement matching and Fit Assessment (turning a normalized candidate profile plus a configured Role Requirement into a structured Fit Assessment — still no scoring/ranking/decision).
