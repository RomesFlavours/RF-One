# Implementation Guidelines

## Purpose

This document provides implementation guidelines for every RF-One module.

Its purpose is to ensure that all implementations remain consistent with the RF-One Architecture, Domain Model and Business Principles.

Implementation choices must always preserve business meaning.

---

# Domain-Driven Implementation

Implementation always begins with the Domain.

The software architecture must reflect the business architecture.

Business concepts are implemented before technical infrastructure.

---

# Respect the Domain

The Domain Model is the single source of business truth.

Implementations shall never:

- redefine business concepts;
- duplicate business knowledge;
- introduce alternative business interpretations.

---

# Layer Separation

Every implementation shall clearly separate:

- Domain
- Application
- Infrastructure
- External Systems

Business logic belongs exclusively to the Domain layer.

## Channel Independence

The Domain layer's business capabilities and the Business Logic required to execute a Process shall not depend on the channel through which the Process is requested, triggered, observed or controlled.

Application/UI is one possible consumer of Domain capability, not the only one. The same Domain capability must be usable, where appropriate, by: Application/UI; Cognito or another cognitive interface; Scheduling/Event Triggering; another Process; an API/Connector; and any future channel. No consumer shall be required to simulate a browser, a form, a click, navigation or a UI route merely to obtain execution of Business Logic that already exists.

This does not: prohibit UI; require microservices, REST APIs, or a service bus; require a new deployment; mandate a specific technology; require every capability to be named "Engine"; or move Business Rules into Cognito or a Scheduler. UI, Cognito, Scheduler and Connector remain consumers/orchestrators — Business Logic remains in the Domain layer.

This is the architectural precondition for a Process to advance autonomously without depending on a person traversing a UI — see [ConceptualArchitecture/11_Process_Autonomy_and_Exception_Driven_Human_Involvement.md](ConceptualArchitecture/11_Process_Autonomy_and_Exception_Driven_Human_Involvement.md). It enables Process Autonomy, Scheduling/Event Triggering, Cognito and other autonomous Processes to consume the same Domain capability; it does not redefine any of them.

---

# External Systems

External systems are implementation details.

Every external source must be translated into RF-One business concepts through the Mapping Layer.

The Domain must never depend directly on external APIs, databases or file formats.

---

# Artificial Intelligence

Artificial Intelligence is an implementation service.

AI may:

- analyze;
- classify;
- recognize;
- estimate;
- suggest.

AI shall never replace Business Rules.

Business decisions always remain under Domain control.

---

# Configuration

Configuration changes system behavior.

Configuration must never change business meaning.

Business Rules are implemented in code, not in configuration files.

---

# Error Handling

Implementation errors must never corrupt business knowledge.

Whenever possible:

- preserve original data;
- log the error;
- continue processing;
- require human validation when necessary.

---

# Traceability

Every implementation shall preserve complete traceability between:

- source data;
- business objects;
- transformations;
- AI processing;
- human decisions.

---

# Testing

Every implementation shall verify:

- Business Rules;
- Domain integrity;
- Mapping correctness;
- Workflow behavior;
- historical consistency.

Testing validates business behavior rather than technical implementation.

---

# Extensibility

Every implementation shall allow future extensions without modifying existing business concepts.

New modules and new data sources must integrate through existing architectural principles.

---

# Design Principles

- Implement the Domain first.
- Keep business logic independent.
- Domain capability must not depend on the channel that invokes it.
- Separate business from infrastructure.
- Preserve traceability.
- Protect business knowledge.
- AI supports the Domain.
- Configuration never changes business meaning.
- Simplicity has priority over technical sophistication.