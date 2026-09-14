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

Version: Core 2.0 (CORE_IDENTITY_AUTHORITY_SECURITY_ARCHITECTURE)

Date: 2026-09-05

Modified Entity:
`RF-ONE Core Principles.md` (Principle 21), `ArchitecturePrinciples.md` (new section "Shared Identity, Authority and Security Infrastructure," Design Principles), `Glossary.md` cross-reference note unchanged, a new canonical document `ConceptualArchitecture/09_Identity_Authority_and_Accountability.md`, and cross-reference/index updates to `ConceptualArchitecture/00_RF-One_Core_Vision.md`, `ConceptualArchitecture/07_Core_Glossary.md`, and `README.md`.

Reason:
A documentation-only architecture task required RF-One's existing implicit notions of "who acts" and "were they allowed to" to be made explicit, transversal Core concepts, so that no Domain or Module invents its own independent identity/authority/audit mechanism. This made explicit: Identity (an Acting Identity is an Entity assuming the Actor role, carrying a permanent identifier independent of visible role/title labels — generalizing `Entity.md` §4/§6, not replacing it), Authority (the bounded, contextual scope of Decisions/Actions an Acting Identity may perform — elevating the "authority" input already named in `03_Decision_Action_Outcome_Learning.md` §2), Delegation (the general Core relationship of which the existing Delegated Authority, Pilot → RF-One, is the specific and most important instance), Accountability (attributing a Decision/Action to its Acting Identity and Authority, including the AI Recommendation vs. AI-Authorized Execution distinction), and Auditability (the capability to reconstruct who/what/when/context/authority/before/after, consistent with the already-existing Traceability and Historical Integrity principles and with Temporal Coherence). The corresponding technical architecture (authentication mechanism, authorization enforcement, RF-One Operational Signature, audit trail, security layers, AWS as primary cloud, multi-tenant isolation, provider abstraction) was documented separately at the Software/Runtime layer, not in Core, per Core's definition-not-implementation nature — see `10 System/Identity & Access/Identity Authority and Security Architecture.md` (moved there from `03 Software/` when the System top-level area was introduced) and `07 Tasks/Reports/CORE_IDENTITY_AUTHORITY_SECURITY_ARCHITECTURE_REPORT.md`.

Concepts introduced:

- Acting Identity
- Authority (as a first-class concept, not merely a Decision input label)
- Delegation (generalizing Delegated Authority)
- Accountability (including AI Recommendation vs. AI-Authorized Execution)
- Auditability

Impacted Domains:

- None modified. This is general-purpose Core vocabulary available to any Domain; no existing Domain file was touched.

Future Expected Impact:

- Every future Domain or Product that models who performs a Decision/Action, what authority governs it, how authority is delegated, or how it must be reconstructable afterward (audit/compliance requirements).

Compatibility Notes:

- All prior Core 2.0 content is preserved; no existing definition was reversed. Changes are additive: a new document plus cross-referencing additions. Delegated Authority (`06_Business_Autopilot_and_Intelligence_Engine.md`) is explicitly preserved as-is and identified as a specific instance of the newly-named general Delegation relationship, not redefined.
- No concrete authentication provider, permission engine, audit table schema, or multi-tenant implementation was introduced anywhere in `00 Core/` — those remain Runtime/Software concerns by design (Core is definition, not implementation).
- No Domain, Product or Software business-logic file was modified; only `03 Software/` cross-cutting *architecture documentation* was added/extended, mirroring how `User Interaction Architecture.md` already sits at that layer.

---

Version: Core 2.0 (CORE_PROCESS_AUTONOMY_AND_EXCEPTION_DRIVEN_HUMAN_INVOLVEMENT)

Date: 2026-09-12

Modified Entity:
`RF-ONE Core Principles.md` (Principle 23), a new canonical document `ConceptualArchitecture/11_Process_Autonomy_and_Exception_Driven_Human_Involvement.md`, and cross-reference/index updates to `ConceptualArchitecture/00_RF-One_Core_Vision.md` and `README.md`.

Reason:
An approved Product Owner conceptual decision required RF-One to be documented as executing its Processes autonomously within established rules and Delegated Authority — already established by `06_Business_Autopilot_and_Intelligence_Engine.md` and by `10_RF-One_Intelligence_and_User_Relationship.md` §12 — verifying their actual result rather than presenting an unverified result as achieved, and involving the competent Acting Identity only when genuine human contribution is required, rather than reproducing an equivalent screen-driven workflow through a sequence of voice commands. This specializes, and does not redefine, the existing Business Autopilot / Delegated Authority model, the Decision/Action/Outcome/Learning cycle, and Identity/Authority/Accountability. It makes explicit that a Process description must start from the expected result and its verification condition (reusing `Process.md`'s existing Components and Verification, and `Goal.md`'s Verification principle) rather than from the sequence of screens a user operates, that an anomaly RF-One can resolve within its own authority does not require escalation, and that when escalation is required it must reach the specific competent Acting Identity with a circumscribed, contextualized request rather than the whole Process or a fixed universal target (e.g. always the highest authority in the organization).

Concepts introduced:

