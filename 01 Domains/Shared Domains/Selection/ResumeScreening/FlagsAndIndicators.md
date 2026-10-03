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
- `EXTRACTION_UNCERTAIN` — the résumé reader could not group one experience's title, employer, dates and duties with certainty (its `structure confidence` is `LOW`, [CandidateCVProfile.md](CandidateCVProfile.md)). Attention level VERIFY. It is about the reading, never about the candidate: it asks a person to check the original résumé before relying on that experience (SELECTION_CV_STRUCTURE_READING_001).

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

**Unknown is not zero (SELECTION_PRESELECTION_COMPARE_001).** Stability is "Unknown" when no job has a computable duration (before, an average of 0 months was read as "Moderate"). For filtering and comparison, direct and propedeutic months are *to be clarified* — never 0 — when the application has no supported target role, when an experience of that kind has no usable dates, or when a reading is uncertain. A value to be clarified never satisfies a numeric or stability filter unless the operator explicitly includes data to be clarified. The absence of declared coordination responsibilities means "not documented in the CV".

**Explanations (SELECTION_INDICATOR_EXPLANATIONS_001).** Direct Role Experience, Relevant / Propedeutic Experience, Stability and Career Progression can each be opened to see the experiences used (original title, employer, dates as written, duration), why each one counts for the application's target role, the rule and thresholds actually applied (restated, not changed: a short job is under 6 months; Weak when short jobs ÷ distinct employers ≥ 50%; Moderate when at least one short job or average tenure under 12 months; Strong otherwise; progression compares each job with the previous one by start date and seniority rank — higher rank at the same employer is a promotion, at another employer an increase in responsibility), and what is excluded, missing or uncertain. A "to be clarified" value says which information is missing; known durations are then shown as detail only, never as a complete total — so the candidate page now shows "to be clarified" instead of a partial sum. Role months come from the job titles as read; declared coordination duties are separate. "Reading uncertain" is about how the CV was read, not about the candidate. The candidate page and the comparison show the same explanation.

**Preselection and comparison.** Applications can be filtered (target role, stage, outcome, direct and propedeutic months, stability, declared coordination, missing or uncertain information) and 2 to 4 applications **for the same target role** compared side by side. Both use only the Indicators, Flags and evidence above: no overall score, ranking, weight or automatic recommendation; the decision stays with the operator.

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
