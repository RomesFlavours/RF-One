# RF-One Domains

## Purpose

`01 Domains/` holds canonical knowledge for reusable Application Domains built on top of the RF-One Core.

A Domain applies and, where necessary, specializes Core concepts (Subject, Reality, Desire, Goal, Decision, Entity, Relationship, Process, and others — see `00 Core/`) for a specific field, without redefining what those concepts mean.

See [Domain Architecture.md](Domain%20Architecture.md) for the current cross-Domain conclusions on the Restaurant boundary, the Shared Domains / Business Domain taxonomy (§4), and the remaining transversal Domain candidates (Customer Feedback, Review).

---

# Shared Domains vs. Business Domain

Every Domain below lives under exactly one of two folders directly inside `01 Domains/`:

- **`Shared Domains/`** *(formerly named `Cross Domain/`)* — Domains whose concepts are genuinely industry-independent and must remain reusable by any business, not just Restaurant. A Shared Domain may consume industry-specific content a Business Domain supplies, but must not structurally depend on one.
- **`Business Domain/`** — Domains whose ontology, integrations and operational semantics are specific to one industry. Restaurant is currently the only one. **"BD" is an accepted textual abbreviation for "Business Domain"** in RF-One documents — a shorthand in prose only, never a folder/path rename.

Do not confuse **`Shared Domains/`** (a family of Domains, reusable by any Business Domain) with **`_Shared/`** below (not a Domain at all — domain-independent-but-not-universal knowledge such as `_Shared/Environment/`). The similar names are coincidental; the two serve different purposes and neither is a specialization of the other.

```text
01 Domains/
├── Shared Domains/                         (formerly Cross Domain/)
│   ├── Administration/                     transversal Domain, with its Payroll and Invoice Intake modules
│   ├── Continuous Productivity Development/ transversal Domain — gaps/opportunities, interventions, outcomes
│   ├── Intercompany Funding & Settlement/   transversal Domain — financial relationships between Legal Entities
│   ├── Operational Knowledge/               transversal Domain — retrievable operational information (formerly "Training")
│   ├── Performance/                         transversal Domain — what people actually produce
│   ├── Personnel Management/                transversal Domain — Workforce and Personnel Decisions modules
│   ├── Purchased/                           transversal Domain — normalized purchase facts from what the business was invoiced for
│   ├── Selection/                           transversal Domain — evaluating/choosing among candidates
│   └── Taxation/                            transversal Domain
├── Business Domain/
│   └── Restaurant/           the current, and so far only, Business Domain
└── _Shared/                  NOT a Domain — see "Current Domains" below
```

**Training and Performance are not modules of Personnel Management** — both were extracted into their own top-level Shared Domain entries; Personnel Management's modules are Workforce, Personnel Decisions and Compensation (formerly named Payroll — see [Domain Architecture.md](Domain%20Architecture.md) §4). Training has since been redefined as **Operational Knowledge**, and **Continuous Productivity Development** was added as a further independent sibling Shared Domain. See [Domain Architecture.md](Domain%20Architecture.md) §4 for the full reasoning.

---

# Authority

Each Domain is **canonical for its own field**, subject to the Core it is built on. Domain knowledge does not redefine universal Core concepts, and does not override Core principles.

A Domain must use only the Core concepts it actually requires — a concept existing in Core does not obligate every Domain to use it.

---

# What belongs here

