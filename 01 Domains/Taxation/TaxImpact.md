# Tax Impact

**Version:** 0.1
**Status:** Draft (initial canonical foundation)
**Module:** Domain / Taxation

---

## Purpose

**Tax Impact** is the tax consequence associated with a transaction, structure, period, [Tax Scenario](TaxScenario.md), or Decision.

Tax Impact is what turns applicable [Tax Obligations](TaxObligation.md) and [Tax Treatments](TaxTreatment.md) into a concrete consequence for a specific fact — it is the mechanism by which a Gross Outcome becomes a Net/Retained Outcome in the tax dimension, applying Core's [Net / Retained Outcome](../../00%20Core/ConceptualArchitecture/08_Net_Outcome_and_Structural_Optimization.md) concept (Section 1) without redefining it.

---

## Definition

```text
Gross Outcome
- Tax Impact (and any other applicable External Obligations/Claims)
= Net / Retained Outcome
```

A Tax Impact quantifies or characterizes how much of a Gross Outcome a given transaction, structure, period, Scenario, or Decision is expected (or was actually determined) to redirect toward Tax Obligations, and over what timing. Not every Tax Impact is reducible to a single number: it may include payment amounts, timing effects (e.g. deferral or acceleration), and non-monetary consequences (e.g. a filing or reporting consequence) — consistent with [TaxObligation.md](TaxObligation.md), "Do not reduce Tax Obligation to a monetary amount only."

---

## Prospective vs. determined Tax Impact

A Tax Impact may be:

- **prospective** — an estimated consequence used within a [Tax Scenario](TaxScenario.md) to compare alternatives before a Decision is made;
- **determined** — the consequence actually produced once an Action has occurred and its Outcome is known.

Both must preserve their epistemic status (see [TaxPosition.md](TaxPosition.md), "Epistemic status"): a prospective Tax Impact is an Inference or Hypothesis based on assumed Tax Treatments, not a Fact, until the underlying facts and rule application are actually determined.

---

## Relationship to the Core loop

```text
... → Action → Outcome → Tax Impact → Net / Retained Outcome → Learning
```

Tax Impact sits between Outcome and Net/Retained Outcome in the operational loop documented in [Taxation.md](Taxation.md), "Outcomes and feedback/learning", and [README.md](README.md), "The operational loop" — it does not introduce a separate cycle.

---

## What a Tax Impact is not

- It is not a Tax Obligation — an Obligation is the duty; an Impact is the consequence that duty (and any applicable Treatment) produces for a specific fact.
- It is not automatically the same as what was estimated in a prospective Tax Scenario — the comparison between estimated and determined Tax Impact is itself Learning (see [../../00 Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md](../../00%20Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md)).
- It is not a universal financial utility function — see [../../00 Core/ConceptualArchitecture/08_Net_Outcome_and_Structural_Optimization.md](../../00%20Core/ConceptualArchitecture/08_Net_Outcome_and_Structural_Optimization.md), Section 1.

---

## Related concepts

- [TaxObligation.md](TaxObligation.md)
- [TaxTreatment.md](TaxTreatment.md)
- [TaxScenario.md](TaxScenario.md)
- [Taxation.md](Taxation.md)
- [../../00 Core/ConceptualArchitecture/08_Net_Outcome_and_Structural_Optimization.md](../../00%20Core/ConceptualArchitecture/08_Net_Outcome_and_Structural_Optimization.md)
