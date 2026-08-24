# TASK_PERSONNEL_001 — Report

**Task:** Model the Performance Module
**Date:** 2026-08-24

---

## A. Summary

Developed the first canonical conceptual model for the **Performance** module at `01 Domains/Personnel Management/Performance/`, replacing the placeholder-level documentation created by TASK_DOMAINS_002. Five canonical concept files were created — `Performance.md`, `PerformanceEvidence.md`, `PerformanceMeasure.md`, `PerformanceIndicator.md`, `PerformanceContext.md` — and `README.md` was rewritten as the module's canonical index. Performance is modeled as what a person actually produces in Reality, built from atomic Performance Evidence, from which Performance Measures may be derived, some of which become Performance Indicators only when actually relevant to a current Goal/Brand/role/technical Domain/Evidence/Outcome combination. No universal score, no fixed KPI list, and no KPI-discovery algorithm were introduced. Core Temporal Coherence is reused (not reinvented) to distinguish isolated event, pattern, improvement, decline, stable performance and context-specific variation. Selection/Performance, Training/Performance and Personnel Decisions/Performance boundaries were preserved as specified (Selection predicts, Performance observes; Training tries to change Performance; Personnel Decisions uses Performance but Performance does not decide). Customer Feedback and Review remain outside Personnel Management, consumed only as specific relevant Evidence items. Restaurant (Server, Restaurant Manager) is used only as validation. `Personnel Management/README.md` and `Domain Architecture.md` received minimal index/status updates. No Core, Workforce, Selection, Training or Personnel Decisions content was modified conceptually. Nothing was staged or committed.

---

## B. Files created

| Path | Purpose |
|---|---|
| `01 Domains/Personnel Management/Performance/Performance.md` | Central Performance concept: what a person actually produces in Reality within a role/context; what Performance is not (personality/moral judgment, universal score, fixed KPI dashboard, résumé assessment, Selection prediction); Selection-predicts/Performance-observes distinction; relationship to expectations/Goals/Outcomes; uncertainty; temporal evolution (reusing Core Temporal Coherence); context dependence; Restaurant example. |
| `01 Domains/Personnel Management/Performance/PerformanceEvidence.md` | Atomic information used to reason about Performance; illustrative atomic observation examples (transaction, item sold, quantity, price, time, employee, shift, guest count, service duration, tip, product mix, customer statement, review text, named-employee mention, operational error, quality event); what must be preserved (source/provenance, Observation, time/context, epistemic status, uncertainty, attribution limitations); direct observation vs. derived interpretation; attribution limitations; cross-Domain evidence from Customer Feedback/Review; what Performance Evidence is not. |
| `01 Domains/Personnel Management/Performance/PerformanceMeasure.md` | A value calculated/observed from Performance Evidence (e.g. gross/hour, contribution margin/guest); Measure ≠ Evidence; a Measure is not automatically a KPI; no globally prescribed formulas; plurality of legitimate, sometimes competing Measures from the same Evidence; what a Measure is not (not Evidence, not automatically an Indicator, not automatically comparable across context, not automatically free of uncertainty). |
| `01 Domains/Personnel Management/Performance/PerformanceIndicator.md` | A Measure/Observation/signal currently considered relevant to evaluating Performance against a Goal/context; relevance derived from Goal+Brand+Role+Technical Domain+available Evidence+observed relationship with Outcomes; not a permanent KPI; no universal scalar score; no KPI-discovery algorithm; what an Indicator must expose when used; Restaurant example showing the same raw Evidence supporting different Indicator sets under different Goals. |
| `01 Domains/Personnel Management/Performance/PerformanceContext.md` | Contextual conditions required to interpret Performance Evidence/Measures fairly; comparison principle (no assumed raw comparability); illustrative, non-mandatory context dimensions (role, Assignment, location, shift, day/time, workload, customer volume, available resources, product/service mix, tenure, operational constraints, business conditions); context affects comparability, not truth; relationship to temporal reasoning; no normalization algorithm designed. |
| `07 Tasks/Reports/TASK_PERSONNEL_001_REPORT.md` | This report. |

No additional concept files beyond the five specified were created; no architectural reason arose to deviate from the task's list.

---

## C. Files modified

