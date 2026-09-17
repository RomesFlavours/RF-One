# Selection Guidability and Training Handoff

**Version:** 0.1
**Status:** Draft (initial canonical foundation)
**Module:** Domain / Selection
**Origin:** Follow-up to the Selection/Training/Guided-Operations documentation audit (2026-09-07) and [PERSON_CONTINUITY_001.md](../PERSON_CONTINUITY_001.md)
**Recovery:** Reconstructed 2026-09-12 after uncommitted working-tree edits to this document were accidentally lost. §7 and the Related documents list have been updated to reflect [../TRAINING_SERVICE_001.md](../TRAINING_SERVICE_001.md) (a later, surviving decision); §11 item 6 has been closed on the same evidence. §11 item 5's original content could not be recovered — see the note at item 5 itself. No version number is asserted for what was lost; the Version above is unchanged from the last committed state.

---

## 1. Purpose

Selection must not only determine whether a candidate is **hirable**. It must also produce a structured baseline describing:

- what the person can already do;
- what can reasonably be learned;
- what can be compensated *temporarily*, during real work, through real-time guidance;
- what remains unsafe or unsuitable to delegate to either Training or guidance at the current stage.

This baseline is what Selection hands to Training when a [Selection Decision](SelectionDecision.md) results in hiring — see §5 and §7. It does not change how Selection reaches its decision; it makes explicit, in a structured form, knowledge Selection's existing reasoning (Evidence, Fit Assessment, Trainable Gap) already implicitly contains, so that knowledge is not lost at the Selection/Training boundary.

---

## 2. Four categories

Every evidenced aspect of a candidate's readiness for a role falls, where Evidence actually supports a classification, into one of four categories. An aspect with no supporting Evidence is an **Unknown** (see [CandidateEvidence.md](CandidateEvidence.md), "Absence of evidence is not evidence of absence") and must not be forced into one of the four merely to complete the picture.

```text
CAPABILITY          What the person can already perform independently, evidenced now.

TRAINABILITY        What the person does not yet know or cannot yet do, but can
                     reasonably learn through Training before working independently.

GUIDABILITY         What the person cannot yet perform autonomously, but can perform
                     correctly right now when given concise, contextual, real-time
                     guidance during actual work.

UNSAFE / NOT        What cannot, at the current stage, safely or economically be
SUITABLE            delegated to either Training or real-time guidance.
```

These four are not a new scoring model and do not replace any existing Selection concept — see §6 for how each maps onto, or extends, what Selection already defines.

---

## 3. Guidability

**Guidability** is the person's ability, right now, to perform correctly under concise, contextual, real-time guidance, even though they cannot yet perform the same task independently. It is distinct from **Trainability**:

```text
Trainability   → can this gap be closed through learning, before independent work begins?
Guidability     → can this gap be safely bridged, right now, by real-time assistance
                   *during* independent work, before it is fully closed?
```

A person may be highly guidable on a task while still being low on trainability for that same task at this point in time (they perform correctly with a timely hint today, but have not yet internalized the underlying judgment) — or the reverse (they learn the underlying judgment quickly in training, but respond poorly to being corrected in the moment). Selection must not assume these correlate.

### Illustrative characteristics (not a score, not a threshold)

Where Evidence supports it, Guidability may be characterized by observations such as:

- ability to understand concise instructions;
- ability to act correctly on a short hint;
- ability to follow an operational sequence once shown;
- contextual attention (noticing what a hint refers to, in the moment it matters);
- receptiveness to correction;
- stability under pressure while being guided;
- ability to change behavior quickly after guidance, rather than reverting;
- ability to work with real-time technological support (e.g. a device-delivered hint) without it becoming a distraction.

**No score, weighting, or threshold is defined by this document.** These characteristics are illustrative dimensions Evidence may speak to, in the same non-mandatory spirit [FitAssessment.md](FitAssessment.md) already uses for its own dimensions ("Possible dimensions... not mandatory universal fields"). A future task may define how Guidability is actually assessed — see §11.

---

## 4. Economic selection principle

Selection should not optimize only for a candidate's current competence at the moment of hiring.

> Selection should support the future RF-One objective of selecting the person who can become safely and economically useful **fastest** — not merely the person who currently appears most qualified.

