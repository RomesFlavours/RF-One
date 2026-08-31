# Server Performance

**Version:** 1.0
**Status:** Approved
**Module:** Restaurant Domain / Server Performance
**Origin:** TASK_SERVER_PERFORMANCE_001

---

## Purpose

Server Performance does not exist primarily to rank Employees. Its purpose is:

> Understand each Server as an individual performer, identify strengths and unrealized opportunities, help that person improve, and learn which interventions actually work for that specific person.

RF-One does not pretend to know the private/personal reason a Server performed differently on a given day. Performance may be affected by innumerable personal or contextual factors RF-One cannot reliably know. RF-One therefore:

- does **not** infer unsupported psychological, health, relationship, hormonal, emotional or personal causes;
- observes performance Reality;
- learns patterns;
- intervenes only on what RF-One can actually influence (Brand guidance, timely information, coaching, training);
- measures what changes as a result.

This mirrors, for the Server role specifically, the general principle already stated in [Personnel Management/Performance.md](../../Personnel%20Management/Performance/Performance.md): Performance grounds Personnel Management in observed Reality rather than impression, reputation or prediction.

---

## The Performance Loop

Server Performance is not a static scorecard. It is a continuous learning cycle:

```text
Brand Expectations
  → Observation
    → Individual Performance Profile
      → Gap / Opportunity
        → Coaching / Training Intervention
          → New Observation
            → Outcome
              → Learning
```

Each stage reuses Core concepts already established for the rest of RF-One rather than inventing a parallel model:

- **Brand Expectations** — a Goal-shaped statement of what the Brand wants (see [Brand Expectation and Personal Baseline.md](Brand%20Expectation%20and%20Personal%20Baseline.md)).
- **Observation** — [Performance Evidence](../../Personnel%20Management/Performance/PerformanceEvidence.md), atomic and provenance-preserving, sourced per [Evidence Sources.md](Evidence%20Sources.md).
- **Individual Performance Profile** — the accumulated, multidimensional record RF-One keeps about one Server (see [Individual Performance Profile.md](Individual%20Performance%20Profile.md)).
- **Gap / Opportunity** — the Core `Reality Check` between expected and observed (`00 Core/ConceptualArchitecture/02_Desire_Goal_and_Reality_Check.md`), evaluated against both Brand Expectation and Personal Baseline simultaneously.
- **Coaching / Training Intervention** — Core `Decision`/`Action` (see [Coaching Model.md](Coaching%20Model.md)); delivered in real time by [Service Copilot](../Service%20Copilot/README.md) and/or structurally by Personnel Management's [Training](../../Personnel%20Management/Training/README.md).
- **New Observation → Outcome → Learning** — Core `Outcome`/`Learning` (`00 Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md`), reused without redefinition, closing the loop back into the Individual Performance Profile.

---

## Two simultaneous benchmarks

Every Server is evaluated against two distinct, non-substitutable reference systems at once — see [Brand Expectation and Personal Baseline.md](Brand%20Expectation%20and%20Personal%20Baseline.md) for the full definition:

- **Brand Expectation** — what the Restaurant/Brand considers desirable performance.
- **Personal Baseline** — how this specific Server normally performs.

Neither benchmark replaces the other. Their combination is what lets RF-One distinguish "below Brand standard but improving rapidly" from "stable high performer" from "persistent underperformance despite intervention," rather than collapsing every Server into one relative rank.

---

## Performance is multidimensional

Server Performance is never reduced to one score. At minimum, five dimensions are documented:

| Dimension | Question it answers | Documented in |
|---|---|---|
| **Productivity** | How much economic activity does the Server produce relative to time/opportunity available? | This document, below |
| **Quality of Sale** | Not just how much — *what* did the Server sell, relative to Brand commercial priorities? | [Quality of Sale.md](Quality%20of%20Sale.md) |
| **Opportunity Capture** | Of what was realistically sellable at this specific table, how much was captured? | [Opportunity Capture.md](Opportunity%20Capture.md) |
| **Operational Discipline** | Do discounts, voids, refunds and anomalies suggest the result was clean or masked? | This document, below |
| **Perceived Service Quality** | How did the guest experience the service? | [Perceived Service Quality.md](Perceived%20Service%20Quality.md) |

Performance Under Load ([Concurrent Service Load.md](Concurrent%20Service%20Load.md)) is not a sixth dimension in the same sense — it is the *context variable* that all five dimensions above should be evaluated as a curve against, not a single aggregate.

### Productivity

How much economic activity the Server produces relative to the time/opportunity available. Example: `Sales per Hour Worked`. Productivity is an important Measure but must never stand alone — a Server can be highly productive while systematically under-selling (see Quality of Sale) or productive only because concurrent load happens to be low (see Concurrent Service Load, "Low load also matters").

### Operational Discipline

Performance must consider operational signals where evidence exists: discounts, voids, refunds, payment problems, unusual adjustments, errors, other operational anomalies (Sales module concepts — `Sales/Restaurant Sales Model.md` §14a "Refund," §14b "Void / Cancellation," §18 "Discounts"). High Sales combined with excessive mistakes or uncontrolled discounting is not automatically high Performance.

