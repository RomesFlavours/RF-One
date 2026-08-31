# RF-One User Interaction Architecture

**Version:** 1.0
**Status:** Approved (initial foundation — TASK_INTERACTION_001)
**Module:** Software / Cross-cutting Runtime Architecture

---

## Purpose

This document establishes RF-One's initial architecture for how Users interact with the system — which interfaces exist, what kind of work happens on each, the initial authentication/authorization model, the role of mobile, the role of document/evidence capture, and the principle by which every future operational module must be checked against this architecture.

**This is not a graphic/UI specification.** It does not define layout, navigation design, visual design system, or any specific frontend/mobile technology — see "Out of Scope" below. It defines the *shape* of interaction, not its appearance.

**Scope: documentation only.** No software, database schema, API, authentication provider, or UI was implemented by this document.

---

## Relationship to Core, Domain, Product and Software

Per `CLAUDE.md`: **Core ≠ Domain ≠ Product ≠ Runtime.**

- **Core** (`00 Core/`) defines universal concepts (Subject, Reality, Decision, Authorization as a Decision input, and others) — it does not define concrete interfaces or a concrete authorization model.
- **Domain** (`01 Domains/`) defines business meaning — e.g. Restaurant/Purchasing's `Purchase Document`, `Purchase Line`, classification. Domains remain authoritative for business meaning; this document never redefines Domain semantics (see "Product / Domain Boundary" below).
- **Product** (`02 Products/`) will define which Domains a commercial offering combines. This document does not create or configure a Product.
- **Software** (`03 Software/`) is authoritative for actual runtime behavior. This document is placed here because it is cross-cutting runtime interaction architecture — how any future Domain/Module surfaces to a User — not a business concept and not tied to one specific runtime module (see `README.md`, "Current modules," for module-specific code).

This document is a **foundation, not an immutable constraint** — see "Module Interaction Readiness Review" below.

---

## 1. Fundamental Principle

RF-One is not designed as a single interface identical on every device. The type of interaction depends on the device and the operational context.

**Canonical initial model:**

```text
DESKTOP / LAPTOP WEB  = full Operational Workspace
MOBILE                = contextual interaction surface
```

Mobile is **not**, for now, a reduced replica of the desktop software. It is a distinct interaction surface with its own natural use cases (see Section 4).

---

## 2. Desktop-First Web Application

The first complete operational interface of RF-One will be a desktop-first Web Application.

Desktop/laptop must support complex functions, including for example:

- domain/module navigation
- operational management
- configuration
- data review
- reconciliation
- analysis
- complex workflows
- personnel management
- purchasing
- payroll
- financial/administrative workflows
- reporting
- system administration

**Not decided by this document:** sidebar vs. top navigation, dashboard structure, cards, visual design, detailed page hierarchy, or any other layout decision. These are made later, based on real modules as they mature (see Section 8, "Module Interaction Readiness Review").

---

## 3. User Identity and Authentication

RF-One must have its own User Identity.

```text
Authentication  = Who are you?
Authorization   = What are you allowed to see/do?
```

These are kept strictly distinct: Authentication establishes identity; Authorization (Section 4) determines what an authenticated identity may see and do.

The architecture must be able to support, when implemented:

- secure login
- password-based authentication initially, if appropriate
- stronger authentication mechanisms such as MFA/passkeys, added later without redesigning the model
- session security
- device/session management, where needed

**Not decided by this document:** specific provider, framework, or protocol (e.g. OAuth, SAML, a specific identity provider). Nothing is implemented here — this section only establishes that Authentication is a distinct, evolvable capability every interaction surface relies on.

---

## 4. Authorization Model

The initial authorization model is simple and understandable, conceptually similar to the Clover model already familiar from RF-One's Restaurant Domain integration.

An Administrator can determine, for each User:

- which Domains they can see;
- which Modules they can see;
- which Pages / Functions they can use;
- which Actions they can perform;
- over which organizational Scope (Section 6).

