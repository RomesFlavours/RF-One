# Performance Module

**Version:** 0.2
**Status:** Draft (initial canonical foundation)
**Module:** Domain / Personnel Management / Performance

---

## Purpose

The Performance module provides the reusable knowledge and reasoning structure Personnel Management uses to answer:

> **What is this person actually producing in Reality, in this role, under this context?**

Performance is not a fixed score and is not a predefined KPI dashboard. It grounds Personnel Management in actually observed [Reality](../../../00%20Core/ConceptualArchitecture/01_Subject_and_Reality.md) rather than impression, reputation, or prediction — see [Performance.md](Performance.md).

---

## Module boundary

Performance answers **"what did the person actually produce"**. It is distinct from the other Personnel Management modules:

- [Workforce](../Workforce/README.md) answers "who currently occupies the role";
- [Selection](../Selection/README.md) answers "who else is a credible alternative," and predicts rather than observes — see "Relationship to Selection" below;
- [Training](../Training/README.md) answers "how do we close an evidenced gap" — Performance is what evidences the gap, and later shows whether it closed;
- [Personnel Decisions](../Personnel%20Decisions/README.md) answers "what should be done about the person currently in the role," using Performance as one input among others, without Performance itself making that Decision.

**No universal performance score is defined here, and none should be assumed to exist. No fixed KPI list is hard-coded by this module.**

---

## Relationship to Core 2.0

Performance is built on the RF-One Core Conceptual Architecture and reuses its concepts without redefining them:

- **Reality** — Performance is what a person actually produces in Reality; see [../../../00 Core/ConceptualArchitecture/01_Subject_and_Reality.md](../../../00%20Core/ConceptualArchitecture/01_Subject_and_Reality.md).
- **Epistemic Boundary** (Fact, Observation, Evidence, Belief, Assumption, Inference, Hypothesis, Unknown) — governs how [Performance Evidence](PerformanceEvidence.md) preserves provenance, uncertainty, and the distinction between direct observation and derived interpretation; see [../../../00 Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md](../../../00%20Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md).
- **Goal, Decision, Action, Outcome, Learning** — Performance relates observed results to expected Outcomes for a Goal, without assuming any single direction (e.g. more revenue) is automatically better; see [../../../00 Core/ConceptualArchitecture/02_Desire_Goal_and_Reality_Check.md](../../../00%20Core/ConceptualArchitecture/02_Desire_Goal_and_Reality_Check.md) and [../../../00 Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md](../../../00%20Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md).
- **Temporal Coherence** — Performance distinguishes isolated event, recurring pattern, improvement, decline, stable performance and context-specific variation by reusing this Core capability, not a parallel temporal framework; see [../../../00 Core/ConceptualArchitecture/04_Temporal_Coherence_and_Evolution.md](../../../00%20Core/ConceptualArchitecture/04_Temporal_Coherence_and_Evolution.md) and [Performance.md](Performance.md), "Temporal evolution."
- **Constraint, Assignment** — operational constraints and a person's Assignment are part of [Performance Context](PerformanceContext.md); see [../../../00 Core/Relationship.md](../../../00%20Core/Relationship.md) and [../../../00 Core/Glossary.md](../../../00%20Core/Glossary.md).

This Domain does not redefine any of these concepts. It specializes them into the Performance-specific documents listed below only where a genuine Performance-specific meaning is required.

---

## Relationship to Workforce

Performance must be attributable to a relevant person/role/Assignment context, but Workforce itself (Person/Worker, Role, Position, Assignment, Responsibility, Availability, Schedule, Employment Relationship) is not modeled in depth by this module or by [Workforce/README.md](../Workforce/README.md) yet. Where a Performance document needs one of these concepts (e.g. Assignment as part of Performance Context), it references it as an external dependency without defining it — the same dependency pattern already used by [Selection/README.md](../Selection/README.md), "Future Workforce dependency."

---

## Relationship to Selection

**Selection predicts. Performance observes.**

[Selection](../Selection/README.md) reasons about a candidate's likely fit and expected Performance before an Assignment exists — a Fit Assessment is an Inference/Hypothesis under the Epistemic Boundary, not an observed result. Performance is what is actually observed afterward. The two remain compatible with the feedback loop Selection's own documentation already anticipates:

```text
Selection expectation
  → Assignment
    → actual Performance
      → Outcome
        → Learning
          → improved future Selection
```

Performance must therefore preserve enough meaning and provenance (see [PerformanceEvidence.md](PerformanceEvidence.md)) to support this loop later — for example, letting a future Selection reasoning process ask which candidate characteristics predicted the Performance actually observed after hiring. **This module does not redesign Selection**, and does not build the feedback mechanism itself.

---

## Relationship to Training

Training may consume Performance Evidence to identify an evidenced gap, and later Performance Evidence may show whether Training changed the result:

```text
Observed Performance
  → Gap
    → Training
      → later Performance
        → Learning
```

See also [Selection/TrainableGap.md](../Selection/TrainableGap.md) for the currently drawn Selection/Training boundary on what counts as a trainable gap. **This module does not model Training in depth.**

---

## Relationship to Personnel Decisions

