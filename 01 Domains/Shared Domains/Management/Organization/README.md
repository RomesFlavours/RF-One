# Organization

**Version:** 0.2 — 2026-10-25
**Status:** Component of the Management Shared Domain. **Approved by the Product Owner (2026-10-25):** Organization's mandate (§1), including the responsibilities formerly documented as the Personnel Management modules **Workforce** and **Personnel Decisions**. The discovery interview, pilot, confidentiality and governance material (§6–§11) keeps its source status: functional reference, with pilot and governance proposals awaiting confirmation.
**Module:** Domain / Management (Shared Domain) / Organization
**Sources:** M03 §4, §§7–10; O01 §§1–12; C01 points 8–10; C02; O02–O05 (see [../SOURCES.md](../SOURCES.md)). Former Workforce and Personnel Decisions placeholders (v0.1), preserved unchanged in `90 Archive/Superseded Documents/01 Domains/Shared Domains/Personnel Management/`.

---

## 1. Mandate

Organization owns the **design of work**: processes, functions, roles, responsibilities, authority, role coverage and assignments. It starts from the Business Domain default, learns the company's reality, compares differences and gaps, proposes a design suited to the actual people and resources, and keeps track of what has actually been approved and covered.

Organization absorbs two responsibilities previously documented as modules of the former Personnel Management Domain:

| Former module | Question it answered | Where it now lives |
|---|---|---|
| Workforce | Who currently occupies, or can occupy, organizational roles? | §3, "Approved assignments and actual coverage" |
| Personnel Decisions | What should be done about the person currently in the role? | §4, "Comparison of alternatives", and §5, "Decisions reserved to authorized people" |

The former Personnel Management Domain no longer exists as a Domain (Product Owner decision, 2026-10-25). Its Compensation module moved to Administration (`../../Administration/Compensation/README.md`). Selection, Performance, Continuous Productivity Development and Operational Knowledge were already independent Shared Domains and remain so.

Organization keeps four kinds of content strictly distinct:

1. **design and proposals** (§2, §6–§11) — what the work should be and who could do it;
2. **approved assignments and actual coverage** (§3) — what has been approved and who is actually covering it;
3. **comparison of alternatives** (§4) — evidence-based reasoning about the current person and the available alternatives;
4. **decisions reserved to authorized people** (§5) — the human decision itself.

A proposal never becomes an approved assignment by being recorded, and a comparison never becomes a decision.

## 2. Design and proposals

Organization starts from the Business Domain default, learns the company's reality, compares differences/gaps and proposes a design suited to actual people/resources. Humans approve. It must not merely digitize current habits or count majority testimony as truth (M03 §§4.1, 4.4).

Keep separate: **current reported reality, confirmed approved references, uncertainty/conflicts, and AI proposals**. Attachments and drafts are evidence/input, not approved procedures. O04 asks for problems → causes → value → functions → structure → people, distinguishing functional, control, approval and hierarchical authority; it is source commentary, not an approval of named assignments.

The discovery interview, synthesis, process design and responsibility proposals that implement this design work are described in §6–§11. Their source status is unchanged by this reorganization.

## 3. Approved assignments and actual coverage

*Formerly the Workforce module.* Organization represents the organization's current human structure: who currently occupies, or can occupy, organizational roles — distinct from who else would be a credible alternative (Selection), what a person actually produced (Performance) and what should be done about the person in the role (§4–§5).

**No new register is introduced.** Organization does not create a parallel registry of people, roles, assignments or authority. Occupancy and coverage are already represented by existing, approved semantics, which Organization preserves and links:

| Existing semantics | Owner and status | What it represents |
|---|---|---|
| [Employee Assignment](../../../Business%20Domain/Restaurant/Organization/Employee%20Assignment.md), [Restaurant Role](../../../Business%20Domain/Restaurant/Organization/Restaurant%20Role.md), [Operational Area](../../../Business%20Domain/Restaurant/Organization/Operational%20Area.md) | Restaurant Domain, Organization module — Approved v1.0 | The Restaurant-specific, temporal assignment of an Employee to a Restaurant Role in an Operational Area (and optionally a Location) |
| Position, Position Scope, Occupant / Position Assignment, Temporary Coverage, Backup Position, Process Ownership ([System README](../../../../10%20System/Organizational%20Responsibility%20and%20Attention%20Management/README.md)) | `10 System/` foundation, implementing `00 Core/Organizational Responsibility.md` — Active | Organizational responsibility, its occupancy and coverage, process ownership and attention routing |
| Accounts, Acting Identities, Authority Grants ([Identity & Access](../../../../10%20System/Identity%20%26%20Access/README.md)) | `10 System/` — structurally frozen | Who may act, with which authority and in which scope |

