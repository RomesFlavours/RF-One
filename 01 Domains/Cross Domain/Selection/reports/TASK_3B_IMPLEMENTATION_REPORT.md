# TASK 3B — Evidence-Based Candidate Fit Assessment: Implementation Report

## 1. What I implemented

An evidence-based Candidate Fit Assessment that answers "for this candidate, against this exact immutable Requirement Set snapshot, what evidence do we currently have regarding each Requirement?" Every assessment is created against an immutable `RequirementSetSnapshot` (Task 3A-FIX) — never live `Requirement` rows — with one `RequirementAssessment` per active `RequirementSnapshotItem`, each carrying zero-or-more append-only `EvidenceItem`s. A conservative, keyword-based résumé matcher generates the first (résumé-stage) evidence automatically; humans can add evidence, confirm, or override. No score, ranking, or hiring decision is produced anywhere.

## 2. Main files changed

- New: `rfone_data_store/selection/core/fit_assessment_model.py` (vocabulary + `compute_status_from_evidence()`)
- New: `rfone_data_store/selection/resume_evidence_matcher.py` (résumé-stage evidence generation)
- New: `rfone_data_store/selection/fit_assessment_service.py` (service layer)
- New: migration `e5a1c8d3f6b2_add_selection_fit_assessment.py` (+3 tables)
- Extended: `models.py` (+`FitAssessment`, `RequirementAssessment`, `EvidenceItem`), `03 Software/Selection/app.py` (+9 routes), `templates/base.html`, `templates/detail.html`, new `templates/fit_assessment_detail.html`
- Extended: `rfone_data_store/selection_validation.py` (+24 checks, `_assert_fit_assessment`)
- **Bug fix in existing Task 3A code**, required for correctness (see §13): `requirements_service.add_requirement()`'s `display_order` auto-numbering and `create_requirement_set_snapshot()`'s item-copying both used to read the `RequirementSet.requirements` ORM relationship, which goes stale in-memory once loaded (a sibling `Requirement` added afterward via a raw FK column never updates an already-loaded collection). Both now use a fresh, explicit `SELECT` instead. This was silently masked in earlier Task 3A/3A-FIX tests (which always happened to call `session.expire_all()` first) but broke Fit Assessment creation outright until fixed.

## 3. Fit Assessment persistence model

`FitAssessment`: `candidate_id`, `requirement_set_snapshot_id` (authoritative), `requirement_set_id` (denormalized, navigation only), `current_stage`, `status`, `notes` (plain, never evidence), timestamps. `RequirementAssessment`: the fundamental Candidate × RequirementSnapshotItem unit (unique per pair), with `stage`, `system_status`, `effective_status`, `confidence`, `notes`, `origin`, `override_reason`/`overridden_at`. `EvidenceItem`: append-only (no `updated_at` — never edited or deleted), `source_type`/`source_stage`/`source_reference`, `evidence_text`, `evidence_classification`, `evidence_relationship`, `confidence`, `explanation`, `is_system_generated`.

## 4. Immutable Requirement snapshot integration

`create_fit_assessment()` calls `requirements_service.create_requirement_set_snapshot()` — reusing Task 3A-FIX's existing, idempotent-per-version mechanism — before creating any assessment rows; `create_fit_assessment_from_snapshot()` is the underlying primitive both it and a future direct-snapshot path share. Every `RequirementAssessment` reads its Requirement's name/criticality/trainability/stages/guidance from the snapshotted `RequirementSnapshotItem`, never from live `Requirement` rows — verified directly (checks 3B-E/F): renaming/re-criticality-ing a live Requirement after assessment creation leaves the assessment showing the original values.

## 5. Requirement-level statuses

`EVIDENCED`, `PARTIALLY_EVIDENCED`, `NOT_EVIDENCED`, `CONFLICTING_EVIDENCE`, `NOT_ASSESSED_AT_THIS_STAGE` — computed by one reusable pure function, `compute_status_from_evidence()`: both SUPPORTS and CONTRADICTS evidence present → CONFLICTING_EVIDENCE; only CONTRADICTS → NOT_EVIDENCED (no "disproven" status exists); SUPPORTS with a HIGH-confidence item → EVIDENCED; SUPPORTS only at lower confidence → PARTIALLY_EVIDENCED; nothing → NOT_EVIDENCED. `NOT_ASSESSED_AT_THIS_STAGE` is never produced by this function — it is set directly, with zero evidence gathered, whenever the current stage isn't in the Requirement's permitted stages, keeping the two statuses structurally distinct everywhere.

## 6. Evidence/source/confidence model

Source types: `RESUME_FACT`, `RESUME_DERIVED_INFORMATION`, `PHONE_INTERVIEW_RESPONSE`, `IN_PERSON_OBSERVATION`, `PRACTICAL_ASSESSMENT_RESULT`, `REFERENCE_CHECK`, `HUMAN_NOTE`, `OTHER` (only the first two are actually produced by Task 3B itself). Classification: `FACT` / `DERIVED_INFORMATION` / `INFERENCE` — the résumé matcher uses FACT for direct structured matches (a skill, a certification), DERIVED_INFORMATION for calculated tenure (reusing Task 2B's `work_entry_duration_months()`), and INFERENCE for free-text-only matches. Relationship: `SUPPORTS`/`CONTRADICTS`/`NEUTRAL`. Confidence: `HIGH`/`MEDIUM`/`LOW`/`UNKNOWN` (same values as Task 2B's date/role normalization convention).

## 7. Assessment-stage enforcement

