# RF-One Operational Database and Data Governance (RF1_OPERATIONAL_DATABASE_001)

**Status:** APPROVED ARCHITECTURAL DECISION — mandatory, Product Owner, 2026-11-21.
**Scope:** RF-One Core, infrastructure, Data Store, APIs, connectors, every Domain and Module, development, testing and release standards.
**Authority:** this page is the **single reference specification** for the principle. Every other document links here instead of restating it. The verbatim approved Italian original is [SOURCE_DECISION_IT.md](SOURCE_DECISION_IT.md); this English text is its faithful rendering, and the original prevails if the two ever differ.
**Precedence:** every earlier document that gives Clover, OpenTable or any other provider the role of RF-One's main operational data model is superseded on that point and must be corrected or marked historical with a link to this page.

This page records the approved decision. It does **not** by itself change code, databases, configuration or AWS, and it does not certify that current software conforms (see §10).

---

## 1. Non-negotiable principle

**RF-One owns its own information model and its own canonical operational database.** External applications (Clover, OpenTable, ADP, PayPal, Amazon or future sources) do not determine RF-One's logical structure: they supply data through connectors, APIs or uploads. The future **RF POS** will feed the same model through RF-One interfaces. Replacing a source must not force the consuming Domains to be rewritten.

This does not mean one table per content type. It means **one canonical RF-One model**, with coherent entities and appropriate relationships. Operational data (orders, payments, order lines, tables, …) is kept separate from financial data and from enrichments where their semantics differ, while integration and governance remain common.

## 2. Mandatory internal flow

```text
1. Source                     external API, upload, connector or RF-One application
        ↓
2. Acquisition connector      extraction and translation of the source format ONLY
        ↓
3. Common ingestion service   identifies location/entity; validity, deduplication,
                              checkpoints, errors, traceability
        ↓
4. RF-One canonical model and operational database
                              where business facts are recorded and updated
        ↓
5. RF-One Domains             read through RF-One interfaces and data — never directly
                              from a provider's APIs or provider-specific tables for
                              ordinary business logic
```

Connectors may keep technical staging, but **no staging table and no provider schema ever becomes an information contract** of WHO, WHY, Tips, Kitchen, Management or any other Domain.

## 3. Incremental acquisition and integrity

- **External POS systems:** **one shared acquisition service** for all locations — never one importer per Domain. Locations keep distinct credentials and identifiers.
- **Operational target: one check every 30 seconds**, within verified API limits and technical constraints. The frequency is set by the common service, never by the Domains.
- Synchronize only data **new or modified since the last consolidated checkpoint**; after an interruption, recover the missing interval automatically.
- Advance the checkpoint **only after a valid write**; use idempotent upserts, RF-One keys and mapping of external IDs.
- Handle late updates, cancellations, corrections, pagination, retries and gap detection **without duplicating events**.
- The first historical import, where needed, is a **separate initialization operation**; it is not repeated each time a Domain is used.
- Locations/merchants and companies stay correctly separated.
- Keep origin and external ID **for audit**, never as the conceptual primary ID of the operational model.

## 4. Ownership by Domain

- **Clover, OpenTable and future systems** are replaceable providers/connectors.
- **Future RF POS** writes into the same canonical contracts, without requiring any adaptation of Tips, Kitchen, Bank, Management or other consumers.
- **Consumer Domains** query RF-One only for their ordinary work; they do not open independent access to the same provider and do not create parallel copies of the same business fact.
- **Bank / Enrichers:** enrichers normalize external information and populate the **enrichment field of the RF-One movement**, distinct from the original bank description and original memo. WHO/WHY consult only the canonical fields of the transaction — never provider or staging tables.

## 5. Contracts and data model — documented before implementation

For each **operational entity**, design must define: meaning, fields, types, RF-One keys, relationships, location/company, provenance, external IDs, update criteria, mutability, history/audit, errors and use by the Domains.

For each **connector**: endpoint/format, field-by-field mapping, frequency, checkpoint, recovery, rate limits, credentials, retry, deduplication, controls and tests.

Do not invent column or table names that have not been verified in the existing code.

## 6. Design prohibitions

1. No new Clover engine for a specific Domain or a specific period.
2. No direct dependency of Domain logic on the database/schema of Clover or any other provider.
3. No systematic duplication of the same events for each module.
4. No new information model decided autonomously by Claude during implementation.
5. No destructive migration and no production change without approval.

## 7. Binding development process

| Role | Who | Responsibility |
|---|---|---|
| **Design** | Product Owner + ChatGPT | External behaviour, architecture, internal flows, data model, APIs, algorithms, edge cases, acceptance criteria. |
| **Implementation** | Claude | Implements the approved specifications in code, **without adding workflows, schemas or architectural decisions on its own**. When an undefined choice emerges, Claude **stops and submits it to design**. Instructions: `CLAUDE.md`, section *Operational database principle and development roles*. |
| **Independent review** | Codex | Verifies conformity, tests, regressions, dependencies, schema and risks. Does not change requirements; reports deviations before deployment. Checklist: [`03 Software/Infrastructure/deploy/CODEX_INDEPENDENT_REVIEW_CHECKLIST.md`](../../03%20Software/Infrastructure/deploy/CODEX_INDEPENDENT_REVIEW_CHECKLIST.md). |
| **Release** | Product Owner | Only after explicit approval. No push, merge, deployment or production change without specific authorization, unless already expressly authorized in the assignment. |

## 8. Mandatory documentation alignment

All relevant normative sources follow this page: principles / legacy / model, RF-One and Data Store architecture, data diagrams, API specifications, connectors/integrations, Clover multi-site, OpenTable, RF POS, Domain documentation, Claude development instructions, the Codex independent checklist, migration and acceptance-testing plans.

