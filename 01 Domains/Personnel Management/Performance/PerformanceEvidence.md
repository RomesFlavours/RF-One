# Performance Evidence

**Version:** 0.1
**Status:** Draft (initial canonical foundation)
**Module:** Domain / Personnel Management / Performance

---

## Purpose

**Performance Evidence** is information relevant to reasoning about [Performance](Performance.md): what a person actually produced, in Reality, within a role/context.

Performance Evidence is a Personnel-Management-specific application of the Core [Evidence](../../../00%20Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md) concept, in the same way [Candidate Evidence](../Selection/CandidateEvidence.md) already applies it to Selection.

---

## Atomicity principle

Performance Evidence should be preserved as **atomically as reasonably possible**. Distinct observations must not be prematurely collapsed into one score or one summary figure.

Illustrative examples of distinct, atomic Performance Evidence items in a Restaurant context:

- a transaction;
- an item sold;
- a quantity;
- a selling price;
- a time (when something occurred);
- the employee involved;
- the shift;
- a guest count;
- a service duration;
- a tip;
- a product/service mix observation;
- a customer statement;
- review text;
- a named-employee mention;
- an operational error;
- a quality event.

**This list is illustrative, not a schema.** It does not assume any particular POS or integration (no Clover-specific structure is implied), and it does not assume Restaurant is the only technical Domain that supplies Performance Evidence — another technical Domain supplies its own atomic observations in the same way.

---

## What every Performance Evidence item must conceptually preserve

Regardless of source, every Performance Evidence item should preserve:

- **source/provenance** — where it came from, and how it was obtained;
- **the underlying Observation** — what was actually observed or recorded, kept separate from any interpretation of it;
- **time/context** — when it occurred, and under what [Performance Context](PerformanceContext.md);
- **epistemic status** — whether it is being treated as Fact, Observation, Evidence, Belief, Assumption, Inference or Hypothesis (see [../../../00 Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md](../../../00%20Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md));
- **uncertainty** — how confident the Evidence should be treated as being;
- **attribution limitations** — see below.

This Domain does not prescribe a database schema or field list for these properties; it requires that they be conceptually preserved, not that they take any particular technical form.

---

## Direct observation vs. derived interpretation

A directly recorded Observation (e.g. "this transaction totaled $42 and was recorded under this employee at 7:14pm") is not the same thing as an interpretation of it (e.g. "this employee is good at upselling"). Performance Evidence is the former. Interpretation belongs to a [Performance Measure](PerformanceMeasure.md) or [Performance Indicator](PerformanceIndicator.md), or to a Hypothesis explicitly labeled as such, never silently folded into the Evidence record itself.

```text
Observation:   "Table 12 was served by this employee; the check total was $118;
                three of five ordered items were the day's higher-margin special."
Interpretation: "This employee is skilled at selling higher-margin items."
```

The Interpretation may be reasonable, but it is an Inference, and must be kept visibly separate from the Observation it was drawn from — the same discipline [CandidateEvidence.md](../Selection/CandidateEvidence.md) already applies to Selection.

**A derived measure is not the same thing as the underlying observations it was calculated from.** `Gross per hour` is a [Performance Measure](PerformanceMeasure.md) computed from transaction and time Evidence; it is not itself a Performance Evidence item. **A review rating is not the same thing as review text.** The rating (if one exists) is typically a derived or externally-computed summary; the text is the underlying Observation/statement, and may support a different or more nuanced reading than the rating alone. **A customer naming an employee is not the same thing as an inferred customer-satisfaction score.** The named mention is an atomic Observation; any satisfaction score inferred from it is a separate, derived Interpretation with its own uncertainty.

---

## Attribution limitations

Not every Performance Evidence item is cleanly attributable to a single person. A result may depend on a team, a shift, a kitchen and front-of-house combination, or conditions outside any individual's control (e.g. a supplier delay, understaffing, equipment failure).

Performance Evidence must represent attribution honestly:

- where attribution to a specific person is direct (e.g. a transaction recorded under a specific employee), it may be preserved as such;
- where attribution is inferred, partial, or shared, that must be represented as an Assumption or Inference, not silently treated as a Fact about the individual;
- where attribution cannot reasonably be determined, that is an Unknown, not a default assignment to whoever is most visible in the record.

Forcing every observation into a single-person attribution where the underlying Reality does not support it would misrepresent Performance rather than ground it.

---

## Cross-Domain evidence: Customer Feedback and Review

Customer Feedback and Review are separate transversal Domain candidates, outside Personnel Management (see [../README.md](../README.md), "Relationship to Customer Feedback and Review", and [../../Domain Architecture.md](../../Domain%20Architecture.md) §6). Performance does not own, move, or duplicate their concepts. It may, however, consume specific items from them as Performance Evidence when they are genuinely relevant to a person's Performance:

```text
Customer Feedback
  → customer explicitly names an employee
    → relevant Performance Evidence (a named mention, preserved atomically)
```

```text
Review
  → review text describes specific service behavior
    → relevant Performance Evidence (the described behavior, preserved atomically,
      separate from any overall rating the Review carries)
```

In both cases, only the specific relevant item becomes Performance Evidence — Performance does not import the entire Customer Feedback or Review record, and does not redefine what Customer Feedback or Review are.

---

## What Performance Evidence is not

- It is not a [Performance Measure](PerformanceMeasure.md) — a Measure is derived/calculated from Evidence.
- It is not a [Performance Indicator](PerformanceIndicator.md) — an Indicator is a Measure or observation currently considered relevant to a Goal.
- It is not automatically a Fact merely because it was recorded.
- It is not a personality judgment or moral judgment about the person.
- It is not a Selection prediction — see [Performance.md](Performance.md), "What Performance is not."

---

## Related concepts

- [Performance.md](Performance.md)
- [PerformanceMeasure.md](PerformanceMeasure.md)
- [PerformanceIndicator.md](PerformanceIndicator.md)
- [PerformanceContext.md](PerformanceContext.md)
- [../Selection/CandidateEvidence.md](../Selection/CandidateEvidence.md)
- [../../../00 Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md](../../../00%20Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md)
