# CORE_IDENTITY_AUTHORITY_SECURITY_ARCHITECTURE — Report

**Date:** 2026-09-05
**Type:** Documentation-only architecture task
**Status:** Complete

---

## 0. Scope confirmation

Per the task instructions, this was documentation only. No software was implemented, no database was touched, no AWS/Cognito resource was created, no authentication/authorization/audit/signature code was written, and no Domain runtime was altered. No broad repository integrity review was performed — only the files below were inspected and/or edited.

---

## 1. Files created

- `00 Core/ConceptualArchitecture/09_Identity_Authority_and_Accountability.md` — new canonical Core conceptual document.
- `03 Software/Identity Authority and Security Architecture.md` — new canonical Software/Runtime technical architecture document.
- `07 Tasks/Reports/CORE_IDENTITY_AUTHORITY_SECURITY_ARCHITECTURE_REPORT.md` — this report.

## 2. Files updated

- `00 Core/ConceptualArchitecture/00_RF-One_Core_Vision.md` — added document 09 to "Related documents" and the "How to read this architecture" table.
- `00 Core/ConceptualArchitecture/07_Core_Glossary.md` — added terms: Acting Identity, Authority, Delegation, Accountability, Auditability.
- `00 Core/README.md` — extended the ConceptualArchitecture row description.
- `00 Core/ArchitecturePrinciples.md` — added a new section "Shared Identity, Authority and Security Infrastructure" (the mandatory no-independent-auth-per-Domain rule) and a Design Principles bullet.
- `00 Core/RF-ONE Core Principles.md` — added Principle 21; bumped document version 6.1 → 6.2; updated the header changelog sentence.
- `00 Core/Core Evolution.md` — added a full Evolution Log entry documenting this change, following the established template.
- `03 Software/README.md` — added a row for the new technical architecture document to the "Cross-cutting runtime architecture" table.
- `03 Software/User Interaction Architecture.md` — bumped to v1.1; added Section 18 (Web Application Architecture Decision — Responsive, Not Native) and Section 19 (Attention-Driven Operational Home); amended the Section 17 Out-of-Scope bullet on native-app-vs-PWA to point at the new Section 18 decision; extended "Related documents."
- `PROJECT_STATE.md` — added one "Current state" bullet summarizing this task, consistent with the existing entry style.

No Domain file (`01 Domains/`), Product file (`02 Products/`), or existing runtime code was modified.

---

## 3. Canonical conceptual definitions added (Core layer)

`00 Core/ConceptualArchitecture/09_Identity_Authority_and_Accountability.md` makes explicit, as transversal Core concepts:

- **Identity** — an *Acting Identity* is an Entity assuming the existing Actor role (`Entity.md` §6), with a permanent identifier independent of visible role/title labels (`Entity.md` §4). Kinds: Human User, System/RF-One, AI Agent, External Service/Connector.
- **Authority** — the bounded, contextual scope of Decisions/Actions an Acting Identity may perform, evaluated against the *existing* Corporate → Brand → Operational Unit → Operational Area hierarchy plus Domain/Module — not a new parallel "Company/Branch" concept.
- **Delegation** — the general Core relationship generalizing the *already-approved* Delegated Authority (Pilot → RF-One, `06_Business_Autopilot_and_Intelligence_Engine.md`), which is preserved unchanged and identified as Delegation's specific, most important instance.
- **Accountability** — attributing a Decision/Action to its Acting Identity and Authority; includes the AI Recommendation vs. AI-Authorized Execution distinction (an AI Agent never acquires Authority merely by being capable of acting).
- **Auditability** — the capability to reconstruct who/what/when/context/authority/before/after, tied explicitly to the *existing* Historical Integrity and Temporal Coherence principles rather than inventing new ones.

Core Principle 21 (`RF-ONE Core Principles.md`) states the resulting mandatory rule at the principle level. `00 Core/ArchitecturePrinciples.md` states it at the architecture-rule level ("Shared Identity, Authority and Security Infrastructure").

---

## 4. Authentication / Authorization architecture documented (Software layer)

`03 Software/Identity Authority and Security Architecture.md`:

- **Authentication** (§7): managed Identity/Authentication service rather than homegrown passwords; **AWS as primary cloud**, **Amazon Cognito as current preferred candidate**, subject to final validation; supports email/password, MFA, recovery, session management, revocation, future passkeys/SSO — not all mandatory for v1.0.
- **Authorization** (§8): backend/service-enforced; UI hiding is explicitly not security; every API call independently re-checks Authority regardless of client state.
- Context Scope (§4) and Authority Model (§5) reuse the existing `Corporate.md` / `Operational Unit.md` hierarchy rather than inventing a new one, and extend (not replace) the smaller Authority taxonomy already in `User Interaction Architecture.md` §4.

This extends, and explicitly does not duplicate, the Authentication/Authorization material already approved in `User Interaction Architecture.md` §3–§6 and §12.

---

## 5. RF-One Operational Signature

