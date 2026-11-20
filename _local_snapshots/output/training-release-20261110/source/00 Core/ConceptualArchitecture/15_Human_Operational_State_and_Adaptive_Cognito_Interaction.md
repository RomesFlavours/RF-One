# Human Operational State and Adaptive Cognito Interaction

**Version:** 1.0
**Status:** APPROVED — Post-Baseline Conceptual Extension. Core 2.0 is already frozen (`core-2.0-freeze`, commit `71de3663dba2716ccbb6c1f93ffd458e20da8ead`) and `release/rf-one-2.0` (tag `rf-one-2.0-baseline`) is a released baseline built from it. This document is a conceptual extension ratified by the Product Owner after that baseline — not a retroactive change to `core-2.0-freeze` or to `release/rf-one-2.0`, and not itself folded into the Approved 00–14 canonical set ([00_RF-One_Core_Vision.md](00_RF-One_Core_Vision.md) §6). See [../Core Evolution.md](../Core%20Evolution.md) for the ratification record. Promotion to a numbered Core Principle remains a separate, future decision.
**Module:** Core / ConceptualArchitecture

> **Exploration-vs-adoption clarification (external-review clarification, added post-baseline — does not modify this document's approved substance):** every candidate evidence category this document names (§2, §5 — including physiological signals such as heart rate, HRV, and respiration rate) is a candidate for *technical exploration only*. Being named here means the concept has been identified as worth evaluating — it does NOT mean RF-One has approved collecting or operationally using that specific signal. The Product Owner's decision sequence is: **first**, explore what each technically available evidence/signal source can actually provide and how reliably; **then, separately**, decide which of those RF-One will actually use operationally. No specific wearable, sensor, or biometric signal is authorized for operational deployment merely by appearing in this document's illustrative lists. Operational adoption of any specific signal requires a later, explicit Product Owner decision, which must also address the privacy, legal, and employee-impact considerations that decision — not this document — owns.

---

## Related documents

- [00_RF-One_Core_Vision.md](00_RF-One_Core_Vision.md)
- [09_Identity_Authority_and_Accountability.md](09_Identity_Authority_and_Accountability.md) — Identity, Authority, Delegation, Accountability. §8 below establishes that nothing in this document creates, extends, or reinterprets any of these.
- [10_RF-One_Intelligence_and_User_Relationship.md](10_RF-One_Intelligence_and_User_Relationship.md) §6–§8 — the Explicit/Inferred discipline and the durable, contextual "support capability" estimate this document's §3 distinguishes from the temporary state defined here.
- [11_Process_Autonomy_and_Exception_Driven_Human_Involvement.md](11_Process_Autonomy_and_Exception_Driven_Human_Involvement.md) — exception-driven human involvement, which §7 below shows may be shaped, but never triggered or suppressed, by Human Operational State.
- [../Organizational Responsibility.md](../Organizational%20Responsibility.md) — Position, Occupant, Temporary Coverage; §8 below states explicitly that Human Operational State never modifies any of these.
- [12_Attention_Management.md](12_Attention_Management.md) — §2 and §10 there already name "the occupant's availability and operational state" and "relevant operational context" as inputs Attention Management may consider. This document specializes what that operational-state input is and how it is formed; it does not redefine Attention Management's own decisions (who/when/priority/channel remain Attention Management's, per §7 below).
- [14_Cognito_RF-One_Cognitive_Intelligence.md](14_Cognito_RF-One_Cognitive_Intelligence.md) — Cognito and its Human Interaction capability, which is the capability this document's Adaptive Cognito Interaction (§4) actually specializes. This document does not add a new capability to Cognito's list ([14] §6) and does not redefine Cognito.
- [05_Epistemic_Boundary_and_Subject_Sovereignty.md](05_Epistemic_Boundary_and_Subject_Sovereignty.md) — the Epistemic Boundary (Fact/Observation/Evidence/Belief/Assumption/Inference/Hypothesis/Unknown) this document's treatment of physiological signals (§5) and medical boundary (§6) applies without modification.

---

## Purpose

This document formalizes **Human Operational State**: the temporary, contextual, dynamic condition of the specific person Cognito is interacting with at the current operational moment — and how Cognito's Human Interaction capability ([14_Cognito_RF-One_Cognitive_Intelligence.md](14_Cognito_RF-One_Cognitive_Intelligence.md) §3) may adapt to it.

The same person is not operationally identical at every moment of the same shift. A server at the first hour of service and the same server at the seventh hour, under sustained load, are the same Acting Identity ([09](09_Identity_Authority_and_Accountability.md) §2) with the same Authority, the same Position ([Organizational Responsibility](../Organizational%20Responsibility.md) §2), and potentially a materially different capacity to absorb information, interruptions, and complexity at that moment. This document gives RF-One a way to recognize that difference and adapt its interaction accordingly, without turning it into a judgment about the person.

