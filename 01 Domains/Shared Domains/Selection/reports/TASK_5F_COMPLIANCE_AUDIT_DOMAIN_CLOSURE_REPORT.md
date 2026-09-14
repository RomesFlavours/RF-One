# TASK 5F — Compliance Review + Explainability Audit + Selection Domain Closure

## 1. What was implemented

- A generic **Compliance/Rule Review Service** (`compliance_service.py`) that reviews any registered
  Selection configuration object (Requirement, Primary Screening Criterion — including Hard
  Disqualifiers, Application Question Definition) against a small, transparent, non-AI keyword/pattern
  rule set, producing human-readable, non-legal warnings with severity and an optional safer-framing
  rewrite suggestion.
- An explicit **human decision layer** (`ComplianceDisposition`) — ACCEPT_REWRITE / EDIT_MANUALLY /
  KEEP_ORIGINAL / DEACTIVATE / ACKNOWLEDGE_HIGH_CONCERN — recorded against a review, never applied
  automatically to the live object.
- An **immutable, append-only Compliance Review history** (`ComplianceReview` → `ComplianceWarning` /
  `ComplianceDisposition`) — a later edit to the live object triggers a brand-new review, never an
  overwrite of a prior one.
- An **Activation Guard** wired into the two existing reactivation routes
  (`primary_screening_criterion_toggle_active`, `application_question_toggle_active`): reactivating an
  object whose latest Compliance Review carries an unacknowledged HIGH CONCERN warning is blocked
  unless a human has recorded `ACKNOWLEDGE_HIGH_CONCERN` (with a mandatory reason) against that review.
- A **Selection Audit / Explainability Report** (`audit_service.py`, `audit.html`) — a pure read-time
  aggregator (never recomputes anything) reachable from the Candidate Dossier, reconstructing the full
  history behind one Application: Session/Rule context, Primary Screening (including the internal
  Priority Index, shown ONLY here), evidence provenance (FACT/DERIVED/INFERENCE with origin/confidence),
  Phone/In-Person evidence, Consistency Threads, Trainable Gaps (RF-One vs. Selezionatore levels),
  full Decision/Outcome and Event/Communication history, ownership changes, Session rule changes, the
  compliance context of the Criteria actually used, and the complete chronological Notes/Timeline —
  with a printable HTML view and a structured JSON export.
- **End-to-end Selection operational validation**: 10 realistic scenarios (A–J from the task) exercised
  through the full pipeline (Session → Job Posting → Application → Primary Screening → Missing-Evidence
  → Phone → In-Person → Consistency → Trainable Gap → Decision/Outcome → Dossier → Audit), plus
  boundary/integrity checks.
- This closure report.

## 2. Main files changed

**New:**
- `rfone_data_store/selection/core/compliance_model.py` — vocabulary (disclaimer, object types,
  severities, warning categories, disposition/activation actions, engine version).
- `rfone_data_store/selection/compliance_service.py` — review engine, history, disposition, activation guard.
- `rfone_data_store/selection/audit_service.py` — audit aggregation + JSON export.
- `migrations/versions/a2d8f4c1b9e6_add_selection_5f_compliance_review.py` — `compliance_reviews`,
  `compliance_warnings`, `compliance_dispositions` tables.
- `03 Software/Selection/templates/compliance_reviews_home.html`, `audit.html`.

**Modified:**
- `rfone_data_store/models.py` — `ComplianceReview`, `ComplianceWarning`, `ComplianceDisposition`.
- `03 Software/Selection/app.py` — Compliance Review routes, Audit routes, activation-guard calls
  wired into the two existing toggle-active routes, compliance-status context for the Criteria/Questions
  pages.
- `03 Software/Selection/templates/base.html` (nav tab), `dossier.html` (Audit link),
  `primary_screening_criteria_home.html`, `application_questions_home.html` (inline review widgets).
- `rfone_data_store/selection_validation.py` — new `_assert_compliance_audit_domain_closure` function
  (checks A–BG).

No files outside `01 Domains/Cross Domain/Selection`'s corresponding software/data-store/report
locations were touched, and no other Domain was modified.

## 3. Compliance Review architecture

