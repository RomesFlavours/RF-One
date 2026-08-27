# Restaurant Domain Roadmap

**Version:** 1.0
**Status:** Approved
**Module:** Restaurant Domain

---

## Related documents

- [README.md](README.md) — Restaurant Domain purpose, scope and current modules
- [../../09 Strategy/04_Business_Capability_Coverage.md](../../09%20Strategy/04_Business_Capability_Coverage.md) — full business capability breadth/coverage classification
- [../Domain Architecture.md](../Domain%20Architecture.md) — cross-Domain conclusions on Restaurant's boundary, the transversal Domain Personnel Management (Workforce, Selection, Training, Performance, Personnel Decisions), and the remaining transversal Domain candidates (Customer Feedback, Review)
- Source taxonomy: [../../90 Archive/Legacy Repository/X00 Knowledge Repository/05 Knowledge Domains/README.md](../../90%20Archive/Legacy%20Repository/X00%20Knowledge%20Repository/05%20Knowledge%20Domains/README.md)

---

## Purpose

This is a **Restaurant Domain knowledge roadmap** — what restaurant business knowledge is already modeled, what is scaffolded but empty, and what genuinely restaurant-specific knowledge remains to be modeled.

It is **not** a Product roadmap (no pricing, go-to-market, or customer packaging decisions) and **not** a Software backlog (no implementation, database, or API planning). Those belong to `02 Products/` and `03 Software/` respectively.

For the broader business-capability classification — including areas that are Strategy, Shared Domain candidates, Product, or Software concerns rather than Restaurant Domain knowledge — see [09 Strategy/04_Business_Capability_Coverage.md](../../09%20Strategy/04_Business_Capability_Coverage.md). This document only develops the rows of that table classified as Restaurant Domain.

---

## 1. Current canonical coverage

Areas already represented by actual repository content, distinguished by how complete that content is.

### Documented

| Area | Evidence | Notes |
|---|---|---|
| Purchasing | `Purchasing/` (16 files: `README.md`, `BusinessRules.md`, `EntityDefinitions.md`, `DataDictionary.md`, `Workflow.md`, `AIResponsibilities.md`, `ValidationRules.md`, `TestingStrategy.md`, `DevelopmentRoadmap.md`, and others) | The most mature module. Models Supplier, Purchase Order, Purchase Document, Purchase Line, Supplier Product, Product, Specification, Ingredient, Validation Log as entities. |
| Commercial Catalog | `Commercial Catalog/` (17 files: `README.md`, `Catalogue.md`, `CatalogueVersion.md`, `Item.md`, `Price.md`, `Modifier.md`, `Bundle.md`, and others) | Models the generic commercial offering structure (Catalogue → Catalogue Version → Catalogue Entry → Item/Price/Availability/Modifiers). Design note: `Sales/Combo.md` states this structure is intended to apply across "restaurants, retail, hospitality, healthcare and future business domains" — see Section 3 below. |
| Restaurant business-profile model | `Model/OU-Restaurant.md`, `Model/OperationalArea.md` | Restaurant as a specialization of Core Operational Unit; Operational Areas (Kitchen, Bar, Dining Room, Storage, etc.) as a specialization of Core Operational Area. |
| Restaurant Organization (Profile, Areas, Roles, temporal Employee Assignment) | `Organization/` (TASK_RESTAURANT_001) | Restaurant identity ↔ Location; Operational Area vs. Physical Area as two distinct, Restaurant-configured concepts; Restaurant Role distinct from Clover SourceRole/systemRole; temporal Employee Assignment (Employee ↔ Operational Area ↔ Restaurant Role, `valid_from`/`valid_to`). Implemented in `03 Software/RF-One Data Store/` — see `RESTAURANT_PROFILE.md`. **Update (TASK_RESTAURANT_003):** Rome's Flavours' Profile is now bootstrapped from current Clover configuration (7 RestaurantRoles, 1 root OperationalArea, 24 prospective EmployeeAssignments from an explicit `T0`) — see `RESTAURANT_PROFILE.md` §6 and `Organization/README.md`, "Profile bootstrap from source configuration." |
| Restaurant Semantic Model (Domain vs. Profile vs. Instance, Area hierarchy semantics, consolidated invariants) | `Restaurant Semantic Model.md` (TASK_RESTAURANT_002) | The canonical, configuration-independent statement of Restaurant Domain semantics — points to `Organization/` for full concept definitions rather than duplicating them. Formally defines optional Operational Area / Physical Area parent-child hierarchy semantics (not yet reflected in the runtime schema — no current Restaurant Profile exists to contradict it). |
| Tips (post-hoc Tip allocation model and engine) | `Tips/` (TASK_TIPS_001, TASK_TIPS_002) | Tip as an observable Payment-attached fact; service-attribution boundary distinct from `Order.employee`/`Payment.employee`; temporal eligibility via Shift + Employee Assignment; Tip Policy/Tip Policy Component/Tip Calculation Run/Tip Allocation/Tip Calculation Issue schema and engine implemented in `03 Software/RF-One Data Store/`. As of TASK_RESTAURANT_003, EmployeeAssignments exist but no Rome's Flavours TipPolicy or service-attribution resolver is configured yet, so Tips remain correctly blocked (`NO_VALID_POLICY`) — see `RESTAURANT_PROFILE.md` and `validate_tips_readiness.py`. |

