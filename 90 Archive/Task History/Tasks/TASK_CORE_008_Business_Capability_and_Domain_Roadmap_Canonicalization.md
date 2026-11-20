# TASK_CORE_008 — Business Capability and Domain Roadmap Canonicalization

## Objective

Canonicalize the useful parts of the historical RF-One `Knowledge Domains` taxonomy without confusing historical “knowledge areas” with the modern architectural concept of `Domain`.

This task must produce two clearly separated outputs:

1. a **business capability / coverage map** at Strategy level;
2. a **Restaurant Domain roadmap** containing only the areas that genuinely belong to Restaurant knowledge.

The purpose is to preserve the planning value of the legacy taxonomy while enforcing:

> **Core ≠ Domain ≠ Product ≠ Runtime ≠ Strategy**

Do not create 18 new Domains.

Do not modify Core.

Do not design Products or Software implementation.

Do not make a Git commit.

---

# Mandatory first steps

1. Read `CLAUDE.md` completely.
2. Read:
   - `07 Tasks/Backlog/LEGACY_KNOWLEDGE_RECONCILIATION_BACKLOG.md`
   - `07 Tasks/TASK_CORE_004_Legacy_Knowledge_Reconciliation_Review.md`
   - `07 Tasks/TASK_CORE_006_Core_Legacy_Knowledge_Canonicalization.md`
   - `07 Tasks/TASK_CORE_007_Strategy_Legacy_Knowledge_Canonicalization.md`
   - `07 Tasks/Reports/TASK_CORE_006_REPORT.md`
   - `07 Tasks/Reports/TASK_CORE_007_REPORT.md`
3. Read current:
   - `01 Domains/README.md`
   - `01 Domains/Restaurant/README.md`
   - `01 Domains/_Shared/Environment/README.md`
   - `02 Products/README.md`
   - `09 Strategy/README.md`
   - `09 Strategy/00_RF-One_Strategy.md`
4. Read the complete historical taxonomy:
   - `90 Archive/Legacy Repository/X00 Knowledge Repository/05 Knowledge Domains/README.md`
5. Inspect the current `01 Domains/Restaurant/` directory to determine which historical knowledge areas already have canonical material.
6. Run `git status` before editing.

The Archive remains non-authoritative. Use the historical taxonomy only as planning input.

---

# Approved interpretation

The old `Knowledge Domains` taxonomy is **not** modern RF-One Domain ontology.

It is best understood as a historical:

```text
business knowledge / capability / coverage map
```

It mixes several different modern layers, including:

- Restaurant-specific knowledge;
- cross-business knowledge;
- Product capabilities;
- Strategy areas;
- Software/AI capability;
- organizational/business functions.

This task must separate those meanings explicitly.

---

# Classification model

Every historical knowledge area must be classified into exactly one primary category.

## A. Restaurant Domain

Use when the knowledge is intrinsically part of restaurant operations or restaurant business semantics.

Examples may include:

- Menu;
- Recipes;
- Purchasing;
- Inventory;
- Suppliers;
- restaurant Operations;
- restaurant-specific Sales semantics.

Do not classify something as Restaurant merely because the first RF-One customer happens to be a restaurant.

---

## B. Shared Domain candidate

Use when the knowledge is reusable across many business Domains but is still business/domain knowledge rather than universal Core ontology.

Possible examples:

- Workforce/Personnel;
- Equipment;
- Facilities;
- Marketing;
- Legal/Compliance;
- Financial operations.

Do not create these future Domains in this task.

Only identify them as candidates.

---

## C. Strategy / business capability

Use when the item describes RF-One's desired business coverage, strategic management capability, performance management, reputation, planning, or other company/product-business concern rather than Domain semantics.

---

## D. Product capability

Use when the item is better understood as a capability that a Product may expose across one or more Domains rather than as knowledge ontology itself.

Do not create a Product specification.

---

## E. Software / Intelligence capability

Use when the item is an implementation/intelligence capability, not business knowledge.

Historical `Artificial Intelligence` must not become a business Domain merely because it appeared in the old taxonomy.

