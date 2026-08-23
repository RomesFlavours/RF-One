# Legacy Knowledge Reconciliation Backlog

**Status:** Approved Product Owner backlog — binding for future work, not itself canonical architecture.
**Created by:** TASK_CORE_005 (Canonical Repository Migration).
**Source analysis:** `07 Tasks/TASK_CORE_004_Legacy_Knowledge_Reconciliation_Review.md` and its Legacy Knowledge Reconciliation Report.
**Purpose:** Ensure that valuable legacy concepts identified in `90 Archive/Legacy Repository/X00 Knowledge Repository/` are not forgotten now that the legacy repository has been moved into the non-authoritative archive.

This file is **not** Core, Domain, Product, or Strategy documentation. It does not define any concept. It records what the Product Owner has approved as worth incorporating later, what has been explicitly rejected, and what remains genuinely open — so that a future reconciliation task can act without re-deriving this analysis from scratch.

---

## A. Core items approved for future incorporation/strengthening

### Early Failure Recognition
**Approved.** Future canonical intent: recognizing early that a Goal is infeasible under known conditions, or that no known path currently exists, is a valuable RF-One outcome rather than a system failure. Must preserve the Core 2.0 distinction between demonstrated impossibility, current infeasibility, no known path, insufficient knowledge, and uncertainty.
Likely target: `00 Core/ConceptualArchitecture/02_Desire_Goal_and_Reality_Check.md`.
Not implemented in this migration.

### Optimization hierarchy
The old literal rule `Mission > Domain Principles > Business Rules > Goal > Execution` is **not approved as-is**.
Approved future principle: optimization and execution must remain subordinate to consciously confirmed Subject direction, active Goals, Constraints, Subject Sovereignty, Delegated Authority, applicable law/policy, and known risk limits.
Do not introduce `Mission` as a new Core primitive from legacy material without a separate architectural decision.
Likely targets: `00 Core/Process.md`, `00 Core/ConceptualArchitecture/06_Business_Autopilot_and_Intelligence_Engine.md`.

### Recursive Process
**Approved for future incorporation.** A Process may be recursively decomposed without requiring a separate universal ontology for `Activity`. Granularity does not automatically create a different class of thing.
Likely target: `00 Core/Process.md`.

### Process persistent status
The old rule "Process status must never be persisted; it must always be inferred" is **not approved as a universal Core rule**. Persistence vs derivation is a Runtime/Domain concern unless a specific semantic distinction is independently justified.
**Recorded as REJECTED AS UNIVERSAL CORE** / possible implementation pattern only.

### Entity versioning
**Approved as an optional Core pattern**, not as a requirement that every Entity must have a Version Entity. Future intent: RF-One Core should be able to represent stable conceptual identity separately from versioned definitions where a Domain requires it.
Likely target: `00 Core/Entity.md`.

### Temporal semantics
**Approved as a Core capability/pattern.** Do not mandate specific database fields such as `EffectiveFrom` / `EffectiveTo` at ontology level. Future intent: Core must allow temporal validity and historical reconstruction where a Domain/Runtime requires it.
Likely target: `00 Core/Entity.md`.

### Hybrid Event Model
**Not** approved for promotion into universal Core ontology. The claim that immutable Events must universally generate Entity state is an implementation/runtime architectural pattern.
Recorded as: MOVE TO SOFTWARE/RUNTIME / future architecture pattern, unless a later architectural task establishes stronger universal semantics.

### Ownership vs Assignment
**Approved for future clarification** as a generic modeling distinction where useful. Ownership and Assignment must not be treated as synonyms. Do not yet prescribe a universal cardinality or data model.
Likely targets: `00 Core/Relationship.md`, `00 Core/Glossary.md`.

### Specialization extends rather than erases identity
**Approved for future strengthening** as a generic Core modeling pattern: a specialization may extend a more general concept without silently replacing the identity/meaning of the general concept.
Likely target: `00 Core/Entity.md`.

### Capacity / Availability / Responsibility placement
Do **not** generalize the historical rules (Capacity belongs to physical provider; Availability belongs to smallest responsible Entity; Responsibility belongs to smallest responsible Entity) into universal Core principles yet. Keep existing valid specific rules where they currently live (`00 Core/Operational Unit.md`).
Recorded for future review when multiple Domains provide enough evidence to generalize.

### Capabilities Enable Services
Do not elevate into a new universal Core principle yet. Recorded for later review as a possible Relationship/Domain modeling pattern.

### Simplicity Before Generalization
Treat as an architecture/development principle, not ontology. If later incorporated, likely target: `CLAUDE.md`, `00 Core/ImplementationGuidelines.md`. Not implemented now.

---

## B. Operational Unit legacy items

