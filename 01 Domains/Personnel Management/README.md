# Personnel Management Domain

**Version:** 0.1
**Status:** Draft (canonical structure established; modules at varying depth)
**Module:** Domain / Personnel Management

---

## Purpose

**Personnel Management** is the transversal (cross-industry) Domain responsible for managing people across the organization: who occupies which roles, who else could credibly occupy them, whether people meet the standard the role requires, what they actually produce, and what should be done about the person currently in the role.

Personnel Management does not belong to Restaurant or to any other technical Domain. Restaurant is one application context that supplies technical content Personnel Management consumes — it is not the architectural owner of Personnel Management, in the same relationship already established for Selection (see [../Domain Architecture.md](../Domain%20Architecture.md)).

---

## Transversal scope

Personnel Management is a **universal business Domain**. It applies wherever an organization has people occupying roles, regardless of industry. Its modules reason about people using the same structure whether the role is a Restaurant Kitchen Manager, a Restaurant/Purchasing account manager, or a role in an entirely different industry; only the technical/behavioral content supplied by the target Domain changes.

---

## Module map

```text
Personnel Management
├── Workforce
├── Selection
├── Training
├── Performance
└── Personnel Decisions
```

These are **modules of one transversal Domain**, not independent top-level Domains. Each module is documented in its own subfolder:

| Module | Answers | Status |
|---|---|---|
| [Workforce/](Workforce/README.md) | Who currently occupies or can occupy organizational roles? | Placeholder — see `Workforce/README.md` |
| [Selection/](Selection/README.md) | Who else is a credible alternative for a role, vacant or not? | Documented — migrated from TASK_SELECTION_002 (Selection, SelectionRequirement, CandidateEvidence, FitAssessment, SelectionDecision, TrainableGap) |
| [Training/](Training/README.md) | How do we close an evidenced, trainable gap? | Placeholder — see `Training/README.md` |
| [Performance/](Performance/README.md) | What did the person actually produce, in Reality? | Documented — TASK_PERSONNEL_001 (Performance, PerformanceEvidence, PerformanceMeasure, PerformanceIndicator, PerformanceContext) |
| [Personnel Decisions/](Personnel%20Decisions/README.md) | What should be done about the person currently in the role? | Placeholder — see `Personnel Decisions/README.md` |

---

## Relationship to Core 2.0

Personnel Management is built on the RF-One Core Conceptual Architecture and reuses its concepts without redefining them, in particular:

- **Subject / Reality** — see [../../00 Core/ConceptualArchitecture/01_Subject_and_Reality.md](../../00%20Core/ConceptualArchitecture/01_Subject_and_Reality.md).
- **Goal** — see [../../00 Core/ConceptualArchitecture/02_Desire_Goal_and_Reality_Check.md](../../00%20Core/ConceptualArchitecture/02_Desire_Goal_and_Reality_Check.md) and [../../00 Core/Goal.md](../../00%20Core/Goal.md).
- **Decision, Action, Outcome, Learning** — see [../../00 Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md](../../00%20Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md). Personnel Decisions applies this cycle to people-related decisions without redefining it.
- **Temporal Coherence** — see [../../00 Core/ConceptualArchitecture/04_Temporal_Coherence_and_Evolution.md](../../00%20Core/ConceptualArchitecture/04_Temporal_Coherence_and_Evolution.md). Observed Performance and Personnel Decisions accumulate over time; a Decision made under earlier Evidence does not retroactively become invalid when later Evidence arrives.
- **Epistemic Boundary and Subject Sovereignty** — see [../../00 Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md](../../00%20Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md). Governs how Candidate Evidence, Performance evidence and Personnel Decisions preserve provenance, uncertainty and Decision authority (including Delegated Authority).
- **Constraint, Relationship, Ownership, Assignment** — see [../../00 Core/Relationship.md](../../00%20Core/Relationship.md) and [../../00 Core/Glossary.md](../../00%20Core/Glossary.md).

This Domain does not redefine any of these concepts; each module specializes them only where a genuine Personnel-Management-specific meaning is required.

---

## Relationship to technical Domains

Personnel Management consumes technical content from whichever Domain the role belongs to; it does not duplicate that Domain's knowledge.

```text
Restaurant Domain (or another technical Domain)
  → role requirements, technical standards, operational context, operational evidence, expected outcomes

Personnel Management
  → applies Workforce / Selection / Training / Performance / Personnel Decisions
    reasoning on top of that content
```

Restaurant remains primarily the technical/operational Domain (see [../Restaurant/README.md](../Restaurant/README.md)). Restaurant does not own Workforce, Selection, Training, Performance or Personnel Decisions.

---

## Relationship to Customer Feedback and Review

Customer Feedback and Review remain separate transversal Domain candidates — they are **not** modules of Personnel Management (see [../Domain Architecture.md](../Domain%20Architecture.md) §6). Personnel Management's Performance module may consume their evidence when relevant (e.g. a customer comment about a specific employee's service), but Personnel Management does not own or define Customer Feedback or Review.

---

## Continuous operating loop

Personnel Management's modules relate through the following guiding loop. This is descriptive of how the modules interact, not a rigid or mandatory formula, and no step is automatic:

```text
Observed Performance
→ communicate / correct / opportunity to improve
→ Training where economically justified
→ observe again

in parallel:

Selection
→ find credible alternatives

then:

Personnel Decision
→ compare current expected value with available alternatives
→ retain / develop / move / replace
```

The comparison a Personnel Decision may draw on:

```text
Expected value of current person

vs

Expected value of available alternative
- recruitment cost
- training cost
- transition cost
- uncertainty / risk
```

This is a guiding principle, not a formula RF-One evaluates automatically. See [Personnel Decisions/README.md](Personnel%20Decisions/README.md).

---

## KPI principle

Personnel Management does not canonize a fixed KPI list. Performance indicators depend on Goals, Brand, role, the target technical Domain, available Evidence and observed Outcomes, and must be derived rather than assumed — see [../Domain Architecture.md](../Domain%20Architecture.md) §8. No KPI algorithm or scoring formula is defined by this Domain.

---

## Current documentation status

- **Selection** — documented in depth (six concept files, migrated unchanged in meaning from `01 Domains/Selection/`, TASK_SELECTION_002). See [Selection/README.md](Selection/README.md).
- **Performance** — documented in depth (Performance, PerformanceEvidence, PerformanceMeasure, PerformanceIndicator, PerformanceContext; TASK_PERSONNEL_001). See [Performance/README.md](Performance/README.md).
- **Workforce, Training, Personnel Decisions** — minimal placeholder `README.md` only. Purpose and module boundary are recorded; detailed concept modeling (entities, business rules, data requirements) is deferred to future tasks.

---

## Related documents

- [../Domain Architecture.md](../Domain%20Architecture.md) — cross-Domain conclusions this structure canonicalizes
- [../README.md](../README.md) — `01 Domains/` purpose and authority
- [../Restaurant/README.md](../Restaurant/README.md), [../Restaurant/Roadmap.md](../Restaurant/Roadmap.md) — Restaurant's technical/operational boundary
- [Selection/README.md](Selection/README.md) — Selection module
- [Performance/README.md](Performance/README.md) — Performance module
