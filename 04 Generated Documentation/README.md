# RF-One Generated Documentation

## Purpose

`04 Generated Documentation/` holds derived/generated material — documentation produced from implementation or from canonical specifications, rather than authored directly as architecture.

---

# Authority

Generated documentation is **never the primary architectural source of truth**. It must be regenerated from authoritative sources (`00 Core/`, `01 Domains/`, `02 Products/`) rather than hand-edited as if it defined architecture. If generated content and canonical documentation disagree, canonical documentation wins and the generated content is stale.

---

# What belongs here

Material produced by tooling or derived from canonical sources, such as:

- API documentation generated from an implementation;
- Database documentation generated from a schema;
- Agent Specifications generated from Core/Domain definitions;
- Functional Specifications derived from approved Domain documentation;
- Prompt Library entries generated/versioned for Intelligence Engine use;
- Test Cases derived from Business Rules and Acceptance Criteria.

# What does not belong here

- Hand-authored conceptual or architectural definitions — those belong in `00 Core/`, `01 Domains/` or `02 Products/`.
- Anything intended to be edited directly as a source of truth.

---

# Current status

No generated documentation exists yet. Subdirectories (`API/`, `Agent Specifications/`, `Database/`, `Functional Specifications/`, `Prompt Library/`, `Test Cases/`) are created on demand, once there is an actual generation process and durable output to hold, rather than scaffolded empty in advance.
