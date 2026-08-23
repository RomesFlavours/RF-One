# Glossary

## Purpose

This glossary defines the core concepts used throughout RF-One.

Each concept has a single business meaning and shall be interpreted consistently across every Domain, Module and implementation.

---

# Artificial Intelligence (AI)

A software component that supports business activities through analysis, recognition, prediction, suggestions, and — within explicitly delegated authority — Decisions and Actions.

Artificial Intelligence assists the Domain. RF-One may make and execute business decisions within delegated authority, but the Subject retains ultimate strategic sovereignty, override authority, and control over the boundaries of delegation. See [ConceptualArchitecture/06_Business_Autopilot_and_Intelligence_Engine.md](ConceptualArchitecture/06_Business_Autopilot_and_Intelligence_Engine.md).

RF-One's Core Conceptual Architecture (see [ConceptualArchitecture/07_Core_Glossary.md](ConceptualArchitecture/07_Core_Glossary.md)) defines a further set of canonical terms — Subject, Reality, Desire, Goal, Decision, Action, Outcome, Learning, and others — that specialize and extend this glossary. This document remains canonical for the terms defined below; it does not duplicate those definitions.

---

# Business Event

A fact that represents something that has occurred in the business.

Business Events are independent from the technology or external systems that generated them.

---

# Business Rule

A permanent rule that defines or constrains business behavior.

Business Rules belong to the Domain and are independent from software implementation.

---

# Configuration

A set of implementation parameters that influence system behavior without changing business meaning.

Configuration must never modify Business Rules.

---

# Domain

A coherent area of business knowledge represented by concepts, relationships and Business Rules.

The Domain defines the meaning of the business independently from technology.

---

# Entity

A business object with a unique identity that remains constant throughout its lifecycle.

An Entity may change its attributes while preserving its identity.

---

# External System

Any software, device or service outside RF-One that provides or consumes business information.

Examples include POS systems, accounting software, suppliers, banks and OCR services.

---

# Goal

The business objective that a Process exists to achieve.

A Process has meaning only if it contributes to the achievement of a Goal.

---

# Knowledge

Business information that has been interpreted and validated according to the Domain Model.

Knowledge is more than raw data.

---

# Mapping Layer

The architectural layer responsible for translating Source Records into RF-One business concepts.

The Mapping Layer isolates the Domain from external systems.

---

# Module

A software component responsible for implementing a specific business capability.

Every Module has a single business responsibility.

---

# Operational Area

A logical grouping of related business activities within a Domain.

Operational Areas organize business capabilities without defining implementation.

---

# Process

An ordered sequence of business activities performed to achieve a Goal.

A Process defines what must be accomplished, not how it is technically implemented.

---

# Relationship

A business association between two or more Entities.

Relationships describe how business concepts interact while preserving their individual identities.

---

# Source Record

The exact information received from an external system before any interpretation or transformation.

Source Records preserve the original representation provided by the source.

---

# Specification

A set of characteristics that further qualifies a business concept without changing its identity.

Specifications distinguish different variants of the same concept.

---

# Traceability

The ability to reconstruct every business object back to its original Source Record and every transformation applied during processing.

---

# Validation

The process of verifying that business information complies with the Domain Model and Business Rules.

Validation may be performed automatically, manually or through Artificial Intelligence.

---

# Workflow

The operational sequence through which a business Process is executed.

A Workflow implements a Process while respecting all Business Rules.