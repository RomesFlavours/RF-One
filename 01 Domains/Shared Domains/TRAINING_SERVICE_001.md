# Training — Internal Service Boundary and Responsibilities

**Version:** 0.1
**Status:** Approved — Product Owner decision recorded verbatim, closing the "Training's Domain-boundary name" open point named in [Selection/SELECTION_PILL_ASSESSMENT_AND_TRAINING_READINESS_001.md](Selection/SELECTION_PILL_ASSESSMENT_AND_TRAINING_READINESS_001.md) and [Selection/SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md](Selection/SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md) §11, item 6. **Documentation only: no code, model, migration, interface, service, or automation is implemented or changed by this document.**
**Scope:** Cross-cutting functional decision. Training is named here as an **internal RF-One service** — functionally, in the same sense [Selection/SELECTION_PILL_ASSESSMENT_AND_TRAINING_READINESS_001.md](Selection/SELECTION_PILL_ASSESSMENT_AND_TRAINING_READINESS_001.md) §1 already describes Selection ("internal RF-One services... not external products with their own independent identity or governance") — not as a new top-level Cross Domain folder. This document does not rename, move, or restructure any existing `01 Domains/Cross Domain/` folder, and does not introduce or change any technical identifier or authorization code.
**Origin:** Product Owner decision (2026-09-11) on the responsibilities of Training, Operational Knowledge and Continuous Productivity Development, closing the open point left by the 2026-09-07 Selection/Training/Guided-Operations documentation audit.

---

## 1. Why this document exists

[SELECTION_PILL_ASSESSMENT_AND_TRAINING_READINESS_001.md](Selection/SELECTION_PILL_ASSESSMENT_AND_TRAINING_READINESS_001.md) and [SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md](Selection/SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md) both used "Training" as the name of the capability that receives Selection's output at hiring, without a canonical document of Training's own to point to. Both recorded, as an explicit open point ("Training's Domain-boundary name"), whether that capability belonged inside Continuous Productivity Development, was a reason to extend Operational Knowledge beyond its "passive repository" definition, was a distinct future Cross Domain, or was something else.

This document records the Product Owner's decision on that point and gives "Training" the canonical reference it was missing. It does not reopen, and does not decide, anything else those two documents already left open — see §8 below.

---

## 2. Decision — Training is an internal RF-One service

**Training is the internal RF-One service responsible for the entire training cycle.** It is described functionally, the same way Selection already is — not as a new top-level Cross Domain, not as a Product, and not owned by Operational Knowledge or by Continuous Productivity Development.

Training governs:

- the catalog of pills and its linkage to the training needs the pills answer;
- the models per role and business context — which pills apply, at what expected level;
- the evaluation criteria for each pill and the expected thresholds;
- the weights an AI mechanism may propose, always confirmed by the trainer before use;
- the calculation of gap and priority (see [SELECTION_PILL_ASSESSMENT_AND_TRAINING_READINESS_001.md](Selection/SELECTION_PILL_ASSESSMENT_AND_TRAINING_READINESS_001.md) §7 for the formulas already decided there);
- the preparation of training paths;
- the assignment of a path — only after the trainer confirms it;
- the verification of learning and any subsequent updates.

This list restates, at the responsibility level, mechanics already decided in detail by [SELECTION_PILL_ASSESSMENT_AND_TRAINING_READINESS_001.md](Selection/SELECTION_PILL_ASSESSMENT_AND_TRAINING_READINESS_001.md) §1 and §6-§8. **This document does not change any of that mechanics — it names the service that owns it.**

---

## 3. Operational Knowledge is a component internal to Training

**Decision:** Operational Knowledge manages the knowledge patrimony and the pills. It is a **component internal to Training**, not a parallel service with responsibilities competing with Training's over the training cycle.

