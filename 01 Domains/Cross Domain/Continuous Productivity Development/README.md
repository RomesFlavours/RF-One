# Continuous Productivity Development

**Version:** 0.2
**Status:** Draft (initial canonical foundation). Domain family: **Cross Domain** (`01 Domains/Cross Domain/Continuous Productivity Development/`) — a top-level, transversal Cross Domain, sibling of [Selection](../Selection/README.md), [Performance](../Performance/README.md), [Personnel Management](../Personnel%20Management/README.md), Taxation and Administration; not a module of any of them. See [../../Domain Architecture.md](../../Domain%20Architecture.md) §4 for the Cross Domain / Business Domain taxonomy this Domain follows.
**Domain:** Continuous Productivity Development (Cross Domain)
**Origin:** Follow-up to the Selection/Training/Guided-Operations documentation audit (2026-09-07); supersedes, conceptually, the placeholder previously held by the Training Cross Domain — see "Relationship to the former Training placeholder" below. That placeholder's folder has since been redefined as the sibling Cross Domain [Operational Knowledge](../Operational%20Knowledge/README.md) — a distinct concept (a retrievable information repository), not a continuation of Training's original "close a trainable gap" scope, which this Domain (Continuous Productivity Development) had already superseded.

> **Reframing note (2026-09-07):** this Domain's governing objective has been corrected. The primary objective is **not** human development itself — it is **continuous optimization of economic productivity**. Development, training, guidance, contextual information, workflow change, manager intervention and automation are all possible *interventions* toward that objective, none privileged over the others. See [CONTINUOUS_PRODUCTIVITY_DEVELOPMENT_001.md](CONTINUOUS_PRODUCTIVITY_DEVELOPMENT_001.md) §1-3 for the corrected model, and "Relationship to the Domain name" below for why the name itself may not be final.

---

## Purpose

RF-One continuously looks for opportunities to improve **economic productivity** — of people and of the operational systems they work within. This Domain is what governs that continuous search.

> Development is one possible response RF-One may choose. It is not the objective.

Conceptually, the governing loop is:

```text
Operational Data
  → Gap / Opportunity
    → Expected Economic Value
      → Best Intervention
        → Outcome
          → Learning
            → New Data
```

**Person development is only one of the interventions this loop may select** — see [CONTINUOUS_PRODUCTIVITY_DEVELOPMENT_001.md](CONTINUOUS_PRODUCTIVITY_DEVELOPMENT_001.md) §3 for the full list of possible interventions, which also includes doing nothing when no intervention is economically justified.

There is deliberately **no final state** this Domain models — not "training completed," not "development completed," not "permanently autonomous," not "fully optimized." Every person and every operational system remains potentially improvable, because context, products, workload, information, tools and opportunities change continuously. See [CONTINUOUS_PRODUCTIVITY_DEVELOPMENT_001.md](CONTINUOUS_PRODUCTIVITY_DEVELOPMENT_001.md) §2.

---

## Module boundary

Continuous Productivity Development answers **"where is there an economically meaningful productivity gap or opportunity, and what is the best available response"** — for a person, a role, or an operational system. Where the response concerns a specific person, it consumes:

- the Selection Output Baseline for the same persistent person (capabilities, Trainable Gaps, Guidability observations, uncertainty — see [Selection/SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md](../Selection/SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md));
- the required standard from the target technical Domain (e.g. Restaurant's service/technical standards);
- role/context;
- operational Performance Evidence — the primary source of the Operational Data the governing loop reasons from (see [Performance/README.md](../Performance/README.md));
- real-time guidance delivered through whatever channel a Business Domain provides (e.g. Restaurant's [Service Copilot](../../Business%20Domain/Restaurant/Service%20Copilot/README.md)) — one possible delivery channel for an intervention, not the objective itself.

It is distinct from Selection, Performance (sibling Cross Domains) and from Personnel Management's own modules, in the same relationship the former Training placeholder previously drew and this Domain now specializes further:

- [Workforce](../Personnel%20Management/Workforce/README.md) (Personnel Management module) answers "who currently occupies the role";
- [Selection](../Selection/README.md) (sibling Cross Domain) answers "who else is a credible alternative," and produces the Baseline this Domain begins from for a given person;
- [Performance](../Performance/README.md) (sibling Cross Domain) answers "what did the person or system actually produce" — the Operational Data this Domain's governing loop consumes;
- [Personnel Decisions](../Personnel%20Management/Personnel%20Decisions/README.md) (Personnel Management module) decides whether continued investment in a person is the economically justified response to observed Performance, and remains the exclusive, human-applied authority over retain/develop/move/replace.

---

## Relationship to Selection, Performance, Personnel Management, and real-time guidance

Continuous Productivity Development is triggered by Operational Data — which may originate from the Selection Output Baseline, from observed Performance, or from any other evidence source a Gap/Opportunity can be detected in — and its effect is measured through further Performance Evidence. It does not itself decide whether continued investment in a person is worth pursuing — that comparison belongs to [Personnel Decisions](../Personnel%20Management/Personnel%20Decisions/README.md). It is a sibling Cross Domain of Personnel Management, Selection and Performance, not a module of any of them — see [../../Domain Architecture.md](../../Domain%20Architecture.md) §4.

A Business Domain's real-time guidance capability (e.g. Restaurant's [Service Copilot](../../Business%20Domain/Restaurant/Service%20Copilot/README.md)) is **one possible delivery mechanism for one possible intervention** this Domain's governing loop may select — not a separate capability outside this Domain's scope, not something this Domain owns or redesigns, and not privileged over any other intervention. See [CONTINUOUS_PRODUCTIVITY_DEVELOPMENT_001.md](CONTINUOUS_PRODUCTIVITY_DEVELOPMENT_001.md) §12.

---

## Relationship to Core

Continuous Productivity Development will build on Core Process, Action, Outcome and Learning (see [../../../00 Core/Process.md](../../../00%20Core/Process.md), [../../../00 Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md](../../../00%20Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md)) and on the persistent person identity established by [PERSON_CONTINUITY_001.md](../PERSON_CONTINUITY_001.md), without redefining either.

---

## Relationship to technical Domains

Continuous Productivity Development consumes technical knowledge and required standards from whichever technical Domain the role belongs to (e.g. Restaurant wine-service or kitchen-process standards — see [../../Business Domain/Restaurant/README.md](../../Business%20Domain/Restaurant/README.md)); it does not duplicate that Domain's knowledge. Like Selection, it is potentially cross-industry — see [CONTINUOUS_PRODUCTIVITY_DEVELOPMENT_001.md](CONTINUOUS_PRODUCTIVITY_DEVELOPMENT_001.md) §16, "Cross Domain scope."

---

## Relationship to the former Training placeholder

`01 Domains/Cross Domain/Training/` originally held an explicit placeholder — "Domain boundary only, no concept modeling" — whose intended scope ("closing an evidenced, trainable gap" through learning) this Domain conceptually superseded, more fully after this reframing than at this Domain's first draft: this Domain's model is not centered on development or learning at all, but on economic productivity optimization, of which development is one possible instrument. See [CONTINUOUS_PRODUCTIVITY_DEVELOPMENT_001.md](CONTINUOUS_PRODUCTIVITY_DEVELOPMENT_001.md) §17 for the full treatment.

That folder has since been renamed and redefined as the sibling Cross Domain [Operational Knowledge](../Operational%20Knowledge/README.md) (RF-One's shared repository of retrievable operational information — see its own README). **Operational Knowledge is not a continuation of Training's original scope** — the "closing an evidenced gap" role Training's placeholder reserved was already, and remains, this Domain's (Continuous Productivity Development's) concern; Operational Knowledge is a genuinely different concept (a passive, retrievable information store, never an intervention-deciding or gap-closing mechanism) that happens to now occupy the Cross Domain slot Training's placeholder used to hold. The two Domains are independent siblings — see [Operational Knowledge/README.md](../Operational%20Knowledge/README.md), "Relationship to Continuous Productivity Development," for the boundary from Operational Knowledge's own side.

---

## Relationship to the Domain name

**"Continuous Productivity Development" is broader than human training** — it already was, at first draft, and the corrected model in this update makes it broader still, since development is now explicitly only one of several possible interventions rather than the organizing concept. The name itself, however, still foregrounds "Development," which may no longer accurately describe what actually governs this Domain: **economic productivity optimization**, applied to people and to operational systems, of which development is one instrument among several (guidance, contextual information, workflow change, reassignment, process redesign, automation, or no intervention at all).

**The name is kept unchanged for now.** Whether this Cross Domain should ultimately be renamed and reframed as something like `Economic Productivity Optimization` is recorded as an explicit open architectural decision — see [CONTINUOUS_PRODUCTIVITY_DEVELOPMENT_001.md](CONTINUOUS_PRODUCTIVITY_DEVELOPMENT_001.md) §19, decision 1. No folder or file rename is performed by this update.

---

## Deferred

Detailed modeling of Continuous Productivity Development entities, intervention types, readiness thresholds and business rules is deferred to future tasks. No database model, curriculum structure, competency taxonomy, or readiness-threshold formula is defined here — see [CONTINUOUS_PRODUCTIVITY_DEVELOPMENT_001.md](CONTINUOUS_PRODUCTIVITY_DEVELOPMENT_001.md) §18 for the full exclusion list and §19 for open decisions.

---

## Canonical documents in this Domain

| Document | Defines |
|---|---|
| [CONTINUOUS_PRODUCTIVITY_DEVELOPMENT_001.md](CONTINUOUS_PRODUCTIVITY_DEVELOPMENT_001.md) | The full concept specification: primary economic-productivity objective, no-end-state principle, intervention set (of which development is only one), economic decision principle, data-driven improvement, person-state continuity, Selection handoff, readiness, Copilot relationship, and relationship to Productivity Measurement and AI-Governed Rule Authoring. |

---

## Related documents

- [../PERSON_CONTINUITY_001.md](../PERSON_CONTINUITY_001.md)
- [../Selection/README.md](../Selection/README.md), [../Selection/SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md](../Selection/SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md)
- [../Performance/README.md](../Performance/README.md)
- [../AI_GOVERNED_RULE_AUTHORING_001.md](../AI_GOVERNED_RULE_AUTHORING_001.md)
- [../Operational Knowledge/README.md](../Operational%20Knowledge/README.md) — sibling Cross Domain, formerly the Training placeholder's folder; a distinct concept, see above
- [../../Business Domain/Restaurant/Server Performance/SERVER_PRODUCTIVITY_MEASUREMENT_001.md](../../Business%20Domain/Restaurant/Server%20Performance/SERVER_PRODUCTIVITY_MEASUREMENT_001.md)
- [../../Business Domain/Restaurant/Service Copilot/README.md](../../Business%20Domain/Restaurant/Service%20Copilot/README.md)
- [../../Domain Architecture.md](../../Domain%20Architecture.md) §4
