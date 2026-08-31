# Brand Expectation and Personal Baseline

**Version:** 1.0
**Status:** Approved
**Module:** Restaurant Domain / Server Performance
**Origin:** TASK_SERVER_PERFORMANCE_001

---

## Purpose

Every Server is evaluated using two distinct reference systems simultaneously. Neither replaces the other; both are required to interpret the same observed result correctly.

```text
Brand Expectation    what the Restaurant/Brand considers desirable performance
Personal Baseline     how this specific Server normally performs
```

This specializes, for the Server role, the generic [Performance Context](../../Personnel%20Management/Performance/PerformanceContext.md) comparison principle: "do not assume raw person-to-person, or raw period-to-period, comparison is meaningful."

---

## A. Brand Expectation

What the Restaurant/Brand considers desirable Server performance. Illustrative dimensions (not a closed list, not prescriptive of any specific Brand's actual configuration):

- desired product mix (which categories/items the Brand wants sold, and in what proportion);
- service behaviors (how the Brand wants guests greeted, paced, closed);
- strategic products (items the Brand currently wants emphasized — a promotion, a high-margin dish, a seasonal item);
- sales priorities (e.g. emphasize appetizers this quarter, protect wine margin, grow dessert attach);
- acceptable operational discipline thresholds (e.g. an acceptable discount rate range);
- desired guest experience (pace, tone, attentiveness).

Brand Expectation is **Brand-configurable**, not canonical RF-One ontology (see [Server Performance/README.md](README.md), "Relationship to other Domains," and `01 Domains/Restaurant/Roadmap.md` §3). Rome's Flavours' specific strategic products, thresholds and priorities are not hard-coded here or anywhere in this module — Rome's Flavours becomes the first *configuration instance* of this concept, not a source of canonical Server Performance rules. The eventual configuration surface belongs to a future Product/Runtime task; this document only fixes that Brand Expectation must be explicit, Brand-owned, and temporally versioned (a Brand may change its priorities, and historical evaluation must use the priorities in force at the time, mirroring `Payroll/Compensation Terms.md`'s temporal-correctness pattern and `EmployeeCompensationTerm`'s never-overwritten history).

Brand Expectation draws on the Commercial Catalog's existing structure (`Commercial Catalog/README.md`: Item, Item Category, Item Group, Brand, Modifier, Modifier Group) as the vocabulary for "which products" — it does not invent a parallel product taxonomy.

---

## B. Personal Baseline

How this specific Server normally performs — an individual, temporal reference derived from that Server's own accumulated Performance Evidence, never from a peer or team average (peer comparison is a separate concept — see [Coaching Model.md](Coaching%20Model.md), "Gamification / comparison").

Personal Baseline exists so RF-One can distinguish cases such as:

- below Brand standard but improving rapidly;
- above team average but deteriorating personally;
- stable high performer;
- low performer responding positively to coaching;
- persistent underperformance despite intervention.

None of these distinctions is recoverable from Brand Expectation alone — a Server permanently below Brand Expectation but steadily closing the gap is a materially different situation from one stable far below it, and Personal Baseline is what makes that difference visible.

### Baseline is not a single number

Consistent with [Performance.md](../../Personnel%20Management/Performance/Performance.md), "Temporal evolution," a Personal Baseline is a Server's typical range/distribution of results under comparable [Performance Context](../../Personnel%20Management/Performance/PerformanceContext.md) (comparable Concurrent Service Load, comparable daypart, comparable tenure stage) — not one fixed number the Server is permanently compared against. A Baseline established during a Server's first month is not assumed valid for evaluating their second year; Personal Baseline evolves as Temporal Coherence (`00 Core/ConceptualArchitecture/04_Temporal_Coherence_and_Evolution.md`) is applied to the accumulating Individual Performance Profile.

---

## How the two benchmarks combine

```text
Observed result
  → compare against Brand Expectation   → Gap or alignment relative to what the Brand wants
  → compare against Personal Baseline   → improvement, decline, or stability relative to this Server's own history

Both comparisons feed the same Gap/Opportunity stage of the Performance Loop (Server Performance.md).
```

A result that is below Brand Expectation but represents a genuine improvement over Personal Baseline is coached differently (recognition + continued development) than a result that is below both Brand Expectation and this Server's own Baseline (a genuine, un-improving Gap). Neither benchmark alone can distinguish these — see [Coaching Model.md](Coaching%20Model.md).

---

## What this document does not do

- It does not specify Rome's Flavours' (or any Brand's) actual strategic products, thresholds or priorities — that is Brand configuration, entered later.
- It does not define a normalization algorithm for comparing across Concurrent Service Load, daypart, or tenure — see [Performance Context.md](../../Personnel%20Management/Performance/PerformanceContext.md), "This document does not design a normalization algorithm," which applies unchanged here.
- It does not define how Personal Baseline is statistically computed (window length, outlier handling, minimum sample size) — that is future Product/Runtime/Intelligence Engine work, not Domain modeling.

---

## Related documents

- [README.md](README.md), [Server Performance.md](Server%20Performance.md)
- [Individual Performance Profile.md](Individual%20Performance%20Profile.md)
- [../../Personnel Management/Performance/PerformanceContext.md](../../Personnel%20Management/Performance/PerformanceContext.md)
- [../Commercial Catalog/README.md](../Commercial%20Catalog/README.md)
