# Process Autonomy and Exception-Driven Human Involvement

**Version:** 1.0
**Status:** Approved (Core 2.0)
**Module:** Core / ConceptualArchitecture

---

## Related documents

- [00_RF-One_Core_Vision.md](00_RF-One_Core_Vision.md)
- [03_Decision_Action_Outcome_Learning.md](03_Decision_Action_Outcome_Learning.md) — the operational cycle (Goal → Process → Decision → Action → Outcome → Learning) this document says must run without a human as a mandatory link between stages, within Delegated Authority
- [06_Business_Autopilot_and_Intelligence_Engine.md](06_Business_Autopilot_and_Intelligence_Engine.md) — Business Autopilot, Delegated Authority and escalation, which this document specializes into a principle about how a Process is executed, verified and escalated
- [09_Identity_Authority_and_Accountability.md](09_Identity_Authority_and_Accountability.md) — Acting Identity and Authority, which bound what RF-One may execute autonomously and determine which specific Acting Identity an escalation must reach
- [10_RF-One_Intelligence_and_User_Relationship.md](10_RF-One_Intelligence_and_User_Relationship.md) §10–§12 — proactive intelligence and the Deterministic action / Authorized autonomy / Recommendation / Material human decision distinction, which this document extends specifically to Process execution and completion
- [05_Epistemic_Boundary_and_Subject_Sovereignty.md](05_Epistemic_Boundary_and_Subject_Sovereignty.md) — the Fact/Belief/Inference distinction this document relies on when it says an unverified result must not be presented as achieved
- See also [../Process.md](../Process.md) (Process components, Verification, Optimization Boundaries, and "Phases of Execution" — Planning/Scheduling-Programming/Management/Operations — reused directly below), [../Goal.md](../Goal.md), and [../ArchitecturePrinciples.md](../ArchitecturePrinciples.md) ("Human Authority").
- [14_Cognito_RF-One_Cognitive_Intelligence.md](14_Cognito_RF-One_Cognitive_Intelligence.md) — the canonical definition of Cognito as RF-One's Cognitive Intelligence, whose Human Interaction capability is the "interaction layer" §5 below refers to.
- See also `00 Core/Cognitive Interface/RF-ONE_COGNITIVE_INTERFACE_CONCEPT.md` — an exploratory, status "CONCEPTUAL DIRECTION — UNDER REVIEW" document about a future interaction layer. That document is not authority for this principle and this document does not depend on it; it is noted only because §7 below states how any such interface relates to the principle defined here.

---

## Purpose

This document states a Core principle: RF-One must execute its Processes autonomously, within already established rules and Delegated Authority, verify their actual result, and involve the competent person only when genuine human contribution is required — never as a routine substitute for already-authorized autonomous execution, merely relocated onto a different interaction channel.

It does not redefine Goal, Process, Decision, Action, Outcome, Learning, Authority, Delegation or Accountability. It specializes them.

---

## 1. The canonical principle

> **RF-One must execute its Processes autonomously within established rules and Delegated Authority, verify their result, and involve the competent person only when genuine human contribution is required.**

The objective is not to replace clicks with voice commands. The objective is to remove the need for a person to start, accompany or repeatedly confirm a routine that the system is already authorized and able to execute.

A sequence of voice commands that reproduces a sequence of screens does not realize this principle: it keeps the person as a mandatory link between the stages of the work (see §7).

Autonomy is exercised within a defined, tested and authorized boundary. It does not authorize RF-One to widen its own Delegated Authority, invent rules, or bypass an authorization that is actually required (see [06_Business_Autopilot_and_Intelligence_Engine.md](06_Business_Autopilot_and_Intelligence_Engine.md) §2, Process.md "Optimization Boundaries").

This principle concerns automating work the system is able to execute. It does not eliminate human work that is intrinsically necessary, ownership of Decisions, or accountability for the Process (see [09_Identity_Authority_and_Accountability.md](09_Identity_Authority_and_Accountability.md) §5, Accountability).

---

## 2. The Process comes before the interaction

A Process description must start from the result to be obtained, not from the operations a user performs in an application (Goal.md, "Outcome First"; Process.md, Components).

To describe a Process, the following must be made explicit, reusing existing Core concepts rather than introducing new ones:

