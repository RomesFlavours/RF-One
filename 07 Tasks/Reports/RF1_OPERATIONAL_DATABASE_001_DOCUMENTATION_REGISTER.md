# RF1_OPERATIONAL_DATABASE_001 — documentation alignment register

**Date:** 2026-11-21 · **Author:** Claude (implementation) · **For:** Codex independent review, then Product Owner.
**Decision:** [`10 System/Operational Database and Data Governance/README.md`](../../10%20System/Operational%20Database%20and%20Data%20Governance/README.md) (verbatim original: `SOURCE_DECISION_IT.md`).
**Branch:** `docs/rf1-operational-database-principle`, created from `handoff/2026-10-17` @ `0e85cef`, worktree `C:\Users\servi\rfone-wt\docs-operational-db-principle`. One local documentation commit. **No code, database, configuration, credential or AWS change; no push, merge or deployment.**

---

## 1. Method

1. Inventory: all 490 Markdown files of the repository at `0e85cef` searched for Clover, OpenTable, connector, enrichment, RF POS, direct provider access, Codex and agent instructions; 115 files outside `90 Archive/` mention Clover/OpenTable. Every file was classified as *normative/current*, *connector/source analysis*, or *historical record*.
2. Other local RF-One locations inspected (§6).
3. Each current normative statement compared with the decision; contradictions corrected with the smallest wording change, or recorded as open questions when the decision does not define the answer.
4. Diagrams: no diagram files (`.mmd`, `.drawio`, `.puml`, `.svg`) exist; text diagrams inside Markdown were updated where they showed a non-conforming flow.

## 2. New documents

| Path | Purpose |
|---|---|
| `10 System/Operational Database and Data Governance/README.md` | **Single reference specification** (English, faithful to the approved text) + non-normative relationship table (§10) + open questions (§11). |
| `10 System/Operational Database and Data Governance/SOURCE_DECISION_IT.md` | Verbatim approved Italian decision, immutable; prevails over the English rendering. |
| `03 Software/Infrastructure/deploy/CODEX_INDEPENDENT_REVIEW_CHECKLIST.md` | Codex independent architectural review checklist. **No Codex checklist existed before**; created as required by decision §7/§10.4. |
| `07 Tasks/Reports/RF1_OPERATIONAL_DATABASE_001_DOCUMENTATION_REGISTER.md` | This register. |

## 3. Updated documents

