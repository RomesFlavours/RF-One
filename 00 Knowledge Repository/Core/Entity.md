# Entity

**Version:** 2.0
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

## 13. Relationship with the Core
Entity is the foundation of the RF-ONE Core.

Entities:
- own Attributes;
- participate in Relationships;
- may assume Roles;
- may be referenced by Processes;
- may contribute to Goals.