- the **expected result** and the condition that demonstrates it was reached (Goal.md Principle 6, Verification; Process.md, "Verification");
- the **triggering event or condition** that starts it (part of the Reality a Decision evaluates — [03_Decision_Action_Outcome_Learning.md](03_Decision_Action_Outcome_Learning.md) §2);
- the **information and prerequisites** required (Process.md, "Inputs");
- the **rules, constraints, authority and execution limits** in force (Process.md, "Optimization Boundaries"; [09_Identity_Authority_and_Accountability.md](09_Identity_Authority_and_Accountability.md) §3, Authority);
- the **activities RF-One may execute autonomously** within that authority ([03_Decision_Action_Outcome_Learning.md](03_Decision_Action_Outcome_Learning.md) §3, Action "may be performed ... by RF-One within delegated authority"; [06_Business_Autopilot_and_Intelligence_Engine.md](06_Business_Autopilot_and_Intelligence_Engine.md) §1, "RF-One handles it");
- the **conditions that require a human contribution**, and the Acting Identity responsible for it ([09_Identity_Authority_and_Accountability.md](09_Identity_Authority_and_Accountability.md) §2–§3; [06_Business_Autopilot_and_Intelligence_Engine.md](06_Business_Autopilot_and_Intelligence_Engine.md) §1, escalation triggers).

No new entity, taxonomy or technical model is introduced to represent this. The list above is a restatement of Process.md's existing Components (Goal, Inputs, Activities, Decisions, Rules, Quality Checks, Verification) together with Authority/Acting Identity already defined in document 09.

---

## 3. Completion requires the verified result, not a calculation or a dispatched command

A Process is not concluded because a calculation has finished or because a command was sent to an external system.

Completion requires the verification proper to the expected result (Process.md, "Verification"; [03_Decision_Action_Outcome_Learning.md](03_Decision_Action_Outcome_Learning.md) §4, Outcome — "what actually happens ... as observed in Reality," not what was expected at Decision time).

A result that has not yet been verified must not be presented as achieved. This applies the existing Epistemic Boundary ([05_Epistemic_Boundary_and_Subject_Sovereignty.md](05_Epistemic_Boundary_and_Subject_Sovereignty.md) §1): an unverified result is at most an Inference or a Hypothesis, never a Fact, and must not be silently treated as one.

Existing Core distinctions are preserved, including the sequence by which a Process moves from being planned to being actually carried out: Planning → Scheduling/Programming → Management → Operations, formalized in [Process.md](../Process.md), "Phases of Execution." A Process need not formally contain all four phases, and none of them is defined by who or what performs it — RF-One may perform Planning, Scheduling/Programming, Management or Operations activity within Delegated Authority, exactly as §4-§5 below describe for exceptions and escalation.

Do not turn Reporting, Administration, Analysis or Feedback into new operational stages of the Decision → Action → Outcome → Learning cycle. The **operational verification** needed to confirm that the expected result was actually reached is part of the Process itself (Outcome, §4 above); the **subsequent** reporting and analysis that consume an already-verified Outcome are a different, later activity, not a precondition for the Process to be considered complete.

---

## 4. Normal operation and exceptions

Normal operation is recorded and remains available for consultation (Auditability, [09_Identity_Authority_and_Accountability.md](09_Identity_Authority_and_Accountability.md) §6). It does not require, by default, announcements, repeated confirmations, or success notifications.

> **Operational silence does not mean absence of control, evidence, or the possibility of consultation.**

An anomaly must not automatically be forwarded to the highest authority in the organization, and does not necessarily require a human at all.

When RF-One can resolve it safely within existing rules and Delegated Authority, it does so autonomously ([06_Business_Autopilot_and_Intelligence_Engine.md](06_Business_Autopilot_and_Intelligence_Engine.md) §1). Autonomy must not be confused with indefinite retrying or with actions that are not authorized (Process.md, "Optimization Boundaries": efficiency and optimization must never silently override Subject Sovereignty, Delegated Authority, applicable law/policy or known risk limits).

When a human intervention is genuinely required, the request must reach the Acting Identity competent for that specific matter: the operational owner, the technical maintainer, or the holder of the necessary Authority for the case at hand — determined by Authority's existing contextual scoping ([09_Identity_Authority_and_Accountability.md](09_Identity_Authority_and_Accountability.md) §3), not by a single fixed escalation target.

The request must contain: the context, the circumscribed problem, what has already been done, what remains pending, and the precise contribution requested.