| # | Path | Section | Change |
|---|---|---|---|
| 1 | `CLAUDE.md` | new top section *Operational database principle and development roles*; *Role of Claude*; *External Technology*; *MIEAF* | Binding Claude instructions: implement complete approved specs, no autonomous design, stop and submit undefined choices, Codex review, release only on explicit approval; "Repository Architect" clarified; provider abstraction made mandatory for data sources; MIEAF limited for design choices (boundary = OQ-9). |
| 2 | `AGENTS.md` | standing rules list | Pointer for Codex/other agents: roles + checklist + spec (file grows no rules of its own). |
| 3 | `README.md` | Where to start | Link to the spec. |
| 4 | `10 System/README.md` | Current areas | New area row. |
| 5 | `PROJECT_STATE.md` | Current reality index | Principle summary + pointers. |
| 6 | `00 Core/ArchitecturePrinciples.md` | Source Independence | Pointer: principle made binding at system level. Core meaning unchanged. |
| 7 | `00 Core/ExternalDataMappingPrinciples.md` | new closing section | Mapping Layer ↔ connector + common ingestion; no redefinition. |
| 8 | `00 Core/ImplementationGuidelines.md` | External Systems | Pointer to the mandatory path. |
| 9 | `03 Software/README.md` | Data Store row | Ownership/independence + pointer. |
| 10 | `03 Software/RF-One Data Store/README.md` | header + flow diagram | Governing note; diagram replaced with the 5-step mandatory flow (old diagram noted as superseded). |
| 11 | `03 Software/RF-One Data Store/DATABASE_SCHEMA.md` | introduction | Schema structure is RF-One's; Clover documents are evidence, not authority; external IDs = provenance. |
| 12 | `03 Software/RF-One Data Store/CLOVER_INGESTION.md` | header | Historical load = separate initialization; shared service; Domains read canonical DB. |
| 13 | `03 Software/RF-One Data Store/CLOVER_CONTINUOUS_SYNCHRONIZATION_ARCHITECTURE.md` | header, §1, §6, §7, §8 | Precedence of the decision; Clover "source operational system / system of record" qualified as replaceable source (OQ-2); rule extended from Cognito to every Domain; Tips direct connector call recorded as residual contradiction (OQ-3); 30 s vs 15/60 s left open (OQ-1). |
| 14 | `03 Software/Clover Data Explorer/README.md` | header (Italian) | Discovery/evidence only; never read by Domains. |
| 15 | `03 Software/Clover Data Explorer/CLOVER_RESTAURANT_DATA_MAPPING.md` | header | Connector-level mapping, not model authority. |
| 16 | `03 Software/Infrastructure/README.md` | Clover jobs section (Italian) | Clover jobs = shared acquisition service; `rfone-tips` image = packaging only. |
| 17 | `03 Software/Infrastructure/deploy/clover-acquisition-job/README.md` | header | Same; OQ-1, OQ-4. |
| 18 | `03 Software/Infrastructure/deploy/clover-correction-sync/README.md` | header | Same; runs per Location today (OQ-4). |
| 19 | `03 Software/Infrastructure/deploy/RELEASE_CHECKLIST.md` | intro + new step 8 | Codex review with no open deviation + explicit PO approval before push/merge/deploy. The sentence "introduces no new approval requirement" was replaced because the decision introduces one. |
| 20 | `01 Domains/Business Domain/Restaurant/Tips/Tips Configuration.md` | header, Purpose diagram, §3, §10 | Tips reads RF-One data only; diagram source renamed to RF-One canonical data; residual contradiction OQ-3. |
| 21 | `01 Domains/.../Functional Specifications/TIP_DISTRIBUTION_ENGINE_FUNCTIONAL_SPEC_001.md` | clock-in/out source sentence | Clover = originating source; engine reads canonical DB only. |
| 22 | `01 Domains/Shared Domains/Administration/Compensation/README.md` | hours bullet | "acquired Clover Shifts" → canonical Shifts (currently acquired from Clover). |
| 23 | `01 Domains/Business Domain/Restaurant/MyRF/Server Tablet/README.md` | Definizioni concordate (Italian) | MyRF reads RF-One canonical data; outbound order sending to Clover = OQ-5. |
| 24 | `01 Domains/Shared Domains/Administration/Bank Reconciliation/README.md` | new section *Enrichers and canonical fields* | Decision §4 for Bank: enrichment field distinct from description/memo; WHO/WHY canonical fields only; field name open (OQ-6). |
| 25 | `01 Domains/Business Domain/Restaurant/Dining Intelligence/README.md` | Reservation / Guest platforms | OpenTable/Resy adapters follow the mandatory flow. |

## 4. Residual contradictions and open questions (not decided)

Recorded also in the spec §11. Each returns to design (Product Owner + ChatGPT).

