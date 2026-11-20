# GLOBAL_INTEGRITY_FIX_002 — Stable Acting Identity + Selection Authority Consolidation Report

**Scope:** Findings C-1 (no stable Acting Identity), I-4 (inconsistent Selection authority patterns), and I-12 (no regression coverage for ownership/authority logic) from `07 Tasks/Reports/RF_ONE_GLOBAL_INTEGRITY_REVIEW_001.md`. Baseline commit: `7fcb1a670d1f399af36edf0a154200d017071e66`. No Cognito/production Authentication, no enterprise RBAC, no Selection redesign, no C-2 (Outcome split-brain) or tenant-architecture work performed.

**Note on starting state:** the shared `ActingIdentity` model (`models.py`) and several `*_identity_id` FK columns (`SelectionSessionAssignment.acting_identity_id`, `ApplicationOwnership.acting_identity_id`/`assigned_by_identity_id`, `SelectionRuleSetVersion.confirmed_by_identity_id`, `SelectionRuleChange.performed_by_identity_id`, `ComplianceDisposition.performed_by_identity_id`) were already present in `models.py` at the start of this task, left by a prior session interrupted before completing this fix (discovered mid-implementation, not before — see the checkpoint conversation). No migration, service-layer rewiring, identity resolver, routes/UI, or tests existed yet for that schema. This report covers completing the fix from that partial schema state, and reconciles/verifies every pre-existing column against the requirements below.

---

## 1. Files Changed

**Created:**
- `03 Software/RF-One Data Store/rfone_data_store/acting_identity_service.py` — the shared Acting Identity substrate + pre-Authentication resolver.
- `03 Software/RF-One Data Store/rfone_data_store/selection/authority_service.py` — the consolidated I-4 authority-checking convention.
- `03 Software/RF-One Data Store/migrations/versions/e1a4c8f2b6d9_add_acting_identity_selection_authority.py` — the migration (down_revision `a2d8f4c1b9e6`, current head).
- `03 Software/Selection/templates/identity_switch.html` — the identity-selection/registration screen.
- `03 Software/Selection/test_acting_identity_http.py` — new permanent HTTP-level trust-boundary regression suite (task §23).
- `07 Tasks/Reports/GLOBAL_INTEGRITY_FIX_002_ACTING_IDENTITY_SELECTION_AUTHORITY_REPORT.md` (this file).

**Modified:**
- `03 Software/RF-One Data Store/rfone_data_store/models.py` — added `performed_by_identity_id` to `ApplicationStageTransition` and `SelectionOutcomeDecision` (Stage transitions and Outcome decisions, explicitly named priority records per task §10; not present in the pre-existing partial schema).
- `03 Software/RF-One Data Store/rfone_data_store/selection/ownership_service.py` — rewritten to key every ownership/authority comparison on `ActingIdentity` id.
- `03 Software/RF-One Data Store/rfone_data_store/selection/session_service.py` — `assign_selezionatore` now takes `acting_identity_id`; added `get_assignment_for_identity`.
- `03 Software/RF-One Data Store/rfone_data_store/selection/rule_set_service.py` — `confirm_rule_set_version` now requires `acting_identity_id`; wires `authority_service`.
- `03 Software/RF-One Data Store/rfone_data_store/selection/rule_change_service.py` — `propose_rule_change` accepts `acting_identity_id`; wires `authority_service`.
- `03 Software/RF-One Data Store/rfone_data_store/selection/compliance_service.py` — `record_disposition` accepts `performed_by_identity_id`.
- `03 Software/RF-One Data Store/rfone_data_store/selection/stage_service.py` — `set_stage` accepts `performed_by_identity_id`.
- `03 Software/RF-One Data Store/rfone_data_store/selection/outcome_service.py` — `apply_outcome`/`reopen_application` accept `performed_by_identity_id`.
- `03 Software/RF-One Data Store/rfone_data_store/selection_validation.py` — existing Task 5C/5F scenarios ported to identity-based calls; 9 new regression checks added (I-12).
- `03 Software/Selection/app.py` — the pre-Auth identity resolver, `/identity/switch` + `/identity/register` routes, and every consequential route listed in §7-§12 below updated to stop trusting client-submitted actor text.
- `03 Software/Selection/templates/{base,dossier,decision_summary,primary_screening_detail,session_detail,alerts_home}.html` — actor text fields removed/replaced per §7/§19.

