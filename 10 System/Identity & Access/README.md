# Identity & Access

**Status:** Structural development **FROZEN** — **approved Domain consumption of the already-built services below is explicitly allowed and, as of Tips STEP 12B, actually happening** (Product Owner decision, baseline-closure task; see "Status: FROZEN" below for the precise scope). This README is a documentation-organization update only where structure is concerned — no NEW feature, model, or migration to Identity & Access's OWN tables is added or changed by it.

---

## Purpose

Identity & Access is RF-One's **system-level capability that governs access across the entire platform** — Core, every Domain, every Product, and every Software/runtime capability. It is the operational system that implements and enforces the abstract Core concepts of Identity, Authority, Delegation, Scope and Accountability (see "Architectural boundary" below).

**Identity & Access is NOT a Domain and NOT a Product.** It does not model a reusable business field, and it is not a commercial configuration for one customer. It is infrastructure every Domain and every Product consumes, per Core Principle 21 ("No Domain or Module may define its own independent identity, authority or audit mechanism" — `00 Core/ArchitecturePrinciples.md`).

---

## Architectural boundary

| Layer | Defines |
|---|---|
| `00 Core/ConceptualArchitecture/09_Identity_Authority_and_Accountability.md` | What Identity, Authority, Delegation, Accountability and Auditability *mean* — abstract, domain-independent, technology-independent Core concepts (Subject, Authority, Delegation, Scope, Accountability). **Not duplicated here.** |
| `10 System/Identity & Access/` (this area) | The operational system that *implements/enforces* those Core concepts: User Account, Authentication, Profiles, Functions/Permissions, Authorization, Authority levels, Branch/Location scope, data visibility, individual overrides, and audit of authorization configuration. |
| `01 Domains/` | What Authority a specific business Decision requires (e.g. who may approve a Purchase Order) — Domains remain authoritative for that business meaning; Identity & Access never redefines it. |
| `02 Products/` | Concrete Company/Branch configuration and which Users hold which Authority for a specific commercial deployment. Not defined here. |
| `03 Software/` | The actual implementation code (models, services, migrations, tests). Identity & Access does not own or duplicate that code — see "Current implementation references" below. |

This document does not move or duplicate genuine Core conceptual definitions merely because Identity & Access uses them — see the Core document above for the authoritative meaning of Identity, Authority, Delegation and Accountability.

---

## Current known concepts

As documented in [Identity Authority and Security Architecture.md](Identity%20Authority%20and%20Security%20Architecture.md) (the full technical architecture, moved here from `03 Software/`):

- User Account / Acting Identity (Human User, System/RF-One, AI Agent, External Service)
- Authentication (managed identity provider; AWS Cognito is the current preferred candidate, not locked)
- Profiles (visible role/title labels, configurable per organization, distinct from the permanent identity)
- Functions / Permissions and Authorization (server-side enforced; UI visibility is never the security boundary)
- Authority levels and Authority classes (VIEW/CREATE/EDIT/APPROVE/etc. — illustrative, not a closed enumeration)
- Branch/Location (Operational Unit) scope, and the broader Corporate/Brand/Operational Unit/Operational Area context chain
- Data visibility (multi-tenant/company logical isolation)
- Individual overrides (Delegation — bounded, accountable grants from one Acting Identity/system to another)
- The RF-One Operational Signature and its three assurance levels (Normal Authenticated Action, Explicit Confirmation, Step-Up Authentication)
- Audit Trail / audit of authorization configuration (append-only; corrections create new records, never silent overwrites)

---

## Current implementation references (`03 Software/`)

An initial software foundation exists and **remains in `03 Software/`** — it is not moved by this reorganization ("Software remains software"). It is currently frozen; no further implementation work is authorized by this document.

- `03 Software/RF-One Data Store/rfone_data_store/models.py` — `ActingIdentity`, `AuthorityGrant`, `OperationalSignature` tables and their kind/scope/assurance-level constants
- `03 Software/RF-One Data Store/rfone_data_store/acting_identity_service.py` — Acting Identity resolution/bootstrap (pre-Authentication resolver, and the JIT-provisioning hook for a verified subject)
- `03 Software/RF-One Data Store/rfone_data_store/authority_service.py` — `authorize()` and Authority grant/revoke helpers
- `03 Software/RF-One Data Store/rfone_data_store/operational_signature_service.py` — `record_operational_signature()`
- `03 Software/RF-One Data Store/rfone_data_store/technical/cognito_jwt.py` — local, JWKS-cached Cognito JWT verification boundary (no Cognito resource created; provider configuration read from the environment)
- `03 Software/RF-One Data Store/migrations/versions/a3cafbea7fe7_add_authority_grant_and_operational_.py` — the schema migration for the two tables above
- `03 Software/RF-One Data Store/rfone_data_store/identity_authority_signature_validation.py`, `03 Software/RF-One Data Store/test_identity_authority_signature.py` — the test suite
- `03 Software/User Interaction Architecture.md` §3–§6, §12 — the initial User Identity/Authentication/Authorization model, Visibility Principle, Authorization Scope and Mobile Security (a broader cross-cutting interaction-architecture document that is not moved here in full; only its Identity/Authority-relevant sections connect to this area)
- `03 Software/RF-One Data Store/migrations/versions/f5d11c7966be_add_restaurant_scope_to_authority_grant.py` — widens `AuthorityGrant.scope_type` to include `RESTAURANT` (TASK_TIPS_RESTAURANT_AUTHORITY_SCOPE_001), the first Domain-driven addition to this table's own vocabulary since the original foundation

