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

# What does not belong here

- Business concept definitions — `00 Core/` or `01 Domains/`.
- Generated documentation artifacts (API specs, agent specs, etc.) — `04 Generated Documentation/`.
- Conceptual/architectural documentation, even if written by developers.

---

# Current modules

| Module | Description |
|---|---|
| `InvoiceIntake/` | Local prototype web app validating the purchase-document intake flow (upload → OCR/extraction → review → Excel). See `InvoiceIntake/README.md`. |

`AI/`, `Backend/`, `Database/`, `Frontend/`, `Infrastructure/` are anticipated future module areas; they are created on demand rather than scaffolded empty in advance.
