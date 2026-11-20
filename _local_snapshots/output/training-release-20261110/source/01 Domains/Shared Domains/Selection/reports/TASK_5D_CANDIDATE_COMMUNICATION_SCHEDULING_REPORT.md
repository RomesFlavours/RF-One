# TASK 5D — Candidate Communication + Interview Scheduling — Implementation Report

**Status:** Complete
**Scope:** Selection Domain runtime (`03 Software/Selection/`, `03 Software/RF-One Data Store/rfone_data_store/selection/`) — no file outside Selection was touched. No existing Primary Screening, Fit Assessment, Phone/In-Person Interview, Consistency, Outcome Engine, Trainable Gap, Candidate Dossier, or Selection Session/Rule Governance logic was redesigned.

---

## 1. What was implemented

A first-class **Candidate Communication + Interview Scheduling** capability: a restaurant-configurable, versioned Communication Template engine that sends SMS + Email simultaneously (or the single available channel); automatic communication triggered as a *consequence* of an existing Stage/Outcome decision (never itself the decision); a Phone Interview advance with a Selezionatore-chosen Scheduling-vs-Contact mode; a secure token-based candidate-facing scheduling page with automatic slot confirmation and double-booking prevention; configurable reminders with a delegated, explicitly-opt-in NO RESPONSE auto-STOP through the existing authoritative Outcome Engine; a deterministic, non-fabricating inbound-message classifier with Selezionatore correction and mandatory late-response alerting; and a complete, chronological, Application-linked communication/appointment history surfaced on the Dossier.

---

## 2. Main files changed

**New (`rfone_data_store/selection/`):**
- `core/communication_model.py` — trigger-event, channel, delivery-status, appointment-status, and inbound-classification vocabulary
- `acquisition_source_service.py`, `communication_providers.py` (mock SMS/Email seam), `communication_template_service.py`, `communication_service.py`, `scheduling_service.py`, `inbound_communication_service.py`

**New (migrations):** `migrations/versions/d4a7c1e9f3b6_add_selection_candidate_communication_scheduling.py` — 9 new tables + 2 nullable columns on `applications`

**New (`03 Software/Selection/templates/`):** `acquisition_sources_home.html`, `communication_templates_home.html`, `reminder_policies_home.html`, `alerts_home.html`, `application_communication_history.html`, `candidate_schedule.html`, `candidate_schedule_invalid.html`

**Modified:**
- `rfone_data_store/models.py` — 9 new tables (`AcquisitionSourceDefinition`, `CommunicationTemplate`, `CommunicationTemplateSnapshot`, `CommunicationReminderPolicy`, `CandidateCommunication`, `InterviewSchedulingWindow`, `InterviewAppointment`, `CandidateSchedulingToken`, `InboundCommunication`); `Application` gained nullable `acquisition_source_id`/`acquisition_source_other_text`
- `rfone_data_store/selection/dossier_service.py` — added `CommunicationContext` to `ApplicationDossier`; no existing field changed
- `rfone_data_store/selection_validation.py` — new `_assert_candidate_communication_scheduling` (43 checks), registered in `run_validation()`
- `03 Software/Selection/app.py` — new imports; ~25 new routes; the existing `/applications/<id>/stage` and `/applications/<id>/outcome/apply` routes each gained one additive call into the new communication service *after* their existing `stage_svc.set_stage`/`outcome_svc.apply_outcome` call succeeds
- `templates/dossier.html` — added a Communication/Scheduling section and a `communication_mode` selector on the existing Move-Stage form; `templates/base.html` — 4 new nav tabs

---

## 3. Acquisition Source model

`AcquisitionSourceDefinition`: a restaurant-configurable lookup table (`restaurant_id`, `name`, `description`, `is_active`, `display_order`) — RF-One seeds the task's own example list (Indeed, LinkedIn, Referral, Walk-In, ...) idempotently, but a restaurant may rename/deactivate/add freely. `Application.acquisition_source_id` (+ `acquisition_source_other_text` for the "Other" catch-all) is a plain nullable FK, structurally unrelated to `CandidateCommunication.channel_sms_used`/`channel_email_used` (Communication Channel) and to `Candidate.source` (Task 2A's résumé-*acquisition-mechanism* field, e.g. `LOCAL_UPLOAD` — a different concept entirely).