- Process Autonomy (Process execution without a human as a mandatory link between stages, within already-established rules and Delegated Authority)
- Exception-Driven Human Involvement (escalation only when genuinely required, addressed to the specific competent Acting Identity, never a default full-process handoff)
- the completion criterion: a Process concludes only once its expected result is verified, not when a calculation finishes or a command is dispatched to an external system

Impacted Domains:

- None modified. This is a Core-level principle available to any Domain or Product; no existing Domain, Product or Software file was touched. The Restaurant Tips nightly-routine example used to illustrate the principle is recorded as a Product Owner functional objective only, not as an implemented capability, and does not alter the Tips/Compensation/Payroll/Banking Domain boundaries.

Future Expected Impact:

- Any future Domain, Product or interaction-layer design (including a future cognitive/voice interface) that must decide when RF-One acts without human involvement, what a Process's completion condition is, and who a required escalation must reach.

Compatibility Notes:

- All prior Core 2.0 content is preserved; no existing definition was reversed. Changes are additive: a new document plus small cross-referencing additions.
- Business Autopilot, Delegated Authority (`06_Business_Autopilot_and_Intelligence_Engine.md`), the Decision/Action/Outcome/Learning cycle (`03_Decision_Action_Outcome_Learning.md`) and Identity/Authority/Accountability (`09_Identity_Authority_and_Accountability.md`) are explicitly preserved as-is; this document specializes them for Process execution and completion, it does not redefine them.
- No specific interface, device, vendor, or the separate, still "CONCEPTUAL DIRECTION — UNDER REVIEW" `00 Core/Cognitive Interface/RF-ONE_COGNITIVE_INTERFACE_CONCEPT.md` document is authorized or elevated in status by this change.
- Open item (resolved by the following entry): the Product Owner's task instructions referred to an existing Core distinction "Planning → Scheduling/Programming → Management → Operations" to be preserved. This exact sequence could not be located as an existing canonical Core, Domain or Software distinction under this or an equivalent name; per the no-new-taxonomy instruction, this document does not assert or fix such a sequence as Core — see `07 Tasks/Reports/CORE_PROCESS_AUTONOMY_AND_EXCEPTION_DRIVEN_HUMAN_INVOLVEMENT_REPORT.md` for the full note and the question for the Product Owner.
- No Domain, Product or Software file was modified.

---

Version: Core 2.0 (CORE_PROCESS_PHASES)

Date: 2026-09-12

Modified Entity:
`Process.md` (new section "Phases of Execution," plus two Design Principles bullets), `RF-ONE Core Principles.md` (Principle 24), and `ConceptualArchitecture/11_Process_Autonomy_and_Exception_Driven_Human_Involvement.md` (updated cross-references, §3 and Related documents, and the corresponding Non-assumptions line, to reflect that the sequence is now formalized rather than open).

Reason:
A Product Owner conceptual decision, following directly from the open item recorded in the previous entry (CORE_PROCESS_AUTONOMY_AND_EXCEPTION_DRIVEN_HUMAN_INVOLVEMENT), formalized the chronological sequence by which a Process's execution progresses: Planning (determining what is to be achieved and under what approach) → Scheduling/Programming (turning what was planned into commitments, assignments, timing or operational readiness) → Management (governing execution: attention, resources, reacting to actual conditions, keeping the Process within Goal/rules/constraints) → Operations (materially carrying out the work that produces the result). This is a logical progression of organizational work, not a software taxonomy, menu structure or mandatory module subdivision, and a Process is not required to formally contain all four phases (`Process.md`, "Recursive Decomposition," already establishes that decomposition is optional and Domain/Runtime-specific). None of the four phases is defined by who or what performs it: within Delegated Authority, RF-One may itself perform Planning, Scheduling/Programming, Management or Operations activity, consistent with Principle 23 and `ConceptualArchitecture/11_Process_Autonomy_and_Exception_Driven_Human_Involvement.md`. Reporting, Administration, Analysis and Feedback were explicitly excluded from this sequence: they observe, support, document, measure or influence the Process without being chronological phases of it; legal, compliance and tax constraints enter the Process as rules/limits under the pre-existing "Optimization Boundaries" section, not as separate phases.

Concepts introduced:

- Phases of Execution: Planning, Scheduling/Programming, Management, Operations (a chronological decomposition of Process execution, not a new Core primitive alongside Process, Decision, Action or Outcome)
- Explicit exclusion of Reporting, Administration, Analysis and Feedback from this sequence

Impacted Domains:

- None modified. This is a Core-level refinement of the existing Process concept, available to any Domain; no existing Domain, Product or Software file was touched. The Tips distribution example used to illustrate the four phases is recorded as a short, generic illustration only and does not modify Tips Domain documentation.

Future Expected Impact:

- Any future Domain or Product that models how a Process's execution unfolds over time, or that needs to distinguish operational phases from Reporting/Administration/Analysis/Feedback.

Compatibility Notes:

