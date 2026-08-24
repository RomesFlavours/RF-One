# TASK_DOMAINS_002 — Canonicalize Personnel Management and Move Selection Under It

## Objective

Apply the approved RF-One architecture in which **Personnel Management** is the transversal Domain responsible for managing people across industries.

Canonical structure:

```text
01 Domains/Personnel Management/
├── README.md
├── Workforce/
├── Selection/
├── Training/
├── Performance/
└── Personnel Decisions/
```

Selection must no longer remain a top-level Domain.

The existing Selection documentation created by TASK_SELECTION_002 is conceptually valid and should be preserved, but moved under Personnel Management.

This is a documentation/architecture task only.

Do not implement software.
Do not design UI.
Do not design Runtime integrations.
Do not stage or commit.

---

# Mandatory first steps

1. Read `CLAUDE.md` completely.

2. Read:

```text
01 Domains/README.md
01 Domains/Domain Architecture.md
01 Domains/Restaurant/README.md
01 Domains/Restaurant/Roadmap.md
```

3. Read the complete current Selection Domain:

```text
01 Domains/Selection/
```

4. Read:

```text
07 Tasks/Reports/TASK_SELECTION_002_REPORT.md
07 Tasks/Reports/TASK_DOMAINS_001_REPORT.md
```

5. Read relevant Core 2.0 documentation for Subject, Reality, Goal, Decision, Action, Outcome, Learning, Evidence, Constraint, Assignment, Ownership, Temporal Coherence and Delegated Authority.

6. Run:

```bash
git status
```

before editing.

---

# Approved architectural decision

The canonical conclusion is now:

```text
Personnel Management
├── Workforce
├── Selection
├── Training
├── Performance
└── Personnel Decisions
```

These are **modules of one transversal Domain**, not independent top-level Domains.

Personnel Management is reusable across industries.

Restaurant and other technical Domains provide the technical standards, role requirements, operational context, and performance evidence required by Personnel Management.

---

# Module boundaries

## Workforce

Represents the current human structure of the organization.

Potential future concepts include Person/Worker, Role, Position, Assignment, Responsibility, Availability, Schedule and Employment Relationship.

Do not model these deeply in this task.

## Selection

Selection continuously identifies and evaluates economically viable human alternatives.

It is not vacancy-only.

Canonical statement:

> Selection continuously creates credible human alternatives for roles, whether or not the role is currently vacant.

Preserve the existing Selection concepts from TASK_SELECTION_002:

- Selection
- SelectionRequirement
- CandidateEvidence
- FitAssessment
- SelectionDecision
- TrainableGap

Do not redesign them unless a minimal edit is required to reflect the new parent Domain.

## Training

Training attempts to close evidenced gaps when doing so is operationally and economically justified.

It consumes the required standard, observed gap, technical knowledge from the target Domain, role/context, learning methods and later Performance evidence.

Do not model Training deeply in this task.

## Performance

Performance represents what the person actually produces in Reality.

It may consume operational evidence such as sales, margin, service time, throughput, product mix, customer feedback, reviews, quality, financial outcomes and other target-Domain evidence.

Do not define a universal score.
Do not hard-code universal KPIs.

## Personnel Decisions

Personnel Decisions applies Core Decision semantics to people-related decisions.

Possible conclusions include retain, continue observing, correct, train, develop, move/reassign, change responsibilities, replace.

Personnel Decisions may compare:

```text
Expected value of current person

vs

Expected value of available alternative
- recruitment cost
- training cost
- transition cost
- uncertainty / risk
```

Do not redefine Core Decision.
Do not create automatic termination thresholds.

---

# Relationship with Restaurant

Restaurant remains primarily the technical/operational Domain.

Restaurant provides Personnel Management with restaurant role requirements, technical capabilities, operational standards, restaurant-specific context, operational evidence and expected outcomes.

Restaurant does not own generic Workforce, Selection, Training, Performance or Personnel Decisions.

---

# Relationship with Customer Feedback and Review

Customer Feedback and Review remain separate transversal Domain candidates.

They are not modules of Personnel Management.

Personnel Management / Performance may consume their evidence when relevant.

Do not create Customer Feedback or Review folders in this task.

---

# Repository changes

## 1. Create Personnel Management

Create:

```text
01 Domains/Personnel Management/
```

Create:

```text
01 Domains/Personnel Management/README.md
```

The README must document purpose, transversal scope, module map, relationship to Core 2.0, relationship to technical Domains, relationship to Customer Feedback / Review, continuous operating loop and current documentation status.