**Conceptual hierarchy:**

```text
User
→ Domain
→ Module
→ Page / Function
→ Permission
→ Scope
```

**Possible permission semantics** (illustrative, not exhaustive):

```text
VIEW
EDIT / EXECUTE
APPROVE
ADMINISTER
```

This is intentionally a small, understandable taxonomy — it is not expanded further by this document. A future module that genuinely needs a finer-grained permission is handled through the Module Interaction Readiness Review (Section 8), not by silently growing this list ad hoc.

---

## 5. Visibility Principle

**Strong principle:**

> A User sees only what the User is authorized to access.

RF-One must **not** be designed so that unauthorized Domains/Modules/Pages remain visible but disabled ("grayed out"). If a User has no authorization for something, it should normally not appear in that User's operational interface at all.

A User's RF-One experience is therefore **dynamically composed** from their authorized capabilities — the interface a User sees is a direct function of the Authorization model (Section 4), not a fixed interface with visibility toggles layered on top.

---

## 6. Authorization Scope

Authorization must also support organizational scope. Examples of scope levels may include:

- Organization / Company
- Legal Entity
- Restaurant Location
- other future operational units

**Conceptual example** (illustrative, not a commitment to any concrete User of any concrete Product):

```text
User A → Restaurant/Purchasing → VIEW + EDIT → Location: Mount Dora
User B → Restaurant/Purchasing → VIEW        → All Locations
```

**Do not hardcode Rome's Flavours-specific (or any other concrete customer's) permissions into this general architecture.** Scope is a dimension of the model, not a fixed list of concrete locations or organizations.

---

## 7. Mobile Role

Mobile is currently **not** considered the primary environment for operating the complete RF-One system. Complex desktop workflows are not, by default, reproduced on a small screen.

**Initial mobile use cases** are interaction types naturally suited to the mobile context:

- alerts
- notifications
- suggestions
- approvals
- confirmations
- quick decisions
- quick actions
- status checks
- capture of Reality / evidence / documents (Section 8)

The mobile architecture may later expand if actual module requirements justify it (see Section 8, "Module Interaction Readiness Review," and Section 9, "Bidirectional Coherence").

### 7.1 Alert vs Notification

"Alerts" and "notifications" above are not synonyms — this document establishes the general distinction; the operational meaning of any specific Alert is always defined by the owning Domain/Module (e.g. `01 Domains/Restaurant/Purchasing/EntityDefinitions.md`, "Alert," is the canonical example as of this writing).

```text
Notification  = informs the User; no response is required to close it.
Alert         = requires a traceable human response before it can close:
                responsible User/role, OPEN state, explicit acknowledgement,
                a recorded human decision when a decision is required, and
                closure only once that response is complete.
```

This document defines only the interaction shape (how an Alert is surfaced, acknowledged and acted on across desktop/mobile). It does not define what any specific Alert means, when one is raised, or what decisions it supports — that is Domain/Module business meaning (Section 16, "Product / Domain Boundary").

---

## 8. Mobile Capture

A key mobile function is acquisition of information from Reality. Examples:

- photograph a receipt
- photograph an invoice
- photograph another business document
- capture an image of equipment
- capture evidence of an operational issue
- potentially capture other media/data in the future

**Conceptual flow:**

```text
Mobile camera
→ capture receipt image
→ preserve original evidence
→ route to appropriate RF-One module
→ extraction / interpretation
→ Domain workflow
```

**For Purchasing** (illustrative — Purchasing is one consumer among others, see Section 9):

```text
Photo / document
→ Purchasing acquisition
→ Purchase Document
→ Purchase Lines
→ normal Purchasing workflow (see 01 Domains/Restaurant/Purchasing/DataAcquisition.md)
```

