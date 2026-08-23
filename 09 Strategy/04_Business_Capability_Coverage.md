# Business Capability Coverage

**Version:** 1.0
**Status:** Approved
**Module:** Strategy

---

## Related documents

- [00_RF-One_Strategy.md](00_RF-One_Strategy.md)
- [01_Economic_Value_and_Measurement.md](01_Economic_Value_and_Measurement.md)
- [README.md](README.md) — layer authority and scope
- [../01 Domains/README.md](../01%20Domains/README.md)
- [../01 Domains/Restaurant/Roadmap.md](../01%20Domains/Restaurant/Roadmap.md)
- Source taxonomy: [../90 Archive/Legacy Repository/X00 Knowledge Repository/05 Knowledge Domains/README.md](../90%20Archive/Legacy%20Repository/X00%20Knowledge%20Repository/05%20Knowledge%20Domains/README.md)
- Backlog authorizing this reconciliation: [../07 Tasks/Backlog/LEGACY_KNOWLEDGE_RECONCILIATION_BACKLOG.md](../07%20Tasks/Backlog/LEGACY_KNOWLEDGE_RECONCILIATION_BACKLOG.md), Section G.

---

## Purpose

RF-One's commercial ambition may span many business capability areas — financial performance, sales, menu, purchasing, personnel, marketing, and more. **A business capability area is not automatically an architectural Domain.**

This document is the canonical breadth/coverage map of the areas RF-One may eventually address commercially. It classifies each historical `Knowledge Domain` entry from the legacy taxonomy into the modern layer it actually belongs to:

> **Core ≠ Domain ≠ Product ≠ Runtime ≠ Strategy**

It does not itself define Domain ontology, Product configuration, or Software behavior. Where a row's future direction is Domain work, the detail belongs to a Domain roadmap (e.g. [../01 Domains/Restaurant/Roadmap.md](../01%20Domains/Restaurant/Roadmap.md)), not to this document.

---

## What this document is not

- It is not a Domain. Classifying an area here does not create a Domain.
- It is not a Product roadmap or backlog.
- It is not a Software implementation plan.
- It is not a re-approval of the legacy taxonomy's own claims (e.g. its framing of "Financial Performance" or "Artificial Intelligence") — those are reinterpreted below under current RF-One architecture.

---

## Historical source

The legacy `Knowledge Domains` taxonomy (`90 Archive/Legacy Repository/X00 Knowledge Repository/05 Knowledge Domains/README.md`, KD-001 through KD-018) predates the current Core/Domain/Product/Runtime/Strategy separation. It mixed restaurant-specific knowledge, cross-business knowledge, Product capability, Strategy areas, Software/AI capability, and organizational functions under one flat list of "domains."

The Archive is non-authoritative. This table is the canonical reinterpretation; the legacy document remains historical reference only.

---

## Coverage table