Concretely: a less experienced candidate who is highly guidable and trainable may represent more value to the organization than a more experienced candidate who adapts poorly to RF-One's guidance and training. Apparent current qualification remains one input among several — this is a direct extension of the principle [Selection.md](Selection.md) already states ("Selection does not imply that the candidate with the highest apparent qualification is automatically the best decision"), now naming Guidability and Trainability explicitly as the two dimensions through which "fastest to become safely and economically useful" can be reasoned about.

**No economic formula, weighting, or decision rule is defined by this document.** This section records the principle Selection should remain compatible with; it does not compute anything.

---

## 5. Selection Output Baseline

The conceptual handoff from Selection to Training is a structured baseline, produced where Evidence actually supports each element — never invented to complete the picture:

```text
Confirmed capabilities         evidenced CAPABILITY (§2), with supporting Evidence
Known limitations               evidenced gaps not yet classified as Trainable,
                                 Guidable, or Unsafe — i.e. still partially Unknown
Trainable Gaps                  as already defined by TrainableGap.md — unchanged
Guidability observations        evidenced GUIDABILITY (§2/§3), where Evidence
                                 actually supports such an observation
Safety/operational constraints  evidenced UNSAFE / NOT SUITABLE (§2) items, and any
                                 hard Constraint already identified by TrainableGap.md
Uncertainty                     material Unknowns — what has not yet been evidenced
                                 at all, preserved as Unknown, never as a negative Fact
Evidence/provenance             the underlying CandidateEvidence each element above
                                 traces back to (see §6)
Expected initial support areas  where, on current Evidence, the person is expected to
                                 need Training and/or guidance immediately upon starting
                                 — an Inference, not a commitment or a curriculum
SelectionDecision                the Selection Decision this baseline accompanies,
                                 including its rationale, authority and expected Outcomes
```

This is a **conceptual container**, not a database schema, table design, or persistence format — consistent with how [SelectionDecision.md](SelectionDecision.md) already treats persistence as a Runtime concern ("This document does not define... a Decision Record schema; database fields"). No new database model is proposed or implied by this section.

Every element of the baseline must preserve the same epistemic status it had when Selection produced it (Fact, Observation, Evidence, Belief, Assumption, Inference, Hypothesis, or Unknown — see §6) rather than being flattened into unlabeled statements once assembled into the baseline.

---

## 6. Relationship to existing Selection concepts

This document does not replace, duplicate, or create a parallel model alongside Selection's existing concepts. It reuses and preserves them:

```text
CandidateEvidence      unchanged — remains the source of everything in the baseline;
                        every baseline element must trace back to specific Evidence,
                        exactly as CandidateEvidence.md already requires
FitAssessment          unchanged — Guidability is a candidate addition to Fit
                        Assessment's existing, non-mandatory "Trainability / Growth
                        Potential" dimension family (FitAssessment.md, "Possible
                        dimensions"), not a competing assessment
TrainableGap            unchanged — TRAINABILITY (§2) is the same concept
                        TrainableGap.md already defines; this document does not
                        redefine what a Trainable Gap is, only names it consistently
                        within the four-category framework
SelectionDecision       unchanged — remains the Decision the baseline accompanies,
                        not something the baseline replaces or overrides
Epistemic Boundary /    unchanged and mandatory throughout — every category in §2,
evidence traceability    and every element in §5, must remain traceable to its
                        Evidence and honest about its own uncertainty
```

Two clarifications on how the four categories (§2) relate to concepts TrainableGap.md already draws:

- **UNSAFE / NOT SUITABLE** is not a new disqualification criterion. It names, within this baseline, whatever TrainableGap.md already classifies as a **hard Constraint** or a **disqualifying incompatibility** — concepts that already exist and are already distinct from a Trainable Gap. This document does not change what qualifies as either.
- **GUIDABILITY** is the one genuinely new element. TrainableGap.md deliberately scopes itself to whether a gap can be closed *before* independent work begins ("training, practice, onboarding, or experience"); it does not address whether a gap can be safely *bridged during* independent work through real-time assistance. Guidability fills that specific, previously undocumented gap — see §3.

---

## 7. Handoff to Training

Training receives the Selection Output Baseline (§5) for the **same persistent person identity** defined in [PERSON_CONTINUITY_001.md](../PERSON_CONTINUITY_001.md) — the baseline is one of the things that document's §6 ("Candidate → Employee transition") requires to survive that transition without being lost.

```text
Selection            → produces the Baseline (§5), scoped to the person, not to a
                        role-agnostic profile
Person Continuity     → carries that Baseline's reference forward from Candidate
                        identity to Employee identity (PERSON_CONTINUITY_001.md §5-6)
Training               → receives the Baseline as its starting point
```

