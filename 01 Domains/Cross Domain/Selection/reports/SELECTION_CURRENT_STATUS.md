# Selection Domain — Current Status Review

Read-only inspection of the actual current files (not task documents) as of this review (2026-09-06 refresh; supersedes the executive summary and feature table below as originally written after TASK_SELECTION_002 — see §4 for that original content, preserved for history).

## 1. Executive summary

Selection now implements a full, working, tested candidate-selection workflow end-to-end — not only Resume Screening. As of this refresh the implementation covers: résumé intake/parsing and evidence structuring, Requirement configuration and Fit Assessment, primary/pre-screening, phone interview planning and evaluation, in-person interview planning and evaluation, trainable-gap identification and review, cross-source consistency checking, Selection Outcome Decisions, a full Job Posting/application-intake workflow (channels, questions, public apply pages), compliance review, acting-identity and authority controls, and supporting communications/scheduling/dossier/audit capabilities. This is real, migrated, service-backed code — not a conceptual sketch — and is validated by an automated suite of **658/658 passing checks** (`rfone_data_store/selection_validation.py`, run via `test_selection_engine.py`; see §8).

The domain conceptual documents (`01 Domains/Cross Domain/Selection/*.md`) describe the target model; the implementation below has, since the original version of this status document was written (after TASK_SELECTION_002), grown to cover nearly all of that conceptual scope end-to-end, across a long sequence of dated development passes (Tasks 2A/2B, 3A–3D, 4A/4B, 5A–5F — see `01 Domains/Cross Domain/Selection/reports/TASK_*_REPORT.md` for each pass's own historical record; not rewritten here). What remains genuinely unimplemented is narrower than before and is listed explicitly in §5/§9 rather than implied by omission.

## 2. Current end-to-end Selection flow

```
Sourcing / acquisition
  → Job Posting authored + approved, published to Channel(s)  (job_posting_service.py, channel_service.py)
  → public "Apply" page / acquisition source                   (application_intake_service.py, application_question_service.py, acquisition_source_service.py)

Intake and structuring
  → résumé file (PDF/DOCX/TXT) or application submission
  → text extraction                                             (parsing/text_extraction.py)
  → structured parsing (LLM or deterministic fallback)          (parsing/llm_parser.py, parsing/deterministic_parser.py, parsing/resolve.py)
  → date + role normalization                                   (normalization.py)
  → candidate/application profile persisted                     (persistence.py, application_service.py, models.py)
  → evidence + Derived/Flags/Indicators view                    (analysis.py, resume_evidence_matcher.py)

Evaluation
  → Requirement configuration (custom or template-based)        (requirements_service.py)
  → Fit Assessment against a Requirement                        (fit_assessment_service.py)
  → Primary/pre-screening (criteria, hard disqualifiers)        (primary_screening_service.py, primary_screening_ai_evaluator.py)
  → Phone interview planning + evaluation                       (phone_interview_service.py)
  → In-person interview planning + evaluation                   (in_person_interview_service.py)
  → Trainable-gap identification + review                       (trainable_gap_service.py)
  → Cross-source consistency threads                            (application_comparison.py, signal_detector.py, signal_service.py)
  → Selection Outcome Decision                                  (outcome_service.py, decision_service.py)

Supporting / governance
  → Queue / stage / session management                          (queue_service.py, stage_service.py, session_service.py)
  → Acting identity + authority controls                        (identity_service.py, authority_service.py, ownership_service.py)
  → Compliance review                                           (compliance_service.py)
  → Communications, scheduling, reminders, inbound handling      (communication_service.py, scheduling_service.py, inbound_communication_service.py)
  → Candidate/application dossier                                (dossier_service.py)
  → Audit trail                                                  (audit_service.py)
```

This supersedes the original diagram, which stopped at "evidence view" and marked everything after it "NOT PRESENT." That stage is now one of many in a longer, implemented chain — see §3 for the per-feature breakdown and §5/§9 for what still is not implemented.

## 3. Feature/status table

| Stage / Feature | Status | Principal files |
|---|---|---|
| Batch multi-file import (one action, per-file isolation) | **IMPLEMENTED** | `app.py` (`/upload`, `/api/upload`), `import_pipeline.py` |
| PDF / DOCX / TXT text extraction | **IMPLEMENTED** | `parsing/text_extraction.py` |
| Unsupported/corrupt/empty file handling | **IMPLEMENTED** | `import_pipeline.py` ("no extractable text" → FAILED, never a fabricated result) |
| Real AI structured parsing | **IMPLEMENTED, but unexercised in this environment** — no `ANTHROPIC_API_KEY` and the `anthropic` package is not installed here, so every real import still falls through to the rule-based parser | `parsing/llm_parser.py`, `parsing/ai_client.py` |
| Real deterministic (rule-based) parsing fallback | **IMPLEMENTED** — the path actually exercised today | `parsing/deterministic_parser.py` |
| Old fixture-based "demo" parser | **PRESENT BUT UNUSED IN PRODUCTION** — kept for direct synthetic-fixture testing only | `parsing/demo_parser.py`, `parsing/fixtures.py` |
| Candidate/application persistence | **IMPLEMENTED** | `models.py`, `persistence.py`, `application_service.py` |
| Duplicate detection (content-hash, per-restaurant) | **IMPLEMENTED** — exact/renamed-file duplicates only, not identity resolution | `parsing/dedup.py`, `import_pipeline.py` |
| Date + role/title normalization | **IMPLEMENTED** | `normalization.py`, `parsing/flexible_dates.py`, `industry/restaurant.py` |
| Evidence-based screening surfacing (Flags, Indicators, Information Quality — no score) | **IMPLEMENTED** | `core/flags.py`, `core/indicators.py`, `core/information_quality.py`, `analysis.py` |
| Organization Intelligence (employer-quality reasoning) | **PLACEHOLDER — explicit, documented stub** (`NOT_IMPLEMENTED = True`), unchanged since the original review | `core/organization_intelligence.py` |
| Requirement configuration (custom or template-based, versioned via snapshots) | **IMPLEMENTED** | `requirements_service.py`, `core/requirement_model.py`, `app.py` (`/requirements/*`) |
| Fit Assessment against a Requirement | **IMPLEMENTED** | `fit_assessment_service.py`, `core/fit_assessment_model.py`, `app.py` (`/candidate/<id>/fit-assessments`, `/fit-assessments/<id>`) |
| Trainable Gap identification + human review | **IMPLEMENTED** | `trainable_gap_service.py`, `core/trainable_gap_model.py`, `app.py` (`/trainable-gaps/<id>/review`) |
| Primary/pre-screening (criteria, hard disqualifiers, override) | **IMPLEMENTED** | `primary_screening_service.py`, `primary_screening_ai_evaluator.py`, `core/primary_screening_model.py`, `app.py` (`/primary-screening-*`) |
| Candidate scoring / universal ranking | **STILL NOT IMPLEMENTED** — explicitly and repeatedly excluded by design ("no universal CV score"); Fit Assessment/Primary Screening produce structured evidence and disposition, not a single rank score | — |
| Phone interview planning + evaluation (question bank, gating, follow-ups, fit/signal evidence capture, decision) | **IMPLEMENTED** | `phone_interview_service.py`, `core/phone_interview_model.py`, `app.py` (`/phone-interview*`, `/phone-interviews/*`) |
| In-person interview planning + evaluation (sections/items, follow-ups, fit/signal evidence, stop) | **IMPLEMENTED** | `in_person_interview_service.py`, `core/in_person_interview_model.py`, `app.py` (`/in-person-interview*`, `/in-person-interviews/*`) |
| Cross-source consistency checks (consistency threads, statements, cross-application generation, clarification) | **IMPLEMENTED** | `application_comparison.py`, `signal_detector.py`, `signal_service.py`, `app.py` (`/consistency-threads/*`) |
| Selection Outcome Decision (apply/reopen, outcome definitions) | **IMPLEMENTED** | `outcome_service.py`, `decision_service.py`, `core/outcome_model.py`, `app.py` (`/applications/<id>/outcome/*`, `/selection-outcomes/*`) |
| Job Posting workflow (author, approve, channel variants, publications) | **IMPLEMENTED** | `job_posting_service.py`, `core/job_posting_model.py`, `channel_service.py`, `app.py` (`/job-postings/*`, `/channels`) |
| Public application intake (apply page, application questions, acquisition source) | **IMPLEMENTED** | `application_intake_service.py`, `application_question_service.py`, `acquisition_source_service.py`, `app.py` (`/apply/<token>`) |
| Channel analytics | **IMPLEMENTED** | `channel_analytics_service.py`, `app.py` (`/channel-analytics`) |
| Compliance review | **IMPLEMENTED** | `compliance_service.py`, `core/compliance_model.py`, `app.py` (`/compliance-reviews`, `/compliance/*`) |
| Acting identity / authority controls (identity switch/register, ownership, reassignment) | **IMPLEMENTED** | `identity_service.py`, `authority_service.py`, `ownership_service.py`, `core/identity_model.py`, `app.py` (`/identity/*`, `/applications/<id>/reassign*`), `test_acting_identity_http.py` |
| Queue / stage / session management (evaluation sessions, rule sets, rule-change impact review) | **IMPLEMENTED** | `queue_service.py`, `stage_service.py`, `session_service.py`, `rule_set_service.py`, `rule_change_service.py`, `app.py` (`/selection-queues`, `/sessions/*`) |
| Missing-evidence follow-up (public token-based request) | **IMPLEMENTED** | `missing_evidence_service.py`, `app.py` (`/missing-evidence/<token>`) |
| Communications (templates, scheduling windows, reminders, inbound handling) | **IMPLEMENTED** | `communication_service.py`, `communication_template_service.py`, `communication_providers.py`, `scheduling_service.py`, `inbound_communication_service.py`, `app.py` (`/communication-templates`, `/schedule/<token>*`, `/inbound/*`) |
| Candidate/application dossier | **IMPLEMENTED** | `dossier_service.py`, `app.py` (`/applications/<id>/dossier`) |
| Audit trail | **IMPLEMENTED** | `audit_service.py`, `app.py` (`/applications/<id>/audit`, `/audit.json`) |
| Priority policies (rule-based application prioritization) | **IMPLEMENTED** | `app.py` (`/priority-policies/*`) — no single dedicated service file identified beyond the route handlers; not yet independently confirmed to have a `*_service.py` module of its own |
| Pattern detection / case memory / governance | **IMPLEMENTED** (present in code, not yet independently walked through route-by-route in this review) | `pattern_service.py`, `case_memory_service.py`, `governance_service.py`, `core/pattern_model.py` |
| UI: candidate list + batch upload | **IMPLEMENTED** | `templates/home.html` |
| UI: candidate/application detail, requirements, fit assessments, interviews, decisions, job postings, compliance, sessions | **IMPLEMENTED** | `templates/*.html` (not individually enumerated in this review) |

## 4. Historical record — status as originally written after TASK_SELECTION_002 (superseded by §1–3 above)

*Preserved verbatim for history; do not treat as current.* At that point in the project, Selection implemented exactly one capability end-to-end: Resume Screening — batch résumé import, text extraction, structured parsing, date/role normalization, and evidence/indicator/flag presentation, validated by 46+19 targeted checks. Everything beyond that (role/job-fit matching, phone interview, interview evaluation, shortlist, Selection Decision) existed only as conceptual documentation with no corresponding code. The most recent completed work at that time was Task 2B (date + role normalization layer, migration `f4d8e2a1c6b3`), preceded by Task 2A (the batch import pipeline itself). Since then, Tasks 3A through 5F implemented the Requirement/Fit Assessment, interview, trainable-gap, consistency-check, outcome-decision, job-posting, compliance, identity/authority, and communications/scheduling/dossier/audit capabilities now reflected in §1–3. See the individual `TASK_*_REPORT.md` files in this same `reports/` folder for each pass's own detailed, unmodified historical record.

## 5. Existing partial / placeholder components and known limitations

- **Real AI parsing path** — fully coded (prompt, JSON mapping, provider abstraction) but not exercised in this environment: no API key configured, `anthropic` package not installed. Every current import goes through the rule-based fallback. Not "fake" — genuinely implemented, just currently unreachable here.
- **`demo_parser.py` / `fixtures.py`** — real code, deliberately not wired into the production import path; used only by direct synthetic-fixture tests of the analysis engine.
- **`organization_intelligence.py`** — an explicit, documented empty extension point (`NOT_IMPLEMENTED = True`), not wired to anything. Unchanged since the original review.
- **Deterministic parser's structural heuristics** — block-splitting/employer-vs-title splitting are heuristic (documented limitations in the code itself); they degrade to `None`/lower confidence rather than fabricating, but are not 100% reliable on unusual résumé layouts.
- **Duplicate handling** — content-hash exact/renamed-file matching only; not candidate identity resolution.
- **Candidate scoring / universal ranking** — deliberately not implemented (design decision, not a gap); Fit Assessment and Primary Screening produce structured evidence and dispositions instead.
- **Priority policy logic** — routes and configuration exist (`/priority-policies/*`); this review did not independently trace whether the prioritization logic lives in a dedicated service module or inline in `app.py` — flagged here rather than asserted either way.
- **Local dev/manual-use database (`03 Software/Selection/data/selection.db`) is lightly populated** — as of this review it held only 2 candidates, 2 applications, 2 selection outcome decisions, and 0 fit assessments/phone interview plans/job postings. The advanced capabilities above are proven correct by the automated disposable-database test suite (§8), but have not yet been exercised through the running web app with substantial real, manually-entered data. This is a real-usage-coverage caveat, not a code-correctness gap.
- **Route/service inventory in §2–3 is not exhaustive** — `app.py` alone exposes roughly 190 routes across the areas listed; a small number of narrower routes/services (e.g. `workflow_projection_service.py`, `channel_service.py` internals) were confirmed to exist but not individually walked through for this refresh.

## 6. Current data model relevant to Selection

The original review's table (résumé/candidate/education/work-history/skills/certifications/languages) remains accurate for the résumé-intake slice and is preserved below unchanged. Beyond that slice, real ORM model classes exist (in `models.py`, referenced via each feature's `core/*_model.py` in §3) for at least: Requirement/RequirementSet (+ snapshots), FitAssessment, TrainableGap, PrimaryScreeningCriterion/Run/Evaluation, PhoneInterviewQuestionDefinition/Plan, InPersonInterviewSection/Item/Plan, ConsistencyThread/Statement, SelectionOutcomeDefinition/application outcome state, JobPosting/ChannelVariant/Publication, Channel, ApplicationQuestion, AcquisitionSource, ComplianceReview, CommunicationTemplate/ReminderPolicy, SchedulingWindow, InboundCommunication, SelectionQueue, EvaluationSession, RuleSet/RuleChange, and audit-trail records. Exact column-level shape was not re-verified line-by-line in this refresh (out of scope — this task explicitly excludes modifying/re-deriving migrations or models) and is not restated here to avoid asserting detail beyond what was directly confirmed; consult `models.py` and the relevant migration(s) directly for authoritative schema.