Include:

```text
Personnel Management
├── Workforce
├── Selection
├── Training
├── Performance
└── Personnel Decisions
```

## 2. Move Selection

Move:

```text
01 Domains/Selection/
```

to:

```text
01 Domains/Personnel Management/Selection/
```

Preserve all seven canonical Selection files.

Do not leave a duplicate `01 Domains/Selection/`.

Update internal Markdown links and wording only as necessary.

Selection remains conceptually the same; only its architectural parent changes.

## 3. Create minimal module placeholders

Create:

```text
01 Domains/Personnel Management/Workforce/README.md
01 Domains/Personnel Management/Training/README.md
01 Domains/Personnel Management/Performance/README.md
01 Domains/Personnel Management/Personnel Decisions/README.md
```

Each README should contain only purpose, module boundary, relationship to other Personnel Management modules, relationship to Core, relationship to technical Domains, and an explicit note that detailed modeling is deferred.

Do not create additional concept files.

---

# Update canonical architecture

Update:

```text
01 Domains/Domain Architecture.md
```

Replace the previous idea that Workforce, Selection, Personnel Management, Performance and Training are separate transversal Domain candidates.

The canonical structure is now:

```text
Personnel Management
├── Workforce
├── Selection
├── Training
├── Performance
└── Personnel Decisions
```

Customer Feedback and Review remain separate transversal Domain candidates.

Update:

```text
01 Domains/README.md
```

to add Personnel Management as a top-level Domain and remove Selection as an independent top-level Domain.

Update only if needed for consistency:

```text
01 Domains/Restaurant/README.md
01 Domains/Restaurant/Roadmap.md
```

Make only minimal changes needed to reference Personnel Management as the transversal parent of Workforce/Selection/Training/Performance.

Do not reorganize Restaurant.

---

# Economic management principle

Document this as a guiding Personnel Management principle:

```text
Observed Performance
→ communicate / correct / opportunity to improve
→ Training where economically justified
→ observe again

in parallel:

Selection
→ find credible alternatives

then:

Personnel Decision
→ compare current expected value with available alternatives
→ retain / develop / move / replace
```

The decision may consider expected performance, actual performance, recruitment cost, training cost, transition cost, time to standard, uncertainty, risk, applicable Constraints and authority.

Do not turn this into a rigid formula.

---

# KPI principle

Preserve the approved conclusion:

> KPIs are contextual and should not be hard-coded as universal truths.

Performance indicators may eventually depend on Goals, Brand, role, technical Domain, available Evidence and observed Outcomes.

Do not design KPI-discovery algorithms in this task.

---

# Validation

Verify:

1. `Personnel Management` exists as a top-level transversal Domain.
2. Workforce, Selection, Training, Performance and Personnel Decisions are modules inside it.
3. `01 Domains/Selection/` no longer exists as a canonical top-level Domain.
4. Existing Selection concepts are preserved.
5. Restaurant remains the technical/operational Domain.
6. Customer Feedback and Review remain outside Personnel Management.
7. Performance has no universal scalar score.
8. No universal KPI list is introduced.
9. Personnel Decisions reuse Core Decision.
10. No deep modeling of Workforce, Training, Performance or Personnel Decisions occurs.
11. No Product/Runtime design is introduced.
12. Markdown links are updated.
13. Nothing is staged.
14. Nothing is committed.

---

# Required report

Create:

```text
07 Tasks/Reports/TASK_DOMAINS_002_REPORT.md
```

with exactly these sections:

## A. Summary
## B. Files created
## C. Files moved
## D. Files modified
## E. Personnel Management boundary
## F. Module boundaries
## G. Selection migration
## H. Relationship with Restaurant
## I. Customer Feedback / Review boundary
## J. Economic personnel-management loop
## K. Deferred modeling
## L. Open Product Owner decisions
## M. Git status / scope confirmation

---

# Restrictions

Do not modify `00 Core/`, `02 Products/`, `03 Software/`, `08 External/`, `09 Strategy/` or `90 Archive/`.

Do not create Customer Feedback or Review folders.
Do not deeply model Workforce, Training, Performance or Personnel Decisions.
Do not invent fixed KPIs.
Do not design automatic firing rules.
Do not design UI.
Do not design integrations.
Do not stage.
Do not commit.

---

# Final response

After creating the report, return only:

1. a short completion summary;
2. the exact report path:

```text
07 Tasks/Reports/TASK_DOMAINS_002_REPORT.md
```

Then stop.
