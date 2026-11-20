# RF-One System

## Purpose

`10 System/` holds RF-One's **system-level capabilities**: platform-wide mechanisms that govern how the whole system operates — across Core, every Domain, every Product, and every piece of Software — without themselves being a business Domain or a commercial Product.

Per `CLAUDE.md`: **Core ≠ Domain ≠ Product ≠ Runtime.** `10 System/` adds one more distinction alongside that rule: **System ≠ Domain, and System ≠ Product.**

---

# Authority

Each area under `10 System/` is **canonical for its own operational/architectural mechanism**, subject to the Core concepts it implements. A System area does not redefine Core concepts, does not own Domain business meaning, and does not configure any specific Product.

---

# What belongs here

A capability belongs in `10 System/` when it is:

- **not a Domain** — it does not model a reusable business field (that is `01 Domains/`);
- **not a Product** — it is not a commercial configuration combining Domains for one customer offering (that is `02 Products/`);
- **genuinely cross-cutting** — it governs access, identity, or platform mechanics across the entire system, not one Domain's or one Product's concern;
- **operational, not conceptual** — it defines the operational system that implements/enforces abstract Core concepts, rather than defining what those concepts mean.

Examples: the global Identity & Access subsystem (see `Identity & Access/README.md`). Future system-level capabilities (e.g. platform-wide notification/messaging infrastructure, tenant/environment management) would also belong here if and when they are introduced — none is created by this document beyond Identity & Access.

# What does not belong here

- **Abstract Core concepts** (e.g. Subject, Authority, Delegation, Scope, Accountability) — these remain in `00 Core/`, which defines what they *mean*, domain-independent and technology-independent. `10 System/` never duplicates or re-defines a genuine Core concept merely because a System capability uses it.
- **Domain business meaning** (e.g. what Authority a specific business Decision requires, such as who may approve a Purchase Order) — that remains with the owning Domain in `01 Domains/`. A Domain determines *what* Authority its own Decisions require; System determines *how* Authority is authenticated, granted, scoped and enforced platform-wide.
- **Product-level configuration** (e.g. which concrete Company/Branch a real deployment has, or which Users hold which Authority for it) — that remains in `02 Products/`.
- **Implementation code** — actual runtime software (models, services, migrations, tests) stays in `03 Software/`, exactly where it already lives. `10 System/` holds the architectural/conceptual-boundary documentation for a system-level capability, never a copy or a move of its code.

---

# Current areas

| Area | Description |
|---|---|
| [Identity & Access/](Identity%20%26%20Access/README.md) | The global RF-One Identity & Access subsystem — User Account, Authentication, Authorization, Authority levels, Branch/Location scope, data visibility, individual overrides, and audit of authorization configuration. Implements the Core concepts defined in `00 Core/ConceptualArchitecture/09_Identity_Authority_and_Accountability.md` without redefining them. **Status: development FROZEN** — see its own README. |
| [Organizational Responsibility and Attention Management/](Organizational%20Responsibility%20and%20Attention%20Management/README.md) | Position/Position Scope/Occupant/Temporary Coverage/Process Ownership, and cross-Domain Attention Items with priority and routing resolution. Implements `00 Core/Organizational Responsibility.md` and `00 Core/ConceptualArchitecture/12_Attention_Management.md` without redefining them. **Status: active, minimum runtime implemented** — see its own README. |

---

## Related documents

- `CLAUDE.md` — Core ≠ Domain ≠ Product ≠ Runtime, and the canonical top-level repository structure
- `README.md` (repository root) — repository structure table
- `00 Core/ConceptualArchitecture/09_Identity_Authority_and_Accountability.md` — the Core conceptual definitions System capabilities implement
- `03 Software/README.md` — where the corresponding implementation code lives
