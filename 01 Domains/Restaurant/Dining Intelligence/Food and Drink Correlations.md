# Food and Drink Correlations

**Version:** 1.0
**Status:** Approved — responsibility and boundaries defined; no model implemented
**Module:** Restaurant Domain / Dining Intelligence
**Origin:** TASK_SERVER_PERFORMANCE_001

---

## Purpose

Dining Intelligence should learn statistical/behavioral relationships between consumption patterns, such as:

```text
"Tables with consumption pattern X frequently purchase beverage Y."
"When product A is ordered, product B becomes a high-probability complementary opportunity."
```

**Do not implement these models now.** This document defines the canonical responsibility and boundaries only.

---

## Why this belongs to Dining Intelligence, not Server Performance

A learned correlation (e.g. "Tables ordering the seafood special frequently add a specific white wine") is a property of consumption behavior in general — it is true regardless of which Server is working the table. Placing correlation-learning inside Server Performance would force every non-Performance consumer (Menu, Marketing, Purchasing forecasting) to depend on a Personnel-Management-adjacent module for a purely commercial/consumption capability. See [README.md](README.md), "Why a separate, shared module."

---

## Consumers (illustrative, not exhaustive)

```text
Server Performance      → informs what counts as "Available Opportunity" (Server Performance/
                           Opportunity Capture.md)
Service Copilot          → informs Next Best Action candidate suggestions (Service Copilot/Next
                           Best Action and Next Best Moment.md)
Training                 → what consumption patterns a Server should learn to recognize
Menu                      → which combinations perform well/poorly, informing menu engineering
Marketing                 → campaign targeting based on observed consumption correlation
Sales analytics            → aggregate trend reporting
Purchasing / Inventory forecasting → demand signal where relevant
Brand analysis              → cross-Location consumption comparison
```

Each consumer applies its own judgment to a correlation Dining Intelligence supplies; Dining Intelligence does not dictate what any consumer does with a correlation it learns.

---

## Epistemic status

A learned correlation is always **Inferred** — a statistical relationship observed across many Dining Sessions, carrying uncertainty and a confidence/support level, never presented as a deterministic rule ("guests who order X always order Y"). It must remain traceable to the underlying Observed Order Item evidence it was learned from, the same traceability requirement already established for a [Performance Indicator](../../Personnel%20Management/Performance/PerformanceIndicator.md).

A correlation is also never treated as causal without further evidence — "tables ordering X frequently also order Y" does not establish that suggesting Y to a table that ordered X will actually increase conversion; it only establishes association. Whether a suggested correlation genuinely helps is itself subject to the same intervention/outcome learning loop [Server Performance/Coaching Model.md](../Server%20Performance/Coaching%20Model.md) already applies to coaching interventions.

---

## Not implemented by this task

No correlation-learning algorithm, statistical model, ML pipeline, or database schema is built by this document or this task. This is explicitly future Product/Runtime/Intelligence Engine work, built once Dining Session Profile evidence exists in sufficient volume to learn from.

---

## Related documents

- [README.md](README.md)
- [Dining Session Profile.md](Dining%20Session%20Profile.md)
- [../Server Performance/Opportunity Capture.md](../Server%20Performance/Opportunity%20Capture.md)
- [../Service Copilot/Next Best Action and Next Best Moment.md](../Service%20Copilot/Next%20Best%20Action%20and%20Next%20Best%20Moment.md)