- Business knowledge, entities, relationships and business rules specific to one reusable field of activity (e.g. `Restaurant/`).
- Domain-level specializations of Core concepts (e.g. a Domain's own `Operational Unit` specialization).
- Shared knowledge reused across multiple Domains, under `_Shared/` (e.g. `_Shared/Environment/` — geography, legal, fiscal, regulatory and standards context).

# What does not belong here

- Universal, domain-independent ontology — that belongs in `00 Core/`.
- Commercial/Product configurations that combine Domains for a specific customer offering — that belongs in `02 Products/`.
- RF-One's own commercial strategy as a company — that belongs in `09 Strategy/`.
- Runtime implementation/software behavior — that belongs in `03 Software/`.

---

# Current Domains

| Domain | Family | Description |
|---|---|---|
| `Shared Domains/Selection/` | Shared Domains | Transversal Domain for evaluating and choosing among candidates for a role/context, usable by any industry — not owned by Restaurant or by Personnel Management, though closely related to Personnel Management's Personnel Decisions module. See `Shared Domains/Selection/README.md`. Restaurant's Industry Extension of Selection (role catalog, Rome's Flavours Server Role Configuration) lives at `Business Domain/Restaurant/Selection/`, depending on and extending Selection Core, never the reverse. |
| `Shared Domains/Continuous Productivity Development/` | Shared Domains | Transversal Domain that identifies gaps/opportunities, estimates their economic value, determines the best available intervention, measures outcomes, and learns from results — usable by any industry. Conceptually superseded the "closes an evidenced, trainable gap" scope originally reserved by the Training placeholder (see [Domain Architecture.md](Domain%20Architecture.md) §4). See `Shared Domains/Continuous Productivity Development/README.md`. |
| `Shared Domains/Operational Knowledge/` | Shared Domains | Transversal Domain: the shared repository of retrievable operational information (Operational Knowledge Pills) that Copilot and other RF-One functions may retrieve — usable by any industry. It does not train, test, assess, or certify. Formerly "Training" (extracted from Personnel Management), redefined as this distinct concept (see [Domain Architecture.md](Domain%20Architecture.md) §4). See `Shared Domains/Operational Knowledge/README.md`. |
| `Shared Domains/Performance/` | Shared Domains | Transversal Domain for what a person actually produces in Reality — usable by any industry. Extracted from Personnel Management (see [Domain Architecture.md](Domain%20Architecture.md) §4); documented in depth (Performance, PerformanceEvidence, PerformanceMeasure, PerformanceIndicator, PerformanceContext — TASK_PERSONNEL_001). See `Shared Domains/Performance/README.md`. |
| `Shared Domains/Personnel Management/` | Shared Domains | Transversal Domain for managing people across industries, built on Core 2.0. Restaurant and other technical Domains are its application contexts, not its architectural owner. See `Shared Domains/Personnel Management/README.md`. **Its modules are Workforce, Personnel Decisions and Compensation** (formerly named Payroll — RF-One determines, composes and approves compensation but does not itself perform Payroll) — Selection, the former Training, and Performance were formerly modules here and are now sibling top-level Shared Domains (above). |
| `Shared Domains/Taxation/` | Shared Domains | Transversal Domain for tax obligations, positions, treatments, scenarios and lawful tax optimization, built on Core 2.0's Net/Retained Outcome and Constraint Shaping. It reasons about the tax consequences of facts owned by other Domains; it does not own those facts, and is explicitly distinct from Accounting, Finance and Legal Entity Management. See `Shared Domains/Taxation/README.md`. |
| `Shared Domains/Administration/` | Shared Domains | Transversal Domain for administrative execution of obligations arising from operating a business, and for the canonical `Total Employee Cost`/`Total Personnel Cost` model (`Personnel Cost.md`) — the causally attributable Employee cost, with no artificial overhead allocation. Its Payroll module (PayrollSchedule/PayrollPeriod/Workweek, Compensation Terms, PayrollRun, Payroll Provider Result/ADP import, Payroll Employer Cost) supplies one component/source of that broader cost model. Administration consumes, but does not own, the derived economic category allocation (Food/Drink/Supplies) produced by `Restaurant/Purchasing`'s Purchase Document/Purchase Line/Effective Product Cost model — that canonical business/cost model is not an Administration concept. Administration's own Invoice Intake module owns only document acquisition/OCR/normalization/routing, never that canonical model (see `Shared Domains/Administration/Invoice Intake/README.md`). Independent from Restaurant, Personnel Management, ADP, and jurisdiction-specific labor law. See `Shared Domains/Administration/README.md`, `Shared Domains/Administration/Personnel Cost.md`, `Shared Domains/Administration/Payroll/README.md`. |
| `Shared Domains/Purchased/` | Shared Domains | Transversal Domain consumed by Business Domains: turns what the business was invoiced for into normalized Purchased Lines (one per economic item/service/charge on a source document, e.g. invoice/credit memo), subject to later supplier-side corrections. Owns only the purchase fact ("what was invoiced/purchased") — never whether/how it was paid (Bank Reconciliation is a boundary owned by the consuming Business Domain, not by Purchased). Invoice Intake is a process that feeds Purchased, not this Domain's name. See `Shared Domains/Purchased/README.md`, which also records the currently open question about this Domain's relationship to Restaurant's pre-existing, Business-Domain-specific `Purchasing` module. |
| `Shared Domains/Intercompany Funding & Settlement/` | Shared Domains | Transversal Domain representing and regulating financial relationships between Legal Entities when one funds, pays, receives, allocates, or financially supports another — prefunding, Payment/Receipt On Behalf, intercompany settlement, netting, and allocation, all governed by a Corporate-configured `SettlementPolicy` rather than a single hardcoded operating model. Distinguishes Funding Balance (prefunded liquidity attributable to a Legal Entity) from Settlement Balance (matured intercompany receivable/payable) — the two are never collapsed. Belongs under Shared Domains, not Administration: the economic relationship exists before its accounting representation. See `Shared Domains/Intercompany Funding & Settlement/README.md`. |
| `Business Domain/Restaurant/` | Business Domain | Business knowledge required to model, operate and continuously improve a restaurant — the current, and so far only, Business Domain. See `Business Domain/Restaurant/README.md` and `Business Domain/Restaurant/Roadmap.md`. |
| `_Shared/` | *(not a Domain)* | Domain-independent-but-not-universal shared knowledge reused across multiple Domains (currently `Environment/`). Deliberately outside both `Shared Domains/` and `Business Domain/` — see "Shared Domains vs. Business Domain" above, and its note distinguishing `_Shared/` from the `Shared Domains/` family. |

A Domain should not automatically equal a Product. Future transversal Domain candidates (e.g. Customer Feedback, Review) are anticipated by [Domain Architecture.md](Domain%20Architecture.md) but are not created by this migration; if created, they would join `Shared Domains/`.

---

# Business capability is not automatically a Domain

RF-One's commercial ambition may span many business capability areas — financial performance, sales, marketing, personnel, and more. A capability or coverage area existing in a historical planning taxonomy, in `CLAUDE.md`'s Domain examples, or in commercial strategy does **not** by itself make it a modern architectural Domain.

The historical `Knowledge Domains` taxonomy inherited from the legacy repository (`90 Archive/Legacy Repository/X00 Knowledge Repository/05 Knowledge Domains/README.md`) was a business knowledge/capability/coverage planning list, not the current architectural definition of Domain. It has been reconciled and classified area-by-area in `09 Strategy/04_Business_Capability_Coverage.md`; some of its areas belong to Restaurant (see `Restaurant/Roadmap.md`), some are Shared Domain candidates (not yet created), and others are Strategy, Product, or Software capability rather than Domain knowledge at all.

`_Shared/` may host reusable business/environment knowledge once a concept is shown to genuinely apply across multiple Domains, not merely because it was listed in a legacy taxonomy or seems generically useful.