It does not redefine Cognito, Attention Management, Organizational Responsibility, Identity/Authority, or the Epistemic Boundary. It specializes them for one specific purpose: how Cognito should interact with a person given their current operational state.

---

## 1. The canonical principle

> **Cognito must adapt its interaction to the current Human Operational State, using authorized operational, behavioral and physiological evidence. Human-state evidence may influence communication and routing, but it never constitutes medical diagnosis, never creates Authority, and never becomes a permanent judgment about the person.**

Every subsequent section specializes one part of this principle.

---

## 2. Human Operational State

**Human Operational State** is the temporary, contextual and dynamic condition of a person in the current operational moment — distinct from who the person durably is (§3).

It may be informed by, illustratively and non-exhaustively:

- shift duration;
- operational load;
- number of concurrent activities;
- pace of requests;
- recent errors;
- interruptions;
- environmental load;
- recent behavior;
- the person's operational history;
- individual preferences;
- availability of support;
- authorized physiological signals (§5).

This list is illustrative, not a fixed mandatory input schema — the same discipline already applied to Attention Management's own inputs ([12](12_Attention_Management.md) §2).

**Human Operational State is not a permanent classification.** It is not a trait, a personality type, a competence score, or a new Entity attribute describing who the person is. It describes a moment, not the person. It must remain revisable, expected to change within the same shift, and must never be carried forward as a fixed label once the operational moment that produced it has passed.

---

## 3. Human Operational State is not Stable Person Knowledge

Two distinct things must never be collapsed into one:

**A. Stable person knowledge** — durable, contextual, revisable understanding of a person, of the same kind already established in [10_RF-One_Intelligence_and_User_Relationship.md](10_RF-One_Intelligence_and_User_Relationship.md) §6–§8 for the User Model generally: preferred communication style, known effective support patterns, preferred level of detail, observed response to interruptions. This is learned over time (§9), evolves slowly, and — exactly as §7 of that document already requires — remains contextual, domain-specific, evidence-based and revisable, never a global classification of the person.

**B. Human Operational State (this document)** — temporary, situational, continuously re-estimated at the current moment. It answers "how is this person doing right now," not "what kind of person is this."

Human Operational State may be interpreted *in light of* stable person knowledge (for example, a known preference for shorter messages under load), but a specific instance of elevated operational load must never itself be written back into stable person knowledge as a new durable trait (e.g., "this person is fragile under pressure"). Doing so would convert a moment into an identity, which §2 and §10 below both prohibit.

---

## 4. Adaptive Cognito Interaction

Human Operational State is evidence Cognito's **Human Interaction** capability ([14](14_Cognito_RF-One_Cognitive_Intelligence.md) §3) may use to adapt, illustratively and non-exhaustively:

- the amount of information conveyed;
- response length;
- tone;
- timing;
- frequency of interruptions;
- the order in which information is presented;
- the complexity of instructions;
- level of detail;
- confirmation style;
- whether to speak directly to the person or involve another Position instead (§7).

This does not add a new capability to Cognito's list ([14](14_Cognito_RF-One_Cognitive_Intelligence.md) §6); it specializes how the existing Human Interaction capability behaves. It does not change what Cognito is authorized to do — Authority is unaffected (§8).

### Illustrative example (non-normative)

A server under significant operational load might be better served by:

> "Table 12 needs attention. I would ask Alex to cover it. OK?"

rather than a longer explanation surveying multiple alternatives. This is illustrative only, in the same spirit as the non-normative examples already used in [12_Attention_Management.md](12_Attention_Management.md) §12 and [11_Process_Autonomy_and_Exception_Driven_Human_Involvement.md](11_Process_Autonomy_and_Exception_Driven_Human_Involvement.md) §6 — it does not fix wording, phrasing, language, or a required interaction script as canonical.

---

## 5. Authorized physiological evidence is contextual, not conclusive

*(See the exploration-vs-adoption clarification at the top of this document: the signals named below are candidates for technical exploration, not an operational authorization.)*

Future authorized devices may supply physiological signals — for example heart rate, heart rate variability (HRV), respiration rate, or other signals that may become available — as additional contextual evidence.

**Physiological signals are not ground truth.** This document explicitly rejects fixed interpretive rules such as "high heart rate = stress," "low HRV = anxiety," or "respiration change = panic." A signal is, at most, **Evidence** in the sense already established by the Epistemic Boundary ([05](05_Epistemic_Boundary_and_Subject_Sovereignty.md) §1) — information that supports, without proving, a Hypothesis about operational load. It is never itself a Fact about the person's internal state.

The compositional model is:

```text
Operational Context
+
Behavioral Context
+
Authorized Physiological Evidence
→
Human Operational State Estimate
→
Adaptive Cognito Interaction
```

