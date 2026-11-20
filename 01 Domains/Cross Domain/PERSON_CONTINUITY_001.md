# Person Continuity

**Version:** 0.1
**Status:** Draft (initial canonical foundation)
**Scope:** Cross-cutting concept — not owned by any single Domain. Applies wherever [Selection](Selection/README.md), Personnel Management ([Workforce](Personnel%20Management/Workforce/README.md)/Organization), Training (see [TRAINING_SERVICE_001.md](TRAINING_SERVICE_001.md) — an internal RF-One service, not a Cross Domain folder), [Performance](Performance/README.md), and any Business Domain's real-time operational-guidance capability (e.g. Restaurant's [Service Copilot](../Business%20Domain/Restaurant/Service%20Copilot/README.md)) each hold evidence about the same real person.
**Origin:** Follow-up to the Selection/Training/Guided-Operations documentation audit (2026-09-07) — see §11.
**Recovery:** Reconstructed 2026-09-12 after uncommitted working-tree edits to this document were accidentally lost. All references to the former `Training/README.md` placeholder have been corrected to [TRAINING_SERVICE_001.md](TRAINING_SERVICE_001.md) (Approved, 2026-09-11), which closed that naming question; §11's existing-state note has been updated accordingly, and Related documents now cross-reference the surviving Selection/Pills documents that already extend this one. No lost version number is asserted; the Version above is unchanged from the last committed state.

---

## 1. Purpose

RF-One must preserve the continuity of the same real person as they move through:

```text
Candidate
  → Selection
    → Hirable / Selected
      → Employee
        → Training
          → Guided Operation
            → Performance
              → Learning
```

The person must not become a new, disconnected identity each time they cross a Domain boundary. A candidate evaluated by Selection, hired into a role, trained, guided through early real-world operation, and later assessed by Performance is, throughout, **one person** — not a sequence of unrelated records that happen to share a name.

This document defines the continuity *requirement* and the *boundary rules* that follow from it. It does not define, and does not decide, how continuity is technically implemented — see §5 and §12.

---

## 2. Core principle

> **Candidate, Employee, Trainee, Server, Manager, etc. are roles or states of the same person — not separate people.**

Each of these is a context-specific role a person occupies at a point in time, in the same sense that [Domain Architecture.md](../Domain%20Architecture.md) §5 already treats Selection, Workforce, Personnel Decisions, Performance and Continuous Productivity Development as distinct *reasoning perspectives* on a person, not distinct people (Training, per [TRAINING_SERVICE_001.md](TRAINING_SERVICE_001.md), is a separate, internal RF-One service, not one of these five Domain-level reasoning perspectives). Person Continuity extends that same discipline to the person's **identity**, not only to the reasoning about them:

- Selection Evidence, Trainable Gaps, and a Selection Decision produced about a candidate;
- the Training history and current training state produced once that candidate is hired;
- the guidance a Service Copilot (or equivalent real-time operational-guidance capability) delivers to that person during actual work;
- the operational Performance evidence observed about that person;
- and any later Outcome or Learning drawn from all of the above;

must all be attributable to **one continuous person identity**, regardless of how many Domain-owned records exist about that person at any given time.

---

## 3. Why this matters

Continuity is a prerequisite — not an enhancement — for RF-One to eventually:

- transfer Selection Evidence into Training, instead of Training starting from zero knowledge of a person it may already have evaluated extensively;
- preserve identified [Trainable Gaps](Selection/TrainableGap.md) after hiring, so the specific gap Selection already characterized is what Training closes, rather than being rediscovered later at greater cost;
- let Training build on what Selection already established (Requirements the person was evaluated against, Evidence gathered, the Fit Assessment formed) rather than repeating that reasoning;
- let a real-time operational-guidance capability (e.g. Service Copilot) understand a person's known gaps and readiness, instead of guiding a person about whom it structurally knows nothing beyond their in-the-moment operational context;
- connect operational Evidence observed during real work back to that same person's development history, closing the loop the Restaurant Server Performance module already describes conceptually (`Server Performance.md`, "The Performance Loop") but cannot yet anchor to anything upstream of hiring;
- evaluate, after the fact, whether a Selection prediction (a Fit Assessment, an accepted Trainable Gap, an expected time-to-standard) was actually correct — which requires the later evidence to be traceable back to the specific person and the specific prediction it is meant to confirm or contradict;
- improve future Selection and Training from real downstream Outcomes, the feedback loop already named as a design intention in [Selection.md](Selection/Selection.md) ("Outcomes and feedback/learning") and in the [Selection Feedback Intelligence Foundation](Selection/reports/SELECTION_FEEDBACK_INTELLIGENCE_FOUNDATION_REPORT.md), but which cannot function without a stable subject to attach the feedback to.

