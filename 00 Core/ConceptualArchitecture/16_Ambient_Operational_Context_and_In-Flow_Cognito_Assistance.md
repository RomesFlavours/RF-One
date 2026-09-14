# Ambient Operational Context and In-Flow Cognito Assistance

**Version:** 1.0
**Status:** APPROVED — Post-Baseline Conceptual Extension. Core 2.0 is already frozen (`core-2.0-freeze`, commit `71de3663dba2716ccbb6c1f93ffd458e20da8ead`) and `release/rf-one-2.0` (tag `rf-one-2.0-baseline`) is a released baseline built from it. This document is a conceptual extension ratified by the Product Owner after that baseline — not a retroactive change to `core-2.0-freeze` or to `release/rf-one-2.0`, and not itself folded into the Approved 00–14 canonical set ([00_RF-One_Core_Vision.md](00_RF-One_Core_Vision.md) §6). It was produced from the tip of `docs/cognito-human-operational-state` (which already carries [15_Human_Operational_State_and_Adaptive_Cognito_Interaction.md](15_Human_Operational_State_and_Adaptive_Cognito_Interaction.md) as APPROVED — Post-Baseline Conceptual Extension) on a further dedicated branch (`docs/cognito-ambient-operational-context`). See [../Core Evolution.md](../Core%20Evolution.md) for the ratification record. Promotion to a numbered Core Principle remains a separate, future decision — exactly the discipline already applied to document 15.
**Module:** Core / ConceptualArchitecture

---

## Related documents

