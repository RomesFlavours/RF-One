# TASK_CORE_010 — Cross-Layer Architecture Decisions Canonicalization Report

**Status:** Completed. No Git commit was made — all changes are unstaged/untracked in the working tree, awaiting Product Owner review.

---

## A. Summary

TASK_CORE_010 canonicalized the Product Owner decisions that follow from the TASK_CORE_009 analysis (`07 Tasks/Reports/TASK_CORE_009_REPORT.md`), closing the architectural review cycle started by TASK_CORE_008 and TASK_CORE_009. No new Shared Domain was created, Commercial Catalog was not moved, and no Core/Product/Software/Archive file was touched. The eleven approved decisions listed in the task specification (no new Shared Domain now; Commercial Catalog stays with an explicit extraction trigger; Marketing's future Brand→generic Marketing→Restaurant-execution split; Reputation deferred; Workforce-before-Selection/Training sequencing; Equipment/Facilities deferred; Financial Performance as Product/use-case-first; Strategic Planning using existing Core concepts only; Customer Restaurant-local; Supplier Purchasing-local; Business Profile not a Domain) were made explicit in canonical planning/governance documentation so they do not need to be re-derived or reopened by future tasks or agents.

---

## B. Commercial Catalog

Current location, unchanged: `01 Domains/Restaurant/Commercial Catalog/`. It is now explicitly recorded (in `Restaurant/README.md`, `Restaurant/Roadmap.md`, and `09 Strategy/04_Business_Capability_Coverage.md`) as the **highest-confidence future Shared Domain extraction candidate**. Approved trigger, recorded verbatim in all three documents: *extract to `01 Domains/_Shared/Commercial Catalog/` when a second genuine Domain or Product requires the same catalog semantics.* The folder is not split concept-by-concept; if extraction occurs later, the whole coherent model moves together unless new evidence creates a natural seam. Nothing was moved in this task.

---

## C. Marketing / Reputation

Approved future split, now recorded in `Restaurant/README.md` and `Restaurant/Roadmap.md`: `Brand (Core) → generic Marketing (future Shared Domain candidate: campaigns, channels, advertising, social media, promotions, loyalty mechanics, audience targeting) → Restaurant-specific marketing execution (Restaurant specialization: menu promotion, seasonal offers, local-store execution, guest communication tied to Menu/Commercial Catalog)`. Marketing is not created now; `Restaurant/README.md`'s existing "Marketing (planned)" scope/module entry is now explicitly annotated as not a commitment that all Marketing ontology belongs permanently inside Restaurant. Reputation remains deferred and is not created as its own Domain; the recorded working assumption is that it is more likely to become part of a future Marketing/Customer Engagement capability than an independent Domain — not a permanent prohibition.

---

## D. Workforce / Selection / Training

Approved sequencing principle, recorded in `Restaurant/Roadmap.md` and the legacy backlog: when People/Workforce modeling becomes necessary, first establish reusable Workforce semantics (worker/person role, role, assignment, responsibility, schedule, skills/capabilities, availability, performance-related facts). Only after those semantics are stable should Selection, Training, and Performance capabilities be designed on top of them. The approved future direction `Goals → Brand → Service Model → Behaviors → Selection / Training / Performance` is preserved. No Domain or Product capability is created in this task, and no final Domain name (`Workforce`, `People`, `Personnel`, `HR`) is chosen.

---

## E. Equipment / Facilities

Both remain deferred — no Shared Domain is created for either. Equipment has essentially no schema evidence beyond a related-concepts mention in `Model/OperationalArea.md`. Facilities' restaurant-specific part (Kitchen, Bar, Dining Room, Storage, etc.) is already correctly and substantially modeled inside Restaurant via `Model/OperationalArea.md` and stays there; the generic building/utilities/floor-plan/maintenance layer is unmodeled and reusable across any physical business, but is not created now. If future evidence supports abstraction, a combined `Asset & Facilities` area is recorded as more coherent than two thin independent Domains — that architecture is explicitly not decided in this task.

---

## F. Financial Performance

RF-One's own commercial/economic strategy remains under `09 Strategy/`, unchanged. For customer-facing financial/performance needs, the approved near-term direction (recorded in `Restaurant/Roadmap.md`) is: build the first customer-facing financial/performance capability from real Domain data (e.g. a future Food Cost module, already named in `Purchasing/DevelopmentRoadmap.md`) as a Product capability, before inventing a general Finance ontology. No general Finance Shared Domain is created now. A future Shared Finance/Performance Domain remains possible once a second Domain or concrete Product feature needs the same revenue/cost/margin/P&L semantics.

---

## G. Strategic Planning

No new Domain is created because customer-level strategic planning is already fully expressible using existing Core concepts — Desire, Goal, Reality Check, Decision, Action, Outcome, Learning, and Temporal Coherence — as confirmed by the TASK_CORE_009 analysis. `Strategic Planning` is not created as a Shared Domain merely because the legacy taxonomy (KD-017) used that name. No new Core primitive (e.g. `Mission`) is introduced. If reusable planning methods later emerge, they are recorded as more likely to become Product capabilities consuming Core + Domain knowledge than a new Domain.

---

## H. Customer / Supplier / Business Profile

- **Customer** remains Restaurant-local. No Shared Customer Domain and no Customer ontology are created in this task. Core provides generic Entity/Role/Relationship semantics (e.g. "Consumer" as a Role); Restaurant may model restaurant-specific guest behavior on top of it. A generic CRM/loyalty capability may later become a Product or Shared capability if actual reuse emerges.
- **Supplier** remains Purchasing-local (`Purchasing/EntityDefinitions.md`). It is not extracted. Approved trigger, now recorded in `Restaurant/Roadmap.md`: re-evaluate Supplier abstraction when a second Domain or reusable Procurement capability needs supplier semantics independently of the current Restaurant Purchasing model. No Procurement Domain is created now.
- **Business Profile** does not become a separate Domain. It is recorded as primarily a composition of existing Core concepts (Corporate, Brand, Operational Unit), Restaurant specialization (`Model/OU-Restaurant.md`, `Model/OperationalArea.md`), and future Product onboarding/configuration workflows. The remaining Restaurant-specific profile gaps identified by TASK_CORE_009 (Cuisine, Service Style) are noted as future additions to the existing `OU-Restaurant.md` document — not implemented in this task, per the restriction against implementing those attributes here.

---

## I. Files modified

No file was created except the required report. Only the smallest coherent subset of the authorized files was modified:

| Path | Change |
|---|---|
| `01 Domains/Restaurant/README.md` | Added two short paragraphs after the Scope list: (1) clarifying that "Marketing" is planned business coverage, not a settled architectural placement, and stating the generic-vs-Restaurant-execution split; (2) stating that Commercial Catalog is canonical Restaurant content today and is recorded as the highest-confidence future Shared Domain extraction candidate. No other content changed. |
| `01 Domains/Restaurant/Roadmap.md` | Section 3 renamed from "Relationship to Shared Domains" to "Cross-Domain candidates and extraction triggers" and expanded to record all eleven approved decisions with explicit extraction triggers for Commercial Catalog, Marketing, Reputation, Workforce/Personnel, Equipment, Facilities, Financial Performance, Customer, and Supplier. No other section changed. |
| `09 Strategy/04_Business_Capability_Coverage.md` | Updated the KD-009 (Products/Commercial Catalog) note to record the approved extraction trigger and "highest-confidence extraction candidate — trigger required" wording; updated the KD-016 (Reputation) row's "Future direction" and note to record the deferred-not-standalone decision; added a new "Approved to create now vs. future candidate" section after "Reading the table" making explicit that every Shared Domain candidate row is a future candidate only, none is approved to create now, and cross-referencing `Restaurant/Roadmap.md` for the remaining decisions (Financial Performance, Strategic Planning, Customer, Supplier, Workforce sequencing). |
| `07 Tasks/Backlog/LEGACY_KNOWLEDGE_RECONCILIATION_BACKLOG.md` | Added new final Section J, "Cross-layer Shared Domain questions — resolved (TASK_CORE_009 / TASK_CORE_010)," recording that the cross-layer Shared Domain questions from Section G and TASK_CORE_008 are now resolved, and preserving all key extraction triggers so this backlog does not need to be reopened later merely to re-answer these questions. Sections A–I were not altered. |
| `PROJECT_STATE.md` | Added one factual bullet under "Current state" recording that the cross-layer Shared Domain review is complete, no new Shared Domain was created, Commercial Catalog is the leading future extraction candidate, and Shared Domain creation remains evidence-triggered; lightly extended the existing "Next planned work" bullet on Shared Domain candidates to state none is scheduled or approved to create now. |

Not modified: `09 Strategy/README.md`, `01 Domains/README.md` (both were authorized-adjacent by earlier tasks but not listed as authorized here and required no change to reflect these decisions).

---

## J. Validation

1. Verified no new Shared Domain directory exists (`01 Domains/_Shared/Commercial Catalog/`, `.../Marketing/`, `.../Workforce/` all absent) — confirmed via directory check after editing.
2. Verified Commercial Catalog remains under `01 Domains/Restaurant/Commercial Catalog/` — not moved.
3. Verified Marketing is described neither as fully Restaurant-only nor as already Shared — both `README.md` and `Roadmap.md` now state the split explicitly as future/undecided-in-execution.
4. Verified Reputation is not declared a standalone Domain — recorded as deferred, likely folding into a future Marketing/Customer Engagement capability.
5. Verified Workforce/Selection/Training sequencing is stated clearly (Workforce semantics first, then Selection/Training/Performance on top).
6. Verified Financial Performance is not turned into ontology — recorded as Product/use-case-first, no Finance Shared Domain created.
7. Verified Strategic Planning is not turned into a Domain or new Core primitive — recorded as Core Goal/Decision usage only, no `Mission` introduced.
8. Verified Customer and Supplier are not extracted — both explicitly recorded as remaining local (Restaurant / Purchasing respectively) with trigger-gated future reconsideration only.
9. Verified no `00 Core/` file was opened for editing in this task (the six pre-existing unstaged TASK_CORE_006 modifications remain, untouched by this task).
10. Ran `git status --porcelain` after editing (see Section K).
11. No `git commit` was executed.

---

## K. Git status / scope confirmation

- **No Core modification:** confirmed — `00 Core/` was not opened for editing. The six modifications visible in `git status` predate this task (TASK_CORE_006).
- **No Product modification:** confirmed — `02 Products/` was not opened.
- **No Software modification:** confirmed — `03 Software/` was not opened.
- **No Archive modification:** confirmed — `90 Archive/` was not opened for editing (only referenced, read-only, in prior tasks' documents).
- **No Shared Domain created:** confirmed — no directory under `01 Domains/_Shared/` was created.
- **No file moved:** confirmed — Commercial Catalog and all other files remain at their existing paths.
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
 M "07 Tasks/Backlog/LEGACY_KNOWLEDGE_RECONCILIATION_BACKLOG.md"
 M "09 Strategy/README.md"
 M PROJECT_STATE.md
?? "01 Domains/Restaurant/Roadmap.md"
?? "07 Tasks/Reports/TASK_CORE_006_REPORT.md"
?? "07 Tasks/Reports/TASK_CORE_007_REPORT.md"
?? "07 Tasks/Reports/TASK_CORE_008_REPORT.md"
?? "07 Tasks/Reports/TASK_CORE_009_REPORT.md"
?? "07 Tasks/TASK_CORE_006_Core_Legacy_Knowledge_Canonicalization.md"
?? "07 Tasks/TASK_CORE_007_Strategy_Legacy_Knowledge_Canonicalization.md"
?? "07 Tasks/TASK_CORE_008_Business_Capability_and_Domain_Roadmap_Canonicalization.md"
?? "07 Tasks/TASK_CORE_009_Cross_Layer_Architecture_and_Shared_Domain_Review.md"
?? "07 Tasks/TASK_CORE_010_Cross_Layer_Architecture_Decisions_Canonicalization.md"
?? "09 Strategy/00_RF-One_Strategy.md"
?? "09 Strategy/01_Economic_Value_and_Measurement.md"
?? "09 Strategy/02_Service_Delivery_and_Knowledge_Advantage.md"
?? "09 Strategy/03_Shared_Intelligence_and_Knowledge_Governance.md"
?? "09 Strategy/04_Business_Capability_Coverage.md"
```

`01 Domains/Restaurant/Roadmap.md` and `09 Strategy/04_Business_Capability_Coverage.md` show as untracked (`??`) rather than modified (`M`) because they were already untracked new files from TASK_CORE_008, predating this task; both were edited in place by this task without being staged or committed. All modifications from TASK_CORE_006–009 remain intact and untouched; this task's own footprint is limited to the five files listed in Section I plus this report.

---

**End of report.**
