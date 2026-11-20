# Server Productivity Measurement

**Version:** 0.1
**Status:** Draft (initial canonical foundation)
**Module:** Restaurant Domain / Server Performance
**Origin:** Follow-up to the Selection/Training/Guided-Operations documentation audit (2026-09-07); builds on [Server Performance.md](Server%20Performance.md), [KPI Framework.md](KPI%20Framework.md), [Opportunity Capture.md](Opportunity%20Capture.md), [Quality of Sale.md](Quality%20of%20Sale.md), [Evidence Sources.md](Evidence%20Sources.md), [Concurrent Service Load.md](Concurrent%20Service%20Load.md), and the Cross Domain [Performance](../../../Cross%20Domain/Performance/README.md) model (`PerformanceMeasure.md`, `PerformanceIndicator.md`, `PerformanceContext.md`).

---

## 1. Purpose

Server Performance should evaluate how effectively a Server converts available operational opportunity, time, customer demand, and support into economic and service outcomes.

The objective is **not** to rank Servers against one another. The objective is to:

- understand economic productivity;
- identify genuine performance differences;
- identify economically meaningful gaps;
- support Training / continuous development ([Coaching Model.md](Coaching%20Model.md));
- support [Service Copilot](../Service%20Copilot/README.md);
- support management decisions (via [Personnel Decisions](../../../Cross%20Domain/Personnel%20Management/Personnel%20Decisions/README.md), never autonomously — see [Exclusions.md](Exclusions.md));
- measure improvement over time.

This document assembles a productivity-specific reading of concepts that already exist in this Domain (Productivity, Quality of Sale, Opportunity Capture, Concurrent Service Load — see [Server Performance.md](Server%20Performance.md), "Performance is multidimensional") and in the Cross Domain [Performance](../../../Cross%20Domain/Performance/README.md) model. It does not redefine any of them.

---

## 2. Economic productivity principle

> RF-One must measure server productivity primarily as an economic and operational outcome, not as an abstract personal score.

Productivity is **contextual and comparative**, not absolute. A Server's productivity should be evaluated relative to comparable people performing the same function under comparable operational conditions:

```text
Person
  + Function
    + Operational Context
      + Opportunity
        + Available Support
          → Economic / Operational Outcome
```

This is the Restaurant-Server specialization of the same reasoning [Performance.md](../../../Cross%20Domain/Performance/Performance.md) already establishes generically ("Relationship to expectations, Goals and Outcomes") and [PerformanceContext.md](../../../Cross%20Domain/Performance/PerformanceContext.md) already requires ("Comparison principle").

**No single universal formula or fixed score is defined by this document.** Consistent with [PerformanceIndicator.md](../../../Cross%20Domain/Performance/PerformanceIndicator.md), "No universal scalar score," and [KPI Framework.md](KPI%20Framework.md)'s existing mandatory reasoning order (ten questions, starting from "what behavior/outcome are we trying to understand," never from "what fields does Clover give us"), this document does not add a formula the KPI Framework has not already declined to fix.

---

## 3. Existing measurable evidence — families of Economic Productivity

Current RF-One/Clover operational data, mediated through Sales' canonical model (Order, Order Item, Payment, Tip, Refund, Void — see [Evidence Sources.md](Evidence%20Sources.md)), already makes several measurement families possible. These extend, rather than replace, the Productivity and Quality of Sale families already named in [KPI Framework.md](KPI%20Framework.md).

### A. Economic Output

Examples: gross / worked hour, gross / order, gross / guest, gross / item, tip / hour, tip / order, total economic contribution over a period.

### B. Selling Effectiveness

Examples: gross / guest, gross / item, items / guest, item/category attachment, dessert/beverage/appetizer/premium-item penetration, modifier/add-on behavior, and other opportunity-conversion measures derivable from Order Item evidence. These overlap substantially with the existing Quality of Sale family ([Quality of Sale.md](Quality%20of%20Sale.md)) — Selling Effectiveness is the economic-output framing of the same underlying evidence, not a competing model.

### C. Operational Throughput

Examples: guests / hour, orders / hour, items / hour, service time, workload handled over time. These extend the existing Productivity family ([Server Performance.md](Server%20Performance.md), "Productivity") and connect to [Concurrent Service Load.md](Concurrent%20Service%20Load.md) where throughput is evaluated as a function of simultaneous load.

