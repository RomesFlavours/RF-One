# Process Activation and Trigger Intelligence

**Version:** 1.0
**Status:** Approved (Core 2.0)
**Module:** Core / ConceptualArchitecture

---

## Related documents

- [00_RF-One_Core_Vision.md](00_RF-One_Core_Vision.md)
- [../Process.md](../Process.md) — Goal, Inputs, Rules, "Phases of Execution"; Process Activation (§4 below) specializes how a Process or phase becomes executable.
- [11_Process_Autonomy_and_Exception_Driven_Human_Involvement.md](11_Process_Autonomy_and_Exception_Driven_Human_Involvement.md) — the principle this document operationalizes at the point where a Process starts, advances, or resumes: RF-One executes autonomously within established rules and Delegated Authority, and involves a person only when genuinely required.
- [12_Attention_Management.md](12_Attention_Management.md) — Trigger Intelligence identifies that a condition requires human attention; Attention Management determines who receives it, with what priority, through what channel (§11 below).
- [09_Identity_Authority_and_Accountability.md](09_Identity_Authority_and_Accountability.md) — Authority and Delegation bound what a recognized trigger may actually cause to happen (§3, "Authorized Consequence").
- [06_Business_Autopilot_and_Intelligence_Engine.md](06_Business_Autopilot_and_Intelligence_Engine.md) — Delegated Authority; the Intelligence Engine abstraction Trigger Intelligence itself is subject to.
- [05_Epistemic_Boundary_and_Subject_Sovereignty.md](05_Epistemic_Boundary_and_Subject_Sovereignty.md) — the Fact/Inference/Unknown distinction this document relies on for Missing Semantics (§10) and Derived Trigger Map confidence (§8).
- [03_Decision_Action_Outcome_Learning.md](03_Decision_Action_Outcome_Learning.md) — Decision, Action, Outcome; a recognized and resolved trigger leads into this cycle, it does not replace it.
- [14_Cognito_RF-One_Cognitive_Intelligence.md](14_Cognito_RF-One_Cognitive_Intelligence.md) — Cognito, RF-One's Cognitive Intelligence, of which Trigger Intelligence is a capability (§13 below corrects an earlier formulation accordingly).
- See also [16_Ambient_Operational_Context_and_In-Flow_Cognito_Assistance.md](16_Ambient_Operational_Context_and_In-Flow_Cognito_Assistance.md) — status APPROVED — Post-Baseline Conceptual Extension, ratified by the Product Owner and still not part of the canonical 00–14 set (ratification does not retroactively extend `core-2.0-freeze`). It states that Ambient Operational Context may supply Trigger Discovery evidence (§3 above), but never itself constitutes Trigger Resolution or an Authorized Consequence; it does not redefine this document's §1–§11.
- See also [17_Visual_Video_Context_as_Ambient_Evidence.md](17_Visual_Video_Context_as_Ambient_Evidence.md) — status PROPOSED — Post-Baseline Conceptual Extension, a sub-extension of document 16. It states that authorized visual/video observation may likewise supply Trigger Discovery evidence only, never itself Trigger Resolution or an Authorized Consequence.
- See also [../ImplementationGuidelines.md](../ImplementationGuidelines.md), "Channel Independence" (§12 below) and [../RF-ONE Core Principles.md](../RF-ONE%20Core%20Principles.md).

---

## Purpose

This document defines **Process Activation** and **Trigger Intelligence**: how RF-One recognizes, from the canonical knowledge of a Process and of Reality, the events and conditions that start it, advance it, change its relevant behavior, or require human attention — without depending on a centralized, manually maintained, trigger-by-trigger hardcoded list.

It does not redefine Process, Decision, Authority, Delegation, Process Autonomy or Attention Management. It specializes them at the specific point where a Process becomes active or relevant.

---

## 1. The general principle

> **RF-One must not depend on a centralized, manually maintained list of hardcoded triggers for each Process.**

Every Process must be documented with sufficient semantics for RF-One to recognize: the events that activate it; the conditions that make it executable; the variables that change its behavior; the conditions that make a given Rule applicable; the conditions that require Attention; and the conditions that allow it to continue or resume.

**Trigger Intelligence** is the use of this Process knowledge to recognize these conditions. It is a way of reading and reasoning about canonical knowledge that already exists (Process, Business Rules, Entities, States, Authority) — it is not a new body of business knowledge, and it does not decide what RF-One is authorized to do about what it recognizes (§3).

---

## 2. Explicit and Implicit Triggers

**Explicit Trigger** — the condition is stated directly in the Process or in the Business Knowledge it references (for example: a document is received; a Payroll Period is closed; a specific state is reached; an explicitly named discrepancy condition occurs).

**Implicit Trigger** — the condition emerges logically from the relationship between Process, Entity, State, Variable, Business Rule, Authority, Outcome and current Reality, without being separately named as a trigger.

> **An implicit trigger is not invented by RF-One. It must be derivable from available canonical knowledge.**

If a consequence cannot be demonstrated from existing Business Knowledge, it is not a reliable operational trigger — it is, at most, a Hypothesis (see [05_Epistemic_Boundary_and_Subject_Sovereignty.md](05_Epistemic_Boundary_and_Subject_Sovereignty.md) §1), and must be treated accordingly, not silently promoted to an operational condition.

