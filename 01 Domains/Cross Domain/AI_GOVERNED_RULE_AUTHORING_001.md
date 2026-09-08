# AI-Governed Rule Authoring

**Version:** 0.1
**Status:** Draft (initial canonical foundation)
**Scope:** Cross-cutting principle — not owned by any single Domain. Applies wherever a human would otherwise author an operational/business rule directly, in any current or future Domain (see §12).
**Origin:** Builds on Core [05_Epistemic_Boundary_and_Subject_Sovereignty.md](../../00%20Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md) and [06_Business_Autopilot_and_Intelligence_Engine.md](../../00%20Core/ConceptualArchitecture/06_Business_Autopilot_and_Intelligence_Engine.md).

---

## 1. Governing principle

> Operational/business rules must not normally be authored directly by users as raw system logic. RF-One should instead use AI-guided clarification, validation, and formulation to convert human intent into coherent executable rules.

**Human Intent First.** The user provides:

- what they want to achieve;
- relevant conditions;
- preferences;
- constraints;
- priorities;
- exceptions;
- operational context.

The user should **not** be expected to know, or to directly manipulate: database structure, rule syntax, workflow logic, technical conditions, or implementation semantics. RF-One's AI acts as the intelligent intermediary that converts expressed intent into a coherent, executable rule — the user's task is to express *meaning*, not *syntax*.

This is a Domain-independent application of the Subject/RF-One relationship already established by Core: the Subject expresses Desire and direction in their own terms; RF-One reasons about how to pursue it (see [01_Subject_and_Reality.md](../../00%20Core/ConceptualArchitecture/01_Subject_and_Reality.md), [02_Desire_Goal_and_Reality_Check.md](../../00%20Core/ConceptualArchitecture/02_Desire_Goal_and_Reality_Check.md)). A business rule is one particular, formal expression of that direction, and should be reached the same way.

---

## 2. Guided clarification

RF-One should interactively ask questions until it understands the intended rule sufficiently well — resembling a competent analyst or consultant interviewing the operator, not a form to fill in.

Questions may clarify: objective, scope, who/what the rule applies to, triggering conditions, thresholds, exceptions, priorities, conflicts, timing, authority, and expected outcome.

**No fixed questionnaire is prescribed by this document.** The questioning process must be adaptive to the specific rule and context — a simple threshold adjustment and a complex multi-condition exception policy do not warrant the same depth of interview. What the interview must establish, regardless of form, is enough clarity to proceed to §3.

---

## 3. Reality / coherence check

RF-One must not passively accept every requested rule. Before a rule is formalized, the AI should evaluate whether it appears:

- contradictory;
- operationally implausible;
- economically irrational;
- inconsistent with other existing rules;
- unsafe;
- impossible with available data;
- outside delegated authority (see §4);
- likely to produce unintended consequences.

This is the rule-authoring application of the Core [Reality Check](../../00%20Core/ConceptualArchitecture/02_Desire_Goal_and_Reality_Check.md) already required generically wherever RF-One reasons about a Subject's Desire against Reality — a rule is itself a Desire/Goal expressed in a formal, executable shape, and is not exempt from that discipline merely because it will become code.

When RF-One detects a problem, it must explain it clearly, in human language — capable of saying, in substance:

> "This rule is likely to create a problem because..."

and explaining why, in terms the user can evaluate, not in terms of implementation. **The exact reasoning engine that performs this evaluation is not defined by this document.**

---

## 4. Constructive challenge

RF-One is not a transcription system. It should challenge a proposed rule when evidence or logic suggests the rule is poor, contradictory, or likely to damage the user's own stated objective. The AI may propose alternatives, or ask the user to reconsider an assumption the rule depends on.

This is a direct application of Core [Subject Sovereignty](../../00%20Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md) to rule authoring specifically: RF-One "may challenge, question, contradict, surface ignored information, identify incoherence, show risk, expose consequences, propose alternatives, recommend reconsideration" — but "must not substitute itself for the Subject's final authority." The governing interaction remains exactly Core's own:

> **"Now that you know this, are you still sure?"**

Applied to rule authoring:

- **AI does not silently override the user.** A challenge is surfaced, explained, and left for the user to resolve — it is never quietly applied as a substitute for what the user actually asked for.
- **AI does not invent authority.** Whether a given user may even request this class of rule, or approve it once formalized, is governed by whatever Delegated Authority already applies in that Domain/Runtime context (see [06_Business_Autopilot_and_Intelligence_Engine.md](../../00%20Core/ConceptualArchitecture/06_Business_Autopilot_and_Intelligence_Engine.md), "Authority model") — this document does not create a new authority model, and does not grant RF-One any authority a Domain has not already delegated to it.
- **Final human authority remains intact.** If the user, having understood RF-One's objection, confirms the rule anyway, RF-One should respect that decision within whatever authority boundary already governs it — not continue to relitigate a decision made with full awareness of the relevant facts (Core, same document, §2).