- [00_RF-One_Core_Vision.md](00_RF-One_Core_Vision.md)
- [14_Cognito_RF-One_Cognitive_Intelligence.md](14_Cognito_RF-One_Cognitive_Intelligence.md) — Cognito and its capability list (§6 there already names **Context Interpretation** as an illustrative, previously unspecialized capability). This document does not add a new capability to that list; it gives Context Interpretation concrete shape, and states how its output feeds Human Interaction and Trigger Intelligence.
- [15_Human_Operational_State_and_Adaptive_Cognito_Interaction.md](15_Human_Operational_State_and_Adaptive_Cognito_Interaction.md) — Human Operational State (the person's own temporary condition) and Adaptive Cognito Interaction. §2 below states precisely how Ambient Operational Context (this document) differs from, and combines with, Human Operational State without collapsing into it.
- [12_Attention_Management.md](12_Attention_Management.md) — who/when/priority/channel decisions, which remain Attention Management's own; §15 below states that Ambient Operational Context is evidence Attention Management may use, never a decision it makes.
- [13_Process_Activation_and_Trigger_Intelligence.md](13_Process_Activation_and_Trigger_Intelligence.md) — Trigger Discovery / Trigger Resolution / Authorized Consequence; §16 below states that ambient observation is, at most, Trigger Discovery evidence, never itself an Authorized Consequence.
- [09_Identity_Authority_and_Accountability.md](09_Identity_Authority_and_Accountability.md) — Authority and Delegation, which Ambient Operational Context never creates, extends, or bypasses.
- [05_Epistemic_Boundary_and_Subject_Sovereignty.md](05_Epistemic_Boundary_and_Subject_Sovereignty.md) — the Epistemic Boundary this document's treatment of ambient/conversational signals (§3, §9) applies without modification: such signals are Evidence at most, never silently promoted to Fact.
- [10_RF-One_Intelligence_and_User_Relationship.md](10_RF-One_Intelligence_and_User_Relationship.md) §2, §7–§9 — the "compendium of the best manager" framing and the support-capability estimate this document's value-proposition section (§13) draws on without redefining.
- [../Organizational Responsibility.md](../Organizational%20Responsibility.md) — Position, Process Ownership; unaffected by this document exactly as already stated for Human Operational State (doc 15 §8).
- [../../01 Domains/Cross Domain/PERSON_CONTINUITY_001.md](../../01%20Domains/Cross%20Domain/PERSON_CONTINUITY_001.md) — stable person knowledge/continuity, a different concept from both Human Operational State and Ambient Operational Context; see that document's own §0.
- [../../01 Domains/Business Domain/Restaurant/Service Copilot/README.md](../../01%20Domains/Business%20Domain/Restaurant/Service%20Copilot/README.md) and its module files — an existing, Approved, **Restaurant Domain-specific** real-time in-service assistance capability, recognized upon this document's ratification as the **first Domain-level consumer instance** of the Core concept this document names (§6). This document does not redefine, rename, extend, merge, or require any change to Service Copilot's approved content or functional behavior — Service Copilot remains a Restaurant Domain module that consumes this Core concept; it is not merged into Cognito, and Cognito is not merged into it.
- See also `00 Core/Cognitive Interface/RF-ONE_COGNITIVE_INTERFACE_CONCEPT.md` — status "CONCEPTUAL DIRECTION — UNDER REVIEW." Not authority for this document.
- See also [17_Visual_Video_Context_as_Ambient_Evidence.md](17_Visual_Video_Context_as_Ambient_Evidence.md) — status PROPOSED — Post-Baseline Conceptual Extension, a sub-extension of this document. It specializes §3's illustrative source-category list with Visual/Video Context (authorized images/video as scene-level Ambient Evidence); it does not redefine this document's §1–§18.

---

## Purpose

This document formalizes **Ambient Operational Context**: Cognito's capacity to understand the real operational context in which a person is currently working — what is happening *around* them, in the current process, conversation, and business state — without requiring the person to interrupt their work to explicitly query RF-One.

> **Traditional software waits for the worker to use it. Cognito should be able to understand the operational context while the work is happening, and assist the worker inside that context.**

It does not redefine Cognito, Human Operational State, Attention Management, Trigger Intelligence, Organizational Responsibility, Identity/Authority, or the Epistemic Boundary. It specializes Cognito's already-named Context Interpretation capability ([14](14_Cognito_RF-One_Cognitive_Intelligence.md) §6) for one purpose: understanding the ambient operational situation, and states how that understanding feeds Human Interaction (as **In-Flow Cognito Assistance**, §5) and Trigger Intelligence (as evidence, §16).

---

## 1. The canonical principle

> **Cognito may perceive and interpret authorized ambient operational signals to understand what is happening around the person it is assisting, combine that understanding with RF-One's canonical business state, and offer assistance inside the natural flow of the person's work — without creating Authority, without becoming a surveillance capability, and without requiring the person to stop working and query RF-One explicitly.**

Every subsequent section specializes one part of this principle.

---

## 2. Ambient Operational Context is not Human Operational State

Two distinct questions must never be collapsed into one:

**A. Human Operational State** ([15](15_Human_Operational_State_and_Adaptive_Cognito_Interaction.md) §2) answers: *"What operational state is the person in right now?"* — their own temporary condition (load, fatigue, pace, recent errors).

**B. Ambient Operational Context** (this document) answers: *"What is happening in the work around the person right now?"* — the current conversation, the process in flight, the business entities involved, the counterpart present, the live business state.

The two are related — Ambient Operational Context is one of the inputs a Human Operational State estimate may draw on ([15] §2 already lists "environmental load" and "recent behavior" illustratively), and Human Operational State shapes how Cognito acts on Ambient Operational Context (§8 below) — but they are not interchangeable and must not be merged into a single concept. This mirrors, for Ambient Operational Context, exactly the distinction [PERSON_CONTINUITY_001.md](../../01%20Domains/Cross%20Domain/PERSON_CONTINUITY_001.md) §0 already draws between itself and Human Operational State: a moment is not a state, a state is not a durable identity, and none of the three should be written back into either of the others as if it were the same thing.

---

## 3. What may compose Ambient Operational Context

Ambient Operational Context may be derived from authorized combinations of, illustratively and non-exhaustively:

- the current conversation;
- the person's Identity/Position ([09](09_Identity_Authority_and_Accountability.md) §2; [Organizational Responsibility](../Organizational%20Responsibility.md) §2);
- the current Process ([../Process.md](../Process.md));
- the business Entities involved;
- the current customer/counterpart, where determinable and authorized;
- RF-One's canonical operational state ([06_Business_Autopilot_and_Intelligence_Engine.md](06_Business_Autopilot_and_Intelligence_Engine.md));
- live data from source systems;
- inventory/availability;
- current tasks;
- recent events;
- location;
- time context;
- the person's current Human Operational State ([15](15_Human_Operational_State_and_Adaptive_Cognito_Interaction.md));
- authorized device/context signals, where available.

This list is illustrative, not a fixed mandatory input schema — the same discipline already applied to Attention Management's own inputs ([12](12_Attention_Management.md) §2) and to Human Operational State's own inputs ([15](15_Human_Operational_State_and_Adaptive_Cognito_Interaction.md) §2). Core does not fix a rigid taxonomy of ambient signals; what is actually available and authorized is a Domain/Runtime/Product question.

---

## 4. Cognito in the working environment

> **Cognito is not merely a system the employee operates. Cognito operates inside the employee's working environment.**

This does **not** mean physical presence, autonomy, or agency independent of the person. It means that, within what is authorized:

- Cognito perceives the authorized ambient context;
- Cognito interprets what is happening;
- Cognito connects that context to canonical RF-One knowledge (Core, Domain, and the specific Process's own documentation — [13](13_Process_Activation_and_Trigger_Intelligence.md) §7's "Process as the source of truth," applied here to Ambient Operational Context as it already applies to Trigger Intelligence);
- Cognito may offer assistance at the operationally appropriate moment (§5).

This specializes Context Interpretation ([14](14_Cognito_RF-One_Cognitive_Intelligence.md) §6); it does not add a new Cognito capability, and it does not change what Cognito is authorized to do — Authority is unaffected (§15–§16).

---

## 5. In-Flow Cognito Assistance

**In-Flow Cognito Assistance** is the specialization of Cognito's **Human Interaction** capability ([14](14_Cognito_RF-One_Cognitive_Intelligence.md) §3) by which Cognito may support a person while a real interaction (with a customer, a colleague, or a task) is actually happening, using Ambient Operational Context (§3) combined with canonical business state (§9) — rather than waiting for the person to stop and query RF-One.

This does not add a new Cognito capability ([14] §6); it specializes how the existing Human Interaction capability behaves, in the same way [15](15_Human_Operational_State_and_Adaptive_Cognito_Interaction.md) §4's Adaptive Cognito Interaction specializes it for Human Operational State.

### Illustrative example — retail (non-normative)

A customer tells the associate: *"I like this dress, but I'd like it less fitted and in a darker color."* Cognito may combine what it heard, the current product, stock, sizes, colors, alternatives, and any authorized customer context, and offer the associate, through an appropriate low-friction channel (§7):

> "The same style is available in navy, size 8. For a looser fit, model X is also available."

The associate keeps interacting naturally with the customer. They are not required to stop and open a screen to ask for help. This example is illustrative only, in the same spirit as the non-normative examples already used in [12](12_Attention_Management.md) §12 and [15](15_Human_Operational_State_and_Adaptive_Cognito_Interaction.md) §12 — it does not fix wording, phrasing, or a required interaction script as canonical, and does not assert that RF-One currently has a Retail Domain (see [01 Domains/README.md](../../01%20Domains/README.md) for RF-One's current canonical Domain list).

---

## 6. Cross-industry illustrations (non-normative)

The following are conceptual illustrations of the same general pattern across different kinds of work. None of them asserts that RF-One currently models a Legal or Accounting Domain, and none of them authorizes Cognito to give legal, medical, or other professional advice, or to become the professional decision-maker in place of the human:

- **Retail associate** — suggesting a genuinely available product or alternative (§5).
- **Restaurant server** — surfacing an ingredient/allergen concern, a known preference, or table context during the conversation with a guest. [Service Copilot](../../01%20Domains/Business%20Domain/Restaurant/Service%20Copilot/README.md) (Approved, Restaurant Domain) is recognized, upon this document's ratification, as the **first Domain-level instance** that already applies this general pattern — real-time, in-service assistance combining ambient context with canonical business state — without this document redefining, renaming, or requiring any functional change to Service Copilot's own approved content:

```text
Core concept:
Ambient Operational Context + In-Flow Cognito Assistance
  ↓ consumed by
Domain instance:
Restaurant / Service Copilot
```

  Service Copilot remains what it already was — a Restaurant Domain module that assists the Server ([Service Copilot README](../../01%20Domains/Business%20Domain/Restaurant/Service%20Copilot/README.md) §"Purpose") — never merged into Cognito, and Cognito is not merged into it: Service Copilot is a Domain consumer of this Core concept, never a replacement for Cognito, and Cognito interprets/assists, it does not replace or absorb Service Copilot.

- **Legal assistant** — recalling a deadline, a missing document, or the risk of an improper commitment during a conversation. This is recall/surfacing of already-known information, never a legal opinion — consistent with [05](05_Epistemic_Boundary_and_Subject_Sovereignty.md) §1's existing rule that a legal interpretation must never be silently promoted to Fact.
- **Accountant** — recalling a missing document, an anomaly, a prior classification, or a deadline while working a case. Same boundary: recall and surfacing, never a tax or accounting determination presented as settled Fact ([05] §1; [08_Net_Outcome_and_Structural_Optimization.md](08_Net_Outcome_and_Structural_Optimization.md), §7).

---

## 7. Low-friction cognitive assistance

In-Flow Cognito Assistance should prefer, illustratively and non-exhaustively:

- short suggestions;
- appropriate timing (this reuses, and does not duplicate, [Next Best Action and Next Best Moment](../../01%20Domains/Business%20Domain/Restaurant/Service%20Copilot/Next%20Best%20Action%20and%20Next%20Best%20Moment.md)'s existing "what vs. when" separation, already approved for Restaurant, generalized here only as an illustrative precedent, not imported as Core content);
- audio/earbud where suitable;
- temporary visual output only when actually needed;
- no unnecessary navigation.

> **Assist without breaking the human interaction.**

This directly reuses the existing "voice to understand and decide, screen when a visual representation improves the decision" principle ([12](12_Attention_Management.md) §7; [11_Process_Autonomy_and_Exception_Driven_Human_Involvement.md](11_Process_Autonomy_and_Exception_Driven_Human_Involvement.md) §5) — it is not a new interaction rule, only its application to in-flow assistance specifically.

---

## 8. Ambient Operational Context combined with Human Operational State

Cognito must use Ambient Operational Context (what is happening) together with Human Operational State (how the person is) — neither alone is sufficient for In-Flow Cognito Assistance to behave well.

The same customer situation may call for different Cognito behavior depending on whether the employee is at the start of a shift or several hours into sustained load ([15](15_Human_Operational_State_and_Adaptive_Cognito_Interaction.md) §4, §12): Cognito may vary the quantity, frequency, detail, and timing of suggestions, or decide whether to intervene directly with the person at all versus favoring a different routing ([15] §7). This does not create a new adaptation mechanism; it is the same Adaptive Cognito Interaction of document 15, now also informed by Ambient Operational Context as one of its inputs.

---

## 9. Combination with canonical business state

Ambient Operational Context must not rest on conversational or perceptual signals alone. Cognito must combine it with **RF-One's canonical business state** — the same discipline [14](14_Cognito_RF-One_Cognitive_Intelligence.md) §1 already requires ("Cognito reasons with and communicates canonical RF-One knowledge — it does not hold a competing copy of it").

Illustrative, non-normative, cross-industry examples of the business state a Domain already owns or may own:

- retail: real stock/availability;
- restaurant: live operational data from a connected source system (e.g. the existing Clover connector referenced elsewhere in this repository);
- legal: matter, deadline, document status (illustrative only; no Legal Domain currently exists in RF-One);
- accounting: client, period, reconciliation, missing-document state (illustrative only; no Accounting Domain currently exists in RF-One).

> **Ambient context without business state is incomplete. Business state without ambient context is passive. Cognito combines both.**

This document does not create, own, or specialize any Domain's business state — it only states that Cognito's Context Interpretation and In-Flow Cognito Assistance must read it from the owning Domain, never fork or restate it, exactly as [13](13_Process_Activation_and_Trigger_Intelligence.md) §7 already requires for Trigger Intelligence generally.

---

## 10. Privacy, consent, and the surveillance boundary

This section is a mandatory boundary, not an optional consideration.

**Ambient Cognition** — Cognito perceiving and interpreting as much authorized ambient context as the current operational moment genuinely requires — is a distinct concept from **Employee Surveillance / Recording**. This document authorizes the former conceptually; it does not authorize, imply, or design the latter.

RF-One / Cognito must **not** be assumed to:

- permanently record conversations;
- retain raw audio;
- produce complete transcripts;
- convert conversations into disciplinary material;
- continuously monitor a person for punitive purposes.

> **Understand what is needed for the moment; retain only what is justified by business purpose.**

This directly parallels the privacy/consent/data-minimization boundary [15](15_Human_Operational_State_and_Adaptive_Cognito_Interaction.md) §10 already establishes for authorized physiological signals, generalized here to ambient/conversational/contextual signals: they must be authorized, minimized to the stated operational purpose, used only for that purpose, protected, and shared only when operationally necessary — and, exactly as [15] §9–§10 already require for Human Operational State, an ambient observation must never be automatically repurposed for discipline, termination, Selection, performance ranking, or any other punitive HR decision.

This document states the boundary only. It does not design consent capture, retention policy, access control, or regulatory-compliance implementation (jurisdiction-dependent) — those remain Product/Runtime/System-level concerns, consistent with Core's definition-not-implementation nature ([00_RF-One_Core_Vision.md](00_RF-One_Core_Vision.md) §1), exactly as [15] §10 already states for its own privacy boundary.

---

## 11. Customer and third-party context

When Cognito's Ambient Operational Context includes a conversation with a customer or another third party:

- that context must be used only for authorized operational purposes;
- retention must be minimized, per §10;
- RF-One must not assume unlimited freedom to record or retain third-party conversations;
- privacy/legal requirements depend on jurisdiction and use case, and are not fixed by this document.

This document does not create specific legal rules for any jurisdiction or use case. Where a Domain already models customer-side context (for example, Restaurant's Dining Intelligence, which Service Copilot already consumes, §6), that context remains owned by its Domain; this document does not redefine it.

---

## 12. Cognito does not replace human presence

Cognito, through In-Flow Cognito Assistance, may: suggest; anticipate; recall; connect; simplify; reduce cognitive load.

Cognito does not, by default, speak to the customer directly. The conceptual default remains:

> **Cognito assists the worker; the worker remains the human-facing actor.**

Any direct-to-customer interaction by Cognito is a separate, future capability, not implied or authorized by this document.

---

## 13. Value proposition

> **Cognito reduces variability in human execution.**

Illustratively, and cross-industry:

- it can raise the floor of performance;
- it can help an average employee perform closer to the organization's best standard;
- it can help a strong employee handle more complexity;
- it can reduce cognitive load;
- it can reduce errors;
- it can improve conversion/revenue;
- it can improve customer experience;
- it can reduce training dependence;
- it can improve consistency.

This extends, for in-flow assistance specifically, the existing framing that RF-One should progressively embody "the knowledge, judgment, analytical discipline and managerial capability of the best manager" so that "the competence required to use RF-One [is] materially lower than the competence embodied by RF-One" ([10](10_RF-One_Intelligence_and_User_Relationship.md) §2), and the existing principle that RF-One's duty of care rises, never its license, when a user needs more support ([10] §9.1). It does not imply anything about the quality of any specific person; it is a statement about what a consistent, well-informed in-flow assistant can add on top of whatever the person already brings.

---

## 14. RF-One / Cognito positioning

> **Cognito is a cross-industry human-performance layer that operates inside the working context, using real business state and authorized ambient context to improve the quality, consistency and economic outcome of human work.**

This restates, in one sentence, the combination this document formalizes: Cognito ([14](14_Cognito_RF-One_Cognitive_Intelligence.md)) interpreting Ambient Operational Context (§3–§4) together with canonical business state (§9) to deliver In-Flow Cognito Assistance (§5) within the value proposition of §13.

---

## 15. Relationship with Attention Management

Ambient Operational Context does not merge with, or redefine, Attention Management ([12](12_Attention_Management.md)):

```text
Ambient Operational Context  → helps understand what is happening
Human Operational State      → helps understand the worker's current condition
Attention Management         → decides who / when / priority / channel
Cognito                      → interprets and assists
```

Ambient Operational Context may be one of the inputs Attention Management considers (reusing, not duplicating, the "relevant operational context" input already named in [12] §2, §10), and In-Flow Cognito Assistance may be the channel through which an Attention Management decision actually reaches a person ([14] §4) — but Ambient Operational Context never itself decides who receives attention, with what priority, or through what channel. That separation is preserved without exception.

---

## 16. Relationship with Trigger Intelligence

Ambient Operational Context may supply evidence useful to Trigger Discovery ([13](13_Process_Activation_and_Trigger_Intelligence.md) §3) — Cognito recognizing that something may be happening. It never by itself constitutes Trigger Resolution or an Authorized Consequence:

> **Ambient observation ≠ Authority.**

The existing separation is preserved unchanged:

```text
Trigger Discovery       → recognizing that something may be significant
Trigger Resolution      → determining whether it is actually the case
Authorized Consequence  → what RF-One may actually do about it, strictly
                          within Business Rules and Delegated Authority
```

Cognito recognizing that a customer sounds dissatisfied, that a document appears to be missing, or that a table needs attention, does not by itself authorize any consequence beyond, at most, generating Attention (§15) or a Recommendation ([09](09_Identity_Authority_and_Accountability.md) §5.1) — never an autonomously executed Action outside already Delegated Authority.

---

## 17. Device independence

Core is device-independent. This document does not select, endorse, or require any specific hardware, sensor, or vendor — the same discipline [15](15_Human_Operational_State_and_Adaptive_Cognito_Interaction.md) §11 and `CLAUDE.md`'s "External Technology" guidance already establish.

> **Cognito consumes authorized ambient/context signals through appropriate edge devices.**

An earbud is a useful illustration (§5, §7) — never an architectural dependency. A future Cognito Edge/mobile bridge may receive authorized ambient signals from an earbud, a smartphone, a smartwatch, or another device; none of them is selected, endorsed, or required by this document.

---

## 18. Relationship to existing Core concepts

| This document | Extends / relates to |
|---|---|
| Ambient Operational Context (§2–§3) | [14](14_Cognito_RF-One_Cognitive_Intelligence.md) §6 (Context Interpretation, here specialized) |
| Distinction from Human Operational State (§2) | [15](15_Human_Operational_State_and_Adaptive_Cognito_Interaction.md) §2–§3 |
| Cognito in the working environment (§4) | [14](14_Cognito_RF-One_Cognitive_Intelligence.md) §1, §6 |
| In-Flow Cognito Assistance (§5, §7) | [14](14_Cognito_RF-One_Cognitive_Intelligence.md) §3 (Human Interaction); [12](12_Attention_Management.md) §7 (voice/screen principle) |
| Combined with Human Operational State (§8) | [15](15_Human_Operational_State_and_Adaptive_Cognito_Interaction.md) §4, §7 |
| Business state integration (§9) | [13](13_Process_Activation_and_Trigger_Intelligence.md) §7 ("Process as the source of truth") |
| Privacy / surveillance boundary (§10–§11) | [15](15_Human_Operational_State_and_Adaptive_Cognito_Interaction.md) §10 (analogous boundary for physiological signals) |
| Attention Management relationship (§15) | [12](12_Attention_Management.md) §2, §7, §10 |
| Trigger Intelligence relationship (§16) | [13](13_Process_Activation_and_Trigger_Intelligence.md) §3 (Discovery/Resolution/Authorized Consequence) |
| Device independence (§17) | [15](15_Human_Operational_State_and_Adaptive_Cognito_Interaction.md) §11 |
| Service Copilot relationship (§6) | [Restaurant Domain / Service Copilot](../../01%20Domains/Business%20Domain/Restaurant/Service%20Copilot/README.md) — first Domain-level consumer instance, recognized upon ratification; not redefined, renamed, or merged with Cognito |

Nothing in this document reopens or redefines Cognito, Human Operational State, Attention Management, Trigger Intelligence, Organizational Responsibility, Identity/Authority/Delegation/Accountability, or the Epistemic Boundary. It names one new, narrowly-scoped concept and one specialization of an existing Cognito capability, and states their relationship to each of them.

---

## Non-assumptions

Do not assume:

```text
this document creates a new Entity, Domain, Authority holder, or Cognito capability
  distinct from the already-named Human Interaction and Context Interpretation
  (14 §6)
Ambient Operational Context is, or may become, a permanent classification of a
  person, in the same sense §2 of document 15 already prohibits for Human
  Operational State
Ambient Operational Context may extend, create, or bypass Authority, Position,
  Process Ownership, or Delegated Authority
this document authorizes microphone capture, speech-to-text, real-time
  transcription, audio streaming, an earbud protocol, customer identification,
  emotion recognition, biometric inference, or a direct-to-customer agent
this document designs, authorizes, or implies employee surveillance, permanent
  audio retention, or continuous monitoring for punitive purposes
this document designs consent capture, data retention, access control, or
  regulatory-compliance implementation for any jurisdiction
a legal, medical, tax, or other professional determination produced with the
  help of Ambient Operational Context is ever presented as settled Fact rather
  than as a Recommendation, Belief, Inference, or Hypothesis (05 §1)
this document asserts that RF-One currently has a Retail, Legal, or Accounting
  Domain — the cross-industry examples in §5–§6, §9 are illustrative only
this document redefines, extends, or requires any change to the Restaurant
  Domain's existing Service Copilot, Next Best Action and Next Best Moment,
  Management Intrusiveness, or Smartwatch Interaction documents
recognizing Service Copilot as this Core concept's first Domain consumer
  instance (§6) renames Service Copilot, merges it into Cognito, merges
  Cognito into it, or changes any of Service Copilot's functional behavior —
  it does not; Service Copilot remains a distinct Restaurant Domain module,
  and Cognito remains a distinct Core capability
this document's APPROVED — Post-Baseline Conceptual Extension status folds
  it into the Approved Core 2.0 00-14 canonical set, or retroactively extends
  the `core-2.0-freeze` tag — see Core Evolution.md's ratification record and
  00_RF-One_Core_Vision.md §6
promotion of this document's canonical principle (§1) to a numbered Core
  Principle has occurred merely because this document is APPROVED as an
  extension
any specific interface, API, vendor, or deployment topology is designed,
  chosen, or authorized by this document
```
