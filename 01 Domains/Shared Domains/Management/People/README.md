# People

**Version:** 0.3 — 2026-10-25
**Status:** Component of the Management Shared Domain. **Approved by the Product Owner (2026-10-25):** People's mandate as a Management component (§1) and the People–Cognito boundary (§2). Everything else keeps the status of its source — reported agreements stay reported agreements, proposals stay proposals (§14). This document attests no implementation and defines no data schema, API or new authorization.
**Module:** Domain / Management (Shared Domain) / People
**Supersedes:** the People consolidation v0.1 (2026-10-24, English) and its Italian revision v0.2 (2026-10-25), both preserved unchanged in `90 Archive/Superseded Documents/01 Domains/Shared Domains/Management/`. This version is the English canonical text of v0.2; the only change of meaning is the People–Cognito boundary decided after v0.2 was written (§2, "Revision note").

---

## 1. Mandate

People organizes and maintains the continuous professional knowledge of the people who work in RF-One: experience, knowledge, skills, observable professional attitudes, critical issues, support needs and their evolution over time, together with the evidence behind them, the confidential observations of authorized contributors (§8), coaching and development. It is the link to Training for the training cycle Training already owns (§10). This knowledge is contextual, evidence-based and revisable.

Its purpose is to compare what the work requires with the capabilities actually available, and to identify how to support and develop them. People always distinguishes what a person declares, what others report, what is demonstrated and what remains uncertain.

People potentially concerns owners, managers, employees and authorized collaborators, regardless of hierarchical level (P01 §1). The agreed initial scope is narrower: knowing the managers in relation to the restaurant's processes and the knowledge, skills and capabilities needed to govern them. This first piece of work is useful without building every future function.

## 2. Boundary with Cognito

**Approved by the Product Owner (2026-10-25).**

- **Cognito** — RF-One's transversal Cognitive Intelligence (`00 Core/ConceptualArchitecture/14_Cognito_RF-One_Cognitive_Intelligence.md`) — provides the **sensory functions, the understanding of language and the management of the conversation**.
- **People** (like Selection in its own field) **leads the specialist reasoning** of its field. People decides **what to explore and for which professional purpose**; Cognito handles understanding and interaction.

**People knows the person professionally and decides what is worth exploring; Cognito perceives, understands and converses.**

Cognito uses the authorized People information, together with operational context and the knowledge of other Domains, to understand and interact with each person. It does not take over People's specialist reasoning about professional knowledge, and People does not replicate Cognito's sensory, language and conversation capabilities as an independent intelligence of its own.

| Responsibility | People | Cognito |
|---|---|---|
| Professional knowledge | Organizes capabilities, evidence, critical issues and development | Uses the pertinent authorized information |
| Professional interview | Decides purpose, what to explore, which distinctions to preserve and when the evidence supports a professional conclusion | Conducts the dialogue, understands answers, asks the follow-up questions People's purpose calls for, and returns its understanding for confirmation |
| Assistance and coaching | Decides, from known capabilities and support needs, which professional support is pertinent | Delivers the interaction: language, timing and form of the exchange in the situation |
| Learning | Maintains professional goals, progress and evidence | Supports the exchange, using the competent services (e.g. Training) |
| Assessment | Organizes professional conclusions, their limits and validation | Supplies what it perceived and understood, without professional judgment or decision authority |

Not every interaction becomes a People assessment. Asking for help, receiving an explanation or being in temporary difficulty does not demonstrate a professional shortcoming. Information collected to assist a person must not be reused indiscriminately to assess them, and never becomes assessment evidence automatically.

A communication preference or a momentary operational state is not a stable professional capability (see `00 Core/ConceptualArchitecture/15_Human_Operational_State_and_Adaptive_Cognito_Interaction.md` §3). The technical relationship between the User Model (`00 Core/ConceptualArchitecture/10_RF-One_Intelligence_and_User_Relationship.md`) and the People profile remains to be specified, without duplicating or automatically merging the two (see `../DECISIONS_AND_GAPS.md`, G27).