---

## 4. Communication Template / version model

`CommunicationTemplate`: `restaurant_id`/`location_label`/`role`/`stage` (any of which may be `None` = "any"), `trigger_event` (the fixed vocabulary in `core/communication_model.py`), `outcome_definition_id` (a live FK, populated only for Outcome-triggered events — see §5), `purpose`, `language`, `sms_text`/`email_subject`/`email_body`, `is_active`, `version`, `notes`. Editing bumps `version`; `CommunicationTemplateSnapshot` is an idempotent-per-version immutable copy (mirrors `SelectionOutcomeDefinitionSnapshot` exactly) that every sent `CandidateCommunication` pins to — **verified (check O)**: editing a Template's `sms_text` after a communication was already sent leaves that communication's `rendered_sms_text` byte-for-byte unchanged. Multilingual variants coexist as separate `CommunicationTemplate` rows sharing the same trigger/stage but different `language`; `communication_template_service.find_best_template` picks the most specific match, preferring the requested language and falling back to `"en"` (checks C).

---

## 5. Outbound communication behavior (the trigger mechanism)

Communication is fired from exactly two hook points, both reading a decision the existing authoritative engines already recorded — **never modifying `outcome_service.py` or `stage_service.py` themselves**:

- **`communication_service.on_stage_transition`** — fires only on advancing to `PHONE_INTERVIEW` (mode-dependent: `ADVANCE_TO_PHONE_SCHEDULING`/`ADVANCE_TO_PHONE_CONTACT`, chosen by the Selezionatore via a `communication_mode` form field) or to `IN_PERSON_PRACTICAL` (`ADVANCE_TO_IN_PERSON`).
- **`communication_service.on_outcome_decision`** — looks up `communication_template_service.find_template_for_outcome_event(outcome_definition_id, stage)`: the ONE lookup that lets the SAME restaurant-configured Outcome (e.g. its "Stop") answer to three *different* Templates/trigger-events depending on the Application's Stage at the moment it was applied (Primary Screening Stop vs. Phone Stop vs. In-Person Stop) — verified distinct in check J. If no matching Template is configured, nothing is sent (an honest "not configured yet," never a fabricated default message).

Both hooks are wired into `app.py`'s existing `/applications/<id>/stage` and `/applications/<id>/outcome/apply` routes as one additive call each, right after the pre-existing service call succeeds and before the single commit — so the Selezionatore's ordinary "Move Stage" / "Apply Outcome" action requires no extra Send step.

---

## 6. SMS + Email behavior

`communication_service.send_communication` is the one function every trigger funnels through: it renders `$placeholder`-style text (`string.Template.safe_substitute`, forgiving of an unrecognized placeholder), determines `recipient_phone`/`recipient_email` from the Application's Candidate/Person record, and sends through *both* channels whenever both contact methods exist (checks D/U), or only the available one when one is missing (check E — `sms_status` recorded as `NOT_APPLICABLE`, never a fabricated failure). Delivery goes through `communication_providers.py`'s injectable `SmsProvider`/`EmailProvider` seam; the default `MockSmsProvider`/`MockEmailProvider` record every attempt and always report success — no real SMS/Email credentials are required anywhere in this task (§30).

---

## 7. Reminder / NO RESPONSE behavior

