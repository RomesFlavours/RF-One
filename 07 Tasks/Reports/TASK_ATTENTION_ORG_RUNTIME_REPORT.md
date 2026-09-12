# TASK_ATTENTION_ORG_RUNTIME — Report

## 0. Scope confirmation

Minimum shared, cross-Domain runtime for Core 2.0's already-approved Organizational Responsibility and Attention Management: Position/Scope/Occupant/Temporary Coverage/Process Ownership, and Attention Item creation/routing/lifecycle. Cross-domain by construction — no Domain package (Tips included) is imported anywhere in the new code or its tests. No Core file modified. No mobile/Cognito/business-specific escalation logic built.

## 1. Pre-existing dirty state (not touched)

Same pre-existing "Selection/Pills/Cognitive Model" cluster from earlier sessions (`.env.example`, several `01 Domains/Cross Domain/...` files, `00 Core/ConceptualArchitecture/20_...md`, two new Selection/Training docs) plus the untracked `Secrets/` directory — none staged or touched. Branched from `main` (not from the still-unmerged `review/tips-core2-pilot` branch), per the task's own "questo lavoro deve essere isolato."

## 2. Audit of existing runtime (task §2)

Confirmed already implemented and REUSED, never duplicated:
- **Identity**: `ActingIdentity` (Human User/System/AI Agent/External Service) — used directly as Occupant/Delegate/Grantor.
- **Authority/Delegation**: `AuthorityGrant` — its exact design pattern (explicit Grantor, bounded duration, `revoked_at` rather than deletion) is reused for `PositionTemporaryCoverage`, in a distinct table (what is delegated is shaped differently — Position occupancy, not a domain/module/action permission).
- **Accountability**: `OperationalSignature` — its plain-string `domain`/`module`/`object_type` (no FK) pattern is reused for `ProcessOwnership`/`AttentionItem`'s own process/source identification, since no canonical cross-Domain Process registry table exists.
- **Legal Entity, Restaurant (Operational Unit)**: real tables, referenced as two of `PositionScope`'s scope kinds.
- **Corporate, Brand, Operational Unit (generic)**: confirmed NOT persisted anywhere (matches `AuthorityGrant`'s own documented finding) — `PositionScope` keeps these as generic, tableless `scope_id` kinds, exactly like `AuthorityGrant` already does.
- **Generic notifications/messages/tasks**: confirmed NOT to exist anywhere — `AttentionItem` is genuinely new, no duplication risk.

## 3. Files created

- `03 Software/RF-One Data Store/migrations/versions/a6aed1d9d2ed_add_organizational_responsibility_and_attention.py`
- `03 Software/RF-One Data Store/rfone_data_store/organizational_responsibility_service.py`
- `03 Software/RF-One Data Store/rfone_data_store/attention_service.py`
- `03 Software/RF-One Data Store/rfone_data_store/attention_org_runtime_validation.py`
- `03 Software/RF-One Data Store/test_attention_org_runtime.py`
- `03 Software/RF-One Web/organizational_responsibility_routes.py`
- `03 Software/RF-One Web/templates/admin_org_{positions,position_form,position_detail,process_ownerships,chart,attention,attention_detail}.html`
- `03 Software/RF-One Web/tests/test_org_attention_admin_http.py`
- `10 System/Organizational Responsibility and Attention Management/README.md`
- `07 Tasks/Reports/TASK_ATTENTION_ORG_RUNTIME_REPORT.md` (this report)

## 4. Files modified

- `03 Software/RF-One Data Store/rfone_data_store/models.py` — added the six new model classes and their constants, placed directly after `OperationalSignature` (the existing Identity/Authority/Accountability section)
- `03 Software/RF-One Web/app.py` — registered the new routes (same `register_*_routes` pattern as `compensation_routes.py`)
- `03 Software/RF-One Web/templates/home.html` — added the admin link
- `10 System/README.md` — indexed the new area

**Tips was not modified.** No file under `03 Software/Tips/` was touched.

## 5. Placement decision (task §15, documented as instructed)

Code: flat, top-level in `rfone_data_store/` (`organizational_responsibility_service.py`, `attention_service.py`) — the SAME placement `authority_service.py`/`acting_identity_service.py` already establish for cross-Domain shared infrastructure, not a new subpackage. Admin UI: `03 Software/RF-One Web/`, mirroring the existing Legal Entity admin precedent exactly (`admin_legal_entities`/`admin_legal_entity_new` route naming, `require_admin`/CSRF/`SessionFactory` conventions) — RF-One Web is already the established home for cross-domain/System-level admin screens. Architectural documentation: `10 System/Organizational Responsibility and Attention Management/README.md`, mirroring `10 System/Identity & Access/` exactly, per `10 System/README.md`'s own explicit statement that future cross-cutting capabilities belong there and that implementation code stays in `03 Software/`.

## 6. Design decisions forced by real constraints (not arbitrary)

- **Process identity as plain strings** (`domain`/`module`/`process_name`/`phase`), not a new canonical Process registry — mirrors `OperationalSignature`'s own, already-justified identical choice (no Domain has ever defined one universal Process table).
- **`resolve_process_owner` ignores scope only when no candidate ambiguity exists** — an earlier stricter design (scope required whenever supplied context was absent) incorrectly blocked resolution for a scoped Position when the caller had no context to supply; scope is a disambiguator between multiple candidates, not a mandatory gate — corrected after the first test run exposed it.

## 7. Test results

- `test_attention_org_runtime.py` (service layer, no Domain imported): **22/22** — covers all 14 numbered scenarios in task §17 plus the full 3-part cross-domain integration demo in task §18 (Position A/Occupant X/Scope Restaurant/Process P/Ownership/Attention routes to X; temporary coverage to Z; a NEW Attention on the same Process routes to Z; the FIRST Attention item is unaffected).
- `test_org_attention_admin_http.py` (new, admin UI): **16/16** — admin-gated (403 for non-admin, redirect-to-login for anonymous), every template renders, Position/Scope creation and Attention acknowledge/resolve work end-to-end via HTTP.
- Regression, unaffected: Tips distribution engine (29/29), Tips distribution rules (27/27), Tips import concurrency guard (26/26); RF-One Web Home/Legal Entities (17/17), Accounts/Domains (38/38), Compensation V1 (30/30), Training integration (29/29).

## 8. Blockers

None. No Core modification was required; Identity/Delegation/Process-identification constraints were all resolved by reusing existing, precedented patterns (§2, §6) rather than by a Core change or a Tips-specific shortcut.

## 9. Confirmation

No Core file modified. No Tips file modified. No mobile/Cognito/push/escalation-policy business logic built. Branch `review/attention-org-runtime`, not merged, not deployed.
