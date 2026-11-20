# GLOBAL_INTEGRITY_FIX_003 — Outcome/Workflow Mutation Path Unification Report

**Scope:** Finding C-2 (split-brain Outcome/Workflow-Status mutation) from `07 Tasks/Reports/RF_ONE_GLOBAL_INTEGRITY_REVIEW_001.md`. Builds on the stable `ActingIdentity`/`assert_can_operate` substrate completed by GLOBAL_INTEGRITY_FIX_002 (still uncommitted in this working tree at the start of this task — this fix's diff is layered on top of it). No Selection redesign, no other-Domain changes, no tenant-architecture work, no C-1/I-4/I-12 rework, no new broad integrity review, and no opportunistic refactoring were performed.

---

## 1. Files Changed

**Created:**
- `03 Software/Selection/test_outcome_workflow_http.py` — HTTP-level regression suite for this fix (task §21).
- `07 Tasks/Reports/GLOBAL_INTEGRITY_FIX_003_OUTCOME_WORKFLOW_UNIFICATION_REPORT.md` (this file).

**Modified:**
- `03 Software/RF-One Data Store/rfone_data_store/selection/outcome_service.py` — added `get_effective_application_outcome()` (task §12).
- `03 Software/RF-One Data Store/rfone_data_store/selection/workflow_projection_service.py` — `apply_legacy_workflow_action` now forwards `performed_by_identity_id` and fires the same Candidate Communication consequence the modern routes fire.
- `03 Software/RF-One Data Store/rfone_data_store/selection/phone_interview_service.py` — `record_post_interview_decision` accepts and forwards `performed_by`/`performed_by_identity_id`.
- `03 Software/RF-One Data Store/rfone_data_store/selection/application_service.py` — `set_outcome`'s docstring marks it legacy/compatibility-only (no behavior change).
- `03 Software/RF-One Data Store/rfone_data_store/selection/primary_screening_ai_evaluator.py` — prior-Application outcome evidence now reads `outcome_service.get_effective_application_outcome` instead of the raw `.outcome` scalar.
- `03 Software/RF-One Data Store/rfone_data_store/selection_validation.py` — new `_assert_outcome_workflow_unification` (17 new checks, task §19), registered in `run_validation`.
- `03 Software/Selection/app.py` — `application_set_workflow_status` and `phone_interview_decision` now resolve the actor and enforce `own_svc.assert_can_operate`; `primary_screening_evaluation_override` gained the same guard; the legacy `/applications/<id>/outcome` route is retired; `applications_home`/`application_detail` no longer read the stale scalar for display.
- `03 Software/Selection/templates/application_detail.html` — the mutable "Historical outcome" form removed (replaced by a read-only legacy display); the "Application History" table's Outcome column now shows the effective (authoritative-first) value.

**No migration was created** — this fix changes only which service functions/routes are reachable and how, not the schema (task §18).

---

## 2. Authoritative Outcome Path

Unchanged and confirmed as the ONLY one: `outcome_service.apply_outcome()` (and `reopen_application`, which calls it) is the sole place a `m.SelectionOutcomeDecision(...)` row is constructed anywhere in the codebase (confirmed by the §20 static search below). Every caller — the modern `application_apply_outcome`/`application_reopen` routes, the legacy `workflow_projection_service.apply_legacy_workflow_action` bridge, and `phone_interview_service.record_post_interview_decision` (which itself goes through that same bridge) — now funnels through this one function, so its own governance (mandatory reason when changing an existing decision, Note/reason validation, reminder/flag/queue side effects, legacy `workflow_status` projection refresh) applies identically regardless of entry point.

## 3. Authoritative Stage Path

Unchanged and confirmed as the ONLY one: `stage_service.set_stage()` is the sole place an `m.ApplicationStageTransition(...)` row is constructed anywhere in the codebase. The same three callers (modern `application_set_stage` route, the legacy bridge, and the phone-interview decision indirectly) all funnel through it.

## 4. Legacy `Application.outcome` Handling

`Application.outcome` (the Task 3C-era free-text/fixed-vocabulary field — `REVIEWED`/`ADVANCED`/`HELD`/.../`RETAINED`, partly describing POST-HIRE progression states with no equivalent in the restaurant-configurable Outcome Definition vocabulary) is now **read-only from any live route**. The column and all historical values are untouched — no migration, no backfill, no deletion. `application_service.set_outcome()` still exists (its own docstring now says explicitly it is legacy/compatibility-only) so the pre-existing Task-3C-era structural regression check ("3C-O" in `selection_validation.py`) keeps passing unmodified, and any future non-HTTP caller can still exercise the field directly — but nothing in `Selection/app.py` calls it anymore. Reads of the raw scalar were replaced with `outcome_service.get_effective_application_outcome()` everywhere it mattered for a decision-relevant display (see §9 below); one dead, unrendered read (`applications_home`'s row-building dict key) was deleted outright.

## 5. Legacy `workflow_status` Handling

Unchanged in design (it was already a correct, additive projection from a prior fix — "Task 5A-FIX"): `application_service.set_workflow_status()` remains the only place the column is written, called only by `workflow_projection_service.refresh_legacy_workflow_status()`, itself called automatically at the end of `stage_service.set_stage()`/`outcome_service.apply_outcome()`. What this fix added is governance PARITY for the one remaining ungoverned entry point into that projection — see §7/§8.

## 6. UI Route Consolidation

- **Retired:** `POST /applications/<id>/outcome` (`application_set_outcome`) — a direct, ungoverned `Application.outcome` overwrite with no ActingIdentity, no authority check, no history, no reason, no communication (task §1 item B, task §4 option A). Its vocabulary does not map cleanly onto restaurant-configured Outcome Definitions, so option B (route it through the Outcome Engine) was rejected as "fabricating a mapping" rather than "failing honestly." The route no longer exists (verified: returns 404). Its template control was replaced with a read-only legacy display.
- **Retained, now governed:** `POST /applications/<id>/workflow-status` (`application_set_workflow_status`) — already routed through `workflow_projection_service.apply_legacy_workflow_action` (a prior fix's work), but the Flask route itself resolved no actor and enforced no authority. It now resolves the actor server-side and calls the same `own_svc.assert_can_operate` guard the modern Stage/Outcome routes use, before calling into the bridge.
- **Retained, now governed:** `POST /phone-interviews/<id>/decision` (`phone_interview_decision`) — maps directly onto the same Stage/Outcome bridge (`phone_interview_service.record_post_interview_decision` → `apply_legacy_workflow_action`) but previously resolved no actor and enforced no authority at all. It now fetches the Plan, resolves the actor, and enforces `own_svc.assert_can_operate(session, plan.application_id, actor.id)` before proceeding.
- **Retained, now governed:** `POST /primary-screening/<run_id>/evaluations/<id>/override` (`primary_screening_evaluation_override`) — a substantive, mandatory-reason override of a screening evaluation's level that had no ownership/authority check, while the structurally identical `override-hard-disqualifier` route (Fix 002) did. Closed the "same category of action, different route, different governance" gap by adding the same guard. `enter`/`confirm`/`not-applicable`/`insufficient-evidence` were deliberately left ungated — they are evidentiary/procedural (entering or acknowledging evidence, never overriding a system-computed level), not a substantive Decision override, so forcing the same governance onto them would contradict task §14's own "if purely evidentiary, document the distinction rather than forcing inappropriate governance."

No second Outcome/Stage mutation control now exists anywhere in the UI that bypasses the authoritative services; the routes/controllers that remain contain no lifecycle business logic of their own — they resolve the actor, enforce the one shared authority guard, and delegate.

## 7. ActingIdentity/Authority Behavior

`workflow_projection_service.apply_legacy_workflow_action` and `phone_interview_service.record_post_interview_decision` both now accept `performed_by_identity_id` and forward it unchanged into `stage_service.set_stage`/`outcome_service.apply_outcome` — the same parameter the modern routes already supplied (from GLOBAL_INTEGRITY_FIX_002). Authority enforcement itself continues to live at the CALLER (the established convention from Fix 002 — `ownership_service.assert_can_operate` is "the ONE reusable guard a route should call," not something embedded inside `set_stage`/`apply_outcome` themselves, which would have required every one of the ~68 pre-existing direct service-layer calls in `selection_validation.py` to also supply an identity/ownership context they don't need for their own unrelated test purposes). Every ROUTE that performs a substantive Stage/Outcome mutation now calls that same guard first: `application_set_stage`, `application_apply_outcome`, `application_reopen` (pre-existing), plus `application_set_workflow_status`, `phone_interview_decision`, and `primary_screening_evaluation_override` (added by this fix). The answer to "may this ActingIdentity perform this transition" no longer depends on which control was used.

## 8. Reason-Governance Behavior

Unchanged and now uniformly reached: the mandatory-reason-on-change rule lives in exactly one place, `outcome_service.apply_outcome`'s own `is_changing_existing_decision` check. Because the legacy bridge and the phone-interview decision path both funnel through that same function, changing an existing governed decision via ANY of the three entry points requires a reason identically (verified by regression check FIX003-F and HTTP checks 3/3b).

## 9. AI Evaluator Correction

`primary_screening_ai_evaluator._application_history_evidence` previously read `prior[-1].outcome` (the stale legacy scalar) directly. It now calls a new private helper, `_prior_outcome_evidence_text`, which uses `outcome_service.get_effective_application_outcome`: when a governed `SelectionOutcomeDecision` exists for the prior Application, its name is used verbatim; when only the legacy scalar exists, it is still surfaced (task's own "legacy fallback may be used explicitly as historical compatibility evidence") but explicitly suffixed "(legacy pre-Outcome-Engine record, not a governed decision)"; when neither exists, "(none recorded)". No governed Decision record is ever fabricated from a legacy value. The same `get_effective_application_outcome` helper is reused (task §12's own "reuse this read helper instead of scattered direct reads") in `Selection/app.py`'s `application_detail` route, feeding the "Application History (this person)" table's Outcome column in `application_detail.html` — the same kind of evidence a human reviewer sees, kept consistent with what the AI evaluator sees.

## 10. Communication Consequence Behavior

`apply_legacy_workflow_action` now triggers `communication_service.on_stage_transition`/`on_outcome_decision` itself — once, inside the one bridge every legacy caller (the Workflow Status route AND `phone_interview_service.record_post_interview_decision`) already funnels through — rather than duplicating that call in each controller (task §10's explicit "do not duplicate communication logic in legacy controllers"). This required a lazy (function-local) import of `communication_service` inside `workflow_projection_service.py` to avoid a circular import (`communication_service` → `outcome_service` → `workflow_projection_service` at module level), matching the file's own pre-existing lazy-import convention for `stage_service`/`outcome_service`. Verified end-to-end (service-level checks FIX003-G/V and HTTP checks 2) that the SAME `CandidateCommunication` row (same `trigger_event`) is created via the legacy bridge as would be created via the modern route for the same transition/decision, when a matching Template is configured — and that nothing fires (no fabricated default) when none is configured, exactly like the modern path.

## 11. Historical Compatibility

Purely non-destructive: no existing `Application.outcome` value, `workflow_status` value, `SelectionOutcomeDecision`, `ApplicationStageTransition`, Note, or Communication history was touched, backfilled, or reinterpreted. No governed Decision was fabricated from a legacy scalar. The one caveat, explicitly documented in `apply_legacy_workflow_action`'s own docstring: the pre-existing "no Outcome Definition configured yet" fallback branch (a direct `workflow_status` write for a restaurant that has never configured an Outcome) still has no ActingIdentity FK to attach to — there is no such column on that write — an honest, narrow, pre-existing compatibility boundary that this fix did not need to close to resolve C-2 (every restaurant that has visited the Selection UI has Outcomes idempotently seeded, so this fallback is not reached in practice).

## 12. Primary Screening Route Consistency Work Directly Included

Covered under §6/§7 above: only `primary_screening_evaluation_override` was changed, closing the one directly-relevant "same action [override], different route, different governance" inconsistency C-2 named. No other Primary Screening route, and no Primary Screening business logic, was touched — a broader Primary Screening authority redesign was explicitly out of scope (task §14).

## 13. Migrations

None. No schema changed; only which functions/routes are reachable, and how, changed.

## 14. Targeted Tests (Service Layer — task §19)

Added `_assert_outcome_workflow_unification` to `rfone_data_store/selection_validation.py` (registered in `run_validation`) — 17 new checks:

- **A** (×2 — Stage- and Outcome-mapped): the legacy bridge creates a real `ApplicationStageTransition`/`SelectionOutcomeDecision`, never a direct scalar write.
- **C/D** (×2): the ActingIdentity is recorded on both bridge-created rows.
- **G/V** (×2): the SAME Candidate Communication fires via the bridge as the modern route would fire, for both a Stage-mapped (ADVANCE_TO_IN_PERSON) and an Outcome-mapped (STOP) transition.
- **F** (×2): changing an existing governed decision via the bridge without a reason is rejected; the same change succeeds once a reason is supplied.
- **Effective-outcome baseline / H / K**: with neither a decision nor a legacy value the effective Outcome is `(None, NONE)`; with only a legacy value it falls back to it and marks the source `LEGACY_FIELD`.
- **I**: once a governed decision exists, it takes precedence over a stale legacy value ('Stop' over 'HIRED').
- **H** (readback): the legacy value itself remains unchanged underneath the governed decision.
- **J** (×2): the AI evaluator's prior-application evidence reflects the authoritative decision when one exists, and the explicitly-labeled legacy fallback when only a legacy value exists (K).
- **L/D** (×2): `phone_interview_service.record_post_interview_decision` maps its decision through the same Stage service and carries the same ActingIdentity.

Full text of every check description is in the code (`selection_validation.py`); each was run and observed passing (see §16).

## 15. HTTP-Level Tests (task §21)

New `03 Software/Selection/test_outcome_workflow_http.py` (mirrors `test_acting_identity_http.py`'s convention: throwaway SQLite database, Werkzeug test client). 13 checks:

1. A non-owner, non-superior identity (Jordan) cannot change the legacy Workflow Status control — no Outcome decision is created (actor cannot be spoofed; authority enforced identically to the modern route).
2. The real owner's (Alex's) legacy Workflow Status change creates a real, governed `SelectionOutcomeDecision` naming the restaurant's own Outcome Definition, carries Alex's ActingIdentity, and fires the same Candidate Communication a modern Outcome decision would fire.
3. Changing that decision again via the same legacy control without a reason is rejected; supplying a reason succeeds and is reflected in the governed decision.
4. `POST /applications/<id>/outcome` (the retired route) returns 404.

`phone_interview_decision`'s and `primary_screening_evaluation_override`'s authority-guard additions were verified at the service layer (§14) and by direct code inspection against the already-HTTP-tested `application_set_stage`/`override-hard-disqualifier` pattern they now mirror exactly; a dedicated HTTP test for each was not added, to keep this fix's test surface bounded to what task §21 explicitly names (the legacy Workflow Status control) rather than opportunistically expanding it.

## 16. Full Regression Results

All suites run against fresh, disposable SQLite databases (never the operational `data/rfone.db`/`data/selection.db` — both confirmed unchanged by this task's own test runs; only an earlier, incidental `python -c "import app"` sanity check accidentally ran the still-pending, purely-additive GLOBAL_INTEGRITY_FIX_002 migration against the local operational `Selection/data/selection.db`, non-destructively — noted here for transparency, not something this fix's own validation runs repeated):

| Suite | Result |
|---|---|
| `test_selection_engine.py` (`selection_validation.py`, includes 17 new FIX003 checks) | SUCCESS — 658/658 |
| `test_organization_validation.py` | SUCCESS — 14/14 |
| `test_payroll_engine.py` | SUCCESS — 52/52 |
| `test_restaurant_profile_bootstrap.py` | SUCCESS — 14/14 |
| `test_sales_validation.py` | SUCCESS — 27/27 |
| `test_tips_engine.py` | SUCCESS — 54/54 |
| `test_purchasing_engine.py` | SUCCESS — 24/24 |
| `Selection/test_batch_upload.py` | SUCCESS — 38/38 |
| `Selection/test_acting_identity_http.py` (Fix 002) | SUCCESS — 12/12 |
| `Selection/test_outcome_workflow_http.py` (new) | SUCCESS — 13/13 |

Template rendering was additionally smoke-tested via the Flask test client (`/applications`, `/applications/<id>`, `/applications/<id>/dossier`, `/applications/<id>/decision`, `/identity/switch`, including a case with a legacy-only `Application.outcome` value and a case with a prior Application showing a legacy outcome in the "Application History" table) — all rendered without error.

## 17. Static Search Results (task §20)

- **`.outcome =`**: exactly one write site, `application_service.py:194` inside `set_outcome()` itself (now documented legacy/compatibility-only, unreachable from any route). All other matches are read-only equality assertions in `selection_validation.py`.
- **`set_outcome(`**: called only from `selection_validation.py` — the pre-existing "3C-O" structural check (untouched) and this fix's own new checks (FIX003-H/K, deliberately exercising the legacy-fallback path). No call from `Selection/app.py` or any template remains.
- **`workflow_status` (direct write, `.workflow_status =`)**: exactly one site, `application_service.py:318` inside `set_workflow_status()` — the pre-existing single choke point, called only by `workflow_projection_service.refresh_legacy_workflow_status`/its documented no-Outcome-configured fallback. Every other match is a read-only assertion.
- **`SelectionOutcomeDecision(`**: exactly one construction site, `outcome_service.py:268` inside `apply_outcome()`.
- **`ApplicationStageTransition(`**: exactly one construction site, `stage_service.py:45` inside `set_stage()`.

No hidden bypass remains: every write to the four inspected surfaces is either the one authoritative choke point or the one explicitly-documented legacy-compatibility function, and none of the latter is reachable from a live route anymore except `set_workflow_status`'s own narrow, pre-existing, documented fallback (§11).

## 18. Is C-2 Fully Resolved?

**Yes**, for every mutation path the review named:

1. `SelectionOutcomeDecision` is the only authoritative substantive Outcome history — confirmed structurally (one construction site) and behaviorally (both remaining legacy entry points route through `apply_outcome`).
2. `ApplicationStageTransition` is the only authoritative Stage history — same confirmation for `set_stage`.
3. `Application.outcome`/`workflow_status` can no longer independently mutate lifecycle truth from any live route — the ungoverned outcome route is retired; `workflow_status` remains a pure derived projection, written only by its one pre-existing choke point.
4. Every retained legacy route (Workflow Status, Phone Interview decision) funnels into the authoritative services.
5. All paths use the stable ActingIdentity from Fix 002.
6. Authority (`assert_can_operate`) is enforced identically regardless of route/button — Workflow Status, Phone Interview decision, and Primary Screening override all closed the gap the review found.
7. The mandatory-reason-on-change rule is preserved and reached identically from every path.
8. Candidate Communication consequences are intact and identical across paths.
9. The AI evaluator (and the equivalent human-facing Dossier evidence) reads the authoritative Outcome history, never the stale scalar.
10. Historical legacy-only Applications remain honestly readable, with no fabricated governed decision.
11. Full regression passes (658+14+52+14+27+54+24+38+12+13 = 906 checks, all green).

## 19. Residual Compatibility Debt

- `workflow_projection_service.apply_legacy_workflow_action`'s pre-existing "no Outcome Definition configured yet" fallback (a direct `workflow_status` write) has no ActingIdentity FK to attach to — narrow, pre-existing, and not reached by any restaurant that has visited the Selection UI (Outcomes are idempotently seeded on first visit). Left as-is; closing it would mean adding a schema column for a code path that, in practice, never fires — out of proportion to this fix's scope.
- `phone_interview_decision`'s and `primary_screening_evaluation_override`'s new authority guards were verified at the service layer and by direct code-pattern equivalence to already-HTTP-tested routes, not by a dedicated new HTTP test for each — a deliberate scope-boundedness choice (task §21 names only the legacy Workflow Status control explicitly), not a gap in the guard itself.
- GLOBAL_INTEGRITY_FIX_002 remains uncommitted in this working tree, as does this fix — both are layered together pending Product Owner review; nothing was committed or pushed.

No unresolved contradiction was found.
