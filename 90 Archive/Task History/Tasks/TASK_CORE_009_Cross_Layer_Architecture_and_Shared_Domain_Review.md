# TASK_CORE_009 — Cross-Layer Architecture and Shared Domain Review

## Objective

Review the canonical RF-One architecture after TASK_CORE_006, TASK_CORE_007, and TASK_CORE_008 and determine whether the current separation between:

> **Core ≠ Domain ≠ Product ≠ Runtime ≠ Strategy**

is coherent in practice.

This is an **analysis-only architectural review**.

The primary purpose is to resolve the genuine open questions identified by TASK_CORE_008 before any new Shared Domain is created or existing Restaurant material is relocated.

Do not modify, move, rename, or delete any repository file.

The only file you may create is the required final report:

```text
07 Tasks/Reports/TASK_CORE_009_REPORT.md
```

Do not make a Git commit.

---

# Mandatory first steps

1. Read `CLAUDE.md` completely.

2. Read:
   - `07 Tasks/TASK_CORE_006_Core_Legacy_Knowledge_Canonicalization.md`
   - `07 Tasks/TASK_CORE_007_Strategy_Legacy_Knowledge_Canonicalization.md`
   - `07 Tasks/TASK_CORE_008_Business_Capability_and_Domain_Roadmap_Canonicalization.md`
   - `07 Tasks/Reports/TASK_CORE_006_REPORT.md`
   - `07 Tasks/Reports/TASK_CORE_007_REPORT.md`
   - `07 Tasks/Reports/TASK_CORE_008_REPORT.md`
   - `07 Tasks/Backlog/LEGACY_KNOWLEDGE_RECONCILIATION_BACKLOG.md`

3. Read the current canonical:
   - `00 Core/README.md`
   - `00 Core/Entity.md`
   - `00 Core/Relationship.md`
   - `00 Core/Process.md`
   - `00 Core/Glossary.md`
   - `00 Core/ConceptualArchitecture/00_RF-One_Core_Vision.md`
   - `00 Core/ConceptualArchitecture/04_Temporal_Coherence_and_Evolution.md`
   - `00 Core/ConceptualArchitecture/06_Business_Autopilot_and_Intelligence_Engine.md`

4. Read the current Strategy layer:
   - `09 Strategy/README.md`
   - `09 Strategy/00_RF-One_Strategy.md`
   - `09 Strategy/01_Economic_Value_and_Measurement.md`
   - `09 Strategy/02_Service_Delivery_and_Knowledge_Advantage.md`
   - `09 Strategy/03_Shared_Intelligence_and_Knowledge_Governance.md`
   - `09 Strategy/04_Business_Capability_Coverage.md`

5. Read the Domain governance and Restaurant roadmap:
   - `01 Domains/README.md`
   - `01 Domains/Restaurant/README.md`
   - `01 Domains/Restaurant/Roadmap.md`
   - `01 Domains/_Shared/Environment/README.md`

6. Inspect all substantive files under:
   - `01 Domains/Restaurant/Commercial Catalog/`
   - `01 Domains/Restaurant/Model/`
   - `01 Domains/Restaurant/Purchasing/`
   - `01 Domains/Restaurant/Sales/`

7. Run `git status` before analysis.

Do not alter the existing unstaged/untracked work from TASK_CORE_006–008.

---

# Context

TASK_CORE_008 identified several genuine unresolved questions:

1. whether Marketing should remain partly Restaurant-specific, become a Shared Domain, or be split between the two;
2. whether Commercial Catalog is actually a Restaurant Domain component or a reusable Shared Domain;
3. whether Financial Performance requires a future reusable business Domain distinct from Strategy;
4. whether customer-level Strategic Planning is a future Product capability, Shared Domain, or something else.

This task must inspect the actual canonical material and provide grounded recommendations.

Do not create new architecture merely to make the repository symmetrical.

---

# Review principles

## 1. Reuse must be earned

A concept should become Shared Domain knowledge only when:

- its semantics are genuinely reusable across multiple business Domains;
- extracting it reduces duplication or future inconsistency;
- it is not merely generic-looking terminology;
- it does not actually belong to Core;
- it is not merely Product functionality.

Do not create Shared Domains speculatively without semantic evidence.

---

## 2. Domain vs Product

A Domain defines reusable structured business knowledge.

A Product combines Domains, capabilities, configuration, workflow, software, and commercial packaging to solve a customer problem.

Do not classify something as a Domain merely because users interact with it.

Do not classify something as Product merely because it has commercial value.

---

## 3. Strategy vs customer business knowledge

`09 Strategy/` describes RF-One's company/product-business strategy.

It must not become the home for the customer's own business semantics merely because those semantics concern finance, planning, growth, or performance.

A customer-level business concept may deserve a Shared Domain even if RF-One also has Strategy documents about its own economics.

