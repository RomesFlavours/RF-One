# RF-One documentation alignment audit — 2026-11-21

**Status:** Review findings; no canonical business decisions amended by this report.
**Baseline inspected:** `integration/live-2026-11-20`.
**Working branch:** `docs/agent-governance-alignment`.
**Scope:** documentation governance and selected Core/Domain/System/Infrastructure references. This is not a full repository or production audit.

## Verified findings

1. **Agent role mismatch — addressed in this branch.** Root `CLAUDE.md` previously instructed Claude to act as a “Repository Architect, Implementation Engineer and Consistency Reviewer”. Product Owner governance requires approved design first, Claude implementation, independent Codex review, and Product Owner deployment authorization. Updated the role section in `CLAUDE.md` without changing Core or Domain architecture.
2. **Codex entrypoint missing — addressed in this branch.** No `AGENTS.md` existed in the inspected baseline. Added a root `AGENTS.md` with canonical-source discovery and independent-review procedure.
3. **Selection → Training → employment timing — requires canonical reconciliation, NOT silently changed.** `01 Domains/Shared Domains/PERSON_CONTINUITY_001.md` §1 and §6 describe Candidate → Employee → Training. `01 Domains/Shared Domains/Selection/SELECTION_PILL_ASSESSMENT_AND_TRAINING_READINESS_001.md` §6 describes handoff at hiring; `Selection/SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md` §7 also refers to Employee identity. The subsequently approved operational workflow is Candidate → Selection → Registry Trainee → Training → manager-confirmed Employee, preserving one Registry identity. Confirm authoritative approved workflow and affected documents before editing conceptual text; distinguish the general cross-industry Selection/Training service boundary from the restaurant-specific runtime workflow.
4. **Project status may be stale — verification required.** `PROJECT_STATE.md` records historical Training readiness/test results and Mount Dora onboarding status. Treat these as dated claims, not live AWS evidence. Verify against current services, releases and migrations before changing operational status assertions.
5. **Multisite invariants exist already.** `01 Domains/Business Domain/Restaurant/Restaurant Semantic Model.md` §3 and §8 establish one Rome's Flavours Brand, two Locations, and location-specific assignments without duplicating Employee identity. `00 Core/ArchitecturePrinciples.md` and `00 Core/ImplementationGuidelines.md` require canonical data ownership and connector mapping. Do not rewrite these principles or invent new blocking controls.
6. **Integration verification remains open.** `03 Software/Infrastructure/integration-2026-11-20/verify-later.txt` lists remaining compatibility and migration checks. Do not mistake branch creation or a documentation-only change for validation of those runtime issues.

## Scope of this branch

- Modified: `CLAUDE.md` — agent role and mandatory independent review.
- Added: `AGENTS.md` — Codex reviewer instructions.
- Added: this audit report.
- **Not modified:** canonical Core/Domain decisions, Selection/Training lifecycle specifications, software, database, migrations, AWS, `main`, or Shelbi's integration branch.

## Required next checks before canonical changes

- Verify the latest approved Selection → Training → Registry workflow and locate its source of authority; reconcile all affected canonical references in one coherent change.
- Verify latest multisite requirements against current implementation and document only confirmed gaps.
- Verify live AWS state independently before updating `PROJECT_STATE.md`.
- Obtain independent Codex review of this documentation branch and Product Owner approval before merge. No deploy is implied.
