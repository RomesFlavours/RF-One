# TASK 5A-FIX — Authoritative Stage/Outcome Model + Operational Queue Movement

## 1. What was implemented

Two problems left open by Task 5A were fixed:

1. `Application.workflow_status` is no longer an independently writable, parallel state source. It is now a derived, one-directional **projection** of the authoritative Stage/Outcome/lifecycle state (`authoritative → legacy`, never the reverse), recomputed automatically after every Stage transition and every Outcome application. Every Selection code path that used to write `workflow_status` directly (Review Queue's legacy status control, Phone Interview's post-interview decision) now routes through the authoritative Stage/Outcome services first.
2. `SelectionOutcomeDefinition.target_queue_label` — previously informational text only — is joined by a real `target_queue_id` reference to a new, first-class **operational Queue/List** concept. Applying an Outcome that targets a configured queue now automatically moves the Application into that queue as part of the same action, with full append-only movement history. Manual queue movement is independently supported and never touches Stage/Outcome. Legacy `target_queue_label` text is preserved for any pre-existing Outcome Definition that has not yet been assigned a queue.

## 2. Main files changed

**New:**
- `rfone_data_store/selection/core/queue_model.py` — queue-movement source vocabulary (`MANUAL`, `OUTCOME_ACTION`).
- `rfone_data_store/selection/queue_service.py` — Queue CRUD, `move_to_queue`, `get_current_queue`, `list_queue_history`.
- `rfone_data_store/selection/workflow_projection_service.py` — the legacy projection engine (`compute_legacy_workflow_status`, `refresh_legacy_workflow_status`, `apply_legacy_workflow_action`).
- `migrations/versions/e7c2a9f4d1b6_add_selection_5a_fix_queues.py` — `selection_queues`, `application_queue_movements` tables; `target_queue_id` on `SelectionOutcomeDefinition`/snapshot; `current_queue_id` on `Application`.
- `templates/selection_queues_home.html` — restaurant-facing queue configuration UI.

**Modified:**
- `rfone_data_store/models.py` — `SelectionQueue`, `ApplicationQueueMovement` models; `target_queue_id`/`current_queue_id` fields and relationships.
- `rfone_data_store/selection/stage_service.py` — `set_stage()` now calls `refresh_legacy_workflow_status()` before returning.
- `rfone_data_store/selection/outcome_service.py` — `apply_outcome()` now moves the Application into the Outcome's `target_queue_id` (if configured) and refreshes the legacy projection; `target_queue_id` added to definition create/update/snapshot.
- `rfone_data_store/selection/phone_interview_service.py` — `record_post_interview_decision()` now calls `workflow_projection_service.apply_legacy_workflow_action()` instead of `application_service.set_workflow_status()` directly.
- `rfone_data_store/selection/decision_service.py` — `DecisionSummary` gains `current_queue` and `queue_history`.
- `rfone_data_store/selection/selection_notes_service.py` — recognizes `"QUEUE_MOVEMENT"` note context.
- `rfone_data_store/selection/industry/restaurant_templates.py` — seeds default queues ("Active Review", "Call Later", "Hold", "Reconsider", "Hired", "Closed") and wires default Outcomes to them.
- `app.py` — legacy workflow-status route now routes through `apply_legacy_workflow_action`; new queue-management and manual-queue-move routes; `current_queue` passed to Application Detail/Decision Summary.
- `templates/decision_summary.html`, `templates/application_detail.html`, `templates/selection_outcomes_home.html`, `templates/base.html` — current-queue display, manual-move form, queue-movement history, Outcome→queue selector, new nav tab.
- `rfone_data_store/selection_validation.py` — new `_assert_selection_5a_fix_authoritative_state_and_queue()` targeted test function.

## 3. Authoritative Stage/Outcome/lifecycle behavior

`current_stage` and the current Outcome Decision's `lifecycle_state` remain exactly as established in Task 5A — unchanged by this fix. Every write to either now triggers `workflow_projection_service.refresh_legacy_workflow_status()`, which recomputes and, only if changed, rewrites `workflow_status`. No code path can change Stage or Outcome without the projection following.

## 4. Legacy `workflow_status` projection strategy

`compute_legacy_workflow_status()` is the single place the mapping is defined:
- Any CLOSED-lifecycle Outcome (HIRE, STOP, WITHDRAWN, or restaurant-authored equivalent) → legacy `STOP` (no legacy "HIRED" exists).
- Any SUSPENDED-lifecycle Outcome → legacy `HOLD`.
- Otherwise (still ACTIVE), current Stage decides: `IN_PERSON_PRACTICAL`→`ADVANCE_TO_IN_PERSON`, `PHONE_INTERVIEW`→`ADVANCE_TO_PHONE`, `PRIMARY_SCREENING`→`IN_REVIEW`, `APPLICATION_RECEIVED`→`NEW` until any Stage/Outcome history exists, then `IN_REVIEW`.

No history is fabricated for pre-existing Applications; the mapping only activates on read/refresh, so existing rows keep their stored `workflow_status` until the first new authoritative action touches them, at which point they become coherent.

## 5. Legacy action routing changes

