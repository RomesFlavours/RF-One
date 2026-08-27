# Tax Obligation

**Version:** 0.1
**Status:** Draft (initial canonical foundation)
**Module:** Domain / Taxation

---

## Purpose

**Tax Obligation** is a legally imposed tax-related duty that applies to a Subject within a given [Tax Jurisdiction](TaxJurisdiction.md) and period.

Tax Obligation is the Taxation-Domain-specific realization of the Core concept of an [External Obligation/Claim](../../00%20Core/ConceptualArchitecture/08_Net_Outcome_and_Structural_Optimization.md) (Section 2): Reality imposing a claim that reduces, redirects, conditions, or delays value the Subject would otherwise retain.

---

## Forms a Tax Obligation may take

A Tax Obligation may include:

```text
payment
filing
withholding
reporting
remittance
```

This is illustrative, not exhaustive. **Do not reduce Tax Obligation to a monetary amount only.** A filing duty, a reporting duty, or a withholding duty is a Tax Obligation even where no immediate payment is due; failing to represent non-payment obligations would misrepresent the Subject's actual compliance burden.

---

## What a Tax Obligation conceptually carries

Regardless of form, a Tax Obligation should conceptually preserve:

- the relevant [Tax Jurisdiction(s)](TaxJurisdiction.md) that impose it;
- the period or point in time it applies to (see [Temporal Coherence](../../00%20Core/ConceptualArchitecture/04_Temporal_Coherence_and_Evolution.md));
- its form (payment, filing, withholding, reporting, remittance, or another form);
- the underlying fact, transaction, or status that gives rise to it;
- its epistemic status — whether the Obligation itself is a confirmed Fact, or a Belief/Inference/Hypothesis pending confirmation (see [../../00 Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md](../../00%20Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md)).

This Domain does not prescribe a database schema or field list for these properties; it requires that they be conceptually preserved.

---

## Relationship to Net / Retained Outcome

Tax Obligations are the External Obligations/Claims that separate a Gross Outcome from a Net/Retained Outcome in the tax dimension (see [TaxImpact.md](TaxImpact.md) and [../../00 Core/ConceptualArchitecture/08_Net_Outcome_and_Structural_Optimization.md](../../00%20Core/ConceptualArchitecture/08_Net_Outcome_and_Structural_Optimization.md), Section 1–2). Taxation must be able to include known and reasonably anticipated Tax Obligations when reasoning about a Subject's expected Net/Retained Outcome.

---

## What a Tax Obligation is not

- It is not a specific tax rate, tax table, or tax rule — Core and this Domain define the concept of Tax Obligation, not its concrete content (see [README.md](README.md), "Scope exclusions").
- It is not automatically a Fact merely because it is asserted — see [TaxEvidence.md](TaxEvidence.md).
- It is not identical to a [Tax Impact](TaxImpact.md) — an Impact is the consequence a specific transaction, structure, period, scenario, or Decision produces; an Obligation is the duty that may give rise to that consequence.

---

## Related concepts

- [TaxJurisdiction.md](TaxJurisdiction.md)
- [TaxImpact.md](TaxImpact.md)
- [TaxEvidence.md](TaxEvidence.md)
- [Taxation.md](Taxation.md)
- [../../00 Core/ConceptualArchitecture/08_Net_Outcome_and_Structural_Optimization.md](../../00%20Core/ConceptualArchitecture/08_Net_Outcome_and_Structural_Optimization.md)
