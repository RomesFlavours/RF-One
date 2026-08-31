# Selection Module

**Version:** 0.2
**Status:** Draft (initial canonical foundation; terminology reconciled by TASK_REPOSITORY_STABILIZATION_001 — Selection is a module of the Personnel Management Domain, not a Domain in its own right, per `../../Domain Architecture.md` §4-5)
**Module:** Domain / Personnel Management / Selection

---

## Purpose

The Selection module provides the reusable knowledge and reasoning structure that allows RF-One to make or support a **Selection Decision**: determining which candidate is the best decision for a given role/context, in a given organization, under its Goals, Brand expectations, operational requirements, technical requirements, Constraints, available Evidence, uncertainty and risk.

Selection is **not** primarily:

- CV keyword matching;
- résumé scoring;
- personality typing;
- an ATS (Applicant Tracking System);
- a job board;
- an interview UI;
- a recruiting workflow product.

Those may become Product/Runtime capabilities built around this module. This module defines the underlying business knowledge, independently of any software that implements it.

---

## Universal scope

Selection is a **universal, cross-industry module** of the transversal Personnel Management Domain (see [../README.md](../README.md) and [../../Domain Architecture.md](../../Domain%20Architecture.md)). It applies wherever an organization must evaluate candidates against role/context requirements and decide whom to select — regardless of industry, role, or the specific technical knowledge involved.

**Restaurant is the first concrete application context, not the architectural owner of this module.** Nothing in Selection may assume a restaurant, a kitchen, a dining room, or any other Restaurant-specific concept. Where this module uses Restaurant examples (see "Restaurant as first application" below), those examples exist to validate universality, not to define it.