- All prior Core 2.0 content is preserved; no existing definition was reversed. The change is additive: a new section in `Process.md`, one new Core Principle, and small cross-reference corrections in the document (11) that had left this sequence explicitly open.
- `Process.md`'s existing Recursive Decomposition, Optimization Boundaries, Verification and Components sections are unchanged in meaning; the new section specializes "Recursive Decomposition" without replacing it.
- No new ConceptualArchitecture document was created; per the task's stated preference, the concept was integrated directly into the existing `Process.md`, judged semantically sufficient.
- No Domain, Product or Software file was modified.

---

Version: Core 2.0 (CORE_ORGANIZATIONAL_RESPONSIBILITY_AND_ATTENTION_MANAGEMENT)

Date: 2026-09-12

Modified Entity:
Two new canonical documents — `Organizational Responsibility.md` (Position, Position scope, Position vs. Occupant, temporary coverage, Process Ownership) and `ConceptualArchitecture/12_Attention_Management.md` (Attention Management: priority, real-time vs. non-real-time attention, attention list vs. report, aggregation, the Cognito interaction principle, direct human intervention and resumption, escalation as organizational policy, human state/context, Learning boundaries) — plus `RF-ONE Core Principles.md` (Principles 25–26) and cross-reference/index updates to `ConceptualArchitecture/00_RF-One_Core_Vision.md` and `README.md`.

Reason:
Process Autonomy (`11_Process_Autonomy_and_Exception_Driven_Human_Involvement.md`) already requires every Process to name the Acting Identity responsible when human contribution is required, and Identity/Authority/Delegation (`09_Identity_Authority_and_Accountability.md`) already establish who acts and under what authority — but neither states which organizational Position is responsible for a given Process, independent of the specific person currently occupying it, nor how RF-One decides whether, to whom, and how a matter genuinely requiring human attention actually reaches that Position's occupant. A Product Owner conceptual decision formalized both gaps as two related, non-overlapping Core documents: `Organizational Responsibility.md` establishes Position as a stable responsibility (scoped through the already-existing Corporate/Brand/Operational Unit/Operational Area hierarchy, never a parallel one) that a person occupies for a period, that may be temporarily covered by a delegate, and that owns a Process or a specific phase of it (reusing `Process.md`'s "Phases of Execution"); `ConceptualArchitecture/12_Attention_Management.md` defines the transversal capability that consumes Position/Process Ownership together with Authority/Delegation to determine whether a matter requires human attention, who receives it, with what priority (CRITICAL/HIGH/MEDIUM/LOW, dynamically determined, never a fixed table), through what channel, and at what level of synthesis — explicitly distinguishing the attention list from a general report, real-time operational intervention from non-real-time attention, and stating that Cognito (or any interaction channel) is a channel, never the Process engine. Neither document fixes a universal organizational hierarchy shape or a universal escalation rule: both are declared organizational policy/configuration, consistent with CLAUDE.md's "Modular Architecture" and the existing refusal (`06_Business_Autopilot_and_Intelligence_Engine.md` §2) to impose a single authority/permission taxonomy.

Concepts introduced:

- Position (a stable organizational responsibility, distinct from its current occupant)
- Position Scope, Position vs. Occupant, Temporary Coverage (a form of Delegation)
- Process Ownership (a Process, or Process phase, attributed to a responsible Position)
- Attention Management (the capability determining whether/who/priority/channel/synthesis for human attention)
- Priority levels CRITICAL/HIGH/MEDIUM/LOW as a dynamic, context-determined classification (not a fixed table)
- Attention List (distinct from a general operational report)
- Real-time operational intervention vs. non-real-time attention
- The Cognito interaction principle ("I interrupted you for X. I would do Y. Do you authorize me?") and direct human intervention with automatic Process resumption

Impacted Domains:

- None modified. Both documents are general-purpose Core vocabulary available to any Domain or Product; no existing Domain, Product or Software file was touched. The illustrative examples (a server struggling during service; a generic Process-phase ownership example) are recorded as non-normative illustrations only, consistent with how the Tips example in document 11 was handled.

Future Expected Impact:

- Any future Domain or Product that models an organizational chart, job/role definitions, shift coverage, on-call/escalation policy, or a proactive/attention-driven interface (including a future Cognitive Interface/Cognito, still separately "CONCEPTUAL DIRECTION — UNDER REVIEW" and not elevated in status by this change).

Compatibility Notes:

- All prior Core 2.0 content is preserved; no existing definition was reversed. Changes are additive: two new documents plus small cross-referencing additions to `00_RF-One_Core_Vision.md`, `README.md` and `RF-ONE Core Principles.md`.
- Identity, Authority, Delegation and Accountability (`09_Identity_Authority_and_Accountability.md`) are explicitly preserved as-is; Position is defined as what an Acting Identity occupies to hold role-derived Authority, not a replacement for any of the four.
- Corporate/Brand/Operational Unit/Operational Area (`Corporate.md`, `Brand.md`, `Operational Unit.md`, `OperationalArea.md`) are explicitly preserved as-is; Position's scope is expressed through this existing hierarchy. The pre-existing "Manager" attribute on Operational Unit/Operational Area is identified as a lightweight precedent this document generalizes, not superseded or required to change.
- No universal organizational hierarchy shape, no universal escalation rule (e.g. "always escalate to the superior"), and no fixed priority-scoring table were introduced — these remain organizational policy/configuration by explicit design.
- No data model, database schema, notification system, scheduler, queue or API was introduced anywhere in `00 Core/` — those remain Runtime/Software/Product concerns by design (Core is definition, not implementation).
- No Domain, Product or Software file was modified.

