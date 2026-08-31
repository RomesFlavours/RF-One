# Future Development

**Version:** 1.0
**Status:** Approved
**Module:** Restaurant Domain / Server Performance
**Origin:** TASK_SERVER_PERFORMANCE_001

---

## Judgment / Customer Reading

**Explicitly future development — not required for the first implementation, and not implemented by this task.**

RF-One may eventually evaluate `Judgment / Customer Reading`:

> How well a Server interprets the table and decides when to pursue an opportunity, modify the approach, or deliberately stop.

This must distinguish:

- observed facts;
- explicit Server input (e.g. a rejection signal — see [Service Copilot/Smartwatch Interaction.md](../Service%20Copilot/Smartwatch%20Interaction.md));
- explicit Customer signals;
- RF-One inference with confidence.

### The rejection signal must not become a false missed-opportunity penalty

A Server should eventually be able to reject a Copilot suggestion with a minimal signal such as "Not appropriate," "Customer not interested," "Already declined," or an equivalent micro-input. **This must never automatically count as a missed opportunity** in [Opportunity Capture.md](Opportunity%20Capture.md) — a Server correctly reading a table that does not want an upsell is good Judgment, not a Gap.

### RF-One later compares Server judgment with outcome

RF-One should later compare the Server's judgment (their decision to pursue, modify, or stop) with the subsequent outcome, and learn whether the Server interpreted the table correctly. This is the critical principle:

> RF-One coaches the Server, but the Server also teaches RF-One about the Customer and the service context.

This is a genuine bidirectional learning loop — distinct from, and complementary to, the Coaching effectiveness loop in [Coaching Model.md](Coaching%20Model.md) (which learns whether an *intervention* worked; Judgment/Customer Reading learns whether the *Server's own read of the table* was correct).

### Why this is deferred

Judgment / Customer Reading depends on:

- a working rejection-signal input mechanism (Service Copilot, not yet built);
- accumulated outcome evidence across many rejected/accepted suggestions per Server;
- a confidence model for RF-One's own table-reading inference, itself unbuilt.

None of these prerequisites exist yet. This document only reserves the concept and its epistemic boundary so a future task does not have to redesign [Opportunity Capture.md](Opportunity%20Capture.md) or [Service Copilot](../Service%20Copilot/README.md) to accommodate it later.

---

## Other explicitly future, non-blocking items

- **Estimated Cash Tips** — the estimation model itself (see [Perceived Service Quality.md](Perceived%20Service%20Quality.md)).
- **Table QR Survey question design** — the actual short question set (see [Perceived Service Quality.md](Perceived%20Service%20Quality.md)).
- **KPI formula finalization** — exact time windows, aggregation methods, thresholds for every family in [KPI Framework.md](KPI%20Framework.md).
- **Brand configuration surface** — the actual Product/Runtime mechanism by which a Restaurant enters its Brand Expectation, strategic products, and Service Copilot intrusiveness level (see [Brand Expectation and Personal Baseline.md](Brand%20Expectation%20and%20Personal%20Baseline.md), [../Service Copilot/Management Intrusiveness.md](../Service%20Copilot/Management%20Intrusiveness.md)).
- **Reservation/Guest provider adapters** — OpenTable, Resy, future CRM/walk-in identification, all via Dining Intelligence (see [../Dining Intelligence/Customer Consumption Profile.md](../Dining%20Intelligence/Customer%20Consumption%20Profile.md), "Reservation / Guest sources").

None of these block declaring the conceptual architecture defined by this task complete — see `07 Tasks/Reports/TASK_SERVER_PERFORMANCE_001_REPORT.md`.

---

## Related documents

- [Opportunity Capture.md](Opportunity%20Capture.md)
- [Coaching Model.md](Coaching%20Model.md)
- [../Service Copilot/Smartwatch Interaction.md](../Service%20Copilot/Smartwatch%20Interaction.md)
- [Exclusions.md](Exclusions.md)
