# Architecture and boundaries

**Status:** Source-backed reference; architecture reclassification remains proposed.  
**Sources:** M03 §§1–2, 7, 10; L02 §§1–5; P01 §§2, 10, 12; R01–R07 in SOURCES.md.

## Two different architectural views

M03 describes the functional chain **Legacy → RFCore → Management → MyRF**. L02 describes three **knowledge layers**: Legacy, Business Domain, Individual Business. P01 discusses Legacy and RFCore separately under its knowledge architecture. RFCore is not silently added as a fourth knowledge-storage layer: these source views describe reasoning responsibilities and knowledge classification from different angles.

| Element | Source meaning | Boundary |
|---|---|---|
| Legacy | Invariant principles used in reasoning | Not company preferences, amounts, named roles or screen formats |
| RFCore | Shared reasoning, uncertainty, controls, authority and autonomy constraints | Management cannot modify it or grant itself powers |
| Shared Domain Management | Applies the reference to people, organization and work | Remains reusable across industries; does not own all related domain knowledge |
| Business Domain | Industry defaults, competencies, typical roles, processes and measures | A default is not a mandatory rule for every company |
| Individual Business | Actual people, evidence, approved procedures, limits, exceptions and resources | Company configuration and data, not universal knowledge |
| MyRF / product presentation | Personal guidance and assigned-work interface | Screen/card/template format is not a knowledge layer |

## Classification rules

L02 §§2–4 and M03 §2 require one place per piece of knowledge. If a rule can change across valid management systems, it probably is not Legacy. Company deviation from an industry default records its reason. A company lesson becomes industry knowledge only after validation elsewhere and approval. Lower layers cannot contradict the invariant core.

Examples retained from M03 §2 and L02 §3:

| Principle | Restaurant default | Company configuration |
|---|---|---|
| Authority must be identifiable and coherent with responsibility | Typical GM/chef/FOH responsibilities | Named approvers, amounts and exceptions |
| Spending approved before commitment; no self-approval/checking | Typical purchasing controls | Crosswise purchase checks and written approval fields |
| Protect customer experience and reputation | Hospitality | “Hosted, not served” |
| Safety and compliance | Food safety, allergens, alcohol | Actual company rules and escalation recipients |

These are source classifications, **not changes to canonical Core files**. L02 is Draft 0.2; M03 §10 still asks to confirm it and approve reclassification. Continuous People Development as an explicit Legacy principle is specifically pending consolidation with Shelbi (P01 §2.1).

## Repository boundaries to preserve

| Existing area | Authority and consequence |
|---|---|
| `00 Core/` | Existing universal definitions remain authoritative. Legacy in these sources is not “legacy software” to replace. |
| `01 Domains/Shared Domains/` | Reusable domain knowledge. This folder documents Management without absorbing sibling domains. |
| `01 Domains/Business Domain/Restaurant/` | Existing industry concepts, role/area/employee-assignment definitions and technical content stay here. |
| `02 Products/` and company runtime configuration | Product configuration and company data are distinct from reusable domain knowledge. This task does not invent a company-configuration storage location. |
| `10 System/Identity & Access/` | Existing account, authority, delegation and visibility capability; structural freeze and consumption rules remain in force. |
| `10 System/Organizational Responsibility and Attention Management/` | Existing Position, occupancy, process-ownership and attention-routing foundation; not the Management discovery interview or MyRF. |
| `03 Software/` | Runtime. Documentation here makes no claim that Management behavior is implemented. |
| `08 External/` and external sibling working folder | Input/reference, never automatic RF-One authority. |
| `90 Archive/` | Historical, never current authority even if an archived file says “approved.” |

## Ownership decided and still open

**Decided by the Product Owner (2026-10-25, D01–D08 in [DECISIONS_AND_GAPS.md](DECISIONS_AND_GAPS.md)):** Management is a Shared Domain of People, Organization and Project Manager; Organization absorbs the former Workforce and Personnel Decisions responsibilities and Personnel Management is no longer a Domain; Compensation belongs to Administration; Cognito provides sensory functions, language understanding and conversation management, while People (and Selection in its field) leads specialist reasoning; the Training cycle and Continuous Productivity Development's mandate are unchanged.

**Still open:** the practical boundary of People's coaching and development with Training and Continuous Productivity Development (G28); People assessment versus Performance evidence and the "evaluations will live in Organization" decision recorded on another branch (G29); how Organization's responsibility proposals map onto the existing System Position foundation and Restaurant Employee Assignment (G02, G03, G32). These are **integration/ownership questions**, not authorization to redesign those areas. See also G04 and the dependency matrix.
