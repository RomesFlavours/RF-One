# TASK 3C — Selection Signals + Review Priority: Implementation Report

*Implemented from the "RF-One Selection 3C Concept Note — Selection Signals + Review Priority," at the user's explicit direction to implement it now, following the same patterns established in Tasks 2A/2B/3A/3A-FIX/3B.*

## 1. What I implemented

A REVIEW PRIORITY framework that helps a Selezionatore decide which Applications to look at first — never a ranking, never an automatic discard. Three pieces: (1) a genuine CANDIDATE (person) vs APPLICATION (one submission) distinction, so application history is visible and usable; (2) a restaurant-configurable Selection Signal framework (mirroring the Requirement Framework exactly) that organizes observable, evidence-based facts into a small number of families; (3) a Review Priority Policy layer, kept structurally separate from Signal detection, that maps detected Signals into one of four priority categories with explicit reasons — never a score.

## 2. Main files changed

- New: `core/signal_model.py` (vocabulary + `compute_signal_status_from_evidence()` + `compute_review_priority()`), `application_service.py`, `signal_service.py`, `signal_detector.py`, migration `d9f3b7a2c5e8_add_selection_signals_and_review_priority.py` (+7 tables)
- Extended: `models.py` (+`CandidatePerson`, `Application`, `SignalDefinition`, `SignalObservation`, `SignalEvidenceItem`, `ReviewPriorityPolicy`, `ReviewPriorityPolicyRule`), `03 Software/Selection/app.py` (Application creation wired into upload + 13 new routes), `templates/base.html`, `templates/detail.html`, `industry/restaurant_templates.py` (+2 seed functions), `rfone_data_store/selection_validation.py` (+15 checks)
- New templates: `applications_home.html`, `application_detail.html`, `signals_home.html`

## 3. Candidate ≠ Application

A deliberate, documented naming compromise: the existing `Candidate` table (Task 2A — one résumé/CV dataset) is **unchanged**, renaming it was judged riskier than adding alongside it. `CandidatePerson` is the new person-level identity; `Application` links a person, a CV snapshot (one `Candidate` row, unique per Application), and context (target role, Requirement Set, Review Priority). Identity resolution (`get_or_create_person_for_candidate`) is a best-effort email match — the same honest limitation Task 2A's content-hash dedup already carries. Every successful résumé upload now automatically creates its Application. Since `Candidate.target_role` defaults to "SERVER" (Task 2A/2B), and the concept's progression Signals need Applications that genuinely target different roles over time, I added a small `set_target_role()`/UI form so an Application's target role can be set independently of the parsed résumé's default.

## 4. Signal families, statuses, and evidence

Families: `FIT_EXPERIENCE`, `READINESS_RECENCY`, `MOTIVATION_PERSONAL`, `MOTIVATION_PROFESSIONAL`. Statuses: `DETECTED`, `POSSIBLE`, `CONFLICTING`, `NOT_DETECTED`, `NOT_ASSESSED` — computed by `compute_signal_status_from_evidence()`, the Signal-framework twin of Task 3B's `compute_status_from_evidence()` (same SUPPORTS/CONTRADICTS/confidence rule, different vocabulary). `NOT_ASSESSED` (stage not permitted, zero evidence gathered) and `NOT_DETECTED` (stage permitted, no evidence found) are kept structurally distinct everywhere, exactly like Task 3B's NOT_ASSESSED_AT_THIS_STAGE/NOT_EVIDENCED. Evidence (`SignalEvidenceItem`) reuses Task 3B's exact vocabulary (source type, classification, relationship, confidence from `core/fit_assessment_model.py`) via a structurally identical but separate table — kept separate rather than a shared/polymorphic one so `EvidenceItem`'s existing NOT NULL FK never needed loosening.

## 5. Signal detection (real, not placeholder)

