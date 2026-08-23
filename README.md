# RF-One

RF-One is built around a **domain-independent Core** that models a Subject in relation to Reality, and supports Desire, Goal, Decision, Action, Outcome and Learning. Application Domains (e.g. Restaurant) apply the Core to specific fields; commercial Products combine one or more Domains.

**Core ≠ Domain ≠ Product ≠ Runtime.** See `CLAUDE.md` for the full project instructions and architectural rules.

RF-One Core 2.0 (Subject ↔ Reality, Desire sovereignty, continuous Reality Check, Decision as a first-class Core concept, Epistemic Boundary, Subject Sovereignty, Temporal Coherence, Business Autopilot) is the current canonical conceptual architecture — see `00 Core/ConceptualArchitecture/00_RF-One_Core_Vision.md`.

---

## Repository structure

| Directory | Layer | Authority |
|---|---|---|
| `00 Core/` | Universal RF-One ontology and conceptual architecture | Highest — canonical for all Domains |
| `01 Domains/` | Reusable business Domains built on Core (e.g. `Restaurant/`) | Canonical for their own field |
| `02 Products/` | Commercial applications combining Core + Domains | Canonical for their own configuration |
| `03 Software/` | Runtime implementation (e.g. `InvoiceIntake/`) | Authoritative for behavior, not for concept meaning |
| `04 Generated Documentation/` | Derived/generated material | Never a source of truth |
| `05 Research/` | Exploration, competitor studies, technical investigation | Not canonical |
| `06 Meetings/` | Meeting notes | Not canonical |
| `07 Tasks/` | Task specifications, execution reports, backlog | Historical record, not live specification |
| `08 External/` | External collaborator material (e.g. `Shelbi/`) | Reference/input only |
| `09 Strategy/` | RF-One's own company/product strategy | Canonical for company strategy once populated |
| `90 Archive/` | Historical/superseded repository material | **Never** current authority, regardless of status text inside |

Each top-level directory has its own `README.md` explaining its purpose, authority level, and what does/does not belong there.

---

## Where to start

- Canonical architecture: `00 Core/ConceptualArchitecture/00_RF-One_Core_Vision.md`
- Current Domain example: `01 Domains/Restaurant/README.md`
- Project instructions: `CLAUDE.md`
- Current repository state: `PROJECT_STATE.md`