### D. Customer Economic Response

Examples: tip / gross, tip / order, gratuity behavior.

**Customer tipping behavior is contextual evidence and must not automatically be interpreted as a pure quality score.** This restates, for this document's Economic Output framing, the discipline [KPI Framework.md](KPI%20Framework.md) already mandates ("Tip % is never equated directly with service quality — it is one signal among several") and [Perceived Service Quality.md](Perceived%20Service%20Quality.md) already establishes for tip evidence generally.

None of A–D is a finalized formula set. Exact time windows, aggregation methods, and rounding remain, as [KPI Framework.md](KPI%20Framework.md) already states, a future task's responsibility once real evidence volume exists to validate them.

---

## 4. Context adjustment

Raw results must not automatically be interpreted as personal performance. Performance may be affected by: shift/daypart, workload, table volume, party size, customer mix, order mix, assigned opportunity, service duration, operational conditions, available support, and other contextual factors already enumerated by [PerformanceContext.md](../../../Cross%20Domain/Performance/PerformanceContext.md).

RF-One should therefore evolve toward comparing actual outcome with expected outcome under comparable conditions:

```text
Actual Economic Outcome
  vs.
Expected Economic Outcome for Comparable Opportunity
```

The resulting difference may support an **Economic Performance Delta**, or an equivalent future concept, once a reliable way to estimate "expected outcome for comparable opportunity" exists.

**No exact statistical or predictive method is prescribed by this document.** This section only records the conceptual comparison RF-One should evolve toward — consistent with [PerformanceContext.md](../../../Cross%20Domain/Performance/PerformanceContext.md), which already states it "does not design a normalization algorithm."

---

## 5. Opportunity capture as a productivity lens

Productivity can also be understood through a Server's ability to convert available commercial opportunity — dessert, beverage, appetizer, premium-product, upsell/add-on, or other category/contextual opportunities. This document does not redefine [Opportunity Capture.md](Opportunity%20Capture.md); it records that, where evidence is sufficient, Opportunity Capture is itself one lens on Economic Productivity:

```text
available opportunity
  → captured opportunity
    → missed opportunity
      → estimated economic consequence
```

The "estimated economic consequence" step already exists conceptually as Opportunity Capture's "opportunity value captured / opportunity value missed" (`Opportunity Capture.md`, "Available Opportunity value and missed value") — remaining, as there, an **Inferred estimate**, never a guaranteed figure.

**No universal eligibility rule or formula is defined here.** This section only records that Opportunity Capture and Economic Productivity are related lenses on the same underlying evidence, not separate models that must be reconciled.

---

## 6. Relationship to Training / continuous productivity development

Performance measurements should be capable of identifying economically meaningful development gaps:

```text
Observed performance gap
  → estimated economic consequence
    → development/guidance intervention
      → subsequent operational evidence
        → measured productivity change
```

This is the same loop [Server Performance.md](Server%20Performance.md) already names ("The Performance Loop": Gap/Opportunity → Coaching/Training Intervention → New Observation → Outcome → Learning) and [Coaching Model.md](Coaching%20Model.md) already closes for coaching effectiveness specifically. This document adds nothing new to that loop — it records that Economic Productivity measures (§3–§5) are a candidate input to identifying the Gap that loop already reasons about, creating the bridge between Server Productivity Measurement and continuous Training/[Service Copilot](../Service%20Copilot/README.md) guidance.

**No intervention algorithm is defined here.**

---

## 7. Existing versus future measures

The measurement model must remain open. Measurement possibilities are classified into three categories; the architecture must not assume today's known KPIs define the final model.

### A. Currently available

Measures supportable from existing RF-One/Clover operational data — the families in §3, and the existing Productivity/Quality of Sale/Opportunity Capture/Operational Discipline families already named in [KPI Framework.md](KPI%20Framework.md).

### B. Future with additional evidence

Measures that become possible once new evidence sources exist, such as: manager interventions, Service Copilot prompts, accepted/ignored guidance, training events, operational mistakes not present in the POS, customer/service evidence (e.g. Guest QR Survey — [Perceived Service Quality.md](Perceived%20Service%20Quality.md)), and support intensity (§10). [Evidence Sources.md](Evidence%20Sources.md) already lists several of these as future evidence sources this Domain remains compatible with.