A small, explicit registry (`_OBJECT_TYPE_REGISTRY`) maps each reviewable object type to its model
class — adding a future object type is a one-line registry entry, never a service redesign. Reviewable
text is extracted generically from common text-bearing attributes (name/description/evaluation
guidance/level descriptions/question text), so the engine is not hard-coded to any one model. A review
is a deterministic pass: keyword/pattern matching (mirroring `deterministic_parser.py`'s "honest,
non-fabricating" philosophy — no AI judgment, no false certainty) plus two structural checks (stage
reliability, missing-evidence-as-negative). Every `review_object()` call creates a brand-new
`ComplianceReview` row pinned to the exact text reviewed at that moment; nothing is ever overwritten.

## 4. Warning/severity behavior

Three severities (INFO / WARNING / HIGH_CONCERN). Fourteen categories from the task's list are
implemented (protected characteristics, proxies, non-job-related, appearance/body,
nationality/ethnicity/race, sex/gender, age, religion, disability, family/marital/pregnancy, vague
subjective, stage-unreliable, missing-evidence-as-negative). Explanations always use the required
conversational, non-legal phrasing ("Potential compliance concern", "Weak job relevance", etc.) and the
`ComplianceReview`/audit surfaces always carry `cpm.DISCLAIMER` ("This review is not legal advice, not a
legal certification, and does not guarantee compliance..."). A match is never presented as proof of an
actual legal problem.

## 5. Rewrite/approval behavior

Rewrite suggestions are generated per-category as job-relevant reframings that preserve the original's
apparent operational intent (e.g. an appearance/age-flagged criterion suggests reframing around
observable job performance) — never a universal find/replace substitution. A suggestion is stored on the
`ComplianceWarning` row and is never applied to the live object automatically; only a recorded
`ComplianceDisposition` (`ACCEPT_REWRITE` / `EDIT_MANUALLY`, each carrying `final_text`) reflects a
human's actual decision, and applying that text back to the live object (e.g. via
`primary_screening_service.update_criterion`) remains a separate, explicit human action. `KEEP_ORIGINAL`
against a HIGH_CONCERN warning requires a reason, preserving the fact that a concern was seen and
knowingly kept.

## 6. Activation-guard behavior

`compliance_service.assert_activation_allowed()` raises `ValueError` when an object's latest review has
an unacknowledged HIGH_CONCERN warning (no later `ACKNOWLEDGE_HIGH_CONCERN`/`ACCEPT_REWRITE`/
`EDIT_MANUALLY` disposition against that same review). It is called only at the two existing
reactivation routes (`primary_screening_criterion_toggle_active`, `application_question_toggle_active`),
reusing that existing route wiring rather than introducing a new authority/governance layer.
Deactivation is never blocked, and no existing active rule was auto-deactivated by this task — an
object active before 5F stays active until a human deactivates it (it will simply show as "not yet
reviewed" until someone runs a review). Verified via both the service-layer test suite and a live HTTP
round-trip (deactivate → blocked reactivation → acknowledge → reactivation succeeds).

## 7. Selection Audit architecture

`audit_service.build_audit()` is a pure, read-only aggregator over already-existing services and tables
(Application, Session, Rule Set versions, Primary Screening runs/evaluations, Fit Assessment/Trainable
Gaps, Phone/In-Person plans, Consistency Threads, Outcome decisions, Events, Communications, Scheduling,
Ownership, Rule Changes, Compliance context, Notes) — it recomputes nothing and writes nothing. The
Candidate Dossier was not redesigned; it received one added link/action into `/applications/<id>/audit`.
The internal Priority Index is exposed only inside this report/JSON, never in any other template.

## 8. Historical Rule/version reconstruction

Every Primary Screening row in the Audit is read through the `PrimaryScreeningCriterionSnapshot`
actually pinned to that historical run (never the live, possibly-since-edited Criterion), and
`report.rule_set_version` is the exact `SelectionRuleSetVersion` in effect for the Application at
evaluation time. A later Session-wide rule change is shown as a distinct `RuleChangeAuditEntry` with an
explicit `impact_on_this_application` flag — the Audit never silently re-evaluates a historical
Application against today's rules.

## 9. Internal Priority Index audit behavior

`ScreeningEvaluationRow.resulting_priority_index`/per-row `contribution` are populated for every
screening run inside the Audit report and JSON export only; no other route, template, or the ordinary
Primary Screening Queue UI reads or displays this numeric value (structural guarantee — it is computed
only inside `audit_service.py`).

## 10. Evidence provenance behavior

Each Criterion Evaluation row preserves `evidence_source`, `confidence`, and `origin`
(SYSTEM_GENERATED / HUMAN_ENTERED / HUMAN_CONFIRMED / HUMAN_OVERRIDDEN) distinctly — never flattened
into prose. The FACT vs. DERIVED_INFORMATION vs. INFERENCE distinction already established elsewhere in
Selection (Work History normalization, Signal observations, Trainable Gaps) is preserved as-is and
surfaced through the Audit's own read of those existing fields, not duplicated by a new classification
scheme.

## 11. Human override audit behavior

Hard Disqualifier overrides, Trainable Gap level corrections, Review Priority overrides, and outcome
reopen events are all reconstructed with their existing before/after/who/reason/when fields (all already
present on the underlying models from Tasks 3B–5A); the Audit surfaces them, it does not add a second,
competing override-tracking mechanism.

## 12. End-to-end scenarios tested

The regression suite's `_assert_compliance_audit_domain_closure` function drives one Session through:
Rule Set confirmation, a full Primary Screening run (including a triggered-then-overridden Hard
Disqualifier and a human-entered evaluation), a Fit Assessment with a Trainable Gap carrying divergent
RF-One/Selezionatore levels, Phone and In-Person Interview Plans, a Consistency Thread, HOLD then STOP
then reopen (via a distinct ACTIVE-lifecycle Outcome), ownership reassignment, an inbound
"no longer interested" message correctly kept as an Event/classification rather than an automatic
Outcome, a mid-Session rule change and its recorded impact, and multiple Compliance Reviews with all
five disposition types. A separate HTTP-level smoke test exercises the same Compliance/Audit routes and
the activation guard's block → acknowledge → allow path through real Flask requests (27/27 checks
passed).

