# TASK_CORE_010 — Cross-Layer Architecture Decisions Canonicalization

## Objective

Canonicalize the Product Owner decisions that follow from:

```text
07 Tasks/Reports/TASK_CORE_009_REPORT.md
```

without creating premature Shared Domains or moving existing Domain content.

This task closes the architectural review cycle started by TASK_CORE_008 and TASK_CORE_009.

The key outcome is to make the current decisions explicit in canonical planning/governance documentation so future developers and AI agents do not repeatedly reopen the same questions.

This is a **documentation-only canonicalization task**.

Do not create Shared Domains.
Do not move Commercial Catalog.
Do not modify Core ontology.
Do not change Software.
Do not make a Git commit.

---

# Mandatory first steps

1. Read `CLAUDE.md` completely.

2. Read:
   - `07 Tasks/TASK_CORE_008_Business_Capability_and_Domain_Roadmap_Canonicalization.md`
   - `07 Tasks/Reports/TASK_CORE_008_REPORT.md`
   - `07 Tasks/TASK_CORE_009_Cross_Layer_Architecture_and_Shared_Domain_Review.md`
   - `07 Tasks/Reports/TASK_CORE_009_REPORT.md`
   - `07 Tasks/Backlog/LEGACY_KNOWLEDGE_RECONCILIATION_BACKLOG.md`

3. Read current:
   - `01 Domains/README.md`
   - `01 Domains/Restaurant/README.md`
   - `01 Domains/Restaurant/Roadmap.md`
   - `09 Strategy/README.md`
   - `09 Strategy/04_Business_Capability_Coverage.md`
   - `PROJECT_STATE.md`

4. Inspect:
   - `01 Domains/Restaurant/Commercial Catalog/README.md`
   - `01 Domains/Restaurant/Sales/Combo.md`
   - `01 Domains/Restaurant/Purchasing/DevelopmentRoadmap.md`
   - `01 Domains/Restaurant/Model/OU-Restaurant.md`
   - `01 Domains/Restaurant/Model/OperationalArea.md`

5. Run `git status` before editing.

Preserve all existing changes from TASK_CORE_006–009.

---

# Product Owner decisions to canonicalize

The following decisions are approved.

## 1. No new Shared Domain now

Do not create any new Shared Domain in this task.

Current evidence is not sufficient to justify creating:

- Workforce;
- Marketing;
- Reputation;
- Finance / Financial Performance;
- Equipment;
- Facilities;
- Strategic Planning;
- Customer;
- Supplier;
- Business Profile;

as new Shared Domains.

The rule remains:

> **Reuse must be earned.**

A Shared Domain should be created only when actual semantic reuse or a concrete second consumer justifies it.

---

## 2. Commercial Catalog remains in Restaurant for now

Current location remains:

```text
01 Domains/Restaurant/Commercial Catalog/
```

Do not move it.

However, record that it is the **highest-confidence future Shared Domain extraction candidate**.

Approved extraction trigger:

> Extract Commercial Catalog to `01 Domains/_Shared/Commercial Catalog/` when a second genuine Domain or Product requires the same catalog semantics.

The current architecture should not pretend actual reuse exists before that happens.

Do not split the folder concept-by-concept.

If extraction occurs later, the default expectation is that the whole coherent model moves together unless new evidence creates a natural seam.

---

## 3. Marketing future model

Approved conceptual direction:

```text
Brand (Core)
→ generic Marketing knowledge (future Shared Domain candidate)
→ Restaurant-specific marketing execution (Restaurant specialization)
```

Generic Marketing may eventually include concepts such as:

- campaigns;
- channels;
- advertising;
- social media;
- promotions;
- loyalty mechanics;
- audience targeting;
- generic engagement workflows.

Restaurant-specific execution may include:

- menu promotion;
- seasonal restaurant offers;
- local-store execution;
- promotion tied to Restaurant Menu / Commercial Catalog;
- restaurant-specific guest communication.

Do not create Marketing now.

Update current Restaurant planning documentation so `Marketing (planned)` is not interpreted as a commitment that all Marketing ontology belongs permanently inside Restaurant.

---

## 4. Reputation remains deferred

Do not create Reputation as its own Domain.

Current working assumption:

