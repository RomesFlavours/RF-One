# Tax Position

**Version:** 0.1
**Status:** Draft (initial canonical foundation)
**Module:** Domain / Taxation

---

## Purpose

**Tax Position** is a tax-relevant position taken or proposed regarding a transaction, entity, asset, deduction, credit, classification, timing, or treatment.

A Tax Position is Taxation's application of the Core [Epistemic Boundary](../../00%20Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md) to a concrete tax question: it is a conclusion (or proposed conclusion) about how tax rules apply, grounded in [Tax Evidence](TaxEvidence.md), not an assertion of Fact by default.

---

## What a Tax Position may concern

```text
transaction
entity
asset
deduction
credit
classification
timing
treatment
```

This is illustrative, not exhaustive.

---

## Must preserve evidence, authority, assumptions, and uncertainty

Every Tax Position must conceptually preserve:

- **the [Tax Evidence](TaxEvidence.md) it relies on** — kept visibly separate from the conclusion itself;
- **the authority/provenance behind the position** — e.g. statutory text, administrative guidance, court interpretation, official ruling, professional opinion, or RF-One inference (see [TaxEvidence.md](TaxEvidence.md), "Authority and provenance");
- **the assumptions made** — facts taken as true for the purpose of reasoning, without independent verification;
- **the uncertainty involved** — how confident the Position should be treated as being, and what would change that confidence.

A Tax Position must never silently collapse these into a single unqualified conclusion. This Domain does not prescribe a database schema or confidence-scoring scheme for these properties; it requires that they be conceptually preserved.

---

## Epistemic status

A Tax Position is, by default, a Belief, Inference or Hypothesis (see [../../00 Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md](../../00%20Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md)) about how a rule applies to the Subject's specific facts and circumstances. **It must never be silently promoted to Fact** merely because it is well-reasoned, widely held, or has gone unchallenged — see [../../00 Core/ConceptualArchitecture/08_Net_Outcome_and_Structural_Optimization.md](../../00%20Core/ConceptualArchitecture/08_Net_Outcome_and_Structural_Optimization.md), Section 7. A Tax Position becomes closer to Fact only where confirmed by a competent authority (e.g. a binding ruling, a final court decision) applicable to the Subject's own facts and period.

---

## When professional review is warranted

Taxation should identify, and surface, when a Tax Position's stakes, complexity, novelty, or interpretive uncertainty warrant external professional review, rather than silently resolving the question on RF-One's own inference — see [Taxation.md](Taxation.md), "Subject and professional authority". This Domain does not define a fixed threshold or algorithm for when review is warranted; that is a Domain/Runtime judgment informed by the uncertainty and authority level actually preserved on the Position.

---

## What a Tax Position is not

- It is not automatically a Fact — see above.
- It is not a [Tax Treatment](TaxTreatment.md) — a Treatment is how a tax regime actually treats a fact; a Position is what the Subject (or RF-One, on the Subject's behalf) takes or proposes regarding that treatment, which may or may not turn out to match it.
- It is not a Decision — see [Taxation.md](Taxation.md), "Relationship to Decision".

---

## Related concepts

- [TaxEvidence.md](TaxEvidence.md)
- [TaxTreatment.md](TaxTreatment.md)
- [Taxation.md](Taxation.md)
- [../../00 Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md](../../00%20Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md)