**Revision note.** v0.2 described Cognito as also "reasoning about alternatives" and adapting "reasoning, questions and explanations". The Product Owner's later decision of 2026-10-25 assigns the specialist reasoning to People (and to Selection in its field) and limits Cognito's role here to sensory functions, language understanding and conversation management. The table above applies that decision; nothing else in v0.2 changed meaning.

## 3. Link with Organization and Project Manager

[Organization](../Organization/README.md) defines the work that is needed. People knows the professional capabilities available. [Project Manager](../Project%20Manager/README.md) accompanies concrete execution and the verification of results. Their information must be linked, not copied into competing definitions.

Organization defines the professional requirements of processes in its own canonical reference. People compares those requirements with the person's evidence, in the context of expected results, activities, constraints and the authority required. The full definition of the process remains in Organization.

A process requirement is distinct from the person currently assigned. Changing the person does not automatically change what the work requires.

The comparison must highlight documented capabilities, support needed, unknown areas and the critical issues pertinent to the assignment. Availability, workload, resources and authority are further conditions to consider with Organization: competence alone does not make an assignment feasible.

Only evidence sufficient for the specific use can support reasoned proposals. An incomplete profile does not exclude a person; it limits the conclusions that can be drawn. The operational sufficiency criterion is still to be defined (G06).

Project Manager returns evidence on commitments, work performed, deliverables, verified results, deviations and causes. People does not confuse a closed task with an achieved result, nor a delay with incapacity: missing approvals, insufficient resources and ambiguous responsibilities are part of the context.

Profile validation, assignment approval and plan approval are distinct acts. People does not assign responsibilities on its own and does not change working conditions. Decisions about the person in the role are reserved to the authorized people identified by Organization (Organization §"Decisions reserved to authorized people").

## 4. What a professional profile contains

The profile covers identity and professional context, relevant experience, knowledge, skills, observable attitudes, evidence, uncertainty, support and development (P01 §7). These are functional categories, not a prescription of tables or fields.

| Dimension | Meaning |
|---|---|
| Knowledge | What the person knows and understands in a field |
| Skills | What the person can carry out, and with what autonomy |
| Professional attitudes | Observable ways of approaching work, decisions and collaboration, always tied to context |
| Critical issues | Difficulties, limits or risks pertinent to the work, distinguishing individual from organizational factors |
| Support and development | Useful assistance, knowledge to acquire and capabilities to verify or consolidate |

Knowing a procedure, performing it, coordinating other people and being accountable for the result are different capabilities. For example: knowing products and suppliers does not by itself demonstrate the ability to forecast needs, plan purchases and close delivery anomalies.

Attitudes are not diagnoses or global personality labels. The profile does not collect private life to explain professional performance. A critical issue is described through situations, observable behavior, consequences and context factors.

## 5. Professional characteristics

The 21 October sources report an agreement in principle on seventeen characteristics (M03 §3.2; C01 point 1). The list is preserved; observable examples, acceptable evidence and practical application are not all defined.

| # | Characteristic |
|---|---|
| 1 | Understanding the objective |
| 2 | Accountability and reliability |
| 3 | Technical competence |
| 4 | Quality of reasoning and decisions |
| 5 | Planning and prioritization |
| 6 | Ability to deliver results |
| 7 | Resource stewardship and economic value |
| 8 | Quality and verification |
| 9 | Communication |
| 10 | Collaboration and delegation |
| 11 | Transparency and respect |
| 12 | Learning and development |
| 13 | Self-management and readiness for work |
| 14 | Managing emotional reactions and difficult situations |
| 15 | Initiative and ownership |
| 16 | Customer and reputation |
| 17 | Safety and compliance |

The descriptive levels reported by the sources are **not observed, with support, independently, able to teach others**. They are not numeric marks or a ranking. "Not observed" does not mean "incapable". The ability to teach requires specific evidence and does not follow automatically from autonomous execution.

The Management v0.3 source (M03 §3.3) reports that characteristics 13–14 are excluded for people who manage or guide others, including consultants, whose result-based engagements are assessed against deliverables, deadlines and commitments. The register records an ambiguity about how far this exclusion extends (G20); it must be clarified before applying it to different groups and is not resolved here by a new interpretation. The same source excludes the assessment of hours, schedules and methods for that group; this boundary is also preserved and clarified within its own scope, without extending it arbitrarily to other responsibilities.

