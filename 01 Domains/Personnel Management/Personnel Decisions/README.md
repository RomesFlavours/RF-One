# Personnel Decisions

**Version:** 0.1
**Status:** Placeholder (module boundary only — no concept modeling)
**Module:** Domain / Personnel Management / Personnel Decisions

---

## Purpose

Personnel Decisions applies Core `Decision` semantics (see [../../../00 Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md](../../../00%20Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md)) to people-related decisions: what should be done about the person currently in a role.

**This module does not redefine Core Decision.**

---

## Module boundary

Personnel Decisions answers **"what should be done about the person currently in the role"**. It is distinct from the other Personnel Management modules:

- [Workforce](../Workforce/README.md) answers "who currently occupies the role";
- [Selection](../Selection/README.md) answers "who else is a credible alternative," and its output is one input to a Personnel Decision;
- [Training](../Training/README.md) answers "how do we close an evidenced gap" — a possible conclusion of a Personnel Decision;
- [Performance](../Performance/README.md) answers "what did the person actually produce" — one input to a Personnel Decision.

Possible conclusions include retain, continue observing, correct, train, develop, move/reassign, change responsibilities, replace. This list is illustrative, not exhaustive or mandatory.

Personnel Decisions may compare:

```text
Expected value of current person

vs

Expected value of available alternative
- recruitment cost
- training cost
- transition cost
- uncertainty / risk
```

This is a guiding comparison, not a rigid formula or an automatic threshold. **No automatic termination or replacement threshold is defined here.**

---

## Relationship to other Personnel Management modules

Personnel Decisions draws on Performance evidence (what actually happened), Selection's identified alternatives (who else is viable), and Training's cost/outcome (what closing a gap would take or achieved), without owning or redefining any of those modules' reasoning.

---

## Relationship to Core

Personnel Decisions reuses Core Decision, Action, Outcome, Learning and Subject Sovereignty / Delegated Authority (see [../../../00 Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md](../../../00%20Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md), [../../../00 Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md](../../../00%20Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md)) without redefining them, in the same way [Selection Decision](../Selection/SelectionDecision.md) already applies Core Decision to selection-specific choices.

---

## Relationship to technical Domains

Personnel Decisions consumes role requirements, operational context and expected outcomes from whichever technical Domain the role belongs to (e.g. Restaurant — see [../../Restaurant/README.md](../../Restaurant/README.md)); it does not duplicate that Domain's knowledge.

---

## Deferred

Detailed modeling of Personnel Decision entities, decision records, authority thresholds and business rules is deferred to a future task. No automatic firing/termination rule is defined here.
