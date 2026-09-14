# Service Copilot

**Version:** 1.0
**Status:** Approved
**Module:** Restaurant Domain / Service Copilot
**Origin:** TASK_SERVER_PERFORMANCE_001

---

## Purpose

Server Performance understands, over time, how a Server performs. **Service Copilot** is the separate, closely connected capability that continuously assists the Server during real service. Its purpose is not to judge:

> Help the Server make the best next decision consistent with the Brand, the current table, the Server's individual capabilities, and the current service context.

---

## Why a separate module, not a submodule of Server Performance

```text
Server Performance   understands (Reality, over time)      → Individual Performance Profile
Service Copilot       acts / assists (in the moment)         → Next Best Action, Next Best Moment
```

Server Performance is retrospective/accumulative reasoning; Service Copilot is real-time decision support. Keeping them separate — while closely connected — mirrors the boundary already drawn between [Server Performance](../Server%20Performance/README.md) and the sibling [Continuous Productivity Development](../../../Shared%20Domains/Continuous%20Productivity%20Development/README.md) Shared Domains (which conceptually superseded the former Training placeholder): distinct responsibilities feeding one another, never merged (`01 Domains/Business Domain/Restaurant/Server Performance/Server Performance.md`, "Relationship to Continuous Productivity Development"). Service Copilot may also retrieve [Operational Knowledge Pills](../../../Shared%20Domains/Operational%20Knowledge/README.md) — a distinct, passive information-retrieval capability, never an intervention or a decision about whether one is needed.

---

## Module map

```text
Restaurant / Service Copilot
├── Service Copilot.md                              Before / During / After phases
├── Next Best Action and Next Best Moment.md         what to suggest, and when (or not) to interrupt
├── Management Intrusiveness.md                      configurable levels of Copilot autonomy
└── Smartwatch Interaction.md                        the envisioned primary interface — output + micro-input
```

---

## Inputs (what Service Copilot consumes, never owns)

```text
Brand Playbook                          Brand Expectation (Server Performance/Brand Expectation
                                          and Personal Baseline.md)
Dining Session Profile                   Dining Intelligence (../Dining Intelligence/Dining Session
                                          Profile.md)
Customer Consumption Profile             Dining Intelligence, when a guest is identified
                                          (../Dining Intelligence/Customer Consumption Profile.md)
products already ordered                 Sales (Order Item evidence)
open opportunities                       Server Performance/Opportunity Capture.md
individual Server performance profile    Server Performance/Individual Performance Profile.md
prior coaching outcomes                  Server Performance/Coaching Model.md
concurrent service load                  Server Performance/Concurrent Service Load.md
operational context                      Sales / Organization evidence
```

Service Copilot computes no consumption pattern itself (that is Dining Intelligence's responsibility) and makes no Personnel Decision itself (that remains Personnel Management's).

---

## Boundaries

Service Copilot is never responsible for table/floor assignment, floor optimization, section assignment, or host seating decisions — see [Server Performance/Exclusions.md](../Server%20Performance/Exclusions.md), which applies identically here. Service Copilot never autonomously decides employment outcomes. No recommendation engine, UI, mobile app, or smartwatch application is built by this task — see [Server Performance/Exclusions.md](../Server%20Performance/Exclusions.md), "No software, models, or schema."

---

## Related documents

- [../Server Performance/README.md](../Server%20Performance/README.md)
- [../Dining Intelligence/README.md](../Dining%20Intelligence/README.md)
- [../Server Performance/Exclusions.md](../Server%20Performance/Exclusions.md)
- `07 Tasks/Reports/TASK_SERVER_PERFORMANCE_001_REPORT.md` — task that created this module
- See also [00 Core/ConceptualArchitecture/16_Ambient_Operational_Context_and_In-Flow_Cognito_Assistance.md](../../../../00%20Core/ConceptualArchitecture/16_Ambient_Operational_Context_and_In-Flow_Cognito_Assistance.md) — status APPROVED — Post-Baseline Conceptual Extension, ratified by the Product Owner. It names, at Core level, the general pattern (Ambient Operational Context + In-Flow Cognito Assistance) of which Service Copilot is recognized as the **first Domain-level consumer instance**: Service Copilot remains this Restaurant Domain module, unchanged, unrenamed, and never merged into Cognito — this cross-reference does not redefine, extend, or require any change to this module's approved content or functional behavior.
