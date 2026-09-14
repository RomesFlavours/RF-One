# TASK 5C — Selection Session + Application Ownership + Rule Governance — Implementation Report

**Status:** Complete
**Scope:** Selection Domain runtime (`03 Software/Selection/`, `03 Software/RF-One Data Store/rfone_data_store/selection/`) — no file outside Selection was touched.

---

## 1. What was implemented

A first-class **Selection Session** — the operational container for selecting candidates for ONE role — carrying multiple Selezionatore assignments with optional configurable authority/dependency; **Application ownership** (explicit "take in charge," read-only for non-owners, reassignment by the owner or a strictly-superior authority, with mandatory reason and full history); a **Rule Set confirmation gate** that blocks all candidate operational work until explicitly reviewed and confirmed; and **Rule Change governance** during an ACTIVE Session, with an explicit SUBSEQUENT_ONLY vs. ENTIRE_SESSION scope, versioned Rule Set history, and safe, non-silent handling of retroactively-impacted Applications.

---

## 2. Main files changed

**New:**
- `rfone_data_store/models.py` — six new tables (`SelectionSession`, `SelectionSessionAssignment`, `ApplicationOwnership`, `SelectionRuleSetVersion`, `SelectionRuleChange`, `SelectionRuleChangeImpact`); `Application` gained nullable `session_id`/`rule_set_version_id`; `ApplicationNote.application_id` widened to nullable with a new `session_id` so the same unified notes table also carries Session-level notes
- `rfone_data_store/selection/core/session_model.py`, `core/rule_set_model.py` — status/scope vocabulary
- `rfone_data_store/selection/session_service.py`, `rule_set_service.py`, `rule_change_service.py`, `ownership_service.py`
- `migrations/versions/a1c4e7b9d2f5_add_selection_session_ownership_rule_governance.py`
- `03 Software/Selection/templates/sessions_home.html`, `session_detail.html`
- This report

**Modified:**
- `rfone_data_store/selection_validation.py` — new `_assert_session_ownership_rule_governance` (38 checks), registered in `run_validation()`
- `rfone_data_store/selection/dossier_service.py` — added `SessionContext` (Session/owner/Rule-Set-version/Rule-Change-impact) to `ApplicationDossier`; no existing field changed
- `03 Software/Selection/app.py` — new imports; new Session/Rule-Set/Rule-Change/Ownership routes; a bounded ownership guard added to 5 existing operational-mutation routes (`application_apply_outcome`, `application_reopen`, `application_set_stage`, `primary_screening_override_hard_disqualifier`, `trainable_gap_review`)
- `templates/dossier.html` — added a Session/Ownership section; added `actor` fields to existing Outcome/Stage/Hard-Disqualifier/Trainable-Gap modals
- `templates/decision_summary.html`, `templates/primary_screening_detail.html` — added `actor` fields to the corresponding existing forms
- `templates/application_detail.html` (5B), `templates/base.html` — a "Sessions" nav tab and Task 5C badge/modal CSS

No existing Primary Screening, Fit Assessment, Phone/In-Person Interview, Consistency, Outcome Engine, Trainable Gap, or Dossier logic was redesigned.

---

## 3. Selection Session model