The approved assignment and actual-coverage view of Organization is these existing records read together; Organization adds the design and approval context around them, not a competing copy. How Management's responsibility proposals (§9) map onto Positions, Process Ownership and Employee Assignment remains to be specified (G02, G03).

Possible further concepts — Person/Worker, Availability, Schedule, Employment Relationship — were listed by the former Workforce placeholder as future concepts. They are still not defined here.

## 4. Comparison of alternatives

*Formerly part of the Personnel Decisions module.* Organization may compare the expected value of the person currently in a role with the available alternatives, applying Core `Decision` semantics without redefining them ([03_Decision_Action_Outcome_Learning.md](../../../../00%20Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md)):

```text
Expected value of current person

vs

Expected value of available alternative
- recruitment cost
- training cost
- transition cost
- uncertainty / risk
```

This is a guiding comparison, not a rigid formula or an automatic threshold. The comparison draws on, without owning or redefining:

- [Performance](../../Performance/README.md) — what actually happened;
- [Selection](../../Selection/README.md) — who else is a credible alternative;
- [Continuous Productivity Development](../../Continuous%20Productivity%20Development/README.md) — what closing a gap or capturing an opportunity would take or achieved;
- [People](../People/README.md) — contextualized professional knowledge, with its evidence and limits;
- [Administration / Personnel Cost](../../Administration/Personnel%20Cost.md) — `Total Employee Cost` as cost evidence. `cheapest Employee = best Employee` is never a conclusion.

The guiding loop, descriptive and not a mandatory formula, is unchanged from the former Personnel Management Domain:

```text
Observed Performance
→ communicate / correct / opportunity to improve
→ Continuous Productivity Development intervention where economically justified
→ observe again

in parallel:

Selection
→ find credible alternatives

then:

Comparison of alternatives
→ compare current expected value with available alternatives
→ conclusion proposed to the authorized people (§5)
```

The question answered is operational and economic, not a moral judgment. No KPI list, scoring formula or ranking is canonized here; indicators are derived, not assumed (`01 Domains/Domain Architecture.md` §8).

## 5. Decisions reserved to authorized people

Possible conclusions include retain, continue observing, correct, train, develop, move/reassign, change responsibilities, replace. This list is illustrative, not exhaustive or mandatory.

These decisions belong to the competent, authorized people. RF-One prepares evidence and comparisons; it never fires, replaces or reassigns a person autonomously, and **no automatic termination or replacement threshold is defined**. Authority to decide comes from the existing Identity & Access and Organizational Responsibility foundations (Subject Sovereignty and Delegated Authority — [05_Epistemic_Boundary_and_Subject_Sovereignty.md](../../../../00%20Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md), [09_Identity_Authority_and_Accountability.md](../../../../00%20Core/ConceptualArchitecture/09_Identity_Authority_and_Accountability.md)); Organization creates no authority of its own.

Detailed modeling of decision records, authority thresholds and business rules is deferred, as it was for the former Personnel Decisions placeholder. The relationship between these decisions and the "evaluations will live in Organization" decision of 2026-10-12, recorded only on another branch, remains open (G29).

## 6. Discovery interview: source contract and conflicts

O01 v0.1 is **for review**, not an implemented or approved pilot. It proposes 5 managers (names confirmed by Pino) plus at least 4 staff, 2 FOH and 2 BOH; voluntary participation and paid interview time for hourly staff. M03 retains the staff proposal but leaves names/numbers/timing open.

Collect/confirm existing account identity, level/area, location, role/work description, preferred language and text/voice preference; allow attachments. Show the purpose/confidentiality notice before question 1 and obtain acknowledgment. The interview is about understanding the business, **not assessing the interviewee**; do not repurpose answers for People assessment (O01 §1).