No single signal governs a decision by itself. No fixed formula, weighting, or threshold is defined by this document — thresholds and scoring, if ever built, are a Runtime/Software concern, consistent with Core's definition-not-implementation nature ([00_RF-One_Core_Vision.md](00_RF-One_Core_Vision.md) §1) and with how Attention Management already declines to fix a universal priority-scoring table ([12](12_Attention_Management.md) §3).

The value of a physiological signal is that it can offer a more objective input than subjective observation alone — not that it replaces contextual and behavioral judgment, and not that it outweighs them.

---

## 6. Human Operational State is not a medical state

RF-One / Cognito does not diagnose. This boundary is explicit and non-negotiable:

RF-One / Cognito must **not** produce, state, or imply a diagnosis of anxiety, panic attack, stress disorder, burnout, fatigue disorder, or any other medical or psychological condition.

Cognito may observe, for example, "possible elevated operational load." Cognito must **not** conclude "this person is having an anxiety attack," or any equivalent medical characterization.

Where a situation appears to potentially require medical attention, that determination and any resulting action fall outside RF-One's diagnostic perimeter entirely — Human Operational State informs operational interaction and routing (§7), never a health assessment, and RF-One does not substitute itself for appropriate medical judgment, personnel or channels.

---

## 7. Relationship with Attention Management

Human Operational State may influence Attention Management's ([12](12_Attention_Management.md)) existing decisions about:

- timing;
- priority handling;
- recipient selection;
- escalation;
- interruption strategy;
- channel.

For example: if the primary person is under elevated operational load, Attention Management may decide to avoid a new interruption, involve Temporary Coverage, involve a Backup Position, involve another appropriate Position, or delay a non-urgent item — using mechanisms Attention Management and Organizational Responsibility already define ([12](12_Attention_Management.md) §4, §9; [Organizational Responsibility](../Organizational%20Responsibility.md) §3, §5), not new ones.

**Cognito and Attention Management remain distinct**, exactly as [14](14_Cognito_RF-One_Cognitive_Intelligence.md) §4 already establishes: Cognito interprets Human Operational State and interacts; Attention Management decides who receives attention, when, and how. This document does not merge them, and does not change which of the two owns which decision.

---

## 8. Relationship with Organizational Responsibility

Human Operational State does **not** modify Position, Authority, Process Ownership, or Position scope ([Organizational Responsibility](../Organizational%20Responsibility.md) §2–§4; [09](09_Identity_Authority_and_Accountability.md) §3).

It may influence operational **routing** through mechanisms Organizational Responsibility already defines. For example: the Position owner may remain the Shift Manager, but if the current Occupant is temporarily under significant operational load, Attention Management may use the already-existing Temporary Coverage → Backup Position → Fallback sequence ([Organizational Responsibility](../Organizational%20Responsibility.md) §3; [12](12_Attention_Management.md) §9) to route a matter elsewhere.

> **Human Operational State never creates Authority.** It may change who Attention Management routes a matter to among people who already hold adequate Authority for it; it never grants Authority to someone who does not already hold it, and never removes Authority from the Position or its Occupant.

---

## 9. Learning boundary

Cognito may learn, over time, patterns such as: which level of detail tends to work best; when a person tends to become operationally overloaded; which forms of support prove effective; when it is preferable to involve someone else; which signals tend to precede a loss of operational effectiveness. This reuses the Explicit/Inferred discipline and confidence/recency/revisability requirements already established for learned User Model characteristics ([10](10_RF-One_Intelligence_and_User_Relationship.md) §6) and for Attention Management's own Learning section ([12](12_Attention_Management.md) §11).

This learning must **not** be converted into:

- a diagnosis;
- an automatic disciplinary judgment;
- Selection scoring;
- Performance penalties;
- an Authority change;
- a permanent label about the person.

> **Learning improves how Cognito interacts and how Attention Management routes. It never becomes a verdict about the person.** This directly parallels the existing rule that Attention Management's own learning "never changes the perimeter of Authority" ([12](12_Attention_Management.md) §11).

---

## 10. Privacy, consent and data minimization

Physiological signals are sensitive personal data. Where authorized devices supply them, they must be:

- explicitly authorized by the person they concern;
- minimized to what the stated operational purpose actually requires;
- used only for the operational purpose declared at the time of authorization;
- protected;
- shared only when operationally necessary.

Physiological signals, and any Human Operational State estimate derived from them, must **not** be automatically repurposed for discipline, termination, Selection, performance ranking, or any other punitive HR decision.

This document states the boundary only. It does not design consent capture, retention policy, access control, regulatory compliance (e.g. data-protection law), or any concrete implementation of this boundary — those are Product/Runtime/System-level concerns, consistent with Core's definition-not-implementation nature ([00_RF-One_Core_Vision.md](00_RF-One_Core_Vision.md) §1).

