# Taxation

**Version:** 0.1
**Status:** Draft (initial canonical foundation)
**Module:** Domain / Taxation

---

## Purpose

**Taxation** is the business activity, and the reasoning process, of representing and evaluating the tax consequences of facts, transactions, structures and Decisions that belong to other Domains, so that a Subject can understand its tax obligations, its available lawful alternatives, and its likely Net/Retained Outcome after tax.

Taxation is a Domain-level specialization of how RF-One reasons about Net/Retained Outcome and Constraint Shaping within the Core's Subject ↔ Reality relationship (see [../../00 Core/ConceptualArchitecture/08_Net_Outcome_and_Structural_Optimization.md](../../00%20Core/ConceptualArchitecture/08_Net_Outcome_and_Structural_Optimization.md)): the Subject acts within a Reality that includes tax authorities, tax rules, tax obligations and lawful tax alternatives, under partial and often uncertain knowledge of how those rules apply.

---

## What Taxation is not

Taxation is not primarily:

- Accounting — the ongoing recording, classification and reporting of financial transactions;
- Finance — capital structure, financing decisions, cash management and investment activity;
- Legal Entity Management — the creation, governance, ownership and lifecycle of legal entities;
- tax return preparation, electronic filing, or specific tax forms;
- a table of tax rates, deductions, credits, or depreciation schedules;
- a substitute for a licensed tax professional, attorney, or tax authority.

See [README.md](README.md), "Taxation ≠ Core, ≠ Accounting, ≠ Finance, ≠ Legal Entity Management", for the full boundary statement. These may become Product/Runtime capabilities, or knowledge supplied by external professionals and services, layered on top of this Domain. They are not what Taxation, as a Domain, *is*.

Taxation does not imply that the lowest nominal tax liability is automatically the best outcome. Nominal tax minimization is one input among several; compliance burden, audit/controversy risk, interpretive uncertainty, transition cost, reversibility and future flexibility all inform the reasoning — see [TaxScenario.md](TaxScenario.md).

---

## Inputs

Taxation's reasoning draws on:

- **[Tax Jurisdiction](TaxJurisdiction.md)** — which governmental/legal tax authority context is relevant, and when;
- **[Tax Obligation](TaxObligation.md)** — what legally imposed tax-related duties currently apply;
- **[Tax Evidence](TaxEvidence.md)** — what is actually known, with its provenance, authority and epistemic status;
- facts owned by other Domains that carry tax consequences (compensation, purchases, entity structure, transactions, financing — see [README.md](README.md), "Cross-Domain relationships");
- the Subject's Goals and Constraints, where genuinely relevant to a tax question;
- known Unknowns — what relevant rule application or fact is simply not yet resolved.

Taxation does not own or define any of these inputs beyond its own reasoning over them; it consumes them from Core, from the Domain that owns the underlying fact, and from Tax Evidence.

---

## Evaluation

Taxation evaluates available Tax Evidence, applicable Tax Jurisdiction and Tax Obligation against a fact, transaction, structure or proposed action to produce a **[Tax Position](TaxPosition.md)** or a **[Tax Treatment](TaxTreatment.md)** — a contextual, evidence-based conclusion, not an automatic Fact.

Where a Subject is choosing between alternative structures or timings, Taxation may construct one or more **[Tax Scenarios](TaxScenario.md)** and evaluate the **[Tax Impact](TaxImpact.md)** of each, in support of a **[Tax Strategy](TaxStrategy.md)**.

---

## Uncertainty

Taxation routinely operates under incomplete and evolving knowledge. It must maintain the [Epistemic Boundary](../../00%20Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md) throughout:

- an Inference about how a rule applies to the Subject's facts and circumstances must never be silently presented as a Fact — see [TaxEvidence.md](TaxEvidence.md) and [TaxPosition.md](TaxPosition.md);
- the absence of clear guidance on a question must never be silently treated as either "clearly allowed" or "clearly disallowed" — it is an Unknown, to be surfaced, not assumed;
- material uncertainty, and where professional review is warranted, must be surfaced explicitly, not omitted — see [Subject and professional authority](#subject-and-professional-authority) below.

---

## Relationship to Decision

Taxation informs, but does not replace, the Core [Decision](../../00%20Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md). A Tax Position, Tax Treatment, Tax Scenario or Tax Strategy is an input to a Decision the Subject (or whoever holds delegated authority) makes — it is not itself the Decision, and it does not by itself constitute authorization to act. See [TaxStrategy.md](TaxStrategy.md), "Tax Strategy is not a Decision".

---

## Outcomes and feedback/learning

What happens after a tax-relevant Decision — an Action taken, its Outcome, its Tax Impact, the resulting Net/Retained Outcome — is feedback this Domain is designed to remain compatible with:

```text
Tax Position / Tax Scenario assumptions
  → Decision
    → Action
      → Outcome
        → Tax Impact
          → Net / Retained Outcome
            → Learning
              → better future Tax Position / Tax Scenario reasoning
```

See [../../00 Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md](../../00%20Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md) for the Core's general Decision → Action → Outcome → Learning cycle, which tax-relevant Decisions participate in like any other Decision, and [../../00 Core/ConceptualArchitecture/08_Net_Outcome_and_Structural_Optimization.md](../../00%20Core/ConceptualArchitecture/08_Net_Outcome_and_Structural_Optimization.md) for the Gross Outcome → Obligations/Claims → Net/Retained Outcome layering this loop specializes.

---

## Cross-Domain examples (illustrative only)

```text
Employee compensation
  → Personnel Management / Workforce fact
      (a compensation structure exists for operational and personnel reasons)
  → Taxation evaluates tax consequences
      (Tax Obligation on payroll, Tax Treatment of benefit components, Tax Position on classification)
```

```text
Restaurant equipment purchase
  → Restaurant / Asset / Finance fact
      (equipment is purchased for operational reasons)
  → Taxation evaluates tax treatment
      (Tax Treatment of the expenditure, timing considerations relevant to a Tax Scenario)
```

```text
Legal entity structure
  → organizational/legal reality owned by Legal Entity Management
      (an entity is structured for governance, liability, and operational reasons)
  → Taxation evaluates tax consequences
      (Tax Obligation and Tax Treatment that follow from the chosen structure; Tax Strategy may
       surface an alternative lawful structure with a different after-tax Net/Retained Outcome —
       the Decision to actually restructure remains outside Taxation, see README.md)
```

In every case, Taxation evaluates tax consequences of a fact it does not own; it does not decide the underlying operational, personnel, asset, or organizational question.

---

## Subject and professional authority

Taxation may:

```text
surface alternatives
calculate scenarios
identify obligations
identify opportunities
compare after-tax outcomes
surface uncertainty
identify where professional review is warranted
```

The Subject retains strategic authority over any tax-relevant Decision — see [Subject Sovereignty](../../00%20Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md). External tax professionals, attorneys and tax authorities may be part of Reality, a source of Tax Evidence, or holders of delegated authority for specific tax matters (see [../../00 Core/ConceptualArchitecture/06_Business_Autopilot_and_Intelligence_Engine.md](../../00%20Core/ConceptualArchitecture/06_Business_Autopilot_and_Intelligence_Engine.md) for Delegated Authority).

**Taxation, as a Domain, is not a substitute for external legal/accounting authority.** Where a question's stakes, complexity or interpretive uncertainty warrant it, Taxation should surface that professional review is warranted rather than silently resolving the question itself — see [TaxPosition.md](TaxPosition.md), "When professional review is warranted".

---

## Related concepts

- [TaxJurisdiction.md](TaxJurisdiction.md)
- [TaxObligation.md](TaxObligation.md)
- [TaxPosition.md](TaxPosition.md)
- [TaxTreatment.md](TaxTreatment.md)
- [TaxScenario.md](TaxScenario.md)
- [TaxImpact.md](TaxImpact.md)
- [TaxStrategy.md](TaxStrategy.md)
- [TaxEvidence.md](TaxEvidence.md)
- [../../00 Core/ConceptualArchitecture/08_Net_Outcome_and_Structural_Optimization.md](../../00%20Core/ConceptualArchitecture/08_Net_Outcome_and_Structural_Optimization.md)
- [../../00 Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md](../../00%20Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md)