Original (résumé-intake) table, unchanged:

- `raw_resumes` — source_type, filename, storage_path, raw_text, content_hash, uploaded_at
- `candidates` — identity/contact facts, summary, linkedin_url, other_profile_url, other_sections_text, source/source_provider, parsing_mode/parser_provider, status, declared/derived age-context, timestamps
- `candidate_education` — institution/program/qualification/field, start/end date + `*_text`/`*_precision`, completion_status, certifications (free text), notes
- `candidate_work_history` — employer/location/original_job_title/normalized_role, start/end date + `*_text`/`*_precision`, is_current, responsibilities/achievements/reason_for_leaving/evidence_snippet, `date_normalization_confidence`, `normalized_title`/`role_family`/`seniority_level`/`multi_role`/`title_normalization_confidence`
- `candidate_skills`, `candidate_certifications`, `candidate_languages` — one-row-per-item child tables

## 7. Current UI/API entry points

Single Flask app, `03 Software/Selection/app.py` — now roughly 190 routes (up from the 4 documented in the original review). Categories confirmed present by route prefix: identity (`/identity/*`), candidate list/upload/detail (`/`, `/upload`, `/api/upload`, `/candidate/<id>*`), requirements (`/requirements/*`), fit assessments (`/candidate/<id>/fit-assessments`, `/fit-assessments/<id>*`), applications (`/applications/<id>/*` — stage, outcome, notes, flags, reassignment, decision, dossier, audit, communications, scheduling), trainable gaps (`/trainable-gaps/<id>/review`), signals/priority (`/signals/*`, `/priority-policies/*`), identity-matches (`/identity-matches/*`), phone interviews (`/phone-interview-questions/*`, `/phone-interviews/<id>/*`), in-person interviews (`/in-person-interview-sections/*`, `/in-person-interviews/<id>/*`), consistency threads (`/consistency-threads/*`, `/applications/<id>/consistency-threads/*`), primary screening (`/primary-screening*`), selection outcomes/queues/sessions (`/selection-outcomes/*`, `/selection-queues/*`, `/sessions/*`), rule sets/changes (`/sessions/<id>/rule-set/*`, `/rule-change-impacts/*`), acquisition sources (`/acquisition-sources*`), communication templates/reminders (`/communication-templates/*`, `/reminder-policies/*`, `/admin/process-reminders`), inbound (`/inbound/*`), alerts (`/alerts`), scheduling (`/schedule/<token>*`), job postings/channels (`/job-postings/*`, `/job-posting-channel-variants/*`, `/channels*`), application questions (`/application-questions/*`), channel analytics (`/channel-analytics`), public apply/missing-evidence pages (`/apply/<token>`, `/missing-evidence/<token>`), and compliance (`/compliance-reviews`, `/compliance/*`). Individual routes are not exhaustively enumerated here; see `app.py` directly for the authoritative list.

