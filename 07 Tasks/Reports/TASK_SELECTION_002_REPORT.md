# TASK_SELECTION_002 — Report

**Task:** Create Canonical Selection Domain Foundation
**Date:** 2026-08-23

---

## A. Summary

Created the initial canonical **Selection Domain** at `01 Domains/Selection/`: a universal business Domain for evaluating and selecting candidates for roles across industries, built on Core 2.0 (Subject/Reality, Goal, Decision/Action/Outcome/Learning, Epistemic Boundary, Subject Sovereignty). Restaurant is used throughout only as illustrative first-application material; no Restaurant-specific Selection file was created, and no Restaurant Domain content was moved or modified. No prior `TASK_SELECTION_001_REPORT.md` existed, so this task proceeded directly from Core 2.0, `01 Domains/README.md`, `01 Domains/Restaurant/README.md` and `Roadmap.md`, and the Shelbi material under `08 External/Shelbi/`.

---

## B. Files created

| Path | Purpose |
|---|---|
| `01 Domains/Selection/README.md` | Domain purpose, universal scope, relationship to Core 2.0/Brand/target Domains, future Workforce dependency, Product/Runtime distinction, document index, architecture flow, candidate-source boundary, legal/fairness safeguards. |
| `01 Domains/Selection/Selection.md` | The central Selection concept: purpose, inputs, evaluation, uncertainty, relationship to Decision, outcomes/feedback, Restaurant example. |
| `01 Domains/Selection/SelectionRequirement.md` | Requirement relevant to selecting a candidate; sources; requirement nature; Requirement ≠ Evidence distinction. |
| `01 Domains/Selection/CandidateEvidence.md` | Information relevant to evaluating a candidate; provenance/epistemic preservation; absence-of-evidence safeguard; candidate-source boundary. |
| `01 Domains/Selection/FitAssessment.md` | Contextual, multidimensional suitability assessment; explicit rejection of a mandatory scalar score; required transparency (supporting/contradicting/missing Evidence, assumptions, uncertainty, risk). |
| `01 Domains/Selection/SelectionDecision.md` | Selection-specific application of Core `Decision`; possible conclusions; what must be preserved; Subject Sovereignty/authority. |
| `01 Domains/Selection/TrainableGap.md` | Gap between current capability and desired standard addressable through training; distinctions from hard Constraint, disqualifying incompatibility, missing Evidence, demonstrated inability. |
| `07 Tasks/Reports/TASK_SELECTION_002_REPORT.md` | This report. |

---

## C. Selection architecture

```text
Goals
  → Brand
    → Service Model
      → Behaviors
        → Role / Context Requirements
          → Technical Domain Requirements
            → Candidate Evidence
              → Fit Assessment
                → Selection Decision
                  → Training / Performance feedback
```

Goals and Brand contribute *some* of the Requirements a role carries (service standards, expected behaviors); they do not by themselves determine who is hired. Requirements also come from role responsibilities, the target technical Domain (e.g. Restaurant), Constraints and law/policy. Candidate Evidence is evaluated against those Requirements to produce a Fit Assessment (multidimensional, not a single score), which informs — but does not make — a Selection Decision. The Decision carries forward its own rationale, authority and expected Outcomes, so that eventual Training and observed performance can feed Learning back into future Selection reasoning, without this task building that feedback mechanism.

---

## D. Core reuse

Reused without redefinition: Subject, Reality, Desire (implicitly, via Goal), Goal, Decision, Action, Outcome, Learning, Constraint, Evidence, Observation, Belief, Assumption, Inference, Hypothesis, Unknown, Delegated Authority, Subject Sovereignty, Relationship, Ownership, Assignment, Brand, Process, Entity.

Duplication was avoided by:
- linking to the canonical Core document for each concept rather than restating its definition;
- specializing only where a genuine Selection-specific meaning was required (`Selection Requirement`, `Candidate Evidence`, `Fit Assessment`, `Selection Decision`, `Trainable Gap` — all new Selection-scoped concepts, not renamed Core concepts);
- explicitly stating in `SelectionDecision.md` that Core `Decision` is not redefined, and that Entity/persistence semantics are not automatically inherited (per `Entity.md` §11 and `ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md` §2.1).

---

## E. Workforce dependencies

Left external/future, referenced only as dependencies without being defined: Person/Worker, Role, Position, Assignment, Responsibility, Availability, Schedule, Skill, Capability, Employment Relationship. `README.md` states explicitly that no Workforce Domain is created by this task and points to `01 Domains/Restaurant/Roadmap.md` §3 for the currently approved sequencing note (Workforce semantics before Selection/Training/Performance design). Where a Selection document needed one of these concepts (e.g. "Decision authority," "role responsibilities"), it referenced the concept without defining its underlying Workforce semantics.

---

## F. Candidate Evidence and epistemic safeguards

