# Cognito — RF-One Cognitive Intelligence

**Version:** 1.0
**Status:** Approved (Core 2.0)
**Module:** Core / ConceptualArchitecture

---

## Related documents

- [00_RF-One_Core_Vision.md](00_RF-One_Core_Vision.md)
- [13_Process_Activation_and_Trigger_Intelligence.md](13_Process_Activation_and_Trigger_Intelligence.md) — Trigger Intelligence, corrected here (§4) to be a capability of Cognito, not a separate intelligence.
- [12_Attention_Management.md](12_Attention_Management.md) — Attention Management decides who/when/priority/channel; Cognito's Human Interaction capability may be the channel through which it reaches a person (§6 below), without Cognito absorbing Attention Management's own decisions.
- [11_Process_Autonomy_and_Exception_Driven_Human_Involvement.md](11_Process_Autonomy_and_Exception_Driven_Human_Involvement.md) — "interaction channel is not the Process" (§5 there); this document specializes what the interaction layer actually is.
- [10_RF-One_Intelligence_and_User_Relationship.md](10_RF-One_Intelligence_and_User_Relationship.md) — RF-One as managerial intelligence, the User Model, and progressive explainability; Cognito is the cognitive capacity through which much of that relationship is exercised, not a separate intelligence from RF-One itself.
- [09_Identity_Authority_and_Accountability.md](09_Identity_Authority_and_Accountability.md) — Authority/Delegation, which Cognito consumes and never extends.
- [06_Business_Autopilot_and_Intelligence_Engine.md](06_Business_Autopilot_and_Intelligence_Engine.md) — the Intelligence Engine abstraction; Cognito is itself an Intelligence Engine consumer, not a replacement for the Business Autopilot model.
- [../ImplementationGuidelines.md](../ImplementationGuidelines.md), "Channel Independence" — a technical separation of Cognito's capabilities must still respect Domain capability being callable independently of any one channel.
- See also `00 Core/Cognitive Interface/RF-ONE_COGNITIVE_INTERFACE_CONCEPT.md` — an earlier exploratory document, status "CONCEPTUAL DIRECTION — UNDER REVIEW," about a future interaction layer. That document does not itself use the name "Cognito," predates this canonical definition, and remains under review at its own stated status — it is not authority for this document and is not elevated in status by it. This document is the canonical definition of what Cognito conceptually is; the exploratory document remains a separate, not-yet-approved product-direction discussion.

---

## Purpose

This document formalizes **Cognito** as RF-One's Cognitive Intelligence: a single transversal cognitive capacity of RF-One, of which conversation/voice interaction and Trigger Intelligence are two capabilities among others — not two independent intelligences. It corrects any prior formulation, in this Core or elsewhere, that described Cognito merely as "a channel" or "a voice interface."

It does not redefine Process, Decision, Authority, Delegation, Process Autonomy, Attention Management, or Trigger Intelligence's own substance (§2 of document 13). It defines what Cognito is, and restates their relationship to it correctly.

---

## 1. The canonical principle

> **Cognito = RF-One's Cognitive Intelligence.**

Cognito is the transversal cognitive capacity of RF-One that may: understand human language; converse with people; interpret context; observe events and the state of Reality; use Trigger Intelligence; explain results; support briefing/debriefing; receive human intervention; and communicate Attention requests.

Cognito does **not**: own Business Rules on its own authority; substitute itself for a Domain; act as the Process Runtime; extend Authority; or become a primary source of Business Knowledge. Cognito reasons with and communicates canonical RF-One knowledge — it does not hold a competing copy of it (consistent with [06_Business_Autopilot_and_Intelligence_Engine.md](06_Business_Autopilot_and_Intelligence_Engine.md) §4: an Intelligence Engine is a component RF-One reasons *with*, never a second, independent source of business meaning).

---

## 2. Trigger Intelligence is a capability of Cognito

Trigger Intelligence ([13_Process_Activation_and_Trigger_Intelligence.md](13_Process_Activation_and_Trigger_Intelligence.md)) is **a capability of Cognito**, not an intelligence separate from it.

This capability: observes Reality/Events; reads Process, Rules, Entities, State and context; recognizes explicit and implicit triggers; contributes to Process Activation. It does **not** execute Business Logic directly, does **not** create Authority, and does **not** invent Business Rules — exactly as already established in document 13 §1–§3, which this document does not reopen.

The distinction between Trigger Intelligence and Cognito's other capabilities is **functional, not ontological**: they are different things Cognito can do, not different things Cognito is.

---

## 3. Human Interaction is a capability of Cognito

**Cognito Human Interaction** is the complementary capability through which Cognito converses with people. It may include: voice; text; briefing; debriefing; questions and answers; authorization requests; explanations; and access to visual views when necessary ([11_Process_Autonomy_and_Exception_Driven_Human_Involvement.md](11_Process_Autonomy_and_Exception_Driven_Human_Involvement.md) §5: voice to understand and decide, screen when a visual representation improves the decision).

