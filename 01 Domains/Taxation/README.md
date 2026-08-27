# Taxation Domain

**Version:** 0.1
**Status:** Draft (initial canonical foundation — TASK_TAXATION_001)
**Module:** Domain / Taxation

---

## Purpose

**Taxation** is the transversal (cross-industry) Domain responsible for representing and reasoning about tax obligations, tax consequences, tax positions, tax treatments, tax incentives, tax credits, tax deductions, tax timing, tax structure, lawful tax planning, after-tax outcomes, tax uncertainty and tax compliance burden.

Taxation reasons about the tax consequences of facts that are owned by many other Domains — it does not own those facts. It is transversal in the same sense already established for Personnel Management (see [../Domain Architecture.md](../Domain%20Architecture.md)): it applies wherever a tax-relevant fact exists, consuming content from whichever Domain owns that fact, without duplicating that Domain's knowledge.

---

## Taxation ≠ Core, ≠ Accounting, ≠ Finance, ≠ Legal Entity Management

```text
Taxation ≠ Core
Taxation ≠ Accounting
Taxation ≠ Finance
Taxation ≠ Legal Entity Management
```

- **Taxation ≠ Core.** Core (`00 Core/`) supplies universal, domain-independent reasoning semantics — Goal, Decision, Outcome, Net/Retained Outcome, Constraint Shaping, Epistemic Boundary, Temporal Coherence, Subject Sovereignty. Taxation applies and specializes those semantics for tax; it does not redefine them, and no tax rate, tax rule, or tax-specific concept belongs in Core. See [Relationship to Core 2.0](#relationship-to-core-20) below.
- **Taxation ≠ Accounting.** Accounting is the ongoing recording, classification and reporting of financial transactions (a ledger, books, financial statements). Taxation evaluates the tax consequences of facts that Accounting (where it exists as a Domain/Runtime capability) records; it does not maintain a ledger, does not post journal entries, and does not produce financial statements.
- **Taxation ≠ Finance.** Finance concerns capital structure, financing decisions, cash management, banking and investment activity for their own sake. Taxation evaluates the tax consequences that financing, banking and investment facts may carry; it does not decide financing strategy, does not manage cash, and does not own banking data.
- **Taxation ≠ Legal Entity Management.** Legal Entity Management concerns the creation, governance, ownership and lifecycle of legal entities (see [../../00 Core/Corporate.md](../../00%20Core/Corporate.md), [../../00 Core/Entity.md](../../00%20Core/Entity.md)) for their own sake. Taxation evaluates the tax consequences of a given entity structure; it does not create entities, does not govern them, and does not decide organizational/ownership structure on non-tax grounds.

Taxation may recommend that a given structural or timing choice would improve after-tax outcomes (see [TaxStrategy.md](TaxStrategy.md)), but the Decision to adopt it, and its implementation as an actual Accounting, Finance, or Legal Entity Management act, belongs to those Domains/Runtimes and to the Subject — see [Cross-Domain Relationships](#cross-domain-relationships).

---

## What Taxation is not

- It is not tax return preparation or electronic filing software.
- It is not a specific country's or state's tax law encoded as rules.
- It is not a table of tax rates, deductions, credits, or depreciation schedules.
- It is not a substitute for a licensed tax professional, attorney, or tax authority.
- It is not Accounting, Finance, or Legal Entity Management (see above).

These may become Product/Runtime capabilities, or knowledge supplied by external professionals and services, layered on top of this Domain. They are not what Taxation, as a Domain, *is*. See [Scope Exclusions](#scope-exclusions).

---

## Domain map

```text
01 Domains/Taxation/
├── README.md              (this document)
├── Taxation.md             the Domain's central reasoning concept
├── TaxJurisdiction.md      the governmental/legal tax authority context
├── TaxObligation.md        a legally imposed tax-related duty
├── TaxPosition.md          a tax-relevant position taken or proposed
├── TaxTreatment.md         how a tax regime treats a relevant fact
├── TaxScenario.md          a counterfactual configuration for comparison
├── TaxImpact.md            the tax consequence of a transaction/structure/scenario
├── TaxStrategy.md          a lawful approach to improve after-tax outcomes
└── TaxEvidence.md          evidence supporting tax facts/positions/treatments
```

This is a flat, one-concept-per-file structure, matching the initial canonical concepts required by TASK_TAXATION_001. No file was created merely for symmetry; each corresponds to a concept the task requires to be analyzed and defined.

---

## Domain positioning

Taxation is transversal. It may interact with, without owning:

```text
Restaurant
Personnel Management
Finance / banking data
Corporate / organizational structure
Assets
Transactions
Ownership
Strategy
```

Taxation does not own those concepts merely because they have tax consequences. Examples:

```text
Employee compensation
→ Personnel/Workforce fact
→ Taxation evaluates tax consequences
```

```text
Restaurant equipment purchase
→ operational/asset/finance fact
→ Taxation evaluates tax treatment
```

```text
Legal entity structure
→ organizational/legal reality
→ Taxation evaluates tax consequences
```

See [Taxation.md](Taxation.md), "Cross-Domain examples", for the fuller treatment, and [Cross-Domain Relationships](#cross-domain-relationships) below.

---

## Relationship to Core 2.0

Taxation is built on the RF-One Core Conceptual Architecture and reuses its concepts without redefining them:

- **Goal, Reality Check** — see [../../00 Core/ConceptualArchitecture/02_Desire_Goal_and_Reality_Check.md](../../00%20Core/ConceptualArchitecture/02_Desire_Goal_and_Reality_Check.md).
- **Decision, Action, Outcome, Learning** — see [../../00 Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md](../../00%20Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md). Tax Strategy informs a Decision; it does not replace Core Decision semantics — see [TaxStrategy.md](TaxStrategy.md).
- **Temporal Coherence** — see [../../00 Core/ConceptualArchitecture/04_Temporal_Coherence_and_Evolution.md](../../00%20Core/ConceptualArchitecture/04_Temporal_Coherence_and_Evolution.md). Tax rules are jurisdiction- and date-dependent; a current treatment must never be assumed to have applied historically or to apply in the future — see [TaxJurisdiction.md](TaxJurisdiction.md) and [TaxTreatment.md](TaxTreatment.md).
- **Epistemic Boundary and Subject Sovereignty** — see [../../00 Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md](../../00%20Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md). Governs how Tax Evidence and Tax Positions preserve provenance, authority and uncertainty, and how the Subject retains final authority — see [TaxEvidence.md](TaxEvidence.md), [TaxPosition.md](TaxPosition.md).
- **Net / Retained Outcome, External Obligations/Claims, Constraint Shaping, Counterfactual Structural Comparison, Lawful Optimization boundary** — see [../../00 Core/ConceptualArchitecture/08_Net_Outcome_and_Structural_Optimization.md](../../00%20Core/ConceptualArchitecture/08_Net_Outcome_and_Structural_Optimization.md). Taxation is the primary — but not the only — Domain-level application of this Core capability: a Tax Obligation is a Domain-specific realization of an External Obligation/Claim; Tax Impact is what separates a Gross Outcome from a Net/Retained Outcome; Tax Strategy is a Domain-specific application of Constraint Shaping; Tax Scenario is a Domain-specific application of Counterfactual Structural Comparison; and the lawful-optimization boundary defined there is reused verbatim, not redefined — see [Lawful Optimization Boundary](#lawful-optimization-boundary) below.

This Domain does not redefine any of these concepts; each Taxation concept specializes them only where a genuine tax-specific meaning is required.

### The operational loop

```text
Goal
→ Reality Check
→ Tax Scenarios / Treatments / Obligations
→ Core Decision
→ Action
→ Outcome
→ Tax Impact
→ Net / Retained Outcome
→ Learning
```

**Taxation supplies domain knowledge. Core supplies decision semantics.** Taxation does not decide on the Subject's behalf, does not replace the Core Decision cycle, and does not introduce a parallel operational loop.

---

## Lawful optimization boundary

Taxation supports lawful tax optimization. It must explicitly distinguish lawful planning from:

```text
evasion
fraud
misrepresentation
concealment
false reporting
sham structures
```

This reuses, and does not redefine, the lawful-optimization boundary established in [../../00 Core/ConceptualArchitecture/08_Net_Outcome_and_Structural_Optimization.md](../../00%20Core/ConceptualArchitecture/08_Net_Outcome_and_Structural_Optimization.md), Section 5: a lawful Tax Strategy genuinely changes the Subject's relationship to Reality (a real structure, a real timing choice, a real election actually made); evasion, fraud, misrepresentation, concealment, false reporting and sham structures instead misstate or conceal that relationship while pretending it is something else. See [TaxStrategy.md](TaxStrategy.md), "Lawful boundary".

---

## Cross-Domain relationships

Taxation consumes facts owned by other Domains and evaluates their tax consequences; it does not own or duplicate those facts:

```text
Restaurant / other technical Domains
  → operational, asset, transaction facts
Personnel Management
  → compensation, benefit, employment facts
Finance / banking data
  → financing, cash, investment facts
Corporate / organizational structure
  → entity, ownership, governance facts
Assets, Transactions, Ownership
  → the underlying business facts
Strategy
  → the organization's own direction (see ../../09 Strategy/)

Taxation
  → evaluates the tax consequences of all of the above
```

See [Taxation.md](Taxation.md), "Cross-Domain examples", for illustrative walkthroughs, and [Scope Exclusions](#scope-exclusions) for what remains explicitly out of scope for this initial task.

---

## Scope exclusions

This task establishes the Domain ontology and boundaries only. It does not implement:

```text
tax return preparation
electronic filing
specific IRS forms
specific tax rates
specific deductions
state-by-state tax tables
country-by-country tax law
live tax-law ingestion
automated entity creation
accounting ledger
bank integration
```

These require later knowledge, Runtime, Product, or other Domain work.

---

## Related documents

- [../README.md](../README.md) — `01 Domains/` purpose and authority
- [../Domain Architecture.md](../Domain%20Architecture.md) — cross-Domain conclusions for other transversal Domains
- [Taxation.md](Taxation.md) — the Domain's central reasoning concept
- [../../00 Core/ConceptualArchitecture/08_Net_Outcome_and_Structural_Optimization.md](../../00%20Core/ConceptualArchitecture/08_Net_Outcome_and_Structural_Optimization.md) — the Core capability this Domain applies
- [../../07 Tasks/TASK_TAXATION_001_Create_RF_One_Taxation_Domain.md](../../07%20Tasks/TASK_TAXATION_001_Create_RF_One_Taxation_Domain.md) — task that created this Domain
