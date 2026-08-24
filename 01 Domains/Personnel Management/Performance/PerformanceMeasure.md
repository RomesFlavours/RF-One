# Performance Measure

**Version:** 0.1
**Status:** Draft (initial canonical foundation)
**Module:** Domain / Personnel Management / Performance

---

## Purpose

A **Performance Measure** is a value calculated or observed from one or more [Performance Evidence](PerformanceEvidence.md) items — a derived aggregation, rate, ratio, or count, rather than an atomic Observation itself.

A Measure is a way of summarizing a set of Evidence for a specific purpose. It is not itself a judgment of whether the summarized result is good, expected, or relevant — that is the role of a [Performance Indicator](PerformanceIndicator.md).

---

## Measure ≠ Evidence

```text
Performance Evidence                     Performance Measure
"what was directly observed"       ≠     "a value derived/calculated from Evidence"
```

A Measure depends on Evidence existing first; it cannot exist without the underlying Evidence it summarizes, and it is only as reliable as that Evidence's own epistemic status and completeness (see [PerformanceEvidence.md](PerformanceEvidence.md)).

---

## A Measure is not automatically a Key Performance Indicator

**Every Measure this Domain could define is a candidate, not a KPI by default.** A Measure becomes a [Performance Indicator](PerformanceIndicator.md) only when it is actually considered relevant to a current Goal, Brand, role, technical Domain, available Evidence, or observed relationship with Outcomes — see [PerformanceIndicator.md](PerformanceIndicator.md). This document does not canonize any Measure as permanently important, and does not prescribe formulas globally: how a specific Measure is calculated (units, time window, rounding, aggregation method) is a Domain/Product/Runtime decision, made when and where the Measure is actually needed.

---

## Illustrative examples (not prescriptive, not exhaustive)

```text
gross per hour              = gross sales (Evidence) ÷ hours worked (Evidence)
contribution margin per guest = contribution margin (derived from item-level Evidence)
                                 ÷ guest count (Evidence)
items sold per shift         = count of item-sold Evidence within a shift's time window
average service time         = mean of service-duration Evidence within a period
```

These are illustrative only. They are not a mandatory list, not a required formula set, and not restaurant-exclusive — a different technical Domain would derive its own Measures from its own Evidence in the same way.

---

## Plurality of Measures

Multiple, sometimes competing, Measures can legitimately be derived from the same underlying Evidence set. For example, `gross per hour` and `contribution margin per hour` may diverge for the same person if their product mix differs — neither is "the" correct Measure; each summarizes the Evidence differently, for a different purpose. Performance does not force a single canonical Measure per role or per Evidence set.

---

## What a Performance Measure is not

- It is not [Performance Evidence](PerformanceEvidence.md) — it is derived from Evidence, not an atomic Observation itself.
- It is not automatically a [Performance Indicator](PerformanceIndicator.md) — relevance to a Goal must be established separately.
- It is not automatically comparable across [Performance Context](PerformanceContext.md) — see "Comparison principle" in [PerformanceContext.md](PerformanceContext.md). A Measure computed under one context (e.g. a high-volume Friday dinner shift) is not directly comparable to the same Measure computed under a materially different context (e.g. a slow Tuesday lunch shift) without accounting for that context.
- It is not automatically a Fact free of uncertainty: a Measure inherits whatever uncertainty, Assumptions, or attribution limitations exist in the Evidence it was calculated from (see "Attribution limitations" in [PerformanceEvidence.md](PerformanceEvidence.md)).

---

## Restaurant example (illustrative only)

```text
Server, Mount Dora — Friday dinner shift

Evidence:  22 transactions; $1,140 gross; itemized selling mix; 14-minute average
           service time; hours worked = 6

Measures derived from that Evidence:
  gross per hour                = $1,140 ÷ 6 = $190/hour
  transactions per hour         = 22 ÷ 6 ≈ 3.7/hour
  average service time          = 14 minutes (already a Measure, aggregated from
                                   per-table Evidence)

None of these Measures is, by itself, a statement that this was a "good" shift —
that judgment depends on which Measure, if any, is currently a relevant Indicator
for the Goal in question (see PerformanceIndicator.md).
```

---

## Related concepts

- [Performance.md](Performance.md)
- [PerformanceEvidence.md](PerformanceEvidence.md)
- [PerformanceIndicator.md](PerformanceIndicator.md)
- [PerformanceContext.md](PerformanceContext.md)
