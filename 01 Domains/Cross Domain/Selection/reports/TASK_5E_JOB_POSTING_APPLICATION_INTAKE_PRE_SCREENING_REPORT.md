# TASK 5E — Job Posting + Application Intake + Missing-Evidence Pre-Screening — Report

**Status:** Complete
**Scope:** Selection Domain runtime (`03 Software/Selection/`, `03 Software/RF-One Data Store/rfone_data_store/selection/`) — no file outside Selection was touched. Primary Screening, Fit Assessment, Phone/In-Person Interview, Consistency, the Outcome Engine, Trainable Gap, the Candidate Dossier, Selection Session/Rule Governance, Candidate Communication, and Scheduling were all preserved unmodified except three deliberately minimal, additive extension points (see §3/§10 below).

---

## 1. What was implemented

The full pre-interview intake pipeline: a Job Posting Generator (auto-drafted from Session/Role context, human-editable/versioned, explicitly approved before any channel work); independently-editable, individually-approved channel-specific variants; a generic Channel/Publication/Tracking-Link container (connected-vs-manual, no provider APIs); a public, mobile-friendly Web Application Form (CV upload + configurable first-screening questions) reached only through an opaque tracking-link token; full reuse of existing CandidatePerson/Application identity resolution (repeated applicants recognized, never duplicated); Application answers preserved as candidate self-reported Primary-Screening evidence; a candidate-specific Missing-Evidence Questionnaire generated automatically only for genuinely missing, importance-flagged Criteria and sent through the existing Communication/Reminder engine; a READY FOR PHONE REVIEW operational state (reusing the existing Queue mechanism) that never itself performs ADVANCE_TO_PHONE; and channel/placement/variant analytics with advisory-only recommendations.

---

## 2. Main files changed

**New (`rfone_data_store/selection/`):**
- `core/job_posting_model.py` — posting/variant/publication status, content-origin, response-type, questionnaire-status, and advisory-recommendation vocabulary
- `job_posting_service.py`, `channel_service.py`, `application_question_service.py`, `missing_evidence_service.py`, `application_intake_service.py`, `channel_analytics_service.py`

**New (migration):** `migrations/versions/f7c3a9d1e6b4_add_selection_5e_job_posting_intake_pre_screening.py` — 12 new tables + 3 additive columns on `primary_screening_criteria`/`_snapshots` + 1 additive column on `applications`

**New (`03 Software/Selection/templates/`):** `job_posting_detail.html`, `channels_home.html`, `application_questions_home.html`, `channel_analytics.html`, `apply_form.html`, `apply_confirmation.html`, `missing_evidence_questionnaire.html`, `missing_evidence_confirmation.html`

**Modified:**
- `rfone_data_store/models.py` — 12 new tables; `PrimaryScreeningCriterion`/`.Snapshot` gained `required_for_phone_review`/`missing_evidence_question_text`/`missing_evidence_answer_level_map`; `Application` gained `channel_publication_id`
- `rfone_data_store/selection/primary_screening_service.py` — ONE new public function, `apply_self_reported_evidence` (plus a small `get_evaluation_for_criterion` lookup helper); every existing function is untouched
- `rfone_data_store/selection/core/communication_model.py` — new `TRIGGER_MISSING_EVIDENCE_QUESTIONNAIRE` trigger event (added to `RESPONSE_AWAITED_TRIGGERS`)
- `rfone_data_store/selection/core/queue_model.py` — new `AUTOMATIC_READINESS` queue-movement source
- `rfone_data_store/selection/dossier_service.py` — added `IntakeContext` to `ApplicationDossier`; no existing field changed
- `03 Software/Selection/app.py` — new imports; ~24 new routes (Job Posting/variant/publication management, Channels, Application Questions, Channel Analytics, and the public `/apply/<token>` and `/missing-evidence/<token>` routes)
- `templates/session_detail.html` — a "Job Postings" section; `templates/dossier.html` — an "Application Intake" section; `templates/base.html` — 3 new nav tabs

---

## 3. Job Posting model