| # | Core topic | Source status |
|---|---|---|
| 1 | Brand | O01 §5, M03 §4.2 |
| 2 | Customers and offering | O01 §5, M03 §4.2 |
| 3 | Actual contribution | O01 §5, M03 §4.2 |
| 4 | Working day | O01 §5, M03 §4.2 |
| 5 | Occasional/non-daily work | O01 §5, M03 §4.2 |
| 6 | Work connections / process compared with industry default | O01 asks openly; M03 introduces default-led comparison |
| 7 | Procedures and practices | O01 §5, M03 §4.2 |
| 8 | Coordination, decisions and blockers | O01 §5, M03 §4.2 |
| 9 | Problems and changes | O01 §5, M03 §4.2 |
| 10 | Waiting, dependencies and bottlenecks | Included in O01; still proposed in M03 |
| 11 | Unique knowledge | Included in O01; still proposed in M03 |

Same core meaning/order across participants; adapt wording to manager/staff level. Ask concrete, non-leading follow-ups, summarize for correction/confirmation and resume the core sequence. O01 §6 proposes at most 3 follow-ups per question unless useful detail continues, plus skip/don't-know/pause/resume. It excludes private health/family/immigration/pay/finance collection and says volunteered private information is not stored.

M03's default-comparison method is a direction for the next interview revision, **not an existing v0.2 specification**. O01/C02 estimate about 45 minutes; M03 about 30. O01 proposes completion within 2 weeks and synthesis within the following week; M03 leaves dates/deadlines open. Preserve these differences (G07–G09).

Within the approved Cognito boundary, Organization decides what the interview must explore and why; Cognito conducts the conversation and understands the answers (`00 Core/ConceptualArchitecture/14_Cognito_RF-One_Cognitive_Intelligence.md` §9).

## 7. Confidentiality proposal

O01 §7 proposes AI-only raw access with an explicit exception for the participant's own answers; combined findings for Pino/Shelbi and others only with Pino's approval. No identifying quotations/details. Attribute by manager/staff level only when at least two in that group report something similar; combine FOH/BOH staff if separation identifies someone. This is a reporting proposal, **not a guaranteed anonymity mechanism**.

Raw retention lasts only as long as analysis requires, for a period to agree, then deletion; combined findings remain. M03 says confidentiality boundaries must be approved before pilot. Its shorthand "humans receive only combined findings" must be reconciled with O01's participant access exception (G10–G11).

## 8. Synthesis, design and review

O01 §8 outputs: business perception; manager/staff differences; actual daily/occasional work; bottlenecks/dependencies; unique knowledge; problems separate from suggestions; clarification points; draft processes. Label findings confirmed by several sources, single-source report, uncertain/contradictory, or AI proposal. Corroboration is not proof by majority.

M03 adds explicit comparison with industry defaults and reasoned proposals for missing/duplicated work. Each process has purpose, trigger, expected outcome, activities and relationships; review **one process at a time** and keep Draft until explicit approval. Conflicts go to a designated human, not an invented reporting line.

### Process, procedure, execution and project

| Concept | Meaning from M03 §4.5 |
|---|---|
| Process | Necessary work producing a business outcome |
| Procedure | Reusable method with conditions, decisions, exceptions and checks |
| Execution | One application of a procedure |
| Project | Finite initiative with a defined objective |

Organization proposes activation conditions, information needs, steps, decision criteria, authority limits, verification, exceptions, controls and maintenance ownership where relevant. Reuse approved procedures and versions; do not create competing documentation. Exact practical records are not defined here. "Process" here is used in the sense of `00 Core/Process.md`; it is not a Project Manager task.

## 9. Responsibility proposals and handoff

After process validation, map who performs work today, including shared, informal, ambiguous and uncovered work. Once adequate People profiles exist, compare needs with evidenced capabilities, availability, workload, resources and constraints.

