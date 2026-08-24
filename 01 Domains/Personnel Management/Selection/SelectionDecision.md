# Selection Decision

**Version:** 0.1
**Status:** Draft (initial canonical foundation)
**Module:** Domain / Selection

---

## Purpose

A **Selection Decision** is the Selection-specific application/context of the Core [Decision](../../../00%20Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md) concept: the act of choosing, given a role/context, applicable [Selection Requirements](SelectionRequirement.md), available [Candidate Evidence](CandidateEvidence.md), a [Fit Assessment](FitAssessment.md), Reality and authority.

**This document does not redefine Core Decision.** A Selection Decision is not, by virtue of being a Decision, automatically an Entity or automatically persisted — see [../../../00 Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md](../../../00%20Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md), section 2.1. Whether and how a specific Selection Decision is persisted as a Decision Record is a Runtime concern, not defined here.

---

## Possible conclusions

A Selection Decision may conclude, for example:

- **proceed** — select the candidate for the role/context;
- **do not proceed** — do not select the candidate;
- **gather more Evidence** — the current Fit Assessment does not yet support a confident conclusion;
- **compare with additional candidates** — evaluate other candidates before concluding;
- **proceed conditionally** — proceed subject to a specific condition being met (e.g. a trial shift, a reference check, closing a specific Trainable Gap before a start date);
- **select with known Trainable Gaps** — proceed while explicitly carrying forward one or more identified [Trainable Gaps](TrainableGap.md) as a known, accepted condition of the hire.

This list is illustrative, not exhaustive or mandatory.

---

## What a Selection Decision must preserve

A Selection Decision should preserve:

- the **candidate/context** it concerns;
- the **Selection Requirements** actually relevant to it;
- the **Candidate Evidence** it was based on;
- the **Fit Assessment** it drew on;
- the **uncertainty** present at the time of Decision;
- the **Constraints** in force;
- the **trade-offs** considered (e.g. between candidates, or between dimensions of Fit);
- the **rationale** for the conclusion reached;
- the **Decision authority** — who had, and who exercised, the authority to make this Decision;
- the **expected Outcomes** — what the Decision-maker expects to happen as a result.

This is what allows a Selection Decision to participate meaningfully in the Core's Decision → Action → Outcome → Learning cycle later (see [../../../00 Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md](../../../00%20Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md)) rather than being an opaque, unexplainable outcome.

---

## Subject Sovereignty and authority

A Selection Decision is made by, or on behalf of, whoever holds the relevant hiring authority for the organization — a Subject, or an actor operating under that Subject's [Delegated Authority](../../../00%20Core/ConceptualArchitecture/06_Business_Autopilot_and_Intelligence_Engine.md). RF-One's Selection reasoning may inform, challenge, or recommend, but it must not substitute itself for that authority — see [../../../00 Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md](../../../00%20Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md).

Where authority itself is unclear — for example, when it is not clear who is entitled to approve a hire, or under what spending/authority threshold — that ambiguity is itself something Selection should surface, not silently resolve on its own. (See the ownership/authority pattern in `08 External/Shelbi/Management Team - Diagnosis and Meeting Plan.pdf`: an unclear boundary of ownership or authority is a structural gap to name and close, not a personal failing to diagnose.)

---

## Persistence is a Runtime concern

This document defines the Selection-specific *meaning* of a Selection Decision. It does not define:

- a Decision Record schema;
- database fields;
- a workflow or UI for capturing the Decision;
- retention or audit mechanisms.

Those belong to Product/Runtime design, consistent with [../../../00 Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md](../../../00%20Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md), section 2.2 ("Decision Record").

---

## Restaurant example (illustrative only)

```text
Candidate/context:     Kitchen Manager, Mount Dora
Requirements:          Independent dinner-service capability (mandatory);
                       food cost discipline (mandatory);
                       wine-service technique (trainable)
Evidence:              5 years comparable kitchen management, verified reference;
                       one observed instance of taking ownership under ambiguous
                       authority; no trial shift performed yet
Fit Assessment:        Technical Fit strong; Behavioral Fit uncertain;
                       Trainability high on wine service
Uncertainty:           Behavioral Fit under this organization's actual
                       escalation structure is not yet evidenced
Constraints:           Start date within 3 weeks (Mount Dora opening)
Trade-offs:            Only candidate currently evaluated within the timeline
Rationale:             Technical strength and clean reference outweigh an
                       unverified behavioral uncertainty, given a trial shift
                       can close that uncertainty before the opening
Authority:             General Manager, within delegated hiring authority
                       for this role
Expected Outcome:      Independent dinner-service capability confirmed via
                       trial shift; wine-service technique reaches standard
                       within 30 days of onboarding

Conclusion:            Proceed conditionally — subject to a trial shift
                       confirming Behavioral Fit before the Mount Dora opening
```

---

## Related concepts

- [Selection.md](Selection.md)
- [SelectionRequirement.md](SelectionRequirement.md)
- [CandidateEvidence.md](CandidateEvidence.md)
- [FitAssessment.md](FitAssessment.md)
- [TrainableGap.md](TrainableGap.md)
- [../../../00 Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md](../../../00%20Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md)
- [../../../00 Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md](../../../00%20Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md)