## 8. Tests currently present and what they cover

- `03 Software/RF-One Data Store/test_selection_engine.py` → `rfone_data_store/selection_validation.py`: the comprehensive, currently-authoritative Selection validation suite (10,320 lines, covering Tasks 2A/2B, 3A–3D, 4A/4B, 5A–5F). **658/658 checks passing**, directly re-run and confirmed as part of this review, against a disposable test database with the full migration chain applied cleanly through the true repository head. Two benign `SAWarning`s (documented cleanup-pattern artifacts, not failures) were observed during the run.
- `03 Software/Selection/test_batch_upload.py`: 19 checks, end-to-end through the real Flask app with real TXT/DOCX fixtures — batch upload, unsupported/corrupt-file handling, PARTIAL/FAILED/DUPLICATE outcomes, normalized dates/roles on live import.
- `03 Software/Selection/test_acting_identity_http.py` — end-to-end HTTP-level test of the acting-identity/authority feature (identity switch/register, ownership/reassignment), present in the repository but not re-run as part of this documentation-only review.
- `03 Software/Selection/test_outcome_workflow_http.py` — end-to-end HTTP-level test of the Selection Outcome Decision workflow (apply/reopen), present in the repository but not re-run as part of this documentation-only review.
- No dedicated test file was identified for every individual feature area in §3 (e.g. channel analytics, compliance review); those are covered, to the extent they are, within `selection_validation.py`'s 658 checks rather than a standalone test file — this was not independently re-verified check-by-check in this refresh.

