# Core Evolution

## Purpose

The Core Domain of RF-One is not designed once and considered complete.

It evolves continuously as new Application Domains are analyzed.

Its purpose is to capture the concepts that prove to be universal across domains.

The Core Domain is therefore an evolving model driven by real-world experience rather than theoretical assumptions.

---

# Evolution Principle

Every new Domain is expected to challenge the Core Domain.

When a limitation, ambiguity or unnecessary abstraction is discovered, the Core must evolve.

Application Domains are never forced to fit an inadequate Core.

Instead, the Core is refined until it naturally supports all Domains.

---

# Evolution Workflow

1. Design or analyze an Application Domain.
2. Identify concepts that do not fit the current Core.
3. Decide whether the issue is domain-specific or universal.
4. If universal, update the Core Domain.
5. Document the reason for the change.
6. Verify that existing Domains remain coherent.

---

# Evolution Log

Each Core modification should be recorded.

For every revision document:

- Version
- Date
- Modified Entity
- Reason for Change
- Impacted Domains
- Compatibility Notes

Example:

Version: 2.0

Modified Entity:
Process

Reason:
Restaurant Domain demonstrated that a Process is not simply a sequence of activities but executable knowledge that also supports training, verification and continuous improvement.

Impacted Domains:

- Restaurant

Future Expected Impact:

- Retail
- Hotel
- Manufacturing
- Healthcare

---

Version: Core 2.0

Date: 2026-08-23

Modified Entity:
RF-ONE Core Principles, Goal, ArchitecturePrinciples (Human Authority), Glossary (Artificial Intelligence), Entity (Section 11), Relationship (Section 14) — plus a new canonical document set, `Core/ConceptualArchitecture/`.

Reason:
Approved product-direction review (TASK_CORE_001) established that RF-One models a Subject in relation to Reality, that a Subject is not assumed rational, that Desire is sovereign and distinct from Goal, that Reality Check/Clarification is continuous rather than a single stage, that Decision must be a first-class Core concept (without being automatically an Entity or automatically persisted), that RF-One reasons across time via Temporal Coherence, that RF-One must maintain an explicit Epistemic Boundary between knowledge states, that Subject Sovereignty coexists with operational autonomy, and that RF-One's commercial operating model is a Business Autopilot under human command acting within explicitly Delegated Authority via interchangeable Intelligence Engines. This superseded the prior absolute rule "AI never owns business decisions" and the prior rule that a Goal exists only once a Process has been defined.

Concepts introduced:

- Subject ↔ Reality
- Desire sovereignty
- continuous Reality Check
- revised Desire → Goal semantics
- Decision as first-class Core concept (Decision Record, Decision Memory)
- Epistemic Boundary
- Subject Sovereignty
- Temporal Coherence
- Business Autopilot
- Delegated Authority
- Intelligence Engine abstraction

Impacted Domains:

- Restaurant (Purchasing AI authority language reviewed; no contradiction requiring change was found — human-approval requirements there stand as legitimate Domain-level Delegated Authority = none configuration)

Future Expected Impact:

- Every future Domain that models Decisions, Desire/Goal formation, or AI/human authority boundaries.

Compatibility Notes:

- Core 1.0 documents (Entity, Process, Relationship, Goal, etc.) remain valid except where explicitly reconciled above.
- "Decision is not an Entity" (Entity.md, Section 11) is preserved, not inverted; only the reason and cross-reference were clarified.
- Legacy documents under `Old/X00 Knowledge Repository/` were not modified. Concepts recovered from `Old/06 Business Model/Desire.md` and `Old/06 Business Model/Decision.md` were incorporated into `Core/ConceptualArchitecture/02_Desire_Goal_and_Reality_Check.md` and `03_Decision_Action_Outcome_Learning.md` where compatible; their conflicting claims (Desire → Process → Goal ordering; Decision as pure non-persistent computation) were not carried forward.

---

Version: Core 2.0 (TASK_CORE_006)

Date: 2026-08-23

Modified Entity:
`ConceptualArchitecture/02_Desire_Goal_and_Reality_Check.md`, `Process.md`, `Entity.md`, `Relationship.md`, `Glossary.md`.