| Legacy ID | Historical name | Modern classification | Current coverage | Future direction | Notes |
|---|---|---|---|---|---|
| KD-001 | Business Profile | Restaurant Domain | Partial canonical content | Expand Restaurant Domain | `Model/OU-Restaurant.md` and `Model/OperationalArea.md` already model restaurant business-profile facets (characteristics, capacity, operating areas). Generic company/corporate identity (Company, Locations) is already Core/Corporate territory, not a new Domain concern. |
| KD-002 | Financial Performance | Strategy / business capability | Strategy coverage only | Strategy capability | Covered at the commercial-strategy level by `01_Economic_Value_and_Measurement.md` (measurable economic value, Cash-Based Profit as one historical metric candidate, counterfactual measurement). Not classified as a Domain: profitability/KPI measurement is a cross-business Strategy concern, not restaurant-intrinsic knowledge. Operational/transactional financial data modeling (e.g. cost lines, budgets) remains a possible future Shared Domain candidate if Domain-level evidence justifies it — not created here. |
| KD-003 | Sales | Restaurant Domain | Partial canonical content | Expand Restaurant Domain | `Sales/Combo.md` is documented. `Sales/Clover/*` (10 files) and `Sales/Toast/README.md` are empty scaffold files — POS integration knowledge, not implemented Domain knowledge. |
| KD-004 | Customers | Restaurant Domain | No canonical coverage yet | Expand Restaurant Domain | `Restaurant/README.md` already lists "Customer Knowledge" in Domain scope; no dedicated canonical file exists yet. |
| KD-005 | Menu | Restaurant Domain | Placeholder/scaffold | Expand Restaurant Domain | `Menu.md` exists but is empty (0 bytes). Commercial Catalog already models the generic Item/Price/Category concepts a future Menu specialization would build on. |
| KD-006 | Recipes | Restaurant Domain | Not yet modeled | Expand Restaurant Domain | No `Recipes.md` exists. `Model/Ingredient.md` is a two-line placeholder ("See generated content placeholder"). Ingredient/Product/Specification entities are already defined in `Purchasing/EntityDefinitions.md` and support future Recipes work. |
| KD-007 | Purchasing | Restaurant Domain | Existing canonical Domain content | Expand Restaurant Domain | The most mature area of current Restaurant Domain coverage: 16 substantive files under `Purchasing/` (business rules, entity definitions, data dictionary, workflow, testing strategy, roadmap, etc.). |
| KD-008 | Inventory | Restaurant Domain | No canonical coverage yet | Expand Restaurant Domain | Explicitly out of scope of the Purchasing Module (`Purchasing/README.md`, "Out of Scope"). Listed as "planned" in `Restaurant/README.md`. |
| KD-009 | Products | Restaurant Domain | Partial canonical content | Expand Restaurant Domain | Covered by Commercial Catalog (`Item.md`, `ItemCategory.md`, `Brand.md`, `UnitOfMeasure.md`, …) and `Model/Product.md`, `Model/Specification.md`. Note: `Sales/Combo.md` states Commercial Catalogue concepts are designed to apply across "restaurants, retail, hospitality, healthcare and future business domains." Approved Product Owner decision (TASK_CORE_010): Commercial Catalog remains under Restaurant now and is the **highest-confidence extraction candidate — trigger required** (extract to `_Shared/Commercial Catalog/` when a second genuine Domain or Product needs the same catalog semantics). Not relocated in this task; see Restaurant Roadmap. |
| KD-010 | Suppliers | Restaurant Domain | Partial canonical content | Expand Restaurant Domain | `Supplier` and `Supplier Product` are documented as entities inside `Purchasing/EntityDefinitions.md`; no standalone `Supplier.md` file exists yet. |
| KD-011 | Operations | Restaurant Domain | Placeholder/scaffold | Expand Restaurant Domain | `ServiceSequence.md` exists but is empty (0 bytes). `Model/OperationalArea.md` lists Opening/Closing Procedures as Processes executed by Operational Areas, but no dedicated Operations documentation exists. |
| KD-012 | Personnel | Shared Domain candidate | No canonical coverage yet | Future Shared Domain candidate | Per `CLAUDE.md` and the reconciliation backlog, historical `Personnel` is evidence for, but not equivalent to, a future reusable Workforce/People Domain. Classified as candidate only; not created here. |
| KD-013 | Equipment | Shared Domain candidate | No canonical coverage yet | Future Shared Domain candidate | Equipment appears only as a related concept inside `Model/OperationalArea.md`; no dedicated entity file exists. `CLAUDE.md` lists Equipment explicitly as a Shared Domain candidate example. |
| KD-014 | Facilities | Restaurant Domain (restaurant-specific part) / Shared Domain candidate (generic part) | Partial canonical content for restaurant-specific areas | Expand Restaurant Domain for restaurant-specific areas; future Shared Domain candidate for generic facility management | `Model/OperationalArea.md` already substantially documents Kitchen, Dining Room, Bar, Storage as restaurant Operational Areas. Generic building/facility-management concerns (Utilities, Maintenance, Floor Plans) are unmodeled and reusable across businesses — not restaurant-intrinsic. |
| KD-015 | Marketing | Shared Domain candidate | No canonical coverage yet | Future Shared Domain candidate / future Product capability | Per the reconciliation backlog and `CLAUDE.md`, Marketing execution knowledge is not automatically Restaurant Domain ontology. Note: `Restaurant/README.md` currently lists "Marketing" in Scope and "Marketing (planned)" in Current Modules — this is an existing tension between restaurant-specific marketing execution and a generic reusable Marketing capability, not resolved by this task (see Restaurant Roadmap, Section "Relationship to Shared Domains", and Report Section H). |
| KD-016 | Reputation | Shared Domain candidate | No canonical coverage yet | Deferred — not created as its own Domain | Reviews, ratings, feedback and competitor tracking are reusable across any customer-facing business, not restaurant-intrinsic. Approved Product Owner decision (TASK_CORE_010): current working assumption is that Reputation is more likely to become part of a future Marketing/Customer Engagement capability than an independent Domain; not a permanent prohibition. |
| KD-017 | Strategic Planning | Strategy / business capability | Strategy coverage only (RF-One-company level) | Strategy capability / future Product capability | `00_RF-One_Strategy.md` addresses strategic horizons at the RF-One-company level. Customer-level expansion/new-locations/investment planning is not yet covered by any canonical document. Distinct from restaurant-level operational "Forecasting" already anticipated as a planned Restaurant Domain module in `Restaurant/README.md` — that remains Restaurant Domain future work, not this entry. |
| KD-018 | Artificial Intelligence | Software / Intelligence capability | Software capability | Software/Intelligence capability | Intelligence Engines are RF-One components, not RF-One itself and not a business Domain — see `00 Core/ConceptualArchitecture/06_Business_Autopilot_and_Intelligence_Engine.md` and `02_Service_Delivery_and_Knowledge_Advantage.md`. No Software file is modified by this task. |

