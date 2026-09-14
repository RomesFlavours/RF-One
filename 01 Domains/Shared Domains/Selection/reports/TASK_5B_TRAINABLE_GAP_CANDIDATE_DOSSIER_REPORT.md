# TASK 5B — Trainable Gap + Operational Candidate Dossier — Implementation Report

**Status:** Complete
**Scope:** Selection Domain runtime (`03 Software/Selection/`, `03 Software/RF-One Data Store/rfone_data_store/selection/`) — no file outside Selection was touched.

---

## 1. What was implemented

**Part A — Trainable Gap.** A new, persistent `TrainableGap` entity tied to Application / Candidate / Fit Assessment / Requirement Assessment, carrying an RF-One-proposed 0–4 initial level and an optional Selezionatore-corrected level, with mandatory-reason-on-divergence enforcement and no automatic effect on workflow, Stage, Outcome, or Training. Reuses the existing Requirement trainability vocabulary (TRAINABLE/PARTIALLY_TRAINABLE/NOT_TRAINABLE/UNKNOWN) — no duplicate vocabulary was created.

**Part B — Operational Candidate Dossier.** One new Application-centric page (`/applications/<id>/dossier`) aggregating Primary Screening (qualitative only), Evidence Summary, Trainable Gaps + non-trainable concerns, Interview journey (Phone/In-Person/Consistency), Decision/Outcome history, Information/Events, candidate/Application history, and a chronological All-Notes feed — with per-section Edit/pencil controls opening native `<dialog>` modals that post to the existing authoritative service routes (no business logic in the Dossier route or template).

---

## 2. Main files changed

**New:**
- `rfone_data_store/models.py` — `TrainableGap` ORM model (appended; also added to `ALL_MODELS`)
- `rfone_data_store/selection/core/trainable_gap_model.py` — vocabulary (0–4 scale, eligibility rules, status)
- `rfone_data_store/selection/trainable_gap_service.py` — generation, retrieval, Selezionatore review, notes
- `rfone_data_store/selection/dossier_service.py` — pure aggregator for the Dossier page
- `migrations/versions/f2a7c4e9b1d6_add_selection_trainable_gap.py` — one additive table, revises `33c870767fef` (current head)
- `03 Software/Selection/templates/dossier.html` — the Dossier page
- `01 Domains/Selection/reports/TASK_5B_TRAINABLE_GAP_CANDIDATE_DOSSIER_REPORT.md` — this report

**Modified:**
- `rfone_data_store/selection_validation.py` — new `_assert_trainable_gap_dossier` section (22 checks), registered in `run_validation()`
- `rfone_data_store/selection/selection_notes_service.py` — added `"TRAINABLE_GAP": "Trainable Gap"` to the existing context-label map (no new notes mechanism)
- `03 Software/Selection/app.py` — new imports; new `application_dossier` and `trainable_gap_review` routes; added `next`-redirect support to `application_add_note_entry` and `primary_screening_override_hard_disqualifier` (mirrors the pattern already used by `application_set_stage`/`application_apply_outcome`)
- `03 Software/Selection/templates/base.html` — CSS only: pencil-button/`<dialog>` modal styling, Trainable Gap level badges
- `03 Software/Selection/templates/application_detail.html` — one link to "Open Candidate Dossier"

No existing route, service function, or template section was redesigned or removed.

---

## 3. Trainable Gap model

`TrainableGap` (one row per `RequirementAssessment`, unique-constrained) preserves: `application_id`/`candidate_id`/`fit_assessment_id`/`requirement_assessment_id` (the last is authoritative and reaches the exact Requirement Snapshot Item / Requirement Set Snapshot via join — no extra denormalized snapshot pointer was needed); `missing_capability`, `trainability`, `source_fit_status`, `importance` (denormalized, immutable copies taken at creation, so a later live-Requirement edit can never retroactively rewrite what the gap meant); `rf_one_initial_level`, `selezionatore_initial_level`, `effective_initial_level`, `confidence`; `origin`/`override_reason`/`overridden_at`/`overridden_by`; `status` (ACTIVE/WITHDRAWN — lifecycle only, never a Training-progress status).

