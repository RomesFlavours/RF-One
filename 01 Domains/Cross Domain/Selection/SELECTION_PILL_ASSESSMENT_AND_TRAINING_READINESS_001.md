# Selection Pill Assessment and Training Readiness

**Version:** 0.2
**Status:** Draft — Product Owner decisions recorded verbatim; pending formal architectural sign-off. **Documentation only: no code, model, migration, interface, or automation is implemented by this document.** The "Training's Domain-boundary name" open point this document originally recorded (see below) is now **closed** — see [../TRAINING_SERVICE_001.md](../TRAINING_SERVICE_001.md).
**Module:** Domain / Selection, with a direct handoff boundary to Training (see "A note on the name 'Training'" below)
**Origin:** Product Owner decision set on Assessment inside Selection and the Selection → Training handoff (this task). Extends [SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md](SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md) and [PERSON_CONTINUITY_001.md](../PERSON_CONTINUITY_001.md) rather than replacing them.

---

## A note on the name "Training"

This document, like [SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md](SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md), [Selection.md](Selection.md) and [PERSON_CONTINUITY_001.md](../PERSON_CONTINUITY_001.md) before it, uses **"Training"** as the name of the capability that receives Selection's output, governs the pill catalog, and turns a gap into an assigned training path. This is the name the Product Owner used throughout the decisions recorded here, and it is also the name the already-implemented software uses (`03 Software/Training/`, `rfone_data_store.training` — Training Pill, Training Need, Training Assignment, Training Attempt).

It is **not**, however, the name of any current top-level Cross Domain folder — Training is named instead as an **internal RF-One service** (functionally, the same way Selection itself is described — see §1 below), not a new Domain folder. See "Training's Domain-boundary name — closed" below, and [../TRAINING_SERVICE_001.md](../TRAINING_SERVICE_001.md), for the Product Owner decision that gives Training this canonical reference and its responsibilities.

---

## 1. Assessment is internal to Selection

**Decision:** Assessment is a function performed **inside** Selection. It is not a new autonomous service, not a new Domain, and not owned by any capability outside Selection.

Selection and Training are both described, functionally, as **internal RF-One services** — not as external products with their own independent identity or governance. This document does not rename or move any `Cross Domain` folder, and does not open a general repository reorganization.

**Training's governance role.** Training (see the naming note above) governs:

- the catalog of pills;
- how pills are linked to the training needs they answer;
- the models per role and business context — which pills apply, at what expected level;
- the evaluation criteria for each pill;
- the expected thresholds;
- the importance weights;
- guidance on security-critical pills.