Without person continuity, every one of these remains structurally impossible, independent of how sophisticated any individual Domain's own reasoning becomes.

---

## 4. Domain boundary rule

> **Domains may own their own role-specific records, but every such record must reference the same underlying person identity.**

This does not merge Domains, and does not change any Domain's existing ownership of its own concepts:

```text
Selection             owns Candidate Evidence, Fit Assessment, Trainable Gap, Selection Decision
Organization /         owns employment / assignment (Employee, Employee Assignment,
  Workforce             Restaurant Role — see 07 Tasks/Reports/TASK_ORGANIZATION_002_REPORT.md)
Training               owns training state / history (once modeled — Training is an internal
                        RF-One service, not a Cross Domain folder; see TRAINING_SERVICE_001.md)
Performance            owns operational Evidence / the Individual Performance Profile
                        (see ../Business Domain/Restaurant/Server Performance/
                        Individual Performance Profile.md for the Restaurant specialization)
Service Copilot        consumes current operational/person context; owns none of the above
                        (see ../Business Domain/Restaurant/Service Copilot/README.md, "Inputs")
```

Each Domain remains fully responsible for the meaning, correctness and lifecycle of its own records, exactly as established elsewhere (e.g. [Domain Architecture.md](../Domain%20Architecture.md) §5.6: "Workforce answers 'who,' Selection answers 'who else is viable,' ... Performance answers 'what actually happened,' and **Continuous Productivity Development** answers 'how do we close an evidenced gap or capture an opportunity'" — Training, per [TRAINING_SERVICE_001.md](TRAINING_SERVICE_001.md), is an internal RF-One service that governs the training cycle, not this Domain-level reasoning perspective). Person Continuity adds exactly one requirement on top of that existing separation: **every one of these Domain-owned records must be able to point back to the same person identity**, so that a person's records can be assembled across Domains without requiring any Domain to duplicate, absorb, or redefine another Domain's knowledge.

