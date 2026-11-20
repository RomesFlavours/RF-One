# Decisions, contradictions and open issues

**Prepared:** 2026-10-24 · **Updated:** 2026-10-25 (Management reorganization). This register records decisions; it does not itself approve any.  
**Sources:** Resolve IDs in SOURCES.md. “Next review” identifies needed review, not an authority grant.

## Product Owner decisions approved on 2026-10-25

These decisions were given explicitly by the Product Owner in the reorganization instruction of 2026-10-25. They are the only items of this register approved by that instruction; every other row below keeps its own status.

| ID | Decision | Applied in |
|---|---|---|
| D01 | Management is a Shared Domain made of **People**, **Organization** and **Project Manager** | [README.md](README.md); `01 Domains/README.md`; `Domain Architecture.md` §4; `CLAUDE.md` |
| D02 | **People:** continuous professional knowledge of the person — capability, experience, evidence, confidential observations, coaching and development; link with Training | [People/README.md](People/README.md) §1 |
| D03 | **Organization:** design of work, processes, functions, roles, responsibilities, authority, role coverage and assignments. It absorbs the responsibilities formerly named **Workforce** and **Personnel Decisions**, preserving their useful content | [Organization/README.md](Organization/README.md) §1–§5 |
| D04 | **Project Manager:** planning, execution and verification of approved assignments | [Project Manager/README.md](Project%20Manager/README.md) §1 |
| D05 | **Personnel Management ceases to be an autonomous Domain**; it is not kept as a competing Domain | Archived to `90 Archive/Superseded Documents/01 Domains/Shared Domains/Personnel Management/` |
| D06 | **Compensation belongs to Administration.** Compensation determines and approves what is owed; Payroll and the Payroll Provider handle their own processing and result acquisition. No economic rule or software behavior changes | `Shared Domains/Administration/Compensation/` |
| D07 | **Cognito** provides sensory functions, language understanding and conversation management. **People and Selection** lead the specialist reasoning in their fields; People decides what to explore and for which professional purpose. Specialist reasoning is not re-attributed to Cognito | [People/README.md](People/README.md) §2; `00 Core/ConceptualArchitecture/14_Cognito_RF-One_Cognitive_Intelligence.md` §9 |
| D08 | The training cycle already attributed to **Training** is unchanged and not absorbed by People; **Continuous Productivity Development** keeps its distinct mandate (productivity improvement, comparison of interventions) | [People/README.md](People/README.md) §10 |

## Approved repository baseline

| ID | Established baseline | Evidence / limit |
|---|---|---|
| B01 | Shared Domains and Business Domain are separate families; reuse existing canonical owners | R01–R02; does not approve every new Management proposal |
| B02 | Restaurant organizational role/area/assignment semantics | R05 explicitly Approved v1.0; scope remains Restaurant |
| B03 | System identity/authority infrastructure is shared; structural freeze preserved | R06; approved consumption is distinct from redesign |
| B04 | Existing Position/ownership/attention foundation remains system-level | R07; not an approved Management integration |

## Agreements reported in sources

| ID | Reported agreement | Evidence and qualification |
|---|---|---|
| A01 | 17 characteristics, in principle, 21 October | M03 §3.2; C01 point 1. Examples/evidence still await approval |
| A02 | Confidential People observations compromise, 21 October | M03 §3.1; C01 point 2. Enforcement must be validated before release |
| A03 | Responsibility-based consultant assessment; exclusions 13–14 | M03 §3.3; C01 point 3 |
| A04 | No self-approval/checking, other-person purchase checks | M03 §5.2; C01 point 4. Exact check timing remains open |
| A05 | Written spending approval fields, 20 October | M03 §5.2; C01 point 5. Company configuration |
| A06 | Assigned processes/projects list in MyRF | M03 §6. Detail and visibility remain open |
| A07 | Three knowledge layers agreed in principle, 23 October | M03 §10; L02 still Draft 0.2 awaiting confirmation/reclassification |
| A08 | Professional history retained while person remains with company | P01 §7.1 calls this agreed; P01 as a whole is proposed consolidation, with obligations/post-departure handling unresolved |

These reports are preserved without presenting the complete drafts as approved specifications.

## Proposals awaiting review

P01's continuous coaching, autonomous initiatives, day-based relevance, configuration page, single Admin, emergency delegate and initial Shelbi-validator designation remain **PROPOSED** under its cover status. Making Continuous People Development explicit in Legacy is specifically **PENDING-SHELBI** (P01 §2.1).

Organization interview/pilot details, governance **AI → Shelbi → Pino**, reference-version approvals, 30-day Project Manager trial, daily briefs/integration and detailed MyRF outputs remain proposed/open in M03 §§4–10. O01's review sequence does not independently grant those authorities.

## Gaps and contradictions