A closely related illustrative case is mobile Receiving — capturing what physically arrived from a Supplier, as distinct from capturing the Invoice itself (`01 Domains/Restaurant/Purchasing/EntityDefinitions.md`, "Receiving Record," "Receiving Line"). Receiving capture may scan package/case labels or confirm quantities against an Order, always with the option to fall back to simple manual entry, and it can complete even while a discrepancy it revealed remains an open Alert for a desktop User to resolve (`01 Domains/Restaurant/Purchasing/BusinessRules.md`, "Receiving Is Mobile-First and Fallback-Capable," "Receiving Completion Is Independent of Alert Resolution"). This document does not define the capture screens themselves — only that Receiving is a further concrete example of the general Capture → Evidence → Routing → Domain flow above.

---

## 9. Capture Is Transversal

Mobile photo/document capture is **not** conceptually owned by Purchasing, or by any other single Domain/Module. The acquisition mechanism is a **transversal interaction capability**.

**Conceptually:**

```text
Capture
→ Evidence / Source
→ Routing
→ Relevant Domain / Module
```

Purchasing is simply one consumer of Capture. Other future modules (e.g. a future Personnel, Maintenance, or Operations capability) may consume captured evidence differently — these are cited here only as illustrative examples of *why* Capture must remain transversal; **this document does not create any of these Domains/Modules.**

Distinguish clearly:

```text
Interaction capability:  Document / Evidence Capture   (this document, transversal)
Domain processing:       Restaurant / Purchasing, Personnel, Maintenance, Operations, etc.
                          (owned by 01 Domains/, each on its own terms)
```

---

## 10. Source Preservation

Captured material from mobile must respect RF-One's Reality/Evidence principles (`00 Core/ConceptualArchitecture/01_Subject_and_Reality.md`). The original captured source must be preservable as evidence/provenance. Derived interpretation must remain distinguishable from the source — the same "persist facts, derive/interpret separately" discipline already canonical in `01 Domains/Restaurant/Purchasing/DataDictionary.md`.

**Conceptually:**

```text
Original Image / Document
→ Source Evidence

Extraction / Recognition
→ Interpretation / structured facts

Domain
→ consumes structured facts and evidence
```

**Not decided by this document:** storage implementation (where evidence is stored, retention, file format, cloud provider).

---

## 11. Routing

Captured input should eventually be routable to the appropriate module. Routing may be based on:

- explicit User choice;
- context;
- document recognition;
- system inference;
- configured workflow.

**Not decided by this document:** the routing algorithm itself. The architectural requirement is only that Capture and Domain Processing remain separable — a Domain must be able to consume routed evidence without owning the capture mechanism (Section 9).

---

## 12. Mobile Security

Mobile interaction remains tied to the same User Identity and Authorization described in Sections 3–6. A mobile User must only be able to:

- capture for authorized scopes;
- see authorized alerts;
- perform authorized approvals/actions;
- access data allowed by the same authorization model used by the Web application.

**Do not create a separate mobile permission model.** One identity/authorization architecture governs every interaction surface — desktop, mobile, and any future surface.

---

## 13. Hardware / Software Interaction Principle

RF-One's software architecture must not assume that every function belongs on every hardware/interface surface. Interaction capabilities are mapped to the hardware/context that best supports them.

**Initial model:**

```text
Desktop/Laptop  → complex cognition and operational control
Mobile          → context, capture, alert, approval, quick interaction
```

Future hardware/interface surfaces (e.g. kitchen display, kiosk, voice) may be added only when a real module/use case requires them. This document does not speculate extensively about future devices beyond noting that the model is open to them.

---

## 14. Module Interaction Readiness Review

**Strong development principle:** whenever a Domain/Module becomes mature enough to move toward operational implementation, RF-One must perform an Interaction Architecture Review for that module.

For that module, ask:

1. What does the User actually need to do?
2. Which actions require desktop Operational Workspace?
3. Which actions naturally belong on mobile?
4. Does the module require Capture?
5. Does it require alerts/notifications?
6. Does it require approval/confirmation actions?
7. What authorization granularity is required?
8. What organizational scope is required?
9. Does the existing interaction architecture support these functions?
10. If not, should the module adapt to the architecture, or should the interaction architecture itself evolve?