`JobPosting` (Session + Role + restaurant/branch + applicable Rule Set version, `status` DRAFT/APPROVED, a convenience `current_version`/`approved_version_id` pointer) + `JobPostingVersion` (the full append-only content history — title, Company description, Branch description, role summary, responsibilities, min/preferred requirements, availability/schedule/compensation/benefits descriptions, location, application instructions, other info — all descriptive text, never a numeric Selection Rule). `job_posting_service.generate_base_posting` drafts version 1 purely from the Session's own structural data (role, location, current Rule Set version) and never sets `status=APPROVED` (checks A/B). Every edit (`edit_posting`) creates a new version; editing after the posting has ever been approved requires a preserved `reason` (checks C/H/I, mirroring `SelectionOutcomeDecision`'s "changing an existing decision requires a reason" discipline). Company and Branch descriptions are two independent fields — editing one never rewrites the other, and no code path copies one into the other (check D).

---

## 4. Channel Variant/version behavior

`JobPostingChannelVariant` (one row per Channel × posting, `create_channel_variant` rejects being called before the base posting is approved — check B) + `JobPostingChannelVariantVersion` (its own append-only content history). Variants are edited and approved **individually** — `approve_channel_variant` operates on exactly one variant id; there is no bulk/"Approve All" function anywhere in the codebase (checks E/F/G). Editing an already-approved variant requires a `reason`, preserved on the new version while the prior, already-published version's text is never overwritten (checks H/I). More than one variant may exist for the same Channel (e.g. two Facebook variants), which is exactly the minimal structure task §34 asks for to compare distinct versions/placements.

---

## 5. Channel/publication/tracking-link model

`ChannelDefinition` — a generic, restaurant-configurable container (`is_connected` vs. manual, `supports_publish/update/pause/stop/metrics/cost_tracking`, `is_paid`, an optional `default_acquisition_source_id`) — RF-One seeds the task's own example list (Indeed, LinkedIn, Facebook, ... ) idempotently; no provider API is called anywhere (check AR — `ChannelDefinition` has no credential/API fields at all). `ChannelPublication` is one specific placement of one *approved* variant version (`record_publication` rejects an unapproved variant), copying `is_connected` at creation time so a later Channel edit never rewrites a historical publication's meaning; cost is optional integer minor-unit cents, `None` when unrecorded (check AP). `ChannelTrackingLink` is a secure, opaque, non-single-use token issued automatically with every publication; `channel_service.resolve_application_context` is the one function that turns a token into everything the public form needs (Session, Role, Job Posting, exact variant/version, restaurant/branch) — multiple placements on the same Channel/variant version each get their own distinct token (checks K/L/M), and applying through one automatically sets `Application.channel_publication_id` and (via the Channel's own configured default) `acquisition_source_id` (check N).

---

## 6. Web Application Form

The public `/apply/<token>` route resolves only through the tracking link — never an internal Session/Job-Posting id — and renders first name/last name/email/phone/CV upload, the Session/Role's configured first-screening questions, an optional message, and a required consent acknowledgement (task §13's "where current architecture supports it" — enforced as a required checkbox; no separate consent-ledger table exists, see §10). Submission reuses the exact same `import_pipeline`/text-extraction path every other intake route already uses (checks O/P/T — verified with a real uploaded file through Werkzeug's test client, not just a service-layer call).

---

## 7. Application Question model

`ApplicationQuestionDefinition` — Session-and/or-Role-scoped (either may be `None` to mean "any", mirroring `CommunicationTemplate`'s scoping convention), `response_type` (TEXT/YES_NO/NUMBER/SCALE), optional `related_criterion_id` + `answer_level_map` (the exact restaurant-configured-mapping pattern `PrimaryScreeningCriterion.auto_evaluation_level_map` already established, applied here to a candidate's own answer instead of a Signal) — a deliberately different table/UI from Phone/In-Person Interview questions (task §17; check Q). `ApplicationQuestionAnswer` preserves the raw answer plus the exact question version answered; `apply_answers_to_screening` is the one place an answer becomes Primary Screening evidence, via the one new `primary_screening_service.apply_self_reported_evidence` function — a level is set only when the restaurant's own mapping resolves it, otherwise the raw text is preserved as evidence with no fabricated level (check W).

---

## 8. Repeated-applicant behavior

`application_intake_service.submit_application` always calls the existing, unmodified `application_service.create_application` (which itself calls `identity_service.resolve_or_create_person`) — a repeated applicant with a new résumé resolves to the SAME `CandidatePerson` (matched by email/phone) but always gets a brand-NEW `Application` row, never merged into or overwriting a prior one (checks U/V). `application_service.list_prior_applications` — completely untouched — remains the one source of repeated-Application history and was verified still populated and reachable from a Task-5E-created Application.

---

## 9. Missing-Evidence Questionnaire

`missing_evidence_service.process_application_readiness` is the one function implementing the product principle: it inspects the latest Primary Screening Run's evaluations, and for every Criterion the restaurant flagged `required_for_phone_review` whose evaluation is still `NOT_EVALUATED`/`INSUFFICIENT_EVIDENCE`, generates exactly one `MissingEvidenceQuestion` (never a duplicate for an already-resolved Criterion, never one for a non-required Criterion like a deep behavioral trait — checks AA/AB/AC). If an active Hard Disqualifier is already present, nothing happens (the Application is "clearly to be stopped," left for the Selezionatore, task §22's own qualifier). The Questionnaire (`MissingEvidenceQuestionnaire` + secure opaque `token`, consistent with Task 5D's `CandidateSchedulingToken` architecture) is sent automatically — no Selezionatore approval step — through the ordinary `communication_service.send_communication` using a new `TRIGGER_MISSING_EVIDENCE_QUESTIONNAIRE` Template (check AD). Submitting answers (`submit_answers`) preserves each raw answer, converts it into evidence via the same `apply_self_reported_evidence` function (a level only when the Criterion's own `missing_evidence_answer_level_map` resolves it), never touches any other Criterion's already-recorded evidence (checks AF/AG/AH), and finishes by re-running the readiness check. Because `TRIGGER_MISSING_EVIDENCE_QUESTIONNAIRE` was added to `RESPONSE_AWAITED_TRIGGERS`, a restaurant-configured `CommunicationReminderPolicy` for it attaches and drives reminders/no-response exactly like every other Task 5D trigger — no separate reminder system exists (check AL).