Reason:
TASK_CORE_006 incorporated the approved universal concepts recorded in `07 Tasks/Backlog/LEGACY_KNOWLEDGE_RECONCILIATION_BACKLOG.md` (itself produced by `TASK_CORE_004`'s legacy reconciliation review of `90 Archive/Legacy Repository/X00 Knowledge Repository/06 Business Model/`), while explicitly keeping rejected Runtime, Domain and commercial patterns out of Core: Early Failure Recognition as a valuable outcome (preserving the impossible/infeasible/no-known-path/insufficient-knowledge/uncertain/temporarily-constrained distinctions); recursive Process decomposition without a separate universal `Activity` type; an Optimization Boundaries principle replacing the rejected literal `Mission > Domain Principles > Business Rules > Goal > Execution` ordering, without introducing `Mission` as a new Core primitive; an optional Entity versioning pattern (stable identity vs. versioned definition); Entity-level Temporal Semantics (without mandating database fields); Specialization Extends Rather Than Erases Identity as a conceptual (not OOP) modeling principle; and Ownership vs Assignment as distinct, non-synonymous Relationship meanings.

Concepts introduced/clarified:

- Early Failure Recognition (Desire/Goal/Reality Check)
- Recursive Process decomposition (no new `Activity` primitive)
- Optimization Boundaries (no new `Mission` primitive)
- Optional Entity Versioning Pattern
- Entity-level Temporal Semantics
- Specialization Extends Rather Than Erases Identity
- Ownership vs Assignment (Relationship, Glossary)

Impacted Domains:

- None directly modified. Restaurant Domain material was not touched; these are general-purpose Core patterns available to any future Domain.

Future Expected Impact:

- Any future Domain that models process hierarchies, entity/version relationships, temporal validity, specialization, or ownership/assignment distinctions.

Compatibility Notes:

- All prior Core 2.0 content is preserved; no existing definition was reversed. Changes are additive clarifications, not redefinitions.
- The following legacy items reviewed in this task were deliberately **not** imported into Core, per the backlog: the literal `Mission > Domain Principles > Business Rules > Goal > Execution` ordering; "Process status must never be persisted"; the Hybrid Event Model (immutable Events universally generate Entity state); Capacity/Availability/Responsibility placement generalizations; Capabilities Enable Services as a universal principle; the Operational Unit physical lifecycle; jurisdiction-specific Corporate legal fields; and all commercial-strategy items (Maximize Economic Profit, Cash-Based Profit, Unlimited Optimization Scope, SaaS-only strategy, shared-intelligence commercial model, counterfactual B2B value measurement as universal Outcome).
- Legacy documents under `90 Archive/Legacy Repository/` were not modified.

---

Version: Core 2.0 (TASK_CORE_013)

Date: 2026-08-26

Modified Entity:
`RF-ONE Core Principles.md` (Principle 20), a new canonical document `ConceptualArchitecture/08_Net_Outcome_and_Structural_Optimization.md`, and cross-reference/consistency updates to `ConceptualArchitecture/00_RF-One_Core_Vision.md`, `03_Decision_Action_Outcome_Learning.md`, `04_Temporal_Coherence_and_Evolution.md`, `05_Epistemic_Boundary_and_Subject_Sovereignty.md`, `07_Core_Glossary.md`, and `README.md`.

Reason:
TASK_CORE_013 made explicit that a Subject may care about the Net/Retained Outcome of an Action, not merely its Gross Outcome, that Reality may impose External Obligations/Claims that reduce or condition what is retained, that some Constraints are not immutable and may be lawfully changed through Constraint Shaping, and that RF-One should be able to perform Counterfactual Structural Comparison between alternative structures. It established the boundary between lawful optimization and evasion/fraud/misrepresentation/concealment/false reporting/sham transactions, and integrated all of this with the existing Epistemic Boundary (legal/tax interpretations are never silently Fact) and Temporal Coherence (obligation/structural rules are jurisdiction- and date-dependent, never timeless). Taxation was explicitly kept out of Core as a domain-specific application of this general capability.

Concepts introduced:

- Gross Outcome vs Net / Retained Outcome
- External Obligations / Claims
- Constraint Shaping
- Counterfactual Structural Comparison
- Lawful Optimization boundary (vs evasion, fraud, misrepresentation, concealment, false reporting, sham transactions)

Impacted Domains:

- None modified. This capability is designed for future consumption by a transversal Taxation Domain and by any Domain reasoning about external claims on Outcome; no existing Domain was touched.

Future Expected Impact:

- Any future Domain reasoning about obligations, structural alternatives, or after-obligation value (e.g. a future Taxation Domain, regulatory compliance Domains, contractual obligation management).

Compatibility Notes:

- All prior Core 2.0 content is preserved; no existing definition was reversed. Changes are additive: a new document plus small cross-referencing additions to existing documents.
- No tax rates, deductions, credits, depreciation rules, entity-specific tax rules, filing obligations, tax forms or a fixed tax-jurisdiction taxonomy were introduced into Core — see `ConceptualArchitecture/08_Net_Outcome_and_Structural_Optimization.md`, Section 11.
- No Domain, Product or Software file was modified.

---

# Design Principles

- The Core Domain is extracted from real domains.
- Practical experience has priority over theoretical elegance.
- Every Core concept must prove its usefulness in at least one real Domain.
- The Core should remain as small as possible.
- Unnecessary abstractions must be removed.
- Every modification must be justified and documented.
- Backward compatibility should be preserved whenever possible.

---

# Long-Term Vision

The Core Domain is the shared language of RF-One.

Its quality depends on continuous validation through real Application Domains.

A mature Core is therefore not the starting point of RF-One.

It is the result of its evolution.