---

## 5. Rationalization before formalization

A rule should be formalized only after the conversation has reached a sufficiently clear, coherent, plausible, and authorized definition. Conceptually, the process moves through:

```text
initial idea
  → clarified intent            (§2, guided clarification)
    → challenged/revised intent  (§3-4, coherence check and constructive challenge)
      → proposed rule
        → approved rule
```

**This document does not define exact workflow states, a state machine, or a persistence model for this progression.** Where a Domain already implements rule governance with its own explicit states — for example Selection's existing Rule Set confirmation gate and versioned Rule Set/Rule Change history (`Selection/reports/TASK_5C_SELECTION_SESSION_RULE_GOVERNANCE_REPORT.md`) — this principle is intended to inform *how a human and RF-One arrive at* a proposed Rule Set/Rule Change, not to replace or redefine the governance mechanism that already exists once a rule reaches that stage. See §12.

---

## 6. AI rule generation

Once sufficiently resolved, RF-One's AI converts the approved intent into whatever internal rule representation the relevant Domain/Runtime requires. The user should not need to directly write conditions, formulas, expressions, workflow code, or technical rule syntax.

**The exact implementation representation — rule-engine syntax, expression language, storage format — is out of scope for this document**, and is not designed here.

---

## 7. Human-readable rule representation

Every AI-authored rule must also have a human-readable representation. The operator should be able to understand, without reading the executable form:

- what the rule does;
- when it applies;
- why it exists;
- important thresholds/conditions;
- exceptions;
- expected consequences.

This descriptive representation must remain **semantically consistent** with the executable/internal rule — it is a rendering of the same rule, not an independent description that could drift from what the rule actually does.

---

## 8. Multilingual representation

Human-readable rules should be renderable in the operator's preferred language. Consistent with the [Language](../../CLAUDE.md) convention already governing this repository (Italian for Product-Owner-facing communication, English for technical artifacts), the same principle extends to rule explanations shown to any operator:

- **language must not change the meaning of the underlying rule** — a translation is a rendering, not a re-authoring;
- the internal rule remains language-independent where practical;
- translations are representations of the same rule, not separate, independently editable rules. Editing a translation edits only its rendering, never the rule it describes.

---

## 9. Single source of truth

The executable/internal rule and its human-readable explanation(s), in any language, must refer to the same authoritative rule object. RF-One must avoid situations where the technical rule says one thing, its documentation says another, or a translation changes the effective meaning. Where a Domain's existing rule-governance mechanism already enforces versioning and confirmation (e.g. Selection's Rule Set version history), this principle requires that any human-readable/multilingual rendering stay bound to the same version, never rendered from a stale or divergent copy.

---

## 10. Change management

When a user wants to modify an existing rule, the system should again work through guided clarification (§2) and impact/coherence checking (§3) rather than exposing raw technical editing by default. The AI should be able to explain:

- what is changing;
- what the previous behavior was;
- likely operational consequences;
- conflicts with existing rules.

This mirrors, at the cross-Domain level, the discipline Selection's own Rule Change governance already applies within its Domain (explicit scope of a change — e.g. SUBSEQUENT_ONLY vs. ENTIRE_SESSION — and non-silent handling of retroactively-impacted records, per `TASK_5C_SELECTION_SESSION_RULE_GOVERNANCE_REPORT.md`). **No versioning implementation is defined here** — where a Domain already has one, this principle governs the conversational path that leads *to* a change request, not the mechanism that records it.

---

## 11. Evidence and explainability

Where the AI challenges or recommends a rule change, the explanation should distinguish, using the same [Epistemic Boundary](../../00%20Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md) states already mandatory throughout RF-One:

```text
factual evidence          Fact / Observation — directly established or perceived
derived conclusions        a deterministic calculation from Observed facts
predictions                Hypothesis — a proposed, not yet confirmed, expectation
assumptions                Assumption — taken as true for the purpose of reasoning,
                            without verification
business judgment          Belief — held to be true by RF-One or the user, not
                            established as Fact
```

**RF-One must not present unsupported AI opinion as fact.** A coherence objection (§3) or a proposed alternative (§4) must be traceable to which of these it actually is — exactly the same discipline [CandidateEvidence.md](Selection/CandidateEvidence.md) and [PerformanceEvidence.md](Performance/PerformanceEvidence.md) already require in their own Domains, applied here to rule-authoring reasoning specifically.

---

## 12. Cross-domain application

