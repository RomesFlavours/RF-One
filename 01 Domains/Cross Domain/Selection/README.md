# Selection Domain

**Version:** 0.3
**Status:** Draft (initial canonical foundation). Selection is a **top-level, transversal Domain**, a sibling of Restaurant, Personnel Management, Taxation and Administration — re-elevated from being a Personnel Management module by explicit Product Owner direction (TASK_DOMAINS_003), which supersedes TASK_DOMAINS_002's earlier consolidation of Selection into Personnel Management. See `../../Domain%20Architecture.md` §4-5 and `07 Tasks/Reports/TASK_DOMAINS_003_REPORT.md`.
**Domain:** Selection

---

## Purpose

The Selection Domain provides the reusable knowledge and reasoning structure that allows RF-One to make or support a **Selection Decision**: determining which candidate is the best decision for a given role/context, in a given organization, under its Goals, Brand expectations, operational requirements, technical requirements, Constraints, available Evidence, uncertainty and risk.

Selection is **not** primarily:

- CV keyword matching;
- résumé scoring;
- personality typing;
- an ATS (Applicant Tracking System);
- a job board;
- an interview UI;
- a recruiting workflow product.

Those may become Product/Runtime capabilities built around this Domain. This Domain defines the underlying business knowledge, independently of any software that implements it.

---

## Universal scope

Selection is a **universal, cross-industry, transversal Domain** (see [../README.md](../../README.md) and [../Domain Architecture.md](../../Domain%20Architecture.md)) — a sibling of Restaurant, Personnel Management, Taxation and Administration, not a module of any of them. It applies wherever an organization must evaluate candidates against role/context requirements and decide whom to select — regardless of industry, role, or the specific technical knowledge involved.

**Restaurant is the first concrete application context, not the architectural owner of this Domain.** Nothing in Selection Core may assume a restaurant, a kitchen, a dining room, or any other Restaurant-specific concept, and Selection Core has no structural dependency on the Restaurant Domain — the dependency runs the other way: Restaurant's own Industry Extension of Selection (`01 Domains/Business Domain/Restaurant/Selection/`) depends on and extends Selection Core, never the reverse. Where this Domain uses Restaurant examples (see "Restaurant as first application" below), those examples exist to validate universality, not to define it.