For each process propose an explained **first choice**, explained **second choice** and uncovered needs. The second choice is not a co-owner or automatic backup (and is distinct from the System's configured Backup Position). Humans can accept either, select another or reject. Only an approved assignment enters Project Manager (M03 §§4.7–4.8) and becomes part of the approved assignments and coverage of §3.

Sequence: **domain default → interviews → synthesis/gaps → draft processes → process approval → adequate People evidence → assignment proposals → approval → Project Manager**. Discovery can begin before People is operational; optimal assignments cannot be claimed without sufficient evidence.

## 10. References and readiness

M03 §4.6 proposes approving Organization Model 0.4, Procedure 001 v0.3 and Manager Model 0.2. These approvals are **not established**. Organization Model 0.4 and Manager Model 0.2 were not located; a file named "Procedure 001 - FOH Supplies and Glassware - Draft 0.3" is listed in the source manifest as located and fingerprinted only, without substantive review or evidence of approval (G16). Available earlier models remain inputs. Do not use their named owners, budgets, backup or control arrangements as active company configuration.

O01 §10 retains acceptance scenarios I01–I14 for future review: notice, voice confirmation, don't-know, resume, colleague-blame redirection, private data exclusion, anonymous aggregation, differences/conflicts, attachment status, reuse, restricted raw access, Draft gating and paid time. These are proposed acceptance criteria, not test results.

## 11. Name disambiguation

"Organization" in this document is the Management component. It must not be confused with:

| Same word, different thing | Location |
|---|---|
| Restaurant Domain's **Organization** module (Restaurant Role, Operational Area, Physical Area, Employee Assignment, Restaurant Profile — Approved) | `01 Domains/Business Domain/Restaurant/Organization/` — an industry-specific source of occupancy semantics this component consumes (§3) |
| The **Organizational Responsibility and Attention Management** foundation | `10 System/` — the runtime Position/ownership/attention mechanism this component reuses (§3) |
| RF-One Web's **ORGANIZATION** access code | Recorded only on another branch (`origin/main`, ACCOUNT_ITEM_ACCESS_001): an access code for the System foundation pages, explicitly "not a decision about where Organization sits in the Domain taxonomy" |

## 12. Relationship to Core and to Business Domains

Organization reuses Core concepts without redefining them: Subject, Entity, Relationship, Assignment and Ownership ([../../../../00 Core/Relationship.md](../../../../00%20Core/Relationship.md), [../../../../00 Core/Entity.md](../../../../00%20Core/Entity.md)); Process ([../../../../00 Core/Process.md](../../../../00%20Core/Process.md)); Position and Process Ownership ([../../../../00 Core/Organizational Responsibility.md](../../../../00%20Core/Organizational%20Responsibility.md)); Decision, Action, Outcome and Learning; Temporal Coherence — a decision made under earlier evidence does not retroactively become invalid when later evidence arrives ([04_Temporal_Coherence_and_Evolution.md](../../../../00%20Core/ConceptualArchitecture/04_Temporal_Coherence_and_Evolution.md)); and the Epistemic Boundary, which governs how evidence, uncertainty and decision authority are preserved.

Organization is industry-independent. It consumes role requirements, role and position context, operational context, technical standards and expected outcomes from whichever Business Domain the role belongs to (today Restaurant — see [Restaurant/README.md](../../../Business%20Domain/Restaurant/README.md)); it does not duplicate that Domain's knowledge.

Customer Feedback and Review remain separate transversal Domain candidates, not part of Organization (`01 Domains/Domain Architecture.md` §6). Performance may consume their evidence when relevant.

## 13. Related documents

- [../README.md](../README.md) — Management Shared Domain
- [../People/README.md](../People/README.md), [../Project Manager/README.md](../Project%20Manager/README.md) — sibling components
- [../INTERFACES_AND_DEPENDENCIES.md](../INTERFACES_AND_DEPENDENCIES.md), [../DECISIONS_AND_GAPS.md](../DECISIONS_AND_GAPS.md) — handoffs and open questions
- [../../../Domain Architecture.md](../../../Domain%20Architecture.md) §4–§5 — taxonomy and the Organization / Selection / Performance / Continuous Productivity Development distinctions
- [../../Selection/README.md](../../Selection/README.md), [../../Performance/README.md](../../Performance/README.md), [../../Continuous Productivity Development/README.md](../../Continuous%20Productivity%20Development/README.md) — sibling Shared Domains this component consumes
