# RF-One Software

## Purpose

`03 Software/` holds Runtime implementation: the actual code that executes, persists data, and interacts with external systems.

---

# Authority

Software is **authoritative for actual runtime behavior** — what the system actually does — but it is **not authoritative for the conceptual meaning** of Core, Domain or Product concepts. Implementation must follow `00 Core/ImplementationGuidelines.md` and must not redefine business meaning through code or configuration.

---

# What belongs here

- Application code, services, scripts and tooling (e.g. `InvoiceIntake/` — an invoice-intake prototype: upload → OCR/text extraction → review → Excel export).
- Runtime configuration, database access code, external API integrations.
- Cross-cutting runtime architecture documents that describe how the software itself is structured to run (e.g. `User Interaction Architecture.md`), as distinct from Core/Domain business meaning.

# What does not belong here

- Business concept definitions — `00 Core/` or `01 Domains/`.
- Generated documentation artifacts (API specs, agent specs, etc.) — `04 Generated Documentation/`.
- Conceptual/architectural documentation about business meaning, even if written by developers — that belongs in `00 Core/` or `01 Domains/`.

---

# Current modules

| Module | Description |
|---|---|
| Employee Directory (`RF-One Web/`, `RF-One Data Store/`) | Shared `Employee.id`, per-merchant Clover links/snapshots, identity review and internal management fields. Administration → Anagrafica dipendenti (`/administration/employees`). See `01 Domains/Shared Domains/Employee Directory/README.md`. |
| `InvoiceIntake/` | Local prototype web app validating the purchase-document intake flow (upload → OCR/extraction → review → RF-One Data Store, Excel as a secondary debug export only — TASK_PURCHASING_004). See `InvoiceIntake/README.md`. |
| `RF-One Data Store/` | The canonical RF-One operational database (SQLAlchemy + Alembic) — Restaurant/Sales (Clover ingestion), Administration/Payroll, and Restaurant/Purchasing (Purchase Document/Line, Physical Receiving, Alerts, Expected Supplier Credit — TASK_PURCHASING_004). See `RF-One Data Store/README.md`. |

`AI/`, `Backend/`, `Database/`, `Frontend/`, `Infrastructure/` are anticipated future module areas; they are created on demand rather than scaffolded empty in advance.

---

# Cross-cutting runtime architecture

| Document | Answers |
|---|---|
| [Shared UI/UI Rules.md](Shared%20UI/UI%20Rules.md) | How every RF-One screen shows times (Location local time, never UTC), employees ("Surname I."), frequent actions (where needed, calling the one central implementation) and navigation (clickable breadcrumb path on every sub-page)? Standing rules — UI_NAVIGATION_AND_LOCAL_TIME_001. |
| [User Interaction Architecture.md](User%20Interaction%20Architecture.md) | Which interfaces/devices does RF-One need, what kind of work happens on each, the initial authentication/authorization model, the role of mobile, the role of document/evidence capture, the responsive-web-app delivery decision, and the attention-driven Home principle? Documented — TASK_INTERACTION_001, extended by CORE_IDENTITY_AUTHORITY_SECURITY_ARCHITECTURE. |

**Moved:** `Identity Authority and Security Architecture.md` now lives at [`10 System/Identity & Access/Identity Authority and Security Architecture.md`](../10%20System/Identity%20%26%20Access/Identity%20Authority%20and%20Security%20Architecture.md) — Identity & Access is a system-level capability (neither a Domain nor a Product), not Software-owned architecture; see `10 System/README.md`. The existing software foundation implementing part of it (Acting Identity, Authority, Operational Signature) remains here, in `RF-One Data Store/` (see that document's "Current implementation references" for the exact files) — development is currently **FROZEN**.

## RF-One-owned person foundation — local implementation 2026-10-29

The included base directory now creates RF-One people without a POS or location.
Every unknown Clover record requires explicit reconciliation, including historical
references. Explicit context links connect accounts, human actors, Training,
Selection and project responsibles without grants or domain-fact rewrites.
Employee remains the compatibility person ID; employment is not directory state.
Migration d9e220261029 and a coordinated consuming-app release are required.
This entry records local implementation, not a completed AWS deployment.
See 07 Tasks/Reports/PERSON_FOUNDATION_003_REPORT.md from the repository root.

The person foundation was subsequently published on AWS on 2026-10-29. Exact
release and backup references: 07 Tasks/Reports/PERSON_FOUNDATION_003_AWS_REPORT.md.

## 2026-11-03 — Employee lifecycle and mandatory RF1 account (local, not deployed)

Branch codex/employee-directory, migration e3f120261103 (after d9e220261029).
Complete Clover roster + clock scans end single-site positions; the last ended
position dismisses the person at the latest clock-in and blocks RF1/Training access
(owner excepted). No-clock identities stay technical observations. Every registered
employee has exactly one RF1 account (INACTIVE shell or confirmed existing account).
Shared services: require_active_employee; organizational applicability in
employee_applicability (migration e4a120261103, EMPLOYEE_APPLICABILITY_001). Not on AWS;
AWS is ahead of this checkout (rfone-web 34a91a8, schema e1b220261102): rebase the
migration's down_revision and reconcile with current main before any release.
PO decisions approved 2026-11-03: owner keeps RF1 access while the person stays
dismissed; Workforce closes assignments; replaced shells stay INACTIVE, unlinked.