The Management v0.3 reference proposes three levels: the general meaning of the characteristics in Legacy, the technical content required by the Business Domain, and the expectations and conditions of the individual company. For example, customer and reputation is the general reference; hospitality is its Restaurant Domain expression; "hosted, not served" is a Rome's Flavours choice. This source classification is not a new approved change to the Core or to Legacy.

## 6. Sources of knowledge and collection

People uses conversation with the person, declared experience, pertinent demonstrations, authorized observations by others and verified results. Each item keeps its provenance, date, context and knowledge state, compatibly with access restrictions.

The sources describe a free, adaptive initial conversation with no mandatory order of the seventeen characteristics (P01 §5). Within the boundary of §2, People determines what is worth exploring and when enough is known for a professional conclusion; Cognito conducts the exchange, looks for concrete examples, follows up contradictions and periodically returns what it understood for confirmation, correction or completion. The conversation allows pause and resume; it must not produce conclusions about areas that were not explored. Voice and text are foreseen by the technical specification, not declared operational.

The People professional conversation remains distinct from the Organization interview, which serves to understand the business. Answers collected for Organization do not automatically become material for assessing the person.

If something is taught during the conversation, People distinguishes initial knowledge, learning during the encounter and later application. A newly learned answer does not yet demonstrate autonomy on the job.

## 7. Evidence, interpretations and corrections

People preserves the distinction between:

- documented fact or verified result;
- the person's own declaration;
- observation reported by others;
- interpretation or hypothesis;
- validated conclusion;
- insufficient or contradictory information.

A validated conclusion remains revisable and does not turn an interpretation into certainty. The frequency of reports does not by itself prove they are well founded: independence of sources, pertinence and contrary evidence must be considered.

Incorrect information is flagged and stops supporting conclusions. The profile must be able to represent improvement, changes of context and later evidence, without turning an episode into a permanent label.

## 8. Confidential observations and right of reply

The sources report this agreement (M03 §3.1; C01 point 2): authorized contributors may provide observations at any time, including on specific assignments; the AI may request targeted observations on pertinent professional activities and behaviors, without being limited to periodic reviews or to the direct manager; the AI knows the authors' identity in order to distinguish independent reports from repetitions, but no human user — including managers, Admin, validator, Pino or Shelbi — accesses individual observations or discovers their authors. P01 §§6–6.2 explicitly extends the raw-contribution restriction to Admin and validator; an ordinary configuration permission must not silently override it.

What is shared are critical issues supported by workplace facts and non-identifying summaries, never the original comments, quotations or details that make the contributor recognizable. Unsupported concerns remain "to verify". The AI explores situations constructively and recognizes unfounded reports, rather than seeking confirmation only. The person can reply, correct and provide evidence; human review precedes any use in decisions.

This is a functional condition to be demonstrated, not a guarantee already obtained. Access, summaries, exports, logs, copies and administrative tools must respect it (G10). The People observation regime must not be confused with that of Organization interviews.

## 9. Validation and decisions

The People specification proposes a confidential preliminary profile for a validator (P01 §8): conclusions, pertinent facts, supporting and contrary elements, uncertainty and further investigation needed. The validator may confirm, correct, reject or request checks, without access to original comments and authors.

Shelbi's initial designation is a proposal in the sources, not an authorization already granted (G14). Substantially modified conclusions require new validation. The sequence between the person's reply and validation (G13), the validator's scope and the operating mode of renewed review remain to be defined.

Organizational and personnel decisions remain with the competent, authorized people (see Organization). People offers knowledge for deciding; it does not automatically produce rankings, promotions, replacements or disciplinary judgments.

## 10. Development and relationships with other areas

The four functions of the earlier specification — understanding, assisting, developing and assessing (P01 §§1, 3) — are read through the boundary with Cognito (§2): People maintains professional knowledge, goals and evidence and leads the specialist reasoning about them; Cognito provides perception, language understanding and conversation, using the pertinent Domains and services.

