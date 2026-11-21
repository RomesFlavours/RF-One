# RF-One documentation alignment audit — 2026-11-21

**Status:** Review findings; no canonical business decisions amended by this report.
**Evidence source examined:** `integration/live-2026-11-20` at immutable commit [`7a4a126e721024fed32751190330850312772022`](https://github.com/RomesFlavours/RF-One/tree/7a4a126e721024fed32751190330850312772022). Those integration files are **not** present on `main` at the PR #2 base.
**PR #2 target:** `main` at base commit `9c154f996080614054f5d512b93a6156b43f9630`.
**PR #2 working branch:** `docs/agent-governance-main-20261121`. PR #1 (`docs/agent-governance-alignment`) is a separate proposal against the integration branch; do not merge both.
**Scope:** documentation governance and selected Core/Domain/System/Infrastructure references. This is not a full repository or production audit.

## Verified findings

1. **Agent role mismatch — addressed in this branch.** Root `CLAUDE.md` previously instructed Claude to act as a “Repository Architect, Implementation Engineer and Consistency Reviewer”. Product Owner governance requires approved design first, Claude implementation, independent Codex review, and Product Owner deployment authorization. Updated the role section in `CLAUDE.md` without changing Core or Domain architecture.
2. **Codex entrypoint missing — addressed in this branch.** No `AGENTS.md` existed in the inspected baseline. Added a root `AGENTS.md` with canonical-source discovery and independent-review procedure.
3. **Selection → Training → employment timing — requires canonical reconciliation, NOT silently changed.** `01 Domains/Shared Domains/PERSON_CONTINUITY_001.md` §1 and §6 describe Candidate → Employee → Training. `01 Domains/Shared Domains/Selection/SELECTION_PILL_ASSESSMENT_AND_TRAINING_READINESS_001.md` §6 describes handoff at hiring; `Selection/SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md` §7 also refers to Employee identity. The Product Owner has subsequently described an operational workflow Candidate → Selection → Registry Trainee → Training → manager-confirmed Employee, preserving one Registry identity. **Its formal canonical approval source has NOT been verified in this repository audit**. Treat this as a discrepancy requiring authoritative source verification, not as a replacement approved by this report. Distinguish the general cross-industry Selection/Training service boundary from the restaurant-specific runtime workflow.
4. **Project status may be stale — verification required.** `PROJECT_STATE.md` records historical Training readiness/test results and Mount Dora onboarding status. Treat these as dated claims, not live AWS evidence. Verify against current services, releases and migrations before changing operational status assertions.
5. **Multisite invariants exist already.** `01 Domains/Business Domain/Restaurant/Restaurant Semantic Model.md` §3 and §8 establish one Rome's Flavours Brand, two Locations, and location-specific assignments without duplicating Employee identity. `00 Core/ArchitecturePrinciples.md` and `00 Core/ImplementationGuidelines.md` require canonical data ownership and connector mapping. Do not rewrite these principles or invent new blocking controls.
6. **Integration verification remains open in historical evidence.** [`verify-later.txt` at integration commit `7a4a126e`](https://github.com/RomesFlavours/RF-One/blob/7a4a126e721024fed32751190330850312772022/03%20Software/Infrastructure/integration-2026-11-20/verify-later.txt) lists compatibility and migration checks. This path is **external to the `main` PR #2 tree** and is not proof of present production status. Do not mistake a documentation-only change for runtime verification.

## Scope of PR #2 (this working branch)

- Modified: `CLAUDE.md` — Claude role, canonical-source reading, and explicit approval gate for design and behavioral changes.
- Added: `AGENTS.md` — Codex reviewer instructions and immutable external evidence reference.
- Modified: `README.md` — entrypoints and correction of the inaccurate blanket README coverage claim (`07 Tasks/README.md` is absent).
- Added: this audit report.
- **Not modified:** canonical Core/Domain decisions, Selection/Training lifecycle specifications, runtime software, database, migrations, AWS, the `main` base branch, or Shelbi's integration branch.

## Required next checks before canonical changes

- Verify the latest approved Selection → Training → Registry workflow and locate its source of authority; reconcile all affected canonical references in one coherent change.
- Verify latest multisite requirements against current implementation and document only confirmed gaps.
- Verify live AWS state independently before updating `PROJECT_STATE.md`.
- Obtain independent Codex review of this documentation branch and Product Owner approval before merge. No deploy is implied.