Any other technical Domain/module that requires evaluating and selecting candidates — Restaurant/Purchasing (selecting a supplier's account manager), Restaurant/Sales, a future professional-services Domain, or an entirely different industry — reuses the same Selection concepts, feeding them its own technical/business requirements instead of Restaurant's.

---

## Relationship to Core 2.0

Selection is built on the RF-One Core Conceptual Architecture (Core 2.0) and reuses its concepts without redefining them:

- **Subject** — the organization (or the person acting with delegated authority within it) making the Selection Decision. See [../../../00 Core/ConceptualArchitecture/01_Subject_and_Reality.md](../../../00%20Core/ConceptualArchitecture/01_Subject_and_Reality.md).
- **Reality** — everything actually true about the candidate, the role and the organization, only ever partially known. See the same document.
- **Goal** — the confirmed business objective a hire is meant to serve (e.g. "Mount Dora needs a Kitchen Manager capable of running dinner service independently within 60 days"). See [../../../00 Core/ConceptualArchitecture/02_Desire_Goal_and_Reality_Check.md](../../../00%20Core/ConceptualArchitecture/02_Desire_Goal_and_Reality_Check.md) and [../../../00 Core/Goal.md](../../../00%20Core/Goal.md).
- **Decision, Action, Outcome, Learning** — the operational cycle a Selection Decision participates in. See [../../../00 Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md](../../../00%20Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md).
- **Epistemic Boundary** (Fact, Observation, Evidence, Belief, Assumption, Inference, Hypothesis, Unknown) and **Subject Sovereignty** — govern how Candidate Evidence and Fit Assessment must be handled, and who retains final Decision authority. See [../../../00 Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md](../../../00%20Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md).
- **Constraint, Relationship, Ownership, Assignment** — see [../../../00 Core/Relationship.md](../../../00%20Core/Relationship.md) and [../../../00 Core/Glossary.md](../../../00%20Core/Glossary.md).

This module does not redefine any of these concepts. It specializes them into the Selection-specific documents listed below only where a genuine Selection-specific meaning is required.

---

## Relationship to Brand

A hiring need does not originate from Brand alone, but Brand is one of its upstream sources. The general direction is:

```text
Goals
  → Brand
    → Service Model
      → Behaviors
        → Role / Context Requirements
          → Technical Domain Requirements
            → Candidate Evidence
              → Fit Assessment
                → Selection Decision
                  → Training / Performance feedback
```

Brand (see [../../../00 Core/Brand.md](../../../00%20Core/Brand.md)) contributes expectations about customer experience, service standards and product philosophy that may shape which behaviors a role requires. It does **not** by itself determine who is hired, and it must never be converted into a personality test. Selection must integrate Brand expectations together with technical requirements, role responsibilities, Constraints, law/policy, available Evidence, trainable gaps, risk and expected Outcomes — see [Selection.md](Selection.md).

If an organization's Brand has not yet been defined in writing, any Selection Requirement claimed to derive from Brand is an **Assumption**, not a Fact, until the Brand itself is confirmed — see [SelectionRequirement.md](SelectionRequirement.md).

---

## Relationship to target technical Domains

Selection **consumes** knowledge from whatever Domain the role belongs to; it does not duplicate that Domain's knowledge.

```text
Restaurant Domain
  → technical requirements for Kitchen Manager
      (food cost discipline, kitchen process, service sequence — see 01 Domains/Restaurant/)

Selection module (Personnel Management)
  → evaluates whether a candidate satisfies those requirements
```

Selection must not redefine Restaurant knowledge such as food cost, kitchen process, service sequence, purchasing, menu, or restaurant operations — that knowledge stays canonical under [../../Restaurant/](../../Restaurant/). In another industry, Selection consumes that industry's own Domain knowledge in the same way.

---

## Future Workforce dependency

Selection will likely depend on future reusable Workforce/People semantics that do not yet exist in depth — the Workforce module (`../Workforce/`, a module of Personnel Management, not a Domain of its own) is currently only a placeholder — for example Person/Worker, Role, Position, Assignment, Responsibility, Availability, Schedule, Skill, Capability, Employment Relationship. See [../../Restaurant/Roadmap.md](../../Restaurant/Roadmap.md), section 3, "Workforce / Personnel," for the currently approved sequencing note.

**No detailed Workforce module content is created by this task.** Where a Selection document needs one of these concepts, it references it as an external dependency and defines only the Selection-specific relationship to it, without defining the concept itself.

---

## Distinction from Product/Runtime

This module defines business knowledge only. It does not define, and this task does not create:

- an ATS or recruiting workflow;
- an interview or evaluation UI;
- scraping or ingestion of candidate platforms;
- integrations with Indeed, LinkedIn, ZipRecruiter, or any other candidate-source or ATS platform;
- persistence schemas, database fields, or automation logic.

Those are Product/Runtime concerns, to be designed later on top of this module if and when a commercial capability requires them.

> **Selection does not own the candidate source.**
> Candidates may come from ATSs, job boards, referrals, internal talent pools, direct applications, external recruiting systems, or other authorized sources. Selection only needs to know that each piece of Candidate Evidence has a source and provenance — see [CandidateEvidence.md](CandidateEvidence.md).

---

## Canonical documents in this module

| Document | Defines |
|---|---|
| [Selection.md](Selection.md) | The central Selection concept: the reasoning process of determining the most appropriate candidate for a role/context. |
| [SelectionRequirement.md](SelectionRequirement.md) | A requirement relevant to selecting a candidate for a particular role/context, and its sources. |
| [CandidateEvidence.md](CandidateEvidence.md) | Information relevant to evaluating a candidate against Selection Requirements, with provenance and epistemic status preserved. |
| [FitAssessment.md](FitAssessment.md) | A contextual, multidimensional assessment of how well available Evidence supports a candidate's suitability — not a Fact, not a mandatory single score. |
| [SelectionDecision.md](SelectionDecision.md) | The Selection-specific application of the Core `Decision` concept. |
| [TrainableGap.md](TrainableGap.md) | A gap between current candidate capability and the desired standard that may reasonably be addressed through learning, training, practice, onboarding or experience. |

---

## Restaurant as first application

Restaurant examples (Restaurant Manager, General Manager, Kitchen Manager, Server) are used throughout these documents to validate that Selection concepts are genuinely reusable — not to define Selection around Restaurant. No Restaurant-specific Selection file is created by this task, and none of this knowledge is moved into `01 Domains/Restaurant/`.

---

## Relationship to future Training and Performance

Selection is designed so that it can later learn from what happens after a Decision:

```text
Selection assumptions / predictions
  → hire or assignment
    → Training
      → observed Performance
        → Outcome
          → Learning
            → better future Selection
```

**No Training module content is created by this task.** (The Performance module is now documented in depth by a later task, TASK_PERSONNEL_001 — see [../Performance/README.md](../Performance/README.md); it was still undocumented when this Selection module was first written.) Selection's definitions only need to remain compatible with this future feedback loop — see [TrainableGap.md](TrainableGap.md) for where the Selection/Training boundary is drawn today.

---

## Legal / fairness / governance safeguards

At minimum, every document in this module preserves:

- only job-relevant criteria may influence Selection;
- sensitive/protected attributes must not be inferred or used improperly;
- Evidence provenance must remain visible;
- Inference must not be silently promoted to Fact;
- uncertainty must remain explicit;
- the authority behind a Selection Decision must be known;
- jurisdiction-specific legal/policy rules are external Constraints, not something this module defines;
- retention/privacy mechanisms belong to future Product/Runtime governance.

This module does not attempt to define employment law.
