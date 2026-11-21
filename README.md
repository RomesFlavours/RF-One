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
| `10 System/` | System-level capabilities spanning the whole platform (e.g. Identity & Access) — not a Domain, not a Product | Canonical for system-level architecture/boundary; implementation code stays in `03 Software/` |
| `90 Archive/` | Historical/superseded repository material | **Never** current authority, regardless of status text inside |

Top-level directories may contain a `README.md` explaining purpose and authority; check the actual tree before relying on it. In this baseline `07 Tasks/README.md` is absent.

---

## Where to start

- Canonical architecture: `00 Core/ConceptualArchitecture/00_RF-One_Core_Vision.md`
- Current Domain example: `01 Domains/Business Domain/Restaurant/README.md`
- Project instructions: `CLAUDE.md`
- Current repository state: `PROJECT_STATE.md`

## Agent entrypoints and review gate

- **Claude:** read [CLAUDE.md](CLAUDE.md) before every task. Claude implements approved specifications; it is **not** the autonomous RF-One architect.
- **Codex:** read [AGENTS.md](AGENTS.md) before every task. Codex independently reviews implementation against the approved specification and canonical documentation.
- **Authority:** Product Owner + ChatGPT define and approve the functional/architectural design; Claude implements; Codex independently reviews; Product Owner authorizes merge/deploy. Neither an agent's report nor passing tests constitute deployment authorization.
- **Source precedence:** canonical `00 Core/`, `01 Domains/`, `02 Products/`, `09 Strategy/` and `10 System/` documentation governs meaning in its own scope. `03 Software/` documents runtime; `07 Tasks/` and `PROJECT_STATE.md` provide dated evidence and history. Conflicting or missing approved decisions must be escalated, not invented.
- **Git discipline:** work on an explicit branch and commit. GitHub and local working copies are **not** automatically synchronized; fetch/pull/push or an explicitly configured sync is required. Do not merge documentation-only work into an active integration branch without checking its current head and reviewing the diff.