Eligibility: a gap is created only where `effective_status` is `NOT_EVIDENCED`/`PARTIALLY_EVIDENCED` **and** trainability is `TRAINABLE`/`PARTIALLY_TRAINABLE`. `NOT_TRAINABLE` gaps are never converted — they surface separately as a derived (non-persisted) "non-trainable concern" list, exactly mirroring how `decision_service.py` already treats such derived summaries. `generate_trainable_gaps_for_fit_assessment()` is idempotent: it never duplicates a row for a `RequirementAssessment` that already has one, and separately withdraws (status only, never levels) a gap whose evidence has since moved to `EVIDENCED`.

No target level, curriculum, Training Step/Check, or Autonomy Level field exists anywhere on the model — verified structurally in tests (TG-H / 5B-TG-H).

---

## 4. RF-One vs. Selezionatore Initial Level behavior

`rf_one_initial_level` is set once at creation (`propose_initial_level()`, a small documented heuristic based on evidence status/confidence) and is **never** written again by any code path. `trainable_gap_service.set_selezionatore_level()`:
- If the chosen level **equals** RF-One's: no duplicate value is stored (`selezionatore_initial_level` stays `None`), `origin` becomes `HUMAN_CONFIRMED`, no reason required.
- If it **differs**: a non-empty `reason` is mandatory (`ValueError` otherwise, mirroring `primary_screening_service.override_hard_disqualifier`'s strict enforcement combined with `outcome_service.apply_outcome`'s change-detection semantics); `selezionatore_initial_level`, `origin=HUMAN_OVERRIDDEN`, `override_reason`, `overridden_at`, `overridden_by` are set, and `effective_initial_level` becomes the Selezionatore's level.

`rf_one_initial_level` is verified unchanged after both agreement and override in both the standalone smoke test and the permanent validation-suite checks.

---

## 5. Dossier structure

Header (identity, role, applied date, Stage, Outcome, open reminders, repeated-applicant indicator, Training-Check-history banner, Open Original CV) → Primary Screening (positive/negative factors, Hard Disqualifier + override control, unresolved/insufficient — **no** Priority Index or score) → Evidence Summary (strong/weak/conflicting/unresolved + Signals) → Trainable Gaps (with levels/edit) + non-trainable concerns → Interview Journey (Phone/In-Person status + incomplete counts, Consistency items-to-verify, links to full detail) → Decision & Outcome (apply/reopen/move-stage + history table) → Information/Events (record form, visibly distinct from Decisions) → Candidate History (prior Applications, Training-Check flags, other active flags) → All Notes (full chronological feed at the bottom).

`dossier_service.get_application_dossier()` is a pure aggregator: it calls `decision_service.get_decision_summary()`, `selection_notes_service.get_selection_notes_history()`, `application_service.list_prior_applications()`, `candidate_flag_service`, `primary_screening_service.list_evaluations()`, `phone_interview_service`/`in_person_interview_service` getters, and the new `trainable_gap_service` — it computes nothing new about candidate suitability itself.

---

## 6. Modal / Edit behavior

No modal infrastructure existed anywhere in this codebase before this task (confirmed by search — no `<dialog>`, no JS framework). The Dossier introduces a small, consistent pattern: each editable section has a pencil button (`onclick="...showModal()"`) opening a native `<dialog class="edit-modal">` containing a plain `<form method="post">` — no AJAX/JSON, no framework, consistent with the app's existing "no build step" convention. Every modal form posts to an **existing** authoritative route/service function (`application_set_stage`, `application_apply_outcome`/`reopen`, `application_record_information_event`, `application_add_note_entry`, `primary_screening_override_hard_disqualifier`) or the new `trainable_gap_review` route — none duplicate business logic; all follow the codebase's established "thin route → service function → commit/rollback → redirect" discipline. A `next` hidden field routes the redirect back to the Dossier; three existing routes already supported `next` (used unchanged), and `next` support was added to the two that didn't (`application_add_note_entry`, `primary_screening_override_hard_disqualifier`) as a minimal, additive change.