This is a narrower, identity-specific instance of the general [Cross-domain evidence principle](../Domain%20Architecture.md#7-cross-domain-evidence-principle) already recorded in `Domain Architecture.md` §7 ("The same Reality may inform multiple Domains... evidence reuse across Domains is expected and must not be blocked by artificial Domain silos"). §7 concerns evidence *content* reuse; this document concerns the *subject* that evidence is about remaining the same subject wherever it is reused.

---

## 5. Identity continuity

RF-One requires **one persistent person identity**, conceptually capable of linking:

- Candidate identity (the person as evaluated by Selection);
- Employee identity (the person as employed/assigned by Organization);
- Training identity/state (the person as a subject of Training, once Training is modeled);
- Operational performer identity (the person as guided in real time, e.g. by Service Copilot);
- Performance history (the person as observed by Performance over time).

**This document does not decide the implementation mechanism.** In particular, it does not decide between, and does not prescribe:

- a new Core-level `Person` entity that Selection's candidate identity, Organization's Employee, and any future Training/Performance subject identity all reference;
- a direct linkage between the existing `candidate_persons` table (Selection) and the existing `employees` table (Organization), with no new Core entity;
- any other technical mechanism.

This is recorded as an open implementation decision — see §12. What this document does fix is that *some* mechanism satisfying the continuity requirement in §2 must exist before Training, guided-operation feedback, or cross-Domain Learning can be built as anything more than isolated, non-connecting capabilities.

---

## 6. Candidate → Employee transition

A successful Selection Outcome may transition a person from Candidate into Employee. When this happens, the transition must **not lose**:

- the [Candidate Evidence](Selection/CandidateEvidence.md) gathered about that person;
- the [Fit Assessment](Selection/FitAssessment.md) formed from that Evidence;
- any [Trainable Gap](Selection/TrainableGap.md) identified and, where applicable, explicitly accepted as a condition of hire (see [SelectionDecision.md](Selection/SelectionDecision.md), "select with known Trainable Gaps");
- the [Selection Decision](Selection/SelectionDecision.md) itself, including its rationale, authority, and expected Outcomes;
- the relevant provenance/audit history behind all of the above (see [CandidateEvidence.md](Selection/CandidateEvidence.md), "What every Candidate Evidence item must conceptually preserve").

The requirement is conceptual: whatever becomes of the Candidate's Selection-side records after hiring, they must remain reachable from the resulting Employee identity — not archived in a way equivalent to deletion, and not orphaned by the transition. **This document does not define the hiring workflow, the transition event's technical mechanics, or where Selection's records physically live afterward** — that is Product/Runtime/implementation-decision scope (see §12).

---

## 7. Historical continuity

Employment termination and later rehire must not erase a person's prior history. Where identity can be reliably established, the same real person should remain recognizable across multiple, possibly non-contiguous, applications and employment periods — their prior Candidate Evidence, Fit Assessments, Trainable Gaps, Training history, and Performance history remaining associated with them rather than being recreated as if they were a new person each time they re-enter the organization's process.

**This document does not define the matching algorithm or mechanism** by which a returning person is recognized as the same person (e.g. how confidently a name/email/phone match, or any other signal, establishes that two records concern the same individual). That is left as an open implementation decision (§12), consistent with §8's requirement that such matching never silently become certainty it does not have.

---

## 8. Privacy / epistemic boundary

Person Continuity does not relax any existing RF-One principle about evidence traceability or certainty. It is bound by the same [Epistemic Boundary](../../00%20Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md) discipline already mandatory throughout Selection and Performance:

- evidence and conclusions must remain traceable to their source, exactly as [CandidateEvidence.md](Selection/CandidateEvidence.md) already requires ("source," "provenance," "time/context");
- an identity linkage between two records is itself a claim with an epistemic status, and must never be silently presented as a Fact when it is actually an Inference or a best-effort match;
- **confirmed identity linkage** (e.g. established through a verified, unambiguous mechanism) must be visibly distinguished from **uncertain/best-effort identity matching** (e.g. name/email/phone similarity of the kind Selection's existing `identity_service.py` already performs between candidate records — see §11), in the same way Selection already distinguishes STRONG/POSSIBLE match suggestions from an automatic, confident attachment;
- an uncertain identity match must never, by itself, silently merge two people's histories, transfer evidence between them, or auto-attach one person's Trainable Gap or Performance history to another person's record;
- where identity cannot be established with the confidence a given downstream use requires (e.g. transferring a Trainable Gap into an active Training record), that uncertainty must be surfaced, not resolved by assumption.

---

## 9. Learning continuity

Person Continuity is the prerequisite for a future learning loop RF-One is designed to remain compatible with, already anticipated in outline by [Selection.md](Selection/Selection.md) ("Outcomes and feedback/learning") and [Selection/README.md](Selection/README.md) ("Relationship to future Training and Performance"):

```text
Selection prediction
  → Training
    → Guided operational performance
      → observed Outcome
        → person history
          → downstream Learning
            → better future Selection / Training
```

**This document defines only the continuity prerequisite for this loop — not the learning algorithms, not how a prediction is later scored against an Outcome, and not how Learning feeds back into future Selection or Training reasoning.** Those remain future scope, dependent on Training and the relevant Learning mechanisms being modeled in depth first.

---

## 10. Explicit exclusions

This document does **not** define, decide, or imply any of the following. They are named only to fix the boundary of this document, not because they are unimportant:

- Training curriculum, methods, or duration (remains Training's own scope — an internal RF-One service, not a Cross Domain folder; see [TRAINING_SERVICE_001.md](TRAINING_SERVICE_001.md));
- Minimum Safe Operational Level;
- Guidability scoring;
- Progressive Autonomy;
- Support Dependency Decay;
- Service Copilot guidance logic (remains [Service Copilot](../Business%20Domain/Restaurant/Service%20Copilot/README.md) scope);
- Performance scoring or any universal KPI (remains excluded by [Domain Architecture.md](../Domain%20Architecture.md) §8, "KPI discovery principle");
- hiring/HR workflow implementation, database schema, or migrations.

---

## 11. Existing-state note

The 2026-09-07 documentation audit (Selection / Training / Guided Operations) found the following, which this document treats as the current gap, not the target design:

- `candidate_persons` (Selection) and `employees` (Organization) are **not presently formally linked** — there is no foreign key or other structural reference between them in the current schema. Selection's own identity matching (`identity_service.py`) operates only *within* Selection, resolving whether two applications concern the same candidate — it does not, and structurally cannot, reach across into Employee identity.
- Selection already has **downstream-feedback foundations** — the `selection_downstream_outcome_feedback` table described in the [Selection Feedback Intelligence Foundation report](Selection/reports/SELECTION_FEEDBACK_INTELLIGENCE_FOUNDATION_REPORT.md), explicitly built "structurally separate, never touching Case Memory" — but that report also explicitly lists "Training integration" and "Performance integration" among the items **deliberately not implemented**. The foundation is a placeholder capable of one day receiving downstream evidence; it is not yet an active continuity mechanism.
- Training's Domain-boundary name was, at the time of the 2026-09-07 audit, an open question — whether the "closes an evidenced gap" capability the former `Training/` placeholder reserved belonged to Operational Knowledge, to Continuous Productivity Development, to a distinct future Cross Domain, or to something else. **This is now closed** (Product Owner decision, 2026-09-11): Training is an internal RF-One service responsible for the entire training cycle, with Operational Knowledge as a component internal to it and Continuous Productivity Development requesting training interventions from it rather than deciding the formative mechanics itself — see [TRAINING_SERVICE_001.md](TRAINING_SERVICE_001.md). This closes the *naming* question only; it does not by itself create the technical continuity mechanism §12 still requires, and the `candidate_persons`/`employees` structural gap noted above remains exactly as described.

None of the above is treated here as acceptable end-state architecture — it is the reason this document exists.

---

## 12. Open implementation decisions

The following are genuine, unresolved decisions this document deliberately leaves open. They require explicit Product Owner and/or architectural decision before implementation begins:

1. **Persistent Person representation.** Whether RF-One introduces a new Core-level `Person` entity that Candidate, Employee, and any future Training/Performance subject all reference, or achieves continuity through some other structural means.
2. **Confirmed identity-link mechanism.** What actually qualifies as a *confirmed* (not merely best-effort) link between a Candidate identity and an Employee identity — e.g. an explicit hiring event, a verified credential, or another mechanism — and how that differs from the uncertain/best-effort matching Selection already performs internally.
3. **Transition event, Candidate → Employee.** How and when the transition described in §6 is technically triggered and recorded — what happens at the moment a Selection Outcome becomes a hire, and which system of record owns that event.
4. **Rehire / duplicate-person resolution.** How RF-One technically resolves whether a new Candidate or a new Employee record is, or is not, the same person as an existing historical record — the matching mechanism §7 explicitly defers.
5. **Where Selection's pre-hire records live relative to the Employee identity after transition** — whether they are referenced in place, migrated, or otherwise made reachable — left open pending decision 1.

---

## Related documents

- [Selection/README.md](Selection/README.md), [Selection.md](Selection/Selection.md), [CandidateEvidence.md](Selection/CandidateEvidence.md), [FitAssessment.md](Selection/FitAssessment.md), [TrainableGap.md](Selection/TrainableGap.md), [SelectionDecision.md](Selection/SelectionDecision.md)
- [Selection/SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md](Selection/SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md), [Selection/SELECTION_PILL_ASSESSMENT_AND_TRAINING_READINESS_001.md](Selection/SELECTION_PILL_ASSESSMENT_AND_TRAINING_READINESS_001.md) — both extend this document's continuity requirement with the Selection Output Baseline and its handoff to Training
- [TRAINING_SERVICE_001.md](TRAINING_SERVICE_001.md) — Training's canonical boundary (internal RF-One service, not a Cross Domain folder)
- [Performance/README.md](Performance/README.md)
- [Personnel Management/README.md](Personnel%20Management/README.md)
- [../Domain Architecture.md](../Domain%20Architecture.md), §5 (Domain distinctions) and §7 (Cross-domain evidence principle)
- [../Business Domain/Restaurant/Service Copilot/README.md](../Business%20Domain/Restaurant/Service%20Copilot/README.md), [../Business Domain/Restaurant/Server Performance/Individual Performance Profile.md](../Business%20Domain/Restaurant/Server%20Performance/Individual%20Performance%20Profile.md)
- [../../00 Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md](../../00%20Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md)
- `07 Tasks/Reports/TASK_ORGANIZATION_002_REPORT.md` — canonical Employee identity, multi-Location, referenced by Server Performance
- [Selection/reports/SELECTION_FEEDBACK_INTELLIGENCE_FOUNDATION_REPORT.md](Selection/reports/SELECTION_FEEDBACK_INTELLIGENCE_FOUNDATION_REPORT.md) — existing downstream-feedback foundation this document's §12 decisions would activate
