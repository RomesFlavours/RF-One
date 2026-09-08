# Personnel Management Domain

**Version:** 0.2
**Status:** Draft (canonical structure established; modules at varying depth). Domain family: **Cross Domain** (`01 Domains/Cross Domain/Personnel Management/`) — see [../../Domain Architecture.md](../../Domain%20Architecture.md) §4.
**Domain:** Personnel Management (Cross Domain)

---

## Purpose

**Personnel Management** is the transversal (cross-industry) Domain responsible for managing people across the organization: who occupies which roles, who else could credibly occupy them, whether people meet the standard the role requires, what they actually produce, and what should be done about the person currently in the role.

Personnel Management does not belong to Restaurant or to any other technical Domain. Restaurant is one application context that supplies technical content Personnel Management consumes — it is not the architectural owner of Personnel Management (see [../Domain Architecture.md](../../Domain%20Architecture.md)).

**Selection, the former Training, and Performance were previously documented as modules of Personnel Management; each is now its own top-level Cross Domain**, a sibling of Personnel Management — see [../Selection/README.md](../Selection/README.md), [../Continuous Productivity Development/README.md](../Continuous%20Productivity%20Development/README.md), [../Operational Knowledge/README.md](../Operational%20Knowledge/README.md), [../Performance/README.md](../Performance/README.md) and `../../Domain%20Architecture.md` §4-5. Personnel Management's Personnel Decisions module consumes Selection's and Performance's output without owning or duplicating either, the same relationship Personnel Management has with any other Domain it consumes from.

---

## Transversal scope

Personnel Management is a **universal business Domain**. It applies wherever an organization has people occupying roles, regardless of industry. Its modules reason about people using the same structure whether the role is a Restaurant Kitchen Manager, a Restaurant/Purchasing account manager, or a role in an entirely different industry; only the technical/behavioral content supplied by the target Domain changes.

---

## Module map

Personnel Management's **remaining modules are Workforce and Personnel Decisions**. Selection, the former Training (now Operational Knowledge) and Performance were formerly modules here too; all three, plus the later-added Continuous Productivity Development, are now sibling top-level Cross Domains, not modules of this Domain — do not re-nest them:

```text
Cross Domain/
├── Personnel Management
│   ├── Workforce
│   └── Personnel Decisions
├── Selection
├── Continuous Productivity Development
├── Operational Knowledge
└── Performance
```

| Module | Answers | Status |
|---|---|---|
| [Workforce/](Workforce/README.md) | Who currently occupies or can occupy organizational roles? | Placeholder — see `Workforce/README.md` |
| [Personnel Decisions/](Personnel%20Decisions/README.md) | What should be done about the person currently in the role? | Placeholder — see `Personnel Decisions/README.md` |

Selection, Continuous Productivity Development, Operational Knowledge and Performance — each its own Cross Domain, not listed in this table — are documented at [../Selection/README.md](../Selection/README.md), [../Continuous Productivity Development/README.md](../Continuous%20Productivity%20Development/README.md), [../Operational Knowledge/README.md](../Operational%20Knowledge/README.md) and [../Performance/README.md](../Performance/README.md) respectively.

---

## Relationship to Core 2.0

Personnel Management is built on the RF-One Core Conceptual Architecture and reuses its concepts without redefining them, in particular:

- **Subject / Reality** — see [../../00 Core/ConceptualArchitecture/01_Subject_and_Reality.md](../../../00%20Core/ConceptualArchitecture/01_Subject_and_Reality.md).
- **Goal** — see [../../00 Core/ConceptualArchitecture/02_Desire_Goal_and_Reality_Check.md](../../../00%20Core/ConceptualArchitecture/02_Desire_Goal_and_Reality_Check.md) and [../../00 Core/Goal.md](../../../00%20Core/Goal.md).
- **Decision, Action, Outcome, Learning** — see [../../00 Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md](../../../00%20Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md). Personnel Decisions applies this cycle to people-related decisions without redefining it.
- **Temporal Coherence** — see [../../00 Core/ConceptualArchitecture/04_Temporal_Coherence_and_Evolution.md](../../../00%20Core/ConceptualArchitecture/04_Temporal_Coherence_and_Evolution.md). Observed Performance and Personnel Decisions accumulate over time; a Decision made under earlier Evidence does not retroactively become invalid when later Evidence arrives.
- **Epistemic Boundary and Subject Sovereignty** — see [../../00 Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md](../../../00%20Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md). Governs how Candidate Evidence, Performance evidence and Personnel Decisions preserve provenance, uncertainty and Decision authority (including Delegated Authority).
- **Constraint, Relationship, Ownership, Assignment** — see [../../00 Core/Relationship.md](../../../00%20Core/Relationship.md) and [../../00 Core/Glossary.md](../../../00%20Core/Glossary.md).

