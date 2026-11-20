# Operational Knowledge

**Version:** 1.0
**Status:** Approved (Domain boundary and core concept — initial concept modeling; detailed data model deferred). Domain family: **Cross Domain** (`01 Domains/Cross Domain/Operational Knowledge/`).
**Domain:** Operational Knowledge (Cross Domain)
**Origin:** Replaces the former placeholder Cross Domain `Training` (`01 Domains/Cross Domain/Training/`, "Domain boundary only — no concept modeling"). This is a redefinition, not a rename-in-place: Operational Knowledge is a genuinely different concept occupying this Cross Domain slot, not a continuation of Training's prior definition under a new name — see "Relationship to Continuous Productivity Development" below, and the "Update — Training Service boundary" note there for the 2026-09-11 decision on where Training's original scope now lives.
**Recovery:** Reconstructed 2026-09-12 after uncommitted working-tree edits to this document were accidentally lost. Only the "Update — Training Service boundary" paragraph below and the Related-documents entry have been added; the rest of this document's surviving content, including its own "passive, retrievable" boundary, is unchanged. No lost version number is asserted; the Version above is unchanged from the last committed state.

---

## Purpose

**Operational Knowledge is the shared RF-One repository of operational information that can be retrieved when useful.**

It is a passive, retrievable resource — not an active process that changes a person's state:

- it does **not** train people by itself;
- it does **not** assume that information was learned;
- it does **not** test, assess, certify, or verify retention.

