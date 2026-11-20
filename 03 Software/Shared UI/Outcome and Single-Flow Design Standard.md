# Outcome-first and single-flow interaction design

**Code:** UI_OUTCOME_SINGLE_FLOW_001  
**Status:** standing development instruction approved by the Product Owner, 2026-11-04.  
**Applies to:** every RF-One Domain, Module, runtime, page, modal and AI-assisted development task.  
**Authority:** this is the canonical operational standard; CLAUDE.md, UI Rules and User Interaction Architecture link here instead of maintaining competing definitions.  
**Implementation status:** documenting this standard does not certify that existing software complies with it.  
**Core status:** the universal principle below is proposed for discussion with Shelbi; this document does not add it to the approved Core or change Core governance.

## 1. Governing principle

> RF-One organizes interaction around the outcome the person wants to achieve. The system handles the complexity it can manage and asks the person only for necessary information and decisions, when they are needed. The software's internal structure must not dictate the user's workflow.

For each user goal, provide **one clear, coherent primary workflow**. Do not make the person choose between competing routes, technical modules or shortcuts into unrelated/later stages to understand what to do next.

Success is the person's ability to reach the intended result correctly, with clear decisions and recoverable errors. Feature completeness, technical correctness and a low click count alone are not sufficient.

## 2. Start from the person's work

Before implementing or changing a function, identify:
1. who is using it and the concrete result they came to achieve;
2. the inputs already available and what RF-One can determine itself;
3. the current step, its legitimate prerequisites and the next meaningful action;
4. the exceptional information or decision that only a person can supply;
5. how completion is recognized and how the person resumes after an interruption.

Describe that journey in plain language before deciding on screens, endpoints or internal services. Code structure, database tables, implementation convenience and the order in which features were developed do not define the journey.

## 3. One primary workflow per outcome

- Every visible action advances the current goal, resolves its current exception, or provides contextual explanation. Remove or relocate actions that open unrelated/competing workflows or bypass meaningful prerequisites.
- A user must not have to decide which technical route to use for the same outcome. Different entry points, when necessary, converge on the same workflow and shared implementation with the relevant context already populated.
- A contextual subtask is part of the current workflow, not an alternative journey: keep it scoped, show what it affects, and return to the same place with state preserved. One workflow may contain several pages or modals; it does not mean one giant screen or one global workflow for every unrelated goal.
- Reveal advanced tools only where needed, subordinate to the primary task. Never use an advanced route as the only way to finish a normal case.
- Navigation to another capability is not automatically useful. Do not add row buttons or cross-links merely because the underlying functions exist.
- Distinct legitimate roles, permissions and exceptional cases must be handled explicitly without creating misleading shortcuts or competing instructions. Do not hide necessary controls, approvals or limitations in the name of simplicity.

## 4. The system performs the work

RF-One reads and connects available facts, checks completeness, applies approved rules, prepares proposals and identifies relevant exceptions before asking the person to intervene.

Do not ask the person to re-enter or infer what the system already knows or can reliably derive. When evidence is insufficient, ask the narrowest necessary question at the point where it matters. Never invent missing data, infer unauthorized consent, or silently make decisions reserved to the person.

Checks and blockers apply to the operation and data actually affected: an unrelated missing file must not block a useful analysis of an already available group. Full processing, simulation, assistance and final application may have different legitimate prerequisites; implement them explicitly and consistently on the server.

## 5. Every field and button must justify its presence

For each control ask: why does this person need it **at this step** to reach this result?

- Do not display technical filters or options when the context already fixes them.
- Do not require the person to select a month/session when uploaded facts determine the relevant coverage and the approved workflow does not call for that choice.
- Show a concrete reason for an exception, a system proposal when supported, and the action or information needed to continue.
- Distinguish facts, proposals, confirmed decisions, application and export. Counts must have clear, non-overlapping meanings and reconcile to their stated totals.
- Preserve fields, unsaved drafts, selected records, group, scroll position and focus through contextual subtasks, help, corrections and refreshes.
- Empty technical panels and legacy comparisons are not normal work instructions. Keep them subordinate or omit them when irrelevant.

