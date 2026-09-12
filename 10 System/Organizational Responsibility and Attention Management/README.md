# Organizational Responsibility and Attention Management

**Status:** Active — minimum shared runtime implemented (TASK_ATTENTION_ORG_RUNTIME). Not frozen; open items below remain for future work.

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
- **Position Scope** (`models.PositionScope`) — CORPORATE/BRAND/LEGAL_ENTITY/OPERATIONAL_UNIT/RESTAURANT/OPERATIONAL_AREA/DOMAIN/MODULE/PROCESS/PROCESS_PHASE/GLOBAL, mirroring `AuthorityGrant`'s own established scope pattern (generic `scope_id` for tableless dimensions, real `scope_id` for Restaurant/Legal Entity, a string `scope_key` for Domain/Module/Process/Phase).
- **Occupant** (`models.PositionAssignment`) — Position -> Acting Identity, effective-dated (`valid_from`/`valid_to`); a Position with no current row is VACANT, never an error.
- **Temporary Coverage** (`models.PositionTemporaryCoverage`) — the same Delegation concept `AuthorityGrant` already implements for Authority, applied to Position occupancy: explicit Grantor, bounded duration, revocable.
- **Process Ownership** (`models.ProcessOwnership`) — Process/Phase (named by plain `domain`/`module`/`process_name`/`phase` strings, like `OperationalSignature` already does — no competing Process registry) -> responsible Position, with an optional scope override.
- **Attention Item** (`models.AttentionItem`) — a cross-Domain "requires human attention" record: priority (CRITICAL/HIGH/MEDIUM/LOW, always supplied by the caller, never computed from a fixed table here), status (OPEN/ACKNOWLEDGED/RESOLVED/CANCELLED), and the recorded routing outcome.
- **Two services**, both flat at the top level of `rfone_data_store/` (same placement as `authority_service.py`): `organizational_responsibility_service.py` (`resolve_process_owner`, `resolve_current_occupant`, `resolve_active_coverage`, `resolve_effective_recipient`) and `attention_service.py` (`create_attention`, `route_attention`, `acknowledge_attention`, `resolve_attention`, `cancel_attention`, `reprioritize_attention`, `list_attention_for_identity`, `list_unresolved_routing`).
- **ADMIN/CONFIGURATION/TEST HARNESS web screens** (`03 Software/RF-One Web/organizational_responsibility_routes.py`, `/admin/org/*`) — configure Positions/Scope/Occupants/Coverage/Process Ownership, inspect Attention Items and routing results. Explicitly labeled as such in every template; not an operational interface.

---

## What this does NOT implement (deliberately out of scope for this task)

- **Cognito / mobile / push delivery.** `route_attention` determines and records the resolved recipient only — it delivers nothing anywhere. No PWA, native app, or push infrastructure exists in this repository (verified by inspection during this task); building one is a separate, future task.
- **Business-specific escalation policy.** Core itself does not fix a universal escalation rule (`Organizational Responsibility.md` §5; `12_Attention_Management.md` §9) — this runtime resolves the current PRIMARY recipient (owner's occupant, or active coverage) and reports "unresolved" otherwise; it never guesses a fallback (e.g. "escalate to the superior").
- **Domain integration.** No Domain (Tips included) has been wired to create real `ProcessOwnership`/`AttentionItem` rows by this task. `03 Software/Tips/`'s existing `TipPaymentInstruction.priority`/`failure_class` fields (from the earlier Tips Core 2.0 pilot) remain plain Domain data, not yet connected to this Foundation — that connection is future integration work, not built here.
- **Real organizational data.** No Rome's Flavours Position/Person is created (task §14) — every row this task's own tests/demo create is `TEST/DEMO`-labeled synthetic data, rolled back at the end of each test run.
- **Aggregation logic for MEDIUM/LOW Attention Items**, priority-history audit trail, and multi-hop temporary-coverage chains (only one hop of coverage is followed by `resolve_effective_recipient` — see that function's own docstring).

---

## Current implementation references (`03 Software/`)

- `03 Software/RF-One Data Store/rfone_data_store/models.py` — `Position`, `PositionScope`, `PositionAssignment`, `PositionTemporaryCoverage`, `ProcessOwnership`, `AttentionItem`, and their scope/phase/priority/status constants
- `03 Software/RF-One Data Store/rfone_data_store/organizational_responsibility_service.py` — Position/Scope/Occupant/Coverage/Process Ownership resolution
- `03 Software/RF-One Data Store/rfone_data_store/attention_service.py` — Attention Item creation, routing, lifecycle
- `03 Software/RF-One Data Store/migrations/versions/a6aed1d9d2ed_add_organizational_responsibility_and_attention.py` — the schema migration for the six tables above
- `03 Software/RF-One Data Store/rfone_data_store/attention_org_runtime_validation.py`, `test_attention_org_runtime.py` — the service-layer test suite (22 checks, no Domain package imported)
- `03 Software/RF-One Web/organizational_responsibility_routes.py`, `templates/admin_org_*.html` — the ADMIN/CONFIGURATION/TEST HARNESS UI
- `03 Software/RF-One Web/tests/test_org_attention_admin_http.py` — the HTTP-layer smoke test (16 checks)

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

---

## Related documents

- `CLAUDE.md` — Core ≠ Domain ≠ Product ≠ Runtime, and the canonical top-level repository structure
- `00 Core/Organizational Responsibility.md`, `00 Core/ConceptualArchitecture/12_Attention_Management.md` — the Core conceptual definitions this area implements
- `00 Core/ConceptualArchitecture/09_Identity_Authority_and_Accountability.md`, `10 System/Identity & Access/README.md` — Acting Identity/Authority/Delegation, which `PositionAssignment`/`PositionTemporaryCoverage` reuse by foreign key (via the already-existing `acting_identities` table) without modifying that (frozen) area
- `01 Domains/Business Domain/Restaurant/Tips/Tips Payment Execution.md` — the earlier Tips Core 2.0 pilot whose own blocker report (§5 of that document) is what this task resolves as shared Foundation, not as a Tips-specific shortcut
- `10 System/README.md` — the System top-level area's own purpose and boundary
- `03 Software/README.md` — where the corresponding implementation code lives
- `07 Tasks/Reports/TASK_ATTENTION_ORG_RUNTIME_REPORT.md` — this task's implementation report