---

## F. Archive-only / superseded

Use only if an area has no current planning value or is fully absorbed by a clearer modern concept.

Be conservative.

---

# Canonical files authorized

You may create:

```text
09 Strategy/04_Business_Capability_Coverage.md
01 Domains/Restaurant/Roadmap.md
07 Tasks/Reports/TASK_CORE_008_REPORT.md
```

You may modify:

```text
09 Strategy/README.md
01 Domains/README.md
01 Domains/Restaurant/README.md
PROJECT_STATE.md
```

Modify only what is necessary.

Do not modify any other file.

---

# Required Strategy document

Create:

```text
09 Strategy/04_Business_Capability_Coverage.md
```

This document must explain that RF-One's commercial ambition may span many business capability areas, but those areas are not automatically architectural Domains.

Include a table with every historical Knowledge Domain entry.

Suggested columns:

| Legacy ID | Historical name | Modern classification | Current coverage | Future direction | Notes |
|---|---|---|---|---|---|

Use the exact legacy IDs/names from the archived source.

For `Current coverage`, use categories such as:

- Existing canonical Domain content
- Partial canonical content
- Strategy coverage only
- No canonical coverage yet
- Software capability
- Historical only

For `Future direction`, use clear terms such as:

- Expand Restaurant Domain
- Future Shared Domain candidate
- Future Product capability
- Strategy capability
- Software/Intelligence capability
- Leave unmodeled until needed

Do not invent a new modern Domain for each row.

---

# Required Restaurant roadmap

Create:

```text
01 Domains/Restaurant/Roadmap.md
```

This must be a Domain knowledge roadmap, not a Product roadmap and not a Software backlog.

It should classify Restaurant knowledge into:

## Current canonical coverage

Areas already represented by actual repository content.

Examples should be based only on current files, such as:

- Purchasing;
- Commercial Catalog;
- Sales scaffolding/integration work;
- Restaurant model;
- Menu/ServiceSequence placeholders where relevant.

Do not claim empty scaffolding is implemented knowledge.

Clearly distinguish:

```text
documented
partial
placeholder/scaffold
not yet modeled
```

## Planned Restaurant knowledge areas

Include only historical taxonomy areas that genuinely belong to Restaurant and remain useful future Domain work.

Do not automatically include:

- Artificial Intelligence;
- Strategic Planning;
- general company Strategy;
- generic corporate finance;
- other cross-business areas

unless repository evidence shows they are truly restaurant-specific knowledge.

## Relationship to Shared Domains

State that some business concerns relevant to restaurants may eventually come from shared reusable Domains rather than being duplicated inside Restaurant.

Possible examples may include Workforce, Marketing, Facilities, Equipment, Legal/Compliance, depending on the taxonomy and existing evidence.

Do not create those Domains in this task.

---

# `01 Domains/README.md`

Update only as needed to explain:

- a Domain is reusable structured knowledge;
- a capability/coverage area is not automatically a Domain;
- historical Knowledge Domains were a planning taxonomy, not the current architectural definition;
- `_Shared/` may host reusable business/environment knowledge when justified.

Keep it concise.

---

# `01 Domains/Restaurant/README.md`

Update to link to:

```text
Roadmap.md
```

and distinguish:

- current canonical modules/knowledge;
- placeholders/scaffolding;
- future roadmap.

Do not rewrite the Restaurant ontology.

Do not fill zero-byte files.

Do not redesign Purchasing or Commercial Catalog.

---

# `09 Strategy/README.md`

Add the new capability-coverage document to the canonical Strategy index.

Do not otherwise rewrite Strategy.

---

# `PROJECT_STATE.md`

Update only if necessary to reflect that:

- the legacy Knowledge Domains taxonomy has been reconciled;
- RF-One now has a canonical business capability coverage map and Restaurant Domain roadmap.

Do not add speculative completion claims.

---

# Important classification safeguards

## Financial Performance

Do not automatically make Financial Performance a universal Domain.

