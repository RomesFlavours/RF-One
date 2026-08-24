# Fit Assessment

**Version:** 0.1
**Status:** Draft (initial canonical foundation)
**Module:** Domain / Selection

---

## Purpose

A **Fit Assessment** is a contextual assessment of how well available [Candidate Evidence](CandidateEvidence.md) supports a candidate's suitability for a specific role/context, evaluated against the applicable [Selection Requirements](SelectionRequirement.md).

Fit is not a Fact. It is an Inference formed from available Evidence, under whatever uncertainty that Evidence carries — see [../../../00 Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md](../../../00%20Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md).

---

## Fit is not a single mandatory scalar score

**This Domain does not define a universal scalar score for Fit.** A single number collapses distinct, sometimes conflicting dimensions of suitability into one figure, hides which dimension is actually driving the assessment, and creates false precision about something that is genuinely uncertain. A Product or Runtime may choose to summarize a Fit Assessment numerically for its own purposes, but that summarization is not part of what this Domain defines, and it must not replace the underlying multidimensional assessment.

---

## Possible dimensions (illustrative, not mandatory)

A Fit Assessment may consider dimensions such as:

- **Role Fit** — alignment with the specific responsibilities of the role;
- **Technical Fit** — alignment with the target Domain's technical requirements (e.g. Restaurant Domain requirements for a Kitchen Manager);
- **Behavioral Fit** — alignment with required operational behaviors (e.g. ownership, escalation, cooperation under pressure);
- **Brand / Service Model Fit** — alignment with Brand-derived expectations, where a genuine Requirement traces to Brand;
- **Availability Fit** — alignment with schedule/location Requirements;
- **Constraint Fit** — compatibility with binding Constraints (budgetary, legal, operational);
- **Team-context Fit** — alignment with the specific team/context the role sits within;
- **Trainability / Growth Potential** — how reasonably any current gaps could be closed (see [TrainableGap.md](TrainableGap.md));
- **Risk** — material risks the Evidence surfaces, whatever their source.

**These are possible dimensions, not mandatory universal fields.** A Fit Assessment should use only the dimensions that the applicable Requirements and available Evidence actually justify for the role/context in question — not populate every dimension by default.

---

## What a Fit Assessment must expose

Every Fit Assessment must make visible:

- **supporting Evidence** — what backs a positive judgment on a given dimension;
- **contradicting Evidence** — what pushes against it, rather than being suppressed;
- **missing Evidence** — which relevant Requirements have no Evidence yet (an Unknown, not a negative Fact — see [CandidateEvidence.md](CandidateEvidence.md));
- **assumptions** — anything taken as true without verification, and labeled as such;
- **uncertainty** — how confident the assessment is, and why;
- **material risks** — anything that could materially affect the Outcome if the assessment turns out to be wrong.

A Fit Assessment that hides any of the above is incomplete, regardless of how confident its overall impression appears.

---

## Safeguards

- Fit Assessment must not infer protected or sensitive attributes (e.g. age, disability, family status, national origin) from Evidence, even indirectly.
- Fit Assessment must not introduce personality pseudoscience — unvalidated typologies, trait tests, or psychological labeling presented as objective measurement.
- Fit Assessment must keep Inference visibly separate from the underlying Observation it was drawn from (see [CandidateEvidence.md](CandidateEvidence.md)).
- A high Fit Assessment on one dimension must never silently substitute for, or hide a gap on, another dimension a Requirement actually depends on.

---

## What a Fit Assessment is not

- It is not a Fact about the candidate.
- It is not the [Selection Decision](SelectionDecision.md) — it informs that Decision but does not make it.
- It is not a personality profile.
- It is not automatically transferable between roles/contexts: a Fit Assessment is scoped to the specific role/context it was made for, because the underlying Requirements are context-specific (see [SelectionRequirement.md](SelectionRequirement.md)).

---

## Restaurant example (illustrative only)

```text
Role: Kitchen Manager, Mount Dora

Dimension              Assessment                          Basis
Technical Fit          Strong                               Five years running a
                                                             comparable kitchen;
                                                             verified reference
Behavioral Fit         Uncertain                            One observed instance of
                                                             taking ownership under
                                                             ambiguous authority; no
                                                             evidence yet under this
                                                             organization's actual
                                                             escalation structure
Brand/Service Fit      No conflict identified               No Evidence gathered
                                                             specifically against this
                                                             dimension — Unknown, not
                                                             confirmed
Trainability           High, on wine-service technique       Gap is procedural, not
                                                             attitudinal — see
                                                             TrainableGap.md
Risk                   Moderate                              Behavioral Fit uncertainty
                                                             plus no trial shift yet
                                                             performed
```

The same structure applies to any other role or industry; only the dimensions actually populated, and their content, change.

---

## Related concepts

- [Selection.md](Selection.md)
- [SelectionRequirement.md](SelectionRequirement.md)
- [CandidateEvidence.md](CandidateEvidence.md)
- [SelectionDecision.md](SelectionDecision.md)
- [TrainableGap.md](TrainableGap.md)
