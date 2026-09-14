# Attention Management

**Version:** 1.0
**Status:** Approved (Core 2.0)
**Module:** Core / ConceptualArchitecture

---

## Related documents

- [11_Process_Autonomy_and_Exception_Driven_Human_Involvement.md](11_Process_Autonomy_and_Exception_Driven_Human_Involvement.md) — the principle this document operationalizes: when, to whom, and how a required human contribution actually reaches a person.
- [09_Identity_Authority_and_Accountability.md](09_Identity_Authority_and_Accountability.md) — Acting Identity, Authority, Delegation, Auditability.
- [../Organizational Responsibility.md](../Organizational%20Responsibility.md) — Position, scope, occupant, temporary coverage, Process Ownership. Attention Management **consumes** this document; it does not redefine it.
- [10_RF-One_Intelligence_and_User_Relationship.md](10_RF-One_Intelligence_and_User_Relationship.md) §§6, 10–12 — Explicit vs. Inferred, proactive intelligence, and the Deterministic action / Authorized autonomy / Recommendation / Material human decision distinction.
- [06_Business_Autopilot_and_Intelligence_Engine.md](06_Business_Autopilot_and_Intelligence_Engine.md) — escalation triggers, Intelligence Engine abstraction.
- [../Process.md](../Process.md) — "Phases of Execution."
- [14_Cognito_RF-One_Cognitive_Intelligence.md](14_Cognito_RF-One_Cognitive_Intelligence.md) — the canonical definition of Cognito as RF-One's Cognitive Intelligence; §7 below is corrected to reflect that Cognito's Human Interaction capability, not Cognito itself, is the channel referred to there.
- See also `00 Core/Cognitive Interface/RF-ONE_COGNITIVE_INTERFACE_CONCEPT.md` — an exploratory, status "CONCEPTUAL DIRECTION — UNDER REVIEW" document. It is not authority for this document; §7 below states how any such interface relates to the principle defined here, independent of that document's own eventual design.
- See also [15_Human_Operational_State_and_Adaptive_Cognito_Interaction.md](15_Human_Operational_State_and_Adaptive_Cognito_Interaction.md) — status APPROVED — Post-Baseline Conceptual Extension, ratified by the Product Owner after the baseline and still not part of the canonical 00–14 set (ratification does not retroactively extend `core-2.0-freeze`). It specializes the "operational state" input already named in §2 and §10 below; it does not redefine who/when/priority/channel decisions, which remain Attention Management's own.

---

## Purpose

This document defines **Attention Management**: the transversal capability by which RF-One determines whether a matter genuinely requires human attention, who should receive it, with what priority, through what channel, and at what level of synthesis. It reuses Process Ownership, Position, Authority, Delegation and Acting Identity ([Organizational Responsibility](../Organizational%20Responsibility.md); [doc 09](09_Identity_Authority_and_Accountability.md)) rather than inventing a parallel notification system.

---

## 1. Not a notification system

Attention Management is not "send a notification." It determines **whether** a matter genuinely requires human attention (the exception-driven principle of [doc 11](11_Process_Autonomy_and_Exception_Driven_Human_Involvement.md)), **who** (the Position responsible per [Organizational Responsibility](../Organizational%20Responsibility.md), and its current occupant or delegate), **with what priority** (§3), **through what channel**, and **at what level of synthesis**.

---

## 2. What Attention Management uses

RF-One draws on all available, relevant context, including: Process Ownership and Position scope ([Organizational Responsibility](../Organizational%20Responsibility.md) §2–§4); Authority and active Delegation/temporary coverage ([doc 09](09_Identity_Authority_and_Accountability.md) §3–§4; [Organizational Responsibility](../Organizational%20Responsibility.md) §3); the occupant's availability and operational state (§10); current operational state; urgency; and the consequence of no intervention. This list is illustrative, not a fixed mandatory input schema.

---

## 3. Priority

Four synthetic levels: **CRITICAL, HIGH, MEDIUM, LOW**. The level is not derived from a fixed universal table — RF-One determines it dynamically from the available, relevant context (§2). The level shapes behavior:

- **CRITICAL** — RF-One must actively obtain human attention, and the signal must also be persisted in textual (or equivalent) form in addition to any immediate channel.
- **HIGH** — requires prompt attention; RF-One actively looks for an appropriate person according to organizational policy (§9).
- **MEDIUM / LOW** — may be aggregated and presented at an appropriate moment, but must never be silenced or discarded.

> **RF-One may decide HOW and WHEN to present a matter; it must never decide to ignore a matter that genuinely requires human attention.**

This is the direct operational consequence of [doc 11](11_Process_Autonomy_and_Exception_Driven_Human_Involvement.md) §4's "operational silence does not mean absence of control, evidence, or the possibility of consultation."

---

## 4. Real-time operational intervention vs. non-real-time attention

Two contexts:

**A. Real-time operational intervention** — situations where immediate action may be needed: a person in operational difficulty, a blocked operational process, an immediate risk, a need for coverage or substitution. RF-One may dynamically search for the most appropriate person according to Position, Authority, availability and organizational policy (§9–§10).