`CommunicationReminderPolicy` (restaurant/branch/role/stage/`trigger_event`-scoped) configures `reminder_count`, `first_reminder_delay_hours`, `reminder_interval_hours`, `final_deadline_hours`, `auto_stop_enabled`, and `auto_stop_outcome_definition_id`. When a trigger with a matching policy is sent, the `CandidateCommunication` row opens a response-tracking cycle (`awaiting_response=True`, `final_deadline_at` computed). `communication_service.process_reminders_and_deadlines` — computed on demand, exactly like the pre-existing `outcome_service.list_due_reminders` convention (no scheduler exists anywhere in this codebase, by design) — sends each configured reminder once due (check Y), takes no action before the deadline (check Z), and, only once every reminder has been sent **and** the deadline has passed **and** no response was recorded **and** `auto_stop_enabled` is explicitly `True`, applies the configured Outcome through the existing, unmodified `outcome_service.apply_outcome(reason="NO RESPONSE", performed_by="SYSTEM_AUTOMATIC_NO_RESPONSE")` (checks AA/AB) — this is the one and only place Task 5D calls `apply_outcome` itself. A late response after this automatic STOP is recorded and linked but never reopens the Application (check AC); it is force-classified `LATE_RESPONSE_AFTER_NO_RESPONSE_STOP` with a mandatory alert (check AD).

---

## 8. Inbound classification model

`inbound_communication_service.classify_inbound_text` is a deterministic, keyword-rule classifier (same honest, non-fabricating convention as `parsing/deterministic_parser.py`) over the fixed vocabulary in `core/communication_model.py` (12 classifications). A message matching more than one distinct rule — genuinely mixed signal — resolves to `AMBIGUOUS_OR_UNCLEAR` rather than guessing (check AG); an unmatched message is `UNCLASSIFIED` at confidence `0.0`. `InboundCommunication.classification_system` is written once and never touched again; `classification_effective` starts equal to it and is the only field a Selezionatore correction (`correct_classification`) changes (check AH). Classification alone never applies/changes/reopens an Outcome (checks AI/AJ, verified directly for DECLINED and WITHDRAWAL) — its only substantive effect is `alert_required` (`core.communication_model.default_requires_alert`, an explicit allow-list of no-alert classifications; everything else, including a brand-new classification added later, defaults to alerting).

---

## 9. Interview Scheduling model

`InterviewSchedulingWindow` (Application-scoped: `interview_stage`, `window_date`, `start_time`/`end_time`, `slot_duration_minutes`, `capacity_per_slot`, `timezone`, `created_by`) — a restaurant may offer any number of windows/days (checks P/Q), not a hard-coded two. `scheduling_service.list_available_slots` derives bookable slots on demand from each active window's own configuration (no separate persisted Slot table). `InterviewAppointment` records one booking; `book_slot` re-checks the slot's confirmed-count against `capacity_per_slot` inside the same call that inserts the new row, rejecting a slot already at capacity (check V) — an adequate guard for this single-process Flask app; a true multi-process deployment would additionally want a DB-level unique/row-lock constraint (see §13). Rescheduling (`reschedule_appointment`) never deletes the prior row — it is marked `RESCHEDULED` and the new row references it via `previous_appointment_id` (check W).

---

## 10. Candidate scheduling page / automatic confirmation

`CandidateSchedulingToken` is an opaque, randomly-generated (`secrets.token_urlsafe`) token that never embeds the internal `application_id` (check R); the public `GET/POST /schedule/<token>` routes in `app.py` resolve it server-side and expose only candidate name, role, restaurant name, and available times. Selecting a slot (`sched_svc.book_slot`) confirms the appointment immediately — no Selezionatore approval — and, inside the same call, invokes `communication_service.send_appointment_confirmation` to send the automatic SMS+Email confirmation (checks S/T/U, verified both at the service layer and through a real Flask `test_client()` HTTP request/response cycle).

---

## 11. Communication History / Dossier integration