---

## 11. Device and wearable independence

The Core is device-independent. A future Cognito Edge / mobile bridge may receive authorized human-state signals from earbuds, a smartwatch, or other wearables.

> **Cognito consumes authorized human-state signals — Cognito does not depend on a specific earbud, smartwatch, or any other named device.**

This document does not select, endorse, or require any specific hardware, sensor, or vendor, consistent with `CLAUDE.md`'s "External Technology" guidance to keep provider-specific integrations behind a replaceable abstraction.

---

## 12. Illustrative use case — extended-shift operational load (non-normative)

A server is well into a long shift: many tables, an elevated pace of requests, recent errors, and an authorized wearable reporting signals consistent with a possible increase in physiological load.

Cognito does **not** conclude "the server is stressed." Cognito may conclude, at most, "evidence suggests elevated operational load" (§5, §6).

Cognito's Human Interaction capability may accordingly favor shorter messages, fewer interruptions, simpler instructions, and direct operational support; Attention Management, separately, may consider a temporary redistribution of load or the involvement of a supporting Position (§7).

This example is illustrative only, in the same spirit as the Tips example in [11](11_Process_Autonomy_and_Exception_Driven_Human_Involvement.md) §6 and the struggling-server example in [12](12_Attention_Management.md) §12. It does not authorize any specific device, sensor, threshold, or algorithm, and does not modify any Restaurant Domain documentation.

---

## 13. Illustrative pattern — a highly capable person under load (non-normative)

Consider a general pattern, not a real individual: a highly capable person who, under load, tends to benefit from fewer simultaneous requests, more concise messages, greater clarity, fewer context switches, and temporary support from another Position.

The purpose of naming this pattern is to give Cognito operational-human sensitivity — recognizing that even a highly capable person's effective capacity varies with their current operational state — without creating a psychological label, trait, or classification of that person. Per §2–§3, this remains a Human Operational State observation, revisable moment to moment, never a durable characterization of who the person is.

---

## 14. Relationship to existing Core concepts

| This document | Extends / relates to |
|---|---|
| Human Operational State (§2) | [12](12_Attention_Management.md) §2, §10 (existing "operational state"/"relevant operational context" input, here specialized) |
| Stable vs. temporary distinction (§3) | [10](10_RF-One_Intelligence_and_User_Relationship.md) §6–§8 (Explicit/Inferred, support-capability estimate) |
| Adaptive Cognito Interaction (§4) | [14](14_Cognito_RF-One_Cognitive_Intelligence.md) §3 (Human Interaction capability) |
| Authorized physiological evidence (§5) | [05](05_Epistemic_Boundary_and_Subject_Sovereignty.md) §1 (Evidence, Hypothesis) |
| Attention Management relationship (§7) | [12](12_Attention_Management.md) §4, §9 (real-time intervention, escalation) |
| Organizational Responsibility relationship (§8) | [Organizational Responsibility](../Organizational%20Responsibility.md) §3, §5 (Temporary Coverage, escalation policy); [09](09_Identity_Authority_and_Accountability.md) §3 (Authority) |
| Learning boundary (§9) | [12](12_Attention_Management.md) §11 (Learning never extends Authority) |

Nothing in this document reopens or redefines Cognito, Attention Management, Organizational Responsibility, Identity/Authority/Delegation/Accountability, or the Epistemic Boundary. It names one new, narrowly-scoped concept and states its relationship to each of them.

---

## Non-assumptions

Do not assume:

```text
this document creates a new Entity, Domain, or Authority holder
Human Operational State is a permanent classification, trait, or identity label
any physiological signal, alone or combined, constitutes a medical diagnosis
this document authorizes any specific wearable, sensor, vendor, or device
this document defines a formula, threshold, scoring model, or algorithm for
  estimating operational load
this document designs consent capture, data retention, access control, or
  regulatory compliance implementation
Human Operational State may extend, create, or remove Authority, Position,
  Process Ownership, or Position scope
learning under this document may produce disciplinary judgments, Selection
  scoring, Performance penalties, or Authority changes
this document's APPROVED — Post-Baseline Conceptual Extension status folds
  it into the Approved Core 2.0 00-14 canonical set, or retroactively extends
  the `core-2.0-freeze` tag — see Core Evolution.md's ratification record and
  00_RF-One_Core_Vision.md §6
promotion to a numbered Core Principle in RF-ONE Core Principles.md has
  occurred merely because this document is APPROVED as an extension
Cognito acquires a new capability distinct from Human Interaction
  ([14_Cognito_RF-One_Cognitive_Intelligence.md](14_Cognito_RF-One_Cognitive_Intelligence.md) §6)
```
