# TASK_CORE_008 — Business Capability and Domain Roadmap Canonicalization Report

**Status:** Completed. No Git commit was made — all changes are unstaged/untracked in the working tree, awaiting Product Owner review.

---

## A. Summary

TASK_CORE_008 reconciled the legacy `Knowledge Domains` taxonomy (`90 Archive/Legacy Repository/X00 Knowledge Repository/05 Knowledge Domains/README.md`, KD-001–KD-018) — approved for preservation as a capability/coverage map by the reconciliation backlog (`07 Tasks/Backlog/LEGACY_KNOWLEDGE_RECONCILIATION_BACKLOG.md`, Section G) — without treating it as modern architectural `Domain` ontology.

Two clearly separated canonical outputs were produced:

1. `09 Strategy/04_Business_Capability_Coverage.md` — the full 18-row classification of every historical Knowledge Domain entry into Restaurant Domain, Shared Domain candidate, Strategy/business capability, Product capability, or Software/Intelligence capability.
2. `01 Domains/Restaurant/Roadmap.md` — a Domain-knowledge roadmap for only the areas that genuinely belong to Restaurant, distinguishing documented / partial / placeholder-scaffold / not-yet-modeled current coverage from planned future work.

No new modern Domain was created. `Artificial Intelligence` (KD-018) was classified as Software/Intelligence capability, not a business Domain. `Financial Performance` (KD-002) and `Strategic Planning` (KD-017) were classified as Strategy/business capability, not Restaurant Domain or a new Domain. `Personnel`, `Equipment`, `Marketing`, and `Reputation` (KD-012, KD-013, KD-015, KD-016) were classified as Shared Domain candidates only — not created as Domains.

---

## B. Historical taxonomy classification

| Legacy ID | Historical name | Modern classification | Current coverage | Future direction |
|---|---|---|---|---|
| KD-001 | Business Profile | Restaurant Domain | Partial canonical content | Expand Restaurant Domain |
| KD-002 | Financial Performance | Strategy / business capability | Strategy coverage only | Strategy capability |
| KD-003 | Sales | Restaurant Domain | Partial canonical content | Expand Restaurant Domain |
| KD-004 | Customers | Restaurant Domain | No canonical coverage yet | Expand Restaurant Domain |
| KD-005 | Menu | Restaurant Domain | Placeholder/scaffold | Expand Restaurant Domain |
| KD-006 | Recipes | Restaurant Domain | Not yet modeled | Expand Restaurant Domain |
| KD-007 | Purchasing | Restaurant Domain | Existing canonical Domain content | Expand Restaurant Domain |
| KD-008 | Inventory | Restaurant Domain | No canonical coverage yet | Expand Restaurant Domain |
| KD-009 | Products | Restaurant Domain | Partial canonical content | Expand Restaurant Domain |
| KD-010 | Suppliers | Restaurant Domain | Partial canonical content | Expand Restaurant Domain |
| KD-011 | Operations | Restaurant Domain | Placeholder/scaffold | Expand Restaurant Domain |
| KD-012 | Personnel | Shared Domain candidate | No canonical coverage yet | Future Shared Domain candidate |
| KD-013 | Equipment | Shared Domain candidate | No canonical coverage yet | Future Shared Domain candidate |
| KD-014 | Facilities | Restaurant Domain (restaurant-specific part) / Shared Domain candidate (generic part) | Partial canonical content for restaurant-specific areas | Expand Restaurant Domain + future Shared Domain candidate |
| KD-015 | Marketing | Shared Domain candidate | No canonical coverage yet | Future Shared Domain candidate / future Product capability |
| KD-016 | Reputation | Shared Domain candidate | No canonical coverage yet | Future Shared Domain candidate |
| KD-017 | Strategic Planning | Strategy / business capability | Strategy coverage only | Strategy capability / future Product capability |
| KD-018 | Artificial Intelligence | Software / Intelligence capability | Software capability | Software/Intelligence capability |

The full table with evidence and notes per row is in `09 Strategy/04_Business_Capability_Coverage.md`.

---

## C. Restaurant roadmap

**Current canonical coverage** (`01 Domains/Restaurant/Roadmap.md`, Section 1):

- **Documented:** Purchasing (16 files — the most mature module), Commercial Catalog (17 files), and the restaurant business-profile model (`Model/OU-Restaurant.md`, `Model/OperationalArea.md`).
- **Partial:** Sales (only `Sales/Combo.md`), restaurant-specific Products (`Model/Product.md`, `Model/Specification.md`), Suppliers (defined inside `Purchasing/EntityDefinitions.md`, no standalone file).
- **Placeholder/scaffold (verified empty, not implemented knowledge):** `Menu.md` (0 bytes), `ServiceSequence.md` (0 bytes), `Model/Ingredient.md` (2-line placeholder), `Sales/Toast/README.md` (0 bytes), and all 10 files under `Sales/Clover/` (0 bytes each).
- **Not yet modeled:** Recipes, Inventory, restaurant-specific Customers, Operations (opening/closing procedures, kitchen workflow), Food Cost, Forecasting.