> Reputation is more likely to become part of a future Marketing / Customer Engagement capability than an independent Domain.

This is not a permanent prohibition.

If future modeling reveals substantial independent semantics, it may be reconsidered.

---

## 5. Workforce before Selection / Training

Approved sequencing principle:

When People/Workforce modeling becomes necessary, first establish reusable Workforce semantics such as:

- worker/person role in the business;
- role;
- assignment;
- responsibility;
- schedule;
- skills/capabilities;
- availability;
- performance-related facts where appropriate.

Only after those semantics are stable should RF-One design Selection, Training, and Performance capabilities on top of them.

Approved future conceptual direction remains:

```text
Goals
→ Brand
→ Service Model
→ Behaviors
→ Selection / Training / Performance
```

but no new Domain or Product capability is created in this task.

Do not choose a final Domain name (`Workforce`, `People`, `Personnel`, `HR`) yet.

---

## 6. Equipment and Facilities remain deferred

Do not create Shared Domains for Equipment or Facilities.

Restaurant-specific physical-area modeling remains in Restaurant.

Future generic concepts such as:

- asset lifecycle;
- maintenance;
- utilities;
- floor plans;
- generic facility management;

may later justify a reusable Shared Domain.

If future evidence supports abstraction, consider whether a combined:

```text
Asset & Facilities
```

area is more coherent than two thin independent Domains.

Do not decide that architecture now.

---

## 7. Financial Performance: Product capability first, ontology later

Keep RF-One's own commercial/economic strategy under:

```text
09 Strategy/
```

For customer-facing financial/performance needs:

- do not create a general Finance Shared Domain yet;
- allow concrete Products/Restaurant capabilities to consume existing Domain data;
- use actual use cases to discover which finance/performance semantics are genuinely reusable.

Approved near-term direction:

> Build the first customer-facing financial/performance capability from real Domain data before inventing a general Finance ontology.

Existing examples such as Restaurant Food Cost may remain Restaurant-specific until evidence supports generalization.

A future Shared Finance/Performance Domain remains possible.

---

## 8. Strategic Planning does not require a new Domain now

Customer-level strategic planning should initially use existing Core concepts:

- Desire;
- Goal;
- Reality Check;
- Decision;
- Action;
- Outcome;
- Learning;
- Temporal Coherence.

Do not create `Strategic Planning` as a Shared Domain merely because the legacy taxonomy contained that name.

If reusable planning methods later emerge, they are more likely to become Product capabilities consuming Core + Domain knowledge.

Do not introduce `Mission` or other new Core primitives.

---

## 9. Customer remains Restaurant-local for now

Do not create a Shared Customer Domain.

Current interpretation:

- Core provides generic Entity / Role / Relationship semantics;
- Restaurant Domain may model restaurant-specific customer/guest behavior and knowledge;
- generic CRM/loyalty functionality may later become a Product or Shared capability if actual reuse emerges.

Do not create Customer ontology in this task.

---

## 10. Supplier remains Purchasing-local for now

Do not extract Supplier from Restaurant Purchasing.

Current Supplier semantics are tightly coupled to Purchasing.

Approved trigger for reconsideration:

> Re-evaluate Supplier abstraction when a second Domain or reusable Procurement capability needs supplier semantics independently of the current Restaurant Purchasing model.

Do not create a Procurement Domain now.

---

## 11. Business Profile does not become a Domain

Do not create `Business Profile` as a separate Domain.

Current interpretation:

Business Profile is primarily a composition of:

- existing Core concepts such as Corporate, Brand, Operational Unit;
- Restaurant specialization such as OU-Restaurant / OperationalArea;
- Product onboarding/configuration workflows.

The remaining Restaurant-specific profile gaps identified by TASK_CORE_009 (for example Cuisine / Service Style) may later be added to the appropriate existing Restaurant model.

Do not implement those attributes in this task.

---

# Canonical files authorized

You may modify only:

```text
01 Domains/Restaurant/README.md
01 Domains/Restaurant/Roadmap.md
09 Strategy/04_Business_Capability_Coverage.md
07 Tasks/Backlog/LEGACY_KNOWLEDGE_RECONCILIATION_BACKLOG.md
PROJECT_STATE.md
```

You may create only:

```text
07 Tasks/Reports/TASK_CORE_010_REPORT.md
```

Do not modify all authorized files automatically.

Use the smallest coherent set.

---

# Required documentation changes

## Restaurant README

Clarify, minimally, that:

- Marketing is planned business coverage but its final architectural split is not fixed;
- generic Marketing is a future Shared Domain candidate;
- Restaurant-specific marketing execution may remain in Restaurant;
- Commercial Catalog remains here today but is the highest-confidence future Shared extraction candidate once a second consumer exists.

Do not rewrite the Restaurant README.

Do not claim future moves are already approved for execution.

---

## Restaurant Roadmap

Add or refine a section such as:

```text
Cross-Domain candidates and extraction triggers
```

Record at minimum:

- Commercial Catalog — stay now; extract on real second consumer;
- Marketing — generic/shared vs Restaurant specialization;
- Workforce — future shared candidate; establish semantics before Selection/Training;
- Financial Performance — Product/use-case first, ontology later;
- Equipment/Facilities — deferred;
- Supplier — Purchasing-local until second use case;
- Customer — Restaurant-local unless cross-business reuse emerges.

Keep the roadmap focused on planning, not ontology design.

---

## Business Capability Coverage

Update only where needed to reflect the approved decisions above.

The document should distinguish:

```text
future candidate
```

from:

```text
approved to create now
```

No row should imply that Marketing, Workforce, Finance, etc. already exist as Shared Domains.

Commercial Catalog may be marked as:

```text
highest-confidence extraction candidate — trigger required
```

---

## Legacy reconciliation backlog

Add a short final section recording that TASK_CORE_009/010 resolved the cross-layer Shared Domain questions.

Do not rewrite prior backlog decisions.

This section should preserve the key extraction triggers so archived legacy material does not need to be reopened later merely to answer these questions.

---

## PROJECT_STATE

Update only if necessary to record factually that:

- cross-layer review is complete;
- no new Shared Domain was created;
- Commercial Catalog is the leading future extraction candidate;
- Shared Domain creation remains evidence-triggered.

Do not add speculative implementation claims.

---

# Validation

After editing:

1. Verify no new Shared Domain directory exists.
2. Verify Commercial Catalog remains under Restaurant.
3. Verify Marketing is not described as fully Restaurant-only or already Shared.
4. Verify Reputation is not declared a standalone Domain.
5. Verify Workforce/Selection/Training sequencing is clear.
6. Verify Finance/Financial Performance is not turned into ontology prematurely.
7. Verify Strategic Planning is not turned into a Domain or new Core primitive.
8. Verify Customer and Supplier are not extracted.
9. Verify no Core file changed.
10. Run `git status`.
11. Do not commit.

---

# Required report

Create:

```text
07 Tasks/Reports/TASK_CORE_010_REPORT.md
```

with exactly these sections.

## A. Summary

What decisions were canonicalized.

## B. Commercial Catalog

State its current location and future extraction trigger.

## C. Marketing / Reputation

State the approved future split and current deferral.

## D. Workforce / Selection / Training

State the sequencing decision.

## E. Equipment / Facilities

State why they remain deferred.

## F. Financial Performance

State the Product/use-case-first decision.

## G. Strategic Planning

State why no new Domain is created.

## H. Customer / Supplier / Business Profile

State the current architectural treatment of each.

## I. Files modified

Exact paths and changes.

## J. Validation

Confirm the decisions are reflected without prematurely implementing them.

## K. Git status / scope confirmation

Confirm:

- no Core modification;
- no Product modification;
- no Software modification;
- no Archive modification;
- no Shared Domain created;
- no file moved;
- no Git commit.

---

# Restrictions

Do not:

- modify `00 Core/`;
- create Shared Domains;
- move Commercial Catalog;
- create Marketing;
- create Reputation;
- create Workforce;
- create Finance;
- create Procurement;
- create Strategic Planning;
- modify `02 Products/`;
- modify `03 Software/`;
- modify `90 Archive/`;
- implement Cuisine / Service Style attributes;
- make a Git commit.

---

# Final response

After creating the report, return only:

1. a short completion summary;
2. the exact report path:

```text
07 Tasks/Reports/TASK_CORE_010_REPORT.md
```

Then stop.