| Area | Responsibility to preserve | Relationship with People |
|---|---|---|
| [Selection](../../Selection/README.md) | Candidate evidence and fit against the selection need; Selection leads its own specialist reasoning | Continuity of pertinent information, without indiscriminate transfers |
| [Performance](../../Performance/README.md) | Observed results, measures and context | Evidence for understanding capabilities and critical issues; result and causes stay distinct |
| [Training](../../TRAINING_SERVICE_001.md) | The training cycle already attributed to the Training service — formative activities and the checks it foresees. **Unchanged; not absorbed by People** | Development path and verification of application on the job |
| [Operational Knowledge](../../Operational%20Knowledge/README.md) | Retrievable operational knowledge | Content usable for support and learning |
| [Continuous Productivity Development](../../Continuous%20Productivity%20Development/README.md) | Productivity opportunities and comparison of interventions. **Mandate unchanged and distinct** | Information about the person; training is not the automatic answer to every problem |
| [Organization](../Organization/README.md) | Work design, roles, assignments and coverage; comparison of alternatives; decisions reserved to authorized people (formerly Workforce and Personnel Decisions) | Knowledge contribution, without absorbing decision authority or keeping a competing register |
| Business Domain | Technical content of the work | Knowledge and standards against which capabilities are contextualized |
| MyRF | Personal interface | Presentation of authorized information and interaction through Cognito |

This delimitation does not absorb or reclassify the Training service or Continuous Productivity Development. Practical contracts and the remaining overlaps — in particular the practical boundary of coaching and development with Training and Continuous Productivity Development — remain to be specified (G01, G28).

Requested assistance and coaching initiatives are covered by the sources, but thresholds, frequency, suspension and authorizations of autonomous initiatives remain proposals (P01 §§9, 12). Before an initiative, the objective, context and missing information, expected benefit, consequences, less intrusive alternatives, reversibility and authority must be evaluated. Verification must be proportionate to the consequences, not to the AI's confidence alone. Low-risk initiatives already permitted may proceed within authorized limits; those subject to approval must wait for it, and prohibited ones are blocked. These criteria come from the functional proposal P01, sections 9 and 12, and set no new operating thresholds.

Forming a judgment does not authorize an action. People does not modify its own authorizations, RFCore, Domain rules, official assessments, responsibilities or working conditions (P01 §12).

## 11. Identity, visibility and history

People links to the existing identities and accounts (P01 §4); no parallel personnel registry is created. A person's professional continuity does not imply mutual access to the data of different companies. The linking mechanism between Employee, Account, Acting Identity, Candidate and other contexts is not chosen here (see `../../PERSON_CONTINUITY_001.md`, Draft; G15).

Organization and Project Manager receive only the information necessary and authorized for the specific use. The full profile and confidential observations are not the default interface between Domains. Access to the People function does not equal access to all its data.

The sources report that professional history is retained while the relationship with the company lasts, subject to applicable obligations (P01 §7.1). Treatment after the relationship ends remains open (G11). The day-based evidence-relevance proposal (P01 §7.2) contains no approved formula; no automatic decay or score is introduced (G12). Current relevance does not change the historical fact.

The proposals of a single Management Admin and an emergency suspension delegate remain to be confirmed and connected to the existing Identity & Access mechanisms (`../CONFIGURATION_AND_MYRF.md`; G14). They grant no access to confidential observations.

## 12. First useful result

The initial result is a minimal, reliable profile of the managers, comparable with the requirements of processes: pertinent experience, knowledge and capabilities demonstrated or only declared, observed attitudes, contextualized critical issues, unobserved areas, contradictions and support needs.

This result must make it possible to answer a concrete question: for this process, what do we know about the person's capability, on what evidence, with what limits, and what support may be needed?

It does not first require a ranking engine, a temporal-relevance formula, the merging of identities across companies, or the full automation of Management.

## 13. Decisions still open

