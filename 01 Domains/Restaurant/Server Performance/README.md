# Server Performance

**Version:** 1.0
**Status:** Approved
**Module:** Restaurant Domain / Server Performance
**Origin:** TASK_SERVER_PERFORMANCE_001

---

## Purpose

**Server Performance** is Restaurant's technical/operational specialization of Personnel Management's generic [Performance](../../Personnel%20Management/Performance/README.md) module, applied to the Server role. It exists to:

> Understand each Server as an individual performer, identify strengths and unrealized opportunities, help that person improve, and learn which interventions actually work for that specific person.

It does **not** exist primarily to rank Employees. See [Server Performance.md](Server%20Performance.md) for the full purpose statement and the canonical Performance Loop.

This module does not begin from "what data does Clover give us and what metrics can we calculate." It begins from what good Server performance means for the Brand, then works backward to evidence — Clover included — only once the concept is defined. See [KPI Framework.md](KPI%20Framework.md), "KPI design principle."

---

## Naming and boundary — why this is not `Personnel Management/Performance/`

`01 Domains/Personnel Management/Performance/` is a **transversal, cross-industry** module: it defines Performance, Performance Evidence, Performance Measure, Performance Indicator and Performance Context in a way that must remain valid for any role in any industry, and explicitly states "No Restaurant-specific Performance file is created by this module" (`Personnel Management/Performance/README.md`, "Restaurant as first validation").

`Server Performance` is the opposite: it is genuinely Restaurant-specific technical/commercial content — Quality of Sale tied to the Commercial Catalog, Opportunity Capture tied to Dining Sessions, Concurrent Service Load tied to Table Service, a Service Copilot that operates during live restaurant service. This is exactly the pattern already established for Restaurant's relationship to every transversal Domain (`01 Domains/Domain Architecture.md` §2): *"Restaurant supplies its own technical content as an input to the transversal Domain that owns that capability — it does not own the capability itself."*

```text
Personnel Management / Performance   (transversal — HOW to reason about any role's Performance:
                                       Evidence / Measure / Indicator / Context)
                ↑ supplies technical content, consumes the reasoning structure
Restaurant / Server Performance      (Restaurant-specific — WHAT good Server performance means,
                                       WHICH dimensions matter, WHICH evidence a restaurant produces)
```

Concretely:

- Every **Server Performance Evidence item** documented here (a wine-conversion opportunity, a concurrent-table count, a QR-survey response) *is* a [Performance Evidence](../../Personnel%20Management/Performance/PerformanceEvidence.md) item in the generic sense — this module does not redefine the Evidence/Measure/Indicator/Context epistemic structure, it populates it with Restaurant content.
- Every **Server Performance KPI family** ([KPI Framework.md](KPI%20Framework.md)) is a set of candidate [Performance Measures](../../Personnel%20Management/Performance/PerformanceMeasure.md), some of which may become [Performance Indicators](../../Personnel%20Management/Performance/PerformanceIndicator.md) when a Goal makes them relevant — never a permanent scored KPI list.
- [Brand Expectation and Personal Baseline.md](Brand%20Expectation%20and%20Personal%20Baseline.md) *is* [Performance Context](../../Personnel%20Management/Performance/PerformanceContext.md), specialized for the Server role.
- This module does **not** redefine Personnel Management's Selection, Workforce, Training or Personnel Decisions modules, and does not decide retain/develop/move/replace — that remains [Personnel Decisions](../../Personnel%20Management/Personnel%20Decisions/README.md)'s exclusive authority (see [Exclusions.md](Exclusions.md)).

`01 Domains/Restaurant/Roadmap.md` §3 ("Workforce / Personnel") previously recorded "No Restaurant Product capability is created now" for this area. TASK_SERVER_PERFORMANCE_001 is the Product Owner decision that supersedes that specific line for Server Performance/Service Copilot/Dining Intelligence — see the Roadmap update this task made.

---

## Module map

```text
Restaurant / Server Performance
├── Server Performance.md                        purpose, Performance Loop, dimension overview, epistemic discipline
├── Brand Expectation and Personal Baseline.md    the dual-benchmark model
├── Individual Performance Profile.md             what RF-One learns about one Server over time
├── Quality of Sale.md                            what was sold, not just how much
├── Opportunity Capture.md                        available vs. captured opportunity per Dining Session
├── Concurrent Service Load.md                    Capacity / Acceleration / Resilience under load
├── Perceived Service Quality.md                  guest-perceived quality; Tips as evidence; QR Survey
├── Coaching Model.md                             recognition + economic motivation + personalization + effectiveness loop
├── KPI Framework.md                              KPI design principle and the KPI families
├── Evidence Sources.md                           Source Evidence vs. Canonical Interpretation vs. Inference
├── Exclusions.md                                 what this module explicitly does not do
└── Future Development.md                         Judgment / Customer Reading (not implemented)
```

Closely related, sibling Restaurant modules:

- [Service Copilot](../Service%20Copilot/README.md) — real-time in-service assistance fed by Server Performance; a separate capability, not a submodule of Server Performance (see [Server Performance.md](Server%20Performance.md), "Relationship to Service Copilot").
- [Dining Intelligence](../Dining%20Intelligence/README.md) — the shared consumption-understanding module Server Performance and Service Copilot both consume, without owning it.

---

## Relationship to other Domains

```text
Sales                → canonical factual Reality (Order, Order Item, Payment, Tip, Refund, Void, business_date)
Organization          → canonical Employee, Restaurant, Location, Restaurant Role, Employee Assignment
Tips                  → realized Tip Allocation as Service Quality evidence, service-attribution boundary
Commercial Catalog    → Item/category/modifier structure Quality of Sale is measured against
Dining Intelligence   → Dining Session Profile / Customer Consumption Profile, consumed not owned
Personnel Management  → Performance (reasoning structure), Training (development), Personnel Decisions (final decision authority)
Payroll                → NOT consumed here; Tip-based economic estimates are illustrative motivation only, never a Payroll input (see Exclusions.md)
```

Server Performance creates no competing Sales model, no competing Organization model, and no competing Tips model — it consumes each Domain's already-canonical facts and derives Performance-specific evidence, measures and indicators from them (see [Evidence Sources.md](Evidence%20Sources.md)).

---

## Related documents

- [../../Personnel Management/Performance/README.md](../../Personnel%20Management/Performance/README.md) — the generic Performance module this specializes
- [../Service Copilot/README.md](../Service%20Copilot/README.md)
- [../Dining Intelligence/README.md](../Dining%20Intelligence/README.md)
- [../Tips/README.md](../Tips/README.md), [../Organization/README.md](../Organization/README.md), [../Sales/Restaurant Sales Model.md](../Sales/Restaurant%20Sales%20Model.md), [../Commercial Catalog/README.md](../Commercial%20Catalog/README.md)
- [../Roadmap.md](../Roadmap.md)
- `07 Tasks/Reports/TASK_SERVER_PERFORMANCE_001_REPORT.md` — task that created this module
