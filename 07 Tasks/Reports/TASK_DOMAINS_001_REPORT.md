# TASK_DOMAINS_001 — Report

**Task:** Document Cross-Domain Architecture Conclusions
**Date:** 2026-08-23

---

## A. Summary

Canonicalized the current cross-Domain architectural conclusions in a new document, `01 Domains/Domain Architecture.md`, before any modeling of the not-yet-created transversal Domains (Workforce, Personnel Management, Performance, Training, Customer Feedback, Review). The document fixes: Restaurant's boundary as primarily the technical/operational Domain; the transversal-Domain principle; distinctions among Selection, Workforce, Personnel Management, Performance and Training; the Customer Feedback / Review distinction; the cross-Domain evidence-reuse principle; and the contextual (non-hard-coded) KPI-discovery principle. `01 Domains/README.md` was updated with a one-line link. `01 Domains/Restaurant/README.md` and `Roadmap.md` received minimal clarifying additions consistent with the new document — no reorganization, no new content areas, no Domain redesign. No Domain folder was created beyond what already existed (`Selection/`). No Core, Product, Software, Strategy or Archive content was touched. Nothing was staged or committed.

---

## B. Files created

| Path | Purpose |
|---|---|
| `01 Domains/Domain Architecture.md` | Canonical cross-Domain architecture conclusions: Restaurant boundary, transversal Domain principle, current candidates, Selection/Workforce/Personnel Management/Performance/Training distinctions, Customer Feedback/Review distinction, cross-Domain evidence principle, KPI discovery principle, open questions. |
| `07 Tasks/Reports/TASK_DOMAINS_001_REPORT.md` | This report. |

---

## C. Files modified

| Path | Change |
|---|---|
| `01 Domains/README.md` | Added one link to `Domain Architecture.md` in the Purpose section. No table or structural change. |
| `01 Domains/Restaurant/README.md` | Added one cross-reference link in the header note, and one sentence in Purpose clarifying Restaurant is primarily the technical/operational Domain and that transversal Domains consume its knowledge rather than duplicating it. |
| `01 Domains/Restaurant/Roadmap.md` | Added `Domain Architecture.md` to "Related documents"; in §3's Workforce/Personnel entry, extended the approved future-direction chain to explicitly include Personnel Management (it was previously folded implicitly into "Workforce/Personnel") and added a cross-reference to the new document. No sequencing decision changed. |

No other files were modified. No Domain folder was created or renamed.

---

## D. Restaurant boundary

Restaurant is documented as primarily the technical/operational Domain: front-of-house/kitchen operations, service processes, menu/recipe execution, restaurant-specific inventory/purchasing semantics, restaurant-specific technical role requirements, and restaurant operational constraints/outcomes. It explicitly does not own a capability merely because that capability is first used in a restaurant. This mirrors the relationship already established for Selection (Restaurant supplies technical requirements; Selection evaluates against them) and generalizes it to the other transversal candidates.

---

## E. Transversal Domain conclusions

Recorded as the current cross-industry Domain candidates: Selection, Workforce, Personnel Management, Performance, Training, Customer Feedback, Review. None of these folders (beyond the pre-existing `Selection/`) were created. The transversal-Domain principle is stated generically: such a Domain's concepts don't depend on any specific industry; it consumes industry-specific content from whichever technical Domain (e.g. Restaurant) the situation currently involves, without duplicating that Domain's knowledge.

---

## F. Selection / Personnel Management / Workforce / Performance / Training distinctions

- **Selection** is continuously active, not vacancy-only — it continuously creates credible human alternatives for roles regardless of current vacancy status.
- **Workforce** represents who currently occupies or can occupy organizational roles (the current human structure) — distinct from managing that person's ongoing relationship/performance.
- **Personnel Management** manages the person currently performing the role: observed performance → communicate/correct/give opportunity → observe again → compare current expected value with available alternatives → retain/develop/move/replace. It is explicitly framed as an operational/economic question, not a moral judgment. Selection finds alternatives; Personnel Management manages the current person and may use those alternatives.
- **Performance** represents what is actually produced in Reality (sales, items sold, margin, service time, throughput, customer reactions, product mix, etc. in a Restaurant example). No universal performance score is defined.
- **Training** consumes the target Domain's required standard, an observed/assessed gap, role/context, learning methods and later performance evidence; Restaurant supplies restaurant-specific knowledge to it, but Training itself is potentially cross-industry, in the same way Selection is.