---

## 10. Evidence-reliability behavior

No redesign of the Task 3D vocabulary was needed: `INSUFFICIENT_EVIDENCE`/`NOT_EVALUATED` and the never-silently-level-0 discipline already existed and were reused as-is. What Task 5E added was strictly additive: `required_for_phone_review` (Criterion Importance stays on `coefficient`/`direction`/`is_hard_disqualifier`, exactly as before; Assessment Reliability at this stage was already expressed via `evidence_sources_allowed`; this new field answers only "is resolving this Criterion required before Phone Review eligibility"). Verified directly: a Criterion with no CV/Signal/Application evidence path stays `effective_level=None` after screening (check X — never a fabricated negative), its status is explicitly `NOT_EVALUATED`/`INSUFFICIENT_EVIDENCE` (check Y), and a deep-behavioral-style Criterion (Guest Sensitivity, evidence restricted to later-stage `CONSISTENCY_INFORMATION`) is never inferred from weak early evidence (check Z).

---

## 11. READY FOR PHONE REVIEW behavior

Reuses the existing `SelectionQueue`/`ApplicationQueueMovement` mechanism (Task 5A-FIX) rather than a new lifecycle field: `missing_evidence_service.get_or_create_ready_for_phone_review_queue` seeds one queue named "Ready for Phone Review," and `queue_service.move_to_queue(..., source=qm.AUTOMATIC_READINESS)` (a new, minimal, additive `SOURCES` entry) moves the Application into it once every required Criterion is resolved (check AI). This never touches `Stage`/`Outcome` — verified that reaching this queue leaves `current_stage` unchanged (check AJ), and that a Selezionatore's own subsequent `stage_service.set_stage(..., PHONE_INTERVIEW)` call still works exactly as before, completely unmodified (check AK) — ADVANCE_TO_PHONE remains exclusively a human action.

---

## 12. Channel analytics / recommendations

`channel_analytics_service.get_channel_funnel_metrics` returns one row per `ChannelPublication` (never collapsed across placements — checks AM/AN/AO, verified with two Facebook placements attributing to two different Applications), reading Applications-received, passed-Primary-Screening, Ready-for-Phone-Review, Advanced-to-Phone, Phone/In-Person-reached, and Hirable (matched by name, the same honest "no dedicated flag" convention `dossier_service._training_check_flags` already established) — future Training/Hired states are simply absent, never stubbed. Cost-derived metrics (`cost_per_application`/`_ready_for_phone_review`/`_advance_to_phone`/`_hirable`) are `None` whenever `cost_amount_cents` is unset (check AP) and populate once it is. `recommend_channel_actions` is a pure, transparent volume/conversion heuristic returning `INCREASE`/`REDUCE`/`MAINTAIN`/`TEST` (check AQ) — it never writes to the database; nothing in this task alters a budget or a live Publication automatically.

