# Opportunity Capture

**Version:** 1.0
**Status:** Approved
**Module:** Restaurant Domain / Server Performance
**Origin:** TASK_SERVER_PERFORMANCE_001

---

## Purpose

RF-One must estimate how effectively a Server converts *realistic* opportunities available at a table. The key concept is **not** generic upselling. It is:

> Opportunity Capture relative to the specific Dining Session.

A Server must never be penalized for failing to sell something that was not a realistic opportunity (a table that already declined wine, a table that is clearly finishing and unlikely to order dessert, a table with a stated dietary restriction). RF-One must progressively estimate, given what was known about a table *at that point in the service*, what was reasonably sellable — then compare Available Opportunity against Captured Opportunity.

```text
Available Opportunity   what was reasonably sellable, given the Dining Session as known so far
Captured Opportunity    what was actually sold from that Available Opportunity
Opportunity Capture     Captured Opportunity ÷ Available Opportunity  (Derived — see below)
```

---

## Where Available Opportunity comes from

Available Opportunity is **not** invented by this module. It is supplied by [Dining Intelligence](../Dining%20Intelligence/README.md)'s [Dining Session Profile](../Dining%20Intelligence/Dining%20Session%20Profile.md) — the evolving, per-session understanding of guest count, daypart, order sequence, food/drink categories already ordered, and other consumption evidence:

```text
Dining Intelligence   → Dining Session Profile → estimated Available Opportunity at this point
Server Performance    → compares actual sold items (Sales evidence) against that Available Opportunity
                       → Captured Opportunity, Opportunity Capture
```

This is the load-bearing reason Dining Intelligence must be a **separate, shared module** rather than logic buried inside Server Performance ([Dining Intelligence/README.md](../Dining%20Intelligence/README.md)): Available Opportunity is a property of the table/session, useful to Service Copilot, Training, Menu and Marketing alike — not a Server Performance-owned calculation.

---

## Progressive, not retrospective-only

"Given what was known about this table at this point in the service" means Available Opportunity is evaluated **as of a moment during the session**, not only after the fact. A dessert opportunity that existed at the start of a meal may no longer be realistically available once the table has asked for the check — Opportunity Capture must account for the moment, not assume every category was available at every point. This progressive evaluation is what [Service Copilot](../Service%20Copilot/README.md)'s "During Service" phase consumes in real time (see [Service Copilot/Service Copilot.md](../Service%20Copilot/Service%20Copilot.md)).

---

## Opportunity Capture at low load also matters

Low Concurrent Service Load does not excuse low Opportunity Capture — see [Concurrent Service Load.md](Concurrent%20Service%20Load.md), "Low load also matters." A quieter shift gives a Server *more* capacity for attentive service, product knowledge, targeted recommendation and guest engagement; RF-One should be able to learn whether a Server's Opportunity Capture actually improves when they have more available service capacity, which is itself a Coaching-relevant finding (see [Coaching Model.md](Coaching%20Model.md)).

---

## Available Opportunity value and missed value

Where a reasonable price/margin estimate exists for the missed opportunity (from the Commercial Catalog), Available Opportunity and Captured Opportunity may each carry an estimated dollar value, giving:

```text
opportunity value captured
opportunity value missed
```

These feed the economic-motivation half of coaching (see [Coaching Model.md](Coaching%20Model.md), "Personal Economic Benefit") — but remain **estimates**, never guaranteed income, and are explicitly labeled as such wherever surfaced.

---

## Epistemic status

- What was actually ordered is **Observed** (Sales evidence).
- Available Opportunity, even when derived from Dining Session Profile features, ultimately rests on a model estimate of "what was reasonably sellable" — this is **Inferred**, carrying uncertainty, never presented as a certain fact about what the table would have bought.
- Opportunity Capture (a ratio of Observed captured value against Inferred available value) inherits that uncertainty and must be presented accordingly.

---

## Related documents

- [Server Performance.md](Server%20Performance.md), [Quality of Sale.md](Quality%20of%20Sale.md)
- [Concurrent Service Load.md](Concurrent%20Service%20Load.md)
- [../Dining Intelligence/Dining Session Profile.md](../Dining%20Intelligence/Dining%20Session%20Profile.md)
- [../Service Copilot/Service Copilot.md](../Service%20Copilot/Service%20Copilot.md)
- [Coaching Model.md](Coaching%20Model.md)