[Personnel Decisions](../Personnel%20Decisions/README.md) may use Performance to compare the current person with alternatives Selection has identified. **Performance itself does not decide retain / train / move / replace** — it provides Reality-grounded evidence for that Decision, together with economics, Constraints, uncertainty and authority that belong to Personnel Decisions, not to Performance. Economic replacement logic is not modeled in this module.

---

## Relationship to technical Domains

Performance consumes Performance Evidence, expected Outcomes, and relevant [Performance Context](PerformanceContext.md) dimensions from whichever technical Domain the role belongs to; it does not duplicate that Domain's knowledge.

```text
Restaurant Domain (or another technical Domain)
  → operational evidence: sales, margin, service time, throughput, product mix,
    quality events, and other target-Domain evidence
  → relevant context: shift, volume, menu/product mix, staffing, and other
    target-Domain-determined context dimensions

Performance module
  → preserves that evidence atomically, distinguishes Measures from Indicators,
    and interprets it through the applicable Performance Context
```

Restaurant is used throughout this module's documents only as a first validation example, not as the architectural owner of Performance — the same relationship already established for Selection (see [../../Domain Architecture.md](../../Domain%20Architecture.md) §2).

---

## Relationship to Customer Feedback and Review

Customer Feedback and Review remain separate transversal Domain candidates, not modules of Personnel Management (see [../README.md](../README.md), "Relationship to Customer Feedback and Review," and [../../Domain Architecture.md](../../Domain%20Architecture.md) §6). Performance does not own, move, or duplicate their concepts. It may consume a specific relevant item from either as [Performance Evidence](PerformanceEvidence.md) — for example, a customer explicitly naming an employee, or review text describing specific service behavior — without importing the rest of that Domain's record or redefining what Customer Feedback or Review are. See "Cross-Domain evidence" in [PerformanceEvidence.md](PerformanceEvidence.md).

---

## KPI / indicator principle

Performance does not canonize permanent KPIs for any role. Which [Performance Measures](PerformanceMeasure.md) currently function as [Performance Indicators](PerformanceIndicator.md) is derived from Goal, Brand, role, technical Domain, available Evidence, and the observed relationship with Outcomes — not from a hard-coded table (see [../../Domain Architecture.md](../../Domain%20Architecture.md) §8). RF-One may later learn that a previously relevant Indicator has little relationship with the desired Outcome, or that another Measure or Observation is more useful. **No KPI-discovery algorithm is defined by this module.**

---

## Canonical documents in this module

| Document | Defines |
|---|---|
| [Performance.md](Performance.md) | The central Performance concept: what a person actually produces in Reality within a role/context; relationship to expectations/Goals/Outcomes; uncertainty; temporal evolution; context dependence; what Performance is not. |
| [PerformanceEvidence.md](PerformanceEvidence.md) | Atomic, directly observed information used to reason about Performance; provenance, epistemic status, uncertainty, attribution limitations; direct observation vs. derived interpretation. |
| [PerformanceMeasure.md](PerformanceMeasure.md) | A value calculated or observed from Performance Evidence (e.g. a rate or ratio); not automatically a Key Performance Indicator; no globally prescribed formulas. |
| [PerformanceIndicator.md](PerformanceIndicator.md) | A Measure, Observation or signal currently considered relevant to evaluating Performance against a particular Goal/context; relevance is derived, not permanent; no universal scalar score; no KPI-discovery algorithm. |
| [PerformanceContext.md](PerformanceContext.md) | The contextual conditions required to interpret Performance Evidence and Measures fairly; comparison principle; no mandatory universal context schema; no normalization algorithm. |

---

## Restaurant as first validation

Restaurant examples (Server, Restaurant Manager) are used throughout these documents to validate that Performance concepts are genuinely reusable — not to define Performance around Restaurant. No Restaurant-specific Performance file is created by this module, and none of this knowledge is moved into `01 Domains/Restaurant/`.

**Update (TASK_SERVER_PERFORMANCE_001):** the Restaurant Domain now has a genuine, populated specialization for the Server role — `01 Domains/Restaurant/Server Performance/` (with the closely related `Service Copilot/` and `Dining Intelligence/` sibling modules). It supplies Restaurant-specific technical content (Quality of Sale, Opportunity Capture, Concurrent Service Load, KPI families) into this module's reasoning structure (Evidence/Measure/Indicator/Context) — it does not redefine or duplicate any concept documented here. See `Server Performance/README.md`, "Naming and boundary," for the exact relationship.

---

## Distinction from Product/Runtime

This module defines business knowledge only. It does not define, and this task does not create:

- POS or integration-specific schemas (e.g. Clover);
- any UI or dashboard;
- any KPI-discovery, scoring, or normalization algorithm;
- persistence schemas, database fields, or automation logic.

Those are Product/Runtime concerns, to be designed later on top of this module if and when a commercial capability requires them.

---

## Deferred

Detailed modeling of Workforce, Training and Personnel Decisions remains deferred to future tasks (see their own module READMEs). Within Performance itself, deferred items include: how Performance Evidence is actually captured or ingested from a specific technical Domain or integration; any concrete normalization method for cross-context comparison; and any KPI-discovery mechanism. See `07 Tasks/Reports/TASK_PERSONNEL_001_REPORT.md` for the full list of open questions.