---

## 3. Trigger Discovery, Trigger Resolution, and Authorized Consequence

Three distinct steps must never be confused:

```text
TRIGGER DISCOVERY
  → recognizing that a variable, event or condition may be significant for a Process.

TRIGGER RESOLUTION
  → determining whether, in current Reality, that condition is actually satisfied.

AUTHORIZED CONSEQUENCE
  → determining what RF-One may actually do once a trigger is recognized and resolved,
    strictly within Business Rules and Delegated Authority.
```

> **Trigger recognition ≠ execution authority.**

Recognizing a trigger — even correctly and with high confidence — never by itself grants RF-One Authority to act on it. What RF-One may do next remains governed entirely by the Process's own Rules and by Delegated Authority ([06_Business_Autopilot_and_Intelligence_Engine.md](06_Business_Autopilot_and_Intelligence_Engine.md); [09_Identity_Authority_and_Accountability.md](09_Identity_Authority_and_Accountability.md) §3). A recognized trigger that implies a possible new Business rule, a new mapping, or a new delegation is itself, at most, a signal for Attention (§11) or Governance work — never a self-authorizing event.

---

## 4. Process Activation

**Process Activation** is broader than "starting a Process." It may mean, illustratively and non-exhaustively:

- activating a phase (see [Process.md](../Process.md), "Phases of Execution");
- making a previously inactive phase executable;
- resuming a suspended Process;
- changing the relevant branch of a Process;
- making a Rule applicable;
- requiring Attention;
- producing a transition consistent with the Process.

Core does not fix a rigid taxonomy beyond these illustrative cases. What counts as an activation event is Process/Domain-specific, derived from that Process's own documented triggers (§2), not from a universal enumeration.

---

## 5. Time is just an event

Scheduling is not modeled here as a separate, foundational concept in its own right. From the standpoint of Process Activation, "it is 02:00," "an invoice arrived," "the customer is seated," "the Payroll Period is closed," and "a second source is available" are all observable changes in Reality that may become relevant to one or more Processes.

Time-based conditions are therefore one possible kind of event or condition among others — not the dominant model of activation. A Process's trigger may be temporal, event-driven, state-driven, or a combination, exactly as that Process's own Rules define it (Process.md, "Scheduling/Programming" remains the phase where such conditions are established; this document does not redefine that phase).

---

## 6. One event may affect multiple Processes

A single event may be relevant to more than one Process. Core does not assume a fixed mapping of `Event → one Module/Process`.

Trigger Intelligence must be able to determine which Processes are affected by an observed change, based on available Business Knowledge — without duplicating Business Rules inside a separate "trigger layer." The Rules that make an event relevant to a given Process remain owned by that Process's own Domain documentation; Trigger Intelligence reads them, it does not restate or fork them.

---

## 7. Process as the source of truth

The Process and its associated canonical Business Knowledge remain the source of truth. Trigger Intelligence must not become a parallel repository of Business Knowledge.

A Process's documentation must either be semantically sufficient on its own, or explicitly reference the knowledge genuinely needed to derive its triggers.

This requirement is drawn directly from experimental evidence: a repeatability test conducted on the Invoice Intake / Purchasing Process found that its unstable triggers were concentrated exactly where the necessary semantics lived in a peripheral document never referenced by the Process's own canonical description — not where the underlying business condition was itself ambiguous.

---

## 8. Derived Trigger Map

A **Derived Trigger Map** is knowledge *derived* from a Process — never a primary source, and never a manually maintained hardcoded list. Where used, for reliability and runtime purposes, it may represent: the recognized trigger; its semantic source; the observed variable/event; the condition; its effect on the Process; a confidence/certainty level; and a validation status, where applicable.

A Derived Trigger Map must be:

- **regenerable** from the Process;
- **invalidatable/recomputable** whenever the canonical knowledge changes;
- **subordinate** to the Process;
- **never authoritative** relative to the Business Knowledge it was derived from.

This document does not design a data model, a table, or a runtime artifact for a Derived Trigger Map — it only establishes the concept and its non-authoritative, derived status.

---

## 9. Stability and validation

An experimental repeatability test on Invoice Intake / Purchasing found: 17 distinct triggers, 11 Stable, 3 Probable, 3 Unstable, 0 Conflict. This result is recorded here as **experimental evidence**, not as a universal rule or a guaranteed ratio for every future Process.

> **A single AI pass does not guarantee perfect coverage.**

For critical Processes, Trigger Intelligence must be able to use stabilization/validation mechanisms for the knowledge it derives. This document does not define, as part of this task, what those mechanisms are — multiple passes, quorum, human approval, confidence thresholds, and persistence policy are illustrative future implementation concerns, not fixed here.

---

## 10. Missing Semantics

When Trigger Intelligence recognizes a potentially significant condition but the available Business Knowledge does not contain enough information to resolve it operationally, RF-One must **not** invent the missing value.

It must instead represent the gap. Illustrative examples: an undefined confidence threshold; a responsible Authority that is not linked to the condition; a missing reference value.