---

## 7. Notes / history behavior

Trainable Gap notes reuse the unified `ApplicationNote` mechanism (`context_type="TRAINABLE_GAP"`) — no new notes table. The Dossier's bottom "All Notes" section calls `selection_notes_service.get_selection_notes_history()` unchanged, so it automatically includes Trainable Gap notes alongside every other stage's notes, chronologically. Information/Events render through the same unified notes history but remain visually and structurally distinct from Decisions (their own "Information / Events" section plus the existing `[event_type]`-prefixed formatting in the notes feed). All governance rules (mandatory reason on Outcome change, mandatory reason on Hard Disqualifier override, mandatory reason on Trainable Gap level divergence) are enforced only in the service layer, identically whether triggered from the Dossier or from any existing screen.

---

## 8. Integration with Primary Screening / Fit / Interviews / Consistency / 5A

Nothing in Tasks 2A–5A/FIX/MICRO-FIX was modified beyond the two additive `next`-support edits above. The Dossier's Primary Screening section deliberately never reads or renders `PrimaryScreeningRun.priority_index`. The Decision/Outcome section is the same `decision_service.get_decision_summary()` object the existing Decision Summary screen uses — not a parallel computation. Interview/Consistency summaries only read plan status, incomplete-item counts, and `CONSISTENCY_ITEMS_TO_VERIFY_STATUSES`-filtered threads; full detail remains on the existing Phone/In-Person/Consistency screens, linked from the Dossier.

---

## 9. Targeted tests and results

Two layers of testing were run (this environment has no pre-configured Python install with dependencies; a scratch virtualenv was created solely to execute these):

**A. Standalone end-to-end smoke test** (fixtures + real Flask app via `test_client()`, against a fresh scratch SQLite DB, migrated to head): all 39 checks passed, covering items A–H, C/D/E/F/G, I/J/K/L/M/N/O/P/Q/R/T/V/W, X (mandatory-reason enforcement through the actual HTTP route), and AB/AE (existing screens still render). Confirmed no numeric score/percentage and no `priority_index` in the rendered page.

**B. Permanent addition to the codebase's own regression suite** (`selection_validation.py::_assert_trainable_gap_dossier`, registered in `run_validation()`): 22 new checks (5B-TG-A through 5B-TG-K2, 5B-DOSSIER-A through E) covering gap creation/eligibility, non-trainable-concern separation, RF-One-level immutability, agree/override/reject-without-reason, idempotent regeneration, evidence-closing withdrawal without level mutation, and Dossier aggregation including cross-Application Training-Check-history surfacing.

**C. Full existing suite re-run**, fresh DB, migrations applied through the new revision: **427/427 checks passed** (405 pre-existing + 22 new), confirming AF (no regression) and AB/AC/AD/AE (Primary Screening, Phone, In-Person, 5A Outcome/Decision Engine all still operational).

The one pre-existing `SAWarning` (a `confirm_deleted_rows` notice from an unrelated 4A cleanup block) is unchanged from before this task and was not introduced by it.

---

## 10. Known limitations directly relevant to Task 5B

- `propose_initial_level()`'s RF-One heuristic is intentionally simple (status + confidence only) and documented as illustrative — a restaurant/product may want to refine it later without changing the persisted 0–4 scale's meaning.
- The Dossier's Primary Screening positive/negative grouping uses each Criterion's configured `direction` as a proxy; it does not re-derive a qualitative judgment beyond what `primary_screening_detail.html` already shows.
- Per the app's existing convention (no `flash()` mechanism anywhere), a rejected mandatory-reason submission (Trainable Gap, Outcome, Hard Disqualifier) redirects back to the Dossier silently rather than showing an inline error — this is the same known, pre-existing UX limitation documented in the Task 5A-MICRO-FIX report, not something newly introduced here.
- Restaurant/location context is not shown in the Dossier header because no template in this single-client demo app currently surfaces it either (`Application.restaurant_id` has no loaded `restaurant` relationship) — consistent with existing screens, not a regression.