**Important:** the current interaction architecture is a **foundation, not an immutable constraint**. The reality of operational modules may require the architecture to evolve — see Section 15.

A reusable checklist for this review is provided at the end of this document ("Module Interaction Readiness Checklist").

---

## 15. Bidirectional Coherence

```text
Module requirements  ↔  Interaction Architecture
```

Do **not** force a valid operational requirement into an unsuitable interface architecture merely because the architecture was documented first. Likewise, do **not** allow each module to invent its own unrelated interaction/security model.

Therefore:

- modules must be checked for coherence with the shared interaction architecture (Section 14);
- the shared architecture must be revised when legitimate module requirements expose a missing capability.

This mirrors, at the interaction layer, the same "approved architecture is implemented faithfully, but genuine contradictions are surfaced rather than silently forced" discipline `CLAUDE.md` already establishes for Core/Domain work.

---

## 16. Product / Domain Boundary

This document does not move Domain semantics into the UI architecture.

**Example:**

```text
Purchasing (Domain, 01 Domains/Restaurant/Purchasing/) defines:
  Purchase Document, Purchase Line, Supplier Product, classification, etc.

Interaction Architecture (this document) defines only HOW a User interacts
with those capabilities:
  desktop review, mobile capture, approval, notification, permissions.
```

The Domain remains authoritative for business meaning. The interaction layer remains authoritative for human-system interaction. Neither redefines the other.

---

## 17. Out of Scope

This document does **not** define:

- exact UI layout
- navigation design
- visual design system
- CSS/frontend framework
- React/Vue/Angular (or other framework) choice
- native mobile app vs. PWA
- authentication provider
- OAuth implementation
- database schema
- API endpoints
- notification provider
- camera implementation
- OCR implementation
- cloud storage
- deployment infrastructure

These are later implementation decisions, made when a concrete module or Product requires them — informed by, but not decided within, this architecture.

---

## Module Interaction Readiness Checklist

Reusable whenever a Domain/Module approaches operational implementation (Section 14):

```text
MODULE INTERACTION READINESS

- Desktop functions identified
- Mobile functions identified
- Capture requirements identified
- Alert requirements identified
- Approval requirements identified
- Authorization requirements identified
- Scope requirements identified
- Evidence/provenance requirements identified
- Existing architecture sufficient? YES/NO
- Architecture change required? YES/NO
```

---

## Related documents

- `CLAUDE.md` — Core ≠ Domain ≠ Product ≠ Runtime; the layer boundaries this document respects.
- `00 Core/ConceptualArchitecture/01_Subject_and_Reality.md` — the Reality/Evidence principle Source Preservation (Section 10) builds on.
- `01 Domains/Restaurant/Purchasing/DataAcquisition.md`, `EntityDefinitions.md`, `DataDictionary.md` — the concrete Domain example used illustratively in Sections 8–9 for Capture routing and the persist-facts/derive-interpretation discipline; Purchasing remains one consumer of Capture, not its owner.
- `01 Domains/Restaurant/Purchasing/EntityDefinitions.md`, "Alert"; `BusinessRules.md`, Rules 20–24 — the concrete Domain example used illustratively in Section 7.1 for the Alert vs Notification distinction; the Domain remains authoritative for what a specific Alert means.
- `01 Domains/Restaurant/Purchasing/EntityDefinitions.md`, "Receiving Record," "Receiving Line"; `BusinessRules.md`, Rules 25–42 — the concrete Domain example used illustratively in Section 8 for mobile Receiving capture; the Domain remains authoritative for Receiving semantics.
- `03 Software/README.md` — Software layer authority and current runtime modules.
- `07 Tasks/TASK_INTERACTION_001_Define_User_Interaction_Architecture.md` — task that created this document.
- `07 Tasks/Reports/TASK_INTERACTION_001_REPORT.md` — task report.
