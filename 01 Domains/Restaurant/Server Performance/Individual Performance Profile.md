# Individual Performance Profile

**Version:** 1.0
**Status:** Approved
**Module:** Restaurant Domain / Server Performance
**Origin:** TASK_SERVER_PERFORMANCE_001

---

## Purpose

The **Individual Performance Profile** is how RF-One represents what it has learned about one specific Server over time. It is the accumulation point the Performance Loop ([Server Performance.md](Server%20Performance.md)) writes back into after every Observation → Outcome → Learning cycle.

It is **not** a single score, a rank, or a static label assigned once. It is an evolving, multidimensional, evidence-grounded record.

---

## What the Profile holds

Structurally, the Profile is an accumulation of the same atomic Performance Evidence, Measures and Indicators already defined generically by [Personnel Management/Performance](../../Personnel%20Management/Performance/README.md), organized around this Server across:

```text
Dimensions        Productivity, Quality of Sale, Opportunity Capture, Operational Discipline,
                   Perceived Service Quality (Server Performance.md)

Benchmarks         current Personal Baseline (per dimension, per comparable context)
                    current Gap against Brand Expectation (per dimension)

Load behavior      the Server's observed Capacity / Acceleration / Resilience curve
                    (Concurrent Service Load.md)

Location context   segmented by Location/context where the Server works more than one
                    (Server Performance.md, "Relationship to Organization") — never duplicating
                    the Employee identity

Coaching history    interventions delivered, and their observed effect (Coaching Model.md,
                    "Coaching effectiveness")

Temporal trajectory isolated event / recurring pattern / improvement / decline / stable
                    performance / context-specific variation (reusing Personnel Management's
                    Temporal Coherence application — Performance.md, "Temporal evolution")
```

None of these fields is a single stored number — each is itself an accumulation of Observed, Derived and Inferred content ([Evidence Sources.md](Evidence%20Sources.md)), preserving the same atomicity principle [PerformanceEvidence.md](../../Personnel%20Management/Performance/PerformanceEvidence.md) already requires generically.

---

## One Employee, one Profile, Location-segmented

Consistent with Organization's canonical Employee identity (`07 Tasks/Reports/TASK_ORGANIZATION_002_REPORT.md`): a Server who works at both Winter Park and Mount Dora has **one** Individual Performance Profile, not two — but the Profile's dimensions, benchmarks and load curve are evaluated per Location/context where that distinction is meaningful (a Server's Personal Baseline at a high-volume Location is not assumed comparable to their Baseline at a quiet one without accounting for that context — see [Performance Context.md](../../Personnel%20Management/Performance/PerformanceContext.md)). The Profile aggregates across Locations only where doing so is meaningful (e.g. Brand-wide recognition), and keeps Location-specific views available where context genuinely differs.

---

## The Profile is never used to autonomously decide employment

The Individual Performance Profile is Reality-grounded evidence. It may eventually help management build the evidence history described in [Coaching Model.md](Coaching%20Model.md), "Underperformance / management evidence" — but it never itself decides retain/develop/move/replace. That Decision belongs exclusively to Personnel Management's [Personnel Decisions](../../Personnel%20Management/Personnel%20Decisions/README.md) module, applied by a human. See [Exclusions.md](Exclusions.md).

---

## Related documents

- [Server Performance.md](Server%20Performance.md), [README.md](README.md)
- [Brand Expectation and Personal Baseline.md](Brand%20Expectation%20and%20Personal%20Baseline.md)
- [Concurrent Service Load.md](Concurrent%20Service%20Load.md)
- [Coaching Model.md](Coaching%20Model.md)
- [../../Personnel Management/Performance/Performance.md](../../Personnel%20Management/Performance/Performance.md), "Temporal evolution"
