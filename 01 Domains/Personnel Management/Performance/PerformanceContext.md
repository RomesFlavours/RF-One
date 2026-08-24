# Performance Context

**Version:** 0.1
**Status:** Draft (initial canonical foundation)
**Module:** Domain / Personnel Management / Performance

---

## Purpose

**Performance Context** is the set of contextual conditions required to interpret [Performance Evidence](PerformanceEvidence.md) and [Performance Measures](PerformanceMeasure.md) fairly and meaningfully.

A raw Performance result is not automatically comparable to another without considering the context it occurred under. Performance Context is what makes that comparison meaningful, or reveals that a comparison should not be made at all without normalization.

---

## Comparison principle

**Do not assume raw person-to-person, or raw period-to-period, comparison is meaningful.** Two raw results that look numerically similar or different may reflect context rather than a genuine difference in Performance.

Illustrative examples where comparison requires contextual reasoning:

- morning vs. evening shift;
- high-volume vs. low-volume shift;
- different menu/product mix;
- different responsibilities within the same role title;
- different operational constraints (e.g. short-staffed vs. fully staffed);
- different tenure (someone in week two vs. someone in year two).

**This document does not design a normalization algorithm.** It documents only the conceptual requirement that context be preserved and accounted for before comparisons or trends are drawn — how any future Product/Runtime actually normalizes or adjusts for context is out of scope here.

---

## Illustrative context dimensions (not mandatory, not exhaustive)

Possible Performance Context dimensions include:

- role;
- Assignment (see [../Workforce/README.md](../Workforce/README.md) — Assignment is a Workforce dependency not yet modeled in depth);
- location;
- shift;
- day/time;
- workload;
- customer volume;
- available resources;
- product/service mix;
- tenure;
- operational constraints;
- business conditions.

**These are examples, not a mandatory universal schema.** Performance Context does not require every Performance Evidence item to carry every one of these fields. Which context dimensions actually matter for a given comparison is determined by the technical Domain the role belongs to, not fixed by this module — a Restaurant shift's relevant context (volume, menu mix) differs from what would be relevant in another technical Domain.

---

## Context affects comparability, not truth

Performance Context does not make a Performance Evidence item more or less true — the underlying Observation stands regardless of context. What context affects is **comparability**: whether two Evidence items, Measures, or apparent trends can be meaningfully placed side by side, or whether doing so without accounting for context would produce a misleading conclusion.

```text
Server A: $190 gross/hour, Friday dinner (high volume, full staffing)
Server B: $95 gross/hour, Tuesday lunch (low volume, short-staffed)

Without Performance Context, this looks like Server A materially outperforms
Server B. With Performance Context (volume, staffing, shift), the comparison
may not be meaningful at all without further reasoning — the raw Measures alone
do not support a conclusion about relative Performance.
```

---

## Relationship to temporal reasoning

Performance Context is also required to correctly apply Core [Temporal Coherence](../../../00%20Core/ConceptualArchitecture/04_Temporal_Coherence_and_Evolution.md) to Performance (see [Performance.md](Performance.md), "Temporal evolution"). A change in a Measure across two periods may reflect a genuine improvement or decline, or may simply reflect a change in context (e.g. a shift change, a menu change, a staffing change) — Performance Context is what lets that distinction be made rather than assumed.

---

## What Performance Context is not

- It is not [Performance Evidence](PerformanceEvidence.md) itself — it is the set of conditions under which Evidence was observed.
- It is not a mandatory universal schema every Domain or Product must populate identically.
- It is not a normalization algorithm — this document states the requirement to account for context, without designing how that adjustment is computed.
- It is not a justification for dismissing an unfavorable result, nor for inflating a favorable one — Performance Context supports fair interpretation, not a way to explain away Evidence.

---

## Related concepts

- [Performance.md](Performance.md)
- [PerformanceEvidence.md](PerformanceEvidence.md)
- [PerformanceMeasure.md](PerformanceMeasure.md)
- [PerformanceIndicator.md](PerformanceIndicator.md)
- [../Workforce/README.md](../Workforce/README.md)
- [../../../00 Core/ConceptualArchitecture/04_Temporal_Coherence_and_Evolution.md](../../../00%20Core/ConceptualArchitecture/04_Temporal_Coherence_and_Evolution.md)
