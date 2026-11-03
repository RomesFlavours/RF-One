# Management Shared Domain

**Version:** 0.2
**Prepared:** 2026-10-24 · **Reorganized:** 2026-10-25
**Status:** **Domain structure approved by the Product Owner (2026-10-25)** — Management is a Shared Domain made of People, Organization and Project Manager, and absorbs the responsibilities of the former Personnel Management modules Workforce and Personnel Decisions. The detailed content of each component keeps the status stated in its own document; it is a source-backed reference, not an approved implementation specification.
**Module:** Domain / Management (Shared Domain)

---

## Purpose

Management is the industry-independent Shared Domain for knowing the people who do the work, designing the work they do, and planning, executing and verifying the work that has been approved. It is the single canonical location for these responsibilities in `01 Domains/`.

| Component | Mandate (approved 2026-10-25) | Reference |
|---|---|---|
| **People** | Continuous professional knowledge of the person: capability, experience, evidence, confidential observations, coaching and development; link with Training | [People/README.md](People/README.md) |
| **Organization** | Design of work: processes, functions, roles, responsibilities, authority, role coverage and assignments. Absorbs the former **Workforce** and **Personnel Decisions** responsibilities | [Organization/README.md](Organization/README.md) |
| **Project Manager** | Planning, execution and verification of approved assignments | [Project Manager/README.md](Project%20Manager/README.md) |

Management Configuration supports these components; MyRF is the personal interface, not a fourth component ([CONFIGURATION_AND_MYRF.md](CONFIGURATION_AND_MYRF.md)).

## Structure

```text
Shared Domains/Management/
├── README.md                       this file — Domain entry point
├── People/README.md                component
├── Organization/README.md          component (includes former Workforce and Personnel Decisions)
├── Project Manager/README.md       component
├── ARCHITECTURE.md                 knowledge layers and repository boundaries
├── CONFIGURATION_AND_MYRF.md       Management Configuration and MyRF (proposals)
├── INTERFACES_AND_DEPENDENCIES.md  handoffs with other Domains and System capabilities
├── DECISIONS_AND_GAPS.md           approved decisions, reported agreements, open questions
├── SOURCES.md                      source register and authority
└── SOURCE_MANIFEST.json            source fingerprints (integrity, not approval)
```

## What Management is not

- **Not a replacement for other Shared Domains.** Selection, Performance, Continuous Productivity Development and Operational Knowledge remain independent Shared Domains. The training cycle remains with the Training service (`../TRAINING_SERVICE_001.md`), not absorbed by People. Continuous Productivity Development keeps its distinct mandate of productivity improvement and comparison of interventions.
- **Not Compensation.** Compensation belongs to Administration ([../Administration/Compensation/README.md](../Administration/Compensation/README.md)): it determines and approves what is owed, while Payroll and the Payroll Provider handle processing and result acquisition.
- **Not a new register.** Management does not introduce a new registry of people, roles, assignments or authority. It preserves and links the existing semantics of Restaurant Employee Assignment, the System Position/occupancy foundation and Identity & Access ([Organization §3](Organization/README.md)).
- **Not Cognito.** Cognito provides sensory functions, language understanding and conversation management; People (and Selection in its field) leads the specialist reasoning ([People §2](People/README.md)).

## Former Personnel Management

The Personnel Management Domain no longer exists as a Domain (Product Owner decision, 2026-10-25):

| Former location | Now |
|---|---|
| `Shared Domains/Personnel Management/Workforce/` | Management / Organization §3 |
| `Shared Domains/Personnel Management/Personnel Decisions/` | Management / Organization §4–§5 |
| `Shared Domains/Personnel Management/Compensation/` | `Shared Domains/Administration/Compensation/` |
| `Shared Domains/Personnel Management/README.md` | Purpose, loop, expected-value comparison and KPI principle consolidated into Organization §1, §4 and §12 |

The original Personnel Management documents are preserved unchanged, with a supersession note, in `90 Archive/Superseded Documents/01 Domains/Shared Domains/Personnel Management/`.