| ID / type | Evidence and issue | Consequence / next review |
|---|---|---|
| G01 PARTIALLY RESOLVED / ownership | P01 §§1,3,9–10 expands People to continuous assistance/training/relational intelligence; R04/R08/R09 already define Personnel Decisions, Performance, development, Training and Cognito. **2026-10-25:** People's mandate (D02), the absorption of Personnel Decisions into Organization (D03) and the People–Cognito boundary (D07) are decided; Training and CPD stay unchanged (D08) | Remaining: practical handoffs with Training, Performance and Continuous Productivity Development (G28); do not merge domains |
| G02 PARTIALLY RESOLVED / ownership | M03 §4 Organization vs R04 Workforce and R05 Restaurant assignments. **2026-10-25:** Workforce is absorbed into Organization (D03) | Remaining: define discovery/proposal versus the existing approved occupancy records (Restaurant Employee Assignment, System Position Assignment) without a new register (G03, G32); preserve approved Restaurant semantics |
| G03 OPEN / integration | M03 §5 vs R07 existing Position/process ownership/attention foundation | Specify reuse/mapping; no duplicate organizational registry or automatic notifications |
| G04 OPEN / architecture | L02's knowledge taxonomy vs P01 §2 separate RFCore discussion; Legacy reclassification not confirmed | Confirm model mapping without editing Core/Legacy or relocating definitions |
| G05 PENDING-SHELBI | P01 §2.1 Continuous People Development as explicit Legacy principle | Consolidate with Shelbi and obtain required approval; no Core addition now |
| G06 OPEN / adequacy | M03 §§4.7–4.8 requires adequate People profiles before assignment; no adequacy criterion | Define usable evidence/validation and handling of unknowns; no objective-optimality claim |
| G07 CONFLICT / questions | O01 §5 includes 10–11; M03 §§4.2,10 calls them proposed | Confirm final core question set; no fabricated interview v0.2 |
| G08 CONFLICT / pilot | O01 §§3,11 and C02 say ~45 minutes; M03 §§4.2,9 ~30; deadlines differ in specificity | Confirm duration, dates, participants, paid time and technical capabilities |
| G09 CHANGE-PENDING | O01 question 6 is open discovery; M03 §4.2 requires default-led confirmation and mentions a future v0.2 | Approve updated wording/default coverage without silently editing v0.1 |
| G10 OPEN / confidentiality | P01 §6 forbids Admin/validator raw observation access; M03 §3.1 forbids any human access; O01 §7 allows own-answer access and conditional aggregation | Specify and validate two distinct confidentiality regimes, non-identifying summaries and all access surfaces before release/pilot |
| G11 OPEN / retention | O01 §7 raw interview deletion period unspecified; P01 §7.1 retains professional history and leaves post-departure handling undefined | Define separate retention/correction rules, including derived information and applicable obligations; do not apply People retention to Organization raw answers |
| G12 TENSION / temporal relevance | M03 §3.2 no numeric characteristic weights/scores; P01 §7.2 differentiated day-based evidence weights | Clarify evidence relevance versus assessment scoring; no decay formula/parameter invented |
| G13 OPEN / validation order | M03 §3.1 person can respond and human reviews before decision use; P01 §8 describes validator then conversation/revalidation | Define exact response, validation and decision-use gates; do not treat validation as factual certainty |
| G14 PROPOSED / authority | P01 §§8,11 single Admin, Shelbi validator, emergency delegate; R06 existing scoped authority and freeze | Confirm identities, scope, delegation, suspension/recovery, audit/notification and limits without new independent authority |
| G15 OPEN / identity isolation | P01 §4 unique profile across companies/domains, separate permissions; R03 identity mechanism undecided | Define authorized cross-context continuity without merging confidential company data |
| G16 MISSING / reference versions | M03 §§4.6,5.6 cites Organization Model 0.4, Manager Model 0.2, Procedure 001 v0.3 and 33 scenarios v1.1. Organization Model 0.4, Manager Model 0.2 and scenarios v1.1 were not located. **Correction 2026-10-25:** a file named "Procedure 001 - FOH Supplies and Glassware - Draft 0.3 - Shelbi Fox.pdf" is in SOURCE_MANIFEST.json as "located and fingerprinted only; not substantively reviewed" — the earlier "not located" wording was inaccurate for that one file | Obtain/identify the missing originals and the actual approval evidence of all four. A located file is not evidence of approval; earlier files are not replacements or an approved acceptance suite |
| G17 CONFLICT / checking | L02 §4 says “check before, not after”; M03 §5.2 keeps purchase-check timing open; O02 §6.7 allows some “decide and record” spending | Clarify approval vs verification timing and authority; no inferred thresholds or universal policy |
| G18 CONFLICT / stages | O02 §6.8 includes Thinking/Proposal/Decision/Operational Rule; M03 §5.3 has thinking/proposal/decision | Confirm intended stage set and visibility/version/change semantics |
| G19 OPEN / PM controls | M03 §§5.5–5.6 checkpoints, autonomy, task approvals, warnings, reporting, escalation and trial unconfirmed | Approve practical behavior and acceptance sources before implementation or pilot |
| G20 AMBIGUOUS / assessment scope | M03 §3.3 says anyone managing/guiding others uses 1–12,15–17; phrasing centers consultants but may encompass employees | Confirm who is excluded from 13–14, and scope for other workers; do not broaden by assumption |
| G21 OPEN / governance | O01 §9 gives AI/Shelbi/Pino sequence; M03 §§7,10 explicitly calls it proposed | Confirm conflict resolver and process/assignment/plan/layer-change authorities; no automatic Shelbi reporting line |
| G22 OPEN / defaults | M03 §9 needs approved domain defaults for scope; L02 lists candidate defaults but not complete approved content | Inventory/approve usable Restaurant defaults; do not manufacture industry rules |
| G23 OPEN / MyRF | M03 §§6,10; P01 §§10–11 exact outputs, recipients, visibility and cadence unspecified | Define minimum authorized views and coaching/suspension interaction |
| G24 SOURCE / portability | Main sources live outside RF-One Git; prior-chat assistant replies are reference placeholders | A standalone checkout lacks original evidence; arrange source access before development. Do not infer missing conversation answers |
| G25 OPEN / model reclassification | O02 includes coordination/control/backup structures; M03 §5.5 assumes no centralized controller; L02 proposes splitting model across layers | Confirm actual company choices and approved versions; named-person proposals remain input |
| G26 OPEN / communication | M03 §§6,10 daily briefs/tags and A.T.G.S. integration await confirmation | Do not implement a fourth component or send messages from a proposed agreement |
| G27 OPEN / User Model | Core 10 §4–§8 defines a User Model ("who is managing the business"), with dimensions such as people-management judgment and analytical capability; Core 15 §3 extends "stable person knowledge" to any person Cognito interacts with; People now owns professional knowledge (D02) | Specify the relationship between the User Model / interaction knowledge and the People profile without duplicating or merging them automatically |
| G28 OPEN / development boundaries | People includes coaching and development (D02); the training cycle stays with Training and CPD keeps intervention choice (D08) | Define the practical handoff: when People's coaching ends and a Training cycle or a CPD intervention begins, and which evidence returns to People |
| G29 CONFLICT / evaluations | `origin/main` (not this checkout) records in `10 System/Organizational Responsibility and Attention Management/README.md`: "Organization is where evaluations will live (decided 2026-10-12)", attached to RF-One Web's ORGANIZATION access code. People organizes professional conclusions and validation (People §7, §9); Organization holds the comparison of alternatives and reserved decisions (Organization §4–§5) | Product Owner to state which "evaluations" that decision meant, and how they divide between People (professional knowledge and validation) and Organization (decisions about the person in the role). Not resolved by this reorganization |
| G30 OPEN / responsible identity | MyRF Project Management v1 (on `origin/main`) records the Task Responsible as "only a name", not linked to any person record; Project Manager works on approved assignments of identified responsible people | Decide whether and how the Responsible links to Position, Employee or Account — without a new register |
| G31 OPEN / MyRF placement | MyRF Project Management v1 lives under `Business Domain/Restaurant/MyRF/` "only because MyRF does today"; its document is not in this checkout | When branches are reconciled, add a reciprocal reference from that document to Management / Project Manager, and decide whether MyRF stays a Restaurant module or becomes the presentation of Shared capabilities |
| G32 CONFLICT / concurrent assignments | Approved `Restaurant/Organization/Employee Assignment.md` (TASK_ORGANIZATION_002) permits concurrent Assignments, e.g. the same Employee at Winter Park and Mount Dora; the runtime index `ux_employee_assignments_one_active_role_per_restaurant` allows one open Assignment per Employee per Restaurant | Product Owner to confirm one rule; then align either the document or the code (code change outside this documentation task). Organization §3 reads existing records and does not resolve this |
| G33 OPEN / branch divergence | This reorganization was applied to checkout `handoff/2026-10-17`, 37 commits behind `origin/main`. Files touched here are identical to `origin/main` except `CLAUDE.md`, which differs; MyRF Project Management and the newer System README exist only on `origin/main` | Carry the reorganization onto the `origin/main` line when the branch is reconciled; merge `CLAUDE.md` by hand |
| G34 OPEN / code comments | Comments and docstrings in `03 Software/RF-One Data Store/` (e.g. `models.py`, `payroll_calculation/*.py`, `legal_entity_service.py`, `selection/core/*.py`, three migration docstrings) still cite `Shared Domains/Personnel Management/...` paths. Nothing reads these paths at runtime | Update in a separately authorized code task; no application code was changed by this reorganization |

## Next layers of work

First review this reference package and resolve source availability/status. Then define practical People behavior against the relevant gaps, followed by the other Management behavior, ending with Project Manager. Only after separate approval should implementation begin, starting with People. Unresolved issues stay visible; no missing policy is delegated to Claude to invent.
