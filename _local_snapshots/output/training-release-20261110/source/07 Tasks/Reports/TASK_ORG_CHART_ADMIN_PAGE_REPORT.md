# TASK_ORG_CHART_ADMIN_PAGE — Report

## 0. Scope confirmation

Interactive Organizational Chart admin page (`/admin/organization`) on top of the existing Organizational Responsibility + Attention Management Foundation, extended with Backup Position (distinct from Temporary Coverage), Organizational Fallback Policy, the Organizational Coverage Check, Trigger Coverage, a structured Scope Interview harness (ADMIN/TEST ONLY, stands in for a future Cognito interview), and an AI Consistency Review service boundary (no real AI call). No Core file modified. No Tips file modified. No mobile/Android/Cognito runtime built.

## 1. Pre-existing state

Continued on `review/attention-org-runtime` (verified via `git status`/`git fetch` before starting: local and remote were identical, no concurrent work in progress). Same pre-existing, unrelated dirty "Selection/Pills/Cognitive Model" cluster left untouched.

## 2. Files created

- `03 Software/RF-One Data Store/migrations/versions/4afdc598f407_...py` — `position_backups`, `organizational_fallback_policies`, `positions.backup_required`, `attention_items.resolution_path`
- `03 Software/RF-One Data Store/rfone_data_store/organizational_coverage_check_service.py`
- `03 Software/RF-One Data Store/rfone_data_store/organizational_ai_review_service.py`
- `03 Software/RF-One Data Store/rfone_data_store/organizational_coverage_validation.py`, `test_organizational_coverage.py`
- `03 Software/RF-One Web/templates/_org_macros.html`, `_position_editor_body.html`, `admin_organization.html`, `admin_org_position_editor_fragment.html`, `admin_org_fallback_policies.html`, `admin_org_coverage_check.html`, `admin_org_position_interview.html`, `admin_org_ai_review.html`
- `03 Software/RF-One Web/static/js/org-chart.js`, `static/js/org-scope-field.js`
- `03 Software/RF-One Web/tests/test_organization_chart_http.py`
- `07 Tasks/Reports/TASK_ORG_CHART_ADMIN_PAGE_REPORT.md` (this report)

## 3. Files modified

- `03 Software/RF-One Data Store/rfone_data_store/models.py` — `Position.backup_required`, `AttentionItem.resolution_path`, `PositionBackup`, `OrganizationalFallbackPolicy`
- `03 Software/RF-One Data Store/rfone_data_store/organizational_responsibility_service.py` — Backup Position/Fallback Policy management; `resolve_effective_recipient` extended (Occupant → Temporary Coverage → Backup Position chain → Organizational Fallback), with a correction (see §6)
- `03 Software/RF-One Data Store/rfone_data_store/attention_service.py` — `route_attention` records `resolution_path`
- `03 Software/RF-One Web/organizational_responsibility_routes.py` — new routes (`/admin/organization*`, backups, fallback policies, coverage check, interview, AI review); `/admin/org/chart` now redirects to `/admin/organization`
- `03 Software/RF-One Web/templates/admin_org_position_detail.html` — now includes the shared editor body (Backup Position, subordinates, structured Scope dropdowns, Cognito interview link)
- `03 Software/RF-One Web/templates/home.html` — link relabeled "Manage Organization"
- `03 Software/RF-One Web/static/css/rf-one.css` — org chart tree, node, modal, coverage-tile CSS (plain CSS, no charting library)
- `03 Software/RF-One Web/tests/test_org_attention_admin_http.py` — 2 assertions updated for the intentional Home-link/`/admin/org/chart` changes above

**Tips and Core were not modified.**

## 4. Nomenclature (task §1)

Used exactly as specified throughout code, UI, and docs: Position, Occupant, Position Scope, Process Ownership, Backup Position, Temporary Coverage / Delegation, Organizational Fallback Policy, Attention. "PdL" is not used anywhere.

## 5. Architecture (graph, editor, structured Scope)

