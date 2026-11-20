# TASK_PURCHASING_002 — REPORT

**Task:** Document, in Restaurant/Purchasing, the behavior for commercial-configuration variation, Alert, Configured Expectation, previous-purchase fallback, Human Decision, operational learning, and the configuration-vs-module-evolution distinction, per `07 Tasks/TASK_PURCHASING_002_Alerts_Expectations_and_Operational_Learning.md`.
**Scope:** Documentation only. No database schema, software, UI, or runtime workflow was created or modified.
**Date:** 2026-08-30

---

## A. Summary

Extended the Restaurant/Purchasing canonical documentation with the Purchase Recording behavior for commercial-configuration variation: a new "Product Identity vs Commercial Configuration" principle; two new first-class concepts, **Configured Expectation** and **Alert**, with **Previous Purchase** documented as a fallback reference (not a concept with independent identity); six new Business Rules (19–24) covering variation detection priority, non-blocking Alerts, Alert lifecycle, prospective knowledge updates, and the Configuration Learning vs Module Capability Gap test; an explicit "Alert vs Validation" boundary in `ValidationRules.md`; a new Workflow step (Step 6, with the rest renumbered 7–9) for variation detection and Alert handling; updated AI responsibilities/limitations and Acceptance Criteria; and a minimal, purely cross-referential addition to `03 Software/User Interaction Architecture.md` formalizing Alert ≠ Notification at the cross-cutting level, illustrated (not owned) by the Purchasing example. Purchase Recording is explicitly distinguished from the future, not-yet-designed Purchase Support capability. No database schema, rule engine, alert severity taxonomy, forecasting, or Purchase Support model was created.

---

## B. Purchase Recording scope

`01 Domains/Restaurant/Purchasing/README.md` now states explicitly that this task's behavior belongs to **Purchase Recording** — observing Reality and comparing it with what the Restaurant knows or expects — and that **Purchase Support** (deciding what/how much/from whom to purchase) is a distinct, future capability not designed here. `Workflow.md` closes with the same distinction.

---

## C. Product identity vs commercial configuration

New section in `EntityDefinitions.md`, "Product Identity vs Commercial Configuration": a Product/Ingredient's identity (Product + Specifications, Rule 6) is independent of commercial configuration (packaging, pack count, pack size, unit, brand, variant, grade). Ricotta `20 × 500 g` vs `1 × 5 kg`, and Olive Oil `4 × 1 GAL` vs `6 × 1 L`, are used as the canonical examples — same identity, different configuration. `BusinessRules.md` Rule 19 formalizes that this variation is observable and never treated as noise, because it can affect normalized cost, freshness, shelf life, waste, yield, storage, usability, quality and recipe/food cost. `DataDictionary.md` gained `PackCount`, `ProductVariant`, `Grade` as `PRODUCT`-only Purchase Line attributes (alongside the existing `PackSize`, `Brand`, `ManufacturerCode`), explicitly documented as the commercial configuration facts a Configured Expectation may reference, and explicitly stated to never affect `SupplierProductId`, `EconomicClassification`, or Ingredient mapping by themselves.

---

## D. Configured Expectation

New entity in `EntityDefinitions.md` and `DataDictionary.md`: approved operational knowledge, per Supplier Product, about the normal/acceptable commercial configuration(s). Holds one or more acceptable configurations. Created/changed only through an explicit Human Decision (never inferred from a single observed purchase); never rewrites historical Purchase Lines. Takes precedence over the previous-purchase fallback (`BusinessRules.md`, Rule 20).

---

## E. Previous-purchase fallback

Documented as "Previous Purchase (Fallback Reference)" in `EntityDefinitions.md`: the most recent prior Purchase Line for the same Supplier + Supplier Product, consulted only when no Configured Expectation is applicable. Explicitly empirical/observational — using it for comparison never elevates it to an approved rule by itself.

---

## F. Variation detection

`BusinessRules.md`, Rule 20, "Two Reference Levels for Variation Detection": Priority 1 = Configured Expectation if it exists; Priority 2 = previous Supplier + Supplier Product purchase, as fallback. A detected deviation generates an Alert when required, and never by itself implies a wrong product, a rejected purchase, a new Product identity, or an automatic block of the Purchase Document. `Workflow.md`, new Step 6, operationalizes this as part of the canonical workflow, placed after Supplier Product resolution (Step 3) and independent of, but distinguished from, identity/interpretation Validation (Step 5).

---

## G. Alert semantics

New "Alert" entity in `EntityDefinitions.md` and `DataDictionary.md`: raised on a `PRODUCT` Purchase Line whose observed Reality deviates from an operational expectation while the underlying facts are known with certainty. Requires: responsible User/role, OPEN state until handled, explicit acknowledgement, a recorded Human Decision when required, who responded, when, what was decided, and closure only once that response is complete (`BusinessRules.md`, Rule 22). `README.md` gained a short "Alerts and Configured Expectations" section summarizing this and cross-referencing the detailed rules.

---

## H. Alert vs Validation

