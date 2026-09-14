# Visual/Video Context as Ambient Evidence for Cognito

**Version:** 1.0
**Status:** PROPOSED — Post-Baseline Conceptual Extension, a sub-extension of [16_Ambient_Operational_Context_and_In-Flow_Cognito_Assistance.md](16_Ambient_Operational_Context_and_In-Flow_Cognito_Assistance.md) (itself APPROVED — Post-Baseline Conceptual Extension). Core 2.0 is already frozen (`core-2.0-freeze`, commit `71de3663dba2716ccbb6c1f93ffd458e20da8ead`) and `release/rf-one-2.0` (tag `rf-one-2.0-baseline`) is a released baseline built from it. This document is a Product Owner conceptual exploration, not yet an approved architectural decision, produced on the same dedicated branch as document 16 (`docs/cognito-ambient-operational-context`), and does not retroactively extend `core-2.0-freeze`. Promotion to Approved status, and to a numbered Core Principle, remain separate, future Product Owner decisions — the same discipline already applied to documents 15 and 16.
**Module:** Core / ConceptualArchitecture

---

## Related documents

- [16_Ambient_Operational_Context_and_In-Flow_Cognito_Assistance.md](16_Ambient_Operational_Context_and_In-Flow_Cognito_Assistance.md) — this document specializes doc 16's §3 ("What may compose Ambient Operational Context," already illustrative and non-exhaustive) with one source category: visual/video signals. It does not add a new Cognito capability, does not redefine Ambient Operational Context, and does not reopen any of doc 16's sections.
- [15_Human_Operational_State_and_Adaptive_Cognito_Interaction.md](15_Human_Operational_State_and_Adaptive_Cognito_Interaction.md) — Human Operational State and its own "no fixed interpretive rule" discipline for authorized physiological evidence (§5), which §6 below extends, unmodified in substance, to visual evidence.
- [14_Cognito_RF-One_Cognitive_Intelligence.md](14_Cognito_RF-One_Cognitive_Intelligence.md) — Cognito and its capability list; this document does not add a new capability, it further specializes Context Interpretation exactly as doc 16 already does.
- [12_Attention_Management.md](12_Attention_Management.md) — who/when/priority/channel decisions, which remain Attention Management's own; §13 below states that visual evidence is, at most, one more input, never a decision.
- [13_Process_Activation_and_Trigger_Intelligence.md](13_Process_Activation_and_Trigger_Intelligence.md) — Trigger Discovery / Trigger Resolution / Authorized Consequence; §13 below states that visual observation is, at most, Trigger Discovery evidence.
- [09_Identity_Authority_and_Accountability.md](09_Identity_Authority_and_Accountability.md) — Authority and Delegation, which visual evidence never creates, extends, or bypasses; also the source of the Acting Identity/Authority discipline §9 and §10 below apply to a person or third party who merely appears in a frame, never confusing "appearing in an authorized view" with "being identified as an Acting Identity."
- [05_Epistemic_Boundary_and_Subject_Sovereignty.md](05_Epistemic_Boundary_and_Subject_Sovereignty.md) — the Epistemic Boundary this document's treatment of visual/video signals (§4) applies without modification: such signals are Evidence at most, never silently promoted to Fact.
- [../../01 Domains/Cross Domain/PERSON_CONTINUITY_001.md](../../01%20Domains/Cross%20Domain/PERSON_CONTINUITY_001.md) — stable person knowledge/continuity; §9/§10 below never feed an uncertain visual appearance into a continuous person identity.

---

## Purpose

This document formalizes **Visual/Video Context** as one source category of Ambient Operational Context (doc 16): how images and video, where authorized, may contribute to Cognito's understanding of what is happening around a person during work.

> **Visual/Video Context is a source of Ambient Evidence. It is not an automatic source of Fact.**

It does not redefine Ambient Operational Context, Cognito, Human Operational State, Attention Management, Trigger Intelligence, Identity/Authority, or the Epistemic Boundary. It specializes doc 16's §3 with one illustrative, non-exhaustive source category, and states the boundaries specific to visual/video signals that do not already follow automatically from doc 16's own text.

---

## 1. The canonical principle

> **Cognito may consume authorized visual/video signals as Ambient Evidence about the operational scene — never as an automatic Fact about that scene, and never as a basis for judging or diagnosing the person(s) who appear in it.**

Every subsequent section specializes one part of this principle.

---

## 2. What visual/video signals may contribute

Visual/video signals may contribute observations about the operational **scene**, illustratively and non-exhaustively:

- occupancy of a zone;
- presence of customers/staff;
- queue length;
- crowding;
- movement/flow;
- a table occupied/free;
- a person waiting;
- an associate near/far from a zone;
- objects present;
- a situation persisting over time;
- observable physical interactions;
- simple environmental events.

