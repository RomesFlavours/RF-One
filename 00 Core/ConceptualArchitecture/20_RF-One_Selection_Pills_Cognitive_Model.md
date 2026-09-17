# RF-One — Selection, Pills, Training and Cognitive Model

**Version:** 0.2 — reconciliation pass against existing canonical documentation (Domain Architecture, Operational Knowledge, Selection Guidability/Training Handoff, Continuous Productivity Development, Restaurant Service Copilot). Freezes the current Product Owner decisions before Shelbi/SWYFox proceeds with Training implementation and the Product Owner continues separately with Cognitive. Genuine unresolved contradictions are recorded in §25, not resolved by invention — see that section before treating any Template Domain relationship below as settled.
**Status:** CONCEPTUAL BASELINE — FROZEN FOR THE DECISIONS RECORDED HERE; UNRESOLVED ITEMS REMAIN OPEN (§25)
**Module:** Core / ConceptualArchitecture

---

## Related documents

- [01 Domains/Domain Architecture.md](../../01%20Domains/Domain%20Architecture.md) §4, §10 — the Shared Domains / Business Domain taxonomy; §10 was added by this task to record Template Domain as a proposed third category. See §1 and §25 below for what remains unreconciled between the two.
- [01 Domains/Shared Domains/Operational Knowledge/README.md](../../01%20Domains/Shared%20Domains/Operational%20Knowledge/README.md) — the canonical Operational Knowledge Pill. This document's Pill (§2) is the same concept, not a competing definition — see §2's reconciliation note.
- [01 Domains/Shared Domains/Continuous Productivity Development/README.md](../../01%20Domains/Shared%20Domains/Continuous%20Productivity%20Development/README.md) and [CONTINUOUS_PRODUCTIVITY_DEVELOPMENT_001.md](../../01%20Domains/Shared%20Domains/Continuous%20Productivity%20Development/CONTINUOUS_PRODUCTIVITY_DEVELOPMENT_001.md) — the Shared Domain that owns gap/opportunity evaluation and intervention selection; economic productivity optimization is its primary objective, development/Training is one candidate intervention among several, never privileged, and "no intervention" is an equally legitimate outcome. §18 below is written to match this precisely (the previous draft's §13/§16 were not).
- [01 Domains/Shared Domains/Selection/SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md](../../01%20Domains/Shared%20Domains/Selection/SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md) — the existing, canonical CAPABILITY / TRAINABILITY / GUIDABILITY / UNSAFE-NOT-SUITABLE model. §6 below reuses these four categories by name; it does not redefine them.
- [01 Domains/Business Domain/Restaurant/Service Copilot/README.md](../../01%20Domains/Business%20Domain/Restaurant/Service%20Copilot/README.md) — the existing, Approved Service Copilot module this document's §9 relates to a proposed Cognitive Template. See §25 for what that document does not yet say about itself.
- [00 Core/Cognitive Interface/RF-ONE_COGNITIVE_INTERFACE_CONCEPT.md](../Cognitive%20Interface/RF-ONE_COGNITIVE_INTERFACE_CONCEPT.md) — a separate, also-under-review Product Owner document describing a broader, cross-Domain "one functional mind" conversational layer (not restaurant- or Business-Domain-scoped). Related but not reconciled with the Cognitive Template proposed here — see §25.
- [00 Core/ConceptualArchitecture/07_Core_Glossary.md](07_Core_Glossary.md)
- `RF-Training-Modules.md` (Shelbi/SWYFox source) — not modified by this document; see §7 and §19.

---

## Purpose

Define the common information and process model that allows RF-One to use the same underlying knowledge for:

- Selection assessment
- traditional structured training
- LLM-assisted training
- real-time Cognitive guidance
- continuous operational assessment
- personalized retraining
- customer briefing and debriefing
- organizational learning

This is a conceptual baseline. It freezes the Product Owner decisions recorded in §1-§24 so that Shelbi/SWYFox can proceed with Training implementation and the Product Owner can continue separately with Cognitive from the same shared foundation. It formalizes a proposed model connecting Selection, Pills, Training, Cognitive guidance, Operations, continuous Evidence, Debriefing, and updated Person/Customer/Training knowledge, and formalizes the emerging concept of **Template Domains**. Where this document's proposals are not yet reconciled with existing canonical documentation, that is recorded explicitly in §25 — not silently resolved by inventing new architecture, and not left unmarked.

---

## 1. Domain Categories

RF-One recognizes three Domain categories.

### Business Domain

Owns actual operational facts and processes — the authoritative source of business truth.

Examples: Restaurant, Sales, Purchasing, Compensation.

Example: the Carbonara recipe belongs to the Restaurant Business Domain. Training or Cognitive must not create a second, conflicting copy of the recipe.

### Shared Domain

Provides a capability or knowledge structure genuinely shared across multiple Business Domains — industry-independent, per [Domain Architecture.md](../../01%20Domains/Domain%20Architecture.md) §3-4. This document does not redefine any existing Shared Domain (Selection, Operational Knowledge, Continuous Productivity Development, Performance, Personnel Management, Taxation, Administration).

### Template Domain

Defines a reusable structure/capability intended to be specialized inside a Business Domain. Template Domains are specialized/instantiated, **not** physically copy-pasted; the purpose of specialization is semantic and operational focus, not merely technical scaling.

Current candidates:

```text
Selection Template   → Restaurant Selection
Training Template    → Restaurant Training
Cognitive Template    → Restaurant Service Copilot
```

Example: Restaurant Service Copilot works primarily inside a smaller relevant universe — tables, guests, menu, recipes, POS, tickets, shifts, staff, service processes, restaurant procedures — instead of searching the entire RF-One organizational universe.

**Reconciliation note (see §25 for the full treatment):** Template Domain is a new proposal, recorded here and cross-referenced from [Domain Architecture.md](../../01%20Domains/Domain%20Architecture.md) §10, which that document's own §4 ("every Domain... belongs to exactly one of two families") is not rewritten to accommodate. Whether Selection Template/Restaurant Selection is a genuinely new relationship or a renaming of the already-canonical "Shared Domain consumes Business Domain technical content" pattern Selection already uses (§3-4 of Domain Architecture.md) is not decided here. Whether Training Template's curriculum/quiz/certification apparatus has any existing canonical owner at all (it does not appear to — see §7 and §25) is also not decided here.

---

## 2. Canonical Pill

Use ONE canonical meaning of Pill across this entire model.

> A Pill is the smallest reusable unit of canonical operational knowledge that RF-One can independently retrieve and relate to Evidence.

A Pill may represent: fact, property, relation, rule, instruction, action, procedure step, approved response, warning, decision condition, escalation condition.

A Pill is **NOT**: a course, a lesson, an assessment, a completion state, or proof that a Person knows something.

**Surfacing a Pill NEVER means training occurred, learning occurred, or competence was demonstrated.**

**Reconciliation: this is the same concept as the existing [Operational Knowledge Pill](../../01%20Domains/Shared%20Domains/Operational%20Knowledge/README.md), not a second, competing definition.** Operational Knowledge Pill's own defining properties — atomic, contextual, retrievable — and its own explicit exclusions ("does not train people... does not assume information was learned... does not test, assess, certify, or verify retention") match this section's definition directly. This document does not introduce a new Pill concept; it adopts Operational Knowledge Pill as the canonical Pill and uses that name interchangeably with "Pill" throughout.

Existing software terminology such as `TrainingPill` is implementation/model debt to review later (see §23). This task does not rename software.

---

## 3. Business Truth Must Not Be Duplicated

Business Domains remain authoritative for business truth.

Example — Restaurant owns Carbonara → Recipe → Ingredients. Training must not maintain a separate, conflicting recipe.

Operational Knowledge may expose/project useful structured information as Pills — e.g. Carbonara → cream_present = false. Restaurant Service Copilot may then answer "Does the Carbonara have cream?" by resolving Carbonara → Recipe → Ingredients → Cream present? → false → "No," without generative LLM reasoning where structured information can answer directly.

A Pill may therefore:

**A.** contain canonical knowledge directly, where the owning Domain is the Pill's own source; or
**B.** reference/project canonical facts owned by another Business Domain (Recipes, Menu, Wine, Policies, Procedures, Processes, Organization, Safety, Brand).

---

## 4. Pill Label

A Pill carries only the metadata needed to make it valid and unambiguous. Not every dimension is mandatory.

**Typical intrinsic characteristics:** identity, subject, type, property/action, canonical value, source, version, effective_from, effective_to.

**Training importance characteristics** may include: risk_if_unknown, benefit_if_known, mandatory, safety_critical, prerequisite relationships.

**Optional applicability dimensions**, only where they change which answer/action is valid: role, location, process, process_state, situation, object, jurisdiction, other discriminating scope.

Canonical rule:

> **Context belongs on the Pill only when that context can change which information or action is valid.**

Example: Carbonara ingredients do not depend on whether the requester is Server or Manager — Role is irrelevant. An Opening Procedure may differ by Role and Location — Role and Location matter there.

---

## 5. Person ↔ Pill

Competence does **not** live on the Pill. RF-One maintains Person ↔ Pill through Evidence.

Possible Evidence sources: Selection, Structured Training, Practical, Certification, Manager Observation, Operations, Cognitive Observation.

Evidence should preserve conceptually: Person, Pill, source, timestamp, context, result, assistance level (where relevant), confidence, recency.

Possible derived competence states may include: not assessed, demonstrated, assisted, repeatedly assisted, autonomous. **These are illustrative, not a final enumeration.**

---

## 6. Selection

Selection and Training must use a coherent competence vocabulary. **This document preserves, and does not redefine, the four categories already canonically defined in [SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md](../../01%20Domains/Shared%20Domains/Selection/SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md) §2:**

```text
CAPABILITY           What the person can already perform independently, evidenced now.

TRAINABILITY         Can this gap be closed through learning before independent work begins?

GUIDABILITY          Can this gap be safely bridged, right now, by real-time assistance
                      during independent work, before it is fully closed?

UNSAFE / NOT SUITABLE  What cannot, at the current stage, safely or economically be
                        delegated to either Training or real-time guidance.
```

CAPABILITY may generate the **first** Person ↔ Pill Evidence (§5) — e.g. professional wine opening: demonstrated; complaint listening: demonstrated; RF Carbonara composition: not expected/not assessed; RF allergy procedure: not yet learned.

TRAINABILITY is the same concept [TrainableGap.md](../../01%20Domains/Shared%20Domains/Selection/TrainableGap.md) already defines. GUIDABILITY is the ability to work effectively with real-time Cognitive guidance ([SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md](../../01%20Domains/Shared%20Domains/Selection/SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md) §3). UNSAFE / NOT SUITABLE names what that same document's §6 already identifies as a hard Constraint or disqualifying incompatibility — not a new disqualification criterion.

Selection therefore establishes: suitability, trainability, guidability, and initial Person ↔ Pill competence Evidence — this is a restatement, in Pill terms, of the Selection Output Baseline that document's §5 already defines, not a second, parallel baseline.

Initial Training Gap (illustrative restatement of the existing Trainable Gap concept — no new formula is defined here, consistent with that document's own "no economic formula... is defined" discipline):

```text
Required Competence
MINUS
Competence already sufficiently demonstrated
=
Initial Training Need
```

Mandatory/safety-critical competence may still require RF-specific verification even if prior experience exists.

---

## 7. Training Template

Training is a Template Domain candidate (§1; see §25 for what this does and does not have a reconciled home in existing Shared Domain documentation). Training consumes Pills and aggregates them into structured learning.

Training Template supports: Curriculum, Role Path, Module, Lesson, Quiz, Scenario, Practical, Gate, Sign-Off, Certification, Renewal.

**A Course/Module is primarily an aggregation of Pills + Training activities** — it must not become the primary storage location of canonical knowledge.

The structured model developed by Shelbi in `RF-Training-Modules.md` remains the principal reference for traditional/structured delivery. **This document does not modify that source document.** Future decomposition into Pills MUST preserve the ability to reconstruct Shelbi's original structured course, and must preserve source statuses such as COMPLETE, PARTIAL, CAPTURE, NEED DEMO VIDEO, NEED REVIEW, LOCATION SPECIFIC where applicable.

---

## 8. Structured / LLM-Assisted Training

LLMs belong primarily in the structured Training path. They may: explain approved knowledge, adapt explanation, tutor, simulate guests, generate practice, conduct exercises, assemble/present courses from approved Pills.

**The LLM is never the source of truth.** All Training must remain grounded in canonical RF-One knowledge.

---

## 9. Cognitive Template

Cognitive is a Template Domain candidate. Its Restaurant specialization is the **existing** Restaurant Service Copilot ([01 Domains/Business Domain/Restaurant/Service Copilot/README.md](../../01%20Domains/Business%20Domain/Restaurant/Service%20Copilot/README.md)) — this document does not create a separate Restaurant Cognitive system.

```text
Cognitive Template → Restaurant Service Copilot
```

Generic Cognitive capabilities: PULL, PUSH, GUIDANCE, OBSERVATION, BRIEFING, DEBRIEFING, EVIDENCE GENERATION.

**Reconciliation note:** Service Copilot's own README (Approved, v1.0) does not currently describe itself as a Template Domain specialization — it is documented as a Restaurant Domain module related to Continuous Productivity Development (one delivery mechanism for one intervention) and to Operational Knowledge (Pill retrieval). This document proposes the Cognitive Template relationship one-directionally; Service Copilot's own document is not rewritten to match (per this task's scope) and the relationship is not yet reconciled from that side. See §25.

---

## 10. Real-Time Cognitive Principle

Real-time Restaurant Service Copilot should prefer **structured, deterministic, fast, unambiguous** retrieval. Do not use an LLM merely to reason over information already available structurally.

Example:

```text
Guest: "Does the Carbonara have cream?"
Copilot: resolve current object = Carbonara → query canonical recipe
         → check ingredient/property → return answer
```

The employee should receive the answer fast enough for normal conversation.

---

## 11. Cognitive Modes

### PULL

Employee asks: "What do I do now?"; "How long does the Branzino take?"; "Does the Carbonara have cream?"

### PUSH

RF-One proactively delivers information because context makes it relevant — shift briefing after POS sign-in, specials, 86 items, operational changes, table-specific relevant information.

### GUIDANCE

RF-One guides work step-by-step. Employee: "I finished this. Now what?" — RF-One determines current process state and returns the next applicable action.

### OBSERVATION

RF-One observes real operational behavior and generates Evidence. The earpiece/microphone is therefore **both** an assistance interface **and** a continuous assessment sensor.

(BRIEFING, DEBRIEFING and EVIDENCE GENERATION are treated as their own generic Cognitive capabilities per §9; see §15-§17.)

---

## 12. Continuous Assessment

Possible real-world Evidence: correct autonomous response, correct autonomous action, cue required, full answer required, repeated request for the same information, operational error, successful recovery, successful customer interaction.

Operational evidence may be more meaningful than an artificial quiz when it directly demonstrates competence.

**But: Cognitive Observation produces Evidence, not automatic truth.** High-risk competence may still require explicit certification or human verification.

---

## 13. Assistance Dependency

RF-One should understand how much assistance a Person requires for a Pill.

Conceptually: full guidance → cue → assistance on request → monitored → autonomous. **These labels are not frozen as final enums yet.**

Repeated autonomous success should reduce assistance. Repeated dependency should create stronger gap Evidence.

---

## 14. Training Priority

Training priority must **not** simply follow course order. It derives from:

```text
KNOWLEDGE / PILL:  risk if unknown, benefit if known, mandatory/safety, prerequisites
CONTEXT:            applicability, exposure/frequency, role/location/process where relevant
PERSON ↔ PILL:      competence gap, evidence, assistance dependency, recency, confidence
```

Canonical principle:

> **The criticality belongs to the knowledge. Applicability belongs to the context. Competence belongs to the person. Training priority is derived from their intersection.**

**No numeric formula is frozen here.**

---

## 15. Briefing

### Shift Briefing

May occur after POS sign-in. Possible inputs: Person, role, location, shift, assignment, specials, 86 items, operational changes, relevant competency concerns.

### Table Briefing

Particularly useful for returning guests. May include appropriately authorized information: returning status, previously stated preferences, restrictions, prior service facts, reservation/context.

Keep briefing minimal and relevant.

---

## 16. Debriefing

After a table/service interaction, Cognitive should provide an honest, concise debriefing, distinguishing:

```text
WHAT WENT WELL
WHAT SHOULD IMPROVE
WHAT WAS LEARNED ABOUT THE EMPLOYEE
WHAT WAS LEARNED ABOUT THE CUSTOMER
WHAT MAY REQUIRE TRAINING
```

The normal debriefing should be short unless something significant happened.

---

## 17. Knowledge Feedback

Debriefing feeds different knowledge areas.

**Employee Knowledge** — updates Person ↔ Pill Evidence (§5).

**Customer Knowledge** — stores relevant facts learned about the guest. Explicit/observed facts must remain separate from inference.

**Training / Knowledge Signals** — Cognitive may detect a Person Gap Candidate (one Person asks the same thing repeatedly) or a Training/Knowledge Gap Candidate (many Persons ask the same thing repeatedly).

Canonical rule:

> **Cognitive observes and proposes. Training governance approves canonical knowledge.**

Cognitive must **not** automatically rewrite canonical Pills.

---

## 18. Continuous Productivity Development

Preserve the boundary with the existing [Continuous Productivity Development](../../01%20Domains/Shared%20Domains/Continuous%20Productivity%20Development/README.md) Shared Domain precisely as that Domain's own documents define it.

**COGNITIVE / SERVICE COPILOT:** assists, observes, collects Evidence, detects signals, briefs, debriefs, surfaces recommendations.

**CONTINUOUS PRODUCTIVITY DEVELOPMENT:** evaluates accumulated Evidence (Operational Data), identifies a Gap/Opportunity, estimates its expected economic value, determines the Best Intervention, measures the Outcome, and learns from the result.

**TRAINING:** provides the structured educational intervention **only when Training is the intervention Continuous Productivity Development selects** — it does not decide that a gap exists or that Training is the right response to it.

**Reconciliation correction (this section replaces language in the prior draft that no longer matches Continuous Productivity Development's actual, canonical model):** a gap or repeated signal detected by Cognitive (§17) is a **candidate** Gap/Opportunity for Continuous Productivity Development's governing loop — it is never a standing instruction to train, and Training is never the default or privileged response. Per [CONTINUOUS_PRODUCTIVITY_DEVELOPMENT_001.md](../../01%20Domains/Shared%20Domains/Continuous%20Productivity%20Development/CONTINUOUS_PRODUCTIVITY_DEVELOPMENT_001.md) §3, possible interventions include:

```text
Training
Cognitive Guidance
Coaching
Practical
Certification
teaching / practice / reminders / contextual information
manager intervention / workflow change / reassignment / process redesign / automation
No intervention
```

**"No intervention" is an explicit, legitimate output**, not an absence of one — a Gap observed by Cognitive is not automatically a Training need; it is, first, an economic question Continuous Productivity Development answers (§4 of that document), never assumed here.

---

## 19. The Complete Loop

```text
SELECTION TEMPLATE
  → Restaurant Selection
  → Capability / Trainability / Guidability / Unsafe (§6)
  → Initial Person ↔ Pill Evidence

then:

TRAINING TEMPLATE
  → Restaurant Training
  → Structured Training when useful

and/or:

COGNITIVE TEMPLATE
  → Restaurant Service Copilot
  → real-time assistance

then:

OPERATIONS
  → actual Questions / Actions / Situations

then:

COGNITIVE OBSERVATION
  → Evidence

then:

DEBRIEFING
  → Employee Knowledge
  → Customer Knowledge
  → Training/Knowledge Signals

then:

CONTINUOUS PRODUCTIVITY DEVELOPMENT
  → Gap/Opportunity Evaluation
  → Intervention Decision (Training, Cognitive Guidance, Coaching, Practical,
    Certification, or No Intervention — §18)

then potentially one of those interventions, then back to Operations.
```

The loop is continuous. Selection, Training and Operations are therefore not isolated information silos.

---

## 20. One Infrastructure — Multiple Delivery Modes

The **same** Pill infrastructure must support:

```text
Traditional Structured Training ↔ LLM-Assisted Training ↔ Guided Operations ↔ Cognitive Real-Time Copilot
```

Do not create two separate knowledge systems. The delivery method may vary by Person, by Pill, by Role, by Risk, by Situation, by available technology. If Cognitive proves ineffective for a specific Person or situation, the same underlying Pills must remain usable through Shelbi's structured Training model.

---

## 21. Ownership / Workstream Boundary

**SHELBI / SWYFOX:**

```text
Training Template
Restaurant Training specialization
structured Pill integration
decomposition of RF-Training-Modules.md into Pills
reconstruction of structured courses
personalized course assembly based on Person ↔ Pill gaps
Selection/Training handoff
interfaces to receive future Cognitive Evidence
```

**PRODUCT OWNER / COGNITIVE WORKSTREAM:**

```text
Cognitive Template
Restaurant Service Copilot
Pull, Push, Guidance, Observation
Shift Briefing, Table Briefing, Debriefing
real-time deterministic retrieval
operational Evidence generation
real-world interaction
```

**SHARED CONTRACT: PILL + EVIDENCE.**

The two workstreams must not depend on each other's internal implementation.

---

## 22. Immediate Validation Before Mass Decomposition

Before decomposing the entire Shelbi Training source, take **one** real module — preferably **S14 Problem Solving** or **S7 Menu Mastery** — and prove the model end-to-end:

1. decompose it into canonical Pills;
2. attach minimum necessary labels (§4);
3. map relevant Pills to Selection assessment where possible (§6);
4. rebuild Shelbi's original structured module from the Pills;
5. prove Restaurant Service Copilot can retrieve the same Pills in real time;
6. define operational Evidence against those Pills (§5, §12);
7. verify Continuous Productivity Development can interpret the resulting gaps (§18).

Only after this proof should broad Pill decomposition begin. **This document does not perform that decomposition** — it records the validation sequence that must happen first.

---

## 23. Implementation Debt

Existing software entity/name: **`TrainingPill`** (`03 Software/RF-One Data Store/rfone_data_store/models.py`) currently carries training-specific semantics (assignment, quiz, completion tracking) baked into its name and its surrounding schema (`TrainingNeed`, `TrainingAssignment`, `TrainingAttempt`).

The canonical conceptual Pill (§2) is now the neutral Operational Knowledge Pill. `TrainingPill`'s name and shape do not yet reflect that. **This is recorded as implementation/model debt to review later — this documentation task does not rename or migrate it.**

---

## 24. Design Principles

1. ONE KNOWLEDGE INFRASTRUCTURE.
2. PILL IS THE SHARED INFORMATION UNIT — the same concept as the Operational Knowledge Pill (§2), not a second definition.
3. BUSINESS TRUTH IS NOT DUPLICATED.
4. SELECTION ESTABLISHES THE INITIAL COMPETENCE STATE, using the existing CAPABILITY / TRAINABILITY / GUIDABILITY / UNSAFE-NOT-SUITABLE model (§6) — not a new one.
5. TRAINING AGGREGATES PILLS WHEN STRUCTURED LEARNING IS USEFUL.
6. COGNITIVE RETRIEVES AND APPLIES PILLS DURING REAL WORK.
7. COGNITIVE ALSO PRODUCES CONTINUOUS EVIDENCE.
8. DEBRIEFING FEEDS EMPLOYEE, CUSTOMER AND TRAINING KNOWLEDGE.
9. TRAINING PRIORITY IS DRIVEN BY RISK, BENEFIT, EXPOSURE AND PERSONAL GAP — never course order alone.
10. THE SAME PILLS MUST SUPPORT STRUCTURED, LLM-ASSISTED, COGNITIVE AND HYBRID TRAINING.
11. REAL-TIME COGNITIVE SHOULD PREFER DETERMINISTIC STRUCTURED RETRIEVAL OVER GENERATIVE LLM REASONING.
12. TEMPLATE DOMAINS SHOULD BE SPECIALIZED, NOT COPY-PASTED.
13. CONTINUOUS PRODUCTIVITY DEVELOPMENT DECIDES THE INTERVENTION — INCLUDING "NO INTERVENTION" — COGNITIVE AND TRAINING NEVER SELF-ASSIGN THAT DECISION TO THEMSELVES (§18).

---

## 25. Remaining Contradictions and Open Reconciliation Items

These are genuine, unresolved architectural questions. Per this task's own instruction, they are reported here, not resolved by inventing new architecture.

1. **Template Domain has no physical or canonical-status equivalent to Shared Domains/Business Domain.** [Domain Architecture.md](../../01%20Domains/Domain%20Architecture.md) §4 states every Domain under `01 Domains/` belongs to exactly one of two families, physically expressed as two folders. Template Domain (§1 here) is a proposed third category with no folder, and §4's own text is not rewritten to accommodate it (per this task's scope — only an additive §10 was appended to that document). Until reconciled, Template Domain is a Core-level (00 Core) proposal cross-referenced from, but not integrated into, the Domain-level (01 Domains) taxonomy.

2. **Selection Template's relationship to the already-canonical Selection Shared Domain is undecided.** Selection is already an Approved, top-level, transversal Shared Domain that consumes Restaurant's technical content as input ([Domain Architecture.md](../../01%20Domains/Domain%20Architecture.md) §2-3). "Selection Template → Restaurant Selection" (§1 here) may describe the identical relationship in different vocabulary, or may name something genuinely new. Not decided here.

3. **Training Template's curriculum/quiz/certification apparatus has no reconciled canonical owner.** [Operational Knowledge](../../01%20Domains/Shared%20Domains/Operational%20Knowledge/README.md) explicitly excludes curricula, courses, completion tracking, testing, assessment and certification. [Continuous Productivity Development](../../01%20Domains/Shared%20Domains/Continuous%20Productivity%20Development/CONTINUOUS_PRODUCTIVITY_DEVELOPMENT_001.md) §18 explicitly excludes "curriculum or course structures" and "certification states" from its own scope — it decides *that* Training should happen (as one candidate intervention among several, §18 here) but does not itself define or own the curriculum/lesson/quiz/gate/certification mechanics §7 describes. Training Template (§7) is therefore not yet a specialization of any existing Shared Domain in the way Domain Architecture.md's own taxonomy would require — it is a new proposal without a reconciled parent. This is the most material open item for the Shelbi/SWYFox workstream (§21) to be aware of.

4. **Cognitive Template's relationship to Restaurant Service Copilot is asserted one-directionally.** Service Copilot's own Approved README does not describe itself as a Template Domain specialization, and is not rewritten by this task to do so (§9). The relationship recorded here is this document's proposal, not yet confirmed from Service Copilot's own canonical side.

5. **Cognitive Template vs. the separate "RF-One Cognitive Interface" concept.** [00 Core/Cognitive Interface/RF-ONE_COGNITIVE_INTERFACE_CONCEPT.md](../Cognitive%20Interface/RF-ONE_COGNITIVE_INTERFACE_CONCEPT.md) — also CONCEPTUAL DIRECTION, UNDER REVIEW — describes a broader, cross-Domain "one functional mind" conversational layer spanning all of RF-One (e.g. approving a Tips calculation, checking an agenda), not narrowed to one Business Domain the way Cognitive Template → Restaurant Service Copilot (§9) deliberately is ("reduce semantic search space... rather than searching the whole RF-One organizational universe," §1). Whether these are the same Cognitive Template at two different altitudes, two genuinely different capabilities, or overlapping proposals that will need to be reconciled with each other before Cognitive implementation proceeds, is not decided here and is not addressed by either source document.

6. **Restaurant Training as a physical/organizational artifact is not defined.** §7 and §21 refer to "Restaurant Training specialization" as the target of Shelbi/SWYFox's work, consistent with the Selection Template/Cognitive Template naming pattern (§1), but no canonical document (this one included) defines what that specialization concretely is — a new module under Restaurant, a configuration of the Training Template, or something else. Not decided here.

None of these six items are resolved by this document. They are recorded so that Shelbi/SWYFox and the Product Owner's Cognitive workstream (§21) share the same list of open questions, rather than each silently assuming a different resolution.