`communication_service.list_communications_for_application` returns one chronological (`created_at`, `id`) list spanning every outbound event (initial sends, reminders, confirmations) — check AK. `inbound_communication_service.list_inbound_for_application` gives the matching inbound side. Both are rendered on the new `application_communication_history.html` page. `dossier_service.ApplicationDossier` gained one additive `CommunicationContext` field (latest communication, pending-response/deadline state, current Phone/In-Person appointment, latest inbound, open alerts) — nothing existing in the Dossier was restructured (check AL); `dossier.html` shows this plus a link to the full history page and an inline scheduling-window creation form. Task 5D deliberately does **not** route outbound/inbound communication rows through `selection_notes_service.py`'s unified Notes History — that mechanism is for free-text Selezionatore notes, and a communication's richer structured fields (channel, delivery status, template version) do not fit it; an ordinary Selezionatore note about a communication still goes through the same, unmodified `application_service.add_note`.

---

## 12. Targeted tests and results

**A. Permanent regression suite** (`selection_validation.py::_assert_candidate_communication_scheduling`, 43 checks covering the task's own A-AN letter items, registered in `run_validation()`): fresh SQLite DB, migrations applied through revision `d4a7c1e9f3b6`. **Full suite result: 508/508 checks passed** (465 pre-existing + 43 new) — no regression in Primary Screening, Phone/In-Person Interview, the Outcome Engine, Trainable Gap/Dossier, or Session/Rule Governance (confirming AM-AS).

**B. Flask HTTP-level smoke test** (throwaway DB, real `test_client()` — one-off, not committed): upload → advance to Phone Interview in SCHEDULING mode (auto-sends a communication containing the scheduling link) → create a scheduling window → `GET /schedule/<token>` (200, shows available times) → `POST /schedule/<token>/book` (200, confirms automatically, sends automatic SMS+Email confirmation) → invalid token rejected (404) → Communication History and Dossier pages still render. **15/15 passed.**

**C. Full-navigation regression smoke** (throwaway DB, real `test_client()`): every existing nav page plus the four new ones (Acquisition Sources, Communication Templates, Reminder Policies, Alerts) render 200 with the new imports/nav tabs in place. **17/17 passed.**

---

## 13. Known limitations directly relevant to Task 5D

- **Double-booking guard is application-level, not DB-level.** `book_slot`'s count-then-insert check happens inside one Python call but is not wrapped in a DB-level unique constraint or row lock; correct and sufficient for this single-process Flask app (verified by check V), but a genuinely concurrent multi-process deployment would want an additional DB-level guard.
- **No structured candidate-language-preference field exists anywhere else in Selection.** `Candidate.languages` (Task 2A) is free text describing spoken languages, not a single preferred-communication code; `communication_service._preferred_language` therefore always returns `None`, so every lookup falls back to the restaurant's default-language (`"en"`) Template unless a caller passes `language` explicitly. Multilingual coexistence itself is fully supported and tested (check C) — only the "read the candidate's own preference automatically" half of task §5 is not yet backed by real captured data.
- **No real scheduler/cron exists anywhere in this codebase (by design, mirroring the pre-existing `outcome_service.list_due_reminders` convention).** `communication_service.process_reminders_and_deadlines` is computed on demand; a real deployment would call the new `POST /admin/process-reminders` route periodically (an external cron), exactly as the task's own §16 "no separate Event Engine" framing anticipates.
- **No real SMS/Email provider is wired up** (task's own explicit non-requirement, §30) — `communication_providers.MockSmsProvider`/`MockEmailProvider` record every attempt and always report success; a real provider implements the same two-method interface and is swapped in via `set_sms_provider`/`set_email_provider`.
- **Inbound classification is a real, deterministic keyword classifier, not an AI model** — consistent with never fabricating confidence and with not requiring external credentials; it correctly resolves genuinely mixed signals to `AMBIGUOUS_OR_UNCLEAR` (check AG) but will not catch phrasing outside its keyword rules (falls through to `UNCLASSIFIED`, always visibly alerted, never silently misread as a confident classification).
- **Interview Scheduling Windows are Application-scoped**, matching the task's own worked example ("the Selezionatore offers two consecutive days... for one Application's Phone or In-Person interview"); a shared pool of slots offered across many candidates for the same Session/role was judged out of the stated scope and was not built.
