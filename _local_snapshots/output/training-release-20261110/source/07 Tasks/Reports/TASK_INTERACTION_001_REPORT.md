# TASK_INTERACTION_001 — REPORT

**Task:** Define RF-One's initial User Interaction Architecture — which interfaces/devices RF-One needs, what kind of work happens on each, the initial authentication/authorization model, the role of mobile, the role of document/evidence capture, and the principle by which future operational modules are checked against this architecture.
**Scope:** Documentation only. No software, UI, database, authentication provider, or API was implemented.
**Date:** 2026-08-30

---

## A. Summary

Created the canonical initial User Interaction Architecture document, `03 Software/User Interaction Architecture.md`, establishing: a desktop-first Web Application as the full Operational Workspace vs. mobile as a contextual interaction surface (not a reduced desktop replica); a User Identity model separating Authentication from Authorization; a Clover-like Authorization hierarchy (User → Domain → Module → Page/Function → Permission → Scope) with a small permission taxonomy (VIEW/EDIT-EXECUTE/APPROVE/ADMINISTER); a strong Visibility Principle (unauthorized capability is absent, not disabled); organizational Scope as a first-class authorization dimension; Mobile Capture as a transversal interaction capability distinct from any Domain (Purchasing is illustrated only as one consumer); a Source Preservation principle for captured evidence; a single identity/authorization model spanning every surface (no separate mobile permission model); and a reusable Module Interaction Readiness Review with checklist for future modules. No layout, visual design, framework, provider, or implementation choice was made — see "Out of Scope" in the canonical document.

---

## B. Canonical document placement

Inspected `00 Core/README.md`, `01 Domains/README.md`, `02 Products/README.md`, and `03 Software/README.md` before choosing a location.

- `00 Core/` is authoritative for universal, domain-independent ontology (Subject, Reality, Decision, etc.) — an interaction/authorization architecture for a concrete system is not that kind of concept, and Core already explicitly excludes Restaurant/Product/Runtime-specific rules.
- `01 Domains/` holds reusable business-field knowledge; this document is explicitly *not* business meaning (Section 16 of the task/document, "Product / Domain Boundary") — it is how a User interacts with whatever a Domain defines.
- `02 Products/` currently has no canonical content (`02 Products/README.md`, "Current status") and is scoped to a specific commercial offering's Domain combination; this architecture is deliberately Product-agnostic (Section 6 explicitly forbids hardcoding one customer's permissions).
- `03 Software/` is authoritative for actual runtime behavior. Its README lists an exclusion for "conceptual/architectural documentation about business meaning" — read narrowly (consistent with the Domain-specific technical architecture documents already living here, e.g. `RF-One Data Store/DATABASE_SCHEMA.md`), this document is cross-cutting *runtime* architecture (which interfaces exist, how auth/capture work across all future modules), not business-meaning documentation, so it does not fall under that exclusion.