Do not import the historical physical-business lifecycle (`Planning → Legal Creation → Site Acquisition → Construction/Setup → Licensing → Operational → Closed...`) as a universal Core lifecycle — it is too specific to certain physical/business Operational Units.
Recorded as a candidate for `01 Domains/_Shared/` or a relevant specific Domain. The generic Core Entity lifecycle remains separate and unchanged.

---

## C. Corporate legacy items

- **Legal identity fields:** do not expand Core now with detailed jurisdiction-specific legal fields. Recorded for Shared Domain / future Legal-Governance Domain review.
- **Corporate Documents:** keep out of Core. Candidate for future Domain/Runtime data model.
- **AI Governance:** approved distinction — universal Delegated Authority / Subject Sovereignty principles remain Core; RF-One company governance policy belongs under `09 Strategy/`; the production workflow for AI-proposed knowledge evolution belongs to Product/Software Runtime. Do not duplicate these layers.

---

## D. Brand legacy items

Marketing execution details are not Core Brand ontology. Recorded as Shared Domain / future Marketing capability knowledge.

The broader approved future direction remains:

```text
Goals
→ Brand
→ Service Model
→ Behaviors
→ Selection / Training / Performance
```

but this relationship is a **future architectural/domain task** and must not be silently implemented during repository migration. Future Domains such as Workforce, Selection, and Training remain valid planned directions (already listed as examples in `CLAUDE.md`), not yet created.

---

## E. Commercial strategy items

Approved for future review/canonicalization under `09 Strategy/`, not Core:

- measurable economic value as RF-One commercial objective;
- Cash-Based Profit as a historical business metric candidate;
- operational vs strategic economic horizons;
- counterfactual measurement of value generated;
- Business Knowledge Platform positioning;
- service/SaaS delivery rationale;
- shared-intelligence/network-effect strategy;
- company-level knowledge governance;
- Product portfolio strategy.

**Maximize Economic Profit:** do not encode as universal Core Goal. Treat as RF-One commercial/business strategy only.

**Unlimited Optimization Scope:** do not preserve the old absolute wording. Approved future interpretation: RF-One may optimize across any business area for which it has relevant Domain knowledge, sufficient Reality information, Delegated Authority, compatible confirmed Goals, applicable Constraints, acceptable risk, and legal/policy permission. This is a commercial/product scope principle, not ontology.

**Counterfactual value measurement:** approved as strategically important for demonstrating B2B value. Do not redefine generic Core Outcome solely around financial counterfactuals. Future Product/Strategy logic may compare actual outcome vs estimated counterfactual outcome without RF-One intervention to estimate value generated.

---

## F. Service / SaaS / shared intelligence legacy material

Preserve the strategic insight that RF-One's proprietary value is primarily accumulated knowledge, ontology, orchestration, decision/outcome learning, and Domain intelligence rather than commodity software primitives.

Do **not** retain the absolute historical claim "RF-One can never be sold as software" as an immutable architectural law. Recorded as a commercial/service-delivery strategy subject to future Product Owner review.

**Shared intelligence:** any future cross-customer learning strategy must explicitly preserve tenant isolation, confidentiality, privacy, contractual restrictions, data ownership, provenance, governance, and abstraction/anonymization where required. Do not assume that customer-specific knowledge may be freely shared across tenants. Only generalized/approved knowledge may become platform-level knowledge under an explicit governance model.

---

## G. Knowledge Domains taxonomy

The historical `Knowledge Domains` list (`90 Archive/Legacy Repository/X00 Knowledge Repository/05 Knowledge Domains/README.md`) is approved for preservation as a capability/coverage map, **not** as modern RF-One architectural `Domain` ontology.

Future action:

- use relevant Restaurant areas as input to a Restaurant Domain roadmap;
- classify cross-business areas separately;
- do not rename all historical Knowledge Domains into top-level modern Domains.

---

## H. Interview-driven Knowledge Engineering

Preserve as an optional knowledge-acquisition method, not a mandatory RF-One architecture. The historical interview template remains in Archive for now. A future Research/Methods task may create a modern interview methodology under `05 Research/Methods/` if needed.

---

## I. Corporate legal detail priority

Detailed Corporate Legal Identity / Corporate Documents are low-priority backlog. Do not expand Core or Domain now solely to preserve those fields. The legacy source remains available in `90 Archive/Legacy Repository/X00 Knowledge Repository/06 Business Model/Corporate.md`.

---

## Status of items not listed above

Any legacy concept identified in the TASK_CORE_004 report that is not explicitly listed here (e.g. stub/empty legacy files, fully superseded Desire/Decision/Goal/Process claims already reconciled in Core Evolution history) requires no further action and may remain historical-only in `90 Archive/`.