This list is illustrative, not a fixed or closed taxonomy — the same discipline doc 16 §3 already applies to Ambient Operational Context generally, and [12](12_Attention_Management.md) §2/§10 and [15](15_Human_Operational_State_and_Adaptive_Cognito_Interaction.md) §2 already apply to their own respective inputs. What is actually available and authorized is a Domain/Runtime/Product question, not fixed here.

---

## 3. Scene/Activity Understanding is not Person Judgment

Two things must never be collapsed into one:

**A. Scene/Activity Understanding** — an observation about what appears to be happening in the operational environment.

**B. Judgment about the person** — a conclusion about a person's character, intent, competence, or worth.

Cognito may infer, illustratively:

> "there appears to be a queue"
> "a customer appears to have been waiting"
> "an employee is no longer in the area"

Cognito must **not** infer, as if it were the same kind of statement:

> "this employee is lazy"
> "the customer is angry"
> "the employee is avoiding work"

The first group describes the scene, revisable and contextual. The second group is a judgment about a person that visual evidence alone can never establish, and that this document does not authorize Cognito to make, communicate, or act on as though it were the first kind of statement.

---

## 4. Visual evidence is Evidence, not Fact

This section applies the existing Epistemic Boundary ([05](05_Epistemic_Boundary_and_Subject_Sovereignty.md) §1 — Fact, Observation, Evidence, Belief, Assumption, Inference, Hypothesis, Unknown) to visual/video signals specifically, without modifying it.

> **Signals/observations = Evidence. Never automatically Fact.**

Visual/video evidence may carry, illustratively and non-exhaustively:

- ambiguity;
- occlusion;
- poor lighting;
- an incomplete field of view;
- a delayed frame;
- uncertain object/activity recognition.

Cognito must treat visual/video evidence as contextual Evidence — at most supporting a Hypothesis about the operational scene — never as ground truth, exactly as [15](15_Human_Operational_State_and_Adaptive_Cognito_Interaction.md) §5 already establishes for authorized physiological signals ("Physiological signals are not ground truth... a signal is, at most, Evidence"). No confidence-scoring formula is defined here.

---

## 5. Combination with canonical business state

Visual/video context gains operational value when combined with RF-One's canonical business state — the same principle doc 16 §9 already establishes generally for Ambient Operational Context, applied here to visual signals specifically.

Illustrative, non-normative, cross-industry examples:

- **Restaurant:** a camera observes a table occupied, combined with Clover reporting no open order for it → a possible new seating not yet acknowledged.
- **Retail:** a camera observes several customers in a fitting-room area, combined with inventory/staffing state → Cognito may suggest support.

> **Ambient visual context without business state is incomplete. Business state without visual context is passive. Cognito combines both — this document does not turn either example into a fixed, mandatory rule.**

This document does not create, own, or specialize any Domain's business state — Cognito reads it from the owning Domain, never forking or restating it, exactly as [13](13_Process_Activation_and_Trigger_Intelligence.md) §7 already requires for Trigger Intelligence generally.

---

## 6. Relationship with Human Operational State

Video must **not** be used automatically to infer Human Operational State ([15](15_Human_Operational_State_and_Adaptive_Cognito_Interaction.md)).

Human Operational State may use authorized evidence, per document 15's own existing framework — but an inference about a person's *internal state* drawn from video must be treated with extreme caution, and this document does not formalize, as fixed interpretive rules:

```text
facial expression  -> stress
body posture       -> anxiety
movement speed     -> fatigue
```

This mirrors, without modifying, [15](15_Human_Operational_State_and_Adaptive_Cognito_Interaction.md) §5's existing, explicit rejection of fixed interpretive rules for physiological signals ("high heart rate = stress," "low HRV = anxiety") — the same discipline, extended to visual signals, not a new one. Where a Domain/Runtime authorizes visual signals as one input to a Human Operational State estimate, they remain subject to document 15's full existing discipline in full (§2–§10 there: illustrative inputs only, never a permanent classification, never a medical diagnosis, never itself creating Authority) — this document adds no new capability to that estimate and does not lower its existing bar.

---

## 7. Surveillance boundary

This section is a mandatory boundary, not an optional consideration.

Distinguish:

**Visual Ambient Cognition** — Cognito perceiving and interpreting as much authorized visual context as the current operational moment genuinely requires, to understand the operational scene.

**Employee Surveillance** — building behavioral dossiers on people.

> **The goal is to understand the operational context, not to build behavioral dossiers on people.**

This document does not assume:

- continuous, permanent recording;
- long-term raw video retention;
- employee scoring;
- disciplinary monitoring;
- productivity surveillance;
- covert observation.

This directly extends doc 16 §10's existing "Ambient Cognition ≠ Employee Surveillance/Recording" boundary and its "Understand what is needed for the moment; retain only what is justified by business purpose" principle to visual/video signals specifically — the same boundary, not a new one, and, exactly as doc 16 §10 already requires, a visual observation must never be automatically repurposed for discipline, termination, Selection, performance ranking, or any other punitive HR decision.

---

## 8. Retention

> **Retain derived operational context when justified; retain raw visual media only when explicitly required by a separate business/legal purpose.**

The architecture must be able to function with:

```text
video processed transiently
  -> derived context retained (e.g. "zone occupied", "queue observed")
  -> raw media discarded
```

This document does not design consent capture, retention duration, access control, or regulatory-compliance implementation for any jurisdiction — those remain Product/Runtime/System-level concerns, consistent with Core's definition-not-implementation nature ([00_RF-One_Core_Vision.md](00_RF-One_Core_Vision.md) §1), exactly as [15](15_Human_Operational_State_and_Adaptive_Cognito_Interaction.md) §10 and doc 16 §10 already state for their own respective privacy boundaries.

---

## 9. Third-party and customer privacy

Images and video may include customers and other third parties, not only employees. This document formalizes, without fixing jurisdiction-specific rules:

- purpose limitation;
- data minimization;
- authorized use only;
- privacy requirements that depend on jurisdiction and use case;
- no assumption of unlimited recording rights.

This extends doc 16 §11's existing customer/third-party context boundary to visual/video signals specifically — the same boundary, not a new one. No specific compliance regime for any State/Country is introduced by this document.

---

## 10. Identity and biometric boundary

This document does not assume Cognito must biometrically identify the people who appear in a video.

Distinguish:

> "a person / an employee / a customer appears in area X"

from:

> "this is John Smith"

Face recognition and biometric identification are a **separate capability**, not implicit in Visual/Video Context as defined here. Nothing in this document authorizes, designs, or implies face recognition, emotion recognition, or any other biometric inference.

---

## 11. Cross-industry illustrations (non-normative)

The following are conceptual illustrations only, in the same spirit as doc 16 §6's own cross-industry illustrations — none of them fixes wording, a required implementation, or asserts that RF-One currently models a Retail, Warehouse, or Office/professional Domain:

- **Restaurant** — a table occupied/not yet served; a queue at the host stand; a crowded bar area.
- **Retail** — a customer waiting; a zone with high traffic; fitting-room congestion.
- **Warehouse/operations** — area congestion; a staging backlog; workstation availability.
- **Office/professional** — used only where visual context genuinely adds value; this document does not force video into a setting where it brings none.

---

## 12. Relationship with Ambient Operational Context

Visual/Video Context is documented as a **specialization / source category** of Ambient Operational Context ([16](16_Ambient_Operational_Context_and_In-Flow_Cognito_Assistance.md) §3) — never as an independent Cognito capability.

```text
Ambient Operational Context (doc 16)
  -> source categories (illustrative, non-exhaustive, doc 16 §3):
       current conversation, business entities, live source-system data, ...
       Visual/Video Context (this document)
```

This document does not add a new capability to Cognito's list ([14](14_Cognito_RF-One_Cognitive_Intelligence.md) §6); it further specializes the same Context Interpretation capability doc 16 already specializes.

---

## 13. Relationship with Cognito

Cognito:

- consumes authorized visual evidence;
- combines it with business state and other ambient signals (§5);
- interprets operational context;
- may support In-Flow Cognito Assistance ([16](16_Ambient_Operational_Context_and_In-Flow_Cognito_Assistance.md) §5).

Cognito must **not**:

- act solely on ambiguous video evidence;
- bypass Authority ([09](09_Identity_Authority_and_Accountability.md));
- convert an uncertain observation into an irreversible action.

This restates, for visual evidence specifically, doc 16 §1's existing principle ("without creating Authority, without becoming a surveillance capability") and §16's "Ambient observation ≠ Authority" — the same discipline, not a new one.

---

## 14. Relationship with Attention Management and Trigger Intelligence

Visual evidence may contribute to:

- Trigger Discovery ([13](13_Process_Activation_and_Trigger_Intelligence.md) §3);
- Attention context ([12](12_Attention_Management.md) §2, §10);
- priority evidence.

But:

> **Visual observation ≠ Authorized Consequence.**

The existing separation is preserved unchanged:

```text
Trigger Discovery       -> recognizing that something may be significant
Trigger Resolution      -> determining whether it is actually the case
Authorized Consequence  -> what RF-One may actually do about it, strictly
                           within Business Rules and Delegated Authority
```

