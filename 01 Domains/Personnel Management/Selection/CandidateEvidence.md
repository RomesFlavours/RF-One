# Candidate Evidence

**Version:** 0.1
**Status:** Draft (initial canonical foundation)
**Module:** Domain / Selection

---

## Purpose

**Candidate Evidence** is information relevant to evaluating a candidate against one or more [Selection Requirements](SelectionRequirement.md).

Candidate Evidence is a Selection-specific application of the Core's [Evidence](../../../00%20Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md) concept: information that supports, without necessarily proving, a Fact, Belief or Hypothesis about a candidate.

---

## Possible sources

Candidate Evidence may come from, among others:

- résumé/CV;
- application materials;
- work history;
- structured interview;
- reference;
- work sample or trial (e.g. a trial shift);
- assessment;
- certification;
- observed behavior;
- prior Outcome/performance data, only where legally and ethically permissible;
- information the candidate provides directly.

This list is illustrative. Selection does not define how any of these sources are captured, scraped, or ingested — see "Candidate-source boundary" below.

---

## What every Candidate Evidence item must conceptually preserve

Regardless of source, every Candidate Evidence item should preserve:

- **source** — where it came from;
- **provenance** — how it was obtained and by whom;
- **time/context** — when it was observed or stated, and under what circumstances;
- **what was actually observed or stated** — the underlying Observation, kept separate from any interpretation of it;
- **uncertainty** — how confident the Evidence should be treated as being;
- **epistemic status** — whether it is being treated as Fact, Observation, Evidence, Belief, Assumption, Inference, or Hypothesis (see [../../../00 Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md](../../../00%20Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md)).

This Domain does not prescribe a database schema or field list for these properties. It requires that they be conceptually preserved, not that they take any particular technical form.

---

## Absence of evidence is not evidence of absence

> A missing observation, an unanswered reference check, or a résumé that does not mention a skill is **not**, by itself, Evidence that the candidate lacks that skill.

Selection must represent a missing observation as an **Unknown**, not silently convert it into a negative Fact about the candidate. This is a direct application of the Core's Epistemic Boundary principle that "I do not know" must never silently become "it cannot be" — see [../../../00 Core/ConceptualArchitecture/02_Desire_Goal_and_Reality_Check.md](../../../00%20Core/ConceptualArchitecture/02_Desire_Goal_and_Reality_Check.md), section 1, and [../../../00 Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md](../../../00%20Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md).

An Unknown about a Requirement may itself be materially important — it may mean more Evidence must be gathered before a [Selection Decision](SelectionDecision.md) is made — but it is not itself disqualifying.

---

## Interpretation must not silently become Fact

Two Evidence items with the same underlying Observation can support very different interpretations. Selection must keep interpretation visibly separate from what was actually observed or stated:

```text
Observation:  "Candidate ran the kitchen alone for one dinner service during the trial."
Inference:    "Candidate can likely run dinner service independently on an ongoing basis."
Hypothesis:   "Candidate would perform the same way under a busier Friday service."
```

The Inference and the Hypothesis are reasonable next steps, but neither is a Fact, and Selection must not present them as one when forming a [Fit Assessment](FitAssessment.md).

---

## Candidate-source boundary

Selection does not own candidate acquisition platforms and does not define how Candidate Evidence is captured or ingested. This document does not, and this Domain must not, define connectors or source-specific handling for Indeed, LinkedIn, ZipRecruiter, ATS systems, recruiting agencies, career sites, or any other candidate-source platform. Those belong to future Product/Runtime/integration architecture.

Selection only needs to know that a given Candidate Evidence item **has** a source and provenance — not what that source's ingestion mechanism looks like.

---

## What Candidate Evidence is not

- It is not a Selection Requirement.
- It is not a Fit Assessment.
- It is not automatically a Fact merely because it was recorded.
- It is not a personality label or psychological diagnosis — an observed behavior is Evidence about that specific behavior in that specific context, not a general trait claim about the person. See the Restaurant example below.
- It must not encode or allow inference of protected/sensitive attributes.

---

## Restaurant example (illustrative only, and translated from provenance rather than judgment)

Real management situations (see `08 External/Shelbi/Management Team - Diagnosis and Meeting Plan.pdf`) often surface exactly this distinction. A manager who becomes visibly territorial about a facilities decision is not thereby evidenced to have a fixed personality trait; the same source material suggests the behavior may be evidence of **unclear ownership**, not of the person's disposition:

```text
Observation:   "Manager pushed back sharply when asked to share ownership of an
                undefined facilities responsibility."
Candidate Evidence (correctly scoped): "Under conditions of unclear ownership,
                this person has been observed to assert control rather than
                escalate or ask for clarification."
Not Evidence of: a fixed personality trait, or a general inability to collaborate.
```

Kept this way, the Evidence remains usable: it is directly relevant to a [Selection Requirement](SelectionRequirement.md) about role clarity and escalation behavior, and it may point toward a [Trainable Gap](TrainableGap.md) (e.g. escalation habits under ambiguous ownership) rather than a disqualifying trait. This is the boundary this Domain must preserve: translate an observation into reusable Selection semantics only when the translation is justified by what was actually observed, never into a canonical judgment about the specific individual.

---

## Related concepts

- [Selection.md](Selection.md)
- [SelectionRequirement.md](SelectionRequirement.md)
- [FitAssessment.md](FitAssessment.md)
- [TrainableGap.md](TrainableGap.md)
- [../../../00 Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md](../../../00%20Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md)