---

Version: Core 2.0 (CORE_UI_INDEPENDENT_DOMAIN_LOGIC)

Date: 2026-09-12

Modified Entity:
`ImplementationGuidelines.md` ("Layer Separation" section — new "Channel Independence" subsection; one new Design Principles bullet).

Reason:
An audit of five representative Domains (Tips, Compensation, Purchasing, Selection, Training) against Process Autonomy (`ConceptualArchitecture/11_Process_Autonomy_and_Exception_Driven_Human_Involvement.md`) found that in four of five cases Business Logic already lives in plain, UI-independent modules, and that the remaining gaps (an unwired reconciliation call, a missing input-derivation capability, a manual batch trigger, and Training's absent Gap/Priority logic) are Domain/Implementation/Governance gaps, not evidence of a missing structural capability. A Product Owner conceptual decision formalized the already-prevailing pattern as an explicit architectural requirement, extending `ImplementationGuidelines.md`'s existing "Business logic belongs exclusively to the Domain layer" rule: Domain capability must not depend on the channel — Application/UI, Cognito or another cognitive interface, Scheduling/Event Triggering, another Process, or an API/Connector — through which a Process is requested, triggered, observed or controlled. This is the architectural precondition Process Autonomy already presupposes for a Process to advance without a person traversing a UI; it does not redefine Process Autonomy, Attention Management or Organizational Responsibility.

Concepts introduced:

- Channel Independence (Domain capability must not depend on its calling channel — Application/UI is one consumer among several, never the only one)

Impacted Domains:

- None modified. This is a clarification of an existing Implementation Guideline, available to any Domain; no Tips, Compensation, Purchasing, Selection or Training file was touched. The local gaps identified by the audit were deliberately left open — they are Domain/Implementation/Governance corrections, not part of this formalization.

Future Expected Impact:

- Any future Domain, Product, Scheduling/Event Triggering capability, or cognitive interface (Cognito) design that needs to invoke existing Domain capability without duplicating or simulating UI behavior.

Compatibility Notes:

- All prior content is preserved; the change is an additive clarification of the pre-existing "Layer Separation" section, not a new rule. No new Core Principle, document, layer or Entity was introduced.
- No microservice, REST API, service bus, deployment, or specific technology was mandated; UI, Cognito, Scheduler and Connector remain consumers/orchestrators, never holders of Business Logic.
- No Domain, Product or Software file was modified.

---

Version: Core 2.0 (CORE_PROCESS_ACTIVATION_AND_TRIGGER_INTELLIGENCE)

Date: 2026-09-12

Modified Entity:
A new canonical document `ConceptualArchitecture/13_Process_Activation_and_Trigger_Intelligence.md` (Process Activation; Trigger Intelligence; Explicit/Implicit Trigger; Trigger Discovery vs. Trigger Resolution vs. Authorized Consequence; Derived Trigger Map; Missing Semantics), `RF-ONE Core Principles.md` (Principle 27), and cross-reference/index updates to `ConceptualArchitecture/00_RF-One_Core_Vision.md` and `README.md`.

Reason:
A repeatability test conducted on the Invoice Intake / Purchasing Process (three independent trigger-discovery passes over the same canonical documentation) found that most explicit and implicit triggers governing a Process's activation and behavior can be recognized directly from existing Process, Business Rule, Entity and State documentation, without a centralized, manually maintained, trigger-by-trigger hardcoded list — and that the triggers which proved unstable across passes were concentrated exactly where the necessary semantics lived in documentation the Process's own canonical description never referenced. A Product Owner conceptual decision generalized what had been framed, in prior analysis, as "Scheduling / Event Triggering" into the broader Process Activation and Trigger Intelligence: time is one possible triggering event among others (a Payroll Period closing, a document arriving, a second reconciliation source becoming available are all instances of the same underlying concept — an observable change in Reality relevant to one or more Processes), not a separate foundational Core concept. The document makes explicit that recognizing a trigger never itself grants Authority to act on it (Trigger Discovery ≠ Trigger Resolution ≠ Authorized Consequence), that a recognized human-attention need is handed to Attention Management rather than resolved internally, that Process Activation must be able to invoke Domain capability under the already-approved Channel Independence principle, and that a possible future Derived Trigger Map is knowledge derived from the Process — regenerable, invalidatable, and never authoritative over the canonical Business Knowledge it comes from.

Concepts introduced:

- Process Activation (starting, advancing, resuming, branching, or making a Rule applicable to a Process — broader than "starting a Process")
- Trigger Intelligence (recognizing explicit and implicit triggers from canonical Process/Business/Entity/State knowledge)
- Explicit Trigger / Implicit Trigger
- Trigger Discovery vs. Trigger Resolution vs. Authorized Consequence
- Derived Trigger Map (a non-authoritative, regenerable, invalidatable representation of recognized triggers — not a data model or runtime artifact)
- Missing Semantics (representing a gap in Business Knowledge needed to resolve a trigger, rather than inventing a value)

Impacted Domains:

- None modified. This is a Core-level principle available to any Domain or Product; no Invoice Intake, Purchasing, or other Domain file was touched. The Invoice Intake example used to illustrate the principle (§14 of the new document) is recorded as a brief, non-normative illustration only, consistent with how prior illustrative examples (Tips, doc 11; a server struggling during service, doc 12) were handled, and does not modify Invoice Intake/Purchasing Domain documentation.

Future Expected Impact:

- Any future Domain, Product, or capability design (including a future Scheduling/event-triggering mechanism, or Cognito) that needs to recognize what activates or changes a Process without a hardcoded, per-Process trigger list.

Compatibility Notes:

- All prior Core 2.0 content is preserved; no existing definition was reversed. The change is additive: a new document plus small cross-referencing additions.
- Process Autonomy (`11_Process_Autonomy_and_Exception_Driven_Human_Involvement.md`), Attention Management (`12_Attention_Management.md`), Organizational Responsibility, Identity/Authority/Delegation (`09_...md`) and Channel Independence (`ImplementationGuidelines.md`) are explicitly preserved as-is; this document specializes and connects them at the point of Process activation, it does not redefine any of them.
- No scheduler, event bus, queue, Trigger table, confidence-scoring algorithm, AI model, or API was introduced or selected anywhere in `00 Core/` — those remain future Runtime/Software/Product concerns by design (Core is definition, not implementation).
- No Domain, Product or Software file was modified.

---

Version: Core 2.0 (CORE_COGNITO_COGNITIVE_INTELLIGENCE)

Date: 2026-09-12

Modified Entity:
A new canonical document `ConceptualArchitecture/14_Cognito_RF-One_Cognitive_Intelligence.md`; corrections to `ConceptualArchitecture/13_Process_Activation_and_Trigger_Intelligence.md` §12–§13 (Cognito's relationship to Trigger Intelligence and to the Process Activation sequence), `ConceptualArchitecture/12_Attention_Management.md` §7 (the Cognito interaction principle), and `ConceptualArchitecture/11_Process_Autonomy_and_Exception_Driven_Human_Involvement.md` §5 (interaction channel wording); a discoverability note added to `00 Core/Cognitive Interface/RF-ONE_COGNITIVE_INTERFACE_CONCEPT.md` without changing its status; `RF-ONE Core Principles.md` (Principle 28); and cross-reference/index updates to `ConceptualArchitecture/00_RF-One_Core_Vision.md`, `README.md` and `ConceptualArchitecture/07_Core_Glossary.md`.

Reason:
Documents 12 and 13, approved earlier in the same conceptual sequence, had each independently described Cognito as "a possible interaction channel" — adequate as far as it went, but incomplete: it left Cognito indistinguishable from a plain voice/UI channel and, in document 13, described Trigger Intelligence as something Cognito merely carried messages for rather than something Cognito itself does. A Product Owner conceptual decision corrected this: Cognito is RF-One's Cognitive Intelligence — a single transversal cognitive capacity, of which Human Interaction (conversation, briefing/debriefing, explanation) and Trigger Intelligence (document 13) are two capabilities among others, not two independent intelligences. The distinction between Cognito's capabilities is functional, not ontological, and a technical implementation may separate them into different agents, processes or services for performance, latency, reliability, scalability or fault isolation — but that separation must never produce divergent Business Knowledge, divergent Authority, divergent Process semantics, or conceptually independent intelligences; every capability consumes the same canonical RF-One knowledge. Attention Management (document 12) remains a distinct capability, not absorbed by Cognito: Trigger Intelligence (a Cognito capability) detects that a matter requires human attention, Attention Management decides who/when/priority/channel, and Cognito's Human Interaction capability may be the cognitive channel Attention Management actually reaches the person through. The document also formally records the terminology collision already present in the repository between this concept and AWS Cognito (a System-level authentication technology candidate, `10 System/Identity & Access/`), without renaming either.

Concepts introduced:

- Cognito (RF-One Cognitive Intelligence) — a single transversal cognitive capacity, not a channel
- Trigger Intelligence and Human Interaction as capabilities of Cognito (functional, not ontological, distinction)
- Cognito's open, non-exhaustive capability list (Human Interaction, Trigger Intelligence, Context Interpretation, Explanation, Briefing/Debriefing)
- Implementation freedom for Cognito's capabilities, bounded by a shared-canonical-knowledge requirement
- The explicit "Cognito ≠ AWS Cognito" terminology distinction

Impacted Domains:

- None modified. This is a Core-level correction and addition available to any Domain or Product; no Domain, Product or Software file was touched, including `10 System/Identity & Access/`, which was reviewed only to confirm the AWS Cognito naming collision and was not modified.

Future Expected Impact:

- Any future design of an actual Cognito runtime, agent, or interface, and any future Domain or Product description of a human-facing interaction that must correctly attribute Business Logic to the Domain, not to Cognito.

Compatibility Notes:

- All prior Core 2.0 content is preserved; no existing definition was reversed except the specific "Cognito = a channel" phrasing in documents 11 §5, 12 §7 and 13 §13, which is corrected in place with an explicit note rather than silently rewritten, consistent with Historical Integrity (`ArchitecturePrinciples.md`) applied to Core documentation itself.
- Process Autonomy, Attention Management, Process Activation and Trigger Intelligence's own substance (documents 11, 12, 13 §1–§11) are explicitly preserved and not reopened; only their description of Cognito's role is corrected.
- `00 Core/Cognitive Interface/RF-ONE_COGNITIVE_INTERFACE_CONCEPT.md` remains at its own stated status, "CONCEPTUAL DIRECTION — UNDER REVIEW" — it was not elevated to Approved, per the task's explicit instruction; only a discoverability note pointing to the new canonical document was added.
- No agent runtime, AI model, prompt, API, microservice, or deployment topology was designed, chosen, or created. AWS Cognito was not renamed or modified.
- No Domain, Product or Software file was modified.

---

---

Version: PROPOSED — Post-Baseline Conceptual Extension (CORE_HUMAN_OPERATIONAL_STATE_AND_ADAPTIVE_COGNITO_INTERACTION)

Date: 2026-09-13

Modified Entity:
A new document `ConceptualArchitecture/15_Human_Operational_State_and_Adaptive_Cognito_Interaction.md` (status PROPOSED, not Approved Core 2.0), plus discoverability/cross-reference-only additions to `ConceptualArchitecture/00_RF-One_Core_Vision.md`, `ConceptualArchitecture/07_Core_Glossary.md`, `ConceptualArchitecture/12_Attention_Management.md` (Related documents only), `ConceptualArchitecture/14_Cognito_RF-One_Cognitive_Intelligence.md` (Related documents plus one clarifying sentence in §3), `Organizational Responsibility.md` (Related documents only), `README.md`, and a FUTURE/CONCEPTUAL EXTENSION note in `RF_ONE_2_0_BASELINE.md`.

Reason:
This work was produced from `release/rf-one-2.0` (tag `rf-one-2.0-baseline`), **after** the `core-2.0-freeze` tag, on a dedicated branch (`docs/cognito-human-operational-state`) — a Product Owner conceptual exploration, not (yet) an approved architectural decision folded into the canonical 00–14 set. It formalizes that the same person is not operationally identical at every moment of the same shift, and that Cognito's Human Interaction capability ([14](ConceptualArchitecture/14_Cognito_RF-One_Cognitive_Intelligence.md) §3) may adapt to the person's current, temporary Human Operational State — informed by operational context, behavioral context, and, where authorized, physiological evidence — without that state ever becoming a medical diagnosis, an Authority change, or a permanent judgment about the person. It explicitly distinguishes this temporary state from the durable, stable person knowledge already described in [10](ConceptualArchitecture/10_RF-One_Intelligence_and_User_Relationship.md) §6–§8, states that it may only influence Attention Management's existing routing/timing/priority/channel decisions ([12](ConceptualArchitecture/12_Attention_Management.md)) and Organizational Responsibility's existing Temporary Coverage/Backup Position/Fallback mechanisms (`Organizational Responsibility.md` §3, §5) — never Position, Authority, or Process Ownership themselves — and states an explicit privacy/consent/data-minimization boundary for any authorized physiological signal, without designing its compliance implementation.

Concepts introduced (PROPOSED, not yet Approved Core 2.0):

- Human Operational State (temporary, contextual, dynamic; distinct from stable person knowledge)
- Adaptive Cognito Interaction (a specialization of the existing Human Interaction capability, not a new Cognito capability)
- Authorized Physiological Evidence as contextual, non-conclusive Evidence (Epistemic Boundary), never a diagnostic signal
- The explicit Human Operational State ≠ Medical State boundary
- The explicit privacy/consent/data-minimization boundary for physiological signals
- Device/wearable independence for future human-state signal consumption

Impacted Domains:

- None modified. No Software, Product, or Domain file was touched; this is documentation-only, Core-level conceptual material available to any future Domain or Product. No wearable, sensor, vendor, threshold, formula, or diagnostic algorithm was chosen or designed.

Future Expected Impact:

- Any future Cognito Edge/mobile bridge design, any future Domain or Product surfacing shift-based or workload-based human context, and any future consent/compliance implementation task for physiological data.

Compatibility Notes:

- All prior Core 2.0 content is preserved; no existing definition was reversed. This entry is explicitly additive and, unlike prior entries in this log, is **not** presented as an Approved Core 2.0 change: the new document's own status is "PROPOSED — Post-Baseline Conceptual Extension," it is deliberately **not** added to the canonical 00–14 table in `00_RF-One_Core_Vision.md` §6 or to `README.md`'s "Approved Core 2.0" ConceptualArchitecture description (both list it only for discoverability, following the same pattern already used for `20_RF-One_Selection_Pills_Cognitive_Model.md`), and `RF-ONE Core Principles.md` was deliberately **not** modified — the "Cognito Principle" this work formalizes is stated only inside the new document itself (§1), pending a future, separate Product Owner ratification decision to number it as a Core Principle.
- The `core-2.0-freeze` tag was not moved and is not referenced as covering this content. `RF_ONE_2_0_BASELINE.md` was updated only to add a FUTURE/CONCEPTUAL EXTENSION note; it was not rewritten to imply this capability is implemented.
- Cognito ([14](ConceptualArchitecture/14_Cognito_RF-One_Cognitive_Intelligence.md)), Attention Management ([12](ConceptualArchitecture/12_Attention_Management.md)), Organizational Responsibility, and Identity/Authority/Delegation/Accountability ([09](ConceptualArchitecture/09_Identity_Authority_and_Accountability.md)) are explicitly preserved as-is; this new document specializes them for one narrow purpose, it does not redefine any of them.
- No Domain, Product or Software file was modified.

---

Version: Core 2.0 (Ratification — CORE_HUMAN_OPERATIONAL_STATE_AND_ADAPTIVE_COGNITO_INTERACTION)

Date: 2026-09-13

Modified Entity:
`ConceptualArchitecture/15_Human_Operational_State_and_Adaptive_Cognito_Interaction.md` (Status header and one Non-assumptions line only), `ConceptualArchitecture/07_Core_Glossary.md` (status parentheticals for the three terms it introduced), `README.md` (discoverability line status), and `RF_ONE_2_0_BASELINE.md` (FUTURE/CONCEPTUAL EXTENSION note status) — following the final consistency review recorded in this ratification entry. `01 Domains/Cross Domain/PERSON_CONTINUITY_001.md` also received a short, targeted cross-reference to document 15, distinguishing Stable Person Knowledge/continuity from current Human Operational State.

Reason:
The Product Owner ratified `ConceptualArchitecture/15_Human_Operational_State_and_Adaptive_Cognito_Interaction.md` following a dedicated final consistency review against Cognito ([14](ConceptualArchitecture/14_Cognito_RF-One_Cognitive_Intelligence.md)), Attention Management ([12](ConceptualArchitecture/12_Attention_Management.md)), Organizational Responsibility, Identity/Authority/Accountability ([09](ConceptualArchitecture/09_Identity_Authority_and_Accountability.md)), the Epistemic Boundary ([05](ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md)), stable person knowledge ([10](ConceptualArchitecture/10_RF-One_Intelligence_and_User_Relationship.md) §6–§8), Person Continuity (`01 Domains/Cross Domain/PERSON_CONTINUITY_001.md`), and the `core-2.0-freeze` discipline. No conceptual contradiction was found; the review confirmed that Human Operational State is never a permanent trait, that Authorized Physiological Evidence remains Evidence and never Fact, that it never creates Authority, that Cognito interprets/adapts interaction while Attention Management alone decides who/when/priority/channel, that vitals never become a medical diagnosis, that a temporary state can never automatically become disciplinary evidence, a Selection score, a Performance penalty, or a permanent label, and that device/wearable independence is preserved. The document's own status is accordingly changed from PROPOSED to **APPROVED — Post-Baseline Conceptual Extension**.

Concepts introduced:

- None new. This entry ratifies the status of concepts already introduced by the prior PROPOSED entry above (Human Operational State, Adaptive Cognito Interaction, Authorized Physiological Evidence); it does not add or redefine any concept.

Impacted Domains:

- None modified beyond the single targeted Person Continuity cross-reference named above. No Software, Product, or Domain business-logic file was touched.

Future Expected Impact:

- Same as the prior PROPOSED entry above; ratification does not by itself trigger new consumption, only removes PROPOSED status from the document and its glossary terms.

Compatibility Notes:

- **APPROVED — Post-Baseline Conceptual Extension does not mean retroactively part of `core-2.0-freeze` or of `release/rf-one-2.0`.** The `core-2.0-freeze` tag was not moved, and its history was not rewritten. Document 15 remains outside the Approved Core 2.0 00–14 canonical set (`00_RF-One_Core_Vision.md` §6) — ratification approves it as a stable, standalone post-baseline extension, not as an addition to that frozen set.
- Promotion of this document's canonical principle (§1 of document 15) to a numbered entry in `RF-ONE Core Principles.md` is deliberately **not** performed by this entry and remains a separate, future Product Owner decision.
- `ConceptualArchitecture/00_RF-One_Core_Vision.md` §6, `ConceptualArchitecture/12_Attention_Management.md`, `ConceptualArchitecture/14_Cognito_RF-One_Cognitive_Intelligence.md`, and `Organizational Responsibility.md` still describe document 15's status as "PROPOSED" in their own Related-documents notes as of this entry; these were intentionally left unmodified because they were outside this review's authorized file scope. This is recorded as a known, non-blocking staleness (see the corresponding task report) to be corrected in a small, separate follow-up edit.
- All prior Core Evolution entries are preserved unchanged, consistent with Historical Integrity (`ArchitecturePrinciples.md`): this is an additive new entry, not a rewrite of the PROPOSED entry it ratifies.
- No Domain, Product or Software file was modified.

---

---

Version: PROPOSED — Post-Baseline Conceptual Extension (CORE_AMBIENT_OPERATIONAL_CONTEXT_AND_IN_FLOW_COGNITO_ASSISTANCE)

Date: 2026-09-14

Modified Entity:
A new document `ConceptualArchitecture/16_Ambient_Operational_Context_and_In-Flow_Cognito_Assistance.md` (status PROPOSED, not Approved Core 2.0), plus discoverability/cross-reference-only additions to `ConceptualArchitecture/00_RF-One_Core_Vision.md`, `ConceptualArchitecture/07_Core_Glossary.md`, `ConceptualArchitecture/12_Attention_Management.md` (Related documents only), `ConceptualArchitecture/13_Process_Activation_and_Trigger_Intelligence.md` (Related documents only), `ConceptualArchitecture/14_Cognito_RF-One_Cognitive_Intelligence.md` (Related documents plus one clarifying sentence in §6), `README.md`, and `01 Domains/Business Domain/Restaurant/Service Copilot/README.md` (Related documents only).

Reason:
This work was produced from the tip of `docs/cognito-human-operational-state` — which already carries document 15 as APPROVED — Post-Baseline Conceptual Extension — on a further dedicated branch (`docs/cognito-ambient-operational-context`), following a Product Owner conceptual exploration, not (yet) an approved architectural decision folded into the canonical 00–14 set. It formalizes that Cognito should be able to understand the real operational context in which a person is working — the current conversation, process, business entities, counterpart, and canonical business state — without requiring the person to interrupt their work to query RF-One explicitly, and specializes this as **Ambient Operational Context**, distinct from the person's own Human Operational State (document 15). It specializes Cognito's already-named, previously unspecialized **Context Interpretation** capability ([14] §6) rather than adding a new one, and states how Ambient Operational Context feeds Cognito's Human Interaction capability as **In-Flow Cognito Assistance** and Trigger Intelligence as Trigger Discovery evidence — never itself an Authorized Consequence ([13] §3). It states a mandatory boundary distinguishing Ambient Cognition from Employee Surveillance/Recording, generalizing document 15 §10's privacy/consent/data-minimization discipline from physiological signals to ambient/conversational signals. It identifies the Restaurant Domain's existing, Approved Service Copilot module as a pre-existing instance of the same general pattern, without redefining it. It records cross-industry illustrations (retail, restaurant, legal assistant, accountant) as non-normative only, explicitly not asserting that RF-One currently has Retail, Legal, or Accounting Domains, and explicitly excluding legal/medical advice or professional decision substitution, consistent with the existing Epistemic Boundary rule that a legal or tax interpretation must never be silently promoted to Fact ([05] §1).

Concepts introduced (PROPOSED, not yet Approved Core 2.0):

- Ambient Operational Context (what is happening around a person, distinct from Human Operational State)
- In-Flow Cognito Assistance (a specialization of the existing Human Interaction capability, using Ambient Operational Context combined with canonical business state)
- The explicit Ambient Cognition ≠ Employee Surveillance/Recording boundary
- The explicit "ambient observation ≠ Authority" restatement of Trigger Discovery/Resolution/Authorized Consequence for ambient evidence specifically

Impacted Domains:

- None modified. No Software, Product, or Domain business-logic file was touched; the single Domain-level edit is a discoverability-only cross-reference added to the Restaurant Domain's existing Service Copilot README, which is not itself redefined. No wearable, sensor, vendor, microphone, transcription mechanism, or surveillance capability was chosen or designed.

Future Expected Impact:

- Any future Cognito Edge/mobile bridge design, any future Domain or Product surfacing real-time in-flow operational assistance (including a possible future description of Service Copilot as an instance of this Core concept), and any future consent/compliance implementation task for ambient/conversational data.

Compatibility Notes:

- All prior Core 2.0 content is preserved; no existing definition was reversed. This entry is additive and, like the initial document 15 entry before its ratification, is **not** presented as an Approved Core 2.0 change: the new document's own status is "PROPOSED — Post-Baseline Conceptual Extension," it is deliberately **not** added to the canonical 00–14 table in `00_RF-One_Core_Vision.md` §6 or to `README.md`'s "Approved Core 2.0" ConceptualArchitecture description (both list it only for discoverability), and `RF-ONE Core Principles.md` was deliberately **not** modified.
- The `core-2.0-freeze` tag was not moved and is not referenced as covering this content.
- Cognito ([14](ConceptualArchitecture/14_Cognito_RF-One_Cognitive_Intelligence.md)), Human Operational State ([15](ConceptualArchitecture/15_Human_Operational_State_and_Adaptive_Cognito_Interaction.md)), Attention Management ([12](ConceptualArchitecture/12_Attention_Management.md)), Trigger Intelligence ([13](ConceptualArchitecture/13_Process_Activation_and_Trigger_Intelligence.md)), Organizational Responsibility, Identity/Authority/Delegation/Accountability ([09](ConceptualArchitecture/09_Identity_Authority_and_Accountability.md)), and the Restaurant Domain's Service Copilot module are explicitly preserved as-is; this new document specializes them for one narrow purpose, it does not redefine any of them.
- No Domain, Product or Software business-logic file was modified.

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