Enforced in exactly one place: `fit_assessment_service.generate_resume_stage_assessment()` checks `RESUME in item.assessment_stages` before doing anything; if not present, the Requirement is set `NOT_ASSESSED_AT_THIS_STAGE` with zero evidence gathered — the matcher (`resume_evidence_matcher.py`) is never even called. Behavioral/personality categories (Attitude/Behavioral Traits, Teamwork, Trainability/Learning, Accountability/Work Ethic) get an additionally conservative path even when RESUME is configured: only the résumé's own self-descriptive text (`summary`/`other_sections_text`) is considered, never job titles, tenure, or responsibilities, and confidence is capped below HIGH so a match is at best PARTIALLY_EVIDENCED.

## 8. Resume-stage assessment behavior

`resume_evidence_matcher.py` dispatches by Requirement category to targeted matchers: work history (title/normalized role/role family/seniority/employer, plus a duration calculation reusing Task 2B's helpers), skills, certifications (including `education.certifications`), languages, education, declared availability, and the conservative behavioral matcher. A structured-field match yields FACT/HIGH-confidence (→ EVIDENCED); a free-text-only match yields INFERENCE/MEDIUM (→ PARTIALLY_EVIDENCED); no match yields nothing (→ NOT_EVIDENCED). Verified against a real résumé: an explicit certification became EVIDENCED, a duty mentioned only in free-text responsibilities became PARTIALLY_EVIDENCED, an entirely absent skill became NOT_EVIDENCED, and a phone-interview-only Rome's Flavours attitude trait stayed NOT_ASSESSED_AT_THIS_STAGE.

## 9. Human/system assessment + notes/override behavior

Origins: `SYSTEM_GENERATED` (default), `HUMAN_ENTERED`, `HUMAN_CONFIRMED`, `HUMAN_OVERRIDDEN`. `add_evidence()` always recomputes `system_status`, but only updates `effective_status` when `origin` is still `SYSTEM_GENERATED` — any human touch locks `effective_status` from further automatic changes. `human_confirm()` sets `origin=HUMAN_CONFIRMED` without changing `effective_status`. `human_override()` sets a new `effective_status`, records `origin=HUMAN_OVERRIDDEN`, `override_reason`, `overridden_at` — and never touches `system_status`, which stays exactly what the system last computed. Plain notes (`add_note()`, on either the Fit Assessment or one Requirement Assessment) are a separate text field, never converted into an `EvidenceItem` and never read by `compute_status_from_evidence()` — verified directly (check 3B-S).

## 10. Reassessment / refresh behavior

`generate_resume_stage_assessment()` doubles as the refresh entry point: it deletes and regenerates only `is_system_generated=True` evidence, leaving human-added evidence untouched, and only auto-updates `effective_status` for Requirements still `SYSTEM_GENERATED`. It always operates against the Fit Assessment's already-bound snapshot — never a newer live version (verified: check 3B-V). Adding evidence for a later stage (e.g. `PHONE_INTERVIEW`) to an existing assessment naturally flips a `NOT_ASSESSED_AT_THIS_STAGE` Requirement to a real status through the same generic recompute path, with the earlier stage's evidence (if any) preserved alongside it. Assessing the same candidate against a newer Requirement Set version always creates a **new** `FitAssessment` bound to a **new**, higher-version snapshot — the historical one is left completely unchanged (verified: check 3B-W).

## 11. UI/API added

Candidate detail page: a "Fit Assessments" card listing existing assessments and a form to create one against any active Requirement Set. New `/fit-assessments/<id>` page: snapshot version/creation-date banner, counts-only summary (never a score), and one card per Requirement Assessment showing name/category/criticality/trainability/permitted stages/current stage/status/confidence/evidence (with source, classification, relationship)/origin/guidance (collapsible), plus forms to add evidence, confirm, override, and set notes. Nine new Flask routes, all delegating to `fit_assessment_service.py`.

## 12. Targeted tests performed and results

- `python test_selection_engine.py` (`selection_validation.py`, incl. new `_assert_fit_assessment`): **100/100 checks passed** (76 pre-existing Task 2A/2B/3A/3A-FIX checks + 24 new Task 3B checks A through W, covering creation, automatic snapshot binding, requirement coverage, live-edit immutability, EVIDENCED/PARTIALLY_EVIDENCED/NOT_EVIDENCED/CONFLICTING_EVIDENCE/NOT_ASSESSED_AT_THIS_STAGE, evidence source/classification/confidence preservation, criticality/trainability exposure without auto-decision, no-score verification, multi-evidence coexistence, notes-never-become-evidence, human override distinguishability, later-stage evidence addition, refresh-retains-snapshot, and newer-version-creates-new-assessment).
- `python test_batch_upload.py`: **19/19 checks passed** — confirms Task 2A/2B résumé pipeline unaffected.
- Full manual smoke test through the real Flask app (`test_client`): résumé upload → candidate detail → create Requirement Set → create Fit Assessment → view detail page → confirm/override/add-evidence/add-note/refresh, all verified working with correct persisted state.
- Full Alembic migration chain verified to apply cleanly through the new head revision on a fresh database.

## 13. Known limitations directly relevant to Task 3B

- The résumé matcher is deliberately simple keyword overlap, not NLP/AI — it can miss synonyms or paraphrased requirement wording; when it misses, the result is the conservative `NOT_EVIDENCED`, never a fabricated `EVIDENCED`.
- `RequirementAssessment.confidence` is a rollup (highest confidence among its SUPPORTS/CONTRADICTS evidence) for display convenience; individual evidence items keep their own confidence regardless.
- A discovered-and-fixed pre-existing Task 3A bug (§2) means any code elsewhere in Selection that still reads `RequirementSet.requirements` after adding a sibling Requirement in the same session (without an intervening `session.expire_all()`) could still exhibit the same staleness outside the two call sites fixed here — none currently do, but it is a pattern worth remembering if new code touches that relationship.
- No candidate-facing summary beyond the plain counts table exists — by design, per the task's explicit "no universal score" instruction.