---

## 4. Core remains universal

Do not recommend moving a concept into Shared Domain if it is truly universal RF-One ontology.

Likewise, do not push business semantics into Core merely because they appear in many Domains.

---

# Required review areas

## A. Commercial Catalog

Inspect all files under:

```text
01 Domains/Restaurant/Commercial Catalog/
```

and all cross-references to those concepts.

Determine whether the model is:

- genuinely Restaurant-specific;
- mostly reusable across retail/hospitality/other transactional businesses;
- a mix of shared generic catalog semantics plus Restaurant-specific specializations.

Pay particular attention to concepts such as:

- Catalogue;
- CatalogueVersion;
- CatalogueEntry;
- CatalogPublication;
- Item;
- ItemCategory;
- ItemGroup;
- Bundle;
- Modifier;
- ModifierGroup;
- Offer;
- Price;
- PriceList;
- Availability;
- SalesChannel;
- TaxCategory;
- UnitOfMeasure;
- Brand.

Explicitly answer:

1. Which concepts are generic across multiple business Domains?
2. Which are Restaurant-specific?
3. Should the entire folder eventually move to `_Shared/`?
4. Should only a generic subset move?
5. Would extraction now materially improve architecture, or is it premature?

Do not move anything.

---

## B. Marketing

Review every current reference to Marketing in:

- Restaurant documentation;
- Strategy coverage map;
- legacy backlog where relevant.

Determine whether the correct future model is:

### Option 1
All Marketing remains Restaurant-specific.

### Option 2
Marketing becomes a reusable Shared Domain.

### Option 3
Generic Marketing becomes Shared while Restaurant-specific marketing rules/knowledge remain Restaurant specializations.

Recommend one.

Consider:

- campaigns;
- advertising;
- social media;
- promotions;
- loyalty;
- reputation;
- Brand relationships;
- menu/product promotion;
- local-store execution.

Do not create Marketing files.

---

## C. Reputation

Determine whether Reputation is:

- part of Marketing;
- its own Shared Domain candidate;
- Product capability;
- a generic business concept that should remain unmodeled until needed.

Consider:

- reviews;
- ratings;
- feedback;
- competitor monitoring;
- sentiment;
- response workflows.

Avoid speculative ontology.

---

## D. Workforce / Personnel

TASK_CORE_008 identified Personnel as a Shared Domain candidate.

Review whether repository evidence supports a future reusable Domain such as:

```text
Workforce
People
Personnel
Human Resources
```

Do not choose a final name unless semantic evidence is sufficient.

Inspect current references to:

- Employee;
- role;
- assignment;
- responsibility;
- scheduling;
- skills;
- performance;
- training;
- selection.

Also consider the approved future direction:

```text
Goals
→ Brand
→ Service Model
→ Behaviors
→ Selection / Training / Performance
```

Explicitly separate:

- Workforce business semantics;
- Selection capability;
- Training capability;
- Product workflows.

Do not create the Domain.

---

## E. Equipment and Facilities

Determine whether these should eventually be:

- separate Shared Domains;
- one broader Asset/Facilities Domain;
- Domain-specific concepts within Restaurant;
- deferred until more evidence exists.

Use actual existing Restaurant modeling evidence.

Do not generalize merely because physical businesses commonly have equipment and facilities.

---

## F. Financial Performance

This requires careful layer separation.

TASK_CORE_008 classified historical Financial Performance as Strategy/business capability.

Now determine whether there are actually **two different things**:

### RF-One Strategy economics

Already correctly located under:

```text
09 Strategy/
```

Examples:

- RF-One commercial value;
- B2B ROI;
- counterfactual value attribution.

### Customer business finance/performance semantics

Potential reusable business Domain concepts such as:

- revenue;
- cost;
- margin;
- cash flow;
- budget;
- P&L;
- financial periods;
- financial targets;
- performance indicators.

Determine whether current evidence is sufficient to justify a future Shared Financial/Performance Domain.

Do not create finance ontology.

Recommend:

- create future Shared Domain;
- treat as Product capability for now;
- leave unmodeled until actual use cases require it.

---

## G. Strategic Planning

Separate:

### RF-One company Strategy
Already under `09 Strategy/`.

from:

### customer business planning
Potential concepts:

- expansion;
- investment;
- scenarios;
- business plans;
- location growth;
- long-term customer Goals.

Determine whether customer-level Strategic Planning is best understood as:

- Core Goal/Decision use only;
- Shared Domain knowledge;
- Product capability;
- combination of Shared Domain + Product workflow.

Do not introduce `Mission` or other new Core primitives.

---

## H. Customers

TASK_CORE_008 classified historical Customers as Restaurant Domain.

Review whether `Customer` is actually:

- Restaurant-specific;
- generic Shared business concept;
- Product/CRM capability;
- a generic Entity role represented differently by each Domain.