A summary relationship block in `Domain Architecture.md` §5.6 states each Domain's distinct question (who / who else is viable / what do we do about the current person / what actually happened / how do we close an evidenced gap) so future modeling does not collapse them into one Domain.

---

## G. Customer Feedback / Review distinction

Customer Feedback is documented as transversal: any business with customers can receive feedback about an experience, product, service, employee, process, or other business aspect. Review is documented as a distinct transversal candidate: it concerns a public or publishable representation of an experience intended for third-party readers, whereas Customer Feedback concerns what the customer communicates to the business. They may be linked (`Customer Feedback ↔ Review`) but are explicitly not collapsed into one concept by this document.

---

## H. Cross-domain evidence and KPI conclusions

**Cross-domain evidence:** the same Reality (e.g. "Tatiana was excellent but the entrée took too long") may inform Personnel Performance, Restaurant Operations, Training, Customer Feedback, Review, and later Selection learning. No new data hierarchy or evidence schema was defined; the document only records that evidence reuse across Domains is expected and consistent with Core's Epistemic Boundary, as already applied in Selection's `CandidateEvidence.md`.

**KPI discovery:** no fixed KPI list is canonized for any role or Domain. RF-One should eventually derive relevant indicators from Goals, Brand, the target Domain, the role, available Evidence, and observed relationships with Outcomes. Sales/hour, contribution margin, named reviews, product mix, service time, and customer feedback are recorded as possible indicators, not universal permanent KPIs. No KPI algorithm or scoring formula was designed.

---

## I. Open questions

Recorded in `Domain Architecture.md` §9, and requiring Product Owner input before further modeling:

1. Sequencing — which of Workforce, Personnel Management, or Performance should be modeled next, given Selection was already created ahead of Workforce (an explicitly authorized exception to the previously recorded sequencing note).
2. Whether the Personnel Management / Workforce boundary (structural occupancy vs. ongoing relationship/performance management) holds once concrete entities (e.g. Assignment, Employment Relationship) are modeled, or whether some concepts naturally belong to both.
3. Whether and how Customer Feedback and Review share an underlying evidence/entity model.
4. Whether Performance is the Domain that hosts KPI-discovery logic, or whether KPI discovery is a cross-Domain capability reading from Performance among others.
5. Final naming for these candidates remains undecided (e.g. "Workforce" vs. "People" vs. "HR").

No contradictions with existing repository content were found; the update to `Restaurant/Roadmap.md` §3 only made an existing implicit distinction (Personnel Management within "Workforce/Personnel") explicit and did not change any previously approved sequencing decision.

---

## J. Git status / scope confirmation

`git status` immediately before this report:

```text
Changes not staged for commit:
  modified:   01 Domains/README.md
  modified:   01 Domains/Restaurant/README.md
  modified:   01 Domains/Restaurant/Roadmap.md

Untracked files:
  01 Domains/Domain Architecture.md
  01 Domains/Selection/                                                        (pre-existing, from TASK_SELECTION_002)
  07 Tasks/Reports/TASK_SELECTION_002_REPORT.md                                (pre-existing)
  07 Tasks/TASK_DOMAINS_001_Document_Cross_Domain_Architecture_Conclusions.md  (this task's spec)
  07 Tasks/TASK_SELECTION_002_Create_Canonical_Selection_Domain_Foundation.md  (pre-existing)
```

Confirmed:

- No modification to `00 Core/`, `02 Products/`, `03 Software/`, `09 Strategy/`, or `90 Archive/`.
- No new Domain folder created (`Workforce/`, `Personnel Management/`, `Performance/`, `Training/`, `Customer Feedback/`, `Review/` all remain absent).
- No Product/Runtime design introduced.
- No `git add` run; no commit performed.
