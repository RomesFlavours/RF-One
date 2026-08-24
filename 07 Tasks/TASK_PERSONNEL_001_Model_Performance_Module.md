# TASK_PERSONNEL_001 — Model the Performance Module

## Objective

Develop the first canonical conceptual model for the **Performance** module inside:

```text
01 Domains/Personnel Management/Performance/
```

Performance is the part of Personnel Management that answers:

> **What is this person actually producing in Reality, in this role, under this context?**

Performance is not a fixed score and is not a predefined KPI dashboard.

This task should model Performance deeply enough that Selection, Training and Personnel Decisions can later use it.

This is a **documentation / conceptual architecture task only**.

Do not implement software.
Do not design UI.
Do not create integrations.
Do not design databases.
Do not stage or commit.

---

# Mandatory first steps

1. Read `CLAUDE.md` completely.

2. Read:

```text
01 Domains/Domain Architecture.md
01 Domains/Personnel Management/README.md
01 Domains/Personnel Management/Performance/README.md
01 Domains/Personnel Management/Selection/
01 Domains/Personnel Management/Training/README.md
01 Domains/Personnel Management/Workforce/README.md
01 Domains/Personnel Management/Personnel Decisions/README.md
01 Domains/Restaurant/README.md
01 Domains/Restaurant/Roadmap.md
```

3. Read the relevant Core 2.0 documentation, especially:

- Reality
- Evidence
- Observation
- Fact
- Assumption
- Inference
- Hypothesis
- Unknown
- Goal
- Decision
- Outcome
- Learning
- Temporal Coherence
- Constraint
- Assignment

4. Read:

```text
07 Tasks/Reports/TASK_DOMAINS_002_REPORT.md
```

5. Run:

```bash
git status
```

before editing.

---

# Approved conceptual direction

Performance must remain grounded in **actual observed Reality**.

Performance is not:

- a personality judgment;
- a moral judgment;
- a universal employee score;
- a fixed KPI list;
- a résumé assessment;
- a Selection prediction.

Performance is about what actually happened.

Selection predicts.
Performance observes.

Training attempts to change future Performance.

Personnel Decisions uses Performance together with alternatives, economics, Constraints, uncertainty and authority.

---

# Core question

Performance should support questions such as:

> What did this person actually produce?

> Under what operational conditions did it happen?

> Relative to which role, Goal, expected standard or Outcome is it relevant?

> Which observations are direct source data and which conclusions are derived?

> Is the observed result stable, improving, declining or context-dependent?

> Which indicators are actually useful for the current Goal?

---

# Atomicity principle

Preserve information as atomically as reasonably possible.

Do not collapse distinct observations prematurely into one score.

Examples in Restaurant may include distinct observations such as:

- transaction;
- item sold;
- quantity;
- selling price;
- time;
- employee;
- shift;
- guest count;
- service duration;
- tip;
- product mix;
- customer statement;
- review text;
- named employee mention;
- operational error;
- quality event.

These are examples only.

Do not create a Clover-specific schema.

Do not assume Restaurant is the only technical Domain.

A derived measure such as `gross per hour` is not the same thing as the underlying observations from which it was calculated.

A review rating is not the same thing as review text.

A customer naming an employee is not the same thing as an inferred customer-satisfaction score.

---

# Context principle

Performance must be interpreted in context.

A raw result may not be comparable without considering relevant context.

Possible context may include:

- role;
- Assignment;
- location;
- shift;
- day/time;
- workload;
- customer volume;
- available resources;
- product/service mix;
- tenure;
- operational constraints;
- business conditions.

Do not mandate these as universal fields.

The technical Domain determines which context is relevant.

---

# Performance and Outcomes

Performance should relate observable activity/results to expected Outcomes.

Do not assume that more revenue always means better Performance.

Depending on the Goal and Domain, relevant outcomes might include:

- revenue;
- contribution margin;
- productivity;
- quality;
- customer experience;
- speed;
- accuracy;
- waste;
- reliability;
- repeat business;
- other measurable or observable effects.

These are examples, not universal KPIs.

---

# KPI / indicator principle

Do **not** define permanent KPIs for a role.

RF-One should eventually be able to determine which indicators matter based on:

```text
Goal
+ Brand
+ Role
+ Technical Domain
+ available Evidence
+ observed relationship with Outcomes
```

A KPI is therefore contextual.

A measure can exist without currently being a Key Performance Indicator.

RF-One may later learn that an indicator once considered important has little relationship with the desired Outcome, or that another observation is more predictive/useful.

Do not implement KPI-discovery algorithms in this task.

---

# Customer Feedback and Review boundary

Customer Feedback and Review are outside Personnel Management.

Performance may consume relevant evidence from them.

Examples:

```text
Customer Feedback
→ customer explicitly names employee
→ relevant Performance Evidence
```

or:

```text
Review
→ text describes service behavior
→ relevant Performance Evidence
```

Do not move or duplicate Customer Feedback / Review concepts into Performance.

Do not create Customer Feedback or Review folders in this task.

---

# Restaurant validation examples

Use Restaurant only to test the model.

Examples may include Server or Restaurant Manager.

For a Server, possible observations may include:

- sales;
- margin contribution;
- items sold;
- selling mix;
- service time;
- guests served;
- customer feedback;
- review content;
- explicit named mentions.

Important example:

Two servers may have equal sales but materially different economic outcomes because they sell different product mixes or contribution margins.

Another example:

A server who generates positive named reviews may be producing business value not visible in raw sales alone.

Do not canonize either of these as universal KPIs.

The purpose is to show why Performance must retain multiple distinct observations and allow contextual indicator selection.

---

# Relationship with Selection

Selection may later ask:

> Which candidate characteristics predicted the Performance actually observed after hiring?

Performance must therefore preserve enough meaning and provenance to support:

```text
Selection expectation
→ Assignment
→ actual Performance
→ Outcome
→ Learning
→ improved future Selection
```

Do not redesign Selection in this task.

---

# Relationship with Training

Training may consume Performance to identify an evidenced gap.

Performance may later show whether Training changed the outcome.

Conceptually:

```text
Observed Performance
→ Gap
→ Training
→ later Performance
→ Learning
```

Do not model Training in depth.

---

# Relationship with Personnel Decisions

Personnel Decisions may use Performance to compare the current person with alternatives created by Selection.

Performance itself does not decide retain / train / move / replace.

It provides Reality-grounded evidence for that Decision.

Do not move economic replacement logic into Performance.

---

# Relationship with Workforce

Performance must be attributable to a relevant person / role / Assignment context.

Do not model Workforce deeply in this task.

Where Workforce semantics are still undefined, identify the dependency rather than inventing a complete Workforce model.

---

# Canonical files to create

Replace the current placeholder-level Performance documentation with the following canonical files:

```text
01 Domains/Personnel Management/Performance/README.md
01 Domains/Personnel Management/Performance/Performance.md
01 Domains/Personnel Management/Performance/PerformanceEvidence.md
01 Domains/Personnel Management/Performance/PerformanceMeasure.md
01 Domains/Personnel Management/Performance/PerformanceIndicator.md
01 Domains/Personnel Management/Performance/PerformanceContext.md
```

Do not create additional concept files without a strong architectural reason.

If an additional concept is genuinely necessary, document the reason in the report before creating it.

---

# File responsibilities

## README.md

Define:

- purpose;
- module boundary;
- relationship to Core;
- relationship to Workforce;
- relationship to Selection;
- relationship to Training;
- relationship to Personnel Decisions;
- relationship to technical Domains;
- relationship to Customer Feedback / Review;
- canonical document index.

## Performance.md

Define the central concept of Performance:

> what a person actually produces in Reality within a role/context.

