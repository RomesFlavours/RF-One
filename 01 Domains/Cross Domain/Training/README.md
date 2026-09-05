# Training

**Version:** 0.2
**Status:** Placeholder (Domain boundary only — no concept modeling). Domain family: **Cross Domain** (`01 Domains/Cross Domain/Training/`) — extracted from Personnel Management, not one of its modules; see [../../Domain Architecture.md](../../Domain%20Architecture.md) §4.
**Domain:** Training (Cross Domain)

---

## Purpose

Training attempts to close evidenced gaps between a person's current capability and a role's required standard, when doing so is operationally and economically justified.

---

## Module boundary

Training answers **"how do we close an evidenced, trainable gap"**. It consumes:

- the required standard from the target technical Domain;
- the observed/assessed gap (see [../Selection/TrainableGap.md](../Selection/TrainableGap.md) for the currently drawn Selection/Training boundary);
- role/context;
- learning methods;
- later [Performance](../Performance/README.md) evidence, to close the feedback loop.

It is distinct from Selection, Performance (sibling Cross Domains) and from Personnel Management's own modules:

- [Workforce](../Personnel%20Management/Workforce/README.md) (Personnel Management module) answers "who currently occupies the role";
- [Selection](../Selection/README.md) (sibling Cross Domain) answers "who else is a credible alternative" and identifies the gap Training may address;
- [Performance](../Performance/README.md) (sibling Cross Domain) answers "what did the person actually produce" — including after Training;
- [Personnel Decisions](../Personnel%20Management/Personnel%20Decisions/README.md) (Personnel Management module) decides whether Training is the economically justified response to observed Performance.

---

## Relationship to Selection, Performance and Personnel Management

Training is triggered by a gap identified through Selection (a [TrainableGap](../Selection/TrainableGap.md)) or through observed Performance, and its effect is measured through later Performance evidence. Training does not itself decide whether it is worth pursuing — that comparison belongs to [Personnel Decisions](../Personnel%20Management/Personnel%20Decisions/README.md), a Personnel Management module. Training itself is a sibling Cross Domain of Personnel Management, Selection and Performance, not a module of any of them — see [../../Domain Architecture.md](../../Domain%20Architecture.md) §4.

---

## Relationship to Core

Training will build on Core Process, Action, Outcome and Learning (see [../../../00 Core/Process.md](../../../00%20Core/Process.md), [../../../00 Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md](../../../00%20Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md)) without redefining them.

---

## Relationship to technical Domains

Training consumes technical knowledge and required standards from whichever technical Domain the role belongs to (e.g. Restaurant wine-service or kitchen-process standards — see [../../Restaurant/README.md](../../Business%20Domain/Restaurant/README.md)); it does not duplicate that Domain's knowledge. Training itself is potentially cross-industry, in the same way Selection is.

---

## Deferred

Detailed modeling of Training entities, curricula, methods, durations and business rules is deferred to a future task. No universal training duration table or curriculum is defined here.