| Topic | Decision needed |
|---|---|
| Characteristics | Observable examples, acceptable evidence, application of the levels and of exclusions 13–14 (G20) |
| Profile sufficiency | When the evidence is enough for a specific organizational comparison (G06) |
| Confidentiality | Effective application of the agreement on every surface, and non-identifying summaries (G10) |
| Validation | Sequence with the person's reply, responsibilities and renewal of conclusions (G13) |
| Visibility | Information accessible to the person, the manager, the validator and other Domains (G23) |
| Identity | Links within a single context and authorized continuity across contexts (G15) |
| History | Retention, corrections, end of the relationship and temporal relevance (G11, G12) |
| Development | Practical boundaries with Training, Performance and Continuous Productivity Development (G01, G28) |
| Initiatives | Limits, authorizations, suspension and handling of support initiatives |
| User Model | Relationship between the Core User Model and the People profile (G27) |

The People–Cognito boundary has been clarified by the Product Owner. It does not automatically close every point of G01, which also covers the relationships with other Domains.

## 14. Traceability of definitions

| Content | Reference and status |
|---|---|
| People as a Management component, mandate (§1) and People–Cognito boundary (§2) | Product Owner decisions of 2026-10-25 — **approved** |
| Initial mandate on managers | Product Owner decision in the 2026-10-25 conversation recorded by v0.2 |
| Profile, observations and 17 characteristics | M03 §§3.1–3.4; C01 points 1–3 — reported agreements, application still to be specified |
| Interview, identity and evolving profile | P01 §§4–7, through the earlier People consolidation v0.1 — functional proposal |
| Confidentiality | M03 §3.1, C01 point 2 and P01 §§6–6.2 — reported agreement, application to be verified |
| Validation and renewal | P01 §8 and M03 §3.1 — proposed process and reported right of reply |
| Assistance, coaching and initiative criteria | P01 §§9, 12 — proposal, to be connected to the approved Cognito boundary |
| History and temporal relevance | P01 §§7.1–7.2 — retention during the relationship reported as agreed; temporal relevance proposed |
| Configuration and visibility | P01 §§10–11 and `../CONFIGURATION_AND_MYRF.md` — proposals and open decisions |
| Organizational exchanges | M03 §§3–5 and `../INTERFACES_AND_DEPENDENCIES.md` — functional references, contracts to be defined |

M03, P01 and C01 are identifiers of the `../SOURCES.md` register: respectively Management v0.3, People specification v0.1, and Shelbi's comments on Management v0.2. Traceability preserves the approval level of the sources.

## 15. Single reference and sources

This file is the single canonical functional reference for People. The Organization, Project Manager, Management and configuration documents describe their own relationships with People and point here, without reproducing its model. The general definition of Cognito remains in the Core; this file states its relationship with People and does not replace it.

The original sources remain historical and provenance evidence, with their own status. This consolidation authorizes no deletion of sources, no Core changes beyond those recorded in `00 Core/Core Evolution.md`, and no promotion of drafts to policy.

Sources used, kept in their own locations:

- `90 Archive/Superseded Documents/01 Domains/Shared Domains/Management/PEOPLE.v0.1-en-2026-10-24.md` and `PEOPLE.v0.2-it-2026-10-25.md` — the two earlier consolidations, preserved unchanged.
- [../CONFIGURATION_AND_MYRF.md](../CONFIGURATION_AND_MYRF.md) — configuration, validator, access and MyRF.
- [../DECISIONS_AND_GAPS.md](../DECISIONS_AND_GAPS.md) — approved decisions, reported agreements and open questions, in particular G01, G05–G06, G10–G15, G20, G23, G27–G28.
- [../INTERFACES_AND_DEPENDENCIES.md](../INTERFACES_AND_DEPENDENCIES.md), [../ARCHITECTURE.md](../ARCHITECTURE.md), [../Organization/README.md](../Organization/README.md), [../Project Manager/README.md](../Project%20Manager/README.md) and [../SOURCES.md](../SOURCES.md) — boundaries, links and provenance.
- `Models-Shelby & Pino/Models/Management/RF1_Management_Cross_Domain_v0.3_EN.md`, sections 1–3 (outside this repository) — primary Markdown source on profile, characteristics and reported agreements. The People specification PDF v0.1 is represented here through the earlier v0.1 consolidation, without attributing new approval to it.
- `00 Core/ConceptualArchitecture/10_RF-One_Intelligence_and_User_Relationship.md` and `14_Cognito_RF-One_Cognitive_Intelligence.md` — User Model and the transversal cognitive capacity, approved within their own scope.