### Partial

| Area | Evidence | Notes |
|---|---|---|
| Sales | `Sales/Combo.md` | Only the Combo concept is documented. No other Sales entity (Order, Transaction, Discount, Tip) has a canonical file yet. |
| Products (restaurant-specific) | `Model/Product.md`, `Model/Specification.md` | Documented as generic culinary concepts (e.g. "Tomato," "Flour") distinct from Supplier Products; used by Purchasing. |
| Suppliers | `Purchasing/EntityDefinitions.md` (Supplier, Supplier Product sections) | Defined as entities inside the Purchasing module documentation; no standalone `Supplier.md` file exists. |

### Placeholder / scaffold

These files exist but contain no substantive knowledge. They must not be described as implemented Domain knowledge.

| File | Size | Notes |
|---|---|---|
| `Menu.md` | 0 bytes | Empty. |
| `ServiceSequence.md` | 0 bytes | Empty. |
| `Model/Ingredient.md` | 2 lines ("See generated content placeholder") | Not filled in this task, per restriction. |
| `Sales/Toast/README.md` | 0 bytes | Empty integration scaffold. |
| `Sales/Clover/*.md` (10 files: `README.md`, `CloverAPIAnalysis.md`, `CloverDataMapping.md`, `Customers.md`, `Employees.md`, `KnownLimitations.md`, `Modifiers.md`, `OrderItems.md`, `Orders.md`, `Payments.md`, `Taxes.md`) | 0 bytes each | Entire empty POS-integration scaffold directory. |

### Not yet modeled

| Area | Notes |
|---|---|
| Recipes | No `Recipes.md` or equivalent exists. Depends on Ingredient (currently placeholder). |
| Inventory | Explicitly out of scope of the Purchasing Module (`Purchasing/README.md`, "Out of Scope"). |
| Customers (restaurant-specific) | No dedicated file exists, though listed in `README.md` scope. |
| Operations (opening/closing procedures, checklists, kitchen workflow) | `Model/OperationalArea.md` lists these as Processes an Operational Area executes, but no dedicated Operations documentation exists. |
| Food Cost, Forecasting | Listed in `README.md` scope as future capabilities; no canonical content yet. |

---

## 2. Planned Restaurant knowledge areas

Historical taxonomy areas that genuinely belong to Restaurant knowledge and remain useful future Domain work, drawn from [09 Strategy/04_Business_Capability_Coverage.md](../../09%20Strategy/04_Business_Capability_Coverage.md):

- **Menu** (KD-005) — categories, dishes, pricing, menu engineering, contribution margin. Builds on the existing Commercial Catalog structure.
- **Recipes** (KD-006) — ingredients, quantities, preparation, yield, portion cost. Builds on Ingredient/Product/Specification, already defined in Purchasing.
- **Inventory** (KD-008) — current inventory, stock movements, waste, shrinkage, stock valuation.
- **Sales** (KD-003), beyond the existing Combo documentation — orders, transactions, discounts, tips; POS integrations (Clover, Toast) once their scaffolds are filled with real mapping knowledge.
- **Customers** (KD-004) — segments, visit frequency, preferences, satisfaction, loyalty (restaurant-specific customer knowledge, distinct from any future generic CRM Shared Domain).
- **Operations** (KD-011) — opening/closing procedures, checklists, service standards, kitchen workflow.
- **Business Profile** (KD-001), remaining restaurant-specific attributes (cuisine, service style, opening hours) not yet fully captured beyond `OU-Restaurant.md`.

The following historical areas are **explicitly not** included here, per the classification safeguards in [09 Strategy/04_Business_Capability_Coverage.md](../../09%20Strategy/04_Business_Capability_Coverage.md):

- Artificial Intelligence (KD-018) — Software/Intelligence capability, not Restaurant Domain knowledge.
- Strategic Planning (KD-017) — Strategy/Product capability at the company/customer-expansion level; distinct from restaurant-level operational Forecasting (which does remain a planned Restaurant module).
- Financial Performance (KD-002) — Strategy capability; not imported as Restaurant Domain ontology.
- Personnel, Equipment, Reputation (KD-012, KD-013, KD-016) — Shared Domain candidates, not Restaurant-intrinsic.

---

## 3. Cross-Domain candidates and extraction triggers