## 9. Concrete current frontier

The implementation is complete and validated (per §8) through the full workflow described in §2: sourcing → job posting → public application intake → résumé/application intake and structuring → Requirement/Fit Assessment → primary screening → phone and in-person interviews → trainable-gap review → cross-source consistency checks → Selection Outcome Decision, plus the supporting queue/session/identity/compliance/communications/dossier/audit layers.

What remains genuinely not implemented, confirmed against actual code rather than inferred from documentation:

- **Candidate scoring / universal ranking** — deliberately excluded by design (§5), not a gap to close.
- **Organization Intelligence** (`core/organization_intelligence.py`) — explicit stub, `NOT_IMPLEMENTED = True`.
- **Real AI structured parsing** — coded but unexercised in this environment (no API key/package installed).
- **Priority-policy business logic ownership** — not independently confirmed to live in a dedicated service module (§5); worth a direct check before relying on it as a clean architectural boundary.

Historical task reports in this `reports/` folder document each individual development pass (Requirement/Fit Assessment, interviews, trainable gaps, consistency checks, outcome decisions, job posting, compliance, identity/authority, communications) in full detail and are the authoritative record of *how* each capability was built; this document is only a current-state summary layered on top of them and does not restate their content.

---

**Recommended next step:** none required by this review — no blocking gap was found. If further Selection work is planned, the smallest concrete items available are: (a) directly confirm whether priority-policy logic has its own service module, and (b) decide whether to exercise the AI parsing path (API key/package) in a real environment rather than leaving it permanently on the deterministic fallback.
