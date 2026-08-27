# Tax Evidence

**Version:** 0.1
**Status:** Draft (initial canonical foundation)
**Module:** Domain / Taxation

---

## Purpose

**Tax Evidence** is information supporting tax facts, treatments, positions, assumptions, or interpretations.

Tax Evidence is a Taxation-Domain-specific application of the Core [Evidence](../../00%20Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md) concept, reusing Core's epistemic semantics rather than defining a parallel one — in the same way [Candidate Evidence](../Personnel%20Management/Selection/CandidateEvidence.md) and [Performance Evidence](../Personnel%20Management/Performance/PerformanceEvidence.md) already apply it within Personnel Management.

---

## Reuse Core epistemic semantics

Every Tax Evidence item must be classifiable within the existing Core Epistemic Boundary — Fact, Observation, Evidence, Belief, Assumption, Inference, Hypothesis, Unknown (see [../../00 Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md](../../00%20Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md)). **This Domain does not create a parallel epistemic system.**

---

## Authority and provenance

Because tax conclusions carry real financial and legal consequences, Taxation must be capable of distinguishing the authority/provenance of Tax Evidence, such as:

```text
statutory text
administrative guidance
court interpretation
official ruling
professional opinion
RF-One inference
```

This is illustrative, not exhaustive. **Do not collapse these into one certainty level.** Statutory text and a binding official ruling on the Subject's own facts carry materially different authority than an administrative guidance document, a professional opinion, or an RF-One inference — and that difference must be preserved and surfaced alongside any conclusion drawn from it, not flattened into an undifferentiated "source."

---

## What every Tax Evidence item must conceptually preserve

- **source/provenance** — where it came from, and its authority level (see above);
- **the underlying content** — the statutory, administrative, judicial, official, professional, or inferred content itself, kept separate from any conclusion drawn from it;
- **jurisdiction and effective date/period** — see [TaxJurisdiction.md](TaxJurisdiction.md) and [../../00 Core/ConceptualArchitecture/04_Temporal_Coherence_and_Evolution.md](../../00%20Core/ConceptualArchitecture/04_Temporal_Coherence_and_Evolution.md);
- **epistemic status** — Fact, Observation, Evidence, Belief, Assumption, Inference, or Hypothesis;
- **uncertainty** — how confident the Evidence should be treated as being.

This Domain does not prescribe a database schema or field list for these properties; it requires that they be conceptually preserved.

---

## Direct source content vs. derived conclusion

A piece of statutory text, an administrative ruling, or a professional opinion is not the same thing as a conclusion drawn from applying it to the Subject's specific facts. Tax Evidence is the former (the source content, preserved with its provenance); a [Tax Position](TaxPosition.md) or [Tax Treatment](TaxTreatment.md) is the latter (the conclusion). The conclusion must be kept visibly separate from the Evidence it was drawn from — the same discipline already applied by [PerformanceEvidence.md](../Personnel%20Management/Performance/PerformanceEvidence.md) within Personnel Management.

---

## What Tax Evidence is not

- It is not a [Tax Position](TaxPosition.md) or [Tax Treatment](TaxTreatment.md) — those are conclusions drawn from Evidence, not the Evidence itself.
- It is not automatically a Fact merely because it was recorded or cited.
- It is not a parallel epistemic system — see "Reuse Core epistemic semantics" above.

---

## Related concepts

- [TaxPosition.md](TaxPosition.md)
- [TaxTreatment.md](TaxTreatment.md)
- [TaxJurisdiction.md](TaxJurisdiction.md)
- [Taxation.md](Taxation.md)
- [../../00 Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md](../../00%20Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md)