This principle applies to rule authoring across RF-One as a whole — it is not owned by, or specific to, any one Domain. Possible future applications include (illustrative, not exhaustive, not a commitment to build any of them):

```text
Selection            Requirement configuration, disqualification criteria, Rule Set/
                      Rule Change content (Selection already has its own governance
                      mechanism for confirming and versioning a Rule Set — see §5, §10 —
                      this principle would inform how a human and RF-One arrive at what
                      goes into that mechanism, not replace it)
Training              curriculum/eligibility rules, once Training is modeled
Performance            Indicator relevance rules, once formalized
Purchasing            approval thresholds, supplier rules
Tips                  allocation rules
Payroll               calculation/eligibility rules
Scheduling             availability/assignment rules
Service Copilot        intervention/threshold configuration (e.g. Management
                      Intrusiveness levels)
Brand standards        Brand Expectation configuration
Organization            Employee Assignment rules
other future Domains   any Domain that eventually needs operator-authored rules
```

**No Domain-specific rule structure is defined by this document.** Each Domain retains full ownership of what its own rules mean and how they are stored, evaluated and governed once formalized; this document governs only the conversational path by which a human's intent becomes that Domain's rule.

---

## 13. User experience principle

The intended experience, independent of Domain:

```text
Human expresses intent
  → RF-One asks intelligent questions               (§2)
    → RF-One tests coherence and feasibility          (§3)
      → RF-One challenges bad assumptions when necessary (§4)
        → Human and AI converge on a rational rule     (§5)
          → Human approves                             (§4, Subject Sovereignty)
            → AI formalizes the rule                    (§6)
              → RF-One shows the rule back in clear human language (§7)
                → same rule can be rendered multilingual (§8)
```

The operator interacts primarily with **meaning**, not system syntax.

---

## 14. Explicit exclusions

This document does **not** define:

- final UI;
- chat interface implementation;
- LLM provider (see [06_Business_Autopilot_and_Intelligence_Engine.md](../../00%20Core/ConceptualArchitecture/06_Business_Autopilot_and_Intelligence_Engine.md), "Intelligence Engines" — RF-One remains provider-independent);
- rule-engine syntax;
- database schema;
- prompt design;
- conflict-resolution algorithm;
- permission model implementation;
- automated approval thresholds;
- Domain-specific rule structures.

---

## 15. Open decisions

The following are genuine, unresolved design questions this document deliberately leaves open:

1. **What confidence/clarity is sufficient** before RF-One proposes a formal rule — how "sufficiently clear, coherent, plausible, and authorized" (§5) is actually determined, rather than judged case by case.
2. **How conflicts with existing rules are surfaced** — mechanically, how RF-One would detect that a proposed rule conflicts with another rule already in force, across potentially different Domains.
3. **How approval authority is resolved** — how RF-One determines, for a given rule and a given user, what Delegated Authority (§4) actually permits, beyond the general principle that it must not invent authority.
4. **How the executable rule and its natural-language rendering are kept semantically synchronized** (§7, §9) — the actual mechanism, not merely the requirement that they must not drift.
5. **How historical rule revisions are preserved** — where a Domain does not yet have its own rule-versioning mechanism (unlike Selection, which already does), what a minimal cross-Domain expectation should be.
6. **When AI should refuse to formalize a rule outright** — as distinct from challenging it (§4) — e.g. a rule that is unsafe, clearly outside any plausible delegated authority, or technically impossible regardless of user insistence.

---

## Related documents

- [../../00 Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md](../../00%20Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md)
- [../../00 Core/ConceptualArchitecture/06_Business_Autopilot_and_Intelligence_Engine.md](../../00%20Core/ConceptualArchitecture/06_Business_Autopilot_and_Intelligence_Engine.md)
- [../../00 Core/ConceptualArchitecture/02_Desire_Goal_and_Reality_Check.md](../../00%20Core/ConceptualArchitecture/02_Desire_Goal_and_Reality_Check.md)
- [Selection/reports/TASK_5C_SELECTION_SESSION_RULE_GOVERNANCE_REPORT.md](Selection/reports/TASK_5C_SELECTION_SESSION_RULE_GOVERNANCE_REPORT.md) — existing Domain-level rule-governance mechanism this principle is designed to remain compatible with, not replace
- [Selection/CandidateEvidence.md](Selection/CandidateEvidence.md), [Performance/PerformanceEvidence.md](Performance/PerformanceEvidence.md) — existing epistemic-traceability discipline this document extends to rule-authoring explanations
- [PERSON_CONTINUITY_001.md](PERSON_CONTINUITY_001.md), [Selection/SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md](Selection/SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md) — related cross-cutting concept documents at this level
