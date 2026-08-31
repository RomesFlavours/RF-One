# TASK_SERVER_PERFORMANCE_001 — Redefine Server Performance & Service Copilot — Report

**Origin:** TASK_SERVER_PERFORMANCE_001
**Type:** Domain / conceptual architecture documentation only — no software, schema, migrations, or applications were built.

---

## A. Executive summary

Server Performance is redefined, purpose-first: RF-One first defines what good Server performance means for the Brand, understands each Server individually, identifies opportunities, coaches, and only then uses evidence (including Clover) to observe and learn — never the reverse. Server Performance does not exist to rank Employees; it exists to understand each Server as an individual performer against two simultaneous benchmarks (Brand Expectation and Personal Baseline), across five dimensions (Productivity, Quality of Sale, Opportunity Capture, Operational Discipline, Perceived Service Quality), under a first-class Concurrent Service Load context variable, closing a continuous coaching learning loop. Two closely related but distinct capabilities are documented alongside it: **Service Copilot** (real-time in-service assistance) and **Dining Intelligence** (a shared, non-owned consumption-understanding module). All three are new Restaurant Domain modules — `01 Domains/Restaurant/Server Performance/`, `Service Copilot/`, `Dining Intelligence/` — deliberately kept separate from, and consistent with, the pre-existing generic, cross-industry `Personnel Management/Performance/` module.

---

## B. Previous model versus new model

The pre-existing `Personnel Management/Performance/` module (Performance, PerformanceEvidence, PerformanceMeasure, PerformanceIndicator, PerformanceContext) was already well-developed and **is preserved unchanged** — it is the correct home for the generic, cross-industry Evidence/Measure/Indicator/Context reasoning structure, and explicitly states no Restaurant-specific Performance file should be created inside it. Nothing in it was compatible-but-incomplete for Server Performance's actual scope; it was simply the wrong location for genuinely Restaurant-specific content (Quality of Sale tied to the Commercial Catalog, Concurrent Service Load tied to Table Service, Service Copilot, Dining Intelligence).

What changed:

- **New location, not a redesign of the old one.** A new sibling set of Restaurant Domain modules (`Server Performance/`, `Service Copilot/`, `Dining Intelligence/`) was created under `01 Domains/Restaurant/`, specializing — never redefining — the generic Performance module.
- **From KPI-first to purpose-first.** No prior Restaurant-specific KPI list existed to correct; this task establishes the purpose-first ordering (purpose → dimensions → benchmarks → evidence → KPI) as the canonical starting point going forward.
- **New concepts with no prior equivalent:** Concurrent Service Load, Capacity/Acceleration/Resilience, Opportunity Capture (available vs. captured), Service Copilot (Before/During/After, Next Best Action, Next Best Moment, management-controlled intrusiveness, smartwatch), Dining Intelligence (Dining Session Profile, Customer Consumption Profile, Food/Drink Correlations), Estimated Cash Tips epistemic rule, Judgment/Customer Reading (future).
- **`Roadmap.md` §3's "No Restaurant Product capability is created now"** for Workforce/Personnel is explicitly updated for the Server-Performance-specific case, per this task's Product Owner authorization (see Section T for the exact edit).

No existing approved concept was discarded. `Personnel Management/Performance/README.md` was updated with one forward pointer to the new specialization; nothing in its own five files was rewritten.

---

## C. Purpose

Server Performance exists to understand each Server as an individual performer, identify strengths and unrealized opportunities, help that person improve, and learn which interventions actually work for that specific person — not primarily to rank Employees. RF-One does not infer unsupported psychological, health, relationship, hormonal, emotional, or personal causes for performance variation; it observes Reality, learns patterns, intervenes only on what it can influence, and measures what changes. See `Server Performance/Server Performance.md`, "Purpose" and "The Performance Loop" (`Brand Expectations → Observation → Individual Performance Profile → Gap/Opportunity → Coaching/Training Intervention → New Observation → Outcome → Learning`).

---

## D. Performance dimensions

Five dimensions, none of which stands alone (`Server Performance/Server Performance.md`):

1. **Productivity** — economic activity relative to time/opportunity available (e.g. Sales per Hour Worked).
2. **Quality of Sale** — not how much, but *what* was sold, relative to Brand commercial priorities (`Quality of Sale.md`).
3. **Opportunity Capture** — available vs. captured opportunity for the specific Dining Session (`Opportunity Capture.md`).
4. **Operational Discipline** — discounts, voids, refunds, anomalies, interpreted, never assumed causal.
5. **Perceived Service Quality** — guest-perceived quality; Tips as careful evidence, future QR Survey (`Perceived Service Quality.md`).

Concurrent Service Load is documented as the *context variable* all five should be evaluated as a curve against, not a sixth dimension of the same kind (`Concurrent Service Load.md`).