Visual evidence never itself decides who receives attention, with what priority, or through what channel — that separation, already established by doc 16 §15 for Ambient Operational Context generally, applies unchanged to visual signals specifically.

---

## 15. Device independence

This document does not select, endorse, or require any specific hardware, sensor, or vendor. It does not tie the concept to:

- a CCTV vendor;
- a camera brand;
- specific smart glasses;
- a mobile camera;
- a fixed camera.

This is the same discipline [15](15_Human_Operational_State_and_Adaptive_Cognito_Interaction.md) §11 and doc 16 §17 already establish, and `CLAUDE.md`'s "External Technology" guidance requires generally: Core remains device-independent. Cognito consumes authorized visual/context signals through whatever appropriate edge device a future implementation chooses; none is selected, endorsed, or required by this document.

---

## 16. Relationship to existing Core concepts

| This document | Extends / relates to |
|---|---|
| Visual/Video Context as Ambient Evidence (§1–§2) | [16](16_Ambient_Operational_Context_and_In-Flow_Cognito_Assistance.md) §3 (source categories, here specialized) |
| Scene Understanding ≠ Person Judgment (§3) | [16](16_Ambient_Operational_Context_and_In-Flow_Cognito_Assistance.md) §4 (Cognito interprets, does not judge) |
| Evidence, not Fact (§4) | [05](05_Epistemic_Boundary_and_Subject_Sovereignty.md) §1 (Epistemic Boundary) |
| Business state combination (§5) | [16](16_Ambient_Operational_Context_and_In-Flow_Cognito_Assistance.md) §9 |
| Human Operational State relationship (§6) | [15](15_Human_Operational_State_and_Adaptive_Cognito_Interaction.md) §5 (no fixed interpretive rule) |
| Surveillance boundary (§7) | [16](16_Ambient_Operational_Context_and_In-Flow_Cognito_Assistance.md) §10 |
| Retention (§8) | [15](15_Human_Operational_State_and_Adaptive_Cognito_Interaction.md) §10; [16](16_Ambient_Operational_Context_and_In-Flow_Cognito_Assistance.md) §10 |
| Third-party/customer privacy (§9) | [16](16_Ambient_Operational_Context_and_In-Flow_Cognito_Assistance.md) §11 |
| Identity/biometric boundary (§10) | [09](09_Identity_Authority_and_Accountability.md) §2 (Acting Identity, not confused with appearing in a frame) |
| Attention/Trigger relationship (§14) | [12](12_Attention_Management.md); [13](13_Process_Activation_and_Trigger_Intelligence.md) §3 |
| Device independence (§15) | [15](15_Human_Operational_State_and_Adaptive_Cognito_Interaction.md) §11; [16](16_Ambient_Operational_Context_and_In-Flow_Cognito_Assistance.md) §17 |

Nothing in this document reopens or redefines Ambient Operational Context, Cognito, Human Operational State, Attention Management, Trigger Intelligence, Identity/Authority/Delegation/Accountability, or the Epistemic Boundary. It names one source category of Ambient Evidence and states its own specific boundaries.

---

## Non-assumptions

Do not assume:

```text
this document creates a new Entity, Domain, Authority holder, or Cognito
  capability distinct from Ambient Operational Context (doc 16) and Context
  Interpretation (14 §6)
visual/video evidence is, or may become, an automatic source of Fact rather
  than Evidence (05 §1)
this document authorizes computer vision models, video ingestion, camera
  streams, image storage, object detection, face recognition, biometric
  identification, or emotion recognition
this document designs, authorizes, or implies continuous permanent
  recording, long-term raw video retention, employee scoring, disciplinary
  monitoring, productivity surveillance, or covert observation
facial expression, body posture, or movement speed may be formalized as a
  fixed rule for inferring stress, anxiety, or fatigue (Human Operational
  State, 15 §5)
Cognito must, or does, biometrically identify a person appearing in a video
this document designs consent capture, retention duration, access control,
  or regulatory-compliance implementation for any jurisdiction
this document introduces jurisdiction- or country-specific privacy
  compliance rules
this document asserts that RF-One currently models a Retail, Warehouse, or
  Office/professional Domain — the cross-industry examples in §11 are
  illustrative only
this document's PROPOSED status folds it into the Approved Core 2.0 00-14
  canonical set, or into document 16's own APPROVED status, or retroactively
  extends the `core-2.0-freeze` tag
promotion of this document's canonical principle (§1) to a numbered Core
  Principle has occurred merely because this document exists
any specific camera vendor, sensor, smart-glasses product, or deployment
  topology is designed, chosen, or authorized by this document
```
