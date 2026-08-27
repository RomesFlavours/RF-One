# RF-One Core

## Purpose

The Core defines the fundamental concepts, principles and architectural rules shared by every RF-One Domain and Module.

It establishes the common language of the platform and guarantees consistency across the entire system.

The Core is independent from any specific business domain.

---

# Authority

`00 Core/` holds the **highest canonical authority** in the repository for universal RF-One ontology, conceptual architecture, reasoning principles, epistemic principles, and domain-independent architecture.

Core must not contain Restaurant-specific (or any other single-Domain) business rules, and must not contain RF-One's own commercial strategy as a company — those belong to `01 Domains/` and `09 Strategy/` respectively.

Relationship to the other layers: **Core ≠ Domain ≠ Product ≠ Runtime**.

- `01 Domains/` applies and specializes Core concepts for a specific field; it does not redefine them.
- `02 Products/` combines Core capabilities and Domains into commercial offerings; it does not redefine Core or Domain semantics.
- `03 Software/` is authoritative for actual runtime behavior, but not for the conceptual meaning of Core/Domain concepts.

A concept existing in the Core does not imply that every Domain must use it, that every implementation must collect data for it, or that every Product must expose it — see `CLAUDE.md`.

---

# Scope

The Core defines:

- business concepts;
- architectural principles;
- implementation principles;
- domain-independent definitions;
- external data mapping principles;
- shared terminology.

It does not define business logic for any specific Domain or Module.

---

# Objectives

The Core ensures that every RF-One implementation:

- uses the same business language;
- follows the same architectural principles;
- preserves conceptual consistency;
- remains independent from implementation technology;
- evolves without breaking existing knowledge.

---

# Core Documents

| Document | Purpose |
|----------|---------|
| ArchitecturePrinciples.md | Defines the architectural principles of RF-One. |
| ImplementationGuidelines.md | Defines implementation guidelines shared by every module. |
| ExternalDataMappingPrinciples.md | Defines how external systems are mapped into the RF-One Domain Model. |
| Glossary.md | Defines the shared vocabulary used throughout RF-One. |
| Entity.md | Defines the concept of a Business Entity. |
| Goal.md | Defines the concept of a Goal. |
| Process.md | Defines the concept of a Business Process. |
| Relationship.md | Defines how business concepts relate to each other. |
| Corporate.md | Defines the highest organizational Entity (governance, ownership, strategy). |
| Brand.md | Defines the commercial identity through which a Corporate presents itself to the market. |
| Operational Unit.md | Defines the fundamental operational Entity responsible for executing business operations. |
| OperationalArea.md | Defines how business capabilities are logically organized. |
| RF-ONE Core Principles.md | Defines the fundamental principles governing the evolution of RF-One. |
| Core Evolution.md | Records the history and process of Core evolution. |
| ConceptualArchitecture/ | The canonical RF-One Core Conceptual Architecture: Subject, Reality, Desire, Goal, Reality Check, Decision, Action, Outcome, Learning, Temporal Coherence, Epistemic Boundary, Subject Sovereignty, Business Autopilot and Intelligence Engine, Net/Retained Outcome and Lawful Structural Optimization. Start at [ConceptualArchitecture/00_RF-One_Core_Vision.md](ConceptualArchitecture/00_RF-One_Core_Vision.md). |

---

# Design Philosophy

RF-One is designed around business knowledge.

Business concepts are defined before software implementation.

Technology exists to support the Domain, never to define it.

Every Domain and Module inherits the principles defined by the Core.

---

# Design Principles

- One shared business language.
- One definition for every core concept.
- Domain before technology.
- Architecture before implementation.
- Business knowledge before data.
- Consistency across all Domains and Modules.