**Training must not restart assessment from zero.** Where Selection has already gathered Evidence, formed a Fit Assessment, or identified a Trainable Gap or a Guidability observation, Training begins from that baseline rather than re-discovering the same ground independently.

Training **may** verify or revise Selection's assumptions through new Evidence gathered during actual training (e.g. a Trainable Gap Selection estimated as low-effort may prove otherwise once training begins). When it does, the **prior Selection Evidence remains preserved and traceable** — a revision produces new Evidence and, where warranted, a new Inference; it does not overwrite or delete what Selection originally recorded, consistent with the same non-destructive discipline [SelectionDecision.md](SelectionDecision.md) and the Selection Feedback Intelligence Foundation already apply elsewhere in this Domain (append-only observation, immutable snapshots — see `reports/SELECTION_FEEDBACK_INTELLIGENCE_FOUNDATION_REPORT.md`).

**No Training curriculum, content, method, or duration is defined by this document** — that belongs to **Training**, the internal RF-One service responsible for the training cycle (see [../TRAINING_SERVICE_001.md](../TRAINING_SERVICE_001.md) and [SELECTION_PILL_ASSESSMENT_AND_TRAINING_READINESS_001.md](SELECTION_PILL_ASSESSMENT_AND_TRAINING_READINESS_001.md)), not to [Continuous Productivity Development/README.md](../Continuous%20Productivity%20Development/README.md), whose own broader, non-training productivity scope is unchanged — see item 6 in §11 below for how this boundary was closed.

---

## 8. Future Guided Operation compatibility

