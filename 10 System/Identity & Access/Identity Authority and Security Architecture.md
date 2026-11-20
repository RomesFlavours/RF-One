# RF-One Identity, Authority and Security Architecture

**Version:** 1.0
**Status:** Approved (initial foundation — CORE_IDENTITY_AUTHORITY_SECURITY_ARCHITECTURE). Moved from `03 Software/` to `10 System/Identity & Access/` when the System top-level area was introduced (this is the same document, unchanged in substance by the move). **Current development status: FROZEN** — see [README.md](README.md).
**Module:** System / Identity & Access — Cross-cutting Architecture

> **Naming note (external-review clarification, added post-baseline — does not modify this document's approved substance):** every "Cognito" in this document refers to **Amazon Cognito**, the AWS authentication/identity service (currently the preferred, not-yet-locked authentication-provider candidate — see §27 below). It is an unrelated concept to **"RF-One Cognito"**, RF-One's own internal name for its Cognitive Intelligence Core concept (`00 Core/ConceptualArchitecture/14_Cognito_RF-One_Cognitive_Intelligence.md`). The two share a name only by coincidence. The Product Owner has already identified this naming collision and a request is in progress to identify a replacement name for RF-One's Cognitive Intelligence concept; this document's own "Cognito" (Amazon's service) is not affected by that renaming.

---

## Purpose

This document establishes RF-One's technical architecture for Identity, Authority, Authentication, Authorization, the RF-One Operational Signature, Legal Electronic Signature, Audit Trail, and the surrounding Security architecture (layers, data security, multi-tenant isolation, environments, cloud decision, provider abstraction).

**Scope: documentation only.** No software, database schema, API, authentication provider, cloud resource, or UI was implemented by this document. No AWS account, Cognito resource, database, or login/permission/audit code was created.

---

## Relationship to Core, Domain, Product, System and Software

Per `CLAUDE.md`: **Core ≠ Domain ≠ Product ≠ Runtime**, with `10 System/` now holding system-level cross-cutting capabilities (like this one) that are neither a Domain nor a Product.

- **Core** (`00 Core/ConceptualArchitecture/09_Identity_Authority_and_Accountability.md`) defines what Identity, Authority, Delegation, Accountability and Auditability *mean* — domain-independent, technology-independent. This document does not redefine those meanings; it defines how they are *implemented*.
- **Domain** (`01 Domains/`) defines what Authority a specific class of business Decision requires (e.g. who may approve a Purchase Order) — Domains remain authoritative for that business meaning. This document never redefines Domain semantics.
- **Product** (`02 Products/`) will define concrete Company/Branch configuration and which Users hold which Authority for a given commercial deployment. This document does not configure any Product.
- **System** (`10 System/Identity & Access/`, this document's current location) is the architectural home for this cross-cutting capability itself — how *any* future Domain/Module/Product authenticates its Users, enforces Authority, and proves what happened — not a business concept, not tied to one Product, and not implementation code.
- **Software** (`03 Software/`) remains authoritative for actual runtime behavior. The existing software foundation implementing part of this architecture (Acting Identity, Authority, Operational Signature persistence and services) lives in `03 Software/RF-One Data Store/` and is not moved by the relocation of this document — see [README.md](README.md), "Current implementation references."

This document is a **foundation, not an immutable constraint** — technical choices recorded here (e.g. Cognito as the current preferred candidate) are subject to final implementation validation and may be revisited through the same architecture-review discipline `User Interaction Architecture.md` §14–15 already establishes for interaction architecture.

---

## 1. Mandatory Architectural Rule

Per `00 Core/ArchitecturePrinciples.md`, "Shared Identity, Authority and Security Infrastructure":

> No Domain or Module implements its own independent Authentication, Authorization, Identity management, Authority mechanism, Operational Signature mechanism, or Audit mechanism. All Domains consume shared RF-One Identity/Authority/Security infrastructure.

A Domain determines **what** Authority a Decision or Action requires. This shared infrastructure determines **who** the Acting Identity is, **what** it is authorized to do, **in what context**, **whether stronger authentication is required**, and **how** the action is recorded and proven historically. Section 24 below restates this as a concrete Domain-facing rule.

---

## 2. Conceptual Foundation (recap, not redefinition)

This document builds directly on two existing approved documents and does not restate their content beyond this pointer:

- `00 Core/ConceptualArchitecture/09_Identity_Authority_and_Accountability.md` — Acting Identity, Authority, Delegation, Accountability, Auditability as Core concepts.
- `User Interaction Architecture.md` §3–§6, §12 — the initial User Identity/Authentication distinction, the Authorization model (`User → Domain → Module → Page/Function → Permission → Scope`), the Visibility Principle, Authorization Scope, and Mobile Security (one identity/authorization model governs every interaction surface).

Everything below extends those with the deeper technical/security layer: mechanism choice, RF-One Operational Signature, Audit Trail, and infrastructure.

---

## 3. Identity Model (technical)

RF-One must support, as distinct kinds of Acting Identity (Core term — see §2 above):

- **Human User** — a person with an RF-One account.
- **System / RF-One** — RF-One acting as itself, within Delegated Authority.
- **AI Agent** — an Intelligence Engine-backed component acting within explicit Delegated Authority (see §8).
- **External Service / Connector** — a third-party system or provider acting on RF-One's or a Subject's behalf (e.g. a POS, payroll provider, or e-signature provider callback).

Every meaningful action must identify the Acting Identity responsible for it (Core Principle 21).

A Human User's identity must remain stable even when their visible job title, Operational Unit ("Branch"), permissions, or an organization's own terminology changes. Visible role labels are configurable Attributes; the internal identifier and its accumulated history are not (see `00 Core/Entity.md` §4–§5 and the new Core document §2.1).

---

## 4. Context Scope

Authorization is contextual, never a flat global permission. The context chain reuses Core concepts that already exist — this document does not introduce a parallel organizational model:

```text
Acting Identity
→ Corporate / Brand            (00 Core/Corporate.md, Brand.md — "Company")
→ Operational Unit             (00 Core/Operational Unit.md — "Branch"/Location)
→ Domain / Module
→ Page / Function / Resource
→ Action
→ Authority
```

Example: a User may be authorized to EDIT inside Restaurant/Purchasing only for one Operational Unit, and only VIEW for others, while having no Authority at all in Payroll.

**The important question is always:** "Is this Acting Identity authorized to perform this specific Action on this specific resource in this specific context?" — never a coarser question like page visibility alone.

---

## 5. Authority Model (technical)

Authority is action-oriented. Illustrative, non-mandatory examples of Authority classes, extending the smaller initial taxonomy already in `User Interaction Architecture.md` §4 (`VIEW / EDIT-EXECUTE / APPROVE / ADMINISTER`) for cases that need finer granularity:

```text
VIEW        CREATE       EDIT         APPROVE
DECIDE      OVERRIDE     CERTIFY      REASSIGN
EXECUTE     DELEGATE
```

Domains may define additional Authority classes they genuinely need; this is not a closed enumeration.

Authority may be direct, role-derived, delegated, conditional, temporary, or scoped to part of the context chain (§4). Whenever Authority is Delegated (Core term, §2 above), the architecture must preserve **who granted it, when, under what Authority, and who revoked it** — a Delegation record is itself subject to Auditability (§14), not an exception to it.

---

## 6. Human Authority / AI Authority (technical corollary)

Per `00 Core/ConceptualArchitecture/06_Business_Autopilot_and_Intelligence_Engine.md` and `09_Identity_Authority_and_Accountability.md` §5.1: an AI Agent does not acquire Authority merely because it is technically capable of executing an action.

The system must record, for every AI-touched Action, which of the two occurred:

```text
AI RECOMMENDATION        — no Action is attributed to the AI Agent; a human
                            or other authorized Acting Identity decides.
AI-AUTHORIZED EXECUTION  — RF-One is the Acting Identity, strictly within
                            an explicit, in-force Delegation record.
```

Absent an explicit Delegation record covering the specific Authority class and context, the system must not allow an AI Agent's output to be persisted or presented as an executed Action.

---

## 7. Authentication

**Authentication answers: "Who are you?"** It is architecturally distinct from Authorization (§8).

RF-One should use a **managed Identity/Authentication service** rather than implementing password authentication from scratch.

**Current infrastructure decision:** PRIMARY CLOUD = AWS (§21). **Amazon Cognito is the current preferred candidate** for RF-One User authentication, subject to final implementation validation.

The authentication architecture should support, where appropriate and not necessarily all in version 1.0:

- email/password;
- multi-factor authentication (MFA);
- password recovery;
- secure session management;
- account disabling/revocation;
- future passkeys;
- future enterprise SSO/federation.

Not every capability above must exist in RF-One 1.0; the architecture must not require redesign to add the remainder later.

---

## 8. Authorization

**Authorization answers: "What are you allowed to do here?"**

Authorization must be enforced by backend/services, never by the UI alone. **UI hiding is not security.** A User who cannot see an action in the interface must also be unable to execute it directly through an API — every API/service call independently re-checks Authority (§4–§5) against the calling Acting Identity, regardless of what the client sent or omitted.

This is the technical enforcement of the Visibility Principle already established in `User Interaction Architecture.md` §5.

---

## 9. RF-One Operational Signature

**RF-One Operational Signature** is a first-class concept: for ordinary operational Decisions, RF-One does **not** require a handwritten graphical signature. The authenticated, authorized action itself becomes the operational signature when RF-One preserves sufficient audit evidence.

For a meaningful signed action, preserve — where relevant:

- actor identity (Acting Identity);
- action/decision performed;
- date/time (§13);
- Company/Branch/context (§4);
- resource/object acted upon;
- previous state;
- resulting state;
- applicable data/rule/Process version;
- Authority used (direct or Delegated, §5);
- mandatory reason, where applicable;
- authentication assurance level, where relevant (§10).

**Illustrative example only** (not a definition of any specific Domain's semantics):

```text
Actor:      Pino Rossi
Action:     Candidate Outcome changed
Before:     STOP
After:      HIRABLE
Time:       2026-09-05T14:32:10Z
Rule Set:   v4
Reason:     Additional reference check completed
```

This history must not be silently overwritten — consistent with Historical Integrity (`00 Core/ArchitecturePrinciples.md`): corrections generate new records.

---

## 10. Signature / Confirmation Levels

A layered model, risk-based rather than uniform:

**Level 1 — Normal Authenticated Action.** An authenticated and authorized User performs a routine action. The Audit record (§14) is sufficient; no extra confirmation is required.

**Level 2 — Explicit Confirmation.** For more consequential actions, RF-One asks the actor to explicitly confirm (e.g. "Confirm this decision.") before it is executed.

**Level 3 — Step-Up Authentication.** For high-risk actions, RF-One may require stronger or more recent authentication (e.g. MFA, passkey re-verification). Illustrative examples: sensitive financial execution, Authority modification, security configuration changes, major destructive operations, critical overrides.

Step-up must be **risk-based** — do not require MFA for every routine action.

---

## 11. Legal Electronic Signature (boundary)

**RF-One Operational Signature** (§9) is explicitly distinct from **Legal Electronic Signature**.

RF-One should **not** build its own legal e-signature platform. When a legally signed document is required, use an external specialized provider through a Connector/API (§22) — illustrative examples: DocuSign, Adobe Acrobat Sign, or another appropriate provider. **Provider choice is not yet locked.**

RF-One should preserve provider evidence such as:

- document/version identifier;
- signatory;
- signature status;
- signed timestamp;
- provider transaction/envelope identifier;
- audit/certificate reference, where available.

---

## 12. Audit Trail

Auditability (Core concept, §2) is common RF-One infrastructure, not something a Domain builds for itself. A meaningful audit record should support reconstructing:

- who (Acting Identity);
- did what;
- when (§13);
- where/context (§4);
- under what Authority (§5);
- to which object;
- before state;
- after state;
- reason, where applicable;
- relevant rule/data version;
- whether the actor was human, System, AI Agent, or External Service (§3, §6).

Audit history should be **append-oriented / immutable in principle**. Corrections create new records/history rather than silently rewriting historical truth — exactly the Historical Integrity discipline `00 Core/ArchitecturePrinciples.md` already requires for business history in general.

---

## 13. Time

Canonical system timestamps should use a consistent technical standard, preferably **UTC**. User interfaces may display timestamps in the relevant Company/Branch/User timezone. Historical audit meaning must remain unambiguous regardless of display timezone.

---

## 14. Security Layers

Conceptual layered architecture:

```text
Internet / Client
  → HTTPS/TLS
  → Edge / Web protection
  → RF-One Web/API
  → Authentication                 (§7)
  → Authorization / Authority enforcement   (§8)
  → Domain Services
  → Data layer / external connectors
```

Potential AWS components, where appropriate (not finalized — §26):

- Cognito (§7);
- WAF;
- Secrets Manager;
- managed database services;
- object storage;
- monitoring/logging.

---

## 15. Data Security

Mandatory principles:

- encryption in transit;
- encryption at rest;
- no plaintext password storage by RF-One (delegated to the managed Authentication service, §7);
- no API credentials committed in source code;
- secrets stored through an appropriate secrets-management mechanism;
- least-privilege access;
- database inaccessible directly from a normal client/browser;
- secure document/file storage;
- controlled file upload;
- backup strategy;
- recovery capability;
- logging/monitoring;
- security-event traceability.

---

## 16. Multi-Tenant / Company Isolation

RF-One is intended to support multiple companies/customers. Security architecture must ensure **strong logical isolation** between customer/company data.

A User belonging to Company A must never obtain Company B data merely through URL manipulation, API calls, guessed IDs, or a UI defect. **Tenant/context validation must occur server-side**, as part of Authorization enforcement (§8), never assumed from client-supplied context alone.

This document records the invariant; it does not design the complete commercial multi-tenant implementation.

---

## 17. Environments

Separate environments: **DEVELOPMENT**, **TEST / STAGING**, **PRODUCTION**.

Production data and credentials must not casually be reused in development/testing. Deployment architecture should support independent configuration/secrets per environment.

---

## 18. Cloud Decision

**AWS is the selected PRIMARY CLOUD for RF-One.** RF-One's production infrastructure is currently intended to be hosted primarily on AWS.

This does **not** mean every external service must be purchased from AWS. RF-One may use specialist external services whenever technically/economically preferable — illustrative examples: AI providers, SMS/email providers, payment/banking providers, POS, payroll, electronic signature (§11), reservation systems. These integrations are isolated through RF-One service/connector boundaries (§19).

---

## 19. Provider Abstraction

RF-One orchestrates external providers. Business logic must not be scattered with provider-specific implementation. Prefer conceptual boundaries such as:

```text
RF-One Messaging Service   → provider adapter
RF-One Storage Service     → provider adapter
RF-One AI Service          → provider adapter
RF-One Payment Connector   → external provider
```

This is not because RF-One expects to change AWS frequently — it maintains clean architecture and avoids unnecessary technical dependency, consistent with `CLAUDE.md` ("External Technology") and `00 Core/ArchitecturePrinciples.md` ("Loose Coupling").

---

## 20. Standard / Portable Components

Where reasonably practical, favor standard technologies/interfaces: PostgreSQL, containers, HTTP/REST APIs, standard file/object interfaces, provider adapters.

**Portability is a desirable architectural property, not a reason to avoid useful AWS managed services.** AWS is the committed primary cloud (§18); portability does not override that commitment.

---

## 21. Domain Rule

A Domain may define:

- required Authority for its Decisions and Actions;
- business Decision and workflow logic;
- domain-specific evidence and approval requirements.

A Domain must **not** independently implement:

- a login/password system;
- an identity system;
- a permission engine;
- audit infrastructure;
- legal signature infrastructure.

Those belong to this shared RF-One infrastructure (§1).

---

## 22. Terminology Stability

Use stable, generic internal terminology for Authority classes and Acting Identity kinds. Visible company-specific labels (job titles, role names, permission-set names shown in a Product's UI) may be configurable per customer. **Changing a visible label must never change the underlying technical identity or permission semantics it maps to.**

---

## 23. Related Interaction Architecture

The Web Application delivery model (one responsive application, not a separate native app) and the attention-driven operational Home principle are architecture decisions about *how Users interact* with RF-One, not about Identity/Authority/Security mechanism — they are documented in `User Interaction Architecture.md` §18–§19, extended alongside this document. This document does not duplicate them.

---

## 24. Not Decided / Out of Scope by this document

This document does **not** decide:

- the final choice of authentication provider (Cognito is the current preferred candidate, not a locked decision);
- exact Cognito (or alternative) configuration, user pool design, or token scheme;
- concrete database schema for identity, permission, or audit tables;
- concrete audit-log storage technology;
- the final legal e-signature provider;
- the complete commercial multi-tenant implementation (schema-per-tenant vs. row-level isolation vs. another model);
- concrete CI/CD or environment-provisioning pipeline design;
- exact AWS service selection beyond the illustrative list in §14.

These are later implementation decisions, made when a concrete module or Product requires them — informed by, but not decided within, this architecture.

---

## Related documents

- `CLAUDE.md` — Core ≠ Domain ≠ Product ≠ Runtime; External Technology.
- `00 Core/ConceptualArchitecture/09_Identity_Authority_and_Accountability.md` — the Core conceptual definitions this document implements.
- `00 Core/ArchitecturePrinciples.md` — "Shared Identity, Authority and Security Infrastructure," Human Authority, Traceability, Historical Integrity, Loose Coupling.
- `00 Core/Corporate.md`, `Operational Unit.md`, `OperationalArea.md` — the Company/Branch context chain reused in §4.
- `User Interaction Architecture.md` — §3–§6 (initial User Identity/Authentication/Authorization model, Visibility Principle, Authorization Scope), §12 (Mobile Security), §18–§19 (Web Application delivery model, Attention-Driven Home).
- `07 Tasks/Reports/CORE_IDENTITY_AUTHORITY_SECURITY_ARCHITECTURE_REPORT.md` — task report.