Some business concerns relevant to running a restaurant may eventually come from **shared reusable Domains** rather than being duplicated inside Restaurant, or may already have a reusable component living inside Restaurant today. TASK_CORE_009 (analysis) and TASK_CORE_010 (Product Owner decision canonicalization) reviewed each candidate; **no Shared Domain is created by this roadmap.** The approved rule remains:

> **Reuse must be earned.** A Shared Domain is created only when actual semantic reuse or a concrete second consumer justifies it.

Approved decisions and extraction triggers, by area:

- **Commercial Catalog** — stays under `01 Domains/Restaurant/Commercial Catalog/` now. It is the **highest-confidence future Shared Domain extraction candidate**: all 17 files are self-declared industry-independent with zero Restaurant-specific fields. Approved trigger: *extract to `01 Domains/_Shared/Commercial Catalog/` when a second genuine Domain or Product requires the same catalog semantics.* Do not split the folder concept-by-concept; if extraction occurs, the whole coherent model moves together unless new evidence creates a natural seam.
- **Marketing** — approved future direction: `Brand (Core) → generic Marketing (future Shared Domain candidate: campaigns, channels, advertising, social media, promotions, loyalty mechanics, audience targeting) → Restaurant-specific marketing execution (Restaurant specialization: menu promotion, seasonal offers, local-store execution, guest communication tied to Menu/Commercial Catalog)`. Not created now. `README.md`'s "Marketing (planned)" scope entry is not a commitment that all Marketing ontology remains permanently inside Restaurant.
- **Reputation** — remains deferred, not created as its own Domain. Current working assumption: Reputation is more likely to become part of a future Marketing/Customer Engagement capability than an independent Domain. Not a permanent prohibition — reconsider if future modeling reveals substantial independent semantics.
- **Workforce / Personnel** — employees, roles, scheduling, payroll, skills, performance. Currently only referenced in passing (`Model/OperationalArea.md`, "Employees are assigned to Operational Areas"). This area is now the **Personnel Management** transversal Domain (`01 Domains/Personnel Management/`, created by TASK_DOMAINS_002), with Workforce, Selection, Training, Performance and Personnel Decisions as its modules. Selection is documented in depth (`Personnel Management/Selection/`); Workforce, Training, Performance and Personnel Decisions currently have only minimal placeholder READMEs — establishing Workforce semantics (role, assignment, responsibility, schedule, skills/capabilities, availability) in depth remains the previously recorded sequencing preference before Training and Performance are modeled further, though Selection was authorized ahead of it. Approved direction: `Goals → Brand → Service Model → Behaviors → Personnel Management (Selection / Training / Performance / Personnel Decisions)`. No Restaurant Product capability is created now. See [../Domain Architecture.md](../Domain%20Architecture.md) and [../Personnel Management/README.md](../Personnel%20Management/README.md) for how Workforce, Selection, Training, Performance and Personnel Decisions are currently distinguished from one another.
- **Equipment** — physical assets, maintenance, depreciation. Currently only referenced in passing (`Model/OperationalArea.md`, "Equipment"). Remains deferred.
- **Facilities (generic part)** — building/utilities/floor-plan/generic facility management, as distinct from the restaurant-specific Operational Area model already documented (which stays in Restaurant). Remains deferred. If future evidence supports abstraction, a combined `Asset & Facilities` area may be more coherent than two thin independent Domains — not decided now.
- **Financial Performance** — RF-One's own commercial/economic strategy stays under `09 Strategy/`. For customer-facing financial/performance needs: no general Finance Shared Domain yet. Approved near-term direction: build the first customer-facing financial/performance capability (e.g. a future Food Cost module) from real Restaurant Domain data as a Product/use-case capability before inventing a general Finance ontology. A future Shared Finance/Performance Domain remains possible once a second Domain or concrete Product feature needs the same semantics.
- **Customer** — stays Restaurant-local for now. Core provides generic Entity/Role/Relationship semantics (e.g. "Consumer" as a Role); Restaurant models restaurant-specific guest behavior and knowledge on top of it. No Shared Customer Domain or Customer ontology is created now; a generic CRM/loyalty capability may later become a Product or Shared capability if actual reuse emerges.
- **Supplier** — stays Purchasing-local (`Purchasing/EntityDefinitions.md`) until a second use case emerges. Approved trigger: *re-evaluate Supplier abstraction when a second Domain or reusable Procurement capability needs supplier semantics independently of the current Restaurant Purchasing model.* No Procurement Domain is created now.

Do not duplicate this knowledge inside Restaurant if a Shared Domain is created later; do not create any of these Domains now.

---

## 4. Non-goals of this roadmap

- Does not fill any empty scaffold file (`Menu.md`, `ServiceSequence.md`, `Sales/Toast/`, `Sales/Clover/*`, `Model/Ingredient.md`).
- Does not redesign Purchasing or Commercial Catalog.
- Does not create Workforce, Equipment, Marketing, Facilities, or Reputation Domains.
- Does not specify Product packaging or Software implementation for any listed area.