**Tips is the first Domain to actually consume this foundation** (STEP 12B integration): `authority_service.authorize()`/`AuthorityGrant` gate Tips' Approve & Pay directly (`03 Software/RF-One Data Store/rfone_data_store/tips/payment_cycle_service.py`), scoped per-Restaurant. This is approved Domain *consumption* of already-built services, not a structural change to Identity & Access itself (the one exception, the `RESTAURANT` scope-value widening above, was itself a minimal, additive, Product-Owner-approved schema change to the existing `scope_type` vocabulary — see "Status: FROZEN" below for why this did not require lifting the freeze). No other Domain (Selection, Purchasing, etc.) has integrated with this foundation yet.

---

## Status: FROZEN (structural) — consumption is allowed

Identity & Access's **structural/architectural development is frozen**: no new capability, no redesign of `ActingIdentity`/`AuthorityGrant`/`OperationalSignature`'s own shape, no authentication-provider decision, and none of the "Open items" below may be worked without the Product Owner explicitly unfreezing them first.

**The freeze does not prohibit an approved Domain from consuming the services already built here.** Any Domain may call `authority_service.authorize()`, request/hold `AuthorityGrant`s, and record `OperationalSignature`s exactly as designed — that is this foundation's whole purpose, and withholding it from Domains that need it would defeat the point of building it centrally (Core Principle 21). Tips does this today (see above). A minimal, additive widening of an EXISTING column's own value vocabulary to support a Domain's legitimate scoping need — e.g. `AuthorityGrant.scope_type` gaining `RESTAURANT` — is Domain-driven consumption, not a structural change to this foundation, and does not itself require lifting the freeze; it still requires ordinary Product Owner approval like any schema change, exactly as `f5d11c7966be` received. What the freeze DOES block is redesigning the foundation itself (its own table shapes, its own authorization algorithm, its own assurance-level model, the authentication-provider choice) — that remains **frozen** until the Product Owner explicitly says otherwise.

---

## Open items

Recorded as open, not designed further here:

- Final choice of authentication provider (Cognito is the current preferred candidate, not a locked decision)
- Exact Cognito (or alternative) configuration, user pool design, and token scheme
- Whether/how Corporate, Brand and Operational Unit become persisted System-level entities (today only `Restaurant` and Restaurant's own narrower `OperationalArea` exist in the canonical schema — the Core Corporate/Brand/Operational Unit chain has no backing table yet)
- Domain integration sequencing beyond Tips — Tips answered "which Domain integrates first, and how" (direct `authority_service.authorize()` consumption, Restaurant-scoped grants); which Domain integrates next, and whether any of them need their own additive scope-vocabulary widening the way Tips did, remains open
- The final legal e-signature provider (explicitly out of scope for the RF-One Operational Signature itself)
- The complete commercial multi-tenant implementation model (schema-per-tenant vs. row-level isolation vs. another model)
- How intervention/delegation revocation chains and the AI-Recommendation-vs-AI-Authorized-Execution rule are actually enforced (currently recorded as data, not policy-enforced)

---

## Related documents

- [Identity Authority and Security Architecture.md](Identity%20Authority%20and%20Security%20Architecture.md) — the full technical architecture (moved here from `03 Software/`)
- `00 Core/ConceptualArchitecture/09_Identity_Authority_and_Accountability.md` — the Core conceptual definitions this area implements
- `00 Core/ArchitecturePrinciples.md` — "Shared Identity, Authority and Security Infrastructure" (Core Principle 21)
- `10 System/README.md` — the System top-level area's own purpose and boundary
- `03 Software/README.md` — where the corresponding implementation code lives
- `07 Tasks/Reports/CORE_IDENTITY_AUTHORITY_SECURITY_ARCHITECTURE_REPORT.md` — historical task report for the original architecture
