# TASK 5A-MICRO-FIX Report

## 1. Changes made

All inside Selection only; no new migration required (pure service/test-layer logic, no new columns).

- `outcome_service.apply_outcome()` (`03 Software/RF-One Data Store/rfone_data_store/selection/outcome_service.py`): added a second, non-configurable check layered on top of the Outcome's own `requires_reason`. It compares the Application's current effective decision (if any) against the Outcome being applied; if one exists and names a **different** `SelectionOutcomeDefinition`, a non-empty `reason` is now mandatory, regardless of what the target Outcome itself requires. Re-applying/confirming the same Outcome again is not treated as a change. `reopen_application()` needed no separate edit — it already calls `apply_outcome()` internally, so it inherits the rule automatically (this is how "STOP -> reopened requires a reason" is satisfied).
- Audited `workflow_projection_service.apply_legacy_workflow_action()` and both `app.py` routes (`/outcome/apply`, `/outcome/reopen`, `/workflow-status`): all three already thread a `reason` form field through to `apply_outcome`/`reopen_application` and already catch `ValueError` by rolling back and redirecting without applying the change — the exact same silent-reject pattern already used for a target Outcome's own `requires_reason`/`requires_note`. No code change was needed there; the new rule reuses existing plumbing end-to-end.
- `selection_validation.py`: updated ~10 existing test call sites (in the pre-existing 5A and 5A-FIX suites, and my own 5A-ALIGN suite) that changed an existing decision without a reason, since those are now correctly rejected; reworded one check (`5A-R`) whose old assertion ("HIRE needs no reason") no longer describes that call site once it became a change, and added a new one (`5A-R2`) that demonstrates the still-true original claim on a fresh Application. Added a new dedicated test function, `_assert_selection_5a_micro_fix` (10 checks: `5A-MF-A` through `5A-MF-G3`), registered in `run_validation()`.

## 2. Decision-change reason behavior

- **First decision for an Application**: follows the chosen Outcome's own configuration only (e.g. HIRABLE, configured `requires_reason=False`, needs none) — verified by `5A-MF-A` and, live, on a fresh Application via Flask.
- **Changing an existing decision to a different Outcome**: always requires a non-empty reason now, even if the target Outcome itself requires none (HIRABLE -> STOP) or the source requires none. Verified: `5A-MF-B`/`C` (HIRABLE->STOP), `5A-MF-D` (STOP->HOLD), `5A-MF-E`/`E2` (STOP->reopened, via `reopen_application`).
- **Re-applying/confirming the same Outcome**: not a "change," no reason required even though a decision already exists (`5A-MF-F`).
- **History**: append-only, nothing overwritten — the previous decision row and the new decision row both remain in `SelectionOutcomeDecision`, each retaining its own `reason`, `performed_by`, and `created_at` (`5A-MF-C`). There is no separate `stage_at_time` column on `SelectionOutcomeDecision`; the Application's Stage at the time of a decision remains reconstructable by timestamp-correlating with `ApplicationStageTransition`, exactly as for every other decision in the 5A model — adding a dedicated column was judged unnecessary duplication of already-available history.
- Live-verified through the real Flask route (`POST /applications/<id>/outcome/apply`): a reason-less attempt to change HIRABLE -> STOP silently no-ops (existing UX pattern, unchanged); supplying a reason succeeds and both decisions persist.

## 3. Training Check history behavior

Already fully built by the prior 5A-ALIGN work; no change needed, only re-verification under this task's exact wording. Applying "Training Check Not Passed" creates a `CandidateFlag` on the person; `flag_svc.list_active_flags_for_application()` surfaces it as "Previous Training Check Not Passed"-equivalent history on any later Application by the same person (`5A-MF-G1`), and `primary_screening_ai_evaluator.build_evidence_package()` already includes it so a restaurant's Primary Screening Criterion can use it as evidence (`5A-MF-G2`). Newly added and explicitly verified for this task: the Flag never by itself sets `PrimaryScreeningRun.has_active_hard_disqualifier` — that only happens once an actual Criterion Evaluation is entered — so a restaurant can configure it as a Hard Disqualifier but nothing rejects automatically (`5A-MF-G3`).

## 4. Tests/results

- `python test_selection_engine.py` (fresh SQLite DB, full migration chain applied): **364/364 checks passed** (354 pre-existing/reworded + 10 new `5A-MF-*`).
- `python test_batch_upload.py`: **38/38 checks passed**, unaffected.
- Live Flask smoke test: applied HIRABLE (first decision, no reason) via a direct service call, then via the real `/applications/<id>/outcome/apply` route attempted HIRABLE -> STOP with no reason (silently rejected, history unchanged) and again with a reason (succeeded; both decisions persisted with correct `reason`/timestamps).

## 5. Remaining relevant limitations

- The silent no-op UX (`app.py` catching `ValueError` and redirecting with no visible error message) is pre-existing from 3C-FIX/5A/5A-FIX and unchanged here; a Selezionatore who forgets a reason on a decision-change sees no explicit on-page error, only that nothing changed. Improving this is a UI concern outside this task's scope.
- No RBAC exists in Selection, so `performed_by` on a decision-change reason remains free-text and unenforced, same as every other actor field in 5A.
- `SelectionOutcomeDecision` still has no dedicated `stage_at_time` column; Stage-at-decision-time is reconstructable via timestamp correlation with `ApplicationStageTransition`, not stored directly on the decision row.
