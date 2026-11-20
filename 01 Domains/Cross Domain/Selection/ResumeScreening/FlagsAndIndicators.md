# Flags, Indicators and Information Quality

**Version:** 0.1
**Status:** Draft (initial canonical foundation)
**Domain:** Selection / Resume Screening
**Origin:** TASK_SELECTION_001

---

## Flags

A structured signal that something in the candidate's Work/Education history is worth the evaluator's attention — see [EvidenceModel.md](EvidenceModel.md). A Flag is never automatically negative.

### Shape

```text
Flag
  type                     one of the types below (Industry Extensions may add their own,
                             more specific types — never remove or redefine a Core type)
  attention_level           e.g. INFO / REVIEW / VERIFY — how much this should matter to the
                             evaluator's attention, never a pass/fail severity
  evidence                  the Fact(s) (with snippet, where available) that produced this Flag
  explanation                plain-language statement of the pattern observed
  confidence                how confident the underlying detection is
  suggested interview question   when appropriate — always motive-neutral (see
                             ExperienceAndTrajectory.md, "Do not infer motive")
```

### Initial types (Selection Core)

- `SHORT_TENURE_PATTERN`
- `EMPLOYMENT_GAP`
- `DATE_OVERLAP`
- `ROLE_TRANSITION`
- `TITLE_INCONSISTENCY`
- `MISSING_INFORMATION`
- `CHRONOLOGY_QUESTION`

An Industry Extension may register additional, more specific flag types alongside these — e.g. the Restaurant extension's `BOH_TO_FOH` (`01 Domains/Business Domain/Restaurant/Selection/README.md`) — without Selection Core needing to know about them. Core code only guarantees the `Flag` shape above and the generic types it lists; it never hard-codes an industry-specific type name.

---

## Indicators

Separate, named, measurable dimensions — never combined into one CV score (`README.md`, "No universal CV score"). Each Indicator carries a raw value plus, where useful, a descriptive state:

```text
Direct Server Experience: 44 months
Stability: Strong
Career Progression: Observed
Information Confidence: 87%
```

### Initial set (minimum)

- Direct Role Experience
- Relevant / Propedeutic Experience
- Industry Experience
- Stability
- Career Progression
- Customer-Facing Exposure
- Commercial Exposure
- Supervisory Responsibility
- Evidence Density
- Information Confidence

No arbitrary weighting between these is defined now. Their relative importance for a given hiring decision is future Client/Role Configuration (`RoleModel.md`, "Role relevance coefficients — not defined here").

---

## Information Quality

Absence of evidence is not automatically negative evidence — a thin résumé is a quality problem to flag, not a candidate weakness to score. Information Quality Indicators exist specifically so a sparse profile is legible as *sparse*, not silently treated as equivalent to "nothing relevant."

- profile completeness
- date precision
- chronology confidence
- evidence density
- overall information confidence

---

## Relationship to Fit Assessment

Flags and Indicators are Resume-Screening-specific instruments that feed a future [Fit Assessment](../FitAssessment.md); they do not replace it. Fit Assessment remains "a contextual, multidimensional assessment... not a Fact, not a mandatory single score" (`../README.md`) — Resume Screening's Indicators are one input among the several Fit Assessment already anticipates (interview, practical test, reference checks — see `../../../../07%20Tasks/` for when those are scoped).
