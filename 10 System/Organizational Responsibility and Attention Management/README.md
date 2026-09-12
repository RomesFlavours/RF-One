# Organizational Responsibility and Attention Management

**Status:** Active — minimum shared runtime implemented (TASK_ATTENTION_ORG_RUNTIME), extended with Backup Position, Organizational Fallback Policy, the Organizational Coverage Check, and an interactive Organizational Chart admin page (TASK_ORG_CHART_ADMIN_PAGE), then corrected for internal consistency by TASK_ORG_RUNTIME_CONSISTENCY_FIXES (RESTAURANT vs OPERATIONAL_UNIT scope UI, DELIVERY vs ORGANIZATIONAL HEALTH separation in the Coverage Check, structured AMBIGUOUS_OWNER classification, coverage-badge accuracy, and an append-only Attention routing audit trail). Not frozen; open items below remain for future work.

---

## Purpose

This is RF-One's **system-level capability that lets any Domain determine which Position owns a Process, who currently occupies that Position, and who the effective recipient of a "this requires human attention" item is right now** — the operational system that implements and enforces the abstract Core concepts already approved in `00 Core/Organizational Responsibility.md` and `00 Core/ConceptualArchitecture/12_Attention_Management.md`.

**This is NOT a Domain and NOT a Product.** It models no reusable business field and no commercial configuration. It is infrastructure any Domain (Tips, Compensation, Purchasing, Selection, and future ones) consumes identically — none of them is integrated by this task; this is foundation only.

---

## Architectural boundary

