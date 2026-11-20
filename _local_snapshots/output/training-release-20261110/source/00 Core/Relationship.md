# Relationship.md

# RF-ONE Core Domain

**Version:** 2.1

------------------------------------------------------------------------

# Purpose

A Relationship represents a meaningful business association between
Business Objects. It is a first-class business concept whose purpose is
to describe how business concepts interact, independently from
implementation or storage.

------------------------------------------------------------------------

# Principles

## 1. Business Meaning

A Relationship exists whenever a meaningful business association exists.

It may originate from: - User input - API - Invoice - Catalog -
Simulation - AI reasoning - Prediction

Its existence does **not** depend on transactions.

## 2. Identity

A Relationship has its own identity.

-   Attribute changes → same Relationship.
-   Business meaning changes → new Relationship.

## 3. Lifecycle

Relationships have their own lifecycle independent from the connected
Business Objects.

Typical states: - Candidate - Approved - Preferred - Suspended -
Archived

## 4. Attribute Ownership

Relationship attributes describe the association, not either endpoint.

Examples: - Price - Lead Time - MOQ - Supplier Quality - Delivery
Frequency - Preferred Status

## 5. Binary by Design

Relationships should preferably connect two Business Objects. More
complex structures emerge through composition.

## 6. Relationships are First-Class Objects

Relationships may participate in other Relationships whenever business
semantics require it.

## 7. Canonical Business Objects

Relationships connect canonical Business Objects. Supplier-specific
descriptions do not create duplicate Products.

## 8. Explicit and Derived Relationships

Relationships may be: - Explicit - AI Derived

## 9. Knowledge Evolution

AI continuously discovers: - new Relationships - hidden patterns -
business opportunities

## 10. Validation Pipeline

Observation

↓

Thought

↓

Hypothesis

↓

Simulation

↓

Proposal

↓

Validated Knowledge

↓

Business Decision

↓

Business Outcome

↓

Learning

↓

New Knowledge

## 11. Opportunity Before Explanation

Business value may be evaluated before complete causal understanding.
Lack of explanation must not prevent innovation.

## 12. Universal Connectivity

Any Business Object may be connected to any other Business Object
whenever a valid business meaning exists.

## 13. Incomplete Knowledge

Relationships may contain unknown elements. The system must reason with
partial knowledge.

## 14. Mission Alignment

RF-ONE exists to help entrepreneurs make the best possible decisions
using all available knowledge while continuously generating new business
knowledge.

Within explicitly delegated authority, RF-ONE may also execute and continuously correct course, not only recommend — operating as a Business Autopilot under human command. This does not remove the importance of human strategic control: the Subject retains sovereignty over direction, Goals, authority boundaries and override at all times. See [ConceptualArchitecture/06_Business_Autopilot_and_Intelligence_Engine.md](ConceptualArchitecture/06_Business_Autopilot_and_Intelligence_Engine.md) and [ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md](ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md).

## 15. Ownership vs Assignment

Ownership and Assignment are distinct Relationship meanings and must not be treated as synonyms.

An Entity may simultaneously be:
- owned by one Subject/Entity;
- assigned to another;
- operated by another;
- responsible to another;
- available to another;

without any of those Relationships being equivalent to, or implying, another.

Core does not prescribe universal cardinalities or a database model for Ownership or Assignment. Core does not assume that Ownership implies operational responsibility, nor that Assignment transfers Ownership. Where a Domain needs to give Ownership or Assignment its own attributes or lifecycle, it may model it as a Relationship Entity (see [Entity.md](Entity.md), Section 7).

------------------------------------------------------------------------

# Design Philosophy

RF-ONE models business reality, not database structures.

The Business Model comes first. Persistence technology is only an
implementation detail.


# Core 1.0 Updates

- Relationship connects Entities.
- A Relationship may become a Relationship Entity only when it owns its own identity, attributes, responsibilities or lifecycle.
- Roles (Owner, Actor, Resource) belong to Entities, not Relationships.
- Relationships never define Goals or Processes; they only express business meaning.
- Relationship is part of the Core and is independent from any Domain or Environment.
