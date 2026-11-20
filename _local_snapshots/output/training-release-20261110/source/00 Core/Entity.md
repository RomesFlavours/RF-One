# Entity

**Version:** 2.1
**Status:** Approved
**Module:** Core

## 1. Purpose
The Entity model defines the fundamental building block of the RF-ONE Core.

An Entity represents any concept that possesses its own identity, independently of any business domain, technology or implementation.

## 2. Definition
An Entity:
- has a unique identity;
- exists independently from relationships;
- owns attributes;
- may assume one or more roles;
- participates in relationships;
- has its own lifecycle.

Without identity there is no Entity.

## 3. Core Principles
- Identity First
- Independence
- Single Responsibility
- Industry Agnostic
- Composition Before Specialization

## 4. Identity
Every Entity owns a permanent RF-ONE identifier that never changes and has no business meaning.

User-facing codes are attributes, never identities.

## 5. Attributes
Attributes describe an Entity.

Changing attributes never changes the identity of the Entity.

## 6. Roles
An Entity may assume one or more roles depending on the context.

Examples:
- Owner
- Actor
- Resource
- Provider
- Consumer

Roles never create new Entities.

## 7. Relationships
Relationships connect Entities.

Relationships are independent from Entity identity.

When a relationship owns attributes or its own lifecycle it may be modeled as a Relationship Entity.

## 8. Responsibility
Every Entity exists to fulfill one or more business responsibilities.

Responsibilities may evolve without changing identity.

## 9. Lifecycle
Typical lifecycle:
- Created
- Active
- Suspended
- Archived
- Historical

Entities are never physically deleted.

## 10. Composition
Whenever possible, business behavior emerges through relationships between Entities rather than specialization.

## 11. What an Entity is NOT
The following are not Entities:
- State
- Event
- Decision
- Collection

They are properties, results or derived concepts.

`Decision` is a first-class concept of the RF-One Core (see [ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md](ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md)), but "first-class Core concept" does not mean "Entity." Not being modeled as an Entity here does not diminish Decision's conceptual status — it means Decision does not, by default, carry Entity identity semantics (a permanent identifier, an independent lifecycle). Whether a specific Decision instance is persisted (as a Decision Record) or related over time (through Decision Memory) is a separate, Domain/Runtime-level question, not something to be inferred automatically from Entity status.

## 12. Examples
Core examples:
- Corporate
- Brand
- Operational Unit
- Operational Area
- Item

Domain-specific entities belong to their respective Domains.

## 13. Optional Versioning Pattern
Core allows — but never requires — a Domain to represent stable conceptual identity separately from versioned definitions or configurations, when the Domain's business meaning genuinely requires distinguishing them.

Illustrative example only, not a Core concept:

```text
Recipe
→ Recipe Version 1
→ Recipe Version 2
```

`Recipe` above is illustrative; it does not make Recipe a Core concept.

Safeguards:
- Not every Entity must be versioned.
- Not every version must itself be a persistent Entity.
- Core does not prescribe version tables, schema fields, or storage mechanisms.
- Entity identity, temporal validity (Section 14), versioned definition, and audit history are four distinct concerns and must not be merged into one.

## 14. Temporal Semantics
An Entity, its attributes, its relationships, and any versioned definition (Section 13) may have temporal validity: they may be true, applicable or in effect only during a particular period, and may change over time.

Where a Domain or Runtime requires it, RF-One should be able to reason about:
- what was true;
- what is true;
- what is expected or intended to become true;
- when a given definition or relationship applied;
- the historical trajectory of an Entity.

This aligns with Temporal Coherence — see [ConceptualArchitecture/04_Temporal_Coherence_and_Evolution.md](ConceptualArchitecture/04_Temporal_Coherence_and_Evolution.md), which reasons about accumulated Decisions and Outcomes over time; this section is the Entity-level counterpart — the capacity to represent that a definition or relationship itself had a period of validity.

Core does not mandate specific fields (for example `EffectiveFrom` / `EffectiveTo`) or any other database representation, and does not imply that every Entity shares the same lifecycle or temporal granularity. Temporal validity, versioned definition (Section 13), and audit history remain distinct concerns and must not be merged: a version identifies *which* definition applied; temporal validity identifies *when* it applied; audit history records *what changed and why*.

## 15. Specialization Extends Rather Than Erases Identity
A specialized concept may extend a more general concept — adding Constraints, Relationships, attributes, rules, behavior or Domain semantics — without silently replacing or erasing the general concept's meaning and identity. A specialization should not redefine its parent so aggressively that the parent ceases to mean the same thing.

This is a conceptual modeling principle, not an object-oriented programming rule: it does not force inheritance as a software implementation pattern. Composition (Section 10) remains the preferred way to express business behavior; specialization is appropriate only when it represents a genuine business distinction rather than a shortcut around composition.

## 16. Relationship with the Core
Entity is the foundation of the RF-ONE Core.

Entities:
- own Attributes;
- participate in Relationships;
- may assume Roles;
- may be referenced by Processes;
- may contribute to Goals.