`signal_detector.py` implements five genuine, evidence-based detectors: recent/long-gap relevant experience (from work-history dates and role/role-family matching, reusing Task 2B's `months_between`), progression since a previous application (comparing a person's earliest Application's work history against the current one for the specific target role — the concept note's own Dishwasher→Line Cook example, verified working end to end), an explicit-interest self-description check (conservative, résumé summary text only, capped below HIGH confidence — mirrors Task 3B's behavioral-Requirement conservatism), and Fit Assessment strength (reusing Task 3B's `get_summary()` output directly, per the concept note's own suggestion). None infer a personal/protected cause for a gap — verified directly (no family/health/pronoun language in generated evidence text).

## 6. Review Priority

`compute_review_priority()` takes `(contribution_tier, reason)` pairs and returns one of `HIGH_PRIORITY`/`INTERESTING`/`STANDARD`/`LOW_PRIORITY` plus the reasons — rule-based on tier *counts* only, never a weighted sum exposed anywhere; mixed-direction Signals always resolve to `INTERESTING`, never silently to one side. `ReviewPriorityPolicy`/`ReviewPriorityPolicyRule` keep "how much a Signal matters" strictly separate from "was it detected" — verified directly: the identical detected Signal produces `STANDARD` with no policy and `HIGH_PRIORITY` once a policy rule exists for it (check 3C-M). With no active policy, every Application is `STANDARD` — never a default judgment invented on the restaurant's behalf.

## 7. Selezionatore authority

`Application.review_priority_system`/`review_priority_effective`/`review_priority_origin` and `SignalObservation`'s equivalents mirror Task 3B's system/effective/origin pattern exactly (`SYSTEM_GENERATED`/`HUMAN_CONFIRMED`/`HUMAN_OVERRIDDEN`, reusing that same vocabulary rather than inventing a parallel one). A human override is never silently recalculated away by a later refresh — verified directly (check 3C-N).

## 8. UI/API added

`/applications` (list, with priority badges), `/applications/<id>` (full detail — priority with confirm/override, target-role/note/outcome editing, application history for the same person, every Signal Observation with its evidence, guidance, confirm/override/add-evidence forms), `/signals` (read-only, grouped by family — Signal Definition authoring happens via seed data for now, the same scope Task 3A took for its first Requirement Template pass). A link from the existing candidate detail page to its Application. 13 new routes, all delegating to `application_service.py`/`signal_service.py`.

## 9. A real bug found and fixed along the way

While testing, `add_evidence()`/`generate_resume_stage_assessment()`-style functions in this new code hit the exact same stale-relationship-collection issue discovered and fixed during Task 3B (`session.expire(...)` after adding a child row via raw FK) — applied consistently here from the start in `signal_service.py`.

## 10. Targeted tests performed and results

- `python test_selection_engine.py` (extended `selection_validation.py`, `_assert_selection_signals`): **115/115 checks passed** (100 pre-existing Task 2A/2B/3A/3A-FIX/3B checks + 15 new checks covering the Candidate/Application distinction, application history, no-automatic-penalty-for-reapplying, all four Signal families, DETECTED/POSSIBLE/NOT_ASSESSED reachability and their structural distinction, restaurant-configurability (two restaurants with independent, non-interfering Signal Definitions), the concept note's own progression worked example with no invented characterization, the no-personal-cause rule for gap Signals, coexisting Signals, priority always being one of four categories with reasons, detection/policy separation, Selezionatore override survival across refresh, and outcome recording).
- `python test_batch_upload.py`: **19/19 checks passed** — confirms Task 2A/2B/3A/3B are unaffected.
- Extensive manual end-to-end smoke testing through the real Flask app (`test_client`): two résumés under the same email → same person recognized, target-role editing, progression Signal detected and displayed, priority computed/overridden/refreshed correctly, `/signals` and `/applications` pages render.
- Full Alembic migration chain verified to apply cleanly through the new head revision on a fresh database.

## 11. Known limitations directly relevant to Task 3C

- Person identity resolution is email-only, best-effort — a person reapplying under a different email is not recognized as the same person (an honest, documented limitation, not silently hidden).
- Signal Definition authoring has no dedicated UI yet — only a read-only `/signals` view plus code-seeded sample data (5 generic Signals + 1 example Review Priority Policy), mirroring Task 3A's own first-pass scope before its Requirement management UI followed.
- Only 5 of many plausible Signal subtypes have real detectors; an unconfigured `signal_subtype` simply produces no evidence rather than an error.
- No historical-outcome learning/correlation logic exists (concept note itself frames this as a *later* capability — "can later allow RF-One to learn"); only the `outcome` field to record it exists today.
- Review Priority is recomputed synchronously on résumé-stage generation/refresh only — no automatic recomputation trigger exists yet for a later stage's evidence (consistent with "do not implement Phone Interview now").
