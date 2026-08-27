# Tax Scenario

**Version:** 0.1
**Status:** Draft (initial canonical foundation)
**Module:** Domain / Taxation

---

## Purpose

**Tax Scenario** is a counterfactual configuration used to compare lawful alternatives, for example:

```text
current structure
vs
alternative structure
```

Tax Scenario is the Taxation-Domain-specific application of Core's [Counterfactual Structural Comparison](../../00%20Core/ConceptualArchitecture/08_Net_Outcome_and_Structural_Optimization.md) (Section 4): it does not introduce a new comparison mechanism, it applies the existing one to tax-relevant structures, timings, and elections.

---

## What a Tax Scenario represents

A Tax Scenario represents one internally-consistent configuration of facts, assumed [Tax Treatments](TaxTreatment.md), and a resulting [Tax Impact](TaxImpact.md) — for example, "keep the current entity structure" versus "adopt an alternative entity structure," or "make the purchase this fiscal period" versus "make it next period." Two or more Tax Scenarios are typically compared against each other, or against the Subject's current/default position.

Lawful alternatives a Tax Scenario may explore include, where applicable:

```text
entity selection
entity separation
ownership structure
transaction timing
compensation structure
capital expenditure timing
deduction / credit utilization
depreciation choices
loss utilization
retirement / benefit structures
jurisdictional choices
asset placement
financing choices
succession / estate structures
```

This is illustrative, not a universal checklist. Taxation should compare consequences rather than assume one structure is always better.

---

## Scenario comparison dimensions

Where relevant, a Tax Scenario comparison may consider:

```text
gross economic outcome
tax liability
after-tax / retained value
cash timing
implementation cost
ongoing administrative cost
compliance burden
audit / controversy risk
interpretive uncertainty
transition cost
reversibility
future flexibility
time horizon
```

**Do not require one universal scalar score.** These dimensions are surfaced to the Subject as tradeoffs, consistent with Core's Counterfactual Structural Comparison (see [../../00 Core/ConceptualArchitecture/08_Net_Outcome_and_Structural_Optimization.md](../../00%20Core/ConceptualArchitecture/08_Net_Outcome_and_Structural_Optimization.md), Section 4) — not collapsed into a single automatic ranking.

---

## Lawful alternatives only

A Tax Scenario represents a genuinely available, lawful alternative — a real structure, timing, or election the Subject could actually adopt. See [TaxStrategy.md](TaxStrategy.md), "Lawful boundary": a Tax Scenario built on a sham structure, a misrepresented fact, or a concealment is not an admissible alternative to weigh against lawful scenarios as if it were a comparable option — see [../../00 Core/ConceptualArchitecture/08_Net_Outcome_and_Structural_Optimization.md](../../00%20Core/ConceptualArchitecture/08_Net_Outcome_and_Structural_Optimization.md), Section 5.

---

## What a Tax Scenario is not

- It is not a Decision — comparing scenarios informs a Decision; it does not make one. See [Taxation.md](Taxation.md), "Relationship to Decision".
- It is not a guarantee — a Scenario's outcome depends on assumed [Tax Treatments](TaxTreatment.md) and [Tax Evidence](TaxEvidence.md) that may carry uncertainty; that uncertainty must be preserved and surfaced, not resolved away by the act of building the Scenario.
- It does not assume that a lower nominal tax liability is automatically the better Scenario — see the full set of comparison dimensions above.

---

## Related concepts

- [TaxImpact.md](TaxImpact.md)
- [TaxTreatment.md](TaxTreatment.md)
- [TaxStrategy.md](TaxStrategy.md)
- [Taxation.md](Taxation.md)
- [../../00 Core/ConceptualArchitecture/08_Net_Outcome_and_Structural_Optimization.md](../../00%20Core/ConceptualArchitecture/08_Net_Outcome_and_Structural_Optimization.md)