- Review Queue / legacy workflow-status route (`app.py: application_set_workflow_status`) now calls `workflow_projection_service.apply_legacy_workflow_action()` instead of writing `workflow_status` directly.
- Phone Interview's post-interview decision (`phone_interview_service.record_post_interview_decision`) routes the same way: `ADVANCE_TO_IN_PERSON`/`ADVANCE_TO_PHONE`/`IN_REVIEW`/`NEW` become Stage transitions; `HOLD`/`STOP` resolve to the restaurant's configured SUSPENDED/CLOSED Outcome Definition and apply it.
- If a restaurant has no matching Outcome Definition configured yet for `HOLD`/`STOP`, `apply_legacy_workflow_action` falls back to the pre-5A-FIX direct write rather than raising — a documented compatibility boundary that is never reached once a restaurant has visited the Selection UI (defaults are seeded idempotently).

## 6. Operational Queue/List model

New `SelectionQueue`: `restaurant_id`, `name`, `description`, `is_active`, `display_order`. New `ApplicationQueueMovement`: append-only, records `application_id`, `previous_queue_id`, `new_queue_id`, `source` (`MANUAL`/`OUTCOME_ACTION`), `reason`, `originating_outcome_decision_id`, `performed_by`, `created_at`. `Application.current_queue_id` is a convenience pointer, never the sole source of truth. Restaurant-facing config UI at `/selection-queues` supports list/create/edit/activate-deactivate/reorder.

## 7. Outcome → Queue behavior

`SelectionOutcomeDefinition.target_queue_id` references a configured `SelectionQueue`; it is snapshotted onto `SelectionOutcomeDefinitionSnapshot` (no FK, mirroring the existing `auto_evaluation_signal_definition_id` pattern) so historical movements are never altered by later edits to the live definition. `outcome_service.apply_outcome()` applies the outcome, its lifecycle effect, and — only if `target_queue_id` is set — the queue move, all as one action, with `require_active=False` so a since-deactivated target queue never blocks the outcome itself. No queue is invented when none is configured; legacy `target_queue_label` text remains for definitions never assigned a queue.

## 8. Manual Queue movement

`/applications/<id>/queue/move` and `queue_service.move_to_queue(..., source=MANUAL, require_active=True)` let a Selezionatore move an Application to any active queue independently, with an optional Note, never altering Stage, Outcome, or lifecycle. Moving to an inactive/unconfigured queue is rejected.

## 9. Queue history and Notes

`ApplicationQueueMovement` rows are permanent and append-only. An optional queue-movement Note reuses `ApplicationNote` with `context_type="QUEUE_MOVEMENT"`, `context_id=movement.id`, and appears in the unified Selection Notes History at the bottom of the Decision Summary page, alongside all other note contexts. Decision Summary shows Current Operational Queue, a Move Queue form, and the full Queue Movement History table.

## 10. Review Queue compatibility

The Review Queue's completion/status-setting action is unchanged in its UI surface; internally it now routes through `apply_legacy_workflow_action()`, so it can never write a `workflow_status` value that contradicts Stage/Outcome. No business logic was duplicated.

## 11. Phone Interview compatibility

Phone Interview itself (question flow, evaluation, consistency engine) is untouched. Only `record_post_interview_decision()`'s final write was refactored: `ADVANCE_TO_IN_PERSON` sets Stage to `IN_PERSON_PRACTICAL`; `HOLD`/`STOP` apply the restaurant's configured Outcome. No contradictory state can result.

## 12. Targeted tests performed and results

All 28+ lettered checks specified in the task were implemented in `_assert_selection_5a_fix_authoritative_state_and_queue()` (`rfone_data_store/selection_validation.py`), covering: stage-change/outcome-change → legacy-projection coherence; legacy `ADVANCE_TO_PHONE`/`HOLD`/`STOP` routing through the correct authoritative service; Phone Interview post-decision no longer creating contradictory state; old UI actions unable to diverge Stage/Outcome from `workflow_status`; restaurant queue creation; Outcome targeting a configured queue and moving the Application; Outcome without a queue not moving it; queue movement history and originating-Outcome-Decision preservation; manual queue movement independent of Stage/Outcome; queue-movement Note preservation in unified history; current queue on Decision Summary; inactive queues rejected; historical movements surviving later Outcome Definition edits; Primary Screening/Hard-Disqualifier/Review-Queue/Phone/In-Person remaining fully operational with no auto-STOP; append-only Outcome/Stage history; no automatic HIRE/STOP introduced.

Results:
- Full DB-layer suite (`test_selection_engine.py`), fresh SQLite database, migrated through `e7c2a9f4d1b6`: **339/339 checks passed** (306 pre-existing + all new 5A-FIX checks), confirming zero regression across every prior task (2A–5A).
- Flask/HTTP-layer suite (`test_batch_upload.py`): **38/38 checks passed**, unaffected by the routing changes.
- Manual end-to-end HTTP smoke test against the real running app confirmed default-seeded Outcomes ("Hold" → "Hold" queue, etc.) and legacy-route → authoritative-service routing work correctly together outside the test fixtures.

## 13. Known limitations directly relevant to this fix

- A restaurant that has never opened the Selection UI (so no Outcome Definitions have been seeded) still falls back to a direct `workflow_status` write for legacy `HOLD`/`STOP` actions, since no SUSPENDED/CLOSED Outcome exists yet to apply. This is a deliberate, documented compatibility boundary, not a bug; it self-resolves the first time that restaurant's defaults are seeded.
- The legacy `workflow_status` vocabulary cannot represent a distinct "HIRED" state; both HIRE and STOP/WITHDRAWN Outcomes project to legacy `STOP`, an intentional, minimal, documented lossy mapping per the task's own instruction.
- `SelectionOutcomeDefinition.target_queue_label` (free text) remains on the model for backward compatibility on definitions that predate this fix and have not been assigned a `target_queue_id`; it has no runtime effect on queue movement.
