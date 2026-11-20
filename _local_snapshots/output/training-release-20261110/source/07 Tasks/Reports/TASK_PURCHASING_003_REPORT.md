# TASK_PURCHASING_003 — REPORT

**Task:** Document, in Restaurant/Purchasing, the operational Purchase Recording behavior for Order vs Invoice vs Physical Receiving, mobile receiving (label-based and Order-based), extra/damaged items, three-way reconciliation, Purchasing Alerts, ACCEPT/REJECT decisions, partial acceptance/rejection, returns, Expected Supplier Credit, credit-note reconciliation, and long-lived unresolved supplier discrepancies, per `07 Tasks/TASK_PURCHASING_003_Purchase_Recording_and_Receiving.md`.
**Scope:** Documentation only. No database schema, software, UI, OCR, camera, Order module, or reconciliation engine was created or modified.
**Date:** 2026-08-30

---

## A. Summary

Extended the canonical Restaurant/Purchasing documentation with the operational half of Purchase Recording: Physical Receiving. Introduced four new entities — **Purchase Order Line** (the minimum Order information needed for reconciliation), **Receiving Record**, **Receiving Line**, and **Expected Supplier Credit** — and generalized the existing **Alert** entity with an explicit `Trigger` (`CONFIGURATION_DEVIATION`, from TASK_PURCHASING_002, or the new `RECEIVING_DISCREPANCY`), since a Receiving discrepancy needs a different Human Decision vocabulary (ACCEPT / REJECT-RETURN) than a configuration deviation (accept-once / accept-as-alternative / change-expectation). Added eighteen new Business Rules (25–42) covering the three sources of Purchase Reality, three-way reconciliation, receiving-as-observation, fallback-capable mobile capture, extra/damaged items, partial quantity, receiving-completion independent of Alert resolution, atomic (non-boolean) reconciliation output, the ACCEPT/REJECT-RETURN decision, historical immutability of a return, Expected Supplier Credit and its partial/long-lived credit reconciliation, and a narrower Receiving authorization scope. Added six new Workflow steps (10–15) extending the canonical Purchase Recording flow past document intake into Receiving, reconciliation, Alert-raising, decision, credit and resolution. Updated `AIResponsibilities.md`, `AcceptanceCriteria.md`, `ValidationRules.md`, `DataAcquisition.md`, `BusinessPermissions.md` (new "Receiving User" role), `Examples.md` (three new reference examples), `ErrorHandling.md`, `DevelopmentRoadmap.md`, `TestingStrategy.md`, `Model/PurchasingModel.md`, and made a light, cross-reference-only addition to `03 Software/User Interaction Architecture.md` Section 8. No Order module, Purchase Support capability, database schema, OCR/camera implementation, or reconciliation engine was designed or built.

---

## B. Purchase Recording scope

Reaffirmed unchanged: this task extends **Purchase Recording** only (`README.md`); **Purchase Support** — deciding what/how much/from whom to purchase — remains a distinct, future, not-designed capability.

---

## C. Three sources of Purchase Reality

New `BusinessRules.md`, Rule 25, "Three Sources of Purchase Reality": Order, Invoice/Purchase Document, and Physical Receiving are three independent representations, never collapsed. The Purchase Document remains Supplier evidence, not automatically equivalent to physical Receiving Reality (already established in `EntityDefinitions.md`, "Purchase Document"; reinforced here).

---

## D. Purchase Order Line (minimal Order dependency)

New entity in `EntityDefinitions.md`/`DataDictionary.md`: `PurchaseOrderLineId`, `PurchaseOrderId`, `SupplierProductId`/`ItemDescription`, `Quantity` — deliberately minimal, per the task's instruction not to design the Order/Purchase Support module. It exists solely to give Purchase Recording an "Order" side for reconciliation.

---

## E. Three-way reconciliation

New `BusinessRules.md`, Rule 26, "Three-Way Reconciliation": Order vs Invoice ("did the Supplier bill what was ordered?"), Invoice vs Receiving ("did the Supplier physically deliver what it billed?"), Order vs Receiving ("did the Restaurant actually receive what it requested?"). The task's four worked examples (short delivery, pre-invoice shorting, unauthorized substitution, invoice/delivery mismatch) are reproduced verbatim as the canonical illustration. `Workflow.md`, new Step 11, operationalizes this in the canonical flow.

