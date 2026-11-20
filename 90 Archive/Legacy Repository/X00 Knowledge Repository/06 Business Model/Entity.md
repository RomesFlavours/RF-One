# Entity
**Version:** 1.0
**Status:** Draft
**Core Domain**

## 1. Purpose
The Entity model defines the fundamental business building blocks of RF-ONE. An Entity represents a business concept with its own identity and lifecycle. The Core Domain is industry-agnostic.

## 2. Definition
An Entity:
- has a unique identity;
- exists independently from relationships;
- has its own lifecycle;
- may evolve through versions;
- exists in time.

Without identity there is no Entity.

## 3. Core Principles
- Identity First
- Independence
- Business Ownership
- Industry Agnostic

## 4. Identity
Every Entity has a permanent UUID that never changes and has no business meaning. User-facing codes are attributes, not identities.

## 5. Core Identity
An Entity remains the same while its Core Identity is preserved. If the business identity changes, a new Entity is created.

## 6. Lifecycle
Typical lifecycle:
- Created
- Active
- Suspended
- Archived
- Historical

Entities are never physically deleted.

## 7. Entity State
State belongs to the Entity lifecycle. Processes change state. Events record state changes.

## 8. Entity vs Relationship
Relationships connect Entities.
A Relationship becomes a Relationship Entity when it owns attributes, business rules or an independent lifecycle.
Examples:
- Employment
- Supply Agreement
- Recipe Component
- Membership

## 9. Entity vs Event
Entities describe what something IS.
Events describe what HAPPENED.

## 10. Entity vs Process
RF-ONE adopts a hybrid model.
Entities own invariants and valid states.
Processes orchestrate workflows, permissions, business rules and cross-entity interactions.

## 11. Attribute Ownership
Every attribute belongs to the business concept it actually describes.
Examples:
- Salary belongs to the Employee/Employment relationship.
- Supplier price belongs to the Supplier/Product relationship.
- Ingredient quantity belongs to the Recipe Component relationship.

## 12. Versioning
Business concepts remain stable.
Operational implementations evolve.
Business Entities own Version Entities.
Example:
Recipe
- Recipe Version 1
- Recipe Version 2
- Recipe Version 3

## 13. Temporal Domain
Every Entity exists in time.
RF-ONE must reconstruct the system at any historical moment.
Typical temporal attributes:
- Created At
- Effective From
- Effective To
- Archived At

## 14. Hybrid Event Model
Events are immutable historical facts.
Entities maintain the current operational state.
Processes transform Events into Entity state.

## 15. Best Practices
- Keep Entities focused.
- Preserve history.
- Store relationship attributes in Relationship Entities.
- Model business concepts, not implementation shortcuts.

## 16. Anti-Patterns
- Smart IDs
- Physical deletion
- Attributes in the wrong Entity
- Mixing Events with Entity state
- Modeling for the database instead of the business

## 17. Examples
Core:
- Corporate
- Brand
- Operational Unit
- Operational Area
- Restaurant
- Employee
- Supplier
- Product
- Customer

Restaurant Domain:
- Recipe
- Ingredient
- Menu
- Kitchen
- Order
- Reservation
- HACCP

## 18. Relationship with the Core Domain
Entity is the foundation of RF-ONE.
Relationship connects Entities.
Event records business facts.
Process orchestrates business behavior.
Version preserves evolution.
Time preserves history.
