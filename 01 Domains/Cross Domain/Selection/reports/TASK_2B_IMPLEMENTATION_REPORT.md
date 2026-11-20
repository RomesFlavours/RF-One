# TASK 2B — Date + Role Normalization: Implementation Report

## 1. What I implemented

A normalization layer that sits between Task 2A's structured parsing and persistence: `resume file → text extraction → structured parsing → DATE + ROLE NORMALIZATION → persisted candidate profile`. Both parsers (`DeterministicResumeParser` and `LLMResumeParser`) now capture dates as raw text only (`start_date_text`/`end_date_text`, exactly as written); a single new module, `selection/normalization.py`, converts that text (plus `original_job_title`) into normalized, machine-usable dates and roles, applied uniformly regardless of which parser produced the profile. The original values are never overwritten — only new fields were added alongside them. A reprocessing function lets already-persisted candidates be normalized without re-uploading the résumé.

## 2. Main files changed

- New: `rfone_data_store/selection/normalization.py` (orchestration: `normalize_profile()`, `reprocess_candidate()`)
- New: migration `f4d8e2a1c6b3_add_selection_date_role_normalization.py`
- Extended: `parsing/flexible_dates.py` (+precision/confidence layer: `normalize_date_text`, `normalize_date_pair`), `core/profile.py` (+new fields on `WorkHistoryRecord`/`EducationRecord`), `models.py` (+10 columns across `candidate_work_history`/`candidate_education`), `persistence.py`, `industry/restaurant.py` (+AGM/GM/MANAGER catalog entries, role families, display names, multi-role splitting, title-based seniority), `core/experience_analysis.py` (+`work_entry_duration_months`, `chronological_timeline`, `current_roles`)
- Changed to emit raw date text instead of converting it themselves: `parsing/deterministic_parser.py`, `parsing/llm_parser.py` (prompt + mapping), `parsing/resolve.py` (now calls `normalize_profile()`)
- Tests: extended `selection_validation.py` (+18 checks, `_assert_normalization`) and `03 Software/Selection/test_batch_upload.py` (+1 pipeline-level check)

## 3. Date normalization rules implemented

Supported formats: ISO `YYYY-MM-DD`/`YYYY-MM`, `Month YYYY` / `Mon YYYY` / `Mon. YYYY`, `MM/YYYY`, bare `YYYY`, `Spring/Summer/Fall/Winter YYYY` (mapped to a representative month, precision `APPROXIMATE`), `Since <date>`, and the current-role markers `Present`/`Current`/`Ongoing`/`Now` (case-insensitive). Precision is one of `DAY`/`MONTH`/`YEAR`/`APPROXIMATE`/`UNKNOWN`; confidence is `HIGH`/`MEDIUM`/`LOW`. A date that cannot be confidently parsed stays `None` with `UNKNOWN`/`LOW` — never guessed. `is_current` is driven solely by the end-date text; a current marker always yields `normalized_end_date=None`. Duration (`work_entry_duration_months`) is never persisted — it is recomputed on read, reusing the existing `months_between()` — and documented: a year-only date is treated as January 1st of that year for duration purposes, so `"2020 – 2022"` computes as exactly 24 months without claiming month-level precision (callers can check `start_date_precision`/`end_date_precision` for that). Overlapping employment is unaffected — the existing `detect_overlaps()` already treated overlap as valid, not an error.

## 4. Role normalization / taxonomy implemented

Extended the existing Restaurant Industry Extension catalog (`industry/restaurant.py`) rather than building a new one. Added `ASSISTANT_GENERAL_MANAGER` and a generic `MANAGER` catalog code (with word-boundary `AGM`/`GM` acronym matching, checked before the substring keyword list so `"AGM"` never collapses into `"GM"`). New per-title outputs: `normalized_title` (human-readable, e.g. `"Assistant General Manager"`; `WAITER`/`WAITRESS`/`DINING_SERVER` all display as `"Server"`), `role_family` (12 hospitality families: FOH Service, Bar, Host/Guest Reception, Support/Busser/Runner, Kitchen/BOH, Culinary Leadership, Restaurant Management, Operations/General Management, plus a defensive Other/Unknown), `seniority_level` (Trainee/Junior/Lead/Supervisor/Assistant Manager/General Manager/Director-Executive — derived ONLY from explicit title wording via ordered regex patterns, never from tenure), `multi_role` and `title_normalization_confidence`. Multi-role titles (`Server/Bartender`, `Host & Server`, `Cook / Dishwasher`, etc.) are split on `/`, `&`, `+`, `,`, and `"and"`, each segment normalized independently, and joined for display (`"Server / Bartender"`). A title matching no catalog role leaves every Task 2B role field `None` — no fabricated classification.

## 5. How original vs normalized values are preserved

`original_job_title` (existing) is never written to by normalization. New raw-text columns `start_date_text`/`end_date_text` hold the résumé's own date text exactly as extracted; the existing `start_date`/`end_date`/`is_current` columns now hold the normalized values, always re-derived from that raw text (never from each other), which is also what makes normalization idempotent — every normalized field is a pure function of one raw source. A record with no captured raw date text (a legacy, pre-Task-2B row) is left completely untouched by the normalizer rather than guessed at.

## 6. Duration / chronology behavior

Duration is exposed, not stored (`experience_analysis.work_entry_duration_months()`), consistent with the existing "Derived Information is recomputed, not persisted" convention already used for the rest of the analysis engine. Chronological ordering (`chronological_timeline()`) sorts by `start_date` ascending, independent of résumé listing order, with undated records appended rather than dropped. `current_roles()` returns every `is_current` record, deliberately as a list — a candidate can hold more than one current role simultaneously (part-time, consulting, seasonal), and overlap is preserved and never treated as an error.

## 7. Known limitations directly relevant to Task 2B

- The deterministic parser's raw-date capture inherits Task 2A's block-splitting heuristics; an unusual single-block resume layout can occasionally misattribute which text is a date, which normalization then correctly flags as `UNKNOWN` rather than silently guessing.
- Multi-role splitting handles common separators only (`/`, `&`, `+`, `,`, `and`); a title like `"Server + Shift Lead"` correctly captures `"Server"` as a catalog role and `"Lead"` as seniority (from the whole-title text), but `"Shift Lead"` alone is not a distinct role-family code.
- A bare, unqualified `"Manager"` normalizes to the generic `MANAGER` code/family "Restaurant Management" with no further specificity — deliberately conservative rather than guessing which kind of manager.
- Reprocessing a genuinely pre-Task-2B legacy candidate (no raw date text ever captured) can only add role normalization; its dates are left exactly as Task 2A produced them, since there is no preserved raw text to re-derive a precision/confidence from.

## 8. Targeted tests performed and results

Extended the existing test runners (no new test framework):

- `python test_selection_engine.py` (`selection_validation.py`, incl. new `_assert_normalization`): **46/46 checks passed** (28 pre-existing + 18 new Task 2B checks 2B-A through 2B-R, covering every item in the task's test checklist: date formats, current-role synonyms, unparseable dates, duration, overlap, Waitress/AGM/GM/multi-role/Lead-seniority/unknown-title/original-title-preserved, idempotency, live pipeline import, and reprocessing an already-persisted candidate).
- `python test_batch_upload.py` (Flask end-to-end, real TXT/DOCX résumés): **19/19 checks passed** (18 pre-existing Task 2A checks + 1 new check confirming the real import pipeline produces normalized dates/roles for a live upload).
- Full Alembic migration chain verified to apply cleanly through the new head revision on a fresh database.

No unresolved issues.