---

## 2. Acting Identity Model/Location

`models.ActingIdentity` (`rfone_data_store/models.py`, table `acting_identities`) — placed at the top of the shared `models.py`, in the same file every Domain's tables already live in, explicitly NOT inside `selection/`, satisfying task §3's "must not live inside Selection-specific architecture."

Fields: `id` (PK), `kind` (`HUMAN_USER`/`SYSTEM`/`AI_AGENT`/`EXTERNAL_SERVICE`, `CheckConstraint`-enforced), `display_name`, `is_active`, `authentication_provider`/`external_subject_id` (nullable, unique together — the future-Authentication seam, task §4), `created_at`/`updated_at`. `ALL_MODELS` includes it first.

## 3. Temporary Pre-Auth Identity Resolver

`rfone_data_store/acting_identity_service.get_current_acting_identity(session, *, requested_identity_id=None)` — resolution order: (1) `requested_identity_id`, only if it resolves to an existing, active `ActingIdentity` row; (2) the `RFONE_DEV_ACTING_IDENTITY_ID` environment variable, same validation; (3) a deterministic, idempotently-bootstrapped default `HUMAN_USER` identity ("Local Operator (pre-Authentication)").

`Selection/app.py`'s `_current_identity(session)` calls this with `requested_identity_id=flask_session.get("acting_identity_id")` — a value set ONLY by `/identity/switch` (POST) after validating the submitted id against a real, active `ActingIdentity` row, stored in a signed Flask session cookie (`app.secret_key`, a fresh random value per process — explicitly not a production Authentication secret; see §19). No route reads an actor identity from a plain request-form field. `/identity/register` lets an operator create a new `HUMAN_USER` row (dev-only roster management, not proof of identity) and immediately switches to it.

## 4. SYSTEM Identity Behavior

`acting_identity_service.get_or_create_system_identity(session)` — idempotent get-or-create keyed on `(authentication_provider="rfone-internal", external_subject_id="SYSTEM")`. The migration bootstraps the same row at upgrade time using the identical key, so calling the runtime function afterward always returns the migration's row rather than creating a duplicate (verified — regression check C). No code in this fix writes a bare `"SYSTEM"` string as an actor; nothing in the pre-existing codebase was found doing so for a newly-created record either (the original C-1 finding's concern was about the risk pattern, not an existing instance to fix).

## 5. Session Assignment Changes

`SelectionSessionAssignment.acting_identity_id` (pre-existing column; unique with `session_id`) is now populated on every new assignment. `session_service.assign_selezionatore()` requires `acting_identity_id`, resolves the identity, derives `selezionatore_name` from `identity.display_name` (display text only), and reactivates an existing assignment by identity id rather than by name. New `get_assignment_for_identity()` is the identity-keyed lookup `authority_service` uses; the old `get_assignment_for_selezionatore()` is kept, explicitly documented as legacy/historical-only, never used for an authorization comparison.

## 6. Ownership Changes

`ownership_service.py` (`take_in_charge`, `can_reassign`, `reassign`, `can_write`, `assert_can_operate`) all now take `acting_identity_id`/`actor_identity_id` (ints), never a name. `can_write`/`can_reassign` return `False` (not an exception, not a guess) whenever the current owner's ownership row has no `acting_identity_id` at all — i.e. a historical, pre-fix row — rather than fabricating an identity match from text (Historical Integrity, task §11/§20). The private `_authority_order` helper is gone; authority comparisons delegate to `authority_service.is_strictly_superior`.