Cover:

- observed results;
- relationship to expectations / Goals / Outcomes;
- uncertainty;
- temporal evolution;
- context dependence;
- what Performance is not.

## PerformanceEvidence.md

Define evidence used to reason about Performance.

Preserve:

- source/provenance;
- observation;
- time/context;
- epistemic status;
- uncertainty;
- attribution limitations.

Explicitly distinguish direct observations from derived interpretations.

## PerformanceMeasure.md

Define a measure calculated or observed from Performance Evidence.

Examples may include gross/hour or contribution margin/guest, but only illustratively.

A measure is not automatically a KPI.

Do not prescribe formulas globally.

## PerformanceIndicator.md

Define an indicator as a measure, observation or signal considered relevant to evaluating Performance against a particular Goal/context.

An indicator becomes "key" only because of the current decision/Goal/context — not because RF-One permanently labels it as universal.

Do not define a universal scalar score.

## PerformanceContext.md

Define the contextual conditions required to interpret Performance Evidence and measures fairly and meaningfully.

Context may affect comparability.

Do not create a mandatory universal context schema.

---

# Temporal principle

Performance is not only a snapshot.

RF-One must eventually be able to distinguish:

- isolated event;
- recurring pattern;
- improvement;
- decline;
- stable performance;
- context-specific variation.

Reuse Core Temporal Coherence.

Do not invent a parallel temporal framework.

---

# Comparison principle

Do not assume raw person-to-person comparison is meaningful.

Comparisons may require normalization or contextual reasoning.

Examples:

- morning vs evening;
- high-volume vs low-volume shift;
- different menu mix;
- different responsibilities;
- different operational constraints.

Do not design normalization algorithms in this task.

Document only the conceptual requirement.

---

# Required updates outside Performance

Update only if required for links/index consistency:

```text
01 Domains/Personnel Management/README.md
01 Domains/Domain Architecture.md
```

Do not modify Selection, Training, Workforce or Personnel Decisions conceptually.

Do not modify Restaurant unless a broken link requires correction.

---

# Validation

Verify:

1. Performance is grounded in actual Reality.
2. Atomic observations are preserved conceptually.
3. Derived measures are distinguishable from source observations.
4. Review text is not collapsed into rating/sentiment.
5. No fixed KPI list is introduced.
6. PerformanceIndicator is contextual.
7. No universal scalar Performance score is created.
8. Context affects interpretation/comparability.
9. Temporal evolution reuses Core Temporal Coherence.
10. Performance does not make Personnel Decisions.
11. Selection prediction is distinguished from actual Performance.
12. Customer Feedback and Review remain outside Personnel Management.
13. Restaurant is only a validation example.
14. No Runtime/Product design is introduced.
15. Nothing is staged.
16. Nothing is committed.

---

# Required report

Create:

```text
07 Tasks/Reports/TASK_PERSONNEL_001_REPORT.md
```

with exactly these sections:

## A. Summary
## B. Files created
## C. Files modified
## D. Performance definition
## E. Atomic evidence model
## F. Measures vs indicators
## G. Context and comparability
## H. Temporal Performance
## I. Relationship with Selection / Training / Personnel Decisions
## J. Customer Feedback / Review boundary
## K. Restaurant validation examples
## L. Deferred questions
## M. Git status / scope confirmation

---

# Restrictions

Do not:

- modify `00 Core/`;
- deeply model Workforce;
- redesign Selection;
- deeply model Training;
- deeply model Personnel Decisions;
- create Customer Feedback;
- create Review;
- define fixed KPIs;
- define a universal employee score;
- design Clover integration;
- design external integrations;
- design UI;
- design persistence schemas;
- stage;
- commit.

---

# Final response

After creating the report, return only:

1. a short completion summary;
2. the exact report path:

```text
07 Tasks/Reports/TASK_PERSONNEL_001_REPORT.md
```

Then stop.