RF-One does **not** assume causation from these signals — a void may reflect a genuine kitchen error, a guest change of mind, or a Server correcting their own mistake, and RF-One cannot reliably distinguish these without further evidence. These signals are evidence requiring interpretation ([Derived](Evidence%20Sources.md), sometimes [Inferred](Evidence%20Sources.md)), never an automatic penalty.

---

## Epistemic discipline (mandatory)

Every important Server Performance concept distinguishes, where appropriate, three epistemic states — the same discipline already established generically by [Personnel Management/Performance](../../Personnel%20Management/Performance/README.md) and by Core's [Epistemic Boundary](../../../00%20Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md), applied here to Restaurant evidence specifically. See [Evidence Sources.md](Evidence%20Sources.md) for the full model and worked examples (e.g. "Server sold wine on 8 of 20 qualifying tables" → 40% conversion → "may be weak at introducing wine to this archetype").

```text
Observed   directly evidenced (a transaction, a Payment Tip, a Shift, a QR Survey response)
Derived    deterministically calculated from Observed canonical facts (a rate, a ratio, a count)
Inferred   a model-generated conclusion carrying uncertainty (a tendency, a propensity, a recommendation)
```

RF-One never collapses these into each other, and never presents an Inferred conclusion with Observed-grade confidence.

---

## Multi-location Brand consistency (strategic objective)

A major purpose of Server Performance, feeding [Service Copilot](../Service%20Copilot/README.md), is:

> Reduce dependence on local training quality and make the Brand's service behavior recognizable across Locations.

Different Locations may have different Servers, different managers, different experience levels — but because RF-One supplies contextual Brand guidance during actual service and evaluates every Server against the same Brand Expectation, a multi-Location Brand can deliver a materially more consistent service model than one that depends solely on each Location's own training quality. This does not require identical Servers or identical management — it requires a shared, RF-One-mediated definition of what "good" means and a shared coaching channel. Compatible with Organization's `COMPLETE — MULTI-LOCATION PRODUCTION READY` model (`07 Tasks/Reports/TASK_ORGANIZATION_002_REPORT.md`): one canonical Employee identity may work at multiple Locations, and Server Performance segments by Location/context (via Employee Assignment and Shift/Table Service evidence) without duplicating the Employee.

---

## Relationship to Service Copilot

Server Performance and Service Copilot are **separate but closely connected capabilities**:

```text
Server Performance   → understands, over time, how this Server performs and where the opportunity is
Service Copilot      → uses that understanding to help the Server make the best next decision, right now
```

Server Performance does not deliver real-time guidance itself; Service Copilot consumes the Individual Performance Profile, Brand Expectation, and Dining Intelligence to do that (see [Service Copilot/README.md](../Service%20Copilot/README.md)).

## Relationship to Dining Intelligence

```text
Dining Intelligence   → what kind of consumption situation is this, and what opportunities appear to exist?
Server Performance    → how effectively is this Server working with the opportunities available?
Service Copilot       → what should help this Server next, and when?
```

Server Performance consumes Dining Session Profile and Customer Consumption Profile from [Dining Intelligence](../Dining%20Intelligence/README.md); it does not compute consumption patterns or correlations itself.

## Relationship to Training

```text
Server Performance   → identifies development need (a Gap against Brand Expectation or a decline from Personal Baseline)
Service Copilot and/or Personnel Management/Training → intervention
Server Performance   → observes outcome, closing the loop
```

Server Performance, Service Copilot and Training remain three distinct modules and are never merged (see [Personnel Management/Performance/README.md](../../Personnel%20Management/Performance/README.md), "Relationship to Training," which this specializes for the Server role).

## Relationship to Sales

Sales remains canonical factual Reality. Server Performance creates no competing Sales model. It consumes `Order`, `Order Item`, `quantity`, `Modifier`, `Discount`, `Payment`, `Tip`, `Refund`, `Void`/`Cancellation`, `Location`, `business_date` (all approved by `07 Tasks/Reports/TASK_SALES_002_REPORT.md`) and derives Performance Evidence/Measures from them — it never redefines these facts.

## Relationship to Organization

Server Performance uses canonical `Employee`, `Restaurant`, `Location`, `Restaurant Role`, `Employee Assignment` from Organization (`07 Tasks/Reports/TASK_ORGANIZATION_002_REPORT.md`). One Employee identity may span multiple Locations; Server Performance profiles may need Location/context segmentation (a Server's Winter Park performance vs. their Mount Dora performance) without duplicating the Employee — the same non-duplication principle Tips already applies (`Tips/README.md`).

---

## Related documents

- [README.md](README.md)
- [Brand Expectation and Personal Baseline.md](Brand%20Expectation%20and%20Personal%20Baseline.md)
- [Individual Performance Profile.md](Individual%20Performance%20Profile.md)
- [Evidence Sources.md](Evidence%20Sources.md)
- [../../Personnel Management/Performance/Performance.md](../../Personnel%20Management/Performance/Performance.md)
