# Selection

**Version:** 0.1
**Status:** Draft (initial canonical foundation)
**Module:** Domain / Selection

---

## Purpose

**Selection** is the business activity, and the reasoning process, of determining the most appropriate candidate for a defined role/context, given an organization's Goals, Brand expectations, operational and technical requirements, Constraints, available Evidence, uncertainty and risk.

Selection is a Domain-level specialization of how RF-One reasons toward a [Decision](../../../00%20Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md) within the Core's Subject ↔ Reality relationship: the Subject (the organization, or whoever holds delegated hiring authority within it) must choose, under partial knowledge of Reality (the candidates, the role, the organization), whom to select.

---

## What Selection is not

Selection is not primarily:

- CV keyword matching;
- résumé scoring;
- personality typing;
- an ATS;
- a job board;
- an interview UI;
- a recruiting workflow product.

These may become Product/Runtime capabilities layered on top of this Domain. They are not what Selection *is*.

Selection does not imply that the candidate with the highest apparent qualification is automatically the best decision. Apparent qualification is one input among several; role requirements, behaviors, technical capability, trainability, time to standard, risk, availability, Constraints, expected performance and the quality of available Evidence all inform the reasoning — see the dimensions below.

---

## Inputs

A Selection reasoning process draws on:

- **[Selection Requirements](SelectionRequirement.md)** — what the role/context actually requires, and why;
- **[Candidate Evidence](CandidateEvidence.md)** — what is actually known, with its provenance and epistemic status;
- the organization's Goals and Brand expectations, where genuinely relevant to the role;
- the target technical Domain's own requirements for the role (e.g. Restaurant's requirements for a Kitchen Manager — see [../../Restaurant/](../../Restaurant/));
- Constraints (legal, budgetary, scheduling, or otherwise);
- known Unknowns — what relevant information is simply not yet available.

Selection does not own or define any of these inputs beyond its own reasoning over them; it consumes them from Core, from the relevant technical Domain, and from Candidate Evidence.

---

## Evaluation

Selection evaluates available Evidence against Requirements to produce a [Fit Assessment](FitAssessment.md) — a contextual, multidimensional judgment of suitability, not a single scalar score and not a Fact.

Selection may also identify [Trainable Gaps](TrainableGap.md): differences between current candidate capability and the desired standard that could reasonably be closed through training, practice, onboarding or experience, as distinct from hard Constraints or disqualifying incompatibilities.

---

## Uncertainty

Selection routinely operates under incomplete knowledge. It must maintain the [Epistemic Boundary](../../../00%20Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md) throughout:

- an Inference about a candidate (e.g. "likely trainable to standard within 60 days") must never be silently presented as a Fact;
- an absence of Evidence about some Requirement must never be silently treated as evidence that the candidate fails it — **absence of evidence is not evidence of absence**, see [CandidateEvidence.md](CandidateEvidence.md);
- material Unknowns must be surfaced explicitly, not omitted.

---

## Relationship to Decision

Selection culminates in, or supports, a [Selection Decision](SelectionDecision.md) — the Selection-specific application of the Core `Decision` concept. Selection itself is the reasoning that leads to that Decision; it does not replace Subject Sovereignty over the final choice, and it does not by itself constitute the Decision. See [../../../00 Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md](../../../00%20Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md).

---

## Outcomes and feedback/learning

What happens after a Selection Decision — hire or assignment, Training, observed performance, Outcome — is future feedback this Domain is designed to remain compatible with, without this task defining Training or Performance as Domains:

```text
Selection assumptions / predictions
  → hire or assignment
    → Training
      → observed Performance
        → Outcome
          → Learning
            → better future Selection
```

See [../../../00 Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md](../../../00%20Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md) for the Core's general Decision → Action → Outcome → Learning cycle, which Selection Decisions participate in like any other Decision.

---

## Restaurant example (illustrative only)

```text
Kitchen Manager, Mount Dora
  → technical requirements from Restaurant Domain
      (e.g. food cost discipline, ability to run dinner service, purchasing judgment)
  → required operational behaviors
      (e.g. clear ownership of kitchen decisions, calm escalation under pressure)
  → Candidate Evidence
      (work history, structured interview, a trial shift)
  → Fit Assessment
      (Technical Fit strong; Behavioral Fit uncertain pending trial shift; no Brand conflict identified)
  → Selection Decision
      (proceed conditionally on the trial shift; owner: General Manager)
```

The same reasoning structure — Requirements, Evidence, Fit Assessment, Decision — applies unchanged to a Server, a General Manager, or a role in an entirely different industry; only the technical and behavioral content of the Requirements changes.

---

## Related concepts

- [SelectionRequirement.md](SelectionRequirement.md)
- [CandidateEvidence.md](CandidateEvidence.md)
- [FitAssessment.md](FitAssessment.md)
- [SelectionDecision.md](SelectionDecision.md)
- [TrainableGap.md](TrainableGap.md)
- [../../../00 Core/Goal.md](../../../00%20Core/Goal.md)
- [../../../00 Core/Brand.md](../../../00%20Core/Brand.md)