- **Graph**: `/admin/organization/graph-data.json` (admin-gated JSON) is the single source of truth, re-fetched on load; `static/js/org-chart.js` renders it as a nested, plain-CSS box-and-line tree (`static/css/rf-one.css`'s `.org-tree`) with click-to-expand/collapse per subtree. No graphical coordinate is ever stored — the tree is built fresh from `Position.parent_position_id` every time (task §20).
- **Click-to-edit**: clicking a node opens a modal (`#org-modal`) that fetches `/admin/organization/positions/<id>/fragment` — the SAME editor content as the full `/admin/org/positions/<id>` page, factored into a shared include (`_position_editor_body.html`) so there is exactly one implementation, not two. Closing the modal (X or backdrop click) never navigates away from the graph. Because this app has no JS framework/build step (an existing, deliberate convention), form submissions inside the modal still round-trip through a normal POST; each carries a `next` hidden field pointing back to `/admin/organization#position-<id>`, and the graph page reopens that Position's modal automatically on load (via `location.hash`) — the chart view is preserved across an edit, without introducing a SPA/AJAX rewrite of the existing form-handling code.
- **Structured Scope** (task §5): `_org_macros.html`'s `scope_field` macro + `static/js/org-scope-field.js` show exactly one correctly-typed input per `scope_type` — a Restaurant dropdown, a Legal Entity dropdown, a Process Phase dropdown, or a generic numeric/string field for the scope kinds with no dedicated table yet. No free-text Scope description field exists anywhere.

## 6. Design correction found during this task (real constraint, not arbitrary)

The original resolution order only consulted the Organizational Fallback Policy when a Process OWNER existed but was vacant — a Process with NO ownership at all (or an ambiguous one) returned unresolved immediately, never reaching the fallback. Task §14's own wording ("quando nessuna Position responsabile... può essere risolta") requires the fallback to apply in BOTH cases. Corrected `resolve_effective_recipient` (`organizational_responsibility_service.py`) to always attempt the fallback as the final step, regardless of why the normal chain failed — found by the automated test suite (`organizational_coverage_validation.py`), not assumed.

## 7. Backup Position vs. Temporary Coverage vs. Organizational Fallback (task §8/§9/§14)

Three distinct, non-overlapping mechanisms, all reusable independently:
- **Temporary Coverage** — time-bounded, precedes even a present Occupant (vacation/sickness).
- **Backup Position** — a standing, ORDERED list (`sequence`), consulted only when the Position's own Occupant/Coverage both fail; never required to be the parent or a manager; no recursion into a backup's own backup chain.
- **Organizational Fallback Policy** — company-wide (or scoped) last resort, explicit opt-in configuration, never a Core rule; for Rome's Flavours, settable to a CEO Position via `/admin/org/fallback-policies`.

## 8. Organizational / Trigger Coverage Check (task §12-13)

Evidence-based only (task's own "NON inventare Business Rules mancanti"): known Processes are the union of configured `ProcessOwnership` rows and `AttentionItem.source_process_name` values actually raised — never an invented exhaustive registry. Classifies each into FULLY_COVERED / COVERED_VIA_BACKUP / COVERED_VIA_FALLBACK / GAP / NO_OWNER / AMBIGUOUS_OWNER, flags Positions marked `backup_required` with none active, and surfaces unresolved Attention Items — all live-computed, re-runnable any time Scope/Ownership changes (`/admin/org/coverage-check`).

## 9. AI Consistency Review boundary (task §16)

This repository DOES have one existing LLM abstraction (`rfone_data_store.selection.parsing.ai_client.generate_json`), but it is Selection-Domain-owned, not promoted to shared/cross-Domain status — importing it here would invert the Foundation's own no-Domain-imports discipline. Treated as "no clean shared AI infrastructure exists" per task §16's own fallback instruction: only structured data (`AIConsistencyReviewRequest`) and a service boundary were built; `run_ai_consistency_review()` always raises `AIConsistencyReviewNotAvailable`. The ADMIN/TEST harness page shows exactly this.

## 10. Test results

- `test_organizational_coverage.py` (new, service layer): **14/14** — Backup Position resolution, ordered chain fallthrough, Fallback Policy (before/after configuration), Trigger Coverage for owned-vacant and never-owned Processes, backup_required gap detection, Coverage Check classification/counts, AI boundary never calling real AI.
- `test_attention_org_runtime.py` (regression, unaffected by the extended resolution order): **22/22**.
- `test_organization_chart_http.py` (new, HTTP/UI): **45/45** — Home link authorization, every new admin route's 403/redirect-to-login/200 gating, graph data reflects DB hierarchy (parent change, vacancy, gap flag) with NO static coordinates, click-to-edit fragment, structured Scope, Backup Position/Temporary Coverage/Fallback Policy creation via the UI, Coverage Check page content, Scope Interview harness (labeled ADMIN/TEST ONLY, persists structured `ProcessOwnership`, never prose), AI review page states NOT YET IMPLEMENTED.
- `test_org_attention_admin_http.py` (regression): **15/15** after updating 2 assertions for this task's own intentional changes (Home link text, `/admin/org/chart` now redirecting).
- Regression, unaffected: Tips distribution engine/rules/import-concurrency (29/27/26), Legal Entities/Accounts-Domains/Compensation/Training (17/38/30/29).

## 11. Blockers

None.

## 12. Confirmation

No Core file modified. No Tips file modified. No mobile/Android/Cognito runtime built. Branch `review/attention-org-runtime`, not merged, not deployed.
