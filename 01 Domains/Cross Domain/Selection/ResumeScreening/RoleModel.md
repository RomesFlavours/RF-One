# Role Model (Resume Screening)

**Version:** 0.1
**Status:** Draft (initial canonical foundation)
**Domain:** Selection / Resume Screening
**Origin:** TASK_SELECTION_001

---

## Purpose

Defines the generic, industry-agnostic shape a Role Configuration must have so [Experience Analysis and Trajectory](ExperienceAndTrajectory.md) can classify a candidate's Work History against the role actually being screened for. Selection Core defines only the *shape*; every concrete value (which roles are equivalent, propedeutic, adjacent) is Industry Extension / Client / Role Configuration content — see `README.md`, "Domain architecture."

---

## Shape

```text
RoleConfiguration
  target_role            the role being screened for (a normalized role code)
  equivalent_roles        roles that satisfy the same requirement directly (different title,
                            same substance — e.g. "Waiter"/"Waitress" for "Server")
  propedeutic_roles       roles that reasonably prepare a candidate for the target role, without
                            being the role itself (e.g. Busser -> Server)
  adjacent_roles          roles outside the target's own industry/function that still transfer
                            relevant capability (e.g. Retail Sales -> Server, both customer-facing)
  transition_flags        role categories whose transition into the target role should generate
                            an investigative question, not automatic exclusion (e.g. BOH -> Server)
```

A Work History record's `normalized_role` is classified against exactly one `RoleConfiguration` at a time — the one for the `target_role` the candidate is actually being screened for — into one of: `TARGET`, `EQUIVALENT`, `PROPEDEUTIC`, `ADJACENT`, or unclassified (`OTHER`).

---

## Role relevance coefficients — not defined here

A future refinement may weight each category's contribution differently (e.g. Equivalent counting more toward "Direct Role Experience" than Propedeutic). **This task does not define those weights.** They belong to Client/Role Configuration, never to Selection Core, and are explicitly out of scope until a Client actually needs them (`README.md`, "No universal CV score" — the same discipline applies to any future sub-indicator weighting, not only to a final score).

---

## Transition flags — investigation, not rejection

A `transition_flags` entry names a *category* of prior role (e.g. "BOH", "Management," "outside the industry entirely") whose move into the target role is worth an interview question, never an automatic disqualification — consistent with `ExperienceAndTrajectory.md`, "Do not infer motive." The Role Configuration only names which category transitions matter for this specific role; the actual question text and Flag shape are generic Resume Screening mechanics (see [FlagsAndIndicators.md](FlagsAndIndicators.md)).

---

## First concrete instance

Rome's Flavours' Server Role Configuration is the first real `RoleConfiguration` — defined under the Restaurant Industry Extension, not here: see `01 Domains/Business Domain/Restaurant/Selection/README.md`, "Rome's Flavours Server Role Configuration."
