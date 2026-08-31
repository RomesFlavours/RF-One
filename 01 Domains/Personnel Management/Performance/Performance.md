# Performance

**Version:** 0.1
**Status:** Draft (initial canonical foundation)
**Module:** Domain / Personnel Management / Performance

---

## Purpose

**Performance** is what a person actually produces in [Reality](../../../00%20Core/ConceptualArchitecture/01_Subject_and_Reality.md), within a given role and context.

> What is this person actually producing in Reality, in this role, under this context?

Performance is a Personnel-Management-specific application of Core `Reality`: the organization's Subject only ever has partial knowledge of what actually happened, and Performance is the discipline of grounding that knowledge in [Performance Evidence](PerformanceEvidence.md) rather than assumption, impression, or reputation.

---

## What Performance is not

Performance is not:

- a personality judgment;
- a moral judgment;
- a universal employee score;
- a fixed KPI dashboard;
- a résumé or Candidate Evidence assessment;
- a Selection prediction.

**Selection predicts. Performance observes.** [Selection](../Selection/README.md) reasons, before an Assignment exists, about how a candidate is *likely* to perform — an Inference or Hypothesis under the [Epistemic Boundary](../../../00%20Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md). Performance is what is *actually* observed to have happened afterward. Confusing the two — treating a Selection Fit Assessment as if it were already Performance, or treating a single Performance observation as if it retroactively proved a Selection judgment right or wrong — collapses a distinction this Domain must preserve.

---

## Observed results

Performance is built from [Performance Evidence](PerformanceEvidence.md): atomic, directly observed or recorded facts about what happened (see "Atomicity" in `PerformanceEvidence.md`). Performance itself is the accumulated body of that Evidence for a person, role and context — it is not a single number, and it does not exist as one summarized Fact.

From Performance Evidence, a Domain/Product/Runtime may calculate [Performance Measures](PerformanceMeasure.md) (e.g. a derived rate or ratio), and may treat some Measures as [Performance Indicators](PerformanceIndicator.md) when they are actually relevant to a current Goal. Performance itself does not privilege any one Measure or Indicator as canonical.

---

## Relationship to expectations, Goals and Outcomes

Performance should relate observed activity/results to expected [Outcomes](../../../00%20Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md) — but **more of a raw result does not automatically mean better Performance**. Whether a given result matters, and in which direction, depends on the Goal it is measured against, the Brand it operates under, and the technical Domain's own standards.

```text
Goal
  → expected Outcome for this role/context
    → observed Performance Evidence
      → (optionally) Performance Measure
        → (optionally, only if currently relevant) Performance Indicator
          → comparison with expected Outcome
```

Two people can produce equal raw sales and materially different economic value if their product mix or contribution margin differs — see the Restaurant example in §"Restaurant example" below and in [PerformanceIndicator.md](PerformanceIndicator.md). Performance must preserve enough distinct Evidence to support that comparison; it must not have already collapsed it into one figure before the comparison is made.

---

## Uncertainty

Performance must maintain the [Epistemic Boundary](../../../00%20Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md) throughout:

- a directly recorded Observation (e.g. a completed transaction) is not the same epistemic status as an Inference drawn from it (e.g. "this person is consistently strong at upselling");
- attribution of a result to a specific person may itself be an Assumption or Inference, not a Fact — see "Attribution limitations" in [PerformanceEvidence.md](PerformanceEvidence.md);
- absence of Performance Evidence for some period or dimension is an Unknown, not evidence of poor or absent Performance;
- Hypotheses about *why* a result occurred (e.g. "the slow service time was due to being understaffed") must remain visibly distinct from the observed result itself.

---

## Temporal evolution

Performance is not only a snapshot. RF-One must eventually be able to distinguish, over time and reusing Core [Temporal Coherence](../../../00%20Core/ConceptualArchitecture/04_Temporal_Coherence_and_Evolution.md) rather than a parallel framework:

- an **isolated event** — a single observation, not yet part of any established pattern;
- a **recurring pattern** — the same result recurring across comparable context;
- **improvement** — a trajectory moving toward the expected standard or Outcome;
- **decline** — a trajectory moving away from it;
- **stable performance** — consistent results across comparable context, neither improving nor declining;
- **context-specific variation** — a result that changes with context (e.g. shift, volume) rather than reflecting a genuine trend in either direction.

Distinguishing these is exactly the kind of trajectory reasoning Temporal Coherence already defines for Decisions and Outcomes generally (`04_Temporal_Coherence_and_Evolution.md` §1: "identifying drift, repeated patterns, ... effects that only become visible across time"). Performance does not invent a separate temporal model; it applies the same capability to accumulated Performance Evidence. A single Performance Evidence item is never, by itself, sufficient to conclude a pattern, an improvement or a decline — see [PerformanceContext.md](PerformanceContext.md) and [PerformanceIndicator.md](PerformanceIndicator.md) for how context and repeated observation bear on that conclusion.

---

## Context dependence

A raw Performance result may not be comparable to another without considering the [Performance Context](PerformanceContext.md) it occurred under (shift, volume, product mix, responsibilities, operational constraints, and other context the technical Domain determines to be relevant). Performance does not assume two people, or the same person at two different times, are directly comparable without that context being accounted for.

---

## Restaurant example (illustrative only)

```text
Server, Mount Dora

Observed (illustrative Performance Evidence):
  - Tuesday lunch shift: 14 transactions, $612 gross, 3 guests mentioned by name in
    post-visit feedback, average service time 9 minutes
  - Friday dinner shift: 22 transactions, $1,140 gross, 1 guest mentioned by name,
    average service time 14 minutes

Two servers with equal weekly gross sales may differ materially in contribution
margin if one consistently sells higher-margin items — equal raw sales does not
imply equal Performance relevant to a margin-focused Goal.

A server generating repeated positive named mentions may be producing business
value (repeat visits, reputation) that raw sales alone do not show.
```

Neither the margin difference nor the named-mention pattern is canonized here as a universal indicator of "good Performance" — see [PerformanceIndicator.md](PerformanceIndicator.md). The example exists only to show why Performance must retain multiple distinct observations rather than collapse them into a single score, and why the same reasoning structure applies to a Restaurant Manager, a Restaurant/Purchasing role, or a role in a different industry entirely — only the technical content of what is observed changes.

---

## Related concepts

- [PerformanceEvidence.md](PerformanceEvidence.md)
- [PerformanceMeasure.md](PerformanceMeasure.md)
- [PerformanceIndicator.md](PerformanceIndicator.md)
- [PerformanceContext.md](PerformanceContext.md)
- [../Selection/README.md](../Selection/README.md)
- [../Training/README.md](../Training/README.md)
- [../Personnel Decisions/README.md](../Personnel%20Decisions/README.md)
- [../../../00 Core/ConceptualArchitecture/01_Subject_and_Reality.md](../../../00%20Core/ConceptualArchitecture/01_Subject_and_Reality.md)
- [../../../00 Core/ConceptualArchitecture/04_Temporal_Coherence_and_Evolution.md](../../../00%20Core/ConceptualArchitecture/04_Temporal_Coherence_and_Evolution.md)