## Status vocabulary

- **APPROVED-PO:** explicitly approved by the Product Owner, with date (e.g. the 2026-10-25 Domain structure and component mandates).
- **APPROVED-REPOSITORY:** an existing canonical repository document explicitly marks its own content approved. Approval is limited to that document's scope.
- **REPORTED-AGREED:** a source explicitly reports agreement. This package preserves that report and its date; it does not independently certify a signed approval.
- **PROPOSED / PENDING-SHELBI:** draft behavior or a proposed change requiring review, including consolidation with Shelbi where the source says so.
- **OPEN / CONFLICT / MISSING:** no decision established, incompatible source statements, or unavailable referenced material.

A document can contain all these states. A later date, an English translation, a file in the repository or an AI summary does not approve it. Every substantive section cites source IDs and sections/pages; resolve IDs in [SOURCES.md](SOURCES.md).

## Reading order for Claude

| Order | File | Purpose |
|---|---|---|
| 1 | [SOURCES.md](SOURCES.md) | Source IDs, original locations, integrity and approval interpretation |
| 2 | [ARCHITECTURE.md](ARCHITECTURE.md) | Legacy, RFCore, Business Domain, Individual Business and repository ownership |
| 3 | [People/README.md](People/README.md) | Professional knowledge, Cognito boundary, confidentiality and validation |
| 4 | [Organization/README.md](Organization/README.md) | Design, approved assignments and coverage, comparison of alternatives, reserved decisions, discovery |
| 5 | [CONFIGURATION_AND_MYRF.md](CONFIGURATION_AND_MYRF.md) | Configuration, authority, visibility and suspension proposals |
| 6 | [Project Manager/README.md](Project%20Manager/README.md) | Two approvals, execution, evidence, verified outcomes, MyRF Project Management |
| 7 | [INTERFACES_AND_DEPENDENCIES.md](INTERFACES_AND_DEPENDENCIES.md) | Semantic handoffs and existing capabilities to reuse |
| 8 | [DECISIONS_AND_GAPS.md](DECISIONS_AND_GAPS.md) | Approved decisions, agreements, proposals, contradictions, missing sources and blockers |

## Instructions for subsequent development

This is the **reference layer only**. Next, define practical behavior starting with People and ending with Project Manager; implement only under separately approved development instructions, again starting with People.

Do not infer schemas, APIs, numeric scores, decay formulas, authority grants, UI flows or escalation policies from this package. Resolve the relevant gaps first. Preserve facts, self-reports, observations, interpretations, proposals, validation and approval as distinct states. Preserve source provenance, applicable company context and temporal context.

Do not rewrite Legacy/RFCore, create a parallel identity/authorization mechanism, promote drafts to policy, copy confidential input into general domain knowledge, turn information collected to assist a person into automatic assessment evidence, or automatically change assignments. Read existing canonical documents before specifying integrations. No software, migrations, commit or push is authorized by this documentation.

## Source availability

The main working sources are in the sibling folder `Models-Shelby & Pino/`, outside this Git repository. Relative links work in the current OneDrive layout; a checkout by itself will not include those sources. The manifest records exact paths and hashes so missing or changed evidence is visible. No source was moved, edited or duplicated.

## Related documents

- [../../README.md](../../README.md) — `01 Domains/` index
- [../../Domain Architecture.md](../../Domain%20Architecture.md) §4–§5 — taxonomy and the Management reorganization
- [../Administration/Compensation/README.md](../Administration/Compensation/README.md) — Compensation (Administration)
- [../Selection/README.md](../Selection/README.md), [../Performance/README.md](../Performance/README.md), [../Continuous Productivity Development/README.md](../Continuous%20Productivity%20Development/README.md), [../Operational Knowledge/README.md](../Operational%20Knowledge/README.md), [../TRAINING_SERVICE_001.md](../TRAINING_SERVICE_001.md) — related Shared Domains and services
