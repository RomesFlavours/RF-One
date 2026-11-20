# Resume Screening

**Version:** 0.1
**Status:** Draft (initial canonical foundation)
**Domain:** Selection / Resume Screening
**Origin:** TASK_SELECTION_001

---

## Purpose

Resume Screening is the first concrete Selection capability RF-One implements: turning a résumé into structured, evidence-preserving information a human evaluator can use to reason about a candidate — never a system that decides for them. It is a specialization of the Selection module ([../README.md](../README.md)), not a replacement for it: every concept here (Evidence, Requirement, Fit Assessment, Trainable Gap, Selection Decision) still applies; this sub-area adds the specific data model, calculations and UI needed to screen a résumé.

Two principles govern everything in this sub-area:

> **"The Brand defines what matters. Selection measures it. The evaluator does not redefine it candidate by candidate."**
> Selection criteria derive from Brand, Values, Candidate Profile, Role and operational requirements ([../README.md](../README.md), "Relationship to Brand"). An evaluator may weigh evidence, but does not invent a new criterion mid-review because one candidate happens to lack or exhibit something.

> **"Selection looks for the right raw material. Training transforms it into the company standard."**
> A candidate is not rejected merely for lacking something reasonably trainable, unless that competency is explicitly required at entry for the role — see [Trainable Gap](../TrainableGap.md). Resume Screening's job is to surface what is and is not yet evidenced, not to apply a pass/fail bar itself.

---

## Domain architecture — four layers

Resume Screening is deliberately layered so that industry- and client-specific interpretation never contaminates the generic reasoning engine (CLAUDE.md, "Modular Architecture" / "Avoid unnecessary coupling"):

```text
A. Selection Core          generic, industry-agnostic: Evidence Model, CandidateCVProfile
                            shape, experience/trajectory calculations, generic Role Model,
                            Flag/Indicator mechanics. Never mentions a restaurant, a kitchen,
                            FOH/BOH, or any other industry concept.

B. Industry Extension       adds interpretation specific to an industry (Restaurant, Hospitality,
                            Retail, Automotive, Legal, Construction, ...) — a role catalog, role
                            classification (customer-facing / commercial / supervisory), seniority
                            ranking for trajectory, and industry-specific flag rules.
                            First instance: 01 Domains/Business Domain/Restaurant/Selection/.

C. Client Configuration     what matters for a specific company, derived from its Brand and
                            Candidate Profile (../README.md, "Relationship to Brand"). First
                            instance: Rome's Flavours, expressed through its Role Configuration
                            below — no separate Client Configuration document exists yet because
                            Rome's Flavours has only ever needed the Server Role Configuration
                            (01 Domains/Business Domain/Restaurant/Selection/README.md, "Rome's Flavours Server
                            Role Configuration").

D. Role Configuration       target role, equivalent roles, propedeutic roles, adjacent roles,
                            and transitions requiring investigation for one specific role — see
                            RoleModel.md.
```

**Restaurant-specific logic must never be hard-coded into Selection Core.** Every restaurant-shaped example in this sub-area's documents is illustrative only (validating universality, per [../README.md](../README.md), "Universal scope"); the actual Restaurant interpretation lives under `01 Domains/Business Domain/Restaurant/Selection/`.

---

## Canonical documents in this sub-area

| Document | Defines |
|---|---|
| [EvidenceModel.md](EvidenceModel.md) | The FACT / DERIVED INFORMATION / FLAG / INDICATOR separation, and the "Claim ≠ Evidence" rule. |
| [CandidateCVProfile.md](CandidateCVProfile.md) | The Resume Source pipeline (ResumeSource → RawResume → ResumeParser → CandidateCVProfile) and the full CandidateCVProfile data shape (Candidate, Education, Work History). |
| [ExperienceAndTrajectory.md](ExperienceAndTrajectory.md) | Experience-analysis calculations (tenure, gaps, overlap-safe totals) and career-trajectory detection (promotions, lateral moves, role transitions requiring investigation), plus the contextual career/age information rules. |
| [RoleModel.md](RoleModel.md) | The generic Role Model: target/equivalent/propedeutic/adjacent roles and transition flags. |
| [FlagsAndIndicators.md](FlagsAndIndicators.md) | The structured Flag model, the initial Indicator set, and Information Quality — and the "no universal CV score" rule. |

---

## No universal CV score

The Resume Engine produces separate Indicators only (see [FlagsAndIndicators.md](FlagsAndIndicators.md)). Their relative importance is a future Client/Role Configuration concern — Brand, Candidate Profile, role and industry all shape it — and is explicitly **not** decided by this sub-area. No document, calculation, or UI in Resume Screening produces one combined ranking number for a candidate.

---

## Human review — what Resume Screening may and must not do

Resume Screening may parse résumés, structure information, calculate durations, normalize roles, compare experience, identify evidence, derive indicators, identify missing information, generate flags, and suggest interview questions. It must not automatically hire, automatically reject a candidate solely from an inference, or hide evidence behind an assessment. The hiring decision remains a human [Selection Decision](../SelectionDecision.md) — see [../README.md](../README.md), "Legal / fairness / governance safeguards."

---

## Organization Intelligence — OPEN / TBD, not implemented

A future capability — reasoning about the *employer* side of a candidate's Work History (e.g. what an employer's training/operating standard actually was, so "3 years at Employer X" carries calibrated weight) — is deliberately **not defined or implemented** by this sub-area. No employer-quality score, employer-training score, external employer research, or employer-enrichment logic exists anywhere in Resume Screening. `CandidateWorkHistory.employer` is preserved only as a Fact (a name string); nothing currently reasons about it. A clean extension point is left in [ExperienceAndTrajectory.md](ExperienceAndTrajectory.md) ("Employer, preserved as a Fact only") for whenever Organization Intelligence is itself defined as its own module.

---

## Relationship to Product/Runtime

This sub-area, like the rest of Selection, defines business knowledge. The first Product/Runtime implementation of it — the CV screening web MVP — lives at `03 Software/Selection/` and `rfone_data_store/selection/`; see that code's own module docstrings for implementation detail. Documentation here remains the canonical source of what the software is supposed to mean; the software must not silently redefine it.