The Selection Output Baseline is designed to remain compatible with a future capability in which Training and a real-time operational-guidance capability (e.g. Restaurant's [Service Copilot](../../Business%20Domain/Restaurant/Service%20Copilot/README.md)) can eventually know, for a given person:

- what the person already knows (Capability, §2);
- what still requires Training (Trainability / Trainable Gap);
- where real-time guidance may safely compensate for a gap not yet closed (Guidability);
- what areas must not yet be delegated to independent operation at all (Unsafe / Not Suitable).

**This document does not define how Training or Service Copilot would actually consume the Baseline, what guidance logic would result, or any Minimum Safe Operational Level.** It only records that the Baseline is the kind of structured knowledge such a future capability would need as an input, so that Selection's existing reasoning does not have to be rebuilt from scratch when that capability is eventually designed.

---

## 9. Learning loop

The Baseline is also the anchor for a future validation loop this Domain is designed to remain compatible with, extending the loop already outlined in [Selection.md](Selection.md) and [PERSON_CONTINUITY_001.md](../PERSON_CONTINUITY_001.md) §9:

```text
Selection prediction (the Baseline: Capability / Trainability / Guidability / Unsafe)
  → Training
    → Guided Operation
      → Operational Evidence
        → validation or refutation of the original Selection assumptions
          → better future Selection
```

For example: a candidate assessed as highly Guidable on a specific task, whose subsequent guided operational performance confirms rapid correct response to real-time hints, validates that Selection assumption; the reverse — persistent failure to respond to guidance despite repeated attempts — refutes it, and is itself Evidence for how future Selection should weigh similar Guidability observations.

**No learning algorithm, scoring mechanism, or automatic feedback process is defined or implemented by this document.** This section only records the loop the Baseline must remain structurally capable of participating in later.

---

## 10. Explicit exclusions

This document does **not** define, decide, or imply any of the following:

- Training curriculum or content;
- Minimum Safe Operational Level;
- Progressive Autonomy;
- Support Dependency Decay;
- smartwatch interaction (remains [Smartwatch Interaction.md](../../Business%20Domain/Restaurant/Service%20Copilot/Smartwatch%20Interaction.md) scope);
- Service Copilot prompting/guidance logic;
- any change to Selection scoring (Selection remains scoreless by design — [SELECTION_CURRENT_STATUS.md](reports/SELECTION_CURRENT_STATUS.md), "Candidate scoring / universal ranking... deliberately not implemented"; the per-pill 1-5 Capability scale later introduced by [SELECTION_PILL_ASSESSMENT_AND_TRAINING_READINESS_001.md](SELECTION_PILL_ASSESSMENT_AND_TRAINING_READINESS_001.md) §4 is a narrower assessment/readiness representation for one pill at a time and does not reopen this exclusion — see that document's own "Reconciling this with 'Selection remains scoreless by design'");
- new hiring rules or workflow;
- new database models, schema, or migrations.

---

## 11. Open decisions

This list mixes three distinct states, kept explicit below so none is mistaken for another: items 1-4 are genuine, unresolved design questions this document deliberately leaves open; item 5 is historical and its original content is not recoverable (see its own note); item 6 was originally open and is now **closed**.

1. **How Guidability will eventually be assessed.** What evidence-gathering mechanism (structured interview, trial shift, simulation, or another method) would actually produce the Guidability observations described in §3 — not decided here.
2. **Whether Guidability becomes a formal [FitAssessment.md](FitAssessment.md) dimension, or remains a separate evidence/concept alongside Fit Assessment.** §6 notes it as a candidate addition to Fit Assessment's dimension family; whether it is formally added there, or kept structurally distinct, is not decided here.
3. **How "expected initial support areas" (§5) will actually be represented** once Training exists to receive them — as a structured field, a narrative note, or some other form.
4. **Which Selection observations are safe to pass into operational guidance at all.** Not every Selection-stage observation about a person (e.g. sensitive interview context) is necessarily appropriate to surface to a real-time guidance capability during live work — which subset of the Baseline is safe and relevant for that eventual purpose is not decided here.
5. **[Historical item — original content not recoverable.]** This list originally carried at least six items, as evidenced by external references to "item 6" below (see [SELECTION_PILL_ASSESSMENT_AND_TRAINING_READINESS_001.md](SELECTION_PILL_ASSESSMENT_AND_TRAINING_READINESS_001.md) and [../TRAINING_SERVICE_001.md](../TRAINING_SERVICE_001.md), both of which cite "§11, item 6" by that number). Item 5's own text was lost together with other uncommitted edits to this document (see "Recovery" above) and is not recoverable from any surviving repository evidence. Its position is preserved, not renumbered or removed, so that the existing external references to item 6 remain valid; no content is invented in its place.
6. **Training's Domain-boundary name — closed.** Whether the capability this document calls "Training" (§7) belonged to Operational Knowledge, to Continuous Productivity Development, to a distinct future Shared Domain, or to something else was originally recorded here as open. **This is now decided**, by the same Product Owner decision that closed the identical open point in [SELECTION_PILL_ASSESSMENT_AND_TRAINING_READINESS_001.md](SELECTION_PILL_ASSESSMENT_AND_TRAINING_READINESS_001.md) ("Training's Domain-boundary name — closed") and recorded in full in [../TRAINING_SERVICE_001.md](../TRAINING_SERVICE_001.md): Training is an internal RF-One service responsible for the entire training cycle described in §7 — not a new top-level Shared Domain folder; Operational Knowledge is a component internal to Training; Continuous Productivity Development keeps its broader, non-training productivity scope and requests a training intervention from Training rather than deciding the formative mechanics itself. See [../TRAINING_SERVICE_001.md](../TRAINING_SERVICE_001.md) for the full decision and for what it deliberately leaves open.

---

## Related documents

- [Selection.md](Selection.md), [CandidateEvidence.md](CandidateEvidence.md), [FitAssessment.md](FitAssessment.md), [TrainableGap.md](TrainableGap.md), [SelectionDecision.md](SelectionDecision.md)
- [../PERSON_CONTINUITY_001.md](../PERSON_CONTINUITY_001.md)
- [SELECTION_PILL_ASSESSMENT_AND_TRAINING_READINESS_001.md](SELECTION_PILL_ASSESSMENT_AND_TRAINING_READINESS_001.md) — extends this document's Baseline with per-pill Capability assessment and the Selection→Training handoff mechanics
- [../TRAINING_SERVICE_001.md](../TRAINING_SERVICE_001.md) — closes item 6 above ("Training's Domain-boundary name")
- [../Continuous Productivity Development/README.md](../Continuous%20Productivity%20Development/README.md) — sibling Shared Domain; keeps its broader, non-training productivity scope per [../TRAINING_SERVICE_001.md](../TRAINING_SERVICE_001.md) §4
- [reports/SELECTION_FEEDBACK_INTELLIGENCE_FOUNDATION_REPORT.md](reports/SELECTION_FEEDBACK_INTELLIGENCE_FOUNDATION_REPORT.md)
- [../../Business Domain/Restaurant/Service Copilot/README.md](../../Business%20Domain/Restaurant/Service%20Copilot/README.md)