A represented gap may subsequently generate Attention (§11), Governance work, or a documentation improvement — it never authorizes an arbitrary inference in its place. This applies the existing Epistemic Boundary ([05_Epistemic_Boundary_and_Subject_Sovereignty.md](05_Epistemic_Boundary_and_Subject_Sovereignty.md) §1): a missing value stays an explicit `Unknown`, never a silently assumed Fact.

---

## 11. Relationship with Attention Management

Trigger Intelligence identifies **that** a condition requires human contribution. It does **not** decide, by its own logic, who should be interrupted, when, or how.

That determination belongs to Attention Management ([12_Attention_Management.md](12_Attention_Management.md)), which uses Process Ownership, Position, Authority, Delegation, Priority, Context and Channel to decide who/when/priority/channel.

```text
Trigger Intelligence  → "Human Attention Required"
Attention Management  → Who / When / Priority / Channel
```

This separation is preserved without exception: Trigger Intelligence must never itself select a person, a channel, or a priority level — those are Attention Management's own responsibilities, reused here rather than duplicated.

---

## 12. Relationship with Channel Independence (Domain capability)

Process Activation must be able to invoke Domain capability independently of the UI. This reuses, and does not duplicate, the Channel Independence principle already formalized in [../ImplementationGuidelines.md](../ImplementationGuidelines.md), "Layer Separation."

Conceptual sequence (extended in [14_Cognito_RF-One_Cognitive_Intelligence.md](14_Cognito_RF-One_Cognitive_Intelligence.md) §5 with Cognito's Human Interaction capability, once Attention Management is involved):

```text
Reality change / Event
→ Trigger Intelligence (a Cognito capability, see document 14)
→ Process Activation / Transition
→ Callable Domain Capability
→ Execution
→ Outcome Verification
→ Attention Management, if required
→ Cognito's Human Interaction capability, Human, intervention if any, Process resumes
```

Each stage reuses an already-approved Core concept (Callable Domain Capability/Channel Independence; Execution and Outcome Verification, [03_Decision_Action_Outcome_Learning.md](03_Decision_Action_Outcome_Learning.md) and [11_Process_Autonomy_and_Exception_Driven_Human_Involvement.md](11_Process_Autonomy_and_Exception_Driven_Human_Involvement.md) §3; Attention, §11 above) — this document only names the sequence that connects them.

---

## 13. Relationship with Cognito

**Correction:** an earlier formulation of this section described Cognito as merely "a possible interaction channel," external to Trigger Intelligence. This is corrected: Trigger Intelligence **is a capability of Cognito** ([14_Cognito_RF-One_Cognitive_Intelligence.md](14_Cognito_RF-One_Cognitive_Intelligence.md) §2), RF-One's Cognitive Intelligence — not a separate intelligence, and not something Cognito merely carries messages for. The distinction between Trigger Intelligence and Cognito's other capabilities (Human Interaction, Context Interpretation, Explanation, Briefing/Debriefing) is functional, not ontological.

Trigger Intelligence, as a capability, can operate entirely in the background, independent of whether any conversation is taking place. Cognito's separate Human Interaction capability may: communicate a relevant recognized trigger; request a decision; explain a consequence; receive a human intervention. Whichever capability is active, Cognito must not contain Business Logic, and must never be a required dependency for Process Activation — consistent with [11_Process_Autonomy_and_Exception_Driven_Human_Involvement.md](11_Process_Autonomy_and_Exception_Driven_Human_Involvement.md) §5 and [12_Attention_Management.md](12_Attention_Management.md) §7. See [14_Cognito_RF-One_Cognitive_Intelligence.md](14_Cognito_RF-One_Cognitive_Intelligence.md) for the full canonical definition of Cognito.

---

## 14. Illustrative example — Invoice Intake (non-normative)

The following restates, briefly and only as illustration, findings from a repeatability test on Invoice Intake / Purchasing. It does not become a Core rule and does not modify Invoice Intake or Purchasing Domain documentation.

- *Document received* → Process Activation.
- *A second source becomes available* → an implicit trigger: reconciliation becomes executable.
- *Identity certain vs. uncertain* → a Process-Relevance condition: Alert vs. Validation path.
- *A receiving discrepancy* → a condition requiring Attention.
- *A confidence threshold is undefined* → Trigger Discovery is possible, but Trigger Resolution is incomplete: a Business Knowledge gap (§10), not an invented value.

---

## Non-assumptions

Do not assume:

```text
Trigger Intelligence is implemented, or any AI model is selected, by this document
a scheduler, event bus, queue, or Trigger table is created by this document
a Derived Trigger Map data model, schema, or runtime artifact is designed here
a confidence-scoring algorithm is defined here
this document authorizes any specific interface, API, or technology
Scheduling is elevated to a foundational Core concept separate from Process Activation
this document changes what a Decision, Action, Outcome, Process, Authority or
  Delegation is, or narrows Attention Management or Channel Independence
recognizing a trigger grants any Authority beyond what is already Delegated
a missing threshold, reference value, or unlinked Authority may be inferred
  rather than represented as a gap
```