This Domain does not redefine any of these concepts; each module specializes them only where a genuine Personnel-Management-specific meaning is required.

---

## Relationship to technical Domains

Personnel Management consumes technical content from whichever Domain the role belongs to; it does not duplicate that Domain's knowledge.

```text
Restaurant Domain (or another technical Domain)
  → role requirements, technical standards, operational context, operational evidence, expected outcomes

Personnel Management
  → applies Workforce / Personnel Decisions
    reasoning on top of that content, consuming Selection's and Performance's output where relevant
```

Restaurant remains primarily the technical/operational Domain (see [../Restaurant/README.md](../../Business%20Domain/Restaurant/README.md)). Restaurant does not own Workforce, Personnel Decisions, Selection, Continuous Productivity Development, Operational Knowledge, or Performance.

---

## Relationship to Customer Feedback and Review

Customer Feedback and Review remain separate transversal Domain candidates — they are **not** modules of Personnel Management, nor of any other Domain (see [../Domain Architecture.md](../../Domain%20Architecture.md) §6). The sibling Performance Cross Domain (not a Personnel Management module — see "Module map" above) may consume their evidence when relevant (e.g. a customer comment about a specific employee's service); Personnel Management itself does not own or define Customer Feedback or Review.

---

## Continuous operating loop

Personnel Management's modules (Workforce, Personnel Decisions) relate through the following guiding loop, which also draws on the sibling Selection, Continuous Productivity Development and Performance Cross Domains' output, even though none of them is a Personnel Management module. This is descriptive of how they interact, not a rigid or mandatory formula, and no step is automatic:

```text
Observed Performance
→ communicate / correct / opportunity to improve
→ Continuous Productivity Development intervention where economically justified
→ observe again

in parallel (Selection Domain, external to Personnel Management):

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

Personnel Management does not canonize a fixed KPI list. Performance indicators depend on Goals, Brand, role, the target technical Domain, available Evidence and observed Outcomes, and must be derived rather than assumed — see [../Domain Architecture.md](../../Domain%20Architecture.md) §8. No KPI algorithm or scoring formula is defined by this Domain.

---

## Current documentation status

This Domain's own modules:

- **Workforce, Personnel Decisions** — minimal placeholder `README.md` only. Purpose and module boundary are recorded; detailed concept modeling (entities, business rules, data requirements) is deferred to future tasks.

Sibling Cross Domains, not documented here (own top-level Domains — see "Module map" above):

- **Selection** — documented in depth; see `../Selection/README.md`.
- **Performance** — documented in depth (Performance, PerformanceEvidence, PerformanceMeasure, PerformanceIndicator, PerformanceContext; TASK_PERSONNEL_001); see `../Performance/README.md`.
- **Continuous Productivity Development** — draft concept specification; see `../Continuous Productivity Development/README.md`.
- **Operational Knowledge** — Domain boundary and core concept (formerly the Training placeholder); see `../Operational Knowledge/README.md`.

---

## Related documents

- [../Domain Architecture.md](../../Domain%20Architecture.md) — cross-Domain conclusions this structure canonicalizes, including the Cross Domain / Business Domain taxonomy (§4)
- [../README.md](../../README.md) — `01 Domains/` purpose and authority
- [../Restaurant/README.md](../../Business%20Domain/Restaurant/README.md), [../Restaurant/Roadmap.md](../../Business%20Domain/Restaurant/Roadmap.md) — Restaurant's technical/operational boundary
- [../Selection/README.md](../Selection/README.md), [../Continuous Productivity Development/README.md](../Continuous%20Productivity%20Development/README.md), [../Operational Knowledge/README.md](../Operational%20Knowledge/README.md), [../Performance/README.md](../Performance/README.md) — sibling Cross Domains (not modules) of Personnel Management