## 7. HTTP Form Trust-Boundary Changes

Routes changed to resolve the actor server-side via `_current_identity(session)` instead of reading `request.form.get("actor"/"owner_name"/"performed_by"/"confirmed_by"/...)`:

- `application_take_in_charge`, `application_set_stage`, `application_apply_outcome`, `application_reopen`, `trainable_gap_review`, `primary_screening_override_hard_disqualifier` — actor resolved server-side; `own_svc.assert_can_operate(session, application_id, actor.id)` is the one choke point all six now share.
- `application_reassign` — performer resolved server-side; the form now selects only the TARGET (`new_owner_identity_id`, an existing Session assignment's stable id), never a typed name (task §9's A/B/C distinction).
- `session_assign_selezionatore` — form selects an existing, registered `ActingIdentity` by id (`acting_identity_id`), never a typed name.
- `session_confirm_rule_set`, `session_propose_rule_change` — actor resolved server-side; `confirmed_by`/`performed_by` text fields removed from the routes (still accepted as *optional* parameters at the service layer for non-HTTP/system callers — see §10/§11).
- `compliance_disposition_create` — actor resolved server-side.
- `inbound_correct_classification`, `inbound_acknowledge_alert` — actor resolved server-side (Tier 2 — see §12/§19 for why no schema column was added here).

`identity_switch.html`/`base.html` render the current identity and a switch link everywhere; no form asks a user to type their own name for a consequential action anymore (task §19) except the deliberately-scoped exceptions in §19 below.

## 8. Authority-Check Consolidation (I-4)

`rfone_data_store/selection/authority_service.py` is the one reconciled convention:
- `get_authority_order_for_identity_in_session` / `is_strictly_superior` — the Session-scoped ordering `ownership_service` used to compute privately, now identity-keyed and shared.
- `check_authority_for_action(restaurant_id, action_type, identity_id, session_id)` — wires `governance_service.get_governance_requirement_for_action` into an actual enforcement path for the first time. Called from `rule_set_service.confirm_rule_set_version` (`ACTION_CONFIRM_RULE_SET`) and `rule_change_service.propose_rule_change` (`ACTION_PROPOSE_RULE_CHANGE`) whenever an `acting_identity_id` is supplied. No configured requirement for an action type means the action is permitted — governance stays opt-in, per `governance_service`'s own pre-existing documented behavior; only a restaurant that explicitly configures a `SelectionGovernanceRequirement` gets a gate.

`ownership_service`'s peer/superior reassignment rule and `rule_set_service`/`rule_change_service`'s new governance gate are now two composable layers through the same module, rather than four independent, inconsistent patterns.

## 9. `governance_service` Disposition

**Wired in**, not retired (task §14 option A) — it was fully configured and structurally sound; the gap was purely "nothing calls it." `authority_service.check_authority_for_action` is now that caller. No change was made to `governance_service.py` itself.

## 10. Rule Set Confirmation Changes

`rule_set_service.confirm_rule_set_version(session, session_id, *, acting_identity_id, note=None, version_id=None)` — `confirmed_by` (free text) is no longer an accepted parameter; it is derived from `identity.display_name` and stored alongside the new `confirmed_by_identity_id`. Enforces `authority_service.check_authority_for_action` before confirming. No change to the confirmation semantics (one confirmation per version, activates the Session, historical `confirmed_by` text preserved).

## 11. Rule Change Changes

