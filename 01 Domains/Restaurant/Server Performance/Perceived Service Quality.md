# Perceived Service Quality

**Version:** 1.0
**Status:** Approved
**Module:** Restaurant Domain / Server Performance
**Origin:** TASK_SERVER_PERFORMANCE_001

---

## Purpose

The quality perceived by the guest is a distinct Performance dimension, separate from Productivity, Quality of Sale, Opportunity Capture and Operational Discipline. Clover alone cannot measure it sufficiently — Clover records transactions, not guest sentiment. RF-One therefore supports, and must eventually integrate, a future direct Guest Feedback evidence source, while treating today's best available proxy (Tips) with explicit epistemic caution.

---

## Tips as evidence — carefully interpreted

Tips are useful Service Quality evidence but must never be equated directly with service quality; a tip percentage reflects guest custom, party composition, payment method, check size and many factors beyond service. It is **one signal among several**, never a proxy score.

At minimum, distinguish:

- **observed card/electronic Tips** — the `Payment Tip` fact already canonical in Sales/Tips (`Sales/Restaurant Sales Model.md` §14 "Tip"; `Tips/Tip.md`);
- **future Estimated Cash Tips** — see below;
- **tip percentage**;
- **tips per hour**;
- **tips relative to comparable service context** (Performance Context — party size, check size, daypart).

### Do not treat Cash Tips as known facts

Cash Tips physically left at the table are generally not directly observable from Clover with sufficient reliability. RF-One must **never** silently treat inferred cash tips as factual Cash Tips. Where RF-One later estimates cash tips (e.g. using an expected tip percentage applied to cash-paid checks), the concept must be explicitly named and represented as:

```text
Estimated Cash Tip
```

never merged with, or presented indistinguishably from, an actually **Observed Tip** (the electronic `Payment Tip` fact):

```text
Observed Tip      ≠     Estimated Cash Tip
(Payment Tip fact,      (a model output, carrying uncertainty,
 canonical Sales fact)   never presented as a recorded fact)
```

This epistemic distinction must be preserved everywhere Tips appear in Server Performance — in the Individual Performance Profile, in KPI Framework's Service Quality Evidence family, and in Coaching Model's economic-motivation estimates. **This module does not implement Estimated Cash Tips** (no estimation formula, model or calculation is built by TASK_SERVER_PERFORMANCE_001) — it only fixes the naming/epistemic requirement so a future implementation cannot silently blur the line.

---

## Table QR Survey (future evidence source)

A QR code associated with the table/service should allow the guest to answer a small number of highly targeted questions — short and purposeful, not a long-form survey. This document does not design the survey questions in detail (no existing documentation does so either); it documents the QR Survey as a **future Evidence source for Perceived Service Quality**.

Where technically possible in a future implementation, the survey response should be linked automatically to context already known to RF-One, so the guest never has to re-enter it:

```text
table identity
approximate service time
Dining Session (Dining Intelligence)
Clover consumption data
Server
```

This linkage is a Product/Runtime concern for a future task, not designed here.

---

## Refund/complaint-related signals

Where evidence genuinely exists (a `Refund` explicitly tied to a service complaint, rather than a Refund for an unrelated reason — `Sales/Restaurant Sales Model.md` §14a), a refund may be a Perceived Service Quality signal. RF-One does not assume every Refund reflects poor service — most Refunds have operational, not service-quality, causes — so this remains an Interpretation requiring context, never an automatic penalty (see [Server Performance.md](Server%20Performance.md), "Operational Discipline," for the parallel caution on Operational Discipline signals).

---

## Epistemic status

- A `Payment Tip` amount is **Observed** — a canonical Sales fact.
- Tip percentage, tips per hour, and any comparison "relative to comparable service context" are **Derived**.
- An `Estimated Cash Tip` is **Inferred** and must always carry that label and its uncertainty.
- "This guest was very satisfied" drawn from a tip amount alone is **Inferred** and weak; a QR Survey response naming satisfaction directly is a stronger, more direct **Observed** signal once that evidence source exists.

---

## Related documents

- [Server Performance.md](Server%20Performance.md)
- [KPI Framework.md](KPI%20Framework.md), "Tip-based performance"
- [../Tips/README.md](../Tips/README.md), [../Tips/Tip.md](../Tips/Tip.md), [../Tips/Tip Allocation.md](../Tips/Tip%20Allocation.md)
- [../Sales/Restaurant Sales Model.md](../Sales/Restaurant%20Sales%20Model.md) §14 "Tip," §14a "Refund"
- [Evidence Sources.md](Evidence%20Sources.md)