**Planned Restaurant knowledge areas** (`Roadmap.md`, Section 2): Menu, Recipes, Inventory, Sales (beyond Combo), Customers, Operations, and remaining Business Profile attributes — all drawn only from taxonomy rows classified Restaurant Domain, with explicit exclusion of Artificial Intelligence, Strategic Planning, Financial Performance, Personnel, Equipment, and Reputation.

---

## D. Shared Domain candidates

Identified but **not created**:

- **Workforce / Personnel** (KD-012) — employees, roles, scheduling, payroll, skills, performance. Only referenced in passing today (`Model/OperationalArea.md`, "Employees are assigned to Operational Areas").
- **Equipment** (KD-013) — physical assets, maintenance, depreciation. Only referenced in passing (`Model/OperationalArea.md`, "Equipment").
- **Facilities, generic part** (KD-014) — building/utilities/floor-plan management, as distinct from the restaurant-specific Operational Area model already documented.
- **Marketing** (KD-015) — campaigns, social media, advertising, promotions.
- **Reputation** (KD-016) — reviews, ratings, feedback, competitor tracking.

Also noted as a structural observation (not acted on): the Commercial Catalog documentation itself (`Sales/Combo.md`, "Multi Domain" section) states its model is designed to apply "across restaurants, retail, hospitality, healthcare and future business domains" — evidence Commercial Catalog may become a Shared Domain candidate in a future task. It was left in place under `01 Domains/Restaurant/Commercial Catalog/` and not relocated.

---

## E. Strategy / Product / Software classifications

- **Financial Performance (KD-002)** — classified as Strategy/business capability, not a Domain. It is already substantively covered by `09 Strategy/01_Economic_Value_and_Measurement.md` (measurable economic value, Cash-Based Profit as one historical metric candidate, counterfactual measurement). Per the task's explicit safeguard, it was not automatically made a universal or Shared Domain; operational/transactional financial data modeling remains a possible future Shared Domain candidate only if Domain-level evidence later justifies it.
- **Strategic Planning (KD-017)** — classified as Strategy/business capability at the company/customer-expansion level (expansion, new locations, investments, business scenarios), distinct from restaurant-level operational Forecasting (already anticipated as a planned Restaurant module in `Restaurant/README.md`). The company-level part is not yet fully covered by any canonical document; the restaurant-level part remains Restaurant Domain future work.
- **Artificial Intelligence (KD-018)** — classified as Software/Intelligence capability per the task's explicit safeguard. Intelligence Engines are RF-One components, not RF-One itself and not a business Domain, consistent with `00 Core/ConceptualArchitecture/06_Business_Autopilot_and_Intelligence_Engine.md` and `09 Strategy/02_Service_Delivery_and_Knowledge_Advantage.md`. No file under `03 Software/` was read or modified to reach this classification — it follows directly from already-canonical Core/Strategy content.
- No Product specification was created for any row; Products (`02 Products/`) were not modified.

---

## F. Files created/modified

**Created:**

| Path | Purpose |
|---|---|
| `09 Strategy/04_Business_Capability_Coverage.md` | Strategy-level business capability/coverage map — the full 18-row classification table. |
| `01 Domains/Restaurant/Roadmap.md` | Restaurant Domain knowledge roadmap — current coverage (documented/partial/placeholder/not-yet-modeled), planned Restaurant areas, relationship to Shared Domain candidates. |
| `07 Tasks/Reports/TASK_CORE_008_REPORT.md` | This report. |

**Modified (minimal, as authorized):**

| Path | Change |
|---|---|
| `01 Domains/README.md` | Updated `Restaurant/` row description to point to `Roadmap.md`; added a new "Business capability is not automatically a Domain" section explaining the legacy taxonomy's reconciled status and pointing to `09 Strategy/04_Business_Capability_Coverage.md`. |
| `01 Domains/Restaurant/README.md` | Added one line at the top linking to `Roadmap.md` and to `09 Strategy/04_Business_Capability_Coverage.md`. No other content changed — Restaurant ontology, scope, and modules list were left exactly as they were. |
| `09 Strategy/README.md` | Added `04_Business_Capability_Coverage.md` to the canonical-documents index table; added a sentence to "Current status" recording that TASK_CORE_008 populated it. |
| `PROJECT_STATE.md` | Added one factual bullet under "Current state" confirming the taxonomy reconciliation; added one bullet under "Next planned work" pointing to the identified Shared Domain candidates. |

No other file was opened for editing. `00 Core/`, `02 Products/`, `03 Software/`, `04 Generated Documentation/`, `05 Research/`, `06 Meetings/`, `08 External/`, and `90 Archive/` were not touched.

---