No existing document already covered this ground (`03 Software/InvoiceIntake/README.md` describes one prototype's own upload flow, not a cross-cutting interaction architecture). Created `03 Software/User Interaction Architecture.md` — the exact path suggested as an example in the task, confirmed as the most coherent fit after inspection. Updated `03 Software/README.md`'s "What belongs here"/"What does not belong here" bullets to make this narrower reading explicit, and added a "Cross-cutting runtime architecture" table entry pointing to the new document.

---

## C. Desktop Web role

Desktop/laptop Web is documented as the full Operational Workspace: domain/module navigation, operational management, configuration, data review, reconciliation, analysis, complex workflows, personnel management, purchasing, payroll, financial/administrative workflows, reporting, system administration. No layout, navigation pattern, dashboard structure, or visual design was decided — explicitly deferred to when real modules mature (Section 2 of the canonical document).

---

## D. Mobile role

Mobile is documented as a contextual interaction surface, not a reduced desktop replica, and not currently the primary environment for operating the full system. Initial use cases: alerts, notifications, suggestions, approvals, confirmations, quick decisions, quick actions, status checks, and Capture (Section 7). The mobile architecture may expand later if real module requirements justify it (linked to Sections 14–15, Module Readiness Review and Bidirectional Coherence).

---

## E. Authentication

Documented as a distinct capability from Authorization ("Who are you?" vs. "What are you allowed to see/do?"). The architecture must be able to support secure login, initial password-based authentication, stronger mechanisms (MFA/passkeys) added later, session security, and device/session management — without committing to a provider, framework, or protocol. Nothing was implemented.

---

## F. Authorization

Documented as a Clover-like hierarchy: User → Domain → Module → Page/Function → Permission → Scope, with an initial small permission taxonomy (VIEW, EDIT/EXECUTE, APPROVE, ADMINISTER) that is deliberately not expanded further by this document — a future module needing a finer-grained permission goes through the Module Interaction Readiness Review (Section 14) rather than growing this taxonomy ad hoc.

---

## G. Visibility rule

Formalized as a strong principle: a User sees only what they are authorized to access; unauthorized Domains/Modules/Pages are absent, not visible-but-disabled. The User's interface is dynamically composed from authorized capability, not a fixed interface with visibility toggles.

---

## H. Organizational scope

Documented as a first-class dimension of Authorization (Organization/Company, Legal Entity, Restaurant Location, other future operational units), illustrated with a conceptual (non-binding) example — User A: Restaurant/Purchasing, VIEW+EDIT, Location Mount Dora; User B: Restaurant/Purchasing, VIEW, All Locations. Explicitly, no Rome's Flavours-specific permission was hardcoded into the general architecture.

---

## I. Mobile Capture

Documented as a key mobile function: photographing a receipt, invoice, other business document, equipment, or operational-issue evidence, with the conceptual flow `Mobile camera → capture → preserve original evidence → route to appropriate module → extraction/interpretation → Domain workflow`. Illustrated concretely for Purchasing (`Photo/document → Purchasing acquisition → Purchase Document → Purchase Lines → normal Purchasing workflow`), consistent with the already-canonical `01 Domains/Restaurant/Purchasing/DataAcquisition.md`.

---

## J. Transversal Capture capability

Formalized that Capture is not conceptually owned by Purchasing or any single Domain: `Capture → Evidence/Source → Routing → Relevant Domain/Module`, with Purchasing as one illustrative consumer among possible future others (Personnel, Maintenance, Operations — cited only as examples of why Capture must stay transversal; **none of these Domains/Modules was created by this task**). The document explicitly distinguishes the Interaction capability (Document/Evidence Capture) from Domain processing.

---

## K. Evidence/provenance

Documented the Source Preservation principle: the original captured source is preservable as evidence, and derived interpretation stays distinguishable from it (`Original Image/Document → Source Evidence`; `Extraction/Recognition → Interpretation/structured facts`; `Domain → consumes structured facts and evidence`), explicitly cross-referenced to the Core Reality/Evidence principle and to the same "persist facts, derive/interpret separately" discipline already canonical in Restaurant/Purchasing's `DataDictionary.md`. Storage implementation was explicitly left undecided.

---

## L. Hardware/software interaction principle

Documented that RF-One's software architecture must not assume every function belongs on every surface; capabilities are mapped to the hardware/context that best supports them (Desktop/Laptop → complex cognition and operational control; Mobile → context, capture, alert, approval, quick interaction). Future surfaces (e.g. kitchen display, kiosk, voice) may be added only when a real module/use case requires them — not speculated on further here.

---

## M. Module Interaction Readiness Review

Documented as a strong development principle: whenever a Domain/Module matures toward operational implementation, an Interaction Architecture Review must be performed, asking the ten questions specified in the task (what the User needs to do; which actions are desktop vs. mobile; Capture/alert/approval needs; authorization granularity; organizational scope; whether the existing architecture already supports these; and, if not, whether the module should adapt or the architecture should evolve). A reusable "Module Interaction Readiness Checklist" (ten YES/NO-style items) is included at the end of the canonical document for reuse on every future module.

---

## N. Bidirectional architecture evolution

Formalized `Module requirements ↔ Interaction Architecture`: a valid operational requirement must not be forced into an unsuitable interface architecture merely because the architecture was documented first, and no module may invent its own unrelated interaction/security model. Modules are checked for coherence with the shared architecture; the shared architecture is revised when legitimate module requirements expose a missing capability. The canonical document states explicitly that it is a foundation, not an immutable constraint.

---

## O. Files created/modified

**Created:**

- `07 Tasks/TASK_INTERACTION_001_Define_User_Interaction_Architecture.md`
- `03 Software/User Interaction Architecture.md` (canonical architecture document)
- `07 Tasks/Reports/TASK_INTERACTION_001_REPORT.md` (this file)

**Modified:**

- `03 Software/README.md` — narrowed the "conceptual/architectural documentation" exclusion to business-meaning documentation specifically, added a note that cross-cutting runtime architecture documents belong here, and added a "Cross-cutting runtime architecture" table entry pointing to the new document.
- `PROJECT_STATE.md` — added one bullet recording that this architecture now exists, alongside the existing bullet style used for other completed tasks.

**Not touched:** `00 Core/`, `01 Domains/` (including Restaurant/Purchasing — referenced illustratively but not modified), `02 Products/`, `09 Strategy/`, top-level `README.md` (generic and directory-level; did not need a new entry), any file under `03 Software/InvoiceIntake/` or any other runtime code.

---

## P. Remaining unresolved implementation choices

These are explicitly out of scope for this task and were not decided, per the task's "Out of Scope" section: exact UI layout; navigation design; visual design system; CSS/frontend framework; React/Vue/Angular (or other) choice; native mobile app vs. PWA; authentication provider; OAuth implementation; database schema; API endpoints; notification provider; camera implementation; OCR implementation; cloud storage; deployment infrastructure. None of these is a contradiction requiring a Product Owner decision now — they are simply deferred to later implementation work, informed by this architecture.

No genuine architectural contradiction was found that would require a Product Owner decision at this stage.

---

## Q. Git scope confirmation

No `git add`, `git commit`, or `git push` was run. The working tree contains only the file creations/modifications listed in Section O; nothing has been staged or committed.