---

## E. Brand Expectation + Personal Baseline

Two simultaneous, non-substitutable benchmarks (`Brand Expectation and Personal Baseline.md`): **Brand Expectation** (what the Restaurant/Brand wants — Brand-configurable, never hard-coded; Rome's Flavours is a future configuration instance, not a source of canonical rules) and **Personal Baseline** (how this specific Server normally performs — an individual, temporal range, not a single fixed number). Together they distinguish "below Brand standard but improving rapidly" from "stable high performer" from "persistent underperformance despite intervention" — neither benchmark alone can make that distinction.

---

## F. Individual Performance Profile

`Individual Performance Profile.md` defines what RF-One learns about one Server over time: accumulated dimensions, current Personal Baseline and Brand Expectation Gap per dimension, observed load-behavior curve, Location-segmented context (one Employee identity, never duplicated, per Organization's canonical model), coaching history and its observed effect, and temporal trajectory (isolated event / recurring pattern / improvement / decline / stable / context-specific variation, reusing Core Temporal Coherence). It is never used to autonomously decide employment — that remains Personnel Decisions' exclusive, human-applied authority.

---

## G. Quality of Sale

Sales volume alone is insufficient because two Servers with equal Sales-per-Hour can represent materially different economic value if their product mix differs (`Quality of Sale.md`) — a Server can be highly productive while systematically failing to present appetizers, strategic dishes, premium items, wine, desserts, or Brand-priority products. Quality of Sale measures alignment between actual selling behavior (Observed Order Item/Modifier evidence) and Brand commercial priorities (Brand Expectation), using the existing Commercial Catalog vocabulary rather than inventing a parallel taxonomy.

---

## H. Opportunity Capture

`Opportunity Capture.md`: Available Opportunity (what was reasonably sellable, given the Dining Session as known so far) is supplied by Dining Intelligence's Dining Session Profile, evaluated progressively (as of a moment in service, not only retrospectively) — never a fixed static estimate. Captured Opportunity is what was actually sold from that Available Opportunity. Opportunity Capture = Captured ÷ Available. A Server is never penalized for failing to sell something that was not a realistic opportunity. Low Concurrent Service Load does not excuse low Opportunity Capture — it creates *more* capacity for attentive selling, and RF-One should learn whether a Server's Opportunity Capture actually improves when they have more available capacity.

---

## I. Performance Under Load

`Concurrent Service Load.md`: Concurrent Service Load is the number of guests/tables being served concurrently — not cumulative shift volume — derived from existing Table Service/Order/Employee Assignment evidence (no new schema). **Capacity** (how much simultaneous demand a Server can effectively manage), **Acceleration** (how effectively pace increases as demand increases), and **Resilience** (how well Quality of Sale, Perceived Service Quality and Operational Discipline hold as load rises) together form a curve per Server, not one aggregate number. Explicitly excluded: this is an input/context variable only — it never authorizes Server Performance or Service Copilot to decide table/floor assignment, floor rotation, section assignment, or host seating.

---

## J. Coaching model

`Coaching Model.md`: two complementary motivational levers — **Pride/Recognition** (evidence-grounded, never manufactured praise) and **Personal Economic Benefit** (translating an improvement opportunity into an estimated dollar Tip upside, always labeled as an estimate, never guaranteed income). Personalized coaching combines three sources: Brand Playbook, best-performing internal patterns (Invisible Benchmarking — never shown as public rankings by default), and individual learning history. The coaching-effectiveness loop (`Intervention → Subsequent Performance → Outcome → Did it help? → Adjust future coaching`) lets RF-One learn that a hint does not work for a specific Server and stop repeating it. Selective Gamification (challenges, competitions, rankings) is management-activated, opt-in, never the default interface. Underperformance evidence (Baseline → Gap → coaching/training → response → improvement or continued underperformance) may inform management, but RF-One never autonomously fires or replaces an Employee — that remains exclusively human, via Personnel Decisions.

---

## K. Service Copilot

`Service Copilot/` (5 files): **Before** (short personalized briefing, one or two priorities, avoid overload), **During** (short, table-specific, actionable micro-guidance), **After** (very short feedback/learning loop closing the coaching-effectiveness cycle). **Next Best Action** (what to suggest — inputs: Brand Playbook, Dining Session Profile, Customer Consumption Profile, products ordered, open opportunities, individual performance profile, prior coaching outcomes, concurrent load, operational context) and **Next Best Moment** (when to intervene, or explicitly not to — "do not interrupt now" is a valid output) are documented as genuinely separate questions, neither implemented as a recommendation engine. **Management-Controlled Intrusiveness** (`Management Intrusiveness.md`) specializes Core's existing Sovereignty/Delegated Authority principle (`00 Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md`) rather than inventing new authority semantics: Observe / Recommend to Manager / Coach with Approval / Autonomous Coaching are illustrative points on one delegated-authority spectrum, Brand/Location-configurable, never a default maximum-autonomy mode.

---

## L. Smartwatch

`Smartwatch Interaction.md`: documented as an approved future interaction concept, not current implementation. As **output**, it is the envisioned primary During-Service surface — discreet, hands-free, extremely concise, actionable, low-interruption, explicitly never dashboard-style. As **input** (human sensor), it allows tiny one-tap context contributions (first time, regular, celebration, in a hurry, problem/waiting, not interested in wine, special request, very satisfied) that feed Dining Session Profile and, eventually, Judgment/Customer Reading. The critical, structurally binding rule: this must remain micro-input, never data entry — if the Server must type, the interaction design has failed. No hardware, firmware, or application is built.

---

## M. Dining/Consumption Intelligence

`Dining Intelligence/README.md`: a separate, shared Restaurant Domain module — not owned by, and not buried inside, Server Performance — because its output (consumption understanding) is useful to Service Copilot, Training, Menu, Marketing, Sales analytics, Purchasing/Inventory forecasting and Brand analysis alike, not only to Performance. `Dining Intelligence` was adopted as the canonical name (no existing repository terminology collision found with either candidate name). It creates no competing Sales model and uses the existing Commercial Catalog vocabulary for product classification.

---

## N. Dining Session Profile

`Dining Session Profile.md`: the evolving, per-service-occasion consumption pattern — explicitly **not** a static label assigned at seating; it must be queryable as of a moment, since Opportunity Capture depends on "what was known at this point in the service." Illustrative features (guest count, daypart, service duration, order sequence, food/drink families, spending level, appetizer/dessert/alcohol behavior, progressive check composition) and food/drink consumption features (carb/protein composition, premium/basic mix, sharing patterns, course sequencing) are documented as consumption-pattern descriptors based on observed products — explicitly never dietary/nutritional or medical/personal profiling.

---

## O. Customer Consumption Profile

`Customer Consumption Profile.md`: a longitudinal, per-identified-guest profile, separate from the per-occasion Dining Session Profile, strongly approved. The Observed-vs-Inferred discipline is mandatory and worked through explicitly ("Customer ordered Chianti in 6 previous visits" [Observed] vs. "Customer appears to prefer structured red wines" [Inferred] — inference never silently becomes fact). Reservation/Guest sources (OpenTable, Resy, future CRM, walk-in identification) are documented as future, provider-independent evidence, mapping into canonical `Guest`/`Reservation`/`Dining Session` concepts — no provider dependency, no integration built.

---

## P. Guest feedback

`Perceived Service Quality.md`, "Table QR Survey": a future direct evidence source for Perceived Service Quality, since Clover alone cannot measure guest-perceived quality sufficiently. Documented as short and purposeful, with automatic linkage (where technically possible) to table identity, approximate service time, Dining Session, Clover consumption data, and Server, so the guest never re-enters known information. Question design is explicitly deferred — no existing documentation specified it, and none is authored by this task.

---

## Q. KPI framework

`KPI Framework.md` states the mandatory ten-question KPI design principle (behavior/outcome → why it matters → canonical facts required → evidence sources → observed/derived/inferred → contextual normalization → misleading risk → coaching use) and defines seven KPI families — Productivity, Quality of Sale, Opportunity Capture, Service Quality Evidence, Operational Discipline, Performance Under Load, Personal Development — each listing the individual candidate KPIs named by the task and explicitly stating what remains to be fully specified later (exact time windows, qualifying-check definitions, thresholds, statistical fitting methods). No formula is presented as finalized. Tip-based performance is treated as a cross-cutting note: Tip % is never equated directly with service quality.

---

## R. Evidence sources

`Evidence Sources.md` lists canonical evidence sources without making them ontology (Clover/POS, Shifts, Sales, Tips, Organization/Employee Assignment, Dining Intelligence, Reservation/Guest platforms, Guest QR Survey, Server smartwatch inputs, Training history, management configuration) and states the boundary `Source Evidence ≠ Canonical Interpretation ≠ Inference` with a worked Clover→Sales-fact→Coaching-inference example, reusing Tips' existing `Order.employee ≠ Service Employee` attribution caution rather than inventing a new one.

---

## S. Epistemic model

Observed / Derived / Inferred is applied throughout every new document (not only Evidence Sources.md): a transaction or Payment Tip is Observed; a rate, ratio, or Concurrent Service Load count is Derived; a tendency, propensity, correlation, or coaching-style preference is Inferred and must always carry that label and its uncertainty, never presented with Observed-grade confidence. This is the same discipline `Personnel Management/Performance/PerformanceEvidence.md` requires generically — applied, not redefined, for Restaurant Server evidence.

---

## T. Multi-location / Brand consistency

`Server Performance.md`, "Multi-location Brand consistency," documents the strategic objective explicitly: because RF-One supplies contextual Brand guidance during actual service and evaluates every Server against the same Brand Expectation, a multi-Location Brand can deliver more consistent service than one relying solely on each Location's own training quality — even with different Servers, managers, and experience levels per Location. Confirmed compatible with Organization's `COMPLETE — MULTI-LOCATION PRODUCTION READY` model: one canonical Employee identity may work multiple Locations; Server Performance segments by Location/context without duplicating the Employee.

---

## U. Explicit exclusions

`Server Performance/Exclusions.md` states, at minimum: table assignment and floor optimization (Concurrent Service Load is input/context only, never assignment authority); Payroll (economic-motivation estimates never touch Administration/Payroll or its `payment_execution_provider`/ADP/Mercury concepts); generic HR (no employment contracts, discipline, leave, benefits modeled); unsupported personal-cause inference (no psychological/health/relationship/hormonal/emotional/personal causation is ever inferred); Judgment/Customer Reading (future-only, cross-referenced to `Future Development.md`); and no software/models/schema of any kind.

---

## V. Future developments

`Server Performance/Future Development.md`: **Judgment / Customer Reading** is documented in full as explicitly future — a Server's skill at interpreting a table, a rejection-signal input that must never automatically count as a missed opportunity, and the bidirectional principle "RF-One coaches the Server, but the Server also teaches RF-One about the Customer and the service context." Also listed as non-blocking future work: Estimated Cash Tips (the estimation model itself), Table QR Survey question design, KPI formula finalization, the Brand-configuration surface (Product/Runtime), and Reservation/Guest provider adapters.

---

## W. Open Product Owner decisions

None. Every decision in this task's Product Owner Vision section was explicit and was implemented as documentation without requiring a new business-policy choice. The only interpretive decisions made (module naming — `Dining Intelligence` over `Consumption Intelligence`; file granularity; placing Server Performance/Service Copilot/Dining Intelligence under `01 Domains/Restaurant/` rather than `01 Domains/Personnel Management/`) were explicitly delegated to this task by its own instructions ("choose the final canonical name only after inspecting existing repository terminology," "use the smallest repository restructuring necessary") and are documented with their rationale in `Server Performance/README.md` and `Dining Intelligence/README.md`.

---

## X. Exact files changed

**New files (22):**

`01 Domains/Restaurant/Server Performance/`: `README.md`, `Server Performance.md`, `Brand Expectation and Personal Baseline.md`, `Individual Performance Profile.md`, `Quality of Sale.md`, `Opportunity Capture.md`, `Concurrent Service Load.md`, `Perceived Service Quality.md`, `Coaching Model.md`, `KPI Framework.md`, `Evidence Sources.md`, `Exclusions.md`, `Future Development.md` (13 files)

`01 Domains/Restaurant/Service Copilot/`: `README.md`, `Service Copilot.md`, `Next Best Action and Next Best Moment.md`, `Management Intrusiveness.md`, `Smartwatch Interaction.md` (5 files)

`01 Domains/Restaurant/Dining Intelligence/`: `README.md`, `Dining Session Profile.md`, `Customer Consumption Profile.md`, `Food and Drink Correlations.md` (4 files)

`07 Tasks/Reports/TASK_SERVER_PERFORMANCE_001_REPORT.md` (this report)

**Modified files (4):**

- `01 Domains/Restaurant/README.md` — added Server Performance, Service Copilot, Dining Intelligence to "Current Modules"
- `01 Domains/Restaurant/Roadmap.md` — added a "Documented" coverage row; updated §3's Workforce/Personnel bullet to reflect this task's authorization
- `01 Domains/Personnel Management/Performance/README.md` — added a forward pointer under "Restaurant as first validation" to the new specialization
- `01 Domains/Restaurant/Tips/README.md` — updated "Relationship to Personnel Management" to reference the real Server Performance consumer

No file outside this list was touched. No SQLAlchemy model, migration, Clover ingestion code, KPI calculation code, AI/recommendation model, survey, mobile/smartwatch application, OpenTable/Resy integration, Training software, or table-assignment logic was created or modified, per this task's explicit prohibition.

---

## Y. Git status

No commit was created and nothing was pushed during this task. All work is in the working tree only. Pre-existing uncommitted changes present at task start (Purchasing, Organization, Tips, InvoiceIntake, Core documentation, and the Payroll Payment-Execution-Provider work from the immediately preceding task in this session) were left exactly as found — this task only added the 22 new files and made the 4 scoped edits listed in Section X, all Server-Performance-related.

---

## Z. Final readiness statement

`SERVER PERFORMANCE DOMAIN STATUS: DEFINED — READY FOR KPI SPECIFICATION`
