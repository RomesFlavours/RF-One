# TASK_DOMAINS_001 — Document Cross-Domain Architecture Conclusions

## Objective

Document the current RF-One architectural conclusions before further Domain modeling.

This is documentation-only. Do not implement software, redesign Core 2.0, create all future Domain folders, stage, or commit.

## Mandatory first steps

1. Read `CLAUDE.md`.
2. Read:
   - `01 Domains/README.md`
   - `01 Domains/Restaurant/README.md`
   - `01 Domains/Restaurant/Roadmap.md`
   - relevant Core 2.0 conceptual architecture
   - any current Selection task/report material
3. Run `git status`.

## Conclusions to canonicalize

### 1. Restaurant is primarily the technical/operational Domain

Restaurant knows restaurant-specific operations and technical knowledge, such as:

- front-of-house and kitchen operations;
- service processes and standards;
- menu and recipe execution;
- restaurant-specific inventory/purchasing semantics;
- restaurant-specific technical role requirements;
- restaurant operational constraints and outcomes.

Restaurant must not own a capability merely because that capability is first used in a restaurant.

### 2. Transversal Domain candidates

Current cross-industry Domain candidates are:

- Selection
- Workforce
- Personnel Management
- Performance
- Training
- Customer Feedback
- Review

Do not create these folders in this task.

### 3. Selection is continuously active

Selection is not vacancy-only.

Its role is to continuously identify and evaluate economically viable human alternatives for roles.

> Selection continuously creates credible human alternatives for roles, whether or not the role is currently vacant.

Selection consumes Goals, Brand expectations, role/context requirements, target-Domain technical requirements, Candidate Evidence, trainable gaps, expected performance, uncertainty, and replacement/training/transition economics.

### 4. Personnel Management is distinct from Selection

Personnel Management manages the person currently performing the role.

Conceptual flow:

```text
Observed performance
→ communicate / correct / give opportunity to improve
→ observe again
→ compare current expected value with available alternatives
→ retain / develop / move / replace
```

Selection finds alternatives.
Personnel Management manages the current person and may use those alternatives.

The question is operational/economic performance, not moral judgment.

### 5. Performance is distinct

Performance represents what people actually produce in Reality.

Restaurant examples may include sales, items sold, margin, service time, throughput, customer reactions, product mix, and other observed outcomes.

Do not define a universal performance score.

### 6. Workforce is distinct

Workforce represents the organization's current human structure.

Possible future concepts include Person/Worker, Role, Position, Assignment, Responsibility, Availability, Schedule, Employment Relationship.

Useful distinction:

> Workforce describes who currently occupies or can occupy organizational roles.

> Personnel Management manages the ongoing relationship and performance of those people.

### 7. Training is transversal

Training consumes the required standard from the target Domain, the observed/assessed gap, role/context, learning methods, and later performance evidence.

Restaurant supplies restaurant-specific knowledge to Training; Training itself is potentially cross-industry.

### 8. Customer Feedback is transversal

Any business with customers can receive feedback about an experience, product, service, employee, process, or other business aspect.

Customer Feedback is therefore a transversal Domain candidate.

### 9. Review is distinct from Customer Feedback

Review is also a transversal Domain candidate.

Customer Feedback concerns what the customer communicates to the business.

Review concerns a public or publishable representation of an experience intended for third-party readers.

They may be linked:

```text
Customer Feedback ↔ Review
```

but should not be collapsed prematurely.

### 10. Cross-domain evidence remains reusable

The same Reality may inform multiple Domains.

Example:

```text
"Tatiana was excellent but the entrée took too long."
```

may inform Personnel Performance, Restaurant Operations, Training, Customer Feedback, Review, and later Selection learning.

Do not define a new data hierarchy here.

### 11. KPI discovery is contextual

Do not canonize a fixed KPI list for each role.

RF-One should eventually determine relevant indicators from Goals, Brand, target Domain, role, available evidence, and observed relationships with Outcomes.

Sales/hour, contribution margin, named reviews, product mix, service time, customer feedback, etc. are possible indicators, not universal permanent KPIs.

Do not design KPI algorithms in this task.

## Canonical documentation changes

Create:

```text
01 Domains/Domain Architecture.md
```

with:

1. Purpose
2. Restaurant Domain boundary
3. Transversal Domain principle
4. Current transversal Domain candidates
5. Selection / Workforce / Personnel Management / Performance / Training distinctions
6. Customer Feedback / Review distinction
7. Cross-domain evidence principle
8. KPI discovery principle
9. Open questions

Update minimally:

```text
01 Domains/README.md
```

to link to it.

Update only if needed for consistency:

```text
01 Domains/Restaurant/README.md
01 Domains/Restaurant/Roadmap.md
```

Clarify only that Restaurant is primarily the technical/operational specialization and transversal Domains may consume Restaurant knowledge.

Do not reorganize Restaurant.

## Important boundary

This task does NOT authorize creation of:

```text
01 Domains/Workforce/
01 Domains/Personnel Management/
01 Domains/Performance/
01 Domains/Training/
01 Domains/Customer Feedback/
01 Domains/Review/
```

Selection may already exist or be under active work; do not redesign it here.

## Validation

Verify:

1. Restaurant does not own universal business capabilities.
2. Selection is continuously active, not vacancy-only.
3. Personnel Management is distinct from Selection.
4. Workforce is distinct from Personnel Management.
5. Performance is grounded in actual outcomes.
6. Training is potentially transversal.
7. Customer Feedback is transversal.
8. Review is distinct from Customer Feedback.
9. KPI lists are not universal hard-coded truths.
10. Core 2.0 is not redefined.
11. No unauthorized Domain folders are created.
12. No Product/Runtime design is introduced.
13. Nothing is staged or committed.

## Required report

Create:

```text
07 Tasks/Reports/TASK_DOMAINS_001_REPORT.md
```

with:

- A. Summary
- B. Files created
- C. Files modified
- D. Restaurant boundary
- E. Transversal Domain conclusions
- F. Selection / Personnel Management / Workforce / Performance / Training distinctions
- G. Customer Feedback / Review distinction
- H. Cross-domain evidence and KPI conclusions
- I. Open questions
- J. Git status / scope confirmation

## Restrictions

Do not modify `00 Core/`, `02 Products/`, `03 Software/`, `09 Strategy/`, or `90 Archive/`.
Do not create the future transversal Domain folders listed above.
Do not stage.
Do not commit.

## Final response

Return only a short completion summary and:

```text
07 Tasks/Reports/TASK_DOMAINS_001_REPORT.md
```

Then stop.