## 6. Bank example — illustration, not a Core-specific rule

Primary journey: **upload files → check completeness → start automatic reconciliation → complete relevant exceptions → export**.

Within an exception group, provide one entry, **Controlla / Review**. The person should not choose between row-level Review, Investigate with AI and Advanced details as competing journeys. AI analysis, rule definition and technical details are contextual capabilities inside Review.

The group is already selected: show its occurrences and problem, not a new set of technical filters requiring the person to reconstruct that selection.

Rule workflow: inspect/propose → define or refine → simulate → review effects → explicitly confirm/save/apply. Show the effect on transactions and other rules, protect confirmed human decisions and return to the same group. General, WHO-category and single-WHO rules share the approved rule lifecycle; their coexistence decisions are documented in BANK_RULE_SCOPE_AND_WHO_CATEGORY_001.

These examples express a cross-domain design requirement. They do not replace Bank semantics or authorize applying anything to operational data.

## 7. Language and contextual explanation

Apply UI_DEVELOPMENT_LANGUAGE_001: the Product Owner's local interface is Italian, including secondary screens, dialogs, generated messages and help. Before an explicitly requested Git/AWS publication, prepare and verify English for the shared/release version while preserving the Italian local working copy. This standard does not authorize publication.

Apply UI_HOW_WORKS_001 and UI_HOW_WORKS_MODAL_001: every operational page has page-specific How Works / Come funziona; every modal has a visible ? opening its exact anchored explanation, without losing work. Update code and the explanation together. Explain the implemented behavior, including when data are saved and decisions take effect, not an intended future capability.

## 8. Mandatory final conformance review

Before declaring a task complete:
1. Read the applicable project instructions and relevant approved specifications, including CLAUDE.md/AGENTS.md where present, this standard, UI Rules, How Works, language policy and the Domain's rules.
2. Follow the actual user journey from the entry point to the requested outcome; include relevant dialogs, dynamic states, errors, recovery and return context. Test behavior, not only the existence of controls.
3. Ask: does the user know what to do next; is the system asking the user to do work it could do; are there competing routes or irrelevant options; can exceptions be resolved without losing context; does help match reality?
4. Correct deviations within the authorized scope and repeat the affected checks. Do not weaken a rule, remove meaningful tests or rewrite the standard to make an implementation appear compliant.
5. Resolve routine implementation choices independently. If applicable approved requirements genuinely contradict one another, identify the exact contradiction and request only the decision needed; do not choose silently.
6. State briefly what was verified, what was corrected and any material remaining limitation. Do not call a workflow complete when an essential step was only mocked or remains unreachable. Separate observed facts, design intent and unverified behavior.

This is a standing instruction for all future development commands, not an optional final polish step. A passing technical test does not by itself prove that a user can understand and complete the workflow.

## 9. Architectural placement and Core proposal

The universal candidate principle is stated in section 1. It is compatible in intent with the Core's user-relationship principle that RF-One performs cognitive work before requiring human attention and does not require a user to know what RF-One already knows; see [RF-One Intelligence and User Relationship](../../00%20Core/ConceptualArchitecture/10_RF-One_Intelligence_and_User_Relationship.md).

This document makes the development/interaction policy operational under Software authority. Any formal Core insertion remains a separately reviewed proposal with Shelbi. No Core entity, Domain semantic, authorization model or accounting rule is changed here.

## References

- [User Interaction Architecture](../User%20Interaction%20Architecture.md)
- [UI Rules](UI%20Rules.md)
- [How Works Standard](How%20Works%20Standard.md)
- [Development Language Policy](Development%20Language%20Policy.md)
- [Bank rule scopes and WHO categories](../../01%20Domains/Shared%20Domains/Administration/Bank%20Reconciliation/BANK_RULE_SCOPE_AND_WHO_CATEGORY_001.md)