| ID | Contradiction / gap | Affected files | Why it matters | Smallest correction (proposal, not applied) |
|---|---|---|---|---|
| OQ-1 | 30 s target vs approved ~15 s (new records) + ~60 s (modifications). | `CLOVER_CONTINUOUS_SYNCHRONIZATION_ARCHITECTURE.md` §2–§3, §5, §11; `deploy/clover-correction-sync/README.md`; `live_sync.py`/`correction_sync.py` defaults (code, untouched). | Two approved cadences coexist. | PO states whether 30 s replaces, bounds or complements the existing cadence. |
| OQ-2 | "Clover remains system of record for POS history"; RF-One keeps only corrected state (correction in place) vs Core *Historical Integrity* and replaceable sources. | `CLOVER_CONTINUOUS_SYNCHRONIZATION_ARCHITECTURE.md` §1, §8 (qualified, not removed); `00 Core/ArchitecturePrinciples.md` *Historical Integrity*. | When Clover is replaced by RF POS, transactional history has no defined owner. | Design the history/correction model for canonical operational facts. |
| OQ-3 | Tips calculation and payment readiness call `technical.connectors.clover.correction_sync.describe_reconciliation_status()` directly. | `Tips Configuration.md` §3, §10; `CLOVER_CONTINUOUS_SYNCHRONIZATION_ARCHITECTURE.md` §7; `Tips Payment Execution.md` (reference only); code `tips/readiness.py`, `tips/payment_readiness.py`. | A Domain depends on a provider connector (decision §2, §6.2); RF POS would require a Tips change. | Design a source-neutral RF-One readiness/consolidation interface. |
| OQ-4 | Live Sync and Correction Poller are per Location (`--location-id 1` on AWS); decision requires one shared service for all locations. | deploy READMEs; multisite release plan on branch `feature/clover-multisite-registry` (§6). | Multi-site rollout may multiply per-site processes. | Define how the one service covers all locations. |
| OQ-5 | Outbound writes to an external POS (MyRF orders to Clover) and RF POS write path not defined. | `MyRF/Server Tablet/README.md`, `03-Tavolo-e-Percorso-Ordine.md`, `05-Verifiche-Integrazione-Clover.md`. | Write-back bypasses the inbound flow definition. | Design the outbound connector contract. |
| OQ-6 | Enrichment field name/location undocumented; separate RFBank repo commit `b2d8c38` says enricher output is "the Memo". | `Bank Reconciliation/README.md`; `RF One/RFBank` (separate repo, not modified). | Decision requires a field distinct from the original memo. | Verify RFBank semantics; design the canonical field. |
| OQ-7 | `SourceRole`/`EmployeeSourceRole`/`SourceRoleMapping` keep required source identity and are read by Tips/Organization flows. | `DATABASE_SCHEMA.md` §4, §4c; `RESTAURANT_PROFILE.md`; `Organization/README.md`; multisite branch `SOURCE_ROLE_MAPPING_RETIREMENT.md`. | May be provider-shaped Domain inputs. | Decide permitted status or retirement. |
| OQ-8 | No complete per-entity / per-connector contract set with all decision §5 attributes. | `DATABASE_SCHEMA.md` (partial), connector docs. | Required before further implementation. | Produce the contracts in design. |
| OQ-9 | MIEAF "choose technical alternatives yourself" vs decision §7 "no autonomous design". | `CLAUDE.md` MIEAF (limit added). | Unclear boundary could make Claude either over-decide or over-escalate. | PO confirms the boundary. |
| OQ-10 | Ratified Core extensions use Clover as illustrative live source ("Clover reporting no open order"). | `00 Core/ConceptualArchitecture/16_…md` line 164, `17_…md` line 110. | Wording only; not prescriptive. Not modified to avoid altering ratified Core text without Core Evolution approval. | PO may approve a wording fix ("RF-One operational data, currently fed by Clover"). |
| OQ-11 | Base of this branch vs the Product Owner's working copy: the main checkout has **uncommitted** edits to `CLAUDE.md` (contextual-help placement 2026-11-14, local DB policy 2026-11-13) and other docs not present at `0e85cef`. | `CLAUDE.md`, `How Works Standard.md`, `UI Rules.md`, `LOCAL_ENVIRONMENT.md`. | Merging this branch into the working copy needs the uncommitted edits preserved (same files, different sections — no textual overlap expected). | At merge time: commit or stash those edits first, then merge. |

## 5. Historical documents

**Marked historical with a link to the decision (banner only, body unchanged):**
`07 Tasks/Reports/CLOVER_TIPS_INGESTION_001.md` (Clover import inside Tips), `CLOVER_DATA_ACQUISITION_ARCHITECTURE_001.md`, `TECHNICAL_CONNECTORS_STRUCTURE_001.md`, `RFONE_OPERATIONAL_DATA_MODEL_001.md`, `TIPS_IMPORT_CONCURRENCY_GUARD_001.md` (Tips "Import from Clover").