## G. Layer integrity review

- **No new modern Domain was created solely because it existed in the historical taxonomy.** All 18 rows were classified into existing layers (Restaurant Domain, Shared Domain candidate, Strategy, Software); none resulted in a new top-level Domain directory or a new Domain README.
- **No Core change.** `00 Core/` was not opened for editing in this task. The six files left modified by the prior `TASK_CORE_006` remain untouched and unstaged, exactly as this task found them.
- **No Product specification.** `02 Products/` was not opened for editing; no Product configuration, packaging, or go-to-market content was created.
- **No Software change.** `03 Software/` was not opened for editing; Artificial Intelligence (KD-018) was classified as Software/Intelligence capability by reference to already-canonical Core/Strategy documents, not by inspecting or changing Software.

---

## H. Remaining Product Owner decisions

- **Marketing: Restaurant-specific vs. Shared Domain.** `Restaurant/README.md` (pre-existing, not modified in scope by this task) already lists "Marketing" in Domain scope and "Marketing (planned)" in Current Modules — written before the current Core/Domain/Strategy separation was formalized. This task did not resolve whether restaurant-specific marketing execution (e.g. menu promotions) should remain inside Restaurant while a separate generic Marketing Shared Domain covers campaigns/social media/advertising generically, or whether all of it should eventually move to a Shared Domain. Flagged in both `09 Strategy/04_Business_Capability_Coverage.md` and `01 Domains/Restaurant/Roadmap.md`; not resolved here per the restriction against redesigning existing Restaurant concepts.
- **Commercial Catalog's future layer.** `Sales/Combo.md` documents the Commercial Catalog as intentionally multi-domain ("restaurants, retail, hospitality, healthcare and future business domains"). Whether it should eventually be promoted/relocated to `01 Domains/_Shared/` is a genuine future architectural decision, not made or acted on in this task.
- **Financial Performance's eventual Domain need.** Whether RF-One will eventually need a Shared Domain for operational/transactional financial data (distinct from the Strategy-level economic-value measurement already canonical) is left open, pending evidence from an actual Domain that needs it.
- **Strategic Planning at customer level.** Company-level customer expansion/investment planning (KD-017's literal historical scope) has no canonical home yet beyond RF-One's own company-level strategic horizons in `00_RF-One_Strategy.md`. Whether this becomes a future Product capability (e.g. within a "Growth" or "Planning" Product) is unresolved.

---

## I. Git status / scope confirmation

- **No Core modification:** confirmed — no file under `00 Core/` was opened for editing in this task. The six pre-existing unstaged modifications from `TASK_CORE_006` remain visible in `git status`, untouched by this task.
- **No Software modification:** confirmed — no file under `03 Software/` was opened or touched.
- **No Archive modification:** confirmed — `90 Archive/Legacy Repository/X00 Knowledge Repository/05 Knowledge Domains/README.md` was read only, never written.
- **No Git commit:** confirmed — no `git commit` was executed.

`git status --porcelain` at completion:

```text
 M "00 Core/ConceptualArchitecture/02_Desire_Goal_and_Reality_Check.md"
 M "00 Core/Core Evolution.md"
 M "00 Core/Entity.md"
 M "00 Core/Glossary.md"
 M "00 Core/Process.md"
 M "00 Core/Relationship.md"
 M "01 Domains/README.md"
 M "01 Domains/Restaurant/README.md"
 M "09 Strategy/README.md"
 M PROJECT_STATE.md
?? "01 Domains/Restaurant/Roadmap.md"
?? "07 Tasks/Reports/TASK_CORE_006_REPORT.md"
?? "07 Tasks/Reports/TASK_CORE_007_REPORT.md"
?? "07 Tasks/TASK_CORE_006_Core_Legacy_Knowledge_Canonicalization.md"
?? "07 Tasks/TASK_CORE_007_Strategy_Legacy_Knowledge_Canonicalization.md"
?? "07 Tasks/TASK_CORE_008_Business_Capability_and_Domain_Roadmap_Canonicalization.md"
?? "09 Strategy/00_RF-One_Strategy.md"
?? "09 Strategy/01_Economic_Value_and_Measurement.md"
?? "09 Strategy/02_Service_Delivery_and_Knowledge_Advantage.md"
?? "09 Strategy/03_Shared_Intelligence_and_Knowledge_Governance.md"
?? "09 Strategy/04_Business_Capability_Coverage.md"
```

The six `00 Core/` modifications and the four `09 Strategy/0*` untracked files predate this task (TASK_CORE_006 and TASK_CORE_007 respectively) and were left exactly as found. This task's own footprint is limited to: `09 Strategy/04_Business_Capability_Coverage.md` (new), `01 Domains/Restaurant/Roadmap.md` (new), `07 Tasks/Reports/TASK_CORE_008_REPORT.md` (new), and the four minimal modifications listed in Section F.

---

**End of report.**