---

## 13. Dossier/UI integration

`ApplicationDossier` gained one additive `IntakeContext` (Acquisition Source, Channel/Publication/placement, Application-Question answers, pending/answered Missing-Evidence Questionnaire state, READY-FOR-PHONE-REVIEW flag) — nothing existing in the Dossier was restructured. Practical UI was added for every Part-G requirement: Job Posting generate/edit/approve, per-variant generate/edit/approve, manual-publication recording with automatic tracking-link display, Session-level "Job Postings" section, restaurant-wide Channels/Application-Questions/Channel-Analytics pages, and the two public candidate-facing pages.

---

## 14. Targeted tests and results

**A. Permanent regression suite** (`selection_validation.py::_assert_job_posting_application_intake_pre_screening`, 48 checks covering the task's own A-AR letter items — AW-BD/BE are the full-suite regression result itself, not separate checks), registered in `run_validation()`. Fresh SQLite DB, migrations applied through revision `f7c3a9d1e6b4`. **Full suite result: 570/570 checks passed, confirmed stable across 3 independent fresh-DB runs** (522 pre-existing including Task 5D/5D-MICRO-FIX's own 43+14 + 48 new) — confirming AW-BD (no regression in Primary Screening, Communication, Scheduling, Session/Rule Governance, Phone Interview, In-Person/Practical, the Outcome Engine, or the Dossier) and BE. One pre-existing Task 5D check (secure-scheduling-token opacity) was found to be probabilistically flaky — a `secrets.token_urlsafe` value can coincidentally contain an Application id's digits as a substring purely by chance — and was tightened to a deterministic property (the token is never literally the id, and is long/high-entropy) rather than "the id's digits never appear," which was never a meaningful safety property in the first place.

**B. Flask HTTP-level smoke test #1** (throwaway DB, real `test_client()`): generate → edit → approve a base Job Posting, create → approve a channel variant, record a publication, load the public `/apply/<token>` page, submit a REAL uploaded CV file, confirm the Application was created/attributed/linked, and confirm an invalid token 404s. **15/15 passed.**

**C. Flask HTTP-level smoke test #2**: the Missing-Evidence Questionnaire end-to-end through real routes (`/missing-evidence/<token>` GET+POST), confirming the submitted answer updates the correct Primary Screening evidence, plus an invalid-token 404 and every new nav page. **9/9 passed** (24/24 combined with test #1's continuation).

**D. Full-navigation regression smoke**: all 20 nav pages (17 pre-existing + 3 new: Channels, Application Questions, Channel Analytics) render 200. **20/20 passed.**

---

## 15. Known limitations directly relevant to Task 5E

- **Consent is enforced as a required checkbox, not a persisted consent record.** Task §13's own qualifier ("where current architecture supports it") is read literally: no consent-ledger table exists elsewhere in Selection, so none was introduced here; the public form simply rejects a submission without the checkbox checked.
- **`missing_evidence_answer_level_map`/`answer_level_map` are exact-string-match mappings**, exactly like the pre-existing `auto_evaluation_level_map` they mirror — a restaurant configuring "YES"/"NO" must match the literal answer value submitted (the form's own YES_NO question type submits exactly those two values). Free-text Missing-Evidence answers with no configured mapping are preserved as evidence text but never assigned a fabricated level — an intentional consequence of the never-fabricate-evidence principle (§19), not a gap.
- **The "Hirable" analytics signal is a name-based match** (`"hirable" in outcome_definition_snapshot.name.lower()`), the same honest, already-established convention `dossier_service._training_check_flags` uses — a restaurant that renames its seeded "Hirable" Outcome to something unrelated will not be picked up by this specific metric (every other funnel metric is unaffected).
- **No provider-specific connector exists** (task's own explicit non-requirement) — `ChannelDefinition.is_connected` is descriptive only; a future connector would own actually calling Indeed/LinkedIn/Facebook/etc.
- **Double-booking-style concurrency protection was not needed here** — Job Posting/Channel/Publication creation has no shared-capacity concept analogous to Task 5D-MICRO-FIX's scheduling slots, so no equivalent DB-level guard was required.