Classify based on the historical wording and modern RF-One architecture.

It may be:

- Shared Domain candidate;
- Product capability;
- Strategy/business-performance capability;

depending on what the legacy source actually describes.

Explain the choice.

---

## Personnel / Workforce

Do not assume historical `Personnel` maps one-to-one to a future `Workforce` Domain.

It may be evidence for a future reusable Workforce/People Domain, but the final ontology is not approved here.

Classify it as a candidate only.

---

## Marketing / Reputation

Do not force these into Restaurant.

They may be cross-business Shared Domain or Strategy/Product capability candidates.

Preserve their relevance while keeping layer boundaries clear.

---

## Strategic Planning

Do not treat Strategic Planning as a Restaurant Domain simply because the taxonomy was originally restaurant-oriented.

It is likely Strategy/Product/business-management capability unless the source supports a Domain-specific semantic reason.

---

## Artificial Intelligence

Do not classify AI as a business Domain.

Intelligence Engines are components of RF-One, not RF-One itself.

Classify appropriately as Software/Intelligence capability.

---

# Current coverage verification

For each area classified as currently covered, verify actual repository evidence.

Do not call an area “implemented” merely because an empty file exists.

Use distinctions such as:

- Canonically modeled
- Substantially documented
- Partial
- Placeholder only
- Not yet represented

For example, empty Clover/Toast/Menu/ServiceSequence files must not be described as completed Domain knowledge.

---

# Naming

Use the term:

```text
Business Capability Coverage
```

for the Strategy-level map.

Use:

```text
Restaurant Domain Roadmap
```

for the Domain-level roadmap.

Avoid reusing `Knowledge Domain` as a modern architectural term except when referring historically to the archived taxonomy.

---

# Validation

After editing:

1. Verify every historical taxonomy entry appears exactly once in the Strategy coverage map.
2. Verify no historical knowledge area has been silently promoted to a modern Domain without justification.
3. Verify `Artificial Intelligence` is not classified as a business Domain.
4. Verify empty/scaffold files are not presented as implemented knowledge.
5. Verify Strategy and Domain roadmap do not duplicate each other:
   - Strategy map = breadth/coverage/classification;
   - Restaurant roadmap = restaurant knowledge development.
6. Verify Markdown links.
7. Run `git status`.
8. Do not commit.

---

# Required report

Create:

```text
07 Tasks/Reports/TASK_CORE_008_REPORT.md
```

with exactly these sections.

## A. Summary

What was reconciled and why.

## B. Historical taxonomy classification

Provide the complete classification table for all historical entries.

## C. Restaurant roadmap

Summarize:

- current canonical coverage;
- partial/scaffold coverage;
- planned Restaurant knowledge areas.

## D. Shared Domain candidates

List areas that appear reusable across businesses and should not be duplicated inside Restaurant.

Do not create them.

## E. Strategy / Product / Software classifications

Explain the historical entries that do not belong in modern Domain ontology.

## F. Files created/modified

Exact paths and changes.

## G. Layer integrity review

Confirm:

- no new modern Domain was created solely because it existed in the historical taxonomy;
- no Core change;
- no Product specification;
- no Software change.

## H. Remaining Product Owner decisions

List only genuine unresolved architectural decisions.

## I. Git status / scope confirmation

Confirm:

- no Core modification;
- no Software modification;
- no Archive modification;
- no Git commit.

---

# Restrictions

Do not:

- modify `00 Core/`;
- create new top-level Domains;
- create Workforce/Marketing/Finance/etc. Domains;
- modify `02 Products/`;
- modify `03 Software/`;
- modify `04 Generated Documentation/`;
- modify `05 Research/`;
- modify `06 Meetings/`;
- modify `08 External/`;
- modify `90 Archive/`;
- fill empty Restaurant scaffold files;
- redesign existing Restaurant concepts;
- make a Git commit.

---

# Final response

After creating the report, return only:

1. a short completion summary;
2. the exact report path:

```text
07 Tasks/Reports/TASK_CORE_008_REPORT.md
```

Then stop.