| Layer | Defines |
|---|---|
| `00 Core/Organizational Responsibility.md`, `00 Core/ConceptualArchitecture/12_Attention_Management.md` | What Position, Position Scope, Occupant, Temporary Coverage, Process Ownership, and Attention Management (priority, routing, aggregation) *mean* — abstract, domain-independent Core concepts. **Not duplicated here.** |
| `10 System/Organizational Responsibility and Attention Management/` (this area) | The operational system that *implements/enforces* those concepts: `Position`/`PositionScope`/`PositionAssignment`/`PositionTemporaryCoverage`/`ProcessOwnership`/`AttentionItem` tables, and the two services that resolve/route against them. |
| `01 Domains/` | What a specific Domain's actual organizational chart, Positions, and escalation policy are — never fixed here; a Domain (or Product) configures Positions, Scope and Process Ownership rows through the ADMIN UI or the service API below. |
| `02 Products/` | Concrete Restaurant/company configuration — which real Positions exist, who occupies them. **Not configured by this task** (task §14: no Rome's Flavours person/Position is invented here). |
| `03 Software/` | The actual implementation code (models, services, migrations, tests). This area does not own or duplicate that code — see "Current implementation references" below. |

This document does not move or duplicate genuine Core conceptual definitions — see the two Core documents above for the authoritative meaning of every concept named here.

---

## What this DOES implement

- **Position** (`models.Position`) — a stable responsibility distinct from any person, with an optional `parent_position_id`.
- **Position Scope** (`models.PositionScope`) — CORPORATE/BRAND/LEGAL_ENTITY/OPERATIONAL_UNIT/RESTAURANT/OPERATIONAL_AREA/DOMAIN/MODULE/PROCESS/PROCESS_PHASE/GLOBAL, mirroring `AuthorityGrant`'s own established scope pattern (generic `scope_id` for the still-tableless CORPORATE/BRAND/OPERATIONAL_AREA dimensions, real `scope_id` for Restaurant/Legal Entity, a string `scope_key` for Domain/Module/Process/Phase). **RESTAURANT and OPERATIONAL_UNIT are deliberately independent scope kinds, never merged/cross-matching** (TASK_ORG_RUNTIME_CONSISTENCY_FIXES §1, verified against the Restaurant Domain's own canonical docs before deciding — see the scope-constants comment in `models.py`): the Restaurant Domain's own `Restaurant Semantic Model.md` §3 maps runtime `Restaurant` to the Core **Brand** level and runtime `Location` to **Operational Unit/site** — so `OPERATIONAL_UNIT.scope_id` is presented in the admin UI against `Location` (its own dedicated dropdown), never sharing `RESTAURANT`'s id space or a raw numeric field.
- **Occupant** (`models.PositionAssignment`) — Position -> Acting Identity, effective-dated (`valid_from`/`valid_to`); a Position with no current row is VACANT, never an error.
- **Temporary Coverage** (`models.PositionTemporaryCoverage`) — the same Delegation concept `AuthorityGrant` already implements for Authority, applied to Position occupancy: explicit Grantor, bounded duration, revocable.
- **Process Ownership** (`models.ProcessOwnership`) — Process/Phase (named by plain `domain`/`module`/`process_name`/`phase` strings, like `OperationalSignature` already does — no competing Process registry) -> responsible Position, with an optional scope override.
- **Attention Item** (`models.AttentionItem`) — a cross-Domain "requires human attention" record: priority (CRITICAL/HIGH/MEDIUM/LOW, always supplied by the caller, never computed from a fixed table here), status (OPEN/ACKNOWLEDGED/RESOLVED/CANCELLED), and the LATEST routing outcome as a convenience snapshot. **Every `route_attention()` evaluation additionally appends one immutable `AttentionRoutingResolution` row** (`models.py`, `attention_service.list_routing_history`; TASK_ORG_RUNTIME_CONSISTENCY_FIXES §5) — the same append-only discipline `OperationalSignature`/`AuthorityGrant` already establish elsewhere, applied here so "Re-evaluate routing now" never destroys the record of a prior resolution, and nothing re-routes automatically when a Position/Occupant changes: only an explicit `route_attention()` call ever creates a new (historical or current) resolution.
- **Backup Position** (`models.PositionBackup`) — a STANDING, ordered escalation chain per Position, explicitly distinct from Temporary Coverage: never date-bounded, never required to be the parent Position or a manager. `resolve_effective_recipient` walks it (by `sequence`) only after a Position's own Occupant/Coverage fails to resolve — never recursing into a backup's own backup chain.
- **Organizational Fallback Policy** (`models.OrganizationalFallbackPolicy`) — explicit, opt-in COMPANY configuration ("Unowned Attention → CEO" for Rome's Flavours), never a Core or Foundation-level universal rule. Applied only as the last resort, whenever no Position/Backup Position resolves at all — including when NO Process Ownership exists, not only when an owner is merely vacant.
- **Organizational Coverage Check** (`organizational_coverage_check_service.py`) — an on-demand, evidence-based report ("if this Process/Phase raised Attention right now, is there a Position that can actually receive it?") over every Process known from configured `ProcessOwnership` OR actually-raised `AttentionItem` history — never an invented, exhaustive Process registry. Reports **two independent dimensions per Process** (TASK_ORG_RUNTIME_CONSISTENCY_FIXES §2, `ProcessCoverageEntry.status`/`.ownership_health`): **DELIVERY COVERAGE** — FULLY_COVERED / COVERED_VIA_BACKUP / COVERED_VIA_FALLBACK / GAP ("will the Attention actually reach somebody?") — and **ORGANIZATIONAL CONFIGURATION HEALTH** — CONFIGURED / NO_OWNER / AMBIGUOUS_OWNER ("does a correctly configured PRIMARY ownership actually exist?"). A Process resolved via Fallback can be delivered (COVERED_VIA_FALLBACK) while its ownership stays unconfigured (NO_OWNER) — both are always shown together, one never hides the other. AMBIGUOUS_OWNER is classified from `organizational_responsibility_service.ProcessOwnerResolution.unresolved_code` (a structured, enumerated constant), never by matching text inside `unresolved_reason`. Positions marked `backup_required` with none configured are still flagged separately.
- **AI Consistency Review boundary** (`organizational_ai_review_service.py`) — a structured request payload built from the Coverage Check, ready for a future Cognito/AI reviewer; `run_ai_consistency_review()` always raises `AIConsistencyReviewNotAvailable` today (no shared, cross-Domain AI infrastructure exists yet to call — see that module's own docstring for why the one existing Selection-Domain LLM client was not reused).
- **Three services**, all flat at the top level of `rfone_data_store/` (same placement as `authority_service.py`): `organizational_responsibility_service.py` (`resolve_process_owner`, `resolve_current_occupant`, `resolve_active_coverage`, `resolve_effective_recipient`, plus Backup Position/Fallback Policy management), `attention_service.py` (`create_attention`, `route_attention`, `acknowledge_attention`, `resolve_attention`, `cancel_attention`, `reprioritize_attention`, `list_attention_for_identity`, `list_unresolved_routing`), and `organizational_coverage_check_service.py`.
- **Interactive Organizational Chart admin page** (`/admin/organization`) — a DB-derived, click-to-expand/collapse graph with click-to-edit (a modal fragment, never losing the chart view), plus dedicated pages for Fallback Policy, the full Coverage Check, and a Scope Interview harness. Each node's delivery badge distinguishes Fully covered (no badge) / Covered via Backup / Covered via Fallback / Configuration gap (TASK_ORG_RUNTIME_CONSISTENCY_FIXES §4) — a Position actually routable via Backup/Fallback is never labelled "⚠ Coverage gap". All labeled **SYSTEM / ORGANIZATION CONFIGURATION**, never an operational interface — see `03 Software/RF-One Web/organizational_responsibility_routes.py`.
- **Scope Interview harness** (`/admin/org/positions/<id>/interview`, explicitly labeled **ADMIN / TEST ONLY**) — stands in for a future Cognito-led interview: the same structured service functions are called on submit; no interview prose is ever saved as canonical Scope.

---

## What this does NOT implement (deliberately out of scope for this task)

- **Cognito / mobile / push delivery.** `route_attention` determines and records the resolved recipient only — it delivers nothing anywhere. No PWA, native app, or push infrastructure exists in this repository (verified by inspection during this task); building one is a separate, future task.
- **Business-specific escalation policy.** Core itself does not fix a universal escalation rule (`Organizational Responsibility.md` §5; `12_Attention_Management.md` §9) — this runtime resolves the current PRIMARY recipient (owner's occupant, or active coverage) and reports "unresolved" otherwise; it never guesses a fallback (e.g. "escalate to the superior").
- **Domain integration.** No Domain (Tips included) has been wired to create real `ProcessOwnership`/`AttentionItem` rows by this task. `03 Software/Tips/`'s existing `TipPaymentInstruction.priority`/`failure_class` fields (from the earlier Tips Core 2.0 pilot) remain plain Domain data, not yet connected to this Foundation — that connection is future integration work, not built here.
- **Real organizational data.** No Rome's Flavours Position/Person is created (task §14) — every row this task's own tests/demo create is `TEST/DEMO`-labeled synthetic data, rolled back at the end of each test run.
- **Aggregation logic for MEDIUM/LOW Attention Items**, priority-history audit trail, and multi-hop temporary-coverage/backup chains (only one hop of coverage or backup is followed by `resolve_effective_recipient` — see that function's own docstring).
- **Mobile/Android/native app** — verified not to exist anywhere in this repository; the admin UI is a server-rendered web page only.
- **A real AI Consistency Review** — see "AI Consistency Review boundary" above; only the structured data and service boundary exist.

---

## Current implementation references (`03 Software/`)

- `03 Software/RF-One Data Store/rfone_data_store/models.py` — `Position` (incl. `backup_required`), `PositionScope`, `PositionAssignment`, `PositionTemporaryCoverage`, `ProcessOwnership`, `AttentionItem` (incl. `resolution_path`), `AttentionRoutingResolution` (append-only routing audit trail), `PositionBackup`, `OrganizationalFallbackPolicy`, and their scope/phase/priority/status constants
- `03 Software/RF-One Data Store/rfone_data_store/organizational_responsibility_service.py` — Position/Scope/Occupant/Coverage/Backup/Fallback/Process Ownership resolution; `ProcessOwnerResolution.unresolved_code` (`PROCESS_OWNER_NOT_FOUND`/`PROCESS_OWNER_AMBIGUOUS`) for structured classification
- `03 Software/RF-One Data Store/rfone_data_store/attention_service.py` — Attention Item creation, routing (`route_attention`, `list_routing_history`), lifecycle
- `03 Software/RF-One Data Store/rfone_data_store/organizational_coverage_check_service.py` — the Organizational/Trigger Coverage Check (`status` = delivery, `ownership_health` = organizational health, tracked independently)
- `03 Software/RF-One Data Store/rfone_data_store/organizational_ai_review_service.py` — the AI Consistency Review boundary (raises `AIConsistencyReviewNotAvailable`)
- `03 Software/RF-One Data Store/migrations/versions/a6aed1d9d2ed_...py`, `4afdc598f407_...py`, `749a28964701_add_attention_routing_resolution_history.py` — the schema migrations
- `03 Software/RF-One Data Store/rfone_data_store/attention_org_runtime_validation.py` + `test_attention_org_runtime.py` (26 checks), `organizational_coverage_validation.py` + `test_organizational_coverage.py` (20 checks) — service-layer test suites, no Domain package imported
- `03 Software/RF-One Web/organizational_responsibility_routes.py`, `templates/admin_org*.html`, `templates/admin_organization.html`, `static/js/org-chart.js`, `static/js/org-scope-field.js` — the ADMIN/CONFIGURATION/TEST HARNESS UI, including the interactive Organizational Chart and the Attention Item routing-history table
- `03 Software/RF-One Web/tests/test_org_attention_admin_http.py` (21 checks), `test_organization_chart_http.py` (49 checks) — HTTP-layer tests

No Domain currently consumes this foundation — by design, per this task's own scope.

---

## Open items

Recorded as open, not designed further here:

- Domain integration sequencing — which Domain (if any) integrates with this Foundation first, and how (e.g. Tips's `TipPaymentInstruction` creating real `AttentionItem` rows instead of only its own local `priority`/`failure_class` fields).
- Cognito's Human Interaction capability (or any other channel) actually consuming `list_attention_for_identity`/`route_attention` and delivering something to a person — not built, only the clean boundary these two services provide.
- Business-specific escalation policy configuration (vertical escalation, substitute, alternative competency, etc. — `Organizational Responsibility.md` §5 leaves this to organizational policy).
- Whether/how Corporate, Brand and Operational Unit become persisted tables (today `PositionScope.scope_id` for those three kinds remains generic/tableless, exactly like `AuthorityGrant.scope_id` already is).
- Multi-hop temporary coverage chains, and a full audit trail for `reprioritize_attention`.
- MEDIUM/LOW Attention Item aggregation (Core doc 12 §6 permits it; not implemented).
- The Restaurant Domain's own two statements about what runtime `Restaurant` "is" (`OU-Restaurant.md`'s "Extends: Operational Unit" vs `Restaurant Semantic Model.md` §3's "runtime `Restaurant` = Brand") are still not reconciled with each other in that Domain's own documentation — out of this Foundation's scope to resolve (TASK_ORG_RUNTIME_CONSISTENCY_FIXES §1 verified this rather than assuming it, and left `POSITION_SCOPE_RESTAURANT`/`POSITION_SCOPE_OPERATIONAL_UNIT` independently scoped either way).

---

## Related documents

- `CLAUDE.md` — Core ≠ Domain ≠ Product ≠ Runtime, and the canonical top-level repository structure
- `00 Core/Organizational Responsibility.md`, `00 Core/ConceptualArchitecture/12_Attention_Management.md` — the Core conceptual definitions this area implements
- `00 Core/ConceptualArchitecture/09_Identity_Authority_and_Accountability.md`, `10 System/Identity & Access/README.md` — Acting Identity/Authority/Delegation, which `PositionAssignment`/`PositionTemporaryCoverage` reuse by foreign key (via the already-existing `acting_identities` table) without modifying that (frozen) area
- `01 Domains/Business Domain/Restaurant/Tips/Tips Payment Execution.md` — the earlier Tips Core 2.0 pilot whose own blocker report (§5 of that document) is what this task resolves as shared Foundation, not as a Tips-specific shortcut
- `10 System/README.md` — the System top-level area's own purpose and boundary
- `03 Software/README.md` — where the corresponding implementation code lives
- `07 Tasks/Reports/TASK_ATTENTION_ORG_RUNTIME_REPORT.md`, `07 Tasks/Reports/TASK_ORG_CHART_ADMIN_PAGE_REPORT.md` — this Foundation's implementation reports
