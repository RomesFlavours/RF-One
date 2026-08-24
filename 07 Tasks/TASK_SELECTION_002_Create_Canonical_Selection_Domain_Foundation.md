# TASK_SELECTION_002 — Create Canonical Selection Domain Foundation

## Objective

Create the initial canonical RF-One **Selection Domain** under:

```text
01 Domains/Selection/
```

Selection is a **universal business Domain** for evaluating and selecting candidates for roles across industries.

Restaurant is the first concrete application context, but Selection itself must not be restaurant-specific.

Selection must build on Core 2.0 and consume technical/business knowledge from the target Domain rather than duplicating it.

The initial conceptual direction is:

```text
Business Goals
→ Brand
→ Service Model
→ Required Behaviors
→ Role / Context Requirements
→ Technical Domain Capabilities
→ Candidate Evidence
→ Fit Assessment
→ Selection Decision
→ Training Implications
→ Performance Outcomes
→ Learning
```

The purpose of this task is to create the first canonical `.md` definitions for Selection.

This is a **documentation-only Domain task**.

Do not implement software.
Do not design UI.
Do not create integrations.
Do not scrape candidate platforms.
Do not modify Core.
Do not make a Git commit.

---

# Mandatory first steps

1. Read `CLAUDE.md` completely.

2. Read the current Core 2.0 canonical documentation required by Selection, especially:

```text
00 Core/Entity.md
00 Core/Relationship.md
00 Core/Process.md
00 Core/Glossary.md
00 Core/ConceptualArchitecture/00_RF-One_Core_Vision.md
00 Core/ConceptualArchitecture/01_Subject_and_Reality.md
00 Core/ConceptualArchitecture/02_Desire_Goal_and_Reality_Check.md
00 Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md
00 Core/ConceptualArchitecture/04_Temporal_Coherence_and_Evolution.md
00 Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md
00 Core/ConceptualArchitecture/06_Business_Autopilot_and_Intelligence_Engine.md
```

3. Read Domain governance:

```text
01 Domains/README.md
01 Domains/Restaurant/README.md
01 Domains/Restaurant/Roadmap.md
```

4. Read all relevant Shelbi source material under:

```text
08 External/Shelbi/
```

including, where present:

```text
Management Team - Diagnosis and Meeting Plan.pdf
RF-One Model Review - Shelbi Fox.pdf
RF-One Strategic Reply - Shelbi Fox.pdf
Romes-Flavours-Project-Outline.pdf
Training-Content-Shot-List.pdf
```

5. Read any active Selection analysis/report already present, especially:

```text
07 Tasks/Reports/TASK_SELECTION_001_REPORT.md
```

If that report exists, treat it as analysis/provenance, not as canonical authority.

If it does not exist, proceed using Core 2.0 + Shelbi material + this task's approved direction.

6. Run:

```bash
git status
```

before editing.

---

# Architectural definition

Selection must answer a question of this general form:

> Which candidate is the best decision for this role, in this organization, under these Goals, Brand expectations, operational requirements, technical Domain requirements, Constraints, available Evidence, uncertainty, and risk?

Selection is **not** primarily:

- CV keyword matching;
- résumé scoring;
- personality typing;
- an ATS;
- a job board;
- an interview UI;
- a recruiting workflow product.

Those may later be Product/Runtime capabilities around the Domain.

Selection is the reusable knowledge and reasoning structure that allows RF-One to make or support a Selection Decision.

---

# Core boundary

Selection reuses Core concepts.

Do not redefine:

- Subject;
- Reality;
- Desire;
- Goal;
- Constraint;
- Decision;
- Action;
- Outcome;
- Learning;
- Evidence;
- Observation;
- Belief;
- Assumption;
- Inference;
- Hypothesis;
- Unknown;
- Delegated Authority;
- Subject Sovereignty;
- Temporal Coherence;
- Relationship;
- Ownership;
- Assignment.

Selection may specialize/contextualize them where necessary, but must not create parallel substitutes.

---

# Domain boundary

Selection consumes knowledge from other Domains.

Example:

```text
Restaurant Domain
→ technical requirements for Kitchen Manager

Selection Domain
→ evaluates whether a candidate satisfies those requirements
```

Selection must not redefine Restaurant knowledge such as:

- food cost;
- kitchen process;
- service sequence;
- purchasing;
- menu;
- restaurant operations.

Likewise, in another industry, Selection should consume that industry's Domain knowledge.

---

# Brand / business-context relationship

Selection should support:

```text
Goals
→ Brand
→ Service Model
→ Behaviors
→ Selection
```

This does not mean Brand alone determines hiring.

Selection should integrate:

- Brand expectations;
- technical Domain requirements;
- role responsibilities;
- Constraints;
- legal/policy restrictions;
- available candidate Evidence;
- trainable gaps;
- risk;
- expected Outcomes.

Do not convert Brand into a personality test.

---

# Workforce dependency

Selection will likely depend on future reusable Workforce/People semantics.

Examples:

- Person / Worker;
- Role;
- Position;
- Assignment;
- Responsibility;
- Availability;
- Schedule;
- Skill;
- Capability;
- Employment Relationship.

Do not create a Workforce Domain in this task.

Where Selection needs these concepts, reference them as external dependencies and define only the Selection-specific relationship to them.

---

# Canonical folder to create

Create:

```text
01 Domains/Selection/
```

---

# Canonical files to create

Create exactly these initial files:

```text
01 Domains/Selection/README.md
01 Domains/Selection/Selection.md
01 Domains/Selection/SelectionRequirement.md
01 Domains/Selection/CandidateEvidence.md
01 Domains/Selection/FitAssessment.md
01 Domains/Selection/SelectionDecision.md
01 Domains/Selection/TrainableGap.md
```

Also create the required task report:

```text
07 Tasks/Reports/TASK_SELECTION_002_REPORT.md
```

Do not create additional Selection files without explicit Product Owner approval.

---

# 1. `README.md`

Define:

- purpose of the Selection Domain;
- universal scope;
- Restaurant as first application, not architectural owner;
- relationship to Core 2.0;
- relationship to Brand;
- relationship to target technical Domains;
- future Workforce dependency;
- distinction from Product/Runtime recruiting workflow;
- list/index of canonical Selection documents.

Include a short architecture flow:

```text
Goals
→ Brand
→ Service Model
→ Behaviors
→ Role/Context Requirements
→ Technical Domain Requirements
→ Candidate Evidence
→ Fit Assessment
→ Selection Decision
→ Training / Performance feedback
```

State explicitly:

> Selection does not own the candidate source.

Candidates may come from ATSs, job boards, referrals, internal talent pools, direct applications, external recruiting systems, or other authorized sources.

---

# 2. `Selection.md`

Define the central Domain concept **Selection**.

Selection should represent the business activity / reasoning process of determining the most appropriate candidate for a defined role/context.

Cover:

- purpose;
- inputs;
- evaluation;
- uncertainty;
- Decision relationship;
- Outcomes;
- feedback/learning.

Important:

Selection must not imply that the candidate with the highest apparent qualification is always the best decision.

Selection may consider:

- role requirements;
- behaviors;
- technical capability;
- trainability;
- time to standard;
- risk;
- availability;
- Constraints;
- expected performance;
- evidence quality.

Do not define a universal scalar score.

---

# 3. `SelectionRequirement.md`

Define **Selection Requirement** as a requirement relevant to selecting a candidate for a particular role/context.

Requirements may originate from:

- Brand;
- Service Model;
- Process;
- role responsibilities;
- target Domain technical knowledge;
- Constraints;
- law/policy;
- availability;
- business Goals.

Classify requirement nature where useful, for example:

- mandatory;
- strong preference;
- trainable;
- contextual;
- prohibitive.

Do not force these into a rigid universal enum if the evidence does not justify it.

Distinguish:

```text
Requirement
from
Evidence that a candidate satisfies the Requirement
```

---

# 4. `CandidateEvidence.md`

Define **Candidate Evidence**.

Candidate Evidence is information relevant to evaluating a candidate against Selection Requirements.

Possible sources may include:

- résumé/CV;
- application;
- work history;
- structured interview;
- reference;
- work sample;
- assessment;
- certification;
- observed behavior;
- prior Outcome/performance data where legally and ethically permissible;
- candidate-provided information.

Every Candidate Evidence item should conceptually preserve:

- source;
- provenance;
- time/context;
- what was actually observed/stated;
- uncertainty;
- whether interpretation is Fact/Observation/Inference/Hypothesis/etc.

Explicitly state:

> absence of evidence is not evidence of absence.

Do not define scraping or ingestion mechanisms here.

---

# 5. `FitAssessment.md`

Define **Fit Assessment** as a contextual assessment of how well available Evidence supports a candidate's suitability for a specific role/context.

Fit is not a Fact and should not automatically be one scalar score.

Potential dimensions may include only where useful:

- Role Fit;
- Technical Fit;
- Behavioral Fit;
- Brand / Service Model Fit;
- Availability Fit;
- Constraint Fit;
- Team-context Fit;
- Trainability / Growth Potential;
- Risk.

The document must state that these are possible dimensions, not mandatory universal fields.

Fit Assessment must expose:

- supporting Evidence;
- contradicting Evidence;
- missing Evidence;
- assumptions;
- uncertainty;
- material risks.

Do not infer protected/sensitive traits.

Do not introduce personality pseudoscience.

---

# 6. `SelectionDecision.md`

Define **Selection Decision** as the Selection-specific application/context of the Core `Decision` concept.

Do not redefine Core Decision.

A Selection Decision may conclude, for example:

- proceed;
- do not proceed;
- gather more Evidence;
- compare with additional candidates;
- proceed conditionally;
- select with known Trainable Gaps.

The Decision should preserve:

- candidate/context;
- relevant Requirements;
- Evidence;
- Fit Assessment;
- uncertainty;
- Constraints;
- trade-offs;
- rationale;
- Decision authority;
- expected Outcomes.

Persistence of a Decision Record is a Runtime concern.

---

# 7. `TrainableGap.md`

Define **Trainable Gap** as a gap between current candidate capability/evidence and the desired role standard that may reasonably be addressed through learning, training, practice, onboarding, or experience.

Important distinctions:

```text
Trainable Gap
≠ hard Constraint
≠ disqualifying incompatibility
≠ missing Evidence
≠ demonstrated inability
```

The concept should help RF-One reason about:

- expected training effort;
- estimated time to standard;
- uncertainty of improvement;
- business cost/risk;
- whether the gap is acceptable relative to other candidate strengths.

Do not define a Training Domain.

Do not prescribe universal training durations.

---

# Restaurant application examples

Use Restaurant examples sparingly to validate universality.

Examples may include roles such as:

- Restaurant Manager;
- General Manager;
- Kitchen Manager;
- Server.

The examples should illustrate how the same Selection concepts consume different Restaurant Domain knowledge.

For example:

```text
Kitchen Manager
→ technical requirements from Restaurant Domain
→ required operational behaviors
→ Candidate Evidence
→ Fit Assessment
→ Selection Decision
```

Do not create Restaurant-specific Selection files yet.

Do not move these concepts into `01 Domains/Restaurant/`.

---

# Shelbi material use

Use Shelbi's work to inform examples and definitions around:

- management ownership;
- authority;
- decision-making;
- cross-functional cooperation;
- behavior under pressure;
- accountability;
- role clarity;
- trainable gaps;
- performance implications.

Do not canonize personal judgments about specific individuals.

Do not create psychological labels.

Translate observations into reusable Selection semantics only when justified.

---

# Candidate-source boundary

Selection does not own candidate acquisition platforms.

Do not create connectors or source-specific files for:

- Indeed;
- LinkedIn;
- ZipRecruiter;
- ATS systems;
- recruiting agencies;
- career sites.

Those belong later to Product/Runtime/integration architecture.

Selection only needs to know that Candidate Evidence has a source and provenance.

---

# Legal / fairness / governance safeguards

All Selection documents should remain compatible with future legal and fairness controls.

At minimum preserve these principles:

- only job-relevant criteria should influence Selection;
- sensitive/protected attributes must not be inferred or used improperly;
- Evidence provenance must be visible;
- Inference must not be silently promoted to Fact;
- uncertainty must be explicit;
- authority for the Decision must be known;
- jurisdiction-specific legal/policy rules are external Constraints;
- retention/privacy mechanisms belong to Product/Runtime governance.

Do not attempt to define employment law.

---

# Relationship to Training and Performance

Selection should be designed to learn later from:

```text
Selection assumptions / predictions
→ hire or assignment
→ Training
→ observed Performance
→ Outcome
→ Learning
→ better future Selection
```

Do not create Training or Performance domains in this task.

Only ensure the Selection definitions can support this future feedback loop.

---

# Documentation style

Use the existing RF-One canonical `.md` style.

For each concept file include, where consistent with repository conventions:

- Purpose / Definition;
- Core meaning;
- Inputs / relationships;
- Rules / safeguards;
- What it is not;
- examples;
- related concepts.

Avoid implementation schemas.

Avoid database field lists unless illustrative and explicitly non-prescriptive.

Avoid creating capitalized concepts casually.

---

# Authorized modifications

You may modify only:

```text
01 Domains/README.md
```

and only minimally, to add Selection to the Domain index if appropriate.

Do not modify any other existing file.

---

# Validation

After writing:

1. Verify Selection is universal and not Restaurant-specific.
2. Verify Restaurant is treated as the first application/example only.
3. Verify Core concepts are reused rather than duplicated.
4. Verify no Workforce Domain was created.
5. Verify no Product or Runtime workflow was created.
6. Verify no candidate-platform integration was designed.
7. Verify Fit is not treated as Fact or mandatory scalar score.
8. Verify Candidate Evidence preserves provenance and epistemic status.
9. Verify Trainable Gap is not conflated with missing Evidence or hard Constraint.
10. Verify Selection Decision references Core Decision rather than redefining it.
11. Verify Markdown links.
12. Run `git status`.
13. Do not stage.
14. Do not commit.

---

# Required report

Create:

```text
07 Tasks/Reports/TASK_SELECTION_002_REPORT.md
```

with exactly these sections.

## A. Summary

What Selection foundation was created.

## B. Files created

List exact paths and purpose.

## C. Selection architecture

Explain the resulting flow from Goals/Brand/Service Model/Domain Requirements to Decision and Learning.

## D. Core reuse

List which concepts are reused from Core and how duplication was avoided.

## E. Workforce dependencies

List concepts intentionally left external/future.

## F. Candidate Evidence and epistemic safeguards

Explain provenance, uncertainty, Fact vs Inference, and missing Evidence.

## G. Fit model

Explain why Fit is contextual and multidimensional rather than automatically one score.

## H. Trainable Gap

Explain the Selection/Training boundary.

## I. Restaurant validation examples

Explain how Restaurant examples were used without making Selection Restaurant-specific.

## J. Product / Runtime boundary

Confirm candidate acquisition platforms, ATS workflows, UI, scraping, integrations, persistence, and automation were not designed.

## K. Open Product Owner decisions

List only genuine unresolved decisions.

## L. Git status / scope confirmation

Confirm:

- Selection folder created;
- only authorized existing file modified, if any;
- no Core modification;
- no Restaurant modification;
- no Strategy modification;
- no Product modification;
- no Software modification;
- no Archive modification;
- no staging;
- no commit.

---

# Restrictions

Do not:

- modify `00 Core/`;
- modify `01 Domains/Restaurant/`;
- create Workforce;
- create Training;
- create Performance;
- modify `02 Products/`;
- modify `03 Software/`;
- modify `09 Strategy/`;
- modify `90 Archive/`;
- create Indeed/LinkedIn/ZipRecruiter integrations;
- implement scraping;
- create ATS workflows;
- stage;
- commit.

---

# Final response

After creating the report, return only:

1. a short completion summary;
2. the exact report path:

```text
07 Tasks/Reports/TASK_SELECTION_002_REPORT.md
```

Then stop.
