# TASK 5A — Conceptual Alignment Check Report

## 1. Current 5A/5A-FIX architecture

Task 5A separated three concepts Selection previously conflated in `Application.workflow_status`: **Stage** (`current_stage` — a free-form position marker, no state-machine restrictions, full history in `ApplicationStageTransition`), **Outcome** (a restaurant-configurable operational decision — `SelectionOutcomeDefinition`/`Snapshot`, applicable at any moment, mirroring `PrimaryScreeningCriterion`'s versioned/snapshot-safe shape), and **Decision History** (`SelectionOutcomeDecision`, append-only, always resolvable to "the most recent row = current effective Outcome"). It also added `CandidateFlag` (person-level, historical, never auto-rejecting), `SelectionReminder` (a follow-up record an Outcome may create), and a unified `selection_notes_service.get_selection_notes_history()` spanning every note-bearing element. Task 5A-FIX made Stage/Outcome/lifecycle the sole authoritative state, reducing `workflow_status` to a derived, one-directional legacy projection, and added a first-class operational Queue/List concept (`SelectionQueue`/`ApplicationQueueMovement`) an Outcome can move an Application into.

## 2. Which authoritative decisions were already satisfied

- **§2 (decisions at any time, any stage)** — `apply_outcome()` never checks or blocks on Stage; already directly tested (5A's O/P/Q).
- **§3/partially §15 (information vs. decision — the SEPARATION principle)** — Stage/Outcome were already cleanly separate from each other; only the STAFF-REPORTED-FACT half was missing (see gaps).
- **§4 (notes everywhere, append-only, chronological)** — `ApplicationNote` + `get_selection_notes_history()` already covered Application/Stage/Outcome/Queue/Primary-Screening/Candidate-Flag contexts and Phone/In-Person's own note fields, sorted chronologically, shown at the bottom of Decision Summary.
- **§6 (HOLD structurally)** — `SelectionReminder.due_date`/`.note_text` already supported time-based (a date) and condition-based (a note, no date) holds structurally; only the restaurant-wide "bring back to attention" surfacing was missing.
- **§7 (STOP reopenable, history preserved)** — `reopen_application()` already works on any CLOSED Application, `is_reopen_event` flags it, nothing is deleted.
- **§8 (mandatory reason on a real decision change)** — already achievable via each Outcome's own restaurant-configurable `requires_reason` flag.
- **§9 (HIRABLE needs no separate reason)** — already the natural behavior for any Outcome with `requires_reason=False`; only the NAME was wrong (see gaps).
- **§16 (full historical reconstructability)** — append-only throughout; nothing overwrites Stage/Outcome/Flag/Reminder rows.
- **§17 (out-of-scope items)** — no Training engine, no Trainer UI, no Business Domain/Employee code, no Compliance service exists anywhere in Selection; verified structurally.

## 3. Genuine gaps found (and fixed)

1. **"HIRE" instead of "HIRABLE"** (§5/§9/§10/§13) — the seeded positive Outcome was literally named "Hire," which the current rules explicitly forbid, and there was no seeded "HIRABLE / DECLINED."
2. **No INFORMATION/EVENT log** (§3/§15) — nothing distinguished a staff-reported fact ("a server took a call...") from a Selezionatore note or decision; only `ApplicationNote` (a note) and `SelectionOutcomeDecision` (a decision) existed.
3. **No Training-downstream example Outcomes** (§11/§12) — "Training Withdrawn"/"Training Check Not Passed" did not exist, so there was no demonstrated way for a "Training Check Not Passed" fact to become a surfaced `CandidateFlag`, and the Primary Screening AI evaluator's evidence package (Task 3D-FIX, which predates `CandidateFlag`) never included Candidate Flags at all — a restaurant genuinely could not yet use that historical fact in Primary Screening.
4. **No restaurant-wide "reminders due" surfacing** (§6) — a time-based HOLD's reminder was only visible by opening that specific Application's own Decision Summary; nothing proactively brought it back to attention.
5. **Missing custom-Outcome wizard metadata** (§14) — "who has authority to apply it" and "candidate- vs. restaurant-driven" were not collectible anywhere.

**Explicitly considered and NOT implemented**, to avoid a broad, risky change: a new engine-level "any decision change always requires a reason" gate. The existing per-Outcome `requires_reason` flag already delivers §8's intent in a way consistent with Selection's own "RF-One never imposes universal judgment" architecture; a hard-coded universal gate would itself be exactly that kind of imposed judgment, and would have silently broken already-relied-upon call sites (e.g. the 5A-FIX legacy `workflow_status` projection, and an existing passing test that returns an Application from Hold to Active with no reason). This boundary is documented in the new migration's own docstring.

## 4. Changes made

All additive, inside Selection only, migration `a3f8e1c6d9b4` (revises `e7c2a9f4d1b6`):
- `ApplicationNote` gained `event_type`/`reported_by`/`original_source`/`stage_at_time` (all nullable); `application_service.record_information_event()` is the one new function that writes a `context_type="INFORMATION_EVENT"` row and touches nothing else about the Application.
- `SelectionOutcomeDefinition`/`Snapshot` gained `authority_label`/`driven_by` (both free-text/informational, matching the existing `performed_by` no-RBAC-exists convention); wired into `outcome_service.create_outcome_definition`/`update_outcome_definition`/snapshot and the `/selection-outcomes` wizard form.
- `industry/restaurant_templates.seed_default_selection_outcomes()`: the old "Hire" seed is renamed **in place** to "Hirable" for any restaurant that already had it (same row id — no historical `SelectionOutcomeDecision`'s own immutable snapshot is ever touched, since those keep saying "Hire" forever, exactly as true at the time); a brand-new restaurant gets "Hirable" directly. Added "Hirable / Declined," "Training Withdrawn," and "Training Check Not Passed" (the last `creates_candidate_flag=True`, `authority_label="Trainer"`).
- `primary_screening_ai_evaluator.build_evidence_package()` now includes active Candidate Flags (grouped under `APPLICATION_HISTORY`) so a restaurant's Criterion can actually use a "Training Check Not Passed" fact, automatically or manually.
- `outcome_service.list_due_reminders()` (new) surfaces every unresolved, date-passed reminder restaurant-wide; shown as a "Reminders Due" card on the Primary Screening Queue page.
- Active Candidate Flags are now displayed on the Primary Screening Queue, Primary Screening Detail, and CV Review pages (previously shown only on Application Detail/Decision Summary) — closing §12's explicit "immediately visible at Primary Screening/CV Review" requirement.
- A "Record Information / Event" form was added to the Decision Summary page, visually and functionally separate from "Apply an Outcome."
- One pre-existing 5A-FIX test's 3 references to the old seeded name `"Hire"` were updated to `"Hirable"` (a direct, necessary consequence of the rename — not a behavior change).

## 5. Notes/timeline behavior

Unchanged in mechanism — still the single `get_selection_notes_history()` query. An Information/Event entry now appears there labeled "Information / Event," formatted as `[EVENT_TYPE] description (source: ...)`, with `author` populated from `reported_by` — verified directly to appear correctly interleaved chronologically alongside ordinary notes.

## 6. Decision/outcome behavior

Unchanged: append-only `SelectionOutcomeDecision`, applicable at any Stage, reopenable always. Verified directly (again) that applying HIRABLE during Primary Screening works with zero reason required, and that Stop/Hold's own `requires_reason=True` is untouched.

## 7. HIRABLE / DECLINED behavior

Verified directly: applying "Hirable," then later "Hirable / Declined," leaves BOTH decisions in `list_outcome_history()` — the original HIRABLE row is never overwritten — and the two Outcome Definitions (`Hirable / Declined` vs. `Stop`) are distinct rows with distinct meanings, never conflated.

## 8. Training-boundary behavior

No Training engine, Trainer UI, or Business Domain code was added — confirmed structurally (`outcome_service.py`'s own source contains no Employee/Business Domain reference). "Training Withdrawn"/"Training Check Not Passed" are ordinary, restaurant-editable Outcome Definitions applied through the exact same `apply_outcome()` every other Outcome uses (a Selezionatore records what a Trainer reported, with `authority_label="Trainer"` as a documentation-only hint — no RBAC exists to enforce it, exactly like `performed_by` throughout). Verified directly that a "Training Check Not Passed" applied on one Application creates a `CandidateFlag` that is detectable on a second, later Application by the same person, and that this same Flag now appears inside the Primary Screening AI evidence package — closing the loop to §12's "the architecture should allow the restaurant to use that historical fact as a configurable Hard Disqualifier," while never making it automatic or universal.

## 9. Custom outcome behavior

`authority_label`/`driven_by` are now collectible via the wizard and preserved onto the immutable per-decision snapshot, alongside every field 5A already had (lifecycle effect, reopenable, note/reason requirements + pick-list, target queue, reminder, future-contact policy, Candidate Flag creation, active/version). Verified directly that both new fields persist from the live Definition onto its Snapshot.

## 10. Tests run and results

Added `_assert_selection_5a_align()` to `selection_validation.py` (14 new checks): decision applied during Primary Screening with HIRABLE needing no reason; HIRABLE never touching Business/Employee code; HIRABLE/DECLINED preserving the original HIRABLE decision and being distinct from Stop; a "Training Check Not Passed" Flag surfacing on a genuinely later Application AND inside the AI evidence package; an Information/Event never changing Stage/lifecycle/workflow_status/decision-count, preserving its own fields, and appearing in the unified Notes History; custom-Outcome `authority_label`/`driven_by` persisting onto the snapshot; HOLD open-ended (no reminder), time-based (a past-due reminder surfaced by the new restaurant-wide query), and condition-based (a no-date reminder excluded from that query but visible on the Application's own open list); and a full regression pass (Primary Screening/Phone/In-Person Plan creation).

- `python test_selection_engine.py`: **353/353 checks passed** (339 pre-existing + 14 new), zero residual rows on a fresh database.
- `python test_batch_upload.py`: **38/38 checks passed**, unaffected.
- Full migration chain (`a3f8e1c6d9b4`, revises `e7c2a9f4d1b6`) verified to apply cleanly on a fresh database AND on the shared `rfone.staging.db` (backed up first).
- Live Flask smoke test: uploaded two Applications for the same person, applied Hirable → Hirable/Declined → Training Check Not Passed on the first, confirmed the resulting Flag rendered on the Primary Screening Queue, Primary Screening Detail, and CV Review pages for the second Application; posted a real Information/Event through the actual form and confirmed the Application's `current_stage`/`lifecycle_state`/`workflow_status` were byte-identical before and after; separately verified in isolation that a restaurant with a pre-existing "Hire" row gets it renamed in place to "Hirable" (same id) rather than duplicated. No server errors at any step.

## 11. Remaining limitations belonging to future domains/tasks

- Training itself, a Trainer-specific UI/login, Business Domain employee activation, and Performance integration are all correctly NOT implemented here — Selection only preserves the Outcome/Flag facts a future integration would need, exactly as instructed.
- No RBAC/authentication exists in Selection, so `authority_label`/`driven_by`/`performed_by`/`reported_by` remain informational, unenforced free text everywhere (a pre-existing, explicitly accepted 5A limitation, unchanged here).
- `list_due_reminders()` only detects TIME-based holds (a passed `due_date`); a CONDITION-based hold has no mechanism to detect when the external condition itself resolves — by design, since RF-One cannot observe an external fact on its own; it remains visible on the Application's own open-reminders list for manual review.
- `record_information_event()` is a single free-text `event_type` field, not a restaurant-configurable event-type taxonomy — sufficient for the task's own example ("candidate called stating withdrawal") without adding a new configuration surface beyond what was asked.
