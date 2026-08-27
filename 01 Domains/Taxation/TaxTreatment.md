# Tax Treatment

**Version:** 0.1
**Status:** Draft (initial canonical foundation)
**Module:** Domain / Taxation

---

## Purpose

**Tax Treatment** is how an applicable tax regime treats a relevant fact, transaction, entity, asset, or event, within a given [Tax Jurisdiction](TaxJurisdiction.md) and period.

Where [Tax Position](TaxPosition.md) is what the Subject (or RF-One, reasoning on the Subject's behalf) takes or proposes, Tax Treatment is the (believed, inferred, or confirmed) actual rule outcome that applies. The two are related but distinct — see [TaxPosition.md](TaxPosition.md), "What a Tax Position is not".

---

## Definition

A Tax Treatment describes how a specific tax regime classifies or handles a fact — for example, whether a cost is currently deductible or must be capitalized, whether a receipt is taxable income or a return of capital, whether an entity is treated as transparent or opaque for tax purposes, or when an item of income or expense is recognized. Core does not encode any specific treatment, rate, or rule (see [../../00 Core/ConceptualArchitecture/08_Net_Outcome_and_Structural_Optimization.md](../../00%20Core/ConceptualArchitecture/08_Net_Outcome_and_Structural_Optimization.md), Section 11); concrete treatments are Domain/Runtime knowledge, applied through this concept, not defined here.

---

## Temporal and jurisdictional dependence

A Tax Treatment is only valid for the [Tax Jurisdiction](TaxJurisdiction.md), effective date/period, and facts and circumstances it was determined under. Consistent with [Temporal Coherence](../../00%20Core/ConceptualArchitecture/04_Temporal_Coherence_and_Evolution.md), a Tax Treatment confirmed under one jurisdiction, date, or set of facts must never be silently generalized as timeless, universal, or automatically applicable to different facts.

---

## What a Tax Treatment conceptually carries

- the [Tax Jurisdiction](TaxJurisdiction.md) and effective date/period it applies under;
- the specific fact, transaction, entity, asset, or event it treats;
- the [Tax Evidence](TaxEvidence.md) and authority supporting it (statutory text, administrative guidance, court interpretation, official ruling, professional opinion, or RF-One inference);
- its epistemic status — see [TaxPosition.md](TaxPosition.md), "Epistemic status", which applies identically here.

---

## Relationship to Tax Impact and Tax Scenario

A Tax Treatment, once determined or assumed for a given fact, feeds into the [Tax Impact](TaxImpact.md) of the transaction, structure or period it belongs to, and into any [Tax Scenario](TaxScenario.md) that compares alternative structures or timings — a scenario's plausibility depends on the Tax Treatment(s) it assumes actually holding.

---

## What a Tax Treatment is not

- It is not a Tax Position — see above.
- It is not a specific tax rate or a monetary figure by itself; a rate or amount may be an input to computing a Tax Impact, but the Treatment is the qualitative/classificatory determination, not the number.
- It is not automatically permanent — see "Temporal and jurisdictional dependence" above.

---

## Related concepts

- [TaxPosition.md](TaxPosition.md)
- [TaxJurisdiction.md](TaxJurisdiction.md)
- [TaxImpact.md](TaxImpact.md)
- [TaxScenario.md](TaxScenario.md)
- [Taxation.md](Taxation.md)