`rule_change_service.propose_rule_change(..., acting_identity_id=None, performed_by=None, ...)` — when `acting_identity_id` is given (every HTTP route now always supplies it), `performed_by` is derived from it, `performed_by_identity_id` is stored, and `authority_service.check_authority_for_action` (`ACTION_PROPOSE_RULE_CHANGE`) is enforced. `performed_by` alone remains accepted as plain descriptive text for a caller with no identity to resolve — Rule Change is gated by the Session being `ACTIVE`, not by a per-actor ownership comparison, so this is a lower-stakes path than ownership/rule-set confirmation (documented explicitly in the function's own docstring). `SUBSEQUENT_ONLY`/`ENTIRE_SESSION` semantics are unchanged.

## 12. Consequential-Action Actor Changes

- **Stage transitions** (`ApplicationStageTransition`) and **Outcome decisions** (`SelectionOutcomeDecision`) — new `performed_by_identity_id` FK added (not present in the prior partial schema; added in this task because both are explicitly named priority records in task §10). `stage_service.set_stage`/`outcome_service.apply_outcome`/`reopen_application` accept and store it.
- **Compliance dispositions** (`ComplianceDisposition.performed_by_identity_id`, pre-existing column) — now populated from the HTTP route.
- **Primary Screening Hard Disqualifier override** — no new column (the evaluation table has no actor field at all, before or after); the HTTP-level fix is the `assert_can_operate` choke point now receiving a real identity id instead of typed text.
- **Trainable Gap correction** — same choke-point-only treatment; `TrainableGap.overridden_by` remains free text, unchanged, since `authority_service`'s enforcement happens at the `assert_can_operate` gate before this write, not by adding a second identity column to a table the review did not name as a schema gap.
- **Inbound classification correction / acknowledgement** — Tier 2 (HTTP trust-boundary only, no schema change — see §19): the route resolves the real actor and passes `actor.display_name` into the existing free-text `corrected_by`/`acknowledged_by` params; a client can no longer submit an arbitrary name, but there is no `*_identity_id` FK on `InboundCommunication` to populate, since the pre-existing partial schema (left by the interrupted prior session) did not add one and the review did not name this table among C-1's schema-level evidence.

## 13. Operational Signature Alignment

Every action in §12 above now preserves: Acting Identity (FK, not just text), action (the route/function itself), timestamp (`created_at`/`decided_at`, pre-existing), context (`application_id`/`session_id`, pre-existing), reason (where the action already required one), and the relevant Rule Set version (`SelectionRuleSetVersion`/snapshot references, pre-existing and unchanged). No second, generic Audit platform was built — the existing Selection historical tables are what now carry a stable identity reference, per task §18's explicit instruction.

## 14. Historical Compatibility Strategy

Purely additive: every new `*_identity_id` column is nullable, and no historical row's free-text actor field was rewritten, backfilled, or used to guess an identity. `ownership_service.can_write`/`can_reassign` treat a historical row with `acting_identity_id IS NULL` as **unverifiable, not owned-by-the-caller** — the safe, honest default (deny match) rather than falling back to a string comparison that would reintroduce the exact vulnerability this fix removes. Regression check T (§16) exercises this directly: a legacy no-identity row remains fully readable through `list_ownership_history`, with no fabricated identity attached.

## 15. Migrations

One migration: `e1a4c8f2b6d9_add_acting_identity_selection_authority.py`, `down_revision = 'a2d8f4c1b9e6'` (the confirmed head at task start). Creates `acting_identities`; adds nullable, indexed `*_identity_id` FK columns to `selection_session_assignments` (+ new unique constraint), `application_ownerships` (two columns), `selection_rule_set_versions`, `selection_rule_changes`, `compliance_dispositions`, `application_stage_transitions`, `selection_outcome_decisions`; bootstraps the SYSTEM identity idempotently (checked by `(provider, subject)` before inserting). All SQLite `ALTER`s use `batch_alter_table`, matching every prior migration's convention. `downgrade()` reverses every step, dropping the FK/columns/table in dependency order. No existing migration was rewritten. Verified: applies cleanly to head on every disposable test database run in §18 (36 → 37 total migrations, single linear chain, no branching).

## 16. Targeted Security/Authority Tests (I-12)

Extended `rfone_data_store/selection_validation.py`'s existing Task 5C (`_assert_session_ownership_rule_governance`) and Task 5F (`_assert_compliance_audit_domain_closure`) suites — ported every `take_in_charge`/`reassign`/`confirm_rule_set_version`/`propose_rule_change`/`assign_selezionatore` call to stable `ActingIdentity` ids instead of name strings (creating `Alex`/`Jordan`/`Morgan` as real `ActingIdentity` rows), and added 9 new checks covering task §22's letter list:
- **G** (as an added assertion inside the existing 5C-I/J block): an arbitrary identity (`Morgan`) cannot be treated as the current owner (`can_write` false).
- **A**: ownership authorization keys on `ActingIdentity.id`, not display name.
- **B**: a `HUMAN_USER` identity works and has a stable id.
- **C**: SYSTEM identity bootstrap is deterministic/idempotent (same id returned twice).
- **F**: renaming an identity's `display_name` does not change `can_write`'s result for the same id.
- **T**: a historical, no-identity ownership row remains readable via `list_ownership_history`, with no fabricated identity attached.
- **Q/Q2**: a restaurant-configured `SelectionGovernanceRequirement` for `ACTION_CONFIRM_RULE_SET` actually blocks an unqualified identity and permits a qualified one (the I-4 wiring, exercised end-to-end for the first time).
- Existing checks K/L/M (peer rejected, owner can reassign, superior can reassign) and the 5F suite's ownership/rule-change flow were preserved as identity-based equivalents of the same scenarios, not weakened.

All cleanup blocks were extended to delete the synthetic `ActingIdentity` rows (and, for the new governance check, the `SelectionGovernanceRequirement` row) after every dependent row is gone, preserving the suite's "always cleans up" discipline.

## 17. HTTP-Level Tests

New `03 Software/Selection/test_acting_identity_http.py` (Werkzeug test client, throwaway SQLite database, mirrors `test_batch_upload.py`'s convention exactly). Two independent test clients ("Alex", "Jordan") register via the real `/identity/register` route. Checks:
1. `POST /applications/<id>/take-in-charge` with a forged `owner_name="Totally Someone Else"` form field — the recorded owner is the server-resolved identity ("Alex"), never the forged text; `acting_identity_id`/`assigned_by_identity_id` both correctly point at Alex.
2. `POST /applications/<id>/reassign` from Jordan (a peer, no configured authority) forging `performed_by_identity_id=<Alex's id>` in the request body — ownership is unchanged; the forged field cannot make Jordan act "as" Alex.
3. A legitimate reassignment (Alex, the real owner, selecting Jordan via `new_owner_identity_id`) succeeds and correctly records both the new owner and the real performer.
4. `POST /applications/<id>/stage` from a non-owner, non-superior identity via the real route — blocked; Stage is unchanged.

Result: 12/12 checks passed.

## 18. Full Regression Results

All suites run against a fresh, self-provisioned disposable SQLite database (GLOBAL_INTEGRITY_FIX_001's `resolve_test_database_url`), never the operational `data/rfone.db`/`data/selection.db` (confirmed unchanged by file mtime before/after: `rfone.db` unmodified since Aug 31, `selection.db` unmodified since Sep 3, neither touched by any run in this task):

| Suite | Result |
|---|---|
| `test_selection_engine.py` (`selection_validation.py`, includes all new checks) | SUCCESS — 641/641 |
| `test_organization_validation.py` | SUCCESS — 14/14 |
| `test_payroll_engine.py` | SUCCESS — 52/52 |
| `test_restaurant_profile_bootstrap.py` | SUCCESS — 14/14 |
| `test_sales_validation.py` | SUCCESS — 27/27 |
| `test_tips_engine.py` | SUCCESS — 54/54 |
| `test_purchasing_engine.py` | SUCCESS — 24/24 |
| `Selection/test_batch_upload.py` | SUCCESS — 38/38 |
| `Selection/test_acting_identity_http.py` (new) | SUCCESS — 12/12 |

Migration `e1a4c8f2b6d9` applies cleanly to head on every run above (37 migrations, single linear chain, no branch). Two pre-existing, unrelated `SAWarning`s (row-count mismatches in `phone_interview_question_instances`/`selection_rule_change_impacts` cleanup, both outside any code this task touched) were observed and are not failures.

## 19. Explicit Remaining Gap Before Production Authentication

This fix establishes stable identity and authority **semantics**. It does **not** make RF-One production-authenticated. Until a real Authentication provider (e.g. Cognito, per `03 Software/Identity Authority and Security Architecture.md`) is connected:

- `acting_identity_service.get_current_acting_identity()`'s resolution (a signed local session cookie an operator can freely switch, or a self-registered identity) is a **development/pre-production convenience**, not proof of identity. Anyone with access to the running app can register an identity and switch to it — this is by design (task §5/§20's own explicit instruction not to build fake Authentication), but it means the current system is not safe for public/multi-tenant production deployment.
- Replacing this is scoped to be cheap: only `get_current_acting_identity()`'s body needs to change to verify a real provider token instead of a session-selected id; no Domain route should need to change, since every route already calls only `_current_identity(session)`.
- **Not addressed in this fix, left as explicit residual scope** (deliberately, to keep this fix bounded — task §10/§17's "do not mechanically redesign every field"):
  - `session_rule_set_update`'s `created_by` field, and Job Posting/Channel Variant `approved_by`/`created_by` fields, and `application_questions_home.html`/`primary_screening_criteria_home.html`'s `performed_by` fields — still free-text, since none of them is currently load-bearing for an authorization decision (they are pre-confirmation configuration edits or descriptive labels, not gated actions).
  - Inbound communication classification correction/acknowledgement (`InboundCommunication.classification_corrected_by`/`alert_acknowledged_by`) — HTTP trust-boundary fixed (server resolves the actor), but no `*_identity_id` FK column was added; these remain display text only.
  - Scheduling actions (`scheduling_service.py`) were not touched — the reviewed code paths are candidate self-service via an opaque token, not a Selezionatore-attributed action, so C-1 does not clearly apply there; this should be re-examined during a future fix rather than assumed safe.
  - `SelectionRuleSetVersion`'s partial-snapshot limitation (I-2) and `restaurant_id`-as-tenant-key (C-3/I-7) are untouched, as instructed.

## 20. Confirmation: C-1 / I-4 / I-12 Status

- **C-1 (No stable Acting Identity):** **Resolved** for every load-bearing authorization comparison the review named — `ownership_service.can_write`/`can_reassign` (the review's own "the only place free text is actively load-bearing for an authorization decision") — plus Session assignment, Rule Set confirmation, Rule Change, and the two additionally-identified priority record types (Stage transitions, Outcome decisions). Residual free-text fields are all descriptive-only or pre-confirmation configuration, explicitly enumerated in §19, none of them gating an authorization decision today.
- **I-4 (Inconsistent authority patterns):** **Resolved** — `ownership_service`, `rule_set_service`, and `rule_change_service` now share one `authority_service` module for both the Session-scoped peer/superior ordering and the restaurant-configured governance gate; `governance_service.get_governance_requirement_for_action` is wired in (not dead code), verified end-to-end by regression checks Q/Q2.
- **I-12 (No regression coverage):** **Resolved** — 9 new service-level checks (A/B/C/F/G/Q/Q2/T plus the existing K/L/M/N ported to identities) in `selection_validation.py`, plus a new dedicated 12-check HTTP-level suite (`test_acting_identity_http.py`) exercising the trust boundary through real Flask routes, not just the service layer.

No unresolved contradiction was found. No unrelated file was modified (confirmed via `git status`/`git diff --stat` against the `7fcb1a6` baseline — 16 modified + 5 new files, all directly part of this fix). Nothing was committed or pushed.