`CandidateEvidence.md` requires every Evidence item to conceptually preserve source, provenance, time/context, the underlying Observation (kept separate from interpretation), uncertainty, and epistemic status (Fact/Observation/Evidence/Belief/Assumption/Inference/Hypothesis/Unknown), without prescribing a schema. It states explicitly that absence of evidence is not evidence of absence — a missing observation is an Unknown, never silently converted into a negative Fact. It also works through a Shelbi-derived example showing how an observed behavior (territorial pushback under unclear facilities ownership) must be scoped to what was actually observed ("under conditions of unclear ownership, this person has been observed to assert control") rather than generalized into a personality claim — directly modeling the task's instruction not to canonize judgments about specific individuals.

---

## G. Fit model

`FitAssessment.md` explicitly refuses a mandatory universal scalar score: collapsing dimensions into one number hides which dimension is driving the assessment and manufactures false precision over genuine uncertainty. Instead it defines a set of *possible* dimensions (Role, Technical, Behavioral, Brand/Service Model, Availability, Constraint, Team-context, Trainability, Risk Fit) that a Domain/Product/Runtime should populate only where the actual Requirements and Evidence justify it — not by default. Every Fit Assessment must expose supporting Evidence, contradicting Evidence, missing Evidence, assumptions, uncertainty and material risk, so the assessment remains auditable rather than a single opaque judgment.

---

## H. Trainable Gap

`TrainableGap.md` draws four boundaries: a Trainable Gap is not a hard Constraint (cannot be closed by training regardless, e.g. legal work authorization), not a disqualifying incompatibility (a demonstrated, not assumed, mismatch with a mandatory Requirement), not missing Evidence (an Unknown, because no gap has actually been evidenced yet), and not demonstrated inability (evidence the candidate already tried and failed to close it). Only a gap that is actually evidenced and plausibly closable through training/practice/onboarding/experience qualifies. No Training Domain, curriculum, or duration table is defined; "estimated time to standard" is left as a case-by-case judgment.

---

## I. Restaurant validation examples

Each concept file includes one Restaurant example (Kitchen Manager, Mount Dora) used only to demonstrate that the same structure (Requirement → Evidence → Fit → Decision → Trainable Gap) holds regardless of industry. `Selection.md` states explicitly that the identical structure "applies unchanged to a Server, a General Manager, or a role in an entirely different industry; only the technical and behavioral content of the Requirements changes." No Restaurant-specific Selection file was created, and no Restaurant Domain document was modified or moved.

---

## J. Product / Runtime boundary

Confirmed not designed in this task: candidate acquisition platforms or connectors (Indeed, LinkedIn, ZipRecruiter, ATS systems, recruiting agencies, career sites), any UI, any scraping/ingestion mechanism, any workflow automation, and any persistence schema or Decision Record data model. `README.md`, `CandidateEvidence.md` and `SelectionDecision.md` each state their respective boundary explicitly (candidate-source boundary; persistence is a Runtime concern).

---

## K. Open Product Owner decisions

1. **Status/versioning.** These files are marked `Version 0.1 / Status: Draft (initial canonical foundation)` rather than `Approved`, since this is the first canonical pass and no prior Selection analysis existed to validate against. Confirm whether these should be promoted to `Approved` as-is, or iterated first.
2. **Workforce sequencing.** `Restaurant/Roadmap.md` (§3) records an approved sequencing note that Workforce semantics should be established *before* Selection/Training/Performance are designed. This task creates Selection ahead of Workforce, per this task's explicit authorization — confirm this ordering is intentional and durable, not just a one-off exception.
3. **Requirement "nature" classification.** `SelectionRequirement.md` offers an illustrative (mandatory/strong preference/trainable/contextual/prohibitive) classification but deliberately does not mandate it. Confirm whether a future Product/Runtime should standardize this taxonomy or continue leaving it case-by-case.
4. **Fit Assessment dimension set.** The eight illustrative dimensions in `FitAssessment.md` are not mandatory. Confirm whether a future Product should still constrain the *allowed* dimension vocabulary (even if population remains optional), to keep cross-role comparability.

---

## L. Git status / scope confirmation

- `01 Domains/Selection/` created with exactly the seven files specified.
- Only authorized existing file modified: `01 Domains/README.md` (added a `Selection/` row to the Domain index table; removed "Selection" from the "not yet created" future-Domains sentence, since it now exists).
- No modification to `00 Core/`.
- No modification to `01 Domains/Restaurant/`.
- No modification to `09 Strategy/`.
- No modification to `02 Products/`.
- No modification to `03 Software/`.
- No modification to `90 Archive/`.
- No staging performed (`git add` not run).
- No commit performed.

`git status` immediately before writing this report showed only: `01 Domains/README.md` modified, `01 Domains/Selection/` and this task's own spec file untracked — consistent with the above.