| Path | Change |
|---|---|
| `01 Domains/Personnel Management/Performance/README.md` | Fully rewritten from a placeholder (module boundary only) to the module's canonical index: purpose, module boundary, relationship to Core 2.0 (Reality, Epistemic Boundary, Goal/Decision/Action/Outcome/Learning, Temporal Coherence, Constraint/Assignment), relationship to Workforce, relationship to Selection (predicts vs. observes, feedback-loop compatibility), relationship to Training, relationship to Personnel Decisions, relationship to technical Domains, relationship to Customer Feedback/Review, KPI/indicator principle, canonical document index (linking the five new files), Restaurant-as-first-validation note, Product/Runtime distinction, deferred items. Version bumped to 0.2 / Draft (initial canonical foundation). |
| `01 Domains/Personnel Management/README.md` | Module map table: Performance row's status changed from "Placeholder" to "Documented — TASK_PERSONNEL_001 (...)". "Current documentation status" section: added a dedicated Performance bullet (documented in depth) and removed Performance from the remaining-placeholder bullet (now only Workforce, Training, Personnel Decisions). "Related documents": added a link to `Performance/README.md`. |
| `01 Domains/Domain Architecture.md` | "Related documents": added a link to `Personnel Management/Performance/README.md`, noting it as the second module documented in depth (after Selection). §4 tree: Performance's annotation changed from "(module — placeholder)" to "(module — documented; TASK_PERSONNEL_001)". §5.4 ("Performance is what is actually produced"): added a cross-reference to the now-documented `Performance/README.md`, without changing the section's substantive content (which already matched the model built here). |

No file under `00 Core/`, `02 Products/`, `03 Software/`, `08 External/`, `09 Strategy/` or `90 Archive/` was touched. `01 Domains/Personnel Management/Selection/`, `Training/README.md`, `Workforce/README.md` and `Personnel Decisions/README.md` were read for context but not modified — their existing cross-references to Performance (e.g. `Training/README.md` → `../Performance/README.md`, `Personnel Decisions/README.md` → `../Performance/README.md`) already pointed at the right path and required no change. `01 Domains/Restaurant/README.md` and `Roadmap.md` were read but not modified — no broken link resulted from this task, so the task's own restriction ("do not modify Restaurant unless a broken link requires correction") kept them untouched.

---

## D. Performance definition

Performance is defined in `Performance.md` as what a person actually produces in Reality, within a role and context — a Personnel-Management-specific application of Core `Reality`, not a Fact assumed to be fully known. It is explicitly not a personality judgment, moral judgment, universal employee score, fixed KPI dashboard, résumé/Candidate-Evidence assessment, or Selection prediction. The central distinction the task required — **Selection predicts, Performance observes** — is stated directly: Selection's Fit Assessment is an Inference/Hypothesis formed before an Assignment exists; Performance is what is actually observed afterward, and conflating the two (treating a Fit Assessment as already-observed Performance, or treating one Performance observation as proof a Selection judgment was right or wrong) is called out as a distinction the Domain must preserve. Performance itself is defined as the accumulated body of Performance Evidence for a person/role/context — not a single number — from which Measures and, contextually, Indicators may be derived without Performance itself privileging any one of them.

---

## E. Atomic evidence model