Human Interaction is **one of Cognito's capabilities, not a synonym for Cognito itself**. Describing Cognito only in terms of voice or conversation, as if that were the whole of it, is exactly the reduction this document corrects.

---

## 4. Relationship with Attention Management

Attention Management ([12_Attention_Management.md](12_Attention_Management.md)) remains a distinct capability, not absorbed by Cognito. Attention Management decides: who must receive attention; priority; timing; channel; escalation; and which Position/Occupant/Delegation is relevant.

Cognito's Human Interaction capability may be the cognitive channel through which Attention Management actually reaches a person — it does not decide any of the above itself:

```text
Trigger Intelligence (a Cognito capability)
→ detects a condition / "Human Attention Required"

Attention Management
→ determines Who / When / Priority / Channel

Cognito Human Interaction
→ communicates/interacts with the person, when the cognitive
  channel is the appropriate one
```

---

## 5. Relationship with Process Activation

Document 13's conceptual sequence is preserved, and corrected only where it described Cognito as external to Trigger Intelligence rather than as its capability:

```text
Reality / Event
→ Cognito's Trigger Intelligence capability
→ Process Activation / Transition
→ Domain Capability (Channel Independence)
→ Execution
→ Outcome Verification
→ Attention Management, if required
→ Cognito's Human Interaction capability
→ Human
→ intervention, if any
→ Process resumes
```

This sequence is conceptual, not a mandatory technical specification (document 13 §12 already states this; it is restated here unchanged).

---

## 6. One Intelligence, several capabilities

Cognito is **one** conceptual Cognitive Intelligence. It may have different capabilities. Approved examples, illustrative and non-exhaustive: Human Interaction; Trigger Intelligence; Context Interpretation; Explanation; Briefing/Debriefing.

Core does not fix a closed taxonomy of Cognito's capabilities, and does not assume this list is complete. A future capability may be added without redefining Cognito itself, exactly as a new Domain may be added without redefining Core (see [00_RF-One_Core_Vision.md](00_RF-One_Core_Vision.md) §1).

---

## 7. Implementation freedom

Cognito's capabilities may be implemented in the same agent/runtime, in different agents, in different processes, or in different services, when doing so improves performance, latency, reliability, scalability, or fault isolation.

> **Technical separation must never produce divergent Business Knowledge, divergent Authority, divergent Process semantics, or conceptually independent intelligences.**

All of Cognito's capabilities, however technically deployed, must consume the same canonical RF-One knowledge (Core, Domain, and the specific Process's own documentation) — never a parallel or forked copy of it. This is the same discipline [13_Process_Activation_and_Trigger_Intelligence.md](13_Process_Activation_and_Trigger_Intelligence.md) §7 already requires of Trigger Intelligence specifically ("Process as the source of truth"), generalized here to every capability of Cognito.

---

## 8. Cognito is not AWS Cognito

**"Cognito," in this and every other RF-One Core/ConceptualArchitecture document, names RF-One's Cognitive Intelligence, as defined above.** It has no relationship to Amazon Web Services' "Cognito" identity/authentication service, referenced elsewhere in this repository (`10 System/Identity & Access/Identity Authority and Security Architecture.md`) as a candidate managed authentication provider.

This document does not rename either concept. It only records the distinction explicitly, since both names are already in active use in this repository for entirely unrelated things: RF-One's Cognitive Intelligence (this document) is a Core conceptual capacity; AWS Cognito is a specific, replaceable, System-level authentication technology candidate (see [09_Identity_Authority_and_Accountability.md](09_Identity_Authority_and_Accountability.md), which already establishes that no specific authentication provider is fixed by Core). Wherever ambiguity is possible, "RF-One Cognito" or "Cognito (RF-One Cognitive Intelligence)" should be used to disambiguate from "AWS Cognito."

---

## Non-assumptions

Do not assume:

```text
this document designs an agent runtime, chooses an AI model, or defines a prompt
this document creates an API, a microservice, or a deployment topology
Cognito is a new Entity, Domain, or Authority holder in its own right
Cognito owns, stores, or arbitrates Business Rules independently of the Domains
  that define them
Cognito extends, grants, or substitutes for Delegated Authority
Human Interaction is synonymous with Cognito, rather than one of its capabilities
Trigger Intelligence's own substance (document 13, §1-§11) is redefined here —
  only its relationship to Cognito is corrected
this document elevates `00 Core/Cognitive Interface/RF-ONE_COGNITIVE_INTERFACE_CONCEPT.md`
  to Approved status, or authorizes any specific interface built from it
this document renames or modifies AWS Cognito or any other System-level
  authentication technology
the list of Cognito's capabilities in §6 is closed or complete
```