Signed historical documents and execution reports are **not** rewritten: they are marked historical with a link to this page. For each modified file the alignment register records path, section, reference, inconsistencies and open decisions. Obsolete operational statements authorizing Domains to query Clover directly are removed or corrected. Change history is preserved (Git).

First alignment register: [`07 Tasks/Reports/RF1_OPERATIONAL_DATABASE_001_DOCUMENTATION_REGISTER.md`](../../07%20Tasks/Reports/RF1_OPERATIONAL_DATABASE_001_DOCUMENTATION_REGISTER.md).

## 9. Documentation acceptance criteria

- A new developer immediately identifies **one RF-One operational model**, distinct from the source systems.
- The end-to-end path source → connector → ingestion → operational DB → Domains is defined unambiguously (§2).
- Every relevant document adopts the same principles, without contradictory instructions.
- The canonical data contract is independent of Clover; replacing it with RF POS requires no redesign of consumers.
- Incremental synchronization, the 30 s target and the integrity safeguards are specified, without claiming unverified API support.
- Claude and Codex have distinct, binding instructions for their roles.
- No code, database or AWS service is modified by a documentation-only alignment.

---

## 10. Relationship to existing documents (non-normative orientation)

This decision is the system-level, binding expression of principles already present in the Core; it does not redefine them:

| Document | Relationship |
|---|---|
| [`00 Core/ArchitecturePrinciples.md`](../../00%20Core/ArchitecturePrinciples.md) — *Source Independence*, *Canonical Knowledge* | Core principle; this page makes it operational and binding for the database and ingestion path. |
| [`00 Core/ExternalDataMappingPrinciples.md`](../../00%20Core/ExternalDataMappingPrinciples.md) | Source Records and Mapping Layer = steps 2–3 of §2. |
| [`00 Core/ImplementationGuidelines.md`](../../00%20Core/ImplementationGuidelines.md) — *External Systems* | Same rule at implementation level. |
| [`03 Software/RF-One Data Store/README.md`](../../03%20Software/RF-One%20Data%20Store/README.md), [`DATABASE_SCHEMA.md`](../../03%20Software/RF-One%20Data%20Store/DATABASE_SCHEMA.md) | Current physical implementation of step 4. |
| [`03 Software/RF-One Data Store/CLOVER_CONTINUOUS_SYNCHRONIZATION_ARCHITECTURE.md`](../../03%20Software/RF-One%20Data%20Store/CLOVER_CONTINUOUS_SYNCHRONIZATION_ARCHITECTURE.md), [`CLOVER_INGESTION.md`](../../03%20Software/RF-One%20Data%20Store/CLOVER_INGESTION.md) | Clover-specific connector/ingestion documents, subordinate to this page. |

**Already consistent at documentation level (observed, not re-verified in code by this page):** RF-One surrogate IDs with optional source provenance on operational tables; the Clover connector under `technical/connectors/` as the one shared fetch/upsert path; the PayPal connector writing into the common `PaymentInstrumentTransaction` ledger; Domain documents separating source semantics (e.g. Clover `SourceRole`) from RF-One concepts.

## 11. Open questions — not decided by this page

These points are **not defined** by the approved decision or conflict with earlier approved documents. They are recorded for design (Product Owner + ChatGPT); Claude does not resolve them. Detail and affected files: the alignment register, §4.

| ID | Question |
|---|---|
| OQ-1 | **Frequency.** The 30 s target (§3) versus the earlier approved Clover cadence — Fast Live Extractor ~15 s for new records, Correction/Reconciliation Poller ~60 s for modifications. Does 30 s replace both, apply to new and modified data alike, or act as an upper bound? |
| OQ-2 | **POS history and correction model.** The Clover sync architecture states that Clover remains the system of record for POS transactional history and that RF-One keeps only the corrected state. With a replaceable source and a future RF POS, where does transactional history live, and how does correction-in-place relate to Core *Historical Integrity* (corrections generate new events)? |
| OQ-3 | **Source-neutral readiness interface.** Tips' calculation and payment readiness gates call a Clover connector function (`correction_sync.describe_reconciliation_status()`) directly. A source-neutral RF-One readiness/consolidation contract is not yet designed. |
| OQ-4 | **One shared service for all locations.** The current Clover Live Sync / Correction Poller run per Location (`--location-id`). How one shared service covers every location (single multi-location process or several instances of the same service) is not defined. |
| OQ-5 | **Outbound writes.** The decision defines the inbound flow. Writing to an external POS (MyRF Server Tablet sending orders to Clover) and the RF POS write path into canonical contracts are not yet specified. |
| OQ-6 | **Bank enrichment field.** The decision requires an enrichment field distinct from the original description and memo; its canonical name and location are not documented, and the separate RFBank repository describes enricher output written to "the Memo". Verification and design are needed. |
| OQ-7 | **Source-evidence tables as Domain inputs.** `SourceRole`, `EmployeeSourceRole` and `SourceRoleMapping` keep a required source identity by design and are read by Tips / Organization flows. Whether these count as permitted canonical inputs or as provider-shaped contracts to be retired is not decided. |
| OQ-8 | **Per-entity and per-connector contracts (§5).** No complete contract document yet covers every operational entity and connector with all §5 attributes; these are to be produced by design before further implementation. |
| OQ-9 | **Boundary with MIEAF.** `CLAUDE.md` MIEAF tells Claude to choose between technical alternatives itself; §7 forbids autonomous architectural, data-model, workflow and API decisions. The exact boundary between "technical implementation choice" and "design choice" needs Product Owner confirmation. |