Operational Knowledge stores and organizes reusable operational knowledge so that any RF-One function — most notably [Copilot](#relationship-to-copilot) — can retrieve exactly the piece of information that is useful in a given moment, rather than requiring a person to have already memorized it.

---

## Operational Knowledge Pills

The atomic, reusable unit of content is the **Operational Knowledge Pill**: a small, contextual piece of information that can be retrieved independently of the others.

A Pill is deliberately small and self-contained — not a course, module, or curriculum. Illustrative, non-exhaustive examples:

```text
product knowledge
menu/product details
service standards
procedures
situational guidance
customer-handling information
operational reminders
```

A Pill's defining properties:

- **atomic** — one piece of information, retrievable on its own, not a sequence of steps that must be consumed in order;
- **contextual** — meaningful in relation to a specific operational situation, role, or moment, not a general-purpose article;
- **retrievable** — designed to be looked up by a function such as Copilot, not to be read cover-to-cover as a course.

No curriculum, course structure, module sequence, learning path, or completion state is defined for a Pill or for any collection of Pills — see "What this Domain does not do" below.

---

## Domain boundary

Operational Knowledge answers **"what information already exists that could help here"**. It consumes:

- operational content authored or curated by a technical Domain (e.g. Restaurant's menu, service standards, or procedures);
- situational/contextual metadata that lets a Pill be matched to the moment it is useful for (role, activity, timing);

and it is retrieved by:

- [Copilot](#relationship-to-copilot) (or an equivalent real-time capability in another Business Domain), before or during an operational activity.

It is distinct from Continuous Productivity Development (sibling Cross Domain) and from Selection (sibling Cross Domain):

- [Continuous Productivity Development](../Continuous%20Productivity%20Development/README.md) (sibling Cross Domain) identifies gaps/opportunities, estimates their economic value, decides the best intervention, measures the outcome, and learns from it — Operational Knowledge is one resource an intervention may draw on (e.g. surfacing a Pill through Copilot), but Operational Knowledge itself never decides that an intervention is needed, and never measures whether one worked;
- [Selection](../Selection/README.md) (sibling Cross Domain) answers "who else is a credible alternative" and evaluates a person's existing capability before they are hired — Operational Knowledge plays no role in that evaluation;
- [Performance](../Performance/README.md) (sibling Cross Domain) answers "what did the person actually produce" — Operational Knowledge does not measure or evidence performance.

---

## Relationship to Copilot

A Business Domain's real-time operational-guidance capability (e.g. Restaurant's [Service Copilot](../../Business%20Domain/Restaurant/Service%20Copilot/README.md)) may retrieve Operational Knowledge Pills:

- **before an operational activity**, when useful preparation/context is needed;
- **during execution**, when contextual information can help the user perform correctly in the moment.

**Copilot operational guidance is not Training.** Retrieving and surfacing a Pill is real-time operational assistance — it never implies a lesson was delivered, a module was completed, or that the information is now "known" by the person who received it. The next time the same situation arises, the same Pill may be retrieved again; Operational Knowledge does not track whether it needs to be.

**No runtime Domain ownership is merged by this document.** Copilot (or an equivalent capability in another Business Domain) remains owned by its own Domain, with its own inputs, boundaries and exclusions. This document only records that Copilot is a consumer of Operational Knowledge Pills, not that Operational Knowledge governs Copilot's own logic, timing, or channel — see [Continuous Productivity Development/README.md](../Continuous%20Productivity%20Development/README.md), "Copilot relationship," for how Copilot's delivery of an intervention is governed.

---

## Relationship to Continuous Productivity Development

Continuous Productivity Development ([README.md](../Continuous%20Productivity%20Development/README.md)) remains an independent sibling Cross Domain. Its role is to identify gaps/opportunities, estimate their expected economic value, determine the best available intervention, measure the outcome, and learn from the result.

Operational Knowledge does not perform any part of that loop. It is, at most, a resource an intervention selected by Continuous Productivity Development may use — e.g. "surface this Pill through Copilot at this moment" is one possible intervention shape — but:

- Operational Knowledge never decides that a gap or opportunity exists;
- Operational Knowledge never estimates economic value;
- Operational Knowledge never measures whether retrieving a Pill produced an improvement.

**Repeated use of a Pill, or repeated Copilot guidance, may naturally lead a person to learn over time — but that learning is an outcome Continuous Productivity Development may eventually observe and measure (as Operational Data feeding its own loop — see [CONTINUOUS_PRODUCTIVITY_DEVELOPMENT_001.md](../Continuous%20Productivity%20Development/CONTINUOUS_PRODUCTIVITY_DEVELOPMENT_001.md) §1), never a responsibility Operational Knowledge itself carries.**

**Update — Training Service boundary (2026-09-11):** [TRAINING_SERVICE_001.md](../TRAINING_SERVICE_001.md) names **Training** — an internal RF-One service, not a Cross Domain — as owner of the training-cycle governance (pill catalog linkage to needs, thresholds, gap/priority, path assignment). For that purpose, Operational Knowledge is **a component internal to Training** (see TRAINING_SERVICE_001.md §3). This changes nothing about the boundary already stated above: Operational Knowledge still never decides an intervention, sets a threshold, or measures an outcome. It means Training, rather than Continuous Productivity Development, is the party that governs how Pills are catalogued and linked to training needs.

---

## Relationship to Selection

[Selection](../Selection/README.md) remains independent. A person's existing knowledge/capabilities (evidenced at Selection time — see [SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md](../Selection/SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md)) and the current operational threshold a Business Domain or Organization defines determine how much real-time assistance a person may need. Operational Knowledge does not evaluate a person's capability, and does not determine that threshold — it only makes retrievable information available when a Domain's own logic (e.g. Copilot's) decides to retrieve it.

---

## What this Domain does not do

Consistent with the core definition above, Operational Knowledge deliberately excludes:

- mandatory learning paths or curricula;
- a notion of "training completion";
- knowledge verification, testing, assessment, or certification;
- tracking whether a person has "learned" a Pill's content;
- deciding that an intervention is needed, or selecting which intervention to use (Continuous Productivity Development's role);
- measuring outcomes or economic value (Continuous Productivity Development's role);
- evaluating a person's existing capability (Selection's role).

None of these are permanently prohibited as a future, separate capability — they are simply not part of Operational Knowledge as defined here, and would need to be explicitly documented elsewhere (e.g. as a future extension of Continuous Productivity Development, or a distinct future Domain) before RF-One treats them as real.

---

## Relationship to Core

Operational Knowledge will build on Core concepts (Process, Resource, and the Epistemic Boundary distinguishing Fact/Evidence/Belief — see [../../../00 Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md](../../../00%20Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md)) without redefining them.

---

## Relationship to technical Domains

Operational Knowledge consumes operational content authored by whichever technical Domain owns it (e.g. Restaurant's menu, wine list, or service-standard content — see [../../Business Domain/Restaurant/README.md](../../Business%20Domain/Restaurant/README.md)); it does not author or own that content itself, and does not duplicate a technical Domain's own knowledge. Like Selection and Continuous Productivity Development, it is potentially cross-industry — a Pill's shape (atomic, contextual, retrievable) does not depend on any one industry.

---

## Deferred

Detailed modeling of Operational Knowledge Pill data structure, authoring/curation workflow, retrieval/matching mechanism, and versioning is deferred to a future task. No database model, retrieval algorithm, or content-authoring UI is defined here.

---

## Related documents

- [../../Domain Architecture.md](../../Domain%20Architecture.md) §4
- [../Continuous Productivity Development/README.md](../Continuous%20Productivity%20Development/README.md), [../Continuous Productivity Development/CONTINUOUS_PRODUCTIVITY_DEVELOPMENT_001.md](../Continuous%20Productivity%20Development/CONTINUOUS_PRODUCTIVITY_DEVELOPMENT_001.md)
- [../TRAINING_SERVICE_001.md](../TRAINING_SERVICE_001.md) — names Training as the internal service Operational Knowledge is a component of
- [../Selection/README.md](../Selection/README.md), [../Selection/SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md](../Selection/SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md), [../Selection/SELECTION_PILL_ASSESSMENT_AND_TRAINING_READINESS_001.md](../Selection/SELECTION_PILL_ASSESSMENT_AND_TRAINING_READINESS_001.md)
- [../Performance/README.md](../Performance/README.md)
- [../../Business Domain/Restaurant/Service Copilot/README.md](../../Business%20Domain/Restaurant/Service%20Copilot/README.md)