Defined in `Identity Authority and Security Architecture.md` §9: for ordinary operational Decisions, the authenticated + authorized action itself is the signature, provided sufficient audit evidence is preserved (actor, action, timestamp, context, object, before/after state, applicable rule/data version, authority used, reason, authentication assurance level). Section 10 documents the three-level confirmation model (Normal Authenticated Action / Explicit Confirmation / risk-based Step-Up Authentication).

---

## 6. Legal e-signature boundary

§11 explicitly distinguishes RF-One Operational Signature from **Legal Electronic Signature**: RF-One does not build a legal e-signature platform; legally signed documents route through an external specialized provider (illustratively DocuSign or Adobe Acrobat Sign) via a Connector, with RF-One preserving provider evidence (document/version, signatory, status, timestamp, provider transaction ID, certificate reference). Provider choice is explicitly left open.

---

## 7. Audit architecture

§12 documents the Audit Trail as shared infrastructure (who/what/when/context/authority/object/before/after/reason/rule-version/actor-kind), append-oriented and immutable in principle, with corrections creating new records rather than overwriting history — the same Historical Integrity discipline already canonical for business history generally.

---

## 8. Interface principles

`User Interaction Architecture.md` §18 records the decision that RF-One 1.0 is **one responsive Web Application** (desktop/tablet/smartphone), with no separate native app required for 1.0 and optional PWA/installable behavior — resolving part of what was previously an open item in that document's Out-of-Scope list, while leaving the concrete PWA implementation undecided. §19 records the **Attention-Driven Operational Home** principle (queues/alerts/approvals/AI recommendations as the Home surface, rather than forcing Company/Branch/Domain/Module tree navigation as the mandatory entry point), governed by the same Authorization/Visibility model already established in §4–§6.

---

## 9. AWS / cloud decision

Recorded as an explicit architectural decision (§18 of the Software document): AWS is RF-One's primary cloud for production infrastructure. This does not preclude specialist non-AWS external services (AI providers, SMS/email, payment/banking, POS, payroll, e-signature, reservation systems) — those are isolated through provider adapters (§19).

---

## 10. Provider-abstraction principle

§19 restates and extends the already-approved `CLAUDE.md` ("External Technology") and `ArchitecturePrinciples.md` ("Loose Coupling") principles specifically for Messaging/Storage/AI/Payment provider boundaries, without introducing a new architectural principle that contradicts either.

---

## 11. Security principles documented

Data Security (§15): encryption in transit/at rest, no plaintext passwords, no committed credentials, secrets management, least privilege, DB not directly client-reachable, controlled upload, backup/recovery, logging/monitoring, security-event traceability.
Multi-Tenant/Company Isolation (§16): mandatory server-side tenant/context validation; invariant only, not a full implementation design.
Environments (§17): DEV/TEST-STAGING/PROD separation, independent config/secrets, no casual prod-data/credential reuse in lower environments.
Security Layers (§14): Internet/Client → TLS → Edge → RF-One Web/API → Authentication → Authorization → Domain Services → Data layer, with an illustrative (non-final) AWS component list.

---

## 12. Contradictions found and corrected

None found that required correction. One point of potential ambiguity was proactively reconciled rather than left implicit:

- `User Interaction Architecture.md` §2 ("Desktop-First Web Application") and §17 (previously left "native mobile app vs. PWA" fully undecided) could have been read as in tension with the new requirement that RF-One 1.0 be "ONE responsive web application." Resolution: §18 clarifies these are compatible — desktop-first describes where complex workflows are *designed for first*, not a separate delivery vehicle from mobile; both are one responsive codebase. The Out-of-Scope bullet in §17 was updated to point at this resolution rather than left as an unresolved open item.
- Delegated Authority (`06_Business_Autopilot_and_Intelligence_Engine.md`) was deliberately **not** redefined. The new Delegation concept in `09_Identity_Authority_and_Accountability.md` §4 is explicit that Delegated Authority is Delegation's specific, most important instance — an additive generalization, not a competing definition.

---

## 13. Unresolved architectural questions for the Product Owner

1. **Authentication provider validation.** Amazon Cognito is recorded as the *current preferred candidate* per your instructions, not a final commitment. A concrete evaluation (cost, MFA/passkey support, SSO roadmap, multi-tenant user-pool strategy) is still needed before implementation.
2. **Legal e-signature provider.** DocuSign vs. Adobe Acrobat Sign vs. another provider is explicitly left open (§11); no evaluation was in scope here.
3. **Multi-tenant implementation strategy.** Schema-per-tenant vs. row-level isolation vs. another model is explicitly out of scope for this document (§24) and will need its own decision when Product-level multi-tenant work begins.
4. **Authority-class taxonomy finality.** §5 offers an illustrative, extended set of Authority verbs (VIEW/CREATE/EDIT/APPROVE/DECIDE/OVERRIDE/CERTIFY/REASSIGN/EXECUTE/DELEGATE) beyond the smaller set already in `User Interaction Architecture.md` §4. Whether Products actually need this larger set, or should stay with the smaller one until a concrete module proves otherwise, is a judgment call left for the Module Interaction Readiness Review process already established in that document.

None of these block the documentation recorded in this task; they are implementation-stage decisions the architecture is deliberately built to accommodate without redesign.
