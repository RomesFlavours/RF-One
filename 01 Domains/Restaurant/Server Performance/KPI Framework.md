# KPI Framework

**Version:** 1.0
**Status:** Approved
**Module:** Restaurant Domain / Server Performance
**Origin:** TASK_SERVER_PERFORMANCE_001

---

## KPI design principle (mandatory order)

RF-One does **not** begin from the list of available Clover fields. For every candidate KPI, the order of reasoning is:

```text
1. What behavior/outcome are we trying to understand?
2. Why does it matter?
3. What canonical facts are required?
4. Which evidence sources can provide them?
5. What can be directly observed?
6. What must be derived?
7. What is only inferred?
8. What contextual normalization is required?
9. How can this KPI be misleading?
10. How can RF-One use it for coaching?
```

This mirrors, for the Server role specifically, the generic KPI-discovery principle already established (`01 Domains/Domain Architecture.md` §8; `Personnel Management/Performance/PerformanceIndicator.md`): no Measure is canonized as a permanent, universal KPI. The families below are candidates — grounded in the dimensions defined by [Server Performance.md](Server%20Performance.md), [Quality of Sale.md](Quality%20of%20Sale.md), [Opportunity Capture.md](Opportunity%20Capture.md), [Concurrent Service Load.md](Concurrent%20Service%20Load.md) and [Perceived Service Quality.md](Perceived%20Service%20Quality.md) — not a finalized formula set. **No formula here is fully optimized; each is a starting definition, further specified by a future task once real evidence volume exists to validate it.**

---

## KPI families

### Productivity

- Sales per Hour Worked
- Orders / Tables per Hour where meaningful
- Sales per concurrent service opportunity where definable (ties to [Concurrent Service Load.md](Concurrent%20Service%20Load.md))

*Remaining to be fully specified:* exact time-window convention, whether "hours worked" uses Shift evidence or a derived active-service window, and how "per concurrent service opportunity" is normalized.

### Quality of Sale

- strategic product penetration
- premium product mix
- food-category mix
- beverage mix
- appetizer attach rate
- dessert attach rate
- wine attach/conversion
- modifiers/add-ons attach
- Brand-priority products

*Remaining to be fully specified:* the qualifying-check definition for each attach rate, and how Brand-configured strategic products are weighted relative to one another. See [Quality of Sale.md](Quality%20of%20Sale.md).

### Opportunity Capture

- available opportunity
- captured opportunity
- opportunity conversion
- opportunity value captured
- opportunity value missed

*Remaining to be fully specified:* the Dining Session Profile feature set and confidence model Available Opportunity actually depends on ([Dining Intelligence/Dining Session Profile.md](../Dining%20Intelligence/Dining%20Session%20Profile.md)) — this is future Dining Intelligence work, not finalized here. See [Opportunity Capture.md](Opportunity%20Capture.md).

### Service Quality Evidence

- Tip-related evidence (observed card/electronic Tips, tip percentage, tips per hour, tips relative to comparable context — never Estimated Cash Tip presented as fact)
- future survey evidence (Table QR Survey)
- refund/complaint-related signals where valid

*Remaining to be fully specified:* the Estimated Cash Tip model itself (explicitly not built by this task — see [Perceived Service Quality.md](Perceived%20Service%20Quality.md)) and the QR Survey question set (explicitly not designed by this task). See [Perceived Service Quality.md](Perceived%20Service%20Quality.md).

### Operational Discipline

- discounts
- voids
- refunds
- unusual adjustments
- payment anomalies

*Remaining to be fully specified:* what counts as "unusual" (a threshold, a statistical deviation from the Server's own Personal Baseline, or a Brand-configured limit) — not fixed here; causation is never assumed from these signals alone (see [Server Performance.md](Server%20Performance.md), "Operational Discipline").

### Performance Under Load

- concurrent guests/tables
- performance degradation curve
- Capacity
- Acceleration
- Resilience

*Remaining to be fully specified:* the statistical method for fitting a Server's degradation curve from observed load/outcome pairs. See [Concurrent Service Load.md](Concurrent%20Service%20Load.md).

### Personal Development

- variance from Personal Baseline
- variance from Brand Expectation
- response to coaching
- sustained improvement
- regression

*Remaining to be fully specified:* the minimum evidence window before a trend is treated as "sustained" rather than noise — reuses, but does not further specify, the Temporal Coherence framing already established generically (`Performance.md`, "Temporal evolution"). See [Coaching Model.md](Coaching%20Model.md).

---

## Tip-based performance (cross-cutting note)

Because Tips appear in both Service Quality Evidence and Coaching's economic-motivation estimates, the epistemic discipline is repeated here for emphasis: distinguish observed card/electronic Tips, future Estimated Cash Tips, tip percentage, tips per hour, and tips relative to comparable service context. **Tip % is never equated directly with service quality** — it is one signal among several. See [Perceived Service Quality.md](Perceived%20Service%20Quality.md).

---

## What this document does not do

- It does not fix exact formulas, time windows, rounding rules or aggregation methods for any KPI listed above.
- It does not implement any calculation, database field, or software.
- It does not declare any Measure a permanent Indicator — relevance is Goal/Brand/context-dependent and derived, per `Personnel Management/Performance/PerformanceIndicator.md`.

---

## Related documents

- [Server Performance.md](Server%20Performance.md)
- [Quality of Sale.md](Quality%20of%20Sale.md), [Opportunity Capture.md](Opportunity%20Capture.md), [Concurrent Service Load.md](Concurrent%20Service%20Load.md), [Perceived Service Quality.md](Perceived%20Service%20Quality.md)
- [../../Personnel Management/Performance/PerformanceMeasure.md](../../Personnel%20Management/Performance/PerformanceMeasure.md), [../../Personnel Management/Performance/PerformanceIndicator.md](../../Personnel%20Management/Performance/PerformanceIndicator.md)
- [../../Domain Architecture.md](../../Domain%20Architecture.md) §8
