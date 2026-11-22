# RF-One Operational Database and Data Governance (RF1_OPERATIONAL_DATABASE_001)

**Status:** APPROVED ARCHITECTURAL DECISION — mandatory, Product Owner, 2026-11-21.
**Scope:** RF-One Core, infrastructure, Data Store, APIs, connectors, every Domain and Module, development, testing and release standards.
**Authority:** this page is the **single reference specification** for the principle. Every other document links here instead of restating it. The verbatim approved Italian original is [SOURCE_DECISION_IT.md](SOURCE_DECISION_IT.md); this English text is its faithful rendering, and the original prevails if the two ever differ.
**Precedence:** every earlier document that gives Clover, OpenTable or any other provider the role of RF-One's main operational data model is superseded on that point and must be corrected or marked historical with a link to this page.

This page records the approved decision. It does **not** by itself change code, databases, configuration or AWS, and it does not certify that current software conforms (see §10).

**Decisions on the open questions OQ-1…OQ-11:** the **current** decisions are in [*Current Product Owner decisions*](#current-decisions); for OQ-1…OQ-8 they supersede the original 2026-11-21 decisions wherever the two differ. §11 keeps the original decisions for traceability, together with the verified behaviour, open defects and steps still to implement. Verbatim Italian text of both: [OQ_DECISIONS_IT.md](OQ_DECISIONS_IT.md). Points that still need a design choice: §12.

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
- **Cadence (current decision OQ-1, clarified 2026-11-22):** the shared service acquires **new records every 30 seconds** as ordinary operational acquisition, and checks **modifications (corrections) at midnight**, within verified API limits and technical constraints. Neither an exclusively nightly acquisition nor live checks only on request is the decision. The frequency is set by the common service, never by the Domains. *(The original 2026-11-21 text set "one check every 30 seconds" for new data and corrections alike; OQ-1 keeps 30 seconds for new records and moves the check of modifications to midnight.)*
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
- Incremental synchronization, the cadence of decision OQ-1 (new records every 30 seconds; modifications checked at midnight) and the integrity safeguards are specified, without claiming unverified API support.
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

<a id="current-decisions"></a>
## Current Product Owner decisions

The decisions below supersede the earlier wording in sections 3, 9, 11 and 12 wherever it differs. For OQ-1, the Product Owner clarification of 2026-11-22 sets the cadence and prevails over the patch wording of the same day ("live at 30 seconds only on active request"). Earlier implementation notes and unresolved design items are historical context where superseded. OQ-9 through OQ-11 continue to apply.

**OQ-1 (clarified 2026-11-22).** The shared service acquires **new Clover records every 30 seconds** (ordinary operational acquisition, not only on request) and checks **modifications (corrections) at midnight**. Resume from the last valid checkpoint. *(Superseded wording of the same day: "new records and corrections at midnight; live checks every 30 seconds only during active requests for a location".)*

**OQ-2.** Keep the latest acquired Clover value. Preserve raw evidence for audit as applicable. Corrections do not reopen FINAL Tips. Native history is deferred to RF POS design.

**OQ-3.** Tips defaults to the next business day after the last consolidated period for the selected location and adds a dedicated configurable day offset for the end date, also in manual mode. Calcola and Consolida require verified full coverage for that location. If coverage is incomplete, block and show the reason and Download data in the modal. A user authorized to calculate Tips for the location may request its acquisition through the midnight process without general CLOVER_ACQUISITION permission. Payment readiness remains separate.

**OQ-4.** At midnight one engine opens separate connections for Winter Park and Mount Dora. Credentials, checkpoints and outcomes are per location. Future live cycles run independently per location.

**OQ-5.** Trial scope is inserting Server Tablet orders in Clover for the selected location. Other data types and changes or cancellations after acceptance are deferred. Insertion is not yet implemented.

**OQ-6.** Current scope is bank and card imports, enricher report imports and linking individual records to the correct bank movements. Preserve original bank text, including across reimports. Normalize only in a separate derived value. Keep the original Memo separate from enrichment_note. WHO, WHY, rules, allocations and use of enrichment are outside this step. The main Data Store adopts the field when the enrichers are connected there.

**OQ-7.** Selection releases the eligible candidate to Training. Only after the Training operator confirms arrival does Training enroll the person and register the Student role in Registry. Registry then creates the person in Clover for the competent location and saves the returned employee ID as POS ID for record linkage. RF-One Registry owns roles; Tips reads the assignment valid for the person, location and date without Clover fallback. Clover creation and POS ID storage are still to be implemented. The authoritative location and canonical POS ID record remain open.

**OQ-8.** Compensation pulls FINAL Tips from RF-One when required. Tips neither sends data nor starts Compensation. CALCULATED results remain inside Tips until finalization.

The verbatim Italian text of these decisions is the section *Decisioni successive del Product Owner* of [OQ_DECISIONS_IT.md](OQ_DECISIONS_IT.md); it prevails over this rendering.

### Status of the current decisions

Four categories are kept separate: **approved decision** (above), **verified behaviour** (what the software did at the source branch base `0e85cef`, observed 2026-11-21, details in §11; the same modules exist on `main` and were not re-verified there), **open defect** (verified behaviour that contradicts the decision) and **to implement** (a step the decision requires that does not exist yet). An approved decision does not certify implementation. No implementation of the current decisions has been verified.

| OQ | Verified behaviour | Open defect | To implement | Still for design (§12) |
|---|---|---|---|---|
| OQ-1 | Two per-Location processes: Live Sync every 15 s for new records, Correction Sync every 60 s for modifications. | Cadences differ from the decision (15 s instead of 30 s for new records; continuous 60 s instead of a midnight check for modifications); two processes instead of one shared service. | One shared service: new records every 30 s; modification check at midnight; resume from checkpoint. | G-1 |
| OQ-2 | Corrections applied in place; raw payloads kept in `SourceRecord` for audit; FINAL Tips immutable. | — | — | G-2 (residual) |
| OQ-3 | Calculation and payment gated by the Clover connector function `describe_reconciliation_status()`. | Gate reads a connector function, not RF-One coverage; no start-date default, end-date offset or per-location coverage check for Calcola/Consolida. | Defaults, coverage check for Calcola and Consolida, blocking modal with reason and *Scarica dati*, per-location acquisition request for users authorized to calculate Tips. | G-3, G-4, G-5 |
| OQ-4 | Each process runs per Location with its own cursor. | — | One midnight engine with separate per-location connections, credentials, checkpoints and outcomes. | G-1 |
| OQ-5 | No outbound order path. | — | **Sending Server Tablet trial orders to Clover** for the selected location. | G-6 |
| OQ-6 | RFBank: `enrichment_note`, `source_memo` separate. Main Data Store: no `enrichment_note`. | — | Step limited to **import and matching**: bank/card imports, enricher report imports, linking records to bank movements; field adoption in the main Data Store when the enrichers are connected there. | G-7 |
| OQ-7 | Tips engine reads `EmployeeAssignment`. | Uncommitted main-copy Tips work reads Clover roles during calculation (see §11 OQ-7). | Selection → Training handoff with arrival confirmation; Student role in Registry; **creation of the Student in Clover and storage of the returned POS ID**. | G-8, G-11 |
| OQ-8 | No complete contract document. | — | Compensation pull of FINAL Tips from RF-One. | G-9 |

## 11. Original decisions on the open questions (Product Owner, 2026-11-21) and verified state

The first alignment recorded eleven open questions. On 2026-11-21 the Product Owner approved a decision for each one. The verbatim Italian text is the section *Testo originale delle decisioni* of [OQ_DECISIONS_IT.md](OQ_DECISIONS_IT.md); it prevails over this rendering.

**For OQ-1…OQ-8, the *Original decision* paragraphs below are historical:** wherever they differ from the [current decisions](#current-decisions), the current decisions apply and the original wording must not be read as an instruction in force. OQ-9…OQ-11 remain in force as written.

For each decision, **Verified behaviour** describes the software at the source branch base `0e85cef` as observed on 2026-11-21 (not re-verified on `main`). A decision does not certify implementation. Points that still need a functional or architectural choice are in §12 and stay with design.

<a id="oq-1"></a>
### OQ-1 — Acquisition frequency (Clover)

**Original decision (2026-11-21; historical where the current decision differs).** **One** acquisition service checks **new data and corrections every 30 seconds**, within verified technical limits. After an interruption it recovers what is missing, restarting from the last valid checkpoint. This approved 30-second cadence replaces the two earlier approved intervals as the target: Fast Live Extractor ~15 s (new records) and Correction/Reconciliation Poller ~60 s (modifications).

**Verified behaviour.** Two separate processes with their own defaults:

- `technical/connectors/clover/live_sync.py`: 15 s, new records by `createdTime`;
- `technical/connectors/clover/correction_sync.py`: 60 s, modifications. On AWS it runs as `rfone-clover-correction-sync`.

Neither runs at 30 s as a single service. Clover API limits for a 30-second cycle across all locations have not been verified.

**Correction coverage still to verify.** Observed in code and documents, not tested against Clover:

| Resource | Coverage today |
|---|---|
| Orders, Payments | Re-checked by Clover `modifiedTime` (Correction Poller). |
| Refunds | No confirmed `modifiedTime`. Fallback: a rolling 48-hour `createdTime` window. Corrections older than that window are not covered. |
| Order items, modifiers, order fees, payment tips | Re-imported with their parent Order/Payment. Whether removed or voided child records are detected is still to verify. |
| Order-level discounts, order item tax | Historical Backfill only; no continuous correction. |
| Shifts (clock-in/out, manager overrides) | Fetched only by Live Sync. Clover's `/shifts` endpoint has no time filter, so shifts are filtered client-side by clock-in inside the current window. There is no Correction resource for shifts, so a later change to a shift whose clock-in has left the window is not covered. Tips presence and Compensation hours depend on shifts. |
| Employees | Catalog refresh in every Live Sync cycle. |

**Current decision:** [OQ-1 in *Current Product Owner decisions*](#current-decisions); status in the table there.

**Aligned in:** [`CLOVER_CONTINUOUS_SYNCHRONIZATION_ARCHITECTURE.md`](../../03%20Software/RF-One%20Data%20Store/CLOVER_CONTINUOUS_SYNCHRONIZATION_ARCHITECTURE.md), [`deploy/clover-acquisition-job/README.md`](../../03%20Software/Infrastructure/deploy/clover-acquisition-job/README.md), [`deploy/clover-correction-sync/README.md`](../../03%20Software/Infrastructure/deploy/clover-correction-sync/README.md), [`03 Software/Infrastructure/README.md`](../../03%20Software/Infrastructure/README.md).

<a id="oq-2"></a>
### OQ-2 — History and corrections

**Original decision (2026-11-21; historical where the current decision differs).** RF-One keeps the **current state** and **records relevant corrections as events**. A correction does **not** automatically reopen a closed Tips period. The history needed to explain corrections belongs to RF-One and must stay usable if the provider changes.

**Verified behaviour.**

- The Correction Poller applies corrections in place on the canonical rows.
- `SourceRecord` keeps raw fetched payloads for audit only; business logic never reads it.
- No RF-One correction event exists.
- Closed (FINAL) Tips periods are already immutable ([`Finalized Tips Period.md`](../../01%20Domains/Business%20Domain/Restaurant/Tips/Finalized%20Tips%20Period.md)).

**Current decision:** [OQ-2 in *Current Product Owner decisions*](#current-decisions); status in the table there.

**Aligned in:** `CLOVER_CONTINUOUS_SYNCHRONIZATION_ARCHITECTURE.md` §1, §8; `Finalized Tips Period.md`.

<a id="oq-3"></a>
### OQ-3 — Starting a Tips calculation

**Original decision (2026-11-21; historical where the current decision differs).** When the user asks for a calculation from one date to another, Tips checks **in RF-One** that the data cover the **whole** requested period. If even one part is missing, the calculation does not start. A modal explains that the available data do not cover the whole range. For starting a calculation, this coverage check **replaces** the separate consolidation check.

The decision covers **calculation only**. Any change to payment conditions needs a separate decision. The modal follows the standing UI rules (`CLAUDE.md`, *RF-One UI Rules* and *Contextual help on every page*): close X at the top right, and the contextual help link where the current UI Rules place it.

**Verified behaviour.** `tips/readiness.describe_readiness()` gates `ready_to_calculate` by calling the Clover connector function `correction_sync.describe_reconciliation_status()` directly. That function requires the Live Cursor and the three Correction cursors to have passed the end of the Business Date. The payment gate `tips/payment_readiness.describe_payment_readiness()` calls the same function; this decision does not change it.

**Current decision:** [OQ-3 in *Current Product Owner decisions*](#current-decisions); status in the table there.

**Aligned in:** [`Tips Configuration.md`](../../01%20Domains/Business%20Domain/Restaurant/Tips/Tips%20Configuration.md) §3, §9, §10; `CLOVER_CONTINUOUS_SYNCHRONIZATION_ARCHITECTURE.md` §7.

<a id="oq-4"></a>
### OQ-4 — Multi-location acquisition

**Original decision (2026-11-21; historical where the current decision differs).** **One** service checks the locations **in parallel**. Each location keeps its own credentials, identifiers and resume point. If one location is blocked, the others continue. The blocked location restarts from its own last valid checkpoint.

**Verified behaviour.** Live Sync and Correction Sync each run per Location (`--location-id`); on AWS, `rfone-clover-correction-sync` runs with `--location-id 1`. The per-Location cursor, and so the per-location resume point, already exists.

**Current decision:** [OQ-4 in *Current Product Owner decisions*](#current-decisions); status in the table there.

**Aligned in:** same documents as OQ-1.

<a id="oq-5"></a>
### OQ-5 — Sending orders from MyRF

**Original decision (2026-11-21; historical where the current decision differs).** RF-One records the order **immediately as pending**, then sends it to the POS through the connector. If the outcome is uncertain, RF-One verifies it before any resend, so that orders are not duplicated. Three events stay distinct: **sending**, **receipt by the POS** and **forwarding to the kitchen**. The future RF POS uses the same RF-One contracts.

**Verified behaviour.** No outbound order path is documented as implemented. The MyRF Server Tablet documents are an unapproved draft.

**Clover capabilities still to verify** (MyRF document 05):

- V3/V4: creating a check and adding items to an existing one;
- V6: quantities, modifiers and notes;
- V7: recognizing an order Clover already received, to verify an uncertain outcome;
- V8: whether and how Clover confirms forwarding to kitchen/bar;
- V9/V10: corrections and cancellations after sending, external changes and check closure.

**Current decision:** [OQ-5 in *Current Product Owner decisions*](#current-decisions); status in the table there. Under the current decision the trial scope is limited to **inserting Server Tablet orders in Clover** for the selected location; sending trial orders is **still to implement**. Other data types, and changes or cancellations after acceptance, are deferred.

**Aligned in:** [`MyRF/Server Tablet/README.md`](../../01%20Domains/Business%20Domain/Restaurant/MyRF/Server%20Tablet/README.md), `03-Tavolo-e-Percorso-Ordine.md`, `05-Verifiche-Integrazione-Clover.md`.

<a id="oq-6"></a>
### OQ-6 — Bank enrichers

**Original decision (2026-11-21; historical where the current decision differs).**

- Enrichers write **only** to the dedicated field. In the verified RFBank implementation that field is `enrichment_note`.
- The imported description is kept **exactly as it arrived from the bank**. No process, including later imports and reloads, may overwrite, clean, normalize or append text to it.
- The original bank Memo stays separate from the enrichment.
- WHO and WHY read the canonical fields of the movement.
- Source tables and enricher tables serve import and matching.

**Verified behaviour.**

- **RFBank** (separate repository `RF One/RFBank`, verified at commit `8b90a4e`, not modified):
  - `financial_transactions.enrichment_note`, written by `bank_reconciliation/enrichers.py`;
  - `source_memo` holds the original bank Memo and is never changed;
  - WHO/WHY read `source_memo` and `enrichment_note` from the movement (`bank_reconciliation/movement_text.py`).
- **Main Data Store** (this repository):
  - `FinancialTransaction` has `description_original`, `description_normalized` and `source_memo`, and **no `enrichment_note`**;
  - adopting the field here is **not done**, and it needs its own approved schema task.

**Current decision:** [OQ-6 in *Current Product Owner decisions*](#current-decisions); status in the table there. Under the current decision this step covers **import and matching** only (bank and card imports, enricher report imports, linking each record to the correct bank movement). WHO, WHY, rules, allocations and the use of enrichment are outside the step.

**Aligned in:** [`Bank Reconciliation/README.md`](../../01%20Domains/Shared%20Domains/Administration/Bank%20Reconciliation/README.md); Codex checklist item 12.

<a id="oq-7"></a>
### OQ-7 — Tips roles

**Original decision (2026-11-21; historical where the current decision differs).**

- The RF-One employee registry (*Anagrafica*) is authoritative: the role that applies is the one valid for the person, the location and the date of the work.
- Imported roles remain **only as historical evidence**.
- The external ID may link the source employee to the RF-One person.
- The imported role **never enters the calculation**, even when the registry has no assignment.

**Verified behaviour.**

- **At the source branch base `0e85cef`**, the Tips engine (`tips/distribution_engine.py`) resolves roles from `EmployeeAssignment` filtered by restaurant, role, validity dates and location. `Tips/README.md` invariant 7 already states this.
- **Open defect (outside this branch):** in the main working copy there is **uncommitted** local Tips work, outside this alignment and not in this branch: `tips/clover_role_history.py` plus changes to `distribution_engine.py`. It reads Clover role observations during calculation and blocks on "Clover role uncertain". It conflicts with this decision and must be reconciled before that work is committed.

**Current decision:** [OQ-7 in *Current Product Owner decisions*](#current-decisions); status in the table there. Under the current decision, creating the Student in Clover and storing the returned employee ID as POS ID are **still to implement**; the authoritative location and the canonical POS ID record are still for design (G-11).

**Aligned in:** [`Tips/README.md`](../../01%20Domains/Business%20Domain/Restaurant/Tips/README.md); [`Organization/Employee Assignment.md`](../../01%20Domains/Business%20Domain/Restaurant/Organization/Employee%20Assignment.md).

<a id="oq-8"></a>
### OQ-8 — Primary flow of Tips and Compensation first

**Original decision (2026-11-21; historical where the current decision differs).** The order of work is:

1. define the primary flow of the two modules;
2. define the data and connector contracts that flow needs (§5);
3. only then clean up old paths.

Designing the flow, and every functional choice still missing, belongs to design (Product Owner + ChatGPT).

**Contracts to prepare before implementation.** These are candidates drawn from existing documents; the final list and their content belong to design. Each one needs the §5 attributes.

- **Entity contracts:**
  - Location and Business Day (time zone, operating-day cutoff);
  - Employee and its external-ID link;
  - Employee Assignment (role per person, location and date — OQ-7);
  - Shift (clock-in/out, manager overrides);
  - Order, Payment, Payment Tip, Order Fee (gratuity/service charge), Refund;
  - data-coverage status (OQ-3);
  - correction event (OQ-2);
  - Tip Entitlement and FINAL Tips period, consumed by Compensation.
- **Connector contracts:**
  - Clover acquisition (orders, payments, refunds, shifts, employees — OQ-1, OQ-4);
  - the payroll-provider exchange that Compensation needs.

**Verified behaviour.** No complete contract document exists. `DATABASE_SCHEMA.md` and the connector documents cover parts of it.

**Current decision:** [OQ-8 in *Current Product Owner decisions*](#current-decisions); status in the table there.

**Aligned in:** `Tips/README.md`; [`Compensation/README.md`](../../01%20Domains/Shared%20Domains/Personnel%20Management/Compensation/README.md).

<a id="oq-9"></a>
### OQ-9 — Claude's choices

**Decision.** Claude decides the **technical details** that respect the approved specification. If a task would change **flow, schema, API or behaviour**, Claude stops and asks design.

**Aligned in:** `CLAUDE.md` (section *Operational database principle and development roles*, rule 2, and the MIEAF limit); [Codex checklist](../../03%20Software/Infrastructure/deploy/CODEX_INDEPENDENT_REVIEW_CHECKLIST.md) item 3.

<a id="oq-10"></a>
### OQ-10 — Examples in the Core

**Decision.** Only the affected sentences of Core documents 16 and 17 are updated. They now say that Cognito reads RF-One operational data, today fed by the Clover connector. The meaning of the examples and the rest of the approved texts are unchanged.

**Aligned in:** [`16_Ambient_Operational_Context_and_In-Flow_Cognito_Assistance.md`](../../00%20Core/ConceptualArchitecture/16_Ambient_Operational_Context_and_In-Flow_Cognito_Assistance.md) §9; [`17_Visual_Video_Context_as_Ambient_Evidence.md`](../../00%20Core/ConceptualArchitecture/17_Visual_Video_Context_as_Ambient_Evidence.md), restaurant example.

<a id="oq-11"></a>
### OQ-11 — Local work

**Decision.**

- Use a separate working copy, and preserve the changes already in the main working copy.
- Check the local versions of the relevant instructions.
- Respect the latest contextual-help and local-database rules.
- Keep unrelated local work out of the diff.

**Observed.** The main working copy holds **uncommitted** newer versions of these instructions, which are not on this branch:

- `CLAUDE.md`: contextual-help placement (2026-11-14) and local database storage (2026-11-13);
- `03 Software/Shared UI/How Works Standard.md` (not present on `main`) and `UI Rules.md`: help placement (2026-11-14);
- `LOCAL_ENVIRONMENT.md`: continuation procedure (2026-11-14).

They were **not copied** into this diff. Merging this branch must preserve them. The documentation prepared here complies with them: the only new UI element described (the OQ-3 modal) refers to the current help-placement and close-X rules, and no database location is prescribed.

**Aligned in:** [alignment register](../../07%20Tasks/Reports/RF1_OPERATIONAL_DATABASE_001_DOCUMENTATION_REGISTER.md) §8.

---

<a id="design-gaps"></a>
## 12. Points still for design (not decided)

These points go beyond the approved decisions. Claude does not resolve them; they return to design (Product Owner + ChatGPT).

| ID | Point | From | Status after the current decisions |
|---|---|---|---|
| G-1 | **Correction coverage per resource** (see the OQ-1 table): Refunds older than 48 h; detection of removed child records; discounts and tax; shifts. Also Clover API limits for 30-second live checks. Verify first, then design wherever a gap is confirmed. | OQ-1, OQ-4 | Open. Applies to the midnight modification check and to the 30 s acquisition of new records. |
| G-2 | How a correction that arrives after a FINAL Tips period is shown or handled. | OQ-2 | **Narrowed.** Current OQ-2: keep the latest Clover value, raw evidence for audit, no reopening of FINAL periods, native history deferred to RF POS design. The original question of which corrections to record as events no longer applies. Only the display/follow-up of a late correction remains undefined. |
| G-3 | **Coverage criterion:** which acquisition checkpoints must have passed the end of the period's last Business Day for the data to count as covering it. This decides when Calcola and Consolida are allowed, so it is a behaviour choice. | OQ-3 | Open. Now applies to both Calcola and Consolida, per location. |
| G-4 | **Automatic calculations.** Manual and scheduled calculations share one gated entry point today (`Tips Configuration.md` §9). Is the coverage check also the gate for scheduled automatic runs? | OQ-3 | Open. |
| G-5 | **Payment gate** still calls the Clover connector function directly (residual contradiction with §2/§6.2). | OQ-3 | Open. Current OQ-3 keeps payment readiness separate; changing it needs its own decision. |
| G-6 | **MyRF order state model** for the trial insertion of Server Tablet orders, after the Clover verifications (V3/V4, V6, V7). | OQ-5 | **Narrowed** to insertion. Changes and cancellations after acceptance, and other data types, are deferred. |
| G-7 | **Main Data Store enrichment field.** Adopting `enrichment_note` is a schema change and needs its own approved task. Still unverified: confirming in code that no re-import rewrites `description_original`. | OQ-6 | **Narrowed.** Current OQ-6 allows normalization only in a separate derived value, so a derived `description_normalized` next to the untouched original is compatible; adoption happens when the enrichers are connected to the main Data Store. |
| G-8 | **`SOURCE_ROLE_MAPPING` provenance.** An Employee Assignment can be seeded from a confirmed Clover SourceRole by an explicit action. Is this still a permitted way to create registry assignments? Also: reconcile the uncommitted main-copy Tips role-history work with OQ-7. | OQ-7 | Open. |
| G-9 | **Tips and Compensation contracts** (OQ-8 list): to be designed before implementation and before any cleanup of old paths. | OQ-8 | **Narrowed.** Current OQ-8 fixes the direction: Compensation pulls FINAL Tips from RF-One; Tips neither sends data nor starts Compensation. The contracts themselves remain to be designed. |
| G-10 | **Merge with the main working copy:** the uncommitted instruction updates (OQ-11) must be preserved when this branch is merged. | OQ-11 | Open. |
| G-11 | **Clover creation of the Student:** which record is authoritative for the competent location, and which record holds the canonical POS ID. | OQ-7 | Open (named as undecided in the current OQ-7). |
