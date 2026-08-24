# Performance Indicator

**Version:** 0.1
**Status:** Draft (initial canonical foundation)
**Module:** Domain / Personnel Management / Performance

---

## Purpose

A **Performance Indicator** is a [Performance Measure](PerformanceMeasure.md), Observation, or signal currently considered relevant to evaluating Performance against a particular Goal and context.

An indicator is "key" only because of the current Decision/Goal/context that makes it relevant — **not because RF-One permanently labels any Measure as universally important.**

---

## Indicator relevance is derived, not assumed

A Performance Indicator becomes relevant as a function of:

```text
Goal
+ Brand
+ Role
+ Technical Domain
+ available Evidence
+ observed relationship with Outcomes
```

This is a contextual, ongoing determination, not a fixed classification. The same underlying [Performance Measure](PerformanceMeasure.md) (e.g. `gross per hour`) may be a highly relevant Indicator for one Goal (e.g. maximizing throughput during a high-volume period) and a poor or even misleading Indicator for another (e.g. a Goal focused on guest experience or margin discipline, where `contribution margin per guest` or a review-derived signal may matter more).

**RF-One does not canonize any Measure as a permanent Key Performance Indicator for a role.** RF-One may later learn that a Measure once treated as an Indicator has little actual relationship with the desired Outcome, or that a different Measure or Observation is more predictive or useful — this is itself an instance of [Learning](../../../00%20Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md) feeding back into future Indicator relevance, consistent with the Core's [Temporal Coherence](../../../00%20Core/ConceptualArchitecture/04_Temporal_Coherence_and_Evolution.md) principle that change is not automatically inconsistency.

**This document does not define a KPI-discovery algorithm.** It defines the concept of a Performance Indicator and the factors relevance depends on; how RF-One would actually derive or rank Indicators from those factors is future Product/Runtime/Intelligence Engine work, not designed here.

---

## Indicator ≠ Measure

```text
Performance Measure                       Performance Indicator
"a value derived/calculated from Evidence" ≠  "a Measure (or Observation/signal)
                                                currently considered relevant to a
                                                Goal/context"
```

Every Performance Indicator is grounded in a [Performance Measure](PerformanceMeasure.md) or in [Performance Evidence](PerformanceEvidence.md) directly (an Observation or signal need not always be aggregated into a Measure first — e.g. a single named customer mention could itself be treated as a relevant signal without further calculation). Not every Measure is currently an Indicator; most Measures that could be calculated from available Evidence are not currently relevant to any specific Goal, and remain ordinary Measures until a genuine relevance is established.

---

## No universal scalar score

**This Domain does not define a single overall Performance score.** A Performance Indicator set may include multiple, sometimes non-comparable, Indicators relevant to different aspects of a Goal (e.g. throughput, quality, guest experience). Collapsing them into one number would hide which Indicator is actually driving an evaluation and manufacture false precision over what is often genuinely uncertain or context-dependent — the same reasoning [FitAssessment.md](../Selection/FitAssessment.md) already applies to Selection's Fit dimensions. A Product or Runtime may choose to summarize Indicators numerically for its own purposes, but that summarization is not part of what this Domain defines, and must not replace the underlying set of distinct Indicators.

---

## What a Performance Indicator must expose, when used

Where a Performance Indicator is actually used to evaluate Performance, it should remain traceable to:

- the [Performance Measure(s)](PerformanceMeasure.md) or [Performance Evidence](PerformanceEvidence.md) it is grounded in;
- the Goal/context that made it relevant;
- the [Performance Context](PerformanceContext.md) under which the underlying Evidence was observed;
- its current uncertainty or known limitations (e.g. attribution limitations inherited from its underlying Evidence).

An Indicator used without this traceability is not distinguishable from an arbitrary number, and defeats the purpose of grounding Performance in Reality.

---

## Restaurant example (illustrative only)

```text
Goal A: maximize throughput during a high-volume launch period
  → relevant Indicators: transactions per hour, average service time

Goal B: protect margin discipline in an established, stable location
  → relevant Indicators: contribution margin per guest, selling mix toward
    higher-margin items

Goal C: strengthen guest experience and repeat business for a new location
  → relevant Indicators: named positive mentions in Customer Feedback/Review,
    repeat-guest indicators (where available)
```

The same person's raw Performance Evidence could support any of these Indicator sets. Which Indicators are actually "key" depends on which Goal is currently in force — none of Goal A, B, or C's Indicators are canonized here as universally important, and a different technical Domain would derive its own candidate Indicators from its own Measures and Evidence in the same way.

---

## What a Performance Indicator is not

- It is not a [Performance Measure](PerformanceMeasure.md) — every Indicator is grounded in a Measure or Evidence, but not every Measure is an Indicator.
- It is not a fixed or permanent KPI — see "Indicator relevance is derived, not assumed" above.
- It is not a universal scalar score.
- It is not itself a [Personnel Decision](../Personnel%20Decisions/README.md) — an Indicator informs that Decision but does not make it.

---

## Related concepts

- [Performance.md](Performance.md)
- [PerformanceEvidence.md](PerformanceEvidence.md)
- [PerformanceMeasure.md](PerformanceMeasure.md)
- [PerformanceContext.md](PerformanceContext.md)
- [../Selection/FitAssessment.md](../Selection/FitAssessment.md)
- [../../../00 Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md](../../../00%20Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md)
- [../../../00 Core/ConceptualArchitecture/04_Temporal_Coherence_and_Evolution.md](../../../00%20Core/ConceptualArchitecture/04_Temporal_Coherence_and_Evolution.md)