Use evidence from current files and architecture.

Do not create Customer ontology.

---

## I. Suppliers

Review whether Supplier semantics are:

- adequately Restaurant/Purchasing-specific today;
- generic enough for a future Procurement/Supplier Shared Domain;
- better left inside Purchasing until a second Domain requires them.

Use the rule:

> Reuse must be earned.

Do not prematurely extract.

---

## J. Business Profile

Review the historical `Business Profile` classification and current Restaurant model.

Determine whether the underlying concepts are:

- Restaurant business profile;
- generic organization/operational-unit configuration;
- already covered by Core Entity/Corporate/Brand/Operational Unit concepts;
- future Product onboarding/profile capability.

Avoid duplicating Core.

---

# Desired target model

Do not assume this exact structure is correct, but evaluate whether RF-One may eventually need something like:

```text
01 Domains/
├── _Shared/
│   ├── Environment/
│   ├── Commercial Catalog/
│   ├── Workforce/
│   ├── Marketing/
│   ├── Finance/
│   └── ...
└── Restaurant/
```

The report must be conservative.

It is acceptable to recommend:

> Do not create this Shared Domain yet.

where evidence is insufficient.

---

# Decision criteria

For each candidate area evaluate:

1. **Semantic universality across businesses**
2. **Current evidence of reuse**
3. **Risk of duplication if left Domain-specific**
4. **Risk of premature abstraction if extracted**
5. **Relationship to Core**
6. **Relationship to Product**
7. **Relationship to Strategy**
8. **Expected commercial importance**
9. **Current repository maturity**

Use these criteria consistently.

---

# Expected output

Return a **Cross-Layer Architecture and Shared Domain Review Report** with exactly these sections.

## A. Executive summary

State the recommended architectural direction.

Explicitly identify which Shared Domains, if any, are mature enough to create next.

---

## B. Candidate classification matrix

Provide:

| Area | Current layer | Recommended future layer | Create now? | Confidence | Reason |
|---|---|---|---|---|---|

Include at minimum:

- Commercial Catalog
- Marketing
- Reputation
- Workforce / Personnel
- Equipment
- Facilities
- Financial Performance
- Strategic Planning
- Customers
- Suppliers
- Business Profile

---

## C. Commercial Catalog recommendation

Provide a concept-level analysis.

If recommending partial extraction, identify the exact concepts that appear generic versus Restaurant-specific.

Do not provide migration commands.

---

## D. Marketing and Reputation recommendation

State the proposed conceptual relationship between Brand, Marketing, Reputation, and Restaurant-specific execution.

---

## E. Workforce / Selection / Training recommendation

Explain whether these should become:

- one Domain;
- multiple Domains;
- Domain + Product capabilities;
- or remain deferred.

---

## F. Equipment and Facilities recommendation

Explain whether abstraction is justified now.

---

## G. Financial Performance recommendation

Separate RF-One Strategy economics from customer-business financial semantics and recommend the appropriate future architecture.

---

## H. Strategic Planning recommendation

Separate RF-One Strategy from customer planning and recommend Domain/Product/Core responsibilities.

---

## I. Customer and Supplier recommendation

Explain whether each should remain Restaurant/Purchasing-local or become reusable Shared concepts.

---

## J. Business Profile recommendation

Explain whether Business Profile is really Domain knowledge or a composition of existing Core + Product onboarding/configuration.

---

## K. Proposed Shared Domain roadmap

Provide a phased roadmap such as:

```text
Phase 1 — create now
Phase 2 — create after evidence
Phase 3 — defer
```

Only include areas justified by the analysis.

---

## L. Repository movement implications

For future implementation only, identify which existing files/directories would eventually move if the recommendations are approved.

Do not execute moves.

---

## M. Product Owner decisions required

List only genuine decisions that cannot be resolved from repository evidence.

---

## N. Git status / scope confirmation

Confirm:

- no repository file modified;
- only `07 Tasks/Reports/TASK_CORE_009_REPORT.md` was created;
- no directory moved;
- no Git commit.

---

# Restrictions

Do not:

- modify any existing file;
- create any file except `07 Tasks/Reports/TASK_CORE_009_REPORT.md`;
- create Shared Domains;
- move Commercial Catalog;
- rewrite Restaurant;
- modify Core;
- modify Strategy;
- modify Product;
- modify Software;
- modify Archive;
- make a Git commit.

This task is analysis only.

---

# Required report file

Create:

```text
07 Tasks/Reports/TASK_CORE_009_REPORT.md
```

containing the complete Cross-Layer Architecture and Shared Domain Review Report with sections A–N above.

# Final response

After creating the report, return only:

1. a short completion summary;
2. the exact report path:

```text
07 Tasks/Reports/TASK_CORE_009_REPORT.md
```

Do not implement the recommendations.

Stop.