---

## Reading the table

- **Restaurant Domain** rows point to `01 Domains/Restaurant/Roadmap.md` for the detailed current-coverage/planned breakdown; this table only records the classification and headline evidence.
- **Shared Domain candidate** rows are not created as Domains here. They are recorded so a future Domain task does not have to re-derive this analysis.
- **Strategy / business capability** rows are covered (or to be covered) by the other `09 Strategy/` documents, not by a Domain.
- **Software / Intelligence capability** (KD-018 only) is explicitly excluded from Domain ontology per `CLAUDE.md` and the approved architectural safeguards.

No row in this table was used to create a new modern Domain, a Product specification, or a Software change.

---

## Approved to create now vs. future candidate

Every "Shared Domain candidate" row in this table (KD-012 Personnel, KD-013 Equipment, KD-014 Facilities generic part, KD-015 Marketing, KD-016 Reputation) is a **future candidate only** — none is **approved to create now**. This distinction was confirmed by TASK_CORE_009 (analysis) and canonicalized as a Product Owner decision by TASK_CORE_010: no new Shared Domain (Workforce, Marketing, Reputation, Finance/Financial Performance, Equipment, Facilities, Strategic Planning, Customer, Supplier, or Business Profile) is created in this task or implied to exist by any row above. Reuse must be earned before any of these rows is promoted.

Commercial Catalog is a special case: although it physically sits under `01 Domains/Restaurant/` today (see KD-009 note above), it is recorded as the **highest-confidence future Shared Domain extraction candidate**, distinct from the other, thinner candidates in this table. Its extraction remains trigger-gated, not approved for execution.

See `01 Domains/Restaurant/Roadmap.md`, "Cross-Domain candidates and extraction triggers," for the full set of approved decisions on Financial Performance (Product/use-case first), Strategic Planning (no new Domain or Core primitive), Customer and Supplier (remain local for now), and Workforce/Selection/Training sequencing.