New section in `ValidationRules.md`, "Alert vs Validation": Validation = insufficient certainty about factual interpretation/classification (example: unknown item identity). Alert = Reality is known, but deviates from an operational expectation and requires human attention (example: known Ricotta, unexpected `1 × 5 kg`). A single line may involve both. An Alert is explicitly stated to not be a Validation Log severity level and not to be recorded as a Validation Log entry — it has its own entity and lifecycle. Alert is also distinguished from a plain Notification in the same section. `BusinessRules.md`, Rule 21, states an Alert does not block Purchase Recording when identity is certain, while an identity-uncertain case is routed to Validation instead.

---

## I. One-time acceptance

`BusinessRules.md`, Rule 23, "ACCEPT THIS PURCHASE ONLY": the specific purchase is accepted; the Configured Expectation is unchanged; the exceptional configuration never becomes the new baseline. Worked example included verbatim from the task: expected `20 × 500 g`, exceptional `1 × 5 kg` accepted as one-time only, next purchase of `20 × 500 g` raises no "change back" Alert because `20 × 500 g` remained the valid Configured Expectation throughout. Reflected in `AcceptanceCriteria.md`.

---

## J. Alternative acceptance

`BusinessRules.md`, Rule 23, "ACCEPT AS ALTERNATIVE": the current configuration is accepted, the existing valid configuration remains valid, and the new configuration becomes an additional approved alternative (example: `20 × 500 g` and `10 × 1 kg` both valid). Future purchases matching either alternative raise no deviation Alert. Reflected in `AcceptanceCriteria.md` and `DataDictionary.md` (`Configured Expectation.AcceptableConfigurations` is explicitly plural).

---

## K. Change expectation

`BusinessRules.md`, Rule 23, "CHANGE EXPECTATION": the newly observed configuration becomes the new approved expected configuration; future purchases compare against the updated expectation. Historical Purchase Lines are never rewritten by this decision.

---

## L. Historical immutability

Reinforced in three places: `BusinessRules.md` Rule 23 (a Human Decision never rewrites the historical Purchase Line, packaging received, price paid, Alert, or decision made at that time); `DataDictionary.md`, "Persist Facts — Derive Calculations" (Configured Expectation and Alert records added as persisted facts) and "Attribute Principles" (new bullet: a Human Decision on an Alert updates the Configured Expectation prospectively, never the historical record); `EntityDefinitions.md`, "Configured Expectation" (changes only prospectively, through explicit Human Decision).

---

## M. Configuration Learning

`BusinessRules.md`, Rule 24, and `Workflow.md` Step 6: if the User's answer is representable by the existing Purchasing model, it is processed as a Configured Expectation update for the Organization/Restaurant context, reused automatically thereafter — no RF-One software/module redesign required. Conceptual flow (Alert → contextual question → Human Decision → Configured Expectation update → future automatic behavior) is documented in `Workflow.md` Step 6 and referenced from `EntityDefinitions.md`, "Alert."

---

## N. Module Capability Gap

`BusinessRules.md`, Rule 24: if the User's answer describes a valid operational rule the current model cannot represent (task example: "accept the 5 kg package only when forecast consumption during the next four days exceeds 4 kg"), RF-One does not force it into an incorrect configuration; instead the requirement is escalated to whoever is responsible for RF-One/module evolution, for evaluation. The escalation mechanism itself is explicitly not implemented, per the task's instruction.

---

## O. Configuration vs RF-One evolution

`BusinessRules.md`, Rule 24, states the decision test verbatim: "can the existing Purchasing model correctly represent the User's operational rule?" — YES → Configuration Learning (customer-specific, applied within this Organization/Restaurant context); NO → Module Capability Gap (escalated, since it is a candidate for general RF-One capability, not a customer-specific workaround forced into an unsupported shape). `AIResponsibilities.md` reflects that this determination is a Human Decision, never made autonomously by AI.

---

## P. Contextual questioning principle

`EntityDefinitions.md`, "Alert," and `BusinessRules.md`, Rule 24, state that RF-One should ask the responsible User the minimum useful contextual question needed to distinguish these cases, rather than silently inferring strategic/operational intent. The task's example question semantics (accept once / accept as alternative / change expectation) is carried into `Workflow.md` Step 6 and `AIResponsibilities.md` ("AI may propose the contextual question... AI never decides which case applies"). No exact UI wording was prescribed, per instruction.

---

## Q. Interaction Architecture boundary

`03 Software/User Interaction Architecture.md` gained a new subsection, 7.1 "Alert vs Notification," stating the general Notification-vs-Alert distinction (informs vs. requires a traceable human response before closing) and explicitly stating that this document defines only the interaction shape — not what any specific Alert means, which remains Domain/Module business meaning, illustrated (not owned) by the Restaurant/Purchasing Alert as the concrete example. The "Related documents" list gained one line pointing to the Purchasing Alert definition as that illustrative example. No Alert-specific UI, layout, or Purchasing-specific interaction architecture was designed; the existing document's scope, authority boundaries and "Out of Scope" section were left otherwise unchanged.