`PerformanceEvidence.md` requires Performance Evidence to be preserved "as atomically as reasonably possible," giving the task's own illustrative list (transaction, item sold, quantity, selling price, time, employee, shift, guest count, service duration, tip, product mix, customer statement, review text, named-employee mention, operational error, quality event) explicitly labeled as illustrative, not a schema — no Clover-specific structure is implied, and Restaurant is stated not to be the only technical Domain that supplies Evidence. Every Evidence item must conceptually preserve source/provenance, the underlying Observation (kept separate from interpretation), time/context, epistemic status, uncertainty and attribution limitations, without a prescribed database schema. Direct observation is explicitly distinguished from derived interpretation with a worked example (`Observation` vs. `Interpretation`), and the task's three required distinctions are stated verbatim in concept: a derived measure (`gross per hour`) is not the same as the observations it was calculated from; a review rating is not the same as review text; a customer naming an employee is not the same as an inferred satisfaction score. A dedicated "Attribution limitations" section addresses results that are not cleanly attributable to one person (team/shift/cross-role results, or conditions outside any individual's control), requiring attribution to be represented as direct, Assumption/Inference, or Unknown as actually warranted — never defaulted to whoever is most visible in the record.

---

## F. Measures vs indicators

`PerformanceMeasure.md` defines a Measure as a value calculated or observed from Performance Evidence (illustratively `gross per hour`, `contribution margin per guest`, `items sold per shift`, `average service time`), explicitly not automatically a KPI, with no globally prescribed formula — units, time window, aggregation method are left to Domain/Product/Runtime decision when actually needed. It records that multiple, sometimes competing Measures can legitimately be derived from the same Evidence (e.g. `gross per hour` vs. `contribution margin per hour` diverging by product mix), with no single Measure treated as canonical.

`PerformanceIndicator.md` defines an Indicator as a Measure, Observation or signal *currently* considered relevant to evaluating Performance against a particular Goal/context, with relevance explicitly derived from `Goal + Brand + Role + Technical Domain + available Evidence + observed relationship with Outcomes` (the task's own formula, reproduced verbatim) — never a permanent classification. It states directly that RF-One may later learn a previously relevant Indicator has little actual relationship with the desired Outcome, or that another Measure/Observation is more predictive, framed as an instance of Core Learning feeding back into Indicator relevance (Temporal Coherence's "change is not automatically inconsistency" is cited explicitly). No universal scalar score is defined — the document explains why collapsing multiple Indicators into one number would hide which dimension drives an evaluation, drawing the same reasoning already used in Selection's `FitAssessment.md`. No KPI-discovery algorithm is designed; the document states this restriction explicitly and defers it to future Product/Runtime/Intelligence Engine work.

---

## G. Context and comparability

`PerformanceContext.md` states the comparison principle directly: raw person-to-person or period-to-period comparison is not assumed meaningful, with the task's own illustrative examples (morning vs. evening shift, high- vs. low-volume shift, different menu mix, different responsibilities, different operational constraints, different tenure) reproduced and extended with a worked Restaurant example showing why an apparently large gap in `gross per hour` between two shifts is not by itself evidence of a Performance difference once volume and staffing context are considered. Context dimensions (role, Assignment, location, shift, day/time, workload, customer volume, available resources, product/service mix, tenure, operational constraints, business conditions) are listed as illustrative and explicitly not mandated as universal fields — the technical Domain determines which context is actually relevant, consistent with the task's instruction. No normalization algorithm is designed; the document states this restriction explicitly, documenting only the conceptual requirement that context be preserved and accounted for.

---

## H. Temporal Performance

`Performance.md`, "Temporal evolution," reuses Core Temporal Coherence (`00 Core/ConceptualArchitecture/04_Temporal_Coherence_and_Evolution.md`) rather than defining a parallel framework, quoting its §1 language ("identifying drift, repeated patterns, ... effects that only become visible across time") and applying it to distinguish: isolated event, recurring pattern, improvement, decline, stable performance, and context-specific variation — the exact six states the task required. It states explicitly that a single Performance Evidence item is never by itself sufficient to conclude a pattern, improvement or decline, and cross-references `PerformanceContext.md` for how context (e.g. a shift or menu change) can explain an apparent trend that is not actually improvement or decline. `PerformanceContext.md`'s own "Relationship to temporal reasoning" section reinforces this same boundary from the context side.

---

## I. Relationship with Selection / Training / Personnel Decisions

- **Selection** — `Performance/README.md`, "Relationship to Selection," states "Selection predicts. Performance observes." verbatim, and reproduces the task's feedback-loop diagram (`Selection expectation → Assignment → actual Performance → Outcome → Learning → improved future Selection`), stating that Performance must preserve enough meaning and provenance to support this loop later (e.g. a future Selection process asking which candidate characteristics predicted actual Performance), without this task building that feedback mechanism or redesigning Selection.
- **Training** — `Performance/README.md`, "Relationship to Training," reproduces the task's `Observed Performance → Gap → Training → later Performance → Learning` diagram, cross-references `Selection/TrainableGap.md` for the existing Selection/Training boundary, and states explicitly that Training is not modeled in depth here.
- **Personnel Decisions** — `Performance/README.md`, "Relationship to Personnel Decisions," states explicitly that Personnel Decisions may use Performance to compare the current person with Selection-identified alternatives, but that **Performance itself does not decide retain/train/move/replace** — it provides Reality-grounded evidence, while economics, Constraints, uncertainty and authority remain Personnel Decisions' responsibility. No economic replacement logic was introduced into Performance.

None of Selection, Training, Personnel Decisions or Workforce were modified conceptually; their existing README files were read for context and cross-referenced, not edited.

---

## J. Customer Feedback / Review boundary

`PerformanceEvidence.md`, "Cross-Domain evidence: Customer Feedback and Review," and `Performance/README.md`, "Relationship to Customer Feedback and Review," both state that Customer Feedback and Review remain separate transversal Domain candidates outside Personnel Management, and reproduce the task's two examples almost verbatim: a customer explicitly naming an employee becomes relevant Performance Evidence; review text describing specific service behavior becomes relevant Performance Evidence, kept separate from any overall rating the Review carries. In both cases only the specific relevant item is stated to become Performance Evidence — the full Customer Feedback or Review record is not imported, and neither Domain's concepts are redefined or duplicated. No `Customer Feedback/` or `Review/` folder was created.

---

## K. Restaurant validation examples

Each of the five concept files (except `PerformanceContext.md`, which uses a compact inline example, and `PerformanceMeasure.md`/`PerformanceIndicator.md`, which include worked Restaurant sections) includes at least one Restaurant example — Server at Mount Dora — used only to validate the model, consistent with the task's instruction to use Restaurant "only to test the model." The task's own two important examples were reproduced faithfully and not canonized as universal KPIs: (1) two servers with equal raw sales differing materially in contribution margin because of different product mix (`Performance.md`, "Restaurant example"; `PerformanceMeasure.md`, plurality-of-Measures example); (2) a server generating positive named reviews potentially producing business value not visible in raw sales alone (`Performance.md`, "Restaurant example"; `PerformanceIndicator.md`, Goal C). No Restaurant-specific Performance file was created, and no Restaurant Domain document was modified beyond what §C records (none were, in fact, modified).

---

## L. Deferred questions

1. **Workforce dependency.** Performance Context references Assignment as a Workforce concept that is not yet modeled in depth (`Workforce/README.md` remains a placeholder). Confirm whether Workforce should now be prioritized next, since Performance's own Context model depends on Assignment semantics that do not yet exist in canonical form.
2. **Normalization mechanism.** `PerformanceContext.md` documents the comparison/normalization *requirement* but does not design how normalization would actually be computed. This remains open for a future Product/Runtime or dedicated modeling task.
3. **KPI-discovery mechanism.** `PerformanceIndicator.md` documents how Indicator relevance is *determined conceptually* (Goal+Brand+Role+Technical Domain+Evidence+Outcome relationship) but explicitly does not design the mechanism that would compute or rank Indicators from those factors. This is recorded as future Product/Runtime/Intelligence Engine work, consistent with `Domain Architecture.md` §8.
4. **Status/versioning.** The five new files and the rewritten `README.md` are marked `Version 0.1` / `0.2`, `Status: Draft (initial canonical foundation)`, mirroring Selection's original status. Confirm whether these should be promoted to `Approved`, or iterated first — the same open question TASK_SELECTION_002 recorded for Selection remains applicable here.
5. **Attribution model depth.** `PerformanceEvidence.md`'s "Attribution limitations" section states the requirement (direct/Assumption-Inference/Unknown attribution) but does not define how partial or shared attribution (e.g. a team result) would actually be represented. This is left as a future modeling question, likely intersecting with Workforce's eventual Assignment/Responsibility model.

---

## M. Git status / scope confirmation

`git status` immediately before writing this report:

```text
Changes not staged for commit:
  modified:   01 Domains/README.md
  modified:   01 Domains/Restaurant/README.md
  modified:   01 Domains/Restaurant/Roadmap.md

Untracked files:
  01 Domains/Domain Architecture.md
  01 Domains/Personnel Management/                                              (includes the newly documented Performance/ module)
  07 Tasks/Reports/TASK_DOMAINS_001_REPORT.md                                   (pre-existing)
  07 Tasks/Reports/TASK_DOMAINS_002_REPORT.md                                   (pre-existing)
  07 Tasks/Reports/TASK_SELECTION_002_REPORT.md                                 (pre-existing)
  07 Tasks/TASK_DOMAINS_001_Document_Cross_Domain_Architecture_Conclusions.md   (pre-existing)
  07 Tasks/TASK_DOMAINS_002_Canonicalize_Personnel_Management_and_Move_Selection.md  (pre-existing)
  07 Tasks/TASK_PERSONNEL_001_Model_Performance_Module.md                       (this task's spec)
  07 Tasks/TASK_SELECTION_002_Create_Canonical_Selection_Domain_Foundation.md   (pre-existing)
```

`01 Domains/README.md`, `01 Domains/Restaurant/README.md` and `01 Domains/Restaurant/Roadmap.md` show as modified only because of the prior TASK_DOMAINS_002 changes already present before this task began — this task did not further modify any of the three.

Confirmed:

- Performance is grounded in actual Reality, not prediction or judgment (§D).
- Atomic observations are preserved conceptually, with an explicit non-schema illustrative list (§E).
- Derived Measures are distinguishable from source Evidence (§E, §F).
- Review text is not collapsed into rating/sentiment (§E).
- No fixed KPI list is introduced (§F).
- PerformanceIndicator relevance is contextual (§F).
- No universal scalar Performance score is created (§D, §F).
- Context affects interpretation/comparability (§G).
- Temporal evolution reuses Core Temporal Coherence, not a parallel framework (§H).
- Performance does not make Personnel Decisions (§I).
- Selection prediction is distinguished from actual Performance (§D, §I).
- Customer Feedback and Review remain outside Personnel Management (§J).
- Restaurant is used only as a validation example (§K).
- No Runtime/Product design (UI, integrations, persistence schema, Clover) is introduced.
- No modification to `00 Core/`, `02 Products/`, `03 Software/`, `08 External/`, `09 Strategy/` or `90 Archive/`.
- No `git add` run; no commit performed.