### C. Future discovery / invention

Measures or models that may emerge from new operational situations, additional Domain integrations, predictive analysis, experimentation, machine learning, AI-generated insight, or future RF-One inventions not yet conceived.

Category C is deliberately open-ended. This document does not, and must not, attempt to enumerate it — enumerating it would contradict its own purpose.

---

## 8. Evidence and epistemic rule

RF-One must distinguish, throughout every measure in §3–§7:

```text
Observed        directly evidenced (an Order Item, a Payment, a Tip, a Shift)
Derived          deterministically calculated from Observed facts (a rate, a ratio, a count)
Inferred         a model-generated conclusion carrying uncertainty (a tendency, an estimate,
                 a prediction, a Hypothesis)
```

This is the same three-state discipline already mandatory throughout this module — see [Evidence Sources.md](Evidence%20Sources.md), "Epistemic model: Observed / Derived / Inferred." **A derived or predictive productivity measure must never be represented as direct fact without preserving provenance and uncertainty.** An Economic Performance Delta (§4) or an estimated economic consequence (§5) is, by construction, Inferred, not Observed, and must be presented accordingly wherever surfaced — including inside a Coaching Model dollar estimate ([Coaching Model.md](Coaching%20Model.md), "Personal Economic Benefit") or a Service Copilot briefing.

---

## 9. Multi-dimensional performance

Server productivity is not reducible to one Performance score — consistent with [PerformanceIndicator.md](../../../Cross%20Domain/Performance/PerformanceIndicator.md), "No universal scalar score," and [Server Performance.md](Server%20Performance.md), "Performance is multidimensional." Productivity may be explained through multiple conceptual families such as:

```text
economic output              (§3.A)
selling effectiveness         (§3.B)
opportunity capture           (§5)
throughput                    (§3.C)
service efficiency
customer response             (§3.D)
support dependency            (§10)
improvement trajectory        (Server Performance.md, "Personal Development"; Performance.md,
                              "Temporal evolution")
```

**These are conceptual families, not a mandatory fixed taxonomy.** A given Server's productivity picture may use only the families evidence actually supports for their role/context — exactly as [FitAssessment.md](../../../Cross%20Domain/Selection/FitAssessment.md) already treats its own dimensions as non-mandatory.

---

## 10. Future support dependency

This document records compatibility with a future measurement of how much external guidance/support a person requires to produce a given outcome — examples may eventually include manager support, trainer support, Service Copilot support, contextual prompts, and escalation frequency.

**Support Dependency Decay mechanics are not defined here.** This section only fixes that Economic Productivity measurement (§3–§9) must remain structurally capable of being read *alongside* a future support-intensity signal, without redesigning the productivity measures themselves once that signal becomes available.

---

## 11. Cross-domain learning

Performance evidence produced under this model may later feed: Training, Service Copilot, Selection validation (evaluating whether a Selection prediction — including a [Trainable Gap](../../../Cross%20Domain/Selection/TrainableGap.md) or a Guidability observation, see [SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md](../../../Cross%20Domain/Selection/SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md) — was correct), person development history (anchored to the persistent person identity defined in [PERSON_CONTINUITY_001.md](../../../Cross%20Domain/PERSON_CONTINUITY_001.md)), and management decision support.

**This document only establishes compatibility with that learning loop.** No learning algorithm is designed here — see also §9 of `SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md` for the parallel loop already recorded on the Selection side.

---

## 12. Current KPI panel

The KPI panel already used operationally (Hours, Gross, Gross/Order, Gross/Item, Gross/Guest, Items/Guest, Guests/Hour, Guests/Table, Orders/Hour, Items/Hour, Service Time, Gross/Hour, Tip/Gross, Tip/Order, Tip/Hour, Gratuity, cash/order measures, morning/evening segmentation, and existing aggregate Performance/Selling/At-the-Table indicators) is an important **operational precursor** to this model. It is not, itself, canonicalized by this Domain as a repository document — this review did not locate it as a file inside `01 Domains/` or `03 Software/`; it exists as an operational artifact outside this Domain's current documentation, which is itself worth noting rather than assuming.

