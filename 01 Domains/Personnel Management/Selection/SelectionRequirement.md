# Selection Requirement

**Version:** 0.1
**Status:** Draft (initial canonical foundation)
**Module:** Domain / Selection

---

## Purpose

A **Selection Requirement** is a requirement relevant to selecting a candidate for a particular role/context.

A Selection Requirement is not itself Evidence, and it is not a judgment about any candidate. It states what the role/context needs; whether a given candidate satisfies it is a separate question — see [CandidateEvidence.md](CandidateEvidence.md) and [FitAssessment.md](FitAssessment.md).

---

## Requirement ≠ Evidence

```text
Selection Requirement                    Candidate Evidence
"what the role/context needs"      ≠     "what is known about this candidate"
```

A Requirement can exist and be fully defined with zero candidates evaluated against it. Conflating the two — treating the statement of a requirement as if it were already a judgment about a person — is a common source of unfair or unreliable Selection and must be avoided.

---

## Sources of a Selection Requirement

A Selection Requirement may originate from:

- **Brand** (see [../../../00 Core/Brand.md](../../../00%20Core/Brand.md)) — e.g. a service standard the Brand commits to;
- **Service Model** — how the organization actually delivers on the Brand's promise operationally;
- **Process** (see [../../../00 Core/Process.md](../../../00%20Core/Process.md)) — a Process may require specific capability from whoever executes it;
- **role responsibilities** — what the role is actually accountable for;
- **target Domain technical knowledge** — e.g. Restaurant Domain knowledge for a Kitchen Manager role (see [../../Restaurant/](../../Restaurant/));
- **Constraints** — budgetary, scheduling, or operational;
- **law/policy** — jurisdiction-specific requirements, treated as external Constraints (see "Legal / fairness" in [README.md](README.md));
- **availability** — schedule or location requirements the role genuinely needs;
- **business Goals** (see [../../../00 Core/Goal.md](../../../00%20Core/Goal.md)) — where a Goal materially shapes what the role must be capable of.

Every Selection Requirement should be traceable to at least one of these sources. A Requirement with no traceable source is an unexamined assumption, not a Requirement, and should be treated as such until its source is identified.

### Brand-derived requirements and the epistemic boundary

If a requirement is claimed to derive from Brand, but the Brand itself has not yet been defined in writing for the organization in question, that requirement is an **Assumption** (see [../../../00 Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md](../../../00%20Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md)), not a confirmed Requirement, until the Brand is confirmed. Selection must not silently promote an assumed Brand expectation into a stated Requirement.

---

## Requirement nature

Where useful, a Requirement's nature may be classified, for example as:

- **mandatory** — the role/context cannot function without it;
- **strong preference** — materially improves fit but is not disqualifying alone;
- **trainable** — a current gap here may reasonably be closed after selection (see [TrainableGap.md](TrainableGap.md));
- **contextual** — depends on the specific role/context, location, or team rather than being universal to the role class;
- **prohibitive** — its absence, or a specific condition, disqualifies the candidate for this role/context.

**This classification is illustrative, not a rigid universal enum.** A Domain, Product or Runtime should classify a given Requirement only when the underlying evidence and business judgment actually justify that classification — not by forcing every Requirement into one of these categories regardless of fit.

---

## What a Selection Requirement is not

- It is not Candidate Evidence.
- It is not a Fit Assessment.
- It is not a personality trait or psychological profile: Requirements describe what the role/context needs, not who a person "is."
- It is not a proxy for a protected or sensitive attribute — see "Legal / fairness / governance safeguards" in [README.md](README.md).

---

## Restaurant examples (illustrative only)

```text
Role: Kitchen Manager, Mount Dora

Requirement                                          Source                 Nature
Able to run dinner service independently             Role responsibility    Mandatory
Working knowledge of food cost discipline            Restaurant Domain      Mandatory
Wine service technique to house standard             Service Model          Trainable
                                                      (see 08 External/Shelbi/
                                                      Training-Content-Shot-List.pdf
                                                      for illustrative technique detail)
Evening/weekend availability                         Availability           Mandatory
Prior fine-dining experience                         —                      Strong preference
```

The same structure — Requirement, Source, Nature — applies to a Server role, a General Manager role, or a role in a different industry entirely; only the content changes.

---

## Related concepts

- [Selection.md](Selection.md)
- [CandidateEvidence.md](CandidateEvidence.md)
- [FitAssessment.md](FitAssessment.md)
- [TrainableGap.md](TrainableGap.md)
- [../../../00 Core/Brand.md](../../../00%20Core/Brand.md)
- [../../../00 Core/Process.md](../../../00%20Core/Process.md)