**B. Non-real-time attention** — administrative, managerial or non-urgent operational matters. These are collected into an **attention list** for the appropriate Position/occupant, presented at a contextually appropriate moment: at the start of a shift, in the morning, in the evening, when the person asks "what needs my attention," or at another contextually appropriate moment. This is not fixed as a canonical "morning list" — the moment is contextual, not a Core-defined schedule.

---

## 5. Attention list ≠ report

The attention list is **not** a general operational report. It must contain primarily: decisions required, authorizations required, exceptions, problems to resolve, and matters requiring human judgment. Normal operation must not generate noise. RF-One may answer "everything is running normally," or provide a general summary, but only when requested or configured by the person — information must never be pushed automatically merely because it is available.

---

## 6. Aggregation

MEDIUM and LOW may be aggregated. **CRITICAL must never be aggregated.** HIGH may be handled dynamically according to context. Aggregation must never cause loss of ownership, priority or traceability of the individual matters it groups — this reuses Auditability ([doc 09](09_Identity_Authority_and_Accountability.md) §6), it does not create a new requirement.

---

## 7. Cognito interaction principle

**Correction:** an earlier formulation of this section described Cognito itself as "a possible channel of interaction." Cognito is RF-One's Cognitive Intelligence, not a channel — see [14_Cognito_RF-One_Cognitive_Intelligence.md](14_Cognito_RF-One_Cognitive_Intelligence.md). What functions as the channel here is specifically Cognito's **Human Interaction** capability, which is never the Process engine — [doc 11](11_Process_Autonomy_and_Exception_Driven_Human_Involvement.md) §5 already establishes this generally for any interaction layer; this section applies it specifically to how attention is requested.

Desired pattern:

> "I interrupted you for X. I would do Y. Do you authorize me?"

**Not**: long preventive explanations, complete logs, all available data, every possible alternative. If the person wants to go deeper, they may ask for detail, ask to see information, or open a screen.

> **Voice to understand and decide; screen when a visual representation improves the decision.**

This reuses the screenless-by-default framing already established in [doc 11](11_Process_Autonomy_and_Exception_Driven_Human_Involvement.md) §5; it is not a new rule.

---

## 8. Direct human intervention

Human intervention on a Process must not be possible only when RF-One/Cognito requests it. The Process Owner (the occupant of the responsible Position, [Organizational Responsibility](../Organizational%20Responsibility.md) §4), or a person holding superior Authority, may intervene directly on a Process: stop, authorize, modify, reassign, correct, or resume it.

After a valid human intervention, RF-One must be able to resume the Process automatically from the appropriate point. An additional "continue" command must not be required when the information or decision already received is sufficient — an intervention that already supplies what was missing is itself the resolution, not a separate step requiring further confirmation.

---

## 9. Escalation

Core does **not** fix a universal escalation rule. Organizations may configure different strategies: vertical escalation, substitute, equivalent person, alternative competency, delegate, superior, or a combination of these ([Organizational Responsibility](../Organizational%20Responsibility.md) §5).

For HIGH and CRITICAL, RF-One may actively search for an appropriate person. For CRITICAL specifically: if the primary responsible Position's occupant is unavailable, RF-One must keep searching according to organizational policy — which may legitimately include involving a Position at a lower hierarchical level if it holds sufficient capability/Authority and policy allows it. This is organizational policy/configuration, not a Core rule.

---

## 10. Human state and context

Availability is not merely online/offline. RF-One may consider relevant operational context, for example: serving a customer, in a meeting, engaged in a critical activity, available, absent, or covered by a delegate. This shapes how and when attention is requested. Illustrative, not a rigid or mandatory taxonomy.

---

## 11. Learning

RF-One may learn over time: interaction preferences, desired level of detail, recurring behavior, preferred channels, appropriate timing, and which people most effectively resolve certain problems.

Learning must **not**: automatically modify Business Rules, extend Authority, create new Delegations, or convert a recurring preference into an authorization.

> **Learning improves routing and interaction. It never changes the perimeter of Authority.**

This directly reuses the Authority/Delegation boundaries already established in [doc 09](09_Identity_Authority_and_Accountability.md), and the Explicit-vs-Inferred discipline of [doc 10](10_RF-One_Intelligence_and_User_Relationship.md) §6: a learned preference remains an Inference about interaction, never silently promoted to policy or Authority.

---

## 12. Illustrative example (non-normative)

A server shows signs of significant difficulty during service. RF-One determines that involving the server directly might increase their load. It identifies an available person with adequate responsibility/capability and signals:

> "Charlie is struggling at tables 4, 12 and 23. Can you cover table 12?"

Charlie receives help without additional pressure. This example is illustrative only. It does not establish a medical or diagnostic rule, and does not introduce canonical health monitoring.

---

## Non-assumptions

Do not assume:

```text
Attention Management is a notification/messaging system to be built now
a fixed universal priority-scoring table is defined here
Core fixes escalation as "always go to the superior"
CRITICAL items may ever be aggregated or silenced
Learning may extend Authority or create a Delegation
this document authorizes any specific channel, device or provider
this document creates health/diagnostic monitoring as a canonical capability
this document redefines Position, Process Ownership, Authority or Delegation
```