---

## R. Workflow changes

`Workflow.md` gained a new **Step 6 – Detect Purchase Configuration Variation and Raise Alerts**, inserted after Step 5 (Validate Unknown/Ambiguous Items) and before cost derivation; the former Steps 6–8 were renumbered 7–9 (Derive Surcharge/Discount-Adjusted Costs; Produce Downstream Restaurant Economic Knowledge; Expose Derived Category Allocation to Administration). Step 6 documents: comparison priority (Configured Expectation, then previous purchase); non-blocking Alert when identity is certain; contextual question and Human Decision; the Configuration Learning vs Module Capability Gap test; and automatic pass-through for known/coherent lines. Two Design Principles bullets and a closing "Purchase Recording vs Purchase Support" section were added. Step 5's text was given one added sentence distinguishing it from the new Step 6 (identity/interpretation uncertainty vs. known-identity configuration deviation).

---

## S. Exact files changed

**Created:**

- `07 Tasks/TASK_PURCHASING_002_Alerts_Expectations_and_Operational_Learning.md`
- `07 Tasks/Reports/TASK_PURCHASING_002_REPORT.md` (this file)

**Modified:**

- `01 Domains/Restaurant/Purchasing/README.md` — Scope list, new "Purchase Recording vs Purchase Support" section, new "Alerts and Configured Expectations" section, two new Design Principles bullets.
- `01 Domains/Restaurant/Purchasing/EntityDefinitions.md` — new sections "Product Identity vs Commercial Configuration," "Configured Expectation," "Previous Purchase (Fallback Reference)," "Alert."
- `01 Domains/Restaurant/Purchasing/BusinessRules.md` — new Rules 19–24; two new Design Principles bullets.
- `01 Domains/Restaurant/Purchasing/ValidationRules.md` — new "Alert vs Validation" section; one new Design Principles bullet.
- `01 Domains/Restaurant/Purchasing/Workflow.md` — new Step 6; renumbered former Steps 6–8 to 7–9; one added sentence in Step 5; two new Design Principles bullets; new closing "Purchase Recording vs Purchase Support" section.
- `01 Domains/Restaurant/Purchasing/DataDictionary.md` — new `PackCount`, `ProductVariant`, `Grade` Purchase Line attributes plus a clarifying paragraph; new "Configured Expectation" and "Alert" entity tables; two additions to "Persist Facts — Derive Calculations" (canonical persisted facts list); one new "Attribute Principles" bullet.
- `01 Domains/Restaurant/Purchasing/AIResponsibilities.md` — two new AI Responsibilities; three new AI Limitations; two new Human Responsibilities; two new items in "Human Decisions."
- `01 Domains/Restaurant/Purchasing/AcceptanceCriteria.md` — new "Configured Expectation and Alert" section; one new AI-shall item; two new AI-shall-not items.
- `01 Domains/Restaurant/Model/PurchasingModel.md` — added Configured Expectation/Alert to the Core Entities diagram and Entity Responsibilities, and two Architectural Principles bullets. Not in the task's mandatory list, but updated for consistency as an affected dependent document (CLAUDE.md, "Approved Architectural Decisions" — identify and update affected dependencies).
- `03 Software/User Interaction Architecture.md` — new subsection 7.1 "Alert vs Notification"; one new "Related documents" line. No layout, UI, or Purchasing-specific interaction architecture was introduced.

**Not touched:** `ErrorHandling.md`, `Examples.md`, `TestingStrategy.md`, `BusinessPermissions.md`, `DataAcquisition.md`, `DevelopmentRoadmap.md`, `Configuration.md`, `Non-FunctionalRequirements.md` — reviewed, no contradiction with this task's additions found, and none required a change to remain consistent. No file outside Restaurant/Purchasing, its Model diagram, and the one Interaction Architecture cross-reference was touched.

---

## T. Remaining unresolved issues

1. **Alert data model is documented, not implemented.** `DataDictionary.md`'s new "Configured Expectation" and "Alert" tables are business-attribute definitions only, per the task's "documentation only" and "do not implement DB schemas" instructions — no database schema, ORM model, or migration was created.
2. **Escalation mechanism for Module Capability Gaps is named but not designed.** Rule 24 states the principle (escalate to whoever is responsible for RF-One/module evolution) but, per instruction, does not define a routing entity, ticketing concept, or workflow — a future task would need to design this if RF-One wants it formalized beyond the current principle.
3. **`AcceptableConfigurations` on Configured Expectation is intentionally left as an unstructured "one or more accepted configurations."** No schema for how multiple alternative configurations are represented was defined, consistent with "do not define a DB schema now" (task Section 6) — a future implementation task will need to decide this.
4. No contradiction was found between this task's additions and any existing canonical Purchasing rule, the Interaction Architecture, or `CLAUDE.md`.

---

## U. Git scope confirmation

No `git add`, `git commit`, or `git push` was run. The working tree contains only the file creation and modifications listed in Section S; nothing has been staged or committed.