**The trainer prepares and validates the base assessment** — the model (§1's list above) — and makes it available to the person running Selection (the **selector**). The know-how belongs to the trainer: the selector is not assumed to be a subject-matter expert. Consequently, whatever tool Selection uses **must** surface explicit instructions and explicit evaluation criteria for every pill being assessed — a selector must never be left to guess what a given score means for a given pill.

---

## 2. The unit of evaluation is always the single pill

**Decision:** A score always belongs to **one pill**. Pills may be grouped, but a group exists **only** to keep the assessment internally homogeneous (e.g. presenting related pills together) — a group is never itself scored, and a group score is never redistributed back down onto its member pills.

Every pill must be linked, in the catalog, to the training need it answers. This catalog linkage is a **standing fact about the pill** ("this pill exists to close this kind of need") and must be kept distinct from a **need actually detected for a specific person**: the mere existence of a pill in the catalog never implies that a given individual has the gap that pill addresses. A pill only becomes relevant to a specific person once Assessment (§4-§5) actually evidences a gap for them.

**No parallel competency catalog.** Selection/Training must not introduce a second, independent taxonomy of "competencies" or "skills" alongside pills. The pill **is** the unit; a competency, where the concept is useful at all, is a way of grouping or describing pills (§2, first paragraph) — never a second, independently-scored entity.

---

## 3. The Selection path

**Decision — sequence:**

```text
CV
  → quiz, before the videocall
    → videocall (data entered by the selector)
      → new, fuller Assessment, built on everything collected so far
        → in-person interview (data entered by the selector)
          → hire
```

The **starting point** for Assessment is a **model per role and business context**, already validated by the trainer (§1). Selection does not invent evaluation criteria at runtime; it applies the model the trainer has already prepared.

Several of Selection's already-implemented capabilities plausibly correspond to stages in this sequence — Resume Screening (CV), Primary Screening / Phone Interview Framework (the pre-videocall quiz and the videocall itself), and the In-Person Interview Framework (the interview) — see `reports/` in this folder for their own implementation history. **This document does not verify or restate that correspondence in implementation detail** — it records the sequence as a Product Owner decision, and leaves the exact mapping onto existing stage/transition machinery (`SelectionOutcomeDecision`, `ApplicationStageTransition`, and similar) to whoever designs the implementation, per the Product Owner's explicit instruction that development priority is decided separately.

### OPEN — progressive adaptation of the model

The **intention** to progressively adapt the per-role/context model to what is learned about the specific person — starting from the CV — is **confirmed**. However, **the rules for how that adaptation works are not decided by this document** and must be analyzed separately. Concretely, none of the following is decided here:

- any algorithm for adapting the model to a person's CV or prior evidence;
- any automatic mechanism for changing which pills apply, or their weights, per person;
- any adaptation threshold;
- any approval step for an adapted model.

This is recorded as an explicitly **open** point, not an implementation gap to be quietly filled in later with an assumed answer.

---

## 4. Capability evaluation

**Decision — who scores.** RF-One (an automated mechanism) enters the score **only** where an evaluation mechanism is actually defined and available for that pill (e.g. a quiz item with a scored answer key). In every other case, the **selector** enters the score, applying the trainer's criteria (§1). **No AI scoring engine is assumed to already be authorized** — introducing one is a separate decision, not implied by this document.

Translating a specific proof point (a quiz answer, an observed videocall/interview response, a CV fact) into one of the five levels below must follow **explicit** criteria defined for that pill (§1, "evaluation criteria"). This document does not invent criteria that are missing; where a pill has no defined criteria yet, that pill cannot be scored against this scale until the trainer defines them (it remains "Not evaluated," §4.2 — never a guessed score).

### 4.1 The accepted scale

| Level | Meaning |
|---|---|
| 1 | Does not demonstrate the required knowledge or capability. |
| 2 | Demonstrates partial elements, with significant gaps. |
| 3 | Handles the ordinary case, with some gaps. |
| 4 | Demonstrates solid mastery in the expected cases. |
| 5 | Demonstrates complete mastery, including relevant variants. |

Criteria for what counts as level 1 through 5 **must be specified per pill** — this is part of the model the trainer prepares (§1). A universal, pill-independent rubric is not what this scale is; it is a shared 1–5 vocabulary that each pill's own criteria give concrete meaning to.

### 4.2 "Not evaluated" and "Not applicable" are states, not scores

**Not evaluated** (no assessment has been performed yet for this pill/person) and **Not applicable** (the pill does not apply to this role/context/person) are **distinct states**, kept separate from the 1–5 scale. Neither may ever be converted into a 0, into a failing score, or silently treated as level 1.

### 4.3 Capability is distinct from Trainability, Guidability, and Unsafe/Not Suitable

**Trainability**, **Guidability**, and **Unsafe / Not Suitable** (see [SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md](SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md) §2-§3) remain **distinct dimensions** of Selection. None of them collapses into, or is computed from, a pill's Capability score. A person can be scored low on Capability for a pill today while being highly Trainable or Guidable on that same pill — the two kinds of judgment are never merged into one number.

### The existing Training quiz score is not assumed to already be this scale

The already-implemented Training quiz mechanism (`03 Software/Training/`, `rfone_data_store.training` — Training Attempt / Training Overall Attempt) produces its own score today. **This document does not assume, and does not define, any conversion from that existing score into the 1-5 scale above.** If that existing mechanism is ever meant to feed pill-level Capability as defined here, the specific conversion criteria must be defined first — this document deliberately does not invent that conversion.

### Reconciling this with "Selection remains scoreless by design"

`reports/SELECTION_CURRENT_STATUS.md` records, correctly, that **Selection has no universal candidate ranking score** — no single number that ranks one candidate against another. That decision is **unchanged and not reopened here**. The per-pill Capability score defined in this section is a different, narrower thing: a structured evaluation of one pill for one person, used for readiness/training purposes (§7), never combined across pills into one aggregate candidate score, and never used to rank candidates against each other.

---

## 5. Evidence and consolidation

**Decision — what every piece of evidence conceptually preserves**, for a given (person, pill) pair:

```text
person and pill
score or state              (1-5, Not evaluated, or Not applicable)
source                      (e.g. quiz item, videocall note, interview note, CV fact)
response or observation     (what was actually answered/observed)
author                      (who entered it — RF-One's mechanism, or the named selector)
date
criteria version used       (which version of the pill's evaluation criteria applied — see §8)
```

**Manual evaluations require a short justification.** Where the selector, not an automated mechanism, enters the score, a brief rationale must be recorded alongside it.

**Consolidation rule — the lowest score wins.** When more than one valid evaluation exists for the same pill within the same Selection assessment, the pill's consolidated result is the **lowest** of those scores. **Averages are never used.** Every piece of evidence that contributed to the result — including the ones that did not "win" — is preserved, never discarded.

**Not evaluated / Not applicable never enter the numeric minimum.** Only actual 1-5 scores participate in the minimum calculation described above.

**This is a consolidation rule for the initial assessment, not a permanent ceiling.** Taking the lowest score consolidates what Selection knew at assessment time. It does not mean that score must be carried forward and kept as a floor once the person is in Training and learning — see §6.

---

## 6. Hiring and the handoff to Training

**Decision.** During Selection, the readiness picture (§4-§5) is filled in **progressively**, pill by pill, as evidence accumulates through the path in §3. **At hiring**, that picture is **consolidated and transmitted to Training.**

Two things this document explicitly does **not** do:

- it does **not** bring forward the transfer to Training to any earlier stage in §3 — consolidation-and-handoff is a hiring-time event, not a running live sync during Selection;
- it does **not** conflate **recording that a hire happened** with **the decision to hire** — the [Selection Decision](SelectionDecision.md) to proceed remains a separate, human, authority-bearing act (§"Subject Sovereignty and authority" in that document); this document only describes what happens to the assessment picture once that decision has already been made and a hire is being recorded.

**What Training does with the consolidated picture:**

```text
Training  → receives the picture, per pill
          → compares it against the applicable model's thresholds
          → calculates gap and priority (§7)
          → prepares a targeted training path aimed at reaching the thresholds
          → submits that path to the trainer
```

**The path is assigned only after the trainer confirms it.** No automatic assignment before that confirmation is permitted.

**After hiring, Selection does not need to reopen.** Quizzes and observations that occur after the hire feed Training directly; they are not required to route back through Selection.

---

## 7. Gap, weights, and priority

**Accepted formulas:**

```text
Gap      = max(0, expected level − observed level) / 4
Priority = Gap × pill's weight within the model's scope
```

**Units.** `expected level` and `observed level` are both points on the 1-5 Capability scale (§4.1); their difference is therefore also on that scale, and dividing by 4 (the scale's maximum possible spread) normalizes `Gap` to a dimensionless value between 0 and 1. `weight` is the pill's dimensionless share (a fraction, or equivalently a percentage) of the applicable model's total scope — see below. `Priority` is therefore also dimensionless, between 0 and 1, and is meaningful only **relative to other pills inside the same model's scope** — it is not a probability, a percentage of anything external, or a score comparable across different models.

**Weights sum to 100% within the defined scope.** "Scope" means the full set of pills belonging to one role/context model — the same denominator the weights are normalized against.

**Who sets weights.** An AI mechanism may **propose** weights. The **trainer confirms** them before they are used. No numeric weight is ever attached to a pill *grouping* — grouping (§2) remains purely organizational and carries no weight of its own.

**No cross-pill compensation.** A result above threshold on one pill never compensates for a gap on a different pill. Every pill's Gap/Priority stands on its own.

**Not evaluated pills are not given an invented gap.** A pill with no evidence yet stays flagged as needing assessment; it does not silently receive a Gap of 0 or a Gap of 1.

**Not applicable pills generate no need.** A pill correctly marked Not applicable for a person/role/context is excluded from Gap/Priority entirely and must never automatically produce a training need.

**Security-critical pills take precedence in ordering, never in exclusion.** The trainer identifies which pills are security-critical enough to require precedence over the numeric priority ordering above (e.g. a safety-critical pill with a modest numeric Priority may still need to be trained first). This precedence affects **the order training happens in** — it must never be automatically converted into a decision to exclude the candidate. Excluding a candidate remains a human [Selection Decision](SelectionDecision.md), never an automatic consequence of a security-critical flag.

### 7.1 Illustrative numeric example (not a validated model)

**This example is illustrative only.** It is not a training model any trainer has validated, and must not be used as one.

Assume a role/context model scoped to just two pills:

```text
Pill                          Expected level   Weight (of model scope)
Wine service technique              4                60%
POS order entry                     3                40%
                                                       ------
                                                       100%

Consolidated Capability score for this person (§5, lowest-score-wins already applied):
Wine service technique:  observed level 2
POS order entry:         observed level 4

Gap (wine service)      = max(0, 4 − 2) / 4 = 2 / 4       = 0.50
Gap (POS order entry)   = max(0, 3 − 4) / 4 = max(0,-1)/4 = 0.00

Priority (wine service)    = 0.50 × 0.60 = 0.30
Priority (POS order entry) = 0.00 × 0.40 = 0.00
```

Reading this example: the person exceeds the expected level on POS order entry (Gap and Priority both 0 — no need is generated there), and falls two levels short on wine service technique, which is also the more heavily weighted pill in this scope, producing the higher Priority. If wine service technique were additionally flagged by the trainer as security-critical, it would be sequenced first in the training path regardless of how its numeric Priority compared to other pills' — never used to exclude the candidate.

---

## 8. Revisions and visibility

**Models are versioned.** Role/context models (§1) carry a version. A future change to a model must **not** retroactively rewrite an assessment that has already been concluded — an already-concluded assessment stays attached to the criteria version that was actually in force when it was performed (see §5, "criteria version used").

**Corrections produce a new revision, never a silent overwrite.** A correction to an assessment that has already been transmitted to Training generates a **new revision**; the prior revision is kept, not discarded.

**Training updates without silent deletion.** When Training receives an updated picture, it must not automatically delete training paths, assignments, or results already on record as a side effect of that update.

**Who sees what:**

| Role | Access |
|---|---|
| Authorized Selection operators | Fill in and confirm assessment evaluations. |
| Authorized trainers | Consult the picture Training receives; confirm training paths (§6) and weights (§7). |
| The candidate | **Does not** see the assessment picture. |

The candidate not seeing the assessment picture does **not** prevent presenting them with the quiz questions or the assessment exercises themselves (§3) — the restriction is on the consolidated evaluation/scoring picture, not on the candidate-facing questions or prompts that produce the evidence in the first place.

---

## Training's Domain-boundary name — closed

The decisions in this document describe one coherent capability — governing the pill catalog, linking pills to needs, holding per-role/context models with thresholds and weights, comparing a consolidated Selection picture against those thresholds, computing Gap/Priority, and assigning a trainer-confirmed path — and call that capability **"Training,"** consistent with every other canonical document that already bridges Selection to it ([SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md](SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md), [Selection.md](Selection.md), [PERSON_CONTINUITY_001.md](../PERSON_CONTINUITY_001.md)) and with the already-implemented software (`03 Software/Training/`).

The current top-level Cross Domain structure has no folder named `Training` — it was conceptually split, on 2026-09-07, into two sibling Cross Domains, **[Operational Knowledge](../Operational%20Knowledge/README.md)** and **[Continuous Productivity Development](../Continuous%20Productivity%20Development/README.md)** — and this document previously recorded, as an open point, whether the Training capability described above belonged to one of those two, to a distinct future Cross Domain, or to something else.

**This is now decided.** Per the Product Owner decision recorded in [../TRAINING_SERVICE_001.md](../TRAINING_SERVICE_001.md):

- Training is an **internal RF-One service** responsible for the entire training cycle described above — not a new top-level Cross Domain folder, and not owned by either Operational Knowledge or Continuous Productivity Development;
- **Operational Knowledge is a component internal to Training**, managing the knowledge patrimony and the pills — not a parallel service with competing responsibilities over the training cycle;
- **Continuous Productivity Development** keeps its broader, non-training productivity scope (organization, tools, processes) and may request a training intervention from Training, but does not itself decide the pill-catalog/threshold/gap/priority mechanics this document defines.

This is a **functional decision**, distinct from the current document organization (the `Operational Knowledge` and `Continuous Productivity Development` folders are not moved, renamed, or merged by it) and from the already-implemented software (`03 Software/Training/` is unaffected). See [../TRAINING_SERVICE_001.md](../TRAINING_SERVICE_001.md) for the full decision and for the points it deliberately leaves open.

---

## Summary — what is decided vs. open vs. already implemented

**Decided in this document (Product Owner decisions, recorded here for the first time):**
- Assessment is internal to Selection, not a new service (§1).
- The pill is always the unit of scoring; grouping is organizational only (§2).
- The Selection path, including the new post-videocall Assessment step (§3).
- The 1-5 Capability scale and its criteria-per-pill requirement (§4).
- "Not evaluated"/"Not applicable" as non-numeric states (§4.2).
- The evidence model and the lowest-score-wins consolidation rule (§5).
- Hire-time consolidation and handoff; trainer-confirmation gate before assignment (§6).
- The Gap/Priority formulas, weight normalization, and the security-critical precedence-not-exclusion rule (§7).
- Versioning, non-retroactive correction, and role-based visibility (§8).
- The Training/Operational Knowledge/Continuous Productivity Development Domain-boundary name — **closed**, see "Training's Domain-boundary name — closed" above and [../TRAINING_SERVICE_001.md](../TRAINING_SERVICE_001.md).

**Explicitly left open (not decided here, not to be assumed):**
- How the per-role/context model progressively adapts to a specific person's CV/evidence (§3).
- Which specific evaluation-gathering mechanism produces Guidability observations, and whether Guidability ever becomes a formal FitAssessment dimension (unchanged from [SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md](SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md) §11, items 1-2).
- Whether any AI scoring mechanism is authorized to produce Capability scores beyond a pill with an already-defined evaluation mechanism (§4) — not assumed here.
- Any conversion from the already-implemented Training quiz mechanism's own current score into the 1-5 scale (§4) — not invented here.

**Already implemented, verified in this session (not newly decided, stated only as fact):**
- `03 Software/Training/` and `rfone_data_store.training` already implement Training Pill, Training Need, and Training Assignment/Attempt concepts in software, distinct from — and predating — the Operational Knowledge/Continuous Productivity Development conceptual split described above. No claim is made here about whether that software already implements the specific 1-5 scale, evidence model, or Gap/Priority formulas this document defines — it does not; those are new decisions as of this document.

**Not implemented by this document:** no code, schema, migration, interface, or automation. See the status line at the top of this document.

---

## Related documents

- [../TRAINING_SERVICE_001.md](../TRAINING_SERVICE_001.md) — closes the "Training's Domain-boundary name" open point this document originally recorded
- [SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md](SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md)
- [FitAssessment.md](FitAssessment.md), [CandidateEvidence.md](CandidateEvidence.md), [TrainableGap.md](TrainableGap.md), [SelectionDecision.md](SelectionDecision.md), [Selection.md](Selection.md)
- [../PERSON_CONTINUITY_001.md](../PERSON_CONTINUITY_001.md)
- [../Operational Knowledge/README.md](../Operational%20Knowledge/README.md)
- [../Continuous Productivity Development/README.md](../Continuous%20Productivity%20Development/README.md)
- [reports/SELECTION_CURRENT_STATUS.md](reports/SELECTION_CURRENT_STATUS.md) — source of the "no universal candidate ranking score" decision this document does not reopen
