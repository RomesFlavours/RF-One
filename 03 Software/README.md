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
| `InvoiceIntake/` | Local prototype web app validating the purchase-document intake flow (upload → OCR/extraction → review → RF-One Data Store, Excel as a secondary debug export only — TASK_PURCHASING_004). See `InvoiceIntake/README.md`. |
| `RF-One Data Store/` | The canonical RF-One operational database (SQLAlchemy + Alembic) — Restaurant/Sales (Clover ingestion), Administration/Payroll, and Restaurant/Purchasing (Purchase Document/Line, Physical Receiving, Alerts, Expected Supplier Credit — TASK_PURCHASING_004). See `RF-One Data Store/README.md`. |

`AI/`, `Backend/`, `Database/`, `Frontend/`, `Infrastructure/` are anticipated future module areas; they are created on demand rather than scaffolded empty in advance.

---

# Cross-cutting runtime architecture

| Document | Answers |
|---|---|
| [User Interaction Architecture.md](User%20Interaction%20Architecture.md) | Which interfaces/devices does RF-One need, what kind of work happens on each, the initial authentication/authorization model, the role of mobile, and the role of document/evidence capture? Documented — TASK_INTERACTION_001. |