These measures should be preserved as **evidence candidates** — most map directly onto §3's families (e.g. Gross/Hour → Economic Output; Tip/Gross → Customer Economic Response; Guests/Hour, Orders/Hour, Items/Hour → Operational Throughput) — while future RF-One logic may reorganize, contextualize, replace, or supplement any composite indicator built from them, consistent with [PerformanceIndicator.md](../../../Cross%20Domain/Performance/PerformanceIndicator.md)'s existing principle that no Measure is a permanent Indicator. **This document does not reproduce the panel's actual values or thresholds.**

---

## 13. Non-prescription principle

> RF-One should implement what is currently known and measurable without pretending that the final performance model is already known.

The model must remain capable of absorbing: newly available evidence, new operational needs, new correlations, improved economic models, predictive measures, and genuinely new RF-One concepts. This document defines principles and evidence boundaries; it does not freeze innovation, and no future measure is precluded merely because it is not named in §3, §7, or §12.

---

## 14. Explicit exclusions

This document does **not** define:

- a final Performance score;
- fixed weighting between any measures;
- exact statistical normalization;
- an ML model;
- a prediction algorithm;
- a final Opportunity Capture formula;
- a final Economic Performance Delta formula;
- Support Dependency Decay formula;
- compensation/pay decisions;
- automatic employment decisions (remain [Personnel Decisions](../../../Cross%20Domain/Personnel%20Management/Personnel%20Decisions/README.md)' exclusive, human-applied authority — see [Individual Performance Profile.md](Individual%20Performance%20Profile.md), "The Profile is never used to autonomously decide employment");
- dashboard redesign;
- an implementation schema, database model, or migration.

---

## 15. Open decisions

The following are genuine, unresolved design/implementation decisions this document deliberately leaves open:

1. **How to define comparable operational context** for the §4 "Expected Economic Outcome for Comparable Opportunity" comparison — which Performance Context dimensions (§4; `PerformanceContext.md`) are load-bearing enough to require matching before two outcomes are compared.
2. **How to estimate expected economic outcome** under comparable context — statistical, predictive, or another method; not decided here.
3. **Which opportunity types (§5) are materially useful** to track as distinct categories, versus which add measurement overhead without economically meaningful signal.
4. **Which current composite KPIs (§12) remain useful** once reorganized under this model's families, versus which should be retired or replaced.
5. **Which future evidence sources (§7.B) should actually be collected first**, and in what priority, once the current model is in operational use.
6. **When predictive/Inferred estimates (§8) are reliable enough for operational use** — e.g. surfaced to a Server via Service Copilot or used in a Coaching Model dollar estimate — versus when they remain internal-reasoning-only.

---

## Related documents

- [Server Performance.md](Server%20Performance.md), [KPI Framework.md](KPI%20Framework.md), [Quality of Sale.md](Quality%20of%20Sale.md), [Opportunity Capture.md](Opportunity%20Capture.md), [Concurrent Service Load.md](Concurrent%20Service%20Load.md), [Evidence Sources.md](Evidence%20Sources.md), [Individual Performance Profile.md](Individual%20Performance%20Profile.md), [Coaching Model.md](Coaching%20Model.md), [Exclusions.md](Exclusions.md)
- [../../../Cross Domain/Performance/README.md](../../../Cross%20Domain/Performance/README.md), [Performance.md](../../../Cross%20Domain/Performance/Performance.md), [PerformanceMeasure.md](../../../Cross%20Domain/Performance/PerformanceMeasure.md), [PerformanceIndicator.md](../../../Cross%20Domain/Performance/PerformanceIndicator.md), [PerformanceContext.md](../../../Cross%20Domain/Performance/PerformanceContext.md)
- [../Service Copilot/README.md](../Service%20Copilot/README.md)
- [../../../Cross Domain/PERSON_CONTINUITY_001.md](../../../Cross%20Domain/PERSON_CONTINUITY_001.md)
- [../../../Cross Domain/Selection/SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md](../../../Cross%20Domain/Selection/SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md)
- [../../Domain Architecture.md](../../../Domain%20Architecture.md) §8, "KPI discovery principle"