---

## F. Receiving Record and Receiving Line

New entities in `EntityDefinitions.md`/`DataDictionary.md`. Receiving Record: Supplier, related Order/Purchase Document when known (neither required), Location, timestamp, Receiving User, capture method, source evidence, Completed/In-Progress status. Receiving Line: related Purchase Order Line and Purchase Line when known, observed quantity and configuration, damaged quantity (a portion of observed quantity, not a separate line), mandatory photo when Extra/Unexpected or damaged. A Receiving Line with no related Purchase Order Line is, by definition, an Extra/Unexpected Item — no separate entity was created for it, consistent with the task's "do not overmodel" instruction.

---

## G. Receiving is observation, not decision

`BusinessRules.md`, Rule 27: the receiving Employee records facts only and never decides acceptability, substitution, retention, or economic classification — those are Purchasing Decisions (Rule 35).

---

## H. Mobile-first, fallback-capable receiving (label-based and Order-based)

`BusinessRules.md`, Rule 28, consolidates both capture modes from the task (label-based: scan Invoice, then each package/case label, AI extracts facts and reconstructs Receiving; Order-based: RF-One shows expected item/quantity, Employee enters only actual quantity, RF-One derives the shortage) and states explicitly that label-based capture falls back to Order-based/manual capture rather than failing the session. `Workflow.md`, Step 10, and `ErrorHandling.md`, new "Receiving Capture Errors" section, reflect the same fallback behavior.

---

## I. Extra/Unexpected Item

`BusinessRules.md`, Rule 29: an Extra/Unexpected Item is a Receiving Line with no related Purchase Order Line; the Employee records only free-text description, quantity, packaging if recognizable, provenance, and a **mandatory** photo; it always raises a `RECEIVING_DISCREPANCY` Alert routed to the responsible Purchasing authority, carrying Supplier/Order/Invoice/description/quantity/photo/evidence and any AI proposal explicitly marked as interpretation. Example 7 in `Examples.md` demonstrates this end to end (label-based receiving plus an unmatched extra case of zucchine).

---

## J. Damaged item

`BusinessRules.md`, Rule 30: damaged quantity is preserved against the affected Receiving Line with a mandatory photo; the Employee is never asked to determine economic responsibility; it always raises a Receiving Discrepancy Alert. Example 8 demonstrates this together with partial acceptance and Expected Supplier Credit.

---

## K. Partial quantity

`BusinessRules.md`, Rule 31, reproduces the task's canonical example (10 received, 2 damaged → 8 ACCEPT / 2 REJECT-RETURN) and states explicitly that a Purchase Line or Receiving Line is never forced into an all-or-nothing decision.

---

## L. Receiving can complete with open issues

`BusinessRules.md`, Rule 32: `Receiving Status = COMPLETED` may coexist with `Purchasing Alerts = OPEN`; the Employee is never blocked waiting for a Purchasing Manager decision. Reflected in `EntityDefinitions.md`, "Receiving Record," `Workflow.md` Steps 10 and 12, `AcceptanceCriteria.md`, and `Examples.md` (Example 6).

---

## M. Reconciliation output — atomic differences

`BusinessRules.md`, Rule 33: reconciliation produces atomic differences (illustratively `MATCH`, `SHORT`, `EXTRA/UNEXPECTED`, `SUBSTITUTED`, `DAMAGED`, `INVOICE MISMATCH`, `ORDER MISMATCH`, `PACKAGING DEVIATION`, `QUANTITY DEVIATION`) rather than one boolean result; this is explicitly not a rigid exhaustive enum. Reconciliation Outcome is documented as a derived measure in `DataDictionary.md`, "Persist Facts — Derive Calculations" — no new persisted entity was created for it, matching how Effective Product Cost is already handled.

---

## N. Alert routing for Receiving discrepancies