Do not place the entire Process on the person merely because one step was not completed. Whether the unaffected parts of the Process proceed depends on that Process's own rules and dependencies (Process.md, Components: Activities, Decisions, Rules), not on a universal assumption that one unresolved step halts everything.

"Tips mechanic" is an illustrative expression the Product Owner has used for this kind of intervention role. It does not create a new canonical role; the underlying concept is the Acting Identity holding the relevant Authority for the specific matter ([09_Identity_Authority_and_Accountability.md](09_Identity_Authority_and_Accountability.md) §2–§3), determined per Domain and per Process.

---

## 5. Interaction channel is not the Process

Whatever interaction layer RF-One eventually uses — voice, text, or screen — is a channel through which a human and RF-One's Processes communicate. It is not a required trigger for a Process whose start condition and Authority are already established (§2). Where that layer is Cognito, RF-One's Cognitive Intelligence, it is specifically Cognito's Human Interaction capability that serves as this channel — Cognito itself is broader than a channel (see [14_Cognito_RF-One_Cognitive_Intelligence.md](14_Cognito_RF-One_Cognitive_Intelligence.md)).

It should not be necessary to issue a command every time to start a routine already governed by a defined triggering condition.

Voice, text and screen are interaction channels, not mandatory stages of a Process. The design direction is voice as the primary channel where appropriate, with minimal necessary reliance on the screen. The screen remains available whenever a visual representation is useful; this document does not introduce an absolute prohibition on graphical interfaces.

Exception-driven involvement concerns only the human contribution needed to keep autonomous routines running. It does not prohibit spontaneous questions, consultation, briefing or coaching when these are the service the person is actually requesting — that relationship is already governed by [10_RF-One_Intelligence_and_User_Relationship.md](10_RF-One_Intelligence_and_User_Relationship.md) (§§2, 7–9) and is not narrowed by this document.

Deterministic calculations and rules must not be left to an Intelligence Engine's free-form interpretation ([06_Business_Autopilot_and_Intelligence_Engine.md](06_Business_Autopilot_and_Intelligence_Engine.md) §4, "AI reasons about the Core but is not part of it"; Process.md, "AI does not define the Process"; Goal.md Principle 8, "AI never changes the meaning of a Goal").

This principle is independent of specific devices, providers or technologies, consistent with the Intelligence Engine abstraction already established in [06_Business_Autopilot_and_Intelligence_Engine.md](06_Business_Autopilot_and_Intelligence_Engine.md) §4.

---

## 6. Illustrative example — Tips (not an implementation record)

The following is reported as a Product Owner functional objective, **not** as an attestation of already-implemented software.

A nightly routine: acquires tips from an external point-of-sale system; verifies the required data; applies the already-defined distribution rules; disburses payments through an external payment provider; verifies the outcomes and records the resulting facts.

The 10% share to hosts is an example of a Domain-level rule. This document does not redefine its calculation basis, eligibility or criteria. Nightly cadence, the specific point-of-sale/payment providers, and percentages are illustrative, Domain/Runtime detail — not Core.

At steady state, after testing and authorization, the responsible person does not need to start this process every night, nor repeatedly reconfirm the same already-established rules. The interaction layer involves them only for a matter that genuinely requires their contribution or Authority; other exceptions go to their respective responsible parties.

The expected result is not "tips calculated" or "command sent" — it is the payment correctly completed and verified (§3).

This example does not authorize any integration, real payment execution, changes to the Tips/Compensation/Payroll/Banking Domain boundaries, or duplicate payment logic. It does not replace the specifications of the Domains involved.

---

## Non-assumptions

Do not assume:

```text
this document grants RF-One any Authority beyond what is already explicitly Delegated
this document changes what a Decision, Action, Outcome, Learning or Process is
this document fixes "tips mechanic," or any other illustrative label, as canonical
  Core vocabulary for an escalation role
this document authorizes any specific interface, device, vendor, integration,
  or the Cognitive Interface concept described elsewhere
this document requires removing or replacing any existing screen or UI
an unresolved integration for the Tips example is a precondition for this
  Core principle
this document turns Reporting, Administration, Analysis or Feedback into new
  stages of the Decision → Action → Outcome → Learning cycle
Management, specifically, requires a human — RF-One may perform governing
  activity within Delegated Authority, see Process.md, "Phases of Execution"
```