## 13. Test results

- Full regression suite (`test_selection_engine.py`, fresh SQLite DB + `alembic upgrade head` each run):
  **633/633 checks passed**, confirmed stable across 3 independent fresh-DB runs.
- HTTP-level smoke test for Task 5F routes (Compliance Review create/history, disposition recording,
  activation-guard block/allow, Audit page + JSON export, Dossier link, nav regression):
  **27/27 checks passed**.
- No prior Task's checks (5A–5E, 570 checks) regressed; they are all included in the 633 total.

## 14. Known limitations directly relevant to Selection 1.0

- The keyword/pattern rule set is deliberately small and illustrative (per task's own "non-exhaustive,
  never AI judgment" instruction) — it will miss many real phrasings and will occasionally flag benign
  text; it is a screening aid for human review, not a compliance detector.
- The activation-guard routes swallow a blocked reactivation's `ValueError` silently (redirect with no
  flash message) — a Selezionatore sees the object simply stay inactive with no on-screen explanation;
  the reason is visible on the Compliance Reviews page. Adding a flash message would be a minor,
  low-risk future UI enhancement, not required for Selection 1.0 to function correctly.
- Export from the Audit view is HTML (browser Print-to-PDF) + structured JSON, as scoped; no dedicated
  PDF-generation pipeline was built.
- There is still no authentication/RBAC system in Selection; `performed_by`/`reviewed_by` fields remain
  honest free-text placeholders, consistent with every other Task in this domain.

## 15. Explicit statement on Selection 1.0 closure

**Selection 1.0 can be considered operationally closed.** The full candidate journey — Session/Rule
governance, Job Posting and public Application intake, CandidatePerson resolution, Primary Screening
(including Missing-Evidence pre-screening and Hard Disqualifiers), Phone and In-Person/Practical
evaluation, Consistency checking, Trainable Gap tracking, Decision/Outcome history, Candidate
Communication/Scheduling, the Candidate Dossier, and now Compliance Review and the Selection Audit —
operates end-to-end, is covered by an automated regression suite (633 checks) and an HTTP smoke suite,
and consistently stops at its declared boundary (HIRABLE, never HIRED; no Training/Performance/Payroll
data fabricated). The known limitations above are minor, documented, and do not block operational use.
No further Selection features are proposed as part of this task, per the Product Owner's explicit
instruction to stop after this closure.