**Not modified — execution records already historical by repository rule** (`07 Tasks/` = historical record, root `README.md`): all other `07 Tasks/Reports/*` and `07 Tasks/Scambio-C/*` mentioning Clover (e.g. `CLOVER_ACQUISITION_JOBS_001`, `CLOVER_ACQUISITION_SAFETY_001`, `CLOVER_ACQUISITION_IDENTITY_001`, `CLOVER_AWS_MASTER_RECOVERY_20261019`, `CLOVER_EMPLOYEE_*_20261019`, `CLOVER_TIPS_DATA_PROBE_001`, `TASK_SALES_00x_REPORT`, `TASK_ORGANIZATION_00x_REPORT`, `TIPS_*_20261019`, `REGISTRY_CLOVER_AWS_RELEASE_20261111`, `PRE_COMMIT_AUDIT`, `RF_ONE_GLOBAL_INTEGRITY_REVIEW_001`, `UI_NAVIGATION_AND_LOCAL_TIME_001`, `002-consolidamento-anagrafica-aws-report`), and all of `90 Archive/` (never current authority).

**Reviewed, already consistent, not modified:** `CLOVER_INGESTION_RECONCILIATION.md` (one run's results); Clover Data Explorer analysis files (`CLOVER_DATA_CAPABILITY_MATRIX`, `CLOVER_SOURCE_RELATIONSHIP_MAP`, `CLOVER_ATOMIC_DERIVED_FACTS`, `CLOVER_EXPORT_*`, `CLOVER_DATA_DISCOVERY` — source evidence, covered by the README banner); `RESTAURANT_PROFILE.md`, `PAYROLL.md`, `PURCHASING.md`, `KITCHEN.md`; Restaurant `Sales/Restaurant Sales Model.md`, `Restaurant Semantic Model.md`, `Organization/*`, `Tips/README.md`, `Tip*.md`, `Server Performance/*`, `Dining Intelligence/Customer Consumption Profile.md`; `Invoice Intake/*`; `Performance/*`; `Intercompany Funding & Settlement/*`; `03 Software/Shared UI/UI Rules.md` (Clover Acquisition is a central RF-One page, Tips links to the one implementation); `LOCAL_ENVIRONMENT.md` (environment facts only). Empty scaffold files `Restaurant/Sales/Clover/*` (0 bytes) left untouched.

**Not found in the repository:** RF POS documentation, OpenTable integration specification, API specifications, migration/acceptance-test plans specific to the operational database, data-diagram files. Nothing to update; their future creation must follow the decision.

## 6. Other local RF-One locations (inspected, not modified)

| Location | Nature | Finding |
|---|---|---|
| ~45 Git worktrees of this repository (`rfone-wt/*`, `.codex/worktrees/*`, `rf-one-*`, `RF1 Sviluppo/*`) | other branches of the same repo | Inherit this alignment when merged. **`feature/clover-multisite-registry`** (and its `release/clover-multisite-*` branches) carry `03 Software/Infrastructure/deploy/CLOVER_MULTISITE_RELEASE_PLAN.md`, `REGISTRY_CLOVER_DEPARTMENTS_RELEASE_PLAN.md`, `tips/SOURCE_ROLE_MAPPING_RETIREMENT.md`, not on this base: to be aligned on merge (OQ-4, OQ-7). Not edited: outside this single branch. |
| `RF One/RFBank` | separate Git repo | `PAYPAL_IMPORT.md`; enricher semantics see OQ-6. |
| `Bank 1.0` | separate Git repo (superseded as base) | no relevant mention. |
| `Bank/`, `BankAWS/`, `rf-one-main-pristine/`, `rf-one-2.0-release/`, `Models-Shelby & Pino/` | non-Git copies / archives | contain older copies of repository docs; not version-controlled, so not updatable within a commit; not current authority. |

## 7. Checks performed

- All new relative links to the spec, checklist, register and source decision resolve (scripted check).
- Every anchored edit matched exactly once before writing (scripted, all-or-nothing).
- `git diff` contains only `.md` files; no code, migration, configuration or data file touched.
- Acceptance criteria of decision §9: one model and one end-to-end path stated in the spec and linked from Core, Data Store, Domains and agent instructions — **met at documentation level**; "no contradictory instructions" — **met except the items of §4**, which are listed rather than resolved, as instructed.
