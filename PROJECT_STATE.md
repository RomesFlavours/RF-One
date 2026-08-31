# PROJECT_STATE

Version: 2.0
Status: Active development

---

## Current state

- **Core 2.0** is documented and canonical — see `00 Core/ConceptualArchitecture/`. It establishes Subject ↔ Reality, Desire sovereignty, continuous Reality Check, Decision as a first-class Core concept, the Epistemic Boundary, Subject Sovereignty, Temporal Coherence, and the Business Autopilot / Delegated Authority / Intelligence Engine model.
- **Restaurant Domain** exists and is under active development under `01 Domains/Restaurant/` (Purchasing, Commercial Catalog, Sales, and shared Restaurant model documentation).
- **InvoiceIntake** exists as current software/prototype tooling under `03 Software/InvoiceIntake/` (upload → OCR/text extraction → review → RF-One Data Store, with Excel now a secondary debug export only — TASK_PURCHASING_004).
- **RF-One Data Store** (`03 Software/RF-One Data Store/`) is the canonical, vendor-independent operational database (SQLAlchemy + Alembic) — Restaurant/Sales via Clover ingestion, Administration/Payroll, and now Restaurant/Purchasing (Supplier, Supplier Product, Purchase Document/Line, Configured Expectation/Alert, Physical Receiving, Order vs Invoice vs Receiving reconciliation, Expected Supplier Credit) — see `03 Software/RF-One Data Store/PURCHASING.md` and `07 Tasks/Reports/TASK_PURCHASING_004_REPORT.md`.
- The repository has been migrated to the canonical top-level structure (`00 Core/` … `90 Archive/`) by `90 Archive/Task History/Tasks/TASK_CORE_005_Canonical_Repository_Migration.md`.
- The pre-Core-2.0 legacy repository has been archived, not deleted, under `90 Archive/Legacy Repository/`. A binding backlog of legacy concepts approved for future incorporation is tracked at `07 Tasks/Backlog/LEGACY_KNOWLEDGE_RECONCILIATION_BACKLOG.md`.
- Approved Core-level legacy reconciliation items (Early Failure Recognition, Recursive Process, Optimization Boundaries, optional Entity versioning/temporal semantics, Specialization, Ownership vs Assignment) have been incorporated into `00 Core/` — see `90 Archive/Task History/Reports/TASK_CORE_006_REPORT.md`.
- **`09 Strategy/`** is now populated with RF-One's own commercial/business-model strategy — business-first orientation, Business Autopilot as commercial direction, bounded optimization scope, economic value and measurement, service-delivery and knowledge-advantage positioning, and shared-intelligence/knowledge-governance principles — see `09 Strategy/README.md` and `90 Archive/Task History/Reports/TASK_CORE_007_REPORT.md`.
- The legacy `Knowledge Domains` taxonomy has been reconciled into a canonical business capability coverage map (`09 Strategy/04_Business_Capability_Coverage.md`) and a Restaurant Domain roadmap (`01 Domains/Restaurant/Roadmap.md`), without promoting any historical entry into a new modern Domain — see `90 Archive/Task History/Reports/TASK_CORE_008_REPORT.md`.
- The cross-layer Shared Domain review is complete (TASK_CORE_009 analysis, TASK_CORE_010 Product Owner decision canonicalization). No new Shared Domain was created. Commercial Catalog (`01 Domains/Restaurant/Commercial Catalog/`) remains under Restaurant and is recorded as the leading future extraction candidate, gated on a concrete second consumer. Shared Domain creation remains evidence-triggered rather than scheduled — see `90 Archive/Task History/Reports/TASK_CORE_009_REPORT.md`, `90 Archive/Task History/Reports/TASK_CORE_010_REPORT.md`, and `07 Tasks/Backlog/LEGACY_KNOWLEDGE_RECONCILIATION_BACKLOG.md` (Section J).
- Completed task specifications and reports (`TASK_CORE_001`–`TASK_CORE_010`) have been archived out of the active `07 Tasks/` workspace into `90 Archive/Task History/` — see `07 Tasks/Reports/TASK_CORE_011_REPORT.md`.
- The Restaurant/Purchasing model has been reconciled and canonicalized (Purchase Line `line_type`, Merchandise/Economic Classification, Effective Product Cost, Administration/Taxation boundary); the duplicate `Administration/Invoice Intake.md` model was removed — see `07 Tasks/Reports/TASK_PURCHASING_001_REPORT.md`.
- An initial cross-cutting User Interaction Architecture (desktop-first Web Application, mobile as a contextual/capture surface, User Identity/Authorization model, transversal document/evidence Capture) is documented at `03 Software/User Interaction Architecture.md` — see `07 Tasks/Reports/TASK_INTERACTION_001_REPORT.md`.

## Next planned work

- Expansion of business Domains and Products beyond the current Restaurant Domain and InvoiceIntake prototype.
- Future Runtime/Product design work implementing the knowledge-governance and shared-intelligence principles established in `09 Strategy/03_Shared_Intelligence_and_Knowledge_Governance.md`.
- Future Domain work on the Shared Domain candidates identified in `09 Strategy/04_Business_Capability_Coverage.md` (e.g. Workforce/Personnel, Equipment, Marketing, Reputation) once sufficient cross-Domain evidence justifies creating them — none is scheduled or approved to create now.

This is a factual snapshot; it is not itself canonical architecture. See `00 Core/Core Evolution.md` for the authoritative Core version history.