Any other Domain/module that requires evaluating and selecting candidates — Restaurant/Purchasing (selecting a supplier's account manager), Restaurant/Sales, a future professional-services Domain, or an entirely different industry — reuses the same Selection concepts, feeding them its own technical/business requirements instead of Restaurant's.

Selection is closely related to Personnel Management (whose remaining modules are Workforce and Personnel Decisions — see `../Personnel%20Management/README.md`) and to the sibling Continuous Productivity Development and Performance Cross Domains, without being subordinate to any of them: it is Personnel Management's most natural collaborator, not its subordinate. See `../../Domain%20Architecture.md` §4-5 for how Selection, Continuous Productivity Development and Performance relate to Personnel Management now that all three stand on their own.

---

## Relationship to Core 2.0

Selection is built on the RF-One Core Conceptual Architecture (Core 2.0) and reuses its concepts without redefining them:

- **Subject** — the organization (or the person acting with delegated authority within it) making the Selection Decision. See [../../00 Core/ConceptualArchitecture/01_Subject_and_Reality.md](../../../00%20Core/ConceptualArchitecture/01_Subject_and_Reality.md).
- **Reality** — everything actually true about the candidate, the role and the organization, only ever partially known. See the same document.
- **Goal** — the confirmed business objective a hire is meant to serve (e.g. "Mount Dora needs a Kitchen Manager capable of running dinner service independently within 60 days"). See [../../00 Core/ConceptualArchitecture/02_Desire_Goal_and_Reality_Check.md](../../../00%20Core/ConceptualArchitecture/02_Desire_Goal_and_Reality_Check.md) and [../../00 Core/Goal.md](../../../00%20Core/Goal.md).
- **Decision, Action, Outcome, Learning** — the operational cycle a Selection Decision participates in. See [../../00 Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md](../../../00%20Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md).
- **Epistemic Boundary** (Fact, Observation, Evidence, Belief, Assumption, Inference, Hypothesis, Unknown) and **Subject Sovereignty** — govern how Candidate Evidence and Fit Assessment must be handled, and who retains final Decision authority. See [../../00 Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md](../../../00%20Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md).
- **Constraint, Relationship, Ownership, Assignment** — see [../../00 Core/Relationship.md](../../../00%20Core/Relationship.md) and [../../00 Core/Glossary.md](../../../00%20Core/Glossary.md).

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
                  → Continuous Productivity Development / Performance feedback
```

Brand (see [../../00 Core/Brand.md](../../../00%20Core/Brand.md)) contributes expectations about customer experience, service standards and product philosophy that may shape which behaviors a role requires. It does **not** by itself determine who is hired, and it must never be converted into a personality test. Selection must integrate Brand expectations together with technical requirements, role responsibilities, Constraints, law/policy, available Evidence, trainable gaps, risk and expected Outcomes — see [Selection.md](Selection.md).

If an organization's Brand has not yet been defined in writing, any Selection Requirement claimed to derive from Brand is an **Assumption**, not a Fact, until the Brand itself is confirmed — see [SelectionRequirement.md](SelectionRequirement.md).

---

## Relationship to target technical Domains

Selection **consumes** knowledge from whatever Domain the role belongs to; it does not duplicate that Domain's knowledge.

```text
Restaurant Domain
  → technical requirements for Kitchen Manager
      (food cost discipline, kitchen process, service sequence — see 01 Domains/Business Domain/Restaurant/)

Selection Domain
  → evaluates whether a candidate satisfies those requirements
```

Selection must not redefine Restaurant knowledge such as food cost, kitchen process, service sequence, purchasing, menu, or restaurant operations — that knowledge stays canonical under [../Restaurant/](../../Business%20Domain/Restaurant/). In another industry, Selection consumes that industry's own Domain knowledge in the same way.

---

## Future Workforce dependency

Selection will likely depend on future reusable Workforce/People semantics that do not yet exist in depth — the Workforce module (`../Personnel%20Management/Workforce/`, a module of Personnel Management, not a Domain of its own) is currently only a placeholder — for example Person/Worker, Role, Position, Assignment, Responsibility, Availability, Schedule, Skill, Capability, Employment Relationship. See [../Restaurant/Roadmap.md](../../Business%20Domain/Restaurant/Roadmap.md), section 3, "Workforce / Personnel," for the currently approved sequencing note.

**No detailed Workforce module content is created by this task.** Where a Selection document needs one of these concepts, it references it as an external dependency (a sibling Domain's module, not a parent) and defines only the Selection-specific relationship to it, without defining the concept itself.

---

## Distinction from Product/Runtime

This Domain defines business knowledge only. It does not define, and this task does not create:

- an ATS or recruiting workflow;
- an interview or evaluation UI;
- scraping or ingestion of candidate platforms;
- integrations with Indeed, LinkedIn, ZipRecruiter, or any other candidate-source or ATS platform;
- persistence schemas, database fields, or automation logic.

Those are Product/Runtime concerns, to be designed later on top of this Domain if and when a commercial capability requires them.

> **Selection does not own the candidate source.**
> Candidates may come from ATSs, job boards, referrals, internal talent pools, direct applications, external recruiting systems, or other authorized sources. Selection only needs to know that each piece of Candidate Evidence has a source and provenance — see [CandidateEvidence.md](CandidateEvidence.md).

---

## Canonical documents in this Domain

| Document | Defines |
|---|---|
| [Selection.md](Selection.md) | The central Selection concept: the reasoning process of determining the most appropriate candidate for a role/context. |
| [SelectionRequirement.md](SelectionRequirement.md) | A requirement relevant to selecting a candidate for a particular role/context, and its sources. |
| [CandidateEvidence.md](CandidateEvidence.md) | Information relevant to evaluating a candidate against Selection Requirements, with provenance and epistemic status preserved. |
| [FitAssessment.md](FitAssessment.md) | A contextual, multidimensional assessment of how well available Evidence supports a candidate's suitability — not a Fact, not a mandatory single score. |
| [SelectionDecision.md](SelectionDecision.md) | The Selection-specific application of the Core `Decision` concept. |
| [TrainableGap.md](TrainableGap.md) | A gap between current candidate capability and the desired standard that may reasonably be addressed through learning, training, practice, onboarding or experience. |

---

## Resume Screening — first concrete capability (TASK_SELECTION_001)

`ResumeScreening/` (this folder) documents Selection's first concrete, implemented capability: CV/résumé screening — the Evidence Model (Fact/Derived/Flag/Indicator), the Candidate CV Profile data shape, experience/trajectory analysis, the generic Role Model, and Flags/Indicators. See [ResumeScreening/README.md](ResumeScreening/README.md). Its Restaurant Industry Extension (role catalog, Rome's Flavours Server Role Configuration) lives under `01 Domains/Business Domain/Restaurant/Selection/`, consistent with "Restaurant as first application" below. The first Runtime implementation (a web MVP) lives at `03 Software/Selection/` and `03 Software/RF-One Data Store/rfone_data_store/selection/`.

---

## Restaurant as first application

Restaurant examples (Restaurant Manager, General Manager, Kitchen Manager, Server) are used throughout these documents to validate that Selection concepts are genuinely reusable — not to define Selection around Restaurant. No Restaurant-specific Selection file is created by this task, and none of this knowledge is moved into `01 Domains/Business Domain/Restaurant/`.

---

## Relationship to Continuous Productivity Development and Performance

Selection is designed so that it can later learn from what happens after a Decision:

```text
Selection assumptions / predictions
  → hire or assignment
    → Continuous Productivity Development (intervention, where economically justified)
      → observed Performance
        → Outcome
          → Learning
            → better future Selection
```

**No Continuous Productivity Development content is created by this task.** (Performance — a sibling Cross Domain, not a Personnel Management module — is now documented in depth by a later task, TASK_PERSONNEL_001; see [../Performance/README.md](../Performance/README.md); it was still undocumented when this Selection Domain was first written. Continuous Productivity Development itself — which conceptually superseded the former Training placeholder's scope — now has its own draft concept specification; see [../Continuous Productivity Development/README.md](../Continuous%20Productivity%20Development/README.md).) Selection's definitions only need to remain compatible with this feedback loop — see [TrainableGap.md](TrainableGap.md) for where the Selection/Continuous Productivity Development boundary is drawn today.

---

## Legal / fairness / governance safeguards

At minimum, every document in this Domain preserves:

- only job-relevant criteria may influence Selection;
- sensitive/protected attributes must not be inferred or used improperly;
- Evidence provenance must remain visible;
- Inference must not be silently promoted to Fact;
- uncertainty must remain explicit;
- the authority behind a Selection Decision must be known;
- jurisdiction-specific legal/policy rules are external Constraints, not something this Domain defines;
- retention/privacy mechanisms belong to future Product/Runtime governance.

This Domain does not attempt to define employment law.
