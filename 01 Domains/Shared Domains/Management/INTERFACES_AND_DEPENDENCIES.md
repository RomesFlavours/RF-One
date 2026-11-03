# Interfaces and dependencies

**Status:** Semantic reference only. No API, schema, event contract or implementation choice is approved.  
**Sources:** M03 §§1–8; P01 §§2–12; O01 §§7–9; R01–R09.

## Management handoffs

| Producer → consumer | Source-backed information | Gate / unresolved detail |
|---|---|---|
| Business Domain → Organization | Default processes, typical roles, competencies, industry measures | Default coverage/approved versions incomplete; not company obligation |
| Business Domain → People | Role-specific technical knowledge and approved procedures | Do not duplicate knowledge or adopt another domain's authority |
| People → Organization | Contextualized capabilities, support needs and uncertainty | Adequate profiles required before reasoned assignment; exact authorized projection open |
| Organization → Project Manager | Approved assignment, process/procedure reference, initial activities | Explicit approval; no automatic assignment from interview |
| Project Manager → MyRF | Responsible person's approved work and plan continuation; MyRF Project Management v1 (approved 2026-10-12, on `origin/main`) is the current planning tool | Assignment is not plan/spend approval; the v1 Responsible is a name only (G30) |
| Project Manager → People / Organization | Work, deliverables, verified outcomes, deviations and causes | Evidence, not automatic profile validation or role/rule changes |
| People → other Domains / MyRF | Necessary authorized contextual assistance/capability information | Exact recipients, fields and visibility unresolved; never raw observations/authors |
| Organization interviews → synthesis | Business accounts and attached sources | Separate from People assessment; confidentiality, retention and aggregation proposals apply |
| Company learning → Business Domain | Potential reusable lesson | Validation elsewhere and explicit promotion approval |

Each future contract must resolve source/reference/version, company/location context, person continuity, time, evidence versus interpretation, uncertainty, approval/validator identity and permitted recipients **where applicable**. This is a checklist of source requirements, not an invented mandatory message schema.

## Existing capabilities and boundaries

| Existing owner | Relevance | What must not be duplicated or inferred |
|---|---|---|
| Former Personnel Management (archived) | Workforce and Personnel Decisions are now Organization responsibilities (D03); the Domain no longer exists (D05) | Do not recreate a competing Domain; the archived text in `90 Archive/Superseded Documents/` is not authority |
| [Administration / Compensation](../Administration/Compensation/README.md) | Determines and approves what is owed (D06) | Management does not compose, approve or pay compensation; Payroll and the Payroll Provider handle processing and result acquisition |
| [Selection](../Selection/README.md) | Candidate evidence, fit and gaps | People profile is not a second selection engine or disconnected identity |
| [Performance](../Performance/README.md) | Observed production/evidence | People assessment does not redefine Performance or create universal KPI scores |
| [Continuous Productivity Development](../Continuous%20Productivity%20Development/README.md) | Gaps, intervention choice and outcomes — mandate unchanged (D08) | People includes coaching and development (D02) without absorbing intervention choice; resolve the practical handoff before implementing People (G28) |
| [Operational Knowledge](../Operational%20Knowledge/README.md) | Retrievable operational knowledge | Stores information; does not itself assess/train/certify |
| [Training service](../TRAINING_SERVICE_001.md) | Existing internal training-cycle reference — unchanged and not absorbed by People (D08) | Do not create a competing domain named Training; People links to the training cycle (D02) |
| [Person Continuity](../PERSON_CONTINUITY_001.md) | Same person across role/context changes | Draft continuity requirement does not choose a database identity mechanism |
| [Restaurant Organization](../../Business%20Domain/Restaurant/Organization/README.md) | Approved role/area/employee-assignment semantics | No replacement from interview testimony, POS roles or named-person draft models |
| [Identity & Access](../../../10%20System/Identity%20%26%20Access/README.md) | Accounts, grants, delegation, scope and audit | No independent identity/authority system; preserve structural freeze |
| [Organizational Responsibility and Attention Management](../../../10%20System/Organizational%20Responsibility%20and%20Attention%20Management/README.md) | Positions, occupancy, process ownership, attention routing | Not Management interview AI or MyRF delivery; configured backup differs from assignment second choice |
| [Core Cognito reference](../../../00%20Core/ConceptualArchitecture/14_Cognito_RF-One_Cognitive_Intelligence.md) | Existing cognitive-intelligence definition; §9 records the 2026-10-25 boundary: Cognito provides sensory functions, language understanding and conversation management | People leads specialist reasoning and decides what to explore (D07); People does not replicate Cognito's capabilities, and Cognito does not take over People's reasoning |
Runtime behavior is not audited or changed in this package. Existing foundation READMEs describe implemented services and limitations; their historical “currently” statements are not independently re-certified here. Management's integrations remain to be specified and approved.

## Explicitly undefined

No endpoints, table names, background schedules, persistence strategy, observation encryption mechanism, identity-linking algorithm, model/provider selection, notification channel, numeric decay formula, automatic conflict resolver, approval matrix or escalation chain is established here. Use the issue register rather than filling these gaps during development.