`BusinessRules.md`, Rule 34, states the same three-role routing as the task (Receiving staff record Reality → RF-One reconciles → responsible Purchasing User decides), mirroring the routing/lifecycle already established for configuration-deviation Alerts in TASK_PURCHASING_002 and `03 Software/User Interaction Architecture.md`, Section 7.1.

---

## O. Alert generalization — Trigger

`EntityDefinitions.md`, "Alert," gained a new "Alert Trigger" subsection distinguishing `CONFIGURATION_DEVIATION` (TASK_PURCHASING_002's existing semantics, unchanged) from the new `RECEIVING_DISCREPANCY`. `DataDictionary.md`'s Alert table gained `Trigger`, `PurchaseOrderLineId`, `ReceivingRecordId`, `ReceivingLineId`, and `ReconciliationOutcome`, and its `HumanDecision` row now branches by Trigger: `ACCEPT_THIS_PURCHASE_ONLY` / `ACCEPT_AS_ALTERNATIVE` / `CHANGE_EXPECTATION` (unchanged, `CONFIGURATION_DEVIATION`) vs. `ACCEPT` / `REJECT_RETURN` (new, `RECEIVING_DISCREPANCY`). This was necessary because the task's ACCEPT/REJECT decision vocabulary is semantically different from TASK_PURCHASING_002's configuration-learning vocabulary and the two must not be conflated. No existing `CONFIGURATION_DEVIATION` behavior, rule, or attribute was changed.

---

## P. ACCEPT / REJECT-RETURN decision

`BusinessRules.md`, Rule 35: exactly two economic outcomes. ACCEPT makes the received quantity a valid acquired quantity and may additionally route through the existing Configured Expectation semantics (Rules 20, 23) without duplicating them, per the task's explicit instruction. REJECT/RETURN is defined by Rule 36.

---

## Q. Rejection preserves historical reality; return is not "never received"

`BusinessRules.md`, Rule 36, combines the task's Sections 21–22 into one rule: the Receiving observation is never erased or rewritten; `Received → Rejected/Returned` must never become `Never received`; both the physical fact and the economic decision are preserved. `DataDictionary.md`, "Attribute Principles," gained a matching bullet.

---

## R. Expected Supplier Credit

New entity (`EntityDefinitions.md`, `DataDictionary.md`) created only when a REJECT/RETURN decision applies to already-invoiced merchandise (`BusinessRules.md`, Rule 37). Satisfied fully or partially by a Credit Note or a credit/adjustment on a later Invoice — no second credit-document ontology was created, per instruction; Credit Note remains the sole canonical credit-document type (already existed as a `Purchase Document.DocumentType` value).

---

## S. Partial credit and outstanding amount

`BusinessRules.md`, Rule 38, reproduces the task's $200/$120/$80 example. `OutstandingAmount` and `RecognizedAmount` are documented as derived, not persisted, in `DataDictionary.md`, "Persist Facts — Derive Calculations," consistent with the module's existing "persist facts, derive calculations" discipline (already applied to Effective Product Cost, category totals, etc.).

---

## T. Credit reconciliation against future Supplier documents

`BusinessRules.md`, Rule 39: a later Supplier Purchase Document's credit/adjustment evidence is reconciled against open Expected Supplier Credits; a correct match resolves fully or partially; an omitted, wrong, misapplied, or partial correction keeps the expectation open and (re)generates an Alert. RF-One never assumes the correction must land on exactly the next invoice.

---

## U. Long-lived open supplier issues — no arbitrary expiration

`BusinessRules.md`, Rule 40, states explicitly that a Purchasing discrepancy's lifecycle may extend beyond delivery and beyond the original Invoice, may remain Open for months or years, and that no module logic imposes automatic expiration, write-off, or closure. `EntityDefinitions.md`, "Expected Supplier Credit," reflects the same rule.

---

## V. Receiving evidence and Employee simplicity

`BusinessRules.md`, Rule 41, consolidates the task's evidence-preservation list (Invoice image, labels, extra/damaged photos, manual observations, Receiving User/timestamp, later credit documents) and the "SCAN INVOICE / SCAN LABEL... / CONFIRM ACTUAL QUANTITY... / ADD EXTRA ITEM + PHOTO / MARK DAMAGED QUANTITY + PHOTO / FINISH" interaction shape, restating that the Employee is never required to understand accounting, Food Cost, disputes, classification, substitution policy, credit handling, or configuration rules.

---

## W. Receiving authorization boundary

`BusinessRules.md`, Rule 42, and a new "Receiving User" role in `BusinessPermissions.md`: a mobile-scoped role narrower than general Purchasing access (assigned scope/Location; capture, quantities, extra/damaged items, complete Receiving), with no automatic right to full Purchasing pages, supplier configuration, cost analysis, approving deviations, resolving Alerts, or changing Configured Expectations. Explicitly cross-referenced to, and does not redesign, the general Authorization Model in `03 Software/User Interaction Architecture.md`, Section 4/6. No customer-specific role was hardcoded.

---

## X. Purchase Recording flow update

`Workflow.md` gained six new steps (10–15): Record Physical Receiving; Reconcile Order vs Invoice vs Receiving; Raise Purchasing Alerts for Receiving Discrepancies; Responsible Purchasing Decision (Accept or Reject/Return); Expected Supplier Credit and Reconciliation; Resolve or Keep Open. Step 10 explicitly notes Receiving is not strictly sequential with Steps 1–9 (goods may arrive before, with, or after the Invoice). Three new Design Principles bullets were added. `Model/PurchasingModel.md`'s Core Entities diagram, Entity Responsibilities, Business Flow, and Architectural Principles were updated to include Purchase Order Line, Receiving Record/Line, the generalized Alert (with its two triggers), and Expected Supplier Credit, consistent with `CLAUDE.md`'s "identify affected dependencies" instruction.

---

## Y. Interaction Architecture boundary

`03 Software/User Interaction Architecture.md`, Section 8 ("Mobile Capture," "For Purchasing"), gained one added paragraph illustrating mobile Receiving (label-based/Order-based, fallback-capable, completable with an open Alert) as a further concrete example of the existing Capture → Evidence → Routing → Domain flow, plus one new "Related documents" line. No new interaction architecture, UI, or layout was designed; the document's scope and "Out of Scope" section are unchanged. This mirrors the light-touch approach TASK_PURCHASING_002 took for Section 7.1.

---

## Z. Exact files changed

**Created:**

- `07 Tasks/TASK_PURCHASING_003_Purchase_Recording_and_Receiving.md`
- `07 Tasks/Reports/TASK_PURCHASING_003_REPORT.md` (this file)

**Modified:**

- `01 Domains/Restaurant/Purchasing/README.md` — Scope list; new "Physical Receiving and Reconciliation" section; three new Design Principles bullets.
- `01 Domains/Restaurant/Purchasing/EntityDefinitions.md` — new "Purchase Order Line," "Receiving Record," "Receiving Line," "Expected Supplier Credit" sections; "Alert" extended with "Alert Trigger" subsection and updated Identity/Responsibilities.
- `01 Domains/Restaurant/Purchasing/DataDictionary.md` — new Purchase Order Line, Receiving Record, Receiving Line, Expected Supplier Credit tables; Alert table extended (Trigger, PurchaseOrderLineId, ReceivingRecordId, ReceivingLineId, ReconciliationOutcome, branched HumanDecision); "Persist Facts — Derive Calculations" and "Attribute Principles" extended.
- `01 Domains/Restaurant/Purchasing/BusinessRules.md` — new Rules 25–42; four new Design Principles bullets.
- `01 Domains/Restaurant/Purchasing/ValidationRules.md` — "Alert vs Validation" extended with a Receiving-specific paragraph (Extra Item identity resolution as Validation vs the discrepancy itself as Alert).
- `01 Domains/Restaurant/Purchasing/Workflow.md` — new Steps 10–15; three new Design Principles bullets.
- `01 Domains/Restaurant/Purchasing/AIResponsibilities.md` — new AI Responsibilities (label reading, reconciliation derivation, Receiving Discrepancy Alert proposal, Expected Supplier Credit proposal/matching); new AI Limitations (no ACCEPT/REJECT decision, no economic-responsibility determination, no rewriting a Receiving observation, no closing an Expected Supplier Credit); new Human Responsibilities and Human Decisions entries.
- `01 Domains/Restaurant/Purchasing/AcceptanceCriteria.md` — new "Physical Receiving and Reconciliation" and "Expected Supplier Credit" sections; extended AI shall/shall-not lists.
- `01 Domains/Restaurant/Purchasing/DataAcquisition.md` — new "Relationship to Physical Receiving" section clarifying Receiving is not a Purchase Document acquisition channel.
- `01 Domains/Restaurant/Purchasing/BusinessPermissions.md` — new "Receiving User" role; two new Protected Operations.
- `01 Domains/Restaurant/Purchasing/Examples.md` — three new reference examples (Order-based shortage, label-based extra item, damaged item/reject-return/Expected Supplier Credit); two new Validation Criteria bullets.
- `01 Domains/Restaurant/Purchasing/ErrorHandling.md` — new "Receiving Capture Errors" section.
- `01 Domains/Restaurant/Purchasing/DevelopmentRoadmap.md` — three new Version 1.0 objectives.
- `01 Domains/Restaurant/Purchasing/TestingStrategy.md` — five new Business Scenario Tests.
- `01 Domains/Restaurant/Model/PurchasingModel.md` — Core Entities diagram, Entity Responsibilities, and Architectural Principles extended with Purchase Order Line, Receiving Record/Line, generalized Alert, and Expected Supplier Credit. Not in the task's mandatory read list, but updated for consistency as an affected dependent document, matching the precedent set by TASK_PURCHASING_002.
- `03 Software/User Interaction Architecture.md` — one added paragraph in Section 8 illustrating mobile Receiving; one new "Related documents" line. No layout, UI, or Purchasing-specific interaction architecture was introduced.

**Not touched:** `Configuration.md`, `Non-FunctionalRequirements.md` (reviewed; no contradiction found, no change required to remain consistent). No file outside Restaurant/Purchasing, its Model diagram, and the one Interaction Architecture cross-reference was touched. `OpenQuestions.md` and `PROJECT_STATE.md` were reviewed and found to contain no statement this task contradicts; PROJECT_STATE.md's Purchasing summary line still accurately describes the module and was left as a historical record of TASK_PURCHASING_001, per the "historical record" nature of that file's phrasing — updating it to mention TASK_PURCHASING_003 was judged optional narrative, not required for consistency, and was left to the Product Owner's discretion.

---

## AA. Remaining unresolved issues

1. **Receiving/Alert/Expected Supplier Credit data model is documented, not implemented.** Per the task's "documentation only" instruction, no database schema, ORM model, migration, or reconciliation engine was created.
2. **The exact algorithm for reconciling a later Supplier document's credit evidence against an open Expected Supplier Credit is not designed** — Rule 39 states the principle (inspect, match, resolve fully/partially, or keep open and alert) but not a matching algorithm, per the task's explicit "do not design a reconciliation engine" instruction.
3. **`AcceptableConfigurations`/`LinkedCreditReferences` remain intentionally unstructured** — `LinkedCreditReferences` on Expected Supplier Credit is documented as "one or more Purchase Documents/Purchase Lines with an applied amount" without a join-entity schema, consistent with the module's existing "do not define a DB schema now" pattern (mirrors `Configured Expectation.AcceptableConfigurations` from TASK_PURCHASING_002, still unresolved from that task too).
4. **The Order/Purchase Support module itself remains undesigned**, as instructed — Purchase Order Line is deliberately minimal (Supplier, item, quantity) and is not a complete Order entity.
5. **PROJECT_STATE.md was not updated** to mention this task — left to the Product Owner, since the existing line already correctly describes the canonicalization outcome of TASK_PURCHASING_001 and this task did not reconcile a contradiction of the same kind; a narrative "what's been documented so far" update is optional, not corrective.
6. No contradiction was found between this task's additions and any existing canonical Purchasing rule (including TASK_PURCHASING_002's Configured Expectation/Alert model, which was extended, not altered), the Interaction Architecture, or `CLAUDE.md`.

---

## AB. Git scope confirmation

No `git add`, `git commit`, or `git push` was run. The working tree contains only the file creation and modifications listed in Section Z; nothing has been staged or committed.