Concretely: the pill *content* itself — the retrievable knowledge patrimony Operational Knowledge already defines ([Operational Knowledge/README.md](Operational%20Knowledge/README.md), "Operational Knowledge Pills") — remains Operational Knowledge's own concern. The training-cycle responsibilities listed in §2 above — catalog governance and need-linkage, per-role/context models, evaluation criteria/thresholds, weights, gap/priority, path preparation, trainer-confirmed assignment, learning verification — belong to Training.

**This does not move, rename, or delete the `01 Domains/Cross Domain/Operational Knowledge/` folder.** The current document organization — Operational Knowledge as its own folder inside `01 Domains/Cross Domain/` — is unchanged by this decision. See §6 for why the functional decision and the folder's physical location are deliberately kept distinct here.

Operational Knowledge continues to serve any RF-One function that retrieves a Pill (e.g. Copilot), exactly as already documented — its "passive, retrievable, does not train/test/assess/certify" boundary ([Operational Knowledge/README.md](Operational%20Knowledge/README.md), "Purpose") is preserved by this decision, not overridden by it: Training does the governing and deciding; Operational Knowledge holds and serves the content.

---

## 4. Continuous Productivity Development keeps its broader, non-training scope

**Decision:** Continuous Productivity Development keeps the broader perimeter of productivity improvement, including interventions on organization, tools and processes — unchanged from [Continuous Productivity Development/README.md](Continuous%20Productivity%20Development/README.md) and [CONTINUOUS_PRODUCTIVITY_DEVELOPMENT_001.md](Continuous%20Productivity%20Development/CONTINUOUS_PRODUCTIVITY_DEVELOPMENT_001.md).

Continuous Productivity Development **may detect a productivity problem and request a training intervention from Training.** Training remains responsible for translating that request into formative gaps, priorities and paths, exactly as it does for any other trigger (§2). **Continuous Productivity Development must not duplicate the formative decisions Training governs** — it does not itself define a pill catalog, per-role/context thresholds, weights, or a training path; it hands an identified productivity problem to Training and lets Training decide the formative response.

Every other responsibility already recorded for Continuous Productivity Development — the non-training interventions it may still select (organization, tools, process redesign, reassignment, automation, or no intervention at all; see [CONTINUOUS_PRODUCTIVITY_DEVELOPMENT_001.md](Continuous%20Productivity%20Development/CONTINUOUS_PRODUCTIVITY_DEVELOPMENT_001.md) §3) — is unchanged and is not narrowed by this document beyond the training-duplication point above.

---

## 5. Selection and Assessment — unchanged

Assessment remains a function internal to Selection, exactly as [SELECTION_PILL_ASSESSMENT_AND_TRAINING_READINESS_001.md](Selection/SELECTION_PILL_ASSESSMENT_AND_TRAINING_READINESS_001.md) §1 already decided. Selection transmits to Training, at hiring, the evaluation for each individual pill, consolidated per that document's §5-§6. This document does not change, and does not reopen, any of the following — all already decided there, and unaffected by the Training-naming decision above:

- the score belongs to the single pill only, never to a group (§2);
- groupings are organizational only, never scored (§2);
- the 1-5 scale (§4.1);
- "Not evaluated" / "Not applicable" as non-numeric states, never a score (§4.2);
- lowest-score-wins consolidation at initial assessment — not a permanent ceiling (§5);
- evidence and revisions preserved, never overwritten (§8);
- Trainability, Guidability, and Unsafe/Not Suitable as dimensions distinct from Capability (§4.3, and [SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md](Selection/SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md) §2);
- a path is assigned only after the trainer confirms it (§6);
- the assessment picture is not visible to the candidate (§8).

Selection and Training are both described, functionally, as **internal RF-One services** — consistent with [SELECTION_PILL_ASSESSMENT_AND_TRAINING_READINESS_001.md](Selection/SELECTION_PILL_ASSESSMENT_AND_TRAINING_READINESS_001.md) §1.

---

## 6. Three distinct things: functional decision, document organization, implemented software

This document is a **functional decision**: it says who is responsible for what, inside the training cycle. It deliberately does not:

- move, rename, or restructure the `Operational Knowledge` or `Continuous Productivity Development` Cross Domain folders, or create a new top-level Cross Domain folder for Training;
- change any technical identifier, authorization code, database object, or the `Cross Domain` / `Business Domain` folder taxonomy itself;
- authorize development of any capability not already implemented.

**Current document organization**, unchanged by this decision: `Operational Knowledge` and `Continuous Productivity Development` remain the two folders under `01 Domains/Cross Domain/` onto which this decision's Training/Operational Knowledge/Continuous Productivity Development boundary is layered. No folder named `Training` exists at that level, and this document does not create one. Whether the physical documentation structure should eventually be reorganized to reflect §2-§4's functional decision more directly is a separate architectural question, **not decided here**.

**Already implemented software**, unchanged and unaffected by this document: `03 Software/Training/` and `rfone_data_store.training` already implement Training Pill, Training Need, Training Assignment and Training Attempt, predating and independent of this decision (see [SELECTION_PILL_ASSESSMENT_AND_TRAINING_READINESS_001.md](Selection/SELECTION_PILL_ASSESSMENT_AND_TRAINING_READINESS_001.md), "Already implemented, verified in this session"). This document does not add to, verify, or change that software, and does not authorize building anything against it beyond what already exists.

---

## 7. Closed point

**"Training's Domain-boundary name"** — named as an open point in [SELECTION_PILL_ASSESSMENT_AND_TRAINING_READINESS_001.md](Selection/SELECTION_PILL_ASSESSMENT_AND_TRAINING_READINESS_001.md) ("Training's Domain-boundary name — closed," formerly "Open point: Training's Domain-boundary name") and in [SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md](Selection/SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md) §11, item 6 — is **closed** by the decision in §2-§4 above:

> Training is an internal RF-One service responsible for the full training cycle. Operational Knowledge is a component internal to Training, managing the knowledge patrimony and the pills. Continuous Productivity Development keeps its broader, non-training productivity scope and routes training-shaped problems to Training instead of deciding them itself.

---

## 8. Points that remain open — not decided by this document

This document decides responsibility boundaries only. It does not decide, and does not authorize resolving, any of the following:

- progressive adaptation of the per-role/context assessment model during Selection ([SELECTION_PILL_ASSESSMENT_AND_TRAINING_READINESS_001.md](Selection/SELECTION_PILL_ASSESSMENT_AND_TRAINING_READINESS_001.md) §3, "OPEN — progressive adaptation of the model");
- conversion of the existing Training quiz score into the 1-5 Capability scale ([SELECTION_PILL_ASSESSMENT_AND_TRAINING_READINESS_001.md](Selection/SELECTION_PILL_ASSESSMENT_AND_TRAINING_READINESS_001.md) §4, "The existing Training quiz score is not assumed to already be this scale");
- whether any AI scoring engine beyond a pill's already-defined evaluation mechanism is authorized (same document, §4);
- how Guidability will eventually be assessed, and whether it becomes a formal FitAssessment dimension ([SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md](Selection/SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md) §11, items 1-2);
- whether the physical document/folder organization should eventually change to reflect §2-§4 more directly (§6 above);
- any other open point recorded elsewhere in this Domain that this document does not name above.

---

## Related documents

- [Selection/SELECTION_PILL_ASSESSMENT_AND_TRAINING_READINESS_001.md](Selection/SELECTION_PILL_ASSESSMENT_AND_TRAINING_READINESS_001.md)
- [Selection/SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md](Selection/SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md)
- [Selection/README.md](Selection/README.md)
- [PERSON_CONTINUITY_001.md](PERSON_CONTINUITY_001.md)
- [Operational Knowledge/README.md](Operational%20Knowledge/README.md)
- [Continuous Productivity Development/README.md](Continuous%20Productivity%20Development/README.md), [Continuous Productivity Development/CONTINUOUS_PRODUCTIVITY_DEVELOPMENT_001.md](Continuous%20Productivity%20Development/CONTINUOUS_PRODUCTIVITY_DEVELOPMENT_001.md)