`SelectionSession`: name, restaurant_id, `location_label`, a single `target_role` (never multi-role — enforced structurally, one column, no list), start/planned-end/actual-close dates, `status` (DRAFT/RULES_REVIEW/ACTIVE/PAUSED/CLOSED, a permissive lifecycle mirroring `stage_service`'s "total freedom" philosophy — not a strict state machine), `created_by`, a legacy single-value `notes` convenience field, and `current_rule_set_version_id` (a convenience pointer, never the sole record of truth — full version history always lives in `SelectionRuleSetVersion`). A Session is "operationally usable" only when `status == ACTIVE` **and** its current Rule Set version carries a recorded confirmation — `session_service.assert_operational()` is the one gate every operational entry point checks.

---

## 4. Selezionatore assignment / authority model

`SelectionSessionAssignment` links a plain identifying string (`selezionatore_name` — the same honest, no-auth-system placeholder convention every `performed_by`/`created_by` field in this codebase already uses) to a Session, with an optional `authority_level_id`. Authority reuses the **existing** `SelectionAuthorityLevel`/`governance_service.py` (from the Selection Feedback Intelligence Foundation task) rather than inventing a parallel hierarchy — satisfying task §32's explicit "reuse existing Task 5A authority structures." Two assignments with no configured level are peers; comparison is by `level_order` only, never a hard-coded title.

---

## 5. Application ownership model

`ApplicationOwnership` is an append-only history table (exactly one `is_active=True` row per Application, enforced in the service layer — the same "current = latest row" discipline `SelectionOutcomeDecision` already established). `take_in_charge()` is the one explicit claiming action (never implied by viewing read-only) and requires the Session to be operational. `reassign()` requires a non-empty reason and closes the previous row (`is_active=False`, `ended_at` set) before creating a new one referencing it via `previous_ownership_id` — nothing is ever overwritten.

---

## 6. Read-only / reassignment behavior

`ownership_service.can_write()`: an Application not linked to a Session, or with no claimed owner, is unrestricted (Task 5C is additive governance, never a retroactive lock). Once owned, only the current owner may write. `can_reassign()`: the current owner may always reassign; otherwise the requester needs a **strictly higher** configured `level_order` than the current owner within that Session — undefined/equal authority on either side means peers, and a peer can never reassign another's Application (verified: current owner ✓, superior ✓, peer ✗, inferior-over-superior ✗).

**Enforcement scope (deliberately bounded, not a broad refactor):** `assert_can_operate()` was wired into exactly the operational-mutation routes the task itself names as examples — Outcome apply/reopen, Hard Disqualifier override, Stage change, and Trainable Gap review — all of which already had (or, for two of them, gained) an `actor` field on their existing Dossier/Decision-Summary/Primary-Screening forms. Granular per-question Phone/In-Person interview-answer routes (a large, separate surface area) were **not** retrofitted, to honor "Do NOT redesign Phone Interview or In-Person/Practical" and "Do NOT perform broad architecture refactors" — see Known Limitations.

---

## 7. Rule Set confirmation gate

`SelectionRuleSetVersion` folds confirmation directly onto the version row (`confirmed_by`/`confirmed_at`/`confirmation_note` — a version is confirmed at most once, by one person, at one time; re-confirming an already-confirmed version is rejected). `rule_set_service.confirm_rule_set_version()` activates the Session (`status = ACTIVE`) as a side effect, mirroring `outcome_service.apply_outcome` setting `lifecycle_state`. Before confirmation, Session/Selezionatore/Rule-Set preparation (including linking Applications) remains allowed; `take_in_charge` and the five guarded mutation routes are blocked — verified via both the service layer and a real HTTP POST through the guarded route.

---

## 8. Rule Set versioning

`build_rule_set_version()` creates one new, immutable envelope per call and advances the Session's `current_rule_set_version_id`. It captures **fresh immutable snapshots** of the Requirement Set (`requirements_service.create_requirement_set_snapshot`) and each referenced Primary Screening Criterion (`primary_screening_service.get_or_create_criterion_snapshot`) at build time; Signals, the Review Priority Policy, Outcome Definitions, and Phone/In-Person question/section definitions are referenced by live id (no snapshot mechanism exists yet for those — an honestly-scoped limitation, not silently duplicated data either). `Application.rule_set_version_id` is stamped once, at `link_application_to_session` time, and is never rewritten afterward.

---

## 9. Subsequent-only Rule Change behavior

`propose_rule_change(scope=SUBSEQUENT_ONLY)` creates a new version and a `SelectionRuleChange` event, advances the Session pointer — and does nothing else. Already-linked Applications keep the `rule_set_version_id` they were stamped with; only Applications linked **after** this point receive the new version (verified: the prior Application's version is unchanged; a newly-linked Application gets the new version).

---

## 10. Entire-Session Rule Change behavior

`propose_rule_change(scope=ENTIRE_SESSION)` additionally queries every Application in the Session whose `rule_set_version_id` differs from the brand-new version and creates one `SelectionRuleChangeImpact` row each. Where a Fit Assessment exists, the existing, idempotent `fit_assessment_service.generate_resume_stage_assessment` is re-run as the safe "deterministic component" (task's own allowed action) — it already never overwrites a human-touched `effective_status` by its own pre-existing design, so a human decision is never silently changed. `recalculation_status` records what happened; `review_status` **always** starts `NEEDS_REVIEW` and only ever advances via an explicit `mark_impact_reviewed()` action — verified that no Outcome/lifecycle/Stage is ever touched automatically.

---

## 11. Application Rule-version traceability

`Application.rule_set_version_id` answers "which version applied when first screened"; `SelectionRuleChangeImpact` rows (queryable per-Application) answer "was this later affected by a retroactive change, and what happened"; `SelectionRuleSetVersion`/`SelectionRuleChange` (never deleted, `created_from_version_id` chains them) answer "what changed between versions" and keep every historical version available. The Dossier's new `session_context` surfaces all of this in one place per Application.

---

## 12. Next-Session Rule inheritance

`session_service.create_session()` auto-detects the most recent prior Session for the same restaurant/role (preferring one whose Rule Set was actually confirmed) and seeds version 1 via `rule_set_service.create_initial_version(seed_from_version_id=...)`, which resolves the prior version's snapshot references back to live ids and re-snapshots them fresh — the **complete current** configuration, not the original pre-Session rules. The new version is never pre-confirmed; every Session, including one seeded this way, must still go through its own explicit Rule Review → Confirmation → ACTIVE.

---

## 13. Dossier / UI integration

The Dossier gained one additive section (Session, role, location, applicable Rule Set version, Rule-Change-impact flag, current owner + Take-In-Charge/Reassign modals) — nothing existing was restructured. `sessions_home.html` (list: name, role, location, status, dates, Application/owned counts, Rule Set version, assigned Selezionatori) and `session_detail.html` (header, Selezionatori + authority, Rule Review with Requirements/Criteria/coefficients/directions/level-definitions/Hard-Disqualifiers/Signals, pre-confirmation edit + Confirm action, Rule Change proposal form, impacts-needing-review list, Rule Change history, linked Applications with owner, Session notes) cover the required minimums.

---

## 14. Targeted tests and results

Three layers, all against a scratch venv created solely for this session (no pre-existing Python environment was available):

**A. Service-layer smoke test** (37 checks) — Session/assignment creation, peer-vs-hierarchy reassignment authorization, the confirmation gate, SUBSEQUENT_ONLY/ENTIRE_SESSION mechanics, and next-Session Rule inheritance, all directly against `session_service`/`rule_set_service`/`rule_change_service`/`ownership_service`.

**B. Flask-level smoke test** (24 checks) — the same governance driven through real HTTP routes via `test_client()`: Session list/detail/create, link-Application, confirm-then-take-in-charge, the ownership guard blocking a non-owner's Outcome-apply and permitting the owner's, peer-vs-owner reassignment, a Rule Change through its route, and confirmation that Primary Screening/Phone/In-Person/Decision-Summary/Application-Detail pages still render.

**C. Permanent addition to the codebase's own regression suite** (`selection_validation.py::_assert_session_ownership_rule_governance`, 38 checks, registered in `run_validation()`), covering items A through AH from the task's own list at the service layer.

**D. Full existing suite re-run**, fresh DB, migrations applied through the new revision: **465/465 checks passed** (427 pre-existing including Task 5B's own 22 + 38 new), confirming AI/AJ/AK/AL/AM/AN — no regression in Primary Screening, Phone Interview, In-Person/Practical, the 5A Outcome Engine, or Task 5B's Trainable Gap/Dossier (the 5B smoke test was independently re-run and still passes in full).

---

## 15. Known limitations directly relevant to Task 5C

- The ownership write-guard is wired into 5 named operational-mutation routes (Outcome apply/reopen, Hard Disqualifier override, Stage change, Trainable Gap review) — the architecturally significant decision/evaluation surfaces — but not into the many granular per-question Phone/In-Person interview-answer routes, to avoid a broad retrofit of pages explicitly protected from redesign. `ownership_service.assert_can_operate()` is reusable and ready for that follow-up.
- No signed-in "current Selezionatore" concept exists anywhere in this app (confirmed absence pre-5C); the guarded forms collect an `actor` free-text field, the same honest placeholder pattern the rest of the codebase uses for `performed_by`. `primary_screening_detail.html`'s own evaluation-enter/override/confirm forms do not yet collect this field, so those specific mutations on a Session-owned Application are correctly blocked by the new guard but have no in-page way to act as the owner — use the Dossier's equivalent controls until a follow-up adds the same field there.
- Signals, the Review Priority Policy, Outcome Definitions, and Phone/In-Person question/section definitions are referenced in a Rule Set version by live id, not an immutable snapshot (none exists yet for those) — noted explicitly in `SelectionRuleSetVersion`'s own docstring as an honestly-scoped gap, not silently duplicated data.
- ENTIRE_SESSION recalculation currently only refreshes résumé-stage Fit Assessment evidence (the one existing, safe, idempotent, non-decision-overwriting mechanism available); it does not attempt to recompute Primary Screening or re-evaluate Hard Disqualifiers automatically — those remain `PENDING`/flagged for the Selezionatore's own review, consistent with "must not silently decide."
